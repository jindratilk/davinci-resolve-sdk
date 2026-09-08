"""Output formatting — JSON, Rich tables, quiet mode."""

from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Sequence

from rich.console import Console
from rich.table import Table
from . import __version__

console = Console()
err_console = Console(stderr=True)

# Global output mode — set by main.py callback
_output_mode: str = "table"  # "table" | "json" | "quiet" | "plain" | "agent"

# Lean JSON: opt-in envelope diet (drop null meta fields). Backward compatible —
# only active with --lean or CUTAGENT_CLI_LEAN=1.
_lean: bool = False
_prepared_action_output_capture: ContextVar[list[Any] | None] = ContextVar(
    "cutagent_prepared_action_output_capture", default=None
)


@contextmanager
def capture_prepared_action_output():
    """Capture one private command handler's raw output without rendering it."""

    captured: list[Any] = []
    token = _prepared_action_output_capture.set(captured)
    try:
        yield captured
    finally:
        _prepared_action_output_capture.reset(token)


def set_output_mode(mode: str) -> None:
    global _output_mode
    _output_mode = mode


def set_lean(value: bool) -> None:
    global _lean
    _lean = bool(value)


def is_lean() -> bool:
    return _lean or os.environ.get("CUTAGENT_CLI_LEAN") == "1"


def get_output_mode() -> str:
    return _output_mode


_command_name: str = "cutagent"
_command_start_monotonic: float = time.monotonic()
_engine: str = "api_native"
_engine_confidence: float = 1.0
_verification_status: str = "not_requested"
_recoverability: str = "not_applicable"
_policy_profile: str = "auto_edit"
_capability_id: str | None = None
_capability_status: str | None = None
_intent_id: str | None = None
_pre_state_hash: str | None = None
_post_state_hash: str | None = None
_rollback_hint: str | None = None
_response_emitted: bool = False
_verbose: bool = False


def set_command_context(command_name: str) -> None:
    """Set command metadata context for response envelopes."""
    global _command_name, _command_start_monotonic, _engine, _engine_confidence
    global _verification_status, _recoverability
    global _policy_profile, _capability_id, _capability_status
    global _intent_id, _pre_state_hash, _post_state_hash, _rollback_hint
    global _response_emitted, _verbose, _select_fields
    _command_name = command_name
    _command_start_monotonic = time.monotonic()
    _engine = "api_native"
    _engine_confidence = 1.0
    _verification_status = "not_requested"
    _recoverability = "not_applicable"
    _policy_profile = "auto_edit"
    _capability_id = None
    _capability_status = None
    _intent_id = None
    _pre_state_hash = None
    _post_state_hash = None
    _rollback_hint = None
    _response_emitted = False
    _verbose = False
    _select_fields = None


def _default_engine_confidence(engine: str) -> float:
    if engine in {"api_native", "fusion_native", "hosted_api"}:
        return 1.0
    if engine == "db_direct":
        return 0.85
    if engine == "db_workaround":
        return 0.9
    if engine == "workaround_setting":
        return 0.75
    if engine == "resolve_gui":
        return 0.65
    if engine == "not_available":
        return 0.0
    return 0.5


def set_execution_engine(engine: str, confidence: float | None = None) -> None:
    """Set execution engine metadata for current command."""
    global _engine, _engine_confidence
    _engine = engine
    _engine_confidence = _default_engine_confidence(engine) if confidence is None else float(confidence)


def set_engine_confidence(confidence: float) -> None:
    global _engine_confidence
    _engine_confidence = float(confidence)


def set_verification_status(status: str) -> None:
    global _verification_status
    _verification_status = status


def fail_active_verification_status() -> None:
    """Mark stale positive verification metadata as failed after command errors."""
    global _verification_status
    if _verification_status not in {"not_requested", "not_available"}:
        _verification_status = "failed"


def set_recoverability(recoverability: str) -> None:
    global _recoverability
    _recoverability = recoverability


def set_intent_context(
    intent_id: str | None,
    pre_state_hash: str | None,
    post_state_hash: str | None,
    rollback_hint: str | None,
) -> None:
    global _intent_id, _pre_state_hash, _post_state_hash, _rollback_hint
    _intent_id = intent_id
    _pre_state_hash = pre_state_hash
    _post_state_hash = post_state_hash
    _rollback_hint = rollback_hint


def set_policy_profile(profile: str) -> None:
    global _policy_profile
    _policy_profile = str(profile)


def set_verbose(value: bool) -> None:
    global _verbose
    _verbose = bool(value)


def is_verbose() -> bool:
    return _verbose


