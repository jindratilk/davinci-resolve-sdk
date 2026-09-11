from __future__ import annotations

from typing import Any

from ..errors import APICallFailed
from ..utils.template import parse_styled_text
from .fusion_common import (
    find_tool,
    get_fusion_comp_for_item,
    iter_tool_list,
    read_tool_input,
    serialize_value,
    set_item_property_multi,
    set_tool_input_multi,
    tool_name,
    tool_reg_id,
)

TEXT_INPUT_FALLBACKS = ("StyledText", "Text", "Title", "TitleText", "TextLine", "Line1", "Subtitle")
TEXT_TIMELINE_PROPERTY_FALLBACKS = TEXT_INPUT_FALLBACKS
ROLE_TOOL_CANDIDATES = {
    "body": ("Body", "Text", "Text1", "TextPlus1", "Template"),
    "header": ("Header", "Title", "Text1", "TextPlus1", "Template"),
}
HEADER_DEFAULT_NAME = "cutagent-explanation-header"
BODY_DEFAULT_NAME = "cutagent-explanation-body"


def normalize_role_text(
    text: str,
    *,
    role: str | None = None,
    uppercase: bool = False,
    double_spaces: bool = False,
) -> str:
    normalized = str(text or "")
    if role == "header" and uppercase:
        normalized = normalized.upper()
    if role == "header" and double_spaces:
        normalized = normalized.replace(" ", "  ")
    return normalized


def parse_text_value(text: str, *, bold_style: str = "ExtraBold", styled: bool | None = None) -> dict[str, Any]:
    requested = str(text or "")
    has_bold_ranges = "**" in requested
    use_styled = bool(styled) or has_bold_ranges
    clean_text = requested
    styling = []
    styled_range_count = requested.count("**") // 2 if has_bold_ranges else 0
    if use_styled:
        clean_text, styling = parse_styled_text(requested, bold_style=bold_style)
    return {
        "requested_text": requested,
        "clean_text": clean_text,
        "has_bold_ranges": has_bold_ranges,
        "styled_range_count": styled_range_count,
        "styling": styling,
        "bold_style": bold_style,
        "styled": use_styled,
    }


def _tool_input_names(tool: Any) -> set[str]:
    getter = getattr(tool, "GetInputList", None)
    if not callable(getter):
        return set()
    attempts = [(), (False,), (True,), (False, "TextTool"), (True, "TextTool")]
    for args in attempts:
        try:
            raw = getter(*args) or {}
        except TypeError:
            continue
        except Exception:
            raw = {}
        if isinstance(raw, dict):
            names = {str(key) for key in raw.keys() if isinstance(key, str)}
            for input_object in raw.values():
                attrs_getter = getattr(input_object, "GetAttrs", None)
                if not callable(attrs_getter):
                    continue
                try:
                    attrs = attrs_getter() or {}
                except Exception:
                    continue
                for key in ("INPS_ID", "INPS_Name"):
                    value = attrs.get(key) if isinstance(attrs, dict) else None
                    if isinstance(value, str) and value:
                        names.add(value)
            return names
        if isinstance(raw, (list, tuple, set)):
            return {str(value) for value in raw}
    return set()


def _text_tool_score(tool: Any, *, requested_names: list[str]) -> tuple[int, int]:
    name = tool_name(tool).lower()
    reg_id = tool_reg_id(tool)
    inputs = {value.lower() for value in _tool_input_names(tool)}

    for index, candidate in enumerate(requested_names):
        lowered = str(candidate or "").strip().lower()
        if lowered and name == lowered:
            return (0, index)
        if lowered and name.startswith(lowered):
            return (1, index)
    if reg_id == "textplus":
        return (2, 0)
    if "styledtext" in inputs or "text" in inputs:
        return (3, 0)
    if any(token in name or token in reg_id for token in ("text", "title", "subtitle")):
        return (4, 0)
    return (99, 99)


def collect_text_tools(comp: Any) -> list[Any]:
    tools = []
    for args in ((), (False,), (True,), (False, "TextTool"), (True, "TextTool"), (False, "TextPlus")):
        for tool in iter_tool_list(comp, *args):
            if tool is None or any(id(tool) == id(existing) for existing in tools):
                continue
            tools.append(tool)
    return tools


def select_text_tool(
    comp: Any,
    *,
    explicit_tool: str | None = None,
    tool_candidates: list[str] | None = None,
    role: str | None = None,
) -> tuple[Any | None, dict[str, Any]]:
    if explicit_tool:
        direct = find_tool(comp, explicit_tool)
        if direct is not None:
            return direct, {"selected_by": "explicit_tool", "tool_selected": tool_name(direct)}

    requested_names = list(tool_candidates or [])
    requested_names.extend(value for value in ROLE_TOOL_CANDIDATES.get(str(role or "").lower(), ()) if value not in requested_names)
    tools = collect_text_tools(comp)
    scored: list[tuple[tuple[int, int], Any]] = []
    for tool in tools:
        score = _text_tool_score(tool, requested_names=requested_names)
        if score[0] < 99:
            scored.append((score, tool))
    if not scored:
        return None, {
            "selected_by": None,
            "requested_names": requested_names,
            "available_tools": [tool_name(tool) for tool in tools],
        }
    scored.sort(key=lambda item: item[0])
    selected = scored[0][1]
    return selected, {
        "selected_by": "candidate_score",
        "requested_names": requested_names,
        "tool_selected": tool_name(selected),
        "available_tools": [tool_name(tool) for tool in tools],
    }


