"""Private exact-target guard for SDK Inspector motion execution."""

from __future__ import annotations

import json
import os
from typing import Any

from ..errors import SdkMutationStaleRevision, ValidationError


SDK_CLIP_MOTION_TARGET_ENV = "CUTAGENT_SDK_EXPECTED_CLIP_MOTION_TARGET"


def expected_target() -> dict[str, Any] | None:
    raw = os.environ.get(SDK_CLIP_MOTION_TARGET_ENV)
    if raw is None:
        return None
    try:
        value = json.loads(raw)
    except Exception as exc:
        raise ValidationError("SDK clip motion target is malformed.") from exc
    required = {"id", "trackType", "trackIndex", "recordStartFrame", "recordEndFrame", "name", "linkedItemIds"}
    if not isinstance(value, dict) or set(value) != required or value.get("trackType") not in {"video", "audio"}:
        raise ValidationError("SDK timeline-item target is incomplete or has an invalid track type.")
    return value


def _native_id(item: Any) -> str:
    getter = getattr(item, "GetUniqueId", None)
    try:
        return str(getter() or "").strip() if callable(getter) else ""
    except Exception:
        return ""


def _linked_ids(item: Any) -> list[str] | None:
    getter = getattr(item, "GetLinkedItems", None)
    if not callable(getter):
        return None
    try:
        linked = getter()
    except Exception:
        return None
    if linked is None:
        return None
    ids = [_native_id(candidate) for candidate in linked]
    return sorted(ids) if all(ids) else None


def resolve_exact_timeline_item(conn: Any, target: dict[str, Any] | None = None) -> Any:
    expected = target or expected_target()
    if expected is None:
        raise ValidationError("SDK clip motion execution omitted its exact private target.")
    timeline = getattr(conn, "timeline", None)
    try:
        items = timeline.GetItemListInTrack(expected["trackType"], int(expected["trackIndex"])) or []
    except Exception as exc:
        raise ValidationError("SDK clip motion target track is unavailable.") from exc
    matches = []
    for item in items:
        try:
            if (_native_id(item) == expected["id"]
                    and int(item.GetStart()) == int(expected["recordStartFrame"])
                    and int(item.GetEnd()) == int(expected["recordEndFrame"])
                    and str(item.GetName() or "") == expected["name"]):
                matches.append(item)
        except Exception:
            continue
    if len(matches) != 1:
        raise SdkMutationStaleRevision(
            "SDK clip motion target changed before execution.",
            details={"match_count": len(matches)},
        )
    actual_links = _linked_ids(matches[0])
    if actual_links is None or actual_links != sorted(expected["linkedItemIds"]):
        raise SdkMutationStaleRevision(
            "SDK clip motion linked-media topology changed before execution."
        )
    return matches[0]
