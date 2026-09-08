"""Native Color Warper payload helpers for Color Page DB operations."""

from __future__ import annotations

import math
import sqlite3
import struct
import uuid
from typing import Any

from ...errors import APICallFailed, ValidationError
from ..db_session import DiskDbMutationSession, execute_sqlite_disk_db_mutation
from ..db_timeline_rows import find_ti_item_row
from .constants import *
from .proto_codec import *
from .version_body import *
from .params import *
from .proto_sections import *
from .cst_hsv import *
from .cst_hsv import _find_param_write_container, _replace_param_write_container
from .grade_state import *


_HUE_SAT_TEMPLATE_PROTO_HEX = (
    "0a8903080110011a4808800f10b8081d0000803f20800f28b808350000803f38800f40b80848ffffffff0f"
    "7a240000803f0000000000000000000000000000803f0000000000000000000000000000803f3a920208011"
    "00120be0128b4013801402c4aed010ae3010801180132dc0112d90108011a5f08a18280b00812579a0154"
    "080112060416101c220a1a48508bed3e4c8dec3e000000003f2db63e2e35b23e00000000efa1c83ee3"
    "a7c53e000000008fb8a33e7ac29e3e00000000df43913ec54f8b3e00000000a016db3e971ad93e00"
    "0000001a1308a68280b008120b72090a072400202122231f1a0d08a98280b008120572030a01221a0a"
    "08ac8280b0081202100c1a0a08ad8280b0081202100c1a1408b08280b008120c620a0a080000800000"
    "0080001a0a08b38280b008120220011a0a08b68280b008120210021a0a08ba8280b0081202100212050"
    "304050612520c0a0a08818080800c1202100260c9cc9885214a0e080110501a08080110401801200152"
    "0e080210401a080802104018022001609299b18a4220b8ddbb9340"
)

_CHROMA_LUMA_TEMPLATE_PROTO_HEX = (
    "0a8205080110011a4808800f10b8081d0000803f20800f28b808350000803f38800f40b80848ffffffff0f"
    "7a240000803f0000000000000000000000000000803f0000000000000000000000000000803f3a8b0408"
    "01100120be0128b4013801402c4ae6030adc030801180132d50312d20308011ad90208a28280b00812d0"
    "029a01cc020801121912130c0f08090a0b28242526271d201e211f18191a161710111aac02aa563e3f"
    "abaa2a3e00000000542b5f3fabaa2a3e0000000055405a3fabaa2a3e00000000a902523eabaaaa3e00"
    "000000aa563e3eabaa2a3e00000000aa56be3eabaa2a3e00000000ffc00e3fabaa2a3e00000000aa80"
    "343fabaa2a3e0000000055405a3f5555553f00000000aa563e3e5555553f00000000aa56be3e555555"
    "3f00000000ffc00e3f5555553f00000000aa80343f5555553f00000000a902523eabaa2a3f00000000"
    "aa563e3fabaa2a3f00000000a902d23eabaa2a3f00000000542b5f3fabaa2a3f00000000fe811d3fab"
    "aa2a3f00000000fe422c3f0000003f00000000a92c483f0000003f000000005416643f0000003f0000"
    "0000a8ae653e0000003f00000000a8aee53e0000003f00000000a902d23eabaaaa3e00000000fe811d"
    "3fabaaaa3e000000001a1108a78280b008120972070a052a060030181a0d08aa8280b008120572030a"
    "01181a0a08ae8280b0081202100c1a0a08af8280b0081202100c1a1408b18280b008120c620a0a0800"
    "008000000080001a0a08b48280b008120220011a0a08b68280b008120210021a0a08ba8280b0081202100"
    "412050304050612520c0a0a08818080800c1202100260d79888ff224a0e080110501a08080110401801"
    "2001520e080210401a08080210401802200160aeb190fe452098bac6d845"
)

_HUE_SAT_BLOCK_MARKER = b"\x1a\x48"
_HUE_SAT_POINT_COUNT = 6
_CHROMA_LUMA_BLOCK_MARKER = b"\x1a\xac\x02"
_CHROMA_LUMA_POINT_COUNT = 25
_COLOR_WARPER_PARAM_KEYS = {
    PARAM_COLOR_WARPER_HUE_SAT_WIDTH,
    PARAM_COLOR_WARPER_HUE_SAT_HEIGHT,
    PARAM_COLOR_WARPER_HUE_SAT_SELECTION,
    PARAM_COLOR_WARPER_CHROMA_LUMA_WIDTH,
    PARAM_COLOR_WARPER_CHROMA_LUMA_HEIGHT,
    PARAM_COLOR_WARPER_CHROMA_LUMA_SELECTION,
    PARAM_COLOR_WARPER_MODE,
    PARAM_COLOR_WARPER_SUBMODE,
    PARAM_COLOR_WARPER_CHROMA_STROKE,
    PARAM_COLOR_WARPER_PANEL_MODE,
}


def _require_unit_float(name: str, value: float) -> float:
    number = float(value)
    if not math.isfinite(number) or number < 0.0 or number > 1.0:
        raise ValidationError(
            "Color Warper coordinates and range controls must be finite numbers between 0 and 1.",
            details={"name": name, "value": value, "minimum": 0.0, "maximum": 1.0},
            recoverability="not_applicable",
        )
    return number


def _normalize_mesh_points(points: list[tuple[float, float]], *, expected_count: int, label: str) -> list[tuple[float, float]]:
    if len(points) != expected_count:
        raise ValidationError(
            f"Color Warper {label} mesh requires exactly {expected_count} x,y points.",
            details={"label": label, "expected_count": expected_count, "actual_count": len(points)},
            recoverability="not_applicable",
        )
    normalized: list[tuple[float, float]] = []
    for index, (x_value, y_value) in enumerate(points):
        normalized.append((
            _require_unit_float(f"{label}[{index}].x", x_value),
            _require_unit_float(f"{label}[{index}].y", y_value),
        ))
    return normalized


