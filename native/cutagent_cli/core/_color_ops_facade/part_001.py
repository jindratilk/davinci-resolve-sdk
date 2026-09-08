"""Color grading operations — LUT, CDL, grade operations, versions."""

from __future__ import annotations

import os
import sys
import math
from typing import Optional, List, Dict, Any, Tuple

from ..errors import APICallFailed, ValidationError
from .fusion_common import iter_api_items, iter_tool_items, tool_name as fusion_tool_name
from . import lut_generator
from ._color_ops import cdl as _cdl
from ._color_ops.fusion_graph import (
    COLOR_RELATED_TOOL_TYPES,
    MASK_CHAIN_TYPES,
    PRIMARY_TOOL_TYPES,
    QUALIFIER_TOOL_TYPES,
    TRACKER_TOOL_TYPES,
    WINDOW_TOOL_TYPES,
    _comp_is_rendering,
    _connect_tool_inline,
    _find_media_io,
    _locked_comp,
    _mask_chain_input_id,
    _same_tool,
    _set_tool_name,
    _tool_name,
    _tool_type,
    _tracker_response_fields,
    _wait_for_comp_render_idle,
    _with_required_page,
)
from ._color_ops import gallery as _gallery
from ._color_ops import groups as _groups
from ._color_ops import luts as _luts
from ._color_ops import nodes as _nodes
from ._color_ops import versions as _versions

_COMPAT_EXPORTS = (
    lut_generator,
    _connect_tool_inline,
)

_SYSTEM_RESOLVE_LUT_ROOT = "/Library/Application Support/Blackmagic Design/DaVinci Resolve/LUT"
_USER_RESOLVE_LUT_ROOT = os.path.expanduser("~/Library/Application Support/Blackmagic Design/DaVinci Resolve/LUT")
CHROMA_KEY_COLORS = {
    "green": {1: 0.0, 2: 1.0, 3: 0.0},
    "blue": {1: 0.0, 2: 0.0, 3: 1.0},
    "red": {1: 1.0, 2: 0.0, 3: 0.0},
}
SECONDARY_WINDOW_SHAPES = {"rectangle", "ellipse"}


def validate_qualifier_chroma_request(
    color: str,
    threshold: float,
    comp_index: int = 1,
) -> tuple[str, float, int]:
    color_name = str(color or "").strip().lower()
    if color_name not in CHROMA_KEY_COLORS:
        raise ValidationError(
            "Unsupported chroma key color.",
            details={"color": color, "supported": sorted(CHROMA_KEY_COLORS)},
            recoverability="not_applicable",
        )

    try:
        threshold_value = float(threshold)
    except (TypeError, ValueError) as exc:
        raise ValidationError(
            "Threshold must be a number between 0.0 and 1.0.",
            details={"threshold": threshold, "minimum": 0.0, "maximum": 1.0},
            recoverability="not_applicable",
        ) from exc
    if not math.isfinite(threshold_value) or threshold_value < 0.0 or threshold_value > 1.0:
        raise ValidationError(
            "Threshold must be between 0.0 and 1.0.",
            details={"threshold": threshold, "minimum": 0.0, "maximum": 1.0},
            recoverability="not_applicable",
        )

    requested_comp = _validate_comp_index(comp_index)
    return color_name, threshold_value, requested_comp


def validate_pattern_center(value: Any) -> Tuple[float, float]:
    try:
        if isinstance(value, str):
            parts = [part.strip() for part in value.split(",")]
        else:
            parts = list(value)
    except TypeError as exc:
        raise ValidationError(
            "Tracker pattern center must be two comma-separated numbers.",
            details={"pattern_center": value},
            recoverability="not_applicable",
        ) from exc
    if len(parts) != 2:
        raise ValidationError(
            "Tracker pattern center must be two comma-separated numbers.",
            details={"pattern_center": value},
            recoverability="not_applicable",
        )
    try:
        cx = float(parts[0])
        cy = float(parts[1])
    except (TypeError, ValueError) as exc:
        raise ValidationError(
            "Tracker pattern center must be two comma-separated numbers.",
            details={"pattern_center": value},
            recoverability="not_applicable",
        ) from exc
    if not math.isfinite(cx) or not math.isfinite(cy):
        raise ValidationError(
            "Tracker pattern center must contain finite numbers.",
            details={"pattern_center": value},
            recoverability="not_applicable",
        )
    return cx, cy


