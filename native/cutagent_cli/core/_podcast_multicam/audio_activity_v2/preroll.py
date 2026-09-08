from __future__ import annotations

from typing import Any, Dict, List, Sequence, Tuple


def _apply_camera_preroll(
    segments: Sequence[Dict[str, Any]],
    *,
    camera_preroll_seconds: float,
    audio_handoff_overlap_seconds: float,
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    adjusted = [dict(segment) for segment in segments]
    metrics = {
        "video_preroll_switches": 0,
        "audio_handoff_overlaps": 0,
    }
    if not adjusted:
        return adjusted, metrics

    for segment in adjusted:
        segment["audio_primary_start"] = float(segment.get("start") or 0.0)
        segment["audio_primary_end"] = float(segment.get("end") or 0.0)
        segment["audio_overlays"] = [dict(item or {}) for item in list(segment.get("audio_overlays") or [])]

    for index in range(1, len(adjusted)):
        previous = adjusted[index - 1]
        current = adjusted[index]
        previous_kind = str(previous.get("target_kind") or "").strip()
        current_kind = str(current.get("target_kind") or "").strip()
        if previous_kind not in {"speaker", "wide"} or current_kind not in {"speaker", "wide"}:
            continue
        previous_speaker_id = str(previous.get("speaker_id") or "").strip()
        current_speaker_id = str(current.get("speaker_id") or "").strip()
        previous_target_id = str(previous.get("target_id") or "").strip()
        current_target_id = str(current.get("target_id") or "").strip()
        same_speaker_target = (
            previous_kind == "speaker"
            and current_kind == "speaker"
            and previous_speaker_id
            and current_speaker_id
            and previous_speaker_id == current_speaker_id
        )
        same_visual_target = (
            previous_kind == current_kind
            and previous_target_id
            and current_target_id
            and previous_target_id == current_target_id
        )
        if same_speaker_target or same_visual_target:
            continue

        confirmed_takeover_time = float(current.get("audio_primary_start") or current.get("start") or 0.0)
        previous_start = float(previous.get("start") or 0.0)
        current_end = float(current.get("end") or 0.0)
        preroll_seconds = max(camera_preroll_seconds, 0.0)
        current_audio_start = confirmed_takeover_time
        if current_kind == "speaker":
            current_audio_start = confirmed_takeover_time - max(audio_handoff_overlap_seconds, 0.0)
        video_switch_time = max(previous_start, current_audio_start - preroll_seconds)
        if video_switch_time < confirmed_takeover_time:
            previous["end"] = max(previous_start, video_switch_time)
            previous_audio_end = float(previous.get("audio_primary_end") or previous_start)
            if previous_kind == "speaker":
                previous_audio_end = max(previous_audio_end, confirmed_takeover_time)
            previous["audio_primary_end"] = max(
                float(previous.get("audio_primary_start") or previous_start),
                previous_audio_end,
            )
            current["start"] = min(video_switch_time, current_end)
            current["audio_primary_start"] = min(
                current_end,
                max(float(current.get("start") or video_switch_time), current_audio_start),
            )
            current["reason"] = str(current.get("reason") or "speaker") + "|video_preroll"
            metrics["video_preroll_switches"] += 1

        carryover_end = min(current_end, confirmed_takeover_time)
        if carryover_end > float(current.get("audio_primary_start") or current.get("start") or 0.0):
            metrics["audio_handoff_overlaps"] += 1

    return adjusted, metrics
