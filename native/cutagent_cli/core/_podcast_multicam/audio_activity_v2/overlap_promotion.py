from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

from cutagent_cli.core._podcast_multicam.audio_activity_v2.segments import _merge_time_ranges


def _promote_long_audio_overlaps_to_wide(
    segments: Sequence[Dict[str, Any]],
    *,
    wide_camera_id: str,
    promote_after_seconds: float,
    gap_tolerance: float,
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    promoted: List[Dict[str, Any]] = []
    metrics = {
        "promoted_long_overlap_segments": 0,
    }

    def _clip_overlay(overlay: Dict[str, Any], start: float, end: float) -> Optional[Dict[str, Any]]:
        clipped_start = max(start, float(overlay.get("start") or start))
        clipped_end = min(end, float(overlay.get("end") or end))
        if clipped_end <= clipped_start:
            return None
        clipped = dict(overlay)
        clipped["start"] = clipped_start
        clipped["end"] = clipped_end
        return clipped

    def _clip_speaker_segment(segment: Dict[str, Any], start: float, end: float, overlays: Sequence[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if end <= start:
            return None
        clipped = dict(segment)
        clipped["start"] = start
        clipped["end"] = end
        clipped["audio_primary_start"] = max(start, float(segment.get("audio_primary_start") or start))
        clipped["audio_primary_end"] = min(end, float(segment.get("audio_primary_end") or end))
        clipped["audio_overlays"] = [
            clipped_overlay
            for overlay in overlays
            if (clipped_overlay := _clip_overlay(overlay, start, end)) is not None
        ]
        return clipped

    for raw_segment in segments:
        segment = dict(raw_segment)
        if str(segment.get("target_kind") or "") != "speaker":
            promoted.append(segment)
            continue

        overlays = [dict(item or {}) for item in list(segment.get("audio_overlays") or [])]
        if not overlays:
            promoted.append(segment)
            continue

        promotable_overlays = [
            overlay
            for overlay in overlays
            if max(0.0, float(overlay.get("end") or 0.0) - float(overlay.get("start") or 0.0)) >= promote_after_seconds
        ]
        if not promotable_overlays:
            promoted.append(segment)
            continue

        segment_start = float(segment.get("start") or 0.0)
        segment_end = float(segment.get("end") or 0.0)
        primary_speaker_id = str(segment.get("speaker_id") or "").strip()
        promotion_ranges = _merge_time_ranges(
            [
                (float(overlay.get("start") or segment_start), float(overlay.get("end") or segment_end))
                for overlay in promotable_overlays
            ],
            gap_tolerance=gap_tolerance,
        )
        if not promotion_ranges:
            promoted.append(segment)
            continue

        non_promotable_overlays = [
            overlay
            for overlay in overlays
            if overlay not in promotable_overlays
        ]
        cursor = segment_start
        for promote_start, promote_end in promotion_ranges:
            speaker_part = _clip_speaker_segment(segment, cursor, promote_start, non_promotable_overlays)
            if speaker_part is not None:
                promoted.append(speaker_part)

            wide_segment = dict(segment)
            wide_segment["start"] = promote_start
            wide_segment["end"] = promote_end
            wide_segment["target_kind"] = "wide"
            wide_segment["target_id"] = wide_camera_id
            wide_segment["speaker_id"] = None
            wide_segment["audio_primary_start"] = promote_start
            wide_segment["audio_primary_end"] = promote_end
            wide_segment["audio_overlays"] = []
            wide_segment["reason"] = str(segment.get("reason") or "speaker") + "|promoted_long_overlap_wide"

            overlap_speakers: List[str] = []
            if primary_speaker_id:
                overlap_speakers.append(primary_speaker_id)
            for overlay in promotable_overlays:
                overlay_start = float(overlay.get("start") or promote_start)
                overlay_end = float(overlay.get("end") or promote_end)
                if overlay_end <= promote_start or overlay_start >= promote_end:
                    continue
                overlay_speaker_id = str(overlay.get("speaker_id") or "").strip()
                if overlay_speaker_id and overlay_speaker_id not in overlap_speakers:
                    overlap_speakers.append(overlay_speaker_id)
            wide_segment["sources"] = [
                {
                    "speaker_id": speaker_id,
                    "target_id": wide_camera_id if speaker_id == primary_speaker_id else str(
                        next(
                            (
                                overlay.get("target_id")
                                for overlay in promotable_overlays
                                if str(overlay.get("speaker_id") or "").strip() == speaker_id
                            ),
                            "",
                        )
                    ),
                }
                for speaker_id in overlap_speakers
            ]
            promoted.append(wide_segment)
            metrics["promoted_long_overlap_segments"] += 1
            cursor = promote_end

        trailing_part = _clip_speaker_segment(segment, cursor, segment_end, non_promotable_overlays)
        if trailing_part is not None:
            promoted.append(trailing_part)

    return promoted, metrics