def find_cls_tool(comp: Any, tool_candidates: list[str] | None = None) -> Any | None:
    explicit = tool_candidates or []
    for candidate in explicit:
        tool = find_tool(comp, candidate)
        if tool is not None:
            return tool
    for tool in collect_text_tools(comp):
        name = tool_name(tool).lower()
        reg_id = tool_reg_id(tool)
        if any(token in name or token in reg_id for token in ("styledtextcls", "characterlevelstyling", "cls")):
            return tool
    return find_tool(comp, "CharacterLevelStyling1")


def build_text_set_plan(
    *,
    selector: dict[str, Any],
    text: str,
    role: str | None,
    explicit_tool: str | None,
    tool_candidates: list[str] | None,
    input_names: list[str] | None,
    uppercase: bool,
    double_spaces: bool,
    bold_style: str,
) -> dict[str, Any]:
    normalized_text = normalize_role_text(text, role=role, uppercase=uppercase, double_spaces=double_spaces)
    parsed = parse_text_value(normalized_text, bold_style=bold_style)
    return {
        "selector": selector,
        "role": role,
        "requested_text": text,
        "clean_text": parsed["clean_text"],
        "has_bold_ranges": parsed["has_bold_ranges"],
        "styled_range_count": parsed["styled_range_count"],
        "bold_style": bold_style,
        "tool_selection": {
            "explicit_tool": explicit_tool,
            "tool_candidates": list(tool_candidates or []),
            "role_candidates": list(ROLE_TOOL_CANDIDATES.get(str(role or "").lower(), ())),
        },
        "input_fallbacks": list(input_names or TEXT_INPUT_FALLBACKS),
        "uppercase": bool(uppercase),
        "double_spaces": bool(double_spaces),
    }


def set_text_on_item(
    item: Any,
    *,
    text: str,
    role: str | None = None,
    explicit_tool: str | None = None,
    tool_candidates: list[str] | None = None,
    input_names: list[str] | None = None,
    uppercase: bool = False,
    double_spaces: bool = False,
    bold_style: str = "ExtraBold",
    styled: bool | None = None,
    cls_tool_candidates: list[str] | None = None,
    require_exact_target: bool = False,
) -> dict[str, Any]:
    comp = get_fusion_comp_for_item(item)
    if comp is None:
        raise APICallFailed(
            "No Fusion composition found for text update.",
            details={"role": role, "recovery_hint": "Use a clip/template that already contains a Text+ or Fusion text tool."},
        )

    return set_text_on_comp(
        item,
        comp,
        text=text,
        role=role,
        explicit_tool=explicit_tool,
        tool_candidates=tool_candidates,
        input_names=input_names,
        uppercase=uppercase,
        double_spaces=double_spaces,
        bold_style=bold_style,
        styled=styled,
        cls_tool_candidates=cls_tool_candidates,
        require_exact_target=require_exact_target,
    )


