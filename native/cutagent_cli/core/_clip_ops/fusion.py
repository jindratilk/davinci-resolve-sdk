from __future__ import annotations

from typing import Any, Optional

from ...errors import APICallFailed, ValidationError
from ...policy import require_api_method
from ...utils.time_ref import parse_source_frame
from .. import fusion_common


def _tool_values(tool_list) -> list[object]:
    if isinstance(tool_list, dict):
        return list(tool_list.values())
    if isinstance(tool_list, (list, tuple)):
        return list(tool_list)
    return [] if tool_list is None else [tool_list]


def _same_fusion_tool(left, right) -> bool:
    if left is right:
        return True
    try:
        left_attrs = left.GetAttrs() or {}
        right_attrs = right.GetAttrs() or {}
        left_name = left_attrs.get("TOOLS_Name") or left_attrs.get("TOOLS_NameDisp")
        right_name = right_attrs.get("TOOLS_Name") or right_attrs.get("TOOLS_NameDisp")
        return bool(left_name and right_name and left_name == right_name)
    except Exception:
        return False


def _fusion_input(tool, input_id: str = "Input"):
    getter = getattr(tool, "GetInputList", None)
    fallback = None
    if callable(getter):
        for input_obj in _tool_values(getter() or {}):
            fallback = fallback or input_obj
            try:
                attrs = input_obj.GetAttrs() or {}
                if attrs.get("INPS_ID") == input_id:
                    return input_obj
            except Exception:
                continue
    direct = getattr(tool, input_id, None)
    return fallback or (None if callable(direct) else direct)


def _fusion_output(tool, output_id: str = "Output"):
    getter = getattr(tool, "GetOutputList", None)
    fallback = None
    if callable(getter):
        for output_obj in _tool_values(getter() or {}):
            fallback = fallback or output_obj
            try:
                attrs = output_obj.GetAttrs() or {}
                if attrs.get("OUTS_ID") == output_id:
                    return output_obj
            except Exception:
                continue
    direct = getattr(tool, output_id, None)
    return fallback or (None if callable(direct) else direct)


def _find_or_create_transform(comp) -> object:
    tool_list = comp.GetToolList(False) or {}
    for tool in _tool_values(tool_list):
        try:
            attrs = tool.GetAttrs() if hasattr(tool, "GetAttrs") else {}
            if attrs.get("TOOLS_RegID") == "Transform":
                return tool
        except Exception:
            continue
    if not hasattr(comp, "AddTool"):
        raise APICallFailed("Fusion composition cannot create tools (missing AddTool).")
    tool = comp.AddTool("Transform", -32768, -32768)
    if not tool:
        raise APICallFailed("Failed to create Transform tool in Fusion composition.")
    return tool


def _connect_transform_inline(comp, transform) -> bool:
    media_in = None
    media_out = None
    for tool in _tool_values(comp.GetToolList(False) or {}):
        try:
            attrs = tool.GetAttrs() if hasattr(tool, "GetAttrs") else {}
            tool_type = attrs.get("TOOLS_RegID") if isinstance(attrs, dict) else None
        except Exception:
            continue
        if tool_type == "MediaIn" and media_in is None:
            media_in = tool
        elif tool_type == "MediaOut" and media_out is None:
            media_out = tool

    if media_out is None:
        raise APICallFailed("Dynamic zoom Fusion composition has no MediaOut tool.")

    media_out_input = _fusion_input(media_out)
    transform_input = _fusion_input(transform)
    transform_output = _fusion_output(transform)
    if media_out_input is None or transform_input is None or transform_output is None:
        raise APICallFailed("Dynamic zoom could not access Fusion image ports.")

    source = media_in
    connected_output_getter = getattr(media_out_input, "GetConnectedOutput", None)
    if callable(connected_output_getter):
        connected_output = connected_output_getter()
        connected_tool_getter = getattr(connected_output, "GetTool", None) if connected_output else None
        connected_tool = connected_tool_getter() if callable(connected_tool_getter) else None
        if connected_tool is not None and _same_fusion_tool(connected_tool, transform):
            return True
        if connected_tool is not None:
            source = connected_tool
    source_output = _fusion_output(source) if source is not None else None
    if source_output is None:
        raise APICallFailed("Dynamic zoom could not find the Fusion image source.")

    if transform_input.ConnectTo(source_output) is False or media_out_input.ConnectTo(transform_output) is False:
        raise APICallFailed("Dynamic zoom failed to connect its Transform tool inline.")
    return True


