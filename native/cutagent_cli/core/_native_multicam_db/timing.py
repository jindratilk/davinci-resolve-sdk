from __future__ import annotations

from typing import Any

from ...errors import ValidationError


def _derive_multicam_fps(reference: Any, source_rows: list[Any], decode_rate_blob_fn) -> float:
    source_rates = [float(row.fps) for row in source_rows if row.fps and row.fps > 0]
    if source_rates:
        first_rate = source_rates[0]
        mismatches = [rate for rate in source_rates[1:] if abs(rate - first_rate) > 1e-6]
        if mismatches:
            raise ValidationError(
                "Native multicam creation requires one shared source frame rate.",
                details={
                    "reason": "mixed_source_frame_rates_unsupported",
                    "source_frame_rates": source_rates,
                },
            )
        return first_rate
    for candidate in (
        decode_rate_blob_fn(reference.sequence_frame_rate),
        decode_rate_blob_fn(reference.frame_rate),
    ):
        if candidate and candidate > 0:
            return candidate
    return 24.0


def _derive_multicam_duration(reference: Any, source_rows: list[Any]) -> int:
    durations = [int(row.duration_frames) for row in source_rows if row.duration_frames and int(row.duration_frames) > 0]
    if durations:
        return min(durations)
    return max(1, int(reference.item_duration))


def _coalesce_template_value(primary: Any, fallback: Any) -> Any:
    return primary if primary not in (None, "") else fallback


