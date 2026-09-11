from __future__ import annotations

from dataclasses import replace
import sqlite3
import uuid
from typing import Any

from ...errors import APICallFailed, ValidationError
from ...multicam_support import support_tier_for_angle_count
from .row_mutation import _clone_item_row_with_segment, _delete_track_items, _insert_row, _update_row
from .selector_blobs import (
    _build_switch_fields_blob,
    _build_three_cam_whole_clip_selector_fields_blob,
    _build_two_cam_camera_selector_fields_blob,
)
from .track_state import (
    _build_fallback_multicam_item_row,
    _load_timeline_multicam_track_state,
    _patch_timeline_multicam_bootstrap_metadata,
)


def _use_two_cam_single_item_in_place_patch(
    *,
    angle_count: int,
    segments: list[Any],
    video_rows: list[dict[str, Any]],
    audio_rows: list[dict[str, Any]],
) -> bool:
    return int(angle_count) == 2 and len(segments) == 1 and len(video_rows) == 1 and len(audio_rows) == 1


def _use_three_cam_single_item_in_place_patch(
    *,
    angle_count: int,
    segments: list[Any],
    video_rows: list[dict[str, Any]],
    audio_rows: list[dict[str, Any]],
) -> bool:
    return int(angle_count) == 3 and len(segments) == 1 and len(video_rows) == 1 and len(audio_rows) == 1


def _use_four_cam_single_item_in_place_patch(
    *,
    angle_count: int,
    segments: list[Any],
    video_rows: list[dict[str, Any]],
    audio_rows: list[dict[str, Any]],
) -> bool:
    return int(angle_count) == 4 and len(segments) == 1 and len(video_rows) == 1 and len(audio_rows) == 1


