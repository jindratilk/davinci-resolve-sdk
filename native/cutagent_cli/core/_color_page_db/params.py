"""Params helpers for Color Page DB operations."""

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


def _new_uuid() -> str:
    return str(uuid.uuid4())


def _db_saved_time() -> int:
    return int(time.time() * 1000)


# ---------------------------------------------------------------------------
# Grade param extraction / injection
# ---------------------------------------------------------------------------

@dataclass
class GradeParam:
    key: int
    value: float | int | bytes
    value_kind: str = "float32"
    node_index: int = 1

    @property
    def key_hex(self) -> str:
        return f"0x{self.key:08X}"

    @property
    def name(self) -> str:
        return PARAM_NAMES.get(self.key, f"param_{self.key_hex}")

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "key": self.key_hex,
            "name": self.name,
            "node": self.node_index,
            "type": self.value_kind,
        }
        if isinstance(self.value, bytes):
            result["value_b64"] = base64.b64encode(self.value).decode("ascii")
            result["size"] = len(self.value)
        elif isinstance(self.value, float):
            result["value"] = round(self.value, 6)
        else:
            result["value"] = self.value
        return result


@dataclass(frozen=True)
class CurvePoint:
    x: float
    y: float

    def to_dict(self) -> dict[str, float]:
        return {"x": round(self.x, 6), "y": round(self.y, 6)}


DEFAULT_POWER_WINDOW_CURVE_POINTS = (
    CurvePoint(0.2821011702219645, 0.2855599297417535),
    CurvePoint(0.8073929786682129, 0.2855599297417535),
    CurvePoint(0.8073929786682129, 0.8389538517704717),
    CurvePoint(0.2821011702219645, 0.8389538517704717),
)


def _get_submessage(data: bytes, target_field: int) -> bytes | None:
    """Get the first length-delimited field with the given number."""
    offset = 0
    while offset < len(data):
        try:
            tag, offset = _read_varint(data, offset)
        except ValueError:
            break
        fn = tag >> 3
        wt = tag & 7
        if wt == 0:
            try:
                _, offset = _read_varint(data, offset)
            except ValueError:
                return None
        elif wt == 1:
            offset += 8
        elif wt == 5:
            offset += 4
        elif wt == 2:
            length, offset = _read_varint(data, offset)
            if fn == target_field:
                return data[offset:offset + length]
            offset += length
        else:
            break
    return None


def _get_all_submessages(data: bytes, target_field: int) -> list[bytes]:
    """Get all instances of a repeated length-delimited field."""
    results: list[bytes] = []
    offset = 0
    while offset < len(data):
        try:
            tag, offset = _read_varint(data, offset)
        except ValueError:
            break
        fn = tag >> 3
        wt = tag & 7
        if wt == 0:
            try:
                _, offset = _read_varint(data, offset)
            except ValueError:
                return results
        elif wt == 1:
            offset += 8
        elif wt == 5:
            offset += 4
        elif wt == 2:
            try:
                length, offset = _read_varint(data, offset)
            except ValueError:
                return results
            if fn == target_field:
                results.append(data[offset:offset + length])
            offset += length
        else:
            break
    return results


def _parse_single_param(data: bytes) -> GradeParam | None:
    """Parse a single param entry.

    Known value encodings observed in DaVinci Resolve 21 Color Page DB payloads:
      {1: key, 2: {1: fixed32}} -> float32 value
      {1: key, 2: {2: varint}}  -> integer/mode value
      {1: key, 2: {3: bytes}}   -> bytes payload, used by some palettes
    """
    off = 0
    param_key: int | None = None
    param_value: float | int | bytes | None = None
    value_kind = "unknown"

    while off < len(data):
        try:
            tag, off = _read_varint(data, off)
        except ValueError:
            break
        fn = tag >> 3
        wt = tag & 7

        if fn == 1 and wt == 0:
            param_key, off = _read_varint(data, off)
        elif fn == 2 and wt == 2:
            length, off = _read_varint(data, off)
            sub = data[off:off + length]
            off += length
            if len(sub) >= 5:
                inner_tag, ioff = _read_varint(sub, 0)
                inner_fn = inner_tag >> 3
                inner_wt = inner_tag & 7
                if inner_fn == 1 and inner_wt == 5 and len(sub) >= ioff + 4:
                    param_value = struct.unpack('<f', sub[ioff:ioff + 4])[0]
                    value_kind = "float32"
                elif inner_fn == 2 and inner_wt == 0:
                    param_value, _ = _read_varint(sub, ioff)
                    value_kind = "varint"
                elif inner_fn in {3, 8, 9, 12, 24, 27, 28} and inner_wt == 2:
                    length, inner_offset = _read_varint(sub, ioff)
                    param_value = sub[inner_offset:inner_offset + length]
                    value_kind = "bytes"
                elif inner_fn == 16 and inner_wt == 2:
                    param_value = sub
                    value_kind = "bytes"
            elif len(sub) >= 2:
                inner_tag, ioff = _read_varint(sub, 0)
                inner_fn = inner_tag >> 3
                inner_wt = inner_tag & 7
                if inner_fn == 2 and inner_wt == 0:
                    param_value, _ = _read_varint(sub, ioff)
                    value_kind = "varint"
        elif wt == 0:
            _, off = _read_varint(data, off)
        elif wt == 1:
            off += 8
        elif wt == 5:
            off += 4
        elif wt == 2:
            length, off = _read_varint(data, off)
            off += length
        else:
            break

    if param_key is not None and param_value is not None:
        return GradeParam(key=param_key, value=param_value, value_kind=value_kind)
    return None


