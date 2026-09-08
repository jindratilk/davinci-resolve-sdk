from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Any, Dict, List, Optional, Tuple

from ...errors import APICallFailed
from ..fusion_common import iter_tool_items, tool_name as fusion_tool_name

WINDOW_TOOL_TYPES = {
    "RectangleMask": "rectangle",
    "EllipseMask": "ellipse",
    "PolylineMask": "polygon",
}
QUALIFIER_TOOL_TYPES = {"ChromaKeyer"}
TRACKER_TOOL_TYPES = {"Tracker"}
PRIMARY_TOOL_TYPES = {"ColorCorrector"}
MASK_CHAIN_TYPES = set(WINDOW_TOOL_TYPES) | QUALIFIER_TOOL_TYPES | TRACKER_TOOL_TYPES
MAIN_PIPE_COLOR_TOOL_TYPES = {"ChromaticAdaptation"}
COLOR_RELATED_TOOL_TYPES = PRIMARY_TOOL_TYPES | MASK_CHAIN_TYPES | MAIN_PIPE_COLOR_TOOL_TYPES


def _tool_name(tool) -> str:
    return fusion_tool_name(tool, "")


def _tool_type(tool) -> str:
    attrs = tool.GetAttrs() if hasattr(tool, "GetAttrs") else {}
    return attrs.get("TOOLS_RegID", getattr(tool, "ID", "?"))


def _mask_chain_input_id(tool_or_type: Any) -> Optional[str]:
    tool_type = tool_or_type if isinstance(tool_or_type, str) else _tool_type(tool_or_type)
    if tool_type in WINDOW_TOOL_TYPES:
        return "EffectMask"
    if tool_type == "ChromaKeyer":
        return "Solid.Matte"
    if tool_type == "Tracker":
        return "Foreground"
    return None


def _same_tool(a, b) -> bool:
    if not a or not b:
        return False
    return _tool_name(a) == _tool_name(b) and _tool_type(a) == _tool_type(b)


def _comp_is_rendering(comp) -> bool:
    if hasattr(comp, "IsRendering"):
        try:
            return bool(comp.IsRendering())
        except Exception:
            pass
    if hasattr(comp, "GetAttrs"):
        try:
            return bool((comp.GetAttrs() or {}).get("COMPB_Rendering"))
        except Exception:
            pass
    return False


def _wait_for_comp_render_idle(comp, *, timeout_s: float = 2.0, poll_s: float = 0.1) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if not _comp_is_rendering(comp):
            return True
        time.sleep(poll_s)
    return not _comp_is_rendering(comp)


@contextmanager
def _locked_comp(comp):
    locked = False
    lock = getattr(comp, "Lock", None)
    if callable(lock):
        try:
            result = lock()
            locked = result is not False
        except Exception:
            locked = False
    try:
        yield
    finally:
        if locked:
            unlock = getattr(comp, "Unlock", None)
            if callable(unlock):
                try:
                    unlock()
                except Exception:
                    pass


@contextmanager
def _with_required_page(conn, page: str):
    resolve = getattr(conn, "resolve", None)
    previous_page: Optional[str] = None
    switched = False

    if resolve and hasattr(resolve, "GetCurrentPage"):
        try:
            previous_page = resolve.GetCurrentPage()
        except Exception:
            previous_page = None

    if resolve and hasattr(resolve, "OpenPage") and previous_page != page:
        opened = resolve.OpenPage(page)
        if opened is False:
            raise APICallFailed(
                f"Failed to switch DaVinci Resolve to '{page}' page.",
                details={"required_page": page, "current_page": previous_page},
            )
        switched = True

    try:
        yield
    finally:
        if switched and resolve and previous_page and previous_page != page:
            try:
                resolve.OpenPage(previous_page)
            except Exception:
                pass


def _list_comp_tools(comp) -> List[Dict[str, Any]]:
    tool_list = comp.GetToolList(False) if hasattr(comp, "GetToolList") else {}
    if not tool_list:
        return []

    rows: List[Dict[str, Any]] = []
    if isinstance(tool_list, dict):
        for tool_id, tool in tool_list.items():
            attrs = tool.GetAttrs() if hasattr(tool, "GetAttrs") else {}
            rows.append(
                {
                    "id": tool_id,
                    "name": getattr(tool, "Name", str(tool_id)),
                    "type": attrs.get("TOOLS_RegID", getattr(tool, "ID", "?")),
                }
            )
    elif isinstance(tool_list, (list, tuple)):
        for i, tool in enumerate(tool_list, 1):
            attrs = tool.GetAttrs() if hasattr(tool, "GetAttrs") else {}
            rows.append(
                {
                    "id": i,
                    "name": getattr(tool, "Name", str(i)),
                    "type": attrs.get("TOOLS_RegID", getattr(tool, "ID", "?")),
                }
            )
    return rows


