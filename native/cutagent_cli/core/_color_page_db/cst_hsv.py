"""Cst Hsv helpers for Color Page DB operations."""

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
from .power_windows import *


def _read_length_delimited_string(data: bytes, target_field: int) -> str | None:
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
            payload = data[offset:offset + length]
            offset += length
            if fn == target_field:
                return _decode_ascii(payload)
        else:
            return None
    return None


def _parse_cst_option_entry(data: bytes) -> tuple[str, str] | None:
    """Parse ResolveFX CST option entry: {1: name, 2: {5: token}}."""
    name = _read_length_delimited_string(data, 1)
    value_container = _get_submessage(data, 2)
    if not name or value_container is None:
        return None
    value = _read_length_delimited_string(value_container, 5)
    if value is None:
        return None
    return name, value


def _build_cst_option_content(name: str, value: str) -> bytes:
    return (
        _encode_length_delimited(1, name.encode("ascii")) +
        _encode_length_delimited(2, _encode_length_delimited(5, value.encode("ascii")))
    )


def _build_cst_bool_option_content(name: str, value: int) -> bytes:
    return (
        _encode_length_delimited(1, name.encode("ascii")) +
        _encode_length_delimited(2, _encode_varint_field(3, value))
    )


def _build_cst_tool_param_entry(key: int, value_content: bytes) -> bytes:
    return _encode_length_delimited(
        1,
        _encode_varint_field(1, key) + _encode_length_delimited(2, value_content),
    )


def _cst_tool_entry_key(data: bytes) -> int | None:
    offset = 0
    try:
        tag, offset = _read_varint(data, offset)
    except ValueError:
        return None
    if (tag >> 3) != 1 or (tag & 7) != 0:
        return None
    try:
        key, _ = _read_varint(data, offset)
    except ValueError:
        return None
    return key


def _strip_cst_tool_entries(block: bytes) -> tuple[bytes, list[int]]:
    result = bytearray()
    removed: list[int] = []
    offset = 0
    while offset < len(block):
        start = offset
        try:
            tag, offset = _read_varint(block, offset)
        except ValueError:
            result.extend(block[start:])
            break
        fn = tag >> 3
        wt = tag & 7
        if wt == 0:
            try:
                _, offset = _read_varint(block, offset)
            except ValueError:
                result.extend(block[start:])
                break
            result.extend(block[start:offset])
        elif wt == 1:
            offset += 8
            result.extend(block[start:offset])
        elif wt == 5:
            offset += 4
            result.extend(block[start:offset])
        elif wt == 2:
            try:
                length, offset = _read_varint(block, offset)
            except ValueError:
                result.extend(block[start:])
                break
            sub = block[offset:offset + length]
            offset += length
            key = _cst_tool_entry_key(sub)
            if fn == 1 and key in CST_TOOL_PARAM_KEYS:
                removed.append(key)
            else:
                result.extend(block[start:offset])
        else:
            result.extend(block[start:])
            break
    return bytes(result), removed


def _build_cst_tool_entries(version_id: str, desired: dict[str, str]) -> bytes:
    context = f"OfxImageEffectContextFilter_{version_id}_2"
    required = {
        CST_PARAM_INPUT_COLOR_SPACE,
        CST_PARAM_INPUT_GAMMA,
        CST_PARAM_OUTPUT_COLOR_SPACE,
        CST_PARAM_OUTPUT_GAMMA,
    }
    missing = sorted(required - set(desired))
    if missing:
        raise ValidationError(
            "Creating a Color Space Transform OFX tool requires all four CST options.",
            details={"missing": missing},
            recoverability="not_applicable",
        )

    options = (
        _encode_varint_field(1, 5195353) +
        _encode_length_delimited(2, CST_OFX_PLUGIN_ID.encode("ascii")) +
        _encode_length_delimited(3, b"OfxImageEffectContextFilter") +
        _encode_varint_field(4, 1) +
        _encode_length_delimited(5, _build_cst_bool_option_content("doCAT", 0)) +
        _encode_length_delimited(5, _build_cst_bool_option_content("doFwdOOTF", 1)) +
        _encode_length_delimited(5, _build_cst_bool_option_content("doInvOOTF", 0)) +
        _encode_length_delimited(5, _build_cst_option_content(CST_PARAM_INPUT_COLOR_SPACE, desired[CST_PARAM_INPUT_COLOR_SPACE])) +
        _encode_length_delimited(5, _build_cst_option_content(CST_PARAM_INPUT_GAMMA, desired[CST_PARAM_INPUT_GAMMA])) +
        _encode_length_delimited(5, _build_cst_option_content(CST_PARAM_OUTPUT_COLOR_SPACE, desired[CST_PARAM_OUTPUT_COLOR_SPACE])) +
        _encode_length_delimited(5, _build_cst_option_content(CST_PARAM_OUTPUT_GAMMA, desired[CST_PARAM_OUTPUT_GAMMA])) +
        _encode_length_delimited(5, _build_cst_option_content(CST_PARAM_RESOLVEFX_VERSION, "1.4"))
    )
    return b"".join([
        _build_cst_tool_param_entry(
            CST_TOOL_PARAM_PLUGIN_ID,
            _encode_length_delimited(5, CST_OFX_PLUGIN_ID.encode("ascii")),
        ),
        _build_cst_tool_param_entry(
            CST_TOOL_PARAM_CONTEXT,
            _encode_length_delimited(5, context.encode("ascii")),
        ),
        _build_cst_tool_param_entry(CST_TOOL_PARAM_ENABLE_A, _encode_varint_field(4, 0)),
        _build_cst_tool_param_entry(
            CST_TOOL_PARAM_OPTIONS,
            _encode_length_delimited(21, options),
        ),
        _build_cst_tool_param_entry(CST_TOOL_PARAM_ENABLE_B, _encode_varint_field(4, 0)),
    ])


