"""Calibration helpers for podcast audio activity planning."""

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
from .windows import *
from .plan_v1 import *
from .plan_v2 import *
from .api import *


def _unique_numbers(values: Iterable[float | int | None], *, as_int: bool = False) -> list[float | int]:
    unique: list[float | int] = []
    seen: set[float | int] = set()
    for value in values:
        if value is None:
            continue
        normalized = int(value) if as_int else _round_db(float(value))
        if normalized in seen:
            continue
        seen.add(normalized)
        unique.append(normalized)
    return unique


def _activity_floor_candidates(per_source: dict[str, dict[str, Any]]) -> list[float]:
    noise_values = [float(source.get("noise_floor_db") or -120.0) for source in per_source.values()]
    percentile_values: list[float] = []
    for source in per_source.values():
        stats = dict(source.get("level_stats") or {})
        percentiles = dict(stats.get("rms_db_percentiles") or {})
        for key in ("10", "25", "50"):
            value = percentiles.get(key)
            if value is not None:
                percentile_values.append(float(value))
    global_noise = statistics.median(noise_values) if noise_values else -60.0
    candidates = _unique_numbers(
        [
            -50.0,
            -45.0,
            max(-70.0, min(-35.0, global_noise + 6.0)),
            _percentile(percentile_values, 25),
        ]
    )
    return [float(max(-75.0, min(-30.0, value))) for value in candidates[:4]]


def _calibration_grid(*, style: str, per_source_by_window: dict[int, dict[str, dict[str, Any]]]) -> list[dict[str, Any]]:
    style = str(style or "balanced").strip().lower()
    if style == "reactive":
        windows = [100, 250]
        min_switches = [700, 1200]
        delays = [250, 500]
        dominance = [3.0, 6.0, 9.0]
        silence_holds = [8000]
    elif style == "calm":
        windows = [250, 500]
        min_switches = [1800, 2800]
        delays = [500, 900]
        dominance = [4.0, 8.0, 12.0]
        silence_holds = [8000, 999999]
    else:
        floor_values = [float(value) for value in _unique_numbers([*list(_activity_floor_candidates(per_source_by_window[250])), -45.0, -50.0])]
        dynamic_floors = [floor for floor in floor_values if floor not in {-45.0, -50.0}][:2]
        curated = [
            (250, -45.0, 6.0, 4.0, 1500, 500, 8000),
            (250, -50.0, 6.0, 4.0, 1500, 500, 8000),
            (250, -45.0, 9.0, 4.0, 1500, 500, 8000),
            (250, -45.0, 6.0, 6.0, 1500, 500, 8000),
            (250, -45.0, 6.0, 4.0, 2000, 500, 8000),
            (500, -45.0, 6.0, 4.0, 1500, 500, 8000),
            (500, -50.0, 6.0, 4.0, 1500, 500, 8000),
        ]
        for floor in dynamic_floors:
            curated.append((250, floor, 6.0, 4.0, 1500, 500, 8000))
            curated.append((250, floor, 6.0, 4.0, 2000, 500, 8000))
        return [
            {
                "analysis_window_ms": window_ms,
                "activity_floor_db": floor,
                "activity_margin_db": activity_margin,
                "dominance_margin_db": dominance_margin,
                "min_switch_ms": min_switch,
                "switch_delay_ms": delay,
                "max_silence_hold_ms": silence_hold,
            }
            for window_ms, floor, activity_margin, dominance_margin, min_switch, delay, silence_hold in curated
        ]
    activity_margins = [3.0, 6.0, 9.0]
    grid: list[dict[str, Any]] = []
    for window_ms in windows:
        floors = _activity_floor_candidates(per_source_by_window[window_ms])
        for floor in floors:
            for activity_margin in activity_margins:
                for dominance_margin in dominance:
                    for min_switch in min_switches:
                        for delay in delays:
                            for silence_hold in silence_holds:
                                grid.append(
                                    {
                                        "analysis_window_ms": int(window_ms),
                                        "activity_floor_db": float(floor),
                                        "activity_margin_db": float(activity_margin),
                                        "dominance_margin_db": float(dominance_margin),
                                        "min_switch_ms": int(min_switch),
                                        "switch_delay_ms": int(delay),
                                        "max_silence_hold_ms": int(silence_hold),
                                    }
                                )
    return grid


