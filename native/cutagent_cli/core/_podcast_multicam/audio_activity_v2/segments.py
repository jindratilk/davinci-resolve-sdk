from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple


def _merge_adjacent_segments(segments: List[Dict[str, Any]], min_gap: float = 0.12) -> List[Dict[str, Any]]:
    if not segments:
        return []

    merged: List[Dict[str, Any]] = [dict(segments[0])]
    for segment in segments[1:]:
        last = merged[-1]
        same_target = last.get("target_id") == segment.get("target_id")
        gap = float(segment.get("start", 0.0)) - float(last.get("end", 0.0))
        if same_target and gap <= min_gap:
            last["end"] = max(float(last.get("end", 0.0)), float(segment.get("end", 0.0)))
            last["confidence"] = max(float(last.get("confidence", 0.0)), float(segment.get("confidence", 0.0)))
            last.setdefault("sources", [])
            last["sources"].extend(segment.get("sources") or [])
            if segment.get("audio_primary_start") is not None:
                existing_audio_start = float(last.get("audio_primary_start") or last.get("start") or 0.0)
                last["audio_primary_start"] = min(existing_audio_start, float(segment.get("audio_primary_start") or existing_audio_start))
            if segment.get("audio_overlays"):
                last.setdefault("audio_overlays", [])
                last["audio_overlays"].extend(dict(item or {}) for item in list(segment.get("audio_overlays") or []))
            if segment.get("audio_primary_end") is not None:
                existing_audio_end = float(last.get("audio_primary_end") or last.get("end") or 0.0)
                last["audio_primary_end"] = max(existing_audio_end, float(segment.get("audio_primary_end") or existing_audio_end))
            continue
        merged.append(dict(segment))
    return merged


def _segment_duration(segment: Dict[str, Any]) -> float:
    return max(0.0, float(segment.get("end", 0.0)) - float(segment.get("start", 0.0)))


def _is_silence_hold(segment: Dict[str, Any]) -> bool:
    return (
        str(segment.get("target_kind") or "") == "wide"
        and not (segment.get("sources") or [])
    )


def _stabilize_short_silence_segments(
    segments: List[Dict[str, Any]],
    *,
    max_silence_seconds: float,
) -> List[Dict[str, Any]]:
    stabilized = [dict(segment) for segment in segments]
    if not stabilized:
        return stabilized

    for index, segment in enumerate(stabilized):
        if not _is_silence_hold(segment):
            continue
        if _segment_duration(segment) > max_silence_seconds:
            continue

        previous = stabilized[index - 1] if index > 0 else None
        following = stabilized[index + 1] if index + 1 < len(stabilized) else None

        preferred = None
        if previous and following and previous.get("target_id") == following.get("target_id"):
            preferred = previous
        elif previous and previous.get("target_kind") != "wide":
            preferred = previous
        elif following and following.get("target_kind") != "wide":
            preferred = following

        if not preferred:
            continue

        segment["target_id"] = preferred.get("target_id")
        segment["target_kind"] = preferred.get("target_kind")
        if preferred.get("speaker_id"):
            segment["speaker_id"] = preferred.get("speaker_id")
        segment["confidence"] = max(float(segment.get("confidence") or 0.0), 0.45)
        segment["reason"] = "held_through_short_pause"

    return stabilized


def _suppress_short_isolated_flips(
    segments: List[Dict[str, Any]],
    *,
    min_segment_seconds: float,
) -> List[Dict[str, Any]]:
    stabilized = [dict(segment) for segment in segments]
    if len(stabilized) < 3:
        return stabilized

    for index in range(1, len(stabilized) - 1):
        current = stabilized[index]
        previous = stabilized[index - 1]
        following = stabilized[index + 1]
        if previous.get("target_id") != following.get("target_id"):
            continue
        if str(previous.get("target_kind") or "") == "wide" or str(following.get("target_kind") or "") == "wide":
            continue
        if str(current.get("target_kind") or "") == "wide":
            continue
        if current.get("target_id") == previous.get("target_id"):
            continue
        if _segment_duration(current) >= min_segment_seconds:
            continue

        current["target_id"] = previous.get("target_id")
        current["target_kind"] = previous.get("target_kind")
        if previous.get("speaker_id"):
            current["speaker_id"] = previous.get("speaker_id")
        current["confidence"] = max(float(current.get("confidence") or 0.0), 0.45)
        current["reason"] = "suppressed_short_flip"

    return stabilized