def _normalize_multicam_switch_scope(value: str | None) -> str:
    normalized = str(value or "linked").strip().lower().replace("_", "-")
    aliases = {
        "both": "linked",
        "all": "linked",
        "video-only": "video",
        "audio-only": "audio",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized not in {"linked", "video", "audio"}:
        raise ValidationError(
            "Multicam switch scope must be linked, video, or audio.",
            details={"switch_scope": value, "supported": ["linked", "video", "audio"]},
        )
    return normalized


def _rewrite_multicam_segments_db(
    project_db_path: str,
    *,
    timeline_name: str,
    multicam_name: str,
    segments: list[Any],
    switch_scope: str = "linked",
    audio_angle_override: str | None = None,
    multicam_media_id: str | None = None,
    timeline_native_id: str | None = None,
    preserved_item_positions: list[dict[str, Any]] | None = None,
    final_start_delta: int = 0,
    ops_module,
) -> dict[str, Any]:
    switch_scope = _normalize_multicam_switch_scope(switch_scope)
    write_video = switch_scope in {"linked", "video"}
    write_audio = switch_scope in {"linked", "audio"}
    expected_clip_names: list[str] = []
    for segment in segments:
        clip_name = str(segment.clip_name or "").strip()
        if clip_name and clip_name not in expected_clip_names:
            expected_clip_names.append(clip_name)
    normalized_audio_angle_override = str(audio_angle_override or "").strip() or None
    if normalized_audio_angle_override and normalized_audio_angle_override not in expected_clip_names:
        expected_clip_names.append(normalized_audio_angle_override)
    angle_indices = ops_module._resolve_multicam_angle_indices(
        project_db_path,
        multicam_name=multicam_name,
        expected_clip_names=expected_clip_names,
        multicam_media_id=multicam_media_id,
    )
    # angle_indices maps every distinct source clip name to its logical track.
    # Multiple source items may therefore share one angle index; counting map
    # keys would incorrectly apply the six-angle limit to source clips.
    angle_count = max(2, max((int(index) for index in angle_indices.values()), default=-1) + 1)
    fixture = (
        ops_module._load_matching_project_multicam_switch_fixture(
            project_db_path,
            multicam_name=multicam_name,
            angle_count=angle_count,
        )
        if angle_count == 4
        else None
    )
    using_project_local_reference = fixture is not None
    support_tier = support_tier_for_angle_count(angle_count)
    if not bool(support_tier.get("switch_contract_supported")):
        raise ValidationError(
            "Native multicam switch execution is unsupported for this angle count.",
            details={
                "step": "unsupported_angle_count",
                "angle_count": angle_count,
                "support_tier": support_tier,
            },
        )
    if not using_project_local_reference:
        switch_family_id = ops_module.multicam_switch_families.ensure_switch_family_supported(angle_count).family_id
    else:
        switch_family_id = "project_local_reference"
    fixture = fixture or ops_module.load_reference_multicam_switch_fixture(angle_count=angle_count)
    track_state = _load_timeline_multicam_track_state(
        project_db_path,
        timeline_name=timeline_name,
        multicam_name=multicam_name,
        multicam_media_id=multicam_media_id,
        timeline_native_id=timeline_native_id,
    )
    video_rows = track_state["video_items"]
    audio_rows = track_state["audio_items"]
    patch_existing_video_items = write_video and len(video_rows) == len(segments)
    patch_existing_audio_items = write_audio and len(audio_rows) == len(segments)
    patch_single_item_in_place = (
        len(segments) == 1
        and (not write_video or len(video_rows) == 1)
        and (not write_audio or len(audio_rows) == 1)
    )
    patch_two_cam_single_item_in_place = int(angle_count) == 2 and patch_single_item_in_place
    patch_three_cam_single_item_in_place = int(angle_count) == 3 and patch_single_item_in_place
    patch_four_cam_single_item_in_place = int(angle_count) == 4 and patch_single_item_in_place
    if (write_video and len(video_rows) > 1 and not patch_existing_video_items) or (
        write_audio and len(audio_rows) > 1 and not patch_existing_audio_items
    ):
        raise APICallFailed(
            "The target timeline does not contain the expected native multicam track shape for switch writing.",
            details={
                "timeline_name": timeline_name,
                "multicam_name": multicam_name,
                "switch_scope": switch_scope,
                "actual_video_items": len(video_rows),
                "actual_audio_items": len(audio_rows),
                "video_track_id": track_state.get("video_track_id"),
                "audio_track_id": track_state.get("audio_track_id"),
            },
        )

    video_base = video_rows[0] if video_rows else {"track_id": track_state.get("video_track_id"), "item_row": None}
    audio_base = audio_rows[0] if audio_rows else {"track_id": track_state.get("audio_track_id"), "item_row": None}
    if (write_video and not video_base["track_id"]) or (write_audio and not audio_base["track_id"]):
        raise APICallFailed(
            "The target timeline is missing the expected video/audio tracks for native multicam switch writing.",
            details={
                "timeline_name": timeline_name,
                "multicam_name": multicam_name,
                "switch_scope": switch_scope,
                "video_track_id": track_state.get("video_track_id"),
                "audio_track_id": track_state.get("audio_track_id"),
            },
        )
    timeline_origin = min(ops_module._segment_record_start_frame(segment) for segment in segments)
    total_duration_frames = max(ops_module._segment_record_end_frame(segment) for segment in segments) - timeline_origin

    connection = sqlite3.connect(project_db_path)
    try:
        cursor = connection.cursor()
        cursor.execute("BEGIN")
        target_track_types = ({0} if write_video else set()) | ({1} if write_audio else set())
        preserved_rows = cursor.execute(
            """
            SELECT item.Sm2TiItem_id, track.Type, item.Start, item.Duration
            FROM Sm2SequenceContainer_Sm2TiTrack track_rel
            JOIN Sm2TiTrack track ON track.Sm2TiTrack_id = track_rel.DbAssociate
            JOIN Sm2TiItem_Sm2TiTrack item_rel
              ON item_rel.DbOwner = track.Sm2TiTrack_id AND item_rel.DbPropertyName = 'Items'
            JOIN Sm2TiItem item ON item.Sm2TiItem_id = item_rel.DbAssociate
            WHERE track_rel.DbOwner = ?
            ORDER BY track.Type, track.Sm2TiTrack_id, item_rel.DbIndex, item.Sm2TiItem_id
            """,
            (track_state["sequence_container_id"],),
        ).fetchall()
        preserved_items_before = [
            {"item_id": str(item_id), "track_type": int(track_type), "start": int(start), "duration": int(duration)}
            for item_id, track_type, start, duration in preserved_rows
            if int(track_type) not in target_track_types
        ]
        if preserved_item_positions is not None:
            expected = {str(row["item_id"]): row for row in preserved_item_positions}
            actual = {str(row["item_id"]): row for row in preserved_items_before}
            if set(actual) != set(expected) or any(
                int(actual[item_id]["duration"]) != int(expected[item_id]["duration"])
                or int(actual[item_id]["track_type"]) != int(expected[item_id]["track_type"])
                for item_id in expected.keys() & actual.keys()
            ):
                raise APICallFailed(
                    "Preserved timeline items changed before the final multicam start-timecode restore.",
                    details={"expected": list(expected.values()), "actual": list(actual.values())},
                )
            for item_id, original in expected.items():
                cursor.execute(
                    "UPDATE Sm2TiItem SET Start = ? WHERE Sm2TiItem_id = ?",
                    (str(int(original["start"]) - int(final_start_delta)), item_id),
                )
        removed_video_items: list[str] = []
        removed_audio_items: list[str] = []
        if write_video and not patch_existing_video_items:
            _delete_track_items(cursor, track_id=video_base["track_id"])
        if write_audio and not patch_existing_audio_items:
            _delete_track_items(cursor, track_id=audio_base["track_id"])

        written_video_items: list[dict[str, Any]] = []
        written_audio_items: list[dict[str, Any]] = []
        total_segments = len(segments)
        for index, segment in enumerate(segments):
            local_angle_index = angle_indices.get(segment.clip_name)
            if local_angle_index is None:
                raise ValidationError(
                    "Switch plan references a clip that is not present in the native multicam angle order.",
                    details={
                        "clip_name": segment.clip_name,
                        "multicam_name": multicam_name,
                        "known_clips": sorted(angle_indices.keys()),
                    },
                )
            template_angle_index = ops_module._resolve_switch_template_angle_index(
                segment=segment,
                local_angle_index=local_angle_index,
                angle_count=angle_count,
            )
            audio_segment = segment
            audio_local_angle_index = local_angle_index
            audio_template_angle_index = template_angle_index
            if write_audio and normalized_audio_angle_override:
                audio_local_angle_index = angle_indices.get(normalized_audio_angle_override)
                if audio_local_angle_index is None:
                    raise ValidationError(
                        "Reference audio source is not present in the native multicam angle order.",
                        details={
                            "audio_angle_override": normalized_audio_angle_override,
                            "multicam_name": multicam_name,
                            "known_clips": sorted(angle_indices),
                        },
                    )
                audio_segment = replace(segment, clip_name=normalized_audio_angle_override)
                audio_template_angle_index = ops_module._resolve_switch_template_angle_index(
                    segment=audio_segment,
                    local_angle_index=audio_local_angle_index,
                    angle_count=angle_count,
                )
            record_start = ops_module._segment_record_start_frame(segment)
            record_end = ops_module._segment_record_end_frame(segment)
            relative_start = record_start - int(timeline_origin)
            relative_end = record_end - int(timeline_origin)
            duration = relative_end - relative_start
            if duration <= 0:
                raise ValidationError(
                    "Switch plan contains a non-positive multicam segment duration.",
                    details={
                        "timeline_name": timeline_name,
                        "multicam_name": multicam_name,
                        "segment_index": index,
                        "start_frame": segment.start_frame,
                        "end_frame": segment.end_frame,
                        "record_start_frame": ops_module._segment_record_start_frame(segment),
                        "record_end_frame": ops_module._segment_record_end_frame(segment),
                        "timeline_origin": timeline_origin,
                    },
                )

            position = ops_module._segment_template_position(index, total_segments)
            video_template = (
                ops_module._select_native_switch_template(
                    fixture.video_segments,
                    position=position,
                    angle_index=template_angle_index,
                )
                if write_video
                else None
            )
            audio_template = (
                ops_module._select_native_switch_template(
                    fixture.audio_segments,
                    position=position,
                    angle_index=audio_template_angle_index if angle_count > 2 else None,
                )
                if write_audio
                else None
            )
            source_start_frame = getattr(segment, "source_start_frame", None)
            source_in_frame = int(source_start_frame) if source_start_frame is not None else relative_start
            video_in_value = None if index == 0 and source_in_frame == 0 else str(source_in_frame)
            audio_in_value = None if index == 0 and relative_start == 0 else str(relative_start)
            video_item_id = str(uuid.uuid4())
            audio_item_id = str(uuid.uuid4())
            video_fields_blob = (
                _build_switch_fields_blob(
                    template=video_template,
                    segment=segment,
                    local_angle_index=local_angle_index,
                    template_angle_index=template_angle_index,
                    segment_index=index,
                    total_segments=total_segments,
                    angle_count=angle_count,
                    track_type="video",
                    calibrated_project_local_reference=using_project_local_reference,
                )
                if video_template is not None
                else None
            )
            audio_fields_blob = (
                _build_switch_fields_blob(
                    template=audio_template,
                    segment=audio_segment,
                    local_angle_index=audio_local_angle_index,
                    template_angle_index=audio_template_angle_index,
                    segment_index=index,
                    total_segments=total_segments,
                    angle_count=angle_count,
                    track_type="audio",
                    calibrated_project_local_reference=using_project_local_reference,
                )
                if audio_template is not None
                else None
            )
            if patch_two_cam_single_item_in_place and write_video:
                video_fields_blob = _build_two_cam_camera_selector_fields_blob(local_angle_index=local_angle_index, track_type="video")
            if patch_two_cam_single_item_in_place and write_audio:
                audio_fields_blob = _build_two_cam_camera_selector_fields_blob(local_angle_index=audio_local_angle_index, track_type="audio")
            elif patch_three_cam_single_item_in_place and write_video:
                video_fields_blob = _build_three_cam_whole_clip_selector_fields_blob(local_angle_index=local_angle_index, track_type="video")
            if patch_three_cam_single_item_in_place and write_audio:
                audio_fields_blob = _build_three_cam_whole_clip_selector_fields_blob(local_angle_index=audio_local_angle_index, track_type="audio")
            elif patch_four_cam_single_item_in_place and write_video and video_template is not None:
                video_fields_blob = bytes(video_template.fields_blob)
            if patch_four_cam_single_item_in_place and write_audio and audio_template is not None:
                audio_fields_blob = bytes(audio_template.fields_blob)

            if write_video and patch_existing_video_items:
                existing_video = video_rows[index]
                video_item_id = str(existing_video["item_row"]["Sm2TiItem_id"])
                video_updates = {
                    "Start": str(relative_start),
                    "Duration": str(duration),
                    "In": video_in_value,
                    "CurrentSelectorIdx": video_template.current_selector_idx,
                    "FieldsBlob": video_fields_blob,
                    "MediaTimemapBA": (
                        video_template.media_timemap_ba
                        if video_template.media_timemap_ba is not None
                        else existing_video["item_row"].get("MediaTimemapBA")
                    ),
                    "EffectFiltersBA": (
                        video_template.effect_filters_ba
                        if video_template.effect_filters_ba is not None
                        else existing_video["item_row"].get("EffectFiltersBA")
                    ),
                }
                if patch_two_cam_single_item_in_place or patch_three_cam_single_item_in_place or patch_four_cam_single_item_in_place:
                    existing_video_row = existing_video["item_row"]
                    existing_video_start = str(existing_video_row.get("Start"))
                    expected_video_start = str(relative_start)
                    video_updates.update(
                        {
                            "Start": existing_video_start if existing_video_start == expected_video_start else expected_video_start,
                            "Duration": existing_video_row.get("Duration"),
                            "In": existing_video_row.get("In"),
                            "CurrentSelectorIdx": existing_video_row.get("CurrentSelectorIdx"),
                            "MediaTimemapBA": existing_video_row.get("MediaTimemapBA"),
                            "EffectFiltersBA": existing_video_row.get("EffectFiltersBA"),
                        }
                    )
                effective_video_start = str(video_updates.get("Start"))
                effective_video_duration = str(video_updates.get("Duration"))
                effective_video_in = video_updates.get("In")
                effective_video_selector = int(video_updates.get("CurrentSelectorIdx") or 0)
                _update_row(cursor, "Sm2TiItem", "Sm2TiItem_id", video_item_id, video_updates)
                cursor.execute(
                    """
                    UPDATE Sm2TiItem_Sm2TiTrack
                    SET DbIndex = ?
                    WHERE DbOwner = ? AND DbAssociate = ? AND DbPropertyName = 'Items'
                    """,
                    (index, existing_video["track_id"], video_item_id),
                )
            elif write_video:
                video_row = (
                    _clone_item_row_with_segment(
                        video_base["item_row"],
                        item_id=video_item_id,
                        start=str(relative_start),
                        duration=str(duration),
                        in_value=video_in_value,
                        current_selector_idx=video_template.current_selector_idx,
                        fields_blob=video_fields_blob,
                        media_timemap_ba=video_template.media_timemap_ba,
                        effect_filters_ba=video_template.effect_filters_ba,
                    )
                    if isinstance(video_base.get("item_row"), dict)
                    else _build_fallback_multicam_item_row(
                        item_id=video_item_id,
                        multicam_name=multicam_name,
                        multicam_media_id=track_state["multicam_media_id"],
                        track_id=video_base["track_id"],
                        track_type=0,
                        start=str(relative_start),
                        duration=str(duration),
                        in_value=video_in_value,
                        current_selector_idx=video_template.current_selector_idx,
                        fields_blob=video_fields_blob,
                        media_timemap_ba=video_template.media_timemap_ba,
                        effect_filters_ba=video_template.effect_filters_ba,
                        ops_module=ops_module,
                    )
                )
                _insert_row(cursor, "Sm2TiItem", video_row)
                cursor.execute(
                    """
                    INSERT INTO Sm2TiItem_Sm2TiTrack (DbOwner, DbAssociate, DbPropertyName, DbIndex)
                    VALUES (?, ?, 'Items', ?)
                    """,
                    (video_base["track_id"], video_item_id, index),
                )
                effective_video_start = str(relative_start)
                effective_video_duration = str(duration)
                effective_video_in = video_in_value
                effective_video_selector = video_template.current_selector_idx

            if write_audio and patch_existing_audio_items:
                existing_audio = audio_rows[index]
                audio_item_id = str(existing_audio["item_row"]["Sm2TiItem_id"])
                audio_updates = {
                    "Start": str(relative_start),
                    "Duration": str(duration),
                    "In": audio_in_value,
                    "CurrentSelectorIdx": audio_template.current_selector_idx,
                    "FieldsBlob": audio_fields_blob,
                    "MediaTimemapBA": (
                        audio_template.media_timemap_ba
                        if audio_template.media_timemap_ba is not None
                        else existing_audio["item_row"].get("MediaTimemapBA")
                    ),
                    "EffectFiltersBA": (
                        audio_template.effect_filters_ba
                        if audio_template.effect_filters_ba is not None
                        else existing_audio["item_row"].get("EffectFiltersBA")
                    ),
                }
                if patch_two_cam_single_item_in_place or patch_three_cam_single_item_in_place or patch_four_cam_single_item_in_place:
                    existing_audio_row = existing_audio["item_row"]
                    existing_audio_start = str(existing_audio_row.get("Start"))
                    expected_audio_start = str(relative_start)
                    audio_updates.update(
                        {
                            "Start": existing_audio_start if existing_audio_start == expected_audio_start else expected_audio_start,
                            "Duration": existing_audio_row.get("Duration"),
                            "In": existing_audio_row.get("In"),
                            "CurrentSelectorIdx": existing_audio_row.get("CurrentSelectorIdx"),
                            "MediaTimemapBA": existing_audio_row.get("MediaTimemapBA"),
                            "EffectFiltersBA": existing_audio_row.get("EffectFiltersBA"),
                        }
                    )
                effective_audio_start = str(audio_updates.get("Start"))
                effective_audio_duration = str(audio_updates.get("Duration"))
                effective_audio_in = audio_updates.get("In")
                effective_audio_selector = int(audio_updates.get("CurrentSelectorIdx") or 0)
                _update_row(cursor, "Sm2TiItem", "Sm2TiItem_id", audio_item_id, audio_updates)
                cursor.execute(
                    """
                    UPDATE Sm2TiItem_Sm2TiTrack
                    SET DbIndex = ?
                    WHERE DbOwner = ? AND DbAssociate = ? AND DbPropertyName = 'Items'
                    """,
                    (index, existing_audio["track_id"], audio_item_id),
                )
            elif write_audio:
                audio_row = (
                    _clone_item_row_with_segment(
                        audio_base["item_row"],
                        item_id=audio_item_id,
                        start=str(relative_start),
                        duration=str(duration),
                        in_value=audio_in_value,
                        current_selector_idx=audio_template.current_selector_idx,
                        fields_blob=audio_fields_blob,
                        media_timemap_ba=audio_template.media_timemap_ba,
                        effect_filters_ba=audio_template.effect_filters_ba,
                    )
                    if isinstance(audio_base.get("item_row"), dict)
                    else _build_fallback_multicam_item_row(
                        item_id=audio_item_id,
                        multicam_name=multicam_name,
                        multicam_media_id=track_state["multicam_media_id"],
                        track_id=audio_base["track_id"],
                        track_type=1,
                        start=str(relative_start),
                        duration=str(duration),
                        in_value=audio_in_value,
                        current_selector_idx=audio_template.current_selector_idx,
                        fields_blob=audio_fields_blob,
                        media_timemap_ba=audio_template.media_timemap_ba,
                        effect_filters_ba=audio_template.effect_filters_ba,
                        ops_module=ops_module,
                    )
                )
                _insert_row(cursor, "Sm2TiItem", audio_row)
                cursor.execute(
                    """
                    INSERT INTO Sm2TiItem_Sm2TiTrack (DbOwner, DbAssociate, DbPropertyName, DbIndex)
                    VALUES (?, ?, 'Items', ?)
                    """,
                    (audio_base["track_id"], audio_item_id, index),
                )
                effective_audio_start = str(relative_start)
                effective_audio_duration = str(duration)
                effective_audio_in = audio_in_value
                effective_audio_selector = audio_template.current_selector_idx
            if write_video:
                written_video_items.append(
                    {
                        "item_id": video_item_id,
                        "start": effective_video_start,
                        "duration": effective_video_duration,
                        "in": effective_video_in,
                        "source_start_frame": source_start_frame,
                        "source_in_frame": source_in_frame,
                        "clip_name": segment.clip_name,
                        "angle": segment.angle,
                        "angle_index": local_angle_index,
                        "template_angle_index": template_angle_index,
                        "selector_value": effective_video_selector,
                        "track_id": video_base["track_id"],
                    }
                )
            if write_audio:
                written_audio_items.append(
                    {
                        "item_id": audio_item_id,
                        "start": effective_audio_start,
                        "duration": effective_audio_duration,
                        "in": effective_audio_in,
                        "selector_value": effective_audio_selector,
                        "clip_name": audio_segment.clip_name,
                        "angle": audio_segment.angle,
                        "angle_index": audio_local_angle_index,
                        "template_angle_index": audio_template_angle_index,
                        "track_id": audio_base["track_id"],
                    }
                )
        _patch_timeline_multicam_bootstrap_metadata(
            cursor,
            track_state=track_state,
            total_duration_frames=total_duration_frames,
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

    return {
        "multicam_media_id": track_state["multicam_media_id"],
        "angle_count": angle_count,
        "switch_family": switch_family_id,
        "switch_scope": switch_scope,
        "video_changed": write_video,
        "audio_changed": write_audio,
        "audio_angle_override": normalized_audio_angle_override,
        "video_segment_count": len(written_video_items),
        "audio_segment_count": len(written_audio_items),
        "removed_video_item_count": len(removed_video_items),
        "removed_audio_item_count": len(removed_audio_items),
        "video_items": written_video_items,
        "audio_items": written_audio_items,
        "preserved_items_before": preserved_items_before,
        "template_fixture_version": fixture.fixture_version,
    }
