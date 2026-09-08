"""Hdr helpers for Color Page DB operations."""

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


def _build_hdr_global_payload(*, exposure: float, saturation: float) -> bytes:
    global_message = (
        _encode_length_delimited(1, b"Global")
        + _encode_fixed32_field(2, struct.pack("<f", exposure))
        + _encode_fixed32_field(7, struct.pack("<f", saturation))
    )
    return _encode_length_delimited(16, _encode_length_delimited(1, global_message))


HDR_PALETTE_ZONE_LABELS: dict[str, str] = {
    "highlight": "Highlight",
    "specular": "Specular",
}

# Per-entry fixed32 field numbers inside the 0x86000305 palette payload.
HDR_PALETTE_FIELD_NUMBERS: dict[str, int] = {
    "exposure": 2,
    "y": 3,
    "x": 4,
    "sat": 7,
}
HDR_PALETTE_FIELD_NAMES: dict[int, str] = {v: k for k, v in HDR_PALETTE_FIELD_NUMBERS.items()}


def _parse_hdr_palette_entries(payload: bytes | None) -> list[dict[str, Any]]:
    """Parse the main-section HDR palette payload into ordered zone entries.

    The render-driving HDR store is param 0x86000305 on the primary grade
    node: one field-16 message holding repeated field-1 zone messages
    ("Global", "Highlight", "Specular", ...) with fixed32 controls.
    """
    entries: list[dict[str, Any]] = []
    if not payload:
        return entries
    offset = 0
    while offset < len(payload):
        try:
            tag, offset = _read_varint(payload, offset)
        except ValueError:
            break
        fn = tag >> 3
        wt = tag & 7
        if wt != 2:
            break
        try:
            length, offset = _read_varint(payload, offset)
        except ValueError:
            break
        message = payload[offset:offset + length]
        offset += length
        if fn != 16:
            continue
        moff = 0
        while moff < len(message):
            try:
                mtag, moff = _read_varint(message, moff)
            except ValueError:
                break
            mfn = mtag >> 3
            mwt = mtag & 7
            if mwt != 2:
                break
            try:
                mlen, moff = _read_varint(message, moff)
            except ValueError:
                break
            inner = message[moff:moff + mlen]
            moff += mlen
            if mfn != 1:
                continue
            entry: dict[str, Any] = {"name": None, "fields": {}}
            ioff = 0
            while ioff < len(inner):
                try:
                    itag, ioff = _read_varint(inner, ioff)
                except ValueError:
                    break
                ifn = itag >> 3
                iwt = itag & 7
                if iwt == 2:
                    try:
                        ilen, ioff = _read_varint(inner, ioff)
                    except ValueError:
                        break
                    value = inner[ioff:ioff + ilen]
                    ioff += ilen
                    if ifn == 1:
                        entry["name"] = value.decode("ascii", "ignore")
                elif iwt == 5:
                    entry["fields"][ifn] = struct.unpack("<f", inner[ioff:ioff + 4])[0]
                    ioff += 4
                elif iwt == 0:
                    value, ioff = _read_varint(inner, ioff)
                    entry["fields"][ifn] = value
                else:
                    break
            if entry["name"]:
                entries.append(entry)
    return entries


def _build_hdr_palette_payload_from_entries(entries: list[dict[str, Any]]) -> bytes:
    inner = b""
    for entry in entries:
        message = _encode_length_delimited(1, str(entry["name"]).encode("ascii", "ignore"))
        for field_number in sorted(entry["fields"]):
            value = entry["fields"][field_number]
            message += _encode_fixed32_field(field_number, struct.pack("<f", float(value)))
        inner += _encode_length_delimited(1, message)
    return _encode_length_delimited(16, inner)


def _hdr_palette_zones_readback_from_params(params: list[GradeParam]) -> dict[str, dict[str, float]]:
    """Read all HDR palette zone entries from the main-section param list."""
    zones: dict[str, dict[str, float]] = {}
    for param in params:
        if param.key == PARAM_HDR_GLOBAL_CONTROL and isinstance(param.value, bytes):
            for entry in _parse_hdr_palette_entries(param.value):
                fields = {
                    HDR_PALETTE_FIELD_NAMES.get(fn, f"field_{fn}"): round(float(value), 6)
                    for fn, value in entry["fields"].items()
                    if isinstance(value, float)
                }
                zones[str(entry["name"])] = fields
    return zones