def _validate_comp_index(comp_index: int = 1) -> int:
    try:
        requested_comp = int(comp_index)
    except (TypeError, ValueError) as exc:
        raise ValidationError(
            "Fusion composition index must be a positive integer.",
            details={"comp_index": comp_index},
            recoverability="not_applicable",
        ) from exc
    if requested_comp < 1:
        raise ValidationError(
            "Fusion composition index must be a positive integer.",
            details={"comp_index": comp_index},
            recoverability="not_applicable",
        )
    return requested_comp


def validate_secondary_create_request(
    *,
    window_shape: Optional[str],
    qualifier_color: Optional[str],
    qualifier_threshold: float,
    track: bool,
    pattern_center: Any,
    comp_index: int = 1,
) -> Tuple[Optional[str], Optional[str], float, bool, Tuple[float, float], int]:
    requested_comp = _validate_comp_index(comp_index)

    normalized_window = None
    if window_shape is not None:
        normalized_window = window_shape.strip().lower()
        if not normalized_window:
            raise ValidationError(
                "Window shape must not be empty.",
                details={"window": window_shape},
                recoverability="not_applicable",
            )
        if normalized_window == "polygon":
            raise ValidationError(
                "Polygon secondary creation requires points; use 'color window polygon' for polygon masks.",
                details={"window": window_shape},
                recoverability="not_applicable",
            )
        if normalized_window not in SECONDARY_WINDOW_SHAPES:
            raise ValidationError(
                "Unsupported secondary window shape.",
                details={"window": window_shape, "supported": sorted(SECONDARY_WINDOW_SHAPES)},
                recoverability="not_applicable",
            )

    try:
        threshold_value = float(qualifier_threshold)
    except (TypeError, ValueError) as exc:
        raise ValidationError(
            "Threshold must be a number between 0.0 and 1.0.",
            details={"threshold": qualifier_threshold, "minimum": 0.0, "maximum": 1.0},
            recoverability="not_applicable",
        ) from exc

    normalized_color = None
    if qualifier_color is not None:
        normalized_color, threshold_value, requested_comp = validate_qualifier_chroma_request(
            qualifier_color,
            qualifier_threshold,
            requested_comp,
        )

    center = validate_pattern_center(pattern_center)
    if not normalized_window and not normalized_color and not track:
        raise ValidationError(
            "Secondary create requires at least one of --window, --qualifier-color, or --track.",
            details={"window": window_shape, "qualifier_color": qualifier_color, "track": track},
            recoverability="not_applicable",
        )

    return normalized_window, normalized_color, threshold_value, bool(track), center, requested_comp


def resolve_item(conn, clip_name: Optional[str]):
    """
    Resolve a timeline item for color operations.
    
    Args:
        conn: ResolveConnection instance
        clip_name: Optional clip name
    
    Returns:
        Timeline item object
    
    Uses clip_ops helper to avoid duplication.
    """
    from .clip_ops import cutagent_clip
    return cutagent_clip(conn, clip_name)


