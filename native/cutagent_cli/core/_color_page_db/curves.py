"""Curves helpers for Color Page DB operations."""

from __future__ import annotations

import base64
import hashlib
import json
import math
import sqlite3
import struct
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from ...errors import APICallFailed, ValidationError
from ..db_session import DiskDbMutationSession, execute_sqlite_disk_db_mutation
from ..db_timeline_rows import find_ti_item_row
from .constants import *
from .proto_codec import *
from .version_body import *
from .transforms import *
from .params import *
from .proto_sections import *


CURVE_CHANNEL_PARAMS = {
    "y": PARAM_CURVE_Y,
    "red": PARAM_CURVE_R,
    "green": PARAM_CURVE_G,
    "blue": PARAM_CURVE_B,
}

CURVE_PARAM_CHANNELS = {value: key for key, value in CURVE_CHANNEL_PARAMS.items()}
CURVE_MODE_PARAM_KEYS = {
    PARAM_CURVES_MODE: 2,
    PARAM_CURVES_LINK: 1,
    0x860000BD: 1,
    0x860000BE: 1,
    0x860000BF: 1,
}

# DaVinci Resolve Studio 21.0.0b.20 GUI-created HDR Global seed payload. Creating only
# the Global bytes param is ignored by DaVinci Resolve; these companion curve/mode
# params are the minimal fixture-backed state that makes the HDR palette persist.
HDR_GLOBAL_SEED_CURVE_PAYLOAD_B64 = {
    PARAM_CURVE_Y: (
        "CgoNAACAxBUAAIDECgAKCg1ghvtCFXZz2EIKCg10l4FDFUIkUEMKCg3GpLxDFZhWokMKCg1IHdVDFd97ukMKCg3H3+FDFfKR3EMKCg1INvlDFfPP9UMKCg0F2SZEFT2YKEQKCg0MCVREFf53U0QKCg0AwH9EFQDAf0Q="
    ),
    PARAM_CURVE_R: (
        "CgoNAACAxBUAAIDECgAKCg0UyPRCFdLE0UIKCg1rb3xDFXNySUMKCg0PlrdDFZtTnUMKCg3tudFDFS8et0MKCg3dQ+BDFX3d2kMKCg1INvlDFfPP9UMKCg2t4CZEFSeRKEQKCg0MCVREFf53U0QKCg0AwH9EFQDAf0Q="
    ),
    PARAM_CURVE_G: (
        "CgoNAACAxBUAAIDECgAKCg3/sPtCFXZz2EIKCg24sYFDFdEYUEMKCg2+xLxDFZhWokMKCg3HONVDFYB3ukMKCg1H5eFDFWGV3EMKCg1INvlDFfPP9UMKCg3A1iZEFVaaKEQKCg0MCVREFf53U0QKCg0AwH9EFQDAf0Q="
    ),
    PARAM_CURVE_B: (
        "CgoNAACAxBUAAIDECgAKCg3QtvZCFdLE0UIKCg2L0H5DFVDtSEMKCg0aCblDFZtTnUMKCg2v+NJDFQrrtkMKCg3DhOBDFR0F20MKCg1INvlDFfPP9UMKCg22xiZEFSOpKEQKCg0MCVREFf53U0QKCg0AwH9EFQDAf0Q="
    ),
}

HDR_GLOBAL_SEED_MODE_PARAM_KEYS = {
    PARAM_CURVES_LINK: 2,
    0x860000BD: 2,
    0x860000BE: 2,
    0x860000BF: 2,
}
CURVE_GUARD_VALUE = -1024.0
CURVE_VISIBLE_MAX = 1023.0
CURVE_GUI_SAMPLE_X = (
    166.14137268066406,
    331.96441650390625,
    498.424072265625,
    672.9650268554688,
    848.141357421875,
)


def _normalize_curve_domain_value(value: float) -> float:
    if value <= 0.0:
        return 0.0
    return value / CURVE_VISIBLE_MAX


def _denormalize_curve_domain_value(value: float) -> float:
    return value * CURVE_VISIBLE_MAX


CURVE_GUI_SAMPLE_POINTS = tuple(
    CurvePoint(_normalize_curve_domain_value(value), _normalize_curve_domain_value(value))
    for value in CURVE_GUI_SAMPLE_X
)


def _decode_curve_points_payload(payload: bytes) -> list[CurvePoint] | None:
    points: list[CurvePoint] = []
    offset = 0
    while offset < len(payload):
        try:
            tag, offset = _read_varint(payload, offset)
        except ValueError:
            return None
        fn = tag >> 3
        wt = tag & 7
        if fn == 1 and wt == 2:
            try:
                length, offset = _read_varint(payload, offset)
            except ValueError:
                return None
            message = payload[offset:offset + length]
            offset += length
            if not message:
                continue
            if len(message) != 10 or message[0] != 0x0D or message[5] != 0x15:
                return None
            x = struct.unpack("<f", message[1:5])[0]
            y = struct.unpack("<f", message[6:10])[0]
            if x < CURVE_GUARD_VALUE or x > CURVE_VISIBLE_MAX:
                continue
            points.append(
                CurvePoint(
                    x=_normalize_curve_domain_value(x),
                    y=_normalize_curve_domain_value(y),
                )
            )
        elif wt == 0:
            try:
                _, offset = _read_varint(payload, offset)
            except ValueError:
                return None
        elif wt == 1:
            offset += 8
        elif wt == 5:
            offset += 4
        elif wt == 2:
            try:
                length, offset = _read_varint(payload, offset)
            except ValueError:
                return None
            offset += length
        else:
            return None
    return points


