"""DB-backed helpers for DaVinci Resolve Change Clip Speed mutations."""

from __future__ import annotations

from dataclasses import asdict
import math
import re
import sqlite3
import struct
from typing import Any

import zstandard as zstd

from ..errors import APICallFailed, ValidationError
from ..fixtures import db_workaround_payloads as fixture_payloads
from ..runtime_health import resolve_current_disk_project_db
from ..utils.time_ref import parse_source_frame
from . import db_timeline_rows, db_timeline_selection, retime_db, retime_render_proof
from .db_timeline_selection import LiveItemRef
from .retime_native_coordinates import exact_native_rate, native_frame_position


_PITCH_CORRECTION_COLUMNS = (
    "PitchCorrection",
    "PitchCorrectionEnabled",
    "PreservePitch",
    "AudioPitchCorrection",
    "RetimePitchCorrection",
)
_CLIP_SPEED_VIDEO_EFFECT_FILTERS = bytes.fromhex(fixture_payloads.CLIP_SPEED_VIDEO_EFFECT_FILTERS_HEX)
_CLIP_SPEED_AUDIO_EFFECT_FILTERS = bytes.fromhex(fixture_payloads.CLIP_SPEED_AUDIO_EFFECT_FILTERS_HEX)
_CLIP_SPEED_KNOWN_EFFECT_FILTERS = {
    "video": {_CLIP_SPEED_VIDEO_EFFECT_FILTERS},
    "audio": {_CLIP_SPEED_AUDIO_EFFECT_FILTERS},
}
_PITCH_ENABLED_MARKER = b"\x20\x01\x78\x04"
_PITCH_DISABLED_MARKER = b"\x20\x01\x10\x00\x78\x04"
_NUMBER_RE = re.compile(r"[-+]?\d+(?:\.\d+)?")


def normalize_keyframe_mode(value: str | None) -> str:
    normalized = str(value or "maintain-timing").strip().lower().replace("_", "-")
    aliases = {
        "maintain": "maintain-timing",
        "maintain-timing": "maintain-timing",
        "timing": "maintain-timing",
        "stretch": "stretch-to-fit",
        "stretch-fit": "stretch-to-fit",
        "stretch-to-fit": "stretch-to-fit",
    }
    result = aliases.get(normalized)
    if result is None:
        raise ValidationError(
            "--keyframes must be one of: maintain-timing, stretch-to-fit.",
            details={"keyframes": value, "supported": ["maintain-timing", "stretch-to-fit"]},
            recoverability="not_applicable",
        )
    return result


def validate_speed_controls(
    *,
    multiplier: float | None = None,
    speed_percent: float | None = None,
    frames_per_second: float | None = None,
    duration: str | None = None,
    reverse_speed: bool = False,
    freeze_frame: bool = False,
    pitch_correction: bool | None = None,
    keyframes: str | None = None,
) -> dict[str, Any]:
    keyframe_mode = normalize_keyframe_mode(keyframes)
    speed_control_count = sum(
        value is not None
        for value in (
            multiplier,
            speed_percent,
            frames_per_second,
            duration,
        )
    )
    if speed_control_count > 1:
        raise ValidationError(
            "Use only one clip speed control: --set/--multiplier, --speed-percent, --fps, or --duration.",
            details={
                "multiplier": multiplier,
                "speed_percent": speed_percent,
                "frames_per_second": frames_per_second,
                "duration": duration,
            },
            recoverability="not_applicable",
        )
    if freeze_frame and reverse_speed:
        raise ValidationError(
            "--freeze-frame cannot be combined with --reverse-speed.",
            details={"freeze_frame": freeze_frame, "reverse_speed": reverse_speed},
            recoverability="not_applicable",
        )
    if freeze_frame and speed_control_count and duration is None:
        raise ValidationError(
            "--freeze-frame can only be combined with --duration.",
            details={
                "freeze_frame": freeze_frame,
                "multiplier": multiplier,
                "speed_percent": speed_percent,
                "frames_per_second": frames_per_second,
                "duration": duration,
            },
            recoverability="not_applicable",
        )
    for field, value in (
        ("multiplier", multiplier),
        ("speed_percent", speed_percent),
        ("frames_per_second", frames_per_second),
    ):
        if value is None:
            continue
        number = float(value)
        if not math.isfinite(number) or number <= 0:
            raise ValidationError(
                f"Clip speed {field} must be finite and greater than 0.",
                details={field: value},
                recoverability="not_applicable",
            )

    retime_requested = any(
        (
            speed_control_count,
            reverse_speed,
            freeze_frame,
        )
    )
    if (pitch_correction is not None or keyframe_mode != "maintain-timing") and not retime_requested:
        raise ValidationError(
            "Pitch correction and keyframe timing are modifiers for a clip speed change.",
            details={"pitch_correction": pitch_correction, "keyframes": keyframe_mode},
            recoverability="not_applicable",
        )
    return {
        "multiplier": None if multiplier is None else float(multiplier),
        "speed_percent": None if speed_percent is None else float(speed_percent),
        "frames_per_second": None if frames_per_second is None else float(frames_per_second),
        "duration": duration,
        "reverse_speed": bool(reverse_speed),
        "freeze_frame": bool(freeze_frame),
        "pitch_correction": pitch_correction,
        "keyframes": keyframe_mode,
        "retime_requested": bool(retime_requested),
    }


