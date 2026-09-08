from __future__ import annotations

from dataclasses import replace
import os
import shutil
import sqlite3
from typing import Any
import uuid

from ...errors import ValidationError
from .audio_modes import build_audio_mode_plan
from ...multicam_support import (
    MAX_SUPPORTED_ANGLE_COUNT,
    SOURCE_CLIP_COUNT_PER_ANGLE_LIMIT,
    SOURCE_ITEM_REPRESENTATION,
    support_tier_for_angle_count,
)
from ...utils.timecode import timecode_to_seconds
from ..native_multicam_audit import AuditReferenceConfig, build_multicam_reference_audit


def _select_representative_item_row(
    cursor: sqlite3.Cursor,
    *,
    media_id: str,
    item_db_type: str,
    preferred_start: str,
    preferred_duration: str,
    ops_module,
) -> dict[str, Any] | None:
    row = cursor.execute(
        """
        SELECT
            i.MediaFilePath,
            i.MediaTimemapBA,
            i.PreConformMediaExtents,
            i.MediaFrameRate,
            i.VirtualAudioTrackBA,
            i.FieldsBlob,
            i."In" AS InValue,
            i.MediaTrackIdx,
            i.MediaStartTime,
            i.CurrentSelectorIdx,
            t.SubType,
            t.FieldsBlob AS TrackFieldsBlob
        FROM Sm2TiItem i
        JOIN Sm2TiTrack t ON t.Sm2TiTrack_id = i.Sm2TiTrack_id
        WHERE i.MediaRef = ?
          AND i.DbType = ?
          AND i.MediaFilePath IS NOT NULL
        ORDER BY
          CASE
            WHEN COALESCE(i.Start, '') = ? AND COALESCE(i.Duration, '') = ? THEN 0
            WHEN COALESCE(i.Duration, '') = ? THEN 1
            ELSE 2
          END,
          i.rowid DESC
        LIMIT 1
        """,
        (media_id, item_db_type, preferred_start, preferred_duration, preferred_duration),
    ).fetchone()
    if row is None:
        return None
    return ops_module._row_to_dict(cursor, row)


def _default_source_templates(
    source_row,
    reference,
    *,
    multicam_duration_frames: int,
    multicam_fps: float,
    ops_module,
):
    dynamic_media_timemap = ops_module._encode_media_timemap_ba(multicam_duration_frames, multicam_fps)
    return ops_module.SourceTemplates(
        video_track=ops_module.TrackTemplate(subtype=0, fields_blob=ops_module._VIDEO_TRACK_FIELDS_BLOB),
        audio_track=ops_module.TrackTemplate(subtype=257, fields_blob=ops_module._AUDIO_TRACK_FIELDS_BLOB),
        video_item=ops_module.ItemTemplate(
            is_placeholder=False,
            media_file_path=source_row.source_path,
            media_timemap_ba=dynamic_media_timemap,
            preconform_media_extents=ops_module._VIDEO_PRECONFORM_MEDIA_EXTENTS,
            media_frame_rate=reference.frame_rate or reference.sequence_frame_rate,
            virtual_audio_track_ba=None,
            fields_blob=ops_module._VIDEO_ITEM_FIELDS_BLOB,
            in_value=None,
            media_track_idx=None,
            current_selector_idx=0,
            media_start_time=None,
        ),
        audio_item=ops_module.ItemTemplate(
            is_placeholder=False,
            media_file_path=source_row.source_path,
            media_timemap_ba=dynamic_media_timemap,
            preconform_media_extents=None,
            media_frame_rate=reference.frame_rate or reference.sequence_frame_rate,
            virtual_audio_track_ba=ops_module._AUDIO_VIRTUAL_AUDIO_TRACK_BA,
            fields_blob=ops_module._AUDIO_ITEM_FIELDS_BLOB,
            in_value=None,
            media_track_idx=0,
            current_selector_idx=0,
            media_start_time=None,
        ),
    )


def _reference_item_template(reference, *, item_db_type: str, angle_index: int, fallback, ops_module):
    matching = [
        template
        for template in reference.item_templates
        if str(template.get("db_type") or "").strip() == item_db_type
    ]
    template = next(
        (
            candidate
            for candidate in matching
            if candidate.get("track_index") not in (None, "")
            and int(candidate.get("track_index")) == angle_index
        ),
        None,
    )
    if template is None and angle_index < len(matching):
        template = matching[angle_index]
    if template is not None:
        media_track_idx = template.get("media_track_idx")
        return ops_module.ItemTemplate(
            is_placeholder=bool(template.get("is_placeholder")),
            media_file_path=str(template.get("media_file_path") or "").strip() or fallback.media_file_path,
            media_timemap_ba=ops_module._decode_optional_bytes(template.get("media_timemap_b64")) or fallback.media_timemap_ba,
            preconform_media_extents=ops_module._decode_optional_bytes(template.get("preconform_media_extents_b64"))
            or fallback.preconform_media_extents,
            media_frame_rate=ops_module._decode_optional_bytes(template.get("media_frame_rate_b64"))
            or fallback.media_frame_rate,
            virtual_audio_track_ba=ops_module._decode_optional_bytes(template.get("virtual_audio_track_b64"))
            or fallback.virtual_audio_track_ba,
            fields_blob=ops_module._decode_optional_bytes(template.get("fields_blob_b64")) or fallback.fields_blob,
            in_value=str(template.get("in_value")).strip() if template.get("in_value") not in (None, "") else fallback.in_value,
            media_track_idx=int(media_track_idx) if media_track_idx not in (None, "") else fallback.media_track_idx,
            current_selector_idx=(
                int(template.get("current_selector_idx"))
                if template.get("current_selector_idx") not in (None, "")
                else fallback.current_selector_idx
            ),
            media_start_time=ops_module._optional_float(template.get("media_start_time"))
            if template.get("media_start_time") not in (None, "")
            else fallback.media_start_time,
        )
    return fallback