def _parse_hdr_global_payload(payload: bytes) -> dict[str, float] | None:
    offset = 0
    while offset < len(payload):
        try:
            tag, offset = _read_varint(payload, offset)
        except ValueError:
            return None
        fn = tag >> 3
        wt = tag & 7
        if fn == 16 and wt == 2:
            try:
                length, offset = _read_varint(payload, offset)
            except ValueError:
                return None
            message = payload[offset:offset + length]
            offset += length
            inner = _get_submessage(message, 1)
            if not inner:
                continue
            label: str | None = None
            exposure: float | None = None
            saturation: float | None = None
            inner_offset = 0
            while inner_offset < len(inner):
                try:
                    inner_tag, inner_offset = _read_varint(inner, inner_offset)
                except ValueError:
                    break
                inner_fn = inner_tag >> 3
                inner_wt = inner_tag & 7
                if inner_fn == 1 and inner_wt == 2:
                    length, inner_offset = _read_varint(inner, inner_offset)
                    label = inner[inner_offset:inner_offset + length].decode("ascii", "ignore")
                    inner_offset += length
                elif inner_fn == 2 and inner_wt == 5:
                    exposure = struct.unpack("<f", inner[inner_offset:inner_offset + 4])[0]
                    inner_offset += 4
                elif inner_fn == 7 and inner_wt == 5:
                    saturation = struct.unpack("<f", inner[inner_offset:inner_offset + 4])[0]
                    inner_offset += 4
                elif inner_wt == 0:
                    _, inner_offset = _read_varint(inner, inner_offset)
                elif inner_wt == 1:
                    inner_offset += 8
                elif inner_wt == 5:
                    inner_offset += 4
                elif inner_wt == 2:
                    length, inner_offset = _read_varint(inner, inner_offset)
                    inner_offset += length
                else:
                    break
            if label == "Global" and exposure is not None and saturation is not None:
                return {
                    "exposure": round(exposure, 6),
                    "saturation": round(saturation, 6),
                }
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
    return None


def _params_to_hdr_dict(params: list[GradeParam]) -> dict[str, Any] | None:
    result: dict[str, Any] = {}
    for param in params:
        if param.key == PARAM_HDR_GLOBAL_CONTROL and isinstance(param.value, bytes):
            global_control = _parse_hdr_global_payload(param.value)
            if global_control:
                result["global"] = global_control
                result["companion_state_verified"] = _has_hdr_global_companion_state(params)
    legacy_vectors: dict[str, dict[str, float]] = {}
    values = {param.key: param.value for param in params if isinstance(param.value, float)}
    if any(key in values for key in {
        PARAM_HDR_DARK_1,
        PARAM_HDR_DARK_2,
        PARAM_HDR_DARK_3,
        PARAM_HDR_SHADOW_1,
        PARAM_HDR_SHADOW_2,
        PARAM_HDR_SHADOW_3,
        PARAM_HDR_LIGHT_1,
        PARAM_HDR_LIGHT_2,
        PARAM_HDR_LIGHT_3,
    }):
        legacy_vectors = {
            "dark": {
                "x": values.get(PARAM_HDR_DARK_1, 0.0),
                "y": values.get(PARAM_HDR_DARK_2, 0.0),
                "z": values.get(PARAM_HDR_DARK_3, 0.0),
            },
            "shadow": {
                "x": values.get(PARAM_HDR_SHADOW_1, 0.0),
                "y": values.get(PARAM_HDR_SHADOW_2, 0.0),
                "z": values.get(PARAM_HDR_SHADOW_3, 0.0),
            },
            "light": {
                "x": values.get(PARAM_HDR_LIGHT_1, 0.0),
                "y": values.get(PARAM_HDR_LIGHT_2, 0.0),
                "z": values.get(PARAM_HDR_LIGHT_3, 0.0),
            },
        }
    if legacy_vectors:
        result["legacy_vectors"] = legacy_vectors
    return result or None


def _validate_hdr_global_value(name: str, value: float, *, minimum: float, maximum: float) -> None:
    if not math.isfinite(value):
        raise ValidationError(
            f"HDR Global {name} must be a finite number.",
            details={name: value},
            recoverability="not_applicable",
        )
    if value < minimum or value > maximum:
        raise ValidationError(
            f"HDR Global {name} must be between {minimum} and {maximum}.",
            details={name: value, "minimum": minimum, "maximum": maximum},
            recoverability="not_applicable",
        )