def _load_source_templates(
    cursor,
    *,
    source_row: Any,
    reference: Any,
    angle_index: int,
    multicam_duration_frames: int,
    multicam_fps: float,
    default_source_templates_fn,
    reference_item_template_fn,
    select_representative_item_row_fn,
    reference_track_template_fn,
    track_template_cls: type,
    item_template_cls: type,
    source_templates_cls: type,
) -> Any:
    defaults = default_source_templates_fn(
        source_row,
        reference,
        multicam_duration_frames=multicam_duration_frames,
        multicam_fps=multicam_fps,
    )
    reference_video_item = reference_item_template_fn(
        reference,
        item_db_type="Sm2TiVideoClip",
        angle_index=angle_index,
        fallback=defaults.video_item,
    )
    reference_audio_item = reference_item_template_fn(
        reference,
        item_db_type="Sm2TiAudioClip",
        angle_index=angle_index,
        fallback=defaults.audio_item,
    )
    video_row = select_representative_item_row_fn(
        cursor,
        media_id=source_row.media_id,
        item_db_type="Sm2TiVideoClip",
        preferred_start=reference.item_start,
        preferred_duration=str(multicam_duration_frames),
    )
    audio_row = select_representative_item_row_fn(
        cursor,
        media_id=source_row.media_id,
        item_db_type="Sm2TiAudioClip",
        preferred_start=reference.item_start,
        preferred_duration=str(multicam_duration_frames),
    )
    reference_matches_duration = str(reference.item_duration) == str(multicam_duration_frames)
    preserve_reference_shape = bool(reference.preserve_reference_shape)
    preferred_video_reference = (
        reference_video_item if (reference_matches_duration or preserve_reference_shape) else defaults.video_item
    )
    preferred_audio_reference = (
        reference_audio_item if (reference_matches_duration or preserve_reference_shape) else defaults.audio_item
    )
    if preserve_reference_shape:
        return source_templates_cls(
            video_track=reference_track_template_fn(
                reference,
                track_type=0,
                angle_index=angle_index,
                fallback=track_template_cls(
                    subtype=defaults.video_track.subtype,
                    fields_blob=defaults.video_track.fields_blob,
                    user_defined_name=f"Angle {angle_index + 1}",
                ),
            ),
            audio_track=reference_track_template_fn(
                reference,
                track_type=1,
                angle_index=angle_index,
                fallback=track_template_cls(
                    subtype=defaults.audio_track.subtype,
                    fields_blob=defaults.audio_track.fields_blob,
                    user_defined_name=f"Angle {angle_index + 1}",
                ),
            ),
            video_item=item_template_cls(
                is_placeholder=preferred_video_reference.is_placeholder,
                media_file_path=_coalesce_template_value(
                    source_row.source_path,
                    preferred_video_reference.media_file_path or defaults.video_item.media_file_path,
                ),
                media_timemap_ba=preferred_video_reference.media_timemap_ba or defaults.video_item.media_timemap_ba,
                preconform_media_extents=preferred_video_reference.preconform_media_extents
                or defaults.video_item.preconform_media_extents,
                media_frame_rate=defaults.video_item.media_frame_rate,
                virtual_audio_track_ba=None,
                fields_blob=preferred_video_reference.fields_blob or defaults.video_item.fields_blob,
                in_value=preferred_video_reference.in_value
                if preferred_video_reference.in_value is not None
                else defaults.video_item.in_value,
                media_track_idx=None,
                current_selector_idx=preferred_video_reference.current_selector_idx
                if preferred_video_reference.current_selector_idx is not None
                else defaults.video_item.current_selector_idx,
                media_start_time=_coalesce_template_value(
                    video_row["MediaStartTime"] if video_row else None,
                    preferred_video_reference.media_start_time
                    if preferred_video_reference.media_start_time is not None
                    else defaults.video_item.media_start_time,
                ),
            ),
            audio_item=item_template_cls(
                is_placeholder=False,
                media_file_path=_coalesce_template_value(
                    audio_row["MediaFilePath"] if audio_row else None,
                    defaults.audio_item.media_file_path or preferred_audio_reference.media_file_path,
                ),
                media_timemap_ba=_coalesce_template_value(
                    audio_row["MediaTimemapBA"] if audio_row else None,
                    preferred_audio_reference.media_timemap_ba or defaults.audio_item.media_timemap_ba,
                ),
                preconform_media_extents=None,
                media_frame_rate=defaults.audio_item.media_frame_rate,
                virtual_audio_track_ba=_coalesce_template_value(
                    audio_row["VirtualAudioTrackBA"] if audio_row else None,
                    preferred_audio_reference.virtual_audio_track_ba or defaults.audio_item.virtual_audio_track_ba,
                ),
                fields_blob=_coalesce_template_value(
                    audio_row["FieldsBlob"] if audio_row else None,
                    preferred_audio_reference.fields_blob or defaults.audio_item.fields_blob,
                ),
                in_value=_coalesce_template_value(
                    audio_row["InValue"] if audio_row else None,
                    preferred_audio_reference.in_value if preferred_audio_reference.in_value is not None else defaults.audio_item.in_value,
                ),
                media_track_idx=int(
                    _coalesce_template_value(
                        audio_row["MediaTrackIdx"] if audio_row else None,
                        preferred_audio_reference.media_track_idx
                        if preferred_audio_reference.media_track_idx is not None
                        else defaults.audio_item.media_track_idx,
                    )
                ),
                current_selector_idx=int(
                    _coalesce_template_value(
                        audio_row["CurrentSelectorIdx"] if audio_row else None,
                        preferred_audio_reference.current_selector_idx
                        if preferred_audio_reference.current_selector_idx is not None
                        else defaults.audio_item.current_selector_idx,
                    )
                ),
                media_start_time=_coalesce_template_value(
                    audio_row["MediaStartTime"] if audio_row else None,
                    preferred_audio_reference.media_start_time
                    if preferred_audio_reference.media_start_time is not None
                    else defaults.audio_item.media_start_time,
                ),
            ),
        )

    return source_templates_cls(
        video_track=reference_track_template_fn(
            reference,
            track_type=0,
            angle_index=angle_index,
            fallback=track_template_cls(
                subtype=defaults.video_track.subtype,
                fields_blob=defaults.video_track.fields_blob,
                user_defined_name=f"Angle {angle_index + 1}",
            ),
        ),
        audio_track=reference_track_template_fn(
            reference,
            track_type=1,
            angle_index=angle_index,
            fallback=track_template_cls(
                subtype=defaults.audio_track.subtype,
                fields_blob=defaults.audio_track.fields_blob,
                user_defined_name=f"Angle {angle_index + 1}",
            ),
        ),
        video_item=item_template_cls(
            is_placeholder=False,
            media_file_path=_coalesce_template_value(
                video_row["MediaFilePath"] if video_row else None,
                defaults.video_item.media_file_path or preferred_video_reference.media_file_path,
            ),
            media_timemap_ba=_coalesce_template_value(
                video_row["MediaTimemapBA"] if video_row else None,
                preferred_video_reference.media_timemap_ba or defaults.video_item.media_timemap_ba,
            ),
            preconform_media_extents=_coalesce_template_value(
                video_row["PreConformMediaExtents"] if video_row else None,
                preferred_video_reference.preconform_media_extents or defaults.video_item.preconform_media_extents,
            ),
            media_frame_rate=defaults.video_item.media_frame_rate,
            virtual_audio_track_ba=None,
            fields_blob=_coalesce_template_value(
                video_row["FieldsBlob"] if video_row else None,
                preferred_video_reference.fields_blob or defaults.video_item.fields_blob,
            ),
            in_value=_coalesce_template_value(
                video_row["InValue"] if video_row else None,
                preferred_video_reference.in_value if preferred_video_reference.in_value is not None else defaults.video_item.in_value,
            ),
            media_track_idx=None,
            current_selector_idx=int(
                _coalesce_template_value(
                    video_row["CurrentSelectorIdx"] if video_row else None,
                    preferred_video_reference.current_selector_idx
                    if preferred_video_reference.current_selector_idx is not None
                    else defaults.video_item.current_selector_idx,
                )
            ),
            media_start_time=_coalesce_template_value(
                video_row["MediaStartTime"] if video_row else None,
                preferred_video_reference.media_start_time
                if preferred_video_reference.media_start_time is not None
                else defaults.video_item.media_start_time,
            ),
        ),
        audio_item=item_template_cls(
            is_placeholder=False,
            media_file_path=_coalesce_template_value(
                audio_row["MediaFilePath"] if audio_row else None,
                defaults.audio_item.media_file_path or preferred_audio_reference.media_file_path,
            ),
            media_timemap_ba=_coalesce_template_value(
                audio_row["MediaTimemapBA"] if audio_row else None,
                preferred_audio_reference.media_timemap_ba or defaults.audio_item.media_timemap_ba,
            ),
            preconform_media_extents=None,
            media_frame_rate=defaults.audio_item.media_frame_rate,
            virtual_audio_track_ba=_coalesce_template_value(
                audio_row["VirtualAudioTrackBA"] if audio_row else None,
                preferred_audio_reference.virtual_audio_track_ba or defaults.audio_item.virtual_audio_track_ba,
            ),
            fields_blob=_coalesce_template_value(
                audio_row["FieldsBlob"] if audio_row else None,
                preferred_audio_reference.fields_blob or defaults.audio_item.fields_blob,
            ),
            in_value=_coalesce_template_value(
                audio_row["InValue"] if audio_row else None,
                preferred_audio_reference.in_value if preferred_audio_reference.in_value is not None else defaults.audio_item.in_value,
            ),
            media_track_idx=int(
                _coalesce_template_value(
                    audio_row["MediaTrackIdx"] if audio_row else None,
                    preferred_audio_reference.media_track_idx
                    if preferred_audio_reference.media_track_idx is not None
                    else defaults.audio_item.media_track_idx,
                )
            ),
            current_selector_idx=int(
                _coalesce_template_value(
                    audio_row["CurrentSelectorIdx"] if audio_row else None,
                    preferred_audio_reference.current_selector_idx
                    if preferred_audio_reference.current_selector_idx is not None
                    else defaults.audio_item.current_selector_idx,
                )
            ),
            media_start_time=_coalesce_template_value(
                audio_row["MediaStartTime"] if audio_row else None,
                preferred_audio_reference.media_start_time
                if preferred_audio_reference.media_start_time is not None
                else defaults.audio_item.media_start_time,
            ),
        ),
    )


