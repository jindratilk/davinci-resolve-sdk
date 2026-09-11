"""
Fusion Scripting API wrapper.

This module provides access to DaVinci Resolve's Fusion scripting API
via resolve.Fusion() → fusion.GetCurrentComp().

Unlike clip-based Fusion access (via item.GetFusionCompByIndex()),
this API provides direct composition manipulation with full tool control,
keyframe animation, and node connection capabilities.
"""

from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Optional, Tuple

from ..errors import APICallFailed, ValidationError
from .fusion_common import iter_api_items, iter_tool_items, tool_name


class FusionAPI:
    """
    Wrapper for Fusion scripting API.
    
    Access via: resolve.Fusion() → fusion.GetCurrentComp()
    """
    
    def __init__(self, conn):
        """Initialize Fusion API with ResolveConnection."""
        self.conn = conn
        self._fusion = None
        self._comp = None
    
    @property
    def fusion(self):
        """Get Fusion object."""
        if not self._fusion:
            try:
                self._fusion = self.conn.resolve.Fusion()
                if not self._fusion:
                    raise APICallFailed("Failed to get Fusion object")
            except Exception as e:
                raise APICallFailed(f"Cannot access Fusion API: {e}")
        return self._fusion
    
    @property
    def comp(self):
        """Get current composition (refreshes each access)."""
        try:
            comp = self.fusion.GetCurrentComp()
            if not comp:
                comp = self._current_timeline_item_comp()
            if not comp:
                raise APICallFailed(
                    "No active Fusion composition. "
                    "Open a Fusion comp or select a timeline clip that already has one.",
                    details={
                        "native_routes": ["Fusion.GetCurrentComp", "Timeline.GetCurrentVideoItem.GetFusionCompByIndex"],
                        "recovery_hint": "Use `cutagent clip fusion add <clip>` or open the clip on the Fusion page before editing Fusion nodes/keyframes.",
                    },
                )
            self._comp = comp
            return comp
        except APICallFailed:
            raise
        except Exception as e:
            raise APICallFailed(f"Cannot get current composition: {e}")

    def _current_timeline_item_comp(self):
        """Fallback to the current timeline item's first Fusion comp."""
        timeline = getattr(self.conn, "timeline", None)
        if not timeline or not hasattr(timeline, "GetCurrentVideoItem"):
            return None
        try:
            item = timeline.GetCurrentVideoItem()
        except Exception:
            return None
        if not item or not hasattr(item, "GetFusionCompByIndex"):
            return None

        indexes: list[int] = []
        if hasattr(item, "GetFusionCompCount"):
            try:
                count = int(item.GetFusionCompCount() or 0)
                indexes.extend(range(1, count + 1))
            except Exception:
                return None
        else:
            count = 0
        if count <= 0:
            return None
        indexes.extend([1, 0])

        seen: set[int] = set()
        for index in indexes:
            if index in seen:
                continue
            seen.add(index)
            try:
                comp = item.GetFusionCompByIndex(index)
                if comp:
                    return comp
            except Exception:
                continue
        return None
    
    def get_comp_info(self) -> Dict[str, Any]:
        """
        Get current composition information.
        
        Returns:
            Dict with comp name, frame range, current time, etc.
        """
        comp = self.comp
        
        attrs = {}
        if hasattr(comp, "GetAttrs"):
            try:
                attrs = comp.GetAttrs() or {}
            except Exception:
                pass
        
        info = {
            "name": getattr(comp, "GetAttrs", lambda: {})().get("COMPS_Name", ""),
            "current_time": getattr(comp, "CurrentTime", 0),
        }
        
        # Try to get frame range
        for key in ["COMPN_RenderStart", "COMPN_RenderEnd", "COMPN_GlobalStart", "COMPN_GlobalEnd"]:
            if key in attrs:
                info[key.lower().replace("compn_", "")] = attrs[key]
        
        return info
    
    # === Tool Management ===

    def list_registered_tools(
        self,
        *,
        query: str | None = None,
        category: str | None = None,
        limit: int = 1024,
    ) -> Dict[str, Any]:
        """List bounded, public-safe creation identifiers from the live Fusion registry."""
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 2048:
            raise ValidationError("Fusion registry limit must be between 1 and 2048.")
        normalized_query = str(query or "").strip().casefold()
        normalized_category = str(category or "").strip().casefold()
        if len(normalized_query) > 256 or len(normalized_category) > 256:
            raise ValidationError("Fusion registry filters must not exceed 256 characters.")

        getter = getattr(self.fusion, "GetRegList", None)
        if not callable(getter):
            raise APICallFailed(
                "Fusion tool registry is unavailable.",
                details={"required_method": "Fusion.GetRegList"},
            )
        try:
            entries = iter_api_items(getter(2) or {})
        except Exception as exc:
            raise APICallFailed("Failed to read the Fusion tool registry.") from exc
        if len(entries) > 2048:
            raise APICallFailed(
                "Fusion tool registry exceeded the supported result bound.",
                details={"maximum_tools": 2048},
            )

        rows: list[dict[str, str]] = []
        identifiers: set[str] = set()
        for key, registration in entries:
            try:
                attrs = registration.GetAttrs() or {}
            except Exception:
                continue
            if not isinstance(attrs, dict):
                continue
            identifier = str(attrs.get("REGS_ID") or (key if isinstance(key, str) else "")).strip()
            if not identifier:
                continue
            name = str(attrs.get("REGS_UIName") or attrs.get("REGS_Name") or identifier).strip()
            tool_category = str(attrs.get("REGS_Category") or "").strip()
            if len(identifier) > 256 or len(name) > 512 or len(tool_category) > 512:
                raise APICallFailed("Fusion tool registry returned an oversized public label.")
            if identifier in identifiers:
                raise APICallFailed("Fusion tool registry returned duplicate creation identifiers.")
            identifiers.add(identifier)
            searchable = f"{identifier}\n{name}\n{tool_category}".casefold()
            if normalized_query and normalized_query not in searchable:
                continue
            if normalized_category and normalized_category not in tool_category.casefold():
                continue
            rows.append({"id": identifier, "name": name, "category": tool_category})

        rows.sort(key=lambda row: row["id"].encode("utf-8"))
        total = len(rows)
        tools = rows[:limit]
        return {
            "tools": tools,
            "total": total,
            "returned": len(tools),
            "truncated": len(tools) < total,
        }
    
    def list_tools(self, selected_only: bool = False) -> List[Dict[str, Any]]:
        """
        List all tools in the composition.
        
        Args:
            selected_only: If True, list only selected tools
        
        Returns:
            List of tool info dicts
        """
        comp = self.comp
        
        try:
            tool_items = iter_tool_items(comp, selected_only)
            if not tool_items:
                return []
            
            result = []
            for tool_id, tool in tool_items:
                info = {
                    "id": tool_id,
                    "name": tool_name(tool, str(tool_id)),
                    "type": self._get_tool_type(tool),
                }
                result.append(info)
            
            return result
        except Exception as e:
            raise APICallFailed(f"Failed to list tools: {e}")
    
    def _get_tool_type(self, tool) -> str:
        """Get tool type name."""
        if hasattr(tool, "GetAttrs"):
            attrs = tool.GetAttrs()
            if isinstance(attrs, dict) and attrs.get("TOOLS_RegID"):
                return attrs["TOOLS_RegID"]
        tool_id = getattr(tool, "ID", None)
        if isinstance(tool_id, str) and tool_id:
            return tool_id
        return "Unknown"
    
    def add_tool(self, tool_type: str, x: int = -32768, y: int = -32768, name: Optional[str] = None) -> Any:
        """
        Add a tool to the composition.
        
        Args:
            tool_type: Tool type (e.g., "TextPlus", "Merge", "Background")
            x: X position in flow (-32768 = auto)
            y: Y position in flow (-32768 = auto)
            name: Optional custom name
        
        Returns:
            Tool object
        """
        comp = self.comp
        if not hasattr(comp, "AddTool"):
            raise APICallFailed(
                "Fusion composition cannot create tools.",
                details={"tool_type": tool_type, "required_method": "AddTool"},
            )

        attempts: list[dict[str, Any]] = []

        def _try_add(args: tuple[Any, ...], route: str):
            try:
                tool = comp.AddTool(*args)
            except Exception as exc:
                attempts.append({"route": route, "args": list(args), "error": str(exc)})
                return None
            if not tool:
                attempts.append({"route": route, "args": list(args), "result": "falsey"})
                return None
            attempts.append({"route": route, "args": list(args), "result": "created"})
            return tool

        tool = _try_add((tool_type, x, y), "AddTool(type,x,y)")
        if tool is None:
            tool = _try_add((tool_type,), "AddTool(type)")

        if not tool:
            raise APICallFailed(
                f"Failed to add Fusion tool '{tool_type}'.",
                details={
                    "tool_type": tool_type,
                    "name": name,
                    "x": x,
                    "y": y,
                    "attempts": attempts,
                    "common_tool_types": [
                        "TextPlus",
                        "Merge",
                        "Background",
                        "Transform",
                        "ColorCorrector",
                        "Blur",
                        "SoftGlow",
                        "Tracker",
                    ],
                },
            )

        rename_error = None
        if name and hasattr(tool, "SetAttrs"):
            try:
                tool.SetAttrs({"TOOLS_Name": name})
            except Exception as exc:
                rename_error = str(exc)

        if rename_error and not hasattr(tool, "Name"):
            raise APICallFailed(
                f"Added Fusion tool '{tool_type}' but failed to set custom name.",
                details={"tool_type": tool_type, "name": name, "rename_error": rename_error},
            )

        return tool
    
    def find_tool(self, name: str) -> Any:
        """
        Find a tool by name.
        
        Args:
            name: Tool name
        
        Returns:
            Tool object
        
        Raises:
            APICallFailed: If tool not found
        """
        requested = str(name or "").strip()
        if not requested:
            raise APICallFailed("Tool not found: empty tool name.", details={"tool_name": name})

        comp = self.comp
        find_error = None
        finder = getattr(comp, "FindTool", None)
        if callable(finder):
            try:
                tool = finder(requested)
                if tool:
                    return tool
            except Exception as exc:
                find_error = str(exc)

        candidates: list[dict[str, Any]] = []
        try:
            tool_map = comp.GetToolList(False) if hasattr(comp, "GetToolList") else {}
        except Exception as exc:
            tool_map = {}
            find_error = find_error or str(exc)

        if isinstance(tool_map, dict):
            exact_matches: list[Any] = []
            case_matches: list[Any] = []
            type_matches: list[Any] = []
            normalized_requested = requested.lower()
            for tool_id, tool in tool_map.items():
                tool_name = self._tool_name(tool, fallback=str(tool_id))
                tool_type = self._get_tool_type(tool)
                row = {"id": str(tool_id), "name": tool_name, "type": tool_type}
                candidates.append(row)
                if requested in {str(tool_id), tool_name}:
                    exact_matches.append(tool)
                if normalized_requested in {str(tool_id).lower(), tool_name.lower()}:
                    case_matches.append(tool)
                if normalized_requested == tool_type.lower():
                    type_matches.append(tool)

            if len(exact_matches) == 1:
                return exact_matches[0]
            if len(case_matches) == 1:
                return case_matches[0]
            if len(type_matches) == 1:
                return type_matches[0]
            if len(type_matches) > 1:
                raise APICallFailed(
                    f"Tool name '{requested}' is ambiguous; multiple Fusion tools have that type.",
                    details={"tool_name": requested, "matches": [row for row in candidates if row["type"].lower() == normalized_requested]},
                )

        raise APICallFailed(
            f"Tool not found: {requested}",
            details={"tool_name": requested, "find_error": find_error, "available_tools": candidates},
        )

    def _tool_name(self, tool, *, fallback: str = "") -> str:
        if hasattr(tool, "Name"):
            try:
                text = str(tool.Name or "").strip()
                if text:
                    return text
            except Exception:
                pass
        if hasattr(tool, "GetAttrs"):
            try:
                attrs = tool.GetAttrs() or {}
                for key in ("TOOLS_Name", "TOOLB_Name"):
                    text = str(attrs.get(key) or "").strip()
                    if text:
                        return text
            except Exception:
                pass
        return fallback
    
    def delete_tool(self, tool_name: str) -> bool:
        """
        Delete a tool.
        
        Args:
            tool_name: Tool name
        
        Returns:
            True if successful
        """
        tool = self.find_tool(tool_name)
        
        try:
            tool.Delete()
            return True
        except Exception as e:
            raise APICallFailed(f"Failed to delete tool {tool_name}: {e}")
    
    # === Tool Inputs/Outputs ===
    
    def get_tool_inputs(self, tool_name: str) -> Dict[str, Any]:
        """
        Get all inputs of a tool.
        
        Args:
            tool_name: Tool name
        
        Returns:
            Dict mapping input name to Input object info
        """
        tool = self.find_tool(tool_name)
        
        try:
            if not hasattr(tool, "GetInputList"):
                return {}
            
            input_list = tool.GetInputList()
            if not input_list:
                return {}
            
            result = {}
            comp = self.comp
            current_time = comp.CurrentTime if hasattr(comp, "CurrentTime") else 0
            
            for input_name, input_obj in iter_api_items(input_list):
                input_name = getattr(input_obj, "ID", None) or input_name
                info = {
                    "name": input_name,
                    "id": getattr(input_obj, "ID", "") if hasattr(input_obj, "ID") else "",
                }
                
                # Try to get current value
                try:
                    value = tool.GetInput(input_name, current_time)
                    info["value"] = value
                except Exception:
                    info["value"] = None
                
                result[input_name] = info
            
            return result
        except Exception as e:
            raise APICallFailed(f"Failed to get inputs for {tool_name}: {e}")
    
    def get_tool_outputs(self, tool_name: str) -> Dict[str, Any]:
        """
        Get all outputs of a tool.
        
        Args:
            tool_name: Tool name
        
        Returns:
            Dict mapping output name to Output object info
        """
        tool = self.find_tool(tool_name)
        
        try:
            if not hasattr(tool, "GetOutputList"):
                return {}
            
            output_list = tool.GetOutputList()
            if not output_list:
                return {}
            
            result = {}
            for output_name, output_obj in iter_api_items(output_list):
                output_name = getattr(output_obj, "ID", None) or output_name
                info = {
                    "name": output_name,
                    "id": getattr(output_obj, "ID", "") if hasattr(output_obj, "ID") else "",
                }
                result[output_name] = info
            
            return result
        except Exception as e:
            raise APICallFailed(f"Failed to get outputs for {tool_name}: {e}")
    
    def get_tool_input(self, tool_name: str, input_name: str, time: Optional[int] = None) -> Any:
        """
        Get a specific tool input value.
        
        Args:
            tool_name: Tool name
            input_name: Input name
            time: Frame time (default: current time)
        
        Returns:
            Input value
        """
        tool = self.find_tool(tool_name)
        comp = self.comp
        
        if time is None:
            time = comp.CurrentTime if hasattr(comp, "CurrentTime") else 0
        
        try:
            value = tool.GetInput(input_name, time)
            return value
        except Exception as e:
            raise APICallFailed(f"Failed to get {tool_name}.{input_name}: {e}")
    
    def set_tool_input(self, tool_name: str, input_name: str, value: Any, time: Optional[int] = None) -> bool:
        """
        Set a tool input value.
        
        Args:
            tool_name: Tool name
            input_name: Input name
            value: Value to set
            time: Frame time (default: current time, None = no keyframe)
        
        Returns:
            True if successful
        """
        tool = self.find_tool(tool_name)
        
        try:
            if time is not None:
                # Set keyframe at specific time
                tool.SetInput(input_name, value, time)
            else:
                # Set value without keyframe
                tool.SetInput(input_name, value)
            return True
        except Exception as e:
            raise APICallFailed(f"Failed to set {tool_name}.{input_name}: {e}")
    
    def get_tool_attrs(self, tool_name: str) -> Dict[str, Any]:
        """
        Get tool attributes.
        
        Args:
            tool_name: Tool name
        
        Returns:
            Dict of attributes
        """
        tool = self.find_tool(tool_name)
        
        try:
            if not hasattr(tool, "GetAttrs"):
                return {}
            
            attrs = tool.GetAttrs()
            return attrs or {}
        except Exception as e:
            raise APICallFailed(f"Failed to get attributes for {tool_name}: {e}")
    
    # === Tool Connections ===
    
    def _find_input_by_id(self, tool, tool_name: str, input_id: str):
        """Find an input object by its INPS_ID string name."""
        if hasattr(tool, "GetInputList"):
            input_list = tool.GetInputList()
            if input_list:
                for key, inp in iter_api_items(input_list):
                    try:
                        attrs = inp.GetAttrs()
                        if attrs and attrs.get("INPS_ID") == input_id:
                            return inp
                    except Exception:
                        pass
        # Fallback: direct attribute access
        obj = getattr(tool, input_id, None)
        if obj:
            return obj
        raise APICallFailed(f"Input '{input_id}' not found on {tool_name}")

    def _find_output_by_id(self, tool, tool_name: str, output_id: str):
        """Find an output object by its OUTS_ID string name."""
        if hasattr(tool, "GetOutputList"):
            output_list = tool.GetOutputList()
            if output_list:
                for key, out in iter_api_items(output_list):
                    try:
                        attrs = out.GetAttrs()
                        if attrs and attrs.get("OUTS_ID") == output_id:
                            return out
                    except Exception:
                        pass
        obj = getattr(tool, output_id, None)
        if obj:
            return obj
        raise APICallFailed(f"Output '{output_id}' not found on {tool_name}")

    def connect_tools(
        self,
        src_tool: str,
        src_output: str,
        dst_tool: str,
        dst_input: str
    ) -> bool:
        """
        Connect two tools.
        
        Args:
            src_tool: Source tool name
            src_output: Source output name
            dst_tool: Destination tool name
            dst_input: Destination input name
        
        Returns:
            True if successful
        """
        src = self.find_tool(src_tool)
        dst = self.find_tool(dst_tool)
        
        try:
            input_obj = self._find_input_by_id(dst, dst_tool, dst_input)
            output_obj = self._find_output_by_id(src, src_tool, src_output)
            
            # Connect
            if hasattr(input_obj, "ConnectTo"):
                input_obj.ConnectTo(output_obj)
            else:
                raise APICallFailed("Input object doesn't support ConnectTo")
            
            return True
        except Exception as e:
            raise APICallFailed(f"Failed to connect {src_tool}.{src_output} → {dst_tool}.{dst_input}: {e}")
    
    def disconnect_tool(self, tool_name: str, input_name: str) -> bool:
        """
        Disconnect a tool input.
        
        Args:
            tool_name: Tool name
            input_name: Input name
        
        Returns:
            True if successful
        """
        tool = self.find_tool(tool_name)
        
        try:
            input_obj = self._find_input_by_id(tool, tool_name, input_name)
            
            # Disconnect by connecting to None
            if hasattr(input_obj, "ConnectTo"):
                input_obj.ConnectTo(None)
            else:
                raise APICallFailed("Input object doesn't support ConnectTo")
            
            return True
        except Exception as e:
            raise APICallFailed(f"Failed to disconnect {tool_name}.{input_name}: {e}")
    
    # === Active Tool ===
    
    def get_active_tool(self) -> Optional[str]:
        """
        Get the currently active tool name.
        
        Returns:
            Tool name or None
        """
        comp = self.comp
        
        def _tool_name(value) -> Optional[str]:
            if not value:
                return None
            if hasattr(value, "Name"):
                return value.Name
            if hasattr(value, "GetAttrs"):
                try:
                    attrs = value.GetAttrs()
                    name = attrs.get("TOOLS_Name") if isinstance(attrs, dict) else None
                    if name:
                        return str(name)
                except Exception:
                    pass
            return str(value)

        try:
            for attr_name in ("ActiveTool", "CurrentTool"):
                active_tool = getattr(comp, attr_name, None)
                name = _tool_name(active_tool)
                if name:
                    return name

            if not hasattr(comp, "GetAttrs"):
                return None

            attrs = comp.GetAttrs()
            active_tool = attrs.get("COMPS_ActiveTool")
            name = _tool_name(active_tool)
            if name:
                return name

            return None
        except Exception:
            return None
    
    def set_active_tool(self, tool_name: str) -> bool:
        """
        Set the active tool.
        
        Args:
            tool_name: Tool name
        
        Returns:
            True if successful
        """
        tool = self.find_tool(tool_name)
        comp = self.comp
        
        try:
            did_set = False
            if hasattr(comp, "SetActiveTool"):
                comp.SetActiveTool(tool)
                did_set = True
            if hasattr(comp, "SetAttrs"):
                comp.SetAttrs({"COMPS_ActiveTool": tool})
                did_set = True
            if did_set:
                return True
            else:
                raise APICallFailed("Composition doesn't support SetActiveTool")
        except Exception as e:
            raise APICallFailed(f"Failed to set active tool to {tool_name}: {e}")
    
    # === Copy/Paste ===
    
    def copy_tools(self, tool_names: List[str]) -> bool:
        """
        Copy tools to clipboard.
        
        Args:
            tool_names: List of tool names to copy
        
        Returns:
            True if successful
        """
        comp = self.comp
        
        try:
            tools = [self.find_tool(name) for name in tool_names]
            
            if hasattr(comp, "Copy"):
                comp.Copy(tools)
            else:
                raise APICallFailed("Composition doesn't support Copy")
            
            return True
        except Exception as e:
            raise APICallFailed(f"Failed to copy tools: {e}")
    
    def paste_tools(self) -> bool:
        """
        Paste tools from clipboard.
        
        Returns:
            True if successful
        """
        comp = self.comp
        
        try:
            if hasattr(comp, "Paste"):
                result = comp.Paste()
                return result is not None
            else:
                raise APICallFailed("Composition doesn't support Paste")
        except Exception as e:
            raise APICallFailed(f"Failed to paste tools: {e}")
    
    # === Playback ===
    
    def play(self) -> bool:
        """Start playback."""
        comp = self.comp
        
        try:
            if hasattr(comp, "Play"):
                comp.Play()
            else:
                raise APICallFailed("Composition doesn't support Play")
            return True
        except Exception as e:
            raise APICallFailed(f"Failed to start playback: {e}")
    
    def stop(self) -> bool:
        """Stop playback."""
        comp = self.comp
        
        try:
            if hasattr(comp, "Stop"):
                comp.Stop()
            else:
                raise APICallFailed("Composition doesn't support Stop")
            return True
        except Exception as e:
            raise APICallFailed(f"Failed to stop playback: {e}")
    
    # === Render ===
    
    def render(self, wait: bool = False) -> bool:
        """
        Render the composition.
        
        Args:
            wait: Wait for render to complete
        
        Returns:
            True if successful
        """
        comp = self.comp
        
        try:
            if hasattr(comp, "Render"):
                result = comp.Render(wait)
                return result if isinstance(result, bool) else True
            else:
                raise APICallFailed("Composition doesn't support Render")
        except Exception as e:
            raise APICallFailed(f"Failed to render: {e}")
    
    def set_render_range(self, start: int, end: int) -> bool:
        """
        Set render range.
        
        Args:
            start: Start frame
            end: End frame
        
        Returns:
            True if successful
        """
        comp = self.comp
        
        try:
            if hasattr(comp, "SetAttrs"):
                comp.SetAttrs({
                    "COMPN_RenderStart": start,
                    "COMPN_RenderEnd": end,
                })
            else:
                raise APICallFailed("Composition doesn't support SetAttrs")
            return True
        except Exception as e:
            raise APICallFailed(f"Failed to set render range: {e}")
    
    # === Keyframes ===
    
    def set_keyframe(self, tool_name: str, input_name: str, frame: int, value: Any) -> bool:
        """
        Set a keyframe.
        
        Args:
            tool_name: Tool name
            input_name: Input name
            frame: Frame number
            value: Value to set
        
        Returns:
            True if successful
        """
        tool = self.find_tool(tool_name)
        
        try:
            # First, ensure the input has a BezierSpline attached for animation
            input_obj = self._find_input_by_id(tool, tool_name, input_name)
            kf = input_obj.GetKeyFrames()
            if not kf:
                # No spline yet — create one and connect it
                spline = self.comp.BezierSpline()
                if spline:
                    input_obj.ConnectTo(spline)
            # Set input at specific frame (creates keyframe)
            tool.SetInput(input_name, value, frame)
            return True
        except Exception as e:
            raise APICallFailed(f"Failed to set keyframe {tool_name}.{input_name}[{frame}]: {e}")
    
    def list_keyframes(self, tool_name: str, input_name: str) -> List[Dict[str, Any]]:
        """
        List keyframes for an input.
        
        Args:
            tool_name: Tool name
            input_name: Input name
        
        Returns:
            List of keyframe dicts with frame and value
        """
        tool = self.find_tool(tool_name)
        
        try:
            # Get the input object by ID
            input_obj = self._find_input_by_id(tool, tool_name, input_name)
            
            # Try to get keyframes via GetKeyFrames method if available
            if hasattr(input_obj, "GetKeyFrames"):
                keyframes = input_obj.GetKeyFrames()
                if keyframes:
                    result = []
                    # GetKeyFrames returns {index: frame_number}
                    for idx, frame in keyframes.items():
                        frame = int(frame) if float(frame) == int(frame) else frame
                        value = tool.GetInput(input_name, frame)
                        result.append({"frame": frame, "value": value})
                    return result
            
            # Alternative: scan through comp range
            # This is a fallback - may not detect all keyframes
            # For now, return empty list as we can't reliably detect keyframes
            return []
        except Exception as e:
            raise APICallFailed(f"Failed to list keyframes for {tool_name}.{input_name}: {e}")
    
    def delete_keyframe(self, tool_name: str, input_name: str, frame: int) -> bool:
        """
        Delete a keyframe.
        
        Args:
            tool_name: Tool name
            input_name: Input name
            frame: Frame number
        
        Returns:
            True if successful
        """
        tool = self.find_tool(tool_name)
        
        try:
            input_obj = self._find_input_by_id(tool, tool_name, input_name)
            get_keyframes = getattr(input_obj, "GetKeyFrames", None)
            if not callable(get_keyframes):
                raise APICallFailed("Keyframe access not supported for this input")

            before = get_keyframes() or {}
            before_frames = sorted(float(value) for value in before.values())
            target_frame = float(frame)
            if not any(abs(value - target_frame) < 1e-6 for value in before_frames):
                raise APICallFailed(
                    f"No keyframe exists at frame {frame} for {tool_name}.{input_name}.",
                    details={"frame": frame, "keyframes": before_frames},
                )

            expected_after_frames = [
                value for value in before_frames if abs(value - target_frame) >= 1e-6
            ]

            get_connected_output = getattr(input_obj, "GetConnectedOutput", None)
            connected_output = get_connected_output() if callable(get_connected_output) else None
            get_modifier = getattr(connected_output, "GetTool", None) if connected_output else None
            modifier = get_modifier() if callable(get_modifier) else None
            delete_keyframes = getattr(modifier, "DeleteKeyFrames", None) if modifier else None
            if not callable(delete_keyframes):
                raise APICallFailed(
                    "The Fusion input is animated, but its connected modifier does not support keyframe deletion.",
                    details={"tool": tool_name, "input": input_name, "frame": frame},
                )

            delete_keyframes(frame)
            after = get_keyframes() or {}
            after_frames = sorted(float(value) for value in after.values())
            if any(abs(value - target_frame) < 1e-6 for value in after_frames):
                raise APICallFailed(
                    f"DaVinci Resolve returned from keyframe deletion without removing frame {frame}.",
                    details={"frame": frame, "keyframes_before": before_frames, "keyframes_after": after_frames},
                )
            if len(after_frames) != len(expected_after_frames) or any(
                abs(actual - expected) >= 1e-6
                for actual, expected in zip(after_frames, expected_after_frames)
            ):
                raise APICallFailed(
                    f"DaVinci Resolve changed keyframes other than frame {frame} during deletion.",
                    details={
                        "frame": frame,
                        "keyframes_before": before_frames,
                        "keyframes_after": after_frames,
                        "expected_keyframes_after": expected_after_frames,
                    },
                )
            return True
        except APICallFailed:
            raise
        except Exception as e:
            raise APICallFailed(f"Failed to delete keyframe {tool_name}.{input_name}[{frame}]: {e}")
    
    def clear_keyframes(self, tool_name: str, input_name: str) -> bool:
        """
        Clear all keyframes for an input.
        
        Args:
            tool_name: Tool name
            input_name: Input name
        
        Returns:
            True if successful
        """
        tool = self.find_tool(tool_name)
        
        try:
            input_obj = self._find_input_by_id(tool, tool_name, input_name)
            get_keyframes = getattr(input_obj, "GetKeyFrames", None)
            if not callable(get_keyframes):
                raise APICallFailed("Keyframe access not supported for this input")

            before = get_keyframes() or {}
            before_frames = sorted(float(value) for value in before.values())
            comp = self.comp
            current_time = comp.CurrentTime if hasattr(comp, "CurrentTime") else 0
            current_value = tool.GetInput(input_name, current_time)

            if before_frames:
                disconnect = getattr(input_obj, "ConnectTo", None)
                if not callable(disconnect):
                    raise APICallFailed(
                        "The Fusion input is animated, but it does not support disconnecting its keyframe modifier.",
                        details={"tool": tool_name, "input": input_name, "keyframes": before_frames},
                    )
                disconnect_result = disconnect(None)
                if disconnect_result is False:
                    raise APICallFailed(
                        "DaVinci Resolve rejected disconnecting the input's keyframe modifier.",
                        details={"tool": tool_name, "input": input_name},
                    )

                after = get_keyframes() or {}
                after_frames = sorted(float(value) for value in after.values())
                if after_frames:
                    raise APICallFailed(
                        "DaVinci Resolve returned from clearing keyframes without removing every keyframe.",
                        details={"keyframes_before": before_frames, "keyframes_after": after_frames},
                    )

            set_result = tool.SetInput(input_name, current_value)
            if set_result is False:
                raise APICallFailed(
                    "DaVinci Resolve rejected the constant value after clearing keyframes.",
                    details={"tool": tool_name, "input": input_name},
                )
            return True
        except APICallFailed:
            raise
        except Exception as e:
            raise APICallFailed(f"Failed to clear keyframes for {tool_name}.{input_name}: {e}")


    # === Inline Tool Insertion ===

    def connect_tool_inline(self, new_tool) -> bool:
        """
        Insert a tool inline between MediaIn→MediaOut (or last tool before MediaOut).
        
        Finds MediaIn and MediaOut, disconnects MediaOut's input,
        connects MediaIn→new_tool→MediaOut.
        If there's already a chain, inserts before MediaOut.
        """
        comp = self.comp
        
        try:
            tool_items = iter_tool_items(comp, False)
            if not tool_items:
                return False
            
            media_in = None
            media_out = None
            
            for _, tool in tool_items:
                tid = self._get_tool_type(tool)
                if tid == "MediaIn" and media_in is None:
                    media_in = tool
                elif tid == "MediaOut" and media_out is None:
                    media_out = tool
            
            if not media_out:
                return False
            
            # Find what's currently connected to MediaOut's Input
            prev_tool = None
            if hasattr(media_out, "Input"):
                inp = media_out.Input
                if hasattr(inp, "GetConnectedOutput"):
                    connected = inp.GetConnectedOutput()
                    if connected and hasattr(connected, "GetTool"):
                        prev_tool = connected.GetTool()
            
            source = prev_tool or media_in
            if not source:
                return False
            
            # Connect: source → new_tool (Input), new_tool → MediaOut (Input)
            if hasattr(new_tool, "Input"):
                src_out = getattr(source, "Output", None)
                if src_out:
                    new_tool.Input.ConnectTo(src_out)
            
            new_out = getattr(new_tool, "Output", None)
            if new_out and hasattr(media_out, "Input"):
                media_out.Input.ConnectTo(new_out)
            
            return True
        except Exception as e:
            raise APICallFailed(f"Failed to connect tool inline: {e}")

    # === High-Level Effect Helpers ===

    def add_effect_blur(self, strength: float = 5.0) -> Any:
        """Add Blur tool with given strength."""
        tool = self.add_tool("Blur")
        tool.SetInput("XBlurSize", strength)
        tool.SetInput("YBlurSize", strength)
        self.connect_tool_inline(tool)
        return tool

    def add_effect_glow(self, intensity: float = 0.5) -> Any:
        """Add SoftGlow tool."""
        tool = self.add_tool("SoftGlow")
        tool.SetInput("Gain", intensity)
        self.connect_tool_inline(tool)
        return tool

    def add_effect_sharpen(self, amount: float = 0.5) -> Any:
        """Add UnsharpMask tool."""
        tool = self.add_tool("UnsharpMask")
        tool.SetInput("XSize", amount)
        tool.SetInput("YSize", amount)
        self.connect_tool_inline(tool)
        return tool

    def add_effect_transform(
        self,
        zoom: float = 1.0,
        x: float = 0.0,
        y: float = 0.0,
        rotation: float = 0.0,
    ) -> Any:
        """Add Transform tool."""
        tool = self.add_tool("Transform")
        tool.SetInput("Size", zoom)
        tool.SetInput("Center", {1: 0.5 + x, 2: 0.5 + y})
        tool.SetInput("Angle", rotation)
        self.connect_tool_inline(tool)
        return tool

    def add_effect_color_correct(
        self,
        gain_r: float = 1.0,
        gain_g: float = 1.0,
        gain_b: float = 1.0,
        gamma: float = 1.0,
        saturation: float = 1.0,
    ) -> Any:
        """Add ColorCorrector tool."""
        tool = self.add_tool("ColorCorrector")
        tool.SetInput("MasterRGBGain", 1.0)
        tool.SetInput("MasterRedGain", gain_r)
        tool.SetInput("MasterGreenGain", gain_g)
        tool.SetInput("MasterBlueGain", gain_b)
        tool.SetInput("MasterRGBGamma", gamma)
        tool.SetInput("Saturation1", saturation)
        self.connect_tool_inline(tool)
        return tool

    def add_mask_rectangle(
        self,
        center: Tuple[float, float] = (0.5, 0.5),
        width: float = 0.5,
        height: float = 0.5,
        softness: float = 0.0,
    ) -> Any:
        """Add RectangleMask tool."""
        tool = self.add_tool("RectangleMask")
        tool.SetInput("Center", {1: center[0], 2: center[1]})
        tool.SetInput("Width", width)
        tool.SetInput("Height", height)
        if softness > 0:
            tool.SetInput("SoftEdge", softness)
        return tool

    def add_mask_ellipse(
        self,
        center: Tuple[float, float] = (0.5, 0.5),
        width: float = 0.5,
        height: float = 0.5,
        softness: float = 0.0,
    ) -> Any:
        """Add EllipseMask tool."""
        tool = self.add_tool("EllipseMask")
        tool.SetInput("Center", {1: center[0], 2: center[1]})
        tool.SetInput("Width", width)
        tool.SetInput("Height", height)
        if softness > 0:
            tool.SetInput("SoftEdge", softness)
        return tool

    def add_mask_polygon(self, points: List[Tuple[float, float]]) -> Any:
        """Add PolygonMask tool with polyline points."""
        tool = self.add_tool("PolylineMask")
        try:
            attrs = tool.GetAttrs() or {}
            name = str(attrs.get("TOOLS_Name") or getattr(tool, "Name", ""))
            if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) is None:
                raise ValueError("created polygon has no safe native name")
            numeric_points = [(float(px), float(py)) for px, py in points]
            if len(numeric_points) < 3 or any(
                not math.isfinite(value) for point in numeric_points for value in point
            ):
                raise ValueError("polygon points must contain finite coordinates")
            # Fusion's documented LoadSettings table carries this parser flag on each map.
            setting_flags = 0x100100
            point_rows = {"__flags": setting_flags}
            point_rows.update({
                float(index): {
                    "__flags": setting_flags,
                    "Linear": True,
                    "X": px,
                    "Y": py,
                }
                for index, (px, py) in enumerate(numeric_points)
            })
            settings = {
                "__flags": setting_flags,
                "Tools": {
                    "__flags": setting_flags,
                    name: {
                        "__ctor": "PolylineMask",
                        "__flags": setting_flags,
                        "Inputs": {
                            "__flags": setting_flags,
                            "Polyline": {
                                "__ctor": "Input",
                                "__flags": setting_flags,
                                "Value": {
                                    "__ctor": "Polyline",
                                    "__flags": setting_flags,
                                    "Closed": True,
                                    "Points": point_rows,
                                },
                            },
                        },
                    },
                },
            }
            tool.LoadSettings(settings)
            observed = tool.GetBezierPolyline(0)
            observed_points = (
                observed.get("Value", {}).get("Points")
                if isinstance(observed, dict) else None
            )
            observed_value = observed.get("Value") if isinstance(observed, dict) else None
            if (
                not isinstance(observed_value, dict)
                or observed_value.get("Closed") is not True
                or not isinstance(observed_points, dict)
            ):
                raise ValueError("native polygon points were not readable")
            rows = [
                row for _, row in sorted(
                    ((float(key), row) for key, row in observed_points.items() if key != "__flags"),
                    key=lambda entry: entry[0],
                )
            ]
            observed_xy = [(float(row["X"]), float(row["Y"])) for row in rows]
            if observed_xy != numeric_points:
                raise ValueError("native polygon points did not match the request")
            return tool
        except Exception as exc:
            try:
                tool.Delete()
            except Exception:
                pass
            raise APICallFailed(
                "This DaVinci Resolve PolylineMask did not retain the requested polygon points."
            ) from exc

    def add_keyer_chroma(
        self,
        color: str = "green",
        threshold: float = 0.3,
    ) -> Any:
        """Add a DeltaKeyer configured for one chroma background color."""
        tool = self.add_tool("DeltaKeyer")
        # Set key color based on name
        color_map = {
            "green": {1: 0.0, 2: 1.0, 3: 0.0},
            "blue": {1: 0.0, 2: 0.0, 3: 1.0},
            "red": {1: 1.0, 2: 0.0, 3: 0.0},
        }
        key_color = color_map.get(color.lower(), color_map["green"])
        expected = {
            "BackgroundRed": key_color[1],
            "BackgroundGreen": key_color[2],
            "BackgroundBlue": key_color[3],
            "LowThreshold": threshold,
        }
        applied = True
        for input_id, value in expected.items():
            try:
                tool.SetInput(input_id, value)
                actual = tool.GetInput(input_id)
                applied = applied and abs(float(actual) - float(value)) <= 1e-9
            except Exception:
                applied = False
        if not applied:
            try:
                tool.Delete()
            except Exception:
                pass
            raise APICallFailed(
                "This DaVinci Resolve DeltaKeyer did not retain the requested chroma controls."
            )
        self.connect_tool_inline(tool)
        return tool

    def add_tracker(
        self,
        pattern_center: Tuple[float, float] = (0.5, 0.5),
    ) -> Any:
        """Add Tracker tool."""
        tool = self.add_tool("Tracker")
        tool.SetInput("PatternCenter1", {1: pattern_center[0], 2: pattern_center[1]})
        self.connect_tool_inline(tool)
        return tool


def get_fusion_api(conn) -> FusionAPI:
    """
    Get FusionAPI instance.
    
    Args:
        conn: ResolveConnection
    
    Returns:
        FusionAPI instance
    """
    return FusionAPI(conn)
