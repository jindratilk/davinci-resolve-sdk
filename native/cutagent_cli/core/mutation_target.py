"""Exact, revalidated timeline-item targets for consequential mutations."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..errors import (
    AmbiguousTimelineItem,
    ClipNotFound,
    StaleTimelineItem,
    ValidationError,
)
from ..utils.time_ref import parse_record_frame
from .sdk_live_inspection import documented_unique_id


def _optional_call(obj: Any, name: str, *args: Any) -> Any:
    method = getattr(obj, name, None)
    if not callable(method):
        return None
    try:
        return method(*args)
    except Exception:
        return None


def _item_names(item: Any) -> set[str]:
    values: set[str] = set()

    def add(value: Any) -> None:
        if value in (None, ""):
            return
        text = str(value).strip()
        if not text:
            return
        values.add(text.casefold())
        values.add(Path(text).name.casefold())

    add(_optional_call(item, "GetName"))
    properties = _optional_call(item, "GetProperty")
    if not isinstance(properties, dict):
        properties = {}
    for key in ("Clip Name", "File Name", "File Path", "Source File", "SourcePath"):
        add(properties.get(key))
        add(_optional_call(item, "GetProperty", key))
    media_item = _optional_call(item, "GetMediaPoolItem")
    if media_item is not None:
        add(_optional_call(media_item, "GetName"))
        media_properties = _optional_call(media_item, "GetClipProperty")
        if isinstance(media_properties, dict):
            for key in ("Clip Name", "File Name", "File Path", "Source File", "SourcePath"):
                add(media_properties.get(key))
    return values


def _int_call(item: Any, name: str) -> int | None:
    value = _optional_call(item, name)
    try:
        return None if value is None else int(value)
    except (TypeError, ValueError):
        return None


def _timeline_items(conn: Any, *, track_type: str = "video") -> list[tuple[int, Any]]:
    timeline = getattr(conn, "timeline", None)
    if timeline is None:
        return []
    try:
        count = int(timeline.GetTrackCount(track_type) or 0)
    except Exception:
        count = 0
    rows: list[tuple[int, Any]] = []
    for track_index in range(1, count + 1):
        try:
            items = timeline.GetItemListInTrack(track_type, track_index) or []
        except Exception:
            items = []
        rows.extend((track_index, item) for item in items)
    return rows


def _record_frame_candidates(conn: Any, record_frame: int) -> set[int]:
    candidates = {int(record_frame)}
    for value in (
        getattr(conn, "start_frame", 0),
        _optional_call(getattr(conn, "timeline", None), "GetStartFrame"),
    ):
        try:
            offset = int(value or 0)
        except (TypeError, ValueError):
            offset = 0
        if offset:
            candidates.add(int(record_frame) - offset)
    return candidates


@dataclass(frozen=True)
class TimelineItemTarget:
    item: Any
    timeline: Any
    timeline_id: str | None
    track_type: str
    track_index: int
    name: str | None
    start: int | None
    end: int | None
    item_id: str | None
    selector: dict[str, Any]

    def public(self) -> dict[str, Any]:
        return {
            "timeline_id": self.timeline_id,
            "timeline_item_id": self.item_id,
            "identity_scope": "native" if self.item_id else "process_snapshot",
            "track_type": self.track_type,
            "track_index": self.track_index,
            "name": self.name,
            "start": self.start,
            "end": self.end,
            "selector": dict(self.selector),
        }


def _target(conn: Any, track_index: int, item: Any, selector: dict[str, Any]) -> TimelineItemTarget:
    name = _optional_call(item, "GetName")
    return TimelineItemTarget(
        item=item,
        timeline=conn.timeline,
        timeline_id=documented_unique_id(conn.timeline),
        track_type="video",
        track_index=int(track_index),
        name=str(name) if name not in (None, "") else None,
        start=_int_call(item, "GetStart"),
        end=_int_call(item, "GetEnd"),
        item_id=documented_unique_id(item),
        selector=selector,
    )


def validate_timeline_item_selector(
    name: str | None = None,
    *,
    item_id: str | None = None,
    track: int | None = None,
    record_frame: str | int | None = None,
) -> tuple[str | None, str | None]:
    """Validate selector shape without reading or mutating DaVinci Resolve state."""

    normalized_name = str(name).strip() if name is not None else None
    normalized_item_id = str(item_id).strip() if item_id is not None else None
    if normalized_name == "":
        raise ValidationError("Clip name must not be empty.", recoverability="not_applicable")
    if normalized_item_id == "":
        raise ValidationError("Timeline item ID must not be empty.", recoverability="not_applicable")
    if (track is None) != (record_frame is None):
        raise ValidationError(
            "Use --track and --record-frame together.",
            details={"track": track, "record_frame": record_frame},
            recoverability="not_applicable",
        )
    if normalized_item_id and track is not None:
        raise ValidationError(
            "Use either --item-id or --track with --record-frame, not both.",
            recoverability="not_applicable",
        )
    if normalized_name and (normalized_item_id or track is not None):
        raise ValidationError(
            "Use a clip name, --item-id, or --track with --record-frame as one exclusive selector.",
            recoverability="not_applicable",
        )
    return normalized_name, normalized_item_id


def resolve_timeline_item_target(
    conn: Any,
    name: str | None = None,
    *,
    item_id: str | None = None,
    track: int | None = None,
    record_frame: str | int | None = None,
) -> TimelineItemTarget:
    """Resolve exactly one video item; names never silently choose the first duplicate."""

    normalized_name, normalized_item_id = validate_timeline_item_selector(
        name,
        item_id=item_id,
        track=track,
        record_frame=record_frame,
    )

    rows = _timeline_items(conn)
    selector: dict[str, Any]
    matches: list[tuple[int, Any]]
    if normalized_item_id:
        selector = {"kind": "timeline_item_id", "timeline_item_id": normalized_item_id}
        matches = [(idx, item) for idx, item in rows if documented_unique_id(item) == normalized_item_id]
    elif track is not None and record_frame is not None:
        try:
            track_index = int(track)
        except (TypeError, ValueError) as exc:
            raise ValidationError("Track index must be an integer.", details={"track": track}) from exc
        if track_index < 1:
            raise ValidationError("Track index must be at least 1.", details={"track": track_index})
        parsed = parse_record_frame(str(record_frame), getattr(conn, "fps", 24.0), getattr(conn, "start_frame", 0))
        candidates = _record_frame_candidates(conn, parsed)
        selector = {
            "kind": "track_record_frame",
            "track": track_index,
            "record_frame": int(parsed),
        }
        matches = []
        for idx, item in rows:
            start = _int_call(item, "GetStart")
            end = _int_call(item, "GetEnd")
            if idx == track_index and start is not None and end is not None and any(start <= frame < end for frame in candidates):
                matches.append((idx, item))
    elif normalized_name:
        selector = {"kind": "exact_name", "name": normalized_name}
        query = normalized_name.casefold()
        basename = Path(normalized_name).name.casefold()
        matches = [
            (idx, item)
            for idx, item in rows
            if query in _item_names(item) or basename in _item_names(item)
        ]
    else:
        current = _optional_call(conn.timeline, "GetCurrentVideoItem")
        if current is None:
            raise ClipNotFound("No current video item is selected.")
        current_id = documented_unique_id(current)
        matches = [
            (idx, item)
            for idx, item in rows
            if item is current or (current_id is not None and documented_unique_id(item) == current_id)
        ]
        selector = {"kind": "current_video_item"}

    if normalized_name and matches:
        query = normalized_name.casefold()
        basename = Path(normalized_name).name.casefold()
        matches = [
            (idx, item)
            for idx, item in matches
            if query in _item_names(item) or basename in _item_names(item)
        ]

    if not matches:
        error = StaleTimelineItem if normalized_item_id else ClipNotFound
        raise error(
            "No current timeline item matched the exact mutation target.",
            details={"selector": selector, "name_precondition": normalized_name},
        )
    if len(matches) != 1:
        raise AmbiguousTimelineItem(
            "Timeline item selector matched multiple video items; use --item-id or --track with --record-frame.",
            details={
                "selector": selector,
                "name_precondition": normalized_name,
                "match_count": len(matches),
                "matches": [
                    {
                        "track": idx,
                        "name": _optional_call(item, "GetName"),
                        "start": _int_call(item, "GetStart"),
                        "end": _int_call(item, "GetEnd"),
                        "timeline_item_id": documented_unique_id(item),
                    }
                    for idx, item in matches
                ],
            },
        )
    return _target(conn, matches[0][0], matches[0][1], selector)


def revalidate_timeline_item_target(conn: Any, target: TimelineItemTarget) -> TimelineItemTarget:
    """Fail if the active timeline or exact item changed after preflight."""

    if conn.timeline is not target.timeline:
        current_timeline_id = documented_unique_id(conn.timeline)
        if not target.timeline_id or current_timeline_id != target.timeline_id:
            raise StaleTimelineItem(
                "The active timeline changed before mutation.",
                details={"expected_timeline_id": target.timeline_id, "actual_timeline_id": current_timeline_id},
            )
    rows = _timeline_items(conn, track_type=target.track_type)
    if target.item_id:
        matches = [(idx, item) for idx, item in rows if documented_unique_id(item) == target.item_id]
    else:
        matches = [(idx, item) for idx, item in rows if item is target.item]
    if len(matches) != 1:
        raise StaleTimelineItem(
            "The exact timeline item is stale or ambiguous before mutation.",
            details={"target": target.public(), "match_count": len(matches)},
        )
    current = _target(conn, matches[0][0], matches[0][1], target.selector)
    expected_structure = (target.track_index, target.name, target.start, target.end)
    actual_structure = (current.track_index, current.name, current.start, current.end)
    if actual_structure != expected_structure:
        raise StaleTimelineItem(
            "Timeline item structure changed after preflight.",
            details={"expected": target.public(), "actual": current.public()},
        )
    return current