def _pack_mesh_points(points: list[tuple[float, float]]) -> bytes:
    payload = bytearray()
    for x_value, y_value in points:
        payload.extend(struct.pack("<f", float(x_value)))
        payload.extend(struct.pack("<f", float(y_value)))
        payload.extend(struct.pack("<f", 0.0))
    return bytes(payload)


def _unpack_mesh_points(payload: bytes, *, expected_count: int) -> list[dict[str, float]]:
    if len(payload) != expected_count * 12:
        return []
    points: list[dict[str, float]] = []
    for offset in range(0, len(payload), 12):
        x_value = struct.unpack("<f", payload[offset:offset + 4])[0]
        y_value = struct.unpack("<f", payload[offset + 4:offset + 8])[0]
        z_value = struct.unpack("<f", payload[offset + 8:offset + 12])[0]
        if not all(math.isfinite(value) for value in (x_value, y_value, z_value)):
            return []
        if abs(z_value) > 0.000001:
            return []
        points.append({"x": round(float(x_value), 6), "y": round(float(y_value), 6)})
    return points


def _find_hue_sat_mesh_block(proto: bytes) -> tuple[int, bytes] | None:
    """Return the verified Hue-Saturation six-point mesh block offset and payload."""
    offset = 0
    while True:
        marker_index = proto.find(_HUE_SAT_BLOCK_MARKER, offset)
        if marker_index < 0:
            return None
        start = marker_index + len(_HUE_SAT_BLOCK_MARKER)
        payload = proto[start:start + (_HUE_SAT_POINT_COUNT * 12)]
        points = _unpack_mesh_points(payload, expected_count=_HUE_SAT_POINT_COUNT)
        if points and all(0.0 <= point["x"] <= 1.0 and 0.0 <= point["y"] <= 1.0 for point in points):
            return start, payload
        offset = marker_index + 1


def _find_chroma_luma_mesh_block(proto: bytes) -> tuple[int, bytes] | None:
    """Return the verified Chroma-Luma Grid 1 twenty-five-point mesh block offset and payload."""
    marker_index = proto.find(_CHROMA_LUMA_BLOCK_MARKER)
    if marker_index < 0:
        return None
    start = marker_index + len(_CHROMA_LUMA_BLOCK_MARKER)
    payload = proto[start:start + (_CHROMA_LUMA_POINT_COUNT * 12)]
    points = _unpack_mesh_points(payload, expected_count=_CHROMA_LUMA_POINT_COUNT)
    if not points:
        return None
    return start, payload


def _color_warper_mesh_template(mode: str) -> tuple[bytes, set[int]]:
    if mode == "hue_saturation":
        return bytes.fromhex(_HUE_SAT_TEMPLATE_PROTO_HEX), {
            PARAM_COLOR_WARPER_HUE_SAT_WIDTH,
            PARAM_COLOR_WARPER_HUE_SAT_HEIGHT,
            PARAM_COLOR_WARPER_HUE_SAT_SELECTION,
            PARAM_COLOR_WARPER_MODE,
            PARAM_COLOR_WARPER_PANEL_MODE,
        }
    if mode == "chroma_luma_grid1":
        return bytes.fromhex(_CHROMA_LUMA_TEMPLATE_PROTO_HEX), {
            PARAM_COLOR_WARPER_CHROMA_LUMA_WIDTH,
            PARAM_COLOR_WARPER_CHROMA_LUMA_HEIGHT,
            PARAM_COLOR_WARPER_CHROMA_LUMA_SELECTION,
            PARAM_COLOR_WARPER_MODE,
            PARAM_COLOR_WARPER_PANEL_MODE,
        }
    raise ValidationError(
        "Unsupported Color Warper mesh mode.",
        details={"mode": mode, "allowed": ["hue_saturation", "chroma_luma_grid1"]},
        recoverability="not_applicable",
    )


def _extract_raw_param_entries(proto: bytes, keys: set[int] | None = None) -> dict[int, bytes]:
    match = _find_param_write_container(proto, 1)
    if match is None:
        return {}
    _root, _containers, _position, _container, _field9, nodes, _node_order = match
    if not nodes:
        return {}
    f6 = _get_submessage(nodes[0], 6)
    param_section = _get_submessage(f6, 2) if f6 else None
    if not param_section:
        return {}
    entries: dict[int, bytes] = {}
    offset = 0
    while offset < len(param_section):
        try:
            tag, offset = _read_varint(param_section, offset)
        except ValueError:
            break
        fn = tag >> 3
        wt = tag & 7
        if wt == 2:
            try:
                length, offset = _read_varint(param_section, offset)
            except ValueError:
                break
            entry = param_section[offset:offset + length]
            offset += length
            if fn != 3:
                continue
            param = _parse_single_param(entry)
            if param is not None and (keys is None or param.key in keys):
                entries[param.key] = entry
        elif wt == 0:
            _, offset = _read_varint(param_section, offset)
        elif wt == 1:
            offset += 8
        elif wt == 5:
            offset += 4
        else:
            break
    return entries


def _raise_warper_scaffold_ofx_loss(label: str, *, mode: str, tool_block_size: int | None = None) -> None:
    details: dict[str, Any] = {
        "mode": mode,
        "reason": "mesh_scaffold_would_replace_ofx_tool_payload",
        "supported_safe_paths": [
            "existing_color_warper_mesh_block",
            "node_1_param_only_grade_body",
            "empty_baseline_grade_body",
        ],
        "required_next_step": "Create the Color Warper mesh on a clean serial node, or add a verified field-10 tool merge route.",
    }
    if tool_block_size is not None:
        details["tool_block_size"] = int(tool_block_size)
    raise APICallFailed(
        f"Color Warper {label} mesh scaffold cannot be inserted into a node with existing OFX tool payloads yet.",
        details=details,
        recoverability="manual",
    )


