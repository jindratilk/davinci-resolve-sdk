"""High-level text/title helpers for agent-facing CLI commands."""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Optional

from ..errors import APICallFailed, ValidationError
from ..output import set_verification_status
from ..policy import require_api_method
from ..utils.template import escape_lua_string, parse_styled_text, render_setting_template
from ..utils.time_ref import parse_record_frame
from ..utils.timecode import parse_time_input, seconds_to_frames, timecode_to_seconds
from . import fusion_text_ops


KNOWN_TEXT_PRESETS: tuple[dict[str, Any], ...] = (
    {
        "name": "Text",
        "kind": "title",
        "text_kind": "basic_title",
        "editable": "runtime_dependent",
        "recommended_command": 'cutagent text insert-preset "Text" --text "Hello" -j',
    },
    {
        "name": "Text+",
        "kind": "fusion-title",
        "text_kind": "text_plus",
        "editable": "yes",
        "recommended_command": 'cutagent text insert "Hello" -j',
    },
    {
        "name": "MultiText",
        "kind": "fusion-title",
        "text_kind": "multitext",
        "editable": "field_dependent",
        "recommended_command": 'cutagent text insert-preset "MultiText" --fields-json \'{"Text1":"A","Text2":"B"}\' -j',
    },
    {
        "name": "Dark Box Text",
        "kind": "fusion-title",
        "text_kind": "fusion_title_preset",
        "editable": "field_dependent",
        "recommended_command": 'cutagent text insert-preset "Dark Box Text" --text "Hello" -j',
    },
    {
        "name": "Dark Box Text Lower Third",
        "kind": "fusion-title",
        "text_kind": "fusion_title_preset",
        "editable": "field_dependent",
        "recommended_command": 'cutagent text insert-preset "Dark Box Text Lower Third" --fields-json \'{"header":"Name","body":"Role"}\' -j',
    },
    {
        "name": "Ribbon Text",
        "kind": "fusion-title",
        "text_kind": "fusion_title_preset",
        "editable": "field_dependent",
        "recommended_command": 'cutagent text insert-preset "Ribbon Text" --text "Hello" -j',
    },
    {
        "name": "Rotating 3D Text",
        "kind": "fusion-title",
        "text_kind": "fusion_title_preset",
        "editable": "field_dependent",
        "recommended_command": 'cutagent text insert-preset "Rotating 3D Text" --text "Hello" -j',
    },
)


def parse_fields_json(fields_json: str | None) -> dict[str, str]:
    if not fields_json:
        return {}
    try:
        payload = json.loads(fields_json)
    except json.JSONDecodeError as exc:
        raise ValidationError("fields-json must be a JSON object.", details={"error": str(exc)}) from exc
    if not isinstance(payload, dict):
        raise ValidationError("fields-json must be a JSON object.", details={"type": type(payload).__name__})
    fields: dict[str, str] = {}
    for key, value in payload.items():
        normalized_key = str(key or "").strip()
        if not normalized_key:
            raise ValidationError("fields-json contains an empty field name.")
        if value is None:
            raise ValidationError("fields-json values must be strings or numbers, not null.", details={"field": normalized_key})
        if isinstance(value, (dict, list)):
            raise ValidationError(
                "fields-json values must be scalar text values.",
                details={"field": normalized_key, "type": type(value).__name__},
            )
        fields[normalized_key] = str(value)
    return fields


def resolve_text_and_fields(
    *,
    text_arg: str | None = None,
    text_option: str | None = None,
    fields_json: str | None = None,
    require_text_or_fields: bool = False,
) -> tuple[str | None, dict[str, str], str | None]:
    fields = parse_fields_json(fields_json)
    text = text_option if text_option is not None else text_arg
    if text is not None:
        text = str(text)
    if text is not None and fields:
        raise ValidationError("--text and --fields-json are mutually exclusive.")
    if require_text_or_fields and (text is None or not str(text).strip()) and not fields:
        raise ValidationError("Provide text as an argument, with --text, or with --fields-json.")
    source = "fields_json" if fields else "option" if text_option is not None else "argument" if text_arg is not None else None
    return text, fields, source


def _text_kind_for_preset(name: str, kind: str) -> str:
    lowered = str(name or "").strip().casefold()
    if lowered == "text":
        return "basic_title"
    if lowered in {"text+", "text plus"}:
        return "text_plus"
    if lowered == "multitext":
        return "multitext"
    if kind == "fusion-title":
        return "fusion_title_preset"
    return "title_preset"


def _field_role(field_name: str) -> str | None:
    lowered = str(field_name or "").strip().lower().replace("-", "_")
    if lowered in {"header", "headline", "title", "name"}:
        return "header"
    if lowered in {"body", "subtitle", "subheader", "role", "text"}:
        return "body"
    return None


def _field_tool_candidates(field_name: str) -> list[str]:
    name = str(field_name or "").strip()
    candidates = [name]
    lowered = name.lower()
    if lowered == "header":
        candidates.extend(["Header", "Title", "Text1", "TextPlus1"])
    elif lowered in {"body", "subtitle", "role", "text"}:
        candidates.extend(["Body", "Text", "Text2", "TextPlus1"])
    return [candidate for index, candidate in enumerate(candidates) if candidate and candidate not in candidates[:index]]