def _resolve_fusion_clip(
    conn,
    clip_name: Optional[str],
    *,
    track: int | None = None,
    record_frame: str | int | None = None,
    ops_module,
):
    if track is not None or record_frame is not None:
        return ops_module.cutagent_clip_by_selector(conn, clip_name, track=track, record_frame=record_frame)
    return ops_module.cutagent_clip(conn, clip_name)


def apply_dynamic_zoom(
    conn,
    clip_name: Optional[str],
    *,
    start: str,
    end: str,
    source_in: Optional[str] = None,
    source_out: Optional[str] = None,
    ease: str = "linear",
    ops_module,
) -> dict[str, Any]:
    item = ops_module.cutagent_clip(conn, clip_name)
    clip_source_start = int(item.GetStart()) if hasattr(item, "GetStart") else 0
    clip_source_end = int(item.GetEnd()) if hasattr(item, "GetEnd") else clip_source_start + 1
    kf_in = parse_source_frame(source_in, conn.fps) if source_in else clip_source_start
    kf_out = parse_source_frame(source_out, conn.fps) if source_out else clip_source_end
    if kf_out <= kf_in:
        raise ValidationError(
            "Dynamic zoom source-out must be greater than source-in.",
            details={"source_in": source_in, "source_out": source_out, "in_frame": kf_in, "out_frame": kf_out},
            recoverability="not_applicable",
        )
    sx, sy, sz = ops_module._parse_zoom_tuple(start)
    ex, ey, ez = ops_module._parse_zoom_tuple(end)

    count = item.GetFusionCompCount() if hasattr(item, "GetFusionCompCount") else 0
    if not count:
        add_comp = getattr(item, "AddFusionComp", None)
        if not callable(add_comp):
            raise APICallFailed("Dynamic zoom requires AddFusionComp support on timeline item.")
        add_result = add_comp()
        if add_result is False:
            raise APICallFailed("Failed to add Fusion composition for dynamic zoom.")
        count = item.GetFusionCompCount() if hasattr(item, "GetFusionCompCount") else 1

    comp = item.GetFusionCompByIndex(1)
    if not comp:
        raise APICallFailed("Could not access Fusion composition for clip.")

    transform = ops_module._find_or_create_transform(comp)
    _connect_transform_inline(comp, transform)
    writes = (
        transform.SetInput("Center", {1: sx, 2: sy}, kf_in),
        transform.SetInput("Size", sz, kf_in),
        transform.SetInput("Center", {1: ex, 2: ey}, kf_out),
        transform.SetInput("Size", ez, kf_out),
    )
    if any(result is False for result in writes):
        raise APICallFailed("Dynamic zoom failed to write Fusion keyframes.")

    ease_value = {"linear": 0, "in": 1, "out": 2, "inout": 3}.get(ease, 0)
    for key in ("SplineMode", "Ease", "KeyframeEase"):
        try:
            transform.SetInput(key, ease_value)
            break
        except Exception:
            continue

    return {
        "clip": clip_name or (item.GetName() if hasattr(item, "GetName") else None),
        "source_in_frame": kf_in,
        "source_out_frame": kf_out,
        "start": {"x": sx, "y": sy, "zoom": sz},
        "end": {"x": ex, "y": ey, "zoom": ez},
        "ease": ease,
    }


def list_fusion_comps(
    conn,
    name: Optional[str],
    *,
    track: int | None = None,
    record_frame: str | int | None = None,
    ops_module,
) -> list[dict[str, Any]]:
    item = _resolve_fusion_clip(conn, name, track=track, record_frame=record_frame, ops_module=ops_module)

    count = 0
    try:
        count = item.GetFusionCompCount()
    except Exception:
        pass

    rows = []
    for i in range(1, (count or 0) + 1):
        comp_name = f"Composition {i}"
        try:
            comp = item.GetFusionCompByIndex(i)
            if comp:
                comp_name = comp.GetAttrs().get("COMPS_Name", comp_name) if hasattr(comp, "GetAttrs") else comp_name
        except Exception:
            pass
        rows.append({"index": i, "name": comp_name})

    return rows


