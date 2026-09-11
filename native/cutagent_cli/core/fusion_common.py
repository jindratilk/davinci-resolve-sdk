from __future__ import annotations

from typing import Any


def serialize_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {str(key): serialize_value(inner) for key, inner in value.items()}
    if isinstance(value, (list, tuple)):
        return [serialize_value(inner) for inner in value]
    try:
        return str(value)
    except Exception:
        return repr(value)


def get_fusion_comp_for_item(item: Any) -> Any | None:
    if item is None:
        return None

    getters = [
        ("GetFusionCompByIndex", 1),
        ("GetFusionCompByIndex", 0),
        ("GetFusionComp", None),
    ]
    seen_indexes: set[int] = set()
    count = 0
    if hasattr(item, "GetFusionCompCount"):
        try:
            count = int(item.GetFusionCompCount() or 0)
        except Exception:
            count = 0

    for idx in range(1, count + 1):
        if idx not in seen_indexes:
            getters.append(("GetFusionCompByIndex", idx))
            seen_indexes.add(idx)
    for idx in range(0, count):
        if idx not in seen_indexes:
            getters.append(("GetFusionCompByIndex", idx))
            seen_indexes.add(idx)

    for method_name, arg in getters:
        method = getattr(item, method_name, None)
        if not callable(method):
            continue
        try:
            comp = method() if arg is None else method(arg)
        except Exception:
            comp = None
        if comp:
            return comp
    return None


def iter_api_items(value: Any) -> list[tuple[Any, Any]]:
    """Normalize Fusion table proxies returned as mappings or sequences."""
    if isinstance(value, dict):
        return list(value.items())
    if isinstance(value, (list, tuple)):
        return list(enumerate(value, 1))
    items = getattr(value, "items", None)
    if callable(items):
        try:
            return list(items())
        except Exception:
            return []
    try:
        return list(enumerate(value, 1))
    except Exception:
        return []


def iter_tool_items(holder: Any, *args: Any) -> list[tuple[Any, Any]]:
    getter = getattr(holder, "GetToolList", None)
    if not callable(getter):
        return []
    call_args = [args] if args else [(), (False,), (True,)]
    for current_args in call_args:
        try:
            raw = getter(*current_args) or {}
        except TypeError:
            continue
        except Exception:
            raw = {}
        return iter_api_items(raw)
    return []


def iter_tool_list(holder: Any, *args: Any) -> list[Any]:
    return [tool for _, tool in iter_tool_items(holder, *args)]


def tool_reg_id(tool: Any) -> str:
    attrs = {}
    getter = getattr(tool, "GetAttrs", None)
    if callable(getter):
        try:
            attrs = getter() or {}
        except Exception:
            attrs = {}
    value = attrs.get("TOOLS_RegID") or attrs.get("REGS_ID") or getattr(tool, "ID", None) or ""
    return str(value or "").strip().lower()


def tool_name(tool: Any, fallback: str | None = None) -> str:
    direct = getattr(tool, "Name", None)
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    getter = getattr(tool, "GetAttrs", None)
    if callable(getter):
        try:
            attrs = getter() or {}
        except Exception:
            attrs = {}
        for key in ("TOOLST_Name", "TOOLS_Name", "TOOLS_ID", "TOOL_Name"):
            value = attrs.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return str(fallback or "Unknown")


def find_tool(holder: Any, name: str) -> Any | None:
    requested = str(name or "").strip()
    if not requested:
        return None
    finder = getattr(holder, "FindTool", None)
    if callable(finder):
        try:
            tool = finder(requested)
        except Exception:
            tool = None
        if tool:
            return tool
    lowered = requested.lower()
    for tool in iter_tool_list(holder, False):
        current_name = tool_name(tool)
        if current_name.lower() == lowered:
            return tool
    return None


def read_tool_input(tool: Any, input_name: str) -> Any:
    getter = getattr(tool, "GetInput", None)
    if callable(getter):
        try:
            return getter(input_name)
        except Exception:
            pass
    try:
        return tool[input_name]
    except Exception:
        return None


def set_tool_input_multi(tool: Any, input_name: str, value: Any, current_time: int | None = None) -> list[dict[str, Any]]:
    attempts: list[dict[str, Any]] = []
    name = tool_name(tool)

    def _append(method: str, *, success: bool, result: Any = None, error: Exception | None = None) -> None:
        row = {
            "target": name,
            "input": input_name,
            "method": method,
            "success": bool(success),
        }
        if error is not None:
            row["error"] = str(error)
        elif result is not None:
            row["result"] = serialize_value(result)
        attempts.append(row)

    setter = getattr(tool, "SetInput", None)
    if callable(setter) and current_time is not None:
        try:
            result = setter(input_name, value, current_time)
            _append("SetInput(value,time)", success=result is not False, result=result)
        except Exception as exc:
            _append("SetInput(value,time)", success=False, error=exc)

    if callable(setter):
        try:
            result = setter(input_name, value)
            _append("SetInput(value)", success=result is not False, result=result)
        except Exception as exc:
            _append("SetInput(value)", success=False, error=exc)

    try:
        tool[input_name] = value
        _append("tool[input]=value", success=True, result=value)
    except Exception as exc:
        _append("tool[input]=value", success=False, error=exc)

    return attempts



def set_item_property_multi(item: Any, property_names: list[str] | tuple[str, ...], value: Any) -> list[dict[str, Any]]:
    attempts: list[dict[str, Any]] = []
    setter = getattr(item, "SetProperty", None)
    if not callable(setter):
        return attempts
    for property_name in property_names:
        try:
            result = setter(property_name, value)
            attempts.append(
                {
                    "target": getattr(item, "GetName", lambda: None)() if hasattr(item, "GetName") else None,
                    "input": property_name,
                    "method": "timeline_item.SetProperty",
                    "success": result is not False,
                    "result": serialize_value(result),
                }
            )
            if result is not False:
                break
        except Exception as exc:
            attempts.append(
                {
                    "target": getattr(item, "GetName", lambda: None)() if hasattr(item, "GetName") else None,
                    "input": property_name,
                    "method": "timeline_item.SetProperty",
                    "success": False,
                    "error": str(exc),
                }
            )
    return attempts