def _params_to_curve_points_dict(params: list[GradeParam]) -> dict[str, list[dict[str, float]]]:
    curves: dict[str, list[dict[str, float]]] = {}
    for param in params:
        channel = CURVE_PARAM_CHANNELS.get(param.key)
        if not channel or not isinstance(param.value, bytes):
            continue
        points = _decode_curve_points_payload(param.value)
        if points is None:
            continue
        curves[channel] = [point.to_dict() for point in points]
    return curves


def hue_curve_input_hue_to_internal(value: float) -> float:
    if not math.isfinite(value) or value < 0.0 or value > 720.0:
        raise ValidationError(
            "Hue vs Hue Input Hue must be a finite GUI value from 0 to 720.",
            details={"input_hue": value, "minimum": 0.0, "maximum": 720.0},
            recoverability="not_applicable",
        )
    return (value - 256.0) / 360.0


def hue_curve_input_hue_from_internal(value: float) -> float:
    return (value * 360.0) + 256.0


def hue_curve_rotate_to_internal(value: float) -> float:
    if not math.isfinite(value) or value < -180.0 or value > 180.0:
        raise ValidationError(
            "Hue vs Hue Rotate must be a finite GUI value from -180 to 180.",
            details={"hue_rotate": value, "minimum": -180.0, "maximum": 180.0},
            recoverability="not_applicable",
        )
    return (180.0 - value) / 360.0


def hue_curve_rotate_from_internal(value: float) -> float:
    return 180.0 - (value * 360.0)


def hue_curve_saturation_to_internal(value: float) -> float:
    if not math.isfinite(value) or value < 0.0 or value > 2.0:
        raise ValidationError(
            "Hue vs Sat Saturation must be a finite GUI value from 0 to 2.",
            details={"saturation": value, "minimum": 0.0, "maximum": 2.0},
            recoverability="not_applicable",
        )
    return (2.0 - value) / 2.0


def hue_curve_saturation_from_internal(value: float) -> float:
    return 2.0 - (value * 2.0)


def hue_curve_lum_gain_to_internal(value: float) -> float:
    if not math.isfinite(value) or value < 0.0 or value > 2.0:
        raise ValidationError(
            "Hue vs Lum Lum Gain must be a finite GUI value from 0 to 2.",
            details={"lum_gain": value, "minimum": 0.0, "maximum": 2.0},
            recoverability="not_applicable",
        )
    return (2.0 - value) / 2.0


def hue_curve_lum_gain_from_internal(value: float) -> float:
    return 2.0 - (value * 2.0)


def sat_curve_input_sat_to_internal(value: float) -> float:
    if not math.isfinite(value) or value < 0.0 or value > 1.0:
        raise ValidationError(
            "Sat vs Sat Input Sat must be a finite GUI value from 0 to 1.",
            details={"input_sat": value, "minimum": 0.0, "maximum": 1.0},
            recoverability="not_applicable",
        )
    return value


def sat_curve_input_sat_from_internal(value: float) -> float:
    return value


def sat_curve_output_sat_to_internal(value: float) -> float:
    if not math.isfinite(value) or value < 0.0 or value > 2.0:
        raise ValidationError(
            "Sat vs Sat Output Sat must be a finite GUI value from 0 to 2.",
            details={"output_sat": value, "minimum": 0.0, "maximum": 2.0},
            recoverability="not_applicable",
        )
    return (2.0 - value) / 2.0


def sat_curve_output_sat_from_internal(value: float) -> float:
    return 2.0 - (value * 2.0)


def sat_curve_lum_to_internal(value: float) -> float:
    if not math.isfinite(value) or value < 0.0 or value > 2.0:
        raise ValidationError(
            "Sat vs Lum Lum must be a finite GUI value from 0 to 2.",
            details={"lum": value, "minimum": 0.0, "maximum": 2.0},
            recoverability="not_applicable",
        )
    return (2.0 - value) / 2.0


def sat_curve_lum_from_internal(value: float) -> float:
    return 2.0 - (value * 2.0)


def lum_curve_input_lum_to_internal(value: float) -> float:
    if not math.isfinite(value) or value < 0.0 or value > 1.0:
        raise ValidationError(
            "Lum vs Sat Input Lum must be a finite GUI value from 0 to 1.",
            details={"input_lum": value, "minimum": 0.0, "maximum": 1.0},
            recoverability="not_applicable",
        )
    return value


def lum_curve_input_lum_from_internal(value: float) -> float:
    return value


def _hue_curve_wrap_points(x: float, y: float) -> tuple[tuple[float, float], ...]:
    start = x if x < 0.0 else x - 1.0
    return (
        (start, y),
        (start + 0.5, y),
        (start + 0.5, y),
        (start + 1.0, y),
        (start + 1.5, y),
        (start + 1.5, y),
        (start + 2.0, y),
    )


def _hue_curve_payload_from_internal(x: float, y: float) -> bytes:
    points = _hue_curve_wrap_points(x, y)
    payload = bytearray()
    for point_x, point_y in points:
        payload.extend(b"\x0a\x0a\x0d")
        payload.extend(struct.pack("<f", point_x))
        payload.extend(b"\x15")
        payload.extend(struct.pack("<f", point_y))
    return bytes(payload)


def _hue_vs_hue_payload(input_hue: float, hue_rotate: float) -> bytes:
    x = hue_curve_input_hue_to_internal(input_hue)
    y = hue_curve_rotate_to_internal(hue_rotate)
    return _hue_curve_payload_from_internal(x, y)


