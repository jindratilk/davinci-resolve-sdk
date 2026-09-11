"""Native multicam podcast orchestration via transcript + DaVinci Resolve native routes."""

from __future__ import annotations

import base64
from dataclasses import asdict, replace
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from typing import Any

from ..errors import APICallFailed, CLIError, StaleDbMulticam, ValidationError
from ..output import set_execution_engine, set_recoverability, set_verification_status
from ..runtime_health import close_current_project_with_runtime_health, get_current_database_details
from ..state_contracts import project_is_closed_enough
from ..utils.timecode import frames_to_timecode, seconds_to_frames, timecode_to_seconds
from . import edit_ops, media_pool, native_multicam_db
from ._podcast_multicam.transcript import (
    SpeakerSegment,
    _coalesce_short_segments,
    _extract_ms,
    _extract_speaker,
    _merge_adjacent_segments,
    _normalize_token,
    _read_json_file,
    _segment_from_row,
    _segments_from_word_rows,
    _token_set,
    normalize_scribe_v2_transcript,
)
from ._podcast_multicam import angle_resolution as _angle_resolution
from ._podcast_multicam.angle_specs import parse_angle_spec as _parse_angle_spec
from ._podcast_multicam import db_switch_patch as _db_switch_patch
from ._podcast_multicam.model import (
    AngleSourceSpec,
    NativeSwitchReferenceFixture,
    NativeSwitchSegmentTemplate,
    ResolvedAngleClip,
    SwitchSegment,
    _segment_record_end_frame,
    _segment_record_start_frame,
)
from ._podcast_multicam import project_lifecycle as _project_lifecycle
from ._podcast_multicam import sync_planner as _sync_planner
from ._podcast_multicam import switch_plan as _switch_plan
from ._podcast_multicam import switch_fixtures as _switch_fixtures
from ._podcast_multicam import timeline_materialization as _timeline_materialization
from ..multicam_support import MAX_SUPPORTED_ANGLE_COUNT, support_tier_for_angle_count
from . import multicam_switch_families
from .waveform_sync import compute_waveform_offsets
from ..external_tools import resolve_tool

_COMPAT_EXPORTS = (
    CLIError,
    set_recoverability,
    set_verification_status,
    close_current_project_with_runtime_health,
    get_current_database_details,
    project_is_closed_enough,
    seconds_to_frames,
    timecode_to_seconds,
    edit_ops,
    _coalesce_short_segments,
    _extract_ms,
    _extract_speaker,
    _merge_adjacent_segments,
    _normalize_token,
    _read_json_file,
    _segment_from_row,
    _segments_from_word_rows,
    _token_set,
    multicam_switch_families,
    time,
    _segment_record_end_frame,
    _segment_record_start_frame,
)

_DEFAULT_MIN_SHOT_MS = 1200
_DEFAULT_MERGE_GAP_MS = 250
_TEMP_BIN_PREFIX = "__CutAgent Native Multicam "
_CAMERA_LABEL_RE = re.compile(rb"Camera \d+")
_SWITCH_FIXTURE_PACKAGE = "cutagent_cli.fixtures"
_SWITCH_FIXTURE_NAME_BY_ANGLE_COUNT = {
    2: "native_multicam_switch_reference_resolve20x.json",
    3: "native_multicam_switch_reference_3cam_resolve20x.json",
    4: "native_multicam_switch_reference_4cam_resolve20x.json",
    5: "native_multicam_switch_reference_5cam_resolve20x.json",
    6: "native_multicam_switch_reference_6cam_resolve20x.json",
}
_PREFERRED_LOCAL_MULTICAM_SWITCH_REFERENCE_NAMES = (
    "native-4-multicam",
    "native-5-multicam",
    "native-6-multicam",
)
_TIMELINE_ITEM_MEDIA_TIMEMAP = base64.b64decode("AkAj6qqqqqqr")
_TIMELINE_ITEM_MEDIA_FRAME_RATE = base64.b64decode("AAAAAAAAOEAAAAAAAAAAAA==")
_TIMELINE_ITEM_VIDEO_PRECONFORM_MEDIA_EXTENTS = base64.b64decode("AAABAAAAMMIAAAEAAAAwQg==")
_TIMELINE_ITEM_AUDIO_VIRTUAL_AUDIO_TRACK = base64.b64decode(
    "AAAAAQAAAAIAAAAUAEMAaABhAG4AbgBlAGwAcwBCAEEAAAAMAAAAAAwAAAACAAAAAQAAQAEAAAASAEEAdQBkAGkAbwBUAHkAcABlAAAAAgAAAAAB"
)
_TOOL_GENERATED_MULTICAM_NAME_PREFIXES = (
    "Multicam Generic ",
    "Podcast Auto Edit ",
    "Native Reference ",
    "__CutAgent ",
)


def parse_speaker_mapping(mapping: str | None) -> dict[str, str]:
    return _switch_plan.parse_speaker_mapping(mapping)


def infer_speaker_camera_mapping(
    *,
    segments: list[dict[str, Any]] | list[SpeakerSegment],
    angle_map: dict[str, str],
) -> dict[str, Any]:
    return _switch_plan.infer_speaker_camera_mapping(segments=segments, angle_map=angle_map)


def build_switch_plan(
    *,
    conn,
    transcript_segments: list[dict[str, Any]],
    angle_map: dict[str, str],
    speaker_map: dict[str, str],
    min_shot_ms: int = _DEFAULT_MIN_SHOT_MS,
    merge_gap_ms: int = _DEFAULT_MERGE_GAP_MS,
    max_end_frame: int | None = None,
) -> dict[str, Any]:
    return _switch_plan.build_switch_plan(
        conn=conn,
        transcript_segments=transcript_segments,
        angle_map=angle_map,
        speaker_map=speaker_map,
        switch_segment_cls=SwitchSegment,
        frames_to_timecode_fn=frames_to_timecode,
        min_shot_ms=min_shot_ms,
        merge_gap_ms=merge_gap_ms,
        max_end_frame=max_end_frame,
    )


def _ops_module():
    return sys.modules[__name__]


def _is_temp_bin_folder_path(folder_path: str | None) -> bool:
    return _angle_resolution._is_temp_bin_folder_path(folder_path, temp_bin_prefix=_TEMP_BIN_PREFIX)


def _normalize_folder_path_for_match(value: str | None) -> str:
    return _angle_resolution._normalize_folder_path_for_match(value)


def _folder_path_matches(candidate: str | None, requested: str | None) -> bool:
    return _angle_resolution._folder_path_matches(candidate, requested)


def _normalize_source_path_for_match(value: str | None) -> str:
    return _angle_resolution._normalize_source_path_for_match(value)


def _stable_clip_matches(conn, clip_name: str) -> list[dict[str, Any]]:
    return _angle_resolution._stable_clip_matches(conn, clip_name, temp_bin_prefix=_TEMP_BIN_PREFIX)


def _find_resolved_angle_clip_match(conn, clip_name: str) -> dict[str, Any] | None:
    return _angle_resolution._find_resolved_angle_clip_match(conn, clip_name, temp_bin_prefix=_TEMP_BIN_PREFIX)


def _normalize_angle_source_specs(source_specs: list[dict[str, Any]] | None, angle_map: dict[str, str]) -> list[AngleSourceSpec]:
    return _angle_resolution._normalize_angle_source_specs(
        source_specs,
        angle_map,
        angle_source_spec_cls=AngleSourceSpec,
    )