def _resolve_angle_timing(
    *,
    source_row: Any,
    templates: Any,
    reference: Any,
    start_offset_frames: int,
    media_start_time_base_seconds: float | None = None,
    source_start_offsets_mode: str = "additive",
    multicam_duration_frames: int,
    multicam_fps: float,
    angle_timing_seed_cls: type,
) -> Any:
    safe_fps = multicam_fps if multicam_fps > 0 else 24.0
    baseline_media_start_time = (
        float(media_start_time_base_seconds)
        if media_start_time_base_seconds is not None
        else next(
            (
                value
                for value in (
                    source_row.media_start_time,
                    templates.video_item.media_start_time,
                    templates.audio_item.media_start_time,
                )
                if value is not None
            ),
            0.0,
        )
    )
    normalized_mode = str(source_start_offsets_mode or "additive").strip().lower()
    item_start_delta = 0
    source_in_frame = 0
    media_start_time_offset_seconds = int(start_offset_frames) / safe_fps
    if normalized_mode == "timeline_offsets":
        item_start_delta = max(0, -int(start_offset_frames))
        source_in_frame = max(0, int(start_offset_frames))
        media_start_time_offset_seconds = 0.0
    item_start_frame = int(reference.item_start) + item_start_delta
    source_duration_frames = int(source_row.duration_frames or 0)
    available_source_frames = (
        max(1, source_duration_frames - source_in_frame)
        if source_duration_frames > 0
        else max(1, int(multicam_duration_frames))
    )
    available_timeline_frames = max(1, int(multicam_duration_frames) - item_start_delta)
    item_duration_frames = max(1, min(available_timeline_frames, available_source_frames))
    return angle_timing_seed_cls(
        item_start_frame=item_start_frame,
        media_start_time_seconds=float(baseline_media_start_time) + media_start_time_offset_seconds,
        item_duration_frames=item_duration_frames,
        media_timemap_duration_frames=(
            source_duration_frames if source_duration_frames > 0 else item_duration_frames
        ),
        sequence_extents_start_frame=int(reference.item_start),
        sequence_extents_duration_frames=max(1, int(multicam_duration_frames)),
        source_in_frame=source_in_frame,
    )