def _hdr_global_readback_from_params(params: list[GradeParam]) -> dict[str, float] | None:
    for param in params:
        if param.key == PARAM_HDR_GLOBAL_CONTROL and isinstance(param.value, bytes):
            return _parse_hdr_global_payload(param.value)
    return None


def _has_hdr_global_companion_state(params: list[GradeParam]) -> bool:
    by_key = {param.key: param for param in params}
    global_param = by_key.get(PARAM_HDR_GLOBAL_CONTROL)
    if not global_param or not isinstance(global_param.value, bytes):
        return False
    flag_param = by_key.get(PARAM_HDR_CONTROL_FLAGS)
    if not flag_param or flag_param.value != 4:
        return False
    for key, expected in HDR_GLOBAL_SEED_MODE_PARAM_KEYS.items():
        param = by_key.get(key)
        if not param or param.value != expected:
            return False
    for key in HDR_GLOBAL_SEED_CURVE_PAYLOAD_B64:
        param = by_key.get(key)
        if not param or not isinstance(param.value, bytes):
            return False
        if _decode_curve_points_payload(param.value) is None:
            return False
    return True


def _inject_hdr_global_into_proto(
    base_proto: bytes,
    *,
    exposure: float | None,
    saturation: float | None,
    zone_updates: dict[str, dict[str, float]] | None = None,
) -> tuple[bytes, bool, dict[str, float]]:
    root = _get_submessage(base_proto, 1)
    if root is None:
        raise APICallFailed(
            "Color Page HDR Global DB route requires an existing Color Page grade body.",
            details={"path": "1"},
            recoverability="manual",
        )

    target_container = None
    field9 = None
    nodes: list[bytes] = []
    for container in _get_all_submessages(root, 7):
        candidate_field9 = _get_submessage(container, 9)
        if candidate_field9 is None:
            continue
        candidate_nodes = _split_grade_node_section(candidate_field9)[1]
        if candidate_nodes:
            target_container = container
            field9 = candidate_field9
            nodes = candidate_nodes
            break

    if target_container is None or field9 is None:
        raise APICallFailed(
            "Color Page HDR Global DB route could not find a grade node.",
            recoverability="manual",
        )
    node = nodes[0]
    f6 = _get_submessage(node, 6)
    f2 = _get_submessage(f6, 2) if f6 is not None else None
    if f2 is None:
        raise APICallFailed(
            "Color Page HDR Global DB route could not find the grade param section.",
            details={"path": "1.7.9.1.6.2"},
            recoverability="manual",
            )

    existing_params = _parse_params_from_param_section(f2, node_index=1)
    had_hdr_global = _has_hdr_global_companion_state(existing_params)
    existing_global = _hdr_global_readback_from_params(existing_params) or {}
    exposure_value = float(exposure if exposure is not None else existing_global.get("exposure", 0.0))
    saturation_value = float(saturation if saturation is not None else existing_global.get("saturation", 1.0))
    _validate_hdr_global_value("exposure", exposure_value, minimum=-4.0, maximum=4.0)
    _validate_hdr_global_value("saturation", saturation_value, minimum=0.0, maximum=4.0)
    expected = {
        "exposure": round(exposure_value, 6),
        "saturation": round(saturation_value, 6),
    }
    existing_payload = None
    for param in existing_params:
        if param.key == PARAM_HDR_GLOBAL_CONTROL and isinstance(param.value, bytes):
            existing_payload = param.value
    entries = _parse_hdr_palette_entries(existing_payload)
    by_name = {entry["name"]: entry for entry in entries}
    global_entry = by_name.get("Global")
    if global_entry is None:
        global_entry = {"name": "Global", "fields": {}}
        entries.insert(0, global_entry)
        by_name["Global"] = global_entry
    global_entry["fields"][HDR_PALETTE_FIELD_NUMBERS["exposure"]] = exposure_value
    global_entry["fields"][HDR_PALETTE_FIELD_NUMBERS["sat"]] = saturation_value
    for zone_label, zone_fields in (zone_updates or {}).items():
        zone_entry = by_name.get(zone_label)
        if zone_entry is None:
            zone_entry = {"name": zone_label, "fields": {}}
            entries.append(zone_entry)
            by_name[zone_label] = zone_entry
        zone_entry["fields"].setdefault(HDR_PALETTE_FIELD_NUMBERS["sat"], 1.0)
        for axis, value in zone_fields.items():
            zone_entry["fields"][HDR_PALETTE_FIELD_NUMBERS[axis]] = float(value)
    raw_entries: dict[int, bytes] = {
        PARAM_HDR_GLOBAL_CONTROL: _build_direct_bytes_param_entry(
            PARAM_HDR_GLOBAL_CONTROL,
            _build_hdr_palette_payload_from_entries(entries),
        ),
        PARAM_HDR_CONTROL_FLAGS: _build_varint_param_entry(PARAM_HDR_CONTROL_FLAGS, 4),
    }
    if not had_hdr_global:
        existing_by_key = {param.key: param for param in existing_params}
        raw_entries.update({
            key: _build_varint_param_entry(key, value)
            for key, value in HDR_GLOBAL_SEED_MODE_PARAM_KEYS.items()
        })
        for key, payload_b64 in HDR_GLOBAL_SEED_CURVE_PAYLOAD_B64.items():
            existing_param = existing_by_key.get(key)
            if isinstance(getattr(existing_param, "value", None), bytes):
                continue
            raw_entries[key] = _build_bytes_param_entry(
                key,
                base64.b64decode(payload_b64),
                inner_field=8,
            )

    new_f2 = _rebuild_param_section_raw(f2, raw_entries)
    new_node = _replace_submessage_at_path(node, [6, 2], new_f2)
    new_field9 = _replace_grade_node(field9, 1, new_node)
    new_container = _replace_length_delimited_field(target_container, 9, new_field9)
    new_root = _replace_first_ld_field(
        root,
        7,
        lambda candidate: candidate == target_container,
        lambda _candidate: new_container,
    )
    return _replace_first_ld_field(base_proto, 1, lambda _root: True, lambda _root: new_root), not had_hdr_global, expected