def _next_tool_name(comp, prefix: str) -> str:
    existing = {row["name"] for row in _list_comp_tools(comp)}
    counter = 1
    while f"{prefix}{counter}" in existing:
        counter += 1
    return f"{prefix}{counter}"


def _find_tool_by_name(comp, tool_name: str):
    if hasattr(comp, "FindTool"):
        try:
            tool = comp.FindTool(tool_name)
        except Exception:
            tool = None
        if tool:
            return tool
    for _, tool in iter_tool_items(comp, False):
        if getattr(tool, "Name", None) == tool_name:
            return tool
    return None


def _find_tools_by_type(comp, tool_type: str) -> List[Any]:
    matches: List[Any] = []
    for _, tool in iter_tool_items(comp, False):
        attrs = tool.GetAttrs() if hasattr(tool, "GetAttrs") else {}
        reg_id = attrs.get("TOOLS_RegID", getattr(tool, "ID", None))
        if reg_id == tool_type:
            matches.append(tool)
    return matches


def _resolve_tracker_tool(comp, tracker_name: str):
    requested = str(tracker_name or "").strip()
    trackers = [tool for tool in _find_tools_by_type(comp, "Tracker") if _tool_type(tool) in TRACKER_TOOL_TYPES]
    available = [_tool_name(tool) for tool in trackers]

    if requested:
        exact = _find_tool_by_name(comp, requested)
        if exact:
            if _tool_type(exact) in TRACKER_TOOL_TYPES:
                return exact, _tool_name(exact), "exact"
            raise APICallFailed(
                "Tracker not found.",
                details={
                    "tracker": tracker_name,
                    "matched_tool": _tool_name(exact),
                    "matched_type": _tool_type(exact),
                    "available_trackers": available,
                },
            )

        requested_lower = requested.lower()
        for tracker in trackers:
            if _tool_name(tracker).lower() == requested_lower:
                return tracker, _tool_name(tracker), "case_insensitive"

        if len(trackers) == 1:
            tracker = trackers[0]
            return tracker, _tool_name(tracker), "single_tracker_fallback"
    elif len(trackers) == 1:
        tracker = trackers[0]
        return tracker, _tool_name(tracker), "single_tracker_default"

    raise APICallFailed(
        "Tracker not found.",
        details={"tracker": tracker_name, "available_trackers": available},
    )


def _tracker_response_fields(requested_name: str, resolved_name: str, resolution: str) -> Dict[str, Any]:
    fields: Dict[str, Any] = {"tracker": resolved_name}
    if str(requested_name or "").strip() != resolved_name:
        fields["requested_tracker"] = requested_name
        fields["tracker_resolution"] = resolution
    return fields


def _set_tool_name(tool, name: str) -> str:
    if hasattr(tool, "SetAttrs"):
        try:
            tool.SetAttrs({"TOOLS_Name": name})
        except Exception:
            pass
    return fusion_tool_name(tool, name)


def _connect_tool_inline(comp, new_tool) -> bool:
    try:
        tool_items = iter_tool_items(comp, False)
        if not tool_items:
            return False

        media_in = None
        media_out = None
        for _, tool in tool_items:
            attrs = tool.GetAttrs() if hasattr(tool, "GetAttrs") else {}
            reg_id = attrs.get("TOOLS_RegID", getattr(tool, "ID", None))
            if reg_id == "MediaIn" and media_in is None:
                media_in = tool
            elif reg_id == "MediaOut" and media_out is None:
                media_out = tool

        if not media_out:
            return False

        prev_tool = None
        if hasattr(media_out, "Input") and hasattr(media_out.Input, "GetConnectedOutput"):
            connected = media_out.Input.GetConnectedOutput()
            if connected and hasattr(connected, "GetTool"):
                prev_tool = connected.GetTool()

        source = prev_tool or media_in
        if not source:
            return False

        if hasattr(new_tool, "Input"):
            source_output = getattr(source, "Output", None)
            if source_output:
                new_tool.Input.ConnectTo(source_output)

        new_output = getattr(new_tool, "Output", None)
        if new_output and hasattr(media_out, "Input"):
            media_out.Input.ConnectTo(new_output)

        return True
    except Exception as exc:
        raise APICallFailed(f"Failed to connect Fusion tool inline: {exc}")


def _find_media_io(comp) -> Tuple[Any, Any]:
    media_in = None
    media_out = None
    for _, tool in iter_tool_items(comp, False):
        attrs = tool.GetAttrs() if hasattr(tool, "GetAttrs") else {}
        reg_id = attrs.get("TOOLS_RegID", getattr(tool, "ID", None))
        if reg_id == "MediaIn" and media_in is None:
            media_in = tool
        elif reg_id == "MediaOut" and media_out is None:
            media_out = tool
    return media_in, media_out