def _find_resolved_angle_source_spec_match(conn, source_spec: AngleSourceSpec) -> dict[str, Any] | None:
    return _angle_resolution._find_resolved_angle_source_spec_match(
        conn,
        source_spec,
        temp_bin_prefix=_TEMP_BIN_PREFIX,
    )


def _resolved_angle_media_start_time(props: dict[str, Any], clip_fps: float) -> float | None:
    return _angle_resolution._resolved_angle_media_start_time(props, clip_fps)


def _resolve_angle_source_specs(
    conn,
    source_specs: list[dict[str, Any]] | None,
    *,
    angle_map: dict[str, str],
) -> list[ResolvedAngleClip]:
    return _angle_resolution._resolve_angle_source_specs(
        conn,
        source_specs,
        angle_map=angle_map,
        angle_source_spec_cls=AngleSourceSpec,
        resolved_angle_clip_cls=ResolvedAngleClip,
        temp_bin_prefix=_TEMP_BIN_PREFIX,
    )


def _resolve_angle_sources(conn, angle_map: dict[str, str]) -> list[ResolvedAngleClip]:
    return _angle_resolution._resolve_angle_sources(
        conn,
        angle_map,
        angle_source_spec_cls=AngleSourceSpec,
        resolved_angle_clip_cls=ResolvedAngleClip,
        temp_bin_prefix=_TEMP_BIN_PREFIX,
    )


def _apply_native_angle_sync(
    conn,
    *,
    sync: str,
    resolved_angles: list[ResolvedAngleClip],
    source_rows: list[native_multicam_db.ResolvedDbMediaRow] | None = None,
    sync_channel: str | int = "auto",
    marker_name: str | None = None,
    full_clip_extents: bool = True,
) -> dict[str, Any]:
    synchronized_sources = list(resolved_angles)
    if source_rows is not None:
        if len(source_rows) != len(resolved_angles):
            raise ValidationError(
                "Resolved multicam source rows must match the live source count before synchronization.",
                details={"resolved_source_count": len(resolved_angles), "db_source_count": len(source_rows)},
            )
        synchronized_sources = [
            replace(
                angle,
                duration_frames=angle.duration_frames or row.duration_frames,
                fps=angle.fps or row.fps,
                media_start_time=(
                    angle.media_start_time
                    if angle.media_start_time is not None
                    else row.media_start_time
                ),
                mark_in_frame=row.mark_in_frame,
                mark_out_frame=row.mark_out_frame,
            )
            for angle, row in zip(resolved_angles, source_rows)
        ]
    if sync == "in" and any(item.duration_frames in (None, 0) for item in synchronized_sources):
        return {
            "sync": "in",
            "sync_mode": "in",
            "sync_engine": "cutagent_timing",
            "sync_channel": None,
            "marker_name": None,
            "full_clip_extents": bool(full_clip_extents),
            "source_item_timing": [
                {
                    "record_start_frame": item.record_start_frame,
                    "source_in_frame": item.source_in_frame,
                    "duration_frames": item.item_duration_frames,
                }
                for item in synchronized_sources
            ],
            "evidence": [{"reason": "duration_deferred_to_native_template"}],
            "offsets_frames": [int(item.record_start_frame or 0) for item in synchronized_sources],
        }
    result = _sync_planner.build_source_item_timing(
        synchronized_sources,
        sync_mode=sync,
        fps=float(synchronized_sources[0].fps or getattr(conn, "fps", 24.0) or 24.0),
        sync_channel=sync_channel,
        marker_name=marker_name,
        full_clip_extents=full_clip_extents,
        waveform_offsets_fn=_compute_native_waveform_offsets,
    )
    return {
        "sync": result["sync_mode"],
        **result,
        "offsets_frames": [
            int(item["record_start_frame"])
            for item in result["source_item_timing"]
        ],
    }


def _compute_native_waveform_offsets(
    source_paths: list[str],
    *,
    fps: float,
    channel: str | int = "auto",
) -> list[int]:
    normalized_channel = _sync_planner.normalize_sync_channel(channel)
    if normalized_channel in {"auto", "mix"}:
        return compute_waveform_offsets(source_paths, fps=fps)

    ffmpeg = resolve_tool("ffmpeg")
    with tempfile.TemporaryDirectory(prefix="cutagent-multicam-sync-") as temp_dir:
        selected_paths: list[str] = []
        for source_index, source_path in enumerate(source_paths):
            output_path = os.path.join(temp_dir, f"source-{source_index}.wav")
            channel_index = int(normalized_channel) - 1
            command = [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                source_path,
                "-vn",
                "-af",
                f"pan=mono|c0=c{channel_index}",
                "-ar",
                "48000",
                output_path,
            ]
            completed = subprocess.run(command, capture_output=True, check=False)
            if completed.returncode != 0 or not os.path.isfile(output_path):
                raise APICallFailed(
                    "CutAgent could not extract the requested audio channel for multicam sound sync.",
                    details={
                        "source_path": source_path,
                        "sync_channel": normalized_channel,
                        "stderr_tail": completed.stderr.decode("utf-8", errors="replace")[-500:],
                    },
                )
            selected_paths.append(output_path)
        return compute_waveform_offsets(selected_paths, fps=fps)


def _set_workflow_verification(status: str) -> None:
    _project_lifecycle._set_workflow_verification(status)


def _current_database_details(conn) -> dict[str, Any]:
    return _project_lifecycle._current_database_details(
        conn,
        get_current_database_details_fn=get_current_database_details,
    )


def _require_live_project_name(
    conn,
    *,
    context: str,
    attempts: int = 6,
    delay: float = 0.1,
) -> str:
    return _project_lifecycle._require_live_project_name(
        conn,
        context=context,
        attempts=attempts,
        delay=delay,
    )


def _project_closed_enough_for_db_write(state: dict[str, Any], *, original_project_name: str) -> bool:
    return _project_lifecycle._project_closed_enough_for_db_write(
        state,
        original_project_name=original_project_name,
        project_is_closed_enough_fn=project_is_closed_enough,
    )


def _timeline_exists(conn, timeline_name: str) -> bool:
    return _project_lifecycle._timeline_exists(conn, timeline_name)


def _live_timeline_names(conn) -> list[str]:
    project = getattr(conn, "project", None)
    if project is None:
        return []
    count = int(project.GetTimelineCount() or 0)
    names: list[str] = []
    for index in range(1, count + 1):
        timeline = project.GetTimelineByIndex(index)
        getter = getattr(timeline, "GetName", None)
        if callable(getter):
            name = str(getter() or "").strip()
            if name:
                names.append(name)
    return names


def _media_pool_item_id(clip: Any) -> str | None:
    for method_name in ("GetMediaId", "GetUniqueId"):
        getter = getattr(clip, method_name, None)
        if callable(getter):
            try:
                value = getter()
            except Exception:
                value = None
            if value:
                return str(value)
    props_getter = getattr(clip, "GetClipProperty", None)
    props = None
    if callable(props_getter):
        try:
            props = props_getter()
        except Exception:
            props = None
    if isinstance(props, dict):
        for key in ("MediaId", "Media ID", "media_id", "Id", "ID"):
            value = props.get(key)
            if value:
                return str(value)
    return None


