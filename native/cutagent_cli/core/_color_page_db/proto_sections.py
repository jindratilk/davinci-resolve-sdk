"""Proto Sections helpers for Color Page DB operations."""

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


def _build_param_entry(key: int, value: float) -> bytes:
    """Build a single param protobuf entry: {1: key, 2: {1: float32_be}}."""
    float_bytes = struct.pack('<f', value)  # protobuf fixed32 = LE
    inner = _encode_fixed32_field(1, float_bytes)
    return (
        _encode_varint_field(1, key) +
        _encode_length_delimited(2, inner)
    )


def _build_varint_param_entry(key: int, value: int) -> bytes:
    inner = _encode_varint_field(2, value)
    return (
        _encode_varint_field(1, key) +
        _encode_length_delimited(2, inner)
    )


def _build_bytes_param_entry(key: int, value: bytes, *, inner_field: int = 8) -> bytes:
    inner = _encode_length_delimited(inner_field, value)
    return (
        _encode_varint_field(1, key) +
        _encode_length_delimited(2, inner)
    )


def _build_direct_bytes_param_entry(key: int, value: bytes) -> bytes:
    return (
        _encode_varint_field(1, key) +
        _encode_length_delimited(2, value)
    )


def _rebuild_param_section(
    existing_section: bytes,
    params: dict[int, float],
    *,
    delete_keys: set[int] | None = None,
) -> bytes:
    """Replace/add params in a param section (the field-2 submessage).

    Preserves all existing field 3 entries that are NOT being overridden,
    replaces matching keys, and appends new ones.
    """
    # Parse existing entries
    existing_entries: list[tuple[int | None, bytes]] = []
    offset = 0
    non_param_fields = b""

    while offset < len(existing_section):
        start = offset
        try:
            tag, offset = _read_varint(existing_section, offset)
        except ValueError:
            break
        fn = tag >> 3
        wt = tag & 7

        if wt == 2:
            length, offset = _read_varint(existing_section, offset)
            entry_data = existing_section[offset:offset + length]
            offset += length

            if fn == 3:
                # Parse param key from entry
                param = _parse_single_param(entry_data)
                key = param.key if param else None
                existing_entries.append((key, existing_section[start:offset]))
            else:
                # Preserve non-param fields (e.g. field 1 = version marker)
                non_param_fields += existing_section[start:offset]
        elif wt == 0:
            _, offset = _read_varint(existing_section, offset)
            non_param_fields += existing_section[start:offset]
        elif wt == 1:
            offset += 8
            non_param_fields += existing_section[start:offset]
        elif wt == 5:
            offset += 4
            non_param_fields += existing_section[start:offset]
        else:
            break

    # Build output: non-param fields first, then params
    result = non_param_fields

    overridden_keys = set(params.keys())
    removed_keys = set(delete_keys or set())

    # Keep existing params not being overridden
    for key, raw in existing_entries:
        if key is not None and (key in overridden_keys or key in removed_keys):
            continue  # will be replaced
        result += raw

    # Add new/updated params
    for key, value in sorted(params.items()):
        result += _encode_length_delimited(3, _build_param_entry(key, value))

    return result


