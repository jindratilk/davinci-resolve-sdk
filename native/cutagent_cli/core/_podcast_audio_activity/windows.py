"""Windows helpers for podcast audio activity planning."""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
import statistics
import struct
import subprocess
import tempfile
from typing import Any, Iterable
import wave

from ...errors import APICallFailed, ValidationError
from ...external_tools import resolve_tool
from .. import waveform_sync
from .._podcast_multicam.audio_activity_v2 import io as audio_activity_v2_io
from .._podcast_multicam.audio_activity_v2 import plan as audio_activity_v2_plan
from .._podcast_multicam.transcript import normalize_scribe_v2_transcript
from .common import *
from .parsing import *
from .levels import *
from .normalization import *


def _choose_window_target(
    *,
    active: list[dict[str, Any]],
    previous_target: dict[str, Any] | None,
    audio_angle_map: dict[str, str],
    audio_targets: dict[str, dict[str, Any]],
    overlap: dict[str, Any],
    activity_floor_db: float,
    activity_margin_db: float,
    dominance_margin_db: float,
) -> dict[str, Any]:
    if not active:
        return {
            "target_kind": "silence",
            "angle": None,
            "audio_source_ids": [],
            "candidate_angles": [],
            "reason": "silence",
            "confidence": 0.35,
        }
    active = sorted(active, key=lambda item: (float(item["rms_db"]), float(item["relative_db"])), reverse=True)
    leader = active[0]
    runner_up = active[1] if len(active) > 1 else None
    dominance_gap = float(leader["rms_db"]) - float(runner_up["rms_db"] if runner_up else -120.0)
    is_overlap = runner_up is not None and dominance_gap < dominance_margin_db
    if is_overlap:
        policy = str(overlap.get("policy") or "mark").strip()
        source_ids = [str(item["id"]) for item in active]
        overlap_relative_floor_db = 0.0 if float(activity_margin_db) <= 0.0 else max(float(activity_margin_db) + 4.0, 10.0)
        real_overlap = (
            runner_up is not None
            and dominance_gap <= max(float(dominance_margin_db) * 3.0, 10.0)
            and float(leader.get("rms_db") or -120.0) >= max(float(activity_floor_db) + 18.0, -32.0)
            and float(runner_up.get("rms_db") or -120.0) >= max(float(activity_floor_db) + 18.0, -32.0)
            and float(leader.get("relative_db") or 0.0) >= overlap_relative_floor_db
            and float(runner_up.get("relative_db") or 0.0) >= overlap_relative_floor_db
        )
        if policy in {"angle", "wide"}:
            if not real_overlap and previous_target and previous_target.get("angle"):
                return {
                    "target_kind": "hold",
                    "angle": previous_target.get("angle"),
                    "audio_source_ids": source_ids,
                    "candidate_angles": [str(previous_target.get("angle"))],
                    "reason": "uncertain_dominance_hold_previous",
                    "confidence": 0.55,
                    "dominance_gap_db": dominance_gap,
                }
            if not real_overlap:
                angle, candidates, source = _resolve_source_angle(str(leader["id"]), audio_angle_map=audio_angle_map, audio_targets=audio_targets)
                return {
                    "target_kind": "audio_source",
                    "angle": angle,
                    "audio_source_ids": [str(leader["id"])],
                    "candidate_angles": candidates,
                    "target_resolution": source,
                    "reason": "uncertain_dominance_fallback_dominant",
                    "confidence": 0.6,
                    "dominance_gap_db": dominance_gap,
                    **({"requires_agent_decision": True} if angle is None else {}),
                }
            angle = str(overlap.get("angle") or "").strip()
            if not angle:
                raise ValidationError(
                    "overlap policy angle/wide requires overlap.angle.",
                    details={"overlap": overlap},
                )
            return {
                "target_kind": "overlap",
                "angle": angle,
                "audio_source_ids": source_ids,
                "candidate_angles": [angle],
                "reason": "overlap_wide" if policy == "wide" else "overlap_angle",
                "confidence": 0.8,
                "dominance_gap_db": dominance_gap,
            }
        if policy == "dominant":
            if not real_overlap and previous_target and previous_target.get("angle"):
                return {
                    "target_kind": "hold",
                    "angle": previous_target.get("angle"),
                    "audio_source_ids": source_ids,
                    "candidate_angles": [str(previous_target.get("angle"))],
                    "reason": "uncertain_dominance_hold_previous",
                    "confidence": 0.55,
                    "dominance_gap_db": dominance_gap,
                }
            angle, candidates, source = _resolve_source_angle(str(leader["id"]), audio_angle_map=audio_angle_map, audio_targets=audio_targets)
            return {
                "target_kind": "audio_source",
                "angle": angle,
                "audio_source_ids": [str(leader["id"])],
                "candidate_angles": candidates,
                "target_resolution": source,
                "reason": "overlap_dominant",
                "confidence": 0.65,
                "dominance_gap_db": dominance_gap,
            }
        if policy == "hold" and previous_target and previous_target.get("angle"):
            return {
                "target_kind": "hold",
                "angle": previous_target.get("angle"),
                "audio_source_ids": source_ids,
                "candidate_angles": [str(previous_target.get("angle"))],
                "reason": "overlap_hold_previous",
                "confidence": 0.55,
                "dominance_gap_db": dominance_gap,
            }
        if policy == "hold":
            angle, candidates, source = _resolve_source_angle(str(leader["id"]), audio_angle_map=audio_angle_map, audio_targets=audio_targets)
            return {
                "target_kind": "audio_source",
                "angle": angle,
                "audio_source_ids": [str(leader["id"])],
                "candidate_angles": candidates,
                "target_resolution": source,
                "reason": "overlap_hold_fallback_dominant",
                "confidence": 0.6,
                "dominance_gap_db": dominance_gap,
                **({"requires_agent_decision": True} if angle is None else {}),
            }
        if policy != "mark":
            raise ValidationError(
                "Unsupported overlap policy.",
                details={"policy": policy, "supported_policies": ["angle", "wide", "dominant", "hold", "mark"]},
            )
        return {
            "target_kind": "overlap",
            "angle": None,
            "audio_source_ids": source_ids,
            "candidate_angles": [],
            "reason": "overlap_marked_for_agent",
            "confidence": 0.5,
            "dominance_gap_db": dominance_gap,
            "requires_agent_decision": True,
        }

    angle, candidates, source = _resolve_source_angle(str(leader["id"]), audio_angle_map=audio_angle_map, audio_targets=audio_targets)
    return {
        "target_kind": "audio_source",
        "angle": angle,
        "audio_source_ids": [str(leader["id"])],
        "candidate_angles": candidates,
        "target_resolution": source,
        "reason": "dominant_audio_source",
        "confidence": min(0.99, max(0.55, 0.6 + dominance_gap / 30.0)),
        "dominance_gap_db": dominance_gap,
        **({"requires_agent_decision": True} if angle is None else {}),
    }


