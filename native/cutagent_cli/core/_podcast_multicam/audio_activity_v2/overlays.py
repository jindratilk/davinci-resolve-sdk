from __future__ import annotations

from typing import Any, Dict, List, Sequence, Tuple

from cutagent_cli.core._podcast_multicam.audio_activity_v2.segments import (
    _merge_overlay_ranges,
    _merge_time_ranges,
)


def _collect_audio_only_interjections(
    segments: Sequence[Dict[str, Any]],
    *,
    raw_windows: Sequence[Dict[str, Any]],
    min_seconds: float,
    max_seconds: float,
    gap_tolerance: float,
    short_guard_seconds: float,
    minimum_first_relative_level_db: float,
    minimum_max_relative_level_db: float,
    minimum_absolute_level_db: float,
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    metrics = {
        "audio_only_interjections": 0,
        "suppressed_noise_spikes": 0,
        "suppressed_weak_interjections": 0,
    }
    enriched = [dict(segment) for segment in segments]
    if not enriched:
        return enriched, metrics

    for index, segment in enumerate(enriched):
        if str(segment.get("target_kind") or "") != "speaker":
            continue
        primary_speaker_id = str(segment.get("speaker_id") or "").strip()
        if not primary_speaker_id:
            continue
        segment_start = float(segment.get("start") or 0.0)
        segment_end = float(segment.get("end") or 0.0)
        if segment_end <= segment_start:
            continue

        overlays: List[Dict[str, Any]] = []
        active_by_secondary: Dict[str, Dict[str, Any]] = {}
        for window in raw_windows:
            window_start = float(window.get("start") or 0.0)
            window_end = float(window.get("end") or 0.0)
            if window_end <= segment_start or window_start >= segment_end:
                continue
            clipped_window_start = max(segment_start, window_start)
            for speaker_id, existing in list(active_by_secondary.items()):
                existing_end = float(existing.get("end") or 0.0)
                if clipped_window_start > existing_end + gap_tolerance:
                    overlays.append(active_by_secondary.pop(speaker_id))
            candidate_kind = str(window.get("candidate_kind") or "").strip()
            candidate_speaker_id = str(window.get("candidate_speaker_id") or "").strip()
            sources = list(window.get("sources") or [])
            current_secondary_ids = set()
            leader_level_db = max(
                (
                    float(source.get("level_db"))
                    for source in sources
                    if source.get("level_db") is not None
                ),
                default=float("-inf"),
            )
            for source in sources:
                secondary_speaker_id = str(source.get("speaker_id") or "").strip()
                secondary_target_id = str(source.get("target_id") or "").strip()
                if not secondary_speaker_id or secondary_speaker_id == primary_speaker_id:
                    continue
                relative_level_db = float(source.get("relative_level_db") or 0.0)
                level_value = source.get("level_db")
                level_db = float(level_value) if level_value is not None else float("-inf")
                if level_db < minimum_absolute_level_db:
                    continue
                existing = active_by_secondary.get(secondary_speaker_id)
                if len(sources) < 2:
                    if not existing:
                        continue
                    if relative_level_db < minimum_first_relative_level_db:
                        continue
                if (
                    candidate_kind == "speaker"
                    and candidate_speaker_id
                    and candidate_speaker_id != secondary_speaker_id
                    and leader_level_db - level_db > 14.0
                ):
                    continue
                clipped_start = max(segment_start, window_start)
                clipped_end = min(segment_end, window_end)
                if existing:
                    existing_start_value = existing.get("start")
                    existing_start = (
                        float(existing_start_value)
                        if existing_start_value is not None
                        else clipped_start
                    )
                    clipped_end = min(clipped_end, existing_start + max_seconds)
                if clipped_end <= clipped_start:
                    continue
                current_secondary_ids.add(secondary_speaker_id)
                if existing and clipped_start <= float(existing.get("end") or 0.0) + gap_tolerance:
                    existing["end"] = max(float(existing.get("end") or 0.0), clipped_end)
                    existing["confidence"] = max(float(existing.get("confidence") or 0.0), float(window.get("candidate_confidence") or 0.0), 0.6)
                    existing["_max_relative_level_db"] = max(
                        float(existing.get("_max_relative_level_db") or float("-inf")),
                        relative_level_db,
                    )
                    existing["_relative_level_sum_db"] = (
                        float(existing.get("_relative_level_sum_db") or 0.0)
                        + relative_level_db
                    )
                    existing["_relative_level_count"] = int(existing.get("_relative_level_count") or 0) + 1
                    existing["_max_level_db"] = max(
                        float(existing.get("_max_level_db") or float("-inf")),
                        level_db,
                    )
                    existing["_level_sum_db"] = float(existing.get("_level_sum_db") or 0.0) + level_db
                    existing["_level_count"] = int(existing.get("_level_count") or 0) + 1
                    continue
                if existing:
                    overlays.append(active_by_secondary.pop(secondary_speaker_id))
                active_by_secondary[secondary_speaker_id] = {
                    "speaker_id": secondary_speaker_id,
                    "target_id": secondary_target_id,
                    "start": clipped_start,
                    "end": min(clipped_end, clipped_start + max_seconds),
                    "mode": "audio_only_interjection",
                    "reason": "audio_only_interjection",
                    "confidence": max(float(window.get("candidate_confidence") or 0.0), 0.6),
                    "_first_relative_level_db": relative_level_db,
                    "_max_relative_level_db": relative_level_db,
                    "_relative_level_sum_db": relative_level_db,
                    "_relative_level_count": 1,
                    "_first_level_db": level_db,
                    "_max_level_db": level_db,
                    "_level_sum_db": level_db,
                    "_level_count": 1,
                }

            closed = [speaker_id for speaker_id in list(active_by_secondary.keys()) if speaker_id not in current_secondary_ids]
            for speaker_id in closed:
                overlays.append(active_by_secondary.pop(speaker_id))

        overlays.extend(active_by_secondary.values())
        overlays = _merge_overlay_ranges(overlays, gap_tolerance=gap_tolerance)
        accepted: List[Dict[str, Any]] = []
        for overlay in overlays:
            duration = max(0.0, float(overlay.get("end") or 0.0) - float(overlay.get("start") or 0.0))
            if duration < min_seconds:
                metrics["suppressed_noise_spikes"] += 1
                continue
            relative_level_count = max(0, int(overlay.get("_relative_level_count") or 0))
            level_count = max(0, int(overlay.get("_level_count") or 0))
            max_relative_level_db = float(overlay.get("_max_relative_level_db") or float("-inf"))
            first_relative_level_db = float(overlay.get("_first_relative_level_db") or float("-inf"))
            max_level_db = float(overlay.get("_max_level_db") or float("-inf"))
            first_level_db = float(overlay.get("_first_level_db") or float("-inf"))
            if max_level_db < minimum_absolute_level_db:
                metrics["suppressed_weak_interjections"] += 1
                continue
            if (
                duration <= max(min_seconds, short_guard_seconds)
                and first_relative_level_db < minimum_first_relative_level_db
                and max_relative_level_db < minimum_max_relative_level_db
            ):
                metrics["suppressed_weak_interjections"] += 1
                continue
            if relative_level_count > 0:
                overlay["relative_level_db"] = float(overlay.get("_relative_level_sum_db") or 0.0) / relative_level_count
                overlay["max_relative_level_db"] = max_relative_level_db
                overlay["first_relative_level_db"] = first_relative_level_db
            if level_count > 0:
                overlay["level_db"] = float(overlay.get("_level_sum_db") or 0.0) / level_count
                overlay["max_level_db"] = max_level_db
                overlay["first_level_db"] = first_level_db
            overlay.pop("_first_relative_level_db", None)
            overlay.pop("_max_relative_level_db", None)
            overlay.pop("_relative_level_sum_db", None)
            overlay.pop("_relative_level_count", None)
            overlay.pop("_first_level_db", None)
            overlay.pop("_max_level_db", None)
            overlay.pop("_level_sum_db", None)
            overlay.pop("_level_count", None)
            accepted.append(overlay)

        if accepted:
            segment["audio_overlays"] = accepted
            metrics["audio_only_interjections"] += len(accepted)
        else:
            segment["audio_overlays"] = []

    return enriched, metrics


def _augment_audio_overlays_from_speaker_activity(
    segments: Sequence[Dict[str, Any]],
    *,
    speaker_ranges: Dict[str, List[Tuple[float, float]]],
    min_seconds: float,
    gap_tolerance: float,
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    adjusted = [dict(segment) for segment in segments]
    metrics = {
        "boundary_activity_overlay_extensions": 0,
    }
    if not adjusted:
        return adjusted, metrics

    for index, raw_segment in enumerate(adjusted):
        segment = dict(raw_segment)
        if str(segment.get("target_kind") or "") != "speaker":
            adjusted[index] = segment
            continue

        primary_speaker_id = str(segment.get("speaker_id") or "").strip()
        segment_start = float(segment.get("start") or 0.0)
        segment_end = float(segment.get("end") or 0.0)
        if not primary_speaker_id or segment_end <= segment_start:
            adjusted[index] = segment
            continue

        existing_overlays = [dict(item or {}) for item in list(segment.get("audio_overlays") or [])]
        overlay_specs: Dict[str, Dict[str, Any]] = {}
        for overlay in existing_overlays:
            speaker_id = str(overlay.get("speaker_id") or "").strip()
            if not speaker_id or speaker_id == primary_speaker_id:
                continue
            overlay_start = max(segment_start, float(overlay.get("start") or segment_start) - gap_tolerance)
            overlay_end = min(segment_end, float(overlay.get("end") or segment_end) + gap_tolerance)
            if overlay_end <= overlay_start:
                continue
            overlay_specs[speaker_id] = {
                "target_id": str(overlay.get("target_id") or "").strip(),
                "start_floor": overlay_start,
                "end_ceiling": overlay_end,
                "mode": str(overlay.get("mode") or "audio_only_interjection"),
                "reason": str(overlay.get("reason") or "audio_only_interjection"),
                "confidence": float(overlay.get("confidence") or 0.0),
            }

        additions: List[Dict[str, Any]] = []
        for speaker_id, spec in overlay_specs.items():
            if speaker_id == primary_speaker_id:
                continue
            activity_ranges = []
            for start, end in speaker_ranges.get(speaker_id) or []:
                clipped_start = max(segment_start, float(spec.get("start_floor") or segment_start), float(start))
                clipped_end = min(segment_end, float(spec.get("end_ceiling") or segment_end), float(end))
                if clipped_end > clipped_start:
                    activity_ranges.append((clipped_start, clipped_end))
            for overlay_start, overlay_end in _merge_time_ranges(activity_ranges, gap_tolerance=gap_tolerance):
                if overlay_end - overlay_start < min_seconds:
                    continue
                additions.append(
                    {
                        "speaker_id": speaker_id,
                        "target_id": str(spec.get("target_id") or ""),
                        "start": overlay_start,
                        "end": overlay_end,
                        "mode": str(spec.get("mode") or "audio_only_interjection"),
                        "reason": str(spec.get("reason") or "audio_only_interjection"),
                        "confidence": max(0.6, float(spec.get("confidence") or 0.0)),
                    }
                )

        merged_overlays = _merge_overlay_ranges(existing_overlays + additions, gap_tolerance=gap_tolerance)
        previous_signature = {
            (
                str(item.get("speaker_id") or "").strip(),
                round(float(item.get("start") or 0.0), 3),
                round(float(item.get("end") or 0.0), 3),
                str(item.get("mode") or "").strip(),
            )
            for item in existing_overlays
        }
        current_signature = {
            (
                str(item.get("speaker_id") or "").strip(),
                round(float(item.get("start") or 0.0), 3),
                round(float(item.get("end") or 0.0), 3),
                str(item.get("mode") or "").strip(),
            )
            for item in merged_overlays
        }
        if current_signature != previous_signature:
            metrics["boundary_activity_overlay_extensions"] += 1
        segment["audio_overlays"] = merged_overlays
        adjusted[index] = segment

    return adjusted, metrics