def _get_clip_comp(conn, clip_name: Optional[str], comp_index: int = 1, *, ensure: bool = False):
    """Get or create a Fusion comp attached to a timeline item."""
    item = resolve_item(conn, clip_name)
    requested_index = _validate_comp_index(comp_index)

    count = 0
    if hasattr(item, "GetFusionCompCount"):
        try:
            count = int(item.GetFusionCompCount() or 0)
        except Exception:
            count = 0

    if requested_index > max(count, 1):
        raise ValidationError(
            "Fusion composition index is out of range.",
            details={"clip": clip_name, "comp_index": requested_index, "comp_count": count},
            recoverability="not_applicable",
        )

    if ensure and count <= 0:
        add_comp = getattr(item, "AddFusionComp", None)
        if not callable(add_comp):
            raise APICallFailed("Timeline item does not support AddFusionComp.", details={"clip": clip_name})
        result = add_comp()
        if result is False:
            raise APICallFailed("Failed to add Fusion composition.", details={"clip": clip_name})
        count = 1

    if count <= 0:
        raise APICallFailed("No Fusion composition attached to clip.", details={"clip": clip_name})
    comp = None
    candidate_indices: List[int] = []
    for idx in (requested_index, requested_index - 1, 0, 1):
        if idx < 0 or idx in candidate_indices:
            continue
        candidate_indices.append(idx)
    for idx in candidate_indices:
        try:
            comp = item.GetFusionCompByIndex(idx)
        except Exception:
            comp = None
        if comp:
            return item, comp

    raise APICallFailed(
        "Cannot access Fusion composition.",
        details={"clip": clip_name, "comp_index": requested_index, "comp_count": count},
    )


