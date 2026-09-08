"""Power Windows helpers for Color Page DB operations."""

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
from .curves import *
from .hdr import *
from .node_graph import *


CIRCLE_POWER_WINDOW_KEYS = {
    PARAM_POWER_WINDOW_SHAPE,
    PARAM_POWER_WINDOW_INVERT,
    PARAM_POWER_WINDOW_OPACITY,
    PARAM_POWER_WINDOW_SIZE,
    PARAM_POWER_WINDOW_X_OFFSET,
    PARAM_POWER_WINDOW_Y_OFFSET,
    PARAM_POWER_WINDOW_SOFT_1,
    PARAM_POWER_WINDOW_GUI_PAN,
    PARAM_POWER_WINDOW_GUI_TILT,
}

GRADIENT_POWER_WINDOW_KEYS = {
    PARAM_POWER_WINDOW_GRADIENT_SHAPE,
    PARAM_POWER_WINDOW_GRADIENT_1,
    PARAM_POWER_WINDOW_GRADIENT_2,
    PARAM_POWER_WINDOW_GRADIENT_3,
    PARAM_POWER_WINDOW_GRADIENT_4,
    PARAM_POWER_WINDOW_GRADIENT_5,
    PARAM_POWER_WINDOW_GRADIENT_SIZE,
}

LINEAR_POWER_WINDOW_KEYS = {
    PARAM_POWER_WINDOW_LINEAR_1,
    PARAM_POWER_WINDOW_LINEAR_2,
    PARAM_POWER_WINDOW_LINEAR_3,
    PARAM_POWER_WINDOW_LINEAR_4,
    PARAM_POWER_WINDOW_LINEAR_POINTS,
    PARAM_POWER_WINDOW_LINEAR_5,
    PARAM_POWER_WINDOW_LINEAR_6,
    PARAM_POWER_WINDOW_LINEAR_7,
    PARAM_POWER_WINDOW_LINEAR_8,
    PARAM_POWER_WINDOW_LINEAR_9,
    PARAM_POWER_WINDOW_LINEAR_10,
    PARAM_POWER_WINDOW_LINEAR_OPACITY,
    PARAM_POWER_WINDOW_LINEAR_SHAPE,
    PARAM_POWER_WINDOW_LINEAR_11,
}

POLYGON_POWER_WINDOW_KEYS = {
    PARAM_POWER_WINDOW_POLYGON_SHAPE,
    PARAM_POWER_WINDOW_POLYGON_1,
    PARAM_POWER_WINDOW_POLYGON_POINTS,
    PARAM_POWER_WINDOW_POLYGON_2,
    PARAM_POWER_WINDOW_POLYGON_3,
    PARAM_POWER_WINDOW_POLYGON_4,
    PARAM_POWER_WINDOW_POLYGON_5,
    PARAM_POWER_WINDOW_POLYGON_6,
    PARAM_POWER_WINDOW_POLYGON_7,
}

CURVE_POWER_WINDOW_KEYS = {
    PARAM_POWER_WINDOW_CURVE_SHAPE,
    PARAM_POWER_WINDOW_CURVE_1,
    PARAM_POWER_WINDOW_CURVE_POINTS_1,
    PARAM_POWER_WINDOW_CURVE_POINTS_2,
    PARAM_POWER_WINDOW_CURVE_POINTS_3,
    PARAM_POWER_WINDOW_CURVE_2,
    PARAM_POWER_WINDOW_CURVE_3,
    PARAM_POWER_WINDOW_CURVE_4,
    PARAM_POWER_WINDOW_CURVE_5,
    PARAM_POWER_WINDOW_CURVE_CENTER_X,
    PARAM_POWER_WINDOW_CURVE_CENTER_Y,
}

POWER_WINDOW_KEYS = (
    CIRCLE_POWER_WINDOW_KEYS
    | GRADIENT_POWER_WINDOW_KEYS
    | LINEAR_POWER_WINDOW_KEYS
    | POLYGON_POWER_WINDOW_KEYS
    | CURVE_POWER_WINDOW_KEYS
)

POWER_WINDOW_PRIMARY_KEYS = {
    PARAM_LIFT_Y,
    PARAM_LIFT_R,
    PARAM_LIFT_G,
    PARAM_LIFT_B,
    PARAM_GAIN_Y,
    PARAM_GAIN_R,
    PARAM_GAIN_G,
    PARAM_GAIN_B,
    PARAM_GAIN_MASTER,
    PARAM_GAMMA_Y,
    PARAM_GAMMA_R,
    PARAM_GAMMA_G,
    PARAM_GAMMA_B,
    PARAM_GAMMA_MASTER,
    PARAM_SATURATION,
    PARAM_HUE,
    PARAM_CONTRAST,
    PARAM_PIVOT,
    PARAM_TEMPERATURE,
    PARAM_TINT,
    PARAM_LUM_MIX,
    PARAM_HIGHLIGHTS,
    PARAM_SHADOWS,
    PARAM_COLOR_BOOST,
    PARAM_MID_DETAIL,
}


def _power_window_node_index_and_params(proto_data: bytes) -> tuple[int | None, list[GradeParam]]:
    for index, node in enumerate(_split_grade_node_section(_extract_submessage(proto_data, [1, 7, 9]) or b"")[1], 1):
        f6 = _get_submessage(node, 6)
        f2 = _get_submessage(f6, 2) if f6 is not None else None
        if not f2:
            continue
        params = _parse_params_from_param_section(f2, node_index=index)
        keys = {param.key for param in params}
        if keys & CIRCLE_POWER_WINDOW_KEYS:
            return index, params
    return None, []


def _grade_node_params(node: bytes, *, node_index: int) -> list[GradeParam]:
    f6 = _get_submessage(node, 6)
    f2 = _get_submessage(f6, 2) if f6 is not None else None
    if not f2:
        return []
    return _parse_params_from_param_section(f2, node_index=node_index)


def _validate_power_window_target_node(
    nodes: list[bytes],
    *,
    node_index: int | None,
    shape_name: str,
    shape_keys: set[int],
    container_node_count: int | None = None,
    containers: list[bytes] | None = None,
) -> tuple[int | None, list[GradeParam], str | None]:
    if node_index is None:
        return None, [], None
    target = int(node_index)
    if target < 1:
        raise ValidationError(
            "Power Window target node index must be a positive integer.",
            details={"node_index": target, "minimum": 1},
            recoverability="not_applicable",
        )
    target_container = None
    target_grade_index = target
    if containers is not None:
        for position, container in enumerate(containers, 1):
            if _get_first_varint_field(container, 2) == target:
                target_container = container
                target_grade_index = position
                break
        if target_container is None and target <= len(containers):
            positional_container = containers[target - 1]
            positional_index = _get_first_varint_field(positional_container, 2)
            if positional_index in {None, target}:
                target_container = positional_container
                target_grade_index = target

    if target_grade_index > len(nodes):
        if (
            container_node_count is not None
            and target_grade_index == len(nodes) + 1
            and target <= int(container_node_count)
            and (
                target_container is None
                or _is_empty_serial_color_node_container(target_container)
            )
        ):
            return target_grade_index, [], "append"
        raise ValidationError(
            "Power Window target node index is out of range.",
            details={
                "node_index": target,
                "grade_node_index": target_grade_index,
                "grade_node_count": len(nodes),
                "color_node_count": container_node_count,
            },
            recoverability="not_applicable",
        )
    params = _grade_node_params(nodes[target_grade_index - 1], node_index=target_grade_index)
    keys = {param.key for param in params}
    existing_power_window_keys = keys & POWER_WINDOW_KEYS
    if existing_power_window_keys and not (existing_power_window_keys & shape_keys):
        raise APICallFailed(
            f"Color Page {shape_name} Power Window DB route found a different Power Window on the requested node.",
            details={
                "node_index": target,
                "requested_shape": shape_name,
                "existing_power_window_param_keys": [f"0x{key:08X}" for key in sorted(existing_power_window_keys)],
            },
            recoverability="manual",
        )
    if not existing_power_window_keys and keys:
        if target_container is not None and _is_empty_serial_color_node_container(target_container):
            return target_grade_index, [], "insert_before"
        raise APICallFailed(
            f"Color Page {shape_name} Power Window DB route will not replace a node that already contains non-window grade params.",
            details={
                "node_index": target,
                "grade_node_index": target_grade_index,
                "requested_shape": shape_name,
                "existing_param_keys": [f"0x{key:08X}" for key in sorted(keys)],
                "safe_sequence": [
                    "create an empty serial node",
                    "apply the Power Window to that node",
                    "then apply node-local wheel/primary corrections to the same node",
                ],
            },
            recoverability="not_applicable",
        )
    return target_grade_index, params, None