def _merge_adjacent_windows(windows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    for raw in windows:
        window = dict(raw)
        if not merged:
            merged.append(window)
            continue
        previous = merged[-1]
        same_exact_target = (
            previous.get("target_kind") == window.get("target_kind")
            and previous.get("angle") == window.get("angle")
            and previous.get("audio_source_ids") == window.get("audio_source_ids")
            and previous.get("requires_agent_decision") == window.get("requires_agent_decision")
        )
        same_resolved_angle = (
            previous.get("angle")
            and previous.get("angle") == window.get("angle")
            and previous.get("requires_agent_decision") == window.get("requires_agent_decision")
        )
        same_target = same_exact_target or same_resolved_angle
        if same_target and int(window["start_ms"]) <= int(previous["end_ms"]):
            previous["end_ms"] = max(int(previous["end_ms"]), int(window["end_ms"]))
            previous["confidence"] = max(float(previous.get("confidence") or 0.0), float(window.get("confidence") or 0.0))
            source_ids = [
                *list(previous.get("audio_source_ids") or []),
                *list(window.get("audio_source_ids") or []),
            ]
            if source_ids:
                previous["audio_source_ids"] = list(dict.fromkeys(str(item) for item in source_ids))
            candidates = [
                *list(previous.get("candidate_angles") or []),
                *list(window.get("candidate_angles") or []),
            ]
            if candidates:
                previous["candidate_angles"] = list(dict.fromkeys(str(item) for item in candidates))
            suppressed_events = list(previous.get("suppressed_audio_events") or [])
            if window.get("suppressed_original"):
                suppressed_events.append(
                    {
                        "start_ms": int(window["start_ms"]),
                        "end_ms": int(window["end_ms"]),
                        **dict(window["suppressed_original"]),
                    }
                )
            suppressed_events.extend(list(window.get("suppressed_audio_events") or []))
            if suppressed_events:
                previous["suppressed_audio_events"] = suppressed_events
            continue
        merged.append(window)
    return merged


def _target_signature(segment: dict[str, Any] | None) -> tuple[str, str] | None:
    if not segment or not segment.get("angle"):
        return None
    return (str(segment.get("target_kind") or ""), str(segment.get("angle") or ""))


def _apply_switch_state_machine(raw_windows: list[dict[str, Any]], *, switch_delay_ms: int, max_silence_hold_ms: int) -> list[dict[str, Any]]:
    if not raw_windows or switch_delay_ms <= 0:
        return [dict(window) for window in raw_windows]

    finalized: list[dict[str, Any]] = []
    current_target: dict[str, Any] | None = None
    pending_target: dict[str, Any] | None = None

    def finalize(window: dict[str, Any], target: dict[str, Any], *, reason: str, confidence: float | None = None) -> dict[str, Any]:
        row = dict(window)
        original_angle = str(row.get("angle") or "").strip()
        original_source_ids = list(row.get("audio_source_ids") or [])
        original_candidate_angles = list(row.get("candidate_angles") or [])
        row["target_kind"] = str(target.get("target_kind") or row.get("target_kind") or "audio_source")
        row["angle"] = target.get("angle")
        row["candidate_angles"] = [str(target.get("angle"))] if target.get("angle") else []
        row["audio_source_ids"] = list(target.get("audio_source_ids") or row.get("audio_source_ids") or [])
        row["reason"] = reason
        row["confidence"] = max(float(row.get("confidence") or 0.0), float(confidence if confidence is not None else target.get("confidence") or 0.0))
        if reason == "confirmed_speaker_switch_backfilled":
            row.pop("suppressed_original", None)
        elif original_angle and original_angle != str(target.get("angle") or "") and original_source_ids:
            row["suppressed_original"] = {
                "audio_source_ids": original_source_ids,
                "candidate_angles": original_candidate_angles or [original_angle],
            }
        return row

    def candidate_from(window: dict[str, Any]) -> dict[str, Any] | None:
        angle = str(window.get("angle") or "").strip()
        if not angle:
            return None
        kind = str(window.get("target_kind") or "").strip()
        if kind in {"silence", "hold"}:
            return None
        return {
            "target_kind": kind,
            "angle": angle,
            "audio_source_ids": list(window.get("audio_source_ids") or []),
            "confidence": float(window.get("confidence") or 0.0),
            "reason": str(window.get("reason") or ""),
        }

    def same_target(left: dict[str, Any] | None, right: dict[str, Any] | None) -> bool:
        return _target_signature(left) == _target_signature(right)

    for index, raw in enumerate(raw_windows):
        window = dict(raw)
        candidate = candidate_from(window)
        if candidate is None:
            pending_target = None
            finalized.append(window)
            continue

        if current_target is None:
            current_target = dict(candidate)
            pending_target = None
            initial = dict(window)
            initial["reason"] = "initial_speaker_lock" if str(candidate.get("target_kind")) == "audio_source" else str(window.get("reason") or "initial_target_lock")
            initial["confidence"] = max(float(initial.get("confidence") or 0.0), 0.6)
            finalized.append(initial)
            continue

        if same_target(current_target, candidate):
            pending_target = None
            finalized.append(window)
            continue

        if same_target(pending_target, candidate):
            pending_target["end_ms"] = int(window.get("end_ms") or pending_target.get("end_ms") or 0)
        else:
            pending_target = {
                **dict(candidate),
                "start_ms": int(window.get("start_ms") or 0),
                "end_ms": int(window.get("end_ms") or 0),
                "start_index": len(finalized),
            }

        finalized.append(
            finalize(
                window,
                current_target,
                reason="waiting_for_switch_delay",
                confidence=max(float(window.get("confidence") or 0.0), 0.45),
            )
        )
        pending_duration = int(pending_target.get("end_ms") or 0) - int(pending_target.get("start_ms") or 0)
        if pending_duration >= max(int(switch_delay_ms), 1):
            start_index = max(0, min(int(pending_target.get("start_index") or len(finalized) - 1), len(finalized) - 1))
            for pending_index in range(start_index, len(finalized)):
                finalized[pending_index] = finalize(
                    finalized[pending_index],
                    pending_target,
                    reason="confirmed_speaker_switch_backfilled",
                    confidence=max(float(finalized[pending_index].get("confidence") or 0.0), float(candidate.get("confidence") or 0.0), 0.6),
                )
            current_target = dict(candidate)
            pending_target = None

    return finalized


def _stabilize_segments(segments: list[dict[str, Any]], *, min_switch_ms: int, switch_delay_ms: int, max_silence_hold_ms: int) -> list[dict[str, Any]]:
    threshold = max(int(min_switch_ms), int(switch_delay_ms))
    stabilized = [dict(segment) for segment in segments]
    for index, segment in enumerate(stabilized):
        duration = int(segment["end_ms"]) - int(segment["start_ms"])
        if segment.get("target_kind") == "silence" and max_silence_hold_ms > 0 and duration <= max_silence_hold_ms:
            replacement = stabilized[index - 1] if index > 0 else (stabilized[index + 1] if index + 1 < len(stabilized) else None)
            if replacement and replacement.get("angle"):
                segment["target_kind"] = "hold"
                segment["angle"] = replacement.get("angle")
                segment["candidate_angles"] = [str(replacement.get("angle"))]
                segment["reason"] = "held_through_short_silence"
                segment["confidence"] = max(float(segment.get("confidence") or 0.0), 0.45)
            continue
        if threshold <= 0 or duration >= threshold or segment.get("target_kind") == "silence":
            continue
        previous = stabilized[index - 1] if index > 0 else None
        following = stabilized[index + 1] if index + 1 < len(stabilized) else None
        replacement = previous if previous and previous.get("angle") else following if following and following.get("angle") else None
        if replacement:
            original_audio_source_ids = list(segment.get("audio_source_ids") or [])
            original_candidate_angles = list(segment.get("candidate_angles") or [])
            segment["target_kind"] = "hold"
            segment["angle"] = replacement.get("angle")
            segment["candidate_angles"] = [str(replacement.get("angle"))]
            segment["reason"] = "suppressed_short_audio_switch"
            segment["confidence"] = max(float(segment.get("confidence") or 0.0), 0.45)
            segment["suppressed_original"] = {
                "audio_source_ids": original_audio_source_ids,
                "candidate_angles": original_candidate_angles,
            }
    return _merge_adjacent_windows(stabilized)


def _duration_ms(segments: list[dict[str, Any]], *, predicate=None) -> int:
    total = 0
    for segment in segments:
        if predicate is not None and not predicate(segment):
            continue
        total += max(0, int(segment.get("end_ms") or 0) - int(segment.get("start_ms") or 0))
    return total


def _dominance_gaps_from_windows(windows: list[dict[str, Any]]) -> list[float]:
    gaps: list[float] = []
    for window in windows:
        sources = sorted(
            [source for source in list(window.get("sources") or []) if isinstance(source, dict)],
            key=lambda source: float(source.get("rms_db") or -120.0),
            reverse=True,
        )
        if len(sources) < 2:
            continue
        gaps.append(float(sources[0].get("rms_db") or -120.0) - float(sources[1].get("rms_db") or -120.0))
    return gaps


def _segment_metrics(*, segments: list[dict[str, Any]], unresolved_segments: list[dict[str, Any]], raw_windows: list[dict[str, Any]], total_ms: int) -> dict[str, Any]:
    resolved_segments = [segment for segment in segments if segment.get("angle")]
    overlap_segments = [segment for segment in segments if segment.get("target_kind") == "overlap"]
    silence_segments = [segment for segment in segments if segment.get("target_kind") == "silence"]
    hold_segments = [segment for segment in segments if segment.get("target_kind") == "hold"]
    resolved_ms = _duration_ms(resolved_segments)
    unresolved_ms = _duration_ms(unresolved_segments)
    overlap_ms = _duration_ms(overlap_segments)
    silence_ms = _duration_ms(silence_segments)
    hold_ms = _duration_ms(hold_segments)
    durations = [max(0, int(segment.get("end_ms") or 0) - int(segment.get("start_ms") or 0)) for segment in resolved_segments]
    short_resolved = [duration for duration in durations if duration < 1000]
    gaps = _dominance_gaps_from_windows(raw_windows)
    return {
        "total_duration_ms": int(total_ms),
        "segment_count": len(segments),
        "resolved_segment_count": len(resolved_segments),
        "unresolved_segment_count": len(unresolved_segments),
        "overlap_segment_count": len(overlap_segments),
        "silence_segment_count": len(silence_segments),
        "hold_segment_count": len(hold_segments),
        "resolved_duration_ms": resolved_ms,
        "unresolved_duration_ms": unresolved_ms,
        "overlap_duration_ms": overlap_ms,
        "silence_duration_ms": silence_ms,
        "hold_duration_ms": hold_ms,
        "resolved_coverage_ratio": round(resolved_ms / total_ms, 4) if total_ms > 0 else 0.0,
        "unresolved_ratio": round(unresolved_ms / total_ms, 4) if total_ms > 0 else 0.0,
        "overlap_ratio": round(overlap_ms / total_ms, 4) if total_ms > 0 else 0.0,
        "silence_ratio": round(silence_ms / total_ms, 4) if total_ms > 0 else 0.0,
        "switches_per_minute": round(max(0, len(resolved_segments) - 1) / max(total_ms / 60000.0, 0.001), 3),
        "average_resolved_shot_ms": round(sum(durations) / len(durations), 1) if durations else 0.0,
        "median_resolved_shot_ms": round(statistics.median(durations), 1) if durations else 0.0,
        "short_resolved_segment_count": len(short_resolved),
        "short_resolved_ratio": round(len(short_resolved) / len(durations), 4) if durations else 0.0,
        "dominance_gap_db_percentiles": {
            str(percentile): (_round_db(value) if value is not None else None)
            for percentile in (10, 25, 50, 75, 90)
            for value in [_percentile(gaps, percentile)]
        },
    }


__all__ = (
    '_choose_window_target',
    '_merge_adjacent_windows',
    '_target_signature',
    '_apply_switch_state_machine',
    '_stabilize_segments',
    '_duration_ms',
    '_dominance_gaps_from_windows',
    '_segment_metrics',
)