def _find_color_node_container_for_cst(
    data: bytes,
    node_index: int,
) -> tuple[bytes, list[bytes], int, bytes]:
    root = _get_submessage(data, 1)
    if root is None:
        raise APICallFailed(
            "Color Space Transform DB route could not find the Color Page root container.",
            details={"path": "1"},
            recoverability="manual",
        )
    containers = _root_color_node_containers(data)
    target = int(node_index)
    for position, container in enumerate(containers, 1):
        current_index = _get_first_varint_field(container, 2)
        if current_index == target or (target == 1 and current_index is None and position == 1):
            return root, containers, position, container
    raise ValidationError(
        "Color Space Transform DB route could not find the requested Color Page node.",
        details={"node_index": target, "node_count": len(containers)},
        recoverability="not_applicable",
    )


def _replace_color_node_container_for_cst(
    data: bytes,
    *,
    root: bytes,
    containers: list[bytes],
    container_position: int,
    container: bytes,
) -> bytes:
    new_containers = list(containers)
    new_containers[container_position - 1] = container
    root_counter = _get_first_varint_field(root, 1) or len(new_containers) + 1
    new_root = _replace_root_color_node_containers(root, new_containers, root_counter=int(root_counter))
    return _replace_submessage_at_path(data, [1], new_root)


def _walk_cst_options_for_node(data: bytes, node_index: int) -> dict[str, str]:
    try:
        _root, _containers, _position, container = _find_color_node_container_for_cst(data, int(node_index))
    except (APICallFailed, ValidationError):
        return {}
    tool_block = _get_submessage(container, 10)
    if tool_block is None:
        return {}
    return _walk_cst_options_in_tool_block(tool_block)


def _insert_cst_tool_entries(
    data: bytes,
    version_id: str,
    desired: dict[str, str],
    *,
    node_index: int = 1,
) -> tuple[bytes, bool]:
    root, containers, position, node = _find_color_node_container_for_cst(data, int(node_index))

    tool_entries = _build_cst_tool_entries(version_id, desired)
    block = _get_submessage(node, 10)
    if block is None:
        new_node = _replace_length_delimited_field(node, 10, tool_entries)
        return _replace_color_node_container_for_cst(
            data,
            root=root,
            containers=containers,
            container_position=position,
            container=new_node,
        ), False

    new_block = block + tool_entries
    new_node = _replace_length_delimited_field(node, 10, new_block)
    return _replace_color_node_container_for_cst(
        data,
        root=root,
        containers=containers,
        container_position=position,
        container=new_node,
    ), False


def _replace_cst_options_in_tool_block(
    block: bytes,
    desired: dict[str, str],
) -> tuple[bytes, set[str], bool, int]:
    result = bytearray()
    offset = 0
    written: set[str] = set()
    changed = False
    cst_tool_count = 0

    while offset < len(block):
        start = offset
        try:
            tag, offset = _read_varint(block, offset)
        except ValueError:
            result.extend(block[start:])
            break
        fn = tag >> 3
        wt = tag & 7
        if wt == 0:
            try:
                _, offset = _read_varint(block, offset)
            except ValueError:
                result.extend(block[start:])
                break
            result.extend(block[start:offset])
        elif wt == 1:
            offset += 8
            result.extend(block[start:offset])
        elif wt == 5:
            offset += 4
            result.extend(block[start:offset])
        elif wt == 2:
            try:
                length, offset = _read_varint(block, offset)
            except ValueError:
                result.extend(block[start:])
                break
            sub = block[offset:offset + length]
            offset += length
            key = _cst_tool_entry_key(sub)
            if fn == 1 and key == CST_TOOL_PARAM_OPTIONS:
                value_content = _get_submessage(sub, 2)
                options = _get_submessage(value_content, 21) if value_content is not None else None
                if options is not None and CST_OFX_PLUGIN_ID.encode("ascii") in options.lower():
                    cst_tool_count += 1
                    if cst_tool_count > 1:
                        raise APICallFailed(
                            "Color Space Transform DB route found multiple CST OFX tools.",
                            details={
                                "route": "db_workaround_color_page_cst_existing_ofx",
                                "reason": "multiple_cst_tools_ambiguous",
                            },
                            recoverability="manual",
                        )
                    new_options, option_written, option_changed = _replace_cst_options_in_message(options, desired)
                    new_value_content = _replace_submessage_at_path(value_content, [21], new_options)
                    new_sub = (
                        _encode_varint_field(1, key) +
                        _encode_length_delimited(2, new_value_content)
                    )
                    result.extend(_encode_length_delimited(fn, new_sub))
                    written.update(option_written)
                    changed = changed or option_changed or new_sub != sub
                else:
                    result.extend(block[start:offset])
            else:
                result.extend(block[start:offset])
        else:
            result.extend(block[start:])
            break

    return bytes(result), written, changed, cst_tool_count


def _replace_cst_options_in_existing_tool(
    data: bytes,
    desired: dict[str, str],
    *,
    node_index: int = 1,
) -> tuple[bytes, set[str], bool, int]:
    root, containers, position, node = _find_color_node_container_for_cst(data, int(node_index))
    block = _get_submessage(node, 10)
    if block is None:
        raise APICallFailed(
            "Color Space Transform DB route could not find the Color Page tool block.",
            details={"node_index": int(node_index), "path": "node.10"},
            recoverability="manual",
        )
    new_block, written, changed, cst_tool_count = _replace_cst_options_in_tool_block(block, desired)
    if cst_tool_count == 0:
        raise APICallFailed(
            "Color Space Transform DB route could not locate the CST OFX option container.",
            details={"route": "db_workaround_color_page_cst_existing_ofx", "node_index": int(node_index)},
            recoverability="manual",
        )
    new_node = _replace_length_delimited_field(node, 10, new_block)
    return _replace_color_node_container_for_cst(
        data,
        root=root,
        containers=containers,
        container_position=position,
        container=new_node,
    ), written, changed, cst_tool_count


