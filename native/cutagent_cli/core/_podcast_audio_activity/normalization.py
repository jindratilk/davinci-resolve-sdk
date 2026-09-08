"""Normalization helpers for podcast audio activity planning."""

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
from .. import audio_conform, waveform_sync
from .._podcast_multicam.audio_activity_v2 import io as audio_activity_v2_io
from .._podcast_multicam.audio_activity_v2 import plan as audio_activity_v2_plan
from .._podcast_multicam.transcript import normalize_scribe_v2_transcript
from .common import *
from .parsing import *
from .levels import *


def normalize_switching_settings(raw: dict[str, Any] | None) -> dict[str, Any]:
    settings = dict(raw or {})
    missing = [key for key in REQUIRED_SWITCHING_KEYS if settings.get(key) is None]
    if missing:
        raise ValidationError(
            "Audio activity planning requires explicit switching parameters.",
            details={
                "missing": missing,
                "recommended_starting_points": {
                    "analysis_window_ms": 250,
                    "activity_margin_db": 6.0,
                    "activity_floor_db": -50.0,
                    "dominance_margin_db": 4.0,
                    "min_switch_ms": 1200,
                    "switch_delay_ms": 500,
                    "max_silence_hold_ms": 8000,
                },
            },
        )
    normalized = {
        "analysis_window_ms": int(_finite_number(settings["analysis_window_ms"], key="analysis_window_ms")),
        "activity_floor_db": _finite_number(settings["activity_floor_db"], key="activity_floor_db"),
        "activity_margin_db": _finite_number(settings["activity_margin_db"], key="activity_margin_db"),
        "dominance_margin_db": _finite_number(settings["dominance_margin_db"], key="dominance_margin_db"),
        "min_switch_ms": int(_finite_number(settings["min_switch_ms"], key="min_switch_ms")),
        "switch_delay_ms": int(_finite_number(settings["switch_delay_ms"], key="switch_delay_ms")),
        "max_silence_hold_ms": int(_finite_number(settings.get("max_silence_hold_ms", 0), key="max_silence_hold_ms")),
    }
    if normalized["analysis_window_ms"] <= 0:
        raise ValidationError("analysis_window_ms must be greater than zero.", details={"analysis_window_ms": normalized["analysis_window_ms"]})
    for key in ("activity_margin_db", "dominance_margin_db"):
        if normalized[key] < 0:
            raise ValidationError(f"{key} must be non-negative.", details={key: normalized[key]})
    for key in ("min_switch_ms", "switch_delay_ms", "max_silence_hold_ms"):
        if normalized[key] < 0:
            raise ValidationError(f"{key} must be non-negative.", details={key: normalized[key]})
    return normalized


def _normalize_audio_sources(raw_sources: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_sources, list) or not raw_sources:
        raise ValidationError(
            "audio_activity_v1 requires audio_sources[].",
            details={"audio_sources": raw_sources},
        )
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_sources):
        if not isinstance(raw, dict):
            raise ValidationError("audio_sources entries must be objects.", details={"index": index, "entry": raw})
        source_id = str(raw.get("id") or raw.get("source_id") or "").strip()
        path = str(raw.get("path") or raw.get("audio_path") or raw.get("file") or "").strip()
        if not source_id or not path:
            raise ValidationError(
                "Each audio source must include id and path.",
                details={"index": index, "entry": raw},
            )
        if source_id in seen:
            raise ValidationError("Audio source ids must be unique.", details={"audio_source_id": source_id})
        seen.add(source_id)
        normalized.append({"id": source_id, "path": path})
    return normalized


def _normalize_audio_angle_map(raw: Any) -> dict[str, str]:
    if raw is None:
        return {}
    if isinstance(raw, str):
        return parse_audio_angle_map(raw)
    if not isinstance(raw, dict):
        raise ValidationError("audio_angle_map must be an object or id=angle string.", details={"audio_angle_map": raw})
    return {str(key): str(value) for key, value in raw.items()}