def apply_text_fields_to_item(
    item: Any,
    *,
    text: str | None = None,
    fields: dict[str, str] | None = None,
    allow_partial: bool = False,
    role: str | None = None,
    explicit_tool: str | None = None,
    tool_candidates: list[str] | None = None,
    input_names: list[str] | None = None,
    uppercase: bool = False,
    double_spaces: bool = False,
    bold_style: str = "ExtraBold",
    styled: bool | None = None,
    cls_tool_candidates: list[str] | None = None,
) -> dict[str, Any]:
    requested_fields = dict(fields or {})
    if text is not None:
        requested_fields = {"text": str(text)}
    if not requested_fields:
        return {
            "requested": {},
            "results": [],
            "ok": True,
            "updated_count": 0,
            "warnings": [],
        }

    results: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for field_name, value in requested_fields.items():
        try:
            field_role = role if len(requested_fields) == 1 and role else _field_role(field_name)
            field_tool = explicit_tool if len(requested_fields) == 1 and explicit_tool else None
            candidates = list(tool_candidates or []) if len(requested_fields) == 1 and tool_candidates else _field_tool_candidates(field_name)
            result = fusion_text_ops.set_text_on_item(
                item,
                text=value,
                role=field_role,
                explicit_tool=field_tool,
                tool_candidates=candidates,
                input_names=input_names,
                uppercase=uppercase,
                double_spaces=double_spaces,
                bold_style=bold_style,
                styled=styled,
                cls_tool_candidates=cls_tool_candidates,
            )
            result["field"] = field_name
            result["ok"] = bool(result.get("verified"))
            if not result["ok"]:
                failures.append({"field": field_name, "reason": "not_verified", "result": result})
                warnings.append({"code": "TEXT_FIELD_NOT_VERIFIED", "field": field_name})
            results.append(result)
        except Exception as exc:
            failure = {"field": field_name, "reason": type(exc).__name__, "message": str(exc)}
            failures.append(failure)
            warnings.append({"code": "TEXT_FIELD_UPDATE_FAILED", **failure})
            results.append({"field": field_name, "ok": False, "error": failure})

    if failures and not allow_partial:
        raise APICallFailed(
            "Text field update failed strict verification.",
            details={
                "requested_fields": list(requested_fields.keys()),
                "failures": failures,
                "allow_partial_fields": allow_partial,
            },
        )

    return {
        "requested": requested_fields,
        "results": results,
        "ok": not failures,
        "updated_count": sum(1 for row in results if row.get("ok")),
        "failure_count": len(failures),
        "warnings": warnings,
    }