def _live_multicam_candidates(conn, *, multicam_name: str) -> list[dict[str, Any]]:
    pool = getattr(conn, "media_pool", None)
    root_getter = getattr(pool, "GetRootFolder", None) if pool is not None else None
    if not callable(root_getter):
        return []
    try:
        root = root_getter()
    except Exception:
        return []
    if root is None:
        return []
    matches: list[dict[str, Any]] = []
    collector = getattr(media_pool, "_collect_clip_matches", None)
    if callable(collector):
        collector(root, multicam_name, "", matches)
    else:
        return []
    return [
        {
            "name": str(match.get("name") or ""),
            "folder": str(match.get("folder") or "") or None,
            "media_id": _media_pool_item_id(match.get("clip")),
        }
        for match in matches
        if str(match.get("name") or "") == multicam_name
    ]


def _preflight_native_multicam_target_names(
    conn,
    *,
    project_db_path: str,
    timeline_name: str,
    multicam_name: str,
    cleanup_stale_targets: bool,
) -> dict[str, Any]:
    preflight = native_multicam_db.inspect_multicam_create_preflight(
        project_db_path,
        multicam_name=multicam_name,
        timeline_name=timeline_name,
        live_multicam_candidates=_live_multicam_candidates(conn, multicam_name=multicam_name),
        live_timeline_names=_live_timeline_names(conn),
    )
    visible_conflicts = preflight.get("visible_conflicts") or {}
    if visible_conflicts.get("multicams") or visible_conflicts.get("timelines"):
        next_steps = [
            "Choose fresh timeline_name and multicam_name, or remove/rename the live DaVinci Resolve "
            "multicam/timeline with these target names.",
        ]
        if preflight.get("cleanup_required"):
            next_steps.append(
                "After live targets are gone, use --cleanup-stale only if preflight still reports "
                "DB-only stale records."
            )
        raise ValidationError(
            "Target multicam or timeline name already exists in the live project. Choose a new name before rerunning.",
            details={
                "reason": "target_name_already_exists",
                "timeline_name": timeline_name,
                "multicam_name": multicam_name,
                "project_db_path": project_db_path,
                "preflight": preflight,
                "next_steps": next_steps,
            },
        )
    if preflight.get("cleanup_required") and not cleanup_stale_targets:
        raise StaleDbMulticam(
            "Target native multicam/timeline name has DB-only stale records that DaVinci Resolve does not expose live.",
            details={
                "reason": "stale_db_only_target",
                "timeline_name": timeline_name,
                "multicam_name": multicam_name,
                "project_db_path": project_db_path,
                "preflight": preflight,
                "next_steps": [
                    "Rerun with --cleanup-stale to remove DB-only records for these exact target names before creating the multicam.",
                    "Alternatively choose a fresh timeline_name and multicam_name.",
                ],
            },
        )
    if preflight.get("cleanup_required") and not preflight.get("cleanup_supported"):
        raise ValidationError(
            "Stale target cleanup is not safe because the target is also visible in the live project.",
            details={
                "reason": "stale_target_cleanup_not_supported",
                "timeline_name": timeline_name,
                "multicam_name": multicam_name,
                "project_db_path": project_db_path,
                "preflight": preflight,
            },
        )
    return preflight


def _ensure_target_timeline_name_available(conn, *, timeline_name: str) -> None:
    _project_lifecycle._ensure_target_timeline_name_available(conn, timeline_name=timeline_name)


def _close_current_project(
    conn,
    *,
    project_name: str,
    current_database: dict[str, Any] | None = None,
    project_db_path: str | None = None,
    save: bool,
    save_step_name: str = "project_save",
    close_step_name: str = "project_close",
    wait_description: str | None = None,
) -> list[dict[str, Any]]:
    return _project_lifecycle._close_current_project(
        conn,
        project_name=project_name,
        current_database=current_database,
        project_db_path=project_db_path,
        save=save,
        save_step_name=save_step_name,
        close_step_name=close_step_name,
        wait_description=wait_description,
        close_current_project_with_runtime_health_fn=close_current_project_with_runtime_health,
        current_database_details_fn=get_current_database_details,
    )


def _save_and_close_current_project(
    conn,
    *,
    project_name: str,
    current_database: dict[str, Any] | None = None,
    project_db_path: str | None = None,
) -> list[dict[str, Any]]:
    return _project_lifecycle._save_and_close_current_project(
        conn,
        project_name=project_name,
        current_database=current_database,
        project_db_path=project_db_path,
        close_current_project_with_runtime_health_fn=close_current_project_with_runtime_health,
        current_database_details_fn=get_current_database_details,
    )


def _reopen_project(conn, *, project_name: str) -> dict[str, Any]:
    return _project_lifecycle._reopen_project(conn, project_name=project_name)


def _best_effort_reopen_project(conn, *, project_name: str, failure_step: str) -> dict[str, Any] | None:
    return _project_lifecycle._best_effort_reopen_project(
        conn,
        project_name=project_name,
        failure_step=failure_step,
    )


def _wait_for_multicam_clip_exposure(
    conn,
    *,
    multicam_name: str,
    attempts: int = 16,
    delay: float = 0.25,
) -> tuple[Any, int]:
    return _project_lifecycle._wait_for_multicam_clip_exposure(
        conn,
        multicam_name=multicam_name,
        attempts=attempts,
        delay=delay,
    )