def set_text_on_comp(
    item: Any,
    comp: Any,
    *,
    text: str,
    role: str | None = None,
    explicit_tool: str | None = None,
    tool_candidates: list[str] | None = None,
    input_names: list[str] | None = None,
    uppercase: bool = False,
    double_spaces: bool = False,
    bold_style: str = "ExtraBold",
    styled: bool | None = None,
    cls_tool_candidates: list[str] | None = None,
    require_exact_target: bool = False,
) -> dict[str, Any]:
    """Set text on one already-bound Fusion composition."""

    current_time = None
    try:
        current_time = int(getattr(comp, "CurrentTime", 0))
    except Exception:
        current_time = 0

    if require_exact_target:
        requested_inputs = list(input_names or [])
        selected_exact = find_tool(comp, str(explicit_tool or "")) if explicit_tool else None
        available_inputs = _tool_input_names(selected_exact) if selected_exact is not None else set()
        if selected_exact is None or len(requested_inputs) != 1 or requested_inputs[0] not in available_inputs:
            raise APICallFailed(
                "Exact Fusion text tool or input was not found.",
                details={"tool": explicit_tool, "input": requested_inputs[0] if len(requested_inputs) == 1 else None},
            )

    normalized_text = normalize_role_text(text, role=role, uppercase=uppercase, double_spaces=double_spaces)
    parsed = parse_text_value(normalized_text, bold_style=bold_style, styled=styled)
    selected_tool, selection_meta = select_text_tool(
        comp,
        explicit_tool=explicit_tool,
        tool_candidates=list(tool_candidates or []),
        role=role,
    )

    attempts: list[dict[str, Any]] = []
    input_applied = None
    if selected_tool is not None:
        for input_name in list(input_names or TEXT_INPUT_FALLBACKS):
            current_attempts = set_tool_input_multi(selected_tool, input_name, parsed["clean_text"], current_time=current_time)
            attempts.extend(current_attempts)
            if any(row.get("success") for row in current_attempts):
                input_applied = input_name
                break
    property_attempts = []
    if input_applied is None and not require_exact_target:
        property_attempts = set_item_property_multi(item, list(TEXT_TIMELINE_PROPERTY_FALLBACKS), parsed["clean_text"])
        attempts.extend(property_attempts)
        for row in property_attempts:
            if row.get("success"):
                input_applied = row.get("input")
                break
    if selected_tool is None and input_applied is None:
        raise APICallFailed(
            "No Fusion/Text tool found for text update.",
            details={
                "role": role,
                "requested_text": text,
                "selection": selection_meta,
                "recovery_hint": "Use `cutagent fusion tool list --json` to inspect available text tools or provide --tool explicitly.",
            },
        )

    cls_tool = None
    cls_attempts: list[dict[str, Any]] = []
    cls_applied = False
    styled_status = "not_requested"
    if parsed["styled"]:
        styled_status = "partial" if parsed["styled_range_count"] else "not_requested"
        cls_tool = find_cls_tool(comp, tool_candidates=list(cls_tool_candidates or []))
        if cls_tool is not None and parsed["styled_range_count"]:
            cls_attempts.extend(set_tool_input_multi(cls_tool, "Text", parsed["clean_text"], current_time=current_time))
            cls_attempts.extend(set_tool_input_multi(cls_tool, "CharacterLevelStyling", parsed["styling"], current_time=current_time))
            cls_applied = any(
                row.get("success") and row.get("input") == "CharacterLevelStyling"
                for row in cls_attempts
            )
            styled_status = "applied" if cls_applied else "partial"

    readback = {
        "tool_selected": tool_name(selected_tool) if selected_tool is not None else None,
        "input_applied": input_applied,
        "value": serialize_value(read_tool_input(selected_tool, input_applied)) if selected_tool is not None and input_applied else None,
        "cls_tool": tool_name(cls_tool) if cls_tool is not None else None,
        "cls_text": serialize_value(read_tool_input(cls_tool, "Text")) if cls_tool is not None else None,
        "cls_value": serialize_value(read_tool_input(cls_tool, "CharacterLevelStyling")) if cls_tool is not None else None,
    }

    verified = bool(input_applied)
    return {
        "role": role,
        "requested_text": text,
        "clean_text": parsed["clean_text"],
        "has_bold_ranges": parsed["has_bold_ranges"],
        "styled_range_count": parsed["styled_range_count"],
        "bold_style": bold_style,
        "tool_selected": tool_name(selected_tool) if selected_tool is not None else None,
        "tool_selection": selection_meta,
        "input_applied": input_applied,
        "attempts": attempts,
        "cls_attempts": cls_attempts,
        "cls_applied": cls_applied,
        "styled_status": styled_status,
        "readback": readback,
        "verified": verified,
        "uppercase": bool(uppercase),
        "double_spaces": bool(double_spaces),
        "updated": verified or cls_applied,
    }


def set_center_on_item(
    item: Any,
    *,
    center_x: float,
    center_y: float,
    role: str | None = None,
    explicit_tool: str | None = None,
    tool_candidates: list[str] | None = None,
) -> dict[str, Any]:
    comp = get_fusion_comp_for_item(item)
    if comp is None:
        raise APICallFailed(
            "No Fusion composition found for center update.",
            details={"role": role, "recovery_hint": "Use a clip/template that already contains a Text+ or Fusion text tool."},
        )
    current_time = None
    try:
        current_time = int(getattr(comp, "CurrentTime", 0))
    except Exception:
        current_time = 0
    selected_tool, selection_meta = select_text_tool(
        comp,
        explicit_tool=explicit_tool,
        tool_candidates=list(tool_candidates or []),
        role=role,
    )
    if selected_tool is None:
        raise APICallFailed(
            "No Fusion/Text tool found for center update.",
            details={
                "role": role,
                "selection": selection_meta,
                "recovery_hint": "Use `cutagent fusion tool list --json` to inspect available text tools or provide --tool explicitly.",
            },
        )
    center_value = [float(center_x), float(center_y)]
    attempts = set_tool_input_multi(selected_tool, "Center", center_value, current_time=current_time)
    applied = any(row.get("success") for row in attempts)
    readback = serialize_value(read_tool_input(selected_tool, "Center"))
    return {
        "requested": {"x": float(center_x), "y": float(center_y)},
        "applied": applied,
        "tool_selected": tool_name(selected_tool),
        "tool_selection": selection_meta,
        "attempts": attempts,
        "readback": readback,
    }