def _normalize_audio_targets(raw: Any) -> dict[str, dict[str, Any]]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValidationError("audio_targets must be an object.", details={"audio_targets": raw})
    targets: dict[str, dict[str, Any]] = {}
    for source_id, value in raw.items():
        if isinstance(value, list):
            angles = [str(item).strip() for item in value if str(item).strip()]
            selection = "default" if len(angles) == 1 else "agent_decides"
        elif isinstance(value, str):
            angles = [str(value).strip()] if str(value).strip() else []
            selection = "default"
        elif isinstance(value, dict):
            angles = [str(item).strip() for item in list(value.get("angles") or []) if str(item).strip()]
            selection = str(value.get("selection") or ("default" if len(angles) == 1 else "agent_decides")).strip()
        else:
            raise ValidationError("audio_targets values must be objects, arrays, or strings.", details={"source_id": source_id, "value": value})
        if not angles:
            raise ValidationError("audio_targets entries require at least one angle.", details={"source_id": source_id})
        targets[str(source_id)] = {"angles": angles, "selection": selection}
    return targets


def _validate_known_angles(*, audio_angle_map: dict[str, str], audio_targets: dict[str, dict[str, Any]], angle_map: dict[str, str]) -> None:
    known = set(angle_map.keys())
    unknown_map = {source_id: angle for source_id, angle in audio_angle_map.items() if angle not in known}
    unknown_targets = {
        source_id: [angle for angle in target.get("angles", []) if angle not in known]
        for source_id, target in audio_targets.items()
        if any(angle not in known for angle in target.get("angles", []))
    }
    if unknown_map or unknown_targets:
        raise ValidationError(
            "Audio activity target references unknown multicam angles.",
            details={
                "unknown_audio_angle_map": unknown_map,
                "unknown_audio_targets": unknown_targets,
                "known_angles": sorted(known),
            },
        )


def _resolve_source_angle(source_id: str, *, audio_angle_map: dict[str, str], audio_targets: dict[str, dict[str, Any]]) -> tuple[str | None, list[str], str]:
    mapped = str(audio_angle_map.get(source_id) or "").strip()
    if mapped:
        return mapped, [mapped], "audio_angle_map"
    target = audio_targets.get(source_id) or {}
    angles = [str(item).strip() for item in list(target.get("angles") or []) if str(item).strip()]
    selection = str(target.get("selection") or "").strip()
    if len(angles) == 1 and selection in {"", "default", "first"}:
        return angles[0], angles, "audio_targets.default"
    if angles:
        return None, angles, selection or "agent_decides"
    return None, [], "unmapped"