def _rebuild_param_section_raw(
    existing_section: bytes,
    raw_entries: dict[int, bytes],
) -> bytes:
    """Replace/add raw param entries in a param section, preserving unrelated entries."""
    existing_entries: list[tuple[int | None, bytes]] = []
    offset = 0
    non_param_fields = b""

    while offset < len(existing_section):
        start = offset
        try:
            tag, offset = _read_varint(existing_section, offset)
        except ValueError:
            break
        fn = tag >> 3
        wt = tag & 7

        if wt == 2:
            try:
                length, offset = _read_varint(existing_section, offset)
            except ValueError:
                break
            entry_data = existing_section[offset:offset + length]
            offset += length
            if fn == 3:
                param = _parse_single_param(entry_data)
                key = param.key if param else None
                if key is None:
                    param_key, _value = _parse_param_entry_key_and_raw_value(entry_data)
                    key = param_key
                existing_entries.append((key, existing_section[start:offset]))
            else:
                non_param_fields += existing_section[start:offset]
        elif wt == 0:
            try:
                _, offset = _read_varint(existing_section, offset)
            except ValueError:
                break
            non_param_fields += existing_section[start:offset]
        elif wt == 1:
            offset += 8
            non_param_fields += existing_section[start:offset]
        elif wt == 5:
            offset += 4
            non_param_fields += existing_section[start:offset]
        else:
            break

    result = bytearray(non_param_fields)
    replaced_keys: set[int] = set()
    for key, raw in existing_entries:
        if key is not None and key in raw_entries:
            result.extend(_encode_length_delimited(3, raw_entries[key]))
            replaced_keys.add(key)
            continue
        result.extend(raw)
    for key in sorted(raw_entries):
        if key in replaced_keys:
            continue
        result.extend(_encode_length_delimited(3, raw_entries[key]))
    return bytes(result)


def _rebuild_tool_param_section_raw(
    existing_section: bytes,
    raw_entries: dict[int, bytes],
    *,
    delete_keys: set[int] | None = None,
) -> bytes:
    """Replace/add raw tool param entries in a field-1 repeated param section."""
    existing_entries: list[tuple[int | None, bytes]] = []
    offset = 0
    non_param_fields = b""
    removed_keys = set(delete_keys or set())

    while offset < len(existing_section):
        start = offset
        try:
            tag, offset = _read_varint(existing_section, offset)
        except ValueError:
            break
        fn = tag >> 3
        wt = tag & 7

        if wt == 2:
            try:
                length, offset = _read_varint(existing_section, offset)
            except ValueError:
                break
            entry_data = existing_section[offset:offset + length]
            offset += length
            if fn == 1:
                param = _parse_single_param(entry_data)
                key = param.key if param else None
                if key is None:
                    param_key, _value = _parse_param_entry_key_and_raw_value(entry_data)
                    key = param_key
                existing_entries.append((key, existing_section[start:offset]))
            else:
                non_param_fields += existing_section[start:offset]
        elif wt == 0:
            try:
                _, offset = _read_varint(existing_section, offset)
            except ValueError:
                break
            non_param_fields += existing_section[start:offset]
        elif wt == 1:
            offset += 8
            non_param_fields += existing_section[start:offset]
        elif wt == 5:
            offset += 4
            non_param_fields += existing_section[start:offset]
        else:
            break

    result = bytearray(non_param_fields)
    replaced_keys: set[int] = set()
    for key, raw in existing_entries:
        if key is not None and key in removed_keys:
            continue
        if key is not None and key in raw_entries:
            result.extend(_encode_length_delimited(1, raw_entries[key]))
            replaced_keys.add(key)
            continue
        result.extend(raw)
    for key in sorted(raw_entries):
        if key in replaced_keys:
            continue
        result.extend(_encode_length_delimited(1, raw_entries[key]))
    return bytes(result)


def _parse_param_entry_key_and_raw_value(data: bytes) -> tuple[int | None, tuple[int, bytes] | None]:
    off = 0
    param_key: int | None = None
    raw_value: tuple[int, bytes] | None = None
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
            try:
                length, off = _read_varint(data, off)
            except ValueError:
                break
            sub = data[off:off + length]
            off += length
            try:
                inner_tag, inner_offset = _read_varint(sub, 0)
            except ValueError:
                continue
            inner_fn = inner_tag >> 3
            inner_wt = inner_tag & 7
            if inner_wt == 2:
                try:
                    inner_length, payload_offset = _read_varint(sub, inner_offset)
                except ValueError:
                    continue
                raw_value = (inner_fn, sub[payload_offset:payload_offset + inner_length])
        elif wt == 0:
            try:
                _, off = _read_varint(data, off)
            except ValueError:
                break
        elif wt == 1:
            off += 8
        elif wt == 5:
            off += 4
        elif wt == 2:
            try:
                length, off = _read_varint(data, off)
            except ValueError:
                break
            off += length
        else:
            break
    return param_key, raw_value