def _timeline_name(conn: Any) -> str | None:
    timeline = getattr(conn, "timeline", None)
    if timeline is None:
        return None
    try:
        return str(timeline.GetName() or "")
    except Exception:
        return None


def _as_int(value: Any, *, default: int = 0) -> int:
    try:
        return int(float(str(value).strip()))
    except Exception:
        return int(default)


def _finite_float(value: Any) -> float | None:
    try:
        number = float(value)
    except Exception:
        return None
    return number if math.isfinite(number) else None


def _record_in_frames(row: dict[str, Any]) -> float:
    # Native untrimmed timeline items store SQL NULL for their zero origin.
    value = row.get("In")
    return native_frame_position(0 if value is None else value)


def _positive_number(value: Any) -> float | None:
    number = _finite_float(value)
    if number is None and value is not None:
        match = _NUMBER_RE.search(str(value))
        if match:
            number = _finite_float(match.group(0))
    return number if number is not None and number > 0 else None


def resolve_timeline_fps(conn: Any) -> float:
    timeline = getattr(conn, "timeline", None)
    get_setting = getattr(timeline, "GetSetting", None)
    if callable(get_setting):
        try:
            settings = get_setting()
        except Exception:
            settings = None
        if isinstance(settings, dict):
            for key in ("timelineFrameRate", "timelinePlaybackFrameRate"):
                number = _positive_number(settings.get(key))
                if number is not None:
                    return exact_native_rate(number)
        try:
            number = _positive_number(get_setting("timelineFrameRate"))
        except Exception:
            number = None
        if number is not None:
            return exact_native_rate(number)
    return exact_native_rate(_positive_number(getattr(conn, "fps", None)) or 25.0)


def _parse_duration_frames(value: str, fps: float) -> int:
    frames = parse_source_frame(str(value), fps)
    if frames <= 0:
        raise ValidationError(
            "Clip speed duration must be greater than 0 frames.",
            details={"duration": value, "duration_frames": frames},
            recoverability="not_applicable",
        )
    return frames


def validate_duration_frames(value: str, fps: float) -> int:
    return _parse_duration_frames(value, fps)


def _decoded_entries(blob: Any) -> dict[str, Any] | None:
    decoded = retime_db.decode_timemap_blob(blob).get("decoded")
    if isinstance(decoded, dict) and isinstance(decoded.get("entries"), dict):
        return decoded["entries"]
    return None


def _decoded_points(blob: Any) -> list[dict[str, float | int]]:
    entries = _decoded_entries(blob)
    if not entries:
        return []
    keyframes_ba = entries.get("KeyframesBA")
    decoded_keyframes = keyframes_ba.get("decoded") if isinstance(keyframes_ba, dict) else None
    if not isinstance(decoded_keyframes, dict):
        return []
    if decoded_keyframes.get("type") in {"RetimeKeyframeListProto", "Sm2TimeMapLegacyKeyframes"}:
        return [
            {
                "x": float(point.get("x", 0.0)),
                "y": float(point.get("y", 0.0)),
                "x_in": float(point.get("x_in", 0.0)),
                "y_in": float(point.get("y_in", 0.0)),
                "x_out": float(point.get("x_out", 0.0)),
                "y_out": float(point.get("y_out", 0.0)),
                "interp": int(point.get("interp", 0)),
            }
            for point in decoded_keyframes.get("keyframes") or []
        ]
    point_entries = decoded_keyframes.get("entries")
    if not isinstance(point_entries, dict):
        return []
    points: list[dict[str, float | int]] = []
    for key in sorted(point_entries, key=lambda raw: int(raw)):
        point = point_entries[key]
        point_decoded = point.get("decoded") if isinstance(point, dict) else None
        values = point_decoded.get("entries") if isinstance(point_decoded, dict) else None
        if not isinstance(values, dict):
            continue
        points.append(
            {
                "x": float(values.get("X", 0.0)),
                "y": float(values.get("Y", 0.0)),
                "x_in": float(values.get("XIn", 0.0)),
                "y_in": float(values.get("YIn", 0.0)),
                "x_out": float(values.get("XOut", 0.0)),
                "y_out": float(values.get("YOut", 0.0)),
                "interp": int(values.get("interp", 0)),
            }
        )
    return points


def _native_interval_metrics(points: list[dict[str, Any]], *, start: float, end: float) -> tuple[float, bool]:
    """Read visible mean slope; nonlinear maps must not drive constant edits."""
    curve = {"points": [{
        "record_frame": p["x"], "source_frame": p["y"],
        "record_frame_in": p["x"] + p.get("x_in", 0.0),
        "source_frame_in": p["y"] + p.get("y_in", 0.0),
        "record_frame_out": p["x"] + p.get("x_out", 0.0),
        "source_frame_out": p["y"] + p.get("y_out", 0.0),
    } for p in points]}
    slope = (retime_render_proof._source_at(curve, end) - retime_render_proof._source_at(curve, start)) / (end - start) if end > start else 0.0
    variable = False
    for left, right in zip(points, points[1:]):
        if right["x"] <= start or left["x"] >= end:
            continue
        segment_slope = (right["y"] - left["y"]) / (right["x"] - left["x"])
        variable |= abs(segment_slope - slope) > 1e-7
        for point, suffix in ((left, "out"), (right, "in")):
            variable |= abs(point.get(f"y_{suffix}", 0.0) - segment_slope * point.get(f"x_{suffix}", 0.0)) > 1e-7
    return slope, variable