def _hue_curve_point_chunk(x: float, y: float) -> bytes:
    return b"\x0a\x0a\x0d" + struct.pack("<f", x) + b"\x15" + struct.pack("<f", y)


def _hue_curve_multi_point_payload(points: list[dict[str, float]], *, value_key: str) -> bytes:
    payload = bytearray()
    for point in points:
        payload.extend(_hue_curve_point_chunk(float(point["x_internal"]), float(point["y_internal"])))
    return bytes(payload)


def _hue_curve_points_readback(points: list[dict[str, float]], *, value_key: str) -> list[dict[str, float]]:
    rows: list[dict[str, float]] = []
    for point in points:
        row = {
            "x_internal": round(float(point["x_internal"]), 6),
            "y_internal": round(float(point["y_internal"]), 6),
            "input_hue": round(hue_curve_input_hue_from_internal(float(point["x_internal"])), 6),
        }
        if value_key == "hue_rotate":
            row[value_key] = round(hue_curve_rotate_from_internal(float(point["y_internal"])), 6)
        elif value_key == "saturation":
            row[value_key] = round(hue_curve_saturation_from_internal(float(point["y_internal"])), 6)
        elif value_key == "lum_gain":
            row[value_key] = round(hue_curve_lum_gain_from_internal(float(point["y_internal"])), 6)
        else:
            raise ValidationError(
                "Unsupported Hue curve point value key.",
                details={"value_key": value_key},
                recoverability="not_applicable",
            )
        rows.append(row)
    return rows


def _sat_curve_point_chunk(x: float, y: float) -> bytes:
    return _encode_length_delimited(1, b"\x0d" + struct.pack("<f", x) + b"\x15" + struct.pack("<f", y))


def _sat_curve_multi_point_payload(points: list[dict[str, float]]) -> bytes:
    payload = bytearray()
    payload.extend(_encode_length_delimited(1, b"\x15" + struct.pack("<f", 0.5)))
    for point in points:
        payload.extend(_sat_curve_point_chunk(float(point["x_internal"]), float(point["y_internal"])))
    return bytes(payload)


def _sat_curve_points_readback(
    points: list[dict[str, float]],
    *,
    x_key: str,
    value_key: str,
) -> list[dict[str, float]]:
    rows: list[dict[str, float]] = []
    for point in points:
        row = {
            "x_internal": round(float(point["x_internal"]), 6),
            "y_internal": round(float(point["y_internal"]), 6),
        }
        if x_key == "input_sat":
            row[x_key] = round(sat_curve_input_sat_from_internal(float(point["x_internal"])), 6)
        elif x_key == "input_lum":
            row[x_key] = round(lum_curve_input_lum_from_internal(float(point["x_internal"])), 6)
        else:
            raise ValidationError(
                "Unsupported Saturation curve point input key.",
                details={"x_key": x_key},
                recoverability="not_applicable",
            )

        if value_key == "output_sat":
            row[value_key] = round(sat_curve_output_sat_from_internal(float(point["y_internal"])), 6)
        elif value_key == "lum":
            row[value_key] = round(sat_curve_lum_from_internal(float(point["y_internal"])), 6)
        elif value_key == "saturation":
            row[value_key] = round(sat_curve_output_sat_from_internal(float(point["y_internal"])), 6)
        else:
            raise ValidationError(
                "Unsupported Saturation curve point value key.",
                details={"value_key": value_key},
                recoverability="not_applicable",
            )
        rows.append(row)
    return rows


def parse_hue_curve_points_spec(value: str, *, mode: str) -> list[dict[str, float]]:
    normalized_mode = mode.strip().lower().replace("_", "-")
    value_key = {
        "hue-vs-hue": "hue_rotate",
        "hue-vs-sat": "saturation",
        "hue-vs-lum": "lum_gain",
    }.get(normalized_mode)
    if value_key is None:
        raise ValidationError(
            "Hue curve points mode must be hue-vs-hue, hue-vs-sat, or hue-vs-lum.",
            details={"mode": mode, "supported_modes": ["hue-vs-hue", "hue-vs-sat", "hue-vs-lum"]},
            recoverability="not_applicable",
        )

    raw_points = [part.strip() for part in str(value).split(";") if part.strip()]
    if len(raw_points) < 2:
        raise ValidationError(
            "Hue curve --points requires at least two input,value pairs.",
            details={"points": value, "minimum_points": 2},
            recoverability="not_applicable",
        )
    if len(raw_points) > 32:
        raise ValidationError(
            "Hue curve --points supports at most 32 points.",
            details={"point_count": len(raw_points), "maximum_points": 32},
            recoverability="not_applicable",
        )

    parsed: list[dict[str, float]] = []
    previous_input_hue: float | None = None
    for raw in raw_points:
        pieces = [piece.strip() for piece in raw.split(",")]
        if len(pieces) != 2:
            raise ValidationError(
                'Hue curve --points entries must use "input,value" pairs separated by semicolons.',
                details={"entry": raw, "points": value},
                recoverability="not_applicable",
            )
        try:
            input_hue = float(pieces[0])
            gui_value = float(pieces[1])
        except ValueError as exc:
            raise ValidationError(
                "Hue curve --points entries must be numeric.",
                details={"entry": raw, "points": value},
                recoverability="not_applicable",
            ) from exc
        if previous_input_hue is not None and input_hue <= previous_input_hue:
            raise ValidationError(
                "Hue curve --points input hue values must be strictly increasing.",
                details={"entry": raw, "previous_input_hue": previous_input_hue, "input_hue": input_hue},
                recoverability="not_applicable",
            )
        previous_input_hue = input_hue
        x = hue_curve_input_hue_to_internal(input_hue)
        if value_key == "hue_rotate":
            y = hue_curve_rotate_to_internal(gui_value)
        elif value_key == "saturation":
            y = hue_curve_saturation_to_internal(gui_value)
        else:
            y = hue_curve_lum_gain_to_internal(gui_value)
        parsed.append({"input_hue": input_hue, value_key: gui_value, "x_internal": x, "y_internal": y})
    return parsed


