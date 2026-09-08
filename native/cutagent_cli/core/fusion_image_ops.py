from __future__ import annotations

from pathlib import Path
from typing import Any

from ..errors import APICallFailed, ValidationError
from .fusion_common import (
    find_tool,
    get_fusion_comp_for_item,
    iter_tool_list,
    read_tool_input,
    serialize_value,
    set_tool_input_multi,
    tool_name,
    tool_reg_id,
)

IMAGE_LOADER_INPUTS = ("Filename", "Clip", "ClipName")
IMAGE_MEDIAIN_FALLBACK_INPUTS = ("ClipName",)
IMAGE_MEDIAIN_HOLD_INPUTS = ("Loop", "HoldLastFrame", "HoldLastFrameOn", "LastFrameHold")

_ZOOM_X_KEYS = ("ZoomX", "TransformZoomX", "ScaleX", "Zoom")
_ZOOM_Y_KEYS = ("ZoomY", "TransformZoomY", "ScaleY", "Zoom")
_X_KEYS = ("Pan", "PositionX", "TransformPan", "CenterX", "AnchorPointX")
_Y_KEYS = ("Tilt", "PositionY", "TransformTilt", "CenterY", "AnchorPointY")


def validate_image_path(image_path: str) -> str:
    normalized = str(image_path or "").strip()
    if not normalized:
        raise ValidationError("Fusion image path is required.", details={"image_path": image_path})
    path = Path(normalized).expanduser()
    if path.suffix.lower() == ".html":
        raise ValidationError(
            "Fusion image injection requires a local image file, not HTML.",
            details={"image_path": str(path)},
        )
    if not path.exists():
        raise ValidationError("Fusion image file not found.", details={"image_path": str(path)})
    if not path.is_file():
        raise ValidationError("Fusion image path must point to a file.", details={"image_path": str(path)})
    return str(path.resolve())


def collect_image_target_tools(comp: Any, group_tool_name: str | None = None) -> dict[str, Any]:
    normalized_group_tool_name = str(group_tool_name or "").strip() or None
    group_tool = find_tool(comp, normalized_group_tool_name) if normalized_group_tool_name else None
    comp_tools = iter_tool_list(comp, False)
    group_tools = iter_tool_list(group_tool, False) if group_tool is not None else []
    loaders: list[Any] = []
    mediains: list[Any] = []
    seen: set[int] = set()

    for tool in [*comp_tools, *group_tools]:
        if tool is None:
            continue
        marker = id(tool)
        if marker in seen:
            continue
        seen.add(marker)
        reg_id = tool_reg_id(tool)
        if reg_id == "loader":
            loaders.append(tool)
        elif reg_id == "mediain":
            mediains.append(tool)

    return {
        "group_tool": group_tool,
        "group_tool_name": normalized_group_tool_name,
        "comp_tools": comp_tools,
        "group_tools": group_tools,
        "loaders": loaders,
        "mediains": mediains,
        "summary": {
            "group_found": group_tool is not None,
            "comp_tool_count": len(comp_tools),
            "group_tool_count": len(group_tools),
            "loader_count": len(loaders),
            "mediain_count": len(mediains),
            "loader_names": [tool_name(tool) for tool in loaders],
            "mediain_names": [tool_name(tool) for tool in mediains],
        },
    }