def _replace_mesh_block(proto: bytes, *, mode: str, points: list[tuple[float, float]]) -> bytes:
    if mode == "hue_saturation":
        block = _find_hue_sat_mesh_block(proto)
        expected_count = _HUE_SAT_POINT_COUNT
        label = "Hue-Saturation"
    elif mode == "chroma_luma_grid1":
        block = _find_chroma_luma_mesh_block(proto)
        expected_count = _CHROMA_LUMA_POINT_COUNT
        label = "Chroma-Luma Grid 1"
    else:
        raise ValidationError(
            "Unsupported Color Warper mesh mode.",
            details={"mode": mode, "allowed": ["hue_saturation", "chroma_luma_grid1"]},
            recoverability="not_applicable",
        )
    if block is None:
        existing_match = _find_param_write_container(proto, 1)
        if existing_match is not None:
            _root, _containers, _position, existing_container, _field9, existing_nodes, _node_order = existing_match
            existing_tool_block = _get_submessage(existing_container, 10)
            if existing_tool_block is None and existing_nodes:
                existing_tool_block = _get_submessage(existing_nodes[0], 10)
            if existing_tool_block:
                _raise_warper_scaffold_ofx_loss(label, mode=mode, tool_block_size=len(existing_tool_block))
            existing_entries = _extract_raw_param_entries(proto)
            risky_keys = sorted(key for key in existing_entries if key in POWER_WINDOW_KEYS)
            if risky_keys:
                raise APICallFailed(
                    f"Color Warper {label} mesh scaffold cannot be inserted into a node with Power Window payloads yet.",
                    details={
                        "mode": mode,
                        "reason": "mesh_scaffold_would_replace_power_window_payload",
                        "risky_keys": [f"0x{key:08X}" for key in risky_keys],
                        "supported_safe_paths": [
                            "existing_color_warper_mesh_block",
                            "node_1_param_only_grade_body",
                            "empty_baseline_grade_body",
                        ],
                    },
                    recoverability="manual",
                )
            template_proto, template_keys = _color_warper_mesh_template(mode)
            template_proto = _replace_mesh_block(template_proto, mode=mode, points=points)
            raw_entries = _extract_raw_param_entries(template_proto, template_keys)
            missing_keys = sorted(template_keys - set(raw_entries))
            if missing_keys:
                raise APICallFailed(
                    f"Verified Color Warper {label} mesh scaffold did not expose all required params.",
                    details={"mode": mode, "missing_keys": [f"0x{key:08X}" for key in missing_keys]},
                    recoverability="manual",
                )
            preserved_entries = {
                key: raw
                for key, raw in existing_entries.items()
                if key not in _COLOR_WARPER_PARAM_KEYS
            }
            if preserved_entries:
                template_proto = _inject_raw_param_entries_into_proto(
                    template_proto,
                    preserved_entries,
                    node_index=1,
                )
            template_match = _find_param_write_container(template_proto, 1)
            if template_match is None or not template_match[5]:
                raise APICallFailed(
                    f"Verified Color Warper {label} mesh scaffold did not expose a grade node.",
                    details={"mode": mode},
                    recoverability="manual",
                )
            root, containers, container_position, container, field9, nodes, _node_order = existing_match
            template_node = template_match[5][0]
            new_field9 = _replace_grade_node(field9, 1, template_node)
            return _replace_param_write_container(
                proto,
                root=root,
                containers=containers,
                container_position=container_position,
                container=container,
                field9=new_field9,
            )
        if b"resolvefx." in proto.lower():
            _raise_warper_scaffold_ofx_loss(label, mode=mode)
        template_proto, template_keys = _color_warper_mesh_template(mode)
        template_proto = _replace_mesh_block(template_proto, mode=mode, points=points)
        raw_entries = _extract_raw_param_entries(template_proto, template_keys)
        missing_keys = sorted(template_keys - set(raw_entries))
        if missing_keys:
            raise APICallFailed(
                f"Verified Color Warper {label} mesh scaffold did not expose all required params.",
                details={"mode": mode, "missing_keys": [f"0x{key:08X}" for key in missing_keys]},
                recoverability="manual",
            )
        preserved_entries = {
            key: raw
            for key, raw in _extract_raw_param_entries(proto).items()
            if key not in _COLOR_WARPER_PARAM_KEYS
        }
        if preserved_entries:
            template_proto = _inject_raw_param_entries_into_proto(
                template_proto,
                preserved_entries,
                node_index=1,
            )
        return template_proto
    normalized = _normalize_mesh_points(points, expected_count=expected_count, label=label)
    start, old_payload = block
    new_payload = _pack_mesh_points(normalized)
    if len(old_payload) != len(new_payload):
        raise APICallFailed(
            "Color Warper mesh replacement length mismatch.",
            details={"mode": mode, "old_length": len(old_payload), "new_length": len(new_payload)},
            recoverability="manual",
        )
    return proto[:start] + new_payload + proto[start + len(old_payload):]


def _decode_color_warper_meshes(proto: bytes) -> dict[str, Any]:
    result: dict[str, Any] = {}
    hue_sat = _find_hue_sat_mesh_block(proto)
    if hue_sat is not None:
        result["hue_saturation_points"] = _unpack_mesh_points(
            hue_sat[1],
            expected_count=_HUE_SAT_POINT_COUNT,
        )
    chroma_luma = _find_chroma_luma_mesh_block(proto)
    if chroma_luma is not None:
        result["chroma_luma_grid1_points"] = _unpack_mesh_points(
            chroma_luma[1],
            expected_count=_CHROMA_LUMA_POINT_COUNT,
        )
    return result


