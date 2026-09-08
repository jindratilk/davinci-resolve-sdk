from __future__ import annotations

import statistics
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from cutagent_cli.core._podcast_multicam.audio_activity_v2.io import (
    AudioWindowSample,
    _read_audio_window_levels,
    _speaker_activity_ranges,
)
from cutagent_cli.core._podcast_multicam.audio_activity_v2.overlays import (
    _augment_audio_overlays_from_speaker_activity,
    _collect_audio_only_interjections,
)
from cutagent_cli.core._podcast_multicam.audio_activity_v2.overlap_promotion import _promote_long_audio_overlaps_to_wide
from cutagent_cli.core._podcast_multicam.audio_activity_v2.preroll import _apply_camera_preroll
from cutagent_cli.core._podcast_multicam.audio_activity_v2.segments import (
    _merge_adjacent_segments,
    _refine_segments_to_speech_boundaries,
    _stabilize_short_silence_segments,
    _suppress_short_isolated_flips,
)
from cutagent_cli.core._podcast_multicam.audio_activity_v2.state import (
    _collapse_unbalanced_wide_segments,
    _resolve_speaker_target,
    _speaker_camera_lookup,
    _suppress_short_interjection_segments,
)
from cutagent_cli.core._podcast_multicam.audio_activity_v2.switching import _apply_switch_state_machine


