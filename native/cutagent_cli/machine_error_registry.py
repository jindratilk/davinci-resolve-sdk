"""Packaged runtime boundary for stable public CutAgent CLI error codes."""

from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path
import re
from typing import Any


_PUBLIC_INVENTORY = Path(__file__).resolve().parent / "public_contract" / "sdk-inventory.json"
_CODE_PATTERN = re.compile(r"[A-Z][A-Z0-9_]+")
_MAX_ERRORS = 128


@lru_cache(maxsize=1)
def _stable_public_error_records() -> dict[str, dict[str, Any]]:
    """Load the generated, packaged registry without importing inventory tooling."""
    payload: Any = json.loads(_PUBLIC_INVENTORY.read_text(encoding="utf-8"))
    errors = payload.get("errors") if isinstance(payload, dict) else None
    if not isinstance(errors, list) or not errors or len(errors) > _MAX_ERRORS:
        raise RuntimeError("Packaged CutAgent CLI public error registry is invalid")
    records: dict[str, dict[str, Any]] = {}
    for entry in errors:
        code = entry.get("code") if isinstance(entry, dict) else None
        if not isinstance(code, str) or _CODE_PATTERN.fullmatch(code) is None or code in records:
            raise RuntimeError("Packaged CutAgent CLI public error registry is invalid")
        exit_code = entry.get("exit_code")
        retryability = entry.get("retryability")
        if (exit_code is not None and (not isinstance(exit_code, int) or exit_code < 1)) or retryability not in {
            "safe",
            "unsafe",
            "manual",
            "unknown",
        }:
            raise RuntimeError("Packaged CutAgent CLI public error registry is invalid")
        records[code] = dict(entry)
    return records


def stable_public_error_records() -> dict[str, dict[str, Any]]:
    """Return a defensive copy of the packaged stable registry."""
    return {code: dict(record) for code, record in _stable_public_error_records().items()}


def stable_public_error_codes() -> frozenset[str]:
    return frozenset(_stable_public_error_records())


def fail_closed_recoverability(code: object, requested: object) -> str:
    """Prevent generic machine envelopes from advising unsafe unchanged retries."""
    recoverability = requested if isinstance(requested, str) else "manual"
    if recoverability != "retryable":
        return recoverability
    try:
        record = _stable_public_error_records().get(code) if isinstance(code, str) else None
    except (OSError, RuntimeError, ValueError):
        return "manual"
    if (
        record is None
        or record["retryability"] != "safe"
        or record.get("possible_mutation") != "no"
    ):
        return "manual"
    return recoverability


def normalize_forwarded_error_code(
    value: object,
    *,
    fallback: str,
    expected_exit_code: int | None = None,
    expected_retryability: str | None = None,
) -> str:
    """Accept only registered broker codes; preserve unknown upstream codes in details."""
    records = _stable_public_error_records()
    if fallback not in records:
        raise RuntimeError(f"Unregistered public fallback error code: {fallback}")
    candidate = value.strip() if isinstance(value, str) else ""
    record = records.get(candidate)
    if record is None:
        return fallback
    if expected_exit_code is not None and record["exit_code"] != expected_exit_code:
        return fallback
    if expected_retryability is not None and record["retryability"] != expected_retryability:
        return fallback
    return candidate


def apply_forwarded_error_contract(error: Any, value: object, *, fallback: str) -> Any:
    """Apply a complete fail-closed public code/exit/recovery contract to a broker error."""
    records = _stable_public_error_records()
    code = normalize_forwarded_error_code(value, fallback=fallback)
    record = records[code]
    if not isinstance(record["exit_code"], int):
        code = fallback
        record = records[code]
    if not isinstance(record["exit_code"], int):
        raise RuntimeError(f"Forwarded fallback error lacks a stable exit code: {fallback}")
    error.code = code
    error.exit_code = record["exit_code"]
    requested = "retryable" if record["retryability"] == "safe" else "manual"
    error.recoverability = fail_closed_recoverability(code, requested)
    return error