def _walk_cst_options_in_tool_block(block: bytes) -> dict[str, str]:
    scoped: dict[str, str] = {}
    offset = 0
    while offset < len(block):
        start = offset
        try:
            tag, offset = _read_varint(block, offset)
        except ValueError:
            break
        fn = tag >> 3
        wt = tag & 7
        if wt == 0:
            try:
                _, offset = _read_varint(block, offset)
            except ValueError:
                break
        elif wt == 1:
            offset += 8
        elif wt == 5:
            offset += 4
        elif wt == 2:
            try:
                length, offset = _read_varint(block, offset)
            except ValueError:
                break
            sub = block[offset:offset + length]
            offset += length
            key = _cst_tool_entry_key(sub)
            if fn == 1 and key == CST_TOOL_PARAM_OPTIONS:
                try:
                    value_content = _get_submessage(sub, 2)
                    options = _get_submessage(value_content, 21) if value_content is not None else None
                except ValueError:
                    options = None
                if options is not None and CST_OFX_PLUGIN_ID.encode("ascii") in options.lower():
                    scoped.update(_walk_cst_options(options, depth=1))
        else:
            break
        if offset <= start:
            break
    return scoped


def _walk_cst_options(data: bytes, *, depth: int = 0) -> dict[str, str]:
    if depth > 16:
        return {}
    if depth == 0:
        block = data
        for field in CST_TOOL_BLOCK_PATH:
            block = _get_submessage(block, field)
            if block is None:
                break
        if block is not None:
            scoped = _walk_cst_options_in_tool_block(block)
            if scoped:
                return scoped
    found: dict[str, str] = {}
    offset = 0
    while offset < len(data):
        try:
            tag, offset = _read_varint(data, offset)
        except ValueError:
            break
        wt = tag & 7
        if wt == 0:
            try:
                _, offset = _read_varint(data, offset)
            except ValueError:
                break
        elif wt == 1:
            offset += 8
        elif wt == 5:
            offset += 4
        elif wt == 2:
            try:
                length, offset = _read_varint(data, offset)
            except ValueError:
                break
            sub = data[offset:offset + length]
            offset += length
            try:
                parsed = _parse_cst_option_entry(sub)
            except ValueError:
                parsed = None
            if parsed and parsed[0] in CST_PARAM_NAMES:
                found[parsed[0]] = parsed[1]
            try:
                found.update(_walk_cst_options(sub, depth=depth + 1))
            except ValueError:
                pass
        else:
            break
    return found


def _replace_cst_options_in_message(
    data: bytes,
    desired: dict[str, str],
    *,
    depth: int = 0,
) -> tuple[bytes, set[str], bool]:
    """Replace/insert CST ResolveFX option entries while preserving protobuf shape."""
    if depth > 16:
        return data, set(), False

    result = bytearray()
    offset = 0
    written: set[str] = set()
    changed = False
    has_cst_plugin = CST_OFX_PLUGIN_ID.encode("ascii") in data.lower()
    has_resolvefx_version_entry = False
    has_any_cst_entry = False

    while offset < len(data):
        start = offset
        try:
            tag, offset = _read_varint(data, offset)
        except ValueError:
            result.extend(data[start:])
            break
        fn = tag >> 3
        wt = tag & 7

        if wt == 0:
            try:
                _, offset = _read_varint(data, offset)
            except ValueError:
                result.extend(data[start:])
                break
            result.extend(data[start:offset])
        elif wt == 1:
            offset += 8
            result.extend(data[start:offset])
        elif wt == 5:
            offset += 4
            result.extend(data[start:offset])
        elif wt == 2:
            try:
                length, offset = _read_varint(data, offset)
            except ValueError:
                result.extend(data[start:])
                break
            sub = data[offset:offset + length]
            offset += length
            parsed = _parse_cst_option_entry(sub) if fn == 5 else None
            if parsed:
                name, _value = parsed
                has_resolvefx_version_entry = has_resolvefx_version_entry or name == CST_PARAM_RESOLVEFX_VERSION
                has_any_cst_entry = has_any_cst_entry or name in CST_PARAM_NAMES
                if name == CST_PARAM_RESOLVEFX_VERSION:
                    for missing_name, missing_value in desired.items():
                        if missing_name not in written:
                            result.extend(_encode_length_delimited(5, _build_cst_option_content(missing_name, missing_value)))
                            written.add(missing_name)
                            changed = True
                if name in desired:
                    new_sub = _build_cst_option_content(name, desired[name])
                    result.extend(_encode_length_delimited(fn, new_sub))
                    written.add(name)
                    changed = changed or new_sub != sub
                else:
                    result.extend(data[start:offset])
            else:
                new_sub, nested_written, nested_changed = _replace_cst_options_in_message(sub, desired, depth=depth + 1)
                if nested_changed:
                    result.extend(_encode_length_delimited(fn, new_sub))
                    written.update(nested_written)
                    changed = True
                else:
                    result.extend(data[start:offset])
        else:
            result.extend(data[start:])
            break

    if depth > 0 and has_cst_plugin and not has_resolvefx_version_entry and has_any_cst_entry:
        for missing_name, missing_value in desired.items():
            if missing_name not in written:
                result.extend(_encode_length_delimited(5, _build_cst_option_content(missing_name, missing_value)))
                written.add(missing_name)
                changed = True

    return bytes(result), written, changed


