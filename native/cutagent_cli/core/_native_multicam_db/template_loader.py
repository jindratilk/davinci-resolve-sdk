from __future__ import annotations

import base64
import sqlite3
from typing import Any


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _project_reference_timing_rejection(
    *,
    fallback,
    source_rows: list[Any],
    video_rows: list[Any],
    audio_rows: list[Any],
    ops_module,
) -> dict[str, Any] | None:
    rejection: dict[str, Any] = {"reasons": []}
    expected_item_start = _optional_int(fallback.item_start)
    actual_video_item_starts = [
        value for value in (_optional_int(row[13]) for row in video_rows) if value is not None
    ]
    if expected_item_start is not None and any(value != expected_item_start for value in actual_video_item_starts):
        rejection["reasons"].append("reference_item_start_mismatch")
        rejection["expected_item_start"] = expected_item_start
        rejection["actual_video_item_starts"] = actual_video_item_starts

    source_media_start_times = {
        str(row.media_id): float(row.media_start_time)
        for row in source_rows
        if getattr(row, "media_start_time", None) not in (None, "")
    }
    media_start_time_mismatches: list[dict[str, Any]] = []
    for kind, rows in (("video", video_rows), ("audio", audio_rows)):
        for row in rows:
            media_ref = str(row[3] or "").strip()
            if not media_ref or media_ref not in source_media_start_times:
                continue
            actual = ops_module._optional_float(row[11])
            expected = source_media_start_times[media_ref]
            if actual is None:
                continue
            if abs(float(actual) - expected) > 0.001:
                media_start_time_mismatches.append(
                    {
                        "kind": kind,
                        "media_ref": media_ref,
                        "expected": expected,
                        "actual": float(actual),
                    }
                )
    if media_start_time_mismatches:
        rejection["reasons"].append("reference_media_start_time_mismatch")
        rejection["media_start_time_mismatches"] = media_start_time_mismatches

    return rejection if rejection["reasons"] else None