def _parse_param_entry_key(data: bytes) -> int | None:
    offset = 0
    while offset < len(data):
        try:
            tag, offset = _read_varint(data, offset)
        except ValueError:
            break
        fn = tag >> 3
        wt = tag & 7
        if fn == 1 and wt == 0:
            key, _ = _read_varint(data, offset)
            return key
        if wt == 0:
            _, offset = _read_varint(data, offset)
        elif wt == 1:
            offset += 8
        elif wt == 5:
            offset += 4
        elif wt == 2:
            length, offset = _read_varint(data, offset)
            offset += length
        else:
            break
    return None


def _parse_param_entry_value(data: bytes) -> bytes | None:
    offset = 0
    while offset < len(data):
        try:
            tag, offset = _read_varint(data, offset)
        except ValueError:
            break
        fn = tag >> 3
        wt = tag & 7
        if fn == 2 and wt == 2:
            length, offset = _read_varint(data, offset)
            return data[offset:offset + length]
        if wt == 0:
            _, offset = _read_varint(data, offset)
        elif wt == 1:
            offset += 8
        elif wt == 5:
            offset += 4
        elif wt == 2:
            length, offset = _read_varint(data, offset)
            offset += length
        else:
            break
    return None


def _build_raw_param_entry(key: int, value: bytes) -> bytes:
    return _encode_length_delimited(
        3,
        _encode_varint_field(1, key) + _encode_length_delimited(2, value),
    )


def _build_varint_param_field(key: int, value: int) -> bytes:
    """Fully-wrapped (field 3) varint param entry for _rebuild_param_section_encoded."""
    return _build_raw_param_entry(key, _encode_varint_field(2, value))


def _build_bytes_param_field(key: int, value: bytes, *, inner_field: int) -> bytes:
    """Fully-wrapped (field 3) bytes param entry for _rebuild_param_section_encoded."""
    return _build_raw_param_entry(key, _encode_length_delimited(inner_field, value))


def _rebuild_param_section_encoded(existing_section: bytes, entries: dict[int, bytes]) -> bytes:
    """Replace/add raw param entries in a param section while preserving order."""
    result = bytearray()
    seen: set[int] = set()
    offset = 0

    while offset < len(existing_section):
        start = offset
        try:
            tag, offset = _read_varint(existing_section, offset)
        except ValueError:
            result.extend(existing_section[start:])
            break
        fn = tag >> 3
        wt = tag & 7

        if wt == 0:
            _, offset = _read_varint(existing_section, offset)
            result.extend(existing_section[start:offset])
        elif wt == 1:
            offset += 8
            result.extend(existing_section[start:offset])
        elif wt == 5:
            offset += 4
            result.extend(existing_section[start:offset])
        elif wt == 2:
            length, offset = _read_varint(existing_section, offset)
            sub = existing_section[offset:offset + length]
            offset += length
            if fn == 3:
                key = _parse_param_entry_key(sub)
                if key in entries:
                    result.extend(entries[key])
                    seen.add(key)
                else:
                    result.extend(existing_section[start:offset])
            else:
                result.extend(existing_section[start:offset])
        else:
            result.extend(existing_section[start:])
            break

    for key, entry in entries.items():
        if key not in seen:
            result.extend(entry)
    return bytes(result)


def _replace_submessage_at_path(
    data: bytes,
    path: list[int],
    new_content: bytes,
) -> bytes:
    """Replace a submessage at a specific field path in protobuf data.

    Preserves all other fields. Only the FIRST occurrence of each
    field in the path is followed/replaced.
    """
    if not path:
        return new_content

    target_field = path[0]
    remaining_path = path[1:]

    result = bytearray()
    offset = 0
    replaced = False

    while offset < len(data):
        start = offset
        try:
            tag, offset = _read_varint(data, offset)
        except ValueError:
            result.extend(data[start:])
            break
        fn = tag >> 3
        wt = tag & 7

        if wt == 2:
            length, offset = _read_varint(data, offset)
            sub_data = data[offset:offset + length]
            offset += length

            if fn == target_field and not replaced:
                if remaining_path:
                    # Recurse deeper
                    modified_sub = _replace_submessage_at_path(sub_data, remaining_path, new_content)
                else:
                    # This is the target — replace content
                    modified_sub = new_content
                result.extend(_encode_length_delimited(fn, modified_sub))
                replaced = True
            else:
                result.extend(data[start:offset])
        elif wt == 0:
            _, offset = _read_varint(data, offset)
            result.extend(data[start:offset])
        elif wt == 1:
            offset += 8
            result.extend(data[start:offset])
        elif wt == 5:
            offset += 4
            result.extend(data[start:offset])
        else:
            result.extend(data[start:])
            break

    return bytes(result)