def add_fusion_comp(
    conn,
    name: Optional[str],
    *,
    track: int | None = None,
    record_frame: str | int | None = None,
    ops_module,
) -> bool:
    item = _resolve_fusion_clip(conn, name, track=track, record_frame=record_frame, ops_module=ops_module)
    try:
        composition_count = int(item.GetFusionCompCount() or 0)
    except Exception:
        composition_count = -1
    api_error: Exception | None = None
    try:
        result = item.AddFusionComp()
    except Exception as exc:
        result = False
        api_error = exc
    try:
        composition_count_after = int(item.GetFusionCompCount() or 0)
    except Exception:
        composition_count_after = -1
    if composition_count >= 0 and composition_count_after == composition_count + 1:
        return True
    if result:
        raise APICallFailed(
            "AddFusionComp did not produce exact composition-count readback.",
            details={"composition_count_before": composition_count, "composition_count_after": composition_count_after},
        )
    if composition_count_after != composition_count:
        raise APICallFailed(
            "AddFusionComp returned an uncertain native result; inspect the clip before retrying.",
            details={
                "composition_count_before": composition_count,
                "composition_count_after": composition_count_after,
                "api_error": str(api_error) if api_error is not None else None,
            },
        )

    # DaVinci Resolve can return false/null for every Fusion UI-write method
    # while the project itself remains available to the supported Disk-project
    # transaction route. The fallback is intentionally limited to attaching the
    # first composition to one exact durable video item; existing compositions
    # retain the official API path rather than risking an ambiguous DB append.
    if composition_count == 0:
        from .. import db_timeline_selection, fusion_composition_db

        item_ref = db_timeline_selection.resolve_video_group(
            conn,
            clip_name=name,
            track=track,
            at=str(record_frame) if record_frame is not None else None,
        )["video"]
        fusion_composition_db.attach_fusion_composition_via_project_db(conn, item_ref=item_ref)
        return True
    raise APICallFailed(
        "Failed to add Fusion composition.",
        details={
            "composition_count_before": composition_count,
            "composition_count_after": composition_count_after,
            "api_error": str(api_error) if api_error is not None else None,
            "db_fallback": "requires_zero_existing_compositions",
        },
    )


def _fusion_comp_count(item) -> Optional[int]:
    try:
        return int(item.GetFusionCompCount())
    except Exception:
        return None


def _fusion_comp_name_list(item) -> list[str]:
    getter = getattr(item, "GetFusionCompNameList", None)
    if not callable(getter):
        return []

    try:
        names = getter() or []
    except Exception:
        return []

    if isinstance(names, dict):
        def _sort_key(value):
            try:
                return int(value)
            except Exception:
                return str(value)

        iterable = [names[key] for key in sorted(names.keys(), key=_sort_key)]
    elif isinstance(names, (list, tuple)):
        iterable = names
    else:
        iterable = [names]

    result: list[str] = []
    for name in iterable:
        try:
            text = str(name).strip()
        except Exception:
            continue
        if text:
            result.append(text)
    return result


def _append_unique(values: list[str], value) -> None:
    try:
        text = str(value).strip()
    except Exception:
        return
    if text and text not in values:
        values.append(text)


_RECREATE_PROPERTY_KEYS = (
    "ZoomX",
    "ZoomY",
    "Pan",
    "Tilt",
    "RotationAngle",
    "AnchorPointX",
    "AnchorPointY",
    "Pitch",
    "Yaw",
    "FlipX",
    "FlipY",
    "CropLeft",
    "CropRight",
    "CropTop",
    "CropBottom",
    "Opacity",
    "CompositeMode",
    "Distortion",
    "DynamicZoomEase",
    "Speed",
    "RetimeProcess",
    "MotionEstimation",
    "Scaling",
    "ResizeFilter",
    "Enabled",
)


def _call_optional(obj: Any, method_name: str, *args) -> Any:
    method = getattr(obj, method_name, None)
    if not callable(method):
        return None
    try:
        return method(*args)
    except Exception:
        return None


def _timeline_item_name(item: Any) -> str | None:
    value = _call_optional(item, "GetName")
    if value in (None, ""):
        return None
    return str(value)


def _timeline_item_unique_id(item: Any) -> str | None:
    for method_name in ("GetUniqueId", "GetUniqueID", "GetId", "GetID"):
        value = _call_optional(item, method_name)
        if value not in (None, ""):
            return str(value)
    return None