def _insert_grade_node_before_index(field9: bytes, new_node: bytes, before_node_index: int) -> bytes:
    fields, _nodes, _node_order = _split_grade_node_section(field9)
    result = bytearray()
    seen = 0
    inserted = False
    for fn, wt, raw, _sub in fields:
        if fn == 1 and wt == 2:
            seen += 1
            if seen == before_node_index:
                result.extend(_encode_length_delimited(1, new_node))
                inserted = True
        result.extend(raw)
    if not inserted:
        raise APICallFailed(
            "Color Page Power Window DB route could not find the insertion point for the requested node.",
            details={"before_node_index": before_node_index, "node_count": seen},
            recoverability="manual",
        )
    return bytes(result)


def _gradient_power_window_node_index_and_params(proto_data: bytes) -> tuple[int | None, list[GradeParam]]:
    for index, node in enumerate(_split_grade_node_section(_extract_submessage(proto_data, [1, 7, 9]) or b"")[1], 1):
        f6 = _get_submessage(node, 6)
        f2 = _get_submessage(f6, 2) if f6 is not None else None
        if not f2:
            continue
        params = _parse_params_from_param_section(f2, node_index=index)
        keys = {param.key for param in params}
        if keys & GRADIENT_POWER_WINDOW_KEYS:
            return index, params
    return None, []


def _linear_power_window_node_index_and_params(proto_data: bytes) -> tuple[int | None, list[GradeParam]]:
    for index, node in enumerate(_split_grade_node_section(_extract_submessage(proto_data, [1, 7, 9]) or b"")[1], 1):
        f6 = _get_submessage(node, 6)
        f2 = _get_submessage(f6, 2) if f6 is not None else None
        if not f2:
            continue
        params = _parse_params_from_param_section(f2, node_index=index)
        keys = {param.key for param in params}
        if keys & LINEAR_POWER_WINDOW_KEYS:
            return index, params
    return None, []


def _polygon_power_window_node_index_and_params(proto_data: bytes) -> tuple[int | None, list[GradeParam]]:
    for index, node in enumerate(_split_grade_node_section(_extract_submessage(proto_data, [1, 7, 9]) or b"")[1], 1):
        f6 = _get_submessage(node, 6)
        f2 = _get_submessage(f6, 2) if f6 is not None else None
        if not f2:
            continue
        params = _parse_params_from_param_section(f2, node_index=index)
        keys = {param.key for param in params}
        if keys & POLYGON_POWER_WINDOW_KEYS:
            return index, params
    return None, []


def _curve_power_window_node_index_and_params(proto_data: bytes) -> tuple[int | None, list[GradeParam]]:
    for index, node in enumerate(_split_grade_node_section(_extract_submessage(proto_data, [1, 7, 9]) or b"")[1], 1):
        f6 = _get_submessage(node, 6)
        f2 = _get_submessage(f6, 2) if f6 is not None else None
        if not f2:
            continue
        params = _parse_params_from_param_section(f2, node_index=index)
        keys = {param.key for param in params}
        if keys & CURVE_POWER_WINDOW_KEYS:
            return index, params
    return None, []


def _decode_power_window_points_payload(value: bytes) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    offset = 0
    while offset < len(value):
        try:
            tag, offset = _read_varint(value, offset)
        except ValueError:
            return []
        fn = tag >> 3
        wt = tag & 7
        if fn == 1 and wt == 2:
            try:
                length, offset = _read_varint(value, offset)
            except ValueError:
                return []
            message = value[offset:offset + length]
            offset += length
            if len(message) == 10 and message[0] == 0x0D and message[5] == 0x15:
                points.append((struct.unpack("<f", message[1:5])[0], struct.unpack("<f", message[6:10])[0]))
        elif wt == 0:
            try:
                _, offset = _read_varint(value, offset)
            except ValueError:
                return []
        elif wt == 1:
            offset += 8
        elif wt == 5:
            offset += 4
        elif wt == 2:
            try:
                length, offset = _read_varint(value, offset)
            except ValueError:
                return []
            offset += length
        else:
            return []
    return points


def _build_power_window_points_payload(points: list[tuple[float, float]]) -> bytes:
    result = bytearray()
    for x, y in points:
        result.extend(
            _encode_length_delimited(
                1,
                _encode_fixed32_field(1, struct.pack("<f", x))
                + _encode_fixed32_field(2, struct.pack("<f", y)),
            )
        )
    return bytes(result)


def _power_window_points_for_readback(points: list[tuple[float, float]]) -> list[dict[str, float]]:
    return [{"x": round(x, 6), "y": round(y, 6)} for x, y in points]


