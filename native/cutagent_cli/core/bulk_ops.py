"""Selector-driven bulk operations over timeline items.

One CLI invocation selects clips by properties (track, name, duration, range,
color, enabled state) and applies a mutation to every match inside a single
Resolve connection. This replaces N per-clip invocations — each of which paid
process startup, a fresh Resolve connection, clip-by-name resolution, and,
when driven by an agent, a full model round-trip.

The selector operates on live TimelineItem handles, so operations never
re-resolve clips by name (duplicate clip names stay unambiguous).
"""

from __future__ import annotations

import re
import time
from typing import Any, Callable, Dict, List, Optional

from ..errors import ValidationError
from ..utils.timecode import frames_to_seconds, parse_time_input, seconds_to_timecode

# Half a frame of tolerance: "duration 4s" must match a clip that is exactly
# 96 frames at 24fps even when float fps arithmetic wobbles.
_DURATION_EPSILON_FRAMES = 0.5
DEFAULT_LIMIT = 500

_TRACK_TYPES = ("video", "audio", "subtitle")


def _safe_call(getter, *args):
    try:
        return getter(*args) if callable(getter) else None
    except Exception:
        return None


def parse_duration_seconds(value: Optional[str], fps: float, *, flag: str) -> Optional[float]:
    if value is None or str(value).strip() == "":
        return None
    try:
        seconds = float(parse_time_input(str(value), fps))
    except Exception as exc:
        raise ValidationError(
            f"Invalid {flag} value. Use seconds ('4' / '4s'), frames ('96f'), or timecode ('00:00:04:00').",
            details={"flag": flag, "value": value},
        ) from exc
    if seconds < 0:
        raise ValidationError(f"{flag} must not be negative.", details={"flag": flag, "value": value})
    return seconds


def _timeline_start_frame(conn) -> int:
    start = getattr(conn, "start_frame", None)
    if start is None:
        start = _safe_call(getattr(conn.timeline, "GetStartFrame", None))
    try:
        return int(start or 0)
    except Exception:
        return 0


def _item_metadata(item, track_type: str, track_index: int, fps: float, timeline_start: int) -> Dict[str, Any]:
    name = str(_safe_call(getattr(item, "GetName", None)) or "")
    start = _safe_call(getattr(item, "GetStart", None))
    end = _safe_call(getattr(item, "GetEnd", None))
    start_frame = int(start) if start is not None else None
    end_frame = int(end) if end is not None else None
    duration_frames = end_frame - start_frame if start_frame is not None and end_frame is not None else None
    duration_seconds = frames_to_seconds(duration_frames, fps) if duration_frames is not None else None
    return {
        "name": name,
        "track_type": track_type,
        "track_index": track_index,
        "track": f"{'V' if track_type == 'video' else 'A' if track_type == 'audio' else 'ST'}{track_index}",
        "start_frame": start_frame,
        "end_frame": end_frame,
        "start_timecode": seconds_to_timecode(frames_to_seconds(start_frame, fps), fps) if start_frame is not None else None,
        "end_timecode": seconds_to_timecode(frames_to_seconds(end_frame, fps), fps) if end_frame is not None else None,
        "duration_seconds": round(duration_seconds, 3) if duration_seconds is not None else None,
        "timeline_item_id": str(_safe_call(getattr(item, "GetUniqueId", None)) or "") or None,
        "clip_color": str(_safe_call(getattr(item, "GetClipColor", None)) or "") or None,
        "enabled": _safe_call(getattr(item, "GetClipEnabled", None)),
        "_timeline_start": timeline_start,
    }


def normalize_selector_filters(
    conn,
    *,
    track_type: str = "video",
    track_index: Optional[int] = None,
    name: Optional[str] = None,
    name_starts_with: Optional[str] = None,
    name_contains: Optional[str] = None,
    name_regex: Optional[str] = None,
    duration: Optional[str] = None,
    min_duration: Optional[str] = None,
    max_duration: Optional[str] = None,
    start_ref: Optional[str] = None,
    end_ref: Optional[str] = None,
    clip_color: Optional[str] = None,
    enabled: Optional[bool] = None,
    limit: int = DEFAULT_LIMIT,
) -> Dict[str, Any]:
    normalized_type = str(track_type or "video").strip().lower()
    if normalized_type not in {*_TRACK_TYPES, "all"}:
        raise ValidationError(
            "Track type must be one of: video, audio, subtitle, all.",
            details={"track_type": track_type},
        )
    if track_index is not None and track_index < 1:
        raise ValidationError("--track must be a positive track index.", details={"track": track_index})
    if limit < 1:
        raise ValidationError("--limit must be at least 1.", details={"limit": limit})

    compiled_regex = None
    if name_regex:
        try:
            compiled_regex = re.compile(name_regex)
        except re.error as exc:
            raise ValidationError(
                "Invalid --name-regex pattern.",
                details={"pattern": name_regex, "error": str(exc)},
            ) from exc

    fps = float(getattr(conn, "fps", 24.0) or 24.0)
    range_start = parse_duration_seconds(start_ref, fps, flag="--from") if start_ref else None
    range_end = parse_duration_seconds(end_ref, fps, flag="--to") if end_ref else None
    if range_start is not None and range_end is not None and range_end <= range_start:
        raise ValidationError(
            "--to must be greater than --from.",
            details={"from": start_ref, "to": end_ref},
        )

    return {
        "track_type": normalized_type,
        "track_index": track_index,
        "name": name.strip() if isinstance(name, str) and name.strip() else None,
        "name_starts_with": name_starts_with if name_starts_with else None,
        "name_contains": name_contains if name_contains else None,
        "name_regex": compiled_regex,
        "name_regex_source": name_regex if name_regex else None,
        "duration_seconds": parse_duration_seconds(duration, fps, flag="--duration"),
        "min_duration_seconds": parse_duration_seconds(min_duration, fps, flag="--min-duration"),
        "max_duration_seconds": parse_duration_seconds(max_duration, fps, flag="--max-duration"),
        "range_start_seconds": range_start,
        "range_end_seconds": range_end,
        "clip_color": clip_color.strip() if isinstance(clip_color, str) and clip_color.strip() else None,
        "enabled": enabled,
        "limit": int(limit),
        "fps": fps,
    }


