"""Shared helpers for command-local batch operations."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Iterable

from ..errors import CLIError, ValidationError

_BATCH_WRAPPER_KEYS = ("entries", "items", "segments", "updates", "batch")


def load_batch_entries(
    *,
    batch_path: str | Path | None = None,
    batch_json: str | None = None,
    input_path: str | Path | None = None,
    wrapper_keys: Iterable[str] = _BATCH_WRAPPER_KEYS,
) -> list[dict[str, Any]]:
    """Load a batch array from a file, inline JSON, or common object wrappers."""
    provided = [value is not None for value in (batch_path, batch_json, input_path)]
    if sum(provided) != 1:
        raise ValidationError(
            "Provide exactly one batch input source.",
            details={"batch": str(batch_path) if batch_path else None, "batch_json": bool(batch_json), "input": str(input_path) if input_path else None},
        )

    if batch_json is not None:
        source = "batch_json"
        raw = batch_json
    else:
        source = "batch" if batch_path is not None else "input"
        path = Path(batch_path if batch_path is not None else input_path).expanduser()
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ValidationError("Could not read batch input file.", details={"path": str(path), "error": str(exc)}) from exc

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValidationError("Invalid JSON batch input.", details={"source": source, "error": str(exc)}) from exc

    entries_obj = parsed
    if isinstance(parsed, dict):
        for key in wrapper_keys:
            if key in parsed:
                entries_obj = parsed[key]
                break
        else:
            raise ValidationError(
                "Batch JSON object must contain one of the supported wrapper keys.",
                details={"source": source, "supported_keys": list(wrapper_keys)},
            )

    if not isinstance(entries_obj, list):
        raise ValidationError("Batch input must resolve to a JSON array.", details={"source": source})

    entries: list[dict[str, Any]] = []
    for index, entry in enumerate(entries_obj):
        if not isinstance(entry, dict):
            raise ValidationError("Batch entries must be JSON objects.", details={"index": index, "entry_type": type(entry).__name__})
        entries.append({"index": index, **entry})
    return entries


def cli_error_payload(exc: BaseException) -> dict[str, Any]:
    """Return a stable per-entry error object, preserving CLIError codes."""
    if isinstance(exc, CLIError):
        return {
            "code": exc.code,
            "message": str(exc),
            "details": exc.details,
            "recoverability": exc.recoverability,
        }
    return {
        "code": "INTERNAL_ERROR",
        "message": str(exc) or exc.__class__.__name__,
        "details": {},
        "recoverability": "fatal",
    }


def count_results(results: Iterable[dict[str, Any]]) -> dict[str, int]:
    rows = list(results)
    updated_count = sum(1 for row in rows if row.get("ok") and row.get("changed"))
    skipped_count = sum(1 for row in rows if row.get("skipped"))
    failure_count = sum(1 for row in rows if row.get("error"))
    planned_count = sum(1 for row in rows if not row.get("error"))
    return {
        "requested_count": len(rows),
        "planned_count": planned_count,
        "updated_count": updated_count,
        "skipped_count": skipped_count,
        "failure_count": failure_count,
    }


def preflight_entries(
    entries: Iterable[dict[str, Any]],
    planner: Callable[[dict[str, Any]], dict[str, Any]],
    *,
    allow_partial: bool = False,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Run preflight for every entry and optionally fail the whole batch."""
    plans: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for entry in entries:
        index = int(entry.get("index", len(results)))
        try:
            plan = planner(entry)
            plans.append(plan)
            results.append({"index": index, "ok": True, "skipped": bool(plan.get("skipped")), "preflight": plan.get("preflight", plan)})
        except Exception as exc:
            error = cli_error_payload(exc)
            row = {"index": index, "ok": False, "skipped": False, "error": error}
            results.append(row)
            failures.append(row)

    if failures and not allow_partial:
        raise ValidationError(
            "Batch preflight failed; no mutations were applied.",
            details={"failure_count": len(failures), "failures": failures},
        )
    return plans, results


def batch_payload(
    *,
    action: str,
    target: dict[str, Any] | None = None,
    changed: bool,
    dry_run: bool = False,
    allow_partial: bool = False,
    preflight: dict[str, Any] | None = None,
    results: list[dict[str, Any]],
    verification: dict[str, Any] | None = None,
    **fields: Any,
) -> dict[str, Any]:
    """Build the stable command-local batch response shape."""
    payload: dict[str, Any] = {
        "action": action,
        "changed": bool(changed),
        "dry_run": bool(dry_run),
        "allow_partial": bool(allow_partial),
        **count_results(results),
    }
    if target is not None:
        payload["target"] = target
    payload["preflight"] = preflight or {}
    payload["results"] = results
    payload["verification"] = verification or {}
    payload.update(fields)
    return payload
