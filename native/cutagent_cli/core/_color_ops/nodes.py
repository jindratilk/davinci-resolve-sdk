from __future__ import annotations

import os
from typing import Any, Dict, Optional

from ...errors import APICallFailed, ValidationError
from ...policy import require_api_method


def _validate_node_stack_layer_index(node_stack_layer_index: int) -> int:
    if isinstance(node_stack_layer_index, bool) or not isinstance(node_stack_layer_index, int) or node_stack_layer_index < 1:
        raise ValidationError(
            "Node-stack layer index must be a positive integer.",
            details={"node_stack_layer_index": node_stack_layer_index, "minimum": 1},
            recoverability="not_applicable",
        )
    return node_stack_layer_index


def _get_node_graph(conn, clip_name: Optional[str], *, node_stack_layer_index: int = 1, ops_module):
    layer_index = _validate_node_stack_layer_index(node_stack_layer_index)
    item = ops_module.resolve_item(conn, clip_name)
    getter = require_api_method(
        item,
        "GetNodeGraph",
        capability_id="color.node_graph_ops",
        runtime_object="timeline_item",
    )
    graph = getter() if layer_index == 1 else getter(layer_index)
    if not graph:
        raise APICallFailed(
            "No node graph available for the requested node-stack layer.",
            details={"clip": clip_name, "node_stack_layer_index": layer_index},
        )
    return graph


def get_num_nodes(conn, clip_name: Optional[str], *, node_stack_layer_index: int = 1, ops_module) -> int:
    graph = _get_node_graph(conn, clip_name, node_stack_layer_index=node_stack_layer_index, ops_module=ops_module)
    try:
        return int(graph.GetNumNodes()) if hasattr(graph, "GetNumNodes") else 0
    except Exception:
        return 0


def _validate_node_index_for_graph(graph, clip_name: Optional[str], node_index: int) -> int:
    if node_index < 1:
        raise ValidationError(
            "Node index must be a positive integer.",
            details={"clip": clip_name, "node_index": node_index, "minimum": 1},
            recoverability="not_applicable",
        )
    try:
        node_count = int(graph.GetNumNodes()) if hasattr(graph, "GetNumNodes") else 0
    except Exception:
        node_count = 0
    if node_count and node_index > node_count:
        raise ValidationError(
            "Node index is out of range.",
            details={"clip": clip_name, "node_index": node_index, "node_count": node_count},
            recoverability="not_applicable",
        )
    return node_count


def validate_node_index(conn, clip_name: Optional[str], node_index: int, *, node_stack_layer_index: int = 1, ops_module) -> int:
    graph = _get_node_graph(conn, clip_name, node_stack_layer_index=node_stack_layer_index, ops_module=ops_module)
    return _validate_node_index_for_graph(graph, clip_name, node_index)


def set_node_lut(conn, clip_name: Optional[str], node_index: int, lut_path: str, *, node_stack_layer_index: int = 1, ops_module) -> bool:
    graph = _get_node_graph(conn, clip_name, node_stack_layer_index=node_stack_layer_index, ops_module=ops_module)
    _validate_node_index_for_graph(graph, clip_name, node_index)
    setter = require_api_method(
        graph,
        "SetLUT",
        capability_id="color.node_graph_ops",
        runtime_object="node_graph",
    )
    getter = getattr(graph, "GetLUT", None)
    try:
        applied_lut_path, lut_info = ops_module._set_lut_with_candidates(conn, setter, node_index, lut_path, getter=getter)
    except APICallFailed as exc:
        raise APICallFailed(
            "Failed to set node LUT.",
            details={"clip": clip_name, "node_index": node_index, "lut_path": lut_path, **exc.details},
        ) from exc

    if callable(getter):
        try:
            readback = getter(node_index)
            if readback not in (None, "") and str(readback) != str(applied_lut_path):
                acceptable = {str(value) for value in lut_info.get("candidates", [])}
                acceptable.update(
                    str(value)
                    for value in [
                        applied_lut_path,
                        lut_path,
                        lut_info.get("installed_lut_key"),
                        lut_info.get("installed_lut_path"),
                        lut_info.get("local_path"),
                    ]
                    if value
                )
                readback_norm = ops_module._normalize_lut_key(str(readback))
                acceptable_norm = {ops_module._normalize_lut_key(value) for value in acceptable}
                acceptable_names = {os.path.basename(value) for value in acceptable_norm}
                if readback_norm not in acceptable_norm and os.path.basename(readback_norm) not in acceptable_names:
                    raise APICallFailed(
                        "Node LUT readback did not match the requested LUT.",
                        details={
                            "clip": clip_name,
                            "node_index": node_index,
                            "lut_path": lut_path,
                            "applied_lut_path": applied_lut_path,
                            "readback_lut_path": readback,
                            **lut_info,
                        },
                    )
        except APICallFailed:
            raise
        except Exception:
            pass

    if applied_lut_path:
        return True
    raise APICallFailed(
        "Failed to set node LUT.",
        details={"clip": clip_name, "node_index": node_index, "lut_path": lut_path},
    )