def _timeline_item_track(conn: Any, item: Any, *, ops_module) -> tuple[str, int]:
    getter = getattr(item, "GetTrackTypeAndIndex", None)
    if callable(getter):
        try:
            track_type, track_index = getter()
            return str(track_type), int(track_index)
        except Exception:
            pass

    for track_type in ("video", "audio"):
        finder = getattr(ops_module, "_find_track_of_item", None)
        if callable(finder):
            track_index = int(finder(conn, item, track_type) or 0)
        else:
            track_index = 0
            count = int(_call_optional(conn.timeline, "GetTrackCount", track_type) or 0)
            for idx in range(1, count + 1):
                for candidate in _call_optional(conn.timeline, "GetItemListInTrack", track_type, idx) or []:
                    if candidate is item:
                        track_index = idx
                        break
                if track_index:
                    break
        if track_index:
            return track_type, track_index

    raise APICallFailed(
        "Could not resolve timeline track for Fusion composition recreation.",
        details={"clip": _timeline_item_name(item), "unique_id": _timeline_item_unique_id(item)},
    )


def _timeline_item_source_start(item: Any) -> int:
    for method_name in ("GetLeftOffset", "GetSourceStartFrame", "GetSourceStart"):
        value = _call_optional(item, method_name)
        if value is not None:
            return int(value)
    return 0


def _timeline_item_markers(item: Any) -> dict[Any, Any]:
    markers = _call_optional(item, "GetMarkers")
    return markers if isinstance(markers, dict) else {}


def _timeline_item_properties(item: Any) -> dict[str, Any]:
    props = _call_optional(item, "GetProperty")
    if not isinstance(props, dict):
        props = {}
    captured: dict[str, Any] = {}
    for key in _RECREATE_PROPERTY_KEYS:
        value = props.get(key)
        if value is None:
            value = _call_optional(item, "GetProperty", key)
        if value is not None:
            captured[key] = value
    return captured


def _linked_recreate_items(target: Any) -> list[Any]:
    items: list[Any] = []
    seen: set[int] = set()

    def add(item: Any) -> None:
        if item is None:
            return
        ident = id(item)
        if ident not in seen:
            seen.add(ident)
            items.append(item)

    add(target)
    linked_getter = getattr(target, "GetLinkedItems", None)
    if callable(linked_getter):
        try:
            for linked_item in linked_getter() or []:
                add(linked_item)
        except Exception:
            pass
    return items


def _snapshot_timeline_item_for_recreate(conn: Any, item: Any, *, ops_module) -> dict[str, Any]:
    start = int(_call_optional(item, "GetStart"))
    end = int(_call_optional(item, "GetEnd"))
    duration = int(_call_optional(item, "GetDuration") or (end - start))
    if duration <= 0:
        raise APICallFailed(
            "Cannot recreate Fusion composition clip with non-positive duration.",
            details={"clip": _timeline_item_name(item), "start": start, "end": end, "duration": duration},
        )

    media_pool_item = _call_optional(item, "GetMediaPoolItem")
    if not media_pool_item:
        raise APICallFailed(
            "Cannot recreate Fusion composition clip without MediaPoolItem access.",
            details={"clip": _timeline_item_name(item), "start": start, "end": end},
        )

    track_type, track_index = _timeline_item_track(conn, item, ops_module=ops_module)
    source_start = _timeline_item_source_start(item)
    source_end = source_start + duration

    color = _call_optional(item, "GetClipColor")
    flags = _call_optional(item, "GetFlagList") or []

    return {
        "item": item,
        "name": _timeline_item_name(item),
        "unique_id": _timeline_item_unique_id(item),
        "media_pool_item": media_pool_item,
        "track_type": track_type,
        "track_index": int(track_index),
        "media_type": 1 if track_type == "video" else 2 if track_type == "audio" else None,
        "start": start,
        "end": end,
        "duration": duration,
        "source_start": source_start,
        "source_end": source_end,
        "properties": _timeline_item_properties(item),
        "clip_color": color if color not in (None, "") else None,
        "flags": list(flags) if isinstance(flags, (list, tuple)) else [],
        "markers": _timeline_item_markers(item),
    }


