"""Node Graph helpers for Color Page DB operations."""

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


def _find_param_in_message(data: bytes, target_key: int, *, depth: int = 0) -> GradeParam | None:
    if depth > 8:
        return None
    parsed = _parse_single_param(data)
    if parsed is not None and parsed.key == target_key:
        return parsed
    offset = 0
    while offset < len(data):
        try:
            tag, offset = _read_varint(data, offset)
        except ValueError:
            return None
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
            try:
                length, offset = _read_varint(data, offset)
            except ValueError:
                return None
            child = data[offset:offset + length]
            offset += length
            found = _find_param_in_message(child, target_key, depth=depth + 1)
            if found is not None:
                return found
        else:
            return None
    return None


def _build_rgb_mixer_monochrome_payload() -> bytes:
    # GUI-derived DaVinci Resolve Studio 21 payload for RGB Mixer Monochrome with Preserve Luminance enabled.
    param_entry = _build_varint_param_entry(PARAM_RGB_MIXER_MONOCHROME_MODE, 4)
    param_section = _encode_varint_field(1, 1) + _encode_length_delimited(3, param_entry)
    node_section = _encode_length_delimited(2, param_section)
    return _encode_varint_field(1, 1) + _encode_varint_field(3, 1) + _encode_length_delimited(6, node_section)


def _rgb_mixer_monochrome_mode_from_container(container: bytes) -> int | None:
    field9 = _get_first_length_delimited_field(container, 9)
    if field9 is None:
        return None
    param = _find_param_in_message(field9, PARAM_RGB_MIXER_MONOCHROME_MODE)
    if param is None or param.value_kind != "varint":
        return None
    return int(param.value)


def _replace_rgb_mixer_monochrome_in_field9(field9: bytes, *, enabled: bool) -> tuple[bytes, bool]:
    result = bytearray()
    offset = 0
    found = False
    replacement = _build_rgb_mixer_monochrome_payload()
    while offset < len(field9):
        start = offset
        try:
            tag, offset = _read_varint(field9, offset)
        except ValueError as exc:
            raise APICallFailed(
                "RGB Mixer Monochrome DB route encountered a malformed Color node payload.",
                recoverability="manual",
            ) from exc
        fn = tag >> 3
        wt = tag & 7
        if wt == 0:
            try:
                _, offset = _read_varint(field9, offset)
            except ValueError as exc:
                raise APICallFailed(
                    "RGB Mixer Monochrome DB route encountered a malformed Color node payload.",
                    recoverability="manual",
                ) from exc
            result.extend(field9[start:offset])
        elif wt == 1:
            offset += 8
            result.extend(field9[start:offset])
        elif wt == 5:
            offset += 4
            result.extend(field9[start:offset])
        elif wt == 2:
            try:
                length, offset = _read_varint(field9, offset)
            except ValueError as exc:
                raise APICallFailed(
                    "RGB Mixer Monochrome DB route encountered a malformed Color node payload.",
                    recoverability="manual",
                ) from exc
            payload = field9[offset:offset + length]
            offset += length
            contains_mode = fn == 1 and _find_param_in_message(payload, PARAM_RGB_MIXER_MONOCHROME_MODE) is not None
            if contains_mode:
                found = True
                if enabled:
                    result.extend(_encode_length_delimited(1, replacement))
            else:
                result.extend(field9[start:offset])
        else:
            raise APICallFailed(
                "RGB Mixer Monochrome DB route encountered an unsupported Color node payload field.",
                details={"field_number": fn, "wire_type": wt},
                recoverability="manual",
            )
    if enabled and not found:
        result = bytearray(_encode_length_delimited(1, replacement)) + result
    return bytes(result), found


def _set_rgb_mixer_monochrome_in_proto(
    base_proto: bytes,
    *,
    node_index: int,
    enabled: bool,
) -> tuple[bytes, dict[str, Any]]:
    root = _get_submessage(base_proto, 1)
    if root is None:
        raise APICallFailed(
            "RGB Mixer Monochrome DB route requires an existing grade root.",
            recoverability="manual",
        )
    containers = _root_color_node_containers(base_proto)
    if not containers:
        raise APICallFailed(
            "RGB Mixer Monochrome DB route could not find Color node containers.",
            recoverability="manual",
        )
    root_counter = _get_first_varint_field(root, 1) or (len(containers) + 1)
    target = int(node_index)
    before_mode = None
    found = False
    changed = False
    new_containers = []
    for container in containers:
        current_index = _get_first_varint_field(container, 2)
        if current_index == target:
            found = True
            before_mode = _rgb_mixer_monochrome_mode_from_container(container)
            field9 = _get_first_length_delimited_field(container, 9) or b""
            updated_field9, _had_mode = _replace_rgb_mixer_monochrome_in_field9(field9, enabled=enabled)
            updated = _replace_length_delimited_field(container, 9, updated_field9 if updated_field9 else None)
            changed = updated != container
            container = updated
        new_containers.append(container)
    if not found:
        raise ValidationError(
            "RGB Mixer Monochrome DB route could not find the requested node.",
            details={"node_index": target, "node_count": len(containers)},
            recoverability="not_applicable",
        )
    new_root = _replace_root_color_node_containers(root, new_containers, root_counter=root_counter)
    after_container = next(
        container
        for container in new_containers
        if _get_first_varint_field(container, 2) == target
    )
    after_mode = _rgb_mixer_monochrome_mode_from_container(after_container)
    return _replace_submessage_at_path(base_proto, [1], new_root), {
        "node_index": target,
        "before_mode": before_mode,
        "mode": after_mode,
        "monochrome": after_mode == 4,
        "preserve_luminance": after_mode == 4,
        "changed": changed,
        "node_count": len(containers),
        "param_key": f"0x{PARAM_RGB_MIXER_MONOCHROME_MODE:08X}",
    }


def _build_serial_color_node_container(
    node_index: int,
    *,
    graph_id: int | None = None,
    x_pos: int | None = None,
    y_pos: int | None = None,
    tick: int | None = None,
) -> bytes:
    resolved_graph_id = int(graph_id if graph_id is not None else node_index)
    if x_pos is not None and y_pos is not None:
        resolved_x = int(x_pos)
        resolved_y = int(y_pos)
    else:
        # DaVinci Resolve GUI-authored serial nodes use graph_id == node_index and
        # place serial nodes on a single horizontal row. The older DB route
        # used root_counter-style graph ids and off-row tail positions, which
        # made downstream node-local writes API-visible but render-inactive.
        resolved_x = 190 + max(0, int(node_index) - 1) * 328
        resolved_y = 180
    tick_value = int(tick if tick is not None else time.time() * 1000)
    return (
        _encode_varint_field(1, resolved_graph_id)
        + _encode_varint_field(2, node_index)
        + _encode_varint_field(4, resolved_x)
        + _encode_varint_field(5, resolved_y)
        + _encode_varint_field(7, 1)
        + _encode_varint_field(8, 44)
        + _encode_length_delimited(9, SERIAL_NODE_GRAPH_ORDER)
        + _encode_length_delimited(10, SERIAL_NODE_EMPTY_TOOLS)
        + _encode_varint_field(12, tick_value)
    )


def _build_empty_serial_grade_node() -> bytes:
    param_section = _encode_varint_field(1, 1)
    return (
        _encode_varint_field(1, 1)
        + _encode_varint_field(3, 1)
        + _encode_length_delimited(6, _encode_length_delimited(2, param_section))
    )