def _cst_lookup_key(value: str) -> str:
    return "".join(ch for ch in str(value or "").casefold() if ch.isalnum())


def _cst_registry_generated_aliases(tokens: set[str], suffix: str) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for token in sorted(tokens):
        if not token.endswith(suffix):
            continue
        stem = token[: -len(suffix)]
        candidates = {
            token,
            stem,
            stem.replace("_", " "),
            stem.replace("_", "-"),
            stem.replace("_OETF", ""),
            stem.replace("_EI800", ""),
        }
        for candidate in candidates:
            raw_lower = str(candidate).strip().lower()
            if raw_lower:
                aliases[raw_lower] = token
            normalized = str(candidate).strip().lower().replace("-", "_").replace("/", "_").replace(".", "_")
            normalized = "_".join(part for part in normalized.split() if part)
            if normalized:
                aliases[normalized] = token
            compact = _cst_lookup_key(candidate)
            if compact:
                aliases[compact] = token
    return aliases


def _cst_registry_curated_aliases(tokens: set[str], curated: dict[str, str]) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for alias, token in curated.items():
        if token not in tokens:
            continue
        raw_lower = str(alias).strip().lower()
        if raw_lower:
            aliases[raw_lower] = token
        normalized = str(alias).strip().lower().replace("-", "_").replace("/", "_").replace(".", "_")
        normalized = "_".join(part for part in normalized.split() if part)
        if normalized:
            aliases[normalized] = token
        compact = _cst_lookup_key(alias)
        if compact:
            aliases[compact] = token
    return aliases


def _build_cst_registry_token_map(
    base_mapping: dict[str, str],
    registry_tokens: set[str] | None,
    *,
    suffix: str,
    curated_aliases: dict[str, str],
) -> dict[str, str]:
    mapping = dict(base_mapping)
    if not registry_tokens:
        return mapping
    allowed = {str(token).strip().upper() for token in registry_tokens if str(token).strip().upper().endswith(suffix)}
    mapping.update(_cst_registry_generated_aliases(allowed, suffix))
    mapping.update(_cst_registry_curated_aliases(allowed, curated_aliases))
    return mapping


def _normalize_cst_token(
    value: str | None,
    mapping: dict[str, str],
    option_name: str,
    *,
    allowed_tokens: set[str] | None = None,
) -> str | None:
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        raise ValidationError(
            f"{option_name} must not be empty.",
            details={"option": option_name},
            recoverability="not_applicable",
        )
    normalized = raw.lower().replace("-", "_").replace("/", "_").replace(".", "_")
    normalized = "_".join(part for part in normalized.split() if part)
    token = mapping.get(raw.lower()) or mapping.get(normalized) or mapping.get(_cst_lookup_key(raw))
    if token:
        if allowed_tokens is not None and token not in allowed_tokens:
            raise ValidationError(
                f"Unsupported Color Space Transform {option_name}.",
                details={"value": value, "token": token, "reason": "token_not_in_live_cst_registry"},
                recoverability="not_applicable",
            )
        return token
    raw_token = raw.strip().upper()
    normalized_token = normalized.upper()
    expected_suffix = "_COLORSPACE" if option_name.endswith("color space") else "_GAMMA"
    if raw_token.endswith(expected_suffix) and raw_token.replace("_", "").isalnum():
        if allowed_tokens is not None and raw_token not in allowed_tokens:
            raise ValidationError(
                f"Unsupported Color Space Transform {option_name}.",
                details={"value": value, "token": raw_token, "reason": "raw_token_not_in_live_cst_registry"},
                recoverability="not_applicable",
            )
        return raw_token
    if normalized_token.endswith(expected_suffix) and normalized_token.replace("_", "").isalnum():
        if allowed_tokens is not None and normalized_token not in allowed_tokens:
            raise ValidationError(
                f"Unsupported Color Space Transform {option_name}.",
                details={"value": value, "token": normalized_token, "reason": "raw_token_not_in_live_cst_registry"},
                recoverability="not_applicable",
            )
        return normalized_token
    raise ValidationError(
        f"Unsupported Color Space Transform {option_name}.",
        details={
            "value": value,
            "known": sorted(mapping),
            "raw_token_hint": "Pass an internal DaVinci Resolve token ending in _COLORSPACE or _GAMMA if it has been live-verified.",
        },
        recoverability="not_applicable",
    )


def _find_param_write_container(
    base_proto: bytes,
    requested_node_index: int,
) -> tuple[bytes, list[bytes], int, bytes, bytes, list[bytes], list[int]] | None:
    """Return the Color Page root field-7 container that owns grade params."""
    root = _get_submessage(base_proto, 1)
    if root is None:
        return None
    containers = _root_color_node_containers(base_proto)
    if requested_node_index > 1:
        for position, container in enumerate(containers, 1):
            if _get_first_varint_field(container, 2) != requested_node_index:
                continue
            field9 = _get_submessage(container, 9) or SERIAL_NODE_GRAPH_ORDER
            _fields, nodes, node_order = _split_grade_node_section(field9)
            return root, containers, position, container, field9, nodes, node_order
        return None

    for position, container in enumerate(containers, 1):
        field9 = _get_submessage(container, 9)
        if field9 is None:
            continue
        _fields, nodes, node_order = _split_grade_node_section(field9)
        if nodes:
            return root, containers, position, container, field9, nodes, node_order
    return None


def _replace_param_write_container(
    base_proto: bytes,
    *,
    root: bytes,
    containers: list[bytes],
    container_position: int,
    container: bytes,
    field9: bytes,
) -> bytes:
    new_container = _replace_length_delimited_field(container, 9, field9)
    new_containers = list(containers)
    new_containers[container_position - 1] = new_container
    root_counter = _get_first_varint_field(root, 1) or len(new_containers) + 1
    new_root = _replace_root_color_node_containers(
        root,
        new_containers,
        root_counter=int(root_counter),
    )
    return _replace_submessage_at_path(base_proto, [1], new_root)