def parse_sat_curve_points_spec(value: str, *, mode: str) -> list[dict[str, float]]:
    normalized_mode = mode.strip().lower().replace("_", "-")
    config = {
        "sat-vs-sat": ("input_sat", "output_sat"),
        "sat-vs-lum": ("input_sat", "lum"),
        "lum-vs-sat": ("input_lum", "saturation"),
    }.get(normalized_mode)
    if config is None:
        raise ValidationError(
            "Saturation curve points mode must be sat-vs-sat, sat-vs-lum, or lum-vs-sat.",
            details={"mode": mode, "supported_modes": ["sat-vs-sat", "sat-vs-lum", "lum-vs-sat"]},
            recoverability="not_applicable",
        )
    x_key, value_key = config

    raw_points = [part.strip() for part in str(value).split(";") if part.strip()]
    if len(raw_points) < 2:
        raise ValidationError(
            "Saturation curve --points requires at least two input,value pairs.",
            details={"points": value, "minimum_points": 2},
            recoverability="not_applicable",
        )
    if len(raw_points) > 32:
        raise ValidationError(
            "Saturation curve --points supports at most 32 points.",
            details={"point_count": len(raw_points), "maximum_points": 32},
            recoverability="not_applicable",
        )

    parsed: list[dict[str, float]] = []
    previous_input: float | None = None
    for raw in raw_points:
        pieces = [piece.strip() for piece in raw.split(",")]
        if len(pieces) != 2:
            raise ValidationError(
                'Saturation curve --points entries must use "input,value" pairs separated by semicolons.',
                details={"entry": raw, "points": value},
                recoverability="not_applicable",
            )
        try:
            gui_input = float(pieces[0])
            gui_value = float(pieces[1])
        except ValueError as exc:
            raise ValidationError(
                "Saturation curve --points entries must be numeric.",
                details={"entry": raw, "points": value},
                recoverability="not_applicable",
            ) from exc
        if previous_input is not None and gui_input <= previous_input:
            raise ValidationError(
                "Saturation curve --points input values must be strictly increasing.",
                details={"entry": raw, "previous_input": previous_input, "input": gui_input},
                recoverability="not_applicable",
            )
        previous_input = gui_input

        if x_key == "input_sat":
            x = sat_curve_input_sat_to_internal(gui_input)
        else:
            x = lum_curve_input_lum_to_internal(gui_input)

        if value_key == "lum":
            y = sat_curve_lum_to_internal(gui_value)
        else:
            y = sat_curve_output_sat_to_internal(gui_value)
        parsed.append({x_key: gui_input, value_key: gui_value, "x_internal": x, "y_internal": y})
    return parsed


def _hue_vs_sat_payload(input_hue: float, saturation: float) -> bytes:
    x = hue_curve_input_hue_to_internal(input_hue)
    y = hue_curve_saturation_to_internal(saturation)
    return _hue_curve_payload_from_internal(x, y)


def _hue_vs_lum_payload(input_hue: float, lum_gain: float) -> bytes:
    x = hue_curve_input_hue_to_internal(input_hue)
    y = hue_curve_lum_gain_to_internal(lum_gain)
    return _hue_curve_payload_from_internal(x, y)


def _sat_vs_sat_payload(input_sat: float, output_sat: float) -> bytes:
    x = sat_curve_input_sat_to_internal(input_sat)
    y = sat_curve_output_sat_to_internal(output_sat)
    if abs(x - SAT_VS_SAT_FIXTURE_INPUT) < 1e-6 and abs(output_sat - SAT_VS_SAT_FIXTURE_OUTPUT) < 1e-6:
        return SAT_VS_SAT_FIXTURE_PAYLOAD
    if x < SAT_VS_SAT_LEFT_DX or x > 0.5:
        raise ValidationError(
            "Saturation curve DB route currently supports fixture-backed low-to-mid input saturation points.",
            details={
                "input_sat": input_sat,
                "supported_minimum": round(SAT_VS_SAT_LEFT_DX, 6),
                "supported_maximum": 0.5,
            },
            recoverability="not_applicable",
        )
    if x + SAT_VS_SAT_RIGHT_DX > 1.0:
        raise ValidationError(
            "Sat vs Sat DB route could not place the GUI guard points for this input saturation.",
            details={"input_sat": input_sat, "right_guard": x + SAT_VS_SAT_RIGHT_DX},
            recoverability="not_applicable",
        )
    left_y = 0.5 + ((y - 0.5) * SAT_VS_SAT_LEFT_BLEND)
    right_y = 0.5 + ((y - 0.5) * SAT_VS_SAT_RIGHT_BLEND)
    payload = bytearray()
    payload.extend(_encode_length_delimited(1, b"\x15" + struct.pack("<f", 0.5)))
    for point_x, point_y in (
        (x - SAT_VS_SAT_LEFT_DX, left_y),
        (x, y),
        (x * 2.0, y),
        (x + 0.5, y),
        (x + SAT_VS_SAT_RIGHT_DX, right_y),
        (1.0, 0.5),
    ):
        payload.extend(b"\x0a\x0a\x0d")
        payload.extend(struct.pack("<f", point_x))
        payload.extend(b"\x15")
        payload.extend(struct.pack("<f", point_y))
    return bytes(payload)


