"""Disk-DB-backed native multicam creation for DaVinci Resolve 20+ project libraries."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import sqlite3
import sys
from typing import Any

from ..errors import ValidationError
from ..multicam_support import (
    MAX_SUPPORTED_ANGLE_COUNT,
    PROJECT_LOCAL_REFERENCE_REQUIRED_ANGLE_COUNTS,
    support_tier_for_angle_count,
)
from ._native_multicam_db.blob_codec import (
    _decode_optional_bytes,
    _decode_rate_blob,
    _encode_media_timemap_ba,
    _encode_sequence_media_extents,
    _extract_blob_uuids,
    _normalized_selector_idx,
    _optional_float,
    _ordered_selector_values,
    _remap_sequence_fields_blob,
    _replace_utf16_uuid,
    _selector_signature,
)
from ._native_multicam_db.binding_inspection import (
    _inspect_multicam_bindings_with_cursor as _binding_inspection_with_cursor,
    _validate_created_multicam_binding as _binding_validate_created_multicam_binding,
    inspect_multicam_bindings as _binding_inspection_inspect_multicam_bindings,
    list_multicam_binding_summaries as _binding_inspection_list_multicam_binding_summaries,
)
from ._native_multicam_db.reference_loader import (
    _build_reference_template_payload as _reference_loader_build_template_payload,
    _decoded_template_blob_lengths as _reference_loader_decoded_template_blob_lengths,
    _load_reference_multicam_fixture_parts,
    _template_selector_values as _reference_loader_template_selector_values,
)
from ._native_multicam_db.template_loader import (
    _load_matching_project_reference as _template_loader_load_matching_project_reference,
    _matching_reference_is_acceptable as _template_loader_matching_reference_is_acceptable,
)
from ._native_multicam_db.reference_shape import (
    _can_fallback_to_packaged_reference_after_rejections as _reference_shape_can_fallback_to_packaged_reference_after_rejections,
    _requires_calibrated_project_reference as _reference_shape_requires_calibrated_project_reference,
    _requires_local_reference as _reference_shape_requires_local_reference,
    _validate_reference_video_selector_shape as _reference_shape_validate_reference_video_selector_shape,
    _video_selector_mapping_from_item_templates as _reference_shape_video_selector_mapping_from_item_templates,
    _video_selector_mapping_from_source_templates as _reference_shape_video_selector_mapping_from_source_templates,
)
from ._native_multicam_db import create_multicam as _create_multicam
from ._native_multicam_db import convert as _convert
from ._native_multicam_db import angle_edit as _angle_edit
from ._native_multicam_db import match_frame as _match_frame
from ._native_multicam_db import flatten as _flatten
from ._native_multicam_db import recover_timing as _recover_timing
from ._native_multicam_db import replace_audio as _replace_audio
from ._native_multicam_db import replace_video as _replace_video
from ._native_multicam_db import reorder_angles as _reorder_angles
from ._native_multicam_db import seed_timeline as _seed_timeline
from ._native_multicam_db import stale_targets as _stale_targets
from ._native_multicam_db import start_timecode as _start_timecode
from ._native_multicam_db import strip_audio as _strip_audio
from ._native_multicam_db.source_rows import resolve_source_media_rows as _source_rows_resolve_source_media_rows
from ._native_multicam_db.timing import (
    _derive_multicam_duration as _timing_derive_multicam_duration,
    _derive_multicam_fps as _timing_derive_multicam_fps,
    _load_source_templates as _timing_load_source_templates,
    _resolve_angle_timing as _timing_resolve_angle_timing,
)
from .native_multicam_audit import AuditReferenceConfig, build_multicam_reference_audit

_COMPAT_EXPORTS = (
    support_tier_for_angle_count,
    _encode_media_timemap_ba,
    _encode_sequence_media_extents,
    _extract_blob_uuids,
    _optional_float,
    _remap_sequence_fields_blob,
    _replace_utf16_uuid,
    _timing_load_source_templates,
    _timing_resolve_angle_timing,
    AuditReferenceConfig,
    build_multicam_reference_audit,
)

_FIXTURE_PACKAGE = "cutagent_cli.fixtures"
_FIXTURE_NAME = "native_multicam_reference_resolve20x.json"
_FIXTURE_NAME_BY_ANGLE_COUNT = {
    3: "native_multicam_reference_3cam_resolve20x.json",
    4: "native_multicam_reference_4cam_resolve20x.json",
    5: "native_multicam_reference_5cam_resolve20x.json",
    6: "native_multicam_reference_6cam_resolve20x.json",
}
_TEMP_BIN_PREFIX = "__CutAgent Native Multicam "
_TOOL_GENERATED_MULTICAM_NAME_PREFIXES = (
    "CutAgent Live Verify ",
    "CutAgent MC ",
    "Checklist ",
    "Multicam Generic ",
    "Podcast Auto Edit ",
    "__CutAgent ",
)
_PREFERRED_LOCAL_MULTICAM_REFERENCE_NAMES = (
    "native-4-multicam",
    "manualne-3-multicam",
    "multicam_3-native",
    "multicam-native",
)
_SPARSE_LOCAL_MULTICAM_REFERENCE_NAMES = (
    "multicam_3-native",
    "multicam-native",
)
NATIVE_ANGLE_SYNC_MODES = ("in", "out", "timecode", "sound", "marker")
DEFAULT_NATIVE_ANGLE_SYNC_MODE = "in"
MULTICAM_REFERENCE_SOURCE_POLICIES = ("packaged_fixture", "project_local_reference", "auto")
DEFAULT_MULTICAM_REFERENCE_SOURCE_POLICY = "packaged_fixture"
_NATIVE_PATH_CLASS = type(Path())


def _default_disk_db_projects_roots() -> list[Path]:
    if os.name != "nt":
        return [
            _NATIVE_PATH_CLASS.home()
            / "Library"
            / "Application Support"
            / "Blackmagic Design"
            / "DaVinci Resolve"
            / "Resolve Project Library"
            / "Resolve Projects"
            / "Users"
        ]

    roaming_root = _NATIVE_PATH_CLASS(
        os.environ.get("APPDATA") or (_NATIVE_PATH_CLASS.home() / "AppData" / "Roaming")
    )
    return [
        roaming_root
        / "Blackmagic Design"
        / "DaVinci Resolve"
        / "Support"
        / "Resolve Project Library"
        / "Resolve Projects"
        / "Users"
    ]


def _ops_module():
    return sys.modules[__name__]


def normalize_native_angle_sync_mode(
    value: Any,
    *,
    details_key: str = "sync",
    supported_key: str = "supported_syncs",
) -> str:
    sync_mode = str(value or DEFAULT_NATIVE_ANGLE_SYNC_MODE).strip().lower()
    if sync_mode not in NATIVE_ANGLE_SYNC_MODES:
        raise ValidationError(
            "Unsupported native multicam sync strategy.",
            details={
                details_key: sync_mode,
                supported_key: list(NATIVE_ANGLE_SYNC_MODES),
            },
        )
    return sync_mode


def normalize_multicam_reference_source_policy(
    value: Any,
    *,
    details_key: str = "reference_source",
    supported_key: str = "supported_reference_sources",
) -> str:
    raw = str(value or DEFAULT_MULTICAM_REFERENCE_SOURCE_POLICY).strip().lower().replace("-", "_")
    aliases = {
        "packaged": "packaged_fixture",
        "fixture": "packaged_fixture",
        "packaged_fixture": "packaged_fixture",
        "project": "project_local_reference",
        "project_local": "project_local_reference",
        "local": "project_local_reference",
        "project_local_reference": "project_local_reference",
        "auto": "auto",
        "prefer_project_local": "auto",
    }
    policy = aliases.get(raw)
    if policy is None:
        raise ValidationError(
            "Unsupported multicam reference source policy.",
            details={
                details_key: raw,
                supported_key: list(MULTICAM_REFERENCE_SOURCE_POLICIES),
            },
        )
    return policy


def _is_preferred_local_reference_name(name: str) -> bool:
    normalized = str(name or "").strip()
    return normalized.startswith("Manual Gold ") or normalized in _PREFERRED_LOCAL_MULTICAM_REFERENCE_NAMES


@dataclass(frozen=True)
class ReferenceMulticamFixture:
    schema_family: str
    fixture_version: int
    angle_count: int | None
    fields_blob: bytes | None
    frame_rate: bytes | None
    video_metadata: bytes | None
    virtual_audio_tracks: bytes | None
    cur_playhead_position: str | None
    audio_source: str | None
    slate_tc: str | None
    sequence_frame_rate: bytes | None
    sequence_resolution: bytes | None
    sequence_media_extents: bytes | None
    sequence_fields_blob: bytes | None
    sequence_render_cache: bytes | None
    sequence_aux_render_cache: bytes | None
    item_start: str
    item_duration: str
    track_templates: list[dict[str, Any]]
    item_templates: list[dict[str, Any]]
    preserve_reference_shape: bool = False


@dataclass(frozen=True)
class ResolvedDbMediaRow:
    media_id: str
    name: str
    folder_id: str | None
    folder_path: str
    db_type: str
    source_path: str | None = None
    duration_frames: int | None = None
    fps: float | None = None
    cur_playhead_position: str | None = None
    slate_tc: str | None = None
    media_start_time: float | None = None
    mark_in_frame: int | None = None
    mark_out_frame: int | None = None
    audio_mapping: dict[str, Any] | None = None


@dataclass(frozen=True)
class TrackTemplate:
    subtype: int
    fields_blob: bytes | None
    user_defined_name: str | None = None


@dataclass(frozen=True)
class ItemTemplate:
    is_placeholder: bool
    media_file_path: str | None
    media_timemap_ba: bytes | None
    preconform_media_extents: bytes | None
    media_frame_rate: bytes | None
    virtual_audio_track_ba: bytes | None
    fields_blob: bytes | None
    in_value: str | None
    media_track_idx: int | None
    current_selector_idx: int | None
    media_start_time: float | None = None


@dataclass(frozen=True)
class SourceTemplates:
    video_track: TrackTemplate
    audio_track: TrackTemplate
    video_item: ItemTemplate
    audio_item: ItemTemplate


@dataclass(frozen=True)
class AngleTimingSeed:
    item_start_frame: int
    media_start_time_seconds: float
    item_duration_frames: int
    media_timemap_duration_frames: int
    sequence_extents_start_frame: int
    sequence_extents_duration_frames: int
    source_in_frame: int = 0


_VIDEO_TRACK_FIELDS_BLOB = bytes.fromhex("000000010000000100000012004E0075006D004C00610079006500720073000000020000000000")
_AUDIO_TRACK_FIELDS_BLOB = bytes.fromhex(
    "000000010000000200000012004E0075006D004C006100790065007200730000000200000000000000003E004500780063006C0075006400650054007200610063006B00460072006F006D00530065007100750065006E0063006500430061006300680069006E0067000000010001"
)
_MEDIA_TIMEMAP_BA = bytes.fromhex("02401FD55555555555")
_VIDEO_PRECONFORM_MEDIA_EXTENTS = bytes.fromhex("00000100000030C20000010000003042")
_AUDIO_VIRTUAL_AUDIO_TRACK_BA = bytes.fromhex(
    "000000010000000200000014004300680061006E006E0065006C0073004200410000000C000000000C000000020000000100004001000000120041007500640069006F0054007900700065000000020000000001"
)
_VIDEO_ITEM_FIELDS_BLOB = bytes.fromhex("0000000200000017800A02200112100000000000000005FFFFFFFFFFFFFFFF")
_AUDIO_ITEM_FIELDS_BLOB = bytes.fromhex(
    "00000002000000538128B52FFD20694D020022461017A037AD018F46BA895D5DF07BFB79EF3E895747B4692D058044113095E7719944EF5522AFBD698A68CF4213B5E879072D6A1226CD132968F8FAD1287EA8544B050100670E09"
)


def load_reference_multicam_fixture(angle_count: int | None = None) -> ReferenceMulticamFixture:
    """Load the canonical DaVinci Resolve 20+ multicam DB reference fixture from the repo."""
    fixture_name, payload, multicam_media, sequence, ti_item = _load_reference_multicam_fixture_parts(
        angle_count=angle_count,
        fixture_package=_FIXTURE_PACKAGE,
        default_fixture_name=_FIXTURE_NAME,
        fixture_name_by_angle_count=_FIXTURE_NAME_BY_ANGLE_COUNT,
    )

    return ReferenceMulticamFixture(
        schema_family=str(payload.get("schema_family") or "resolve_20x"),
        fixture_version=int(payload.get("fixture_version") or 1),
        angle_count=(
            int(payload.get("angle_count"))
            if payload.get("angle_count") not in (None, "")
            else angle_count
        ),
        fields_blob=_decode_optional_bytes(multicam_media.get("fields_blob_b64")),
        frame_rate=_decode_optional_bytes(multicam_media.get("frame_rate_b64")),
        video_metadata=_decode_optional_bytes(multicam_media.get("video_metadata_b64")),
        virtual_audio_tracks=_decode_optional_bytes(multicam_media.get("virtual_audio_tracks_b64")),
        cur_playhead_position=(
            str(multicam_media.get("cur_playhead_position")).strip()
            if multicam_media.get("cur_playhead_position") not in (None, "")
            else None
        ),
        audio_source=(
            str(multicam_media.get("audio_source")).strip()
            if multicam_media.get("audio_source") not in (None, "")
            else None
        ),
        slate_tc=(
            str(multicam_media.get("slate_tc")).strip()
            if multicam_media.get("slate_tc") not in (None, "")
            else None
        ),
        sequence_frame_rate=_decode_optional_bytes(sequence.get("frame_rate_b64")),
        sequence_resolution=_decode_optional_bytes(sequence.get("resolution_b64")),
        sequence_media_extents=_decode_optional_bytes(sequence.get("media_extents_b64")),
        sequence_fields_blob=_decode_optional_bytes(sequence.get("fields_blob_b64")),
        sequence_render_cache=_decode_optional_bytes(sequence.get("render_cache_b64")),
        sequence_aux_render_cache=_decode_optional_bytes(sequence.get("aux_render_cache_b64")),
        item_start=str(ti_item.get("start") or "86400"),
        item_duration=str(ti_item.get("duration") or "192"),
        track_templates=list(payload.get("track_templates") or []),
        item_templates=list(payload.get("item_templates") or []),
    )


def resolve_disk_project_db_path(
    *,
    project_name: str,
    projects_root: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    """Resolve the on-disk Project.db path for a local Disk database project."""
    normalized_project_name = str(project_name or "").strip()
    if not normalized_project_name:
        raise ValidationError(
            "Cannot resolve Project.db path without an open project name.",
            details={"reason": "missing_project_name"},
        )

    roots = [_NATIVE_PATH_CLASS(projects_root).expanduser()] if projects_root else _default_disk_db_projects_roots()
    project_name_path = _NATIVE_PATH_CLASS(normalized_project_name)
    if (
        normalized_project_name in {".", ".."}
        or project_name_path.is_absolute()
        or project_name_path.name != normalized_project_name
    ):
        raise ValidationError(
            "Project name must be a single local project folder name.",
            details={
                "reason": "invalid_project_name",
                "project_name": normalized_project_name,
            },
        )

    search_pattern = "*/Projects"
    candidates = sorted(
        str(projects_dir / normalized_project_name / "Project.db")
        for root in roots
        for projects_dir in root.glob(search_pattern)
        if (projects_dir / normalized_project_name / "Project.db").is_file()
    )
    if len(candidates) == 1:
        return {
            "project_name": normalized_project_name,
            "project_db_path": candidates[0],
            "candidates": candidates,
        }
    if not candidates:
        raise ValidationError(
            "Could not locate Project.db for the current Disk database project.",
            details={
                "reason": "project_db_not_found",
                "project_name": normalized_project_name,
                "search_root": str(roots[0]) if len(roots) == 1 else os.pathsep.join(str(root) for root in roots),
                "search_roots": [str(root) for root in roots],
                "search_pattern": search_pattern,
                "candidates": [],
            },
        )
    raise ValidationError(
        "Project.db path is ambiguous for the current Disk database project.",
        details={
            "reason": "ambiguous_project_db_path",
            "project_name": normalized_project_name,
            "search_root": str(roots[0]) if len(roots) == 1 else os.pathsep.join(str(root) for root in roots),
            "search_roots": [str(root) for root in roots],
            "search_pattern": search_pattern,
            "candidates": candidates,
        },
    )


def _row_to_dict(cursor: sqlite3.Cursor, row: tuple[Any, ...]) -> dict[str, Any]:
    return {cursor.description[index][0]: value for index, value in enumerate(row)}


def _fetch_folder_paths(cursor: sqlite3.Cursor) -> dict[str, str]:
    rows = cursor.execute(
        """
        SELECT
            Sm2MpFolder_id,
            Name,
            MpFolder,
            Sm2MpFolder_Owner_id
        FROM Sm2MpFolder
        """
    ).fetchall()
    folder_rows = {
        str(row[0]): {
            "id": str(row[0]),
            "name": str(row[1] or ""),
            "parent": str(row[2] or row[3] or "") or None,
        }
        for row in rows
        if row[0]
    }

    cache: dict[str, str] = {}

    def build_path(folder_id: str, stack: set[str] | None = None) -> str:
        if folder_id in cache:
            return cache[folder_id]
        stack = stack or set()
        if folder_id in stack:
            return folder_rows[folder_id]["name"]
        stack.add(folder_id)
        folder = folder_rows[folder_id]
        name = folder["name"]
        parent_id = folder["parent"]
        if parent_id and parent_id in folder_rows and parent_id != folder_id:
            parent_path = build_path(parent_id, stack)
            cache[folder_id] = f"{parent_path}/{name}" if parent_path else name
        else:
            cache[folder_id] = name
        stack.remove(folder_id)
        return cache[folder_id]

    for folder_id in folder_rows:
        build_path(folder_id)
    return cache


def _is_temp_bin_folder_path(folder_path: str | None) -> bool:
    normalized = str(folder_path or "")
    return f"/{_TEMP_BIN_PREFIX}" in normalized or normalized.startswith(_TEMP_BIN_PREFIX)


def _next_db_saved_time(cursor: sqlite3.Cursor) -> int:
    max_saved_time = 0
    for table_name in (
        "Sm2Sequence",
        "Sm2SequenceContainer",
        "ListMgt::LmVersionTable",
        "BtLockableBlob",
    ):
        try:
            row = cursor.execute(f'SELECT COALESCE(MAX("DbSavedTime"), 0) FROM "{table_name}"').fetchone()
        except sqlite3.OperationalError:
            continue
        value = row[0] if row else 0
        try:
            max_saved_time = max(max_saved_time, int(value or 0))
        except (TypeError, ValueError):
            continue
    return max_saved_time + 1


def resolve_source_media_rows(
    project_db_path: str,
    *,
    resolved_angles: list[dict[str, Any]],
) -> list[ResolvedDbMediaRow]:
    """Resolve source Sm2MpMedia rows for the already-resolved media-pool angle clips."""
    return _source_rows_resolve_source_media_rows(
        project_db_path,
        resolved_angles=resolved_angles,
        resolved_db_media_row_cls=ResolvedDbMediaRow,
        row_to_dict_fn=_row_to_dict,
        temp_bin_prefix=_TEMP_BIN_PREFIX,
    )


def _derive_multicam_fps(reference: ReferenceMulticamFixture, source_rows: list[ResolvedDbMediaRow]) -> float:
    return _timing_derive_multicam_fps(reference, source_rows, _decode_rate_blob)


def _derive_multicam_duration(reference: ReferenceMulticamFixture, source_rows: list[ResolvedDbMediaRow]) -> int:
    return _timing_derive_multicam_duration(reference, source_rows)


def _build_reference_template_payload(
    *,
    db_type: str,
    track_index: int | None,
    is_placeholder: bool,
    media_file_path: str | None,
    media_timemap_ba: bytes | None,
    preconform_media_extents: bytes | None,
    media_frame_rate: bytes | None,
    virtual_audio_track_ba: bytes | None,
    fields_blob: bytes | None,
    in_value: str | None,
    media_track_idx: int | None,
    current_selector_idx: int | None,
    media_start_time: float | None = None,
) -> dict[str, Any]:
    return _reference_loader_build_template_payload(
        db_type=db_type,
        track_index=track_index,
        is_placeholder=is_placeholder,
        media_file_path=media_file_path,
        media_timemap_ba=media_timemap_ba,
        preconform_media_extents=preconform_media_extents,
        media_frame_rate=media_frame_rate,
        virtual_audio_track_ba=virtual_audio_track_ba,
        fields_blob=fields_blob,
        in_value=in_value,
        media_track_idx=media_track_idx,
        current_selector_idx=current_selector_idx,
        media_start_time=media_start_time,
    )


def _decoded_template_blob_lengths(reference: ReferenceMulticamFixture) -> dict[str, list[int]]:
    return _reference_loader_decoded_template_blob_lengths(reference, _decode_optional_bytes)


def _template_selector_values(reference: ReferenceMulticamFixture) -> dict[str, list[int | None]]:
    return _reference_loader_template_selector_values(reference)


def _video_selector_mapping_from_item_templates(item_templates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return _reference_shape_video_selector_mapping_from_item_templates(
        item_templates,
        decode_optional_bytes_fn=_decode_optional_bytes,
        selector_signature_fn=_selector_signature,
    )


def _video_selector_mapping_from_source_templates(
    source_templates_by_index: list[SourceTemplates],
) -> list[dict[str, Any]]:
    return _reference_shape_video_selector_mapping_from_source_templates(
        source_templates_by_index,
        selector_signature_fn=_selector_signature,
    )


def _validate_reference_video_selector_shape(
    *,
    resolved_angle_count: int,
    expected_mapping: list[dict[str, Any]],
    actual_mapping: list[dict[str, Any]],
) -> dict[str, Any]:
    return _reference_shape_validate_reference_video_selector_shape(
        resolved_angle_count=resolved_angle_count,
        expected_mapping=expected_mapping,
        actual_mapping=actual_mapping,
        normalized_selector_idx_fn=_normalized_selector_idx,
        ordered_selector_values_fn=_ordered_selector_values,
    )


def _requires_local_reference(angle_count: int) -> bool:
    return _reference_shape_requires_local_reference(angle_count, max_supported_angle_count=MAX_SUPPORTED_ANGLE_COUNT)


def _requires_calibrated_project_reference(angle_count: int) -> bool:
    return _reference_shape_requires_calibrated_project_reference(
        angle_count,
        project_local_reference_required_angle_counts=PROJECT_LOCAL_REFERENCE_REQUIRED_ANGLE_COUNTS,
    )


def _can_fallback_to_packaged_reference_after_rejections(
    *,
    requested_angle_count: int,
    rejected_candidates: list[dict[str, Any]],
) -> bool:
    return _reference_shape_can_fallback_to_packaged_reference_after_rejections(
        requested_angle_count=requested_angle_count,
        rejected_candidates=rejected_candidates,
    )


def _matching_reference_is_acceptable(
    *,
    fallback: ReferenceMulticamFixture,
    candidate_name: str,
    candidate_fields_blob: bytes | None = None,
    track_templates: list[dict[str, Any]],
    item_templates: list[dict[str, Any]],
) -> dict[str, Any]:
    return _template_loader_matching_reference_is_acceptable(
        fallback=fallback,
        candidate_name=candidate_name,
        candidate_fields_blob=candidate_fields_blob,
        track_templates=track_templates,
        item_templates=item_templates,
        ops_module=_ops_module(),
    )


def _load_matching_project_reference(
    cursor: sqlite3.Cursor,
    *,
    source_rows: list[ResolvedDbMediaRow],
    excluded_name: str,
    fallback: ReferenceMulticamFixture,
) -> dict[str, Any]:
    return _template_loader_load_matching_project_reference(
        cursor,
        source_rows=source_rows,
        excluded_name=excluded_name,
        fallback=fallback,
        ops_module=_ops_module(),
    )


def _inspect_multicam_bindings_with_cursor(
    cursor: sqlite3.Cursor,
    *,
    multicam_media_id: str | None = None,
    multicam_name: str | None = None,
) -> dict[str, Any]:
    return _binding_inspection_with_cursor(
        cursor,
        multicam_media_id=multicam_media_id,
        multicam_name=multicam_name,
        row_to_dict_fn=_row_to_dict,
        selector_signature_fn=_selector_signature,
    )


def inspect_multicam_bindings(
    project_db_path: str,
    *,
    multicam_media_id: str | None = None,
    multicam_name: str | None = None,
) -> dict[str, Any]:
    return _binding_inspection_inspect_multicam_bindings(
        project_db_path,
        multicam_media_id=multicam_media_id,
        multicam_name=multicam_name,
        inspect_with_cursor_fn=_inspect_multicam_bindings_with_cursor,
    )


def list_multicam_binding_summaries(project_db_path: str) -> list[dict[str, Any]]:
    """List DB-backed native multicam clips available for inspection."""
    return _binding_inspection_list_multicam_binding_summaries(
        project_db_path,
        row_to_dict_fn=_row_to_dict,
    )


def _validate_created_multicam_binding(
    cursor: sqlite3.Cursor,
    *,
    multicam_media_id: str,
    expected_source_rows: list[ResolvedDbMediaRow],
    expected_source_angle_labels: list[str] | None = None,
    expected_video_selector_mapping: list[dict[str, Any]],
    expected_source_item_timing: list[dict[str, int]] | None = None,
) -> dict[str, Any]:
    return _binding_validate_created_multicam_binding(
        cursor,
        multicam_media_id=multicam_media_id,
        expected_source_rows=expected_source_rows,
        expected_source_angle_labels=expected_source_angle_labels,
        expected_source_item_timing=expected_source_item_timing,
        expected_video_selector_mapping=expected_video_selector_mapping,
        inspect_with_cursor_fn=_inspect_multicam_bindings_with_cursor,
        normalized_selector_idx_fn=_normalized_selector_idx,
    )


def _select_representative_item_row(
    cursor: sqlite3.Cursor,
    *,
    media_id: str,
    item_db_type: str,
    preferred_start: str,
    preferred_duration: str,
) -> dict[str, Any] | None:
    return _create_multicam._select_representative_item_row(
        cursor,
        media_id=media_id,
        item_db_type=item_db_type,
        preferred_start=preferred_start,
        preferred_duration=preferred_duration,
        ops_module=_ops_module(),
    )


def _default_source_templates(
    source_row: ResolvedDbMediaRow,
    reference: ReferenceMulticamFixture,
    *,
    multicam_duration_frames: int,
    multicam_fps: float,
) -> SourceTemplates:
    return _create_multicam._default_source_templates(
        source_row,
        reference,
        multicam_duration_frames=multicam_duration_frames,
        multicam_fps=multicam_fps,
        ops_module=_ops_module(),
    )


def _reference_item_template(
    reference: ReferenceMulticamFixture,
    *,
    item_db_type: str,
    angle_index: int,
    fallback: ItemTemplate,
) -> ItemTemplate:
    return _create_multicam._reference_item_template(
        reference,
        item_db_type=item_db_type,
        angle_index=angle_index,
        fallback=fallback,
        ops_module=_ops_module(),
    )


def _reference_track_template(
    reference: ReferenceMulticamFixture,
    *,
    track_type: int,
    angle_index: int,
    fallback: TrackTemplate,
) -> TrackTemplate:
    return _create_multicam._reference_track_template(
        reference,
        track_type=track_type,
        angle_index=angle_index,
        fallback=fallback,
        ops_module=_ops_module(),
    )


def _coalesce_template_value(primary: Any, fallback: Any) -> Any:
    return _create_multicam._coalesce_template_value(primary, fallback)


def _table_columns(cursor: sqlite3.Cursor, table_name: str) -> set[str]:
    return _create_multicam._table_columns(cursor, table_name)


def _load_source_templates(
    cursor: sqlite3.Cursor,
    *,
    source_row: ResolvedDbMediaRow,
    reference: ReferenceMulticamFixture,
    angle_index: int,
    multicam_duration_frames: int,
    multicam_fps: float,
) -> SourceTemplates:
    return _create_multicam._load_source_templates(
        cursor,
        source_row=source_row,
        reference=reference,
        angle_index=angle_index,
        multicam_duration_frames=multicam_duration_frames,
        multicam_fps=multicam_fps,
        ops_module=_ops_module(),
    )


def _resolve_angle_timing(
    *,
    source_row: ResolvedDbMediaRow,
    templates: SourceTemplates,
    reference: ReferenceMulticamFixture,
    start_offset_frames: int,
    media_start_time_base_seconds: float | None = None,
    source_start_offsets_mode: str = "additive",
    multicam_duration_frames: int,
    multicam_fps: float,
) -> AngleTimingSeed:
    return _create_multicam._resolve_angle_timing(
        source_row=source_row,
        templates=templates,
        reference=reference,
        start_offset_frames=start_offset_frames,
        media_start_time_base_seconds=media_start_time_base_seconds,
        source_start_offsets_mode=source_start_offsets_mode,
        multicam_duration_frames=multicam_duration_frames,
        multicam_fps=multicam_fps,
        ops_module=_ops_module(),
    )


def create_multicam_clip(
    *,
    project_db_path: str,
    multicam_name: str,
    source_rows: list[ResolvedDbMediaRow],
    source_angle_labels: list[str] | None = None,
    angle_names: dict[str, str] | None = None,
    source_item_timing: list[dict[str, int | None]] | None = None,
    source_layout: str = "contiguous",
    sync_mode: str = DEFAULT_NATIVE_ANGLE_SYNC_MODE,
    source_cur_playhead_positions: list[int | str | None] | None = None,
    source_start_offsets_frames: list[int] | None = None,
    source_start_offsets_mode: str = "additive",
    audio_mode: str = "source_audio_channels",
    reference_audio_angle: str | None = None,
    start_timecode: str | None = None,
    fixture: ReferenceMulticamFixture | None = None,
    reference_source: str = DEFAULT_MULTICAM_REFERENCE_SOURCE_POLICY,
    preferred_duration_frames: int | None = None,
    create_backup: bool = True,
) -> dict[str, Any]:
    """Write a native multicam clip directly into a DaVinci Resolve Disk Project.db."""
    return _create_multicam.create_multicam_clip(
        project_db_path=project_db_path,
        multicam_name=multicam_name,
        source_rows=source_rows,
        source_angle_labels=source_angle_labels,
        angle_names=angle_names,
        source_item_timing=source_item_timing,
        source_layout=source_layout,
        sync_mode=sync_mode,
        source_cur_playhead_positions=source_cur_playhead_positions,
        source_start_offsets_frames=source_start_offsets_frames,
        source_start_offsets_mode=source_start_offsets_mode,
        audio_mode=audio_mode,
        reference_audio_angle=reference_audio_angle,
        start_timecode=start_timecode,
        fixture=fixture,
        reference_source=reference_source,
        preferred_duration_frames=preferred_duration_frames,
        create_backup=create_backup,
        ops_module=_ops_module(),
    )


def plan_multicam_angle_edit(project_db_path: str, **kwargs: Any) -> dict[str, Any]:
    return _angle_edit.plan_multicam_angle_edit(project_db_path, **kwargs)


def edit_multicam_angle(conn: Any, **kwargs: Any) -> dict[str, Any]:
    return _angle_edit.edit_multicam_angle(conn, **kwargs)


def plan_multicam_start_timecode(project_db_path: str, **kwargs: Any) -> dict[str, Any]:
    return _start_timecode.plan_multicam_start_timecode(project_db_path, **kwargs)


def set_multicam_start_timecode(conn: Any, **kwargs: Any) -> dict[str, Any]:
    return _start_timecode.set_multicam_start_timecode(conn, **kwargs)


def match_multicam_frame(project_db_path: str, **kwargs: Any) -> dict[str, Any]:
    return _match_frame.match_multicam_frame(project_db_path, **kwargs)


def match_timeline_multicam_frame(project_db_path: str, **kwargs: Any) -> dict[str, Any]:
    return _match_frame.match_timeline_multicam_frame(project_db_path, **kwargs)


def flatten_multicam_timeline(conn: Any, **kwargs: Any) -> dict[str, Any]:
    return _flatten.flatten_multicam_timeline(conn, **kwargs)


def plan_multicam_flatten(project_db_path: str, **kwargs: Any) -> dict[str, Any]:
    return _flatten.plan_multicam_flatten(project_db_path, **kwargs)


def plan_multicam_convert(project_db_path: str, **kwargs: Any) -> dict[str, Any]:
    return _convert.plan_multicam_convert(project_db_path, **kwargs)


def convert_to_multicam(conn: Any, **kwargs: Any) -> dict[str, Any]:
    return _convert.convert_to_multicam(conn, **kwargs)


def inspect_multicam_create_preflight(
    project_db_path: str,
    *,
    multicam_name: str,
    timeline_name: str,
    live_multicam_candidates: list[dict[str, Any]] | None = None,
    live_timeline_names: list[str] | set[str] | None = None,
) -> dict[str, Any]:
    return _stale_targets.inspect_multicam_create_preflight(
        project_db_path,
        multicam_name=multicam_name,
        timeline_name=timeline_name,
        live_multicam_candidates=live_multicam_candidates,
        live_timeline_names=live_timeline_names,
    )


def cleanup_stale_multicam_create_targets(
    project_db_path: str,
    *,
    preflight: dict[str, Any],
    backup_path: str | None = None,
) -> dict[str, Any]:
    return _stale_targets.cleanup_stale_multicam_create_targets(
        project_db_path,
        preflight=preflight,
        backup_path=backup_path,
    )


def plan_multicam_embedded_audio_strip(
    project_db_path: str,
    *,
    multicam_name: str | None = None,
    media_id: str | None = None,
    sequence_id: str | None = None,
    allow_missing_audio: bool = False,
) -> dict[str, Any]:
    """Inspect a native multicam embedded-audio strip without mutating Project.db."""
    return _strip_audio.plan_multicam_embedded_audio_strip(
        project_db_path,
        multicam_name=multicam_name,
        media_id=media_id,
        sequence_id=sequence_id,
        allow_missing_audio=allow_missing_audio,
    )


def normalize_multicam_audio_replacement_settings(raw: Any) -> dict[str, Any] | None:
    """Normalize a structured program_audio block for native multicam internals."""
    return _replace_audio.normalize_multicam_audio_replacement_settings(raw)


def plan_multicam_audio_replacement(
    project_db_path: str,
    *,
    multicam_name: str | None = None,
    media_id: str | None = None,
    sequence_id: str | None = None,
    audio_sources: list[dict[str, Any]],
    audio_angle_map: dict[str, str],
    angle_order: list[str] | None = None,
    offsets: dict[str, int] | None = None,
    unmapped_audio: str = "keep",
    empty_angle_indices: list[int] | None = None,
) -> dict[str, Any]:
    """Inspect native multicam internal audio replacement without mutating Project.db."""
    return _replace_audio.plan_multicam_audio_replacement(
        project_db_path,
        multicam_name=multicam_name,
        media_id=media_id,
        sequence_id=sequence_id,
        audio_sources=audio_sources,
        audio_angle_map=audio_angle_map,
        angle_order=angle_order,
        offsets=offsets,
        unmapped_audio=unmapped_audio,
        empty_angle_indices=empty_angle_indices,
    )


def plan_multicam_timing_recovery(
    project_db_path: str,
    *,
    source_specs: list[dict[str, Any]] | None,
    multicam_name: str | None = None,
    media_id: str | None = None,
    sequence_id: str | None = None,
    apply_timemap: bool = False,
    apply_source_start_tc: bool = False,
    apply_media_extents: bool = False,
    verify_reopen: bool = False,
    conn=None,
) -> dict[str, Any]:
    """Inspect a native multicam timing recovery plan without mutating Project.db."""
    return _recover_timing.plan_multicam_timing_recovery(
        project_db_path,
        source_specs=source_specs,
        multicam_name=multicam_name,
        media_id=media_id,
        sequence_id=sequence_id,
        apply_timemap=apply_timemap,
        apply_source_start_tc=apply_source_start_tc,
        apply_media_extents=apply_media_extents,
        verify_reopen=verify_reopen,
        conn=conn,
        ops_module=_ops_module(),
    )


def plan_multicam_angle_reorder(
    project_db_path: str,
    *,
    multicam_name: str | None = None,
    media_id: str | None = None,
    sequence_id: str | None = None,
    angle_order: list[str] | None = None,
    rename_tracks: bool = True,
    include_audio: bool = True,
    strict: bool = True,
) -> dict[str, Any]:
    """Inspect a native multicam angle reorder without mutating Project.db."""
    return _reorder_angles.plan_multicam_angle_reorder(
        project_db_path,
        multicam_name=multicam_name,
        media_id=media_id,
        sequence_id=sequence_id,
        angle_order=angle_order,
        rename_tracks=rename_tracks,
        include_audio=include_audio,
        strict=strict,
    )


def plan_multicam_timeline_seed(
    conn: Any,
    *,
    project_db_path: str,
    multicam_name: str | None = None,
    media_id: str | None = None,
    folder: str | None = None,
    timeline_name: str | None = None,
    record_frame: str | None = None,
    absolute_record_frame: int | None = None,
    require_empty: bool = False,
    reset_first: bool = False,
) -> dict[str, Any]:
    """Inspect a native multicam timeline seed without mutating DaVinci Resolve."""
    return _seed_timeline.plan_multicam_timeline_seed(
        conn,
        project_db_path=project_db_path,
        multicam_name=multicam_name,
        media_id=media_id,
        folder=folder,
        timeline_name=timeline_name,
        record_frame=record_frame,
        absolute_record_frame=absolute_record_frame,
        require_empty=require_empty,
        reset_first=reset_first,
    )


def strip_multicam_embedded_audio(
    conn: Any,
    *,
    multicam_name: str | None = None,
    media_id: str | None = None,
    sequence_id: str | None = None,
    allow_missing_audio: bool = False,
) -> dict[str, Any]:
    """Strip audio tracks/items from a native multicam sequence via Disk Project.db."""
    return _strip_audio.strip_multicam_embedded_audio(
        conn,
        multicam_name=multicam_name,
        media_id=media_id,
        sequence_id=sequence_id,
        allow_missing_audio=allow_missing_audio,
    )


def replace_multicam_audio(
    conn: Any,
    *,
    multicam_name: str | None = None,
    media_id: str | None = None,
    sequence_id: str | None = None,
    audio_sources: list[dict[str, Any]],
    audio_angle_map: dict[str, str],
    angle_order: list[str] | None = None,
    offsets: dict[str, int] | None = None,
    unmapped_audio: str = "keep",
    empty_angle_indices: list[int] | None = None,
) -> dict[str, Any]:
    """Replace audio items inside a native multicam sequence via Disk Project.db."""
    return _replace_audio.replace_multicam_audio(
        conn,
        multicam_name=multicam_name,
        media_id=media_id,
        sequence_id=sequence_id,
        audio_sources=audio_sources,
        audio_angle_map=audio_angle_map,
        angle_order=angle_order,
        offsets=offsets,
        unmapped_audio=unmapped_audio,
        empty_angle_indices=empty_angle_indices,
    )


def plan_multicam_video_replacement(
    project_db_path: str,
    *,
    multicam_name: str | None = None,
    media_id: str | None = None,
    sequence_id: str | None = None,
    video_targets: list[dict[str, Any]],
    source_in_frames: dict[int, int] | None = None,
    start_frames: dict[int, int] | None = None,
    duration_frames: dict[int, int] | None = None,
    allow_short_source: bool = False,
) -> dict[str, Any]:
    """Inspect native multicam internal video replacement without mutating Project.db."""
    return _replace_video.plan_multicam_video_replacement(
        project_db_path,
        multicam_name=multicam_name,
        media_id=media_id,
        sequence_id=sequence_id,
        video_targets=video_targets,
        source_in_frames=source_in_frames,
        start_frames=start_frames,
        duration_frames=duration_frames,
        allow_short_source=allow_short_source,
    )


def replace_multicam_video(
    conn: Any,
    *,
    multicam_name: str | None = None,
    media_id: str | None = None,
    sequence_id: str | None = None,
    video_targets: list[dict[str, Any]],
    source_in_frames: dict[int, int] | None = None,
    start_frames: dict[int, int] | None = None,
    duration_frames: dict[int, int] | None = None,
    allow_short_source: bool = False,
) -> dict[str, Any]:
    """Replace video items inside a native multicam sequence via Disk Project.db."""
    return _replace_video.replace_multicam_video(
        conn,
        multicam_name=multicam_name,
        media_id=media_id,
        sequence_id=sequence_id,
        video_targets=video_targets,
        source_in_frames=source_in_frames,
        start_frames=start_frames,
        duration_frames=duration_frames,
        allow_short_source=allow_short_source,
    )


def recover_multicam_timing(
    conn: Any,
    *,
    source_specs: list[dict[str, Any]] | None,
    multicam_name: str | None = None,
    media_id: str | None = None,
    sequence_id: str | None = None,
    apply_timemap: bool = False,
    apply_source_start_tc: bool = False,
    apply_media_extents: bool = False,
    verify_reopen: bool = False,
) -> dict[str, Any]:
    """Recover native multicam timing fields through a guarded Disk-DB mutation."""
    return _recover_timing.recover_multicam_timing(
        conn,
        source_specs=source_specs,
        multicam_name=multicam_name,
        media_id=media_id,
        sequence_id=sequence_id,
        apply_timemap=apply_timemap,
        apply_source_start_tc=apply_source_start_tc,
        apply_media_extents=apply_media_extents,
        verify_reopen=verify_reopen,
        ops_module=_ops_module(),
    )


def reorder_multicam_angles(
    conn: Any,
    *,
    multicam_name: str | None = None,
    media_id: str | None = None,
    sequence_id: str | None = None,
    angle_order: list[str] | None = None,
    rename_tracks: bool = True,
    include_audio: bool = True,
    strict: bool = True,
) -> dict[str, Any]:
    """Reorder angle tracks/items inside a native multicam sequence via Disk Project.db."""
    return _reorder_angles.reorder_multicam_angles(
        conn,
        multicam_name=multicam_name,
        media_id=media_id,
        sequence_id=sequence_id,
        angle_order=angle_order,
        rename_tracks=rename_tracks,
        include_audio=include_audio,
        strict=strict,
    )


def seed_multicam_timeline(
    conn: Any,
    *,
    project_db_path: str,
    multicam_name: str | None = None,
    media_id: str | None = None,
    folder: str | None = None,
    timeline_name: str | None = None,
    record_frame: str | None = None,
    absolute_record_frame: int | None = None,
    require_empty: bool = False,
    reset_first: bool = False,
) -> dict[str, Any]:
    """Append a native multicam clip to V1 of a target timeline."""
    return _seed_timeline.seed_multicam_timeline(
        conn,
        project_db_path=project_db_path,
        multicam_name=multicam_name,
        media_id=media_id,
        folder=folder,
        timeline_name=timeline_name,
        record_frame=record_frame,
        absolute_record_frame=absolute_record_frame,
        require_empty=require_empty,
        reset_first=reset_first,
    )


def _write_multicam_embedded_audio_strip(
    cursor: sqlite3.Cursor,
    *,
    multicam_name: str | None = None,
    media_id: str | None = None,
    sequence_id: str | None = None,
    allow_missing_audio: bool = False,
) -> dict[str, Any]:
    return _strip_audio._write_multicam_embedded_audio_strip(
        cursor,
        multicam_name=multicam_name,
        media_id=media_id,
        sequence_id=sequence_id,
        allow_missing_audio=allow_missing_audio,
    )


def _write_multicam_audio_replacement(
    cursor: sqlite3.Cursor,
    *,
    project_db_path: str,
    multicam_name: str | None = None,
    media_id: str | None = None,
    sequence_id: str | None = None,
    audio_sources: list[dict[str, Any]],
    audio_angle_map: dict[str, str],
    angle_order: list[str] | None = None,
    offsets: dict[str, int] | None = None,
    unmapped_audio: str = "keep",
    empty_angle_indices: list[int] | None = None,
) -> dict[str, Any]:
    return _replace_audio._write_multicam_audio_replacement(
        cursor,
        project_db_path=project_db_path,
        multicam_name=multicam_name,
        media_id=media_id,
        sequence_id=sequence_id,
        audio_sources=audio_sources,
        audio_angle_map=audio_angle_map,
        angle_order=angle_order,
        offsets=offsets,
        unmapped_audio=unmapped_audio,
        empty_angle_indices=empty_angle_indices,
    )


def _write_multicam_video_replacement(
    cursor: sqlite3.Cursor,
    *,
    project_db_path: str,
    multicam_name: str | None = None,
    media_id: str | None = None,
    sequence_id: str | None = None,
    video_targets: list[dict[str, Any]],
    source_in_frames: dict[int, int] | None = None,
    start_frames: dict[int, int] | None = None,
    duration_frames: dict[int, int] | None = None,
    allow_short_source: bool = False,
) -> dict[str, Any]:
    return _replace_video._write_multicam_video_replacement(
        cursor,
        project_db_path=project_db_path,
        multicam_name=multicam_name,
        media_id=media_id,
        sequence_id=sequence_id,
        video_targets=video_targets,
        source_in_frames=source_in_frames,
        start_frames=start_frames,
        duration_frames=duration_frames,
        allow_short_source=allow_short_source,
    )


def _write_timeline_seed_reset(
    cursor: sqlite3.Cursor,
    *,
    timeline_name: str,
) -> dict[str, Any]:
    return _seed_timeline._write_timeline_seed_reset(cursor, timeline_name=timeline_name)


def _write_multicam_timing_recovery(
    cursor: sqlite3.Cursor,
    *,
    plan: dict[str, Any],
) -> dict[str, Any]:
    return _recover_timing._write_multicam_timing_recovery(
        cursor,
        plan=plan,
    )


def _write_multicam_angle_reorder(
    cursor: sqlite3.Cursor,
    *,
    multicam_name: str | None = None,
    media_id: str | None = None,
    sequence_id: str | None = None,
    angle_order: list[str] | None = None,
    rename_tracks: bool = True,
    include_audio: bool = True,
    strict: bool = True,
) -> dict[str, Any]:
    return _reorder_angles._write_multicam_angle_reorder(
        cursor,
        multicam_name=multicam_name,
        media_id=media_id,
        sequence_id=sequence_id,
        angle_order=angle_order,
        rename_tracks=rename_tracks,
        include_audio=include_audio,
        strict=strict,
    )


def _encode_recovery_media_timemap_ba(duration_frames: int, fps: float) -> bytes:
    return _recover_timing._encode_recovery_media_timemap_ba(duration_frames, fps)


def _encode_recovery_sequence_media_extents(start_frame: int, duration_frames: int, fps: float) -> bytes:
    return _recover_timing._encode_recovery_sequence_media_extents(start_frame, duration_frames, fps)


def _timecode_to_frames(value: str, fps: float) -> int:
    return _recover_timing._timecode_to_frames(value, fps)