def _param_readback_node_index_for_color_node_index(
    base_proto: bytes,
    requested_node_index: int,
) -> int:
    match = _find_param_write_container(base_proto, int(requested_node_index))
    if match is None:
        return int(requested_node_index)
    _root, _containers, container_position, container, _field9, _nodes, _node_order = match
    return int(_get_first_varint_field(container, 2) or container_position)


def _inject_params_into_proto(
    base_proto: bytes,
    params: dict[int, float],
    *,
    node_index: int = 1,
    delete_keys: set[int] | None = None,
) -> bytes:
    """Inject or update grade params in the version body protobuf.

    Uses surgical replacement: finds the Color Page grade-node container,
    modifies only the param entries, and preserves the surrounding protobuf
    structure exactly as-is.

    If the base_proto has no grade section (baseline), creates the
    full grade structure from a known-good template.
    """
    requested_node_index = int(node_index)
    if requested_node_index < 1:
        raise ValidationError(
            "Color Page node index must be a positive integer.",
            details={"node_index": node_index, "minimum": 1},
            recoverability="not_applicable",
        )
    target_node_index = _grade_node_index_for_color_node_index(base_proto, requested_node_index)

    container_match = _find_param_write_container(base_proto, requested_node_index)
    if container_match is not None:
        root, containers, target_container_position, target_container, field9, nodes, node_order = container_match
        if requested_node_index > 1:
            target_existing_node_position: int | None = None
            mixed_existing_node_position: int | None = None
            primary_node_position: int | None = None
            first_window_node_position: int | None = None
            desired_keys = set(params) | set(delete_keys or set())
            for position, node in enumerate(nodes, 1):
                node_params = _grade_node_params(node, node_index=requested_node_index)
                keys = {param.key for param in node_params}
                has_window = bool(keys & POWER_WINDOW_KEYS)
                if keys & desired_keys and has_window:
                    mixed_existing_node_position = position
                    continue
                if keys & desired_keys:
                    target_existing_node_position = position
                    break
                if has_window and first_window_node_position is None:
                    first_window_node_position = position
                if not has_window and keys:
                    primary_node_position = position

            if target_existing_node_position is not None:
                target_node = nodes[target_existing_node_position - 1]
            elif mixed_existing_node_position is not None:
                target_node = _strip_grade_node_params(
                    _rebase_grade_node_onto_primary_template(
                        base_proto,
                        nodes[mixed_existing_node_position - 1],
                    ),
                    POWER_WINDOW_KEYS,
                )
            elif first_window_node_position is not None:
                target_node = _rebase_grade_node_onto_primary_template(
                    base_proto,
                    _build_empty_serial_grade_node(),
                )
            elif primary_node_position is not None:
                target_node = _strip_grade_node_params(
                    _rebase_grade_node_onto_primary_template(
                        base_proto,
                        nodes[primary_node_position - 1],
                    ),
                        POWER_WINDOW_KEYS,
                )
            else:
                target_node = _rebase_grade_node_onto_primary_template(
                    base_proto,
                    _build_empty_serial_grade_node(),
                )
            f6 = _get_submessage(target_node, 6)
            existing_f2 = _get_submessage(f6, 2) if f6 else None
            if existing_f2 is not None:
                new_f2 = _rebuild_param_section(existing_f2, params, delete_keys=delete_keys)
                new_node = _replace_submessage_at_path(target_node, [6, 2], new_f2)
                if target_existing_node_position is not None:
                    new_field9 = _replace_grade_node(field9, target_existing_node_position, new_node)
                elif mixed_existing_node_position is not None:
                    window_only_node = _strip_grade_node_params(
                        nodes[mixed_existing_node_position - 1],
                        set(params) | set(delete_keys or set()),
                    )
                    new_field9 = _replace_grade_node(field9, mixed_existing_node_position, window_only_node)
                    new_field9 = _insert_grade_node_before_order(
                        new_field9,
                        new_node,
                        node_order or SERIAL_NODE_GRAPH_ORDER,
                    )
                elif first_window_node_position is not None:
                    new_field9 = _insert_grade_node_before_order(
                        field9,
                        new_node,
                        node_order or SERIAL_NODE_GRAPH_ORDER,
                    )
                elif primary_node_position is not None:
                    new_field9 = _replace_grade_node(field9, primary_node_position, new_node)
                else:
                    new_field9 = _insert_grade_node_before_order(
                        field9,
                        new_node,
                        node_order or SERIAL_NODE_GRAPH_ORDER,
                    )
                return _replace_param_write_container(
                    base_proto,
                    root=root,
                    containers=containers,
                    container_position=target_container_position,
                    container=target_container,
                    field9=new_field9,
                )

        if requested_node_index == 1:
            # Grade structure exists — do surgical replacement. Select the
            # requested repeated node and rebuild that node's param section.
            grade_node_position = 1
            if grade_node_position <= len(nodes):
                target_node = nodes[grade_node_position - 1]
                f6 = _get_submessage(target_node, 6)
                existing_f2 = _get_submessage(f6, 2) if f6 else None
                if existing_f2 is not None:
                    new_f2 = _rebuild_param_section(existing_f2, params, delete_keys=delete_keys)
                    new_node = _replace_submessage_at_path(target_node, [6, 2], new_f2)
                    new_f9 = _replace_grade_node(field9, grade_node_position, new_node)
                    return _replace_param_write_container(
                        base_proto,
                        root=root,
                        containers=containers,
                        container_position=target_container_position,
                        container=target_container,
                        field9=new_f9,
                    )
            else:
                raise ValidationError(
                    "Color Page node-local DB write could not find the requested node.",
                    details={
                        "node_index": requested_node_index,
                        "grade_node_index": grade_node_position,
                        "node_count": len(nodes),
                    },
                    recoverability="not_applicable",
                )

    # No existing grade — build from template
    if requested_node_index != 1:
        raise ValidationError(
            "Color Page node-local DB write requires an existing grade graph for node indexes above 1.",
            details={"node_index": requested_node_index, "grade_node_index": target_node_index},
            recoverability="not_applicable",
        )
    return _build_graded_proto_from_baseline(base_proto, params)