def _is_resolve_gui_serial_color_node_container(container: bytes) -> bool:
    node_index = _get_first_varint_field(container, 2)
    graph_id = _get_first_varint_field(container, 1)
    node_type = _get_first_varint_field(container, 8)
    x_pos = _get_first_varint_field(container, 4)
    y_pos = _get_first_varint_field(container, 5)
    if node_index is None:
        return False
    expected_x = 190 + max(0, int(node_index) - 1) * 328
    return (
        int(graph_id or -1) == int(node_index)
        and int(node_type or -1) == 44
        and int(x_pos or -1) == expected_x
        and int(y_pos or -1) == 180
        and _get_submessage(container, 9) == SERIAL_NODE_GRAPH_ORDER
        and _get_submessage(container, 10) == SERIAL_NODE_EMPTY_TOOLS
    )


def _insert_empty_serial_grade_node(
    proto_data: bytes,
    *,
    position: str,
    target_node_index: int | None,
) -> tuple[bytes, int | None]:
    field9 = _extract_submessage(proto_data, [1, 7, 9])
    if field9 is None:
        return proto_data, None
    _fields, nodes, _node_order = _split_grade_node_section(field9)
    new_node = _build_empty_serial_grade_node()
    normalized_position = str(position or "after").strip().lower()
    if normalized_position == "after":
        if not nodes:
            new_field9 = _insert_grade_node_before_order(field9, new_node, SERIAL_NODE_GRAPH_ORDER)
            grade_node_index = 1
        else:
            new_field9 = _insert_grade_node_after_index(field9, new_node, len(nodes))
            grade_node_index = len(nodes) + 1
    else:
        target = int(target_node_index or 1)
        if target < 1 or target > len(nodes):
            raise ValidationError(
                "Color Page grade node-add before target is out of range.",
                details={"target_node_index": target, "grade_node_count": len(nodes)},
                recoverability="not_applicable",
            )
        rebuilt = bytearray()
        seen = 0
        inserted = False
        for fn, wt, raw, _sub in _split_grade_node_section(field9)[0]:
            if fn == 1 and wt == 2:
                seen += 1
                if seen == target:
                    rebuilt.extend(_encode_length_delimited(1, new_node))
                    inserted = True
            rebuilt.extend(raw)
        if not inserted:
            raise APICallFailed(
                "Color Page node-add DB route could not insert the grade payload before the requested node.",
                details={"target_node_index": target, "grade_node_count": seen},
                recoverability="manual",
            )
        new_field9 = bytes(rebuilt)
        grade_node_index = target
    return _replace_submessage_at_path(proto_data, [1, 7, 9], new_field9), grade_node_index


def _remove_empty_serial_grade_nodes(proto_data: bytes) -> tuple[bytes, list[int]]:
    field9 = _extract_submessage(proto_data, [1, 7, 9])
    if field9 is None:
        return proto_data, []
    empty_node = _build_empty_serial_grade_node()
    rebuilt = bytearray()
    seen = 0
    removed: list[int] = []
    for fn, wt, raw, sub in _split_grade_node_section(field9)[0]:
        if fn == 1 and wt == 2:
            seen += 1
            if sub == empty_node:
                removed.append(seen)
                continue
        rebuilt.extend(raw)
    if not removed:
        return proto_data, []
    return _replace_submessage_at_path(proto_data, [1, 7, 9], bytes(rebuilt)), removed


def _build_mixer_color_node_container(mixer_type: int, *, tick: int | None = None) -> bytes:
    tick_value = int(tick if tick is not None else time.time() * 1000)
    return (
        _encode_varint_field(1, 3)
        + _encode_varint_field(2, 3)
        + _encode_varint_field(4, 518)
        + _encode_varint_field(5, 180)
        + _encode_varint_field(7, 1)
        + _encode_varint_field(8, mixer_type)
        + _encode_length_delimited(9, b"")
        + _encode_length_delimited(10, SERIAL_NODE_EMPTY_TOOLS)
        + _encode_varint_field(12, tick_value)
    )


def validate_layer_mixer_composite_mode(mode: str) -> tuple[str, int]:
    normalized = str(mode or "").strip().replace("-", " ").replace("_", " ").lower()
    normalized = " ".join(normalized.split())
    if normalized not in LAYER_MIXER_COMPOSITE_MODES:
        raise ValidationError(
            "Unsupported Layer Mixer composite mode.",
            details={
                "mode": mode,
                "allowed": sorted(label.title() for label in LAYER_MIXER_COMPOSITE_MODES),
            },
            recoverability="not_applicable",
        )
    enum_value = LAYER_MIXER_COMPOSITE_MODES[normalized]
    return LAYER_MIXER_COMPOSITE_MODE_LABELS.get(enum_value, normalized.title()), enum_value


def _replace_or_append_varint_field(data: bytes, field_number: int, value: int) -> tuple[bytes, int | None]:
    result = bytearray()
    offset = 0
    old_value: int | None = None
    replaced = False
    while offset < len(data):
        start = offset
        tag, offset = _read_varint(data, offset)
        fn = tag >> 3
        wt = tag & 7
        if wt == 0:
            current_value, offset = _read_varint(data, offset)
            if fn == field_number and not replaced:
                old_value = current_value
                result.extend(_encode_varint_field(field_number, value))
                replaced = True
            else:
                result.extend(data[start:offset])
        elif wt == 1:
            offset += 8
            result.extend(data[start:offset])
        elif wt == 5:
            offset += 4
            result.extend(data[start:offset])
        elif wt == 2:
            length, offset = _read_varint(data, offset)
            offset += length
            result.extend(data[start:offset])
        else:
            raise APICallFailed(
                "Color Page Layer Mixer DB route encountered an unsupported protobuf field.",
                details={"field_number": fn, "wire_type": wt},
                recoverability="manual",
            )
    if not replaced:
        result.extend(_encode_varint_field(field_number, value))
    return bytes(result), old_value


def _root_graph_edges(root: bytes) -> list[dict[str, int]]:
    edges: list[dict[str, int]] = []
    offset = 0
    while offset < len(root):
        tag, offset = _read_varint(root, offset)
        fn = tag >> 3
        wt = tag & 7
        if wt == 0:
            _value, offset = _read_varint(root, offset)
        elif wt == 1:
            offset += 8
        elif wt == 5:
            offset += 4
        elif wt == 2:
            length, offset = _read_varint(root, offset)
            payload = root[offset : offset + length]
            offset += length
            if fn == 8:
                edge: dict[str, int] = {}
                edge_offset = 0
                while edge_offset < len(payload):
                    edge_tag, edge_offset = _read_varint(payload, edge_offset)
                    edge_fn = edge_tag >> 3
                    edge_wt = edge_tag & 7
                    if edge_wt == 0:
                        edge_value, edge_offset = _read_varint(payload, edge_offset)
                        edge[str(edge_fn)] = edge_value
                    elif edge_wt == 1:
                        edge_offset += 8
                    elif edge_wt == 5:
                        edge_offset += 4
                    elif edge_wt == 2:
                        edge_length, edge_offset = _read_varint(payload, edge_offset)
                        edge_offset += edge_length
                    else:
                        break
                edges.append(edge)
        else:
            raise APICallFailed(
                "Color Page Layer Mixer DB route encountered an unsupported protobuf field.",
                details={"field_number": fn, "wire_type": wt},
                recoverability="manual",
            )
    return edges


def _layer_mixer_container_composite_mode(mixer_container: bytes) -> int:
    tool_section = _get_submessage(mixer_container, 10)
    if not tool_section:
        return LAYER_MIXER_COMPOSITE_MODES["normal"]
    for entry in _get_all_submessages(tool_section, 1):
        param = _parse_single_param(entry)
        if (
            param is not None
            and param.key == PARAM_LAYER_MIXER_COMPOSITE_MODE
            and param.value_kind == "varint"
            and isinstance(param.value, int)
        ):
            return int(param.value)
    return LAYER_MIXER_COMPOSITE_MODES["normal"]


