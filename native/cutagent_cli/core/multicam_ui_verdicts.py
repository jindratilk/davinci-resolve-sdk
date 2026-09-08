"""Manual DaVinci Resolve UI verdict registry helpers for known multicam families."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import json
import os
from pathlib import Path
import re
from typing import Any
import uuid

from ..errors import ValidationError

_DEFAULT_REGISTRY_PATH = Path(__file__).resolve().parent.parent / "fixtures" / "multicam_ui_verdicts.json"
_REGISTRY_PATH_ENV = "CUTAGENT_CLI_MULTICAM_UI_VERDICTS_PATH"
_ALLOWED_STATUSES = frozenset({"ui_confirmed", "ui_rejected"})
_ISO_DATE_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}")


@dataclass(frozen=True)
class ManualMulticamUIVerdict:
    rule_id: str
    status: str
    angle_count: int | None
    label: str
    verified_on: str | None
    clip_name_patterns: tuple[str, ...]
    notes: tuple[str, ...]


def registry_path(*, path_override: str | None = None) -> Path:
    candidate = path_override or os.getenv(_REGISTRY_PATH_ENV) or str(_DEFAULT_REGISTRY_PATH)
    return Path(candidate).expanduser().resolve()


def _normalize_status(status: str) -> str:
    normalized = str(status or "").strip()
    if normalized not in _ALLOWED_STATUSES:
        raise ValidationError(
            "Unsupported multicam UI verdict status.",
            details={
                "status": status,
                "allowed_statuses": sorted(_ALLOWED_STATUSES),
            },
        )
    return normalized


def _normalize_verified_on(verified_on: str | None, *, default_today: bool = False) -> str | None:
    normalized = str(verified_on or "").strip()
    if not normalized:
        return date.today().isoformat() if default_today else None
    if not _ISO_DATE_PATTERN.fullmatch(normalized):
        raise ValidationError(
            "Manual multicam UI verdict verified_on must be a YYYY-MM-DD date.",
            details={
                "verified_on": verified_on,
                "format": "YYYY-MM-DD",
            },
        )
    try:
        date.fromisoformat(normalized)
    except ValueError as exc:
        raise ValidationError(
            "Manual multicam UI verdict verified_on must be a valid calendar date.",
            details={
                "verified_on": verified_on,
                "format": "YYYY-MM-DD",
            },
        ) from exc
    return normalized


def validate_manual_multicam_ui_verdict_options(*, status: str, verified_on: str | None = None) -> dict[str, str | None]:
    """Validate user-facing verdict options before dry-run or mutation paths."""
    return {
        "status": _normalize_status(status),
        "verified_on": _normalize_verified_on(verified_on),
    }


def _normalize_rule(raw_rule: dict[str, Any]) -> ManualMulticamUIVerdict:
    if not isinstance(raw_rule, dict):
        raise ValidationError(
            "Manual multicam UI verdict registry entries must be objects.",
            details={"entry_type": type(raw_rule).__name__},
        )

    clip_name_patterns = tuple(
        str(pattern).strip()
        for pattern in list(raw_rule.get("clip_name_patterns") or [])
        if str(pattern).strip()
    )
    if not clip_name_patterns:
        raise ValidationError(
            "Manual multicam UI verdict requires at least one clip name pattern.",
            details={"rule_id": raw_rule.get("id")},
        )
    return ManualMulticamUIVerdict(
        rule_id=str(raw_rule.get("id") or "").strip(),
        status=_normalize_status(str(raw_rule.get("status") or "").strip()),
        angle_count=(int(raw_rule["angle_count"]) if raw_rule.get("angle_count") not in (None, "") else None),
        label=str(raw_rule.get("label") or "").strip() or "Manual multicam UI verdict",
        verified_on=_normalize_verified_on(raw_rule.get("verified_on")),
        clip_name_patterns=clip_name_patterns,
        notes=tuple(str(note).strip() for note in list(raw_rule.get("notes") or []) if str(note).strip()),
    )


def _rule_to_dict(rule: ManualMulticamUIVerdict) -> dict[str, Any]:
    return {
        "id": rule.rule_id,
        "status": rule.status,
        "angle_count": rule.angle_count,
        "label": rule.label,
        "verified_on": rule.verified_on,
        "clip_name_patterns": list(rule.clip_name_patterns),
        "notes": list(rule.notes),
    }


def load_multicam_ui_verdict_registry(*, path_override: str | None = None) -> dict[str, Any]:
    path = registry_path(path_override=path_override)
    if not path.exists():
        return {
            "registry_path": str(path),
            "schema_version": 1,
            "verdicts": [],
        }

    with open(path, "r", encoding="utf-8") as handle:
        raw_text = handle.read()
    if not raw_text.strip():
        return {
            "registry_path": str(path),
            "schema_version": 1,
            "verdicts": [],
        }
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ValidationError(
            "Manual multicam UI verdict registry is not valid JSON.",
            details={
                "registry_path": str(path),
                "line": exc.lineno,
                "column": exc.colno,
                "position": exc.pos,
            },
        ) from exc

    if not isinstance(payload, dict):
        raise ValidationError(
            "Manual multicam UI verdict registry must be a JSON object.",
            details={
                "registry_path": str(path),
                "payload_type": type(payload).__name__,
            },
        )

    raw_verdicts = payload.get("verdicts") or []
    if not isinstance(raw_verdicts, list):
        raise ValidationError(
            "Manual multicam UI verdict registry verdicts must be a list.",
            details={
                "registry_path": str(path),
                "verdicts_type": type(raw_verdicts).__name__,
            },
        )

    verdicts = [_normalize_rule(item) for item in raw_verdicts]
    return {
        "registry_path": str(path),
        "schema_version": int(payload.get("schema_version") or 1),
        "verdicts": [_rule_to_dict(item) for item in verdicts],
    }


def _write_multicam_ui_verdict_registry(*, verdicts: list[dict[str, Any]], path_override: str | None = None) -> dict[str, Any]:
    path = registry_path(path_override=path_override)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "verdicts": verdicts,
    }
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=True)
        handle.write("\n")
    return {
        "registry_path": str(path),
        "schema_version": 1,
        "verdicts": verdicts,
    }


def list_manual_multicam_ui_verdicts(*, path_override: str | None = None) -> dict[str, Any]:
    registry = load_multicam_ui_verdict_registry(path_override=path_override)
    return {
        "registry_path": registry["registry_path"],
        "schema_version": registry["schema_version"],
        "verdict_count": len(list(registry["verdicts"])),
        "verdicts": list(registry["verdicts"]),
    }


def upsert_manual_multicam_ui_verdict(
    *,
    status: str,
    label: str | None,
    angle_count: int | None,
    clip_name_patterns: list[str],
    notes: list[str] | None = None,
    verified_on: str | None = None,
    rule_id: str | None = None,
    path_override: str | None = None,
) -> dict[str, Any]:
    normalized_patterns = [str(pattern).strip() for pattern in clip_name_patterns if str(pattern).strip()]
    if not normalized_patterns:
        raise ValidationError(
            "Manual multicam UI verdict requires at least one clip name pattern.",
            details={"clip_name_patterns": clip_name_patterns},
        )

    normalized_status = _normalize_status(status)
    registry = load_multicam_ui_verdict_registry(path_override=path_override)
    existing_verdicts = list(registry["verdicts"])
    effective_rule_id = str(rule_id or "").strip() or f"manual_{normalized_status}_{uuid.uuid4().hex[:12]}"
    effective_label = str(label or "").strip() or f"Manual {normalized_status.replace('_', ' ')} verdict"
    effective_verified_on = _normalize_verified_on(verified_on, default_today=True)
    normalized_notes = [str(note).strip() for note in list(notes or []) if str(note).strip()]

    updated = {
        "id": effective_rule_id,
        "status": normalized_status,
        "angle_count": int(angle_count) if angle_count not in (None, "") else None,
        "label": effective_label,
        "verified_on": effective_verified_on,
        "clip_name_patterns": normalized_patterns,
        "notes": normalized_notes,
    }

    replaced = False
    for index, verdict in enumerate(existing_verdicts):
        if str(verdict.get("id") or "") == effective_rule_id:
            existing_verdicts[index] = updated
            replaced = True
            break
    if not replaced:
        existing_verdicts.append(updated)

    written = _write_multicam_ui_verdict_registry(verdicts=existing_verdicts, path_override=path_override)
    return {
        "registry_path": written["registry_path"],
        "schema_version": written["schema_version"],
        "updated_verdict": updated,
        "replaced_existing": replaced,
        "verdict_count": len(existing_verdicts),
    }


def remove_manual_multicam_ui_verdict(*, rule_id: str, path_override: str | None = None) -> dict[str, Any]:
    normalized_rule_id = str(rule_id or "").strip()
    if not normalized_rule_id:
        raise ValidationError(
            "Manual multicam UI verdict removal requires a rule id.",
            details={"rule_id": rule_id},
        )

    registry = load_multicam_ui_verdict_registry(path_override=path_override)
    existing_verdicts = list(registry["verdicts"])
    kept_verdicts = [verdict for verdict in existing_verdicts if str(verdict.get("id") or "") != normalized_rule_id]
    removed = len(kept_verdicts) != len(existing_verdicts)

    written = _write_multicam_ui_verdict_registry(verdicts=kept_verdicts, path_override=path_override)
    return {
        "registry_path": written["registry_path"],
        "schema_version": written["schema_version"],
        "removed": removed,
        "rule_id": normalized_rule_id,
        "verdict_count": len(kept_verdicts),
    }


def resolve_manual_multicam_ui_verdict(
    *,
    multicam_name: str,
    angle_count: int | None,
    path_override: str | None = None,
) -> dict[str, Any]:
    normalized_name = str(multicam_name or "").strip()
    normalized_angle_count = int(angle_count or 0)
    registry = load_multicam_ui_verdict_registry(path_override=path_override)

    for raw_rule in list(registry["verdicts"]):
        rule = _normalize_rule(raw_rule)
        if rule.angle_count is not None and normalized_angle_count and rule.angle_count != normalized_angle_count:
            continue
        for pattern in rule.clip_name_patterns:
            try:
                if re.search(pattern, normalized_name):
                    return {
                        "status": rule.status,
                        "source": "repo_manual_registry",
                        "matched_rule_id": rule.rule_id,
                        "label": rule.label,
                        "verified_on": rule.verified_on,
                        "notes": list(rule.notes),
                    }
            except re.error:
                continue

    return {
        "status": "not_recorded",
        "source": "repo_manual_registry",
        "matched_rule_id": None,
        "label": "No manual UI verdict recorded",
        "verified_on": None,
        "notes": [
            "No explicit DaVinci Resolve UI verdict is recorded for this multicam family in the repo registry.",
        ],
    }