def _build_varint_param_entry_content(key: int, value: int) -> bytes:
    return (
        _encode_varint_field(1, int(key))
        + _encode_length_delimited(2, _encode_varint_field(2, int(value)))
    )


def _inject_raw_param_entries_into_proto(
    base_proto: bytes,
    raw_entries: dict[int, bytes],
    *,
    node_index: int = 1,
) -> bytes:
    """Inject pre-encoded param entries into an existing node param section."""
    if not raw_entries:
        return base_proto
    requested_node_index = int(node_index)
    if requested_node_index < 1:
        raise ValidationError(
            "Color Page node index must be a positive integer.",
            details={"node_index": node_index, "minimum": 1},
            recoverability="not_applicable",
        )
    target_node_index = _grade_node_index_for_color_node_index(base_proto, requested_node_index)

    container_match = _find_param_write_container(base_proto, requested_node_index)
    if container_match is not None:
        root, containers, target_container_position, target_container, field9, nodes, node_order = container_match
        if requested_node_index > 1:
            target_existing_node_position: int | None = None
            mixed_existing_node_position: int | None = None
            primary_node_position: int | None = None
            first_window_node_position: int | None = None
            desired_keys = set(raw_entries)
            for position, node in enumerate(nodes, 1):
                node_params = _grade_node_params(node, node_index=requested_node_index)
                keys = {param.key for param in node_params}
                has_window = bool(keys & POWER_WINDOW_KEYS)
                if keys & desired_keys and has_window:
                    mixed_existing_node_position = position
                    continue
                if keys & desired_keys:
                    target_existing_node_position = position
                    break
                if has_window and first_window_node_position is None:
                    first_window_node_position = position
                if not has_window and keys:
                    primary_node_position = position

            if target_existing_node_position is not None:
                target_node = nodes[target_existing_node_position - 1]
            elif mixed_existing_node_position is not None:
                target_node = _strip_grade_node_params(
                    _rebase_grade_node_onto_primary_template(
                        base_proto,
                        nodes[mixed_existing_node_position - 1],
                    ),
                    POWER_WINDOW_KEYS,
                )
            elif first_window_node_position is not None:
                target_node = _rebase_grade_node_onto_primary_template(
                    base_proto,
                    _build_empty_serial_grade_node(),
                )
            elif primary_node_position is not None:
                target_node = _strip_grade_node_params(
                    _rebase_grade_node_onto_primary_template(
                        base_proto,
                        nodes[primary_node_position - 1],
                    ),
                        POWER_WINDOW_KEYS,
                )
            else:
                target_node = _rebase_grade_node_onto_primary_template(
                    base_proto,
                    _build_empty_serial_grade_node(),
                )
            f6 = _get_submessage(target_node, 6)
            existing_f2 = _get_submessage(f6, 2) if f6 else None
            if existing_f2 is not None:
                new_f2 = _rebuild_param_section_raw(existing_f2, raw_entries)
                new_node = _replace_submessage_at_path(target_node, [6, 2], new_f2)
                if target_existing_node_position is not None:
                    new_field9 = _replace_grade_node(field9, target_existing_node_position, new_node)
                elif mixed_existing_node_position is not None:
                    window_only_node = _strip_grade_node_params(
                        nodes[mixed_existing_node_position - 1],
                        set(raw_entries),
                    )
                    new_field9 = _replace_grade_node(field9, mixed_existing_node_position, window_only_node)
                    new_field9 = _insert_grade_node_before_order(
                        new_field9,
                        new_node,
                        node_order or SERIAL_NODE_GRAPH_ORDER,
                    )
                elif first_window_node_position is not None:
                    new_field9 = _insert_grade_node_before_order(
                        field9,
                        new_node,
                        node_order or SERIAL_NODE_GRAPH_ORDER,
                    )
                elif primary_node_position is not None:
                    new_field9 = _replace_grade_node(field9, primary_node_position, new_node)
                else:
                    new_field9 = _insert_grade_node_before_order(
                        field9,
                        new_node,
                        node_order or SERIAL_NODE_GRAPH_ORDER,
                    )
                return _replace_param_write_container(
                    base_proto,
                    root=root,
                    containers=containers,
                    container_position=target_container_position,
                    container=target_container,
                    field9=new_field9,
                )

        if requested_node_index == 1:
            grade_node_position = 1
            if grade_node_position <= len(nodes):
                target_node = nodes[grade_node_position - 1]
                f6 = _get_submessage(target_node, 6)
                existing_f2 = _get_submessage(f6, 2) if f6 else None
                if existing_f2 is not None:
                    new_f2 = _rebuild_param_section_raw(existing_f2, raw_entries)
                    new_node = _replace_submessage_at_path(target_node, [6, 2], new_f2)
                    new_f9 = _replace_grade_node(field9, grade_node_position, new_node)
                    return _replace_param_write_container(
                        base_proto,
                        root=root,
                        containers=containers,
                        container_position=target_container_position,
                        container=target_container,
                        field9=new_f9,
                    )
            else:
                raise ValidationError(
                    "Color Page node-local DB write could not find the requested node.",
                    details={
                        "node_index": requested_node_index,
                        "grade_node_index": grade_node_position,
                        "node_count": len(nodes),
                    },
                    recoverability="not_applicable",
                )

    raise ValidationError(
        "Color Page raw param DB write requires an existing grade graph.",
        details={"node_index": requested_node_index, "grade_node_index": target_node_index},
        recoverability="not_applicable",
    )