def _append_recreated_timeline_item(conn: Any, snapshot: dict[str, Any]) -> Any:
    clip_info = {
        "mediaPoolItem": snapshot["media_pool_item"],
        "startFrame": int(snapshot["source_start"]),
        "endFrame": int(snapshot["source_end"]),
        "recordFrame": int(snapshot["start"]),
        "trackIndex": int(snapshot["track_index"]),
    }
    if snapshot.get("media_type") is not None:
        clip_info["mediaType"] = int(snapshot["media_type"])
    else:
        clip_info["trackType"] = snapshot["track_type"]

    result = conn.media_pool.AppendToTimeline([clip_info])
    if not result:
        raise APICallFailed(
            "AppendToTimeline failed while recreating clip without its last Fusion composition.",
            details={
                "clip": snapshot.get("name"),
                "track_type": snapshot.get("track_type"),
                "track_index": snapshot.get("track_index"),
                "start": snapshot.get("start"),
                "end": snapshot.get("end"),
                "source_start": snapshot.get("source_start"),
                "source_end": snapshot.get("source_end"),
            },
        )
    if isinstance(result, list) and result:
        return result[0]
    return result


def _restore_recreated_timeline_item_state(item: Any, snapshot: dict[str, Any]) -> dict[str, Any]:
    restored = {"properties": [], "property_errors": [], "clip_color": False, "flags": 0, "markers": 0, "name": False}

    setter = getattr(item, "SetProperty", None)
    if callable(setter):
        for key, value in snapshot.get("properties", {}).items():
            try:
                if setter(key, value) is not False:
                    restored["properties"].append(key)
            except Exception as exc:
                restored["property_errors"].append({"key": key, "error": str(exc)})

    if snapshot.get("clip_color") is not None:
        color_setter = getattr(item, "SetClipColor", None)
        if callable(color_setter):
            try:
                restored["clip_color"] = color_setter(snapshot["clip_color"]) is not False
            except Exception:
                restored["clip_color"] = False

    flag_adder = getattr(item, "AddFlag", None)
    if callable(flag_adder):
        for color in snapshot.get("flags", []):
            try:
                if flag_adder(color) is not False:
                    restored["flags"] += 1
            except Exception:
                continue

    marker_adder = getattr(item, "AddMarker", None)
    if callable(marker_adder):
        for frame, marker in snapshot.get("markers", {}).items():
            if not isinstance(marker, dict):
                continue
            color = marker.get("color") or marker.get("Color") or "Blue"
            name = marker.get("name") or marker.get("Name") or ""
            note = marker.get("note") or marker.get("Note") or ""
            duration = marker.get("duration") or marker.get("Duration") or 1
            custom_data = marker.get("customData") or marker.get("custom_data")
            try:
                if custom_data is not None:
                    result = marker_adder(frame, color, name, note, duration, custom_data)
                else:
                    result = marker_adder(frame, color, name, note, duration)
                if result is not False:
                    restored["markers"] += 1
            except TypeError:
                try:
                    if marker_adder(frame, color, name, note, duration) is not False:
                        restored["markers"] += 1
                except Exception:
                    continue
            except Exception:
                continue

    if snapshot.get("name"):
        name_setter = getattr(item, "SetName", None)
        if callable(name_setter):
            try:
                restored["name"] = name_setter(snapshot["name"]) is not False
            except Exception:
                restored["name"] = False
    return restored


def _find_recreated_timeline_item(conn: Any, snapshot: dict[str, Any]) -> Any | None:
    track_type = snapshot["track_type"]
    track_index = int(snapshot["track_index"])
    items = _call_optional(conn.timeline, "GetItemListInTrack", track_type, track_index) or []
    for candidate in items:
        try:
            if int(candidate.GetStart()) != int(snapshot["start"]):
                continue
            if int(candidate.GetEnd()) != int(snapshot["end"]):
                continue
        except Exception:
            continue
        candidate_name = _timeline_item_name(candidate)
        if snapshot.get("name") and candidate_name and candidate_name != snapshot["name"]:
            continue
        return candidate
    return None


