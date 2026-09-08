"""Selector-driven bulk clip operations (`bulk ...`).

One invocation, one Resolve connection, many clips: select targets by track,
name, duration, range, color, or enabled state, then apply a mutation to every
match. Use `bulk select` first to preview exactly which clips a selector
hits; every mutating subcommand supports `--dry-run` with the same semantics.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import typer

from ..connection import get_connection
from ..core import bulk_ops, color_ops
from ..errors import APICallFailed, ValidationError, handle_errors
from ..output import (
    is_dry_run,
    output,
    set_execution_engine,
    set_recoverability,
    set_verification_status,
)
from ..policy import enforce_mutation_policy, require_api_method

app = typer.Typer(help="Bulk operations over clips selected by track, name, duration, range, color, or enabled state.")


def _selector_options_help() -> str:
    return "Selector flags choose the target clips; combine freely (all must match)."


def _build_selection(
    conn,
    *,
    track_type: str,
    track: Optional[int],
    name: Optional[str],
    name_starts_with: Optional[str],
    name_contains: Optional[str],
    name_regex: Optional[str],
    duration: Optional[str],
    min_duration: Optional[str],
    max_duration: Optional[str],
    start_ref: Optional[str],
    end_ref: Optional[str],
    clip_color: Optional[str],
    enabled_state: Optional[str],
    limit: int,
):
    enabled: Optional[bool] = None
    if enabled_state is not None:
        normalized = enabled_state.strip().lower()
        if normalized not in {"enabled", "disabled"}:
            raise ValidationError(
                "--state must be 'enabled' or 'disabled'.",
                details={"state": enabled_state},
            )
        enabled = normalized == "enabled"
    filters = bulk_ops.normalize_selector_filters(
        conn,
        track_type=track_type,
        track_index=track,
        name=name,
        name_starts_with=name_starts_with,
        name_contains=name_contains,
        name_regex=name_regex,
        duration=duration,
        min_duration=min_duration,
        max_duration=max_duration,
        start_ref=start_ref,
        end_ref=end_ref,
        clip_color=clip_color,
        enabled=enabled,
        limit=limit,
    )
    matches = bulk_ops.select_timeline_items(conn, filters)
    return filters, matches


def _selection_payload(filters: Dict[str, Any], matches: List[Dict[str, Any]]) -> Dict[str, Any]:
    truncated = bool(matches and matches[0]["meta"].get("truncated_by_limit"))
    return {
        "selector": bulk_ops.describe_selector(filters),
        "matched": len(matches),
        "truncated_by_limit": truncated,
        "clips": [
            {key: value for key, value in match["meta"].items() if key != "truncated_by_limit" and value is not None}
            for match in matches
        ],
    }


def _require_matches(filters: Dict[str, Any], matches: List[Dict[str, Any]]) -> None:
    if not matches:
        raise ValidationError(
            "No clips matched the selector. Run `bulk select` with the same flags to inspect the timeline, "
            "then adjust the filters.",
            details={"selector": bulk_ops.describe_selector(filters)},
        )


def _finish_bulk(action: str, filters: Dict[str, Any], summary: Dict[str, Any], extra: Dict[str, Any] | None = None) -> None:
    set_verification_status("verified" if summary["failed"] == 0 else "failed")
    set_recoverability("not_applicable" if summary["failed"] == 0 else "manual")
    payload = {
        "action": action,
        "selector": bulk_ops.describe_selector(filters),
        **(extra or {}),
        **summary,
    }
    if summary["failed"] > 0:
        payload["warning"] = (
            f"{summary['failed']} of {summary['matched']} clips failed; see per-clip errors. "
            "Re-run with a narrower selector to retry only the failures."
        )
    output(payload, title=f"Bulk {action}")


# Typer requires explicit parameters per command; the selector block is
# intentionally identical across subcommands so agents learn it once.
_TRACK_TYPE = typer.Option("video", "--track-type", help="Track type to search: video, audio, subtitle, or all.")
_TRACK = typer.Option(None, "--track", help="Only clips on this 1-based track index.")
_NAME = typer.Option(None, "--name", help="Exact clip name match.")
_NAME_STARTS = typer.Option(None, "--name-starts-with", help="Clip name prefix match (case-sensitive).")
_NAME_CONTAINS = typer.Option(None, "--name-contains", help="Clip name substring match (case-insensitive).")
_NAME_REGEX = typer.Option(None, "--name-regex", help="Clip name regular expression match.")
_DURATION = typer.Option(None, "--duration", help="Exact clip duration: seconds ('4' / '4s'), frames ('96f'), or timecode.")
_MIN_DURATION = typer.Option(None, "--min-duration", help="Minimum clip duration (same formats as --duration).")
_MAX_DURATION = typer.Option(None, "--max-duration", help="Maximum clip duration (same formats as --duration).")
_FROM = typer.Option(None, "--from", help="Only clips overlapping a record-domain range start (timecode, seconds, frames).")
_TO = typer.Option(None, "--to", help="Only clips overlapping a record-domain range end (timecode, seconds, frames).")
_CLIP_COLOR = typer.Option(None, "--clip-color", help="Only clips currently flagged with this clip color.")
_STATE = typer.Option(None, "--state", help="Only clips in this state: enabled or disabled.")
_LIMIT = typer.Option(bulk_ops.DEFAULT_LIMIT, "--limit", help="Safety cap on selected clips.")
_FAIL_FAST = typer.Option(False, "--fail-fast", help="Stop at the first failing clip instead of continuing.")


@app.command("select")
@handle_errors
def bulk_select(
    track_type: str = _TRACK_TYPE,
    track: Optional[int] = _TRACK,
    name: Optional[str] = _NAME,
    name_starts_with: Optional[str] = _NAME_STARTS,
    name_contains: Optional[str] = _NAME_CONTAINS,
    name_regex: Optional[str] = _NAME_REGEX,
    duration: Optional[str] = _DURATION,
    min_duration: Optional[str] = _MIN_DURATION,
    max_duration: Optional[str] = _MAX_DURATION,
    start_ref: Optional[str] = _FROM,
    end_ref: Optional[str] = _TO,
    clip_color: Optional[str] = _CLIP_COLOR,
    enabled_state: Optional[str] = _STATE,
    limit: int = _LIMIT,
):
    """Preview which clips a selector matches (read-only)."""
    set_execution_engine("api_native")
    conn = get_connection(require_timeline=True)
    filters, matches = _build_selection(
        conn,
        track_type=track_type,
        track=track,
        name=name,
        name_starts_with=name_starts_with,
        name_contains=name_contains,
        name_regex=name_regex,
        duration=duration,
        min_duration=min_duration,
        max_duration=max_duration,
        start_ref=start_ref,
        end_ref=end_ref,
        clip_color=clip_color,
        enabled_state=enabled_state,
        limit=limit,
    )
    output(_selection_payload(filters, matches), title="Bulk Select")


def _run_bulk_mutation(
    *,
    action: str,
    policy_id: str,
    operation,
    extra: Dict[str, Any] | None = None,
    track_type: str,
    track: Optional[int],
    name: Optional[str],
    name_starts_with: Optional[str],
    name_contains: Optional[str],
    name_regex: Optional[str],
    duration: Optional[str],
    min_duration: Optional[str],
    max_duration: Optional[str],
    start_ref: Optional[str],
    end_ref: Optional[str],
    clip_color: Optional[str],
    enabled_state: Optional[str],
    limit: int,
    fail_fast: bool,
) -> None:
    set_execution_engine("api_native")
    enforce_mutation_policy(policy_id, intended_engine="api_native", mutating=not is_dry_run())
    conn = get_connection(require_timeline=True)
    filters, matches = _build_selection(
        conn,
        track_type=track_type,
        track=track,
        name=name,
        name_starts_with=name_starts_with,
        name_contains=name_contains,
        name_regex=name_regex,
        duration=duration,
        min_duration=min_duration,
        max_duration=max_duration,
        start_ref=start_ref,
        end_ref=end_ref,
        clip_color=clip_color,
        enabled_state=enabled_state,
        limit=limit,
    )
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            {
                "action": action,
                "would_apply": True,
                **(extra or {}),
                **_selection_payload(filters, matches),
            },
            title=f"Bulk {action} Preview",
        )
        return
    _require_matches(filters, matches)
    summary = bulk_ops.apply_to_items(conn, matches, operation, fail_fast=fail_fast)
    _finish_bulk(action, filters, summary, extra)


@app.command("lut-set")
@handle_errors
def bulk_lut_set(
    node_index: int = typer.Argument(..., help="1-based color node index to receive the LUT"),
    lut_path: str = typer.Argument(..., help="LUT path (absolute, or relative to the Resolve LUT root)"),
    track_type: str = _TRACK_TYPE,
    track: Optional[int] = _TRACK,
    name: Optional[str] = _NAME,
    name_starts_with: Optional[str] = _NAME_STARTS,
    name_contains: Optional[str] = _NAME_CONTAINS,
    name_regex: Optional[str] = _NAME_REGEX,
    duration: Optional[str] = _DURATION,
    min_duration: Optional[str] = _MIN_DURATION,
    max_duration: Optional[str] = _MAX_DURATION,
    start_ref: Optional[str] = _FROM,
    end_ref: Optional[str] = _TO,
    clip_color: Optional[str] = _CLIP_COLOR,
    enabled_state: Optional[str] = _STATE,
    limit: int = _LIMIT,
    fail_fast: bool = _FAIL_FAST,
):
    """Set a LUT on a color node of every selected clip in one pass."""
    if node_index < 1:
        raise ValidationError("Node index must be a positive integer.", details={"node_index": node_index})

    def operation(conn, item, meta):
        graph_getter = require_api_method(
            item,
            "GetNodeGraph",
            capability_id="color.node_graph_ops",
            runtime_object="timeline_item",
        )
        graph = graph_getter()
        if not graph:
            raise APICallFailed("No node graph available for this timeline item.", details={"clip": meta["name"]})
        setter = require_api_method(
            graph,
            "SetLUT",
            capability_id="color.node_graph_ops",
            runtime_object="node_graph",
        )
        getter = getattr(graph, "GetLUT", None)
        applied_path, _info = color_ops._set_lut_with_candidates(conn, setter, node_index, lut_path, getter=getter)
        return {"lut": applied_path}

    _run_bulk_mutation(
        action="lut-set",
        policy_id="color.node_graph_ops",
        operation=operation,
        extra={"node_index": node_index, "lut_path": lut_path},
        track_type=track_type,
        track=track,
        name=name,
        name_starts_with=name_starts_with,
        name_contains=name_contains,
        name_regex=name_regex,
        duration=duration,
        min_duration=min_duration,
        max_duration=max_duration,
        start_ref=start_ref,
        end_ref=end_ref,
        clip_color=clip_color,
        enabled_state=enabled_state,
        limit=limit,
        fail_fast=fail_fast,
    )


@app.command("clip-color-set")
@handle_errors
def bulk_clip_color_set(
    color: str = typer.Argument(..., help="Clip color name (e.g. Orange, Teal) or 'clear' to remove"),
    track_type: str = _TRACK_TYPE,
    track: Optional[int] = _TRACK,
    name: Optional[str] = _NAME,
    name_starts_with: Optional[str] = _NAME_STARTS,
    name_contains: Optional[str] = _NAME_CONTAINS,
    name_regex: Optional[str] = _NAME_REGEX,
    duration: Optional[str] = _DURATION,
    min_duration: Optional[str] = _MIN_DURATION,
    max_duration: Optional[str] = _MAX_DURATION,
    start_ref: Optional[str] = _FROM,
    end_ref: Optional[str] = _TO,
    clip_color: Optional[str] = _CLIP_COLOR,
    enabled_state: Optional[str] = _STATE,
    limit: int = _LIMIT,
    fail_fast: bool = _FAIL_FAST,
):
    """Set (or clear) the clip color on every selected clip in one pass."""
    requested = color.strip()
    clearing = requested.lower() in {"clear", "none"}

    def operation(_conn, item, meta):
        if clearing:
            method = require_api_method(item, "ClearClipColor", capability_id="clip.color_flag", runtime_object="timeline_item")
            result = method()
        else:
            method = require_api_method(item, "SetClipColor", capability_id="clip.color_flag", runtime_object="timeline_item")
            result = method(requested)
        if result is False:
            raise APICallFailed("DaVinci Resolve rejected the clip color change.", details={"clip": meta["name"], "color": requested})
        return {"clip_color": None if clearing else requested}

    _run_bulk_mutation(
        action="clip-color-set",
        policy_id="clip.color_flag",
        operation=operation,
        extra={"color": None if clearing else requested, "clear": clearing},
        track_type=track_type,
        track=track,
        name=name,
        name_starts_with=name_starts_with,
        name_contains=name_contains,
        name_regex=name_regex,
        duration=duration,
        min_duration=min_duration,
        max_duration=max_duration,
        start_ref=start_ref,
        end_ref=end_ref,
        clip_color=clip_color,
        enabled_state=enabled_state,
        limit=limit,
        fail_fast=fail_fast,
    )


def _set_enabled_operation(enabled: bool):
    def operation(_conn, item, meta):
        method = require_api_method(item, "SetClipEnabled", capability_id="clip.enable_disable", runtime_object="timeline_item")
        result = method(enabled)
        if result is False:
            raise APICallFailed("DaVinci Resolve rejected the enable/disable change.", details={"clip": meta["name"], "enabled": enabled})
        return {"enabled": enabled}

    return operation


def _bulk_set_enabled(action: str, enabled: bool, kwargs: Dict[str, Any]) -> None:
    _run_bulk_mutation(
        action=action,
        policy_id="clip.enable_disable",
        operation=_set_enabled_operation(enabled),
        extra={"enabled": enabled},
        **kwargs,
    )


@app.command("enable")
@handle_errors
def bulk_enable(
    track_type: str = _TRACK_TYPE,
    track: Optional[int] = _TRACK,
    name: Optional[str] = _NAME,
    name_starts_with: Optional[str] = _NAME_STARTS,
    name_contains: Optional[str] = _NAME_CONTAINS,
    name_regex: Optional[str] = _NAME_REGEX,
    duration: Optional[str] = _DURATION,
    min_duration: Optional[str] = _MIN_DURATION,
    max_duration: Optional[str] = _MAX_DURATION,
    start_ref: Optional[str] = _FROM,
    end_ref: Optional[str] = _TO,
    clip_color: Optional[str] = _CLIP_COLOR,
    enabled_state: Optional[str] = _STATE,
    limit: int = _LIMIT,
    fail_fast: bool = _FAIL_FAST,
):
    """Enable every selected clip in one pass."""
    _bulk_set_enabled("enable", True, dict(
        track_type=track_type, track=track, name=name, name_starts_with=name_starts_with,
        name_contains=name_contains, name_regex=name_regex, duration=duration,
        min_duration=min_duration, max_duration=max_duration, start_ref=start_ref,
        end_ref=end_ref, clip_color=clip_color, enabled_state=enabled_state,
        limit=limit, fail_fast=fail_fast,
    ))


@app.command("disable")
@handle_errors
def bulk_disable(
    track_type: str = _TRACK_TYPE,
    track: Optional[int] = _TRACK,
    name: Optional[str] = _NAME,
    name_starts_with: Optional[str] = _NAME_STARTS,
    name_contains: Optional[str] = _NAME_CONTAINS,
    name_regex: Optional[str] = _NAME_REGEX,
    duration: Optional[str] = _DURATION,
    min_duration: Optional[str] = _MIN_DURATION,
    max_duration: Optional[str] = _MAX_DURATION,
    start_ref: Optional[str] = _FROM,
    end_ref: Optional[str] = _TO,
    clip_color: Optional[str] = _CLIP_COLOR,
    enabled_state: Optional[str] = _STATE,
    limit: int = _LIMIT,
    fail_fast: bool = _FAIL_FAST,
):
    """Disable every selected clip in one pass."""
    _bulk_set_enabled("disable", False, dict(
        track_type=track_type, track=track, name=name, name_starts_with=name_starts_with,
        name_contains=name_contains, name_regex=name_regex, duration=duration,
        min_duration=min_duration, max_duration=max_duration, start_ref=start_ref,
        end_ref=end_ref, clip_color=clip_color, enabled_state=enabled_state,
        limit=limit, fail_fast=fail_fast,
    ))


def _coerce_property_value(raw: str) -> Any:
    text = raw.strip()
    lowered = text.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    try:
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        pass
    return text


@app.command("property-set")
@handle_errors
def bulk_property_set(
    key: str = typer.Argument(..., help="Timeline item property key (e.g. ZoomX, Pan, Opacity)"),
    value: str = typer.Argument(..., help="Property value; numbers and true/false are auto-typed"),
    track_type: str = _TRACK_TYPE,
    track: Optional[int] = _TRACK,
    name: Optional[str] = _NAME,
    name_starts_with: Optional[str] = _NAME_STARTS,
    name_contains: Optional[str] = _NAME_CONTAINS,
    name_regex: Optional[str] = _NAME_REGEX,
    duration: Optional[str] = _DURATION,
    min_duration: Optional[str] = _MIN_DURATION,
    max_duration: Optional[str] = _MAX_DURATION,
    start_ref: Optional[str] = _FROM,
    end_ref: Optional[str] = _TO,
    clip_color: Optional[str] = _CLIP_COLOR,
    enabled_state: Optional[str] = _STATE,
    limit: int = _LIMIT,
    fail_fast: bool = _FAIL_FAST,
):
    """Set a timeline item property (transform, opacity, ...) on every selected clip."""
    coerced = _coerce_property_value(value)

    def operation(_conn, item, meta):
        method = require_api_method(item, "SetProperty", capability_id="clip.properties_write", runtime_object="timeline_item")
        result = method(key, coerced)
        if result is False:
            raise APICallFailed(
                "DaVinci Resolve rejected the property change.",
                details={"clip": meta["name"], "key": key, "value": coerced},
            )
        return {key: coerced}

    _run_bulk_mutation(
        action="property-set",
        policy_id="clip.properties_write",
        operation=operation,
        extra={"key": key, "value": coerced},
        track_type=track_type,
        track=track,
        name=name,
        name_starts_with=name_starts_with,
        name_contains=name_contains,
        name_regex=name_regex,
        duration=duration,
        min_duration=min_duration,
        max_duration=max_duration,
        start_ref=start_ref,
        end_ref=end_ref,
        clip_color=clip_color,
        enabled_state=enabled_state,
        limit=limit,
        fail_fast=fail_fast,
    )