def _sat_vs_lum_payload(input_sat: float, lum: float) -> bytes:
    sat_curve_lum_to_internal(lum)
    return _sat_vs_sat_payload(input_sat, lum)


def _lum_vs_sat_payload(input_lum: float, saturation: float) -> bytes:
    x = lum_curve_input_lum_to_internal(input_lum)
    return _sat_vs_sat_payload(x / 2.0, saturation)


def _decode_hue_vs_hue_payload(payload: bytes) -> list[dict[str, float]] | None:
    if len(payload) % 12 != 0:
        return None
    points: list[dict[str, float]] = []
    for offset in range(0, len(payload), 12):
        chunk = payload[offset:offset + 12]
        if chunk[:3] != b"\x0a\x0a\x0d" or chunk[7] != 0x15:
            return None
        x = struct.unpack("<f", chunk[3:7])[0]
        y = struct.unpack("<f", chunk[8:12])[0]
        points.append(
            {
                "x_internal": round(x, 6),
                "y_internal": round(y, 6),
                "input_hue": round(hue_curve_input_hue_from_internal(x), 6),
                "hue_rotate": round(hue_curve_rotate_from_internal(y), 6),
            }
        )
    return points


def _decode_hue_vs_sat_payload(payload: bytes) -> list[dict[str, float]] | None:
    if len(payload) % 12 != 0:
        return None
    points: list[dict[str, float]] = []
    for offset in range(0, len(payload), 12):
        chunk = payload[offset:offset + 12]
        if chunk[:3] != b"\x0a\x0a\x0d" or chunk[7] != 0x15:
            return None
        x = struct.unpack("<f", chunk[3:7])[0]
        y = struct.unpack("<f", chunk[8:12])[0]
        points.append(
            {
                "x_internal": round(x, 6),
                "y_internal": round(y, 6),
                "input_hue": round(hue_curve_input_hue_from_internal(x), 6),
                "saturation": round(hue_curve_saturation_from_internal(y), 6),
            }
        )
    return points


def _decode_hue_vs_lum_payload(payload: bytes) -> list[dict[str, float]] | None:
    if len(payload) % 12 != 0:
        return None
    points: list[dict[str, float]] = []
    for offset in range(0, len(payload), 12):
        chunk = payload[offset:offset + 12]
        if chunk[:3] != b"\x0a\x0a\x0d" or chunk[7] != 0x15:
            return None
        x = struct.unpack("<f", chunk[3:7])[0]
        y = struct.unpack("<f", chunk[8:12])[0]
        points.append(
            {
                "x_internal": round(x, 6),
                "y_internal": round(y, 6),
                "input_hue": round(hue_curve_input_hue_from_internal(x), 6),
                "lum_gain": round(hue_curve_lum_gain_from_internal(y), 6),
            }
        )
    return points


def _decode_sat_vs_sat_payload(payload: bytes) -> list[dict[str, float]] | None:
    points: list[dict[str, float]] = []
    offset = 0
    while offset < len(payload):
        try:
            tag, offset = _read_varint(payload, offset)
        except ValueError:
            return None
        fn = tag >> 3
        wt = tag & 7
        if fn != 1 or wt != 2:
            return None
        try:
            length, offset = _read_varint(payload, offset)
        except ValueError:
            return None
        chunk = payload[offset:offset + length]
        offset += length
        if len(chunk) == 5 and chunk[0] == 0x15:
            y = struct.unpack("<f", chunk[1:5])[0]
            points.append(
                {
                    "x_internal": None,
                    "y_internal": round(y, 6),
                    "input_sat": None,
                    "output_sat": round(sat_curve_output_sat_from_internal(y), 6),
                    "role": "start_guard",
                }
            )
            continue
        if len(chunk) != 10 or chunk[0] != 0x0D or chunk[5] != 0x15:
            return None
        x = struct.unpack("<f", chunk[1:5])[0]
        y = struct.unpack("<f", chunk[6:10])[0]
        points.append(
            {
                "x_internal": round(x, 6),
                "y_internal": round(y, 6),
                "input_sat": round(sat_curve_input_sat_from_internal(x), 6),
                "output_sat": round(sat_curve_output_sat_from_internal(y), 6),
            }
        )
    return points