def _matching_reference_is_acceptable(
    *,
    fallback,
    candidate_name: str,
    candidate_fields_blob: bytes | None = None,
    track_templates: list[dict[str, Any]],
    item_templates: list[dict[str, Any]],
    ops_module,
) -> dict[str, Any]:
    resolved_angle_count = sum(1 for template in track_templates if int(template.get("type", -1)) == 0)
    selector_validation = ops_module._validate_reference_video_selector_shape(
        resolved_angle_count=resolved_angle_count,
        expected_mapping=ops_module._video_selector_mapping_from_item_templates(fallback.item_templates),
        actual_mapping=ops_module._video_selector_mapping_from_item_templates(item_templates),
    )
    if ops_module._requires_local_reference(resolved_angle_count) and any(
        bool(template.get("is_placeholder")) for template in item_templates
    ):
        return {
            "acceptable": False,
            "shape_valid": False,
            "selector_valid": selector_validation["valid"],
            **selector_validation,
        }
    if resolved_angle_count >= 5 and len(candidate_fields_blob or b"") < 224:
        return {
            "acceptable": False,
            "shape_valid": False,
            "selector_valid": selector_validation["valid"],
            "shape_reason": "multicam_media_fields_blob_too_small",
            **selector_validation,
        }

    expected_track_lengths = {
        "video": [
            len(ops_module._decode_optional_bytes(template.get("fields_blob_b64")) or b"")
            for template in fallback.track_templates
            if int(template.get("type", -1)) == 0
        ],
        "audio": [
            len(ops_module._decode_optional_bytes(template.get("fields_blob_b64")) or b"")
            for template in fallback.track_templates
            if int(template.get("type", -1)) == 1
        ],
    }
    candidate_track_lengths = {
        "video": [
            len(ops_module._decode_optional_bytes(template.get("fields_blob_b64")) or b"")
            for template in track_templates
            if int(template.get("type", -1)) == 0
        ],
        "audio": [
            len(ops_module._decode_optional_bytes(template.get("fields_blob_b64")) or b"")
            for template in track_templates
            if int(template.get("type", -1)) == 1
        ],
    }
    expected_item_lengths = {
        "video": [
            len(ops_module._decode_optional_bytes(template.get("fields_blob_b64")) or b"")
            for template in fallback.item_templates
            if str(template.get("db_type") or "").strip() != "Sm2TiAudioClip"
        ],
        "audio": [
            len(ops_module._decode_optional_bytes(template.get("fields_blob_b64")) or b"")
            for template in fallback.item_templates
            if str(template.get("db_type") or "").strip() == "Sm2TiAudioClip"
        ],
    }
    candidate_item_lengths = {
        "video": [
            len(ops_module._decode_optional_bytes(template.get("fields_blob_b64")) or b"")
            for template in item_templates
            if str(template.get("db_type") or "").strip() != "Sm2TiAudioClip"
        ],
        "audio": [
            len(ops_module._decode_optional_bytes(template.get("fields_blob_b64")) or b"")
            for template in item_templates
            if str(template.get("db_type") or "").strip() == "Sm2TiAudioClip"
        ],
    }
    if (
        len(candidate_track_lengths["video"]) != len(expected_track_lengths["video"])
        or len(candidate_track_lengths["audio"]) != len(expected_track_lengths["audio"])
        or len(candidate_item_lengths["video"]) != len(expected_item_lengths["video"])
        or len(candidate_item_lengths["audio"]) != len(expected_item_lengths["audio"])
    ):
        return {
            "acceptable": False,
            "shape_valid": False,
            "selector_valid": selector_validation["valid"],
            **selector_validation,
        }
    tolerance = 10
    allow_sparse_placeholder = str(candidate_name or "").strip() in ops_module._SPARSE_LOCAL_MULTICAM_REFERENCE_NAMES
    for key in ("video", "audio"):
        for candidate, reference_length in zip(candidate_track_lengths[key], expected_track_lengths[key]):
            if candidate < max(1, reference_length - tolerance):
                return {
                    "acceptable": False,
                    "shape_valid": False,
                    "selector_valid": selector_validation["valid"],
                    **selector_validation,
                }
    placeholder_budget = {"video": 1, "audio": 1} if allow_sparse_placeholder else {"video": 0, "audio": 0}
    candidate_items_by_kind = {
        "video": [
            template for template in item_templates if str(template.get("db_type") or "").strip() != "Sm2TiAudioClip"
        ],
        "audio": [
            template for template in item_templates if str(template.get("db_type") or "").strip() == "Sm2TiAudioClip"
        ],
    }
    for key in ("video", "audio"):
        for template, candidate, reference_length in zip(
            candidate_items_by_kind[key],
            candidate_item_lengths[key],
            expected_item_lengths[key],
        ):
            if template.get("is_placeholder") and candidate == 0 and placeholder_budget[key] > 0:
                placeholder_budget[key] -= 1
                continue
            if candidate < max(1, reference_length - tolerance):
                return {
                    "acceptable": False,
                    "shape_valid": False,
                    "selector_valid": selector_validation["valid"],
                    **selector_validation,
                }
    return {
        "acceptable": selector_validation["valid"],
        "shape_valid": True,
        "selector_valid": selector_validation["valid"],
        **selector_validation,
    }