def import_image_media_item(conn: Any, image_path: str) -> dict[str, Any]:
    media_pool = getattr(conn, "media_pool", None)
    importer = getattr(media_pool, "ImportMedia", None) if media_pool is not None else None
    if not callable(importer):
        return {"status": "unavailable", "imported": False, "media_id": None}

    try:
        imported = importer([image_path])
    except Exception as exc:
        return {"status": "failed", "imported": False, "media_id": None, "error": str(exc)}
    if not imported:
        return {"status": "empty", "imported": False, "media_id": None}

    item = imported[0] if isinstance(imported, list) else imported
    media_id = None
    for attr_name in ("GetMediaId", "GetMediaID"):
        getter = getattr(item, attr_name, None)
        if not callable(getter):
            continue
        try:
            media_id = getter()
        except Exception:
            media_id = None
        if media_id:
            break
    if not media_id:
        getter = getattr(item, "GetClipProperty", None)
        if callable(getter):
            try:
                media_id = getter("Media ID")
            except TypeError:
                try:
                    props = getter() or {}
                except Exception:
                    props = {}
                media_id = props.get("Media ID") if isinstance(props, dict) else None
            except Exception:
                media_id = None
    item_name = None
    getter = getattr(item, "GetName", None)
    if callable(getter):
        try:
            item_name = getter()
        except Exception:
            item_name = None
    return {
        "status": "imported",
        "imported": True,
        "media_id": str(media_id) if media_id else None,
        "item_name": tool_name(item, fallback=str(item_name or "Imported Image")),
    }


def _set_indexed_media_id(tool: Any, media_id: str, current_time: int | None) -> dict[str, Any]:
    row = {
        "target": tool_name(tool),
        "input": "MediaID",
        "method": "tool.MediaID[time]=value",
        "success": False,
    }
    if current_time is None:
        row["error"] = "current_time unavailable"
        return row
    try:
        tool.MediaID[current_time] = media_id
    except Exception as exc:
        row["error"] = str(exc)
        return row
    row["success"] = True
    row["result"] = serialize_value(media_id)
    return row


def _refresh_comp(comp: Any) -> list[dict[str, Any]]:
    attempts: list[dict[str, Any]] = []
    for method_name in ("Update", "Redraw"):
        method = getattr(comp, method_name, None)
        if not callable(method):
            continue
        try:
            result = method()
            attempts.append({"target": "fusion_comp", "input": None, "method": method_name, "success": result is not False, "result": serialize_value(result)})
        except Exception as exc:
            attempts.append({"target": "fusion_comp", "input": None, "method": method_name, "success": False, "error": str(exc)})
    return attempts


def _build_transform_aliases(transform: dict[str, Any]) -> dict[str, tuple[str, ...]]:
    zoom_x = transform.get("zoom_x")
    zoom_y = transform.get("zoom_y")
    zoom_uniform_allowed = zoom_x is None or zoom_y is None or float(zoom_x) == float(zoom_y)
    return {
        "zoom_x": _ZOOM_X_KEYS if zoom_uniform_allowed else _ZOOM_X_KEYS[:-1],
        "zoom_y": _ZOOM_Y_KEYS if zoom_uniform_allowed else _ZOOM_Y_KEYS[:-1],
        "position_x": _X_KEYS,
        "position_y": _Y_KEYS,
    }


def apply_image_transform(item: Any, transform: dict[str, Any] | None) -> dict[str, Any]:
    requested = dict(transform or {})
    normalized = {
        "zoom_x": requested.get("zoom_x"),
        "zoom_y": requested.get("zoom_y"),
        "position_x": requested.get("position_x") if requested.get("position_x") is not None else requested.get("pan"),
        "position_y": requested.get("position_y") if requested.get("position_y") is not None else requested.get("tilt"),
    }
    setter = getattr(item, "SetProperty", None)
    result: dict[str, Any] = {
        "requested": requested,
        "normalized": normalized,
        "applied": {},
        "attempts": [],
        "changed": False,
    }
    if not callable(setter):
        result["reason"] = "SetProperty unavailable"
        return result

    for field_name, value in normalized.items():
        if value is None:
            continue
        aliases = _build_transform_aliases(normalized).get(field_name, ())
        for alias in aliases:
            try:
                api_result = setter(alias, float(value))
                result["attempts"].append({"field": field_name, "property": alias, "value": float(value), "success": api_result is not False, "result": serialize_value(api_result)})
                if api_result is not False:
                    result["applied"][field_name] = alias
                    result["changed"] = True
                    break
            except Exception as exc:
                result["attempts"].append({"field": field_name, "property": alias, "value": float(value), "success": False, "error": str(exc)})
    return result