def _split_grade_node_section(field9: bytes) -> tuple[list[tuple[int, int, bytes, bytes | None]], list[bytes], bytes | None]:
    """Return raw field records, repeated node entries, and node-order bytes for root.1.7.9."""
    fields: list[tuple[int, int, bytes, bytes | None]] = []
    nodes: list[bytes] = []
    node_order: bytes | None = None
    offset = 0
    while offset < len(field9):
        start = offset
        try:
            tag, offset = _read_varint(field9, offset)
        except ValueError:
            break
        fn = tag >> 3
        wt = tag & 7
        sub: bytes | None = None
        if wt == 0:
            try:
                _, offset = _read_varint(field9, offset)
            except ValueError:
                break
        elif wt == 1:
            offset += 8
        elif wt == 5:
            offset += 4
        elif wt == 2:
            try:
                length, offset = _read_varint(field9, offset)
            except ValueError:
                break
            sub = field9[offset:offset + length]
            offset += length
            if fn == 1:
                nodes.append(sub)
            elif fn == 2:
                node_order = sub
        else:
            break
        fields.append((fn, wt, field9[start:offset], sub))
    return fields, nodes, node_order


def _replace_grade_node(field9: bytes, node_index: int, new_node: bytes) -> bytes:
    fields, _nodes, _node_order = _split_grade_node_section(field9)
    result = bytearray()
    seen = 0
    replaced = False
    for fn, wt, raw, _sub in fields:
        if fn == 1 and wt == 2:
            seen += 1
            if seen == node_index:
                result.extend(_encode_length_delimited(1, new_node))
                replaced = True
                continue
        result.extend(raw)
    if not replaced:
        raise APICallFailed(
            "Color Page Power Window DB route could not find the requested window node.",
            details={"node_index": node_index, "node_count": seen},
            recoverability="manual",
        )
    return bytes(result)


def _insert_grade_node_before_order(field9: bytes, new_node: bytes, node_order: bytes) -> bytes:
    fields, _nodes, _existing_order = _split_grade_node_section(field9)
    result = bytearray()
    inserted = False
    for fn, wt, raw, _sub in fields:
        if fn == 2 and wt == 2:
            result.extend(_encode_length_delimited(1, new_node))
            result.extend(_encode_length_delimited(2, node_order))
            inserted = True
        else:
            result.extend(raw)
    if not inserted:
        result.extend(_encode_length_delimited(1, new_node))
        result.extend(_encode_length_delimited(2, node_order))
    return bytes(result)


def _insert_grade_node_after_index(field9: bytes, new_node: bytes, after_node_index: int) -> bytes:
    fields, _nodes, _node_order = _split_grade_node_section(field9)
    result = bytearray()
    seen = 0
    inserted = False
    for fn, wt, raw, _sub in fields:
        result.extend(raw)
        if fn == 1 and wt == 2:
            seen += 1
            if seen == after_node_index:
                result.extend(_encode_length_delimited(1, new_node))
                inserted = True
    if not inserted:
        raise APICallFailed(
            "Color Page Key Output DB route could not find the insertion point for the native Node Key payload.",
            details={"after_node_index": after_node_index, "node_count": seen},
            recoverability="manual",
        )
    return bytes(result)