def _reference_track_template(reference, *, track_type: int, angle_index: int, fallback, ops_module):
    matching = [template for template in reference.track_templates if int(template.get("type", -1)) == track_type]
    if angle_index < len(matching):
        template = matching[angle_index]
        return ops_module.TrackTemplate(
            subtype=int(template.get("subtype", fallback.subtype)),
            fields_blob=ops_module._decode_optional_bytes(template.get("fields_blob_b64")) or fallback.fields_blob,
            user_defined_name=(
                str(template.get("user_defined_name")).strip()
                if template.get("user_defined_name") is not None
                else fallback.user_defined_name
            ),
        )
    return fallback


def _coalesce_template_value(primary: Any, fallback: Any) -> Any:
    return primary if primary not in (None, "") else fallback


def _table_columns(cursor: sqlite3.Cursor, table_name: str) -> set[str]:
    return {str(row[1]) for row in cursor.execute(f"PRAGMA table_info({table_name})").fetchall()}


def _load_source_templates(
    cursor: sqlite3.Cursor,
    *,
    source_row,
    reference,
    angle_index: int,
    multicam_duration_frames: int,
    multicam_fps: float,
    ops_module,
):
    return ops_module._timing_load_source_templates(
        cursor,
        source_row=source_row,
        reference=reference,
        angle_index=angle_index,
        multicam_duration_frames=multicam_duration_frames,
        multicam_fps=multicam_fps,
        default_source_templates_fn=lambda *a, **kw: _default_source_templates(*a, **kw, ops_module=ops_module),
        reference_item_template_fn=lambda *a, **kw: _reference_item_template(*a, **kw, ops_module=ops_module),
        select_representative_item_row_fn=lambda *a, **kw: _select_representative_item_row(*a, **kw, ops_module=ops_module),
        reference_track_template_fn=lambda *a, **kw: _reference_track_template(*a, **kw, ops_module=ops_module),
        track_template_cls=ops_module.TrackTemplate,
        item_template_cls=ops_module.ItemTemplate,
        source_templates_cls=ops_module.SourceTemplates,
    )


def _resolve_angle_timing(
    *,
    source_row,
    templates,
    reference,
    start_offset_frames: int,
    media_start_time_base_seconds: float | None = None,
    source_start_offsets_mode: str = "additive",
    multicam_duration_frames: int,
    multicam_fps: float,
    ops_module,
):
    return ops_module._timing_resolve_angle_timing(
        source_row=source_row,
        templates=templates,
        reference=reference,
        start_offset_frames=start_offset_frames,
        media_start_time_base_seconds=media_start_time_base_seconds,
        source_start_offsets_mode=source_start_offsets_mode,
        multicam_duration_frames=multicam_duration_frames,
        multicam_fps=multicam_fps,
        angle_timing_seed_cls=ops_module.AngleTimingSeed,
    )