def infer_timemap_state(row: dict[str, Any], *, fps: float, record_fps: float | None = None, fallback_duration_frames: int | None = None) -> dict[str, Any]:
    duration_frames = _as_int(row.get("Duration"), default=fallback_duration_frames or 0)
    record_fps = float(record_fps or fps)
    blob = row.get("MediaTimemapBA")
    summary = retime_db.decode_timemap_blob(blob)
    decoded = summary.get("decoded")
    if isinstance(decoded, dict) and decoded.get("type") == "simple_default":
        source_duration = max(1, int(round(duration_frames * fps / record_fps)))
        return {
            "duration_frames": duration_frames,
            "source_duration_frames": source_duration,
            "speed_multiplier": 1.0,
            "speed_percent": 100.0,
            "reverse_speed": False,
            "freeze_frame": False,
            "timemap": summary,
            "native_interval": True,
        }

    entries = _decoded_entries(blob)
    if not entries:
        fallback_duration = max(1, duration_frames or int(fallback_duration_frames or 1))
        return {
            "duration_frames": duration_frames,
            "source_duration_frames": fallback_duration,
            "speed_multiplier": 1.0,
            "speed_percent": 100.0,
            "reverse_speed": False,
            "freeze_frame": False,
            "timemap": summary,
        }

    points = _decoded_points(blob)
    keyframe_type = entries.get("KeyframesBA", {}).get("decoded", {}).get("type")
    if points and keyframe_type == "RetimeKeyframeListProto":
        start = _record_in_frames(row) / record_fps
        end = start + max(0, duration_frames - 1) / record_fps
        signed_speed, variable = _native_interval_metrics(points, start=start, end=end)
        multiplier = abs(signed_speed)
        source_duration = max(1, int(round(duration_frames * multiplier * fps / record_fps)))
        return {
            "duration_frames": duration_frames, "source_duration_frames": source_duration,
            "speed_multiplier": multiplier, "speed_percent": multiplier * 100,
            "reverse_speed": signed_speed < 0,
            "freeze_frame": not variable and multiplier == 0,
            "variable_speed": variable, "native_interval": True, "timemap": summary,
        }
    y_values = [float(point["y"]) for point in points]
    x_values = [float(point["x"]) for point in points]
    last_valid = _finite_float(entries.get("LastValidYOffset"))
    y_max = _finite_float(entries.get("YMax"))
    source_seconds = last_valid if last_valid is not None and last_valid > 0 else y_max
    if (source_seconds is None or source_seconds <= 0) and y_values:
        source_seconds = max(abs(value) for value in y_values)
    source_duration = (
        max(1, int(round(float(source_seconds) * float(fps or 25.0))) + 1)
        if source_seconds is not None
        else max(1, int(fallback_duration_frames or duration_frames or 1))
    )
    output_duration = max(1, duration_frames or int(round(float(entries.get("XMax") or 0.0) * float(fps or 25.0))) + 1)
    freeze_frame = bool(points) and len({round(value, 9) for value in y_values}) == 1 and max(x_values or [0.0]) > 1000.0
    reverse_speed = bool(points) and len(points) >= 2 and float(points[-1]["y"]) < float(points[0]["y"])
    multiplier = 0.0 if freeze_frame else float(source_duration) / float(output_duration)
    return {
        "duration_frames": duration_frames,
        "source_duration_frames": source_duration,
        "speed_multiplier": multiplier,
        "speed_percent": multiplier * 100.0,
        "reverse_speed": reverse_speed,
        "freeze_frame": freeze_frame,
        "timemap": summary,
    }