def _color_warper_mesh_key_and_count(mode: str) -> tuple[str, int, str]:
    if mode == "hue_saturation":
        return "hue_saturation_points", _HUE_SAT_POINT_COUNT, "Hue-Saturation"
    if mode == "chroma_luma_grid1":
        return "chroma_luma_grid1_points", _CHROMA_LUMA_POINT_COUNT, "Chroma-Luma Grid 1"
    raise ValidationError(
        "Unsupported Color Warper mesh mode.",
        details={"mode": mode, "allowed": ["hue_saturation", "chroma_luma_grid1"]},
        recoverability="not_applicable",
    )


def default_color_warper_mesh_points(mode: str) -> list[tuple[float, float]]:
    """Return the verified DaVinci Resolve 21 scaffold points for a supported Color Warper mesh."""
    normalized_mode = str(mode).strip().lower().replace("-", "_")
    if normalized_mode in {"hue_sat", "hue_saturation", "huesat"}:
        mesh_mode = "hue_saturation"
    elif normalized_mode in {"chroma_luma", "chromaluma", "chroma_luma_grid1", "chroma_luma_grid_1"}:
        mesh_mode = "chroma_luma_grid1"
    else:
        raise ValidationError(
            "Unsupported Color Warper mesh mode.",
            details={"mode": mode, "allowed": ["hue_saturation", "chroma_luma_grid1"]},
            recoverability="not_applicable",
        )
    readback_key, expected_count, label = _color_warper_mesh_key_and_count(mesh_mode)
    template_proto, _template_keys = _color_warper_mesh_template(mesh_mode)
    decoded = _decode_color_warper_meshes(template_proto).get(readback_key)
    if not isinstance(decoded, list) or len(decoded) != expected_count:
        raise APICallFailed(
            f"Verified Color Warper {label} template did not decode to the expected mesh points.",
            details={"mode": mesh_mode, "expected_count": expected_count},
            recoverability="manual",
        )
    return [(float(point["x"]), float(point["y"])) for point in decoded]


def _mesh_points_from_readback(readback: dict[str, Any] | None, *, mode: str) -> list[tuple[float, float]] | None:
    if not isinstance(readback, dict):
        return None
    readback_key, expected_count, _label = _color_warper_mesh_key_and_count(mode)
    points = readback.get(readback_key)
    if not isinstance(points, list) or len(points) != expected_count:
        return None
    try:
        return [(float(point["x"]), float(point["y"])) for point in points]
    except (KeyError, TypeError, ValueError):
        return None


def apply_color_warper_mesh_edit(
    points: list[tuple[float, float]],
    *,
    mode: str,
    index: int,
    delta_x: float | None = None,
    delta_y: float | None = None,
    target_point: tuple[float, float] | None = None,
    boundary_policy: str = "reject",
) -> list[tuple[float, float]]:
    """Apply a single indexed mesh point edit with an explicit boundary policy."""
    _readback_key, expected_count, label = _color_warper_mesh_key_and_count(mode)
    normalized = _normalize_mesh_points(points, expected_count=expected_count, label=label)
    normalized_policy = str(boundary_policy or "reject").strip().lower()
    if normalized_policy not in {"reject", "clamp"}:
        raise ValidationError(
            "Color Warper mesh boundary policy must be reject or clamp.",
            details={"boundary_policy": boundary_policy, "allowed": ["reject", "clamp"]},
            recoverability="not_applicable",
        )

    def _apply_boundary(name: str, value: float) -> float:
        if normalized_policy == "clamp":
            if not math.isfinite(float(value)):
                raise ValidationError(
                    "Color Warper coordinates must be finite numbers.",
                    details={"name": name, "value": value},
                    recoverability="not_applicable",
                )
            return max(0.0, min(1.0, float(value)))
        return _require_unit_float(name, value)

    point_index = int(index)
    if point_index < 0 or point_index >= expected_count:
        raise ValidationError(
            f"Color Warper {label} mesh index is out of range.",
            details={"mode": mode, "index": index, "minimum": 0, "maximum": expected_count - 1},
            recoverability="not_applicable",
        )
    if target_point is not None and (delta_x is not None or delta_y is not None):
        raise ValidationError(
            "Color Warper mesh edit must use either --mesh-target or delta values, not both.",
            details={"mode": mode, "index": index},
            recoverability="not_applicable",
    )
    current_x, current_y = normalized[point_index]
    if target_point is not None:
        next_x = _apply_boundary(f"{label}[{point_index}].x", target_point[0])
        next_y = _apply_boundary(f"{label}[{point_index}].y", target_point[1])
    else:
        next_x = _apply_boundary(f"{label}[{point_index}].x", current_x + float(delta_x or 0.0))
        next_y = _apply_boundary(f"{label}[{point_index}].y", current_y + float(delta_y or 0.0))
    edited = list(normalized)
    edited[point_index] = (next_x, next_y)
    return edited


def _build_color_warper_varint_param_entry(key: int, value: int) -> bytes:
    return _encode_varint_field(1, int(key)) + _encode_length_delimited(
        2,
        _encode_varint_field(2, int(value)),
    )


def _build_color_warper_chroma_stroke_payload(
    *,
    source_x: float,
    source_y: float,
    target_x: float,
    target_y: float,
    chroma_range: float = 0.04,
    tonal_low: float = 1.0,
    tonal_high: float = 1.0,
    tonal_pivot: float = 0.5,
) -> bytes:
    values = (
        _encode_varint_field(1, 1)
        + _encode_fixed32_field(2, struct.pack("<f", _require_unit_float("source_x", source_x)))
        + _encode_fixed32_field(3, struct.pack("<f", _require_unit_float("source_y", source_y)))
        + _encode_fixed32_field(4, struct.pack("<f", _require_unit_float("target_x", target_x)))
        + _encode_fixed32_field(5, struct.pack("<f", _require_unit_float("target_y", target_y)))
        + _encode_fixed32_field(6, struct.pack("<f", _require_unit_float("chroma_range", chroma_range)))
        + _encode_fixed32_field(8, struct.pack("<f", _require_unit_float("tonal_low", tonal_low)))
        + _encode_fixed32_field(9, struct.pack("<f", _require_unit_float("tonal_high", tonal_high)))
        + _encode_fixed32_field(10, struct.pack("<f", _require_unit_float("tonal_pivot", tonal_pivot)))
    )
    return _encode_length_delimited(27, _encode_length_delimited(1, values))