def _is_hdr_detail_container(field7: bytes) -> bool:
    varints = _message_varints(field7)
    return (
        varints.get(1) == 4
        and varints.get(2) == 2
        and varints.get(4) == 190
        and varints.get(5) == 416
    )


def _is_primary_hdr_detail_node(node: bytes) -> bool:
    varints = _message_varints(node)
    return varints.get(1) == 1 and varints.get(3) == 1


def _hdr_detail_param_section(base_proto: bytes) -> bytes | None:
    root = _first_ld_field(base_proto, 1)
    if root is None:
        return None
    for field7 in _all_ld_fields(root, 7):
        if not _is_hdr_detail_container(field7):
            continue
        field9 = _first_ld_field(field7, 9)
        if field9 is None:
            continue
        for node in _all_ld_fields(field9, 1):
            if not _is_primary_hdr_detail_node(node):
                continue
            field6 = _first_ld_field(node, 6)
            if field6 is None:
                continue
            section = _first_ld_field(field6, 2)
            if section is not None:
                return section
    return None


def _replace_hdr_detail_param_section(base_proto: bytes, new_section: bytes) -> bytes:
    root = _first_ld_field(base_proto, 1)
    if root is None:
        raise APICallFailed(
            "Color Page HDR detail DB route requires an existing Color Page grade body.",
            details={"path": "1"},
            recoverability="manual",
        )

    def _replace_field7(field7: bytes) -> bytes:
        def _replace_field9(field9: bytes) -> bytes:
            def _replace_node(node: bytes) -> bytes:
                def _replace_field6(field6: bytes) -> bytes:
                    return _replace_first_ld_field(field6, 2, lambda _section: True, lambda _section: new_section)

                return _replace_first_ld_field(node, 6, lambda _field6: True, _replace_field6)

            return _replace_first_ld_field(field9, 1, _is_primary_hdr_detail_node, _replace_node)

        return _replace_first_ld_field(field7, 9, lambda _field9: True, _replace_field9)

    new_root = _replace_first_ld_field(root, 7, _is_hdr_detail_container, _replace_field7)
    return _replace_first_ld_field(base_proto, 1, lambda _root: True, lambda _root: new_root)


def _fixed32_value(value: bytes) -> float:
    return struct.unpack("<f", value)[0]


def _fixed32_field(field_number: int, value: float) -> bytes:
    return _encode_fixed32_field(field_number, struct.pack("<f", float(value)))