def normalized_time_map_state(
    row: dict[str, Any], *, fps: float, record_start_frame: int, fallback_duration_frames: int | None = None
) -> dict[str, Any]:
    """Project decoded retime bytes into a bounded semantic frame-domain state."""

    fps = exact_native_rate(fps)
    source_fps = _source_fps(row, fallback_fps=fps)
    state = infer_timemap_state(row, fps=source_fps, record_fps=fps, fallback_duration_frames=fallback_duration_frames)
    duration = max(1, int(state["duration_frames"] or fallback_duration_frames or 1))
    semantic_multiplier = (
        0.0
        if state["freeze_frame"]
        else (float(state["source_duration_frames"]) / source_fps) / (float(duration) / float(fps or 25.0))
    )
    if state.get("native_interval"):
        semantic_multiplier = state["speed_multiplier"]
    # Native keyframes span media time, including the region before the trim.
    # DB In is on the record-rate axis; Y is already absolute media seconds.
    record_origin = float(record_start_frame) - _record_in_frames(row)
    source_start = _record_in_frames(row) * source_fps / float(fps)
    decoded = _decoded_points(row.get("MediaTimemapBA"))
    points: list[dict[str, Any]] = []
    for index, point in enumerate(decoded):
        if index + 1 < len(decoded):
            next_point = decoded[index + 1]
            dx = float(next_point["x"]) - float(point["x"])
            speed = 0.0 if abs(dx) < 1e-12 else (float(next_point["y"]) - float(point["y"])) / dx
        elif points:
            speed = float(points[-1]["speed"])
        else:
            speed = 0.0 if state["freeze_frame"] else (-semantic_multiplier if state["reverse_speed"] else semantic_multiplier)
        points.append(
            {
                "record_frame": int(round(record_origin + float(point["x"]) * fps)),
                "record_position": record_origin + (float(point["x"]) * fps),
                "interpolation_code": int(point.get("interp", 0)),
                "source_frame": float(point["y"]) * source_fps,
                "record_frame_in": record_origin + ((float(point["x"]) + float(point.get("x_in", 0.0))) * fps),
                "source_frame_in": (float(point["y"]) + float(point.get("y_in", 0.0))) * source_fps,
                "record_frame_out": record_origin + ((float(point["x"]) + float(point.get("x_out", 0.0))) * fps),
                "source_frame_out": (float(point["y"]) + float(point.get("y_out", 0.0))) * source_fps,
                "speed": float(speed),
                "interpolation": "hold" if state["freeze_frame"] else (
                    "bezier"
                    if int(point.get("interp", 0)) != 0 or any(abs(float(point.get(key, 0.0))) > 1e-12 for key in ("x_in", "y_in", "x_out", "y_out"))
                    else "linear"
                ),
            }
        )
    if not points:
        signed_speed = 0.0 if state["freeze_frame"] else (-semantic_multiplier if state["reverse_speed"] else semantic_multiplier)
        source_end = source_start if state["freeze_frame"] else source_start + (duration - 1) * source_fps / float(fps)
        if state["reverse_speed"]:
            source_start, source_end = source_end, source_start
        points = [
            {
                "record_frame": int(record_start_frame),
                "record_position": float(record_start_frame),
                "source_frame": float(source_start),
                "record_frame_in": float(record_start_frame),
                "source_frame_in": float(source_start),
                "record_frame_out": float(record_start_frame),
                "source_frame_out": float(source_start),
                "speed": signed_speed,
                "interpolation": "hold" if state["freeze_frame"] else "linear",
            },
            {
                "record_frame": int(record_start_frame) + duration - 1,
                "record_position": float(int(record_start_frame) + duration - 1),
                "source_frame": float(source_end),
                "record_frame_in": float(int(record_start_frame) + duration - 1),
                "source_frame_in": float(source_end),
                "record_frame_out": float(int(record_start_frame) + duration - 1),
                "source_frame_out": float(source_end),
                "speed": signed_speed,
                "interpolation": "hold" if state["freeze_frame"] else "linear",
            },
        ]
    return {
        "duration_frames": duration,
        "native_record_origin_seconds": _record_in_frames(row) / float(fps),
        "record_fps": float(fps),
        "curve_kind": "explicit_points" if decoded else (
            "identity" if (state["timemap"].get("decoded") or {}).get("type") == "simple_default" else "unsupported"
        ),
        "curve_points": decoded,
        "source_fps": source_fps,
        "speed_multiplier": float(semantic_multiplier),
        "reversed": bool(state["reverse_speed"]),
        "frozen": bool(state["freeze_frame"]),
        "points": points,
    }


def _source_fps(row: dict[str, Any], *, fallback_fps: float) -> float:
    for key in ("MediaFrameRate", "FrameRate", "FPS"):
        value = row.get(key)
        if isinstance(value, (bytes, bytearray)) and len(value) >= 8:
            try:
                number = float(struct.unpack("<d", bytes(value[:8]))[0])
            except (struct.error, TypeError, ValueError):
                number = None
        else:
            number = _finite_float(value)
        if number is not None and math.isfinite(number) and number > 0:
            return number
    return float(fallback_fps or 25.0)