def get_node_lut(conn, clip_name: Optional[str], node_index: int, *, node_stack_layer_index: int = 1, ops_module) -> str:
    graph = _get_node_graph(conn, clip_name, node_stack_layer_index=node_stack_layer_index, ops_module=ops_module)
    _validate_node_index_for_graph(graph, clip_name, node_index)
    getter = require_api_method(
        graph,
        "GetLUT",
        capability_id="color.node_graph_ops",
        runtime_object="node_graph",
    )
    lut = getter(node_index)
    return str(lut) if lut is not None else ""


def set_node_cache_mode(conn, clip_name: Optional[str], node_index: int, cache_value: int, *, node_stack_layer_index: int = 1, ops_module) -> bool:
    if cache_value not in (-1, 0, 1):
        raise ValidationError(
            "Invalid cache mode.",
            details={"cache_value": cache_value, "allowed": [-1, 0, 1]},
        )
    graph = _get_node_graph(conn, clip_name, node_stack_layer_index=node_stack_layer_index, ops_module=ops_module)
    _validate_node_index_for_graph(graph, clip_name, node_index)
    setter = require_api_method(
        graph,
        "SetNodeCacheMode",
        capability_id="color.node_graph_ops",
        runtime_object="node_graph",
    )
    result = setter(node_index, cache_value)
    if result:
        return True
    raise APICallFailed(
        "Failed to set node cache mode.",
        details={"clip": clip_name, "node_index": node_index, "cache_value": cache_value},
    )


def get_node_cache_mode(conn, clip_name: Optional[str], node_index: int, *, node_stack_layer_index: int = 1, ops_module) -> Dict[str, Any]:
    graph = _get_node_graph(conn, clip_name, node_stack_layer_index=node_stack_layer_index, ops_module=ops_module)
    _validate_node_index_for_graph(graph, clip_name, node_index)
    getter = require_api_method(
        graph,
        "GetNodeCacheMode",
        capability_id="color.node_graph_ops",
        runtime_object="node_graph",
    )
    mode = getter(node_index)
    names = {-1: "Auto", 0: "Disabled", 1: "Enabled"}
    return {"cache_mode": mode, "mode_name": names.get(mode, "Unknown")}


def get_node_label(conn, clip_name: Optional[str], node_index: int, *, node_stack_layer_index: int = 1, ops_module) -> str:
    graph = _get_node_graph(conn, clip_name, node_stack_layer_index=node_stack_layer_index, ops_module=ops_module)
    _validate_node_index_for_graph(graph, clip_name, node_index)
    getter = require_api_method(
        graph,
        "GetNodeLabel",
        capability_id="color.node_graph_ops",
        runtime_object="node_graph",
    )
    label = getter(node_index)
    return str(label) if label is not None else ""


def set_node_label(conn, clip_name: Optional[str], node_index: int, label: str, *, node_stack_layer_index: int = 1, ops_module) -> bool:
    graph = _get_node_graph(conn, clip_name, node_stack_layer_index=node_stack_layer_index, ops_module=ops_module)
    _validate_node_index_for_graph(graph, clip_name, node_index)
    setter = require_api_method(
        graph,
        "SetNodeLabel",
        capability_id="color.node_graph_ops",
        runtime_object="node_graph",
    )
    normalized_label = str(label)
    result = setter(node_index, normalized_label)
    if result is False:
        raise APICallFailed(
            "Failed to set node label.",
            details={"clip": clip_name, "node_index": node_index, "label": normalized_label},
        )
    getter = getattr(graph, "GetNodeLabel", None)
    if callable(getter):
        try:
            readback = getter(node_index)
        except Exception:
            readback = None
        if readback is not None and str(readback) != normalized_label:
            raise APICallFailed(
                "Node label readback did not match requested label.",
                details={
                    "clip": clip_name,
                    "node_index": node_index,
                    "requested_label": normalized_label,
                    "actual_label": str(readback),
                },
            )
    return True