def _source_noise_floor(samples: list[AudioWindowSample]) -> float:
    levels = [sample.rms_db for sample in samples]
    if not levels:
        return -120.0
    try:
        return statistics.median(sorted(levels)[: max(1, len(levels) // 4)])
    except statistics.StatisticsError:
        return -120.0


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(float(value) for value in values)
    if len(ordered) == 1:
        return ordered[0]
    rank = max(0.0, min(100.0, float(percentile))) / 100.0 * (len(ordered) - 1)
    lower = int(math.floor(rank))
    upper = int(math.ceil(rank))
    if lower == upper:
        return ordered[lower]
    weight = rank - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def _round_db(value: float) -> float:
    return round(float(value) * 2.0) / 2.0


def _source_level_stats(samples: list[AudioWindowSample], *, noise_floor_db: float) -> dict[str, Any]:
    levels = [float(sample.rms_db) for sample in samples]
    relatives = [float(sample.rms_db) - float(noise_floor_db) for sample in samples]
    percentiles = {
        str(percentile): (_round_db(value) if value is not None else None)
        for percentile in (5, 10, 25, 50, 75, 90, 95)
        for value in [_percentile(levels, percentile)]
    }
    relative_percentiles = {
        str(percentile): (_round_db(value) if value is not None else None)
        for percentile in (5, 10, 25, 50, 75, 90, 95)
        for value in [_percentile(relatives, percentile)]
    }
    return {
        "window_count": len(samples),
        "noise_floor_db": _round_db(noise_floor_db),
        "rms_db_percentiles": percentiles,
        "relative_db_percentiles": relative_percentiles,
    }


def _resolve_audio_offsets(
    *,
    audio_sources: list[dict[str, Any]],
    audio_sync: dict[str, Any],
    reference_audio_by_angle: dict[str, str],
    fps: float,
) -> tuple[dict[str, int], dict[str, dict[str, Any]]]:
    """Resolve per-source frame offsets plus (waveform mode) the rich sync details.

    The second mapping carries the v2 estimator result per source id —
    fractional offset, drift, confidence — and is empty for prealigned/manual
    offset modes.
    """
    mode = str(audio_sync.get("mode") or "prealigned").strip()
    if mode == "prealigned":
        return {source["id"]: 0 for source in audio_sources}, {}
    if mode in {"offsets", "offsets-json"}:
        offsets = audio_sync.get("offsets") or {}
        if not isinstance(offsets, dict):
            raise ValidationError("audio_sync.offsets must be an object.", details={"audio_sync": audio_sync})
        offsets_seconds = audio_sync.get("offsets_seconds") or {}
        if offsets_seconds is not None and not isinstance(offsets_seconds, dict):
            raise ValidationError("audio_sync.offsets_seconds must be an object.", details={"audio_sync": audio_sync})
        effective_fps = float(fps or 24.0)
        normalized_offsets: dict[str, int] = {}
        details: dict[str, dict[str, Any]] = {}
        for source in audio_sources:
            source_id = str(source["id"])
            raw_frame_offset = int(offsets.get(source_id, 0) or 0)
            if isinstance(offsets_seconds, dict) and source_id in offsets_seconds:
                offset_seconds = float(offsets_seconds[source_id])
                offset_frames = int(round(offset_seconds * effective_fps))
                normalized_offsets[source_id] = offset_frames
                details[source_id] = {
                    "offset_frames_int": offset_frames,
                    "offset_seconds": offset_seconds,
                    "subframe_residual_ms": (offset_seconds - offset_frames / effective_fps) * 1000.0,
                    "drift_ppm": 0.0,
                    "drift_span_ms": 0.0,
                    "midpoint_seconds": 0.0,
                    "confidence": {
                        "source": "audio_offsets_json",
                        "source_fps": audio_sync.get("fps"),
                        "source_offset_frames": raw_frame_offset,
                    },
                    "warnings": [],
                    "method": "offsets_json_schema_v2",
                }
            else:
                normalized_offsets[source_id] = raw_frame_offset
        return normalized_offsets, details
    if mode == "waveform":
        reference_path = str(audio_sync.get("reference_audio_path") or "").strip()
        reference_angle = str(audio_sync.get("reference_angle") or "").strip()
        source_references = audio_sync.get("source_reference_paths") or {}
        if source_references is not None and not isinstance(source_references, dict):
            raise ValidationError("audio_sync.source_reference_paths must be an object.", details={"audio_sync": audio_sync})
        if not reference_path and reference_angle:
            reference_path = str(reference_audio_by_angle.get(reference_angle) or "").strip()
        if not reference_path and not source_references:
            raise ValidationError(
                "audio_sync mode waveform requires reference_audio_path, reference_angle with a source path, or source_reference_paths.",
                details={"audio_sync": audio_sync},
            )
        offsets: dict[str, int] = {}
        details: dict[str, dict[str, Any]] = {}
        for source in audio_sources:
            source_reference_path = str(dict(source_references or {}).get(source["id"]) or reference_path).strip()
            if not source_reference_path:
                raise ValidationError(
                    "audio_sync mode waveform is missing a reference for an audio source.",
                    details={"audio_source_id": source["id"], "audio_sync": audio_sync},
                )
            result = waveform_sync.estimate_offset(source_reference_path, str(source["path"]), fps)
            offsets[source["id"]] = int(result["offset_frames_int"])
            details[source["id"]] = result
        offsets, details = _normalize_waveform_same_recorder_offsets(
            audio_sources=audio_sources,
            offsets=offsets,
            details=details,
            fps=float(fps or 24.0),
        )
        return offsets, details
    raise ValidationError(
        "Unsupported audio activity sync mode.",
        details={"mode": mode, "supported_modes": ["prealigned", "waveform", "offsets-json"]},
    )


def _normalize_waveform_same_recorder_offsets(
    *,
    audio_sources: list[dict[str, Any]],
    offsets: dict[str, int],
    details: dict[str, dict[str, Any]],
    fps: float,
) -> tuple[dict[str, int], dict[str, dict[str, Any]]]:
    if len(offsets) < 2:
        return offsets, details
    values = [int(value) for value in offsets.values()]
    if max(values) - min(values) <= 1:
        common_offset = max(values, key=lambda value: abs(int(value)))
        normalized_offsets = {source_id: int(common_offset) for source_id in offsets}
        normalized_details = {
            source_id: _normalized_waveform_detail(
                detail=dict(details.get(source_id) or {}),
                common_offset=int(common_offset),
                fps=float(fps or 24.0),
                reason="same_recorder_offsets_within_one_frame",
            )
            for source_id in offsets
        }
        return normalized_offsets, normalized_details

    if not _audio_sources_are_mutually_aligned(audio_sources, fps=float(fps or 24.0)):
        return offsets, details

    raise ValidationError(
        "Waveform sync measured different source-specific mic offsets, but the microphone files appear mutually aligned.",
        details={
            "offsets": dict(offsets),
            "hint": (
                "Do not apply different source offsets to same-recorder microphones; "
                "first prove the camera angles are synced, use one shared waveform reference, "
                "or provide verified offsets-json."
            ),
        },
    )


def _normalized_waveform_detail(
    *,
    detail: dict[str, Any],
    common_offset: int,
    fps: float,
    reason: str,
) -> dict[str, Any]:
    normalized = dict(detail)
    effective_fps = float(fps or 24.0)
    normalized["offset_frames_int"] = int(common_offset)
    normalized["offset_seconds"] = float(common_offset) / effective_fps
    normalized["subframe_residual_ms"] = 0.0
    warnings = list(normalized.get("warnings") or [])
    if reason not in warnings:
        warnings.append(reason)
    normalized["warnings"] = warnings
    normalized["same_recorder_offset_normalized"] = True
    return normalized


def _audio_sources_are_mutually_aligned(audio_sources: list[dict[str, Any]], *, fps: float) -> bool:
    if len(audio_sources) < 2:
        return False
    first = audio_sources[0]
    first_path = str(first.get("path") or "").strip()
    if not first_path:
        return False
    for source in audio_sources[1:]:
        source_path = str(source.get("path") or "").strip()
        if not source_path:
            return False
        try:
            result = waveform_sync.estimate_offset(first_path, source_path, fps)
        except Exception:
            return False
        if abs(int(result.get("offset_frames_int") or 0)) > 1:
            return False
    return True


def _prepare_audio_activity_sources(
    *,
    audio_sources: list[dict[str, Any]],
    audio_sync: dict[str, Any] | None,
    reference_audio_by_angle: dict[str, str] | None,
    fps: float,
    window_ms: int,
    offset_details: dict[str, dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    normalized_sources = _normalize_audio_sources(audio_sources)
    offsets, resolved_details = _resolve_audio_offsets(
        audio_sources=normalized_sources,
        audio_sync=dict(audio_sync or {"mode": "prealigned"}),
        reference_audio_by_angle=dict(reference_audio_by_angle or {}),
        fps=float(fps or 24.0),
    )
    details = dict(resolved_details)
    for source_id, detail in dict(offset_details or {}).items():
        details.setdefault(source_id, detail)
    per_source: dict[str, dict[str, Any]] = {}
    effective_fps = float(fps or 24.0)
    sync_settings = dict(audio_sync or {})
    conform_setting = str(sync_settings.get("subframe_conform", "auto")).strip().lower()
    conform_enabled = conform_setting not in {"0", "false", "no", "off", "none", "disabled"}
    derived_media_dir = sync_settings.get("derived_media_dir")
    try:
        max_derived_media_gb = float(sync_settings.get("max_derived_media_gb") or audio_conform.DEFAULT_RUN_BUDGET_GB)
    except (TypeError, ValueError):
        max_derived_media_gb = audio_conform.DEFAULT_RUN_BUDGET_GB
    conform_budget = audio_conform.ConformRunBudget(max_derived_media_gb)
    for source in normalized_sources:
        source_path = str(source["path"])
        offset_frames = int(offsets.get(source["id"], 0))
        detail = details.get(source["id"]) or {}
        offset_seconds = (
            float(detail["offset_seconds"])
            if detail.get("offset_seconds") is not None
            else offset_frames / effective_fps
        )
        residual_seconds = offset_seconds - offset_frames / effective_fps
        conform_result: dict[str, Any] | None = None
        if conform_enabled and abs(residual_seconds) * 1000.0 >= audio_conform.RESIDUAL_SKIP_MS:
            try:
                conform_result = audio_conform.conform_audio(
                    source_path,
                    residual_seconds=residual_seconds,
                    drift_ppm=0.0,
                    drift_span_ms=0.0,
                    derived_media_dir=str(derived_media_dir) if derived_media_dir else None,
                    run_budget=conform_budget,
                )
            except Exception as exc:
                conform_result = {
                    "conformed": False,
                    "path": source_path,
                    "reason": "conform_error",
                    "error": str(exc),
                }
            if conform_result.get("conformed") and conform_result.get("path"):
                source_path = str(conform_result["path"])
                offset_seconds = offset_frames / effective_fps
                residual_seconds = 0.0
        duration, sample_rate, samples = _read_audio_window_levels(source_path, window_ms=int(window_ms))
        noise_floor = _source_noise_floor(samples)
        per_source[source["id"]] = {
            "id": source["id"],
            "path": source_path,
            "original_path": source["path"] if source_path != str(source["path"]) else None,
            "duration_seconds": duration,
            "sample_rate": sample_rate,
            "samples": samples,
            "noise_floor_db": noise_floor,
            "offset_frames": offset_frames,
            # Fractional milliseconds: activity windows and slice translation
            # use the true measured offset, not the frame-quantized one.
            "offset_ms": offset_seconds * 1000.0,
            "offset_seconds": offset_seconds,
            "subframe_residual_ms": residual_seconds * 1000.0,
            "audio_conform": conform_result,
            "drift_ppm": float(detail.get("drift_ppm") or 0.0),
            "drift_span_ms": float(detail.get("drift_span_ms") or 0.0),
            "drift_midpoint_seconds": float(detail.get("midpoint_seconds") or 0.0),
            "sync_confidence": detail.get("confidence"),
            "sync_warnings": detail.get("warnings"),
            "sync_method": detail.get("method"),
            "fps": effective_fps,
            "level_stats": _source_level_stats(samples, noise_floor_db=noise_floor),
        }
    return normalized_sources, per_source


__all__ = (
    'normalize_switching_settings',
    '_normalize_audio_sources',
    '_normalize_audio_angle_map',
    '_normalize_audio_targets',
    '_validate_known_angles',
    '_resolve_source_angle',
    '_source_noise_floor',
    '_percentile',
    '_round_db',
    '_source_level_stats',
    '_resolve_audio_offsets',
    '_prepare_audio_activity_sources',
)