def set_capability_context(capability_id: str | None, capability_status: str | None) -> None:
    global _capability_id, _capability_status
    _capability_id = capability_id
    _capability_status = capability_status


def is_machine_mode() -> bool:
    """JSON and agent modes share the machine contract paths (envelopes, errors)."""
    return get_output_mode() in {"json", "agent"}


def is_agent_mode() -> bool:
    return get_output_mode() == "agent"


def _duration_ms() -> int:
    return int((time.monotonic() - _command_start_monotonic) * 1000)


def _meta() -> dict[str, Any]:
    return {
        "command": _command_name,
        "version": __version__,
        "duration_ms": _duration_ms(),
        "dry_run": _dry_run,
        "engine": _engine,
        "engine_confidence": _engine_confidence,
        "verification_status": _verification_status,
        "recoverability": _recoverability,
        "policy_profile": _policy_profile,
        "capability_id": _capability_id,
        "capability_status": _capability_status,
        "intent_id": _intent_id,
        "pre_state_hash": _pre_state_hash,
        "post_state_hash": _post_state_hash,
        "rollback_hint": _rollback_hint,
    }


def _public_error_envelope_enabled() -> bool:
    return os.environ.get("CUTAGENT_CLI_PUBLIC_ERROR_ENVELOPE") == "1"


# Remediation hints surfaced to humans and agents alongside error envelopes.
_SUGGESTED_FIXES_BY_CODE: dict[str, str] = {
    "AUTH_REQUIRED": "Open the CutAgent app and sign in to use CutAgent CLI.",
    "SUBSCRIPTION_REQUIRED": "Your CutAgent plan is inactive. Renew your subscription in the CutAgent app to use CutAgent CLI.",
    "AUTH_TOKEN_EXPIRED": "Retry the command to request fresh authorization.",
    "AUTH_TOKEN_INVALID": "Retry the command. If the problem persists, restart the CutAgent app.",
    "AUTH_TOKEN_COMMAND_MISMATCH": "Retry the command. If the problem persists, restart the CutAgent app.",
    "EDIT_CONSTRAINT_VIOLATION": (
        "Review user-owned editing constraints and select an exact permitted stable target "
        "before trying again."
    ),
    "RESOLVE_NOT_RUNNING": "Start DaVinci Resolve, then retry the command.",
    "RESOLVE_SCRIPTING_UNAVAILABLE": (
        "Enable local external scripting in DaVinci Resolve Studio and restart it, "
        "or run Workspace > Scripts > CutAgent in DaVinci Resolve Free."
    ),
}


def default_suggested_fix(code: Any) -> str | None:
    """Return the default remediation hint for a stable error code."""
    if not isinstance(code, str):
        return None
    return _SUGGESTED_FIXES_BY_CODE.get(code)


def _error_meta() -> dict[str, Any]:
    meta = _meta()
    if _public_error_envelope_enabled():
        meta.pop("engine", None)
        meta.pop("engine_confidence", None)
    return meta


def _safe_json_text(value: Any, *, fallback: str = "Unserializable value") -> str:
    """Return text without trusting foreign API objects' __str__ implementations."""
    try:
        text = str(value)
        if isinstance(text, str) and text:
            return _public_command_text(text)
    except Exception:
        pass

    try:
        candidate = getattr(value, "message", None)
    except Exception:
        candidate = None
    if isinstance(candidate, str) and candidate:
        return _public_command_text(candidate)

    if value is not None:
        class_name = value.__class__.__name__
        if class_name:
            return class_name
    return fallback


def _public_command_text(value: str) -> str:
    """Normalize public command examples without rewriting internal resource ids."""
    return value.replace("cutagent-cli ", "cutagent ")


def _make_json_safe(value: Any) -> Any:
    """Recursively convert DaVinci Resolve/Python proxy objects into JSON-safe values."""
    if isinstance(value, str):
        return _public_command_text(value)
    if value is None or isinstance(value, (int, float, bool)):
        return value

    if isinstance(value, dict):
        return {
            key if isinstance(key, str) else _safe_json_text(key, fallback="key"): _make_json_safe(item)
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple, set, frozenset)):
        return [_make_json_safe(item) for item in value]

    return _safe_json_text(value)


class ResponseBuilder:
    """Builds contract envelopes for successful and failed JSON responses."""

    @staticmethod
    def success(data: Any) -> dict[str, Any]:
        return {
            "ok": True,
            "data": data,
            "error": None,
            "meta": _meta(),
        }

    @staticmethod
    def error(
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
        suggested_fix: str | None = None,
    ) -> dict[str, Any]:
        safe_code = _safe_json_text(code, fallback="INTERNAL_ERROR")
        fix = suggested_fix if isinstance(suggested_fix, str) and suggested_fix else default_suggested_fix(safe_code)
        return {
            "ok": False,
            "data": None,
            "error": {
                "code": safe_code,
                "message": _safe_json_text(message, fallback="Unknown error."),
                "suggested_fix": fix,
                "details": _make_json_safe(details or {}),
            },
            "meta": _error_meta(),
        }