def agent_text_payload(
    *,
    intent: str,
    text_kind: str,
    route: str,
    request: dict[str, Any],
    result: dict[str, Any] | None = None,
    verification: dict[str, Any] | None = None,
    fallback_used: bool = False,
    warnings: list[dict[str, Any]] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    return {
        "intent": intent,
        "text_kind": text_kind,
        "route": route,
        "request": request,
        "verification": verification or {},
        "fallback_used": bool(fallback_used),
        "warnings": list(warnings or []),
        **({"result": result} if result is not None else {}),
        **extra,
    }


def insertion_fallback_used(result: dict[str, Any] | None) -> bool:
    if not isinstance(result, dict):
        return False
    if result.get("fallback_from"):
        return True
    if result.get("db_move") is not None or result.get("duration_db_update") is not None:
        return True
    nested_insert = result.get("insert")
    if isinstance(nested_insert, dict):
        return insertion_fallback_used(nested_insert)
    return False


def default_text_overlay_template_path() -> str:
    return str(Path(__file__).resolve().parents[1] / "assets" / "fusion-templates" / "cutagent_textplus_default.setting")


def _timeline_start_frame(conn) -> int:
    try:
        return int(conn.timeline.GetStartFrame())
    except Exception:
        try:
            return int(getattr(conn, "start_frame", 0) or 0)
        except Exception:
            return 0


def _record_frame(conn, position: str) -> int:
    pos = str(position or "0s").strip()
    start_frame = _timeline_start_frame(conn)
    if ":" in pos or ";" in pos:
        absolute_frame = seconds_to_frames(timecode_to_seconds(pos, conn.fps), conn.fps)
        if absolute_frame >= start_frame:
            return absolute_frame
    return parse_record_frame(pos, conn.fps, start_frame)


def _duration_frames(conn, duration: str | int | float) -> int:
    if isinstance(duration, (int, float)):
        seconds = float(duration)
    else:
        seconds = parse_time_input(str(duration), conn.fps)
    frames = seconds_to_frames(seconds, conn.fps)
    if frames <= 0:
        raise ValidationError("Text overlay duration must be greater than 0.", details={"duration": duration})
    return frames


def _load_template(template_path: Optional[str]) -> tuple[str, str, bool]:
    path = template_path or default_text_overlay_template_path()
    if not os.path.isfile(path):
        raise APICallFailed("Text overlay template file not found.", details={"template": path})
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read(), path, template_path is None


def _item_track(item) -> tuple[str | None, int | None]:
    getter = getattr(item, "GetTrackTypeAndIndex", None)
    if callable(getter):
        try:
            result = getter()
            if result:
                return str(result[0]).lower(), int(result[1])
        except Exception:
            pass
    return None, None


def _item_summary(item) -> dict[str, Any]:
    data: dict[str, Any] = {}
    if item is None:
        return data
    track_type, track_index = _item_track(item)
    if track_type:
        data["track_type"] = track_type
    if track_index is not None:
        data["track_index"] = track_index
    for attr in ("GetUniqueId", "GetUniqueID", "GetId", "GetID"):
        getter = getattr(item, attr, None)
        if not callable(getter):
            continue
        try:
            value = getter()
        except Exception:
            continue
        if value not in (None, ""):
            data["timeline_item_id"] = str(value)
            break
    for key, attr in (("name", "GetName"), ("start", "GetStart"), ("end", "GetEnd"), ("duration", "GetDuration")):
        getter = getattr(item, attr, None)
        if not callable(getter):
            continue
        try:
            value = getter()
            if key in {"start", "end", "duration"}:
                value = int(value)
            data[key] = value
        except Exception:
            pass
    return data


def _timeline_item_count(conn, track: int) -> int | None:
    getter = getattr(getattr(conn, "timeline", None), "GetItemListInTrack", None)
    if not callable(getter):
        return None
    try:
        return len(getter("video", track) or [])
    except Exception:
        return None


def _verify_overlay_item(
    conn,
    item,
    *,
    requested_name: str,
    requested_track: int,
    requested_duration_frames: int,
    pre_count: int | None,
    require_name: bool = True,
) -> dict[str, Any]:
    summary = _item_summary(item)
    post_count = _timeline_item_count(conn, requested_track)
    checks = {
        "track": summary.get("track_index") == requested_track if "track_index" in summary else post_count is not None and (pre_count is None or post_count > pre_count),
        "duration": summary.get("duration") == requested_duration_frames if "duration" in summary else True,
        "name": summary.get("name") == requested_name if require_name and "name" in summary else True,
        "track_item_count_increased": True
        if summary.get("track_index") == requested_track or pre_count is None or post_count is None
        else post_count > pre_count,
    }
    status = "verified" if all(checks.values()) else "failed"
    return {
        "status": status,
        "requested": {
            "name": requested_name,
            "track": requested_track,
            "duration_frames": requested_duration_frames,
        },
        "item": summary,
        "pre_track_item_count": pre_count,
        "post_track_item_count": post_count,
        "name_required": require_name,
        "checks": checks,
    }


def _safe_delete_timeline_item(conn, item) -> dict[str, Any]:
    deleter = getattr(getattr(conn, "timeline", None), "DeleteClips", None)
    if not callable(deleter):
        return {"attempted": False, "reason": "Timeline.DeleteClips unavailable"}
    try:
        result = deleter([item], False)
        return {"attempted": True, "api_result": result, "used_non_ripple_argument": True}
    except TypeError:
        try:
            result = deleter([item])
            return {"attempted": True, "api_result": result, "used_non_ripple_argument": False}
        except Exception as exc:
            return {"attempted": True, "api_result": False, "error": str(exc)}
    except Exception as exc:
        return {"attempted": True, "api_result": False, "error": str(exc)}


def _lua_block_end(source: str, open_brace: int) -> int | None:
    depth = 0
    in_string = False
    escaped = False
    for index in range(open_brace, len(source)):
        char = source[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index + 1
    return None


def _setting_tool_input_matches(
    source: str,
    *,
    tool_type: str,
    input_name: str,
) -> list[tuple[re.Match[str], str]]:
    matches: list[tuple[re.Match[str], str]] = []
    header_pattern = re.compile(
        rf"\b(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*{re.escape(tool_type)}\s*\{{"
    )
    input_pattern = re.compile(
        rf'(\b{re.escape(input_name)}\s*=\s*Input\s*\{{\s*Value\s*=\s*")((?:\\.|[^"\\])*)("\s*,\s*\}})',
        flags=re.DOTALL,
    )
    for header in header_pattern.finditer(source):
        open_brace = source.find("{", header.start(), header.end())
        block_end = _lua_block_end(source, open_brace)
        if block_end is None:
            raise APICallFailed(
                f"Text overlay template contains an unterminated {tool_type} tool.",
                details={"reason": "unterminated_text_tool", "tool_type": tool_type},
                recoverability="manual",
            )
        matches.extend(
            (match, str(header.group("name")))
            for match in input_pattern.finditer(source, header.end(), block_end)
        )
    return matches


def _inject_visible_text_into_setting(source: str, text: str) -> tuple[str, str, str]:
    quoted = escape_lua_string(text)
    direct_matches = _setting_tool_input_matches(
        source,
        tool_type="TextPlus",
        input_name="StyledText",
    )
    cls_matches = _setting_tool_input_matches(
        source,
        tool_type="StyledTextCLS",
        input_name="Text",
    )
    supported_matches = [
        *((match, tool_name, "textplus_styled_text") for match, tool_name in direct_matches),
        *((match, tool_name, "styled_text_cls_text") for match, tool_name in cls_matches),
    ]
    if len(supported_matches) != 1:
        raise APICallFailed(
            "Text overlay template does not contain exactly one supported visible text input.",
            details={
                "reason": "visible_text_input_not_unique",
                "match_count": len(supported_matches),
                "direct_textplus_matches": len(direct_matches),
                "styled_text_cls_matches": len(cls_matches),
            },
            recoverability="manual",
        )
    match, tool_name, route = supported_matches[0]
    return (
        f"{source[:match.start(2)]}{quoted}{source[match.end(2):]}",
        route,
        tool_name,
    )


def render_text_overlay_setting(
    text: str,
    *,
    template_path: Optional[str] = None,
    bold_style: str = "ExtraBold",
    replacements: Optional[dict[str, Any]] = None,
) -> tuple[str, dict[str, Any]]:
    template_code, resolved_template, bundled = _load_template(template_path)
    clean_text, styling = parse_styled_text(text, bold_style)
    rendered = render_setting_template(
        template_code,
        text=clean_text,
        styling=styling,
        replacements={str(key): value for key, value in (replacements or {}).items()},
    )
    rendered, text_replacement_route, text_replacement_tool = _inject_visible_text_into_setting(rendered, clean_text)
    return rendered, {
        "template": resolved_template,
        "template_source": "bundled" if bundled else "custom",
        "text": clean_text,
        "bold_style": bold_style,
        "styled_ranges": len(styling or []),
        "text_replacement_route": text_replacement_route,
        "text_replacement_tool": text_replacement_tool,
    }


def _read_inserted_overlay_text(item: Any, *, route: str, tool_name: str) -> dict[str, Any]:
    comp = _get_comp(item)
    if comp is None:
        return {"accessible": False, "route": route, "text": None, "tool": None, "input": None}
    tool = fusion_text_ops.find_tool(comp, tool_name)
    input_name = "Text" if route == "styled_text_cls_text" else "StyledText"
    return {
        "accessible": tool is not None,
        "route": route,
        "text": _get_tool_input(tool, input_name) if tool is not None else None,
        "tool": fusion_text_ops.tool_name(tool) if tool is not None else None,
        "input": input_name,
    }


def _delete_inserted_overlay_and_verify(
    conn: Any,
    item: Any,
    *,
    track: int,
    start_frame: int,
    duration_frames: int,
    name: str,
) -> dict[str, Any]:
    cleanup = _safe_delete_timeline_item(conn, item)
    try:
        from ..commands import fusion as fusion_commands

        remaining = [
            row["readback"]
            for row in fusion_commands._enumerated_video_items(conn)
            if row["readback"].get("track_index") == int(track)
            and row["readback"].get("start") == int(start_frame)
            and row["readback"].get("duration") == int(duration_frames)
            and str(row["readback"].get("name") or "") == str(name)
        ]
        cleanup["absence_verified"] = not remaining
        cleanup["remaining_matches"] = remaining
    except Exception as exc:
        cleanup["absence_verified"] = False
        cleanup["verification_error"] = {"type": exc.__class__.__name__, "message": str(exc)}
    return cleanup


def insert_text_overlay_setting(
    conn,
    *,
    text: str,
    template_path: Optional[str] = None,
    name: str = "Text Overlay",
    at: str = "0s",
    duration: str | int | float = "5s",
    track: int = 2,
    bold_style: str = "ExtraBold",
) -> dict[str, Any]:
    rendered, render_info = render_text_overlay_setting(text, template_path=template_path, bold_style=bold_style)
    start_frame = _record_frame(conn, at)
    duration_frames = _duration_frames(conn, duration)
    timeline_name_getter = getattr(getattr(conn, "timeline", None), "GetName", None)
    try:
        target_timeline_name = str(timeline_name_getter() or "").strip() if callable(timeline_name_getter) else ""
    except Exception:
        target_timeline_name = ""
    if track < 1:
        raise ValidationError("Text overlay track must be 1 or greater for the setting route.", details={"track": track})

    with tempfile.NamedTemporaryFile(suffix=".setting", delete=False, mode="w", encoding="utf-8") as handle:
        handle.write(rendered)
        setting_path = handle.name

    try:
        from ..commands import fusion as fusion_commands

        inserted = fusion_commands._insert_setting_precise(
            conn,
            path=setting_path,
            clip_name=name,
            at=f"{start_frame}f",
            record_frame=start_frame,
            duration=f"{duration_frames}f",
            track=track,
            holder="Text+",
            holder_kind="textplus",
            position_x=None,
            position_y=None,
        )
        verification = inserted.get("verification") or {}
        route_used = str(inserted.get("route") or "timeline_item.ImportFusionComp")
        if not verification.get("imported"):
            set_verification_status("failed")
            raise APICallFailed(
                "Text overlay .setting was not imported into the Text+ holder.",
                details={"route": route_used, "verification": verification},
            )
        if not (verification.get("track_ok", True) and verification.get("start_ok", True) and verification.get("duration_ok", True)):
            set_verification_status("failed")
            raise APICallFailed(
                "Text overlay insertion did not match requested track/start/duration.",
                details={"route": route_used, "verification": verification},
            )

        readback_conn = conn
        if inserted.get("connection_reloaded"):
            from ..connection import get_connection

            readback_conn = get_connection(require_timeline=True)
            fresh_name_getter = getattr(getattr(readback_conn, "timeline", None), "GetName", None)
            try:
                fresh_timeline_name = str(fresh_name_getter() or "").strip() if callable(fresh_name_getter) else ""
            except Exception:
                fresh_timeline_name = ""
            if not target_timeline_name or fresh_timeline_name != target_timeline_name:
                set_verification_status("failed")
                raise APICallFailed(
                    "Text overlay post-reopen readback did not restore the exact target timeline.",
                    details={
                        "expected_timeline": target_timeline_name or None,
                        "actual_timeline": fresh_timeline_name or None,
                        "route": route_used,
                    },
                    recoverability="manual",
                )

        exact_item = fusion_commands._unique_enumerated_video_item(
            readback_conn,
            track_index=track,
            start=start_frame,
            duration=duration_frames,
            name=name,
        )
        text_readback = _read_inserted_overlay_text(
            exact_item["item"],
            route=str(render_info["text_replacement_route"]),
            tool_name=str(render_info["text_replacement_tool"]),
        )
        text_verified = text_readback.get("accessible") is True and text_readback.get("text") == render_info["text"]
        if not text_verified:
            cleanup = _delete_inserted_overlay_and_verify(
                readback_conn,
                exact_item["item"],
                track=track,
                start_frame=start_frame,
                duration_frames=duration_frames,
                name=name,
            )
            set_verification_status("failed")
            raise APICallFailed(
                "Text overlay Fusion graph did not contain the requested visible text.",
                details={
                    "route": route_used,
                    "requested_text": render_info["text"],
                    "readback": text_readback,
                    "item": exact_item["readback"],
                    "cleanup": cleanup,
                },
                recoverability="retryable" if cleanup.get("absence_verified") else "manual",
            )
        verification = {
            **verification,
            "visible_text_ok": True,
            "visible_text_readback": text_readback,
        }

        return {
            "route": route_used,
            "name": name,
            "text": render_info["text"],
            "at": at,
            "track": track,
            "duration": duration,
            "start_frame": start_frame,
            "duration_frames": duration_frames,
            "template": render_info["template"],
            "template_source": render_info["template_source"],
            "styled_ranges": render_info["styled_ranges"],
            "text_replacement_route": render_info["text_replacement_route"],
            "text_replacement_tool": render_info["text_replacement_tool"],
            "readback_text": text_readback["text"],
            "track_preflight": inserted.get("track_summary"),
            "holder_lookup": inserted.get("holder_lookup"),
            "insert": inserted,
            "verification": verification,
        }
    finally:
        try:
            os.unlink(setting_path)
        except Exception:
            pass


def _get_comp(item):
    for index in (1, 0):
        getter = getattr(item, "GetFusionCompByIndex", None)
        if not callable(getter):
            break
        try:
            comp = getter(index)
        except Exception:
            comp = None
        if comp:
            return comp
    return None


def _tool_attrs(tool) -> dict[str, Any]:
    try:
        attrs = tool.GetAttrs() if hasattr(tool, "GetAttrs") else {}
    except Exception:
        attrs = {}
    return attrs if isinstance(attrs, dict) else {}


def _tool_name(tool, fallback: Any) -> str:
    for attr in ("Name", "name"):
        value = getattr(tool, attr, None)
        if value:
            return str(value)
    attrs = _tool_attrs(tool)
    return str(attrs.get("TOOLS_Name") or fallback)


def _find_text_tool(comp):
    finder = getattr(comp, "FindTool", None)
    if callable(finder):
        for name in ("Text1", "TextPlus1", "Template"):
            try:
                tool = finder(name)
            except Exception:
                tool = None
            if tool:
                return tool, name

    getter = getattr(comp, "GetToolList", None)
    if not callable(getter):
        return None, None
    try:
        tools = getter(False) or {}
    except TypeError:
        tools = getter() or {}
    except Exception:
        tools = {}

    iterable = tools.items() if isinstance(tools, dict) else enumerate(tools)
    fallback = None
    for key, tool in iterable:
        attrs = _tool_attrs(tool)
        reg_id = str(attrs.get("TOOLS_RegID") or getattr(tool, "ID", "") or "")
        name = _tool_name(tool, key)
        if reg_id == "TextPlus":
            return tool, name
        if fallback is None and "text" in f"{reg_id} {name}".lower():
            fallback = (tool, name)
    return fallback if fallback is not None else (None, None)


def _set_tool_input(tool, input_name: str, value: Any) -> bool:
    setter = getattr(tool, "SetInput", None)
    if not callable(setter):
        return False
    try:
        result = setter(input_name, value)
    except TypeError:
        result = setter(input_name, value, 0)
    return result is not False


def _get_tool_input(tool, input_name: str):
    getter = getattr(tool, "GetInput", None)
    if not callable(getter):
        return None
    for args in ((input_name,), (input_name, 0)):
        try:
            return getter(*args)
        except Exception:
            continue
    return None


def _apply_name_and_duration(item, *, name: str, duration_frames: int) -> dict[str, Any]:
    result = {"name_applied": False, "duration_applied": False}
    setter = getattr(item, "SetProperty", None)
    if not callable(setter):
        return result

    try:
        result["name_applied"] = setter("Clip Name", name) is not False
    except Exception:
        pass

    for key in ("Duration", "End"):
        try:
            value = duration_frames
            if key == "End" and hasattr(item, "GetStart"):
                value = int(item.GetStart()) + duration_frames
            if setter(key, value) is not False:
                result["duration_applied"] = True
                break
        except Exception:
            continue
    return result


def insert_text_overlay_native_title(
    conn,
    *,
    text: str,
    name: str = "Text Overlay",
    at: str = "0s",
    duration: str | int | float = "5s",
    track: int = 1,
    title_preset: str = "Text+",
) -> dict[str, Any]:
    from . import timeline_ops

    if track != 1:
        raise ValidationError(
            "The native-title route cannot target arbitrary video tracks; use route=auto or route=setting for --track values other than 1.",
            details={"route": "native-title", "track": track, "supported_track": 1},
            recoverability="not_applicable",
        )

    duration_frames = _duration_frames(conn, duration)
    pre_count = _timeline_item_count(conn, track)
    final_tc = timeline_ops.set_playhead(conn, at)
    inserter = require_api_method(
        conn.timeline,
        "InsertFusionTitleIntoTimeline",
        capability_id="timeline.insert_title",
        runtime_object="timeline",
    )
    item = inserter(title_preset)
    if not item:
        raise APICallFailed(
            "Failed to insert native Fusion title for text overlay.",
            details={"route": "native_fusion_title", "title_preset": title_preset},
        )

    comp = _get_comp(item)
    if not comp:
        raise APICallFailed(
            "Inserted Fusion title, but its Fusion composition was not accessible.",
            details={"route": "native_fusion_title", "title_preset": title_preset},
        )

    tool, tool_name = _find_text_tool(comp)
    if not tool:
        raise APICallFailed(
            "Inserted Fusion title, but no TextPlus tool was found.",
            details={"route": "native_fusion_title", "title_preset": title_preset},
        )

    if not _set_tool_input(tool, "StyledText", text):
        raise APICallFailed(
            "Failed to set TextPlus StyledText on inserted title.",
            details={"route": "native_fusion_title", "tool": tool_name},
        )

    readback = _get_tool_input(tool, "StyledText")
    applied = _apply_name_and_duration(item, name=name, duration_frames=duration_frames)
    item_verification = _verify_overlay_item(
        conn,
        item,
        requested_name=name,
        requested_track=track,
        requested_duration_frames=duration_frames,
        pre_count=pre_count,
        require_name=False,
    )
    verification = {
        "styled_text": "verified" if readback == text else "set",
        "item": item_verification,
    }
    if readback != text or item_verification["status"] != "verified":
        set_verification_status("failed")
        cleanup = _safe_delete_timeline_item(conn, item)
        raise APICallFailed(
            "Native title text overlay did not apply requested text, track, or duration.",
            details={
                "route": "native_fusion_title",
                "name": name,
                "text": text,
                "readback_text": readback,
                "duration_frames": duration_frames,
                "applied": applied,
                "verification": verification,
                "cleanup": cleanup,
            },
        )
    set_verification_status("verified")
    return {
        "route": "native_fusion_title",
        "name": name,
        "text": text,
        "at": at,
        "playhead_timecode": final_tc,
        "duration": duration,
        "duration_frames": duration_frames,
        "title_preset": title_preset,
        "tool": tool_name,
        "readback_text": readback,
        **applied,
        "verification": verification,
    }


def insert_text_overlay(
    conn,
    *,
    text: str,
    template_path: Optional[str] = None,
    name: str = "Text Overlay",
    at: str = "0s",
    duration: str | int | float = "5s",
    track: int = 2,
    bold_style: str = "ExtraBold",
    route: str = "auto",
) -> dict[str, Any]:
    text = str(text or "").strip()
    if not text:
        raise ValidationError("Text overlay requires non-empty text.")

    route_key = str(route or "auto").strip().lower().replace("_", "-")
    if route_key not in {"auto", "setting", "native-title"}:
        raise ValidationError(
            "Unsupported text overlay route.",
            details={"route": route, "allowed": ["auto", "setting", "native-title"]},
        )

    if route_key == "native-title":
        return insert_text_overlay_native_title(conn, text=text, name=name, at=at, duration=duration, track=track)

    try:
        return insert_text_overlay_setting(
            conn,
            text=text,
            template_path=template_path,
            name=name,
            at=at,
            duration=duration,
            track=track,
            bold_style=bold_style,
        )
    except APICallFailed as setting_error:
        if route_key != "auto" or template_path:
            raise
        if track != 1:
            raise APICallFailed(
                "Text overlay setting route failed and native-title fallback cannot honor the requested track.",
                details={"track": track, "setting_error": str(setting_error)},
            ) from setting_error
        native = insert_text_overlay_native_title(conn, text=text, name=name, at=at, duration=duration, track=track)
        native["fallback_from"] = "timeline_item.ImportFusionComp"
        native["fallback_error"] = str(setting_error)
        return native


def insert_visible_text(
    conn,
    *,
    text: str,
    template_path: Optional[str] = None,
    name: str = "Text Overlay",
    at: str = "0s",
    duration: str | int | float = "5s",
    track: int = 2,
    bold_style: str = "ExtraBold",
    route: str = "auto",
) -> dict[str, Any]:
    result = insert_text_overlay(
        conn,
        text=text,
        template_path=template_path,
        name=name,
        at=at,
        duration=duration,
        track=track,
        bold_style=bold_style,
        route=route,
    )
    return agent_text_payload(
        intent="visible_text_overlay",
        text_kind="text_plus",
        route=str(result.get("route") or route),
        request={
            "text": text,
            "name": name,
            "at": at,
            "duration": duration,
            "track": track,
            "template": template_path,
            "route": route,
        },
        result=result,
        verification=result.get("verification") if isinstance(result.get("verification"), dict) else {},
        fallback_used=insertion_fallback_used(result),
        warnings=[],
    )


def _resolve_preset_kind(name: str, kind: str) -> tuple[str, bool]:
    key = str(kind or "auto").strip().lower().replace("_", "-")
    if key not in {"auto", "title", "fusion-title"}:
        raise ValidationError(
            "Unsupported text preset kind.",
            details={"kind": kind, "allowed": ["auto", "title", "fusion-title"]},
        )
    if key == "auto":
        key = "title" if str(name or "").strip().casefold() == "text" else "fusion-title"
    return key, key == "fusion-title"


def _insert_native_preset_item(conn, *, name: str, kind: str, at: str) -> tuple[Any, str, str]:
    from . import timeline_ops

    resolved_kind, fusion = _resolve_preset_kind(name, kind)
    method_name = "InsertFusionTitleIntoTimeline" if fusion else "InsertTitleIntoTimeline"
    timeline_ops.set_playhead(conn, at)
    inserter = require_api_method(
        conn.timeline,
        method_name,
        capability_id="text.insert_preset",
        runtime_object="timeline",
    )
    item = inserter(name)
    if not item:
        raise APICallFailed(
            "Failed to insert text preset into timeline.",
            details={"name": name, "kind": resolved_kind, "method": method_name},
        )
    return item, resolved_kind, method_name


def _move_inserted_preset_if_needed(
    conn,
    *,
    item: Any,
    preset_name: str,
    clip_name: str,
    kind: str,
    track: int,
    record_frame: int,
    duration_frames: int,
) -> dict[str, Any] | None:
    current_track_type, current_track_index = _item_track(item)
    summary = _item_summary(item)
    current_start = summary.get("start")
    current_duration = summary.get("duration")
    track_ok = current_track_index == track if current_track_type == "video" and current_track_index is not None else track == 1
    start_ok = int(current_start) == int(record_frame) if current_start is not None else True
    duration_ok = int(current_duration) == int(duration_frames) if current_duration is not None else True
    if track_ok and start_ok and duration_ok:
        return None
    if current_track_type != "video" or current_track_index is None:
        raise APICallFailed(
            "Inserted text preset did not expose a verified source video track for precise placement.",
            details={"item": summary, "requested_track": track},
        )

    from ..commands import fusion as fusion_commands

    return fusion_commands._move_native_precise_holder_via_db(
        conn,
        timeline_name=None,
        staging_readback={
            "name": summary.get("name") or preset_name,
            "start": current_start if current_start is not None else record_frame,
            "duration": current_duration or duration_frames,
            "track_index": current_track_index,
            "timeline_item_id": summary.get("timeline_item_id"),
        },
        target_track=track,
        target_record_frame=record_frame,
        target_duration_frames=duration_frames,
        clip_name=clip_name,
        holder=preset_name,
        holder_kind="textplus" if kind == "fusion-title" else "fusion",
    )


def insert_text_preset(
    conn,
    *,
    preset_name: str,
    kind: str = "auto",
    text: str | None = None,
    fields: dict[str, str] | None = None,
    allow_partial_fields: bool = False,
    name: str | None = None,
    at: str = "0s",
    duration: str | int | float = "5s",
    track: int = 1,
    bold_style: str = "ExtraBold",
) -> dict[str, Any]:
    if track < 1:
        raise ValidationError("Text preset track must be 1 or greater.", details={"track": track})
    clip_name = str(name or preset_name).strip() or preset_name
    record_frame = _record_frame(conn, at)
    duration_frames = _duration_frames(conn, duration)
    from ..commands import fusion as fusion_commands
    from ..connection import ResolveConnection
    from . import timeline_ops

    target_timeline_name = str(conn.timeline.GetName() or "")
    if not target_timeline_name:
        raise APICallFailed("Text preset insertion lost the active Timeline name.")
    try:
        target_playhead = timeline_ops.get_playhead(conn)
    except Exception:
        target_playhead = None
    target_format = fusion_commands._current_timeline_format(conn)
    scratch_name = fusion_commands._unique_validate_scratch_timeline_name(conn)
    scratch_created = False
    cleanup = None
    item = None
    item_summary: dict[str, Any] = {}
    apply_result: dict[str, Any] = {}
    field_result: dict[str, Any] = {"requested": {}, "results": [], "ok": True, "warnings": []}
    db_move = None
    resolved_kind, _fusion = _resolve_preset_kind(preset_name, kind)
    method_name = "InsertFusionTitleIntoTimeline" if _fusion else "InsertTitleIntoTimeline"
    try:
        timeline_ops.create_timeline(
            conn,
            scratch_name,
            width=target_format.get("width"),
            height=target_format.get("height"),
            fps=target_format.get("fps"),
        )
        scratch_created = True
        conn.refresh()
        if str(conn.timeline.GetName() or "") != scratch_name or fusion_commands._enumerated_video_items(conn):
            raise APICallFailed("Text preset scratch Timeline did not open empty.")
        scratch_start = fusion_commands._connection_start_frame(conn)
        item, resolved_kind, method_name = _insert_native_preset_item(
            conn,
            name=preset_name,
            kind=resolved_kind,
            at=fusion_commands._absolute_record_frame_ref(conn, scratch_start),
        )
        apply_result = _apply_name_and_duration(item, name=clip_name, duration_frames=duration_frames)
        field_result = apply_text_fields_to_item(
            item,
            text=text,
            fields=fields,
            allow_partial=allow_partial_fields,
            bold_style=bold_style,
            styled=True if text and "**" in text else None,
        )
        item_summary = _item_summary(item)
        staging_readback = {
            "name": item_summary.get("name") or preset_name,
            "start": item_summary.get("start"),
            "duration": item_summary.get("duration"),
            "track_index": item_summary.get("track_index"),
            "timeline_item_id": item_summary.get("timeline_item_id"),
        }
        if staging_readback["start"] is None or staging_readback["duration"] is None:
            raise APICallFailed(
                "Inserted text preset did not expose readable scratch timing.",
                details={"staging_readback": staging_readback},
            )
        staging_readback["db_start_candidates"] = fusion_commands._project_db_start_candidates(
            conn,
            int(staging_readback["start"]),
        )
        timeline_ops.switch_timeline(conn, name=target_timeline_name)
        if str(conn.timeline.GetName() or "") != target_timeline_name:
            raise APICallFailed(
                "Target Timeline did not restore before text preset Project.db placement.",
                details={"target_timeline": target_timeline_name},
            )
        db_move = fusion_commands._move_native_precise_holder_via_db(
            conn,
            timeline_name=target_timeline_name,
            source_timeline_name=scratch_name,
            staging_readback=staging_readback,
            target_track=track,
            target_record_frame=record_frame,
            target_duration_frames=duration_frames,
            clip_name=clip_name,
            holder=preset_name,
            holder_kind="textplus" if resolved_kind == "fusion-title" else "fusion",
            require_fusion_tools=resolved_kind == "fusion-title",
        )
        db_status = (db_move.get("verification") or {}).get("status") if isinstance(db_move, dict) else None
        if db_status != "verified":
            raise APICallFailed("Inserted text preset DB placement did not verify.", details={"db_move": db_move})
        fresh = ResolveConnection.get()
        fresh.connect()
        cleanup = fusion_commands._cleanup_native_precise_scratch_timeline(
            fresh,
            target_timeline_name=target_timeline_name,
            scratch_timeline_name=scratch_name,
            target_playhead=target_playhead,
        )
        if not cleanup.get("ok"):
            raise APICallFailed("Text preset scratch cleanup did not verify.", details={"cleanup": cleanup})
    except Exception as exc:
        if scratch_created and not (isinstance(cleanup, dict) and cleanup.get("ok")):
            try:
                fresh = ResolveConnection.get()
                fresh.connect()
                cleanup = fusion_commands._cleanup_native_precise_scratch_timeline(
                    fresh,
                    target_timeline_name=target_timeline_name,
                    scratch_timeline_name=scratch_name,
                    target_playhead=target_playhead,
                )
            except Exception as cleanup_error:
                cleanup = {"ok": False, "error": str(cleanup_error)}
        if hasattr(exc, "details") and isinstance(exc.details, dict):
            exc.details["native_staging_cleanup"] = cleanup
            if db_move is not None:
                exc.details["possible_mutation"] = True
                exc.details["possible_mutation_state"] = "target_insert_verified_post_move_failure"
            elif scratch_created and not (isinstance(cleanup, dict) and cleanup.get("ok")):
                exc.details["possible_mutation"] = True
                exc.details["possible_mutation_state"] = "scratch_cleanup_unverified"
        raise

    db_verification = db_move["verification"]
    readback = dict(db_verification["readback"])
    verification = {
        "status": "verified",
        "requested": {"name": clip_name, "track": track, "duration_frames": duration_frames},
        "item": readback,
        "db_move": db_verification,
        "checks": {
            "track": readback.get("track_index") == track,
            "duration": readback.get("duration") == duration_frames,
            "name": readback.get("name") == clip_name,
            "db_move_verified": True,
        },
    }
    set_verification_status("verified" if field_result.get("ok") and verification["status"] == "verified" else "partial")
    warnings = list(field_result.get("warnings") or [])
    if name and readback.get("name") != clip_name:
        warnings.append(
            {
                "code": "TEXT_PRESET_NAME_NOT_VERIFIED",
                "requested_name": clip_name,
                "actual_name": readback.get("name"),
                "note": "DaVinci Resolve may keep built-in title preset names in timeline readback.",
            }
        )
    warnings.append({"code": "TEXT_PRESET_DB_PLACEMENT_USED"})
    route = f"scratch.timeline.{method_name} -> project_db.move_timeline_item"
    return agent_text_payload(
        intent="visible_text_preset",
        text_kind=_text_kind_for_preset(preset_name, resolved_kind),
        route=route,
        request={
            "preset": preset_name,
            "kind": resolved_kind,
            "text": text,
            "fields": fields or {},
            "name": clip_name,
            "at": at,
            "duration": duration,
            "track": track,
            "allow_partial_fields": allow_partial_fields,
        },
        result={
            "preset": preset_name,
            "kind": resolved_kind,
            "method": method_name,
            "item": readback,
            "applied": apply_result,
            "fields": field_result,
            "db_move": db_move,
            "scratch_cleanup": cleanup,
        },
        verification=verification,
        fallback_used=db_move is not None,
        warnings=warnings,
    )


def inspect_text_item(item: Any) -> dict[str, Any]:
    comp = None
    try:
        from .fusion_common import get_fusion_comp_for_item, tool_name, tool_reg_id

        comp = get_fusion_comp_for_item(item)
        tools = []
        if comp is not None:
            for tool in fusion_text_ops.collect_text_tools(comp):
                tools.append(
                    {
                        "name": tool_name(tool),
                        "type": tool_reg_id(tool),
                        "inputs": sorted(fusion_text_ops._tool_input_names(tool)),
                    }
                )
        return {
            "kind": "clip",
            "item": _item_summary(item),
            "has_fusion_comp": comp is not None,
            "editable": bool(tools),
            "fields": tools,
        }
    except Exception as exc:
        return {"kind": "clip", "item": _item_summary(item), "has_fusion_comp": comp is not None, "editable": False, "error": str(exc)}