def _effective_plan_for_row(
    row: dict[str, Any],
    *,
    fps: float,
    options: dict[str, Any],
) -> dict[str, Any]:
    old_duration = max(1, _as_int(row.get("Duration"), default=1))
    source_fps = _source_fps(row, fallback_fps=fps)
    state = infer_timemap_state(row, fps=source_fps, record_fps=fps, fallback_duration_frames=old_duration)
    if state.get("variable_speed"):
        raise ValidationError("A nonlinear native time map cannot be converted to constant speed without an explicit source-span policy.")
    source_duration = int(state["source_duration_frames"])
    requested_duration = options.get("duration")
    duration_frames = _parse_duration_frames(str(requested_duration), fps) if requested_duration is not None else None

    if options["freeze_frame"]:
        new_duration = int(duration_frames or old_duration)
        speed_multiplier = 0.0
        timemap = retime_db.build_freeze_timemap(source_duration, source_fps)
        operation = "freeze-frame"
    else:
        if duration_frames is not None:
            new_duration = int(duration_frames)
            speed_multiplier = (float(source_duration) / source_fps) / (float(new_duration) / fps)
        elif options["frames_per_second"] is not None:
            speed_multiplier = float(options["frames_per_second"]) / _source_fps(row, fallback_fps=fps)
            new_duration = max(1, int(round((source_duration / source_fps) * fps / speed_multiplier)))
        elif options["speed_percent"] is not None:
            speed_multiplier = float(options["speed_percent"]) / 100.0
            new_duration = max(1, int(round((source_duration / source_fps) * fps / speed_multiplier)))
        elif options["multiplier"] is not None:
            speed_multiplier = float(options["multiplier"])
            new_duration = max(1, int(round((source_duration / source_fps) * fps / speed_multiplier)))
        else:
            new_duration = old_duration
            speed_multiplier = (float(source_duration) / source_fps) / (float(new_duration) / fps)

        if options["reverse_speed"]:
            operation = "reverse-speed"
            if abs(speed_multiplier - 1.0) < 1e-9 and new_duration == old_duration:
                timemap = retime_db.build_reverse_timemap(source_duration, source_fps)
            else:
                timemap = retime_db.build_constant_retime_timemap(source_duration, new_duration, fps, reverse=True, source_fps=source_fps)
        elif abs(speed_multiplier - 1.0) < 1e-9 and new_duration == old_duration:
            operation = "constant-speed"
            timemap = retime_db.default_timemap(old_duration, fps)
        else:
            operation = "constant-speed"
            timemap = retime_db.build_constant_retime_timemap(source_duration, new_duration, fps, source_fps=source_fps)

    return {
        "operation": operation,
        "old_duration": old_duration,
        "new_duration": int(new_duration),
        "source_duration_frames": int(source_duration),
        "speed_multiplier": float(speed_multiplier),
        "speed_percent": float(speed_multiplier) * 100.0,
        "timemap": timemap,
        "previous": state,
    }


def _decode_qt_zstd_blob(blob: Any) -> bytes | None:
    payload = bytes(blob or b"")
    if len(payload) < 9 or payload[8] != 0x81:
        return None
    try:
        return zstd.ZstdDecompressor().decompress(payload[9:], max_output_size=16 * 1024 * 1024)
    except Exception:
        return None


def _encode_qt_zstd_blob(proto: bytes) -> bytes:
    body = b"\x81" + zstd.ZstdCompressor(level=3).compress(bytes(proto))
    return struct.pack(">II", 2, len(body)) + body


def _pitch_state_from_fields_blob(blob: Any) -> bool | None:
    proto = _decode_qt_zstd_blob(blob)
    if proto is None:
        return None
    if _PITCH_DISABLED_MARKER in proto:
        return False
    if _PITCH_ENABLED_MARKER in proto:
        return True
    return None