def _refine_segments_to_speech_boundaries(
    segments: List[Dict[str, Any]],
    *,
    lookup: Dict[str, Dict[str, Any]],
    speaker_ranges: Dict[str, List[Tuple[float, float]]],
    refine_window_seconds: float,
) -> Tuple[List[Dict[str, Any]], int]:
    refined = [dict(segment) for segment in segments]
    refined_count = 0
    if not refined:
        return refined, refined_count

    for segment in refined:
        if str(segment.get("target_kind") or "") != "speaker":
            continue
        speaker_id = str(segment.get("speaker_id") or "").strip()
        if not speaker_id:
            target_id = str(segment.get("target_id") or "").strip()
            speaker_id = (
                str(lookup.get(target_id, {}).get("speaker_id") or "").strip()
                or str(lookup.get(Path(target_id).name, {}).get("speaker_id") or "").strip()
            )
        ranges = speaker_ranges.get(speaker_id or "")
        if not ranges:
            continue
        segment_start = float(segment.get("start") or 0.0)
        segment_end = float(segment.get("end") or 0.0)
        overlapping = [
            item
            for item in ranges
            if item[1] > segment_start and item[0] < segment_end
        ]
        if not overlapping:
            continue
        refined_start = max(segment_start, overlapping[0][0])
        refined_end = min(segment_end, overlapping[-1][1])
        if refined_end <= refined_start:
            continue
        if (
            abs(refined_start - segment_start) >= refine_window_seconds * 0.5
            or abs(refined_end - segment_end) >= refine_window_seconds * 0.5
        ):
            segment["start"] = refined_start
            segment["end"] = refined_end
            segment["reason"] = str(segment.get("reason") or "refined") + "|speech_boundary_refined"
            refined_count += 1

    return refined, refined_count


def _merge_overlay_ranges(
    overlays: Sequence[Dict[str, Any]],
    *,
    gap_tolerance: float,
) -> List[Dict[str, Any]]:
    merged: List[Dict[str, Any]] = []
    for raw in sorted(
        [dict(item or {}) for item in overlays],
        key=lambda item: (
            str(item.get("speaker_id") or ""),
            float(item.get("start") or 0.0),
            float(item.get("end") or 0.0),
        ),
    ):
        start = float(raw.get("start") or 0.0)
        end = float(raw.get("end") or 0.0)
        if end <= start:
            continue
        if (
            merged
            and str(merged[-1].get("speaker_id") or "") == str(raw.get("speaker_id") or "")
            and str(merged[-1].get("mode") or "") == str(raw.get("mode") or "")
            and str(merged[-1].get("reason") or "") == str(raw.get("reason") or "")
            and start <= float(merged[-1].get("end") or 0.0) + gap_tolerance
        ):
            merged[-1]["end"] = max(float(merged[-1].get("end") or 0.0), end)
            merged[-1]["confidence"] = max(float(merged[-1].get("confidence") or 0.0), float(raw.get("confidence") or 0.0))
            merged[-1]["_max_relative_level_db"] = max(
                float(merged[-1].get("_max_relative_level_db") or float("-inf")),
                float(raw.get("_max_relative_level_db") or float("-inf")),
            )
            merged[-1]["_relative_level_sum_db"] = (
                float(merged[-1].get("_relative_level_sum_db") or 0.0)
                + float(raw.get("_relative_level_sum_db") or 0.0)
            )
            merged[-1]["_relative_level_count"] = (
                int(merged[-1].get("_relative_level_count") or 0)
                + int(raw.get("_relative_level_count") or 0)
            )
            merged[-1]["_max_level_db"] = max(
                float(merged[-1].get("_max_level_db") or float("-inf")),
                float(raw.get("_max_level_db") or float("-inf")),
            )
            merged[-1]["_level_sum_db"] = (
                float(merged[-1].get("_level_sum_db") or 0.0)
                + float(raw.get("_level_sum_db") or 0.0)
            )
            merged[-1]["_level_count"] = (
                int(merged[-1].get("_level_count") or 0)
                + int(raw.get("_level_count") or 0)
            )
            continue
        merged.append(raw)
    return merged


def _merge_time_ranges(
    ranges: Sequence[Tuple[float, float]],
    *,
    gap_tolerance: float,
) -> List[Tuple[float, float]]:
    merged: List[Tuple[float, float]] = []
    for start, end in sorted(
        ((float(start), float(end)) for start, end in ranges),
        key=lambda item: (item[0], item[1]),
    ):
        if end <= start:
            continue
        if merged and start <= merged[-1][1] + gap_tolerance:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
            continue
        merged.append((start, end))
    return merged


def _find_adjacent_speaker_segment(
    segments: Sequence[Dict[str, Any]],
    index: int,
    *,
    direction: int,
) -> Optional[Dict[str, Any]]:
    cursor = index + direction
    while 0 <= cursor < len(segments):
        candidate = dict(segments[cursor] or {})
        if str(candidate.get("target_kind") or "") == "speaker" and str(candidate.get("speaker_id") or "").strip():
            return candidate
        cursor += direction
    return None