def _read_layer_mixer_composite_mode_from_root(root: bytes, layer_node_graph_id: int) -> int | None:
    mixer_graph_id = None
    for edge in _root_graph_edges(root):
        if edge.get("1") == layer_node_graph_id and edge.get("3") is not None:
            mixer_graph_id = edge.get("3")
            break
    if mixer_graph_id is None:
        return None
    for container in _get_all_submessages(root, 7):
        if (
            _get_first_varint_field(container, 1) == mixer_graph_id
            and _get_first_varint_field(container, 8) == LAYER_MIXER_TYPE
        ):
            return _layer_mixer_container_composite_mode(container)
    return None


def _set_layer_mixer_composite_mode_in_container(
    mixer_container: bytes,
    *,
    mode_value: int,
) -> tuple[bytes, int]:
    old_mode = _layer_mixer_container_composite_mode(mixer_container)
    existing_section = _get_submessage(mixer_container, 10) or b""
    if mode_value == LAYER_MIXER_COMPOSITE_MODES["normal"]:
        new_section = _rebuild_tool_param_section_raw(
            existing_section,
            {},
            delete_keys={PARAM_LAYER_MIXER_COMPOSITE_MODE},
        )
    else:
        new_section = _rebuild_tool_param_section_raw(
            existing_section,
            {
                PARAM_LAYER_MIXER_COMPOSITE_MODE: _build_varint_param_entry(
                    PARAM_LAYER_MIXER_COMPOSITE_MODE,
                    mode_value,
                )
            },
        )
    return _replace_submessage_at_path(mixer_container, [10], new_section), old_mode


def _set_layer_mixer_composite_mode_in_root(
    root: bytes,
    *,
    layer_node_graph_id: int,
    mode_value: int,
) -> tuple[bytes, int | None]:
    mixer_graph_id = None
    for edge in _root_graph_edges(root):
        if edge.get("1") == layer_node_graph_id and edge.get("3") is not None:
            mixer_graph_id = edge.get("3")
            break
    if mixer_graph_id is None:
        raise ValidationError(
            "Color Page Layer Mixer route could not find a layer edge feeding a mixer.",
            details={"layer_node_graph_id": layer_node_graph_id},
            recoverability="not_applicable",
        )
    containers = _get_all_submessages(root, 7)
    new_containers: list[bytes] = []
    replaced = False
    old_mode: int | None = None
    for container in containers:
        if (
            _get_first_varint_field(container, 1) == mixer_graph_id
            and _get_first_varint_field(container, 8) == LAYER_MIXER_TYPE
        ):
            new_container, old_mode = _set_layer_mixer_composite_mode_in_container(
                container,
                mode_value=mode_value,
            )
            new_containers.append(new_container)
            replaced = True
        else:
            new_containers.append(container)
    if not replaced:
        raise ValidationError(
            "Color Page Layer Mixer route could not find the mixer node container.",
            details={"layer_node_graph_id": layer_node_graph_id, "mixer_graph_id": mixer_graph_id},
            recoverability="not_applicable",
        )
    return _replace_root_color_node_containers(
        root,
        new_containers,
        root_counter=_get_first_varint_field(root, 1) or len(new_containers),
    ), old_mode


def _layer_mixer_branch_opacity_from_root(root: bytes, layer_node_graph_id: int) -> float | None:
    for container in _get_all_submessages(root, 7):
        if _get_first_varint_field(container, 1) != int(layer_node_graph_id):
            continue
        field9 = _get_submessage(container, 9)
        if field9 is None:
            return None
        gain = _key_output_gain_from_node_section(field9)
        return None if gain is None else float(gain) * 100.0
    return None


def _set_layer_mixer_branch_opacity_in_root(
    root: bytes,
    *,
    layer_node_graph_id: int,
    opacity_percent: float,
) -> tuple[bytes, dict[str, Any]]:
    if not math.isfinite(opacity_percent) or opacity_percent < 0.0 or opacity_percent > 100.0:
        raise ValidationError(
            "Layer Mixer branch opacity must be between 0 and 100.",
            details={"opacity": opacity_percent, "minimum": 0.0, "maximum": 100.0},
            recoverability="not_applicable",
        )
    target_gain = float(opacity_percent) / 100.0
    containers = _get_all_submessages(root, 7)
    new_containers: list[bytes] = []
    replaced = False
    old_gain: float | None = None
    for container in containers:
        if _get_first_varint_field(container, 1) == int(layer_node_graph_id):
            field9 = _get_submessage(container, 9)
            if field9 is None:
                raise APICallFailed(
                    "Color Page Layer Mixer opacity route could not find the branch node native key section.",
                    details={"layer_node_graph_id": layer_node_graph_id},
                    recoverability="manual",
                )
            new_field9, old_gain = _set_key_output_gain_in_node_section(field9, target_gain)
            new_container = _replace_submessage_at_path(container, [9], new_field9)
            new_container, _old_tick = _replace_or_append_varint_field(
                new_container,
                12,
                int(time.time() * 1000),
            )
            new_containers.append(new_container)
            replaced = True
        else:
            new_containers.append(container)
    if not replaced:
        raise ValidationError(
            "Color Page Layer Mixer opacity route could not find the requested branch node container.",
            details={"layer_node_graph_id": layer_node_graph_id},
            recoverability="not_applicable",
        )
    new_root = _replace_root_color_node_containers(
        root,
        new_containers,
        root_counter=_get_first_varint_field(root, 1) or len(new_containers),
    )
    old_opacity = None if old_gain is None else float(old_gain) * 100.0
    return new_root, {
        "old_opacity": old_opacity,
        "old_opacity_gain": old_gain,
        "new_opacity": float(opacity_percent),
        "new_opacity_gain": target_gain,
        "opacity_changed": old_gain is None or abs(float(old_gain) - target_gain) > 0.000001,
        "opacity_route": "native_branch_node_key_output_payload",
    }


def _set_layer_mixer_composite_mode_in_proto(
    base_proto: bytes,
    *,
    layer_node_index: int,
    mode_value: int,
    branch_opacity: float | None = None,
) -> tuple[bytes, dict[str, Any]]:
    root = _get_submessage(base_proto, 1)
    if root is None:
        raise APICallFailed(
            "Color Page Layer Mixer DB route requires an existing grade root.",
            recoverability="manual",
        )
    containers = _get_all_submessages(root, 7)
    mixer_graph_ids = {
        _get_first_varint_field(container, 1)
        for container in containers
        if _get_first_varint_field(container, 8) == LAYER_MIXER_TYPE
    }
    mixer_graph_ids.discard(None)
    if not mixer_graph_ids:
        raise ValidationError(
            "Color Page Layer Mixer route requires an existing Layer Mixer node.",
            details={"node_count": len(containers)},
            recoverability="not_applicable",
        )
    layer_node_container = None
    primary_node_container = None
    for container in containers:
        if _get_first_varint_field(container, 2) == 1:
            primary_node_container = container
        if _get_first_varint_field(container, 2) == layer_node_index:
            layer_node_container = container
    if primary_node_container is None:
        raise ValidationError(
            "Color Page Layer Mixer route could not find the primary node.",
            details={"layer_node_index": layer_node_index, "node_count": len(containers)},
            recoverability="not_applicable",
        )
    if layer_node_container is None:
        raise ValidationError(
            "Color Page Layer Mixer route could not find the requested layer node.",
            details={"layer_node_index": layer_node_index, "node_count": len(containers)},
            recoverability="not_applicable",
        )
    primary_graph_id = _get_first_varint_field(primary_node_container, 1)
    layer_graph_id = _get_first_varint_field(layer_node_container, 1)
    if primary_graph_id is None or layer_graph_id is None:
        raise APICallFailed(
            "Color Page Layer Mixer route could not read graph ids.",
            details={"layer_node_index": layer_node_index, "primary_graph_id": primary_graph_id},
            recoverability="manual",
        )
    mixer_graph_id = next(iter(mixer_graph_ids), None)
    if mixer_graph_id is None:
        raise APICallFailed(
            "Color Page Layer Mixer route could not read the Layer Mixer graph id.",
            details={"layer_node_index": layer_node_index},
            recoverability="manual",
        )
    old_mode = _read_layer_mixer_composite_mode_from_root(root, layer_graph_id)
    new_root, previous_mode = _set_layer_mixer_composite_mode_in_root(
        root,
        layer_node_graph_id=layer_graph_id,
        mode_value=mode_value,
    )
    new_root, render_fields_changed = _ensure_layer_mixer_render_graph_fields(
        new_root,
        primary_graph_id=int(primary_graph_id),
        branch_graph_id=int(layer_graph_id),
        mixer_graph_id=int(mixer_graph_id),
    )
    opacity_mutation: dict[str, Any] = {}
    if branch_opacity is not None:
        new_root, opacity_mutation = _set_layer_mixer_branch_opacity_in_root(
            new_root,
            layer_node_graph_id=int(layer_graph_id),
            opacity_percent=float(branch_opacity),
        )
    if previous_mode is not None:
        old_mode = previous_mode
    return _replace_submessage_at_path(base_proto, [1], new_root), {
        "layer_node_index": layer_node_index,
        "layer_node_graph_id": layer_graph_id,
        "primary_node_graph_id": primary_graph_id,
        "mixer_node_graph_id": mixer_graph_id,
        "mixer_node_count": len(mixer_graph_ids),
        "old_mode_value": 0 if old_mode is None else old_mode,
        "new_mode_value": mode_value,
        "changed": old_mode != mode_value,
        "render_graph_fields_changed": render_fields_changed,
        **opacity_mutation,
    }


