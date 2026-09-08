"""Plan V2 helpers for podcast audio activity planning."""

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


def _synced_v2_samples(
    *,
    source: dict[str, Any],
    window_ms: int,
    cached_samples: list[AudioWindowSample] | None = None,
    gain_normalization_db: float = 0.0,
) -> tuple[float, int, list[Any]]:
    offset_ms = int(source.get("offset_ms") or 0)
    if cached_samples is None:
        duration, sample_rate, samples = _read_audio_window_levels(str(source["path"]), window_ms=window_ms)
    else:
        duration = float(source.get("duration_seconds") or 0.0)
        sample_rate = int(source.get("sample_rate") or 48_000)
        samples = cached_samples
    synced: list[Any] = []
    if offset_ms > 0:
        cursor = 0
        while cursor < offset_ms:
            end_ms = min(offset_ms, cursor + window_ms)
            synced.append(
                audio_activity_v2_io.AudioWindowSample(
                    start=float(cursor) / 1000.0,
                    end=float(end_ms) / 1000.0,
                    rms_db=-120.0,
                    active=False,
                )
            )
            cursor = end_ms
    for sample in samples:
        start_ms = int(sample.start_ms) + offset_ms
        end_ms = int(sample.end_ms) + offset_ms
        if end_ms <= 0:
            continue
        start_ms = max(0, start_ms)
        if end_ms <= start_ms:
            continue
        synced.append(
            audio_activity_v2_io.AudioWindowSample(
                start=float(start_ms) / 1000.0,
                end=float(end_ms) / 1000.0,
                rms_db=float(sample.rms_db) + float(gain_normalization_db),
                active=False,
            )
        )
    synced_duration = max((float(sample.end) for sample in synced), default=max(0.0, duration + float(offset_ms) / 1000.0))
    return synced_duration, sample_rate, synced


def _seconds_to_frames(value: Any, *, fps: float) -> int:
    return int(round(float(value or 0.0) * float(fps or 24.0)))


def _frame_range_from_seconds(
    *,
    start_seconds: Any,
    end_seconds: Any,
    fps: float,
    timeline_end_frame: int | None,
) -> tuple[int, int] | None:
    start_frame = _seconds_to_frames(start_seconds, fps=fps)
    end_frame = _seconds_to_frames(end_seconds, fps=fps)
    if timeline_end_frame is not None:
        start_frame = min(start_frame, timeline_end_frame)
        end_frame = min(end_frame, timeline_end_frame)
    if end_frame <= start_frame:
        return None
    return start_frame, end_frame


def _slice_offset_frames(source: dict[str, Any], record_start_frame: int) -> int:
    """Frame offset for one slice, evaluated at the slice's timeline position.

    With measured clock drift, the true offset is time-dependent:
    offset(t) = offset_mid + drift · (t − t_mid). Each slice is independently
    anchored, so evaluating the model per slice compensates drift with pure
    placement math — no media is rewritten. Without drift this reduces to the
    constant frame offset.
    """
    offset_frames = int(source.get("offset_frames") or 0)
    drift_ppm = float(source.get("drift_ppm") or 0.0)
    fps = float(source.get("fps") or 0.0)
    if not drift_ppm or fps <= 0:
        return offset_frames
    offset_mid = float(source.get("offset_seconds") or (offset_frames / fps))
    t_mid = float(source.get("drift_midpoint_seconds") or 0.0)
    t = float(record_start_frame) / fps
    offset_at_t = offset_mid + drift_ppm * 1e-6 * (t - t_mid)
    return int(round(offset_at_t * fps))


def _source_frame_range_for_timeline_range(
    *,
    source_id: str,
    record_start_frame: int,
    record_end_frame: int,
    per_source: dict[str, dict[str, Any]],
) -> tuple[int, int] | None:
    source = per_source.get(str(source_id))
    if not source:
        return None
    offset_frames = _slice_offset_frames(source, int(record_start_frame))
    source_start_frame = int(record_start_frame) - offset_frames
    source_end_frame = int(record_end_frame) - offset_frames
    if source_end_frame <= 0:
        return None
    source_start_frame = max(0, source_start_frame)
    if source_end_frame <= source_start_frame:
        return None
    return source_start_frame, source_end_frame


