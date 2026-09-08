"""Lightweight Fusion .setting inspection helpers.

The .setting format is Lua-ish text, not JSON. These helpers intentionally stay
conservative: they do not try to execute or fully parse Lua, but they provide
enough structure to catch the common authoring mistakes that make agent-built
Fusion comps fail only after import/render.
"""

from __future__ import annotations

import re
import tempfile
from pathlib import Path
from typing import Any

from ..errors import ValidationError

_TOOL_HEADER_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*([A-Za-z_][A-Za-z0-9_]*)\s*\{")
_SOURCE_OP_RE = re.compile(r'SourceOp\s*=\s*"([^"]+)"')
_SOURCE_INPUT_RE = re.compile(r'([A-Za-z_][A-Za-z0-9_]*)\s*=\s*Input\s*\{[^{}]*SourceOp\s*=\s*"([^"]+)"')
_POINT_RE = re.compile(r"\{\s*X\s*=\s*(-?\d+(?:\.\d+)?)\s*,\s*Y\s*=\s*(-?\d+(?:\.\d+)?)")
_VIEWINFO_POS_RE = re.compile(
    r"ViewInfo\s*=\s*OperatorInfo\s*\{\s*Pos\s*=\s*\{\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*\}\s*\}",
    re.MULTILINE,
)
_VIEWINFO_LINE_RE = re.compile(
    r"(?m)^[ \t]*ViewInfo\s*=\s*OperatorInfo\s*\{\s*Pos\s*=\s*\{\s*-?\d+(?:\.\d+)?\s*,\s*-?\d+(?:\.\d+)?\s*\}\s*\},?[ \t]*(?:\r?\n)?"
)

ANIMATION_CLASSES = {"BezierSpline", "PolyPath"}
FLOW_LAYOUT_EXCLUDED_CLASSES = {"BezierSpline", "PolyPath", "StyledTextCLS"}
_STATUS_KEY_PARTS = ("ERROR", "ERR", "FAIL", "INVALID", "STATUS", "WARN")
_BAD_STATUS_WORDS = ("error", "failed", "fail", "invalid", "missing", "offline", "unavailable")


def resolve_setting_path(path: str) -> Path:
    raw = str(path or "").strip()
    if not raw:
        raise ValidationError(".setting path must not be empty.", details={"path": path})
    resolved = Path(raw).expanduser()
    if not resolved.is_absolute():
        resolved = Path.cwd() / resolved
    resolved = resolved.resolve(strict=False)
    if not resolved.is_file():
        raise ValidationError(".setting file was not found.", details={"path": str(resolved)})
    return resolved


def normalized_center_to_polypath(x: float, y: float) -> dict[str, float]:
    return {"X": float(x) - 0.5, "Y": float(y) - 0.5}


def polypath_to_normalized_center(x: float, y: float) -> dict[str, float]:
    return {"CenterX": float(x) + 0.5, "CenterY": float(y) + 0.5}


def _extract_balanced_block(lines: list[str], start: int) -> tuple[str, int]:
    depth = 0
    parts: list[str] = []
    for index in range(start, len(lines)):
        line = lines[index]
        parts.append(line)
        depth += line.count("{") - line.count("}")
        if depth <= 0:
            return "".join(parts), index
    return "".join(parts), len(lines) - 1


def _iter_tool_blocks(text: str) -> list[dict[str, Any]]:
    lines = text.splitlines(keepends=True)
    tools: list[dict[str, Any]] = []
    index = 0
    while index < len(lines):
        match = _TOOL_HEADER_RE.match(lines[index])
        if not match:
            index += 1
            continue
        name, cls = match.groups()
        block, end_index = _extract_balanced_block(lines, index)
        tools.append(
            {
                "name": name,
                "class": cls,
                "start_line": index + 1,
                "end_line": end_index + 1,
                "block": block,
            }
        )
        index = end_index + 1
    return tools


def _poly_points(block: str) -> list[dict[str, float]]:
    return [{"X": float(x), "Y": float(y)} for x, y in _POINT_RE.findall(block)]


def _view_position(block: str) -> dict[str, float] | None:
    match = _VIEWINFO_POS_RE.search(block)
    if not match:
        return None
    return {"x": float(match.group(1)), "y": float(match.group(2))}


def is_flow_layout_tool(tool_class: str) -> bool:
    return str(tool_class or "") not in FLOW_LAYOUT_EXCLUDED_CLASSES


def _is_media_output_tool(tool: dict[str, Any]) -> bool:
    tool_class = str(tool.get("class") or "")
    tool_name = str(tool.get("name") or "")
    return tool_class == "MediaOut" or (tool_class == "Saver" and tool_name.startswith("MediaOut"))


def _position_key(position: dict[str, float]) -> tuple[float, float]:
    return (round(float(position["x"]), 6), round(float(position["y"]), 6))


def _flow_layout_summary(tools: list[dict[str, Any]]) -> dict[str, Any]:
    flow_tools = [tool for tool in tools if is_flow_layout_tool(str(tool.get("class") or ""))]
    missing = [
        {"name": tool["name"], "class": tool["class"], "line": tool["start_line"]}
        for tool in flow_tools
        if tool.get("view_position") is None
    ]
    positions: dict[tuple[float, float], list[dict[str, Any]]] = {}
    for tool in flow_tools:
        position = tool.get("view_position")
        if position is None:
            continue
        positions.setdefault(_position_key(position), []).append(tool)
    duplicates = []
    for (x, y), positioned_tools in sorted(positions.items(), key=lambda item: (item[0][0], item[0][1])):
        if len(positioned_tools) <= 1:
            continue
        duplicates.append(
            {
                "position": {"x": x, "y": y},
                "tools": [
                    {"name": tool["name"], "class": tool["class"], "line": tool["start_line"]}
                    for tool in positioned_tools
                ],
            }
        )

    warnings: list[dict[str, Any]] = []
    if missing:
        warnings.append(
            {
                "code": "fusion_flow_layout_missing",
                "severity": "warning",
                "tool_count": len(missing),
                "tools": missing,
                "message": "One or more visible Fusion flow tools do not have ViewInfo node-graph positions.",
            }
        )
    if duplicates:
        warnings.append(
            {
                "code": "fusion_flow_layout_duplicate_position",
                "severity": "warning",
                "position_count": len(duplicates),
                "positions": duplicates,
                "message": "Multiple visible Fusion flow tools share the same node-graph position.",
            }
        )
    return {
        "flow_tool_count": len(flow_tools),
        "positioned_tool_count": len(flow_tools) - len(missing),
        "missing_viewinfo": missing,
        "missing_viewinfo_count": len(missing),
        "duplicate_positions": duplicates,
        "duplicate_position_count": len(duplicates),
        "layout_warnings": warnings,
        "healthy": not missing and not duplicates,
    }


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    try:
        return str(value)
    except Exception:
        return f"<{value.__class__.__name__}>"


def _status_attr_is_bad(key: str, value: Any) -> bool:
    key_upper = str(key).upper()
    if value is None or value is False or value == "":
        return False
    if isinstance(value, (int, float)):
        if any(part in key_upper for part in ("ERROR", "ERR", "FAIL", "INVALID")):
            return value != 0
        return False
    text = str(value).strip().lower()
    if not text or text in {"0", "false", "none", "ok", "okay", "valid", "success", "successful"}:
        return False
    if any(part in key_upper for part in ("ERROR", "ERR", "FAIL", "INVALID")):
        return True
    if "STATUS" in key_upper:
        return any(word in text for word in _BAD_STATUS_WORDS)
    return False


def runtime_tool_status_from_attrs(name: str, tool_class: str, attrs: dict[str, Any] | None) -> dict[str, Any]:
    """Summarize DaVinci Resolve runtime status-like tool attrs without assuming key parity across versions."""
    attrs = attrs or {}
    status_attrs = {
        str(key): _json_safe(value)
        for key, value in attrs.items()
        if any(part in str(key).upper() for part in _STATUS_KEY_PARTS)
    }
    error_indicators = [
        {"key": key, "value": value}
        for key, value in status_attrs.items()
        if _status_attr_is_bad(key, value)
    ]
    if status_attrs:
        detection = "status_attrs"
    else:
        detection = "no_status_attrs_exposed"
    return {
        "name": str(name),
        "type": str(tool_class),
        "attrs_readable": True,
        "status_detection": detection,
        "status_attrs": status_attrs,
        "error_indicators": error_indicators,
        "ok": not error_indicators,
    }


def inspect_setting(path: str | Path) -> dict[str, Any]:
    resolved = resolve_setting_path(str(path))
    text = resolved.read_text(encoding="utf-8", errors="replace")
    tools = _iter_tool_blocks(text)
    name_to_class = {tool["name"]: tool["class"] for tool in tools}
    outgoing: dict[str, list[dict[str, str]]] = {tool["name"]: [] for tool in tools}
    incoming: dict[str, list[dict[str, str]]] = {tool["name"]: [] for tool in tools}
    missing: list[dict[str, str]] = []
    animated_inputs: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    for tool in tools:
        tool["view_position"] = _view_position(tool["block"])
        tool["is_flow_tool"] = is_flow_layout_tool(tool["class"])
        source_ops = sorted(set(_SOURCE_OP_RE.findall(tool["block"])))
        tool["source_ops"] = source_ops
        tool["source_inputs"] = [
            {"input": input_name, "source_op": source_op}
            for input_name, source_op in _SOURCE_INPUT_RE.findall(tool["block"])
        ]
        if tool["class"] == "PolyPath":
            tool["points"] = _poly_points(tool["block"])
        for source_op in source_ops:
            edge = {"from": source_op, "to": tool["name"]}
            if source_op in outgoing:
                outgoing[source_op].append({"to": tool["name"], "to_class": tool["class"]})
                incoming[tool["name"]].append({"from": source_op, "from_class": name_to_class.get(source_op, "")})
            else:
                missing.append(edge)
        for source_input in tool["source_inputs"]:
            source_cls = name_to_class.get(source_input["source_op"])
            if source_cls in ANIMATION_CLASSES:
                animated_inputs.append(
                    {
                        "tool": tool["name"],
                        "tool_class": tool["class"],
                        "input": source_input["input"],
                        "source_op": source_input["source_op"],
                        "source_class": source_cls,
                    }
                )

    media_out = [tool for tool in tools if _is_media_output_tool(tool)]
    dead_tools = []
    unused_animation_tools = []
    for tool in tools:
        if _is_media_output_tool(tool):
            continue
        refs = outgoing.get(tool["name"], [])
        if not refs:
            if tool["class"] in ANIMATION_CLASSES:
                unused_animation_tools.append(tool["name"])
            else:
                dead_tools.append(tool["name"])

    for tool in tools:
        block = tool["block"]
        if tool["class"] == "PolylineMask" and re.search(r"Length\s*=\s*Input\s*\{[^{}]*SourceOp", block):
            warnings.append(
                {
                    "code": "polyline_length_write_on",
                    "severity": "info",
                    "tool": tool["name"],
                    "line": tool["start_line"],
                    "message": "Animated PolylineMask Length can be fragile in imported .setting comps; verify with exported frames or use a reveal mask fallback.",
                }
            )
        if tool["class"] == "TextPlus" and re.search(r"Alpha1\s*=\s*Input\s*\{[^{}]*SourceOp", block):
            warnings.append(
                {
                    "code": "textplus_alpha_reveal",
                    "severity": "warning",
                    "tool": tool["name"],
                    "line": tool["start_line"],
                    "message": "Animated Text+ Alpha1 may not be the most reliable reveal path; prefer animating Merge.Blend for visibility reveals.",
                }
            )
        if tool["class"] == "PolyPath":
            points = tool.get("points") or []
            if points and all(0 <= point["X"] <= 1 and 0 <= point["Y"] <= 1 for point in points):
                warnings.append(
                    {
                        "code": "polypath_maybe_normalized_center_coords",
                        "severity": "warning",
                        "tool": tool["name"],
                        "line": tool["start_line"],
                        "message": "PolyPath points are all 0..1; Fusion path positions are usually relative to center, so convert normalized Center values with X=x-0.5, Y=y-0.5.",
                    }
                )

    layout = _flow_layout_summary(tools)
    warnings.extend(layout["layout_warnings"])

    errors: list[dict[str, Any]] = []
    for edge in missing:
        errors.append(
            {
                "code": "missing_source_op",
                "severity": "error",
                "tool": edge["to"],
                "source_op": edge["from"],
                "message": f"{edge['to']} references missing SourceOp {edge['from']}.",
            }
        )
    if not media_out:
        errors.append(
            {
                "code": "missing_media_out",
                "severity": "error",
                "message": "No MediaOut tool was found.",
            }
        )
    elif all(not incoming.get(tool["name"]) for tool in media_out):
        errors.append(
            {
                "code": "disconnected_media_out",
                "severity": "error",
                "tools": [tool["name"] for tool in media_out],
                "message": "MediaOut exists but has no SourceOp input.",
            }
        )

    tool_rows = [
        {
            "name": tool["name"],
            "class": tool["class"],
            "start_line": tool["start_line"],
            "end_line": tool["end_line"],
            "source_ops": tool["source_ops"],
            "view_position": tool.get("view_position"),
            "is_flow_tool": bool(tool.get("is_flow_tool")),
            "outgoing_count": len(outgoing.get(tool["name"], [])),
            "incoming_count": len(incoming.get(tool["name"], [])),
        }
        for tool in tools
    ]
    return {
        "path": str(resolved),
        "tool_count": len(tools),
        "tools": tool_rows,
        "media_out": [{"name": tool["name"], "incoming": incoming.get(tool["name"], [])} for tool in media_out],
        "connections": [{"from": source, "to": edge["to"], "to_class": edge["to_class"]} for source, edges in outgoing.items() for edge in edges],
        "animated_inputs": animated_inputs,
        "dead_tools": dead_tools,
        "unused_animation_tools": unused_animation_tools,
        "layout": layout,
        "warnings": warnings,
        "errors": errors,
        "valid": not errors,
    }


def setting_summary(path: str | Path, *, include_connections: bool = False, include_animated: bool = False) -> dict[str, Any]:
    inspected = inspect_setting(path)
    class_counts: dict[str, int] = {}
    for tool in inspected["tools"]:
        class_counts[tool["class"]] = class_counts.get(tool["class"], 0) + 1
    payload: dict[str, Any] = {
        "path": inspected["path"],
        "valid": inspected["valid"],
        "tool_count": inspected["tool_count"],
        "class_counts": dict(sorted(class_counts.items())),
        "media_out": inspected["media_out"],
        "dead_tool_count": len(inspected["dead_tools"]),
        "unused_animation_tool_count": len(inspected["unused_animation_tools"]),
        "warning_count": len(inspected["warnings"]),
        "error_count": len(inspected["errors"]),
        "layout": inspected["layout"],
    }
    if include_connections:
        payload["connections"] = inspected["connections"]
        payload["dead_tools"] = inspected["dead_tools"]
    if include_animated:
        payload["animated_inputs"] = inspected["animated_inputs"]
        payload["unused_animation_tools"] = inspected["unused_animation_tools"]
    return payload


def _format_number(value: float) -> str:
    number = float(value)
    if number.is_integer():
        return str(int(number))
    return f"{number:.3f}".rstrip("0").rstrip(".")


def _position_line(block: str, x: float, y: float) -> str:
    first_line = block.splitlines()[0] if block.splitlines() else ""
    indent = re.match(r"^(\s*)", first_line).group(1) if re.match(r"^(\s*)", first_line) else ""
    return f"{indent}    ViewInfo = OperatorInfo {{ Pos = {{ {_format_number(x)}, {_format_number(y)} }} }},\n"


def _append_lua_field_separator(line: str) -> str:
    if line.endswith("\r\n"):
        return f"{line[:-2].rstrip()},\r\n"
    if line.endswith("\n"):
        return f"{line[:-1].rstrip()},\n"
    return f"{line.rstrip()},"


def _ensure_previous_lua_field_separator(lines: list[str], insert_at: int) -> None:
    previous = insert_at - 1
    while previous > 0 and not lines[previous].strip():
        previous -= 1
    stripped = lines[previous].strip() if previous >= 0 else ""
    if stripped and not stripped.endswith((",", ";", "{")):
        lines[previous] = _append_lua_field_separator(lines[previous])


def _replace_tool_viewinfo(block: str, x: float, y: float) -> str:
    viewinfo = _position_line(block, x, y)
    if _VIEWINFO_POS_RE.search(block):
        replaced, count = _VIEWINFO_LINE_RE.subn(viewinfo, block, count=1)
        if count:
            return replaced
        return _VIEWINFO_POS_RE.sub(viewinfo.strip().rstrip(","), block, count=1)

    lines = block.splitlines(keepends=True)
    if len(lines) > 1:
        insert_at = len(lines) - 1
        while insert_at > 0 and not lines[insert_at].strip():
            insert_at -= 1
        _ensure_previous_lua_field_separator(lines, insert_at)
        lines.insert(insert_at, viewinfo)
        return "".join(lines)

    stripped = block.rstrip("\n")
    newline = "\n" if block.endswith("\n") else ""
    last_brace = stripped.rfind("}")
    if last_brace < 0:
        return block
    prefix = stripped[:last_brace].rstrip()
    suffix = stripped[last_brace:]
    separator = "\n" if prefix.endswith((",", "{")) else ",\n"
    return f"{prefix}{separator}{viewinfo}{suffix}{newline}"


def _auto_layout_positions(tools: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    name_to_tool = {tool["name"]: tool for tool in tools}
    flow_names = {tool["name"] for tool in tools if is_flow_layout_tool(tool["class"])}
    source_map: dict[str, list[str]] = {
        tool["name"]: [source for source in tool.get("source_ops", []) if source in flow_names]
        for tool in tools
        if tool["name"] in flow_names
    }
    order = {tool["name"]: index for index, tool in enumerate(tools)}
    levels: dict[str, int] = {}
    visiting: set[str] = set()

    def _level(name: str) -> int:
        if name in levels:
            return levels[name]
        if name in visiting:
            return 0
        visiting.add(name)
        deps = [source for source in source_map.get(name, []) if source in name_to_tool]
        value = 0 if not deps else max(_level(source) for source in deps) + 1
        visiting.discard(name)
        levels[name] = value
        return value

    for name in sorted(flow_names, key=lambda item: order.get(item, 0)):
        _level(name)

    non_media_levels = [level for name, level in levels.items() if not _is_media_output_tool(name_to_tool.get(name, {}))]
    far_right_level = (max(non_media_levels) + 1) if non_media_levels else 0
    for name in flow_names:
        if _is_media_output_tool(name_to_tool.get(name, {})):
            levels[name] = max(levels.get(name, 0), far_right_level)

    columns: dict[int, list[str]] = {}
    for name, level in levels.items():
        columns.setdefault(level, []).append(name)
    for names in columns.values():
        names.sort(key=lambda item: order.get(item, 0))

    positions: dict[str, dict[str, float]] = {}
    for level in sorted(columns):
        names = columns[level]
        center_offset = (len(names) - 1) / 2.0
        for row, name in enumerate(names):
            positions[name] = {
                "x": float(level * 220),
                "y": float((row - center_offset) * 120),
            }
    return positions


def _write_auto_layout_setting(source_path: Path, inspected: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    text = source_path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines(keepends=True)
    tool_blocks = _iter_tool_blocks(text)
    for tool in tool_blocks:
        tool["source_ops"] = sorted(set(_SOURCE_OP_RE.findall(tool["block"])))
    positions = _auto_layout_positions(tool_blocks)

    replacements = {
        tool["name"]: _replace_tool_viewinfo(tool["block"], positions[tool["name"]]["x"], positions[tool["name"]]["y"])
        for tool in tool_blocks
        if tool["name"] in positions
    }
    for tool in sorted(tool_blocks, key=lambda item: item["start_line"], reverse=True):
        replacement = replacements.get(tool["name"])
        if replacement is None:
            continue
        lines[tool["start_line"] - 1 : tool["end_line"]] = [replacement]

    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".setting", encoding="utf-8") as handle:
        handle.write("".join(lines))
        import_path = handle.name
    repaired = inspect_setting(import_path)
    return import_path, repaired


def prepare_setting_for_import(path: str | Path) -> dict[str, Any]:
    """Return an import-ready .setting path, repairing only unusable flow layout."""
    source_path = resolve_setting_path(str(path))
    inspected = inspect_setting(source_path)
    layout_before = inspected.get("layout") or {}
    base_payload: dict[str, Any] = {
        "auto_layout_applied": False,
        "source_path": str(source_path),
        "import_path": str(source_path),
        "cleanup_path": None,
        "cleanup": {"temporary_setting_deleted": False},
        "flow_tool_count": int(layout_before.get("flow_tool_count") or 0),
        "positioned_tool_count_before": int(layout_before.get("positioned_tool_count") or 0),
        "missing_viewinfo_before": int(layout_before.get("missing_viewinfo_count") or 0),
        "duplicate_positions_before": int(layout_before.get("duplicate_position_count") or 0),
        "layout_warnings_before": layout_before.get("layout_warnings") or [],
        "layout_before": layout_before,
    }
    if bool(layout_before.get("healthy", True)):
        base_payload["layout_after"] = layout_before
        return base_payload

    import_path, repaired = _write_auto_layout_setting(source_path, inspected)
    layout_after = repaired.get("layout") or {}
    base_payload.update(
        {
            "auto_layout_applied": True,
            "import_path": str(import_path),
            "cleanup_path": str(import_path),
            "positioned_tool_count_after": int(layout_after.get("positioned_tool_count") or 0),
            "missing_viewinfo_after": int(layout_after.get("missing_viewinfo_count") or 0),
            "duplicate_positions_after": int(layout_after.get("duplicate_position_count") or 0),
            "layout_warnings_after": layout_after.get("layout_warnings") or [],
            "layout_after": layout_after,
        }
    )
    return base_payload
