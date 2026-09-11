from __future__ import annotations

import base64
import hashlib
import math
import re
import struct
from typing import Any

from ...errors import ValidationError

_UUID_PATTERN = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"


def _decode_rate_blob(blob: bytes | None) -> float | None:
    if not blob or len(blob) < 8:
        return None
    try:
        return float(struct.unpack("<d", blob[:8])[0])
    except Exception:
        return None


def _encode_rate_blob(fps: float, template: bytes | None = None) -> bytes:
    safe_fps = float(fps)
    if not math.isfinite(safe_fps) or safe_fps <= 0:
        raise ValidationError(
            "Native multicam frame rate must be a finite positive number.",
            details={"fps": fps},
        )
    suffix = bytes(template[8:]) if template and len(template) >= 8 else b"\x00" * 8
    return struct.pack("<d", safe_fps) + suffix


def _encode_media_timemap_ba(duration_frames: int, fps: float) -> bytes:
    bounded_duration = max(1, int(duration_frames))
    safe_fps = fps if fps > 0 else 24.0
    duration_seconds = max(0.0, (bounded_duration - 1) / safe_fps)
    return b"\x02" + struct.pack(">d", duration_seconds)


def _encode_sequence_media_extents(item_start: str, duration_frames: int, fps: float) -> bytes:
    safe_fps = fps if fps > 0 else 24.0
    start_frame = int(str(item_start or "0"))
    start_seconds = start_frame / safe_fps
    duration_seconds = max(0.0, int(duration_frames) / safe_fps)
    return struct.pack("<dd", start_seconds, duration_seconds)


def _decode_optional_bytes(value: Any) -> bytes | None:
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise ValidationError(
            "Native multicam reference fixture is invalid.",
            details={"field_value": value, "reason": "expected_base64_string"},
        )
    try:
        return base64.b64decode(value)
    except Exception as exc:  # pragma: no cover - defensive
        raise ValidationError(
            "Native multicam reference fixture could not be decoded.",
            details={"reason": "invalid_base64"},
        ) from exc


def _optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _extract_blob_uuids(blob: bytes | None) -> list[str]:
    if not blob:
        return []
    try:
        text = blob.decode("utf-16-be", errors="ignore")
    except Exception:
        return []
    return re.findall(_UUID_PATTERN, text, flags=re.IGNORECASE)


def _replace_utf16_uuid(blob: bytes | None, old_uuid: str | None, new_uuid: str | None) -> bytes | None:
    if not blob or not old_uuid or not new_uuid or old_uuid == new_uuid:
        return blob
    return blob.replace(old_uuid.encode("utf-16-le"), new_uuid.encode("utf-16-le"))


def _remap_sequence_fields_blob(
    blob: bytes | None,
    *,
    new_sequence_container_id: str,
    new_unique_sequence_id: str,
) -> bytes | None:
    updated = blob
    uuids = _extract_blob_uuids(updated)
    if uuids:
        updated = _replace_utf16_uuid(updated, uuids[0], new_unique_sequence_id)
    if len(uuids) > 1:
        updated = _replace_utf16_uuid(updated, uuids[1], new_sequence_container_id)
    return updated


def _selector_signature(blob: bytes | None) -> str | None:
    if not blob:
        return None
    return hashlib.sha1(blob).hexdigest()[:16]


def _normalized_selector_idx(value: Any) -> int:
    return int(value) if value not in (None, "") else 0


def _ordered_selector_values(mapping: list[dict[str, Any]]) -> list[int]:
    ordered = sorted(mapping, key=lambda entry: int(entry.get("angle_index") or 0))
    return [_normalized_selector_idx(entry.get("current_selector_idx")) for entry in ordered]
