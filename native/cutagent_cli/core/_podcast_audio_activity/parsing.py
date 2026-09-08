"""Parsing helpers for podcast audio activity planning."""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
import statistics
import struct
import subprocess
import tempfile
from typing import Any, Iterable
import wave

from ...errors import APICallFailed, ValidationError
from ...external_tools import resolve_tool
from .. import waveform_sync
from .._podcast_multicam.audio_activity_v2 import io as audio_activity_v2_io
from .._podcast_multicam.audio_activity_v2 import plan as audio_activity_v2_plan
from .._podcast_multicam.transcript import normalize_scribe_v2_transcript
from .common import *


def parse_key_value_spec(spec: str, *, value_name: str) -> tuple[str, str]:
    text = str(spec or "").strip()
    if "=" not in text:
        raise ValidationError(
            f"{value_name} spec must use id=value syntax.",
            details={"spec": spec},
        )
    key, value = [part.strip() for part in text.split("=", 1)]
    if not key or not value:
        raise ValidationError(
            f"{value_name} spec must use non-empty id=value syntax.",
            details={"spec": spec},
        )
    return key, value


def parse_audio_sources(specs: Iterable[str] | None) -> list[dict[str, str]]:
    sources: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw in list(specs or []):
        source_id, source_path = parse_key_value_spec(raw, value_name="Audio source")
        if source_id in seen:
            raise ValidationError(
                "Audio source ids must be unique.",
                details={"audio_source_id": source_id},
            )
        seen.add(source_id)
        sources.append({"id": source_id, "path": source_path})
    return sources


def parse_audio_angle_map(mapping: str | None) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for raw_entry in str(mapping or "").split(","):
        entry = raw_entry.strip()
        if not entry:
            continue
        source_id, angle = parse_key_value_spec(entry, value_name="Audio angle map")
        parsed[source_id] = angle
    return parsed


def parse_audio_targets(specs: Iterable[str] | None) -> dict[str, dict[str, Any]]:
    targets: dict[str, dict[str, Any]] = {}
    for raw in list(specs or []):
        source_id, angle_list = parse_key_value_spec(raw, value_name="Audio target")
        angles = [part.strip() for part in angle_list.split(",") if part.strip()]
        if not angles:
            raise ValidationError(
                "Audio target requires at least one angle.",
                details={"spec": raw, "audio_source_id": source_id},
            )
        targets[source_id] = {
            "angles": angles,
            "selection": "default" if len(angles) == 1 else "agent_decides",
        }
    return targets


def load_audio_offsets_payload(path: str | None) -> dict[str, Any]:
    value = str(path or "").strip()
    if not value:
        return {}
    expanded = Path(value).expanduser()
    if not expanded.is_file():
        raise ValidationError("Audio offsets JSON file not found.", details={"path": str(expanded)})
    try:
        payload = json.loads(expanded.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValidationError(
            "Audio offsets JSON is not valid.",
            details={"path": str(expanded), "line": exc.lineno, "column": exc.colno},
        ) from exc
    if not isinstance(payload, dict):
        raise ValidationError(
            "Audio offsets JSON must be an object or an object with offsets.",
            details={"path": str(expanded)},
        )
    if isinstance(payload.get("offsets"), dict):
        offsets_raw = payload["offsets"]
        offsets_seconds_raw = payload.get("offsets_seconds") if isinstance(payload.get("offsets_seconds"), dict) else {}
        result: dict[str, Any] = {
            "offsets": {str(key): int(value) for key, value in offsets_raw.items()},
        }
        if offsets_seconds_raw:
            result["offsets_seconds"] = {
                str(key): float(value)
                for key, value in offsets_seconds_raw.items()
                if str(key) in result["offsets"]
            }
        for key in ("schema_version", "fps", "offset_domain", "anchor", "anchor_label", "anchor_angle"):
            if key in payload:
                result[key] = payload[key]
        return result
    return {"offsets": {str(key): int(value) for key, value in payload.items()}}


def load_audio_offsets_json(path: str | None) -> dict[str, int]:
    payload = load_audio_offsets_payload(path)
    offsets = payload.get("offsets") if isinstance(payload, dict) else None
    return dict(offsets or {})


__all__ = (
    'parse_key_value_spec',
    'parse_audio_sources',
    'parse_audio_angle_map',
    'parse_audio_targets',
    'load_audio_offsets_payload',
    'load_audio_offsets_json',
)