def _decode_hdr_zone_name(data: bytes) -> str | None:
    raw = _first_ld_field(data, 1)
    if raw is None:
        return None
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _parse_hdr_detail_vector_payload(value: bytes | None) -> dict[str, dict[str, float]]:
    if value is None:
        return {}
    container = _first_ld_field(value, 16)
    if container is None:
        return {}
    zones: dict[str, dict[str, float]] = {}
    for zone_msg in _all_ld_fields(container, 1):
        name = _decode_hdr_zone_name(zone_msg)
        if name not in HDR_DETAIL_ZONE_NAMES.values():
            continue
        values: dict[str, float] = {}
        for fn, wt, field_value, _raw in _iter_proto_fields(zone_msg):
            if wt != 5:
                continue
            if fn == 3:
                values["y"] = _fixed32_value(field_value)
            elif fn == 4:
                values["x"] = _fixed32_value(field_value)
            elif fn == 7:
                values["sat"] = _fixed32_value(field_value)
        zones[name.lower()] = values
    return zones


def _build_hdr_detail_vector_payload(zones: dict[str, dict[str, float]]) -> bytes:
    entries = bytearray()
    for zone_name in ("Specular", "Highlight"):
        payload = zones.get(zone_name.lower())
        if not payload:
            continue
        zone = bytearray(_encode_length_delimited(1, zone_name.encode("utf-8")))
        if "y" in payload:
            zone.extend(_fixed32_field(3, payload["y"]))
        if "x" in payload:
            zone.extend(_fixed32_field(4, payload["x"]))
        zone.extend(_fixed32_field(7, float(payload.get("sat", 1.0))))
        entries.extend(_encode_length_delimited(1, bytes(zone)))
    return bytes(entries)


def _parse_hdr_detail_range_payload(value: bytes | None) -> dict[str, dict[str, float]]:
    if value is None:
        return {}
    zones: dict[str, dict[str, float]] = {}
    for wrapper in _all_ld_fields(value, 17):
        zone_msg = _first_ld_field(wrapper, 1)
        if zone_msg is None:
            continue
        name = _decode_hdr_zone_name(zone_msg)
        if name not in HDR_DETAIL_ZONE_NAMES.values():
            continue
        values: dict[str, float] = {}
        for fn, wt, field_value, _raw in _iter_proto_fields(zone_msg):
            if wt != 5:
                continue
            if fn == 2:
                values["range_upper"] = _fixed32_value(field_value)
            elif fn == 3:
                values["range"] = _fixed32_value(field_value)
            elif fn == 4:
                values["anchor"] = _fixed32_value(field_value)
            elif fn == 5:
                values["falloff"] = _fixed32_value(field_value)
        zones[name.lower()] = values
    return zones


def _build_hdr_detail_range_payload(zones: dict[str, dict[str, float]]) -> bytes:
    entries = bytearray()
    for zone_name in ("Specular", "Highlight"):
        payload = zones.get(zone_name.lower())
        if not payload:
            continue
        defaults = HDR_DETAIL_RANGE_DEFAULTS[zone_name.lower()]
        zone = bytearray(_encode_length_delimited(1, zone_name.encode("utf-8")))
        zone.extend(_fixed32_field(2, float(payload.get("range_upper", defaults["range_upper"]))))
        zone.extend(_fixed32_field(3, float(payload.get("range", defaults["range"]))))
        zone.extend(_fixed32_field(4, float(payload.get("anchor", defaults["anchor"]))))
        zone.extend(_fixed32_field(5, float(payload.get("falloff", defaults["falloff"]))))
        wrapper = _encode_length_delimited(1, bytes(zone))
        entries.extend(_encode_length_delimited(17, wrapper))
    return bytes(entries)


def _parse_hdr_detail_readback(base_proto: bytes) -> dict[str, Any]:
    section = _hdr_detail_param_section(base_proto)
    if section is None:
        return {}
    entries: dict[int, bytes] = {}
    for entry in _all_ld_fields(section, 3):
        key = _parse_param_entry_key(entry)
        value = _parse_param_entry_value(entry)
        if key is not None and value is not None:
            entries[key] = value
    return {
        "zones": _parse_hdr_detail_vector_payload(entries.get(PARAM_HDR_DETAIL_VECTOR)),
        "ranges": _parse_hdr_detail_range_payload(entries.get(PARAM_HDR_DETAIL_RANGE)),
        "flags": 4 if entries.get(PARAM_HDR_DETAIL_FLAGS) == _encode_varint_field(2, 4) else None,
    }