def _build_color_warper_chroma_stroke_param_entry(
    *,
    source_x: float,
    source_y: float,
    target_x: float,
    target_y: float,
    chroma_range: float = 0.04,
    tonal_low: float = 1.0,
    tonal_high: float = 1.0,
    tonal_pivot: float = 0.5,
) -> bytes:
    return _encode_varint_field(1, PARAM_COLOR_WARPER_CHROMA_STROKE) + _encode_length_delimited(
        2,
        _build_color_warper_chroma_stroke_payload(
            source_x=source_x,
            source_y=source_y,
            target_x=target_x,
            target_y=target_y,
            chroma_range=chroma_range,
            tonal_low=tonal_low,
            tonal_high=tonal_high,
            tonal_pivot=tonal_pivot,
        ),
    )


def _decode_color_warper_chroma_stroke_payload(payload: bytes) -> dict[str, float]:
    wrapper = _get_submessage(payload, 27)
    if wrapper is None:
        wrapper = payload
    stroke = _get_submessage(wrapper, 1) if wrapper is not None else None
    if stroke is None:
        return {}
    result: dict[str, float] = {}
    offset = 0
    field_names = {
        2: "source_x",
        3: "source_y",
        4: "target_x",
        5: "target_y",
        6: "chroma_range",
        8: "tonal_low",
        9: "tonal_high",
        10: "tonal_pivot",
    }
    while offset < len(stroke):
        try:
            tag, offset = _read_varint(stroke, offset)
        except ValueError:
            break
        fn = tag >> 3
        wt = tag & 7
        if wt == 0:
            _value, offset = _read_varint(stroke, offset)
        elif wt == 5:
            if offset + 4 > len(stroke):
                break
            value = struct.unpack("<f", stroke[offset:offset + 4])[0]
            offset += 4
            if fn in field_names:
                result[field_names[fn]] = float(value)
        elif wt == 2:
            try:
                length, offset = _read_varint(stroke, offset)
            except ValueError:
                break
            offset += length
        elif wt == 1:
            offset += 8
        else:
            break
    return result


def _color_warper_payloads_from_params(params: list[GradeParam]) -> dict[str, Any] | None:
    result: dict[str, Any] = {}
    for param in params:
        if param.key == PARAM_COLOR_WARPER_HUE_SAT_WIDTH and isinstance(param.value, int):
            result["hue_saturation_width"] = int(param.value)
        elif param.key == PARAM_COLOR_WARPER_HUE_SAT_HEIGHT and isinstance(param.value, int):
            result["hue_saturation_height"] = int(param.value)
        elif param.key == PARAM_COLOR_WARPER_HUE_SAT_SELECTION and isinstance(param.value, bytes):
            result["hue_saturation_selection_hex"] = param.value.hex()
        elif param.key == PARAM_COLOR_WARPER_CHROMA_LUMA_WIDTH and isinstance(param.value, int):
            result["chroma_luma_width"] = int(param.value)
        elif param.key == PARAM_COLOR_WARPER_CHROMA_LUMA_HEIGHT and isinstance(param.value, int):
            result["chroma_luma_height"] = int(param.value)
        elif param.key == PARAM_COLOR_WARPER_CHROMA_LUMA_SELECTION and isinstance(param.value, bytes):
            result["chroma_luma_selection_hex"] = param.value.hex()
        if param.key == PARAM_COLOR_WARPER_MODE and isinstance(param.value, int):
            result["mode"] = int(param.value)
        elif param.key == PARAM_COLOR_WARPER_SUBMODE and isinstance(param.value, int):
            result["submode"] = int(param.value)
        elif param.key == PARAM_COLOR_WARPER_CHROMA_STROKE and isinstance(param.value, bytes):
            result["chroma_stroke"] = _decode_color_warper_chroma_stroke_payload(param.value)
        elif param.key == PARAM_COLOR_WARPER_PANEL_MODE and isinstance(param.value, int):
            result["panel_mode"] = int(param.value)
    return result or None


def _existing_color_warper_state(proto: bytes) -> dict[str, Any] | None:
    result = _color_warper_payloads_from_params(_parse_params_from_proto(proto)) or {}
    result.update(_decode_color_warper_meshes(proto))
    return result or None


def _inject_color_warper_chroma_stroke_into_proto(
    base_proto: bytes,
    *,
    node_index: int,
    source_x: float,
    source_y: float,
    target_x: float,
    target_y: float,
    chroma_range: float = 0.04,
    tonal_low: float = 1.0,
    tonal_high: float = 1.0,
    tonal_pivot: float = 0.5,
) -> tuple[bytes, dict[str, Any] | None]:
    proto = base_proto
    if _find_param_write_container(proto, int(node_index)) is None:
        if int(node_index) != 1:
            raise ValidationError(
                "Color Warper DB write requires an existing grade graph for node indexes above 1.",
                details={"node_index": node_index},
                recoverability="not_applicable",
            )
        proto = _build_graded_proto_from_baseline(proto, {})
    raw_entries = {
        PARAM_COLOR_WARPER_MODE: _build_color_warper_varint_param_entry(PARAM_COLOR_WARPER_MODE, 2),
        PARAM_COLOR_WARPER_SUBMODE: _build_color_warper_varint_param_entry(PARAM_COLOR_WARPER_SUBMODE, 0),
        PARAM_COLOR_WARPER_CHROMA_STROKE: _build_color_warper_chroma_stroke_param_entry(
            source_x=source_x,
            source_y=source_y,
            target_x=target_x,
            target_y=target_y,
            chroma_range=chroma_range,
            tonal_low=tonal_low,
            tonal_high=tonal_high,
            tonal_pivot=tonal_pivot,
        ),
    }
    proto = _inject_raw_param_entries_into_proto(proto, raw_entries, node_index=int(node_index))
    return proto, _existing_color_warper_state(proto)