def _delete_last_fusion_comp_by_recreating_item(conn: Any, item: Any, *, ops_module) -> dict[str, Any]:
    snapshots = [
        _snapshot_timeline_item_for_recreate(conn, current_item, ops_module=ops_module)
        for current_item in _linked_recreate_items(item)
    ]
    deleter = getattr(conn.timeline, "DeleteClips", None)
    if not callable(deleter):
        raise APICallFailed("Timeline.DeleteClips is required to delete the last Fusion composition.")

    try:
        delete_result = deleter([snapshot["item"] for snapshot in snapshots], False)
    except TypeError:
        delete_result = deleter([snapshot["item"] for snapshot in snapshots])
    if delete_result is False:
        raise APICallFailed(
            "DaVinci Resolve rejected timeline item recreation while deleting the last Fusion composition.",
            details={"route": "timeline_item.recreate_without_fusion_comp", "deleted_items": len(snapshots)},
        )

    readback: list[dict[str, Any]] = []
    for snapshot in snapshots:
        appended = _append_recreated_timeline_item(conn, snapshot)
        recreated = _find_recreated_timeline_item(conn, snapshot) or appended
        restored = _restore_recreated_timeline_item_state(recreated, snapshot)
        comp_count = _fusion_comp_count(recreated) if snapshot["item"] is item else None
        readback.append(
            {
                "name": snapshot.get("name"),
                "track_type": snapshot.get("track_type"),
                "track_index": snapshot.get("track_index"),
                "start": snapshot.get("start"),
                "end": snapshot.get("end"),
                "fusion_comp_count": comp_count,
                "restored": restored,
            }
        )

    target_readback = next((row for row in readback if row["fusion_comp_count"] is not None), None)
    if not target_readback or target_readback["fusion_comp_count"] != 0:
        raise APICallFailed(
            "Last Fusion composition recreation did not verify with zero compositions.",
            details={"route": "timeline_item.recreate_without_fusion_comp", "readback": readback},
        )

    return {
        "route": "timeline_item.recreate_without_fusion_comp",
        "deleted": True,
        "recreated_items": len(snapshots),
        "readback": readback,
    }


def delete_fusion_comp(
    conn,
    clip_name: Optional[str],
    index: int,
    *,
    track: int | None = None,
    record_frame: str | int | None = None,
    ops_module,
) -> bool:
    if index < 1:
        raise ValidationError("Fusion composition index must be 1 or greater.", details={"index": index})

    item = _resolve_fusion_clip(conn, clip_name, track=track, record_frame=record_frame, ops_module=ops_module)
    before_count = ops_module._fusion_comp_count(item)
    if before_count is not None and index > before_count:
        raise ValidationError(
            f"Fusion composition index {index} is out of range; clip has {before_count} composition(s).",
            details={"index": index, "count": before_count},
        )
    if index == 1 and before_count == 1:
        _delete_last_fusion_comp_by_recreating_item(conn, item, ops_module=ops_module)
        return True

    result = False

    comp = None
    try:
        comp = item.GetFusionCompByIndex(index)
    except Exception:
        comp = None

    candidate_names: list[str] = []
    name_list = ops_module._fusion_comp_name_list(item)
    if 0 <= index - 1 < len(name_list):
        ops_module._append_unique(candidate_names, name_list[index - 1])

    if comp and hasattr(comp, "GetAttrs"):
        try:
            attrs = comp.GetAttrs() or {}
            comp_name = attrs.get("COMPS_Name")
            if comp_name:
                ops_module._append_unique(candidate_names, comp_name)
        except Exception:
            pass
    ops_module._append_unique(candidate_names, f"Composition {index}")
    ops_module._append_unique(candidate_names, f"Composition{index}")

    deleter_by_name = getattr(item, "DeleteFusionCompByName", None)
    if callable(deleter_by_name):
        loader_by_name = getattr(item, "LoadFusionCompByName", None)
        if before_count and before_count > 1 and callable(loader_by_name):
            alternate_names = [
                name
                for position, name in enumerate(name_list, start=1)
                if position != index
            ]
            for alternate_name in alternate_names:
                try:
                    if loader_by_name(alternate_name):
                        break
                except Exception:
                    continue
        for candidate in candidate_names:
            try:
                result = bool(deleter_by_name(candidate))
            except Exception:
                result = False
            if not result and before_count is not None:
                after_count = ops_module._fusion_comp_count(item)
                result = after_count is not None and after_count < before_count
            if result:
                break

    if not result:
        deleter_by_index = getattr(item, "DeleteFusionComp", None)
        if callable(deleter_by_index):
            try:
                result = bool(deleter_by_index(index))
            except Exception:
                result = False
    if result:
        return True
    raise APICallFailed(f"Failed to delete composition {index}.")