def _replace_root_color_node_containers(
    root: bytes,
    containers: list[bytes],
    *,
    root_counter: int,
) -> bytes:
    result = bytearray()
    offset = 0
    field7_index = 0
    while offset < len(root):
        start = offset
        tag, offset = _read_varint(root, offset)
        fn = tag >> 3
        wt = tag & 7
        if wt == 0:
            _old_value, offset = _read_varint(root, offset)
            if fn == 1:
                result.extend(_encode_varint_field(1, root_counter))
            else:
                result.extend(root[start:offset])
        elif wt == 1:
            offset += 8
            result.extend(root[start:offset])
        elif wt == 5:
            offset += 4
            result.extend(root[start:offset])
        elif wt == 2:
            length, offset = _read_varint(root, offset)
            offset += length
            if fn == 7:
                if field7_index < len(containers):
                    result.extend(_encode_length_delimited(7, containers[field7_index]))
                field7_index += 1
            else:
                result.extend(root[start:offset])
        else:
            raise APICallFailed(
                "Color Page node DB route encountered an unsupported protobuf field.",
                details={"field_number": fn, "wire_type": wt},
                recoverability="manual",
            )
    for container in containers[field7_index:]:
        result.extend(_encode_length_delimited(7, container))
    return bytes(result)


def _build_layer_mixer_root_edge(
    *,
    source_graph_id: int,
    mixer_graph_id: int,
    edge_slot: int,
    secondary_input: bool = False,
) -> bytes:
    payload = _encode_varint_field(1, int(source_graph_id)) + _encode_varint_field(3, int(mixer_graph_id))
    if secondary_input:
        payload += _encode_varint_field(4, 1)
    payload += _encode_varint_field(5, 64)
    payload += _encode_varint_field(6, 64)
    payload += _encode_varint_field(7, int(edge_slot))
    return payload


def _root_has_graph_edge(root: bytes, *, source_graph_id: int, target_graph_id: int) -> bool:
    for edge in _root_graph_edges(root):
        if edge.get("1") == int(source_graph_id) and edge.get("3") == int(target_graph_id):
            return True
    return False


def _ensure_layer_mixer_root_edges(
    root: bytes,
    *,
    primary_graph_id: int,
    branch_graph_id: int,
    mixer_graph_id: int,
) -> tuple[bytes, int]:
    result = bytearray(root)
    added = 0
    if not _root_has_graph_edge(root, source_graph_id=primary_graph_id, target_graph_id=mixer_graph_id):
        result.extend(
            _encode_length_delimited(
                8,
                _build_layer_mixer_root_edge(
                    source_graph_id=primary_graph_id,
                    mixer_graph_id=mixer_graph_id,
                    edge_slot=LAYER_MIXER_PRIMARY_EDGE_SLOT,
                ),
            )
        )
        added += 1
    current = bytes(result)
    if not _root_has_graph_edge(current, source_graph_id=branch_graph_id, target_graph_id=mixer_graph_id):
        result.extend(
            _encode_length_delimited(
                8,
                _build_layer_mixer_root_edge(
                    source_graph_id=branch_graph_id,
                    mixer_graph_id=mixer_graph_id,
                    edge_slot=LAYER_MIXER_BRANCH_EDGE_SLOT,
                    secondary_input=True,
                ),
            )
        )
        added += 1
    return bytes(result), added


def _build_layer_mixer_render_graph_fields(
    *,
    primary_graph_id: int,
    branch_graph_id: int,
    mixer_graph_id: int,
    tick: int | None = None,
) -> bytes:
    resolved_tick = int(tick if tick is not None else time.time() * 1000)
    mixer_map = (
        _encode_varint_field(1, int(mixer_graph_id))
        + _encode_varint_field(2, 80)
        + _encode_length_delimited(
            3,
            _encode_varint_field(1, int(mixer_graph_id))
            + _encode_varint_field(2, 64)
            + _encode_varint_field(3, int(mixer_graph_id))
            + _encode_varint_field(4, int(primary_graph_id)),
        )
        + _encode_length_delimited(
            3,
            _encode_varint_field(1, LAYER_MIXER_RENDER_PRIMARY_PORT)
            + _encode_varint_field(2, 64)
            + _encode_varint_field(3, int(mixer_graph_id))
            + _encode_varint_field(4, int(branch_graph_id)),
        )
    )
    branch_map = (
        _encode_varint_field(1, int(branch_graph_id))
        + _encode_varint_field(2, 64)
        + _encode_length_delimited(
            3,
            _encode_varint_field(1, LAYER_MIXER_RENDER_BRANCH_PORT)
            + _encode_varint_field(2, 64)
            + _encode_varint_field(3, int(branch_graph_id))
            + _encode_varint_field(4, int(mixer_graph_id)),
        )
    )
    return (
        _encode_length_delimited(9, mixer_map)
        + _encode_length_delimited(10, branch_map)
        + _encode_varint_field(12, resolved_tick)
    )


def _expected_layer_mixer_render_graph_payloads(
    *,
    primary_graph_id: int,
    branch_graph_id: int,
    mixer_graph_id: int,
) -> tuple[bytes, bytes]:
    fields = _build_layer_mixer_render_graph_fields(
        primary_graph_id=primary_graph_id,
        branch_graph_id=branch_graph_id,
        mixer_graph_id=mixer_graph_id,
        tick=0,
    )
    field9 = _get_first_length_delimited_field(fields, 9)
    field10 = _get_first_length_delimited_field(fields, 10)
    if field9 is None or field10 is None:
        raise APICallFailed(
            "Color Page Layer Mixer DB route could not build render graph payloads.",
            recoverability="manual",
        )
    return field9, field10