def _hsv_node_expected_params(
    *,
    gamma_r: float | None = None,
    gamma_g: float | None = None,
    gamma_b: float | None = None,
    gamma_master: float | None = None,
    gain_r: float | None = None,
    gain_g: float | None = None,
    gain_b: float | None = None,
    gain_master: float | None = None,
) -> dict[int, float]:
    params = dict(HSV_NODE_DEFAULT_PARAMS)
    overrides = {
        PARAM_GAMMA_R: gamma_r,
        PARAM_GAMMA_G: gamma_g,
        PARAM_GAMMA_B: gamma_b,
        PARAM_GAMMA_MASTER: gamma_master,
        PARAM_GAIN_R: gain_r,
        PARAM_GAIN_G: gain_g,
        PARAM_GAIN_B: gain_b,
        PARAM_GAIN_MASTER: gain_master,
    }
    for key, value in overrides.items():
        if value is None:
            continue
        if not math.isfinite(float(value)):
            raise ValidationError(
                "Color Page HSV node wheel values must be finite numbers.",
                details={"name": PARAM_NAMES.get(key, f"0x{key:08X}"), "value": value},
                recoverability="not_applicable",
            )
        params[key] = float(value)
    return params


def _hsv_node_template_field7() -> bytes:
    return bytes.fromhex(HSV_NODE_FIELD7_TEMPLATE_HEX)


def _hsv_node_template_root_field3() -> bytes:
    return bytes.fromhex(HSV_NODE_ROOT_FIELD3_TEMPLATE_HEX)


def _inject_hsv_node_into_proto(base_proto: bytes, params: dict[int, float]) -> bytes:
    """Graft the verified GUI HSV node/channel-mode payload into a grade body."""

    template_field7 = _hsv_node_template_field7()
    template_f2 = _extract_submessage(template_field7, [9, 1, 6, 2])
    if template_f2 is None:
        raise APICallFailed(
            "Color Page HSV node fixture is missing the Primary Balance param section.",
            recoverability="manual",
        )
    new_f2 = _rebuild_param_section(template_f2, params)
    new_field7 = _replace_submessage_at_path(template_field7, [9, 1, 6, 2], new_f2)

    root = _get_submessage(base_proto, 1)
    if root is None:
        baseline = _build_graded_proto_from_baseline(base_proto, {})
        root = _get_submessage(baseline, 1)
        base_proto = baseline
    if root is None:
        raise APICallFailed(
            "Color Page HSV node DB route could not find the grade root payload.",
            recoverability="manual",
        )

    root = _replace_length_delimited_field(root, 7, new_field7)
    new_proto = _replace_submessage_at_path(base_proto, [1], root)
    # The GUI-created HSV fixture replaces the legacy top-level field 4 with a
    # top-level field 3 mode block. Preserve that shape so DaVinci Resolve reopens it as
    # the native HSV/channel-mode node instead of only ordinary RGB primaries.
    new_proto = _remove_root_fields(new_proto, {4})
    new_proto = _replace_length_delimited_field(new_proto, 3, _hsv_node_template_root_field3())
    return new_proto


def _hsv_node_graft_readback(proto_data: bytes) -> dict[str, Any]:
    field7 = _extract_submessage(proto_data, [1, 7])
    template_f10 = _extract_submessage(_hsv_node_template_field7(), [10])
    actual_f10 = _extract_submessage(proto_data, [1, 7, 10])
    root_field3 = _get_first_length_delimited_field(proto_data, 3)
    field9 = _extract_submessage(proto_data, [1, 7, 9])
    nodes = _get_all_submessages(field9, 1) if field9 is not None else []
    return {
        "mode": "hsv_channel_2_primary_balance_fixture",
        "verified_gui_fixture": "davinci_resolve_studio_21_0_0b20_manual_hsv_node_20260608",
        "root_field3_matches_fixture": root_field3 == _hsv_node_template_root_field3(),
        "field10_matches_fixture": actual_f10 == template_f10,
        "field7_present": field7 is not None,
        "node_count": len(nodes),
        "root_field3_sha256": hashlib.sha256(root_field3 or b"").hexdigest() if root_field3 is not None else None,
        "field10_sha256": hashlib.sha256(actual_f10 or b"").hexdigest() if actual_f10 is not None else None,
    }


def _inject_key_output_gain_into_proto(base_proto: bytes, gain: float) -> bytes:
    field9 = _extract_submessage(base_proto, [1, 7, 9])
    if field9 is None:
        raise APICallFailed(
            "Color Page Key Output DB route requires an existing Color Page grade body.",
            recoverability="manual",
        )
    new_field9, _old_gain = _set_key_output_gain_in_node_section(field9, gain)
    return _replace_submessage_at_path(base_proto, [1, 7, 9], new_field9)


def _key_output_gain_from_grade_node(node: bytes) -> float | None:
    f6 = _get_submessage(node, 6)
    f2 = _get_submessage(f6, 2) if f6 is not None else None
    if f2 is None:
        return None
    params = _parse_params_from_param_section(f2, node_index=0)
    for param in params:
        if param.key == PARAM_KEY_OUTPUT_GAIN:
            return float(param.value)
    return None


def _key_output_gain_from_node_section(field9: bytes) -> float | None:
    _fields, nodes, _node_order = _split_grade_node_section(field9)
    for node in nodes:
        gain = _key_output_gain_from_grade_node(node)
        if gain is not None:
            return gain
    return None