def _load_matching_project_reference(
    cursor: sqlite3.Cursor,
    *,
    source_rows: list[Any],
    excluded_name: str,
    fallback,
    ops_module,
) -> dict[str, Any]:
    source_media_ids = {row.media_id for row in source_rows}
    candidate_rows = cursor.execute(
        """
        SELECT Sm2MpMedia_id, Name, CurPlayheadPosition, AudioSource, FrameRate, SlateTC,
               VideoMetadata, VirtualAudioTracksBA, FieldsBlob
        FROM Sm2MpMedia
        WHERE DbType = 'Sm2MpMulticamClip'
          AND Name <> ?
        ORDER BY rowid DESC
        """,
        (excluded_name,),
    ).fetchall()
    result: dict[str, Any] = {
        "reference": None,
        "ordered_source_rows": None,
        "candidate_count": len(candidate_rows),
        "matched_candidate_name": None,
        "rejected_candidates": [],
    }
    structural_match: dict[str, Any] | None = None

    def _candidate_sort_key(candidate_row: tuple[Any, ...]) -> tuple[int, int, str]:
        clip_name = str(candidate_row[1] or "").strip()
        preferred = int(not ops_module._is_preferred_local_reference_name(clip_name))
        generated = int(clip_name.startswith(ops_module._TOOL_GENERATED_MULTICAM_NAME_PREFIXES))
        return (preferred, generated, clip_name.lower())

    for candidate in sorted(candidate_rows, key=_candidate_sort_key):
        media_id = str(candidate[0] or "")
        clip_name = str(candidate[1] or "").strip()
        rejection: dict[str, Any] = {
            "clip_name": clip_name,
            "media_id": media_id,
            "reasons": [],
        }
        if ops_module._requires_local_reference(int(fallback.angle_count or 0)) and clip_name.startswith(
            ops_module._TOOL_GENERATED_MULTICAM_NAME_PREFIXES
        ):
            rejection["reasons"].append("tool_generated_reference_excluded")
            result["rejected_candidates"].append(rejection)
            continue
        sequence_row = cursor.execute(
            """
            SELECT Sm2Sequence_id, FrameRate, Resolution, MediaExtents, FieldsBlob,
                   RenderCacheBA, AuxRenderCacheBA
            FROM Sm2Sequence
            WHERE Sm2MpMedia_id = ?
            LIMIT 1
            """,
            (media_id,),
        ).fetchone()
        if sequence_row is None:
            rejection["reasons"].append("missing_sequence")
            result["rejected_candidates"].append(rejection)
            continue
        sequence_id = str(sequence_row[0] or "")
        video_rows = cursor.execute(
            """
            SELECT
                t.SubType,
                t.UserDefinedName,
                t.FieldsBlob,
                i.MediaRef,
                i.MediaFilePath,
                i.MediaTimemapBA,
                i.PreConformMediaExtents,
                i.MediaFrameRate,
                i.FieldsBlob,
                i."In",
                i.MediaTrackIdx,
                i.MediaStartTime,
                i.CurrentSelectorIdx,
                i.Start,
                i.Duration
            FROM Sm2TiTrack t
            LEFT JOIN Sm2TiItem i ON i.Sm2TiTrack_id = t.Sm2TiTrack_id
            WHERE t.Sequence = ?
              AND t.Type = 0
              AND (i.DbType = 'Sm2TiVideoClip' OR i.Sm2TiItem_id IS NULL)
            ORDER BY COALESCE(t.UserDefinedName, ''), t.rowid
            """,
            (sequence_id,),
        ).fetchall()
        if len(video_rows) != len(source_rows):
            rejection["reasons"].append("video_track_count_mismatch")
            rejection["video_track_count"] = len(video_rows)
            result["rejected_candidates"].append(rejection)
            continue
        video_media_ids = [str(row[3] or "").strip() or None for row in video_rows]
        rejection["video_source_mapping"] = video_media_ids
        if any(media_ref is None for media_ref in video_media_ids):
            rejection["reasons"].append("video_placeholder_angle")
            result["rejected_candidates"].append(rejection)
            continue
        if len(set(video_media_ids)) != len(source_rows):
            rejection["reasons"].append("video_source_not_unique")
            result["rejected_candidates"].append(rejection)
            continue
        exact_video_source_set = set(video_media_ids) == source_media_ids
        if not exact_video_source_set:
            rejection["reasons"].append("video_source_set_mismatch")
        audio_rows = cursor.execute(
            """
            SELECT
                t.SubType,
                t.UserDefinedName,
                t.FieldsBlob,
                i.MediaRef,
                i.MediaFilePath,
                i.MediaTimemapBA,
                i.MediaFrameRate,
                i.VirtualAudioTrackBA,
                i.FieldsBlob,
                i."In",
                i.MediaTrackIdx,
                i.MediaStartTime,
                i.CurrentSelectorIdx
            FROM Sm2TiTrack t
            LEFT JOIN Sm2TiItem i ON i.Sm2TiTrack_id = t.Sm2TiTrack_id
            WHERE t.Sequence = ?
              AND t.Type = 1
              AND (i.DbType = 'Sm2TiAudioClip' OR i.Sm2TiItem_id IS NULL)
            ORDER BY COALESCE(t.UserDefinedName, ''), t.rowid
            """,
            (sequence_id,),
        ).fetchall()
        if len(audio_rows) != len(source_rows):
            rejection["reasons"].append("audio_track_count_mismatch")
            rejection["audio_track_count"] = len(audio_rows)
            result["rejected_candidates"].append(rejection)
            continue
        audio_media_ids = [str(row[3] or "").strip() or None for row in audio_rows]
        rejection["audio_source_mapping"] = audio_media_ids
        if any(media_ref is None for media_ref in audio_media_ids):
            rejection["reasons"].append("audio_placeholder_angle")
            result["rejected_candidates"].append(rejection)
            continue
        if len(set(audio_media_ids)) != len(source_rows):
            rejection["reasons"].append("audio_source_not_unique")
            result["rejected_candidates"].append(rejection)
            continue
        exact_audio_source_set = set(audio_media_ids) == source_media_ids
        if not exact_audio_source_set:
            rejection["reasons"].append("audio_source_set_mismatch")
        if audio_media_ids != video_media_ids:
            rejection["reasons"].append("audio_video_order_mismatch")
            result["rejected_candidates"].append(rejection)
            continue
        timing_rejection = _project_reference_timing_rejection(
            fallback=fallback,
            source_rows=source_rows,
            video_rows=video_rows,
            audio_rows=audio_rows,
            ops_module=ops_module,
        )
        if timing_rejection is not None:
            rejection.update(timing_rejection)
            result["rejected_candidates"].append(rejection)
            continue
        ordered_rows = list(source_rows)
        track_templates: list[dict[str, Any]] = []
        item_templates: list[dict[str, Any]] = []
        for index, row in enumerate(video_rows):
            track_templates.append(
                {
                    "type": 0,
                    "subtype": int(row[0] or 0),
                    "user_defined_name": str(row[1] or ""),
                    "fields_blob_b64": base64.b64encode(row[2]).decode("ascii") if row[2] else None,
                }
            )
            item_templates.append(
                ops_module._build_reference_template_payload(
                    db_type="Sm2TiVideoClip",
                    track_index=index,
                    is_placeholder=row[3] in (None, ""),
                    media_file_path=str(row[4] or "") or None,
                    media_timemap_ba=row[5],
                    preconform_media_extents=row[6],
                    media_frame_rate=row[7],
                    virtual_audio_track_ba=None,
                    fields_blob=row[8],
                    in_value=str(row[9]).strip() if row[9] not in (None, "") else None,
                    media_track_idx=None,
                    current_selector_idx=int(row[12]) if row[12] not in (None, "") else None,
                    media_start_time=ops_module._optional_float(row[11]),
                )
            )
        for index, row in enumerate(audio_rows):
            track_templates.append(
                {
                    "type": 1,
                    "subtype": int(row[0] or 257),
                    "user_defined_name": str(row[1] or ""),
                    "fields_blob_b64": base64.b64encode(row[2]).decode("ascii") if row[2] else None,
                }
            )
            item_templates.append(
                ops_module._build_reference_template_payload(
                    db_type="Sm2TiAudioClip",
                    track_index=index,
                    is_placeholder=row[3] in (None, ""),
                    media_file_path=str(row[4] or "") or None,
                    media_timemap_ba=row[5],
                    preconform_media_extents=None,
                    media_frame_rate=row[6],
                    virtual_audio_track_ba=row[7],
                    fields_blob=row[8],
                    in_value=str(row[9]).strip() if row[9] not in (None, "") else None,
                    media_track_idx=int(row[10]) if row[10] not in (None, "") else None,
                    current_selector_idx=int(row[12]) if row[12] not in (None, "") else None,
                    media_start_time=ops_module._optional_float(row[11]),
                )
            )

        if len(source_rows) >= 5:
            actual_selector_mapping = ops_module._video_selector_mapping_from_item_templates(item_templates)
            selector_validation = ops_module._validate_reference_video_selector_shape(
                resolved_angle_count=len(source_rows),
                expected_mapping=actual_selector_mapping,
                actual_mapping=actual_selector_mapping,
            )
            candidate_fields_blob_len = len(candidate[8] or b"")
            acceptance = {
                "acceptable": selector_validation["valid"] and candidate_fields_blob_len >= 224,
                "shape_valid": candidate_fields_blob_len >= 224,
                "selector_valid": selector_validation["valid"],
                "shape_reason": "multicam_media_fields_blob_too_small" if candidate_fields_blob_len < 224 else None,
                **selector_validation,
            }
        else:
            acceptance = _matching_reference_is_acceptable(
                fallback=fallback,
                candidate_name=clip_name,
                candidate_fields_blob=candidate[8],
                track_templates=track_templates,
                item_templates=item_templates,
                ops_module=ops_module,
            )
        if not acceptance["acceptable"]:
            if not acceptance["shape_valid"]:
                rejection["reasons"].append(acceptance.get("shape_reason") or "reference_template_shape_mismatch")
            if not acceptance["selector_valid"]:
                rejection["reasons"].append("video_selector_shape_invalid")
            rejection["expected_video_selector_mapping"] = acceptance["expected_video_selector_mapping"]
            rejection["actual_video_selector_mapping"] = acceptance["actual_video_selector_mapping"]
            rejection["selector_mismatches"] = acceptance["selector_mismatches"]
            result["rejected_candidates"].append(rejection)
            continue
        if ops_module._requires_calibrated_project_reference(len(source_rows)) and (
            not exact_video_source_set or not exact_audio_source_set
        ):
            rejection["reasons"].append("project_local_reference_source_set_mismatch")
            result["rejected_candidates"].append(rejection)
            continue

        first_video = video_rows[0]
        fixture = ops_module.ReferenceMulticamFixture(
            schema_family=fallback.schema_family,
            fixture_version=fallback.fixture_version,
            angle_count=len(source_rows),
            fields_blob=candidate[8],
            frame_rate=candidate[4],
            video_metadata=candidate[6],
            virtual_audio_tracks=candidate[7],
            cur_playhead_position=str(candidate[2]).strip() if candidate[2] not in (None, "") else None,
            audio_source=str(candidate[3]).strip() if candidate[3] not in (None, "") else None,
            slate_tc=str(candidate[5]).strip() if candidate[5] not in (None, "") else None,
            sequence_frame_rate=sequence_row[1],
            sequence_resolution=sequence_row[2],
            sequence_media_extents=sequence_row[3],
            sequence_fields_blob=sequence_row[4],
            sequence_render_cache=sequence_row[5],
            sequence_aux_render_cache=sequence_row[6],
            item_start=str(first_video[13] or fallback.item_start),
            item_duration=str(first_video[14] or fallback.item_duration),
            track_templates=track_templates,
            item_templates=item_templates,
            preserve_reference_shape=True,
        )
        if exact_video_source_set and exact_audio_source_set:
            result["reference"] = fixture
            result["ordered_source_rows"] = ordered_rows
            result["matched_candidate_name"] = clip_name
            return result
        if structural_match is None and len(source_rows) < 5:
            structural_match = {
                "reference": fixture,
                "ordered_source_rows": list(source_rows),
                "matched_candidate_name": clip_name,
            }
    if structural_match is not None:
        result.update(structural_match)
        return result
    return result