def write_color_warper_chroma_stroke(
    conn: Any,
    *,
    clip_name: str | None = None,
    node_index: int = 1,
    source_x: float,
    source_y: float,
    target_x: float,
    target_y: float,
    chroma_range: float = 0.04,
    tonal_low: float = 1.0,
    tonal_high: float = 1.0,
    tonal_pivot: float = 0.5,
) -> dict[str, Any]:
    """Set native Color Warper Chroma Warp stroke through the Disk Project.db route."""
    target_node_index = int(node_index)
    if target_node_index < 1:
        raise ValidationError(
            "Color Page node index must be a positive integer.",
            details={"node_index": node_index, "minimum": 1},
            recoverability="not_applicable",
        )
    expected = {
        "source_x": _require_unit_float("source_x", source_x),
        "source_y": _require_unit_float("source_y", source_y),
        "target_x": _require_unit_float("target_x", target_x),
        "target_y": _require_unit_float("target_y", target_y),
        "chroma_range": _require_unit_float("chroma_range", chroma_range),
        "tonal_low": _require_unit_float("tonal_low", tonal_low),
        "tonal_high": _require_unit_float("tonal_high", tonal_high),
        "tonal_pivot": _require_unit_float("tonal_pivot", tonal_pivot),
    }

    from ..db_timeline_selection import resolve_video_group

    item_ref = resolve_video_group(conn, clip_name=clip_name)["video"]
    timeline = getattr(conn, "timeline", None)
    timeline_name = timeline.GetName() if timeline and hasattr(timeline, "GetName") else None

    def writer(connection: Any, cursor: sqlite3.Cursor, session: DiskDbMutationSession) -> dict[str, Any]:
        row = find_ti_item_row(cursor, item=item_ref, db_type="Sm2TiVideoClip", timeline_name=timeline_name)
        clip_id = row["Sm2TiItem_id"]
        ver_table_id = row["pLmVerTable"]
        ver = _select_active_grade_version(cursor, str(ver_table_id)) if ver_table_id else None
        if ver and ver["Body"]:
            base_proto = decompress_version_body(ver["Body"])
            version_id = ver["ListMgt::LmVersion_id"]
            created_version = False
            created_version_table = False
        else:
            base_body = None
            if ver_table_id:
                base_ver = cursor.execute(
                    '''SELECT v.Body FROM "ListMgt::LmVersion" v
                       JOIN "ListMgt::LmVersion_ListMgt::LmVersionTable" rel
                         ON rel.DbAssociate = v."ListMgt::LmVersion_id"
                       WHERE rel.DbOwner = ?
                       ORDER BY v.rowid LIMIT 1''',
                    (ver_table_id,),
                ).fetchone()
                if base_ver:
                    base_body = base_ver["Body"]
            base_proto = decompress_version_body(base_body or bytes.fromhex(_BASELINE_VERSION_BODY_HEX))
            if not ver_table_id:
                ver_table_id = _create_lm_version_table_for_item(
                    cursor,
                    item_id=str(clip_id),
                    fields_blob=bytes.fromhex(_VERSION_TABLE_FIELDS_BLOB_HEX),
                )
                created_version_table = True
            else:
                created_version_table = False
            version_id = str(uuid.uuid4())
            created_version = True

        new_proto, readback = _inject_color_warper_chroma_stroke_into_proto(
            base_proto,
            node_index=target_node_index,
            **expected,
        )
        new_body = compress_version_body(new_proto)
        if created_version:
            _insert_lm_version_from_body(
                cursor,
                body=new_body,
                version_id=version_id,
                version_table_id=str(ver_table_id),
            )
            session.steps.append("create_color_warper_grade_version")
        else:
            cursor.execute(
                '''UPDATE "ListMgt::LmVersion" SET Body = ?, HasCorrection = 1
                   WHERE "ListMgt::LmVersion_id" = ?''',
                (new_body, version_id),
            )
            session.steps.append("update_color_warper_grade_version")
        if created_version_table:
            session.steps.append("create_grade_version_table")
        return {
            "clip": item_ref.name,
            "clip_id": clip_id,
            "version_id": version_id,
            "node_index": target_node_index,
            "created_version": created_version,
            "created_version_table": created_version_table,
            "color_warper_written": {"mode": "chroma_warp", **expected},
            "readback": {"color_warper": readback},
        }

    def verifier(_fresh_conn: Any, mutation_result: Any, session: DiskDbMutationSession) -> dict[str, Any]:
        if not isinstance(mutation_result, dict):
            raise APICallFailed(
                "Color Warper DB mutation did not return a mutation payload for verification.",
                details={"mutation_result": mutation_result},
            )
        version_id = mutation_result.get("version_id")
        connection = sqlite3.connect(session.project_db_path)
        connection.row_factory = sqlite3.Row
        try:
            row = connection.execute(
                'SELECT Body FROM "ListMgt::LmVersion" WHERE "ListMgt::LmVersion_id" = ?',
                (version_id,),
            ).fetchone()
            if not row or not row["Body"]:
                raise APICallFailed(
                    "Color Warper verification could not read the active grade body.",
                    details={"version_id": version_id},
                    recoverability="manual",
                )
            readback = _existing_color_warper_state(decompress_version_body(row["Body"]))
        finally:
            connection.close()

        stroke = (readback or {}).get("chroma_stroke") if isinstance(readback, dict) else None
        mismatches: list[dict[str, Any]] = []
        for key, expected_value in expected.items():
            actual = (stroke or {}).get(key)
            if actual is None or abs(float(actual) - float(expected_value)) > 0.001:
                mismatches.append({"name": key, "expected": expected_value, "actual": actual})
        if (readback or {}).get("mode") != 2:
            mismatches.append({"name": "mode", "expected": 2, "actual": (readback or {}).get("mode")})
        if (readback or {}).get("submode") != 0:
            mismatches.append({"name": "submode", "expected": 0, "actual": (readback or {}).get("submode")})
        if mismatches:
            raise APICallFailed(
                "Color Warper DB write did not verify after project reload.",
                details={"mismatches": mismatches, "readback": readback},
                recoverability="manual",
            )
        return {
            "status": "db_readback_verified",
            "clip": mutation_result.get("clip"),
            "node_index": target_node_index,
            "color_warper": readback,
            "render_proof_status": "not_performed",
            "render_proof_required": True,
        }

    return execute_sqlite_disk_db_mutation(
        conn,
        context="color page color warper db mutation",
        writer=writer,
        verifier=verifier,
        allow_project_name_inference=True,
    )