def _read_layer_mixer_render_graph_state(
    root: bytes,
    *,
    primary_graph_id: int,
    branch_graph_id: int,
    mixer_graph_id: int,
) -> dict[str, Any]:
    expected_field9, expected_field10 = _expected_layer_mixer_render_graph_payloads(
        primary_graph_id=primary_graph_id,
        branch_graph_id=branch_graph_id,
        mixer_graph_id=mixer_graph_id,
    )
    actual_field9 = _get_first_length_delimited_field(root, 9)
    actual_field10 = _get_first_length_delimited_field(root, 10)
    return {
        "field9_present": actual_field9 is not None,
        "field10_present": actual_field10 is not None,
        "field9_matches": actual_field9 == expected_field9,
        "field10_matches": actual_field10 == expected_field10,
        "field12_present": _get_first_varint_field(root, 12) is not None,
    }


def _ensure_layer_mixer_render_graph_fields(
    root: bytes,
    *,
    primary_graph_id: int,
    branch_graph_id: int,
    mixer_graph_id: int,
) -> tuple[bytes, bool]:
    state = _read_layer_mixer_render_graph_state(
        root,
        primary_graph_id=primary_graph_id,
        branch_graph_id=branch_graph_id,
        mixer_graph_id=mixer_graph_id,
    )
    if state["field9_matches"] and state["field10_matches"] and state["field12_present"]:
        return root, False
    stripped = _remove_root_fields(root, {9, 10, 12})
    return stripped + _build_layer_mixer_render_graph_fields(
        primary_graph_id=primary_graph_id,
        branch_graph_id=branch_graph_id,
        mixer_graph_id=mixer_graph_id,
    ), True


def _build_serial_root_edge(
    *,
    source_graph_id: int,
    target_graph_id: int,
    edge_slot: int,
) -> bytes:
    return (
        _encode_varint_field(1, int(source_graph_id))
        + _encode_varint_field(3, int(target_graph_id))
        + _encode_varint_field(5, 64)
        + _encode_varint_field(6, 64)
        + _encode_varint_field(7, int(edge_slot))
    )


def _ensure_serial_root_edges(root: bytes, containers: list[bytes]) -> tuple[bytes, int]:
    serial_graph_ids = [
        int(graph_id)
        for container in containers
        if _get_first_varint_field(container, 8) == 44
        for graph_id in [_get_first_varint_field(container, 1)]
        if graph_id is not None
    ]
    if len(serial_graph_ids) < 2:
        return root, 0
    result = bytearray(root)
    added = 0
    current = bytes(result)
    for slot, (source_graph_id, target_graph_id) in enumerate(zip(serial_graph_ids, serial_graph_ids[1:]), 1):
        if _root_has_graph_edge(current, source_graph_id=source_graph_id, target_graph_id=target_graph_id):
            continue
        result.extend(
            _encode_length_delimited(
                8,
                _build_serial_root_edge(
                    source_graph_id=source_graph_id,
                    target_graph_id=target_graph_id,
                    edge_slot=slot,
                ),
            )
        )
        current = bytes(result)
        added += 1
    return bytes(result), added


def _build_serial_render_graph_fields(
    *,
    final_graph_id: int,
    tick: int | None = None,
) -> bytes:
    resolved_tick = int(tick if tick is not None else time.time() * 1000)
    primary_map = (
        _encode_varint_field(1, 1)
        + _encode_varint_field(2, 80)
        + _encode_length_delimited(
            3,
            _encode_varint_field(1, 1)
            + _encode_varint_field(2, 64)
            + _encode_varint_field(3, 1)
            + _encode_varint_field(4, 1),
        )
    )
    final_map = (
        _encode_varint_field(1, 2)
        + _encode_varint_field(2, 64)
        + _encode_length_delimited(
            3,
            _encode_varint_field(1, 4)
            + _encode_varint_field(2, 64)
            + _encode_varint_field(3, 2)
            + _encode_varint_field(4, int(final_graph_id)),
        )
    )
    return (
        _encode_length_delimited(9, primary_map)
        + _encode_length_delimited(10, final_map)
        + _encode_varint_field(12, resolved_tick)
    )


def _ensure_serial_render_graph_fields(root: bytes, containers: list[bytes]) -> tuple[bytes, dict[str, Any]]:
    if len(containers) < 2:
        return root, {"serial_graph_edges_added": 0, "serial_render_graph_fields_changed": False}
    if any(_get_first_varint_field(container, 8) != 44 for container in containers):
        return root, {
            "serial_graph_edges_added": 0,
            "serial_render_graph_fields_changed": False,
            "serial_render_graph_skipped": "non_serial_topology",
        }
    graph_ids = [
        _get_first_varint_field(container, 1)
        for container in containers
    ]
    if any(graph_id is None for graph_id in graph_ids):
        raise APICallFailed(
            "Color Page serial node-add route could not read serial graph ids.",
            recoverability="manual",
        )
    root_with_edges, edges_added = _ensure_serial_root_edges(root, containers)
    final_graph_id = int(graph_ids[-1])
    expected = _build_serial_render_graph_fields(final_graph_id=final_graph_id, tick=0)
    expected_field9 = _get_first_length_delimited_field(expected, 9)
    expected_field10 = _get_first_length_delimited_field(expected, 10)
    actual_field9 = _get_first_length_delimited_field(root_with_edges, 9)
    actual_field10 = _get_first_length_delimited_field(root_with_edges, 10)
    has_tick = _get_first_varint_field(root_with_edges, 12) is not None
    if actual_field9 == expected_field9 and actual_field10 == expected_field10 and has_tick:
        return root_with_edges, {
            "serial_graph_edges_added": edges_added,
            "serial_render_graph_fields_changed": False,
            "serial_final_graph_id": final_graph_id,
        }
    stripped = _remove_root_fields(root_with_edges, {9, 10, 12})
    return stripped + _build_serial_render_graph_fields(final_graph_id=final_graph_id), {
        "serial_graph_edges_added": edges_added,
        "serial_render_graph_fields_changed": True,
        "serial_final_graph_id": final_graph_id,
    }


def _container_by_node_index(containers: list[bytes], node_index: int) -> bytes | None:
    for container in containers:
        if _get_first_varint_field(container, 2) == int(node_index):
            return container
    return None


def _read_bleach_bypass_state_from_proto(base_proto: bytes) -> dict[str, Any]:
    root = _get_submessage(base_proto, 1)
    containers = _root_color_node_containers(base_proto)
    state: dict[str, Any] = {
        "node_count": len(containers),
        "branch_node_index": LAYER_MIXER_BRANCH_NODE_INDEX,
        "mixer_node_index": LAYER_MIXER_NODE_INDEX,
        "topology": "unknown",
    }
    if root is None:
        return state
    primary = _container_by_node_index(containers, 1)
    branch = _container_by_node_index(containers, LAYER_MIXER_BRANCH_NODE_INDEX)
    mixer = _container_by_node_index(containers, LAYER_MIXER_NODE_INDEX)
    if len(containers) == 1:
        state["topology"] = "single_node"
        return state
    if primary is None or branch is None or mixer is None:
        return state
    mixer_type = _get_first_varint_field(mixer, 8)
    primary_graph_id = _get_first_varint_field(primary, 1)
    branch_graph_id = _get_first_varint_field(branch, 1)
    mixer_graph_id = _get_first_varint_field(mixer, 1)
    state.update(
        {
            "topology": "layer_mixer" if mixer_type == LAYER_MIXER_TYPE else "unsupported_mixer",
            "mixer_type": mixer_type,
            "primary_graph_id": primary_graph_id,
            "branch_node_graph_id": branch_graph_id,
            "mixer_node_graph_id": mixer_graph_id,
            "rgb_mixer_mode_value": _rgb_mixer_monochrome_mode_from_container(branch),
        }
    )
    if branch_graph_id is not None:
        mode_value = _read_layer_mixer_composite_mode_from_root(root, branch_graph_id)
        state["layer_mixer_mode_value"] = mode_value
        if mode_value is not None:
            state["layer_mixer_mode"] = LAYER_MIXER_COMPOSITE_MODE_LABELS.get(mode_value, str(mode_value))
    if primary_graph_id is not None and branch_graph_id is not None and mixer_graph_id is not None:
        render_graph = _read_layer_mixer_render_graph_state(
            root,
            primary_graph_id=primary_graph_id,
            branch_graph_id=branch_graph_id,
            mixer_graph_id=mixer_graph_id,
        )
        state["render_graph"] = render_graph
        state["render_graph_verified"] = (
            render_graph["field9_matches"]
            and render_graph["field10_matches"]
            and render_graph["field12_present"]
        )
    state["monochrome"] = state.get("rgb_mixer_mode_value") == 4
    state["preserve_luminance"] = state.get("rgb_mixer_mode_value") == 4
    return state