def _primary_hue_curve_point(points: list[dict[str, float]]) -> dict[str, float]:
    first = points[0]
    if 0.0 <= first.get("input_hue", -1.0) <= 720.0:
        return first
    return points[len(points) // 2]


def _params_to_hue_vs_hue_curve(params: list[GradeParam]) -> dict[str, Any] | None:
    payload = None
    for param in params:
        if param.key == PARAM_HUE_VS_HUE_CURVE and isinstance(param.value, bytes):
            payload = param.value
            break
    if payload is None:
        return None
    points = _decode_hue_vs_hue_payload(payload)
    if not points:
        return None
    center = _primary_hue_curve_point(points)
    return {
        "input_hue": center["input_hue"],
        "hue_rotate": center["hue_rotate"],
        "points": points,
    }


def _params_to_hue_vs_sat_curve(params: list[GradeParam]) -> dict[str, Any] | None:
    payload = None
    for param in params:
        if param.key == PARAM_HUE_VS_SAT_CURVE and isinstance(param.value, bytes):
            payload = param.value
            break
    if payload is None:
        return None
    points = _decode_hue_vs_sat_payload(payload)
    if not points:
        return None
    center = _primary_hue_curve_point(points)
    return {
        "input_hue": center["input_hue"],
        "saturation": center["saturation"],
        "points": points,
    }


def _params_to_hue_vs_lum_curve(params: list[GradeParam]) -> dict[str, Any] | None:
    payload = None
    for param in params:
        if param.key == PARAM_HUE_VS_LUM_CURVE and isinstance(param.value, bytes):
            payload = param.value
            break
    if payload is None:
        return None
    points = _decode_hue_vs_lum_payload(payload)
    if not points:
        return None
    center = _primary_hue_curve_point(points)
    return {
        "input_hue": center["input_hue"],
        "lum_gain": center["lum_gain"],
        "points": points,
    }


def _params_to_sat_vs_sat_curve(params: list[GradeParam]) -> dict[str, Any] | None:
    payload = None
    for param in params:
        if param.key == PARAM_SAT_VS_SAT_CURVE and isinstance(param.value, bytes):
            payload = param.value
            break
    if payload is None:
        return None
    points = _decode_sat_vs_sat_payload(payload)
    if not points:
        return None
    candidates = [
        point for point in points
        if point.get("x_internal") is not None and point.get("y_internal") is not None
    ]
    if not candidates:
        return None
    center = min(candidates, key=lambda point: abs(float(point["y_internal"])))
    return {
        "input_sat": center["input_sat"],
        "output_sat": center["output_sat"],
        "points": points,
    }


def _params_to_sat_vs_lum_curve(params: list[GradeParam]) -> dict[str, Any] | None:
    payload = None
    for param in params:
        if param.key == PARAM_SAT_VS_LUM_CURVE and isinstance(param.value, bytes):
            payload = param.value
            break
    if payload is None:
        return None
    points = _decode_sat_vs_sat_payload(payload)
    if not points:
        return None
    candidates = [
        point for point in points
        if point.get("x_internal") is not None and point.get("y_internal") is not None
    ]
    if not candidates:
        return None
    center = min(candidates, key=lambda point: abs(float(point["y_internal"])))
    return {
        "input_sat": center["input_sat"],
        "lum": center["output_sat"],
        "points": points,
    }


def _interpolate_curve_points(points: list[CurvePoint], x: float) -> float:
    sorted_points = [CurvePoint(0.0, 0.0)]
    sorted_points.extend(point for point in points if 0.0 < point.x < 1.0)
    sorted_points.append(CurvePoint(1.0, 1.0))
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    for left, right in zip(sorted_points, sorted_points[1:]):
        if left.x <= x <= right.x:
            if abs(right.x - left.x) < 1e-9:
                return right.y
            ratio = (x - left.x) / (right.x - left.x)
            return left.y + ((right.y - left.y) * ratio)
    return sorted_points[-1].y


def _curve_points_with_resolve_guards(points: list[CurvePoint]) -> list[CurvePoint | None]:
    sampled = [
        CurvePoint(sample.x, _interpolate_curve_points(points, sample.x))
        for sample in CURVE_GUI_SAMPLE_POINTS
    ]
    return [
        CurvePoint(0.0, 0.0),
        None,
        *sampled,
        CurvePoint(1.0, 1.0),
    ]


def _curve_payload_with_guards(points: list[CurvePoint]) -> bytes:
    previous_x = -1.0
    for point in points:
        if not math.isfinite(point.x) or not math.isfinite(point.y):
            raise ValidationError(
                "Color Page curve control points must be finite numbers.",
                details={"point": point.to_dict()},
                recoverability="not_applicable",
            )
        if point.x < 0.0 or point.x > 1.0 or point.y < 0.0 or point.y > 1.0:
            raise ValidationError(
                "Color Page curve control points must be normalized between 0 and 1.",
                details={"point": point.to_dict()},
                recoverability="not_applicable",
            )
        if point.x < previous_x:
            raise ValidationError(
                "Color Page curve control points must be sorted by x.",
                details={"point": point.to_dict(), "previous_x": previous_x},
                recoverability="not_applicable",
            )
        previous_x = point.x
    result = bytearray()
    for index, point in enumerate(_curve_points_with_resolve_guards(points)):
        if point is None:
            result.extend(_encode_length_delimited(1, b""))
            continue
        if index == 0 and point.x == 0.0 and point.y == 0.0:
            x = CURVE_GUARD_VALUE
            y = CURVE_GUARD_VALUE
        else:
            x = _denormalize_curve_domain_value(point.x)
            y = _denormalize_curve_domain_value(point.y)
        result.extend(
            _encode_length_delimited(
                1,
                b"\x0d" + struct.pack("<f", x) + b"\x15" + struct.pack("<f", y),
            )
        )
    return bytes(result)


def parse_curve_points_spec(value: str) -> list[CurvePoint]:
    points: list[CurvePoint] = []
    for raw_pair in value.split(";"):
        pair = raw_pair.strip()
        if not pair:
            continue
        parts = [part.strip() for part in pair.split(",")]
        if len(parts) != 2:
            raise ValidationError(
                "Curve point specs must use 'x,y;x,y' normalized pairs.",
                details={"pair": pair, "value": value},
                recoverability="not_applicable",
            )
        try:
            x = float(parts[0])
            y = float(parts[1])
        except ValueError as exc:
            raise ValidationError(
                "Curve point specs must contain numeric x,y values.",
                details={"pair": pair, "value": value},
                recoverability="not_applicable",
            ) from exc
        points.append(CurvePoint(x=x, y=y))

    if not points:
        raise ValidationError(
            "Curve point spec must include at least one point.",
            details={"value": value},
            recoverability="not_applicable",
        )
    _curve_payload_with_guards(points)
    return points


def _curve_points_for_readback(points: list[CurvePoint]) -> list[dict[str, float]]:
    return [
        point.to_dict()
        for point in _curve_points_with_resolve_guards(points)
        if point is not None
    ]


def _curve_points_match(
    actual: list[dict[str, float]] | None,
    expected: list[dict[str, float]],
    *,
    tolerance: float = 0.001,
) -> bool:
    if actual is None or len(actual) != len(expected):
        return False
    for actual_point, expected_point in zip(actual, expected):
        actual_x = float(actual_point["x"])
        actual_y = float(actual_point["y"])
        expected_x = float(expected_point["x"])
        expected_y = float(expected_point["y"])
        if not all(math.isfinite(value) for value in (actual_x, actual_y, expected_x, expected_y)):
            return False
        if (
            abs(actual_x - expected_x) > tolerance or
            abs(actual_y - expected_y) > tolerance
        ):
            return False
    return True


def _validate_split_tone_amount(name: str, value: float) -> float:
    numeric = float(value)
    if not math.isfinite(numeric):
        raise ValidationError(
            f"Color Page split tone {name} must be a finite number.",
            details={name: value},
            recoverability="not_applicable",
        )
    if numeric < -0.5 or numeric > 0.5:
        raise ValidationError(
            f"Color Page split tone {name} must be between -0.5 and 0.5.",
            details={name: numeric, "minimum": -0.5, "maximum": 0.5},
            recoverability="not_applicable",
        )
    return numeric


def _validate_split_tone_strength(value: float) -> float:
    numeric = float(value)
    if not math.isfinite(numeric):
        raise ValidationError(
            "Color Page split tone strength must be a finite number.",
            details={"strength": value},
            recoverability="not_applicable",
        )
    if numeric < 0.0 or numeric > 2.0:
        raise ValidationError(
            "Color Page split tone strength must be between 0 and 2.",
            details={"strength": numeric, "minimum": 0.0, "maximum": 2.0},
            recoverability="not_applicable",
        )
    return numeric


def _validate_split_tone_pivot(value: float) -> float:
    numeric = float(value)
    if not math.isfinite(numeric):
        raise ValidationError(
            "Color Page split tone pivot must be a finite number.",
            details={"pivot": value},
            recoverability="not_applicable",
        )
    if numeric < 0.05 or numeric > 0.95:
        raise ValidationError(
            "Color Page split tone pivot must be between 0.05 and 0.95.",
            details={"pivot": numeric, "minimum": 0.05, "maximum": 0.95},
            recoverability="not_applicable",
        )
    return numeric


def _validate_split_tone_rolloff(value: float) -> float:
    numeric = float(value)
    if not math.isfinite(numeric):
        raise ValidationError(
            "Color Page split tone rolloff must be a finite number.",
            details={"rolloff": value},
            recoverability="not_applicable",
        )
    if numeric < 0.25 or numeric > 4.0:
        raise ValidationError(
            "Color Page split tone rolloff must be between 0.25 and 4.",
            details={"rolloff": numeric, "minimum": 0.25, "maximum": 4.0},
            recoverability="not_applicable",
        )
    return numeric


def _clamp_curve_value(value: float) -> float:
    return max(0.0, min(1.0, value))


def build_split_tone_curve_points(
    *,
    strength: float = 1.0,
    shadow_cool: float = 0.06,
    highlight_warm: float = 0.06,
    shadow_lift: float = 0.0,
    highlight_lift: float = 0.0,
    pivot: float = 0.5,
    rolloff: float = 1.0,
    shadow_r: float | None = None,
    shadow_g: float | None = None,
    shadow_b: float | None = None,
    highlight_r: float | None = None,
    highlight_g: float | None = None,
    highlight_b: float | None = None,
    y_mood: float = 0.0,
) -> dict[str, list[CurvePoint]]:
    """Build Custom Curves points for a warm-highlights/cool-shadows split tone."""
    strength = _validate_split_tone_strength(strength)
    shadow_cool = _validate_split_tone_amount("shadow_cool", shadow_cool)
    highlight_warm = _validate_split_tone_amount("highlight_warm", highlight_warm)
    shadow_lift = _validate_split_tone_amount("shadow_lift", shadow_lift)
    highlight_lift = _validate_split_tone_amount("highlight_lift", highlight_lift)
    pivot = _validate_split_tone_pivot(pivot)
    rolloff = _validate_split_tone_rolloff(rolloff)
    y_mood = _validate_split_tone_amount("y_mood", y_mood)

    shadow_offsets = {
        "red": shadow_lift - shadow_cool * 0.5,
        "green": shadow_lift - shadow_cool * 0.2,
        "blue": shadow_lift + shadow_cool,
    }
    highlight_offsets = {
        "red": highlight_lift + highlight_warm,
        "green": highlight_lift + highlight_warm * 0.35,
        "blue": highlight_lift - highlight_warm * 0.55,
    }
    for channel, value in (("red", shadow_r), ("green", shadow_g), ("blue", shadow_b)):
        if value is not None:
            shadow_offsets[channel] = _validate_split_tone_amount(f"shadow_{channel[0]}", value)
    for channel, value in (("red", highlight_r), ("green", highlight_g), ("blue", highlight_b)):
        if value is not None:
            highlight_offsets[channel] = _validate_split_tone_amount(f"highlight_{channel[0]}", value)

    samples = (0.0, pivot / 2.0, pivot, (1.0 + pivot) / 2.0, 1.0)
    curves: dict[str, list[CurvePoint]] = {}
    channel_offsets = {
        channel: (shadow_offsets[channel] * strength, highlight_offsets[channel] * strength)
        for channel in ("red", "green", "blue")
    }
    if y_mood:
        channel_offsets["y"] = (-y_mood * strength, y_mood * strength)
    for channel, (shadow_offset, highlight_offset) in channel_offsets.items():
        points: list[CurvePoint] = []
        for x in samples:
            if x < pivot:
                weight = ((pivot - x) / pivot) ** rolloff
                offset = shadow_offset * weight
            elif x > pivot:
                weight = ((x - pivot) / (1.0 - pivot)) ** rolloff
                offset = highlight_offset * weight
            else:
                offset = 0.0
            points.append(CurvePoint(x=x, y=_clamp_curve_value(x + offset)))
        curves[channel] = points
    return curves


def _params_to_lum_vs_sat_curve(params: list[GradeParam]) -> dict[str, Any] | None:
    payload = None
    for param in params:
        if param.key == PARAM_LUM_VS_SAT_CURVE and isinstance(param.value, bytes):
            payload = param.value
            break
    if payload is None:
        return None
    points = _decode_sat_vs_sat_payload(payload)
    if not points:
        return None
    candidates = [
        point for point in points
        if point.get("x_internal") is not None and point.get("y_internal") is not None
    ]
    if not candidates:
        return None
    min_y = min(abs(float(point["y_internal"])) for point in candidates)
    low_points = sorted(
        (point for point in candidates if abs(abs(float(point["y_internal"])) - min_y) < 1e-6),
        key=lambda point: float(point["x_internal"]),
    )
    center = low_points[len(low_points) // 2]
    return {
        "input_lum": round(lum_curve_input_lum_from_internal(float(center["x_internal"])), 6),
        "saturation": center["output_sat"],
        "points": points,
    }


__all__ = (
    'CURVE_CHANNEL_PARAMS',
    'CURVE_PARAM_CHANNELS',
    'CURVE_MODE_PARAM_KEYS',
    'HDR_GLOBAL_SEED_CURVE_PAYLOAD_B64',
    'HDR_GLOBAL_SEED_MODE_PARAM_KEYS',
    'CURVE_GUARD_VALUE',
    'CURVE_VISIBLE_MAX',
    'CURVE_GUI_SAMPLE_X',
    '_normalize_curve_domain_value',
    '_denormalize_curve_domain_value',
    'CURVE_GUI_SAMPLE_POINTS',
    '_decode_curve_points_payload',
    '_params_to_curve_points_dict',
    'hue_curve_input_hue_to_internal',
    'hue_curve_input_hue_from_internal',
    'hue_curve_rotate_to_internal',
    'hue_curve_rotate_from_internal',
    'hue_curve_saturation_to_internal',
    'hue_curve_saturation_from_internal',
    'hue_curve_lum_gain_to_internal',
    'hue_curve_lum_gain_from_internal',
    'sat_curve_input_sat_to_internal',
    'sat_curve_input_sat_from_internal',
    'sat_curve_output_sat_to_internal',
    'sat_curve_output_sat_from_internal',
    'sat_curve_lum_to_internal',
    'sat_curve_lum_from_internal',
    'lum_curve_input_lum_to_internal',
    'lum_curve_input_lum_from_internal',
    '_hue_curve_wrap_points',
    '_hue_curve_payload_from_internal',
    '_hue_vs_hue_payload',
    '_hue_curve_point_chunk',
    '_hue_curve_multi_point_payload',
    '_hue_curve_points_readback',
    '_sat_curve_point_chunk',
    '_sat_curve_multi_point_payload',
    '_sat_curve_points_readback',
    'parse_hue_curve_points_spec',
    'parse_sat_curve_points_spec',
    '_hue_vs_sat_payload',
    '_hue_vs_lum_payload',
    '_sat_vs_sat_payload',
    '_sat_vs_lum_payload',
    '_lum_vs_sat_payload',
    '_decode_hue_vs_hue_payload',
    '_decode_hue_vs_sat_payload',
    '_decode_hue_vs_lum_payload',
    '_decode_sat_vs_sat_payload',
    '_primary_hue_curve_point',
    '_params_to_hue_vs_hue_curve',
    '_params_to_hue_vs_sat_curve',
    '_params_to_hue_vs_lum_curve',
    '_params_to_sat_vs_sat_curve',
    '_params_to_sat_vs_lum_curve',
    '_interpolate_curve_points',
    '_curve_points_with_resolve_guards',
    '_curve_payload_with_guards',
    'parse_curve_points_spec',
    '_curve_points_for_readback',
    '_curve_points_match',
    '_validate_split_tone_amount',
    '_validate_split_tone_strength',
    '_validate_split_tone_pivot',
    '_validate_split_tone_rolloff',
    '_clamp_curve_value',
    'build_split_tone_curve_points',
    '_params_to_lum_vs_sat_curve',
)