def _power_window_points_match(
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
        if abs(actual_x - expected_x) > tolerance or abs(actual_y - expected_y) > tolerance:
            return False
    return True


def _scaled_readback(value: Any, scale: float) -> float | None:
    if not isinstance(value, (int, float)):
        return None
    return round(float(value) / scale, 6)


def gradient_pan_to_internal(value: float) -> float:
    return (float(value) - POWER_WINDOW_GUI_PAN_CENTER) * POWER_WINDOW_GUI_PAN_SCALE


def gradient_pan_from_internal(value: float) -> float:
    return POWER_WINDOW_GUI_PAN_CENTER + (float(value) / POWER_WINDOW_GUI_PAN_SCALE)


def gradient_tilt_to_internal(value: float) -> float:
    return (float(value) - POWER_WINDOW_GUI_TILT_CENTER) * POWER_WINDOW_GUI_TILT_SCALE


def gradient_tilt_from_internal(value: float) -> float:
    return POWER_WINDOW_GUI_TILT_CENTER + (float(value) / POWER_WINDOW_GUI_TILT_SCALE)


def gradient_soft_1_to_internal(value: float) -> float:
    return float(value) * POWER_WINDOW_GRADIENT_SOFT_1_SCALE


def gradient_soft_1_from_internal(value: float) -> float:
    return float(value) / POWER_WINDOW_GRADIENT_SOFT_1_SCALE


def _power_window_readback(params: list[GradeParam]) -> dict[str, Any]:
    by_key = {param.key: param.value for param in params}
    if by_key.get(PARAM_POWER_WINDOW_CURVE_SHAPE) == POWER_WINDOW_CURVE_SHAPE_CODE:
        points_internal: list[dict[str, float]] = []
        expanded_internal: list[dict[str, float]] = []
        value = by_key.get(PARAM_POWER_WINDOW_CURVE_POINTS_1)
        if isinstance(value, bytes):
            expanded_points = _decode_power_window_points_payload(value)
            expanded_internal = [
                {"x": round(x, 6), "y": round(y, 6)}
                for x, y in expanded_points
            ]
            unique: list[tuple[float, float]] = []
            for point in expanded_points:
                if not unique or abs(point[0] - unique[-1][0]) > 0.001 or abs(point[1] - unique[-1][1]) > 0.001:
                    unique.append(point)
            if len(unique) > 1 and abs(unique[-1][0] - unique[0][0]) <= 0.001 and abs(unique[-1][1] - unique[0][1]) <= 0.001:
                unique.pop()
            points_internal = [{"x": round(x, 6), "y": round(y, 6)} for x, y in unique]
        return {
            "shape": "curve",
            "shape_code": by_key.get(PARAM_POWER_WINDOW_CURVE_SHAPE),
            "points_internal": points_internal,
            "expanded_points_internal": expanded_internal,
            "center_x": by_key.get(PARAM_POWER_WINDOW_CURVE_CENTER_X),
            "center_y": by_key.get(PARAM_POWER_WINDOW_CURVE_CENTER_Y),
            "params": [param.to_dict() for param in params],
        }
    if by_key.get(PARAM_POWER_WINDOW_POLYGON_SHAPE) == POWER_WINDOW_POLYGON_SHAPE_CODE:
        points_internal: list[dict[str, float]] = []
        value = by_key.get(PARAM_POWER_WINDOW_POLYGON_POINTS)
        if isinstance(value, bytes):
            points_internal = _power_window_points_for_readback(
                _decode_power_window_points_payload(value)
            )
        return {
            "shape": "polygon",
            "shape_code": by_key.get(PARAM_POWER_WINDOW_POLYGON_SHAPE),
            "points_internal": points_internal,
            "params": [param.to_dict() for param in params],
        }
    if by_key.get(PARAM_POWER_WINDOW_LINEAR_SHAPE) == POWER_WINDOW_LINEAR_SHAPE_CODE:
        soft_1_internal = by_key.get(PARAM_POWER_WINDOW_LINEAR_1)
        soft_2_internal = by_key.get(PARAM_POWER_WINDOW_LINEAR_2)
        soft_3_internal = by_key.get(PARAM_POWER_WINDOW_LINEAR_3)
        soft_4_internal = by_key.get(PARAM_POWER_WINDOW_LINEAR_4)
        return {
            "shape": "linear",
            "shape_code": by_key.get(PARAM_POWER_WINDOW_LINEAR_SHAPE),
            "soft_1": _scaled_readback(soft_1_internal, POWER_WINDOW_LINEAR_SOFT_SCALE),
            "soft_2": _scaled_readback(soft_2_internal, POWER_WINDOW_LINEAR_SOFT_SCALE),
            "soft_3": _scaled_readback(soft_3_internal, POWER_WINDOW_LINEAR_SOFT_SCALE),
            "soft_4": _scaled_readback(soft_4_internal, POWER_WINDOW_LINEAR_SOFT_SCALE),
            "soft_1_internal": soft_1_internal,
            "soft_2_internal": soft_2_internal,
            "soft_3_internal": soft_3_internal,
            "soft_4_internal": soft_4_internal,
            "x": by_key.get(PARAM_POWER_WINDOW_LINEAR_5),
            "y": by_key.get(PARAM_POWER_WINDOW_LINEAR_6),
            "width": by_key.get(PARAM_POWER_WINDOW_LINEAR_7),
            "height": by_key.get(PARAM_POWER_WINDOW_LINEAR_8),
            "opacity": _scaled_readback(
                by_key.get(PARAM_POWER_WINDOW_LINEAR_OPACITY),
                1.0 / POWER_WINDOW_LINEAR_OPACITY_SCALE,
            ),
            "opacity_internal": by_key.get(PARAM_POWER_WINDOW_LINEAR_OPACITY),
            "params": [param.to_dict() for param in params],
        }
    if set(by_key) & GRADIENT_POWER_WINDOW_KEYS:
        rotate_marker_internal = by_key.get(PARAM_POWER_WINDOW_GRADIENT_ROTATE)
        pan_internal = by_key.get(PARAM_POWER_WINDOW_GRADIENT_PAN)
        tilt_internal = by_key.get(PARAM_POWER_WINDOW_GRADIENT_TILT)
        soft_1_internal = by_key.get(PARAM_POWER_WINDOW_GRADIENT_SOFT_1)
        return {
            "shape": "gradient",
            "shape_code": by_key.get(PARAM_POWER_WINDOW_GRADIENT_SHAPE),
            "rotate_marker_internal": rotate_marker_internal,
            "pan": round(gradient_pan_from_internal(float(pan_internal)), 6)
            if isinstance(pan_internal, (int, float))
            else None,
            "pan_internal": pan_internal,
            "tilt": round(gradient_tilt_from_internal(float(tilt_internal)), 6)
            if isinstance(tilt_internal, (int, float))
            else None,
            "tilt_internal": tilt_internal,
            "soft_1": round(gradient_soft_1_from_internal(float(soft_1_internal)), 6)
            if isinstance(soft_1_internal, (int, float))
            else None,
            "soft_1_internal": soft_1_internal,
            "gradient_size": by_key.get(PARAM_POWER_WINDOW_GRADIENT_SOFT_1),
            "params": [param.to_dict() for param in params],
        }
    soft_1_internal = by_key.get(PARAM_POWER_WINDOW_SOFT_1)
    soft_1 = None
    if isinstance(soft_1_internal, (int, float)):
        soft_1 = float(soft_1_internal) / POWER_WINDOW_SOFT_1_SCALE
    pan_internal = by_key.get(PARAM_POWER_WINDOW_GUI_PAN)
    pan = None
    if isinstance(pan_internal, (int, float)):
        pan = POWER_WINDOW_GUI_PAN_CENTER + (float(pan_internal) / POWER_WINDOW_GUI_PAN_SCALE)
    tilt_internal = by_key.get(PARAM_POWER_WINDOW_GUI_TILT)
    tilt = None
    if isinstance(tilt_internal, (int, float)):
        tilt = POWER_WINDOW_GUI_TILT_CENTER + (float(tilt_internal) / POWER_WINDOW_GUI_TILT_SCALE)
    opacity_internal = by_key.get(PARAM_POWER_WINDOW_OPACITY)
    opacity = None
    if isinstance(opacity_internal, (int, float)):
        opacity = float(opacity_internal) * 100.0
    return {
        "shape": "circle" if by_key.get(PARAM_POWER_WINDOW_SHAPE) == POWER_WINDOW_CIRCLE_SHAPE_CODE else "unknown",
        "shape_code": by_key.get(PARAM_POWER_WINDOW_SHAPE),
        "invert": by_key.get(PARAM_POWER_WINDOW_INVERT) == 2,
        "invert_internal": by_key.get(PARAM_POWER_WINDOW_INVERT),
        "opacity": round(opacity, 6) if opacity is not None else None,
        "opacity_internal": opacity_internal,
        "size": by_key.get(PARAM_POWER_WINDOW_SIZE),
        "soft_1": round(soft_1, 6) if soft_1 is not None else None,
        "soft_1_internal": soft_1_internal,
        "pan": round(pan, 6) if pan is not None else None,
        "pan_internal": pan_internal,
        "tilt": round(tilt, 6) if tilt is not None else None,
        "tilt_internal": tilt_internal,
        "x_offset": by_key.get(PARAM_POWER_WINDOW_X_OFFSET),
        "y_offset": by_key.get(PARAM_POWER_WINDOW_Y_OFFSET),
        "params": [param.to_dict() for param in params],
    }


def _circle_power_window_updates(
    *,
    size: float,
    soft_1: float | None = None,
    pan: float | None = None,
    tilt: float | None = None,
    opacity: float | None = None,
) -> dict[int, float]:
    updates: dict[int, float] = {PARAM_POWER_WINDOW_SIZE: size}
    if opacity is not None:
        updates[PARAM_POWER_WINDOW_OPACITY] = opacity / 100.0
    if soft_1 is not None:
        updates[PARAM_POWER_WINDOW_SOFT_1] = soft_1 * POWER_WINDOW_SOFT_1_SCALE
    if pan is not None:
        updates[PARAM_POWER_WINDOW_GUI_PAN] = (pan - POWER_WINDOW_GUI_PAN_CENTER) * POWER_WINDOW_GUI_PAN_SCALE
    if tilt is not None:
        updates[PARAM_POWER_WINDOW_GUI_TILT] = (tilt - POWER_WINDOW_GUI_TILT_CENTER) * POWER_WINDOW_GUI_TILT_SCALE
    return updates


def _rebuild_circle_power_window_param_section(
    existing_section: bytes,
    *,
    size: float,
    soft_1: float | None = None,
    pan: float | None = None,
    tilt: float | None = None,
    opacity: float | None = None,
    invert: bool | None = None,
) -> bytes:
    delete_keys = {PARAM_POWER_WINDOW_INVERT} if invert is False else None
    section = _rebuild_param_section(
        existing_section,
        _circle_power_window_updates(size=size, soft_1=soft_1, pan=pan, tilt=tilt, opacity=opacity),
        delete_keys=delete_keys,
    )
    if invert is True:
        section = _rebuild_param_section_raw(
            section,
            {PARAM_POWER_WINDOW_INVERT: _build_varint_param_entry(PARAM_POWER_WINDOW_INVERT, 2)},
        )
    return section


def _build_circle_power_window_node(
    *,
    size: float,
    soft_1: float | None = None,
    pan: float | None = None,
    tilt: float | None = None,
    opacity: float | None = None,
    invert: bool | None = None,
) -> bytes:
    node = POWER_WINDOW_CIRCLE_NODE_TEMPLATE
    f6 = _get_submessage(node, 6)
    f2 = _get_submessage(f6, 2) if f6 is not None else None
    if f2 is None:
        raise APICallFailed(
            "Color Page Power Window DB route has an invalid Circle fixture.",
            recoverability="manual",
        )
    new_f2 = _rebuild_circle_power_window_param_section(
        f2,
        size=size,
        soft_1=soft_1,
        pan=pan,
        tilt=tilt,
        opacity=opacity,
        invert=invert,
    )
    return _replace_submessage_at_path(node, [6, 2], new_f2)


def _build_gradient_power_window_node() -> bytes:
    return POWER_WINDOW_GRADIENT_NODE_TEMPLATE


def validate_gradient_power_window_size(size: float) -> None:
    if not math.isfinite(size):
        raise ValidationError(
            "Gradient Power Window size must be a finite number.",
            details={"value": size},
            recoverability="not_applicable",
        )
    if size < 1.0 or size > 1000.0:
        raise ValidationError(
            "Gradient Power Window size must be between 1.0 and 1000.0.",
            details={"value": size, "minimum": 1.0, "maximum": 1000.0},
            recoverability="not_applicable",
        )


def _build_gradient_power_window_node_with_size(size: float) -> bytes:
    validate_gradient_power_window_size(size)
    if abs(size - 200.0) <= 0.001:
        return POWER_WINDOW_GRADIENT_NODE_TEMPLATE
    node = POWER_WINDOW_GRADIENT_NODE_TEMPLATE
    return _patch_gradient_power_window_node(node, soft_1_internal=size)


def _patch_gradient_power_window_node(
    node: bytes,
    *,
    soft_1_internal: float | None = None,
    pan: float | None = None,
    tilt: float | None = None,
) -> bytes:
    if soft_1_internal is not None:
        validate_gradient_power_window_size(soft_1_internal)
    if node.startswith(POWER_WINDOW_GRADIENT_LEGACY_NODE_HEADER):
        node = POWER_WINDOW_GRADIENT_GUI_NODE_HEADER + node[len(POWER_WINDOW_GRADIENT_LEGACY_NODE_HEADER):]
    f6 = _get_submessage(node, 6)
    f2 = _get_submessage(f6, 2) if f6 is not None else None
    if f2 is None:
        raise APICallFailed(
            "Color Page Gradient Power Window DB route has an invalid Gradient fixture.",
            recoverability="manual",
        )
    updates: dict[int, float] = {}
    if soft_1_internal is not None:
        updates[PARAM_POWER_WINDOW_GRADIENT_SOFT_1] = soft_1_internal
    if pan is not None:
        updates[PARAM_POWER_WINDOW_GRADIENT_PAN] = gradient_pan_to_internal(pan)
    if tilt is not None:
        updates[PARAM_POWER_WINDOW_GRADIENT_TILT] = gradient_tilt_to_internal(tilt)
    if not updates:
        return node
    new_f2 = _rebuild_param_section_raw(
        f2,
        {key: _build_param_entry(key, value) for key, value in updates.items()},
    )
    return _replace_submessage_at_path(node, [6, 2], new_f2)


def _patch_gradient_power_window_node_size(node: bytes, size: float) -> bytes:
    return _patch_gradient_power_window_node(node, soft_1_internal=size)


def _validate_linear_geometry_value(
    name: str,
    value: float | None,
    *,
    minimum: float,
    maximum: float,
) -> None:
    if value is None:
        return
    if not math.isfinite(value):
        raise ValidationError(
            f"Linear Power Window {name} must be a finite number.",
            details={"value": value},
            recoverability="not_applicable",
        )
    if value < minimum or value > maximum:
        raise ValidationError(
            f"Linear Power Window {name} must be between {minimum} and {maximum}.",
            details={"value": value, "minimum": minimum, "maximum": maximum},
            recoverability="not_applicable",
        )


def validate_linear_power_window_softness_value(name: str, value: float | None) -> None:
    if value is None:
        return
    if not math.isfinite(value):
        raise ValidationError(
            f"Linear Power Window {name} must be a finite number.",
            details={"value": value},
            recoverability="not_applicable",
        )
    if value < 0.0 or value > 62.5:
        raise ValidationError(
            f"Linear Power Window {name} must be between 0.0 and 62.5.",
            details={"value": value, "minimum": 0.0, "maximum": 62.5},
            recoverability="not_applicable",
        )


def _linear_power_window_updates(
    *,
    x: float | None = None,
    y: float | None = None,
    width: float | None = None,
    height: float | None = None,
    soft_1: float | None = None,
    soft_2: float | None = None,
    soft_3: float | None = None,
    soft_4: float | None = None,
    opacity: float | None = None,
) -> dict[int, float]:
    _validate_linear_geometry_value("x", x, minimum=-2.0, maximum=2.0)
    _validate_linear_geometry_value("y", y, minimum=-2.0, maximum=2.0)
    _validate_linear_geometry_value("width", width, minimum=0.05, maximum=4.0)
    _validate_linear_geometry_value("height", height, minimum=0.05, maximum=4.0)
    validate_linear_power_window_softness_value("soft_1", soft_1)
    validate_linear_power_window_softness_value("soft_2", soft_2)
    validate_linear_power_window_softness_value("soft_3", soft_3)
    validate_linear_power_window_softness_value("soft_4", soft_4)
    _validate_linear_geometry_value("opacity", opacity, minimum=0.0, maximum=100.0)
    updates: dict[int, float] = {}
    if x is not None:
        updates[PARAM_POWER_WINDOW_LINEAR_5] = x
    if y is not None:
        updates[PARAM_POWER_WINDOW_LINEAR_6] = y
    if width is not None:
        updates[PARAM_POWER_WINDOW_LINEAR_7] = width
    if height is not None:
        updates[PARAM_POWER_WINDOW_LINEAR_8] = height
    if soft_1 is not None:
        updates[PARAM_POWER_WINDOW_LINEAR_1] = soft_1 * POWER_WINDOW_LINEAR_SOFT_SCALE
    if soft_2 is not None:
        updates[PARAM_POWER_WINDOW_LINEAR_2] = soft_2 * POWER_WINDOW_LINEAR_SOFT_SCALE
    if soft_3 is not None:
        updates[PARAM_POWER_WINDOW_LINEAR_3] = soft_3 * POWER_WINDOW_LINEAR_SOFT_SCALE
    if soft_4 is not None:
        updates[PARAM_POWER_WINDOW_LINEAR_4] = soft_4 * POWER_WINDOW_LINEAR_SOFT_SCALE
    if opacity is not None:
        updates[PARAM_POWER_WINDOW_LINEAR_OPACITY] = opacity / POWER_WINDOW_LINEAR_OPACITY_SCALE
    return updates


def _build_linear_power_window_points_payload(
    *,
    x: float,
    y: float,
    width: float,
    height: float,
) -> bytes:
    center_x = float(x) * 768.0
    center_y = float(y) * 432.0
    half_width = float(width) * 384.0
    half_height = float(height) * 216.0
    return _build_power_window_points_payload(
        [
            (center_x - half_width, center_y - half_height),
            (center_x - half_width, center_y + half_height),
            (center_x + half_width, center_y + half_height),
            (center_x + half_width, center_y - half_height),
        ]
    )


def validate_linear_power_window_geometry(
    *,
    x: float | None = None,
    y: float | None = None,
    width: float | None = None,
    height: float | None = None,
    soft_1: float | None = None,
    soft_2: float | None = None,
    soft_3: float | None = None,
    soft_4: float | None = None,
    opacity: float | None = None,
) -> None:
    _linear_power_window_updates(
        x=x,
        y=y,
        width=width,
        height=height,
        soft_1=soft_1,
        soft_2=soft_2,
        soft_3=soft_3,
        soft_4=soft_4,
        opacity=opacity,
    )


def _build_linear_power_window_node(
    *,
    x: float | None = None,
    y: float | None = None,
    width: float | None = None,
    height: float | None = None,
    soft_1: float | None = None,
    soft_2: float | None = None,
    soft_3: float | None = None,
    soft_4: float | None = None,
    opacity: float | None = None,
) -> bytes:
    updates = _linear_power_window_updates(
        x=x,
        y=y,
        width=width,
        height=height,
        soft_1=soft_1,
        soft_2=soft_2,
        soft_3=soft_3,
        soft_4=soft_4,
        opacity=opacity,
    )
    if not updates:
        return POWER_WINDOW_LINEAR_NODE_TEMPLATE
    node = POWER_WINDOW_LINEAR_NODE_TEMPLATE
    f6 = _get_submessage(node, 6)
    f2 = _get_submessage(f6, 2) if f6 is not None else None
    if f2 is None:
        raise APICallFailed(
            "Color Page Linear Power Window DB route has an invalid Linear fixture.",
            recoverability="manual",
        )
    new_f2 = _rebuild_param_section(f2, updates)
    if any(value is not None for value in (x, y, width, height)):
        payload = _build_linear_power_window_points_payload(
            x=0.0 if x is None else x,
            y=0.0 if y is None else y,
            width=1.0 if width is None else width,
            height=1.0 if height is None else height,
        )
        new_f2 = _rebuild_param_section_raw(
            new_f2,
            {
                PARAM_POWER_WINDOW_LINEAR_POINTS: _build_bytes_param_entry(
                    PARAM_POWER_WINDOW_LINEAR_POINTS,
                    payload,
                    inner_field=9,
                ),
            },
        )
    return _replace_submessage_at_path(node, [6, 2], new_f2)


def _patch_linear_power_window_node(
    node: bytes,
    *,
    x: float | None = None,
    y: float | None = None,
    width: float | None = None,
    height: float | None = None,
    soft_1: float | None = None,
    soft_2: float | None = None,
    soft_3: float | None = None,
    soft_4: float | None = None,
    opacity: float | None = None,
) -> bytes:
    updates = _linear_power_window_updates(
        x=x,
        y=y,
        width=width,
        height=height,
        soft_1=soft_1,
        soft_2=soft_2,
        soft_3=soft_3,
        soft_4=soft_4,
        opacity=opacity,
    )
    if not updates:
        return node
    f6 = _get_submessage(node, 6)
    f2 = _get_submessage(f6, 2) if f6 is not None else None
    if f2 is None:
        raise APICallFailed(
            "Color Page Linear Power Window DB route could not find the existing Linear param section.",
            recoverability="manual",
        )
    new_f2 = _rebuild_param_section(f2, updates)
    if any(value is not None for value in (x, y, width, height)):
        existing_params = _parse_params_from_param_section(f2, node_index=1)
        by_key = {param.key: param.value for param in existing_params}
        payload = _build_linear_power_window_points_payload(
            x=float(by_key.get(PARAM_POWER_WINDOW_LINEAR_5, 0.0) if x is None else x),
            y=float(by_key.get(PARAM_POWER_WINDOW_LINEAR_6, 0.0) if y is None else y),
            width=float(by_key.get(PARAM_POWER_WINDOW_LINEAR_7, 1.0) if width is None else width),
            height=float(by_key.get(PARAM_POWER_WINDOW_LINEAR_8, 1.0) if height is None else height),
        )
        new_f2 = _rebuild_param_section_raw(
            new_f2,
            {
                PARAM_POWER_WINDOW_LINEAR_POINTS: _build_bytes_param_entry(
                    PARAM_POWER_WINDOW_LINEAR_POINTS,
                    payload,
                    inner_field=9,
                ),
            },
        )
    return _replace_submessage_at_path(node, [6, 2], new_f2)


def _strip_grade_node_params(node: bytes, keys: set[int]) -> bytes:
    if not keys:
        return node
    f6 = _get_submessage(node, 6)
    f2 = _get_submessage(f6, 2) if f6 is not None else None
    if f2 is None:
        return node
    new_f2 = _rebuild_param_section(f2, {}, delete_keys=keys)
    return _replace_submessage_at_path(node, [6, 2], new_f2)


def _upsert_power_window_in_color_node_container(
    base_proto: bytes,
    *,
    node_index: int,
    shape_name: str,
    shape_keys: set[int],
    build_node: Callable[[], bytes],
    patch_node: Callable[[bytes], bytes],
    node_order: bytes,
) -> tuple[bytes, bool, dict[str, Any]] | None:
    if int(node_index) <= 1:
        return None

    root = _get_submessage(base_proto, 1)
    containers = _root_color_node_containers(base_proto)
    target_container_position = None
    target_container = None
    for position, container in enumerate(containers, 1):
        if _get_first_varint_field(container, 2) == int(node_index):
            target_container_position = position
            target_container = container
            break
    if root is None or target_container is None or target_container_position is None:
        return None

    field9 = _get_submessage(target_container, 9) or SERIAL_NODE_GRAPH_ORDER
    _fields, nodes, _existing_order = _split_grade_node_section(field9)
    existing_params: list[GradeParam] = []
    window_node_position: int | None = None
    mixed_node_position: int | None = None

    for position, node in enumerate(nodes, 1):
        params = _grade_node_params(node, node_index=int(node_index))
        keys = {param.key for param in params}
        if keys & (POWER_WINDOW_KEYS - shape_keys):
            raise APICallFailed(
                f"Color Page {shape_name} Power Window DB route found a different Power Window on the requested node.",
                details={
                    "node_index": int(node_index),
                    "requested_shape": shape_name,
                    "existing_power_window_param_keys": [
                        f"0x{key:08X}" for key in sorted(keys & (POWER_WINDOW_KEYS - shape_keys))
                    ],
                },
                recoverability="manual",
            )
        if not (keys & shape_keys):
            continue
        window_node_position = position
        existing_params = params
        break

    new_field9 = field9
    created = window_node_position is None
    if window_node_position is not None:
        new_node = patch_node(nodes[window_node_position - 1])
        new_field9 = _replace_grade_node(new_field9, window_node_position, new_node)
        action = "updated"
    else:
        if mixed_node_position is not None:
            stripped_node = _strip_grade_node_params(nodes[mixed_node_position - 1], shape_keys)
            new_field9 = _replace_grade_node(new_field9, mixed_node_position, stripped_node)
            action = "migrated"
        else:
            action = "created"
        new_node = build_node()
        new_field9 = _insert_grade_node_before_order(new_field9, new_node, node_order)

    new_container = _replace_length_delimited_field(target_container, 9, new_field9)
    new_containers = list(containers)
    new_containers[target_container_position - 1] = new_container
    root_counter = _get_first_varint_field(root, 1) or len(new_containers) + 1
    new_root = _replace_root_color_node_containers(
        root,
        new_containers,
        root_counter=int(root_counter),
    )
    new_proto = _replace_submessage_at_path(base_proto, [1], new_root)
    new_params = _grade_node_params(new_node, node_index=int(node_index))
    readback = _power_window_readback(new_params)
    readback["node_index"] = int(node_index)
    readback["grade_payload_scope"] = "color_node_container"
    readback["action"] = action
    readback["previous"] = _power_window_readback(existing_params) if existing_params else None
    return new_proto, created, readback


def parse_power_window_points_spec(value: str) -> list[CurvePoint]:
    points: list[CurvePoint] = []
    for raw_pair in value.split(";"):
        pair = raw_pair.strip()
        if not pair:
            continue
        parts = [part.strip() for part in pair.split(",")]
        if len(parts) != 2:
            raise ValidationError(
                "Power Window point specs must use 'x,y;x,y' normalized pairs.",
                details={"pair": pair, "value": value},
                recoverability="not_applicable",
            )
        try:
            x = float(parts[0])
            y = float(parts[1])
        except ValueError as exc:
            raise ValidationError(
                "Power Window point specs must contain numeric x,y values.",
                details={"pair": pair, "value": value},
                recoverability="not_applicable",
            ) from exc
        if not math.isfinite(x) or not math.isfinite(y) or x < 0.0 or x > 1.0 or y < 0.0 or y > 1.0:
            raise ValidationError(
                "Power Window point specs must be normalized between 0 and 1.",
                details={"point": {"x": x, "y": y}},
                recoverability="not_applicable",
            )
        points.append(CurvePoint(x=x, y=y))
    if len(points) < 3:
        raise ValidationError(
            "Power Window requires at least three normalized points.",
            details={"value": value, "point_count": len(points)},
            recoverability="not_applicable",
        )
    return points


def _power_window_internal_points(
    points: list[CurvePoint],
    *,
    width: int,
    height: int,
) -> list[tuple[float, float]]:
    half_width = float(width) / 2.0
    half_height = float(height) / 2.0
    return [
        ((point.x * float(width)) - half_width, half_height - (point.y * float(height)))
        for point in points
    ]


def _power_window_curve_internal_points(
    points: list[CurvePoint],
    *,
    width: int,
    height: int,
) -> list[tuple[float, float]]:
    return _power_window_internal_points(points, width=width, height=height)


def _power_window_curve_expanded_points(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    if not points:
        return []
    expanded: list[tuple[float, float]] = [points[0], points[0]]
    for point in points[1:]:
        expanded.extend([point, point, point])
    expanded.extend([points[0], points[0]])
    return expanded


def _build_power_window_curve_points_payload(points: list[tuple[float, float]]) -> bytes:
    return _build_power_window_points_payload(_power_window_curve_expanded_points(points))


DEFAULT_POWER_WINDOW_POLYGON_POINTS = (
    CurvePoint(0.25, 0.75),
    CurvePoint(0.25, 0.25),
    CurvePoint(0.75, 0.25),
    CurvePoint(0.75, 0.75),
)


def _build_polygon_power_window_node(
    *,
    points: list[CurvePoint],
    width: int,
    height: int,
) -> bytes:
    node = POWER_WINDOW_POLYGON_NODE_TEMPLATE
    f6 = _get_submessage(node, 6)
    f2 = _get_submessage(f6, 2) if f6 is not None else None
    if f2 is None:
        raise APICallFailed(
            "Color Page Polygon Power Window DB route has an invalid Polygon fixture.",
            recoverability="manual",
        )
    internal_points = _power_window_internal_points(points, width=width, height=height)
    payload = _build_power_window_points_payload(internal_points)
    new_f2 = _rebuild_param_section_raw(
        f2,
        {
            PARAM_POWER_WINDOW_POLYGON_POINTS: _build_direct_bytes_param_entry(
                PARAM_POWER_WINDOW_POLYGON_POINTS,
                _encode_length_delimited(9, payload),
            ),
        },
    )
    return _replace_submessage_at_path(node, [6, 2], new_f2)


def _build_curve_power_window_node(
    *,
    points: list[CurvePoint],
    width: int,
    height: int,
) -> bytes:
    node = POWER_WINDOW_CURVE_NODE_TEMPLATE
    f6 = _get_submessage(node, 6)
    f2 = _get_submessage(f6, 2) if f6 is not None else None
    if f2 is None:
        raise APICallFailed(
            "Color Page Curve Power Window DB route has an invalid Curve fixture.",
            recoverability="manual",
        )
    internal_points = _power_window_curve_internal_points(points, width=width, height=height)
    expanded_points = _power_window_curve_expanded_points(internal_points)
    center_x = sum(point[0] for point in expanded_points) / len(expanded_points)
    center_y = sum(point[1] for point in expanded_points) / len(expanded_points)
    payload = _build_power_window_curve_points_payload(internal_points)
    raw_entries = {
        PARAM_POWER_WINDOW_CURVE_POINTS_1: _build_direct_bytes_param_entry(
            PARAM_POWER_WINDOW_CURVE_POINTS_1,
            _encode_length_delimited(9, payload),
        ),
        PARAM_POWER_WINDOW_CURVE_POINTS_2: _build_direct_bytes_param_entry(
            PARAM_POWER_WINDOW_CURVE_POINTS_2,
            _encode_length_delimited(9, payload),
        ),
        PARAM_POWER_WINDOW_CURVE_POINTS_3: _build_direct_bytes_param_entry(
            PARAM_POWER_WINDOW_CURVE_POINTS_3,
            _encode_length_delimited(9, payload),
        ),
        PARAM_POWER_WINDOW_CURVE_CENTER_X: _build_param_entry(PARAM_POWER_WINDOW_CURVE_CENTER_X, center_x),
        PARAM_POWER_WINDOW_CURVE_CENTER_Y: _build_param_entry(PARAM_POWER_WINDOW_CURVE_CENTER_Y, center_y),
    }
    new_f2 = _rebuild_param_section_raw(f2, raw_entries)
    return _replace_submessage_at_path(node, [6, 2], new_f2)


def _upsert_circle_power_window_proto(
    base_proto: bytes,
    *,
    node_index: int | None = None,
    size: float,
    soft_1: float | None = None,
    pan: float | None = None,
    tilt: float | None = None,
    opacity: float | None = None,
    invert: bool | None = None,
) -> tuple[bytes, bool, dict[str, Any]]:
    def _patch_circle_node(node: bytes) -> bytes:
        f2 = _get_submessage(_get_submessage(node, 6), 2)
        if f2 is None:
            raise APICallFailed(
                "Color Page Power Window DB route could not find the existing window param section.",
                details={"node_index": node_index},
                recoverability="manual",
            )
        new_f2 = _rebuild_circle_power_window_param_section(
            f2,
            size=size,
            soft_1=soft_1,
            pan=pan,
            tilt=tilt,
            opacity=opacity,
            invert=invert,
        )
        return _replace_submessage_at_path(node, [6, 2], new_f2)

    if node_index is not None and int(node_index) > 1:
        container_result = _upsert_power_window_in_color_node_container(
            base_proto,
            node_index=int(node_index),
            shape_name="Circle",
            shape_keys=CIRCLE_POWER_WINDOW_KEYS,
            build_node=lambda: _build_circle_power_window_node(
                size=size,
                soft_1=soft_1,
                pan=pan,
                tilt=tilt,
                opacity=opacity,
                invert=invert,
            ),
            patch_node=_patch_circle_node,
            node_order=POWER_WINDOW_NODE_ORDER,
        )
        if container_result is not None:
            return container_result

    field9 = _extract_submessage(base_proto, [1, 7, 9])
    if field9 is None:
        raise APICallFailed(
            "Color Page Power Window DB route requires an existing Color Page grade body.",
            details={"path": "1.7.9"},
            recoverability="manual",
        )

    fields, nodes, _node_order = _split_grade_node_section(field9)
    containers = _root_color_node_containers(base_proto)
    container_node_count = len(containers)
    target_index, target_params, target_insert_mode = _validate_power_window_target_node(
        nodes,
        node_index=node_index,
        shape_name="Circle",
        shape_keys=CIRCLE_POWER_WINDOW_KEYS,
        container_node_count=container_node_count,
        containers=containers,
    )
    existing_index, existing_params = _power_window_node_index_and_params(base_proto)
    if target_index is not None:
        existing_index = target_index
        existing_params = target_params
    if existing_index is not None:
        new_node = _patch_circle_node(nodes[existing_index - 1])
        new_field9 = _replace_grade_node(field9, existing_index, new_node)
        action = "updated"
    else:
        new_node = _build_circle_power_window_node(
            size=size,
            soft_1=soft_1,
            pan=pan,
            tilt=tilt,
            opacity=opacity,
            invert=invert,
        )
        if target_insert_mode == "insert_before" and target_index is not None:
            new_field9 = _insert_grade_node_before_index(field9, new_node, target_index)
        elif target_index is not None and target_index > len(nodes):
            new_field9 = _insert_grade_node_after_index(field9, new_node, len(nodes))
        else:
            new_field9 = _insert_grade_node_before_order(field9, new_node, POWER_WINDOW_NODE_ORDER)
        action = "created"

    new_proto = _replace_submessage_at_path(base_proto, [1, 7, 9], new_field9)
    new_index, new_params = _power_window_node_index_and_params(new_proto)
    readback = _power_window_readback(new_params)
    readback["node_index"] = new_index
    readback["action"] = action
    readback["previous"] = _power_window_readback(existing_params) if existing_params else None
    return new_proto, action == "created", readback


def _upsert_gradient_power_window_proto(
    base_proto: bytes,
    *,
    node_index: int | None = None,
    size: float | None = 200.0,
    pan: float | None = None,
    tilt: float | None = None,
) -> tuple[bytes, bool, dict[str, Any]]:
    if node_index is not None and int(node_index) > 1:
        container_result = _upsert_power_window_in_color_node_container(
            base_proto,
            node_index=int(node_index),
            shape_name="Gradient",
            shape_keys=GRADIENT_POWER_WINDOW_KEYS,
            build_node=lambda: _patch_gradient_power_window_node(
                _build_gradient_power_window_node_with_size(200.0 if size is None else size),
                pan=pan,
                tilt=tilt,
            ),
            patch_node=lambda node: _patch_gradient_power_window_node(
                node,
                soft_1_internal=size,
                pan=pan,
                tilt=tilt,
            ),
            node_order=POWER_WINDOW_GRADIENT_NODE_ORDER,
        )
        if container_result is not None:
            return container_result

    field9 = _extract_submessage(base_proto, [1, 7, 9])
    if field9 is None:
        raise APICallFailed(
            "Color Page Gradient Power Window DB route requires an existing Color Page grade body.",
            details={"path": "1.7.9"},
            recoverability="manual",
        )

    fields, nodes, _node_order = _split_grade_node_section(field9)
    containers = _root_color_node_containers(base_proto)
    container_node_count = len(containers)
    target_index, target_params, target_insert_mode = _validate_power_window_target_node(
        nodes,
        node_index=node_index,
        shape_name="Gradient",
        shape_keys=GRADIENT_POWER_WINDOW_KEYS,
        container_node_count=container_node_count,
        containers=containers,
    )
    existing_index, existing_params = _gradient_power_window_node_index_and_params(base_proto)
    circle_index, _circle_params = _power_window_node_index_and_params(base_proto)
    if target_index is not None:
        existing_index = target_index if target_params else None
        existing_params = target_params
    if target_index is None and existing_index is None and circle_index is not None:
        raise APICallFailed(
            "Color Page Gradient Power Window DB route found an existing non-gradient Power Window.",
            details={"existing_node_index": circle_index},
            recoverability="manual",
        )

    if existing_index is not None:
        node = nodes[existing_index - 1]
        new_node = _patch_gradient_power_window_node(
            node,
            soft_1_internal=size,
            pan=pan,
            tilt=tilt,
        )
        new_field9 = _replace_grade_node(field9, existing_index, new_node)
        action = "updated"
    else:
        if target_index is None and len(nodes) > 1:
            raise APICallFailed(
                "Color Page Gradient Power Window DB route cannot safely insert into an unknown multi-node window payload.",
                details={"node_count": len(nodes)},
                recoverability="manual",
            )
        new_node = _build_gradient_power_window_node_with_size(200.0 if size is None else size)
        new_node = _patch_gradient_power_window_node(new_node, pan=pan, tilt=tilt)
        if target_index is not None:
            if target_insert_mode == "insert_before":
                new_field9 = _insert_grade_node_before_index(field9, new_node, target_index)
            elif target_index > len(nodes):
                new_field9 = _insert_grade_node_after_index(field9, new_node, len(nodes))
            else:
                new_field9 = _replace_grade_node(field9, target_index, new_node)
        else:
            new_field9 = _insert_grade_node_before_order(field9, new_node, POWER_WINDOW_GRADIENT_NODE_ORDER)
        action = "created"

    new_proto = _replace_submessage_at_path(base_proto, [1, 7, 9], new_field9)
    new_index, new_params = _gradient_power_window_node_index_and_params(new_proto)
    readback = _power_window_readback(new_params)
    readback["node_index"] = new_index
    readback["action"] = action
    readback["previous"] = _power_window_readback(existing_params) if existing_params else None
    return new_proto, action == "created", readback


def _upsert_linear_power_window_proto(
    base_proto: bytes,
    *,
    node_index: int | None = None,
    x: float | None = None,
    y: float | None = None,
    width: float | None = None,
    height: float | None = None,
    soft_1: float | None = None,
    soft_2: float | None = None,
    soft_3: float | None = None,
    soft_4: float | None = None,
    opacity: float | None = None,
) -> tuple[bytes, bool, dict[str, Any]]:
    if node_index is not None and int(node_index) > 1:
        root = _get_submessage(base_proto, 1)
        containers = _root_color_node_containers(base_proto)
        target_container_position = None
        target_container = None
        for position, container in enumerate(containers, 1):
            if _get_first_varint_field(container, 2) == int(node_index):
                target_container_position = position
                target_container = container
                break
        if root is not None and target_container is not None and target_container_position is not None:
            field9 = _get_submessage(target_container, 9) or SERIAL_NODE_GRAPH_ORDER
            _fields, nodes, node_order = _split_grade_node_section(field9)
            existing_params: list[GradeParam] = []
            window_node_position: int | None = None
            for position, node in enumerate(nodes, 1):
                params = _grade_node_params(node, node_index=int(node_index))
                keys = {param.key for param in params}
                if not (keys & LINEAR_POWER_WINDOW_KEYS):
                    continue
                window_node_position = position
                existing_params = params
                break

            new_field9 = field9
            action = "created"
            if window_node_position is not None:
                new_node = _patch_linear_power_window_node(
                    nodes[window_node_position - 1],
                    x=x,
                    y=y,
                    width=width,
                    height=height,
                    soft_1=soft_1,
                    soft_2=soft_2,
                    soft_3=soft_3,
                    soft_4=soft_4,
                    opacity=opacity,
                )
                new_field9 = _replace_grade_node(new_field9, window_node_position, new_node)
                action = "updated"
            else:
                new_node = _build_linear_power_window_node(
                    x=x,
                    y=y,
                    width=width,
                    height=height,
                    soft_1=soft_1,
                    soft_2=soft_2,
                    soft_3=soft_3,
                    soft_4=soft_4,
                    opacity=opacity,
                )
                new_field9 = _insert_grade_node_before_order(
                    new_field9,
                    new_node,
                    POWER_WINDOW_LINEAR_NODE_ORDER,
                )
            new_container = _replace_length_delimited_field(target_container, 9, new_field9)
            new_containers = list(containers)
            new_containers[target_container_position - 1] = new_container
            root_counter = _get_first_varint_field(root, 1) or len(new_containers) + 1
            new_root = _replace_root_color_node_containers(
                root,
                new_containers,
                root_counter=int(root_counter),
            )
            new_proto = _replace_submessage_at_path(base_proto, [1], new_root)
            new_params = _grade_node_params(new_node, node_index=int(node_index))
            readback = _power_window_readback(new_params)
            readback["node_index"] = int(node_index)
            readback["grade_payload_scope"] = "color_node_container"
            readback["action"] = action
            readback["previous"] = _power_window_readback(existing_params) if existing_params else None
            return new_proto, action == "created", readback

    field9 = _extract_submessage(base_proto, [1, 7, 9])
    if field9 is None:
        raise APICallFailed(
            "Color Page Linear Power Window DB route requires an existing Color Page grade body.",
            details={"path": "1.7.9"},
            recoverability="manual",
        )

    _fields, nodes, _node_order = _split_grade_node_section(field9)
    containers = _root_color_node_containers(base_proto)
    container_node_count = len(containers)
    target_index, target_params, target_insert_mode = _validate_power_window_target_node(
        nodes,
        node_index=node_index,
        shape_name="Linear",
        shape_keys=LINEAR_POWER_WINDOW_KEYS,
        container_node_count=container_node_count,
        containers=containers,
    )
    existing_index, existing_params = _linear_power_window_node_index_and_params(base_proto)
    circle_index, _circle_params = _power_window_node_index_and_params(base_proto)
    gradient_index, _gradient_params = _gradient_power_window_node_index_and_params(base_proto)
    if target_index is not None:
        existing_index = target_index if target_params else None
        existing_params = target_params
    if target_index is None and existing_index is None and (circle_index is not None or gradient_index is not None):
        raise APICallFailed(
            "Color Page Linear Power Window DB route found an existing non-linear Power Window.",
            details={"existing_node_index": circle_index or gradient_index},
            recoverability="manual",
        )

    if existing_index is not None:
        new_node = _patch_linear_power_window_node(
            nodes[existing_index - 1],
            x=x,
            y=y,
            width=width,
            height=height,
            soft_1=soft_1,
            soft_2=soft_2,
            soft_3=soft_3,
            soft_4=soft_4,
            opacity=opacity,
        )
        new_field9 = _replace_grade_node(field9, existing_index, new_node)
        action = "updated"
    else:
        if target_index is None and len(nodes) > 1:
            raise APICallFailed(
                "Color Page Linear Power Window DB route cannot safely insert into an unknown multi-node window payload.",
                details={"node_count": len(nodes)},
                recoverability="manual",
            )
        new_node = _build_linear_power_window_node(
            x=x,
            y=y,
            width=width,
            height=height,
            soft_1=soft_1,
            soft_2=soft_2,
            soft_3=soft_3,
            soft_4=soft_4,
            opacity=opacity,
        )
        if target_index is not None:
            if target_insert_mode == "insert_before":
                new_field9 = _insert_grade_node_before_index(field9, new_node, target_index)
            elif target_index > len(nodes):
                new_field9 = _insert_grade_node_after_index(field9, new_node, len(nodes))
            else:
                new_field9 = _replace_grade_node(field9, target_index, new_node)
        else:
            new_field9 = _insert_grade_node_before_order(field9, new_node, POWER_WINDOW_LINEAR_NODE_ORDER)
        action = "created"

    new_proto = _replace_submessage_at_path(base_proto, [1, 7, 9], new_field9)
    new_index, new_params = _linear_power_window_node_index_and_params(new_proto)
    readback = _power_window_readback(new_params)
    readback["node_index"] = new_index
    readback["action"] = action
    readback["previous"] = _power_window_readback(existing_params) if existing_params else None
    return new_proto, action == "created", readback


def _upsert_polygon_power_window_proto(
    base_proto: bytes,
    *,
    node_index: int | None = None,
    points: list[CurvePoint],
    width: int,
    height: int,
) -> tuple[bytes, bool, dict[str, Any]]:
    if node_index is not None and int(node_index) > 1:
        container_result = _upsert_power_window_in_color_node_container(
            base_proto,
            node_index=int(node_index),
            shape_name="Polygon",
            shape_keys=POLYGON_POWER_WINDOW_KEYS,
            build_node=lambda: _build_polygon_power_window_node(points=points, width=width, height=height),
            patch_node=lambda _node: _build_polygon_power_window_node(points=points, width=width, height=height),
            node_order=POWER_WINDOW_POLYGON_NODE_ORDER,
        )
        if container_result is not None:
            return container_result

    field9 = _extract_submessage(base_proto, [1, 7, 9])
    if field9 is None:
        raise APICallFailed(
            "Color Page Polygon Power Window DB route requires an existing Color Page grade body.",
            details={"path": "1.7.9"},
            recoverability="manual",
        )

    _fields, nodes, _node_order = _split_grade_node_section(field9)
    containers = _root_color_node_containers(base_proto)
    container_node_count = len(containers)
    target_index, target_params, target_insert_mode = _validate_power_window_target_node(
        nodes,
        node_index=node_index,
        shape_name="Polygon",
        shape_keys=POLYGON_POWER_WINDOW_KEYS,
        container_node_count=container_node_count,
        containers=containers,
    )
    existing_index, existing_params = _polygon_power_window_node_index_and_params(base_proto)
    circle_index, _circle_params = _power_window_node_index_and_params(base_proto)
    gradient_index, _gradient_params = _gradient_power_window_node_index_and_params(base_proto)
    linear_index, _linear_params = _linear_power_window_node_index_and_params(base_proto)
    if target_index is not None:
        existing_index = target_index if target_params else None
        existing_params = target_params
    if target_index is None and existing_index is None and (circle_index is not None or gradient_index is not None or linear_index is not None):
        raise APICallFailed(
            "Color Page Polygon Power Window DB route found an existing non-polygon Power Window.",
            details={"existing_node_index": circle_index or gradient_index or linear_index},
            recoverability="manual",
        )

    new_node = _build_polygon_power_window_node(points=points, width=width, height=height)
    if existing_index is not None:
        new_field9 = _replace_grade_node(field9, existing_index, new_node)
        action = "updated"
    else:
        if target_index is None and len(nodes) > 1:
            raise APICallFailed(
                "Color Page Polygon Power Window DB route cannot safely insert into an unknown multi-node window payload.",
                details={"node_count": len(nodes)},
                recoverability="manual",
            )
        if target_index is not None:
            if target_insert_mode == "insert_before":
                new_field9 = _insert_grade_node_before_index(field9, new_node, target_index)
            elif target_index > len(nodes):
                new_field9 = _insert_grade_node_after_index(field9, new_node, len(nodes))
            else:
                new_field9 = _replace_grade_node(field9, target_index, new_node)
        else:
            new_field9 = _insert_grade_node_before_order(field9, new_node, POWER_WINDOW_POLYGON_NODE_ORDER)
        action = "created"

    new_proto = _replace_submessage_at_path(base_proto, [1, 7, 9], new_field9)
    new_index, new_params = _polygon_power_window_node_index_and_params(new_proto)
    readback = _power_window_readback(new_params)
    readback["node_index"] = new_index
    readback["action"] = action
    readback["previous"] = _power_window_readback(existing_params) if existing_params else None
    return new_proto, action == "created", readback


def _upsert_curve_power_window_proto(
    base_proto: bytes,
    *,
    node_index: int | None = None,
    points: list[CurvePoint],
    width: int,
    height: int,
) -> tuple[bytes, bool, dict[str, Any]]:
    if node_index is not None and int(node_index) > 1:
        container_result = _upsert_power_window_in_color_node_container(
            base_proto,
            node_index=int(node_index),
            shape_name="Curve",
            shape_keys=CURVE_POWER_WINDOW_KEYS,
            build_node=lambda: _build_curve_power_window_node(points=points, width=width, height=height),
            patch_node=lambda _node: _build_curve_power_window_node(points=points, width=width, height=height),
            node_order=POWER_WINDOW_CURVE_NODE_ORDER,
        )
        if container_result is not None:
            return container_result

    field9 = _extract_submessage(base_proto, [1, 7, 9])
    if field9 is None:
        raise APICallFailed(
            "Color Page Curve Power Window DB route requires an existing Color Page grade body.",
            details={"path": "1.7.9"},
            recoverability="manual",
        )

    _fields, nodes, _node_order = _split_grade_node_section(field9)
    containers = _root_color_node_containers(base_proto)
    container_node_count = len(containers)
    target_index, target_params, target_insert_mode = _validate_power_window_target_node(
        nodes,
        node_index=node_index,
        shape_name="Curve",
        shape_keys=CURVE_POWER_WINDOW_KEYS,
        container_node_count=container_node_count,
        containers=containers,
    )
    existing_index, existing_params = _curve_power_window_node_index_and_params(base_proto)
    circle_index, _circle_params = _power_window_node_index_and_params(base_proto)
    gradient_index, _gradient_params = _gradient_power_window_node_index_and_params(base_proto)
    linear_index, _linear_params = _linear_power_window_node_index_and_params(base_proto)
    polygon_index, _polygon_params = _polygon_power_window_node_index_and_params(base_proto)
    if target_index is not None:
        existing_index = target_index if target_params else None
        existing_params = target_params
    if target_index is None and existing_index is None and (
        circle_index is not None
        or gradient_index is not None
        or linear_index is not None
        or polygon_index is not None
    ):
        raise APICallFailed(
            "Color Page Curve Power Window DB route found an existing non-curve Power Window.",
            details={"existing_node_index": circle_index or gradient_index or linear_index or polygon_index},
            recoverability="manual",
        )

    new_node = _build_curve_power_window_node(points=points, width=width, height=height)
    if existing_index is not None:
        new_field9 = _replace_grade_node(field9, existing_index, new_node)
        action = "updated"
    else:
        if target_index is None and len(nodes) > 1:
            raise APICallFailed(
                "Color Page Curve Power Window DB route cannot safely insert into an unknown multi-node window payload.",
                details={"node_count": len(nodes)},
                recoverability="manual",
            )
        if target_index is not None:
            if target_insert_mode == "insert_before":
                new_field9 = _insert_grade_node_before_index(field9, new_node, target_index)
            elif target_index > len(nodes):
                new_field9 = _insert_grade_node_after_index(field9, new_node, len(nodes))
            else:
                new_field9 = _replace_grade_node(field9, target_index, new_node)
        else:
            new_field9 = _insert_grade_node_before_order(field9, new_node, POWER_WINDOW_CURVE_NODE_ORDER)
        action = "created"

    new_proto = _replace_submessage_at_path(base_proto, [1, 7, 9], new_field9)
    new_index, new_params = _curve_power_window_node_index_and_params(new_proto)
    readback = _power_window_readback(new_params)
    readback["node_index"] = new_index
    readback["action"] = action
    readback["previous"] = _power_window_readback(existing_params) if existing_params else None
    return new_proto, action == "created", readback


def _timeline_resolution(conn: Any) -> tuple[int, int]:
    timeline = getattr(conn, "timeline", None)
    width = 1920
    height = 1080
    if timeline is not None and hasattr(timeline, "GetSetting"):
        try:
            raw_width = timeline.GetSetting("timelineResolutionWidth")
            raw_height = timeline.GetSetting("timelineResolutionHeight")
            width = int(float(raw_width or width))
            height = int(float(raw_height or height))
        except Exception:
            width = 1920
            height = 1080
    if width <= 0 or height <= 0:
        return 1920, 1080
    return width, height


__all__ = (
    'CIRCLE_POWER_WINDOW_KEYS',
    'GRADIENT_POWER_WINDOW_KEYS',
    'LINEAR_POWER_WINDOW_KEYS',
    'POLYGON_POWER_WINDOW_KEYS',
    'CURVE_POWER_WINDOW_KEYS',
    'POWER_WINDOW_KEYS',
    '_grade_node_params',
    '_strip_grade_node_params',
    '_insert_grade_node_before_index',
    '_power_window_node_index_and_params',
    '_gradient_power_window_node_index_and_params',
    '_linear_power_window_node_index_and_params',
    '_polygon_power_window_node_index_and_params',
    '_curve_power_window_node_index_and_params',
    '_decode_power_window_points_payload',
    '_build_power_window_points_payload',
    '_power_window_points_for_readback',
    '_power_window_points_match',
    '_scaled_readback',
    'gradient_pan_to_internal',
    'gradient_pan_from_internal',
    'gradient_tilt_to_internal',
    'gradient_tilt_from_internal',
    'gradient_soft_1_to_internal',
    'gradient_soft_1_from_internal',
    '_power_window_readback',
    '_circle_power_window_updates',
    '_rebuild_circle_power_window_param_section',
    '_build_circle_power_window_node',
    '_build_gradient_power_window_node',
    'validate_gradient_power_window_size',
    '_build_gradient_power_window_node_with_size',
    '_patch_gradient_power_window_node',
    '_patch_gradient_power_window_node_size',
    '_validate_linear_geometry_value',
    'validate_linear_power_window_softness_value',
    '_linear_power_window_updates',
    'validate_linear_power_window_geometry',
    '_build_linear_power_window_node',
    'parse_power_window_points_spec',
    '_power_window_internal_points',
    '_power_window_curve_internal_points',
    '_power_window_curve_expanded_points',
    '_build_power_window_curve_points_payload',
    'DEFAULT_POWER_WINDOW_POLYGON_POINTS',
    '_build_polygon_power_window_node',
    '_build_curve_power_window_node',
    '_upsert_circle_power_window_proto',
    '_upsert_gradient_power_window_proto',
    '_upsert_linear_power_window_proto',
    '_upsert_polygon_power_window_proto',
    '_upsert_curve_power_window_proto',
    '_timeline_resolution',
)