def _calibration_overlap_candidates(overlap: dict[str, Any] | None) -> list[dict[str, Any]]:
    base = dict(overlap or {})
    policy = str(base.get("policy") or "").strip()
    angle = str(base.get("angle") or "").strip()
    if policy and policy != "auto":
        return [base]
    if not angle:
        return [base]
    # A supplied overlap angle means "this shared angle is available", not
    # necessarily that every ambiguous window should cut wide. Calibration ranks
    # the creative policy so agents can apply the same choice during switch.
    return [
        {"policy": "wide", "angle": angle},
        {"policy": "dominant", "angle": angle},
        {"policy": "hold", "angle": angle},
    ]


def _style_targets(style: str) -> dict[str, float]:
    style = str(style or "balanced").strip().lower()
    if style == "reactive":
        return {"target_shot_ms": 7000.0, "max_switches_per_minute": 14.0, "min_switches_per_minute": 5.0}
    if style == "calm":
        return {"target_shot_ms": 28000.0, "max_switches_per_minute": 5.0, "min_switches_per_minute": 1.4}
    return {"target_shot_ms": 18000.0, "max_switches_per_minute": 8.0, "min_switches_per_minute": 2.3}


def _segment_angle_at(segments: list[dict[str, Any]], midpoint_ms: int) -> str | None:
    for segment in segments:
        if int(segment.get("start_ms") or 0) <= midpoint_ms < int(segment.get("end_ms") or 0):
            angle = str(segment.get("angle") or "").strip()
            return angle or None
    return None