def _ensure_verified_bleach_bypass_topology(base_proto: bytes) -> tuple[bytes, dict[str, Any]]:
    state = _read_bleach_bypass_state_from_proto(base_proto)
    if state["topology"] == "single_node":
        new_proto, node_result = _inject_layer_color_node_into_proto(base_proto)
        return new_proto, {
            "created_layer_topology": True,
            "reused_layer_topology": False,
            "topology_before": state,
            "node_add": node_result,
        }
    if (
        state["topology"] == "layer_mixer"
        and state["node_count"] == 3
        and state.get("primary_graph_id") is not None
        and state.get("branch_node_graph_id") is not None
        and state.get("mixer_node_graph_id") is not None
    ):
        root = _get_submessage(base_proto, 1)
        assert root is not None
        new_root, edges_added = _ensure_layer_mixer_root_edges(
            root,
            primary_graph_id=int(state["primary_graph_id"]),
            branch_graph_id=int(state["branch_node_graph_id"]),
            mixer_graph_id=int(state["mixer_node_graph_id"]),
        )
        new_root, render_fields_changed = _ensure_layer_mixer_render_graph_fields(
            new_root,
            primary_graph_id=int(state["primary_graph_id"]),
            branch_graph_id=int(state["branch_node_graph_id"]),
            mixer_graph_id=int(state["mixer_node_graph_id"]),
        )
        return _replace_submessage_at_path(base_proto, [1], new_root), {
            "created_layer_topology": False,
            "reused_layer_topology": True,
            "topology_before": state,
            "graph_edges_added": edges_added,
            "render_graph_fields_changed": render_fields_changed,
        }
    raise ValidationError(
        "Bleach bypass DB route currently supports only a single-node grade or the verified three-node Layer Mixer topology.",
        details={
            "node_count": state.get("node_count"),
            "topology": state.get("topology"),
            "mixer_type": state.get("mixer_type"),
        },
        recoverability="not_applicable",
    )


def _set_bleach_bypass_in_proto(base_proto: bytes) -> tuple[bytes, dict[str, Any]]:
    working_proto, topology_result = _ensure_verified_bleach_bypass_topology(base_proto)
    working_proto, rgb_result = _set_rgb_mixer_monochrome_in_proto(
        working_proto,
        node_index=LAYER_MIXER_BRANCH_NODE_INDEX,
        enabled=True,
    )
    working_proto, layer_result = _set_layer_mixer_composite_mode_in_proto(
        working_proto,
        layer_node_index=LAYER_MIXER_BRANCH_NODE_INDEX,
        mode_value=LAYER_MIXER_COMPOSITE_MODES["overlay"],
    )
    state = _read_bleach_bypass_state_from_proto(working_proto)
    return working_proto, {
        **topology_result,
        "rgb_mixer": rgb_result,
        "layer_mixer": layer_result,
        "topology_after": state,
        "branch_node_index": LAYER_MIXER_BRANCH_NODE_INDEX,
        "mixer_node_index": LAYER_MIXER_NODE_INDEX,
        "mode": "Overlay",
        "mode_value": LAYER_MIXER_COMPOSITE_MODES["overlay"],
    }


def _inject_serial_color_node_into_proto(
    base_proto: bytes,
    *,
    position: str = "after",
    target_node_index: int | None = None,
) -> tuple[bytes, dict[str, Any]]:
    root = _get_submessage(base_proto, 1)
    if root is None:
        raise APICallFailed(
            "Color Page node-add DB route requires an existing grade root.",
            recoverability="manual",
        )
    existing_nodes = _get_all_submessages(root, 7)
    if not existing_nodes:
        raise APICallFailed(
            "Color Page node-add DB route could not find the primary Color node container.",
            recoverability="manual",
        )
    before_count = len(existing_nodes)
    existing_node_hashes = [hashlib.sha256(container).hexdigest() for container in existing_nodes]
    mixer_node_indices = [
        int(node_index)
        for container in existing_nodes
        if _get_first_varint_field(container, 8) in {68, 90}
        for node_index in [_get_first_varint_field(container, 2)]
        if node_index is not None
    ]
    normalized_position = str(position or "after").strip().lower()
    if normalized_position == "after":
        new_node_index = before_count + 1
        root_counter = new_node_index + 1
        new_root = _set_first_varint_field(root, 1, root_counter)
        new_root += _encode_length_delimited(
            7,
            _build_serial_color_node_container(new_node_index),
        )
    elif normalized_position == "before":
        target = int(target_node_index or 1)
        if target < 1 or target > before_count:
            raise ValidationError(
                "Color Page node-add before target is out of range.",
                details={"target_node_index": target, "node_count": before_count},
                recoverability="not_applicable",
            )
        non_serial_nodes = [
            {
                "node_index": _get_first_varint_field(container, 2),
                "node_type": _get_first_varint_field(container, 8),
            }
            for container in existing_nodes
            if _get_first_varint_field(container, 8) != 44
        ]
        if non_serial_nodes:
            raise ValidationError(
                "Adding a serial Color Page node before an arbitrary target is verified only for serial-only graphs.",
                details={"target_node_index": target, "non_serial_nodes": non_serial_nodes},
                recoverability="not_applicable",
            )
        root_counter = before_count + 2
        shifted_nodes = []
        for container in existing_nodes:
            current_index = _get_first_varint_field(container, 2)
            if current_index is not None and current_index >= target:
                shifted_nodes.append(_set_first_varint_field(container, 2, current_index + 1))
            else:
                shifted_nodes.append(container)
        shifted_nodes.append(
            _build_serial_color_node_container(
                target,
            )
        )
        new_node_index = target
        new_root = _replace_root_color_node_containers(root, shifted_nodes, root_counter=root_counter)
    else:
        raise ValidationError(
            "Invalid Color Page node-add position.",
            details={"position": position, "allowed": ["after", "before"]},
            recoverability="not_applicable",
        )
    final_containers = _get_all_submessages(new_root, 7)
    new_root, serial_render_graph = _ensure_serial_render_graph_fields(new_root, final_containers)
    return _replace_submessage_at_path(base_proto, [1], new_root), {
        "kind": "serial",
        "position": normalized_position,
        "before_node_count": before_count,
        "after_node_count": before_count + 1,
        "node_index": new_node_index,
        "grade_node_index": None,
        "root_counter": root_counter,
        "preserved_existing_node_count": before_count if normalized_position == "after" else None,
        "preserved_existing_node_hashes": existing_node_hashes if normalized_position == "after" else None,
        "grade_payload_augmented": False,
        "preserved_mixer_node_indices": mixer_node_indices if normalized_position == "after" and mixer_node_indices else [],
        **serial_render_graph,
    }