def write_color_warper_mesh(
    conn: Any,
    *,
    clip_name: str | None = None,
    node_index: int = 1,
    mode: str,
    points: list[tuple[float, float]] | None = None,
    edit_index: int | None = None,
    delta_x: float | None = None,
    delta_y: float | None = None,
    target_point: tuple[float, float] | None = None,
    boundary_policy: str = "reject",
) -> dict[str, Any]:
    """Set a verified native Color Warper packed mesh through the Disk Project.db route."""
    target_node_index = int(node_index)
    if target_node_index != 1:
        raise ValidationError(
            "Verified Color Warper mesh writes currently support node 1 only.",
            details={"node_index": node_index, "supported_node_index": 1},
            recoverability="not_applicable",
        )
    normalized_mode = str(mode).strip().lower().replace("-", "_")
    if normalized_mode in {"hue_sat", "hue_saturation", "huesat"}:
        mesh_mode = "hue_saturation"
        expected_count = _HUE_SAT_POINT_COUNT
        readback_key = "hue_saturation_points"
    elif normalized_mode in {"chroma_luma", "chromaluma", "chroma_luma_grid1", "chroma_luma_grid_1"}:
        mesh_mode = "chroma_luma_grid1"
        expected_count = _CHROMA_LUMA_POINT_COUNT
        readback_key = "chroma_luma_grid1_points"
    else:
        raise ValidationError(
            "Unsupported Color Warper mesh mode.",
            details={
                "mode": mode,
                "allowed": ["hue_saturation", "chroma_luma_grid1"],
            },
            recoverability="not_applicable",
        )
    explicit_points = None
    if points is not None:
        explicit_points = _normalize_mesh_points(points, expected_count=expected_count, label=mesh_mode)
    if explicit_points is not None and edit_index is not None:
        raise ValidationError(
            "Color Warper mesh write must use either explicit points or a single point edit, not both.",
            details={"mode": mesh_mode, "node_index": node_index},
            recoverability="not_applicable",
        )
    if explicit_points is None and edit_index is None:
        raise ValidationError(
            "Color Warper mesh write requires either explicit points or --mesh-index edit parameters.",
            details={"mode": mesh_mode, "expected_count": expected_count},
            recoverability="not_applicable",
        )

    from ..db_timeline_selection import resolve_video_group

    item_ref = resolve_video_group(conn, clip_name=clip_name)["video"]
    timeline = getattr(conn, "timeline", None)
    timeline_name = timeline.GetName() if timeline and hasattr(timeline, "GetName") else None

    def writer(connection: Any, cursor: sqlite3.Cursor, session: DiskDbMutationSession) -> dict[str, Any]:
        row = find_ti_item_row(cursor, item=item_ref, db_type="Sm2TiVideoClip", timeline_name=timeline_name)
        clip_id = row["Sm2TiItem_id"]
        ver_table_id = row["pLmVerTable"]
        ver = _select_active_grade_version(cursor, str(ver_table_id)) if ver_table_id else None
        if ver and ver["Body"]:
            base_proto = decompress_version_body(ver["Body"])
            version_id = ver["ListMgt::LmVersion_id"]
            created_version = False
            created_version_table = False
        else:
            base_body = None
            if ver_table_id:
                base_ver = cursor.execute(
                    '''SELECT v.Body FROM "ListMgt::LmVersion" v
                       JOIN "ListMgt::LmVersion_ListMgt::LmVersionTable" rel
                         ON rel.DbAssociate = v."ListMgt::LmVersion_id"
                       WHERE rel.DbOwner = ?
                       ORDER BY v.rowid LIMIT 1''',
                    (ver_table_id,),
                ).fetchone()
                if base_ver:
                    base_body = base_ver["Body"]
            base_proto = decompress_version_body(base_body or bytes.fromhex(_BASELINE_VERSION_BODY_HEX))
            if not ver_table_id:
                ver_table_id = _create_lm_version_table_for_item(
                    cursor,
                    item_id=str(clip_id),
                    fields_blob=bytes.fromhex(_VERSION_TABLE_FIELDS_BLOB_HEX),
                )
                created_version_table = True
            else:
                created_version_table = False
            version_id = str(uuid.uuid4())
            created_version = True

        if explicit_points is not None:
            expected_points = explicit_points
            mesh_points_source = "explicit_points"
        else:
            active_points = _mesh_points_from_readback(_existing_color_warper_state(base_proto), mode=mesh_mode)
            if active_points is not None:
                base_points = active_points
                mesh_points_source = "active_grade_mesh"
            else:
                base_points = default_color_warper_mesh_points(mesh_mode)
                mesh_points_source = "verified_template_mesh"
            expected_points = apply_color_warper_mesh_edit(
                base_points,
                mode=mesh_mode,
                index=int(edit_index),
                delta_x=delta_x,
                delta_y=delta_y,
                target_point=target_point,
                boundary_policy=boundary_policy,
            )
        new_proto = _replace_mesh_block(base_proto, mode=mesh_mode, points=expected_points)
        readback = _existing_color_warper_state(new_proto)
        new_body = compress_version_body(new_proto)
        if created_version:
            _insert_lm_version_from_body(
                cursor,
                body=new_body,
                version_id=version_id,
                version_table_id=str(ver_table_id),
            )
            session.steps.append("create_color_warper_mesh_grade_version")
        else:
            cursor.execute(
                '''UPDATE "ListMgt::LmVersion" SET Body = ?, HasCorrection = 1
                   WHERE "ListMgt::LmVersion_id" = ?''',
                (new_body, version_id),
            )
            session.steps.append("update_color_warper_mesh_grade_version")
        if created_version_table:
            session.steps.append("create_grade_version_table")
        return {
            "clip": item_ref.name,
            "clip_id": clip_id,
            "version_id": version_id,
            "node_index": target_node_index,
            "created_version": created_version,
            "created_version_table": created_version_table,
            "color_warper_written": {
                "mode": mesh_mode,
                "mesh_points_source": mesh_points_source,
                "edit": (
                    None
                    if edit_index is None
                    else {
                        "index": int(edit_index),
                        "delta_x": delta_x,
                        "delta_y": delta_y,
                        "target": None if target_point is None else {"x": target_point[0], "y": target_point[1]},
                        "boundary_policy": str(boundary_policy or "reject").strip().lower(),
                    }
                ),
                "points": [{"x": x, "y": y} for x, y in expected_points],
            },
            "readback": {"color_warper": readback},
        }

    def verifier(_fresh_conn: Any, mutation_result: Any, session: DiskDbMutationSession) -> dict[str, Any]:
        if not isinstance(mutation_result, dict):
            raise APICallFailed(
                "Color Warper mesh DB mutation did not return a mutation payload for verification.",
                details={"mutation_result": mutation_result},
            )
        version_id = mutation_result.get("version_id")
        connection = sqlite3.connect(session.project_db_path)
        connection.row_factory = sqlite3.Row
        try:
            row = connection.execute(
                'SELECT Body FROM "ListMgt::LmVersion" WHERE "ListMgt::LmVersion_id" = ?',
                (version_id,),
            ).fetchone()
            if not row or not row["Body"]:
                raise APICallFailed(
                    "Color Warper mesh verification could not read the active grade body.",
                    details={"version_id": version_id},
                    recoverability="manual",
                )
            readback = _existing_color_warper_state(decompress_version_body(row["Body"]))
        finally:
            connection.close()

        written = mutation_result.get("color_warper_written") if isinstance(mutation_result, dict) else {}
        expected_rows = written.get("points") if isinstance(written, dict) else None
        expected_points = [
            (float(row["x"]), float(row["y"]))
            for row in expected_rows
        ] if isinstance(expected_rows, list) else []
        actual_points = (readback or {}).get(readback_key) if isinstance(readback, dict) else None
        mismatches: list[dict[str, Any]] = []
        if not isinstance(actual_points, list) or len(actual_points) != len(expected_points):
            mismatches.append({
                "name": readback_key,
                "expected_count": len(expected_points),
                "actual_count": len(actual_points) if isinstance(actual_points, list) else None,
            })
        else:
            for index, ((expected_x, expected_y), actual) in enumerate(zip(expected_points, actual_points)):
                actual_x = actual.get("x") if isinstance(actual, dict) else None
                actual_y = actual.get("y") if isinstance(actual, dict) else None
                if actual_x is None or actual_y is None or abs(float(actual_x) - expected_x) > 0.001 or abs(float(actual_y) - expected_y) > 0.001:
                    mismatches.append({
                        "name": f"{readback_key}[{index}]",
                        "expected": {"x": expected_x, "y": expected_y},
                        "actual": actual,
                    })
        if (readback or {}).get("mode") != 2:
            mismatches.append({"name": "mode", "expected": 2, "actual": (readback or {}).get("mode")})
        expected_panel_mode = 2 if mesh_mode == "hue_saturation" else 4
        if (readback or {}).get("panel_mode") != expected_panel_mode:
            mismatches.append({"name": "panel_mode", "expected": expected_panel_mode, "actual": (readback or {}).get("panel_mode")})
        if mismatches:
            raise APICallFailed(
                "Color Warper mesh DB write did not verify after project reload.",
                details={"mismatches": mismatches, "readback": readback},
                recoverability="manual",
            )
        return {
            "status": "db_readback_verified",
            "clip": mutation_result.get("clip"),
            "node_index": target_node_index,
            "color_warper": readback,
            "render_proof_status": "not_performed",
            "render_proof_required": True,
        }

    return execute_sqlite_disk_db_mutation(
        conn,
        context="color page color warper mesh db mutation",
        writer=writer,
        verifier=verifier,
        allow_project_name_inference=True,
    )


__all__ = (
    "_build_color_warper_chroma_stroke_payload",
    "_build_color_warper_chroma_stroke_param_entry",
    "_decode_color_warper_chroma_stroke_payload",
    "_decode_color_warper_meshes",
    "_color_warper_payloads_from_params",
    "_inject_color_warper_chroma_stroke_into_proto",
    "_replace_mesh_block",
    "apply_color_warper_mesh_edit",
    "default_color_warper_mesh_points",
    "write_color_warper_chroma_stroke",
    "write_color_warper_mesh",
)