def _root_color_node_containers(proto_data: bytes) -> list[bytes]:
    root = _get_submessage(proto_data, 1)
    if root is None:
        return []
    return _get_all_submessages(root, 7)


def _grade_node_index_for_color_node_index(proto_data: bytes, color_node_index: int) -> int:
    for position, container in enumerate(_root_color_node_containers(proto_data), 1):
        if _get_first_varint_field(container, 2) == int(color_node_index):
            return position
    return int(color_node_index)


def _primary_grade_node_template_from_proto(proto_data: bytes) -> bytes | None:
    for container in _root_color_node_containers(proto_data):
        field9 = _get_submessage(container, 9)
        if field9 is None:
            continue
        _fields, nodes, _node_order = _split_grade_node_section(field9)
        if nodes:
            return nodes[0]
    return None


def _rebase_grade_node_onto_primary_template(proto_data: bytes, source_node: bytes) -> bytes:
    template = _primary_grade_node_template_from_proto(proto_data)
    if template is None:
        return source_node
    f6 = _get_submessage(source_node, 6)
    source_f2 = _get_submessage(f6, 2) if f6 is not None else None
    if source_f2 is None:
        return template
    return _replace_submessage_at_path(template, [6, 2], source_f2)


def _set_first_varint_field(data: bytes, field_number: int, value: int) -> bytes:
    result = bytearray()
    offset = 0
    replaced = False
    while offset < len(data):
        start = offset
        tag, offset = _read_varint(data, offset)
        fn = tag >> 3
        wt = tag & 7
        if wt == 0:
            _old_value, offset = _read_varint(data, offset)
            if fn == field_number and not replaced:
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
                "Color Page node-add DB route encountered an unsupported protobuf field.",
                details={"field_number": fn, "wire_type": wt},
                recoverability="manual",
            )
    if not replaced:
        return _encode_varint_field(field_number, value) + bytes(result)
    return bytes(result)


def _get_first_varint_field(data: bytes, field_number: int) -> int | None:
    offset = 0
    while offset < len(data):
        tag, offset = _read_varint(data, offset)
        fn = tag >> 3
        wt = tag & 7
        if wt == 0:
            value, offset = _read_varint(data, offset)
            if fn == field_number:
                return value
        elif wt == 1:
            offset += 8
        elif wt == 5:
            offset += 4
        elif wt == 2:
            length, offset = _read_varint(data, offset)
            offset += length
        else:
            raise APICallFailed(
                "Color Page node DB route encountered an unsupported protobuf field.",
                details={"field_number": fn, "wire_type": wt},
                recoverability="manual",
            )
    return None


def _replace_length_delimited_field(data: bytes, field_number: int, payload: bytes | None) -> bytes:
    result = bytearray()
    offset = 0
    replaced = False
    while offset < len(data):
        start = offset
        tag, offset = _read_varint(data, offset)
        fn = tag >> 3
        wt = tag & 7
        if wt == 0:
            _value, offset = _read_varint(data, offset)
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
            if fn == field_number:
                if payload is not None and not replaced:
                    result.extend(_encode_length_delimited(field_number, payload))
                    replaced = True
            else:
                result.extend(data[start:offset])
        else:
            raise APICallFailed(
                "Color Page node DB route encountered an unsupported protobuf field.",
                details={"field_number": fn, "wire_type": wt},
                recoverability="manual",
            )
    if payload is not None and not replaced:
        result.extend(_encode_length_delimited(field_number, payload))
    return bytes(result)


def _remove_root_fields(data: bytes, field_numbers: set[int]) -> bytes:
    result = bytearray()
    offset = 0
    while offset < len(data):
        start = offset
        tag, offset = _read_varint(data, offset)
        fn = tag >> 3
        wt = tag & 7
        if wt == 0:
            _value, offset = _read_varint(data, offset)
        elif wt == 1:
            offset += 8
        elif wt == 5:
            offset += 4
        elif wt == 2:
            length, offset = _read_varint(data, offset)
            offset += length
        else:
            raise APICallFailed(
                "Color Page Layer Mixer DB route encountered an unsupported protobuf field.",
                details={"field_number": fn, "wire_type": wt},
                recoverability="manual",
            )
        if fn not in field_numbers:
            result.extend(data[start:offset])
    return bytes(result)