def _parse_params_from_param_section(param_section: bytes, *, node_index: int) -> list[GradeParam]:
    params: list[GradeParam] = []
    entries = _get_all_submessages(param_section, 3)
    for entry in entries:
        param = _parse_single_param(entry)
        if param is not None:
            param.node_index = node_index
            params.append(param)
    return params


def _param_parser_first_varint_field(data: bytes, field_number: int) -> int | None:
    offset = 0
    while offset < len(data):
        try:
            tag, offset = _read_varint(data, offset)
        except ValueError:
            return None
        fn = tag >> 3
        wt = tag & 7
        if wt == 0:
            try:
                value, offset = _read_varint(data, offset)
            except ValueError:
                return None
            if fn == field_number:
                return value
        elif wt == 1:
            offset += 8
        elif wt == 5:
            offset += 4
        elif wt == 2:
            try:
                length, offset = _read_varint(data, offset)
            except ValueError:
                return None
            offset += length
        else:
            return None
    return None


def _parse_params_from_proto(proto_data: bytes) -> list[GradeParam]:
    """Extract all grade parameter key-value pairs from VersionBody protobuf.

    Walks every Color node container:
      root → field 1 → repeated field 7 → field 9 → repeated field 1 → field 6 → field 2 → repeated field 3
    Each field 3 entry: {1: param_key (varint), 2: {1: float32_le (fixed32)}}
    """
    params: list[GradeParam] = []

    root = _get_submessage(proto_data, 1)
    if root is None:
        return params

    containers = _get_all_submessages(root, 7)
    for position, container in enumerate(containers, 1):
        node_index = _param_parser_first_varint_field(container, 2) or position
        field9 = _get_submessage(container, 9)
        if field9 is None:
            continue
        nodes = _get_all_submessages(field9, 1)
        for node in nodes:
            f6 = _get_submessage(node, 6)
            if not f6:
                continue
            param_section = _get_submessage(f6, 2)
            if not param_section:
                continue
            params.extend(_parse_params_from_param_section(param_section, node_index=int(node_index)))

    return params


def _params_to_node_dicts(params: list[GradeParam]) -> list[dict[str, Any]]:
    nodes: dict[int, list[dict[str, Any]]] = {}
    for param in params:
        nodes.setdefault(param.node_index, []).append(param.to_dict())
    return [
        {"index": index, "params": node_params}
        for index, node_params in sorted(nodes.items())
    ]


def _params_to_curves_dict(params: list[GradeParam]) -> dict[str, Any]:
    values = {param.key: param.value for param in params if isinstance(param.value, float)}
    internal = {
        "y": values.get(PARAM_CURVE_HIGH_Y, 1.0),
        "red": values.get(PARAM_CURVE_HIGH_R, 1.0),
        "green": values.get(PARAM_CURVE_HIGH_G, 1.0),
        "blue": values.get(PARAM_CURVE_HIGH_B, 1.0),
    }
    result: dict[str, Any] = {
        "custom_endpoint_internal": internal,
        "custom_endpoint_ui": {
            channel: round(curve_endpoint_internal_to_ui(value), 3)
            for channel, value in internal.items()
        },
    }
    control_points = _params_to_curve_points_dict(params)
    if control_points:
        result["control_points"] = control_points
    hue_vs_hue = _params_to_hue_vs_hue_curve(params)
    if hue_vs_hue:
        result["hue_vs_hue"] = hue_vs_hue
    hue_vs_sat = _params_to_hue_vs_sat_curve(params)
    if hue_vs_sat:
        result["hue_vs_sat"] = hue_vs_sat
    hue_vs_lum = _params_to_hue_vs_lum_curve(params)
    if hue_vs_lum:
        result["hue_vs_lum"] = hue_vs_lum
    sat_vs_sat = _params_to_sat_vs_sat_curve(params)
    if sat_vs_sat:
        result["sat_vs_sat"] = sat_vs_sat
    sat_vs_lum = _params_to_sat_vs_lum_curve(params)
    if sat_vs_lum:
        result["sat_vs_lum"] = sat_vs_lum
    lum_vs_sat = _params_to_lum_vs_sat_curve(params)
    if lum_vs_sat:
        result["lum_vs_sat"] = lum_vs_sat
    return result


__all__ = (
    '_new_uuid',
    '_db_saved_time',
    'GradeParam',
    'CurvePoint',
    'DEFAULT_POWER_WINDOW_CURVE_POINTS',
    '_get_submessage',
    '_get_all_submessages',
    '_parse_single_param',
    '_parse_params_from_param_section',
    '_parse_params_from_proto',
    '_params_to_node_dicts',
    '_params_to_curves_dict',
)