def get_tools_in_node(conn, clip_name: Optional[str], node_index: int, *, node_stack_layer_index: int = 1, ops_module) -> list[str]:
    graph = _get_node_graph(conn, clip_name, node_stack_layer_index=node_stack_layer_index, ops_module=ops_module)
    _validate_node_index_for_graph(graph, clip_name, node_index)
    getter = require_api_method(
        graph,
        "GetToolsInNode",
        capability_id="color.node_graph_ops",
        runtime_object="node_graph",
    )
    tools = getter(node_index)
    if not tools:
        return []
    if isinstance(tools, list):
        return [str(t) for t in tools]
    return [str(tools)]


def set_node_enabled(conn, clip_name: Optional[str], node_index: int, is_enabled: bool, *, node_stack_layer_index: int = 1, ops_module) -> bool:
    graph = _get_node_graph(conn, clip_name, node_stack_layer_index=node_stack_layer_index, ops_module=ops_module)
    _validate_node_index_for_graph(graph, clip_name, node_index)
    setter = require_api_method(
        graph,
        "SetNodeEnabled",
        capability_id="color.node_graph_ops",
        runtime_object="node_graph",
    )
    result = setter(node_index, bool(is_enabled))
    if result:
        return True
    raise APICallFailed(
        "Failed to set node enabled state.",
        details={"clip": clip_name, "node_index": node_index, "is_enabled": bool(is_enabled)},
    )


def apply_grade_from_drx(conn, clip_name: Optional[str], drx_path: str, grade_mode: int = 0, *, node_stack_layer_index: int = 1, ops_module) -> bool:
    graph = _get_node_graph(conn, clip_name, node_stack_layer_index=node_stack_layer_index, ops_module=ops_module)
    applier = require_api_method(
        graph,
        "ApplyGradeFromDRX",
        capability_id="color.node_graph_ops",
        runtime_object="node_graph",
    )
    result = applier(drx_path, grade_mode)
    if result:
        return True
    raise APICallFailed(
        "Failed to apply grade from DRX.",
        details={"clip": clip_name, "drx_path": drx_path, "grade_mode": grade_mode},
    )


def _node_graph_snapshot(graph) -> Dict[str, Any]:
    try:
        node_count = int(graph.GetNumNodes()) if hasattr(graph, "GetNumNodes") else 0
    except Exception:
        node_count = 0

    nodes: list[dict[str, Any]] = []
    for index in range(1, node_count + 1):
        row: dict[str, Any] = {"index": index}
        for key, method in (
            ("label", "GetNodeLabel"),
            ("lut", "GetLUT"),
            ("tools", "GetToolsInNode"),
            ("cache_mode", "GetNodeCacheMode"),
        ):
            getter = getattr(graph, method, None)
            if not callable(getter):
                continue
            try:
                value = getter(index)
            except Exception:
                continue
            if key == "tools":
                if isinstance(value, list):
                    row[key] = [str(item) for item in value]
                elif value:
                    row[key] = [str(value)]
                else:
                    row[key] = []
            else:
                row[key] = value
        nodes.append(row)
    return {"node_count": node_count, "nodes": nodes}


def _node_graph_changes(before: Dict[str, Any], after: Dict[str, Any]) -> Dict[str, Any]:
    before_nodes = {row.get("index"): row for row in before.get("nodes", []) if isinstance(row, dict)}
    after_nodes = {row.get("index"): row for row in after.get("nodes", []) if isinstance(row, dict)}
    changed_nodes = sorted(
        index
        for index in set(before_nodes).union(after_nodes)
        if before_nodes.get(index) != after_nodes.get(index)
    )
    return {
        "node_count_changed": before.get("node_count") != after.get("node_count"),
        "changed_nodes": changed_nodes,
    }