def describe_selector(filters: Dict[str, Any]) -> Dict[str, Any]:
    """JSON-safe echo of the active filters for readbacks and dry runs."""
    described = {}
    for key, value in filters.items():
        if key in {"name_regex", "fps"} or value is None:
            continue
        described[key.replace("_regex_source", "_regex")] = value
    return described


def _matches(meta: Dict[str, Any], filters: Dict[str, Any]) -> bool:
    name = meta["name"]
    if filters["name"] is not None and name != filters["name"]:
        return False
    if filters["name_starts_with"] is not None and not name.startswith(filters["name_starts_with"]):
        return False
    if filters["name_contains"] is not None and filters["name_contains"].lower() not in name.lower():
        return False
    if filters["name_regex"] is not None and not filters["name_regex"].search(name):
        return False

    fps = filters["fps"]
    duration = meta["duration_seconds"]
    epsilon = _DURATION_EPSILON_FRAMES / fps
    if filters["duration_seconds"] is not None:
        if duration is None or abs(duration - filters["duration_seconds"]) > epsilon:
            return False
    if filters["min_duration_seconds"] is not None and (duration is None or duration < filters["min_duration_seconds"] - epsilon):
        return False
    if filters["max_duration_seconds"] is not None and (duration is None or duration > filters["max_duration_seconds"] + epsilon):
        return False

    if filters["range_start_seconds"] is not None or filters["range_end_seconds"] is not None:
        start_frame = meta["start_frame"]
        end_frame = meta["end_frame"]
        if start_frame is None or end_frame is None:
            return False
        timeline_start = meta["_timeline_start"]
        item_start = frames_to_seconds(start_frame - timeline_start, fps)
        item_end = frames_to_seconds(end_frame - timeline_start, fps)
        if filters["range_end_seconds"] is not None and item_start >= filters["range_end_seconds"]:
            return False
        if filters["range_start_seconds"] is not None and item_end <= filters["range_start_seconds"]:
            return False

    if filters["clip_color"] is not None:
        if str(meta["clip_color"] or "").lower() != filters["clip_color"].lower():
            return False
    if filters["enabled"] is not None and bool(meta["enabled"]) is not bool(filters["enabled"]):
        return False
    return True


def select_timeline_items(conn, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return matches as {"item": handle, "meta": metadata} in timeline order."""
    types_to_search = _TRACK_TYPES if filters["track_type"] == "all" else (filters["track_type"],)
    fps = filters["fps"]
    timeline_start = _timeline_start_frame(conn)
    matches: List[Dict[str, Any]] = []
    truncated = False
    for current_type in types_to_search:
        track_count = int(_safe_call(getattr(conn.timeline, "GetTrackCount", None), current_type) or 0)
        wanted_index = filters["track_index"]
        if wanted_index is not None and wanted_index > track_count:
            if filters["track_type"] == "all":
                continue
            raise ValidationError(
                "Track index not found.",
                details={"track_type": current_type, "track": wanted_index, "track_count": track_count},
            )
        indexes = [wanted_index] if wanted_index is not None else range(1, track_count + 1)
        for index in indexes:
            items = _safe_call(getattr(conn.timeline, "GetItemListInTrack", None), current_type, index) or []
            for item in items:
                if item is None:
                    continue
                meta = _item_metadata(item, current_type, index, fps, timeline_start)
                if not _matches(meta, filters):
                    continue
                if len(matches) >= filters["limit"]:
                    truncated = True
                    break
                matches.append({"item": item, "meta": meta})
            if truncated:
                break
        if truncated:
            break
    for match in matches:
        match["meta"].pop("_timeline_start", None)
        match["meta"]["truncated_by_limit"] = truncated
    return matches


def apply_to_items(
    conn,
    matches: List[Dict[str, Any]],
    operation: Callable[[Any, Any, Dict[str, Any]], Any],
    *,
    fail_fast: bool = False,
) -> Dict[str, Any]:
    """Apply *operation(conn, item, meta)* to every match in one connection.

    Fails soft by default: one broken clip must not waste the work already
    done on the rest. Every row reports ok/error so the caller can retry
    precisely the failures.
    """
    started = time.monotonic()
    results: List[Dict[str, Any]] = []
    applied = 0
    failed = 0
    for match in matches:
        meta = {key: value for key, value in match["meta"].items() if key != "truncated_by_limit"}
        row = {
            "name": meta["name"],
            "track": meta["track"],
            "start_timecode": meta["start_timecode"],
            "end_timecode": meta["end_timecode"],
            "timeline_item_id": meta["timeline_item_id"],
        }
        try:
            detail = operation(conn, match["item"], meta)
            row["ok"] = True
            if isinstance(detail, dict) and detail:
                row["detail"] = detail
            applied += 1
        except Exception as exc:
            row["ok"] = False
            row["error"] = str(exc) or exc.__class__.__name__
            failed += 1
            if fail_fast:
                results.append(row)
                break
        results.append(row)
    return {
        "matched": len(matches),
        "applied": applied,
        "failed": failed,
        "duration_ms": int((time.monotonic() - started) * 1000),
        "results": results,
    }