def build_image_set_plan(
    *,
    selector: dict[str, Any],
    image_path: str,
    group_tool_name: str | None = None,
    group_input_name: str | None = None,
    group_inputs: dict[str, Any] | None = None,
    import_media: bool = True,
    transform: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if group_tool_name and not group_input_name:
        raise ValidationError(
            "Fusion image group injection requires --group-input when --group-tool is provided.",
            details={"group_tool": group_tool_name, "group_input": group_input_name},
        )
    return {
        "selector": selector,
        "image_path": image_path,
        "group_tool": group_tool_name,
        "group_input": group_input_name,
        "group_inputs": dict(group_inputs or {}),
        "import_media": bool(import_media),
        "loader_inputs": list(IMAGE_LOADER_INPUTS),
        "mediain_inputs": ["MediaSource", "MediaID", *IMAGE_MEDIAIN_FALLBACK_INPUTS],
        "transform": {
            "requested": dict(transform or {}),
            "aliases": {
                "zoom_x": list(_ZOOM_X_KEYS),
                "zoom_y": list(_ZOOM_Y_KEYS),
                "position_x": list(_X_KEYS),
                "position_y": list(_Y_KEYS),
            },
        },
    }


def set_image_on_item(
    conn: Any,
    item: Any,
    image_path: str,
    *,
    group_tool_name: str | None = None,
    group_input_name: str | None = None,
    group_inputs: dict[str, Any] | None = None,
    import_media: bool = True,
    transform: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_path = validate_image_path(image_path)
    normalized_group_input_name = str(group_input_name or "").strip() or None
    if group_tool_name and not normalized_group_input_name:
        raise ValidationError(
            "Fusion image group injection requires group_input_name when group_tool_name is provided.",
            details={"group_tool": group_tool_name, "group_input": group_input_name},
        )
    comp = get_fusion_comp_for_item(item)
    if comp is None:
        raise APICallFailed(
            "No Fusion composition found for the target clip.",
            details={
                "image_path": normalized_path,
                "group_tool": group_tool_name,
                "recovery_hint": "Apply this command to a clip/template that already contains a Fusion composition.",
            },
        )

    current_time = None
    try:
        current_time = int(getattr(comp, "CurrentTime", 0))
    except Exception:
        current_time = 0

    targets = collect_image_target_tools(comp, group_tool_name=group_tool_name)
    if not targets["group_tool"] and not targets["loaders"] and not targets["mediains"]:
        raise APICallFailed(
            "No Fusion image targets found in the composition.",
            details={
                "image_path": normalized_path,
                "group_tool": group_tool_name,
                "tool_summary": targets["summary"],
                "recovery_hint": "Use a template that exposes a Loader, MediaIn, or pass --group-tool/--group-input for a custom group input.",
            },
        )

    import_result = {"status": "skipped", "imported": False, "media_id": None}
    if import_media:
        import_result = import_image_media_item(conn, normalized_path)
    media_id = import_result.get("media_id")

    attempts: list[dict[str, Any]] = []
    image_updated = False
    group_inputs_updated = False

    group_tool = targets["group_tool"]
    normalized_group_inputs = {
        str(key).strip(): value
        for key, value in dict(group_inputs or {}).items()
        if str(key).strip()
    }
    if group_tool is not None:
        group_attempts = set_tool_input_multi(group_tool, normalized_group_input_name, normalized_path, current_time=current_time)
        attempts.extend(group_attempts)
        image_updated = image_updated or any(row.get("success") for row in group_attempts)
        for input_name, input_value in normalized_group_inputs.items():
            input_attempts = set_tool_input_multi(group_tool, input_name, input_value, current_time=current_time)
            attempts.extend(input_attempts)
            group_inputs_updated = group_inputs_updated or any(row.get("success") for row in input_attempts)
    skip_generic_targets = group_tool is not None and image_updated

    if not skip_generic_targets:
        for loader in targets["loaders"]:
            for input_name in IMAGE_LOADER_INPUTS:
                loader_attempts = set_tool_input_multi(loader, input_name, normalized_path, current_time=current_time)
                attempts.extend(loader_attempts)
                image_updated = image_updated or any(row.get("success") for row in loader_attempts)
            loop_attempts = set_tool_input_multi(loader, "Loop", 1, current_time=current_time)
            attempts.extend(loop_attempts)

        for media_in in targets["mediains"]:
            if media_id:
                media_source_attempts = set_tool_input_multi(media_in, "MediaSource", "MediaPool", current_time=current_time)
                attempts.extend(media_source_attempts)
                media_id_attempts = set_tool_input_multi(media_in, "MediaID", media_id, current_time=current_time)
                attempts.extend(media_id_attempts)
                indexed_attempt = _set_indexed_media_id(media_in, media_id, current_time=current_time)
                attempts.append(indexed_attempt)
                image_updated = image_updated or any(row.get("success") for row in media_source_attempts + media_id_attempts) or indexed_attempt.get("success", False)
            for input_name in IMAGE_MEDIAIN_FALLBACK_INPUTS:
                clip_name_attempts = set_tool_input_multi(media_in, input_name, normalized_path, current_time=current_time)
                attempts.extend(clip_name_attempts)
                image_updated = image_updated or any(row.get("success") for row in clip_name_attempts)
            for input_name in IMAGE_MEDIAIN_HOLD_INPUTS:
                hold_attempts = set_tool_input_multi(media_in, input_name, 1, current_time=current_time)
                attempts.extend(hold_attempts)

    transform_result = apply_image_transform(item, transform)
    refresh_attempts = _refresh_comp(comp)
    attempts.extend(refresh_attempts)

    verification = {
        "group_input": None,
        "group_inputs": {},
        "loaders": [],
        "mediains": [],
    }
    if group_tool is not None:
        verification["group_input"] = {
            "tool": tool_name(group_tool),
            "input": normalized_group_input_name,
            "value": serialize_value(read_tool_input(group_tool, normalized_group_input_name)),
        }
        for input_name in normalized_group_inputs:
            verification["group_inputs"][input_name] = serialize_value(read_tool_input(group_tool, input_name))
    for loader in targets["loaders"]:
        verification["loaders"].append(
            {
                "tool": tool_name(loader),
                "Filename": serialize_value(read_tool_input(loader, "Filename")),
                "Clip": serialize_value(read_tool_input(loader, "Clip")),
                "ClipName": serialize_value(read_tool_input(loader, "ClipName")),
                "Loop": serialize_value(read_tool_input(loader, "Loop")),
            }
        )
    for media_in in targets["mediains"]:
        verification["mediains"].append(
            {
                "tool": tool_name(media_in),
                "MediaSource": serialize_value(read_tool_input(media_in, "MediaSource")),
                "MediaID": serialize_value(read_tool_input(media_in, "MediaID")),
                "ClipName": serialize_value(read_tool_input(media_in, "ClipName")),
                "Loop": serialize_value(read_tool_input(media_in, "Loop")),
                "HoldLastFrame": serialize_value(read_tool_input(media_in, "HoldLastFrame")),
            }
        )

    return {
        "image_path": normalized_path,
        "group_tool": group_tool_name,
        "group_input": normalized_group_input_name,
        "group_inputs": normalized_group_inputs,
        "import_status": import_result.get("status"),
        "imported_media_id": media_id,
        "import_result": import_result,
        "tool_summary": targets["summary"],
        "skipped_generic_targets": bool(skip_generic_targets),
        "image_updated": image_updated,
        "group_inputs_updated": group_inputs_updated,
        "updated": bool(image_updated or group_inputs_updated or transform_result.get("changed")),
        "attempts": attempts,
        "transform": transform_result,
        "verification": verification,
    }