def _envelope(
    *,
    ok: bool,
    data: Any = None,
    error: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if ok:
        return ResponseBuilder.success(data)
    payload_error = error or {"code": "INTERNAL_ERROR", "message": "Unknown error.", "details": {}}
    payload_fix = payload_error.get("suggested_fix")
    return ResponseBuilder.error(
        code=_safe_json_text(payload_error.get("code", "INTERNAL_ERROR"), fallback="INTERNAL_ERROR"),
        message=_safe_json_text(payload_error.get("message", "Unknown error."), fallback="Unknown error."),
        details=payload_error.get("details") if isinstance(payload_error.get("details"), dict) else {},
        suggested_fix=payload_fix if isinstance(payload_fix, str) and payload_fix else None,
    )


# Global select fields — comma-separated field names to filter output columns
_select_fields: list[str] | None = None


def set_select_fields(fields: str) -> None:
    """Set field filter from comma-separated string (e.g. 'name,duration')."""
    global _select_fields
    _select_fields = [f.strip() for f in fields.split(",") if f.strip()]


def get_select_fields() -> list[str] | None:
    return _select_fields


# Global dry-run flag
_dry_run: bool = False


def set_dry_run(value: bool) -> None:
    global _dry_run
    _dry_run = value


def is_dry_run() -> bool:
    return _dry_run


def dry_run_message(msg: str) -> None:
    """Print a dry-run message and return."""
    if get_output_mode() in {"json", "agent"}:
        if not has_response_emitted():
            output({"message": f"DRY-RUN: {msg}"})
        return
    err_console.print(f"[yellow]DRY-RUN:[/yellow] {msg}")


def _lean_envelope(payload: Any) -> Any:
    """Drop null meta fields from an envelope (lean JSON diet, opt-in)."""
    if not isinstance(payload, dict) or not isinstance(payload.get("meta"), dict):
        return payload
    lean = dict(payload)
    lean["meta"] = {key: value for key, value in payload["meta"].items() if value is not None}
    return lean


def print_json(data: Any) -> None:
    """Emit a machine payload: pretty JSON in json mode, compact text in agent mode."""
    global _response_emitted
    if _response_emitted:
        return
    _response_emitted = True
    safe = _make_json_safe(data)
    if get_output_mode() == "agent":
        from .agent_output import maybe_spill, render_envelope

        if isinstance(safe, dict) and "ok" in safe and "meta" in safe:
            rendered = render_envelope(safe, columns=_consume_render_columns())
            command = (safe.get("meta") or {}).get("command")
        else:
            rendered = json.dumps(safe, ensure_ascii=False, default=_safe_json_text)
            command = None
        print(maybe_spill(rendered, command))
        return
    if is_lean():
        safe = _lean_envelope(safe)
    print(json.dumps(safe, indent=2, ensure_ascii=False, default=_safe_json_text))


# Column hints for the agent renderer, set by output() just before print_json.
_render_columns: list[tuple[str, str]] | None = None


def _set_render_columns(columns: list[tuple[str, str]] | None) -> None:
    global _render_columns
    _render_columns = columns


def _consume_render_columns() -> list[tuple[str, str]] | None:
    global _render_columns
    columns = _render_columns
    _render_columns = None
    return columns


def has_response_emitted() -> bool:
    return _response_emitted


def json_error(
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
    suggested_fix: str | None = None,
) -> None:
    """Print error envelope in machine modes (json/agent)."""
    if get_output_mode() not in {"json", "agent"}:
        return
    print_json(
        _envelope(
            ok=False,
            error={
                "code": code,
                "message": message,
                "suggested_fix": suggested_fix,
                "details": details or {},
            },
        )
    )


def print_value(value: Any) -> None:
    """Print a single value (quiet mode)."""
    if isinstance(value, (list, tuple)):
        for item in value:
            console.print(str(item))
    elif isinstance(value, dict):
        for k, v in value.items():
            console.print(f"{k}: {v}")
    else:
        console.print(str(value))


def _apply_select(
    rows: Sequence[dict],
    columns: list[tuple[str, str]] | None,
) -> tuple[Sequence[dict], list[tuple[str, str]] | None]:
    """Filter rows and columns based on _select_fields."""
    fields = get_select_fields()
    if not fields:
        return rows, columns

    if columns is not None:
        columns = [(k, h) for k, h in columns if k in fields]
    else:
        columns = [(f, f.replace("_", " ").title()) for f in fields]

    rows = [{k: row.get(k, "") for k in fields} for row in rows]
    return rows, columns


def print_plain(
    rows: Sequence[dict],
    columns: list[tuple[str, str]] | None = None,
) -> None:
    """Print data as TSV (tab-separated values, no colors, no borders)."""
    if not rows:
        return

    if columns is None:
        columns = [(k, k) for k in rows[0].keys()]

    # Header row
    print("\t".join(h for _, h in columns))

    # Data rows
    for row in rows:
        print("\t".join(str(row.get(key, "")) for key, _ in columns))


def print_table(
    rows: Sequence[dict],
    columns: list[tuple[str, str]] | None = None,
    title: str | None = None,
) -> None:
    """
    Print a Rich table from list of dicts.
    
    columns: list of (key, header) tuples. If None, auto-detect from first row.
    """
    if not rows:
        console.print("[dim]No results.[/dim]")
        return

    if columns is None:
        columns = [(k, k.replace("_", " ").title()) for k in rows[0].keys()]

    table = Table(title=title, show_lines=False)
    for _, header in columns:
        table.add_column(header)

    for row in rows:
        table.add_row(*[str(row.get(key, "")) for key, _ in columns])

    console.print(table)


def output(
    data: Any,
    columns: list[tuple[str, str]] | None = None,
    title: str | None = None,
    quiet_key: str | None = None,
) -> None:
    """
    Universal output function. Respects current output mode.
    
    data: dict, list of dicts, or scalar
    columns: for table mode
    quiet_key: which key to print in quiet mode (for list of dicts)
    """
    captured = _prepared_action_output_capture.get()
    if captured is not None:
        captured.append(_make_json_safe(data))
        return
    mode = get_output_mode()

    # Apply select filtering for list-of-dict data
    if isinstance(data, list) and data and isinstance(data[0], dict) and get_select_fields():
        data, columns = _apply_select(data, columns)
    elif isinstance(data, dict) and get_select_fields() and mode in {"json", "agent"}:
        fields = get_select_fields()
        data = {k: v for k, v in data.items() if k in fields}

    if mode in {"json", "agent"}:
        _set_render_columns(columns)
        print_json(_envelope(ok=True, data=data))
        return

    if mode == "quiet":
        if isinstance(data, list) and quiet_key:
            for row in data:
                console.print(str(row.get(quiet_key, "")))
        elif isinstance(data, list):
            for row in data:
                if isinstance(row, dict):
                    console.print(str(list(row.values())[0]) if row else "")
                else:
                    console.print(str(row))
        elif isinstance(data, dict) and quiet_key:
            console.print(str(data.get(quiet_key, "")))
        else:
            print_value(data)
        return

    if mode == "plain":
        if isinstance(data, list) and data and isinstance(data[0], dict):
            print_plain(data, columns=columns)
        elif isinstance(data, dict):
            rows = [{"key": k, "value": v} for k, v in data.items()]
            print_plain(rows, columns=[("key", "Key"), ("value", "Value")])
        else:
            print_value(data)
        return

    # Table mode
    if isinstance(data, list) and data and isinstance(data[0], dict):
        print_table(data, columns=columns, title=title)
    elif isinstance(data, dict):
        # Single dict — key/value table
        rows = [{"key": k, "value": v} for k, v in data.items()]
        print_table(rows, columns=[("key", "Key"), ("value", "Value")], title=title)
    else:
        print_value(data)


def success(msg: str) -> None:
    """Print a success message."""
    captured = _prepared_action_output_capture.get()
    if captured is not None:
        captured.append({"message": str(msg)})
        return
    if get_output_mode() in {"json", "agent"}:
        if not has_response_emitted():
            output({"message": msg})
        return
    console.print(f"[green]✓[/green] {msg}")


def mutation_payload(
    *,
    action: str,
    target: dict[str, Any] | None = None,
    changed: bool = True,
    **fields: Any,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "action": action,
        "changed": changed,
    }
    if target is not None:
        payload["target"] = target
    payload.update(fields)
    return payload


def warning(msg: str) -> None:
    """Print a warning."""
    if get_output_mode() in {"json", "agent"}:
        if not has_response_emitted():
            output({"warning": msg})
        return
    err_console.print(f"[yellow]⚠[/yellow] {msg}")


def info(msg: str) -> None:
    """Print an info message."""
    if get_output_mode() in {"json", "agent"}:
        if not has_response_emitted():
            output({"info": msg})
        return
    err_console.print(f"[blue]ℹ[/blue] {msg}")
