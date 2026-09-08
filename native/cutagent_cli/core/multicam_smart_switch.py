"""Persistent deterministic equivalent of DaVinci Resolve Multicam SmartSwitch settings."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from ..errors import ValidationError

_WIDE_KEYWORDS = (
    "wide",
    "master",
    "two shot",
    "two-shot",
    "2 shot",
    "2-shot",
    "group",
    "establishing",
    "full shot",
)
_FREQUENCY_INTERVAL_MS = {"off": None, "low": 120_000, "medium": 60_000, "high": 30_000}


def _automatic_wide_angle(
    *,
    angle_map: dict[str, str],
    angle_order: list[str],
    angle_names: dict[str, str],
    sources: list[dict[str, Any]],
    audio_angle_map: dict[str, str],
) -> dict[str, Any]:
    direct_audio_angles = {str(value) for value in audio_angle_map.values() if str(value)}
    source_by_angle: dict[str, list[dict[str, Any]]] = {}
    for source in sources:
        source_by_angle.setdefault(str(source.get("angle") or ""), []).append(source)
    scored: list[dict[str, Any]] = []
    focal_lengths: dict[str, float] = {}
    for angle in angle_order:
        for source in source_by_angle.get(angle, []):
            value = source.get("focal_length_mm") or source.get("focal_length")
            try:
                if value not in (None, ""):
                    focal_lengths[angle] = min(float(value), focal_lengths.get(angle, float("inf")))
            except (TypeError, ValueError):
                pass
    shortest_focal = min(focal_lengths.values()) if focal_lengths else None
    for order_index, angle in enumerate(angle_order):
        evidence: list[str] = []
        search_text = " ".join(
            [
                angle,
                angle_names.get(angle, ""),
                angle_map.get(angle, ""),
                *[
                    str(source.get(key) or "")
                    for source in source_by_angle.get(angle, [])
                    for key in ("label", "role", "shot_type", "camera_position")
                ],
            ]
        ).casefold()
        keyword_hits = [keyword for keyword in _WIDE_KEYWORDS if keyword in search_text]
        score = float(len(keyword_hits) * 100)
        if keyword_hits:
            evidence.append("wide_keywords:" + ",".join(keyword_hits))
        if angle not in direct_audio_angles:
            score += 25.0
            evidence.append("not_directly_mapped_to_isolated_speaker_audio")
        if shortest_focal is not None and angle in focal_lengths:
            focal = focal_lengths[angle]
            score += max(0.0, 40.0 - (focal - shortest_focal))
            evidence.append(f"focal_length_mm:{focal:g}")
        scored.append(
            {
                "angle": angle,
                "score": round(score, 3),
                "order_index": order_index,
                "evidence": evidence,
            }
        )
    if not scored:
        raise ValidationError("SmartSwitch automatic wide-angle detection requires at least one angle.")
    scored.sort(key=lambda row: (-float(row["score"]), int(row["order_index"])))
    winner = scored[0]
    runner_score = float(scored[1]["score"]) if len(scored) > 1 else -1.0
    margin = float(winner["score"]) - runner_score
    return {
        "angle": str(winner["angle"]),
        "mode": "automatic",
        "confidence": "high" if float(winner["score"]) >= 100 and margin >= 25 else "medium" if margin > 0 else "low",
        "score_margin": round(margin, 3),
        "candidates": scored,
        "route": "angle/file/shot metadata + isolated-audio mapping heuristic",
    }


def _merge_adjacent(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    for segment in sorted(segments, key=lambda row: (int(row["start_ms"]), int(row["end_ms"]))):
        current = deepcopy(segment)
        if (
            merged
            and int(merged[-1]["end_ms"]) == int(current["start_ms"])
            and str(merged[-1].get("angle") or "") == str(current.get("angle") or "")
            and str(merged[-1].get("target_kind") or "") == str(current.get("target_kind") or "")
        ):
            merged[-1]["end_ms"] = int(current["end_ms"])
            reasons = [part for part in (str(merged[-1].get("reason") or ""), str(current.get("reason") or "")) if part]
            merged[-1]["reason"] = "|".join(dict.fromkeys(reasons))
            continue
        merged.append(current)
    return merged


def _force_interval(
    segments: list[dict[str, Any]],
    *,
    start_ms: int,
    end_ms: int,
    angle: str,
    reason: str,
    minimum_edit_ms: int,
) -> list[dict[str, Any]]:
    forced: list[dict[str, Any]] = []
    for segment in segments:
        segment_start = int(segment["start_ms"])
        segment_end = int(segment["end_ms"])
        overlap_start = max(segment_start, int(start_ms))
        overlap_end = min(segment_end, int(end_ms))
        if overlap_end <= overlap_start:
            forced.append(deepcopy(segment))
            continue
        if 0 < overlap_start - segment_start < minimum_edit_ms:
            overlap_start = segment_start
        if 0 < segment_end - overlap_end < minimum_edit_ms:
            overlap_end = segment_end
        if segment_start < overlap_start:
            before = deepcopy(segment)
            before["end_ms"] = overlap_start
            forced.append(before)
        wide = deepcopy(segment)
        wide.update(
            {
                "start_ms": overlap_start,
                "end_ms": overlap_end,
                "angle": angle,
                "target_id": angle,
                "target_kind": "wide",
                "reason": reason,
                "candidate_angles": [angle],
            }
        )
        forced.append(wide)
        if overlap_end < segment_end:
            after = deepcopy(segment)
            after["start_ms"] = overlap_end
            forced.append(after)
    return _merge_adjacent(forced)


def apply_smart_switch_policy(
    analysis: dict[str, Any],
    *,
    smart_switch: dict[str, Any],
    angle_map: dict[str, str],
    angle_order: list[str],
    angle_names: dict[str, str],
    sources: list[dict[str, Any]],
    audio_angle_map: dict[str, str],
) -> dict[str, Any]:
    settings = dict(smart_switch or {})
    wide_mode = str(settings.get("wide_angle_mode") or "automatic").strip().lower().replace("-", "_")
    if wide_mode not in {"automatic", "manual"}:
        raise ValidationError(
            "SmartSwitch wide_angle_mode must be automatic or manual.",
            details={"wide_angle_mode": wide_mode},
        )
    if wide_mode == "manual":
        wide_angle = str(settings.get("wide_angle") or "").strip()
        if wide_angle not in angle_map:
            raise ValidationError(
                "SmartSwitch manual wide angle must be one of the multicam angles.",
                details={"wide_angle": wide_angle, "known_angles": angle_order},
            )
        wide_detection = {"angle": wide_angle, "mode": "manual", "confidence": "explicit", "candidates": []}
    else:
        wide_detection = _automatic_wide_angle(
            angle_map=angle_map,
            angle_order=angle_order,
            angle_names=angle_names,
            sources=sources,
            audio_angle_map=audio_angle_map,
        )
        wide_angle = str(wide_detection["angle"])
    frequency = str(settings.get("wide_angle_frequency") or "medium").strip().lower()
    if frequency not in _FREQUENCY_INTERVAL_MS:
        raise ValidationError(
            "SmartSwitch wide_angle_frequency must be off, low, medium, or high.",
            details={"wide_angle_frequency": frequency},
        )
    switch_mode = str(settings.get("switch") or "video_only").strip().lower().replace("-", "_")
    if switch_mode not in {"video_only", "video_and_audio"}:
        raise ValidationError(
            "SmartSwitch switch must be video_only or video_and_audio.",
            details={"switch": switch_mode},
        )
    minimum_edit_ms = max(1, int(settings.get("minimum_edit_duration_ms") or (analysis.get("switching") or {}).get("min_switch_ms") or 1200))
    intro_outro_ms = max(minimum_edit_ms, int(settings.get("intro_outro_duration_ms") or minimum_edit_ms))
    segments = [deepcopy(row) for row in list(analysis.get("segments") or []) if int(row.get("end_ms") or 0) > int(row.get("start_ms") or 0)]
    if not segments:
        return {
            **analysis,
            "smart_switch": {
                **settings,
                "wide_angle_detection": wide_detection,
                "switch": switch_mode,
                "use_audio_only_fast_analysis": bool(settings.get("use_audio_only_fast_analysis", False)),
            },
        }
    segments = _merge_adjacent(segments)
    if bool(settings.get("use_wide_angle_for_silence", True)):
        for index, segment in enumerate(segments):
            reason = str(segment.get("reason") or "").casefold()
            if str(segment.get("target_kind") or "") == "silence" or "silence" in reason:
                segments[index] = {
                    **segment,
                    "angle": wide_angle,
                    "target_id": wide_angle,
                    "target_kind": "wide",
                    "candidate_angles": [wide_angle],
                    "reason": "smart_switch_silence_wide",
                }
        segments = _merge_adjacent(segments)
    program_start = min(int(row["start_ms"]) for row in segments)
    program_end = max(int(row["end_ms"]) for row in segments)
    if bool(settings.get("use_wide_angle_for_intro_outro", True)):
        segments = _force_interval(
            segments,
            start_ms=program_start,
            end_ms=min(program_end, program_start + intro_outro_ms),
            angle=wide_angle,
            reason="smart_switch_intro_wide",
            minimum_edit_ms=minimum_edit_ms,
        )
        segments = _force_interval(
            segments,
            start_ms=max(program_start, program_end - intro_outro_ms),
            end_ms=program_end,
            angle=wide_angle,
            reason="smart_switch_outro_wide",
            minimum_edit_ms=minimum_edit_ms,
        )
    interval_ms = _FREQUENCY_INTERVAL_MS[frequency]
    inserted_frequency_shots = 0
    if interval_ms:
        shot_duration_ms = max(minimum_edit_ms, int(settings.get("wide_shot_duration_ms") or 2000))
        cursor_ms = program_start + int(interval_ms)
        while cursor_ms < program_end - intro_outro_ms:
            before_count = sum(1 for row in segments if str(row.get("reason") or "") == "smart_switch_frequency_wide")
            segments = _force_interval(
                segments,
                start_ms=cursor_ms,
                end_ms=min(program_end, cursor_ms + shot_duration_ms),
                angle=wide_angle,
                reason="smart_switch_frequency_wide",
                minimum_edit_ms=minimum_edit_ms,
            )
            after_count = sum(1 for row in segments if "smart_switch_frequency_wide" in str(row.get("reason") or ""))
            inserted_frequency_shots += max(0, after_count - before_count)
            cursor_ms += int(interval_ms)
    output = deepcopy(analysis)
    output["segments"] = _merge_adjacent(segments)
    output["smart_switch"] = {
        "minimum_edit_duration_ms": minimum_edit_ms,
        "edit_change_delay_ms": int(settings.get("edit_change_delay_ms") or (analysis.get("switching") or {}).get("switch_delay_ms") or 0),
        "wide_angle_mode": wide_mode,
        "wide_angle": wide_angle,
        "wide_angle_detection": wide_detection,
        "wide_angle_frequency": frequency,
        "use_wide_angle_for_intro_outro": bool(settings.get("use_wide_angle_for_intro_outro", True)),
        "use_wide_angle_for_silence": bool(settings.get("use_wide_angle_for_silence", True)),
        "switch": switch_mode,
        "use_audio_only_fast_analysis": bool(settings.get("use_audio_only_fast_analysis", False)),
        "analysis_engine": "cutagent_audio_only" if bool(settings.get("use_audio_only_fast_analysis", False)) else "cutagent_audio_plus_angle_metadata",
        "intro_outro_duration_ms": intro_outro_ms,
        "frequency_interval_ms": interval_ms,
        "inserted_frequency_shots": inserted_frequency_shots,
    }
    return output