def _get_first_length_delimited_field(data: bytes, field_number: int) -> bytes | None:
    offset = 0
    while offset < len(data):
        tag, offset = _read_varint(data, offset)
        fn = tag >> 3
        wt = tag & 7
        if wt == 0:
            _value, offset = _read_varint(data, offset)
        elif wt == 1:
            offset += 8
        elif wt == 5:
            offset += 4
        elif wt == 2:
            length, offset = _read_varint(data, offset)
            payload = data[offset : offset + length]
            offset += length
            if fn == field_number:
                return payload
        else:
            raise APICallFailed(
                "Color Page node DB route encountered an unsupported protobuf field.",
                details={"field_number": fn, "wire_type": wt},
                recoverability="manual",
            )
    return None


def _decode_node_label(container: bytes) -> str:
    payload = _get_first_length_delimited_field(container, NODE_LABEL_FIELD)
    if payload is None:
        return ""
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise APICallFailed(
            "Color Page node label payload is not valid UTF-8.",
            details={"field_number": NODE_LABEL_FIELD},
            recoverability="manual",
        ) from exc


def _set_node_label_in_proto(base_proto: bytes, *, node_index: int, label: str) -> tuple[bytes, dict[str, Any]]:
    root = _get_submessage(base_proto, 1)
    if root is None:
        raise APICallFailed(
            "Color Page node label DB route requires an existing grade root.",
            recoverability="manual",
        )
    containers = _root_color_node_containers(base_proto)
    if not containers:
        raise APICallFailed(
            "Color Page node label DB route could not find Color node containers.",
            recoverability="manual",
        )
    root_counter = _get_first_varint_field(root, 1) or (len(containers) + 1)
    target = int(node_index)
    normalized_label = str(label)
    encoded_label = normalized_label.encode("utf-8") if normalized_label else None
    before_label = None
    changed = False
    found = False
    new_containers = []
    for container in containers:
        current_index = _get_first_varint_field(container, 2)
        if current_index == target:
            found = True
            before_label = _decode_node_label(container)
            updated = _replace_length_delimited_field(container, NODE_LABEL_FIELD, encoded_label)
            changed = updated != container
            container = updated
        new_containers.append(container)
    if not found:
        raise ValidationError(
            "Color Page node label DB route could not find the requested node.",
            details={"node_index": target, "node_count": len(containers)},
            recoverability="not_applicable",
        )
    new_root = _replace_root_color_node_containers(root, new_containers, root_counter=root_counter)
    return _replace_submessage_at_path(base_proto, [1], new_root), {
        "node_index": target,
        "before_label": before_label or "",
        "label": normalized_label,
        "changed": changed,
        "node_count": len(containers),
        "field": NODE_LABEL_FIELD,
    }


def _extract_submessage(data: bytes, path: list[int]) -> bytes | None:
    """Walk a protobuf along field path and return the submessage bytes."""
    current = data
    for target_field in path:
        offset = 0
        found = False
        while offset < len(current):
            try:
                tag, offset = _read_varint(current, offset)
            except ValueError:
                break
            fn = tag >> 3
            wt = tag & 7
            if wt == 0:
                _, offset = _read_varint(current, offset)
            elif wt == 1:
                offset += 8
            elif wt == 5:
                offset += 4
            elif wt == 2:
                length, offset = _read_varint(current, offset)
                if fn == target_field:
                    current = current[offset:offset + length]
                    found = True
                    break
                offset += length
            else:
                break
        if not found:
            return None
    return current