def create_multicam_clip(
    *,
    project_db_path: str,
    multicam_name: str,
    source_rows: list[Any],
    source_angle_labels: list[str] | None,
    angle_names: dict[str, str] | None,
    source_item_timing: list[dict[str, int | None]] | None,
    source_layout: str,
    sync_mode: str,
    source_cur_playhead_positions: list[int | str | None] | None,
    source_start_offsets_frames: list[int] | None,
    source_start_offsets_mode: str,
    audio_mode: str,
    reference_audio_angle: str | None,
    start_timecode: str | None,
    fixture,
    reference_source: str,
    preferred_duration_frames: int | None,
    create_backup: bool,
    ops_module,
) -> dict[str, Any]:
    normalized_audio_mode = str(audio_mode or "source_audio_channels").strip().lower().replace("-", "_")
    if normalized_audio_mode not in {
        "source_audio_channels",
        "reference_audio",
        "adaptive_tracks",
        "all_angles",
    }:
        raise ValidationError(
            "Unsupported native multicam audio mode.",
            details={
                "audio_mode": audio_mode,
                "supported_audio_modes": [
                    "source_audio_channels",
                    "reference_audio",
                    "adaptive_tracks",
                    "all_angles",
                ],
            },
        )
    normalized_reference_audio_angle = str(reference_audio_angle or "").strip() or None
    labels = [str(value or "").strip() for value in list(source_angle_labels or [])]
    if labels and len(labels) != len(source_rows):
        raise ValidationError(
            "source_angle_labels length must match source clip count.",
            details={"source_count": len(source_rows), "label_count": len(labels)},
        )
    if not labels:
        labels = [str(index + 1) for index in range(len(source_rows))]
    if any(not label for label in labels):
        raise ValidationError("source_angle_labels must not contain empty values.")
    angle_order = list(dict.fromkeys(labels))
    requested_angle_names = {
        str(key): str(value).strip()
        for key, value in dict(angle_names or {}).items()
        if str(key).strip() and str(value).strip()
    }
    if normalized_reference_audio_angle is None:
        normalized_reference_audio_angle = angle_order[0] if angle_order else None
    if normalized_reference_audio_angle not in angle_order:
        raise ValidationError(
            "reference_audio_angle must identify one logical multicam angle.",
            details={
                "reference_audio_angle": reference_audio_angle,
                "angle_order": angle_order,
            },
        )
    requested_angle_count = len(angle_order)
    source_clip_count = len(source_rows)
    multi_clip_angles = source_clip_count > requested_angle_count
    normalized_source_layout = str(source_layout or "contiguous").strip().lower().replace("_", "-")
    if normalized_source_layout not in {"contiguous", "sparse"}:
        raise ValidationError(
            "Unsupported native multicam source layout.",
            details={
                "source_layout": source_layout,
                "supported_source_layouts": ["contiguous", "sparse"],
            },
        )
    raw_item_timing = list(source_item_timing or [])
    if raw_item_timing and len(raw_item_timing) != source_clip_count:
        raise ValidationError(
            "source_item_timing length must match source clip count.",
            details={"source_count": source_clip_count, "source_item_timing_count": len(raw_item_timing)},
        )
    if not raw_item_timing:
        raw_item_timing = [{} for _ in source_rows]
    normalized_item_timing: list[dict[str, int | None]] = []
    for source_index, raw_timing in enumerate(raw_item_timing):
        if not isinstance(raw_timing, dict):
            raise ValidationError(
                "Each source_item_timing entry must be an object.",
                details={"source_index": source_index, "source_item_timing": raw_timing},
            )
        normalized: dict[str, int | None] = {}
        for field in ("record_start_frame", "source_in_frame", "duration_frames"):
            raw_value = raw_timing.get(field)
            try:
                value = int(raw_value) if raw_value is not None else None
            except (TypeError, ValueError) as exc:
                raise ValidationError(
                    f"Multicam source {field} must be an integer when provided.",
                    details={"source_index": source_index, field: raw_value},
                ) from exc
            if field in {"record_start_frame", "source_in_frame"} and value is not None and value < 0:
                raise ValidationError(
                    f"Multicam source {field} must be zero or greater.",
                    details={"source_index": source_index, field: value},
                )
            if field == "duration_frames" and value is not None and value <= 0:
                raise ValidationError(
                    "Multicam source duration_frames must be positive.",
                    details={"source_index": source_index, field: value},
                )
            normalized[field] = value
        normalized_item_timing.append(normalized)
    has_explicit_item_timing = any(
        any(value is not None for value in timing.values())
        for timing in normalized_item_timing
    )

    if requested_angle_count < 2:
        raise ValidationError(
            "Native DB multicam requires at least 2 logical angles.",
            details={"source_count": source_clip_count, "angle_count": requested_angle_count},
        )
    if requested_angle_count > MAX_SUPPORTED_ANGLE_COUNT:
        raise ValidationError(
            f"Native DB multicam currently supports at most {MAX_SUPPORTED_ANGLE_COUNT} logical angles.",
            details={
                "source_count": source_clip_count,
                "angle_count": requested_angle_count,
                "max_supported_angle_count": MAX_SUPPORTED_ANGLE_COUNT,
                "reason": "unsupported_angle_count",
            },
        )

    normalized_sync_mode = ops_module.normalize_native_angle_sync_mode(
        sync_mode,
        details_key="sync_mode",
        supported_key="supported_sync_modes",
    )
    start_offsets = [int(value) for value in list(source_start_offsets_frames or [])]
    if start_offsets and len(start_offsets) != len(source_rows):
        raise ValidationError(
            "source_start_offsets_frames length must match source clip count.",
            details={
                "source_count": len(source_rows),
                "offsets_count": len(start_offsets),
            },
        )
    if not start_offsets:
        start_offsets = [0] * len(source_rows)
    if multi_clip_angles and any(start_offsets):
        raise ValidationError(
            "Multi-clip angle creation does not yet support per-angle source offsets.",
            details={
                "reason": "multi_clip_source_offsets_not_verified",
                "source_start_offsets_frames": start_offsets,
            },
        )
    normalized_start_offsets_mode = str(source_start_offsets_mode or "additive").strip().lower()
    if normalized_start_offsets_mode not in {"additive", "anchor_zero", "timeline_offsets"}:
        raise ValidationError(
            "Unsupported source_start_offsets_mode.",
            details={
                "source_start_offsets_mode": source_start_offsets_mode,
                "supported_modes": ["additive", "anchor_zero", "timeline_offsets"],
            },
        )
    anchor_media_start_time_base: float | None = None
    if normalized_start_offsets_mode == "anchor_zero":
        anchor_index = next((index for index, value in enumerate(start_offsets) if int(value) == 0), 0)
        anchor_media_start_time_base = float(source_rows[anchor_index].media_start_time or 0.0)
    normalized_cur_playhead_positions = list(source_cur_playhead_positions or [])
    if normalized_cur_playhead_positions and len(normalized_cur_playhead_positions) != len(source_rows):
        raise ValidationError(
            "Native DB multicam source playhead positions must match the source clip count.",
            details={
                "source_count": len(source_rows),
                "position_count": len(normalized_cur_playhead_positions),
            },
        )
    fixture_provided = fixture is not None
    reference = fixture or ops_module.load_reference_multicam_fixture(requested_angle_count)
    reference_source_policy = ops_module.normalize_multicam_reference_source_policy(reference_source)
    reference_source = "explicit_fixture" if fixture_provided else "packaged_fixture"
    backup_path = f"{project_db_path}.bak"
    if create_backup:
        shutil.copy2(project_db_path, backup_path)

    working_db_path = f"{project_db_path}.cutagent-write"
    shutil.copy2(project_db_path, working_db_path)

    connection = sqlite3.connect(working_db_path)
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        cursor = connection.cursor()
        cursor.execute("BEGIN")

        if multi_clip_angles and reference_source_policy == "project_local_reference":
            raise ValidationError(
                "Multi-clip angle creation does not yet support project_local_reference.",
                details={
                    "reason": "multi_clip_project_local_reference_not_verified",
                    "reference_source": reference_source_policy,
                    "angle_count": requested_angle_count,
                    "source_clip_count": source_clip_count,
                },
            )
        if not fixture_provided and not multi_clip_angles and reference_source_policy in {"project_local_reference", "auto"}:
            matching_reference = ops_module._load_matching_project_reference(
                cursor,
                source_rows=source_rows,
                excluded_name=multicam_name,
                fallback=reference,
            )
            if matching_reference["reference"] is not None:
                reference = matching_reference["reference"]
                source_rows = matching_reference["ordered_source_rows"]
                reference_source = "project_local_reference"
            elif reference_source_policy == "project_local_reference" or ops_module._requires_local_reference(requested_angle_count):
                rejected_candidates = list(matching_reference.get("rejected_candidates") or [])
                if reference_source_policy == "project_local_reference":
                    reason = "invalid_local_reference_shape" if rejected_candidates else "project_local_reference_required"
                    raise ValidationError(
                        "Native multicam create requires a valid project-local reference when reference_source is project_local_reference.",
                        details={
                            "reason": reason,
                            "requested_angle_count": requested_angle_count,
                            "multicam_name": multicam_name,
                            "project_db_path": project_db_path,
                            "source_media_ids": [row.media_id for row in source_rows],
                            "candidate_count": int(matching_reference.get("candidate_count") or 0),
                            "rejected_candidates": rejected_candidates,
                            "reference_source_policy": reference_source_policy,
                            "support_tier": support_tier_for_angle_count(requested_angle_count),
                        },
                    )
                if ops_module._requires_calibrated_project_reference(requested_angle_count):
                    raise ValidationError(
                        "Native multicam create requires a calibrated local project reference for this angle count.",
                        details={
                            "reason": "project_local_reference_required",
                            "requested_angle_count": requested_angle_count,
                            "multicam_name": multicam_name,
                            "project_db_path": project_db_path,
                            "source_media_ids": [row.media_id for row in source_rows],
                            "candidate_count": int(matching_reference.get("candidate_count") or 0),
                            "rejected_candidates": rejected_candidates,
                            "support_tier": support_tier_for_angle_count(requested_angle_count),
                        },
                    )
                if rejected_candidates and not ops_module._can_fallback_to_packaged_reference_after_rejections(
                    requested_angle_count=requested_angle_count,
                    rejected_candidates=rejected_candidates,
                ):
                    raise ValidationError(
                        "Native multicam create requires a valid local project reference for this angle count.",
                        details={
                            "reason": "invalid_local_reference_shape",
                            "requested_angle_count": requested_angle_count,
                            "multicam_name": multicam_name,
                            "project_db_path": project_db_path,
                            "source_media_ids": [row.media_id for row in source_rows],
                            "candidate_count": int(matching_reference.get("candidate_count") or 0),
                            "rejected_candidates": rejected_candidates,
                        },
                    )
                if requested_angle_count >= 3 and not reference.preserve_reference_shape:
                    reference = replace(reference, preserve_reference_shape=True)

        if not fixture_provided and reference_source == "packaged_fixture" and requested_angle_count >= 3:
            reference = replace(reference, preserve_reference_shape=True)

        multicam_fps = ops_module._derive_multicam_fps(reference, source_rows)
        normalized_start_timecode = str(start_timecode or "").strip() or None
        if normalized_start_timecode is not None:
            try:
                multicam_start_frame = int(round(timecode_to_seconds(normalized_start_timecode, multicam_fps) * multicam_fps))
            except Exception as exc:
                raise ValidationError(
                    "Multicam start_timecode must be a valid HH:MM:SS:FF or HH:MM:SS;FF value.",
                    details={"start_timecode": start_timecode, "fps": multicam_fps},
                ) from exc
        else:
            multicam_start_frame = int(reference.item_start)
        uses_distinct_item_timing = multi_clip_angles or has_explicit_item_timing or normalized_source_layout == "sparse"
        resolved_item_timing: list[dict[str, int]] = []
        if uses_distinct_item_timing:
            missing_duration_indices = [
                index
                for index, row in enumerate(source_rows)
                if not row.duration_frames or int(row.duration_frames) <= 0
            ]
            if missing_duration_indices:
                raise ValidationError(
                    "Distinct multicam source items require a positive source duration for every clip.",
                    details={
                        "reason": "source_item_duration_required",
                        "missing_source_indices": missing_duration_indices,
                        "source_clip_count": source_clip_count,
                    },
                )
            next_end_by_angle = {angle: 0 for angle in angle_order}
            for source_index, (source_row, label, timing) in enumerate(
                zip(source_rows, labels, normalized_item_timing)
            ):
                source_duration = int(source_row.duration_frames or 0)
                source_in = int(timing["source_in_frame"] or 0)
                duration = (
                    int(timing["duration_frames"])
                    if timing["duration_frames"] is not None
                    else source_duration - source_in
                )
                record_start = (
                    int(timing["record_start_frame"])
                    if timing["record_start_frame"] is not None
                    else int(next_end_by_angle[label])
                )
                if source_in >= source_duration or source_in + duration > source_duration:
                    raise ValidationError(
                        "Multicam source range exceeds the available source media.",
                        details={
                            "reason": "source_item_range_out_of_bounds",
                            "source_index": source_index,
                            "angle": label,
                            "clip_name": source_row.name,
                            "source_in_frame": source_in,
                            "duration_frames": duration,
                            "source_duration_frames": source_duration,
                        },
                    )
                previous_end = int(next_end_by_angle[label])
                if record_start < previous_end:
                    raise ValidationError(
                        "Multicam source items on the same angle must not overlap or be out of timeline order.",
                        details={
                            "reason": "overlapping_source_items",
                            "source_index": source_index,
                            "angle": label,
                            "record_start_frame": record_start,
                            "previous_end_frame": previous_end,
                        },
                    )
                if normalized_source_layout == "contiguous" and record_start != previous_end:
                    raise ValidationError(
                        "Contiguous multicam source items must not contain leading or internal gaps.",
                        details={
                            "reason": "gap_requires_sparse_source_layout",
                            "source_index": source_index,
                            "angle": label,
                            "record_start_frame": record_start,
                            "expected_record_start_frame": previous_end,
                        },
                    )
                resolved_item_timing.append(
                    {
                        "record_start_frame": record_start,
                        "source_in_frame": source_in,
                        "duration_frames": duration,
                        "record_end_frame": record_start + duration,
                    }
                )
                next_end_by_angle[label] = record_start + duration
            duration_by_angle = {angle: int(next_end_by_angle[angle]) for angle in angle_order}
            derived_duration_frames = max(duration_by_angle.values())
        else:
            duration_by_angle = {
                angle_order[index]: int(row.duration_frames or 0)
                for index, row in enumerate(source_rows)
            }
            derived_duration_frames = ops_module._derive_multicam_duration(reference, source_rows)
        if preferred_duration_frames is not None:
            preferred_duration_frames = int(preferred_duration_frames)
            if preferred_duration_frames <= 0:
                raise ValidationError(
                    "preferred_duration_frames must be positive when provided.",
                    details={"preferred_duration_frames": preferred_duration_frames},
                )
            if uses_distinct_item_timing and preferred_duration_frames < int(derived_duration_frames):
                raise ValidationError(
                    "timeline duration would truncate one or more multicam source items.",
                    details={
                        "reason": "source_item_timeline_duration_too_short",
                        "preferred_duration_frames": preferred_duration_frames,
                        "required_duration_frames": int(derived_duration_frames),
                        "duration_by_angle": duration_by_angle,
                    },
                )
            multicam_duration_frames = (
                preferred_duration_frames
                if normalized_source_layout == "sparse"
                else min(int(derived_duration_frames), preferred_duration_frames)
            )
        else:
            multicam_duration_frames = int(derived_duration_frames)
        sequence_fps = ops_module._decode_rate_blob(reference.sequence_frame_rate) or multicam_fps
        sequence_media_extents = ops_module._encode_sequence_media_extents(
            multicam_start_frame,
            multicam_duration_frames,
            sequence_fps,
        )
        audio_mode_plan = build_audio_mode_plan(
            audio_mode=normalized_audio_mode,
            reference_audio_angle=str(normalized_reference_audio_angle),
            source_rows=source_rows,
            source_angle_labels=labels,
        )
        preserve_legacy_audio_shape = (
            normalized_audio_mode == "source_audio_channels"
            and not audio_mode_plan["has_explicit_source_audio_mapping"]
        )

        multicam_media_id = str(uuid.uuid4())
        sequence_id = str(uuid.uuid4())
        sequence_container_id = str(uuid.uuid4())
        sequence_unique_id = str(uuid.uuid4())
        folder_id = source_rows[0].folder_id
        if not folder_id:
            raise ValidationError(
                "Cannot determine the target Media Pool folder for the multicam clip.",
                details={"source_row": ops_module.asdict(source_rows[0])},
            )
        db_saved_time = ops_module._next_db_saved_time(cursor)

        video_track_ids = [str(uuid.uuid4()) for _ in angle_order]
        audio_track_ids = [str(uuid.uuid4()) for _ in angle_order]
        video_item_ids = [str(uuid.uuid4()) for _ in source_rows]
        audio_item_ids = [str(uuid.uuid4()) for _ in source_rows]
        sm2tiitem_columns = _table_columns(cursor, "Sm2TiItem")
        include_item_state_columns = {
            "LastChangedTime",
            "LastRenderedTime",
            "IsMarkedForCaching",
        }.issubset(sm2tiitem_columns)

        cursor.execute(
            """
            INSERT INTO Sm2MpMedia (
                Sm2MpMedia_id, DbType, Name, MpFolder, CurPlayheadPosition, AudioSource,
                FrameRate, PTZRPresetType, SlateTC, VideoMetadata, Sm2MpFolder_id,
                Sequence, VirtualAudioTracksBA, UniqueMediaPoolItemId, VideoType,
                LeftEyeOffset, RightEyeOffset, FieldsBlob, BlobLockSysId, CompTableLockSysId, VersionTableLockSysId
            ) VALUES (?, 'Sm2MpMulticamClip', ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?, 0, 0, 0, ?, '', '', '')
            """,
            (
                multicam_media_id,
                multicam_name,
                folder_id,
                reference.cur_playhead_position,
                reference.audio_source if preserve_legacy_audio_shape else "AUDIO_SOURCE_EMBEDDED",
                reference.frame_rate,
                reference.slate_tc,
                reference.video_metadata,
                folder_id,
                sequence_id,
                (
                    reference.virtual_audio_tracks
                    if preserve_legacy_audio_shape
                    else audio_mode_plan["media_virtual_audio_tracks_ba"]
                ),
                str(uuid.uuid4()),
                reference.fields_blob,
            ),
        )

        cursor.execute(
            """
            INSERT INTO Sm2Sequence (
                Sm2Sequence_id, DbType, Parent, pLmVerTable, Sm2MpMedia_id,
                NumOutputAudioChannels, OutputAudioGain, FrameRate, Resolution, MediaExtents,
                LastChangedTime, RenderCacheBA, AuxRenderCacheBA, UniqueSequenceId,
                FieldsBlob, DbSavedTime, LockStatus, BlobLockSysId, VersionTableLockSysId, LockSysId
            ) VALUES (?, 'Sm2Sequence', ?, NULL, ?, ?, 0.0, ?, ?, ?, 0, ?, ?, ?, ?, ?, 0, '', '', '')
            """,
            (
                sequence_id,
                multicam_media_id,
                multicam_media_id,
                1 if preserve_legacy_audio_shape else int(audio_mode_plan["audio_output_channel_count"]),
                reference.sequence_frame_rate,
                reference.sequence_resolution,
                sequence_media_extents,
                reference.sequence_render_cache,
                reference.sequence_aux_render_cache,
                sequence_unique_id,
                ops_module._remap_sequence_fields_blob(
                    reference.sequence_fields_blob,
                    new_sequence_container_id=sequence_container_id,
                    new_unique_sequence_id=sequence_unique_id,
                ),
                db_saved_time,
            ),
        )

        cursor.execute(
            """
            INSERT INTO Sm2SequenceContainer (
                Sm2SequenceContainer_id, DbType, Sm2Sequence_id, FieldsBlob, DbSavedTime
            ) VALUES (?, 'Sm2SequenceContainer', ?, NULL, ?)
            """,
            (sequence_container_id, sequence_id, db_saved_time),
        )

        if normalized_cur_playhead_positions:
            for index, source_row in enumerate(source_rows):
                cursor.execute(
                    "UPDATE Sm2MpMedia SET CurPlayheadPosition = ? WHERE Sm2MpMedia_id = ?",
                    (
                        None if normalized_cur_playhead_positions[index] is None else str(normalized_cur_playhead_positions[index]),
                        source_row.media_id,
                    ),
                )

        angle_index_by_label = {label: index for index, label in enumerate(angle_order)}
        source_item_indices: list[int] = []
        next_item_index_by_angle = {label: 0 for label in angle_order}
        source_templates_by_index: list[Any] = []
        selector_template_by_angle: dict[int, Any] = {}
        for index, source_row in enumerate(source_rows):
            source_label = labels[index]
            angle_index = angle_index_by_label[source_label]
            item_index = next_item_index_by_angle[source_label]
            next_item_index_by_angle[source_label] = item_index + 1
            source_item_indices.append(item_index)
            templates = _load_source_templates(
                cursor,
                source_row=source_row,
                reference=reference,
                angle_index=angle_index,
                multicam_duration_frames=multicam_duration_frames,
                multicam_fps=multicam_fps,
                ops_module=ops_module,
            )
            source_templates_by_index.append(templates)
            selector_template_by_angle.setdefault(angle_index, templates)
            angle_timing = _resolve_angle_timing(
                source_row=source_row,
                templates=templates,
                reference=reference,
                start_offset_frames=start_offsets[index],
                media_start_time_base_seconds=anchor_media_start_time_base,
                source_start_offsets_mode=normalized_start_offsets_mode,
                multicam_duration_frames=multicam_duration_frames,
                multicam_fps=multicam_fps,
                ops_module=ops_module,
            )
            if normalized_start_timecode is not None and not uses_distinct_item_timing:
                angle_timing = replace(
                    angle_timing,
                    item_start_frame=(
                        multicam_start_frame
                        + int(angle_timing.item_start_frame)
                        - int(reference.item_start)
                    ),
                )
            if uses_distinct_item_timing:
                item_timing = resolved_item_timing[index]
                angle_timing = replace(
                    angle_timing,
                    item_start_frame=multicam_start_frame + int(item_timing["record_start_frame"]),
                    item_duration_frames=int(item_timing["duration_frames"]),
                    media_timemap_duration_frames=int(item_timing["duration_frames"]),
                    sequence_extents_duration_frames=multicam_duration_frames,
                    source_in_frame=int(item_timing["source_in_frame"]),
                )
            requested_angle_name = requested_angle_names.get(source_label)
            video_label = requested_angle_name or (
                templates.video_track.user_defined_name
                if templates.video_track.user_defined_name is not None
                else f"Angle {angle_index + 1}"
            )
            audio_label = requested_angle_name or (
                templates.audio_track.user_defined_name
                if templates.audio_track.user_defined_name is not None
                else f"Angle {angle_index + 1}"
            )
            dynamic_media_timemap = ops_module._encode_media_timemap_ba(
                angle_timing.media_timemap_duration_frames,
                multicam_fps,
            )

            if item_index == 0:
                cursor.execute(
                    """
                    INSERT INTO Sm2TiTrack (
                        Sm2TiTrack_id, DbType, Type, SubType, Flags, Sequence,
                        UserDefinedName, FieldsBlob, Sm2SequenceContainer_id
                    ) VALUES (?, 'Sm2TiTrack', 0, ?, 0, ?, ?, ?, ?)
                    """,
                    (video_track_ids[angle_index], templates.video_track.subtype, sequence_id, video_label, templates.video_track.fields_blob, sequence_container_id),
                )
                cursor.execute(
                    """
                    INSERT INTO Sm2TiTrack (
                        Sm2TiTrack_id, DbType, Type, SubType, Flags, Sequence,
                        UserDefinedName, FieldsBlob, Sm2SequenceContainer_id
                    ) VALUES (?, 'Sm2TiTrack', 1, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        audio_track_ids[angle_index],
                        (
                            templates.audio_track.subtype
                            if preserve_legacy_audio_shape
                            else int(audio_mode_plan["track_subtype_by_angle"][source_label])
                        ),
                        (
                            2
                            if normalized_audio_mode == "reference_audio"
                            and source_label != normalized_reference_audio_angle
                            else 0
                        ),
                        sequence_id,
                        audio_label,
                        templates.audio_track.fields_blob,
                        sequence_container_id,
                    ),
                )
            if not templates.video_item.is_placeholder:
                video_item_columns = [
                    "Sm2TiItem_id","DbType","Name","Start","Duration",'"In"',"MediaRef","MediaStartTime","MediaFilePath",
                    "MediaTimemapBA","PreConformMediaExtents","MediaFrameRate","Sm2TiTrack_id","UiMemento","Flags","PriorityIndex",
                ]
                video_item_values: list[Any] = [
                    video_item_ids[index],"Sm2TiVideoClip",source_row.name,str(angle_timing.item_start_frame),str(angle_timing.item_duration_frames),
                    str(angle_timing.source_in_frame)
                    if uses_distinct_item_timing or int(angle_timing.source_in_frame) > 0
                    else templates.video_item.in_value,
                    source_row.media_id,angle_timing.media_start_time_seconds,templates.video_item.media_file_path,
                    dynamic_media_timemap,
                    templates.video_item.preconform_media_extents,templates.video_item.media_frame_rate,video_track_ids[angle_index],0,0,0,
                ]
                if include_item_state_columns:
                    video_item_columns.extend(["LastChangedTime", "LastRenderedTime", "IsMarkedForCaching"])
                    video_item_values.extend([0, 0, 0])
                video_item_columns.extend([
                    "ThumbnailDirtyFlag","RenderTextEnabled","RenderTextGanged","RenderTextPrefixed","IsForceConformed","MatchConflictState",
                    "IsPreConformed","MixedFrameRateAlignment","UseOppositeSrcForLeftEye","UseOppositeSrcForRightEye","WasDisbanded",
                    "CurrentSelectorIdx","FieldsBlob",
                ])
                video_item_values.extend([1,1,1,1,1,0,0,0,0,0,0,templates.video_item.current_selector_idx,templates.video_item.fields_blob])
                video_placeholders = ", ".join("?" for _ in video_item_columns)
                cursor.execute(f"""INSERT INTO Sm2TiItem ({", ".join(video_item_columns)}) VALUES ({video_placeholders})""", tuple(video_item_values))
            if not templates.audio_item.is_placeholder:
                audio_item_columns = [
                    "Sm2TiItem_id","DbType","Name","Start","Duration",'"In"',"MediaRef","MediaStartTime","MediaFilePath","MediaTimemapBA",
                    "MediaFrameRate","VirtualAudioTrackBA","MediaTrackIdx","Sm2TiTrack_id","UiMemento","Flags","PriorityIndex",
                ]
                audio_item_values: list[Any] = [
                    audio_item_ids[index],"Sm2TiAudioClip",source_row.name,str(angle_timing.item_start_frame),str(angle_timing.item_duration_frames),
                    str(angle_timing.source_in_frame)
                    if uses_distinct_item_timing or int(angle_timing.source_in_frame) > 0
                    else templates.audio_item.in_value,
                    source_row.media_id,angle_timing.media_start_time_seconds,templates.audio_item.media_file_path,
                    dynamic_media_timemap,
                    templates.audio_item.media_frame_rate,
                    (
                        templates.audio_item.virtual_audio_track_ba
                        if preserve_legacy_audio_shape
                        else audio_mode_plan["item_virtual_audio_track_ba_by_source_index"][index]
                    ),
                    templates.audio_item.media_track_idx,
                    audio_track_ids[angle_index],0,0,0,
                ]
                if include_item_state_columns:
                    audio_item_columns.extend(["LastChangedTime", "LastRenderedTime", "IsMarkedForCaching"])
                    audio_item_values.extend([0, 0, 0])
                audio_item_columns.extend([
                    "ThumbnailDirtyFlag","RenderTextEnabled","RenderTextGanged","RenderTextPrefixed","IsForceConformed","MatchConflictState",
                    "IsPreConformed","MixedFrameRateAlignment","UseOppositeSrcForLeftEye","UseOppositeSrcForRightEye","WasDisbanded",
                    "CurrentSelectorIdx","FieldsBlob",
                ])
                audio_item_values.extend([1,1,1,1,1,0,0,0,0,0,0,templates.audio_item.current_selector_idx,templates.audio_item.fields_blob])
                audio_placeholders = ", ".join("?" for _ in audio_item_columns)
                cursor.execute(f"""INSERT INTO Sm2TiItem ({", ".join(audio_item_columns)}) VALUES ({audio_placeholders})""", tuple(audio_item_values))

        for angle_index in range(requested_angle_count):
            cursor.execute("INSERT INTO Sm2SequenceContainer_Sm2TiTrack VALUES (?, ?, 'VideoTrackVec', ?)", (sequence_container_id, video_track_ids[angle_index], angle_index))
            cursor.execute("INSERT INTO Sm2SequenceContainer_Sm2TiTrack VALUES (?, ?, 'AudioTrackVec', ?)", (sequence_container_id, audio_track_ids[angle_index], angle_index))
        for index, templates in enumerate(source_templates_by_index):
            angle_index = angle_index_by_label[labels[index]]
            item_index = source_item_indices[index]
            if not templates.video_item.is_placeholder:
                cursor.execute("INSERT INTO Sm2TiItem_Sm2TiTrack VALUES (?, ?, 'Items', ?)", (video_track_ids[angle_index], video_item_ids[index], item_index))
            if not templates.audio_item.is_placeholder:
                cursor.execute("INSERT INTO Sm2TiItem_Sm2TiTrack VALUES (?, ?, 'Items', ?)", (audio_track_ids[angle_index], audio_item_ids[index], item_index))

        cursor.execute(
            """
            INSERT INTO Sm2MpFolder_Sm2MpMedia (DbOwner, DbAssociate, DbPropertyName, DbIndex)
            SELECT ?, ?, 'MediaVec', COALESCE(MAX(DbIndex) + 1, 0)
            FROM Sm2MpFolder_Sm2MpMedia
            WHERE DbOwner = ?
            """,
            (folder_id, multicam_media_id, folder_id),
        )

        connection.commit()
        expected_video_selector_mapping = ops_module._video_selector_mapping_from_source_templates(
            [selector_template_by_angle[index] for index in range(requested_angle_count)]
        )
        binding_validation = ops_module._validate_created_multicam_binding(
            cursor,
            multicam_media_id=multicam_media_id,
            expected_source_rows=source_rows,
            expected_source_angle_labels=labels,
            expected_source_item_timing=(
                [
                    {
                        "start_frame": multicam_start_frame + int(item["record_start_frame"]),
                        "duration_frames": int(item["duration_frames"]),
                        "source_in_frame": int(item["source_in_frame"]),
                    }
                    for item in resolved_item_timing
                ]
                if uses_distinct_item_timing
                else None
            ),
            expected_video_selector_mapping=expected_video_selector_mapping,
        )
        if binding_validation["status"] != "verified":
            raise ValidationError(
                "Created native multicam binding did not match the requested source clips.",
                details={
                    "reason": "post_create_binding_validation_failed",
                    "multicam_name": multicam_name,
                    "multicam_media_id": multicam_media_id,
                    "multicam_sequence_id": sequence_id,
                    "project_db_path": project_db_path,
                    "reference_source": reference_source,
                    "binding_validation": binding_validation,
                },
            )
        connection.close()
        connection = None
        os.replace(working_db_path, project_db_path)
        audit = build_multicam_reference_audit(project_db_path, candidate_media_id=multicam_media_id, config=AuditReferenceConfig())
        return {
            "multicam_name": multicam_name,
            "angle_count": requested_angle_count,
            "source_clip_count": source_clip_count,
            "source_angle_labels": labels,
            "angle_names": {
                label: requested_angle_names.get(label) or f"Angle {index + 1}"
                for index, label in enumerate(angle_order)
            },
            "source_counts_by_angle": {
                angle: labels.count(angle)
                for angle in angle_order
            },
            "source_layout": normalized_source_layout,
            "source_item_representation": SOURCE_ITEM_REPRESENTATION,
            "source_clip_count_per_angle_limit": SOURCE_CLIP_COUNT_PER_ANGLE_LIMIT,
            "creates_flattened_media": False,
            "duration_by_angle": duration_by_angle,
            "trailing_gap_frames_by_angle": {
                angle: max(0, int(multicam_duration_frames) - int(duration_by_angle[angle]))
                for angle in angle_order
            },
            "source_item_timing": [
                {
                    "source_index": index,
                    "angle": labels[index],
                    "item_index": source_item_indices[index],
                    **item,
                }
                for index, item in enumerate(resolved_item_timing)
            ],
            "multicam_duration_frames": multicam_duration_frames,
            "multicam_media_id": multicam_media_id,
            "multicam_sequence_id": sequence_id,
            "project_db_path": project_db_path,
            "backup_path": backup_path if create_backup else None,
            "folder_id": folder_id,
            "route": "db_native",
            "source_media_ids": [row.media_id for row in source_rows],
            "fixture_schema_family": reference.schema_family,
            "reference_source": reference_source,
            "reference_source_policy": "explicit_fixture" if fixture_provided else reference_source_policy,
            "reference_angle_count": reference.angle_count,
            "binding_validation": binding_validation,
            "support_tier": support_tier_for_angle_count(
                requested_angle_count,
                has_multi_clip_angle=source_clip_count > requested_angle_count,
                source_layout=normalized_source_layout,
            ),
            "sync_mode": normalized_sync_mode,
            "sync_engine": "cutagent",
            "audio_mode": normalized_audio_mode,
            "reference_audio_angle": normalized_reference_audio_angle,
            "audio_track_policy": (
                "reference_angle_only"
                if normalized_audio_mode == "reference_audio"
                else "adaptive_per_angle"
                if normalized_audio_mode == "adaptive_tracks"
                else "all_angle_tracks_exposed"
                if normalized_audio_mode == "all_angles"
                else "follow_selected_source_angle"
            ),
            "audio_mapping": audio_mode_plan["media_track_mapping"],
            "audio_channel_count_by_angle": audio_mode_plan["channel_count_by_angle"],
            "audio_output_track_count": audio_mode_plan["audio_output_track_count"],
            "audio_output_channel_count": audio_mode_plan["audio_output_channel_count"],
            "start_timecode": normalized_start_timecode,
            "start_frame": multicam_start_frame,
            "source_start_offsets_frames": start_offsets,
            "source_start_offsets_mode": normalized_start_offsets_mode,
            "source_start_offsets_anchor_media_start_time": anchor_media_start_time_base,
            "source_cur_playhead_positions": normalized_cur_playhead_positions or [row.cur_playhead_position for row in source_rows],
            "db_audit": audit,
        }
    except Exception:
        if connection is not None:
            connection.rollback()
        raise
    finally:
        if connection is not None:
            connection.close()
        try:
            if os.path.exists(working_db_path):
                os.remove(working_db_path)
        except OSError:
            pass
