"""Native Color Slice payload helpers for Color Page DB operations."""

from __future__ import annotations

import math
import sqlite3
import struct
import uuid
import hashlib
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
from .node_graph import (
    _build_empty_serial_grade_node,
    _is_resolve_gui_serial_color_node_container,
    _replace_root_color_node_containers,
)
from .power_windows import _grade_node_params, _strip_grade_node_params
from .grade_state import _select_active_grade_version, _create_lm_version_table_for_item, _insert_lm_version_from_body


COLOR_SLICE_GLOBAL_PARAM_KEYS = {
    "den": PARAM_COLOR_SLICE_GLOBAL_DEN,
    "den_depth": PARAM_COLOR_SLICE_GLOBAL_DEN_DEPTH,
    "sat": PARAM_COLOR_SLICE_GLOBAL_SAT,
    "sat_balance": PARAM_COLOR_SLICE_GLOBAL_SAT_BALANCE,
    "sat_depth": PARAM_COLOR_SLICE_GLOBAL_SAT_DEPTH,
    "hue": PARAM_COLOR_SLICE_GLOBAL_HUE,
}

COLOR_SLICE_PARAM_KEYS = {
    *COLOR_SLICE_GLOBAL_PARAM_KEYS.values(),
    PARAM_COLOR_SLICE_CENTER,
    PARAM_COLOR_SLICE_PER_SLICE,
}

COLOR_SLICE_TOOL_ENTRY = bytes.fromhex("0a0a08dc8180800c12022001")