def _pitch_state_from_column(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return bool(value)
    if isinstance(value, bytes):
        try:
            value = value.decode("utf-8", errors="ignore")
        except Exception:
            return None
    if isinstance(value, str):
        normalized = value.strip().lower()
        if not normalized or normalized in {"null", "none"}:
            return None
        if normalized in {"true", "yes", "on", "enabled"}:
            return True
        if normalized in {"false", "no", "off", "disabled"}:
            return False
        value = normalized
    number = _finite_float(value)
    if number is None:
        return None
    return number != 0


def _pitch_state_from_row(row: dict[str, Any]) -> bool | None:
    fields_blob_state = _pitch_state_from_fields_blob(row.get("FieldsBlob"))
    if fields_blob_state is not None:
        return fields_blob_state
    for column in _PITCH_CORRECTION_COLUMNS:
        if column not in row:
            continue
        state = _pitch_state_from_column(row.get(column))
        if state is not None:
            return state
    return None


def _set_pitch_state_in_fields_blob(blob: Any, *, enabled: bool) -> tuple[bytes | None, bool | None, str]:
    proto = _decode_qt_zstd_blob(blob)
    if proto is None:
        return None, None, "fields_blob_not_decodable"
    if enabled:
        if _PITCH_DISABLED_MARKER in proto:
            return _encode_qt_zstd_blob(proto.replace(_PITCH_DISABLED_MARKER, _PITCH_ENABLED_MARKER, 1)), True, "fields_blob_marker"
        if _PITCH_ENABLED_MARKER in proto:
            return bytes(blob), True, "fields_blob_marker_already_enabled"
        return None, None, "fields_blob_marker_unavailable"
    if _PITCH_DISABLED_MARKER in proto:
        return bytes(blob), False, "fields_blob_marker_already_disabled"
    if _PITCH_ENABLED_MARKER in proto:
        return _encode_qt_zstd_blob(proto.replace(_PITCH_ENABLED_MARKER, _PITCH_DISABLED_MARKER, 1)), False, "fields_blob_marker"
    return None, None, "fields_blob_marker_unavailable"


def _clip_speed_effect_filter_update(
    cursor: sqlite3.Cursor,
    *,
    row: dict[str, Any],
    media_kind: str,
    enabled: bool,
) -> dict[str, Any]:
    if not enabled or "EffectFiltersBA" not in db_timeline_rows.table_columns(cursor, "Sm2TiItem"):
        return {"applied": False, "reason": "effect_filters_column_unavailable" if enabled else "not_needed", "updates": {}}
    payload = _CLIP_SPEED_VIDEO_EFFECT_FILTERS if media_kind == "video" else _CLIP_SPEED_AUDIO_EFFECT_FILTERS
    existing = row.get("EffectFiltersBA")
    known = _CLIP_SPEED_KNOWN_EFFECT_FILTERS.get(media_kind, set())
    if existing is not None and bytes(existing) not in known:
        return {
            "applied": False,
            "reason": "existing_effect_filters_preserved",
            "existing_length": len(bytes(existing)),
            "updates": {},
        }
    return {
        "applied": True,
        "reason": "gui_clip_speed_effect_filters",
        "updates": {"EffectFiltersBA": sqlite3.Binary(payload)},
        "effect_filters_length": len(payload),
    }


def _pitch_correction_update(cursor: sqlite3.Cursor, *, row: dict[str, Any], enabled: bool | None) -> dict[str, Any]:
    if enabled is None:
        return {"requested": None, "applied": False, "reason": "not_requested", "updates": {}}
    available = db_timeline_rows.table_columns(cursor, "Sm2TiItem")
    updates: dict[str, Any] = {}
    applied_paths: list[str] = []
    previous_state: bool | None = None

    column = next((candidate for candidate in _PITCH_CORRECTION_COLUMNS if candidate in available), None)
    if column is not None:
        updates[column] = 1 if enabled else 0
        applied_paths.append(f"column:{column}")

    if "FieldsBlob" in available:
        previous_state = _pitch_state_from_fields_blob(row.get("FieldsBlob"))
        fields_blob, _, reason = _set_pitch_state_in_fields_blob(row.get("FieldsBlob"), enabled=bool(enabled))
        if fields_blob is not None:
            updates["FieldsBlob"] = sqlite3.Binary(fields_blob)
            applied_paths.append(reason)

    if not applied_paths:
        return {
            "requested": bool(enabled),
            "applied": False,
            "reason": "pitch_state_storage_unavailable",
            "previous_state": previous_state,
            "candidate_columns": list(_PITCH_CORRECTION_COLUMNS),
            "updates": {},
        }
    return {
        "requested": bool(enabled),
        "applied": True,
        "paths": applied_paths,
        "previous_state": previous_state,
        "value": bool(enabled),
        "updates": updates,
    }


def _timeline_track_ids(cursor: sqlite3.Cursor, *, timeline_name: str | None) -> list[str]:
    if not timeline_name:
        return []
    try:
        rows = cursor.execute(
            """
            SELECT rel.DbAssociate
            FROM Sm2Timeline tl
            JOIN Sm2SequenceContainer sc ON sc.Sm2Sequence_id = tl.Sequence
            JOIN Sm2SequenceContainer_Sm2TiTrack rel ON rel.DbOwner = sc.Sm2SequenceContainer_id
            WHERE tl.Name = ?
              AND rel.DbAssociate IS NOT NULL
            """,
            (timeline_name,),
        ).fetchall()
    except sqlite3.Error:
        return []
    return [str(row[0]) for row in rows if row[0] is not None]


def _apply_ripple_shift(
    cursor: sqlite3.Cursor,
    *,
    timeline_name: str | None,
    anchor_end: int,
    delta_frames: int,
    target_ids: set[str],
) -> dict[str, Any]:
    if delta_frames == 0:
        return {"enabled": True, "delta_frames": 0, "shifted": []}
    track_ids = _timeline_track_ids(cursor, timeline_name=timeline_name)
    if not track_ids:
        return {
            "enabled": True,
            "delta_frames": int(delta_frames),
            "shifted": [],
            "warning": "timeline_track_ids_unavailable",
        }
    placeholders = ", ".join("?" for _ in track_ids)
    rows = cursor.execute(
        f"""
        SELECT Sm2TiItem_id, DbType, Name, Start, Duration, Sm2TiTrack_id
        FROM Sm2TiItem
        WHERE Sm2TiTrack_id IN ({placeholders})
          AND CAST(COALESCE(Start, '0') AS INTEGER) >= ?
        ORDER BY CAST(COALESCE(Start, '0') AS INTEGER), Sm2TiItem_id
        """,
        (*track_ids, int(anchor_end)),
    ).fetchall()
    shifted: list[dict[str, Any]] = []
    for row in rows:
        item_id = str(row["Sm2TiItem_id"])
        if item_id in target_ids:
            continue
        old_start = _as_int(row["Start"])
        new_start = old_start + int(delta_frames)
        db_timeline_rows.update_row(cursor, "Sm2TiItem", "Sm2TiItem_id", item_id, {"Start": str(new_start)})
        shifted.append(
            {
                "item_id": item_id,
                "db_type": row["DbType"],
                "name": row["Name"],
                "track_id": row["Sm2TiTrack_id"],
                "old_start": old_start,
                "new_start": new_start,
            }
        )
    return {"enabled": True, "delta_frames": int(delta_frames), "shifted": shifted}


def apply_clip_speed(
    cursor: sqlite3.Cursor,
    *,
    conn: Any,
    selection: dict[str, LiveItemRef | list[LiveItemRef] | None],
    timeline_name: str | None,
    options: dict[str, Any],
    fps: float | None = None,
) -> dict[str, Any]:
    fps = _positive_number(fps) or resolve_timeline_fps(conn)
    updated: list[dict[str, Any]] = []
    target_ids: set[str] = set()
    for media_kind, db_type in (("video", "Sm2TiVideoClip"), ("audio", "Sm2TiAudioClip")):
        selected = selection.get(media_kind)
        item_refs = selected if isinstance(selected, list) else [selected]
        for item_ref in item_refs:
            if not isinstance(item_ref, LiveItemRef):
                continue
            row = db_timeline_rows.find_ti_item_row(cursor, item=item_ref, db_type=db_type, timeline_name=timeline_name)
            row_dict = dict(row)
            plan = _effective_plan_for_row(row_dict, fps=fps, options=options)
            effect_filters = _clip_speed_effect_filter_update(
                cursor,
                row=row_dict,
                media_kind=media_kind,
                enabled=bool(options.get("retime_requested")),
            )
            pitch = _pitch_correction_update(cursor, row=row_dict, enabled=options.get("pitch_correction") if media_kind == "audio" else None)
            updates: dict[str, Any] = {
                "MediaTimemapBA": sqlite3.Binary(plan["timemap"]),
                "Duration": str(plan["new_duration"]),
            }
            updates.update(effect_filters.get("updates") or {})
            updates.update(pitch.get("updates") or {})
            db_timeline_rows.update_row(cursor, "Sm2TiItem", "Sm2TiItem_id", row["Sm2TiItem_id"], updates)
            target_ids.add(str(row["Sm2TiItem_id"]))
            updated.append(
                {
                "media_kind": media_kind,
                "item_id": row["Sm2TiItem_id"],
                "db_type": db_type,
                "name": row["Name"],
                "track_type": item_ref.track_type,
                "track_index": item_ref.track_index,
                "start": item_ref.start,
                "old_duration": plan["old_duration"],
                "new_duration": plan["new_duration"],
                "source_duration_frames": plan["source_duration_frames"],
                "speed_multiplier": plan["speed_multiplier"],
                "speed_percent": plan["speed_percent"],
                "reverse_speed": bool(options["reverse_speed"]),
                "freeze_frame": bool(options["freeze_frame"]),
                "pitch_correction": {key: value for key, value in pitch.items() if key != "updates"},
                "effect_filters": {key: value for key, value in effect_filters.items() if key != "updates"},
                "keyframes": {
                    "mode": options["keyframes"],
                    "applied": bool(options.get("retime_requested")),
                    "reason": "gui_mode_has_no_persistent_db_flag",
                },
                "old_timemap": retime_db.timemap_blob_summary(row_dict.get("MediaTimemapBA")),
                "new_timemap": retime_db.timemap_blob_summary(plan["timemap"]),
                "before_state": normalized_time_map_state(row_dict, fps=fps, record_start_frame=item_ref.start, fallback_duration_frames=item_ref.duration),
                "after_state": normalized_time_map_state(
                    {**row_dict, "Duration": str(plan["new_duration"]), "MediaTimemapBA": plan["timemap"]},
                    fps=fps,
                    record_start_frame=item_ref.start,
                    fallback_duration_frames=plan["new_duration"],
                ),
                }
            )
    if not updated:
        raise ValidationError("Clip speed DB plan did not contain any patchable targets.")

    primary = next((entry for entry in updated if entry["media_kind"] == "video"), updated[0])
    delta_frames = int(primary["new_duration"]) - int(primary["old_duration"])
    anchor_end = int(primary["start"]) + int(primary["old_duration"])
    ripple = (
        _apply_ripple_shift(
            cursor,
            timeline_name=timeline_name,
            anchor_end=anchor_end,
            delta_frames=delta_frames,
            target_ids=target_ids,
        )
        if options.get("ripple_timeline")
        else {"enabled": False, "delta_frames": delta_frames, "shifted": []}
    )
    return {
        "operation": "clip-speed",
        "timeline_name": timeline_name,
        "options": {
            "speed_multiplier": options.get("multiplier"),
            "speed_percent": options.get("speed_percent"),
            "frames_per_second": options.get("frames_per_second"),
            "duration": options.get("duration"),
            "ripple_timeline": bool(options.get("ripple_timeline")),
            "reverse_speed": bool(options.get("reverse_speed")),
            "freeze_frame": bool(options.get("freeze_frame")),
            "pitch_correction": options.get("pitch_correction"),
            "keyframes": options.get("keyframes"),
        },
        "updated": updated,
        "ripple": ripple,
        "speed_multiplier": primary["speed_multiplier"],
        "speed_percent": primary["speed_percent"],
        "duration_frames": primary["new_duration"],
    }


def preview_clip_speed_render_updates(
    conn: Any,
    *,
    selection: dict[str, LiveItemRef | None],
    timeline_name: str | None,
    options: dict[str, Any],
    fps: float,
) -> list[dict[str, Any]]:
    """Read the video row and derive the exact before/after map before closing the project."""

    current_db = resolve_current_disk_project_db(conn, allow_project_name_inference=True)
    connection = sqlite3.connect(str(current_db["project_db_path"]), timeout=2.0)
    connection.row_factory = sqlite3.Row
    try:
        item = selection.get("video")
        if not isinstance(item, LiveItemRef):
            raise ValidationError("Retime rendered proof requires an exact video target.")
        row = db_timeline_rows.find_ti_item_row(
            connection.cursor(), item=item, db_type="Sm2TiVideoClip", timeline_name=timeline_name
        )
        row_dict = dict(row)
        plan = _effective_plan_for_row(row_dict, fps=fps, options=options)
        return [{
            "media_kind": "video",
            "item_id": row["Sm2TiItem_id"],
            "name": row["Name"],
            "track_type": item.track_type,
            "track_index": item.track_index,
            "start": item.start,
            "old_duration": plan["old_duration"],
            "new_duration": plan["new_duration"],
            "before_state": normalized_time_map_state(
                row_dict, fps=fps, record_start_frame=item.start, fallback_duration_frames=item.duration
            ),
            "after_state": normalized_time_map_state(
                {**row_dict, "Duration": str(plan["new_duration"]), "MediaTimemapBA": plan["timemap"]},
                fps=fps,
                record_start_frame=item.start,
                fallback_duration_frames=plan["new_duration"],
            ),
        }]
    finally:
        connection.close()


def verify_clip_speed_mutation(
    fresh_conn: Any,
    mutation_result: dict[str, Any],
    session: Any,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = [{"name": "project_db_route", "ok": True}]
    connection = sqlite3.connect(session.project_db_path, timeout=2.0)
    connection.row_factory = sqlite3.Row
    try:
        for update in mutation_result.get("updated") or []:
            row = connection.execute(
                "SELECT Sm2TiItem_id, Duration, MediaTimemapBA FROM Sm2TiItem WHERE Sm2TiItem_id = ?",
                (update["item_id"],),
            ).fetchone()
            row_ok = row is not None
            duration_ok = row_ok and str(row["Duration"]) == str(update["new_duration"])
            timemap_ok = row_ok and retime_db.timemap_blob_summary(row["MediaTimemapBA"])["hex"] == update["new_timemap"]["hex"]
            checks.append(
                {
                    "name": f"{update['media_kind']}_{update['item_id']}",
                    "ok": bool(row_ok and duration_ok and timemap_ok),
                    "row_present": bool(row_ok),
                    "duration_ok": bool(duration_ok),
                    "timemap_match": bool(timemap_ok),
                }
            )
    finally:
        connection.close()
    failed = [check for check in checks if not check.get("ok")]
    if failed:
        raise APICallFailed(
            "Clip speed DB verification failed after project reopen.",
            details={"checks": checks, "updated": mutation_result.get("updated")},
            recoverability="manual",
        )
    return {"status": "verified", "checks": checks}


def inspect_clip_speed(conn: Any, *, clip_name: str | None = None, at: str | None = None) -> dict[str, Any]:
    current_db = resolve_current_disk_project_db(conn, allow_project_name_inference=True)
    project_db_path = str(current_db["project_db_path"])
    selection = db_timeline_selection.resolve_linked_av_group(conn, clip_name=clip_name, at=at)
    timeline_name = _timeline_name(conn)
    fps = resolve_timeline_fps(conn)
    rows: list[dict[str, Any]] = []
    connection = sqlite3.connect(project_db_path, timeout=2.0)
    connection.row_factory = sqlite3.Row
    try:
        cursor = connection.cursor()
        for media_kind, db_type in (("video", "Sm2TiVideoClip"), ("audio", "Sm2TiAudioClip")):
            item_ref = selection.get(media_kind)
            if not isinstance(item_ref, LiveItemRef):
                continue
            row = db_timeline_rows.find_ti_item_row(cursor, item=item_ref, db_type=db_type, timeline_name=timeline_name)
            row_dict = {key: row[key] for key in row.keys()}
            state = infer_timemap_state(row_dict, fps=_source_fps(row_dict, fallback_fps=fps), record_fps=fps, fallback_duration_frames=item_ref.duration)
            rows.append(
                {
                    "media_kind": media_kind,
                    "item": asdict(item_ref),
                    "item_id": row["Sm2TiItem_id"],
                    "db_type": db_type,
                    "duration_frames": state["duration_frames"],
                    "source_duration_frames": state["source_duration_frames"],
                    "speed_multiplier": state["speed_multiplier"],
                    "speed_percent": state["speed_percent"],
                    "reverse_speed": state["reverse_speed"],
                    "freeze_frame": state["freeze_frame"],
                    "pitch_correction": _pitch_state_from_row(row_dict) if media_kind == "audio" else None,
                    "timemap": state["timemap"],
                }
            )
    finally:
        connection.close()
    primary = next((row for row in rows if row["media_kind"] == "video"), rows[0] if rows else None)
    if primary is None:
        raise ValidationError("Could not inspect a selected clip speed DB row.", details={"clip_name": clip_name, "at": at})
    return {
        "speed": primary["speed_percent"],
        "multiplier": primary["speed_multiplier"],
        "speed_percent": primary["speed_percent"],
        "duration_frames": primary["duration_frames"],
        "source_duration_frames": primary["source_duration_frames"],
        "reverse_speed": primary["reverse_speed"],
        "freeze_frame": primary["freeze_frame"],
        "pitch_correction": next((row["pitch_correction"] for row in rows if row["media_kind"] == "audio"), None),
        "current_database": current_db,
        "timeline_name": timeline_name,
        "rows": rows,
    }