def apply_arri_cdl_lut(conn, clip_name: Optional[str], *, node_stack_layer_index: int = 1, ops_module) -> Dict[str, Any]:
    graph = _get_node_graph(conn, clip_name, node_stack_layer_index=node_stack_layer_index, ops_module=ops_module)
    applier = require_api_method(
        graph,
        "ApplyArriCdlLut",
        capability_id="color.node_graph_ops",
        runtime_object="node_graph",
    )
    before = _node_graph_snapshot(graph)
    result = applier()
    after = _node_graph_snapshot(graph)
    changes = _node_graph_changes(before, after)
    changed = bool(changes["node_count_changed"] or changes["changed_nodes"])
    if result:
        return {
            "clip": clip_name,
            "applied": True,
            "verified": changed,
            "verification_method": "node_graph_snapshot",
            "before": before,
            "after": after,
            "changes": changes,
            "note": (
                "ARRI CDL/LUT helper produced an observable node graph change."
                if changed
                else "DaVinci Resolve reported success, but the node graph was unchanged; the source clip may not carry ARRI CDL/LUT metadata exposed to the helper."
            ),
        }
    raise APICallFailed("Failed to apply ARRI CDL LUT.", details={"clip": clip_name})


def reset_all_grades(conn, clip_name: Optional[str], *, node_stack_layer_index: int = 1, ops_module) -> bool:
    graph = _get_node_graph(conn, clip_name, node_stack_layer_index=node_stack_layer_index, ops_module=ops_module)
    resetter = require_api_method(
        graph,
        "ResetAllGrades",
        capability_id="color.node_graph_ops",
        runtime_object="node_graph",
    )
    result = resetter()
    if result:
        return True
    raise APICallFailed("Failed to reset all grades.", details={"clip": clip_name})


def copy_grade(conn, source_name: str, target_names: list[str], *, ops_module) -> list[str]:
    src_item = ops_module.resolve_item(conn, source_name)
    target_items = []
    resolved_names = []

    for target_name in target_names:
        if target_name:
            try:
                tgt_item = ops_module.resolve_item(conn, target_name)
                target_items.append(tgt_item)
                resolved_names.append(target_name)
            except Exception:
                pass

    if not target_items:
        raise APICallFailed("No valid target clips found.")

    try:
        result = src_item.CopyGrades(target_items)
        if result:
            return resolved_names
    except AttributeError:
        pass

    success_list = []
    for tgt_item, name in zip(target_items, resolved_names):
        try:
            tgt_item.ApplyGrade(src_item)
            success_list.append(name)
        except Exception:
            pass

    return success_list


def apply_grade_from_file(
    conn,
    clip_name: Optional[str],
    path: str,
    mode: int = 0,
    *,
    node_stack_layer_index: int = 1,
    ops_module,
) -> bool:
    item = ops_module.resolve_item(conn, clip_name)
    timeline_attempt: dict[str, Any] | None = None
    apply_grade = getattr(conn.timeline, "ApplyGradeFromDRX", None)
    if callable(apply_grade):
        try:
            result = apply_grade(path, mode, [item])
            timeline_attempt = {
                "runtime_object": "timeline",
                "api_method": "ApplyGradeFromDRX",
                "api_result": result,
            }
            if result:
                return True
        except TypeError as exc:
            timeline_attempt = {
                "runtime_object": "timeline",
                "api_method": "ApplyGradeFromDRX",
                "exception_type": exc.__class__.__name__,
                "exception": str(exc),
            }

    graph = _get_node_graph(conn, clip_name, node_stack_layer_index=node_stack_layer_index, ops_module=ops_module)
    graph_apply = require_api_method(
        graph,
        "ApplyGradeFromDRX",
        capability_id="color.grade_apply_drx",
        runtime_object="node_graph",
    )
    result = graph_apply(path, mode)
    if result:
        return True

    raise APICallFailed(
        f"ApplyGradeFromDRX failed for: {path}",
        details={
            "clip": clip_name,
            "path": path,
            "mode": mode,
            "runtime_object": "node_graph",
            "api_method": "ApplyGradeFromDRX",
            "api_result": result,
            "timeline_attempt": timeline_attempt,
        },
    )