def _fusion_comp_candidate_names(item, index: int, *, ops_module) -> list[str]:
    candidate_names: list[str] = []
    name_list = ops_module._fusion_comp_name_list(item)
    if 0 <= index - 1 < len(name_list):
        ops_module._append_unique(candidate_names, name_list[index - 1])

    comp = None
    try:
        comp = item.GetFusionCompByIndex(index)
    except Exception:
        comp = None

    if comp and hasattr(comp, "GetAttrs"):
        try:
            attrs = comp.GetAttrs() or {}
            comp_name = attrs.get("COMPS_Name")
            if comp_name:
                ops_module._append_unique(candidate_names, comp_name)
        except Exception:
            pass
    ops_module._append_unique(candidate_names, f"Composition {index}")
    ops_module._append_unique(candidate_names, f"Composition{index}")
    return candidate_names


def rename_fusion_comp(
    conn,
    clip_name: Optional[str],
    index: int,
    new_name: str,
    *,
    ops_module,
) -> dict[str, Any]:
    if index < 1:
        raise ValidationError("Fusion composition index must be 1 or greater.", details={"index": index})
    target_name = str(new_name or "").strip()
    if not target_name:
        raise ValidationError(
            "Fusion composition rename requires a non-empty new name.",
            details={"index": index, "new_name": new_name},
        )

    item = ops_module.cutagent_clip(conn, clip_name)
    before_count = ops_module._fusion_comp_count(item)
    if before_count is not None and index > before_count:
        raise ValidationError(
            f"Fusion composition index {index} is out of range; clip has {before_count} composition(s).",
            details={"index": index, "count": before_count},
        )

    before_names = ops_module._fusion_comp_name_list(item)
    candidate_names = ops_module._fusion_comp_candidate_names(item, index)
    if not candidate_names:
        raise APICallFailed(
            f"Could not resolve Fusion composition {index} name before rename.",
            details={"index": index, "clip": clip_name, "names": before_names},
        )
    old_name = candidate_names[0]

    if target_name == old_name:
        return {
            "renamed": False,
            "index": index,
            "old_name": old_name,
            "new_name": target_name,
            "route": "timeline_item.RenameFusionCompByName",
            "reason": "already_named",
        }
    if target_name in before_names:
        raise ValidationError(
            "A Fusion composition with that name already exists on this clip.",
            details={"index": index, "new_name": target_name, "existing_names": before_names},
        )

    renamer = require_api_method(
        item,
        "RenameFusionCompByName",
        capability_id="clip.fusion_comp",
        runtime_object="timeline_item",
    )

    attempted: list[str] = []
    for candidate in candidate_names:
        attempted.append(candidate)
        try:
            result = bool(renamer(candidate, target_name))
        except Exception:
            result = False
        after_names = ops_module._fusion_comp_name_list(item)
        verified = target_name in after_names and candidate not in after_names
        if result or verified:
            return {
                "renamed": True,
                "index": index,
                "old_name": candidate,
                "new_name": target_name,
                "route": "timeline_item.RenameFusionCompByName",
                "verified": verified,
            }

    raise APICallFailed(
        f"Failed to rename composition {index}.",
        details={
            "index": index,
            "new_name": target_name,
            "attempted_old_names": attempted,
            "before_names": before_names,
            "after_names": ops_module._fusion_comp_name_list(item),
        },
    )


def export_fusion_comp(
    conn,
    clip_name: Optional[str],
    index: int,
    path: str,
    *,
    track: int | None = None,
    record_frame: str | int | None = None,
    ops_module,
) -> bool:
    output_path = ops_module.validate_fusion_export_request(index, path)
    item = _resolve_fusion_clip(conn, clip_name, track=track, record_frame=record_frame, ops_module=ops_module)
    count = ops_module._fusion_comp_count(item)
    if count is not None:
        if count <= 0:
            raise APICallFailed(
                "No Fusion composition attached to clip.",
                details={"clip": clip_name, "index": index, "count": count},
            )
        if index > count:
            raise ValidationError(
                f"Fusion composition index {index} is out of range; clip has {count} composition(s).",
                details={"index": index, "count": count},
                recoverability="not_applicable",
            )
    result = item.ExportFusionComp(output_path, index)
    if result:
        return True
    raise APICallFailed("Failed to export composition.")


