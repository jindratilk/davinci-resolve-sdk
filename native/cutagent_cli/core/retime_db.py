"""Archive-backed MediaTimemapBA builders for Disk DB retime routes."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import math
import struct
import uuid
from typing import Any, Sequence

import zstandard as zstd

from ..errors import ValidationError
from ..fixtures import db_workaround_payloads as fixture_payloads


_FREEZE_TEMPLATE = bytes.fromhex(fixture_payloads.RETIME_FREEZE_TEMPLATE_HEX)
_REVERSE_TEMPLATE = bytes.fromhex(fixture_payloads.RETIME_REVERSE_TEMPLATE_HEX)

_OLD_FREEZE_UUID = "55e99288-07b2-4571-9f3d-aa2f9340f7a3"
_OLD_REVERSE_UUID = "88333b76-71a4-420c-9774-1e62a8979b92"

_OLD_DURATION_SECONDS = struct.unpack(">d", bytes.fromhex("4013D55555555555"))[0]


@dataclass(frozen=True)
class TimeMapPoint:
    index: int
    x: float
    y: float
    interp: int = 0
    x_in: float = 0.0
    y_in: float = 0.0
    x_out: float = 0.0
    y_out: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SpeedRampTimeMap:
    media_timemap_ba: bytes
    duration_frames: int
    output_duration_frames: int
    source_duration_frames: int
    fps: float
    ramp_frames: int
    peak_speed: float
    curve: str
    direction: str
    reverse: bool
    x_max: float
    y_max: float
    keyframes: tuple[TimeMapPoint, ...]
    timemap_encoding: str = "qmap"
    builder_mode: str = "transition"

    def to_plan(self, *, include_hex: bool = False) -> dict[str, Any]:
        payload = {
            "duration_frames": self.duration_frames,
            "output_duration_frames": self.output_duration_frames,
            "source_duration_frames": self.source_duration_frames,
            "source_extra_frames_required": max(0, self.source_duration_frames - self.duration_frames),
            "fps": self.fps,
            "ramp_frames": self.ramp_frames,
            "peak_speed": self.peak_speed,
            "curve": self.curve,
            "direction": self.direction,
            "reverse": self.reverse,
            "builder_mode": self.builder_mode,
            "x_max_seconds": self.x_max,
            "y_max_seconds": self.y_max,
            "timemap_encoding": self.timemap_encoding,
            "media_timemap_ba_length": len(self.media_timemap_ba),
            "keyframes": [point.to_dict() for point in self.keyframes],
        }
        if include_hex:
            payload["media_timemap_ba_hex"] = self.media_timemap_ba.hex().upper()
        return payload


def default_timemap(duration_frames: int, fps: float) -> bytes:
    safe_fps = float(fps or 25.0)
    duration_seconds = max(0.0, (int(duration_frames) - 1) / safe_fps)
    return b"\x02" + struct.pack(">d", duration_seconds)


def _replace_uuid_bytes(blob: bytes, old_uuid: str, new_uuid: str) -> bytes:
    return blob.replace(str(old_uuid).encode("utf-16-be"), str(new_uuid).encode("utf-16-be"))


def _replace_double(blob: bytes, old_value: float, new_value: float) -> bytes:
    return blob.replace(struct.pack(">d", float(old_value)), struct.pack(">d", float(new_value)))


def retimed_duration_frames(duration_frames: int, speed_multiplier: float) -> int:
    speed = float(speed_multiplier)
    if not math.isfinite(speed) or speed <= 0:
        raise ValidationError("Speed multiplier must be greater than 0.", details={"speed_multiplier": speed_multiplier})
    return max(1, int(round(float(duration_frames) / speed)))


def build_constant_speed_timemap(duration_frames: int, fps: float, speed_multiplier: float) -> bytes:
    speed = float(speed_multiplier)
    if not math.isfinite(speed) or speed <= 0:
        raise ValidationError("Speed multiplier must be greater than 0.", details={"speed_multiplier": speed_multiplier})
    output_duration = retimed_duration_frames(int(duration_frames), speed)
    return build_constant_retime_timemap(int(duration_frames), output_duration, fps)


def build_freeze_timemap(duration_frames: int | None = None, fps: float | None = None) -> bytes:
    payload = _replace_uuid_bytes(bytes(_FREEZE_TEMPLATE), _OLD_FREEZE_UUID, str(uuid.uuid4()))
    if duration_frames is None:
        return payload
    input_seconds = max(0.0, (int(duration_frames) - 1) / float(fps or 25.0))
    return _replace_double(payload, _OLD_DURATION_SECONDS, input_seconds)


def build_reverse_timemap(duration_frames: int, fps: float) -> bytes:
    input_seconds = max(0.0, (int(duration_frames) - 1) / float(fps or 25.0))
    payload = bytes(_REVERSE_TEMPLATE)
    payload = _replace_uuid_bytes(payload, _OLD_REVERSE_UUID, str(uuid.uuid4()))
    payload = _replace_double(payload, _OLD_DURATION_SECONDS, input_seconds)
    return payload


def build_constant_retime_timemap(
    source_duration_frames: int,
    output_duration_frames: int,
    fps: float,
    *,
    reverse: bool = False,
    source_fps: float | None = None,
) -> bytes:
    """Build a two-point DaVinci Resolve Sm2TimeMap for GUI-style constant retimes."""
    safe_source_duration = int(source_duration_frames)
    safe_output_duration = int(output_duration_frames)
    safe_fps = float(fps or 25.0)
    if safe_source_duration <= 0 or safe_output_duration <= 0:
        raise ValidationError(
            "Retime source and output durations must be greater than 0.",
            details={
                "source_duration_frames": source_duration_frames,
                "output_duration_frames": output_duration_frames,
            },
            recoverability="not_applicable",
        )
    if not math.isfinite(safe_fps) or safe_fps <= 0:
        raise ValidationError("Timeline FPS must be greater than 0.", details={"fps": fps}, recoverability="not_applicable")

    x_max = max(0.0, (safe_output_duration - 1) / safe_fps)
    safe_source_fps = float(source_fps or safe_fps)
    if not math.isfinite(safe_source_fps) or safe_source_fps <= 0:
        raise ValidationError("Source FPS must be greater than 0.", details={"source_fps": source_fps}, recoverability="not_applicable")
    y_max = max(0.0, (safe_source_duration - 1) / safe_source_fps)
    if reverse:
        points = (
            TimeMapPoint(0, 0.0, y_max),
            TimeMapPoint(1, x_max, 0.0),
        )
    else:
        points = (
            TimeMapPoint(0, 0.0, 0.0),
            TimeMapPoint(1, x_max, y_max),
        )
    return _encode_sm2_time_map(
        x_max=x_max,
        y_max=y_max,
        last_valid_y_offset=y_max,
        keyframes=points,
    )


def _q_int(value: int) -> bytes:
    return struct.pack(">i", int(value))


def _q_uint(value: int) -> bytes:
    return struct.pack(">I", int(value))


def _q_double(value: float) -> bytes:
    return struct.pack(">d", float(value))


def _q_string(value: str) -> bytes:
    encoded = str(value).encode("utf-16-be")
    return _q_uint(len(encoded)) + encoded


def _q_variant(type_id: int, payload: bytes) -> bytes:
    return _q_uint(type_id) + b"\x00" + payload


def _q_variant_int(value: int) -> bytes:
    return _q_variant(2, _q_int(value))


def _q_variant_double(value: float) -> bytes:
    return _q_variant(6, _q_double(value))


def _q_variant_string(value: str) -> bytes:
    return _q_variant(10, _q_string(value))


def _q_variant_bytearray(value: bytes) -> bytes:
    return _q_variant(12, _q_uint(len(value)) + bytes(value))


def _q_map(entries: list[tuple[str, bytes]]) -> bytes:
    payload = _q_uint(1) + _q_uint(len(entries))
    for key, value in entries:
        payload += _q_string(key)
        payload += value
    return payload


def _pb_varint(value: int) -> bytes:
    number = int(value)
    if number < 0:
        raise ValueError("protobuf varint cannot encode negative values")
    out = bytearray()
    while True:
        byte = number & 0x7F
        number >>= 7
        if number:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def _pb_field_key(field_number: int, wire_type: int) -> bytes:
    return _pb_varint((int(field_number) << 3) | int(wire_type))


def _pb_fixed64(field_number: int, value: float) -> bytes:
    return _pb_field_key(field_number, 1) + struct.pack("<d", float(value))


def _pb_bytes(field_number: int, value: bytes) -> bytes:
    payload = bytes(value)
    return _pb_field_key(field_number, 2) + _pb_varint(len(payload)) + payload


def _retime_keyframe_bezier_bytes(point: TimeMapPoint) -> bytes:
    """Encode DaVinci Resolve's 48-byte Sm2Bezier payload.

    GUI captures from DaVinci Resolve Studio 21 store incoming and outgoing
    handle *deltas* in the first two pairs. The anchor is stored separately in
    protobuf fields 1/2. The last pair is zero in the captured native curves;
    it is not the outgoing handle. See the native fixture regression tests.
    """
    return struct.pack("<6d", point.x_in, point.y_in, point.x_out, point.y_out, 0.0, 0.0)


def _encode_retime_keyframe_proto(point: TimeMapPoint) -> bytes:
    payload = bytearray()
    if abs(point.x) > 1e-12:
        payload += _pb_fixed64(1, point.x)
    if abs(point.y) > 1e-12:
        payload += _pb_fixed64(2, point.y)
    payload += _pb_bytes(3, _retime_keyframe_bezier_bytes(point))
    return bytes(payload)


def _encode_retime_keyframe_position_proto(point: TimeMapPoint) -> bytes:
    payload = bytearray()
    if abs(point.x) > 1e-12:
        payload += _pb_fixed64(1, point.x)
    if abs(point.y) > 1e-12:
        payload += _pb_fixed64(2, point.y)
    return bytes(payload)


def _encode_retime_keyframe_list_proto(points: tuple[TimeMapPoint, ...]) -> bytes:
    payload = bytearray()
    for point in points:
        payload += _pb_bytes(1, _encode_retime_keyframe_proto(point))
    compressed = zstd.ZstdCompressor(level=3).compress(bytes(payload))
    return b"\x81" + compressed


def _encode_prefixed_retime_keyframe_list_proto(
    points: tuple[TimeMapPoint, ...],
    *,
    empty_first: bool = False,
) -> bytes:
    payload = bytearray()
    for index, point in enumerate(points):
        raw = b"" if empty_first and index == 0 else _encode_retime_keyframe_position_proto(point)
        payload += _pb_bytes(1, raw)
    return b"\x80" + bytes(payload)


def normalize_curve(curve: str) -> str:
    normalized = str(curve or "").strip().lower().replace("_", "-")
    aliases = {
        "none": "linear",
        "no-ease": "linear",
        "straight": "linear",
        "ease": "normal-s",
        "ease-in-out": "normal-s",
        "normal": "normal-s",
        "s": "normal-s",
        "s-curve": "normal-s",
        "smooth": "normal-s",
        "smooth-s": "normal-s",
        "sharp": "sharp-s",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized not in {"linear", "normal-s", "sharp-s"}:
        raise ValidationError(
            "--curve must be one of: linear, normal-s, sharp-s.",
            details={"curve": curve, "supported": ["linear", "normal-s", "sharp-s"]},
            recoverability="not_applicable",
        )
    return normalized


def _normalize_curve(curve: str) -> str:
    return normalize_curve(curve)


def _normalize_direction(direction: str) -> str:
    normalized = str(direction or "").strip().lower().replace("_", "-")
    if normalized not in {"outgoing", "incoming"}:
        raise ValidationError(
            "Speed-ramp direction must be outgoing or incoming.",
            details={"direction": direction, "supported": ["outgoing", "incoming"]},
            recoverability="not_applicable",
        )
    return normalized


def _validate_speed_ramp_inputs(
    *,
    duration_frames: int,
    fps: float,
    ramp_frames: int,
    peak_speed: float,
) -> tuple[int, float, int, float]:
    safe_duration = int(duration_frames)
    safe_fps = float(fps or 25.0)
    safe_ramp_frames = int(ramp_frames)
    safe_peak = float(peak_speed)
    if safe_duration <= 1:
        raise ValidationError(
            "Speed-ramp target clip must be at least 2 frames long.",
            details={"duration_frames": duration_frames},
            recoverability="not_applicable",
        )
    if not math.isfinite(safe_fps) or safe_fps <= 0:
        raise ValidationError("Timeline FPS must be greater than 0.", details={"fps": fps}, recoverability="not_applicable")
    if safe_ramp_frames <= 0:
        raise ValidationError(
            "Speed-ramp frame count must be greater than 0.",
            details={"ramp_frames": ramp_frames},
            recoverability="not_applicable",
        )
    if not math.isfinite(safe_peak) or safe_peak <= 1.0:
        raise ValidationError(
            "Peak speed must be greater than 1x.",
            details={"peak_speed": peak_speed},
            recoverability="not_applicable",
        )
    return safe_duration, safe_fps, safe_ramp_frames, safe_peak


def _last_valid_seconds(duration_frames: int, fps: float) -> float:
    return max(0.0, (int(duration_frames) - 1) / float(fps or 25.0))


def _source_frames_from_y_max(y_max: float, fps: float) -> int:
    return max(1, int(round(float(y_max) * float(fps or 25.0))) + 1)


def _ramp_source_delta_seconds(ramp_seconds: float, peak_speed: float) -> float:
    return float(ramp_seconds) * ((1.0 + float(peak_speed)) / 2.0)


def _curve_handle_factor(curve: str) -> float:
    # A linear change in playback speed integrates to a quadratic source-time
    # curve. One-third endpoint-tangent handles encode that quadratic exactly.
    # This is deliberately the same geometry as the existing normal-s preset;
    # normal-s and sharp-s behavior must remain stable for existing callers.
    return 1.0 / 3.0 if curve in {"linear", "normal-s"} else 0.18


def normalize_ease_mode(ease: str | None) -> str:
    normalized = str(ease or "in-out").strip().lower().replace("_", "-")
    aliases = {
        "": "in-out",
        "auto": "in-out",
        "default": "in-out",
        "smooth": "in-out",
        "s": "in-out",
        "s-curve": "in-out",
        "ease": "in-out",
        "in-out": "in-out",
        "ease-in-out": "in-out",
        "inout": "in-out",
        "both": "in-out",
        "all": "in-out",
        "none": "none",
        "off": "none",
        "linear": "none",
        "no-ease": "none",
        "in": "in",
        "ease-in": "in",
        "end": "in",
        "out": "out",
        "ease-out": "out",
        "start": "out",
    }
    result = aliases.get(normalized)
    if result is None:
        raise ValidationError(
            "Speed-ramp ease must be one of: none, in, out, in-out.",
            details={"ease": ease, "supported": ["none", "in", "out", "in-out"]},
            recoverability="not_applicable",
        )
    return result


def _apply_ramp_handles(
    points: list[TimeMapPoint],
    *,
    start_index: int,
    end_index: int,
    start_speed: float,
    end_speed: float,
    curve: str,
    start_handle: tuple[float, float] | None = None,
    end_handle: tuple[float, float] | None = None,
    ease: str = "in-out",
    start_interp: int | None = None,
    end_interp: int | None = None,
) -> list[TimeMapPoint]:
    if start_index < 0 or end_index >= len(points) or start_index >= end_index:
        return points
    start = points[start_index]
    end = points[end_index]
    span = max(0.0, float(end.x) - float(start.x))
    if span <= 0:
        return points
    handle_x = span * _curve_handle_factor(curve)
    normalized_ease = normalize_ease_mode(ease)
    use_start_handle = normalized_ease in {"out", "in-out"} or start_handle is not None
    use_end_handle = normalized_ease in {"in", "in-out"} or end_handle is not None
    start_x_out, start_y_out = (
        start_handle
        if start_handle is not None
        else ((handle_x, float(start_speed) * handle_x) if use_start_handle else (0.0, 0.0))
    )
    end_x_in, end_y_in = (
        end_handle
        if end_handle is not None
        else ((-handle_x, -float(end_speed) * handle_x) if use_end_handle else (0.0, 0.0))
    )
    points[start_index] = replace(
        start,
        interp=start_interp if start_interp is not None else start.interp,
        x_out=start_x_out,
        y_out=start_y_out,
    )
    points[end_index] = replace(
        end,
        interp=end_interp if end_interp is not None else end.interp,
        x_in=end_x_in,
        y_in=end_y_in,
    )
    return points


def _dedupe_points(points: list[TimeMapPoint]) -> tuple[TimeMapPoint, ...]:
    deduped: list[TimeMapPoint] = []
    for point in points:
        if deduped and abs(deduped[-1].x - point.x) < 1e-9:
            deduped[-1] = replace(point, index=deduped[-1].index)
        else:
            deduped.append(point)
    return tuple(replace(point, index=index) for index, point in enumerate(deduped))


def _encode_time_map_point(point: TimeMapPoint) -> bytes:
    return _q_map(
        [
            ("interp", _q_variant_int(point.interp)),
            ("YOut", _q_variant_double(point.y_out)),
            ("YIn", _q_variant_double(point.y_in)),
            ("Y", _q_variant_double(point.y)),
            ("XOut", _q_variant_double(point.x_out)),
            ("XIn", _q_variant_double(point.x_in)),
            ("X", _q_variant_double(point.x)),
        ]
    )


def _encode_keyframes(points: tuple[TimeMapPoint, ...]) -> bytes:
    entries = [
        (str(index), _q_variant_bytearray(_encode_time_map_point(points[index])))
        for index in reversed(range(len(points)))
    ]
    return _q_map(entries)


def _encode_sm2_time_map(*, x_max: float, y_max: float, last_valid_y_offset: float, keyframes: tuple[TimeMapPoint, ...]) -> bytes:
    return _q_map(
        [
            ("YMax", _q_variant_double(y_max)),
            ("XMax", _q_variant_double(x_max)),
            ("UniqueId", _q_variant_string(str(uuid.uuid4()))),
            ("LastValidYOffset", _q_variant_double(last_valid_y_offset)),
            ("KeyframesBA", _q_variant_bytearray(_encode_keyframes(keyframes))),
            ("DbType", _q_variant_string("Sm2TimeMap")),
        ]
    )


def _encode_sm2_time_map_compressed_proto(*, x_max: float, y_max: float, keyframes: tuple[TimeMapPoint, ...], last_valid_y_offset: float | None = None) -> bytes:
    return _q_map(
        [
            ("YMin", _q_variant_double(-1.0)),
            ("YMax", _q_variant_double(-1.0)),
            ("XMax", _q_variant_double(x_max)),
            ("UniqueId", _q_variant_string(str(uuid.uuid4()))),
            ("LastValidYOffset", _q_variant_double(y_max if last_valid_y_offset is None else last_valid_y_offset)),
            ("KeyframesBA", _q_variant_bytearray(_encode_retime_keyframe_list_proto(keyframes))),
            ("DbType", _q_variant_string("Sm2TimeMap")),
        ]
    )


def _encode_sm2_time_map_prefixed_proto(*, x_max: float, y_max: float, keyframes: tuple[TimeMapPoint, ...]) -> bytes:
    return _q_map(
        [
            ("YMin", _q_variant_double(-1.0)),
            ("YMax", _q_variant_double(-1.0)),
            ("XMax", _q_variant_double(x_max)),
            ("UniqueId", _q_variant_string(str(uuid.uuid4()))),
            ("LastValidYOffset", _q_variant_double(y_max)),
            ("KeyframesBA", _q_variant_bytearray(_encode_prefixed_retime_keyframe_list_proto(keyframes, empty_first=True))),
            ("DbType", _q_variant_string("Sm2TimeMap")),
        ]
    )


def build_elastic_wave_timemap(
    duration_frames: int,
    fps: float,
    *,
    at_seconds: float,
    stretch_ratio: float = 1.0,
) -> SpeedRampTimeMap:
    safe_duration = int(duration_frames)
    safe_fps = float(fps or 25.0)
    safe_at = float(at_seconds)
    safe_stretch = float(stretch_ratio)
    if safe_duration <= 1:
        raise ValidationError(
            "Elastic wave timemap target clip must be at least 2 frames long.",
            details={"duration_frames": duration_frames},
            recoverability="not_applicable",
        )
    if not math.isfinite(safe_fps) or safe_fps <= 0:
        raise ValidationError("Timeline FPS must be greater than 0.", details={"fps": fps}, recoverability="not_applicable")
    if not math.isfinite(safe_at) or safe_at < 0.0:
        raise ValidationError(
            "Elastic wave anchor time must be a finite non-negative value.",
            details={"at_seconds": at_seconds},
            recoverability="not_applicable",
        )
    if not math.isfinite(safe_stretch) or safe_stretch <= 0.0:
        raise ValidationError(
            "Elastic wave stretch ratio must be greater than 0.",
            details={"stretch_ratio": stretch_ratio},
            recoverability="not_applicable",
        )

    x_max = safe_duration / safe_fps
    anchor_x = min(safe_at, x_max)
    anchor_y = anchor_x * safe_stretch
    y_max = x_max * safe_stretch
    points = (
        TimeMapPoint(0, 0.0, 0.0),
        TimeMapPoint(1, anchor_x, anchor_y),
        TimeMapPoint(2, x_max, y_max),
    )
    payload = _encode_sm2_time_map_prefixed_proto(x_max=x_max, y_max=y_max, keyframes=points)
    return SpeedRampTimeMap(
        media_timemap_ba=payload,
        duration_frames=safe_duration,
        output_duration_frames=safe_duration,
        source_duration_frames=max(1, int(round(y_max * safe_fps))),
        fps=safe_fps,
        ramp_frames=max(1, int(round(anchor_x * safe_fps))),
        peak_speed=safe_stretch,
        curve="elastic-wave",
        direction="outgoing",
        reverse=False,
        x_max=x_max,
        y_max=y_max,
        keyframes=points,
        timemap_encoding="prefixed-proto",
        builder_mode="elastic_wave",
    )


def build_speed_ramp_timemap(
    duration_frames: int,
    fps: float,
    *,
    ramp_frames: int,
    peak_speed: float,
    curve: str = "sharp-s",
    direction: str = "outgoing",
    reverse: bool = False,
    start_speed: float | None = None,
    end_speed: float | None = None,
    start_handle: tuple[float, float] | None = None,
    end_handle: tuple[float, float] | None = None,
    ease: str = "in-out",
    start_interp: int | None = None,
    end_interp: int | None = None,
) -> SpeedRampTimeMap:
    """Build a DaVinci Resolve Sm2TimeMap payload for a single variable-speed ramp."""
    safe_duration, safe_fps, safe_ramp_frames, safe_peak = _validate_speed_ramp_inputs(
        duration_frames=duration_frames,
        fps=fps,
        ramp_frames=ramp_frames,
        peak_speed=peak_speed,
    )
    normalized_curve = _normalize_curve(curve)
    normalized_direction = _normalize_direction(direction)
    x_max = _last_valid_seconds(safe_duration, safe_fps)
    ramp_seconds = min(float(safe_ramp_frames), float(safe_duration - 1)) / safe_fps

    if normalized_direction == "outgoing":
        safe_start_speed = _validate_segment_speed(1.0 if start_speed is None else start_speed, field="start_speed")
        safe_end_speed = _validate_segment_speed(safe_peak if end_speed is None else end_speed, field="end_speed")
        ramp_delta = float(ramp_seconds) * ((safe_start_speed + safe_end_speed) / 2.0)
        ramp_start_x = max(0.0, x_max - ramp_seconds)
        ramp_start_y = ramp_start_x * safe_start_speed
        y_max = ramp_start_y + ramp_delta
        points = _dedupe_points(
            [
                TimeMapPoint(0, 0.0, 0.0),
                TimeMapPoint(1, ramp_start_x, ramp_start_y),
                TimeMapPoint(2, x_max, y_max),
            ]
        )
        mutable_points = list(points)
        _apply_ramp_handles(
            mutable_points,
            start_index=max(0, len(mutable_points) - 2),
            end_index=len(mutable_points) - 1,
            start_speed=safe_start_speed,
            end_speed=safe_end_speed,
            curve=normalized_curve,
            start_handle=start_handle,
            end_handle=end_handle,
            ease=ease,
            start_interp=start_interp,
            end_interp=end_interp,
        )
        points = tuple(mutable_points)
    else:
        safe_start_speed = _validate_segment_speed(safe_peak if start_speed is None else start_speed, field="start_speed")
        safe_end_speed = _validate_segment_speed(1.0 if end_speed is None else end_speed, field="end_speed")
        ramp_delta = float(ramp_seconds) * ((safe_start_speed + safe_end_speed) / 2.0)
        ramp_end_x = min(x_max, ramp_seconds)
        normal_tail = max(0.0, x_max - ramp_end_x)
        y_max = ramp_delta + (normal_tail * safe_end_speed)
        if reverse:
            points = _dedupe_points(
                [
                    TimeMapPoint(0, 0.0, y_max),
                    TimeMapPoint(1, ramp_end_x, y_max - ramp_delta),
                    TimeMapPoint(2, x_max, 0.0),
                ]
            )
            handle_start_speed = -safe_start_speed
            handle_end_speed = -safe_end_speed
        else:
            points = _dedupe_points(
                [
                    TimeMapPoint(0, 0.0, 0.0),
                    TimeMapPoint(1, ramp_end_x, ramp_delta),
                    TimeMapPoint(2, x_max, y_max),
                ]
            )
            handle_start_speed = safe_start_speed
            handle_end_speed = safe_end_speed
        mutable_points = list(points)
        _apply_ramp_handles(
            mutable_points,
            start_index=0,
            end_index=min(1, len(mutable_points) - 1),
            start_speed=handle_start_speed,
            end_speed=handle_end_speed,
            curve=normalized_curve,
            start_handle=start_handle,
            end_handle=end_handle,
            ease=ease,
            start_interp=start_interp,
            end_interp=end_interp,
        )
        points = tuple(mutable_points)

    use_raw_qmap_interp = start_interp is not None or end_interp is not None
    if use_raw_qmap_interp:
        payload = _encode_sm2_time_map(x_max=x_max, y_max=y_max, last_valid_y_offset=y_max, keyframes=points)
        timemap_encoding = "qmap"
    else:
        payload = _encode_sm2_time_map_compressed_proto(x_max=x_max, y_max=y_max, keyframes=points)
        timemap_encoding = "compressed-proto"
    return SpeedRampTimeMap(
        media_timemap_ba=payload,
        duration_frames=safe_duration,
        output_duration_frames=safe_duration,
        source_duration_frames=_source_frames_from_y_max(y_max, safe_fps),
        fps=safe_fps,
        ramp_frames=safe_ramp_frames,
        peak_speed=max(safe_peak, safe_start_speed, safe_end_speed),
        curve=normalized_curve,
        direction=normalized_direction,
        reverse=bool(reverse),
        x_max=x_max,
        y_max=y_max,
        keyframes=points,
        timemap_encoding=timemap_encoding,
    )


def _validate_segment_speed(value: float, *, field: str) -> float:
    speed = float(value)
    if not math.isfinite(speed) or speed <= 0:
        raise ValidationError(
            "Speed-ramp segment speeds must be greater than 0x.",
            details={field: value},
            recoverability="not_applicable",
        )
    return speed


def build_explicit_speed_ramp_timemap(
    duration_frames: int,
    fps: float,
    *,
    points: Sequence[TimeMapPoint],
    direction: str = "outgoing",
    reverse: bool = False,
    curve: str = "custom",
) -> SpeedRampTimeMap:
    """Build a DaVinci Resolve Sm2TimeMap payload from explicit GUI-like point values."""
    safe_duration = int(duration_frames)
    safe_fps = float(fps or 25.0)
    if safe_duration <= 1:
        raise ValidationError(
            "Speed-ramp target clip must be at least 2 frames long.",
            details={"duration_frames": duration_frames},
            recoverability="not_applicable",
        )
    if not math.isfinite(safe_fps) or safe_fps <= 0:
        raise ValidationError("Timeline FPS must be greater than 0.", details={"fps": fps}, recoverability="not_applicable")
    normalized_direction = _normalize_direction(direction)
    normalized_points = tuple(replace(point, index=index) for index, point in enumerate(points))
    if len(normalized_points) < 2:
        raise ValidationError(
            "Explicit speed-ramp points require at least two points.",
            details={"point_count": len(normalized_points)},
            recoverability="not_applicable",
        )
    x_max = _last_valid_seconds(safe_duration, safe_fps)
    previous_x = -math.inf
    for point in normalized_points:
        values = (point.x, point.y, point.x_in, point.y_in, point.x_out, point.y_out)
        if not all(math.isfinite(float(value)) for value in values):
            raise ValidationError("Explicit speed-ramp point values must be finite.", details={"point": point.to_dict()})
        if point.x < -1e-9 or point.x > x_max + 1e-9:
            raise ValidationError(
                "Explicit speed-ramp X values must be inside the clip output duration.",
                details={"point": point.to_dict(), "x_max_seconds": x_max},
                recoverability="not_applicable",
            )
        if point.x <= previous_x:
            raise ValidationError(
                "Explicit speed-ramp points must use strictly increasing X values.",
                details={"point": point.to_dict()},
                recoverability="not_applicable",
            )
        previous_x = point.x

    y_max = max(float(point.y) for point in normalized_points)
    # Native v21 converts legacy QMap handles into extra anchors on reload.
    # Match the current native representation unless raw interpolation codes
    # were explicitly requested (the protobuf does not carry those codes).
    if any(point.interp != 0 for point in normalized_points):
        payload = _encode_sm2_time_map(
            x_max=x_max, y_max=y_max, last_valid_y_offset=y_max, keyframes=normalized_points,
        )
        timemap_encoding = "qmap"
    else:
        payload = _encode_sm2_time_map_compressed_proto(
            x_max=x_max, y_max=y_max, keyframes=normalized_points,
        )
        timemap_encoding = "compressed-proto"
    return SpeedRampTimeMap(
        media_timemap_ba=payload,
        duration_frames=safe_duration,
        output_duration_frames=safe_duration,
        source_duration_frames=_source_frames_from_y_max(y_max, safe_fps),
        fps=safe_fps,
        ramp_frames=max(1, int(round((normalized_points[-1].x - normalized_points[0].x) * safe_fps))),
        peak_speed=_estimate_peak_speed(normalized_points),
        curve=str(curve or "custom"),
        direction=normalized_direction,
        reverse=bool(reverse),
        x_max=x_max,
        y_max=y_max,
        keyframes=normalized_points,
        timemap_encoding=timemap_encoding,
        builder_mode="explicit_points",
    )


def _estimate_peak_speed(points: Sequence[TimeMapPoint]) -> float:
    speeds: list[float] = []
    ordered = list(points)
    for left, right in zip(ordered, ordered[1:]):
        dx = float(right.x) - float(left.x)
        if abs(dx) > 1e-9:
            speeds.append(abs((float(right.y) - float(left.y)) / dx))
    for point in ordered:
        if point.x_out:
            speeds.append(abs(point.y_out / point.x_out))
        if point.x_in:
            speeds.append(abs(point.y_in / point.x_in))
    return max([1.0, *speeds])


def build_speed_ramp_transition_timemaps(
    *,
    outgoing_duration_frames: int,
    incoming_duration_frames: int,
    fps: float,
    out_frames: int,
    in_frames: int,
    peak_speed: float,
    curve: str = "sharp-s",
    reverse_incoming: bool = False,
    outgoing_start_speed: float | None = None,
    outgoing_end_speed: float | None = None,
    incoming_start_speed: float | None = None,
    incoming_end_speed: float | None = None,
    outgoing_start_handle: tuple[float, float] | None = None,
    outgoing_end_handle: tuple[float, float] | None = None,
    incoming_start_handle: tuple[float, float] | None = None,
    incoming_end_handle: tuple[float, float] | None = None,
    outgoing_ease: str = "in-out",
    incoming_ease: str = "in-out",
    outgoing_start_interp: int | None = None,
    outgoing_end_interp: int | None = None,
    incoming_start_interp: int | None = None,
    incoming_end_interp: int | None = None,
    outgoing_points: Sequence[TimeMapPoint] | None = None,
    incoming_points: Sequence[TimeMapPoint] | None = None,
) -> dict[str, SpeedRampTimeMap]:
    """Build outgoing/incoming MediaTimemapBA payloads for a two-clip cut ramp."""
    if outgoing_points:
        outgoing = build_explicit_speed_ramp_timemap(
            outgoing_duration_frames,
            fps,
            points=outgoing_points,
            direction="outgoing",
            reverse=False,
        )
    else:
        outgoing = build_speed_ramp_timemap(
            outgoing_duration_frames,
            fps,
            ramp_frames=out_frames,
            peak_speed=peak_speed,
            curve=curve,
            direction="outgoing",
            reverse=False,
            start_speed=outgoing_start_speed,
            end_speed=outgoing_end_speed,
            start_handle=outgoing_start_handle,
            end_handle=outgoing_end_handle,
            ease=outgoing_ease,
            start_interp=outgoing_start_interp,
            end_interp=outgoing_end_interp,
        )
    if incoming_points:
        incoming = build_explicit_speed_ramp_timemap(
            incoming_duration_frames,
            fps,
            points=incoming_points,
            direction="incoming",
            reverse=reverse_incoming,
        )
    else:
        incoming = build_speed_ramp_timemap(
            incoming_duration_frames,
            fps,
            ramp_frames=in_frames,
            peak_speed=peak_speed,
            curve=curve,
            direction="incoming",
            reverse=reverse_incoming,
            start_speed=incoming_start_speed,
            end_speed=incoming_end_speed,
            start_handle=incoming_start_handle,
            end_handle=incoming_end_handle,
            ease=incoming_ease,
            start_interp=incoming_start_interp,
            end_interp=incoming_end_interp,
        )
    return {
        "outgoing": outgoing,
        "incoming": incoming,
    }


def timemap_source_bounds(points: Sequence[TimeMapPoint]) -> tuple[float, float]:
    """Exact source-coordinate extrema, including peaks between anchors."""
    if any(point.interp != 0 for point in points):
        raise ValidationError("Cannot establish source bounds for an unsupported raw interpolation code.")
    values = [float(point.y) for point in points]
    if not values or not all(math.isfinite(value) for value in values):
        raise ValidationError("Cannot establish finite speed-ramp source bounds.")
    for left, right in zip(points, points[1:]):
        controls = (left.y, left.y + left.y_out, right.y + right.y_in, right.y)
        if not all(math.isfinite(value) for value in controls):
            raise ValidationError("Cannot establish finite speed-ramp source bounds.")
        # Solve at unit scale so large but finite handles cannot overflow the
        # discriminant and hide a source-range excursion.
        scale = max(abs(value) for value in controls) or 1.0
        y0, y1, y2, y3 = (value / scale for value in controls)
        a = -y0 + 3 * y1 - 3 * y2 + y3
        b = 2 * (y0 - 2 * y1 + y2)
        c = y1 - y0
        roots = []
        if abs(a) < 1e-12:
            if abs(b) >= 1e-12:
                roots.append(-c / b)
        else:
            discriminant = b * b - 4 * a * c
            if discriminant >= 0:
                root = math.sqrt(discriminant)
                roots.extend(((-b + root) / (2 * a), (-b - root) / (2 * a)))
        for t in roots:
            if 0 < t < 1:
                mt = 1 - t
                value = (mt**3 * y0 + 3 * mt * mt * t * y1 + 3 * mt * t * t * y2 + t**3 * y3) * scale
                if not math.isfinite(value):
                    raise ValidationError("Cannot establish finite speed-ramp source bounds.")
                values.append(value)
    return min(values), max(values)


def _simple_timemap_fields(blob: bytes) -> dict[str, Any] | None:
    if blob[:1] != b"\x02":
        return None
    if len(blob) == 9:
        return {"type": "simple_default", "last_valid_seconds": struct.unpack(">d", blob[1:9])[0]}
    if len(blob) == 41:
        fields = struct.unpack(">5d", blob[1:])
        # Native v21 captures at 30/60 and 24/30 record/source rates. Retain
        # all fields; only admit the observed zero-offset identity layout.
        if all(math.isfinite(value) for value in fields) and fields[0] >= 0 and fields[2] >= 0 and fields[1] == fields[3] == 0 and fields[0] == fields[4]:
            return {"type": "simple_default", "last_valid_seconds": fields[4], "record_last_valid_seconds": fields[2], "native_fields": list(fields)}
    return None


def timemap_blob_summary(value: Any) -> dict[str, Any]:
    if value in (None, b"", ""):
        return {"length": 0, "hex": "", "is_default_simple": True}
    blob = bytes(value)
    return {
        "length": len(blob),
        "hex": blob.hex().upper(),
        "is_default_simple": _simple_timemap_fields(blob) is not None,
    }


def _read_u32(blob: bytes, offset: int) -> tuple[int, int]:
    if offset + 4 > len(blob):
        raise ValueError("unexpected end while reading uint32")
    return struct.unpack(">I", blob[offset : offset + 4])[0], offset + 4


def _read_i32(blob: bytes, offset: int) -> tuple[int, int]:
    if offset + 4 > len(blob):
        raise ValueError("unexpected end while reading int32")
    return struct.unpack(">i", blob[offset : offset + 4])[0], offset + 4


def _read_double(blob: bytes, offset: int) -> tuple[float, int]:
    if offset + 8 > len(blob):
        raise ValueError("unexpected end while reading double")
    return struct.unpack(">d", blob[offset : offset + 8])[0], offset + 8


def _read_string(blob: bytes, offset: int) -> tuple[str, int]:
    byte_length, offset = _read_u32(blob, offset)
    if offset + byte_length > len(blob):
        raise ValueError("unexpected end while reading string")
    raw = blob[offset : offset + byte_length]
    return raw.decode("utf-16-be"), offset + byte_length


def _read_pb_varint(blob: bytes, offset: int) -> tuple[int, int]:
    shift = 0
    value = 0
    while offset < len(blob):
        byte = blob[offset]
        offset += 1
        value |= (byte & 0x7F) << shift
        if not (byte & 0x80):
            return value, offset
        shift += 7
        if shift > 63:
            raise ValueError("protobuf varint is too long")
    raise ValueError("unexpected end while reading protobuf varint")


def _read_pb_fixed64(blob: bytes, offset: int) -> tuple[float, int]:
    if offset + 8 > len(blob):
        raise ValueError("unexpected end while reading protobuf fixed64")
    return struct.unpack("<d", blob[offset : offset + 8])[0], offset + 8


def _decode_retime_bezier_bytes(raw: bytes, *, x: float, y: float) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "length": len(raw),
        "hex": raw.hex().upper(),
        "is_zero": not any(raw),
    }
    if len(raw) == 48:
        in_x, in_y, out_x, out_y, reserved_x, reserved_y = struct.unpack("<6d", raw)
        payload.update(
            {
                "format": "six_little_endian_doubles",
                "in_x": in_x,
                "in_y": in_y,
                "anchor_x": x,
                "anchor_y": y,
                "out_x": out_x,
                "out_y": out_y,
                "x_in": in_x,
                "y_in": in_y,
                "x_out": out_x,
                "y_out": out_y,
                "reserved_x": reserved_x,
                "reserved_y": reserved_y,
            }
        )
    return payload


def _decode_retime_keyframe_proto(raw: bytes, index: int) -> dict[str, Any]:
    offset = 0
    x = 0.0
    y = 0.0
    bezier = b""
    fields: list[dict[str, Any]] = []
    while offset < len(raw):
        key, offset = _read_pb_varint(raw, offset)
        field = key >> 3
        wire_type = key & 7
        if wire_type == 1:
            value, offset = _read_pb_fixed64(raw, offset)
            fields.append({"field": field, "wire_type": wire_type, "value": value})
            if field == 1:
                x = value
            elif field == 2:
                y = value
            continue
        if wire_type == 2:
            length, offset = _read_pb_varint(raw, offset)
            if offset + length > len(raw):
                raise ValueError("unexpected end while reading protobuf bytes")
            value = bytes(raw[offset : offset + length])
            offset += length
            fields.append({"field": field, "wire_type": wire_type, "length": length, "hex": value.hex().upper()})
            if field == 3:
                bezier = value
            continue
        if wire_type == 0:
            value, offset = _read_pb_varint(raw, offset)
            fields.append({"field": field, "wire_type": wire_type, "value": value})
            continue
        raise ValueError(f"unsupported protobuf wire type {wire_type}")
    decoded_bezier = _decode_retime_bezier_bytes(bezier, x=x, y=y)
    return {
        "index": index,
        "x": x,
        "y": y,
        "x_in": float(decoded_bezier.get("x_in", 0.0)),
        "y_in": float(decoded_bezier.get("y_in", 0.0)),
        "x_out": float(decoded_bezier.get("x_out", 0.0)),
        "y_out": float(decoded_bezier.get("y_out", 0.0)),
        "interp": 0,
        "bezier": decoded_bezier,
        "fields": fields,
        "length": len(raw),
        "hex": raw.hex().upper(),
    }


def _decode_compressed_retime_keyframes(raw: bytes) -> dict[str, Any] | None:
    if not (len(raw) >= 5 and raw[:1] == b"\x81" and raw[1:5] == b"\x28\xb5\x2f\xfd"):
        return None
    decompressed = zstd.ZstdDecompressor().decompress(raw[1:])
    payload = _decode_retime_keyframe_list_proto_payload(decompressed)
    return {
        **payload,
        "encoding": "zstd",
        "prefix": raw[:1].hex().upper(),
        "compressed_length": len(raw),
        "decompressed_length": len(decompressed),
        "decompressed_hex": decompressed.hex().upper(),
    }


def _decode_retime_keyframe_list_proto_payload(payload: bytes) -> dict[str, Any]:
    offset = 0
    keyframes: list[dict[str, Any]] = []
    while offset < len(payload):
        key, offset = _read_pb_varint(payload, offset)
        field = key >> 3
        wire_type = key & 7
        if field != 1 or wire_type != 2:
            raise ValueError("unexpected field in RetimeKeyframeListProto")
        length, offset = _read_pb_varint(payload, offset)
        if offset + length > len(payload):
            raise ValueError("unexpected end while reading RetimeKeyframeProto bytes")
        keyframe_raw = bytes(payload[offset : offset + length])
        offset += length
        keyframes.append(_decode_retime_keyframe_proto(keyframe_raw, len(keyframes)))
    return {
        "type": "RetimeKeyframeListProto",
        "count": len(keyframes),
        "keyframes": keyframes,
    }


def _decode_prefixed_retime_keyframes(raw: bytes) -> dict[str, Any] | None:
    if not (len(raw) >= 2 and raw[:1] == b"\x80"):
        return None
    payload = _decode_retime_keyframe_list_proto_payload(raw[1:])
    return {
        **payload,
        "encoding": "uncompressed",
        "prefix": raw[:1].hex().upper(),
        "payload_length": len(raw) - 1,
        "payload_hex": raw[1:].hex().upper(),
    }


def _decode_legacy_qmap_keyframe(raw: bytes, index: int) -> dict[str, Any]:
    decoded = _decode_qmap(raw)
    entries = decoded.get("entries", {}) if isinstance(decoded, dict) else {}
    return {
        "index": index,
        "x": float(entries.get("X", 0.0) or 0.0),
        "y": float(entries.get("Y", 0.0) or 0.0),
        "x_in": float(entries.get("XIn", 0.0) or 0.0),
        "y_in": float(entries.get("YIn", 0.0) or 0.0),
        "x_out": float(entries.get("XOut", 0.0) or 0.0),
        "y_out": float(entries.get("YOut", 0.0) or 0.0),
        "interp": int(entries.get("interp", 0) or 0),
        "raw": decoded,
        "length": len(raw),
        "hex": raw.hex().upper(),
    }


def _decode_legacy_qmap_retime_keyframes(raw: bytes) -> dict[str, Any] | None:
    if not _looks_like_qmap(raw):
        return None
    decoded = _decode_qmap(raw)
    entries = decoded.get("entries", {}) if isinstance(decoded, dict) else {}
    keyframes: list[dict[str, Any]] = []
    for key, value in sorted(entries.items(), key=lambda item: int(item[0]) if str(item[0]).isdigit() else 10**9):
        if not isinstance(value, dict) or value.get("type") != "QByteArray":
            continue
        nested_hex = value.get("hex")
        if not isinstance(nested_hex, str):
            continue
        nested_raw = bytes.fromhex(nested_hex)
        keyframes.append(_decode_legacy_qmap_keyframe(nested_raw, len(keyframes)))
    if not keyframes:
        return None
    return {
        "type": "Sm2TimeMapLegacyKeyframes",
        "encoding": "qmap",
        "count": len(keyframes),
        "keyframes": keyframes,
        "raw": decoded,
    }


def _looks_like_qmap(blob: bytes) -> bool:
    if len(blob) < 8:
        return False
    version, count = struct.unpack(">II", blob[:8])
    return version in {0, 1} and count < 10000


def _decode_qvariant(blob: bytes, offset: int) -> tuple[Any, int]:
    type_id, offset = _read_u32(blob, offset)
    if offset >= len(blob):
        raise ValueError("unexpected end while reading variant null flag")
    null_flag = blob[offset]
    offset += 1
    if type_id == 2:
        value, offset = _read_i32(blob, offset)
        return value, offset
    if type_id == 6:
        value, offset = _read_double(blob, offset)
        return value, offset
    if type_id == 10:
        value, offset = _read_string(blob, offset)
        return value, offset
    if type_id == 12:
        length, offset = _read_u32(blob, offset)
        if offset + length > len(blob):
            raise ValueError("unexpected end while reading bytearray")
        raw = bytes(blob[offset : offset + length])
        offset += length
        decoded: Any | None = None
        try:
            decoded = _decode_compressed_retime_keyframes(raw)
        except ValueError:
            decoded = None
        if decoded is None:
            try:
                decoded = _decode_prefixed_retime_keyframes(raw)
            except ValueError:
                decoded = None
        if decoded is None and _looks_like_qmap(raw):
            try:
                decoded = _decode_legacy_qmap_retime_keyframes(raw) or _decode_qmap(raw)
            except ValueError:
                decoded = None
        payload: dict[str, Any] = {
            "type": "QByteArray",
            "length": len(raw),
            "hex": raw.hex().upper(),
        }
        if decoded is not None:
            payload["decoded"] = decoded
        return payload, offset
    return {
        "type": f"QVariant<{type_id}>",
        "null_flag": null_flag,
        "offset": offset,
    }, offset


def _decode_qmap(blob: bytes) -> dict[str, Any]:
    version, offset = _read_u32(blob, 0)
    count, offset = _read_u32(blob, offset)
    entries: dict[str, Any] = {}
    for _ in range(count):
        key, offset = _read_string(blob, offset)
        value, offset = _decode_qvariant(blob, offset)
        entries[key] = value
    return {
        "type": "QMap<QString,QVariant>",
        "version": version,
        "count": count,
        "entries": entries,
        "trailing_bytes": len(blob) - offset,
    }


def decode_timemap_blob(value: Any) -> dict[str, Any]:
    """Best-effort research decoder for DaVinci Resolve MediaTimemapBA blobs."""
    summary = timemap_blob_summary(value)
    blob = bytes(value or b"")
    if not blob:
        return {**summary, "decoded": None}
    simple = _simple_timemap_fields(blob)
    if simple is not None:
        return {**summary, "decoded": simple}
    if _looks_like_qmap(blob):
        try:
            return {**summary, "decoded": _decode_qmap(blob)}
        except ValueError as exc:
            return {**summary, "decode_error": str(exc), "decoded": None}
    return {**summary, "decode_error": "unrecognized_timemap_blob_shape", "decoded": None}
