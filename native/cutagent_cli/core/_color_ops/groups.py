from __future__ import annotations

from typing import Any, Dict, Optional

from ...errors import APICallFailed
from ...policy import require_api_method


def _get_color_group_obj(conn, group_name: str):
    getter = require_api_method(
        conn.project,
        "GetColorGroupsList",
        capability_id="color.color_group_management",
        runtime_object="project",
    )
    groups = getter() or []
    for group in groups:
        try:
            if group.GetName() == group_name:
                return group
        except Exception:
            continue
    raise APICallFailed(f"Color group '{group_name}' not found.")


def list_color_groups(conn) -> list[Dict[str, Any]]:
    getter = require_api_method(
        conn.project,
        "GetColorGroupsList",
        capability_id="color.color_group_management",
        runtime_object="project",
    )
    groups = getter() or []
    rows: list[Dict[str, Any]] = []
    for i, group in enumerate(groups, 1):
        name = ""
        try:
            name = group.GetName()
        except Exception:
            name = f"Group {i}"
        rows.append({"index": i, "name": str(name)})
    return rows


def add_color_group(conn, group_name: str) -> bool:
    adder = require_api_method(
        conn.project,
        "AddColorGroup",
        capability_id="color.color_group_management",
        runtime_object="project",
    )
    result = adder(group_name)
    if result:
        return True
    raise APICallFailed("Failed to add color group.", details={"group_name": group_name})


def delete_color_group(conn, group_name: str, *, ops_module) -> bool:
    group = ops_module._get_color_group_obj(conn, group_name)
    deleter = require_api_method(
        conn.project,
        "DeleteColorGroup",
        capability_id="color.color_group_management",
        runtime_object="project",
    )
    result = deleter(group)
    if result:
        return True
    raise APICallFailed("Failed to delete color group.", details={"group_name": group_name})


def get_color_group(conn, clip_name: Optional[str], *, ops_module) -> Dict[str, Any]:
    item = ops_module.resolve_item(conn, clip_name)
    getter = require_api_method(
        item,
        "GetColorGroup",
        capability_id="color.color_group_management",
        runtime_object="timeline_item",
    )
    group = getter()
    if not group:
        return {"group_name": None}
    name = group.GetName() if hasattr(group, "GetName") else str(group)
    return {"group_name": name}


def assign_to_color_group(conn, clip_name: Optional[str], group_name: str, *, ops_module) -> bool:
    item = ops_module.resolve_item(conn, clip_name)
    group = ops_module._get_color_group_obj(conn, group_name)
    assigner = require_api_method(
        item,
        "AssignToColorGroup",
        capability_id="color.color_group_management",
        runtime_object="timeline_item",
    )
    result = assigner(group)
    if result:
        return True
    raise APICallFailed(
        "Failed to assign timeline item to color group.",
        details={"clip": clip_name, "group_name": group_name},
    )


def remove_from_color_group(conn, clip_name: Optional[str], *, ops_module) -> bool:
    item = ops_module.resolve_item(conn, clip_name)
    remover = require_api_method(
        item,
        "RemoveFromColorGroup",
        capability_id="color.color_group_management",
        runtime_object="timeline_item",
    )
    result = remover()
    if result:
        return True
    raise APICallFailed("Failed to remove timeline item from color group.", details={"clip": clip_name})


def get_name(conn, group_name: str, *, ops_module) -> str:
    group = ops_module._get_color_group_obj(conn, group_name)
    getter = require_api_method(
        group,
        "GetName",
        capability_id="color.color_group_management",
        runtime_object="color_group",
    )
    result = getter()
    return str(result) if result is not None else ""


def set_name(conn, group_name: str, new_name: str, *, ops_module) -> bool:
    group = ops_module._get_color_group_obj(conn, group_name)
    setter = require_api_method(
        group,
        "SetName",
        capability_id="color.color_group_management",
        runtime_object="color_group",
    )
    result = setter(new_name)
    if result:
        return True
    raise APICallFailed(
        "Failed to rename color group.",
        details={"group_name": group_name, "new_name": new_name},
    )


def get_clips_in_timeline(conn, group_name: str, *, ops_module) -> list[Dict[str, Any]]:
    group = ops_module._get_color_group_obj(conn, group_name)
    getter = require_api_method(
        group,
        "GetClipsInTimeline",
        capability_id="color.color_group_management",
        runtime_object="color_group",
    )
    clips = getter() or []
    rows: list[Dict[str, Any]] = []
    for i, clip in enumerate(clips, 1):
        entry: Dict[str, Any] = {
            "index": i,
            "name": clip.GetName() if hasattr(clip, "GetName") else f"Clip {i}",
        }
        if hasattr(clip, "GetUniqueId"):
            try:
                entry["unique_id"] = clip.GetUniqueId()
            except Exception:
                pass
        rows.append(entry)
    return rows


def _color_group_graph_summary(group_name: str, graph_type: str, graph: Any) -> Dict[str, Any]:
    num_nodes = None
    if graph and hasattr(graph, "GetNumNodes"):
        try:
            num_nodes = graph.GetNumNodes()
        except Exception:
            num_nodes = None
    return {
        "group": group_name,
        "graph_type": graph_type,
        "has_graph": bool(graph),
        "num_nodes": num_nodes,
    }


def get_pre_clip_node_graph(conn, group_name: str, *, ops_module) -> Dict[str, Any]:
    group = ops_module._get_color_group_obj(conn, group_name)
    getter = require_api_method(
        group,
        "GetPreClipNodeGraph",
        capability_id="color.color_group_management",
        runtime_object="color_group",
    )
    graph = getter()
    if not graph:
        raise APICallFailed("No pre-clip node graph available.", details={"group_name": group_name})
    return ops_module._color_group_graph_summary(group_name, "pre_clip", graph)


def get_post_clip_node_graph(conn, group_name: str, *, ops_module) -> Dict[str, Any]:
    group = ops_module._get_color_group_obj(conn, group_name)
    getter = require_api_method(
        group,
        "GetPostClipNodeGraph",
        capability_id="color.color_group_management",
        runtime_object="color_group",
    )
    graph = getter()
    if not graph:
        raise APICallFailed("No post-clip node graph available.", details={"group_name": group_name})
    return ops_module._color_group_graph_summary(group_name, "post_clip", graph)