def normalize_color_slice_name(name: str) -> str:
    normalized = str(name or "").strip().lower().replace("-", "_")
    aliases = {
        "orange": "skin",
        "skintone": "skin",
        "skin_tone": "skin",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized not in COLOR_SLICE_NAMES:
        raise ValidationError(
            "Color Slice name must be one of: red, skin, yellow, green, cyan, blue, magenta.",
            details={"slice": name, "supported": list(COLOR_SLICE_NAMES)},
            recoverability="not_applicable",
        )
    return normalized


def _require_finite(name: str, value: float) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValidationError(
            "Color Slice values must be finite numbers.",
            details={"name": name, "value": value},
            recoverability="not_applicable",
        )
    return number


def _slice_index(name: str) -> int:
    return list(COLOR_SLICE_NAMES).index(normalize_color_slice_name(name))


def _encode_color_slice_centers(values: list[float]) -> bytes:
    if len(values) != len(COLOR_SLICE_NAMES):
        raise ValueError("Color Slice center payload requires seven values.")
    raw = struct.pack("<" + "f" * len(values), *values)
    return _encode_length_delimited(1, raw)


def _decode_color_slice_centers(payload: bytes) -> dict[str, float]:
    raw = _get_submessage(payload, 1)
    if raw is None or len(raw) != 4 * len(COLOR_SLICE_NAMES):
        return {}
    values = struct.unpack("<" + "f" * len(COLOR_SLICE_NAMES), raw)
    return {name: float(values[index]) for index, name in enumerate(COLOR_SLICE_NAMES)}


def _encode_color_slice_controls(values: dict[str, dict[str, float]]) -> bytes:
    payload = bytearray()
    for name in COLOR_SLICE_NAMES:
        controls = values.get(name, {})
        entry = bytearray(_encode_varint_field(1, 1))
        density = controls.get("density")
        luma = controls.get("luma", 1.0)
        hue = controls.get("hue", 0.0)
        if density is not None:
            entry.extend(_encode_fixed32_field(2, struct.pack("<f", float(density))))
        entry.extend(_encode_fixed32_field(3, struct.pack("<f", float(luma))))
        # DaVinci Resolve writes this field even for the neutral GUI value. The neutral
        # payload is negative zero (00 00 00 80); omitting it makes DaVinci Resolve 21
        # accept Project.db bytes but later sanitize the live Color Page graph.
        entry.extend(_encode_fixed32_field(4, struct.pack("<f", -float(hue))))
        payload.extend(_encode_length_delimited(1, bytes(entry)))
    return bytes(payload)


def _decode_color_slice_controls(payload: bytes) -> dict[str, dict[str, float]]:
    result: dict[str, dict[str, float]] = {}
    offset = 0
    index = 0
    while offset < len(payload) and index < len(COLOR_SLICE_NAMES):
        try:
            tag, offset = _read_varint(payload, offset)
        except ValueError:
            break
        fn = tag >> 3
        wt = tag & 7
        if fn != 1 or wt != 2:
            break
        try:
            length, offset = _read_varint(payload, offset)
        except ValueError:
            break
        entry = payload[offset:offset + length]
        offset += length
        controls: dict[str, float] = {"luma": 1.0, "hue": 0.0}
        entry_offset = 0
        while entry_offset < len(entry):
            try:
                entry_tag, entry_offset = _read_varint(entry, entry_offset)
            except ValueError:
                break
            entry_fn = entry_tag >> 3
            entry_wt = entry_tag & 7
            if entry_wt == 0:
                _, entry_offset = _read_varint(entry, entry_offset)
            elif entry_wt == 5:
                if entry_offset + 4 > len(entry):
                    break
                value = struct.unpack("<f", entry[entry_offset:entry_offset + 4])[0]
                entry_offset += 4
                if entry_fn == 2:
                    controls["density"] = float(value)
                elif entry_fn == 3:
                    controls["luma"] = float(value)
                elif entry_fn == 4:
                    controls["hue"] = float(-value)
            elif entry_wt == 2:
                try:
                    length, entry_offset = _read_varint(entry, entry_offset)
                except ValueError:
                    break
                entry_offset += length
            elif entry_wt == 1:
                entry_offset += 8
            else:
                break
        result[COLOR_SLICE_NAMES[index]] = controls
        index += 1
    return result


def _color_slice_payloads_from_params(params: list[GradeParam]) -> dict[str, Any]:
    global_values: dict[str, float] = {}
    centers = {name: 0.0 for name in COLOR_SLICE_NAMES}
    controls = {name: {"luma": 1.0, "hue": 0.0} for name in COLOR_SLICE_NAMES}
    for param in params:
        if param.key in COLOR_SLICE_GLOBAL_PARAM_KEYS.values() and isinstance(param.value, float):
            name = PARAM_NAMES.get(param.key, f"0x{param.key:08X}").removeprefix("color_slice_global_")
            # DaVinci Resolve stores the top-level Color Slice Hue with the opposite
            # sign from the GUI value. Keep the public readback in GUI terms.
            global_values[name] = -float(param.value) if param.key == PARAM_COLOR_SLICE_GLOBAL_HUE else float(param.value)
        elif param.key == PARAM_COLOR_SLICE_CENTER and isinstance(param.value, bytes):
            centers.update(_decode_color_slice_centers(param.value))
        elif param.key == PARAM_COLOR_SLICE_PER_SLICE and isinstance(param.value, bytes):
            decoded = _decode_color_slice_controls(param.value)
            for name, values in decoded.items():
                controls.setdefault(name, {}).update(values)
    return {"global": global_values, "centers": centers, "slices": controls}


def _color_slice_raw_param_entry(key: int, payload: bytes) -> bytes:
    inner_field = 24 if key == PARAM_COLOR_SLICE_PER_SLICE else 12
    return _encode_varint_field(1, key) + _encode_length_delimited(
        2,
        _encode_length_delimited(inner_field, payload),
    )


def _existing_color_slice_state(proto: bytes) -> dict[str, Any]:
    return _color_slice_payloads_from_params(_parse_params_from_proto(proto))


def _stable_non_color_slice_param_value(param: GradeParam) -> Any:
    if isinstance(param.value, bytes):
        return {"kind": param.value_kind, "sha256": hashlib.sha256(param.value).hexdigest(), "size": len(param.value)}
    return {"kind": param.value_kind, "value": round(float(param.value), 9) if isinstance(param.value, float) else param.value}


def _tool_block_preservation_signature(tool_block: bytes) -> dict[str, Any]:
    preserved = bytes(tool_block or b"").replace(COLOR_SLICE_TOOL_ENTRY, b"")
    return {
        "sha256": hashlib.sha256(preserved).hexdigest() if preserved else None,
        "size": len(preserved),
        "has_color_slice_tool": COLOR_SLICE_TOOL_ENTRY in (tool_block or b""),
    }


def _color_slice_graph_preservation_signature(proto: bytes) -> dict[str, Any]:
    """Return the graph pieces Color Slice is never allowed to rewrite.

    Color Slice writes may add/replace only Color Slice param entries on the
    requested node. They must not collapse Color Page node containers, rewrite
    labels/tools, remove CST/OFX payloads, or drop unrelated primary/window
    parameters. This signature intentionally ignores Color Slice param values
    while preserving enough structure to catch DaVinci Resolve sanitizing a
    malformed grade body back to a one-node/empty graph after reopen.
    """
    containers = _root_color_node_containers(proto)
    nodes: list[dict[str, Any]] = []
    for position, container in enumerate(containers, 1):
        field9 = _get_submessage(container, 9) or b""
        _fields, grade_nodes, _node_order = _split_grade_node_section(field9)
        grade_node_signatures: list[dict[str, Any]] = []
        color_node_index = int(_get_first_varint_field(container, 2) or position)
        for grade_position, grade_node in enumerate(grade_nodes, 1):
            params = [
                param
                for param in _grade_node_params(grade_node, node_index=color_node_index)
                if param.key not in COLOR_SLICE_PARAM_KEYS
            ]
            grade_node_signatures.append(
                {
                    "position": grade_position,
                    "non_color_slice_params": [
                        {
                            "key": f"0x{param.key:08X}",
                            **_stable_non_color_slice_param_value(param),
                        }
                        for param in sorted(params, key=lambda item: item.key)
                    ],
                }
            )
        tool_block = _get_submessage(container, 10) or b""
        tool_signature = _tool_block_preservation_signature(tool_block)
        nodes.append(
            {
                "position": position,
                "graph_id": _get_first_varint_field(container, 1),
                "node_index": color_node_index,
                "node_type": _get_first_varint_field(container, 8),
                "label": _decode_node_label(container),
                "tool_block_sha256": tool_signature["sha256"],
                "tool_block_size": tool_signature["size"],
                "has_color_slice_tool": tool_signature["has_color_slice_tool"],
                "grade_node_count": len(grade_nodes),
                "grade_nodes": grade_node_signatures,
            }
        )
    return {"node_count": len(containers), "nodes": nodes}


def _color_slice_preservation_comparison_signature(signature: dict[str, Any]) -> dict[str, Any]:
    comparable = {"node_count": signature.get("node_count"), "nodes": []}
    for node in signature.get("nodes") or []:
        if not isinstance(node, dict):
            continue
        copied = dict(node)
        copied.pop("has_color_slice_tool", None)
        copied["grade_nodes"] = [
            grade_node
            for grade_node in (copied.get("grade_nodes") or [])
            if (grade_node.get("non_color_slice_params") if isinstance(grade_node, dict) else None)
        ]
        copied["grade_node_count"] = len(copied["grade_nodes"])
        comparable["nodes"].append(copied)
    return comparable


def _raise_color_slice_graph_preservation_error(
    *,
    stage: str,
    expected: dict[str, Any],
    actual: dict[str, Any],
) -> None:
    raise APICallFailed(
        "Color Slice DB write did not preserve the existing Color Page node graph.",
        details={
            "reason": "color_slice_graph_preservation_failed",
            "stage": stage,
            "expected_node_count": expected.get("node_count"),
            "actual_node_count": actual.get("node_count"),
            "expected_graph_signature": expected,
            "actual_graph_signature": actual,
        },
        recoverability="manual",
    )


def _verify_color_slice_graph_preserved(
    *,
    stage: str,
    expected: dict[str, Any],
    actual: dict[str, Any],
) -> None:
    if _color_slice_preservation_comparison_signature(actual) != _color_slice_preservation_comparison_signature(expected):
        _raise_color_slice_graph_preservation_error(stage=stage, expected=expected, actual=actual)


def _ensure_color_slice_tool_entry_in_proto(base_proto: bytes, *, node_index: int) -> bytes:
    target = int(node_index)
    container_match = _find_param_write_container(base_proto, target)
    if container_match is None:
        raise ValidationError(
            "Color Slice tool metadata requires an existing Color Page node graph.",
            details={"node_index": target},
            recoverability="not_applicable",
        )
    root, containers, container_position, container, field9, _nodes, _node_order = container_match
    tool_block = _get_submessage(container, 10) or b""
    if COLOR_SLICE_TOOL_ENTRY in tool_block:
        return base_proto
    new_container = _replace_length_delimited_field(container, 10, tool_block + COLOR_SLICE_TOOL_ENTRY)
    new_containers = list(containers)
    new_containers[container_position - 1] = new_container
    root_counter = _get_first_varint_field(root, 1) or len(new_containers) + 1
    new_root = _replace_root_color_node_containers(
        root,
        new_containers,
        root_counter=int(root_counter),
    )
    return _replace_submessage_at_path(base_proto, [1], new_root)


def _inject_color_slice_raw_entries_into_proto(
    base_proto: bytes,
    raw_entries: dict[int, bytes],
    *,
    node_index: int,
) -> bytes:
    """Inject Color Slice params without corrupting existing node-local tools.

    DaVinci Resolve 21 accepts Color Slice as a node-local tool, but live testing showed
    that adding Color Slice raw params into a secondary node's existing
    Primary/CDL grade subnode can make GetToolsInNode() drop that node's tools
    after reopen. GUI-authored secondary Color Slice payloads use a separate
    ColorSlice-only grade subnode, so secondary writes follow that shape.
    """
    if int(node_index) <= 1:
        if _find_param_write_container(base_proto, 1) is None:
            base_proto = _build_graded_proto_from_baseline(base_proto, {})
        return _inject_raw_param_entries_into_proto(
            base_proto,
            raw_entries,
            node_index=node_index,
        )

    container_match = _find_param_write_container(base_proto, int(node_index))
    if container_match is None:
        return _inject_raw_param_entries_into_proto(
            base_proto,
            raw_entries,
            node_index=node_index,
        )

    root, containers, container_position, container, field9, nodes, node_order = container_match
    color_slice_position: int | None = None
    mixed_color_slice_position: int | None = None
    for position, node in enumerate(nodes, 1):
        keys = {param.key for param in _grade_node_params(node, node_index=int(node_index))}
        if not keys & COLOR_SLICE_PARAM_KEYS:
            continue
        if keys - COLOR_SLICE_PARAM_KEYS:
            mixed_color_slice_position = position
        else:
            color_slice_position = position
            break

    template_node = (
        nodes[color_slice_position - 1]
        if color_slice_position is not None
        else _rebase_grade_node_onto_primary_template(base_proto, _build_empty_serial_grade_node())
    )
    f6 = _get_submessage(template_node, 6)
    existing_f2 = _get_submessage(f6, 2) if f6 else None
    if existing_f2 is None:
        raise ValidationError(
            "Color Slice DB write could not find a valid node parameter section.",
            details={"node_index": int(node_index)},
            recoverability="not_applicable",
        )
    color_slice_f2 = _rebuild_param_section_raw(existing_f2, raw_entries)
    color_slice_node = _replace_submessage_at_path(template_node, [6, 2], color_slice_f2)

    if color_slice_position is not None:
        new_field9 = _replace_grade_node(field9, color_slice_position, color_slice_node)
    elif mixed_color_slice_position is not None:
        cleaned_node = _strip_grade_node_params(
            nodes[mixed_color_slice_position - 1],
            COLOR_SLICE_PARAM_KEYS,
        )
        new_field9 = _replace_grade_node(field9, mixed_color_slice_position, cleaned_node)
        new_field9 = _insert_grade_node_before_order(
            new_field9,
            color_slice_node,
            node_order or SERIAL_NODE_GRAPH_ORDER,
        )
    else:
        new_field9 = _insert_grade_node_before_order(
            field9,
            color_slice_node,
            node_order or SERIAL_NODE_GRAPH_ORDER,
        )

    return _replace_param_write_container(
        base_proto,
        root=root,
        containers=containers,
        container_position=container_position,
        container=container,
        field9=new_field9,
    )


def _require_color_slice_render_active_target(base_proto: bytes, *, node_index: int) -> None:
    target = int(node_index)
    if target <= 1:
        return
    container_match = _find_param_write_container(base_proto, target)
    if container_match is None:
        return
    _root, _containers, _container_position, container, _field9, nodes, _node_order = container_match
    if nodes:
        return
    if _is_resolve_gui_serial_color_node_container(container):
        return
    raise ValidationError(
        "Color Slice requires a render-active Color Page node with a DaVinci Resolve-like serial container.",
        details={
            "node_index": target,
            "grade_node_count": 0,
            "reason": "empty_serial_node_container_shape_is_not_render_visible_for_color_slice",
            "suggested_fix": "Create the target node with the render-visible serial node route or apply Color Slice to an existing render-active node.",
        },
        recoverability="manual",
    )


def _inject_color_slice_into_proto(
    base_proto: bytes,
    *,
    node_index: int,
    slice_name: str | None = None,
    center: float | None = None,
    hue: float | None = None,
    density: float | None = None,
    luma: float | None = None,
    global_values: dict[str, float] | None = None,
) -> tuple[bytes, dict[str, Any]]:
    globals_to_write = dict(global_values or {})
    _require_color_slice_render_active_target(base_proto, node_index=node_index)
    proto = base_proto
    raw_entries: dict[int, bytes] = {
        COLOR_SLICE_GLOBAL_PARAM_KEYS[name]: _build_param_entry(
            COLOR_SLICE_GLOBAL_PARAM_KEYS[name],
            -_require_finite(name, value) if name == "hue" else _require_finite(name, value),
        )
        for name, value in globals_to_write.items()
        if value is not None
    }
    if slice_name is not None or center is not None or hue is not None or density is not None or luma is not None:
        if slice_name is None:
            raise ValidationError(
                "--slice is required when setting per-slice Color Slice controls.",
                details={"per_slice_options": ["center", "hue", "density", "luma"]},
                recoverability="not_applicable",
            )
        normalized_slice = normalize_color_slice_name(slice_name)
        state = _existing_color_slice_state(proto)
        centers = dict(state["centers"])
        controls = {name: dict(values) for name, values in state["slices"].items()}
        if center is not None:
            centers[normalized_slice] = _require_finite("center", center)
        target = controls.setdefault(normalized_slice, {"luma": 1.0, "hue": 0.0})
        if hue is not None:
            target["hue"] = _require_finite("hue", hue)
        if density is not None:
            target["density"] = _require_finite("density", density)
        if luma is not None:
            target["luma"] = _require_finite("luma", luma)
        raw_entries[PARAM_COLOR_SLICE_CENTER] = _color_slice_raw_param_entry(
            PARAM_COLOR_SLICE_CENTER,
            _encode_color_slice_centers([centers[name] for name in COLOR_SLICE_NAMES]),
        )
        raw_entries[PARAM_COLOR_SLICE_PER_SLICE] = _color_slice_raw_param_entry(
            PARAM_COLOR_SLICE_PER_SLICE,
            _encode_color_slice_controls(controls),
        )
    if raw_entries:
        state = _existing_color_slice_state(proto)
        raw_entries.setdefault(
            PARAM_COLOR_SLICE_CENTER,
            _color_slice_raw_param_entry(
                PARAM_COLOR_SLICE_CENTER,
                _encode_color_slice_centers([state["centers"][name] for name in COLOR_SLICE_NAMES]),
            ),
        )
        raw_entries.setdefault(
            PARAM_COLOR_SLICE_PER_SLICE,
            _color_slice_raw_param_entry(
                PARAM_COLOR_SLICE_PER_SLICE,
                _encode_color_slice_controls(state["slices"]),
            ),
        )
        proto = _inject_color_slice_raw_entries_into_proto(proto, raw_entries, node_index=node_index)
        proto = _ensure_color_slice_tool_entry_in_proto(proto, node_index=node_index)
    return proto, _existing_color_slice_state(proto)


def write_color_slice(
    conn: Any,
    *,
    clip_name: str | None = None,
    node_index: int = 1,
    slice_name: str | None = None,
    center: float | None = None,
    hue: float | None = None,
    density: float | None = None,
    luma: float | None = None,
    global_den: float | None = None,
    global_den_depth: float | None = None,
    global_sat: float | None = None,
    global_sat_balance: float | None = None,
    global_sat_depth: float | None = None,
    global_hue: float | None = None,
) -> dict[str, Any]:
    """Set native Color Slice controls through the Disk Project.db route."""
    target_node_index = int(node_index)
    if target_node_index < 1:
        raise ValidationError(
            "Color Page node index must be a positive integer.",
            details={"node_index": node_index, "minimum": 1},
            recoverability="not_applicable",
        )
    global_values = {
        "den": global_den,
        "den_depth": global_den_depth,
        "sat": global_sat,
        "sat_balance": global_sat_balance,
        "sat_depth": global_sat_depth,
        "hue": global_hue,
    }
    global_values = {key: value for key, value in global_values.items() if value is not None}
    if not global_values and slice_name is None and center is None and hue is None and density is None and luma is None:
        raise ValidationError("No Color Slice values specified.")

    from ..db_timeline_selection import resolve_video_group

    item_ref = resolve_video_group(conn, clip_name=clip_name)["video"]
    timeline = getattr(conn, "timeline", None)
    timeline_name = timeline.GetName() if timeline and hasattr(timeline, "GetName") else None

    def writer(connection: Any, cursor: sqlite3.Cursor, session: DiskDbMutationSession) -> dict[str, Any]:
        row = find_ti_item_row(
            cursor,
            item=item_ref,
            db_type="Sm2TiVideoClip",
            timeline_name=timeline_name,
        )
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
            base_proto = _build_graded_proto_from_baseline(base_proto, {})
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

        graph_preservation_signature = _color_slice_graph_preservation_signature(base_proto)

        new_proto, color_slice_readback = _inject_color_slice_into_proto(
            base_proto,
            node_index=target_node_index,
            slice_name=slice_name,
            center=center,
            hue=hue,
            density=density,
            luma=luma,
            global_values=global_values,
        )
        post_injection_signature = _color_slice_graph_preservation_signature(new_proto)
        _verify_color_slice_graph_preserved(
            stage="pre_commit_encoder",
            expected=graph_preservation_signature,
            actual=post_injection_signature,
        )
        new_body = compress_version_body(new_proto)
        if created_version:
            _insert_lm_version_from_body(
                cursor,
                body=new_body,
                version_id=version_id,
                version_table_id=str(ver_table_id),
            )
            session.steps.append("create_color_slice_grade_version")
        else:
            cursor.execute(
                '''UPDATE "ListMgt::LmVersion" SET Body = ?, HasCorrection = 1
                   WHERE "ListMgt::LmVersion_id" = ?''',
                (new_body, version_id),
            )
            session.steps.append("update_color_slice_grade_version")
        if created_version_table:
            session.steps.append("create_grade_version_table")
        return {
            "clip": item_ref.name,
            "clip_id": clip_id,
            "version_table_id": str(ver_table_id),
            "version_id": version_id,
            "node_index": target_node_index,
            "created_version": created_version,
            "created_version_table": created_version_table,
            "color_slice_written": {
                "slice": normalize_color_slice_name(slice_name) if slice_name is not None else None,
                "center": center,
                "hue": hue,
                "density": density,
                "luma": luma,
                "global": global_values,
            },
            "readback": {"color_slice": color_slice_readback},
            "graph_preservation": {
                "status": "verified_pre_commit",
                "signature": graph_preservation_signature,
            },
        }

    def verifier(_fresh_conn: Any, mutation_result: Any, session: DiskDbMutationSession) -> dict[str, Any]:
        if not isinstance(mutation_result, dict):
            raise APICallFailed(
                "Color Slice DB mutation did not return a mutation payload for verification.",
                details={"mutation_result": mutation_result},
            )
        version_id = mutation_result.get("version_id")
        version_table_id = mutation_result.get("version_table_id")
        connection = sqlite3.connect(session.project_db_path)
        connection.row_factory = sqlite3.Row
        try:
            if version_table_id:
                active_row = connection.execute(
                    'SELECT pActive FROM "ListMgt::LmVersionTable" WHERE "ListMgt::LmVersionTable_id" = ?',
                    (version_table_id,),
                ).fetchone()
                if active_row and str(active_row["pActive"]) != str(version_id):
                    raise APICallFailed(
                        "Color Slice verification found that DaVinci Resolve did not keep the mutated grade version active after project reload.",
                        details={
                            "version_table_id": version_table_id,
                            "expected_active_version_id": version_id,
                            "actual_active_version_id": active_row["pActive"],
                        },
                        recoverability="manual",
                    )
            row = connection.execute(
                'SELECT Body, HasCorrection FROM "ListMgt::LmVersion" WHERE "ListMgt::LmVersion_id" = ?',
                (version_id,),
            ).fetchone()
            if not row or not row["Body"]:
                raise APICallFailed(
                    "Color Slice verification could not read the active grade body.",
                    details={"version_id": version_id},
                    recoverability="manual",
                )
            if int(row["HasCorrection"] or 0) != 1:
                raise APICallFailed(
                    "Color Slice verification found the active grade version was not marked as a valid correction after project reload.",
                    details={
                        "version_id": version_id,
                        "version_table_id": version_table_id,
                        "has_correction": row["HasCorrection"],
                    },
                    recoverability="manual",
                )
            reloaded_proto = decompress_version_body(row["Body"])
            reloaded_graph_signature = _color_slice_graph_preservation_signature(reloaded_proto)
            expected_graph_signature = (mutation_result.get("graph_preservation") or {}).get("signature") or {}
            _verify_color_slice_graph_preserved(
                stage="post_reopen_verifier",
                expected=expected_graph_signature,
                actual=reloaded_graph_signature,
            )
            readback = _existing_color_slice_state(reloaded_proto)
        finally:
            connection.close()

        written = mutation_result["color_slice_written"]
        mismatches: list[dict[str, Any]] = []
        tolerance = 0.001
        for name, expected in written["global"].items():
            actual = readback["global"].get(name)
            if actual is None or abs(float(actual) - float(expected)) > tolerance:
                mismatches.append({"scope": "global", "name": name, "expected": expected, "actual": actual})
        target_slice = written.get("slice")
        if target_slice:
            if written.get("center") is not None:
                actual = readback["centers"].get(target_slice)
                if actual is None or abs(float(actual) - float(written["center"])) > tolerance:
                    mismatches.append({"scope": "center", "slice": target_slice, "expected": written["center"], "actual": actual})
            for key in ("hue", "density", "luma"):
                expected = written.get(key)
                if expected is None:
                    continue
                actual = readback["slices"].get(target_slice, {}).get(key)
                if actual is None or abs(float(actual) - float(expected)) > tolerance:
                    mismatches.append({"scope": "slice", "slice": target_slice, "name": key, "expected": expected, "actual": actual})
        if mismatches:
            raise APICallFailed(
                "Color Slice DB write did not verify after project reload.",
                details={"mismatches": mismatches, "readback": readback},
                recoverability="manual",
            )
        return {
            "status": "db_readback_verified",
            "clip": mutation_result.get("clip"),
            "node_index": target_node_index,
            "color_slice": readback,
            "render_proof_status": "not_performed",
            "render_proof_required": True,
            "graph_preservation_status": "verified",
            "graph_signature": (mutation_result.get("graph_preservation") or {}).get("signature"),
            "note": (
                "Project.db readback matched after project reload. Final workflows must still use "
                "render/frame proof before claiming a visible grade."
            ),
        }

    return execute_sqlite_disk_db_mutation(
        conn,
        context="color page color slice db mutation",
        writer=writer,
        verifier=verifier,
        allow_project_name_inference=True,
    )


__all__ = (
    "COLOR_SLICE_GLOBAL_PARAM_KEYS",
    "normalize_color_slice_name",
    "_encode_color_slice_centers",
    "_decode_color_slice_centers",
    "_encode_color_slice_controls",
    "_decode_color_slice_controls",
    "_color_slice_raw_param_entry",
    "_color_slice_payloads_from_params",
    "_color_slice_graph_preservation_signature",
    "_color_slice_preservation_comparison_signature",
    "_inject_color_slice_raw_entries_into_proto",
    "_inject_color_slice_into_proto",
    "write_color_slice",
)