def _inject_parallel_color_node_into_proto(base_proto: bytes) -> tuple[bytes, dict[str, Any]]:
    root = _get_submessage(base_proto, 1)
    if root is None:
        raise APICallFailed(
            "Color Page parallel node-add DB route requires an existing grade root.",
            recoverability="manual",
        )
    existing_nodes = _get_all_submessages(root, 7)
    if len(existing_nodes) != 1:
        raise ValidationError(
            "Adding a parallel Color Page node is currently verified only from a single-node graph.",
            details={"node_count": len(existing_nodes), "required_node_count": 1},
            recoverability="not_applicable",
        )
    containers = [
        existing_nodes[0],
        _build_mixer_color_node_container(68),
        _build_serial_color_node_container(
            2,
            graph_id=4,
            x_pos=190,
            y_pos=416,
        ),
    ]
    root_counter = 4
    new_root = _replace_root_color_node_containers(root, containers, root_counter=root_counter)
    return _replace_submessage_at_path(base_proto, [1], new_root), {
        "kind": "parallel",
        "before_node_count": len(existing_nodes),
        "after_node_count": len(containers),
        "node_index": 2,
        "mixer_node_index": 3,
        "root_counter": root_counter,
    }


def _inject_layer_color_node_into_proto(base_proto: bytes) -> tuple[bytes, dict[str, Any]]:
    root = _get_submessage(base_proto, 1)
    if root is None:
        raise APICallFailed(
            "Color Page layer node-add DB route requires an existing grade root.",
            recoverability="manual",
        )
    existing_nodes = _get_all_submessages(root, 7)
    if len(existing_nodes) != 1:
        raise ValidationError(
            "Adding a layer Color Page node is currently verified only from a single-node graph.",
            details={"node_count": len(existing_nodes), "required_node_count": 1},
            recoverability="not_applicable",
        )
    containers = [
        existing_nodes[0],
        _build_mixer_color_node_container(90),
        _build_serial_color_node_container(
            2,
            graph_id=4,
            x_pos=190,
            y_pos=416,
        ),
    ]
    root_counter = 4
    new_root = _replace_root_color_node_containers(root, containers, root_counter=root_counter)
    primary_graph_id = _get_first_varint_field(existing_nodes[0], 1)
    if primary_graph_id is None:
        raise APICallFailed(
            "Color Page layer node-add DB route could not read the primary graph id.",
            recoverability="manual",
        )
    new_root, added_edges = _ensure_layer_mixer_root_edges(
        new_root,
        primary_graph_id=primary_graph_id,
        branch_graph_id=4,
        mixer_graph_id=3,
    )
    new_root, render_fields_changed = _ensure_layer_mixer_render_graph_fields(
        new_root,
        primary_graph_id=primary_graph_id,
        branch_graph_id=4,
        mixer_graph_id=3,
    )
    return _replace_submessage_at_path(base_proto, [1], new_root), {
        "kind": "layer",
        "before_node_count": len(existing_nodes),
        "after_node_count": len(containers),
        "node_index": 2,
        "mixer_node_index": 3,
        "root_counter": root_counter,
        "graph_edges_added": added_edges,
        "render_graph_fields_changed": render_fields_changed,
    }


def _is_empty_serial_color_node_container(container: bytes) -> bool:
    return (
        _get_submessage(container, 9) == SERIAL_NODE_GRAPH_ORDER
        and _get_submessage(container, 10) == SERIAL_NODE_EMPTY_TOOLS
    )


def _remove_empty_serial_color_nodes_from_proto(base_proto: bytes) -> tuple[bytes, dict[str, Any]]:
    root = _get_submessage(base_proto, 1)
    if root is None:
        raise APICallFailed(
            "Color Page node-cleanup DB route requires an existing grade root.",
            recoverability="manual",
        )
    containers = _get_all_submessages(root, 7)
    if not containers:
        raise APICallFailed(
            "Color Page node-cleanup DB route could not find the primary Color node container.",
            recoverability="manual",
        )
    container_info = [
        {
            "position": position,
            "node_index": _get_first_varint_field(container, 2),
            "graph_id": _get_first_varint_field(container, 1),
            "node_type": _get_first_varint_field(container, 8),
            "container": container,
        }
        for position, container in enumerate(containers, 1)
    ]
    mixer_node_indices = [
        int(info["node_index"])
        for info in container_info
        if info["node_type"] in {68, 90} and info["node_index"] is not None
    ]
    if mixer_node_indices:
        max_mixer_node_index = max(mixer_node_indices)
        removable_positions = {
            int(info["position"])
            for info in container_info
            if info["node_index"] is not None
            and int(info["node_index"]) > max_mixer_node_index
            and _is_empty_serial_color_node_container(info["container"])
        }
        if not removable_positions:
            return base_proto, {
                "before_node_count": len(containers),
                "after_node_count": len(containers),
                "removed_node_count": 0,
                "removed_node_indices": [],
                "skipped_reason": "mixer_topology_no_empty_serial_tail",
                "mixer_node_indices": mixer_node_indices,
            }
        kept_containers = [
            info["container"]
            for info in container_info
            if int(info["position"]) not in removable_positions
        ]
        graph_ids = [
            int(_get_first_varint_field(container, 1))
            for container in kept_containers
            if _get_first_varint_field(container, 1) is not None
        ]
        root_counter = max(graph_ids) if graph_ids else len(kept_containers) + 1
        new_root = _replace_root_color_node_containers(root, kept_containers, root_counter=root_counter)
        removed_node_indices = [
            int(info["node_index"])
            for info in container_info
            if int(info["position"]) in removable_positions and info["node_index"] is not None
        ]
        proto_without_containers = _replace_submessage_at_path(base_proto, [1], new_root)
        cleaned_proto, removed_grade_node_indices = _remove_empty_serial_grade_nodes(proto_without_containers)
        result = {
            "before_node_count": len(containers),
            "after_node_count": len(kept_containers),
            "removed_node_count": len(removable_positions),
            "removed_node_indices": sorted(removed_node_indices),
            "preserved_mixer_node_indices": mixer_node_indices,
        }
        if removed_grade_node_indices:
            result["removed_grade_node_indices"] = removed_grade_node_indices
        return cleaned_proto, result
    removable = {
        index
        for index, container in enumerate(containers, 1)
        if index > 1 and _is_empty_serial_color_node_container(container)
    }
    if not removable:
        return base_proto, {
            "before_node_count": len(containers),
            "after_node_count": len(containers),
            "removed_node_count": 0,
            "removed_node_indices": [],
        }

    remaining_count = len(containers) - len(removable)
    root_counter = remaining_count + 1
    kept_containers = [
        _set_first_varint_field(container, 2, index)
        for index, container in enumerate(
            [container for index, container in enumerate(containers, 1) if index not in removable],
            1,
        )
    ]

    new_root = _replace_root_color_node_containers(root, kept_containers, root_counter=root_counter)
    proto_without_containers = _replace_submessage_at_path(base_proto, [1], new_root)
    cleaned_proto, removed_grade_node_indices = _remove_empty_serial_grade_nodes(proto_without_containers)
    result = {
        "before_node_count": len(containers),
        "after_node_count": remaining_count,
        "removed_node_count": len(removable),
        "removed_node_indices": sorted(removable),
    }
    if removed_grade_node_indices:
        result["removed_grade_node_indices"] = removed_grade_node_indices
    return cleaned_proto, result


_SINGLE_NODE_VIDEO_INPUT_PAYLOAD = bytes.fromhex("080110501a080801104018012001")
_SINGLE_NODE_VIDEO_OUTPUT_PAYLOAD = bytes.fromhex("080210401a080802104018022001")
_SINGLE_NODE_ALPHA_OUTPUT_PAYLOAD = bytes.fromhex("080310101a0a08031010180320012801")