def _transcript_alignment_metrics(
    *,
    plan: dict[str, Any],
    transcript_path: str | None,
    transcript_speaker_map: dict[str, str],
    audio_angle_map: dict[str, str],
    audio_targets: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    if not transcript_path:
        return None
    transcript = normalize_scribe_v2_transcript(transcript_path)
    segments = list(plan.get("segments") or [])
    transcript_segments = list(transcript.get("segments") or [])
    metrics = dict(plan.get("metrics") or {})
    analyzed_end_ms = int(metrics.get("total_duration_ms") or 0)
    if analyzed_end_ms <= 0:
        analyzed_end_ms = max((int(segment.get("end_ms") or 0) for segment in segments), default=0)
    mapped_total_ms = 0
    matching_ms = 0
    mismatches: list[dict[str, Any]] = []
    unmapped_speakers: set[str] = set()
    for row in transcript_segments:
        speaker_id = str(row.get("speaker_id") or "").strip()
        source_id = str(transcript_speaker_map.get(speaker_id) or "").strip()
        if not source_id:
            unmapped_speakers.add(speaker_id)
            continue
        expected_angle, _candidate_angles, _resolution_source = _resolve_source_angle(
            source_id,
            audio_angle_map=audio_angle_map,
            audio_targets=audio_targets,
        )
        expected_angle = str(expected_angle or "").strip()
        if not expected_angle:
            unmapped_speakers.add(speaker_id)
            continue
        start_ms = int(row.get("start_ms") or 0)
        end_ms = int(row.get("end_ms") or start_ms)
        if analyzed_end_ms > 0:
            start_ms = max(0, min(start_ms, analyzed_end_ms))
            end_ms = max(0, min(end_ms, analyzed_end_ms))
        if end_ms <= start_ms:
            continue
        duration = end_ms - start_ms
        midpoint_ms = start_ms + duration // 2
        actual_angle = _segment_angle_at(segments, midpoint_ms)
        mapped_total_ms += duration
        if actual_angle == expected_angle:
            matching_ms += duration
        else:
            mismatches.append(
                {
                    "start_ms": start_ms,
                    "end_ms": end_ms,
                    "speaker_id": speaker_id,
                    "expected_source_id": source_id,
                    "expected_angle": expected_angle,
                    "actual_angle": actual_angle,
                    "text": str(row.get("text") or "")[:160],
                }
            )
    agreement = matching_ms / mapped_total_ms if mapped_total_ms > 0 else None
    return {
        "transcript_format": transcript.get("format"),
        "source_key": transcript.get("source_key"),
        "speaker_count": len(transcript.get("speakers") or []),
        "mapped_duration_ms": mapped_total_ms,
        "agreement_ratio": round(float(agreement), 4) if agreement is not None else None,
        "mismatch_count": len(mismatches),
        "unmapped_speakers": sorted(item for item in unmapped_speakers if item),
        "sample_mismatches": mismatches[:10],
    }


def _score_candidate(
    *,
    plan: dict[str, Any],
    transcript_alignment: dict[str, Any] | None,
    style: str,
    overlap: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metrics = dict(plan.get("metrics") or {})
    switching = dict(plan.get("switching") or {})
    is_v2_plan = bool(metrics.get("v2_metrics")) or str(plan.get("planner") or "") == "audio_activity_v2"
    targets = _style_targets(style)
    score = 100.0
    risks: list[str] = []
    unresolved_ratio = float(metrics.get("unresolved_ratio") or 0.0)
    silence_ratio = float(metrics.get("silence_ratio") or 0.0)
    overlap_ratio = float(metrics.get("overlap_ratio") or 0.0)
    short_ratio = float(metrics.get("short_resolved_ratio") or 0.0)
    switches_per_minute = float(metrics.get("switches_per_minute") or 0.0)
    average_shot_ms = float(metrics.get("average_resolved_shot_ms") or 0.0)
    total_duration_ms = float(metrics.get("total_duration_ms") or 0.0)
    resolved_segment_count = int(metrics.get("resolved_segment_count") or 0)
    suppressed_short_switch_count = int(metrics.get("suppressed_short_switch_count") or 0)
    dominance_p25 = dict(metrics.get("dominance_gap_db_percentiles") or {}).get("25")
    overlap_policy = str(dict(overlap or {}).get("policy") or "").strip()
    activity_floor_db = float(switching.get("activity_floor_db") or 0.0)
    gain_normalization_db = abs(float(metrics.get("gain_normalization_db") or 0.0))
    source_p90_spread_db = float(metrics.get("source_p90_spread_db") or 0.0)
    score -= min(35.0, unresolved_ratio * 120.0)
    score -= min(6.0, silence_ratio * 120.0)
    score -= min(20.0, max(0.0, silence_ratio - 0.12) * 70.0)
    score -= min(20.0, max(0.0, overlap_ratio - 0.35) * 55.0)
    if overlap_policy in {"angle", "wide"} and overlap_ratio > 0.0:
        score -= min(8.0, 3.0 + overlap_ratio * 60.0)
        risks.append("wide_overlap_bias")
    score -= min(18.0, short_ratio * 45.0)
    score -= min(18.0, max(0.0, switches_per_minute - targets["max_switches_per_minute"]) * 2.0)
    min_switches_per_minute = float(targets["min_switches_per_minute"])
    if total_duration_ms >= 180000 and switches_per_minute < min_switches_per_minute:
        score -= min(18.0, (min_switches_per_minute - switches_per_minute) * 3.0)
        risks.append("too_few_switches")
    if average_shot_ms and average_shot_ms < targets["target_shot_ms"] * 0.35:
        score -= 12.0
    if average_shot_ms and average_shot_ms > targets["target_shot_ms"] * 1.75:
        score -= min(18.0, ((average_shot_ms / targets["target_shot_ms"]) - 1.75) * 7.0)
        risks.append("shots_too_long")
    if is_v2_plan and str(style or "balanced").strip().lower() == "balanced" and int(switching.get("analysis_window_ms") or 0) > 250:
        score -= 7.0
        risks.append("coarse_analysis_window")
    if is_v2_plan and str(style or "balanced").strip().lower() == "balanced" and activity_floor_db not in {-45.0, -50.0}:
        score -= 1.0
        if gain_normalization_db >= 8.0:
            score -= 1.5
            risks.append("dynamic_floor_gain_sensitive")
    if is_v2_plan and source_p90_spread_db > 6.0:
        score -= min(12.0, (source_p90_spread_db - 6.0) * 1.5)
        risks.append("gain_imbalance_review")
    if suppressed_short_switch_count and resolved_segment_count:
        suppressed_per_resolved = suppressed_short_switch_count / max(1.0, float(resolved_segment_count))
        suppressed_per_minute = suppressed_short_switch_count / max(total_duration_ms / 60000.0, 0.001)
        if (not is_v2_plan) and total_duration_ms >= 180000 and suppressed_per_resolved > 1.5 and suppressed_per_minute > switches_per_minute:
            score -= min(24.0, (suppressed_per_resolved - 1.5) * 10.0)
            risks.append("suppression_heavy")
    if (not is_v2_plan) and dominance_p25 is not None and float(dominance_p25) < 2.5:
        score -= 10.0
        risks.append("low_speaker_separation")
    if unresolved_ratio > 0.08:
        risks.append("unresolved_audio_targets")
    if silence_ratio > 0.02:
        risks.append("silence_gaps")
    if overlap_ratio > 0.4:
        risks.append("overlap_heavy")
    if short_ratio > 0.18:
        risks.append("many_short_segments")
    if transcript_alignment:
        agreement = transcript_alignment.get("agreement_ratio")
        if agreement is not None:
            score = score * 0.55 + float(agreement) * 100.0 * 0.45
            if float(agreement) < 0.72:
                risks.append("transcript_audio_disagreement")
        if transcript_alignment.get("unmapped_speakers"):
            score -= 8.0
            risks.append("unmapped_transcript_speakers")
    score = max(0.0, min(100.0, score))
    if score >= 82:
        confidence = "high"
    elif score >= 64:
        confidence = "medium"
    else:
        confidence = "low"
    pacing_risks = {"too_few_switches", "shots_too_long", "suppression_heavy", "gain_imbalance_review", "dynamic_floor_gain_sensitive"}
    if confidence == "high" and pacing_risks.intersection(risks):
        confidence = "medium"
    return {
        "score": round(score, 3),
        "confidence": confidence,
        "risks": sorted(set(risks)),
    }


def _inspect_samples(plan: dict[str, Any], transcript_alignment: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    for segment in list(plan.get("unresolved_segments") or [])[:4]:
        samples.append(
            {
                "start_ms": int(segment.get("start_ms") or 0),
                "end_ms": int(segment.get("end_ms") or 0),
                "reason": "unresolved_audio_target",
                "audio_source_ids": list(segment.get("audio_source_ids") or []),
                "candidate_angles": list(segment.get("candidate_angles") or []),
            }
        )
    for event in list(plan.get("suppressed_audio_segments") or [])[:4]:
        samples.append(
            {
                "start_ms": int(event.get("start_ms") or 0),
                "end_ms": int(event.get("end_ms") or 0),
                "reason": "short_audio_event_suppressed",
                "audio_source_ids": list(event.get("audio_source_ids") or []),
                "candidate_angles": list(event.get("candidate_angles") or []),
            }
        )
    if transcript_alignment:
        for mismatch in list(transcript_alignment.get("sample_mismatches") or [])[:4]:
            samples.append(
                {
                    "start_ms": int(mismatch.get("start_ms") or 0),
                    "end_ms": int(mismatch.get("end_ms") or 0),
                    "reason": "transcript_audio_disagreement",
                    "speaker_id": mismatch.get("speaker_id"),
                    "expected_angle": mismatch.get("expected_angle"),
                    "actual_angle": mismatch.get("actual_angle"),
                    "text": mismatch.get("text"),
                }
            )
    return samples[:10]


def calibrate_audio_activity(
    *,
    audio_sources: list[dict[str, Any]],
    audio_angle_map: dict[str, str],
    audio_targets: dict[str, dict[str, Any]] | None,
    audio_sync: dict[str, Any] | None,
    overlap: dict[str, Any] | None,
    angle_map: dict[str, str],
    reference_audio_by_angle: dict[str, str] | None = None,
    max_timeline_ms: int | None = None,
    fps: float = 24.0,
    style: str = "balanced",
    transcript_path: str | None = None,
    transcript_speaker_map: dict[str, str] | None = None,
    max_ranked_candidates: int = 8,
) -> dict[str, Any]:
    normalized_angle_map = _normalize_audio_angle_map(audio_angle_map)
    normalized_targets = _normalize_audio_targets(audio_targets)
    normalized_sources_base = _normalize_audio_sources(audio_sources)
    _validate_known_angles(audio_angle_map=normalized_angle_map, audio_targets=normalized_targets, angle_map=angle_map)
    calibration_offsets, calibration_details = _resolve_audio_offsets(
        audio_sources=normalized_sources_base,
        audio_sync=dict(audio_sync or {"mode": "prealigned"}),
        reference_audio_by_angle=dict(reference_audio_by_angle or angle_map),
        fps=float(fps or 24.0),
    )
    cached_sync = {"mode": "offsets", "offsets": calibration_offsets}
    normalized_style = str(style or "balanced").strip().lower()
    window_values = [100, 250] if normalized_style == "reactive" else [250, 500]
    per_source_by_window: dict[int, dict[str, dict[str, Any]]] = {}
    normalized_sources_by_window: dict[int, list[dict[str, Any]]] = {}
    for window_ms in window_values:
        normalized_sources, per_source = _prepare_audio_activity_sources(
            audio_sources=normalized_sources_base,
            audio_sync=cached_sync,
            reference_audio_by_angle=reference_audio_by_angle or angle_map,
            fps=fps,
            window_ms=window_ms,
            offset_details=calibration_details,
        )
        normalized_sources_by_window[window_ms] = normalized_sources
        per_source_by_window[window_ms] = per_source
    grid = _calibration_grid(style=style, per_source_by_window=per_source_by_window)
    overlap_candidates = _calibration_overlap_candidates(overlap)
    if not normalized_targets and normalized_angle_map and max_timeline_ms is not None and int(max_timeline_ms) >= 120000:
        overlap_angle = str(dict(overlap or {}).get("angle") or "").strip()
        if overlap_angle:
            overlap_candidates = [{"policy": "dominant", "angle": overlap_angle}]
    ranked: list[dict[str, Any]] = []
    transcript_map = dict(transcript_speaker_map or {})
    candidate_index = 0
    v2_level_cache: dict[tuple[str, int, int], tuple[float, int, list[Any]]] = {}
    all_sources_have_direct_angles = all(str(source["id"]) in normalized_angle_map for source in normalized_sources_base)
    for overlap_index, candidate_overlap in enumerate(overlap_candidates, start=1):
        for settings in grid:
            candidate_index += 1
            window_ms = int(settings["analysis_window_ms"])
            if int(settings["switch_delay_ms"]) > 0 and not normalized_targets and normalized_angle_map and all_sources_have_direct_angles:
                plan = _build_audio_activity_plan_v2_from_precomputed(
                    normalized_sources=normalized_sources_by_window[window_ms],
                    normalized_angle_map=normalized_angle_map,
                    per_source=per_source_by_window[window_ms],
                    switching=settings,
                    overlap=candidate_overlap,
                    angle_map=angle_map,
                    max_timeline_ms=max_timeline_ms,
                    fps=fps,
                    level_cache=v2_level_cache,
                )
            else:
                plan = _build_audio_activity_plan_from_precomputed(
                    normalized_sources=normalized_sources_by_window[window_ms],
                    normalized_angle_map=normalized_angle_map,
                    normalized_targets=normalized_targets,
                    per_source=per_source_by_window[window_ms],
                    switching=settings,
                    overlap=candidate_overlap,
                    angle_map=angle_map,
                    max_timeline_ms=max_timeline_ms,
                    fps=fps,
                )
            transcript_alignment = _transcript_alignment_metrics(
                plan=plan,
                transcript_path=transcript_path,
                transcript_speaker_map=transcript_map,
                audio_angle_map=normalized_angle_map,
                audio_targets=normalized_targets,
            )
            score = _score_candidate(
                plan=plan,
                transcript_alignment=transcript_alignment,
                style=style,
                overlap=candidate_overlap,
            )
            ranked.append(
                {
                    "rank": 0,
                    "candidate_id": f"candidate_{candidate_index:04d}",
                    "settings": settings,
                    "overlap": candidate_overlap,
                    "score": score["score"],
                    "confidence": score["confidence"],
                    "risks": score["risks"],
                    "metrics": plan.get("metrics") or {},
                    "transcript_alignment": transcript_alignment,
                    "inspect_samples": _inspect_samples(plan, transcript_alignment),
                }
            )
    ranked.sort(key=lambda item: (-float(item["score"]), str(item["candidate_id"])))
    for rank, item in enumerate(ranked, start=1):
        item["rank"] = rank
    recommendation = ranked[0] if ranked else None
    next_action = "use_recommended_settings" if recommendation and recommendation.get("confidence") != "low" else "transcript_assisted_calibration_recommended"
    return {
        "kind": "audio_activity_calibration_v1",
        "style": str(style or "balanced"),
        "candidate_count": len(ranked),
        "recommendation": recommendation,
        "ranked_candidates": ranked[: max(1, int(max_ranked_candidates))],
        "diagnostics": {
            "mode": "transcript_assisted" if transcript_path else "audio_only",
            "next_best_action": next_action,
            "window_ms_values": window_values,
            "overlap_candidates": overlap_candidates,
            "audio_sources": [
                {
                    "id": source["id"],
                    "path": source["path"],
                    "duration_seconds": source["duration_seconds"],
                    "sample_rate": source["sample_rate"],
                    "noise_floor_db": _round_db(float(source["noise_floor_db"])),
                    "offset_frames": source["offset_frames"],
                    "offset_ms": source["offset_ms"],
                    "offset_seconds": round(float(source.get("offset_seconds") or float(source["offset_ms"]) / 1000.0), 6),
                    "subframe_residual_ms": round(float(source.get("subframe_residual_ms") or 0.0), 3),
                    "drift_ppm": round(float(source.get("drift_ppm") or 0.0), 3),
                    "drift_span_ms": round(float(source.get("drift_span_ms") or 0.0), 3),
                    "sync_confidence": source.get("sync_confidence"),
                    "sync_method": source.get("sync_method"),
                    "level_stats": source.get("level_stats"),
                }
                for source in per_source_by_window[window_values[0]].values()
            ],
            "transcript_used": bool(transcript_path),
            "transcript_speaker_map": transcript_map,
        },
    }


__all__ = (
    '_unique_numbers',
    '_activity_floor_candidates',
    '_calibration_grid',
    '_calibration_overlap_candidates',
    '_style_targets',
    '_segment_angle_at',
    '_transcript_alignment_metrics',
    '_score_candidate',
    '_inspect_samples',
    'calibrate_audio_activity',
)