def _materialize_multicam_timeline(
    conn,
    *,
    created_clip: Any,
    multicam_name: str,
    timeline_name: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    return _project_lifecycle._materialize_multicam_timeline(
        conn,
        created_clip=created_clip,
        multicam_name=multicam_name,
        timeline_name=timeline_name,
        ops_module=_ops_module(),
    )


def _raise_step_failure(step: str, exc: Exception, *, extra: dict[str, Any] | None = None) -> None:
    _project_lifecycle._raise_step_failure(step, exc, extra=extra)


def _rollback_db_create_from_backup(
    conn,
    *,
    project_name: str,
    current_database: dict[str, Any],
    project_db_path: str,
    backup_path: str | None,
    multicam_name: str,
) -> dict[str, Any]:
    """Best-effort rollback for DB multicam writes that DaVinci Resolve never exposes."""
    step: dict[str, Any] = {
        "name": "project_db_rollback",
        "ok": False,
        "project_name": project_name,
        "project_db_path": project_db_path,
        "backup_path": backup_path,
        "multicam_name": multicam_name,
    }
    if not backup_path or not os.path.exists(backup_path):
        step["reason"] = "backup_missing"
        return step

    close_steps: list[dict[str, Any]] = []
    try:
        close_steps = _close_current_project(
            conn,
            project_name=project_name,
            current_database=current_database,
            project_db_path=project_db_path,
            save=False,
            close_step_name="project_rollback_close",
            wait_description=f"project '{project_name}' to close before rolling back failed multicam DB write",
        )
        shutil.copy2(backup_path, project_db_path)
        restore_step = _best_effort_reopen_project(
            conn,
            project_name=project_name,
            failure_step="project_db_rollback",
        )
        step.update(
            {
                "ok": True,
                "rolled_back": True,
                "close_steps": close_steps,
                "restore_step": restore_step,
            }
        )
    except Exception as rollback_exc:
        step["rolled_back"] = False
        step["error"] = str(rollback_exc)
        if close_steps:
            step["close_steps"] = close_steps
    return step


def _native_multicam_create_via_db(
    conn,
    *,
    timeline_name: str,
    multicam_name: str,
    angles: str,
    source_specs: list[dict[str, Any]] | None = None,
    angle_names: dict[str, str] | None = None,
    source_layout: str = "contiguous",
    sync: str = native_multicam_db.DEFAULT_NATIVE_ANGLE_SYNC_MODE,
    sync_channel: str | int = "auto",
    marker_name: str | None = None,
    full_clip_extents: bool = True,
    audio_mode: str = "source_audio_channels",
    reference_audio_angle: str | None = None,
    start_timecode: str | None = None,
    source_start_offsets_frames: list[int] | None = None,
    source_start_offsets_mode: str = "additive",
    materialize_timeline: bool = True,
    reference_source: str = native_multicam_db.DEFAULT_MULTICAM_REFERENCE_SOURCE_POLICY,
    cleanup_stale_targets: bool = False,
    preferred_duration_frames: int | None = None,
) -> dict[str, Any]:
    angle_map = _parse_angle_spec(angles)
    angle_count = len(angle_map)
    source_spec_labels = [
        str(item.get("angle") or item.get("label") or "").strip()
        for item in list(source_specs or [])
        if isinstance(item, dict)
    ]
    support_tier = support_tier_for_angle_count(
        angle_count,
        has_multi_clip_angle=len(source_spec_labels) > angle_count,
        source_layout=source_layout,
    )
    if not bool(support_tier.get("create_supported")):
        raise ValidationError(
            f"Native multicam create currently supports only {MAX_SUPPORTED_ANGLE_COUNT} source angles.",
            details={
                "reason": "unsupported_angle_count",
                "angle_count": angle_count,
                "max_supported_angle_count": MAX_SUPPORTED_ANGLE_COUNT,
                "support_tier": support_tier,
            },
        )
    normalized_sync = native_multicam_db.normalize_native_angle_sync_mode(sync)

    current_database = _current_database_details(conn)
    if str(current_database.get("DbType") or "") != "Disk":
        raise ValidationError(
            "DB-backed native multicam create currently supports only Disk project databases.",
            details={
                "reason": "unsupported_database",
                "current_database": current_database,
                "supported_db_types": ["Disk"],
            },
        )

    project_name = _require_live_project_name(conn, context="DB-backed multicam creation")

    db_resolution = native_multicam_db.resolve_disk_project_db_path(project_name=project_name)
    project_db_path = str(db_resolution["project_db_path"])
    target_preflight = _preflight_native_multicam_target_names(
        conn,
        project_db_path=project_db_path,
        timeline_name=timeline_name,
        multicam_name=multicam_name,
        cleanup_stale_targets=cleanup_stale_targets,
    )
    resolved_angles = (
        _resolve_angle_source_specs(conn, source_specs, angle_map=angle_map)
        if source_specs is not None
        else _resolve_angle_sources(conn, angle_map)
    )
    source_rows = native_multicam_db.resolve_source_media_rows(
        project_db_path,
        resolved_angles=[asdict(item) for item in resolved_angles],
    )
    native_angle_sync = _apply_native_angle_sync(
        conn,
        sync=normalized_sync,
        resolved_angles=resolved_angles,
        source_rows=source_rows,
        sync_channel=sync_channel,
        marker_name=marker_name,
        full_clip_extents=full_clip_extents,
    )
    synchronized_timing = list(native_angle_sync["source_item_timing"])
    next_end_by_angle = {label: 0 for label in angle_map}
    timing_requires_sparse = False
    for resolved_angle, item_timing in zip(resolved_angles, synchronized_timing):
        if item_timing.get("record_start_frame") is None or item_timing.get("duration_frames") is None:
            continue
        record_start = int(item_timing["record_start_frame"])
        if record_start != int(next_end_by_angle[resolved_angle.label]):
            timing_requires_sparse = True
        next_end_by_angle[resolved_angle.label] = record_start + int(item_timing["duration_frames"])
    effective_source_layout = "sparse" if timing_requires_sparse else source_layout

    set_execution_engine("db_workaround")
    steps: list[dict[str, Any]] = [
        {
            "name": "project_db_resolution",
            "ok": True,
            "project_name": project_name,
            "project_db_path": project_db_path,
        }
    ]
    steps.append(
        {
            "name": "target_name_preflight",
            "ok": True,
            "status": target_preflight.get("status"),
            "cleanup_required": bool(target_preflight.get("cleanup_required")),
            "cleanup_supported": bool(target_preflight.get("cleanup_supported")),
            "multicam_name": multicam_name,
            "timeline_name": timeline_name,
        }
    )
    if native_angle_sync is not None:
        steps.append({"name": "native_angle_sync", "ok": True, **native_angle_sync})
    steps.extend(
        _save_and_close_current_project(
            conn,
            project_name=project_name,
            current_database=current_database,
            project_db_path=project_db_path,
        )
    )
    cleanup_result: dict[str, Any] | None = None
    if cleanup_stale_targets and target_preflight.get("cleanup_required"):
        try:
            cleanup_result = native_multicam_db.cleanup_stale_multicam_create_targets(
                project_db_path,
                preflight=target_preflight,
            )
            steps.append({"name": "stale_target_cleanup", "ok": True, **cleanup_result})
        except Exception as exc:
            restore_step = _best_effort_reopen_project(
                conn,
                project_name=project_name,
                failure_step="stale_target_cleanup",
            )
            if restore_step is not None:
                steps.append(restore_step)
            _raise_step_failure(
                "stale_target_cleanup",
                exc,
                extra={
                    "project_name": project_name,
                    "project_db_path": project_db_path,
                    "timeline_name": timeline_name,
                    "multicam_name": multicam_name,
                    "target_preflight": target_preflight,
                },
            )
    db_create_result: dict[str, Any] | None = None
    try:
        explicit_offsets = [int(value) for value in source_start_offsets_frames] if source_start_offsets_frames is not None else None
        db_create_result = native_multicam_db.create_multicam_clip(
            project_db_path=project_db_path,
            multicam_name=multicam_name,
            source_rows=source_rows,
            source_angle_labels=[item.label for item in resolved_angles],
            angle_names=angle_names,
            source_item_timing=synchronized_timing,
            source_layout=effective_source_layout,
            sync_mode=normalized_sync,
            source_start_offsets_frames=explicit_offsets,
            source_start_offsets_mode=source_start_offsets_mode,
            audio_mode=audio_mode,
            reference_audio_angle=reference_audio_angle,
            start_timecode=start_timecode,
            reference_source=reference_source,
            preferred_duration_frames=preferred_duration_frames,
        )
        steps.append({"name": "project_db_write", "ok": True, **db_create_result})
    except Exception as exc:
        restore_step = _best_effort_reopen_project(
            conn,
            project_name=project_name,
            failure_step="project_db_write",
        )
        if restore_step is not None:
            steps.append(restore_step)
        _raise_step_failure(
            "project_db_write",
            exc,
            extra={
                "project_name": project_name,
                "project_db_path": project_db_path,
                "multicam_name": multicam_name,
                "angles": angle_map,
            },
        )

    verification_checks: list[dict[str, Any]] = []

    created_clip = None
    try:
        total_attempts = 0
        reopen_cycles = 0
        for cycle_index in range(1, 3):
            reopen_cycles = cycle_index
            reopen_step = _reopen_project(conn, project_name=project_name)
            if cycle_index > 1:
                reopen_step["name"] = f"project_reopen_cycle_{cycle_index}"
            reopen_step["reopen_cycle"] = cycle_index
            steps.append(reopen_step)

            try:
                created_clip, attempts_used = _wait_for_multicam_clip_exposure(conn, multicam_name=multicam_name)
                total_attempts += attempts_used
                break
            except APICallFailed as exc:
                total_attempts += int(exc.details.get("attempts") or 0)
                if cycle_index >= 2:
                    raise APICallFailed(
                        str(exc),
                        details={
                            **dict(exc.details),
                            "attempts": total_attempts,
                            "reopen_cycles": reopen_cycles,
                            "multicam_name": multicam_name,
                            "project_name": project_name,
                            "project_db_path": project_db_path,
                        },
                        recoverability=exc.recoverability,
                    ) from exc
                steps.extend(
                    _close_current_project(
                        conn,
                        project_name=project_name,
                        current_database=current_database,
                        project_db_path=project_db_path,
                        save=False,
                        close_step_name="project_reload_close",
                        wait_description=f"project '{project_name}' to stop being current before Project.db reload",
                    )
                )

        if created_clip is None:
            raise APICallFailed(
                "DB-backed multicam clip was not available after the controlled project reload cycles.",
                details={
                    "attempts": total_attempts,
                    "reopen_cycles": reopen_cycles,
                    "multicam_name": multicam_name,
                    "project_name": project_name,
                    "project_db_path": project_db_path,
                },
            )
        verification_checks.append({"name": "multicam_clip_exists", "ok": True, "multicam_name": multicam_name})
    except Exception as exc:
        db_audit = db_create_result.get("db_audit") if isinstance(db_create_result, dict) else None
        rollback_step = None
        if isinstance(db_create_result, dict):
            rollback_step = _rollback_db_create_from_backup(
                conn,
                project_name=project_name,
                current_database=current_database,
                project_db_path=project_db_path,
                backup_path=db_create_result.get("backup_path"),
                multicam_name=multicam_name,
            )
        _raise_step_failure(
            "multicam_exposure",
            exc,
            extra={
                "project_name": project_name,
                "project_db_path": project_db_path,
                "timeline_name": timeline_name,
                "multicam_name": multicam_name,
                "multicam_media_id": db_create_result.get("multicam_media_id") if db_create_result else None,
                "multicam_sequence_id": db_create_result.get("multicam_sequence_id") if db_create_result else None,
                "db_audit": db_audit,
                "target_preflight": target_preflight,
                "stale_target_cleanup": cleanup_result,
                "rollback": rollback_step,
            },
        )

    if materialize_timeline:
        try:
            timeline_step, timeline_checks = _materialize_multicam_timeline(
                conn,
                created_clip=created_clip,
                multicam_name=multicam_name,
                timeline_name=timeline_name,
            )
            steps.append(timeline_step)
            verification_checks.extend(check for check in timeline_checks if check.get("name") != "multicam_clip_exists")
            if str(db_create_result.get("audio_mode") or "") == "reference_audio":
                reference_label = str(db_create_result.get("reference_audio_angle") or "")
                reference_source = next(
                    (item for item in resolved_angles if str(item.label) == reference_label),
                    None,
                )
                if reference_source is None:
                    raise ValidationError(
                        "Reference audio angle could not be resolved after native multicam creation.",
                        details={
                            "reference_audio_angle": reference_label,
                            "resolved_angles": [asdict(item) for item in resolved_angles],
                        },
                    )
                timeline_start = int(conn.timeline.GetStartFrame() or 0)
                timeline_duration = int(db_create_result.get("multicam_duration_frames") or 0)
                reference_step, reference_checks = _materialize_timeline_from_switch_plan(
                    conn,
                    timeline_name=timeline_name,
                    multicam_name=multicam_name,
                    plan={
                        "segments": [
                            {
                                "speaker_id": "reference_audio",
                                "angle": reference_label,
                                "clip_name": reference_source.clip_name,
                                "start_frame": 0,
                                "end_frame": timeline_duration,
                                "record_start_frame": timeline_start,
                                "record_end_frame": timeline_start + timeline_duration,
                                "start_tc": "",
                                "end_tc": "",
                                "text": "",
                            }
                        ],
                        "multicam_settings": {
                            "angle_order": list(angle_map),
                            "audio_mode": "reference_audio",
                            "reference_audio_angle": reference_label,
                            "reference_audio_clip_name": reference_source.clip_name,
                        },
                    },
                    replace_active_timeline=True,
                    switch_scope="audio",
                )
                reference_step["name"] = "reference_audio_materialization"
                steps.append(reference_step)
                verification_checks.extend(reference_checks)
        except Exception as exc:
            db_audit = db_create_result.get("db_audit") if isinstance(db_create_result, dict) else None
            _raise_step_failure(
                "timeline_creation",
                exc,
                extra={
                    "project_name": project_name,
                    "project_db_path": project_db_path,
                    "timeline_name": timeline_name,
                    "multicam_name": multicam_name,
                    "multicam_media_id": db_create_result.get("multicam_media_id") if db_create_result else None,
                    "multicam_sequence_id": db_create_result.get("multicam_sequence_id") if db_create_result else None,
                    "db_audit": db_audit,
                    "target_preflight": target_preflight,
                    "stale_target_cleanup": cleanup_result,
                },
            )

    verification_status = "verified" if all(check.get("ok") for check in verification_checks) else "pending_manual"
    _set_workflow_verification(verification_status)

    return {
        "timeline_name": timeline_name,
        "multicam_name": multicam_name,
        "angle_count": angle_count,
        "angles": angle_map,
        "resolved_angles": [asdict(item) for item in resolved_angles],
        "sync_mode": normalized_sync,
        "sync_engine": "cutagent",
        "sync_channel": native_angle_sync.get("sync_channel"),
        "marker_name": native_angle_sync.get("marker_name"),
        "full_clip_extents": bool(full_clip_extents),
        "audio_mode": db_create_result.get("audio_mode"),
        "reference_audio_angle": db_create_result.get("reference_audio_angle"),
        "audio_track_policy": db_create_result.get("audio_track_policy"),
        "start_timecode": db_create_result.get("start_timecode"),
        "start_frame": db_create_result.get("start_frame"),
        "native_angle_sync": native_angle_sync,
        "created": True,
        "route": "db_native",
        "project_database": current_database,
        "project_db_path": project_db_path,
        "backup_path": db_create_result.get("backup_path"),
        "multicam_media_id": db_create_result.get("multicam_media_id"),
        "multicam_sequence_id": db_create_result.get("multicam_sequence_id"),
        "folder_id": db_create_result.get("folder_id"),
        "source_clip_count": db_create_result.get("source_clip_count", angle_count),
        "source_angle_labels": db_create_result.get("source_angle_labels"),
        "source_counts_by_angle": db_create_result.get("source_counts_by_angle"),
        "source_layout": db_create_result.get("source_layout"),
        "duration_by_angle": db_create_result.get("duration_by_angle"),
        "trailing_gap_frames_by_angle": db_create_result.get("trailing_gap_frames_by_angle"),
        "source_item_timing": db_create_result.get("source_item_timing"),
        "multicam_duration_frames": db_create_result.get("multicam_duration_frames"),
        "reference_source": db_create_result.get("reference_source"),
        "reference_source_policy": db_create_result.get("reference_source_policy"),
        "binding_validation": db_create_result.get("binding_validation"),
        "db_audit": db_create_result.get("db_audit"),
        "target_preflight": target_preflight,
        "stale_target_cleanup": cleanup_result,
        "support_tier": support_tier,
        "meta": {
            "engine": "db_workaround",
            "fixture_schema_family": db_create_result.get("fixture_schema_family"),
        },
        "steps": steps,
        "verification": {
            "status": verification_status,
            "checks": verification_checks,
        },
    }


def native_multicam_create(
    conn,
    *,
    timeline_name: str,
    multicam_name: str,
    angles: str,
    source_specs: list[dict[str, Any]] | None = None,
    angle_names: dict[str, str] | None = None,
    source_layout: str = "contiguous",
    sync: str = native_multicam_db.DEFAULT_NATIVE_ANGLE_SYNC_MODE,
    sync_channel: str | int = "auto",
    marker_name: str | None = None,
    full_clip_extents: bool = True,
    audio_mode: str = "source_audio_channels",
    reference_audio_angle: str | None = None,
    start_timecode: str | None = None,
    provider: str = "ax_native",
    verify: bool = True,
    checkpoint: bool = False,
    retries: int = 1,
    materialize_timeline: bool = True,
    reference_source: str = native_multicam_db.DEFAULT_MULTICAM_REFERENCE_SOURCE_POLICY,
    cleanup_stale_targets: bool = False,
    source_start_offsets_frames: list[int] | None = None,
    source_start_offsets_mode: str = "additive",
    preferred_duration_frames: int | None = None,
) -> dict[str, Any]:
    current_database = _current_database_details(conn)
    if str(current_database.get("DbType") or "") == "Disk":
        return _native_multicam_create_via_db(
            conn,
            timeline_name=timeline_name,
            multicam_name=multicam_name,
            angles=angles,
            source_specs=source_specs,
            angle_names=angle_names,
            source_layout=source_layout,
            sync=sync,
            sync_channel=sync_channel,
            marker_name=marker_name,
            full_clip_extents=full_clip_extents,
            audio_mode=audio_mode,
            reference_audio_angle=reference_audio_angle,
            start_timecode=start_timecode,
            source_start_offsets_frames=source_start_offsets_frames,
            source_start_offsets_mode=source_start_offsets_mode,
            materialize_timeline=materialize_timeline,
            reference_source=reference_source,
            cleanup_stale_targets=cleanup_stale_targets,
            preferred_duration_frames=preferred_duration_frames,
        )

    raise ValidationError(
        "Native multicam create is only supported for Disk project databases in V1.",
        details={
            "reason": "unsupported_database",
            "current_database": current_database,
            "supported_db_types": ["Disk"],
            "route": "db_native",
        },
    )


def _angle_map_from_switch_plan(plan: dict[str, Any]) -> dict[str, str]:
    angle_map: dict[str, str] = {}
    for segment in plan.get("segments", []):
        if not isinstance(segment, dict):
            continue
        angle = str(segment.get("angle") or "").strip()
        clip_name = str(segment.get("clip_name") or "").strip()
        if angle and clip_name and angle not in angle_map:
            angle_map[angle] = clip_name
    return angle_map


def _resolve_current_project_db_path(conn) -> str:
    return _timeline_materialization._resolve_current_project_db_path(conn, ops_module=_ops_module())


def _timeline_track_items(conn, track_type: str) -> list[Any]:
    return _timeline_materialization._timeline_track_items(conn, track_type)


def _clear_active_timeline_items(conn, *, switch_scope: str = "linked") -> dict[str, int]:
    return _timeline_materialization._clear_active_timeline_items(conn, switch_scope=switch_scope)


def _activate_timeline_by_name(conn, timeline_name: str, timeline_native_id: str | None = None) -> Any:
    return _timeline_materialization._activate_timeline_by_name(
        conn,
        timeline_name,
        timeline_native_id=timeline_native_id,
    )


def _decode_optional_blob_b64(value: Any) -> bytes:
    return _switch_fixtures._decode_optional_blob_b64(value)


def load_reference_multicam_switch_fixture(angle_count: int | None = None) -> NativeSwitchReferenceFixture:
    return _switch_fixtures.load_reference_multicam_switch_fixture(angle_count=angle_count, ops_module=_ops_module())


def _load_matching_project_multicam_switch_fixture(
    project_db_path: str,
    *,
    multicam_name: str,
    angle_count: int,
) -> NativeSwitchReferenceFixture | None:
    return _switch_fixtures._load_matching_project_multicam_switch_fixture(
        project_db_path,
        multicam_name=multicam_name,
        angle_count=angle_count,
        ops_module=_ops_module(),
    )


def _resolve_multicam_angle_indices(
    project_db_path: str,
    *,
    multicam_name: str,
    expected_clip_names: list[str] | None = None,
    multicam_media_id: str | None = None,
) -> dict[str, int]:
    return _switch_fixtures._resolve_multicam_angle_indices(
        project_db_path,
        multicam_name=multicam_name,
        expected_clip_names=expected_clip_names,
        multicam_media_id=multicam_media_id,
    )


def _segment_template_position(index: int, total_segments: int) -> str:
    return _switch_fixtures._segment_template_position(index, total_segments)


def _select_native_switch_template(
    templates: list[NativeSwitchSegmentTemplate],
    *,
    position: str,
    angle_index: int | None,
) -> NativeSwitchSegmentTemplate:
    return _switch_fixtures._select_native_switch_template(
        templates,
        position=position,
        angle_index=angle_index,
    )


def _resolve_switch_template_angle_index(*, segment: SwitchSegment, local_angle_index: int, angle_count: int) -> int:
    return _switch_fixtures._resolve_switch_template_angle_index(
        segment=segment,
        local_angle_index=local_angle_index,
        angle_count=angle_count,
    )


def _build_compact_angle_selector_fields_blob(local_angle_index: int) -> bytes:
    return _db_switch_patch._build_compact_angle_selector_fields_blob(local_angle_index)


def _build_two_cam_camera_selector_fields_blob(*, local_angle_index: int, track_type: str) -> bytes:
    return _db_switch_patch._build_two_cam_camera_selector_fields_blob(
        local_angle_index=local_angle_index,
        track_type=track_type,
    )


def _build_three_cam_whole_clip_selector_fields_blob(*, local_angle_index: int, track_type: str) -> bytes:
    return _db_switch_patch._build_three_cam_whole_clip_selector_fields_blob(
        local_angle_index=local_angle_index,
        track_type=track_type,
    )


def _patch_three_angle_selector_fields_blob(
    template_blob: bytes,
    *,
    position: str,
    template_angle_index: int,
    track_type: str,
) -> bytes:
    return _db_switch_patch._patch_three_angle_selector_fields_blob(
        template_blob,
        position=position,
        template_angle_index=template_angle_index,
        track_type=track_type,
    )


def _clone_item_row_with_segment(
    base_row: dict[str, Any],
    *,
    item_id: str,
    start: str,
    duration: str,
    in_value: str | None,
    current_selector_idx: int,
    fields_blob: bytes,
    media_timemap_ba: bytes | None = None,
    effect_filters_ba: bytes | None = None,
) -> dict[str, Any]:
    return _db_switch_patch._clone_item_row_with_segment(
        base_row,
        item_id=item_id,
        start=start,
        duration=duration,
        in_value=in_value,
        current_selector_idx=current_selector_idx,
        fields_blob=fields_blob,
        media_timemap_ba=media_timemap_ba,
        effect_filters_ba=effect_filters_ba,
    )


def _decode_frame_rate_blob(value: Any) -> float | None:
    return _db_switch_patch._decode_frame_rate_blob(value)


def _encode_media_extents(start_seconds: float, duration_seconds: float) -> bytes:
    return _db_switch_patch._encode_media_extents(start_seconds, duration_seconds)


def _quote_identifier(identifier: str) -> str:
    return _db_switch_patch._quote_identifier(identifier)


def _insert_row(cursor: sqlite3.Cursor, table_name: str, row: dict[str, Any]) -> None:
    _db_switch_patch._insert_row(cursor, table_name, row)


def _update_row(cursor: sqlite3.Cursor, table_name: str, row_id_column: str, row_id: Any, updates: dict[str, Any]) -> None:
    _db_switch_patch._update_row(cursor, table_name, row_id_column, row_id, updates)


def _build_switch_fields_blob(
    *,
    template: NativeSwitchSegmentTemplate,
    segment: SwitchSegment,
    local_angle_index: int,
    template_angle_index: int,
    segment_index: int,
    total_segments: int,
    angle_count: int,
    track_type: str,
    calibrated_project_local_reference: bool = False,
) -> bytes:
    return _db_switch_patch._build_switch_fields_blob(
        template=template,
        segment=segment,
        local_angle_index=local_angle_index,
        template_angle_index=template_angle_index,
        segment_index=segment_index,
        total_segments=total_segments,
        angle_count=angle_count,
        track_type=track_type,
        calibrated_project_local_reference=calibrated_project_local_reference,
    )


def _load_timeline_multicam_track_state(
    project_db_path: str,
    *,
    timeline_name: str,
    multicam_name: str,
    multicam_media_id: str | None = None,
    timeline_native_id: str | None = None,
) -> dict[str, Any]:
    return _db_switch_patch._load_timeline_multicam_track_state(
        project_db_path,
        timeline_name=timeline_name,
        multicam_name=multicam_name,
        multicam_media_id=multicam_media_id,
        timeline_native_id=timeline_native_id,
    )


def _build_fallback_multicam_item_row(
    *,
    item_id: str,
    multicam_name: str,
    multicam_media_id: str,
    track_id: str,
    track_type: int,
    start: str,
    duration: str,
    in_value: str | None,
    current_selector_idx: int,
    fields_blob: bytes,
    media_timemap_ba: bytes | None = None,
    effect_filters_ba: bytes | None = None,
) -> dict[str, Any]:
    return _db_switch_patch._build_fallback_multicam_item_row(
        item_id=item_id,
        multicam_name=multicam_name,
        multicam_media_id=multicam_media_id,
        track_id=track_id,
        track_type=track_type,
        start=start,
        duration=duration,
        in_value=in_value,
        current_selector_idx=current_selector_idx,
        fields_blob=fields_blob,
        media_timemap_ba=media_timemap_ba,
        effect_filters_ba=effect_filters_ba,
        ops_module=_ops_module(),
    )


def _delete_track_items(cursor: sqlite3.Cursor, *, track_id: str) -> None:
    _db_switch_patch._delete_track_items(cursor, track_id=track_id)


def _patch_timeline_multicam_bootstrap_metadata(
    cursor: sqlite3.Cursor,
    *,
    track_state: dict[str, Any],
    total_duration_frames: int,
) -> None:
    _db_switch_patch._patch_timeline_multicam_bootstrap_metadata(
        cursor,
        track_state=track_state,
        total_duration_frames=total_duration_frames,
    )


def _use_two_cam_single_item_in_place_patch(
    *,
    angle_count: int,
    segments: list[SwitchSegment],
    video_rows: list[dict[str, Any]],
    audio_rows: list[dict[str, Any]],
) -> bool:
    return _db_switch_patch._use_two_cam_single_item_in_place_patch(
        angle_count=angle_count,
        segments=segments,
        video_rows=video_rows,
        audio_rows=audio_rows,
    )


def _use_three_cam_single_item_in_place_patch(
    *,
    angle_count: int,
    segments: list[SwitchSegment],
    video_rows: list[dict[str, Any]],
    audio_rows: list[dict[str, Any]],
) -> bool:
    return _db_switch_patch._use_three_cam_single_item_in_place_patch(
        angle_count=angle_count,
        segments=segments,
        video_rows=video_rows,
        audio_rows=audio_rows,
    )


def _use_four_cam_single_item_in_place_patch(
    *,
    angle_count: int,
    segments: list[SwitchSegment],
    video_rows: list[dict[str, Any]],
    audio_rows: list[dict[str, Any]],
) -> bool:
    return _db_switch_patch._use_four_cam_single_item_in_place_patch(
        angle_count=angle_count,
        segments=segments,
        video_rows=video_rows,
        audio_rows=audio_rows,
    )


def _rewrite_multicam_segments_db(
    project_db_path: str,
    *,
    timeline_name: str,
    multicam_name: str,
    segments: list[SwitchSegment],
    switch_scope: str = "linked",
    audio_angle_override: str | None = None,
    multicam_media_id: str | None = None,
    timeline_native_id: str | None = None,
    preserved_item_positions: list[dict[str, Any]] | None = None,
    final_start_delta: int = 0,
) -> dict[str, Any]:
    return _db_switch_patch._rewrite_multicam_segments_db(
        project_db_path,
        timeline_name=timeline_name,
        multicam_name=multicam_name,
        segments=segments,
        switch_scope=switch_scope,
        audio_angle_override=audio_angle_override,
        multicam_media_id=multicam_media_id,
        timeline_native_id=timeline_native_id,
        preserved_item_positions=preserved_item_positions,
        final_start_delta=final_start_delta,
        ops_module=_ops_module(),
    )


def _append_multicam_clip_to_active_timeline(
    conn,
    *,
    created_clip: Any,
    multicam_name: str,
    project_db_path: str | None = None,
    allow_db_bootstrap: bool = False,
    record_frame: int | None = None,
    switch_scope: str = "linked",
) -> dict[str, Any]:
    return _timeline_materialization._append_multicam_clip_to_active_timeline(
        conn,
        created_clip=created_clip,
        multicam_name=multicam_name,
        project_db_path=project_db_path,
        allow_db_bootstrap=allow_db_bootstrap,
        record_frame=record_frame,
        switch_scope=switch_scope,
    )


def _split_multicam_items_for_segments(conn, *, segments: list[SwitchSegment]) -> dict[str, Any]:
    return _timeline_materialization._split_multicam_items_for_segments(
        conn,
        segments=segments,
        ops_module=_ops_module(),
    )


def _db_only_split_summary(*, conn, segments: list[SwitchSegment]) -> dict[str, Any]:
    return _timeline_materialization._db_only_split_summary(
        conn=conn,
        segments=segments,
        ops_module=_ops_module(),
    )


def _snapshot_timeline_multicam_segments_db(
    project_db_path: str,
    *,
    timeline_name: str,
    multicam_name: str,
    multicam_media_id: str | None = None,
    timeline_native_id: str | None = None,
) -> dict[str, Any]:
    return _timeline_materialization._snapshot_timeline_multicam_segments_db(
        project_db_path,
        timeline_name=timeline_name,
        multicam_name=multicam_name,
        multicam_media_id=multicam_media_id,
        timeline_native_id=timeline_native_id,
        ops_module=_ops_module(),
    )


def _inspect_timeline_multicam_db_materialization(
    project_db_path: str,
    *,
    timeline_name: str,
    multicam_name: str,
) -> dict[str, Any]:
    return _timeline_materialization._inspect_timeline_multicam_db_materialization(
        project_db_path,
        timeline_name=timeline_name,
        multicam_name=multicam_name,
    )


def _wait_for_timeline_multicam_db_materialization(
    conn,
    *,
    project_db_path: str,
    timeline_name: str,
    multicam_name: str,
    allow_empty_items: bool = False,
    attempts: int = 8,
    delay: float = 0.15,
) -> dict[str, Any]:
    return _timeline_materialization._wait_for_timeline_multicam_db_materialization(
        conn,
        project_db_path=project_db_path,
        timeline_name=timeline_name,
        multicam_name=multicam_name,
        allow_empty_items=allow_empty_items,
        attempts=attempts,
        delay=delay,
    )


def _wait_for_timeline_db_existence(
    project_db_path: str,
    *,
    timeline_name: str,
    attempts: int = 8,
    delay: float = 0.15,
) -> dict[str, Any]:
    return _timeline_materialization._wait_for_timeline_db_existence(
        project_db_path,
        timeline_name=timeline_name,
        attempts=attempts,
        delay=delay,
    )


def _materialize_timeline_from_switch_plan(
    conn,
    *,
    timeline_name: str,
    multicam_name: str,
    plan: dict[str, Any],
    replace_active_timeline: bool,
    switch_scope: str = "linked",
    multicam_media_id: str | None = None,
    timeline_native_id: str | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    return _timeline_materialization._materialize_timeline_from_switch_plan(
        conn,
        timeline_name=timeline_name,
        multicam_name=multicam_name,
        plan=plan,
        replace_active_timeline=replace_active_timeline,
        switch_scope=switch_scope,
        multicam_media_id=multicam_media_id,
        timeline_native_id=timeline_native_id,
        ops_module=_ops_module(),
    )


def native_multicam_switch(
    conn,
    *,
    multicam_name: str,
    plan: dict[str, Any],
    speaker_map: dict[str, str],
    provider: str = "ax_native",
    verify: bool = True,
    checkpoint: bool = False,
    retries: int = 1,
) -> dict[str, Any]:
    _ = (speaker_map, provider, verify, checkpoint, retries)

    media_pool.find_clip(conn, multicam_name)
    timeline_step, verification_checks = _materialize_timeline_from_switch_plan(
        conn,
        timeline_name=getattr(conn.timeline, "GetName", lambda: None)() or "",
        multicam_name=multicam_name,
        plan=plan,
        replace_active_timeline=True,
    )

    return {
        "multicam_name": multicam_name,
        "engine": "db_workaround",
        "timeline_name": timeline_step["timeline_name"],
        "segments_applied": timeline_step["segment_count"],
        "deleted_clip_count": timeline_step["deleted_clip_count"],
        "video_item_count": timeline_step["video_item_count"],
        "audio_item_count": timeline_step["audio_item_count"],
        "split_count": timeline_step["split_count"],
        "segment_write": timeline_step["segment_write"],
        "selector_patch": timeline_step["selector_patch"],
        "timeline_start_restore": timeline_step.get("timeline_start_restore"),
        "verification": {
            "status": "verified" if all(check.get("ok") for check in verification_checks) else "pending_manual",
            "checks": verification_checks,
        },
    }


def auto_edit_podcast_multicam(
    conn,
    *,
    timeline_name: str,
    multicam_name: str | None,
    angles: str,
    transcript_path: str,
    speaker_map_text: str | None = None,
    sync: str = native_multicam_db.DEFAULT_NATIVE_ANGLE_SYNC_MODE,
    provider: str = "ax_native",
    verify: bool = True,
    checkpoint: bool = False,
    retries: int = 1,
    min_shot_ms: int = _DEFAULT_MIN_SHOT_MS,
    merge_gap_ms: int = _DEFAULT_MERGE_GAP_MS,
) -> dict[str, Any]:
    angle_map = _parse_angle_spec(angles)
    transcript = normalize_scribe_v2_transcript(transcript_path)
    resolved_speaker_map = parse_speaker_mapping(speaker_map_text)

    if not resolved_speaker_map:
        inference = infer_speaker_camera_mapping(
            segments=transcript["segments"],
            angle_map=angle_map,
        )
        if inference.get("needs_clarification"):
            raise ValidationError(
                "Speaker-to-camera mapping is ambiguous. Ask one clarification and rerun with --speaker-map.",
                details={
                    "candidate_mappings": inference.get("candidate_mappings", []),
                    "speakers": transcript.get("speakers", []),
                    "angles": angle_map,
                },
        )
        resolved_speaker_map = dict(inference["mapping"])

    _ensure_target_timeline_name_available(conn, timeline_name=timeline_name)

    current_multicam_name = multicam_name or f"{timeline_name} Multicam"
    create_result = native_multicam_create(
        conn,
        timeline_name=timeline_name,
        multicam_name=current_multicam_name,
        angles=angles,
        sync=sync,
        provider=provider,
        verify=verify,
        checkpoint=checkpoint,
        retries=retries,
        materialize_timeline=False,
    )
    resolved_angle_durations = [
        int(item.get("duration_frames"))
        for item in create_result.get("resolved_angles", [])
        if item.get("duration_frames") is not None
    ]
    max_end_frame = None
    if resolved_angle_durations:
        max_end_frame = int(conn.start_frame) + min(resolved_angle_durations)

    switch_plan = build_switch_plan(
        conn=conn,
        transcript_segments=transcript["segments"],
        angle_map=angle_map,
        speaker_map=resolved_speaker_map,
        min_shot_ms=min_shot_ms,
        merge_gap_ms=merge_gap_ms,
        max_end_frame=max_end_frame,
    )
    timeline_step, verification_checks = _materialize_timeline_from_switch_plan(
        conn,
        timeline_name=timeline_name,
        multicam_name=current_multicam_name,
        plan=switch_plan,
        replace_active_timeline=False,
    )
    switch_result = {
        "multicam_name": current_multicam_name,
        "timeline_name": timeline_name,
        "engine": "db_workaround",
        "segments_applied": timeline_step["segment_count"],
        "deleted_clip_count": timeline_step["deleted_clip_count"],
        "video_item_count": timeline_step["video_item_count"],
        "audio_item_count": timeline_step["audio_item_count"],
        "split_count": timeline_step["split_count"],
        "segment_write": timeline_step["segment_write"],
        "selector_patch": timeline_step["selector_patch"],
        "verification": {
            "status": "verified" if all(check.get("ok") for check in verification_checks) else "pending_manual",
            "checks": verification_checks,
        },
    }
    route_engine = "db_workaround" if create_result.get("route") == "db_native" else "api_native"
    set_execution_engine(route_engine)

    return {
        "timeline_name": timeline_name,
        "multicam_name": current_multicam_name,
        "provider": provider,
        "engine": route_engine,
        "route": create_result.get("route"),
        "transcript": transcript,
        "speaker_map": resolved_speaker_map,
        "create": create_result,
        "switch_plan": switch_plan,
        "switch": switch_result,
        "verification": {
            "status": switch_result.get("verification", {}).get("status", "not_requested"),
            "checks": switch_result.get("verification", {}).get("checks", []),
        },
    }