def _set_key_output_gain_in_node_section(field9: bytes, gain: float) -> tuple[bytes, float | None]:
    _fields, nodes, node_order = _split_grade_node_section(field9)
    key_node_index = None
    key_node = None
    old_gain = None
    for index, candidate in enumerate(nodes, 1):
        candidate_gain = _key_output_gain_from_grade_node(candidate)
        if candidate_gain is not None:
            key_node_index = index
            key_node = candidate
            old_gain = candidate_gain
            break
    if key_node is None:
        key_node = KEY_OUTPUT_NODE_TEMPLATE
        key_node_index = None
    f6 = _get_submessage(key_node, 6)
    f2 = _get_submessage(f6, 2) if f6 is not None else None
    if f2 is None:
        raise APICallFailed(
            "Color Page Key Output DB route could not find the native Node Key param payload.",
            details={"required_node_index": 2},
            recoverability="manual",
        )
    new_f2 = _rebuild_param_section(f2, {PARAM_KEY_OUTPUT_GAIN: gain})
    new_node = _replace_submessage_at_path(key_node, [6, 2], new_f2)
    if key_node_index is None:
        if not nodes:
            return _insert_grade_node_before_order(field9, new_node, node_order or SERIAL_NODE_GRAPH_ORDER), old_gain
        return _insert_grade_node_after_index(field9, new_node, 1), old_gain
    return _replace_grade_node(field9, key_node_index, new_node), old_gain


def _build_graded_proto_from_baseline(
    base_proto: bytes,
    params: dict[int, float],
) -> bytes:
    """Create a full graded VersionBody protobuf from a baseline.

    Uses the baseline's resolution/framerate data and adds a grade
    section with the requested params.
    """
    # Extract resolution block from baseline
    resolution_block = _extract_submessage(base_proto, [1, 3])
    if not resolution_block:
        resolution_block = bytes.fromhex(
            "08800f10b8081d0000803f20800f28b808"
            "350000803f38800f40b80848ffffffff0f"
        )

    # Build param entries
    param_entries = b""
    for key, value in sorted(params.items()):
        param_entries += _encode_length_delimited(3, _build_param_entry(key, value))

    # Build: field 6 → field 2 (param section with field 1 = version marker)
    param_section = _encode_varint_field(1, 1) + param_entries
    param_container = _encode_length_delimited(6,
        _encode_length_delimited(2, param_section))

    # Build node entry: field 1 { field 1: 1, field 3: 1, field 6: {...} }
    node_entry = _encode_length_delimited(1,
        _encode_varint_field(1, 1) +
        _encode_varint_field(3, 1) +
        param_container)

    # Build grade section (field 9): node + node order
    grade_section = node_entry + _encode_length_delimited(2, b"\x03\x04\x05\x06\x12")

    # Build field 7 (grade container)
    field7 = (
        _encode_varint_field(1, 1) +
        _encode_varint_field(2, 1) +
        _encode_varint_field(4, 190) +
        _encode_varint_field(5, 180) +
        _encode_varint_field(7, 1) +
        _encode_varint_field(8, 44) +
        _encode_length_delimited(9, grade_section)
    )

    # Extract framerate from baseline
    framerate_val = _extract_varint(base_proto, [1, 12]) or _extract_varint(base_proto, [12])

    # Build VersionBody inner (field 1)
    version_inner = (
        _encode_varint_field(1, 1) +
        _encode_varint_field(2, 1) +
        _encode_length_delimited(3, resolution_block) +
        _encode_length_delimited(7, field7) +
        _encode_length_delimited(9,
            _encode_varint_field(1, 1) + _encode_varint_field(2, 80) +
            _encode_length_delimited(3,
                _encode_varint_field(1, 1) + _encode_varint_field(2, 64) +
                _encode_varint_field(3, 1) + _encode_varint_field(4, 1))) +
        _encode_length_delimited(10,
            _encode_varint_field(1, 2) + _encode_varint_field(2, 64) +
            _encode_length_delimited(3,
                _encode_varint_field(1, 2) + _encode_varint_field(2, 64) +
                _encode_varint_field(3, 2) + _encode_varint_field(4, 1)))
    )
    if framerate_val:
        version_inner += _encode_varint_field(12, framerate_val)

    outer = _encode_length_delimited(1, version_inner)
    if framerate_val:
        outer += _encode_varint_field(4, framerate_val)

    return outer


__all__ = (
    '_read_length_delimited_string',
    '_parse_cst_option_entry',
    '_build_cst_option_content',
    '_build_cst_bool_option_content',
    '_build_cst_tool_param_entry',
    '_cst_tool_entry_key',
    '_strip_cst_tool_entries',
    '_build_cst_tool_entries',
    '_insert_cst_tool_entries',
    '_replace_cst_options_in_tool_block',
    '_replace_cst_options_in_existing_tool',
    '_walk_cst_options',
    '_walk_cst_options_in_tool_block',
    '_walk_cst_options_for_node',
    '_replace_cst_options_in_message',
    '_build_cst_registry_token_map',
    '_normalize_cst_token',
    '_inject_params_into_proto',
    '_param_readback_node_index_for_color_node_index',
    '_build_varint_param_entry_content',
    '_inject_raw_param_entries_into_proto',
    '_hsv_node_expected_params',
    '_hsv_node_template_field7',
    '_hsv_node_template_root_field3',
    '_inject_hsv_node_into_proto',
    '_hsv_node_graft_readback',
    '_inject_key_output_gain_into_proto',
    '_key_output_gain_from_grade_node',
    '_key_output_gain_from_node_section',
    '_set_key_output_gain_in_node_section',
    '_build_graded_proto_from_baseline',
)