def _inject_hdr_detail_vector_into_proto(
    base_proto: bytes,
    *,
    zone: str,
    x: float | None = None,
    y: float | None = None,
    sat: float | None = None,
    range_value: float | None = None,
    falloff: float | None = None,
) -> tuple[bytes, dict[str, Any]]:
    section = _hdr_detail_param_section(base_proto)
    if section is None:
        raise APICallFailed(
            "Color Page HDR Highlight/Specular route requires an existing HDR detail container.",
            details={"path": "1.7[hdr].9.1.6.2", "zone": zone},
            recoverability="manual",
        )
    entries: dict[int, bytes] = {}
    for entry in _all_ld_fields(section, 3):
        key = _parse_param_entry_key(entry)
        value = _parse_param_entry_value(entry)
        if key is not None and value is not None:
            entries[key] = value

    existing = _parse_hdr_detail_vector_payload(entries.get(PARAM_HDR_DETAIL_VECTOR))
    zone_label = HDR_DETAIL_ZONE_NAMES[zone]
    current = dict(existing.get(zone, {}))
    if x is not None:
        current["x"] = float(x)
    if y is not None:
        current["y"] = float(y)
    if sat is not None:
        current["sat"] = float(sat)
    current.setdefault("sat", 1.0)
    existing[zone] = current

    existing_ranges = _parse_hdr_detail_range_payload(entries.get(PARAM_HDR_DETAIL_RANGE))
    range_written: dict[str, float] = {}
    if range_value is not None or falloff is not None:
        range_current = dict(HDR_DETAIL_RANGE_DEFAULTS[zone])
        range_current.update(existing_ranges.get(zone, {}))
        if range_value is not None:
            range_current["range"] = float(range_value)
            range_written["range"] = float(range_value)
        if falloff is not None:
            range_current["falloff"] = float(falloff)
            range_written["falloff"] = float(falloff)
        if y is not None:
            range_current["anchor"] = float(y)
        elif "y" in current:
            range_current.setdefault("anchor", float(current["y"]))
        existing_ranges[zone] = range_current

    raw_entries = {
        PARAM_HDR_DETAIL_VECTOR: _build_bytes_param_field(
            PARAM_HDR_DETAIL_VECTOR,
            _build_hdr_detail_vector_payload(existing),
            inner_field=16,
        ),
        PARAM_HDR_DETAIL_FLAGS: _build_varint_param_field(PARAM_HDR_DETAIL_FLAGS, 4),
    }
    if existing_ranges:
        raw_entries[PARAM_HDR_DETAIL_RANGE] = _build_raw_param_entry(
            PARAM_HDR_DETAIL_RANGE,
            _build_hdr_detail_range_payload(existing_ranges),
        )
    new_section = _rebuild_param_section_encoded(section, raw_entries)
    return _replace_hdr_detail_param_section(base_proto, new_section), {
        "zone": zone,
        "zone_label": zone_label,
        "values": {axis: current[axis] for axis in ("x", "y", "sat") if axis in current},
        "range_values": range_written,
    }


__all__ = (
    '_build_hdr_global_payload',
    'HDR_PALETTE_ZONE_LABELS',
    'HDR_PALETTE_FIELD_NUMBERS',
    'HDR_PALETTE_FIELD_NAMES',
    '_parse_hdr_palette_entries',
    '_build_hdr_palette_payload_from_entries',
    '_hdr_palette_zones_readback_from_params',
    '_parse_hdr_global_payload',
    '_params_to_hdr_dict',
    '_validate_hdr_global_value',
    '_hdr_global_readback_from_params',
    '_has_hdr_global_companion_state',
    '_inject_hdr_global_into_proto',
    '_is_hdr_detail_container',
    '_is_primary_hdr_detail_node',
    '_hdr_detail_param_section',
    '_replace_hdr_detail_param_section',
    '_fixed32_value',
    '_fixed32_field',
    '_decode_hdr_zone_name',
    '_parse_hdr_detail_vector_payload',
    '_build_hdr_detail_vector_payload',
    '_parse_hdr_detail_range_payload',
    '_build_hdr_detail_range_payload',
    '_parse_hdr_detail_readback',
    '_inject_hdr_detail_vector_into_proto',
)