def _extract_varint(data: bytes, path: list[int]) -> int | None:
    """Walk a protobuf along field path and return a varint value."""
    if len(path) > 1:
        sub = _extract_submessage(data, path[:-1])
        if sub is None:
            return None
        data = sub
    target = path[-1]
    offset = 0
    while offset < len(data):
        try:
            tag, offset = _read_varint(data, offset)
        except ValueError:
            break
        fn = tag >> 3
        wt = tag & 7
        if fn == target and wt == 0:
            val, _ = _read_varint(data, offset)
            return val
        if wt == 0:
            _, offset = _read_varint(data, offset)
        elif wt == 1:
            offset += 8
        elif wt == 5:
            offset += 4
        elif wt == 2:
            length, offset = _read_varint(data, offset)
            offset += length
        else:
            break
    return None


def _iter_proto_fields(data: bytes) -> list[tuple[int, int, Any, bytes]]:
    fields: list[tuple[int, int, Any, bytes]] = []
    offset = 0
    while offset < len(data):
        start = offset
        try:
            tag, offset = _read_varint(data, offset)
        except ValueError:
            break
        fn = tag >> 3
        wt = tag & 7
        if wt == 0:
            value, offset = _read_varint(data, offset)
            fields.append((fn, wt, value, data[start:offset]))
        elif wt == 1:
            value = data[offset:offset + 8]
            offset += 8
            fields.append((fn, wt, value, data[start:offset]))
        elif wt == 5:
            value = data[offset:offset + 4]
            offset += 4
            fields.append((fn, wt, value, data[start:offset]))
        elif wt == 2:
            length, offset = _read_varint(data, offset)
            value = data[offset:offset + length]
            offset += length
            fields.append((fn, wt, value, data[start:offset]))
        else:
            break
    return fields


def _message_varints(data: bytes) -> dict[int, int]:
    return {fn: int(value) for fn, wt, value, _raw in _iter_proto_fields(data) if wt == 0}


def _first_ld_field(data: bytes, field_number: int) -> bytes | None:
    for fn, wt, value, _raw in _iter_proto_fields(data):
        if fn == field_number and wt == 2:
            return bytes(value)
    return None


def _all_ld_fields(data: bytes, field_number: int) -> list[bytes]:
    return [
        bytes(value)
        for fn, wt, value, _raw in _iter_proto_fields(data)
        if fn == field_number and wt == 2
    ]


def _replace_first_ld_field(
    data: bytes,
    field_number: int,
    predicate: Any,
    replacement: Any,
) -> bytes:
    result = bytearray()
    replaced = False
    for fn, wt, value, raw in _iter_proto_fields(data):
        if fn == field_number and wt == 2 and not replaced and predicate(value):
            result.extend(_encode_length_delimited(fn, replacement(value)))
            replaced = True
        else:
            result.extend(raw)
    if not replaced:
        raise APICallFailed(
            "Color Page HDR detail DB route could not find the expected protobuf container.",
            details={"field_number": field_number},
            recoverability="manual",
        )
    return bytes(result)


__all__ = (
    '_build_param_entry',
    '_build_varint_param_entry',
    '_build_bytes_param_entry',
    '_build_direct_bytes_param_entry',
    '_rebuild_param_section',
    '_rebuild_param_section_raw',
    '_rebuild_tool_param_section_raw',
    '_parse_param_entry_key_and_raw_value',
    '_parse_param_entry_key',
    '_parse_param_entry_value',
    '_build_raw_param_entry',
    '_build_varint_param_field',
    '_build_bytes_param_field',
    '_rebuild_param_section_encoded',
    '_replace_submessage_at_path',
    '_split_grade_node_section',
    '_replace_grade_node',
    '_insert_grade_node_before_order',
    '_insert_grade_node_after_index',
    '_root_color_node_containers',
    '_grade_node_index_for_color_node_index',
    '_primary_grade_node_template_from_proto',
    '_rebase_grade_node_onto_primary_template',
    '_set_first_varint_field',
    '_get_first_varint_field',
    '_replace_length_delimited_field',
    '_remove_root_fields',
    '_get_first_length_delimited_field',
    '_decode_node_label',
    '_set_node_label_in_proto',
    '_extract_submessage',
    '_extract_varint',
    '_iter_proto_fields',
    '_message_varints',
    '_first_ld_field',
    '_all_ld_fields',
    '_replace_first_ld_field',
)