def _audio_instruction_row(
    *,
    source_id: str,
    mode: str,
    record_start_frame: int,
    record_end_frame: int,
    source_start_frame: int,
    source_end_frame: int,
    reason: str,
    confidence: float,
    per_source: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    source = per_source.get(str(source_id)) or {}
    return {
        "source_id": str(source_id),
        "speaker_id": str(source_id),
        "track_id": str(source_id),
        "source_path": str(source.get("path") or ""),
        "record_start_frame": int(record_start_frame),
        "record_end_frame": int(record_end_frame),
        "source_start_frame": int(source_start_frame),
        "source_end_frame": int(source_end_frame),
        "mode": str(mode or "primary"),
        "confidence": float(confidence or 0.0),
        "reason": str(reason or mode or "audio_activity"),
    }


def _dedupe_audio_overlays(overlays: Iterable[Any]) -> list[dict[str, Any]]:
    seen: set[tuple[str, int, int, str]] = set()
    rows: list[dict[str, Any]] = []
    for raw in overlays:
        if not isinstance(raw, dict):
            continue
        speaker_id = str(raw.get("speaker_id") or "").strip()
        start_ms = int(round(float(raw.get("start") or 0.0) * 1000.0))
        end_ms = int(round(float(raw.get("end") or 0.0) * 1000.0))
        mode = str(raw.get("mode") or "audio_only_interjection")
        key = (speaker_id, start_ms, end_ms, mode)
        if not speaker_id or end_ms <= start_ms or key in seen:
            continue
        seen.add(key)
        rows.append(dict(raw))
    return rows


def _audio_instructions_from_segments(
    *,
    segments: list[dict[str, Any]],
    direct_source_ids: list[str],
    per_source: dict[str, dict[str, Any]],
    fps: float,
    max_timeline_ms: int | None,
) -> list[dict[str, Any]]:
    timeline_end_frame = _seconds_to_frames(float(max_timeline_ms) / 1000.0, fps=fps) if max_timeline_ms is not None else None
    instructions: list[dict[str, Any]] = []
    for segment in segments:
        segment_start_seconds = float(int(segment.get("start_ms") or 0) / 1000.0)
        segment_end_seconds = float(int(segment.get("end_ms") or 0) / 1000.0)
        segment_range = _frame_range_from_seconds(
            start_seconds=segment_start_seconds,
            end_seconds=segment_end_seconds,
            fps=fps,
            timeline_end_frame=timeline_end_frame,
        )
        if segment_range is None:
            continue
        segment_start_frame, segment_end_frame = segment_range
        audio_start_seconds = float(segment.get("audio_primary_start") if segment.get("audio_primary_start") is not None else segment_start_seconds)
        audio_end_seconds = float(segment.get("audio_primary_end") if segment.get("audio_primary_end") is not None else segment_end_seconds)
        audio_range = _frame_range_from_seconds(
            start_seconds=max(segment_start_seconds, audio_start_seconds),
            end_seconds=max(audio_start_seconds, audio_end_seconds),
            fps=fps,
            timeline_end_frame=timeline_end_frame,
        )
        target_kind = str(segment.get("target_kind") or "").strip()
        reason = str(segment.get("reason") or target_kind or "audio_activity")
        is_signal_silence = "silence" in reason.lower() and not list(segment.get("sources") or [])
        primary_source_ids: list[str] = []
        if target_kind == "overlap":
            if not is_signal_silence:
                primary_source_ids = list(direct_source_ids)
        elif not is_signal_silence:
            for source_id in list(segment.get("audio_source_ids") or []):
                source_key = str(source_id)
                if source_key in per_source:
                    primary_source_ids.append(source_key)
            if not primary_source_ids and target_kind == "wide":
                primary_source_ids = list(direct_source_ids)

        if audio_range is not None:
            audio_start_frame, audio_end_frame = audio_range
            for source_id in dict.fromkeys(primary_source_ids):
                translated = _source_frame_range_for_timeline_range(
                    source_id=source_id,
                    record_start_frame=audio_start_frame,
                    record_end_frame=audio_end_frame,
                    per_source=per_source,
                )
                if translated is None:
                    continue
                source_start_frame, source_end_frame = translated
                instructions.append(
                    _audio_instruction_row(
                        source_id=source_id,
                        mode="wide" if target_kind == "overlap" else "primary",
                        record_start_frame=audio_start_frame,
                        record_end_frame=audio_end_frame,
                        source_start_frame=source_start_frame,
                        source_end_frame=source_end_frame,
                        reason=reason,
                        confidence=float(segment.get("confidence") or 0.0),
                        per_source=per_source,
                    )
                )

        for overlay in _dedupe_audio_overlays(segment.get("audio_overlays") or []):
            overlay_source_id = str(overlay.get("speaker_id") or "").strip()
            overlay_range = _frame_range_from_seconds(
                start_seconds=max(segment_start_seconds, float(overlay.get("start") or segment_start_seconds)),
                end_seconds=min(segment_end_seconds, float(overlay.get("end") or segment_end_seconds)),
                fps=fps,
                timeline_end_frame=timeline_end_frame,
            )
            if overlay_source_id not in per_source or overlay_range is None:
                continue
            overlay_start_frame, overlay_end_frame = overlay_range
            if overlay_end_frame <= segment_start_frame or overlay_start_frame >= segment_end_frame:
                continue
            translated = _source_frame_range_for_timeline_range(
                source_id=overlay_source_id,
                record_start_frame=overlay_start_frame,
                record_end_frame=overlay_end_frame,
                per_source=per_source,
            )
            if translated is None:
                continue
            source_start_frame, source_end_frame = translated
            instructions.append(
                _audio_instruction_row(
                    source_id=overlay_source_id,
                    mode=str(overlay.get("mode") or "audio_only_interjection"),
                    record_start_frame=overlay_start_frame,
                    record_end_frame=overlay_end_frame,
                    source_start_frame=source_start_frame,
                    source_end_frame=source_end_frame,
                    reason=str(overlay.get("reason") or "audio_overlay"),
                    confidence=float(overlay.get("confidence") or segment.get("confidence") or 0.0),
                    per_source=per_source,
                )
            )
    return sorted(
        instructions,
        key=lambda row: (
            str(row.get("source_id") or row.get("speaker_id") or ""),
            int(row.get("record_start_frame") or 0),
            int(row.get("record_end_frame") or 0),
            str(row.get("mode") or ""),
        ),
    )


def _merge_audio_instructions(instructions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = sorted(
        [dict(row) for row in instructions if isinstance(row, dict)],
        key=lambda row: (
            str(row.get("source_id") or row.get("speaker_id") or row.get("track_id") or ""),
            int(row.get("record_start_frame") or 0),
            int(row.get("record_end_frame") or 0),
        ),
    )
    merged: list[dict[str, Any]] = []
    for row in rows:
        source_id = str(row.get("source_id") or row.get("speaker_id") or row.get("track_id") or "").strip()
        record_start = int(row.get("record_start_frame") or 0)
        record_end = int(row.get("record_end_frame") or 0)
        source_start = int(row.get("source_start_frame") or 0)
        source_end = int(row.get("source_end_frame") or 0)
        if not source_id or record_end <= record_start or source_end <= source_start:
            continue
        normalized = {
            "source_id": source_id,
            "speaker_id": str(row.get("speaker_id") or source_id),
            "track_id": str(row.get("track_id") or source_id),
            "source_path": str(row.get("source_path") or ""),
            "record_start_frame": record_start,
            "record_end_frame": record_end,
            "source_start_frame": source_start,
            "source_end_frame": source_end,
            "modes": [str(row.get("mode") or "primary")],
            "reasons": [str(row.get("reason") or row.get("mode") or "audio_activity")],
        }
        if (
            merged
            and str(merged[-1].get("source_id") or "") == source_id
            and record_start <= int(merged[-1].get("record_end_frame") or 0)
            and source_start <= int(merged[-1].get("source_end_frame") or 0) + max(1, record_start - int(merged[-1].get("record_end_frame") or 0))
        ):
            previous = merged[-1]
            previous["record_end_frame"] = max(int(previous["record_end_frame"]), record_end)
            previous["source_end_frame"] = max(int(previous["source_end_frame"]), source_end)
            previous["modes"] = sorted(set(list(previous.get("modes") or []) + normalized["modes"]))
            previous["reasons"] = sorted(set(list(previous.get("reasons") or []) + normalized["reasons"]))
            continue
        merged.append(normalized)
    return merged


def _audio_batch_templates_from_ranges(ranges: list[dict[str, Any]]) -> dict[str, Any]:
    append_templates: list[dict[str, Any]] = []
    patch_templates: list[dict[str, Any]] = []
    fade_templates: list[dict[str, Any]] = []
    for index, row in enumerate(ranges):
        source_id = str(row.get("source_id") or row.get("speaker_id") or row.get("track_id") or "").strip()
        source_path = str(row.get("source_path") or "").strip()
        record_start = int(row.get("record_start_frame") or 0)
        record_end = int(row.get("record_end_frame") or 0)
        source_start = int(row.get("source_start_frame") or 0)
        source_end = int(row.get("source_end_frame") or 0)
        duration = min(record_end - record_start, source_end - source_start)
        if not source_id or not source_path or duration <= 0:
            continue
        source_end = source_start + duration
        base_selector = {
            "source_id": source_id,
            "record_frame": str(record_start),
            "record_duration": f"{duration}f",
            "requires_output_track_map": True,
        }
        append_templates.append(
            {
                "source_id": source_id,
                "track_type": "audio",
                "track_index": None,
                "absolute_record_frame": record_start,
                "source_start": f"{source_start}f",
                "source_end": f"{source_end}f",
                "path": source_path,
                "name_after_append": Path(source_path).name,
                "requires_output_track_map": True,
            }
        )
        patch_templates.append({**base_selector, "source_start_frame": source_start, "source_end_frame": source_end})
        fade_templates.append(dict(base_selector))
    return {
        "requires_output_track_map": True,
        "append_templates": append_templates,
        "source_patch_templates": patch_templates,
        "fade_templates": fade_templates,
        "recommended_fade_in_seconds": 0.2,
        "recommended_fade_range_seconds": [0.08, 0.25],
        "recommended_gain_db": None,
    }


def _build_audio_activity_plan_v2_from_precomputed(
    *,
    normalized_sources: list[dict[str, Any]],
    normalized_angle_map: dict[str, str],
    per_source: dict[str, dict[str, Any]],
    switching: dict[str, Any],
    overlap: dict[str, Any] | None,
    angle_map: dict[str, str],
    max_timeline_ms: int | None,
    fps: float,
    level_cache: dict[tuple[str, int, int], tuple[float, int, list[Any]]] | None = None,
) -> dict[str, Any]:
    settings = normalize_switching_settings(switching)
    overlap_settings = dict(overlap or {})
    wide_angle = str(overlap_settings.get("angle") or overlap_settings.get("wide_angle") or "").strip()
    direct_sources = [source for source in normalized_sources if normalized_angle_map.get(str(source["id"]))]
    if not direct_sources:
        raise ValidationError(
            "Audio activity v2 planning requires direct audio_angle_map entries.",
            details={"audio_angle_map": normalized_angle_map},
        )
    source_by_path: dict[str, dict[str, Any]] = {}
    for source in direct_sources:
        prepared = dict(per_source[str(source["id"])])
        for key in {str(source["path"]), str(Path(source["path"]).expanduser()), Path(str(source["path"])).name}:
            source_by_path[key] = prepared
    p90_values: list[float] = []
    for source in direct_sources:
        stats = dict(per_source[str(source["id"])].get("level_stats") or {})
        percentiles = dict(stats.get("rms_db_percentiles") or {})
        if percentiles.get("90") is not None:
            p90_values.append(float(percentiles["90"]))
    program_p90 = statistics.median(p90_values) if p90_values else -20.0
    source_p90_spread_db = (max(p90_values) - min(p90_values)) if len(p90_values) >= 2 else 0.0
    gain_normalization_db = max(-24.0, min(24.0, -20.0 - float(program_p90)))
    reader_cache = level_cache if level_cache is not None else {}
    original_plan_reader = audio_activity_v2_plan._read_audio_window_levels
    original_io_reader = audio_activity_v2_io._read_audio_window_levels

    def synced_reader(path: Path, window_seconds: float = 0.25):
        path_key = str(path)
        source = source_by_path.get(path_key) or source_by_path.get(str(Path(path).expanduser())) or source_by_path.get(Path(path).name)
        if not source:
            return original_io_reader(path, window_seconds=window_seconds)
        window_ms = max(1, int(round(float(window_seconds) * 1000.0)))
        cache_key = (str(Path(path).expanduser()), window_ms, int(source.get("offset_ms") or 0))
        if cache_key in reader_cache:
            return reader_cache[cache_key]
        cached = source.get("samples") if window_ms == int(settings["analysis_window_ms"]) else None
        reader_cache[cache_key] = _synced_v2_samples(
            source=source,
            window_ms=window_ms,
            cached_samples=cached,
            gain_normalization_db=gain_normalization_db,
        )
        return reader_cache[cache_key]

    speaker_map = [
        {
            "speaker_id": str(source["id"]),
            "camera_file": str(normalized_angle_map[str(source["id"])]),
            "camera_name": str(normalized_angle_map[str(source["id"])]),
            "angle": str(normalized_angle_map[str(source["id"])]),
            "mic_file": str(source["path"]),
            "audio_file": str(source["path"]),
        }
        for source in direct_sources
    ]

    audio_activity_v2_plan._read_audio_window_levels = synced_reader
    audio_activity_v2_io._read_audio_window_levels = synced_reader
    try:
        v2 = audio_activity_v2_plan.build_audio_activity_plan(
            [str(source["path"]) for source in direct_sources],
            speaker_map,
            wide_camera_id=wide_angle or None,
            window_seconds=float(settings["analysis_window_ms"]) / 1000.0,
            activity_margin_db=float(settings["activity_margin_db"]),
            dominance_margin_db=float(settings["dominance_margin_db"]),
            min_hold_seconds=max(float(settings["min_switch_ms"]) / 1000.0, float(settings["analysis_window_ms"]) / 500.0),
            max_silence_hold_seconds=float(settings["max_silence_hold_ms"]) / 1000.0,
            switch_delay_seconds=max(float(settings["switch_delay_ms"]) / 1000.0, float(settings["analysis_window_ms"]) / 1000.0),
            short_interjection_max_seconds=0.7,
            overlap_secondary_margin_db=max(float(settings["dominance_margin_db"]) * 3.0, 10.0),
            absolute_activity_floor_db=float(settings["activity_floor_db"]),
            camera_preroll_seconds=min(0.35, max(0.0, float(settings["switch_delay_ms"]) / 1000.0)),
            audio_handoff_overlap_seconds=0.35,
            audio_only_interjection_min_seconds=0.2,
            audio_only_interjection_max_seconds=2.5,
        )
    finally:
        audio_activity_v2_plan._read_audio_window_levels = original_plan_reader
        audio_activity_v2_io._read_audio_window_levels = original_io_reader

    total_ms = int(max_timeline_ms) if max_timeline_ms is not None else int(round(float(v2.get("duration_seconds") or 0.0) * 1000.0))
    raw_segments: list[dict[str, Any]] = []
    direct_source_ids = [str(source["id"]) for source in direct_sources]
    direct_angle_values = {str(angle) for angle in normalized_angle_map.values()}
    overlap_policy = str(overlap_settings.get("policy") or "mark").strip()
    for raw in list(v2.get("segments") or []):
        start_ms = max(0, int(round(float(raw.get("start") or 0.0) * 1000.0)))
        end_ms = int(round(float(raw.get("end") or 0.0) * 1000.0))
        if total_ms > 0:
            start_ms = min(start_ms, total_ms)
            end_ms = min(end_ms, total_ms)
        if end_ms <= start_ms:
            continue
        target_kind = str(raw.get("target_kind") or "").strip()
        target_id = str(raw.get("target_id") or "").strip()
        is_signal_silence = target_kind == "wide" and not list(raw.get("sources") or [])
        if is_signal_silence:
            raw_segments.append(
                {
                    "start_ms": start_ms,
                    "end_ms": end_ms,
                    "sources": [],
                    "target_kind": "silence",
                    "target_id": target_id,
                    "speaker_id": "",
                    "angle": None,
                    "audio_source_ids": [],
                    "candidate_angles": [],
                    "reason": str(raw.get("reason") or "silence"),
                    "confidence": float(raw.get("confidence") or 0.0),
                }
            )
            continue
        angle = target_id if target_id in angle_map else (wide_angle if target_kind == "wide" and wide_angle in angle_map else "")
        raw_sources = [dict(item or {}) for item in list(raw.get("sources") or []) if isinstance(item, dict)]
        if target_kind == "wide" and raw_sources and overlap_policy in {"dominant", "hold"}:
            candidate_angles = [
                str(item.get("target_id") or "")
                for item in raw_sources
                if str(item.get("target_id") or "") in direct_angle_values
            ]
            source_ids = [
                str(item.get("speaker_id") or "").strip()
                for item in raw_sources
                if str(item.get("speaker_id") or "").strip()
            ]
            previous_resolved = next((segment for segment in reversed(raw_segments) if segment.get("angle")), None)
            if overlap_policy == "hold" and previous_resolved and previous_resolved.get("angle"):
                held_angle = str(previous_resolved.get("angle"))
                raw_segments.append(
                    {
                        "start_ms": start_ms,
                        "end_ms": end_ms,
                        "sources": raw_sources,
                        "target_kind": "hold",
                        "target_id": held_angle,
                        "speaker_id": str(previous_resolved.get("speaker_id") or ""),
                        "angle": held_angle,
                        "audio_source_ids": source_ids,
                        "candidate_angles": list(dict.fromkeys(candidate_angles or [held_angle])),
                        "reason": "overlap_hold_previous",
                        "confidence": float(raw.get("confidence") or 0.0),
                    }
                )
                continue
            leader = next((item for item in raw_sources if str(item.get("target_id") or "") in direct_angle_values), None)
            if leader is not None:
                leader_angle = str(leader.get("target_id") or "")
                leader_source_id = str(leader.get("speaker_id") or "").strip()
                raw_segments.append(
                    {
                        "start_ms": start_ms,
                        "end_ms": end_ms,
                        "sources": raw_sources,
                        "target_kind": "audio_source",
                        "target_id": leader_angle,
                        "speaker_id": leader_source_id,
                        "angle": leader_angle,
                        "audio_source_ids": [leader_source_id] if leader_source_id else [],
                        "candidate_angles": list(dict.fromkeys(candidate_angles or [leader_angle])),
                        "reason": "overlap_dominant" if overlap_policy == "dominant" else "overlap_hold_fallback_dominant",
                        "confidence": float(raw.get("confidence") or 0.0),
                    }
                )
                continue
        if not angle:
            continue
        speaker_id = str(raw.get("speaker_id") or "").strip()
        source_ids = [speaker_id] if speaker_id else list(direct_source_ids) if target_kind == "wide" else []
        audio_primary_start = float(raw.get("audio_primary_start") if raw.get("audio_primary_start") is not None else raw.get("start") or 0.0)
        audio_primary_end = float(raw.get("audio_primary_end") if raw.get("audio_primary_end") is not None else raw.get("end") or 0.0)
        raw_segments.append(
            {
                "start_ms": start_ms,
                "end_ms": end_ms,
                "sources": list(raw.get("sources") or []),
                "target_kind": "overlap" if target_kind == "wide" and raw.get("sources") else ("hold" if target_kind == "hold" else "audio_source"),
                "target_id": target_id,
                "speaker_id": speaker_id,
                "angle": angle,
                "audio_source_ids": source_ids,
                "candidate_angles": [angle],
                "reason": str(raw.get("reason") or target_kind or "audio_activity_v2"),
                "confidence": float(raw.get("confidence") or 0.0),
                "audio_primary_start": audio_primary_start,
                "audio_primary_end": audio_primary_end,
                **({"audio_overlays": list(raw.get("audio_overlays") or [])} if raw.get("audio_overlays") else {}),
            }
        )

    filled = _merge_adjacent_windows(raw_segments)
    if total_ms > 0 and filled:
        filled[0]["start_ms"] = 0
        filled[-1]["end_ms"] = max(int(filled[-1]["end_ms"]), total_ms)
    audio_instructions = _audio_instructions_from_segments(
        segments=raw_segments,
        direct_source_ids=direct_source_ids,
        per_source=per_source,
        fps=fps,
        max_timeline_ms=total_ms if total_ms > 0 else max_timeline_ms,
    )
    audio_ranges = _merge_audio_instructions(audio_instructions)
    audio_batch_plan = _audio_batch_templates_from_ranges(audio_ranges)
    unresolved_segments: list[dict[str, Any]] = []
    suppressed_audio_segments = [
        {
            "start_ms": int(round(float(row.get("start") or 0.0) * 1000.0)),
            "end_ms": int(round(float(row.get("end") or 0.0) * 1000.0)),
            "audio_source_ids": [str(row.get("speaker_id") or "")],
            "candidate_angles": [str(row.get("target_id") or "")],
            "reason": str(row.get("reason") or row.get("mode") or "audio_overlay"),
        }
        for row in list(v2.get("audio_instructions") or [])
        if row.get("speaker_id") and float(row.get("end") or 0.0) > float(row.get("start") or 0.0)
    ]
    metrics = _segment_metrics(
        segments=filled,
        unresolved_segments=unresolved_segments,
        raw_windows=filled,
        total_ms=total_ms,
    )
    return {
        "kind": "audio_activity_v1",
        "planner": "audio_activity_v2",
        "segments": filled,
        "unresolved_segments": unresolved_segments,
        "suppressed_audio_segments": suppressed_audio_segments,
        "audio_instructions": audio_instructions,
        "audio_ranges": audio_ranges,
        "audio_batch_plan": audio_batch_plan,
        "raw_window_count": int(v2.get("metrics", {}).get("raw_window_count") or 0),
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
        "audio_targets": {},
        "metrics": {
            **metrics,
            "suppressed_short_switch_count": len(suppressed_audio_segments) + int((v2.get("metrics") or {}).get("suppressed_interjections") or 0),
            "v2_metrics": dict(v2.get("metrics") or {}),
            "gain_normalization_db": round(float(gain_normalization_db), 3),
            "source_p90_spread_db": round(float(source_p90_spread_db), 3),
            "audio_instruction_count": len(audio_instructions),
            "audio_range_count": len(audio_ranges),
            "audio_append_template_count": len(audio_batch_plan.get("append_templates") or []),
        },
    }


__all__ = (
    '_synced_v2_samples',
    '_seconds_to_frames',
    '_frame_range_from_seconds',
    '_slice_offset_frames',
    '_source_frame_range_for_timeline_range',
    '_audio_instruction_row',
    '_dedupe_audio_overlays',
    '_audio_instructions_from_segments',
    '_merge_audio_instructions',
    '_audio_batch_templates_from_ranges',
    '_build_audio_activity_plan_v2_from_precomputed',
)
