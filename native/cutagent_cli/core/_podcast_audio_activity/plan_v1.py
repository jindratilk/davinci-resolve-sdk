"""Plan V1 helpers for podcast audio activity planning."""

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


def _build_audio_activity_plan_from_precomputed(
    *,
    normalized_sources: list[dict[str, Any]],
    normalized_angle_map: dict[str, str],
    normalized_targets: dict[str, dict[str, Any]],
    per_source: dict[str, dict[str, Any]],
    switching: dict[str, Any],
    overlap: dict[str, Any] | None,
    angle_map: dict[str, str],
    max_timeline_ms: int | None,
    fps: float,
) -> dict[str, Any]:
    settings = normalize_switching_settings(switching)
    overlap_settings = dict(overlap or {})
    if overlap_settings.get("angle") and str(overlap_settings["angle"]) not in set(angle_map.keys()):
        raise ValidationError(
            "overlap.angle must be one of the multicam angles.",
            details={"overlap_angle": overlap_settings["angle"], "known_angles": sorted(angle_map.keys())},
        )

    window_ms = int(settings["analysis_window_ms"])
    max_timeline_end_ms = 0
    for source in per_source.values():
        for sample in source["samples"]:
            max_timeline_end_ms = max(
                max_timeline_end_ms,
                int(sample.end_ms) + int(source["offset_ms"]),
            )
    if max_timeline_ms is not None:
        max_timeline_end_ms = min(max_timeline_end_ms, max(0, int(max_timeline_ms)))

    raw_windows: list[dict[str, Any]] = []
    previous_target: dict[str, Any] | None = None
    for window_start_ms in range(0, max(0, max_timeline_end_ms), window_ms):
        window_end_ms = min(max_timeline_end_ms, window_start_ms + window_ms)
        if window_end_ms <= window_start_ms:
            continue
        active: list[dict[str, Any]] = []
        for source in per_source.values():
            samples = source["samples"]
            midpoint_ms = window_start_ms + ((window_end_ms - window_start_ms) / 2.0)
            source_midpoint_ms = midpoint_ms - int(source["offset_ms"])
            if source_midpoint_ms < 0:
                continue
            window_index = int(source_midpoint_ms // window_ms)
            if window_index >= len(samples):
                continue
            sample = samples[window_index]
            relative_db = float(sample.rms_db) - float(source["noise_floor_db"])
            if sample.rms_db > float(settings["activity_floor_db"]) and relative_db >= float(settings["activity_margin_db"]):
                active.append(
                    {
                        "id": source["id"],
                        "path": source["path"],
                        "rms_db": sample.rms_db,
                        "relative_db": relative_db,
                        "noise_floor_db": source["noise_floor_db"],
                    }
                )
        target = _choose_window_target(
            active=active,
            previous_target=previous_target,
            audio_angle_map=normalized_angle_map,
            audio_targets=normalized_targets,
            overlap=overlap_settings,
            activity_floor_db=float(settings["activity_floor_db"]),
            activity_margin_db=float(settings["activity_margin_db"]),
            dominance_margin_db=float(settings["dominance_margin_db"]),
        )
        if target.get("angle"):
            previous_target = target
        raw_windows.append(
            {
                "start_ms": window_start_ms,
                "end_ms": window_end_ms,
                "sources": active,
                **target,
            }
        )

    state_windows = _apply_switch_state_machine(
        raw_windows,
        switch_delay_ms=int(settings["switch_delay_ms"]),
        max_silence_hold_ms=int(settings["max_silence_hold_ms"]),
    )
    merged = _merge_adjacent_windows(state_windows)
    segments = _stabilize_segments(
        merged,
        min_switch_ms=int(settings["min_switch_ms"]),
        switch_delay_ms=int(settings["switch_delay_ms"]),
        max_silence_hold_ms=int(settings["max_silence_hold_ms"]),
    )
    resolved_segments = [segment for segment in segments if segment.get("angle")]
    unresolved_segments = [
        segment
        for segment in segments
        if not segment.get("angle") and segment.get("target_kind") != "silence"
    ]
    suppressed_audio_segments = [
        event
        for segment in segments
        for event in list(segment.get("suppressed_audio_events") or [])
    ]
    suppressed_audio_segments.extend(
        {
            "start_ms": int(segment["start_ms"]),
            "end_ms": int(segment["end_ms"]),
            **dict(segment["suppressed_original"]),
        }
        for segment in segments
        if segment.get("suppressed_original")
    )
    metrics = _segment_metrics(
        segments=segments,
        unresolved_segments=unresolved_segments,
        raw_windows=raw_windows,
        total_ms=max_timeline_end_ms,
    )
    return {
        "kind": "audio_activity_v1",
        "segments": resolved_segments,
        "unresolved_segments": unresolved_segments,
        "suppressed_audio_segments": suppressed_audio_segments,
        "raw_window_count": len(raw_windows),
        "switching": settings,
        "overlap": overlap_settings,
        "max_timeline_ms": int(max_timeline_ms) if max_timeline_ms is not None else None,
        "audio_sources": [
            {
                "id": source["id"],
                "path": per_source[source["id"]]["path"],
                "original_path": per_source[source["id"]].get("original_path"),
                "duration_seconds": per_source[source["id"]]["duration_seconds"],
                "noise_floor_db": per_source[source["id"]]["noise_floor_db"],
                "offset_frames": per_source[source["id"]]["offset_frames"],
                "offset_ms": per_source[source["id"]]["offset_ms"],
                "offset_seconds": round(float(per_source[source["id"]]["offset_seconds"]), 6),
                "subframe_residual_ms": round(float(per_source[source["id"]].get("subframe_residual_ms") or 0.0), 3),
                "audio_conform": per_source[source["id"]].get("audio_conform"),
                "drift_ppm": round(float(per_source[source["id"]].get("drift_ppm") or 0.0), 3),
                "drift_span_ms": round(float(per_source[source["id"]].get("drift_span_ms") or 0.0), 3),
                "sync_confidence": per_source[source["id"]].get("sync_confidence"),
                "sync_method": per_source[source["id"]].get("sync_method"),
                "level_stats": per_source[source["id"]].get("level_stats"),
            }
            for source in normalized_sources
        ],
        "audio_angle_map": normalized_angle_map,
        "audio_targets": normalized_targets,
        "metrics": {
            **metrics,
            "suppressed_short_switch_count": len(suppressed_audio_segments)
            + sum(1 for segment in segments if segment.get("reason") == "suppressed_short_audio_switch"),
        },
    }


__all__ = (
    '_build_audio_activity_plan_from_precomputed',
)