def _list_comp_tools(comp) -> List[Dict[str, Any]]:
    """List tools from a clip-attached Fusion composition."""
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
                    "name": fusion_tool_name(tool, str(tool_id)),
                    "type": attrs.get("TOOLS_RegID", getattr(tool, "ID", "?")),
                }
            )
    elif isinstance(tool_list, (list, tuple)):
        for i, tool in enumerate(tool_list, 1):
            attrs = tool.GetAttrs() if hasattr(tool, "GetAttrs") else {}
            rows.append(
                {
                    "id": i,
                    "name": fusion_tool_name(tool, str(i)),
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


def _find_input_obj(tool, input_id: str):
    if hasattr(tool, "GetInputList"):
        for _, obj in iter_api_items(tool.GetInputList() or {}):
            try:
                attrs = obj.GetAttrs() if hasattr(obj, "GetAttrs") else {}
                if attrs.get("INPS_ID") == input_id:
                    return obj
            except Exception:
                continue
    return getattr(tool, input_id, None)


def _find_output_obj(tool, output_id: str = "Output"):
    if hasattr(tool, "GetOutputList"):
        fallback = None
        for _, obj in iter_api_items(tool.GetOutputList() or {}):
            try:
                attrs = obj.GetAttrs() if hasattr(obj, "GetAttrs") else {}
                if fallback is None:
                    fallback = obj
                if attrs.get("OUTS_ID") == output_id:
                    return obj
            except Exception:
                continue
        if fallback is not None:
            return fallback
    return getattr(tool, output_id, None)


def _output_id(output_obj) -> str:
    if output_obj and hasattr(output_obj, "GetAttrs"):
        try:
            attrs = output_obj.GetAttrs() or {}
            out_id = attrs.get("OUTS_ID")
            if out_id:
                return str(out_id)
        except Exception:
            pass
    return getattr(output_obj, "ID", None) or "Output"


def _iter_input_ids(tool) -> List[str]:
    ids: List[str] = []
    if hasattr(tool, "GetInputList"):
        for _, obj in iter_api_items(tool.GetInputList() or {}):
            try:
                attrs = obj.GetAttrs() if hasattr(obj, "GetAttrs") else {}
                input_id = attrs.get("INPS_ID")
                if input_id:
                    ids.append(str(input_id))
            except Exception:
                continue
    if not ids:
        for candidate in ("Input", "Foreground", "Background", "EffectMask", "Solid.Matte", "Garbage.Matte"):
            if getattr(tool, candidate.replace(".", "_"), None) or getattr(tool, candidate, None):
                ids.append(candidate)
    return list(dict.fromkeys(ids))


def _all_tools(comp) -> List[Any]:
    tool_list = comp.GetToolList(False) if hasattr(comp, "GetToolList") else {}
    if isinstance(tool_list, dict):
        return list(tool_list.values())
    if isinstance(tool_list, (list, tuple)):
        return list(tool_list)
    return []


def _tool_map(comp) -> Dict[str, Any]:
    return {_tool_name(tool): tool for tool in _all_tools(comp)}


def _snapshot_comp_graph(comp) -> Dict[str, Any]:
    snapshot: Dict[str, Any] = {"tools": {}, "order": []}
    for tool in _all_tools(comp):
        name = _tool_name(tool)
        snapshot["order"].append(name)
        inputs: Dict[str, Any] = {}
        for input_id in _iter_input_ids(tool):
            input_obj = _find_input_obj(tool, input_id)
            source_name = None
            source_output = None
            if input_obj and hasattr(input_obj, "GetConnectedOutput"):
                try:
                    connected = input_obj.GetConnectedOutput()
                except Exception:
                    connected = None
                if connected and hasattr(connected, "GetTool"):
                    try:
                        source_tool = connected.GetTool()
                    except Exception:
                        source_tool = None
                    if source_tool:
                        source_name = _tool_name(source_tool)
                        source_output = _output_id(connected)
            value = _tool_input(tool, input_id, default=None)
            inputs[input_id] = {
                "value": value,
                "source_name": source_name,
                "source_output": source_output,
            }
        snapshot["tools"][name] = {
            "type": _tool_type(tool),
            "inputs": inputs,
        }
    return snapshot


def _delete_tool(comp, tool_name: str) -> bool:
    tool = _find_tool_by_name(comp, tool_name)
    if not tool:
        return False
    for method_name in ("Delete", "DeleteTool"):
        method = getattr(tool, method_name, None)
        if callable(method):
            try:
                result = method()
            except TypeError:
                result = method(tool)
            except Exception:
                result = False
            if result is not False:
                return True
    comp_delete = getattr(comp, "DeleteTool", None)
    if callable(comp_delete):
        try:
            result = comp_delete(tool)
        except Exception:
            result = False
        if result is not False:
            return True
    return False


def _restore_comp_graph(comp, snapshot: Dict[str, Any]) -> None:
    target_tools = snapshot.get("tools", {})
    current_tools = _tool_map(comp)

    for name in list(current_tools):
        if name not in target_tools:
            _delete_tool(comp, name)

    current_tools = _tool_map(comp)
    for name in snapshot.get("order", []):
        if name in current_tools:
            continue
        info = target_tools.get(name) or {}
        recreated = _create_comp_tool(comp, info.get("type", "Background"))
        _set_tool_name(recreated, name)
        current_tools[name] = recreated

    for name, info in target_tools.items():
        tool = current_tools.get(name) or _find_tool_by_name(comp, name)
        if not tool:
            continue
        for input_id in info.get("inputs", {}):
            _disconnect_input(tool, input_id)
        for input_id, input_info in info.get("inputs", {}).items():
            if input_info.get("source_name"):
                continue
            value = input_info.get("value")
            if value is None:
                continue
            try:
                tool.SetInput(input_id, value)
            except Exception:
                continue

    current_tools = _tool_map(comp)
    for name, info in target_tools.items():
        tool = current_tools.get(name)
        if not tool:
            continue
        for input_id, input_info in info.get("inputs", {}).items():
            src_name = input_info.get("source_name")
            if not src_name:
                continue
            src_tool = current_tools.get(src_name)
            if not src_tool:
                continue
            _connect_tools(src_tool, tool, input_id, input_info.get("source_output") or "Output")


def _chain_order_from_primary(primary) -> List[Any]:
    chain: List[Any] = []
    current = _connected_source(primary, "EffectMask")
    seen: set[str] = set()
    while current:
        name = _tool_name(current)
        if name in seen:
            break
        seen.add(name)
        chain.append(current)
        chain_input = _mask_chain_input_id(current)
        if not chain_input:
            break
        current = _connected_source(current, chain_input)
    chain.reverse()
    return chain


def _main_chain(media_out, media_in) -> List[Any]:
    chain: List[Any] = []
    current = _connected_source(media_out, "Input") if media_out else None
    seen: set[str] = set()
    while current:
        name = _tool_name(current)
        if name in seen:
            break
        seen.add(name)
        chain.append(current)
        if _same_tool(current, media_in):
            break
        next_source = _connected_source(current, "Input") if _find_input_obj(current, "Input") else None
        if not next_source or next_source == current:
            break
        current = next_source
    return chain


def inspect_fusion_graph(conn, clip_name: Optional[str], comp_index: int = 1) -> Dict[str, Any]:
    item, comp = _get_clip_comp(conn, clip_name, comp_index, ensure=False)
    media_in, media_out = _find_media_io(comp)
    tools = _all_tools(comp)
    primary_tools = [tool for tool in tools if _tool_type(tool) in PRIMARY_TOOL_TYPES]
    primary = primary_tools[0] if primary_tools else None
    active_mask_chain = _chain_order_from_primary(primary) if primary else []
    main_chain = _main_chain(media_out, media_in)
    attached_names = {_tool_name(tool) for tool in active_mask_chain + main_chain if tool}
    attached_names.update({_tool_name(tool) for tool in (media_in, media_out, primary) if tool})

    windows: List[Dict[str, Any]] = []
    qualifiers: List[Dict[str, Any]] = []
    trackers: List[Dict[str, Any]] = []
    orphaned: List[Dict[str, Any]] = []

    active_chain_names = {_tool_name(tool) for tool in active_mask_chain}
    for tool in tools:
        name = _tool_name(tool)
        tool_type = _tool_type(tool)
        row = _format_tool_row(tool)
        row["connected"] = name in attached_names
        if tool_type in WINDOW_TOOL_TYPES:
            row["shape"] = WINDOW_TOOL_TYPES[tool_type]
            row["active_mask_chain"] = name in active_chain_names
            windows.append(row)
        elif tool_type in QUALIFIER_TOOL_TYPES:
            row["active_mask_chain"] = name in active_chain_names
            row["media_input_connected"] = _same_tool(_connected_source(tool, "Input"), media_in)
            qualifiers.append(row)
        elif tool_type in TRACKER_TOOL_TYPES:
            row["active_mask_chain"] = name in active_chain_names
            row["media_input_connected"] = _same_tool(_connected_source(tool, "Input"), media_in)
            trackers.append(row)
        if tool_type in COLOR_RELATED_TOOL_TYPES and name not in attached_names:
            orphaned.append(row)

    return {
        "clip": clip_name,
        "comp_name": (comp.GetAttrs() or {}).get("COMPS_Name") if hasattr(comp, "GetAttrs") else None,
        "comp_index": comp_index,
        "comp_count": int(item.GetFusionCompCount() or 0) if hasattr(item, "GetFusionCompCount") else 1,
        "media_in": _tool_name(media_in) if media_in else None,
        "media_out": _tool_name(media_out) if media_out else None,
        "main_output_source": _tool_name(_connected_source(media_out, "Input")) if media_out else None,
        "main_chain": [_tool_name(tool) for tool in main_chain],
        "primary": _tool_name(primary) if primary else None,
        "extra_primaries": [_tool_name(tool) for tool in primary_tools[1:]],
        "mask_chain": [_tool_name(tool) for tool in active_mask_chain],
        "windows": windows,
        "qualifiers": qualifiers,
        "trackers": trackers,
        "orphaned_tools": orphaned,
        "tools": _list_comp_tools(comp),
    }


def validate_fusion_graph(
    conn,
    clip_name: Optional[str],
    *,
    comp_index: int = 1,
    strict: bool = False,
) -> Dict[str, Any]:
    graph = inspect_fusion_graph(conn, clip_name, comp_index=comp_index)
    errors: List[str] = []
    warnings: List[str] = []

    if not graph.get("media_in"):
        errors.append("Missing MediaIn tool.")
    if not graph.get("media_out"):
        errors.append("Missing MediaOut tool.")
    if graph.get("media_out") and not graph.get("main_output_source"):
        errors.append("MediaOut.Input is disconnected.")

    primary_name = graph.get("primary")
    main_source = graph.get("main_output_source")
    main_chain = graph.get("main_chain") or []
    if primary_name:
        if main_source != primary_name:
            errors.append("Main image pipe does not terminate at primary ColorCorrector.")
        if graph.get("media_in") and graph.get("media_in") not in main_chain:
            errors.append("Primary image pipe is not connected back to MediaIn.")
    elif graph.get("main_output_source") and graph.get("media_in") and main_source != graph.get("media_in"):
        tool_type_by_name = {row.get("name"): row.get("type") for row in graph.get("tools") or []}
        linear_color_chain = bool(main_chain) and graph.get("media_in") in main_chain
        for name in main_chain:
            tool_type = tool_type_by_name.get(name)
            if name == graph.get("media_in"):
                continue
            if tool_type != "ChromaticAdaptation":
                linear_color_chain = False
                break
        if not linear_color_chain:
            errors.append("Main image pipe is not connected directly to MediaIn.")

    if (graph.get("windows") or graph.get("qualifiers") or graph.get("trackers")) and not primary_name:
        errors.append("Mask/qualifier/tracker tools exist without a primary ColorCorrector.")

    for qualifier in graph.get("qualifiers") or []:
        if qualifier.get("active_mask_chain") and not qualifier.get("media_input_connected"):
            errors.append(f"{qualifier['name']} is missing MediaIn on Input.")
    for tracker in graph.get("trackers") or []:
        if tracker.get("active_mask_chain") and not tracker.get("media_input_connected"):
            errors.append(f"{tracker['name']} is missing MediaIn on Input.")

    for orphan in graph.get("orphaned_tools") or []:
        message = f"Orphaned color tool: {orphan['name']} ({orphan['type']})"
        if strict:
            errors.append(message)
        else:
            warnings.append(message)

    graph["valid"] = not errors
    graph["errors"] = errors
    graph["warnings"] = warnings
    return graph


def _canonicalize_graph(
    comp,
    *,
    include_windows: Optional[List[Any]] = None,
    include_qualifiers: Optional[List[Any]] = None,
    include_trackers: Optional[List[Any]] = None,
    create_primary: bool = False,
) -> Dict[str, Any]:
    media_in, media_out = _find_media_io(comp)
    if not media_in or not media_out:
        raise APICallFailed("Fusion graph missing MediaIn/MediaOut.")

    tools = _all_tools(comp)
    primary_tools = [tool for tool in tools if _tool_type(tool) in PRIMARY_TOOL_TYPES]
    primary = primary_tools[0] if primary_tools else None
    if create_primary and not primary:
        primary = _create_comp_tool(comp, "ColorCorrector", prefix="ColorCorrector")

    if primary:
        _connect_tools(media_in, primary, "Input")
        _connect_tools(primary, media_out, "Input")
    else:
        _connect_tools(media_in, media_out, "Input")

    ordered_tools = tools
    windows = include_windows if include_windows is not None else [tool for tool in ordered_tools if _tool_type(tool) in WINDOW_TOOL_TYPES]
    qualifiers = include_qualifiers if include_qualifiers is not None else [tool for tool in ordered_tools if _tool_type(tool) in QUALIFIER_TOOL_TYPES]
    trackers = include_trackers if include_trackers is not None else [tool for tool in ordered_tools if _tool_type(tool) in TRACKER_TOOL_TYPES]

    current_source = None
    if primary:
        _disconnect_input(primary, "EffectMask")

    for tool in windows:
        _disconnect_input(tool, "EffectMask")
        if current_source:
            _connect_tools(current_source, tool, "EffectMask")
        current_source = tool

    for tool in qualifiers:
        for input_id in ("Input", "Solid.Matte", "Garbage.Matte", "EffectMask"):
            _disconnect_input(tool, input_id)
        _connect_tools(media_in, tool, "Input")
        if current_source:
            _connect_tools(current_source, tool, "Solid.Matte")
        current_source = tool

    for tool in trackers:
        for input_id in ("Input", "Foreground", "EffectMask"):
            _disconnect_input(tool, input_id)
        _connect_tools(media_in, tool, "Input")
        if current_source:
            _connect_tools(current_source, tool, "Foreground")
        current_source = tool

    if primary and current_source:
        _connect_tools(current_source, primary, "EffectMask")

    return {
        "primary": _tool_name(primary) if primary else None,
        "windows": [_tool_name(tool) for tool in windows],
        "qualifiers": [_tool_name(tool) for tool in qualifiers],
        "trackers": [_tool_name(tool) for tool in trackers],
    }


def _mutate_with_graph_rollback(conn, clip_name: Optional[str], comp_index: int, fn):
    _, comp = _get_clip_comp(conn, clip_name, comp_index, ensure=True)
    snapshot: Dict[str, Any] = {}
    try:
        with _locked_comp(comp):
            snapshot = _snapshot_comp_graph(comp)
            result = fn(comp)
        validation = validate_fusion_graph(conn, clip_name, comp_index=comp_index)
        if not validation.get("valid"):
            raise APICallFailed(
                "Fusion graph validation failed after mutation.",
                details={"validation": validation},
            )
        if isinstance(result, dict):
            result["validation"] = {
                "valid": validation["valid"],
                "errors": validation["errors"],
                "warnings": validation["warnings"],
            }
        return result
    except Exception:
        try:
            if snapshot:
                with _locked_comp(comp):
                    _restore_comp_graph(comp, snapshot)
        except Exception:
            pass
        raise

def _connect_tools(src_tool, dst_tool, dst_input: str, src_output: str = "Output") -> bool:
    input_obj = _find_input_obj(dst_tool, dst_input)
    output_obj = _find_output_obj(src_tool, src_output)
    if not input_obj or not output_obj or not hasattr(input_obj, "ConnectTo"):
        return False
    input_obj.ConnectTo(output_obj)
    return True


def _disconnect_input(tool, input_id: str) -> bool:
    input_obj = _find_input_obj(tool, input_id)
    if not input_obj or not hasattr(input_obj, "ConnectTo"):
        return False
    input_obj.ConnectTo(None)
    return True


def _get_primary_tool(comp):
    tools = _find_tools_by_type(comp, "ColorCorrector")
    return tools[0] if tools else None


def _attach_effect_mask_chain(comp, mask_tool) -> Optional[str]:
    primary = _get_primary_tool(comp)
    if not primary:
        return None
    previous = _connected_source(primary, "EffectMask")
    _disconnect_input(primary, "EffectMask")
    if previous and _find_input_obj(mask_tool, "EffectMask"):
        _disconnect_input(mask_tool, "EffectMask")
        _connect_tools(previous, mask_tool, "EffectMask")
    if _connect_tools(mask_tool, primary, "EffectMask"):
        return getattr(primary, "Name", "ColorCorrector")
    if previous:
        _connect_tools(previous, primary, "EffectMask")
    return None


def _connected_source(tool, input_id: str):
    input_obj = _find_input_obj(tool, input_id)
    if not input_obj or not hasattr(input_obj, "GetConnectedOutput"):
        return None
    try:
        out = input_obj.GetConnectedOutput()
    except Exception:
        out = None
    if out and hasattr(out, "GetTool"):
        return out.GetTool()
    return None