def _root_raw_fields(data: bytes) -> list[tuple[int, int, bytes]]:
    """Return complete encoded root fields without interpreting unknown payloads."""
    fields: list[tuple[int, int, bytes]] = []
    offset = 0
    while offset < len(data):
        start = offset
        try:
            tag, offset = _read_varint(data, offset)
        except ValueError as exc:
            raise APICallFailed(
                "Color Page Alpha Output DB route encountered a malformed grade root.",
                recoverability="manual",
            ) from exc
        field_number = tag >> 3
        wire_type = tag & 7
        if field_number <= 0:
            raise APICallFailed(
                "Color Page Alpha Output DB route encountered an invalid grade root field.",
                details={"field_number": field_number, "wire_type": wire_type},
                recoverability="manual",
            )
        if wire_type == 0:
            try:
                _value, offset = _read_varint(data, offset)
            except ValueError as exc:
                raise APICallFailed(
                    "Color Page Alpha Output DB route encountered a malformed grade root varint.",
                    details={"field_number": field_number},
                    recoverability="manual",
                ) from exc
        elif wire_type == 1:
            offset += 8
        elif wire_type == 5:
            offset += 4
        elif wire_type == 2:
            try:
                length, offset = _read_varint(data, offset)
            except ValueError as exc:
                raise APICallFailed(
                    "Color Page Alpha Output DB route encountered a malformed grade root length.",
                    details={"field_number": field_number},
                    recoverability="manual",
                ) from exc
            offset += int(length)
        else:
            raise APICallFailed(
                "Color Page Alpha Output DB route encountered an unsupported grade root field.",
                details={"field_number": field_number, "wire_type": wire_type},
                recoverability="manual",
            )
        if offset > len(data):
            raise APICallFailed(
                "Color Page Alpha Output DB route encountered a truncated grade root field.",
                details={"field_number": field_number, "wire_type": wire_type},
                recoverability="manual",
            )
        fields.append((field_number, wire_type, data[start:offset]))
    return fields


def _single_node_alpha_output_state(base_proto: bytes, *, node_index: int = 1) -> dict[str, Any]:
    """Read the exact GUI-authored one-node RGB/alpha output topology."""
    root = _get_submessage(base_proto, 1)
    if root is None:
        raise APICallFailed(
            "Color Page Alpha Output DB route requires an existing grade root.",
            recoverability="manual",
        )
    containers = _root_color_node_containers(base_proto)
    requested_node_index = int(node_index)
    if len(containers) != 1 or _get_first_varint_field(containers[0], 2) != requested_node_index:
        raise ValidationError(
            "Color Page Alpha Output DB route is verified only for an exact single-node Color graph.",
            details={
                "requested_node_index": requested_node_index,
                "node_count": len(containers),
                "node_indices": [_get_first_varint_field(container, 2) for container in containers],
            },
            recoverability="not_applicable",
        )
    video_inputs = _get_all_submessages(root, 9)
    render_outputs = _get_all_submessages(root, 10)
    alpha_enabled = _get_first_varint_field(root, 11)
    if video_inputs != [_SINGLE_NODE_VIDEO_INPUT_PAYLOAD]:
        raise APICallFailed(
            "Color Page Alpha Output DB route found an unsupported graph input topology.",
            details={"input_count": len(video_inputs)},
            recoverability="manual",
        )
    connected = (
        render_outputs == [_SINGLE_NODE_VIDEO_OUTPUT_PAYLOAD, _SINGLE_NODE_ALPHA_OUTPUT_PAYLOAD]
        and alpha_enabled == 1
    )
    clean_rgb_only = render_outputs == [_SINGLE_NODE_VIDEO_OUTPUT_PAYLOAD] and alpha_enabled is None
    if not connected and not clean_rgb_only:
        raise APICallFailed(
            "Color Page Alpha Output DB route found an unsupported or ambiguous output topology.",
            details={
                "output_count": len(render_outputs),
                "alpha_enabled": alpha_enabled,
                "known_alpha_output_present": _SINGLE_NODE_ALPHA_OUTPUT_PAYLOAD in render_outputs,
            },
            recoverability="manual",
        )
    return {
        "node_index": requested_node_index,
        "node_count": 1,
        "video_output_count": 1,
        "alpha_output_count": 1 if connected else 0,
        "alpha_output_connected": connected,
        "alpha_output_enabled": alpha_enabled == 1,
        "topology": "single_node_rgb_alpha" if connected else "single_node_rgb_only",
    }


def _ensure_single_node_alpha_output_in_proto(
    base_proto: bytes,
    *,
    node_index: int = 1,
) -> tuple[bytes, dict[str, Any]]:
    """Add the GUI-authored Alpha Output edge without changing node-local mask data."""
    before = _single_node_alpha_output_state(base_proto, node_index=node_index)
    if before["alpha_output_connected"]:
        return base_proto, {**before, "changed": False, "before_topology": before["topology"]}

    root = _get_submessage(base_proto, 1)
    assert root is not None
    encoded_alpha_output = _encode_length_delimited(10, _SINGLE_NODE_ALPHA_OUTPUT_PAYLOAD)
    encoded_alpha_enabled = _encode_varint_field(11, 1)
    result = bytearray()
    inserted = False
    for field_number, _wire_type, raw in _root_raw_fields(root):
        if not inserted and field_number == 12:
            result.extend(encoded_alpha_output)
            result.extend(encoded_alpha_enabled)
            inserted = True
        result.extend(raw)
    if not inserted:
        result.extend(encoded_alpha_output)
        result.extend(encoded_alpha_enabled)
    updated_proto = _replace_submessage_at_path(base_proto, [1], bytes(result))
    after = _single_node_alpha_output_state(updated_proto, node_index=node_index)
    if not after["alpha_output_connected"]:
        raise APICallFailed(
            "Color Page Alpha Output DB route could not construct the verified native topology.",
            recoverability="manual",
        )
    return updated_proto, {
        **after,
        "changed": updated_proto != base_proto,
        "before_topology": before["topology"],
    }


__all__ = (
    '_find_param_in_message',
    '_build_rgb_mixer_monochrome_payload',
    '_rgb_mixer_monochrome_mode_from_container',
    '_replace_rgb_mixer_monochrome_in_field9',
    '_set_rgb_mixer_monochrome_in_proto',
    '_build_serial_color_node_container',
    '_build_empty_serial_grade_node',
    '_build_mixer_color_node_container',
    'validate_layer_mixer_composite_mode',
    '_replace_or_append_varint_field',
    '_root_graph_edges',
    '_layer_mixer_container_composite_mode',
    '_read_layer_mixer_composite_mode_from_root',
    '_set_layer_mixer_composite_mode_in_container',
    '_set_layer_mixer_composite_mode_in_root',
    '_layer_mixer_branch_opacity_from_root',
    '_set_layer_mixer_branch_opacity_in_root',
    '_set_layer_mixer_composite_mode_in_proto',
    '_replace_root_color_node_containers',
    '_build_layer_mixer_root_edge',
    '_root_has_graph_edge',
    '_ensure_layer_mixer_root_edges',
    '_build_layer_mixer_render_graph_fields',
    '_expected_layer_mixer_render_graph_payloads',
    '_read_layer_mixer_render_graph_state',
    '_ensure_layer_mixer_render_graph_fields',
    '_build_serial_root_edge',
    '_ensure_serial_root_edges',
    '_build_serial_render_graph_fields',
    '_ensure_serial_render_graph_fields',
    '_container_by_node_index',
    '_read_bleach_bypass_state_from_proto',
    '_ensure_verified_bleach_bypass_topology',
    '_set_bleach_bypass_in_proto',
    '_inject_serial_color_node_into_proto',
    '_inject_parallel_color_node_into_proto',
    '_inject_layer_color_node_into_proto',
    '_is_empty_serial_color_node_container',
    '_is_resolve_gui_serial_color_node_container',
    '_remove_empty_serial_color_nodes_from_proto',
    '_single_node_alpha_output_state',
    '_ensure_single_node_alpha_output_in_proto',
)