def import_fusion_comp(
    conn,
    clip_name: Optional[str],
    path: str,
    *,
    track: int | None = None,
    record_frame: str | int | None = None,
    ops_module,
) -> bool:
    item = _resolve_fusion_clip(conn, clip_name, track=track, record_frame=record_frame, ops_module=ops_module)

    if not hasattr(item, "ImportFusionComp"):
        raise APICallFailed("This clip doesn't support ImportFusionComp (may require DaVinci Resolve 20+ Studio).")

    result = item.ImportFusionComp(path)
    if result:
        return True
    raise APICallFailed("ImportFusionComp failed. Check the .setting file format.")


def _get_fusion_comp(item, comp_index: int):
    if comp_index < 1:
        raise ValidationError(
            "Fusion composition index must be 1 or greater.",
            details={"index": comp_index},
            recoverability="not_applicable",
        )
    count = _fusion_comp_count(item)
    if count is not None and (count <= 0 or comp_index > count):
        raise ValidationError(
            f"Fusion composition index {comp_index} is out of range; clip has {count} composition(s).",
            details={"index": comp_index, "count": count},
            recoverability="not_applicable",
        )
    comp = None
    for idx in [comp_index, comp_index - 1]:
        try:
            comp = item.GetFusionCompByIndex(idx)
            if comp:
                break
        except Exception:
            pass
    return comp


def list_fusion_tools(
    conn,
    clip_name: Optional[str],
    comp_index: int = 1,
    *,
    track: int | None = None,
    record_frame: str | int | None = None,
    ops_module,
) -> list[dict[str, Any]]:
    item = _resolve_fusion_clip(conn, clip_name, track=track, record_frame=record_frame, ops_module=ops_module)
    comp = _get_fusion_comp(item, comp_index)

    if not comp:
        raise APICallFailed(f"Cannot get Fusion composition {comp_index}.")

    tool_list = comp.GetToolList() if hasattr(comp, "GetToolList") else {}
    if not tool_list:
        return []

    rows = []
    for table_key, tool in fusion_common.iter_api_items(tool_list):
        tool_name = fusion_common.tool_name(
            tool,
            fallback=table_key if isinstance(table_key, str) else None,
        )
        if tool_name == "Unknown":
            raise APICallFailed(
                "Fusion composition returned a tool without an addressable name.",
                details={"table_key": str(table_key), "required_attribute": "TOOLST_Name"},
            )
        attrs = tool.GetAttrs() if hasattr(tool, "GetAttrs") else {}
        tool_type = attrs.get("TOOLS_RegID", "?") if isinstance(attrs, dict) else "?"
        rows.append({"id": table_key, "name": tool_name, "type": tool_type})

    return rows


def get_fusion_tool_input(
    conn,
    clip_name: Optional[str],
    tool_name: str,
    input_name: str,
    comp_index: int = 1,
    *,
    track: int | None = None,
    record_frame: str | int | None = None,
    ops_module,
) -> Any:
    item = _resolve_fusion_clip(conn, clip_name, track=track, record_frame=record_frame, ops_module=ops_module)
    comp = _get_fusion_comp(item, comp_index)

    if not comp:
        raise APICallFailed("Cannot get Fusion composition.")

    tool = comp.FindTool(tool_name) if hasattr(comp, "FindTool") else None
    if not tool:
        raise APICallFailed(f"Tool '{tool_name}' not found.")

    return tool.GetInput(input_name) if hasattr(tool, "GetInput") else None


def set_fusion_tool_input(
    conn,
    clip_name: Optional[str],
    tool_name: str,
    input_name: str,
    value: str,
    comp_index: int = 1,
    *,
    track: int | None = None,
    record_frame: str | int | None = None,
    ops_module,
) -> None:
    item = _resolve_fusion_clip(conn, clip_name, track=track, record_frame=record_frame, ops_module=ops_module)
    comp = _get_fusion_comp(item, comp_index)

    if not comp:
        raise APICallFailed("Cannot get Fusion composition.")

    tool = comp.FindTool(tool_name) if hasattr(comp, "FindTool") else None
    if not tool:
        raise APICallFailed(f"Tool '{tool_name}' not found.")

    try:
        parsed = float(value)
        if parsed == int(parsed):
            parsed = int(parsed)
        tool.SetInput(input_name, parsed)
    except ValueError:
        tool.SetInput(input_name, value)