def build_audio_activity_plan(
    audio_files: Sequence[str],
    speaker_map: Sequence[Dict[str, Any]],
    wide_camera_id: Optional[str] = None,
    window_seconds: float = 0.25,
    activity_margin_db: float = 6.0,
    dominance_margin_db: float = 4.0,
    min_hold_seconds: float = 1.5,
    max_silence_hold_seconds: float = 8.0,
    switch_delay_seconds: float = 0.5,
    short_interjection_max_seconds: float = 0.7,
    overlap_secondary_margin_db: float = 12.0,
    absolute_activity_floor_db: float = -50.0,
    camera_preroll_seconds: float = 0.35,
    audio_handoff_overlap_seconds: float = 0.35,
    audio_only_interjection_min_seconds: float = 0.2,
    audio_only_interjection_max_seconds: float = 2.5,
) -> Dict[str, Any]:
    """
    Inspect isolated microphone tracks and produce a camera switch plan.

    The audio analysis assumes one isolated mic track per speaker. Speaker
    switches require continuous dominance for a short delay; wide is reserved
    for real overlap where two speakers are simultaneously active.
    """
    track_samples: List[Tuple[str, float, int, List[AudioWindowSample]]] = []
    source_stats: List[Dict[str, Any]] = []

    for index, file_name in enumerate(audio_files or []):
        path = Path(file_name).expanduser()
        if not path.exists():
            source_stats.append(
                {
                    "audio_file": str(path),
                    "status": "missing",
                    "track_index": index,
                }
            )
            continue
        try:
            duration, frame_rate, samples = _read_audio_window_levels(path, window_seconds=window_seconds)
            if not samples:
                source_stats.append(
                    {
                        "audio_file": str(path),
                        "status": "empty",
                        "track_index": index,
                        "duration": duration,
                    }
                )
                continue
            track_samples.append((str(path), duration, frame_rate, samples))
            source_stats.append(
                {
                    "audio_file": str(path),
                    "status": "ok",
                    "track_index": index,
                    "duration": duration,
                    "sample_rate": frame_rate,
                    "window_count": len(samples),
                }
            )
        except Exception as exc:
            source_stats.append(
                {
                    "audio_file": str(path),
                    "status": "error",
                    "track_index": index,
                    "error": str(exc),
                }
            )

    if not track_samples:
        return {
            "duration_seconds": 0.0,
            "window_seconds": window_seconds,
            "segments": [],
            "source_stats": source_stats,
        }

    lookup = _speaker_camera_lookup(speaker_map)
    max_duration = max(duration for _path, duration, _sample_rate, _samples in track_samples)
    total_windows = max(len(samples) for _path, _duration, _sample_rate, samples in track_samples)
    refine_window_seconds = max(0.02, min(window_seconds / 5.0, 0.05))
    speaker_ranges = _speaker_activity_ranges(
        speaker_map,
        activity_margin_db=activity_margin_db,
        absolute_activity_floor_db=absolute_activity_floor_db,
        window_seconds=refine_window_seconds,
    )

    per_track_noise: Dict[str, float] = {}
    for path, _duration, _sample_rate, samples in track_samples:
        levels = [sample.rms_db for sample in samples]
        if not levels:
            per_track_noise[path] = -120.0
            continue
        try:
            per_track_noise[path] = statistics.median(sorted(levels)[: max(1, len(levels) // 4)])
        except Exception:
            per_track_noise[path] = statistics.median(levels)

    wide_target = str(wide_camera_id or "wide")
    overlap_relative_floor_db = max(activity_margin_db + 4.0, 10.0)
    overlap_absolute_floor_db = max(absolute_activity_floor_db + 18.0, -32.0)
    audio_only_interjection_absolute_floor_db = max(absolute_activity_floor_db + 18.0, -32.0)
    raw_windows: List[Dict[str, Any]] = []
    for window_index in range(total_windows):
        start = window_index * window_seconds
        end = min(max_duration, start + window_seconds)
        if start >= max_duration:
            break

        candidates: List[Dict[str, Any]] = []
        for path, _duration, _sample_rate, samples in track_samples:
            if window_index >= len(samples):
                continue
            sample = samples[window_index]
            if sample.end <= sample.start:
                continue
            noise_floor = per_track_noise.get(path, -120.0)
            relative_level = sample.rms_db - noise_floor
            active = relative_level >= activity_margin_db and sample.rms_db > absolute_activity_floor_db
            if active:
                speaker_id, target_id = _resolve_speaker_target(path, speaker_map, lookup)
                candidates.append(
                    {
                        "audio_file": path,
                        "level_db": sample.rms_db,
                        "relative_level_db": relative_level,
                        "speaker_id": speaker_id,
                        "target_id": target_id,
                    }
                )

        if not candidates:
            raw_windows.append(
                {
                    "start": start,
                    "end": end,
                    "candidate_kind": "hold",
                    "candidate_reason": "silence_hold",
                    "candidate_confidence": 0.4,
                    "sources": [],
                    "dominance_gap_db": None,
                }
            )
            continue

        candidates.sort(key=lambda item: (item["level_db"], item["relative_level_db"]), reverse=True)
        leader = candidates[0]
        runner_up = candidates[1] if len(candidates) > 1 else None
        dominance_gap = leader["level_db"] - (runner_up["level_db"] if runner_up else absolute_activity_floor_db)
        real_overlap = (
            runner_up is not None
            and dominance_gap <= overlap_secondary_margin_db
            and float(leader.get("level_db") or -120.0) >= overlap_absolute_floor_db
            and float(runner_up.get("level_db") or -120.0) >= overlap_absolute_floor_db
            and float(leader.get("relative_level_db") or 0.0) >= overlap_relative_floor_db
            and float(runner_up.get("relative_level_db") or 0.0) >= overlap_relative_floor_db
        )

        if real_overlap:
            raw_windows.append(
                {
                    "start": start,
                    "end": end,
                    "candidate_kind": "wide",
                    "candidate_target_id": wide_target,
                    "candidate_reason": "overlap_wide",
                    "candidate_confidence": max(0.7, min(0.95, 0.78 + ((overlap_secondary_margin_db - dominance_gap) / 30.0))),
                    "sources": candidates,
                    "dominance_gap_db": dominance_gap,
                }
            )
            continue

        if runner_up is not None and dominance_gap < dominance_margin_db:
            raw_windows.append(
                {
                    "start": start,
                    "end": end,
                    "candidate_kind": "hold",
                    "candidate_reason": "uncertain_dominance_hold",
                    "candidate_confidence": max(0.4, min(0.6, 0.45 + (dominance_gap / max(dominance_margin_db, 1.0)) * 0.15)),
                    "sources": candidates,
                    "dominance_gap_db": dominance_gap,
                }
            )
            continue

        confidence = max(0.55, min(0.99, 0.62 + (dominance_gap / 14.0)))
        raw_windows.append(
            {
                "start": start,
                "end": end,
                "candidate_kind": "speaker",
                "candidate_target_id": str(leader.get("target_id") or leader["audio_file"]),
                "candidate_speaker_id": leader.get("speaker_id"),
                "candidate_reason": "dominant_speaker",
                "candidate_confidence": confidence,
                "sources": candidates,
                "dominance_gap_db": dominance_gap,
            }
        )

    stabilized_windows, state_metrics = _apply_switch_state_machine(
        raw_windows,
        wide_camera_id=wide_target,
        switch_delay_seconds=max(window_seconds, switch_delay_seconds),
        silence_transition_anticipation_seconds=min(max_silence_hold_seconds, 1.0),
    )
    merged_windows = _merge_adjacent_segments(stabilized_windows, min_gap=max(window_seconds / 2.0, 0.08))
    merged_windows = _stabilize_short_silence_segments(
        merged_windows,
        max_silence_seconds=max(0.0, float(max_silence_hold_seconds or 0.0)),
    )
    merged_windows = _merge_adjacent_segments(merged_windows, min_gap=max(window_seconds / 2.0, 0.08))
    merged_windows, suppressed_interjections = _suppress_short_interjection_segments(
        merged_windows,
        short_interjection_max_seconds=max(short_interjection_max_seconds + window_seconds, window_seconds),
    )
    merged_windows = _merge_adjacent_segments(merged_windows, min_gap=max(window_seconds / 2.0, 0.08))
    merged_windows, collapsed_pending_overlaps = _collapse_unbalanced_wide_segments(
        merged_windows,
    )
    merged_windows = _merge_adjacent_segments(merged_windows, min_gap=max(window_seconds / 2.0, 0.08))
    merged_windows = _suppress_short_isolated_flips(
        merged_windows,
        min_segment_seconds=max(min_hold_seconds, window_seconds * 2.0),
    )
    merged_windows = _merge_adjacent_segments(merged_windows, min_gap=max(window_seconds / 2.0, 0.08))
    merged_windows, refined_boundaries = _refine_segments_to_speech_boundaries(
        merged_windows,
        lookup=lookup,
        speaker_ranges=speaker_ranges,
        refine_window_seconds=refine_window_seconds,
    )
    merged_windows = _merge_adjacent_segments(merged_windows, min_gap=max(window_seconds / 2.0, 0.08))
    merged_windows, interjection_metrics = _collect_audio_only_interjections(
        merged_windows,
        raw_windows=raw_windows,
        min_seconds=max(window_seconds, audio_only_interjection_min_seconds),
        max_seconds=max(audio_only_interjection_max_seconds, audio_only_interjection_min_seconds),
        gap_tolerance=max(window_seconds / 2.0, 0.08),
        short_guard_seconds=0.85,
        minimum_first_relative_level_db=activity_margin_db + 6.0,
        minimum_max_relative_level_db=activity_margin_db + 8.0,
        minimum_absolute_level_db=audio_only_interjection_absolute_floor_db,
    )
    merged_windows, boundary_overlay_metrics = _augment_audio_overlays_from_speaker_activity(
        merged_windows,
        speaker_ranges=speaker_ranges,
        min_seconds=max(window_seconds, audio_only_interjection_min_seconds),
        gap_tolerance=max(window_seconds / 2.0, 0.08),
    )
    merged_windows, promoted_overlap_metrics = _promote_long_audio_overlaps_to_wide(
        merged_windows,
        wide_camera_id=wide_target,
        promote_after_seconds=max(
            max(window_seconds, audio_only_interjection_min_seconds),
            min(max(audio_only_interjection_max_seconds, audio_only_interjection_min_seconds), 2.0),
        ),
        gap_tolerance=max(window_seconds / 2.0, 0.08),
    )
    merged_windows = _merge_adjacent_segments(merged_windows, min_gap=max(window_seconds / 2.0, 0.08))
    merged_windows, preroll_metrics = _apply_camera_preroll(
        merged_windows,
        camera_preroll_seconds=max(0.0, camera_preroll_seconds),
        audio_handoff_overlap_seconds=max(0.0, audio_handoff_overlap_seconds),
    )
    merged_windows = _merge_adjacent_segments(merged_windows, min_gap=max(window_seconds / 2.0, 0.08))
    metrics = {
        **state_metrics,
        "suppressed_interjections": state_metrics.get("suppressed_interjections", 0) + suppressed_interjections,
        "collapsed_unbalanced_wide_segments": collapsed_pending_overlaps,
        "speech_boundary_refinements": refined_boundaries,
        **interjection_metrics,
        **boundary_overlay_metrics,
        **promoted_overlap_metrics,
        **preroll_metrics,
        "wide_overlap_segments": sum(
            1
            for segment in merged_windows
            if str(segment.get("target_kind") or "") == "wide"
            and bool(segment.get("sources"))
        ),
    }
    return {
        "duration_seconds": max_duration,
        "window_seconds": window_seconds,
        "camera_switch_settings": {
            "switch_delay_seconds": switch_delay_seconds,
            "short_interjection_max_seconds": short_interjection_max_seconds,
            "analysis_window_seconds": window_seconds,
            "activity_margin_db": activity_margin_db,
            "dominance_margin_db": dominance_margin_db,
            "overlap_secondary_margin_db": overlap_secondary_margin_db,
            "camera_preroll_seconds": camera_preroll_seconds,
            "audio_handoff_overlap_seconds": audio_handoff_overlap_seconds,
            "audio_only_interjection_min_seconds": audio_only_interjection_min_seconds,
            "audio_only_interjection_max_seconds": audio_only_interjection_max_seconds,
            "audio_only_interjection_absolute_floor_db": audio_only_interjection_absolute_floor_db,
            "absolute_activity_floor_db": absolute_activity_floor_db,
            "max_silence_hold_seconds": max_silence_hold_seconds,
        },
        "segments": merged_windows,
        "source_stats": source_stats,
        "metrics": metrics,
        "audio_instructions": [
            {
                "speaker_id": str(item.get("speaker_id") or ""),
                "target_id": str(item.get("target_id") or ""),
                "start": float(item.get("start") or 0.0),
                "end": float(item.get("end") or 0.0),
                "mode": str(item.get("mode") or "primary"),
                "reason": str(item.get("reason") or ""),
                "confidence": float(item.get("confidence") or 0.0),
                "host_speaker_id": str(segment.get("speaker_id") or ""),
                "duration_seconds": max(0.0, float(item.get("end") or 0.0) - float(item.get("start") or 0.0)),
            }
            for segment in merged_windows
            for item in list(segment.get("audio_overlays") or [])
        ],
    }
