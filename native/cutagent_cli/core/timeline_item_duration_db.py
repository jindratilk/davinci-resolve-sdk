"""Disk-DB backed timeline item duration/end mutation."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import re
import sqlite3
from typing import Any

from ..errors import APICallFailed, ClipNotFound, ValidationError
from ..utils.frame_math import parse_frame_quantity
from . import clip_ops, db_session, db_timeline_rows, retime_db, timeline_item_mutation, timeline_ops


@dataclass(frozen=True)
class TimelineItemDurationTarget:
    item_id: str | None
    track_type: str
    track_index: int
    name: str
    start: int
    duration: int
    end: int
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class FairlightEditTimelineIdentity:
    name: str
    unique_id: str


_TRACK_DB_TYPES = {
    "video": 0,
    "audio": 1,
    "subtitle": 2,
}

_TRACK_RELATION_NAMES = {
    "video": "VideoTrackVec",
    "audio": "AudioTrackVec",
    "subtitle": "SubtitleTrackVec",
}


_FAIRLIGHT_EDIT_TRANSITION_NATIVE_PROBE_CONTEXT = {
    "runtime": "DaVinci Resolve 20.3.2.9 Free",
    "transport": "direct_utility_lua_script",
    "probe_project": "CUTAGENT_FAIRLIGHT_PARITY_20260605_175239",
    "probe_timeline": "FL_PARITY_24FPS",
    "baseline_verified_methods": [
        "Project.GetName()",
        "Timeline.GetName()",
        "Timeline.GetTrackCount('audio')",
        "Timeline.GetItemListInTrack('audio', 1)",
    ],
}


_FAIRLIGHT_TRANSITION_ADJACENT_EDIT_NATIVE_PROBE_EVIDENCE = {
    **_FAIRLIGHT_EDIT_TRANSITION_NATIVE_PROBE_CONTEXT,
    "candidate_methods_not_available": [
        "Timeline.GetTransitions()",
        "Timeline.GetTransitionList()",
        "Timeline.GetTransitionItems()",
        "Timeline.GetTransitionItemsInTrack('audio', 1)",
        "Timeline.GetAudioTransitions()",
        "Timeline.GetAudioTransitionList()",
        "TimelineItem.GetTransitions()",
        "TimelineItem.GetLeftTransition()",
        "TimelineItem.GetRightTransition()",
        "TimelineItem.GetTransitionProperties()",
        "Timeline.GetSelectedItems()",
        "Timeline.GetSelectedTimelineItems()",
        "Timeline.GetSelectedClips()",
        "Timeline.GetSelection()",
        "Timeline.GetRangeSelection()",
        "Timeline.GetInOutRange()",
        "Timeline.GetClipLayers('audio', 1)",
        "Timeline.GetTrackLayers('audio', 1)",
        "TimelineItem.GetLayer()",
        "TimelineItem.GetClipLayer()",
        "TimelineItem.GetTrackLayer()",
        "Timeline.GetThroughEdits('audio', 1)",
        "Timeline.GetSmoothCutCandidates('audio', 1)",
        "TimelineItem.GetThroughEditState()",
        "TimelineItem.GetEditPointState()",
    ],
    "available_but_insufficient_methods": [
        "TimelineItem.GetLinkedItems()",
    ],
    "mutating_candidates_not_called": [
        "Timeline.AddTransition(...)",
        "Timeline.AddAudioTransition(...)",
        "Timeline.ApplyTransition(...)",
        "Timeline.SetTransitionProperty(...)",
        "Timeline.SetSelectedItems(...)",
        "Timeline.SetRangeSelection(...)",
        "Timeline.SlideClip(...)",
        "TimelineItem.Slide(...)",
        "TimelineItem.SetLayer(...)",
        "Timeline.HealEdit(...)",
        "Timeline.SmoothCut(...)",
    ],
    "probe_result": "transition, selection/range, slide/layer, and heal/smooth-cut getters returned method_not_available; TimelineItem.GetLinkedItems exists but does not expose transition reflow or layer/slide semantics",
    "transition_native_readback_supported": False,
    "selection_native_readback_supported": False,
    "slide_layer_native_readback_supported": False,
    "heal_edit_native_supported": False,
    "transition_adjacent_native_mutation_supported": False,
}


def fairlight_transition_adjacent_edit_blocker_evidence(
    *,
    available_db_route: str,
    supported_columns: list[str],
    unsupported_operation: str,
) -> dict[str, Any]:
    return {
        "available_db_route": available_db_route,
        "transition_model_evidence": {
            "conflict_detector": "overlapping Project.db Sm2TiItem rows where DbType='Sm2TiTransition'",
            "transition_table": "Sm2TiItem",
            "transition_db_type": "Sm2TiTransition",
            "simple_item_write_supported": True,
            "supported_simple_item_columns": list(supported_columns),
            "transition_reflow_supported": False,
            "unsupported_operation": unsupported_operation,
            "unverified_transition_semantics": [
                "reposition adjacent Fairlight transition rows",
                "preserve transition alignment after source or record-range edits",
                "rebind transition rows across track moves",
                "verify transition continuity through the DaVinci Resolve timeline item API",
            ],
        },
        "native_probe_evidence": _FAIRLIGHT_TRANSITION_ADJACENT_EDIT_NATIVE_PROBE_EVIDENCE,
        "db_blocker_note": (
            "The simple audio-item DB route is verified for clips without overlapping Sm2TiTransition rows. "
            "Transition-adjacent Fairlight edits remain blocked until transition row reflow, binding, and live "
            "readback semantics are mapped."
        ),
    }


def _timeline_start_frame(conn: Any) -> int:
    try:
        value = int(getattr(conn, "start_frame", 0) or 0)
    except Exception:
        value = 0
    if value == 0 and getattr(conn, "timeline", None) is not None and hasattr(conn.timeline, "GetStartFrame"):
        try:
            value = int(conn.timeline.GetStartFrame())
        except Exception:
            value = 0
    return value


def _timeline_name(conn: Any) -> str | None:
    try:
        return conn.timeline.GetName()
    except Exception:
        return None


def _frame_candidates(conn: Any, raw: str | None) -> set[int]:
    if raw is None:
        return set()
    timeline_start = _timeline_start_frame(conn)
    relative = parse_frame_quantity(
        str(raw),
        conn.fps,
        field="record_frame",
        allow_signed=False,
        bare_integers_are_frames=True,
    )
    parsed = int(relative) + int(timeline_start)
    candidates = {int(parsed)}
    if timeline_start:
        candidates.add(int(parsed) - int(timeline_start))
    return candidates


def _target_record_frame(conn: Any, raw: str) -> int:
    """Parse a target record-frame ref without double-offsetting absolute frame literals."""
    timeline_start = _timeline_start_frame(conn)
    value = str(raw or "").strip()
    relative = parse_frame_quantity(
        value,
        conn.fps,
        field="target_record_frame",
        allow_signed=False,
        bare_integers_are_frames=True,
    )
    parsed = int(relative) + int(timeline_start)
    frame_literal = value[:-1].strip() if value.endswith("f") else value
    if timeline_start and frame_literal.isdigit():
        literal = int(frame_literal)
        if literal >= int(timeline_start):
            return literal
    return int(parsed)


def _duration_frames(raw: str, fps: float) -> int:
    frames = parse_frame_quantity(raw, fps, field="duration", allow_signed=False)
    if frames <= 0:
        raise ValidationError("Duration must be greater than 0.", details={"duration": raw})
    return int(frames)


def _signed_duration_frames(raw: str, fps: float, *, field: str) -> int:
    frames = parse_frame_quantity(raw, fps, field=field, allow_signed=True)
    if frames == 0:
        raise ValidationError("Signed duration magnitude must be greater than 0.", details={field: raw})
    return frames


def _item_name_candidates(item: Any) -> tuple[str, ...]:
    try:
        values = clip_ops._item_name_candidates(item)
    except Exception:
        values = set()
    try:
        name = str(item.GetName() or "").strip()
    except Exception:
        name = ""
    if name:
        values.add(name)
    return tuple(sorted(str(value) for value in values if str(value or "").strip()))


def _matches_name(target: TimelineItemDurationTarget, name: str | None) -> bool:
    query = str(name or "").strip()
    if not query:
        return True
    query_lower = query.lower()
    return query_lower in {value.lower() for value in (target.name, *target.aliases)}


def _live_item_right_offset(item: Any) -> int | None:
    getter = getattr(item, "GetRightOffset", None)
    if not callable(getter):
        return None
    try:
        return int(getter())
    except Exception:
        return None


def media_pool_item_type(item: Any) -> str | None:
    getter = getattr(item, "GetMediaPoolItem", None)
    if not callable(getter):
        return None
    try:
        media_item = getter()
    except Exception:
        return None
    if media_item is None:
        return None

    property_getter = getattr(media_item, "GetClipProperty", None)
    if not callable(property_getter):
        return None
    for args in (("Type",), ()):
        try:
            value = property_getter(*args)
        except TypeError:
            continue
        except Exception:
            continue
        if isinstance(value, dict):
            for key in ("Type", "Clip Type", "File Type"):
                type_value = value.get(key)
                if str(type_value or "").strip():
                    return str(type_value).strip()
        elif str(value or "").strip():
            return str(value).strip()
    return None


def _uses_finite_source_bounds(item: Any) -> tuple[bool, str | None]:
    media_type = media_pool_item_type(item)
    normalized = str(media_type or "").strip().lower()
    if not normalized:
        return False, media_type
    if "still" in normalized or "image" in normalized:
        return False, media_type
    return ("video" in normalized or "audio" in normalized), media_type


def _live_source_bounds(item: Any) -> dict[str, Any] | None:
    right_offset = _live_item_right_offset(item)
    finite_source_bounds, media_type = _uses_finite_source_bounds(item)
    if finite_source_bounds and right_offset is not None:
        return {"right_offset": right_offset, "media_type": media_type}
    return None


def _item_id_live_source_bounds_for_duration(
    conn: Any,
    *,
    target: TimelineItemDurationTarget,
) -> tuple[dict[str, Any] | None, Exception | None]:
    try:
        _bounds_target, live_item = _select_live_item(
            conn,
            track_type=target.track_type,
            track_index=target.track_index,
            start_ref=f"{target.start}f",
            current_end_ref=f"{target.end}f",
            name=target.name or None,
        )
        return _live_source_bounds(live_item), None
    except Exception as exc:
        return None, exc


def _validate_duration_source_bounds(
    *,
    name: str,
    start: int,
    current_duration: int,
    requested_duration: int,
    live_source_bounds: dict[str, Any] | None,
    live_lookup_error: Exception | None,
    item_id: str | None = None,
    batch_index: int | None = None,
) -> None:
    if live_source_bounds is not None:
        right_offset = live_source_bounds.get("right_offset")
        media_type = live_source_bounds.get("media_type")
        if right_offset is not None and requested_duration > current_duration + int(right_offset):
            details: dict[str, Any] = {
                "name": name,
                "media_type": media_type,
                "start": start,
                "current_duration": current_duration,
                "requested_duration": requested_duration,
                "right_offset": int(right_offset),
            }
            if item_id is not None:
                details["item_id"] = item_id
            if batch_index is not None:
                details["index"] = batch_index
            raise ValidationError(
                "Requested duration exceeds the selected item's available right trim/source extent.",
                details=details,
            )
        return

    if live_lookup_error is not None and requested_duration > current_duration:
        details = {
            "name": name,
            "start": start,
            "current_duration": current_duration,
            "requested_duration": requested_duration,
            "live_lookup_error": str(live_lookup_error),
        }
        if item_id is not None:
            details["item_id"] = item_id
        if batch_index is not None:
            details["index"] = batch_index
        raise ValidationError(
            "Cannot verify the selected item_id duration against live source bounds.",
            details=details,
        )


def _target_from_live_item(item: Any, *, track_type: str, track_index: int, item_id: str | None = None) -> TimelineItemDurationTarget:
    start = timeline_item_mutation.timeline_item_start(item)
    end = timeline_item_mutation.timeline_item_end(item)
    if start is None or end is None:
        raise ValidationError("Timeline item did not expose a readable start/end range.")
    name = str(item.GetName() or "")
    return TimelineItemDurationTarget(
        item_id=item_id,
        track_type=track_type,
        track_index=int(track_index),
        name=name,
        start=int(start),
        duration=max(0, int(end) - int(start)),
        end=int(end),
        aliases=_item_name_candidates(item),
    )


def _select_live_item(
    conn: Any,
    *,
    track_type: str,
    track_index: int,
    start_ref: str | None,
    current_end_ref: str | None,
    name: str | None,
    expected_item_id: str | None = None,
) -> tuple[TimelineItemDurationTarget, Any]:
    normalized_track_type = timeline_ops.normalize_timeline_track_type(track_type)
    normalized_track_index = timeline_ops.validate_timeline_track_index(track_index)
    if start_ref is None and not name:
        raise ValidationError(
            "Timeline item selection requires --start-frame or --name when --item-id is not provided.",
            details={"track_type": normalized_track_type, "track_index": normalized_track_index},
        )

    start_candidates = _frame_candidates(conn, start_ref)
    end_candidates = _frame_candidates(conn, current_end_ref)
    matches: list[tuple[TimelineItemDurationTarget, Any]] = []
    items = conn.timeline.GetItemListInTrack(normalized_track_type, normalized_track_index) or []
    for item in items:
        try:
            live_item_id = None
            if expected_item_id is not None:
                unique_id_getter = getattr(item, "GetUniqueId", None)
                live_item_id = str(unique_id_getter() or "") if callable(unique_id_getter) else ""
                if live_item_id != expected_item_id:
                    continue
            target = _target_from_live_item(
                item,
                track_type=normalized_track_type,
                track_index=normalized_track_index,
                item_id=live_item_id,
            )
        except Exception:
            continue
        if start_candidates and target.start not in start_candidates:
            continue
        if end_candidates and target.end not in end_candidates:
            continue
        if not _matches_name(target, name):
            continue
        matches.append((target, item))

    details = {
        "track_type": normalized_track_type,
        "track_index": normalized_track_index,
        "start_frame": start_ref,
        "current_end_frame": current_end_ref,
        "name": name,
        "stable_identity_required": expected_item_id is not None,
        "matches": [
            {key: value for key, value in asdict(target).items() if key != "item_id"}
            for target, _item in matches
        ],
    }
    if not matches:
        raise ClipNotFound("No timeline item matched the duration selector.", details=details)
    if len(matches) > 1:
        raise ValidationError("Timeline item duration selector is ambiguous.", details=details)
    return matches[0]


def _resolve_new_duration(
    conn: Any,
    *,
    item_start: int,
    duration: str | None,
    target_end_frame: str | None,
) -> tuple[int, int, dict[str, Any]]:
    if bool(duration) == bool(target_end_frame):
        raise ValidationError(
            "Provide exactly one of --duration or --end-frame/--target-end-frame.",
            details={"duration": duration, "target_end_frame": target_end_frame},
        )
    if duration:
        frames = _duration_frames(duration, conn.fps)
        return frames, int(item_start) + frames, {"mode": "duration", "duration": duration}

    candidates = sorted(frame for frame in _frame_candidates(conn, target_end_frame) if frame > int(item_start))
    if not candidates:
        raise ValidationError(
            "Target end frame must be after the item start frame.",
            details={"target_end_frame": target_end_frame, "item_start": item_start},
        )
    end_frame = candidates[0]
    return end_frame - int(item_start), end_frame, {"mode": "target_end_frame", "target_end_frame": target_end_frame}


def _resolve_head_trim_start(
    conn: Any,
    *,
    current_start: int,
    current_end: int,
    target_start_frame: str | None,
    head_delta: str | None,
) -> tuple[int, dict[str, Any]]:
    if bool(target_start_frame) == bool(head_delta):
        raise ValidationError(
            "Provide exactly one of --target-start-frame/--new-start-frame or --head-delta.",
            details={"target_start_frame": target_start_frame, "head_delta": head_delta},
        )
    timeline_start = _timeline_start_frame(conn)
    if target_start_frame:
        parsed = _target_record_frame(conn, str(target_start_frame))
        if timeline_start and int(current_start) < timeline_start <= int(parsed):
            parsed = int(parsed) - int(timeline_start)
        new_start = int(parsed)
        requested = {"mode": "target_start_frame", "target_start_frame": target_start_frame}
    else:
        delta_frames = _signed_duration_frames(str(head_delta), conn.fps, field="head_delta")
        new_start = int(current_start) + int(delta_frames)
        requested = {"mode": "head_delta", "head_delta": head_delta, "head_delta_frames": int(delta_frames)}

    if new_start < 0:
        raise ValidationError("Head trim would place the item before frame 0.", details={"new_start": new_start})
    if timeline_start and int(current_start) >= timeline_start and new_start < timeline_start:
        raise ValidationError(
            "Head trim would place the item before the timeline start frame.",
            details={"new_start": new_start, "timeline_start_frame": timeline_start},
        )
    if new_start >= int(current_end):
        raise ValidationError(
            "Head trim must keep the item start before its current end.",
            details={"new_start": new_start, "current_end": int(current_end)},
        )
    return new_start, requested


def _source_position_frames(raw: str, fps: float, *, field: str) -> int:
    frames = parse_frame_quantity(
        raw,
        fps,
        field=field,
        allow_signed=False,
        bare_integers_are_frames=True,
    )
    if frames < 0:
        raise ValidationError("Source frame must be zero or greater.", details={field: raw, "frames": frames})
    return int(frames)


def _readback_range_candidates(expected_start: int, expected_end: int, timeline_start: int) -> set[tuple[int, int]]:
    ranges = {(int(expected_start), int(expected_end))}
    if timeline_start:
        offset = int(timeline_start)
        ranges.add((int(expected_start) + offset, int(expected_end) + offset))
        ranges.add((int(expected_start) - offset, int(expected_end) - offset))
    return ranges


def _resolve_source_slip_in(
    conn: Any,
    *,
    current_in: int,
    source_start_frame: str | None,
    delta: str | None,
) -> tuple[int, dict[str, Any]]:
    if bool(source_start_frame) == bool(delta):
        raise ValidationError(
            "Provide exactly one of --source-start-frame/--source-in-frame or --delta/--slip.",
            details={"source_start_frame": source_start_frame, "delta": delta},
        )
    if source_start_frame is not None:
        new_in = _source_position_frames(str(source_start_frame), conn.fps, field="source_start_frame")
        requested = {"mode": "source_start_frame", "source_start_frame": source_start_frame}
    else:
        delta_frames = _signed_duration_frames(str(delta), conn.fps, field="delta")
        new_in = int(current_in) + int(delta_frames)
        requested = {"mode": "delta", "delta": delta, "delta_frames": int(delta_frames)}

    if new_in < 0:
        raise ValidationError(
            "Slip would require source audio before frame 0.",
            details={"old_in": int(current_in), "new_in": int(new_in), "delta": delta},
        )
    return int(new_in), requested


def _validate_source_slip_bounds(
    *,
    current_in: int,
    new_in: int,
    right_offset: int | None,
    item_duration: int,
    media_type: str | None,
    name: str,
) -> None:
    if right_offset is None:
        return
    try:
        available_right_offset = int(right_offset)
    except Exception:
        return
    if available_right_offset < 0:
        return
    max_source_in = int(current_in) + available_right_offset
    if int(new_in) <= max_source_in:
        return
    raise ValidationError(
        "Requested slip exceeds the selected item's available right source extent.",
        details={
            "name": name,
            "media_type": media_type,
            "current_in": int(current_in),
            "requested_in": int(new_in),
            "duration": int(item_duration),
            "right_offset": available_right_offset,
            "max_source_in": max_source_in,
        },
    )


def _normalize_selector_track_type(track_type: str | None) -> str:
    normalized = timeline_ops.normalize_timeline_track_type(track_type or "video")
    if normalized not in _TRACK_DB_TYPES:
        raise ValidationError(
            "Timeline item duration supports video, audio, or subtitle tracks.",
            details={"track_type": track_type, "allowed_track_types": sorted(_TRACK_DB_TYPES)},
        )
    return normalized


def _int_cell(value: Any, *, field: str) -> int:
    raw_value = value
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    if isinstance(value, str) and "|" in value:
        value = value.split("|", 1)[0]
    if isinstance(value, str):
        value = value.strip()
        if re.fullmatch(r"[+-]?\d+\.0+", value):
            value = value.split(".", 1)[0]
    try:
        return int(value)
    except Exception as exc:
        raise ValidationError("Project.db row contains an invalid integer field.", details={"field": field, "value": raw_value}) from exc


def _row_to_dict(cursor: sqlite3.Cursor, row: sqlite3.Row | tuple[Any, ...]) -> dict[str, Any]:
    if isinstance(row, sqlite3.Row):
        return {key: row[key] for key in row.keys()}
    return {cursor.description[index][0]: value for index, value in enumerate(row)}


def _timeline_track_ids(
    cursor: sqlite3.Cursor,
    *,
    timeline_name: str,
    track_type: str,
    track_index: int | None = None,
) -> list[dict[str, Any]]:
    relation_name = _TRACK_RELATION_NAMES[track_type]
    params: list[Any] = [relation_name]
    index_clause = ""
    if track_index is not None:
        index_clause = "AND rel.DbIndex = ?"
        params.append(int(track_index) - 1)
    params.append(timeline_name)
    rows = cursor.execute(
        f"""
        SELECT
            track.Sm2TiTrack_id AS track_id,
            rel.DbIndex AS db_track_index,
            track.Type AS track_db_type
        FROM Sm2Timeline timeline
        JOIN Sm2SequenceContainer container ON container.Sm2Sequence_id = timeline.Sequence
        JOIN Sm2SequenceContainer_Sm2TiTrack rel
          ON rel.DbOwner = container.Sm2SequenceContainer_id
         AND rel.DbPropertyName = ?
         {index_clause}
        JOIN Sm2TiTrack track ON track.Sm2TiTrack_id = rel.DbAssociate
        WHERE timeline.Name = ?
        ORDER BY rel.DbIndex
        """,
        tuple(params),
    ).fetchall()
    return [_row_to_dict(cursor, row) for row in rows]


def _fetch_item_rows_for_track_ids(cursor: sqlite3.Cursor, *, track_ids: list[str]) -> list[dict[str, Any]]:
    if not track_ids:
        return []
    placeholders = ", ".join("?" for _ in track_ids)
    rows = cursor.execute(
        f"""
        SELECT
            item.*,
            rel.DbIndex AS item_db_index,
            rel.DbOwner AS relation_track_id
        FROM Sm2TiItem item
        LEFT JOIN Sm2TiItem_Sm2TiTrack rel
          ON rel.DbAssociate = item.Sm2TiItem_id
         AND rel.DbPropertyName = 'Items'
        WHERE COALESCE(rel.DbOwner, item.Sm2TiTrack_id) IN ({placeholders})
        """,
        tuple(track_ids),
    ).fetchall()
    return [_row_to_dict(cursor, row) for row in rows]


def _fetch_db_row_by_item_id(
    cursor: sqlite3.Cursor,
    *,
    item_id: str,
    timeline_name: str | None,
    track_type: str | None,
    track_index: int | None,
) -> dict[str, Any]:
    rows = cursor.execute(
        """
        SELECT
            item.*,
            rel.DbOwner AS relation_track_id,
            rel.DbIndex AS item_db_index
        FROM Sm2TiItem item
        LEFT JOIN Sm2TiItem_Sm2TiTrack rel
          ON rel.DbAssociate = item.Sm2TiItem_id
         AND rel.DbPropertyName = 'Items'
        WHERE item.Sm2TiItem_id = ?
        """,
        (item_id,),
    ).fetchall()
    if not rows:
        raise ClipNotFound("No Project.db timeline item row matched --item-id.", details={"item_id": item_id})
    if len(rows) > 1:
        raise ValidationError("Project.db item_id matched multiple timeline relations.", details={"item_id": item_id, "match_count": len(rows)})
    row = _row_to_dict(cursor, rows[0])
    if timeline_name and track_type:
        track_rows = _timeline_track_ids(cursor, timeline_name=timeline_name, track_type=track_type, track_index=track_index)
        track_ids = {str(track["track_id"]) for track in track_rows}
        row_track_id = str(row.get("relation_track_id") or row.get("Sm2TiTrack_id") or "")
        if row_track_id and row_track_id not in track_ids:
            raise ClipNotFound(
                "The requested item_id does not belong to the selected timeline track.",
                details={"item_id": item_id, "timeline": timeline_name, "track_type": track_type, "track_index": track_index},
            )
    return row


def _fetch_db_row_for_live_target(
    cursor: sqlite3.Cursor,
    *,
    target: TimelineItemDurationTarget,
    timeline_name: str,
) -> dict[str, Any]:
    track_rows = _timeline_track_ids(
        cursor,
        timeline_name=timeline_name,
        track_type=target.track_type,
        track_index=target.track_index,
    )
    track_ids = [str(row["track_id"]) for row in track_rows]
    rows = []
    target_names = {value.lower() for value in (target.name, *target.aliases) if str(value or "").strip()}
    for row in _fetch_item_rows_for_track_ids(cursor, track_ids=track_ids):
        try:
            row_start = _int_cell(row.get("Start") or 0, field="Start")
            row_duration = _int_cell(row.get("Duration") or 0, field="Duration")
        except Exception:
            continue
        if row_start != int(target.start) or row_duration != int(target.duration):
            continue
        db_name = str(row.get("Name") or "")
        row["_name_matches_live_target"] = bool(db_name and db_name.lower() in target_names)
        rows.append(row)
    if not rows:
        raise ClipNotFound(
            "No Project.db row matched the selected live timeline item.",
            details={"timeline": timeline_name, "target": asdict(target), "track_ids": track_ids},
        )
    name_matches = [row for row in rows if row.get("_name_matches_live_target")]
    if len(name_matches) == 1:
        return name_matches[0]
    if len(name_matches) > 1:
        raise ValidationError(
            "Selected live timeline item matched multiple Project.db rows by name.",
            details={"timeline": timeline_name, "target": asdict(target), "match_count": len(name_matches)},
        )
    if len(rows) > 1:
        raise ValidationError(
            "Selected live timeline item matched multiple Project.db rows.",
            details={"timeline": timeline_name, "target": asdict(target), "match_count": len(rows)},
        )
    return rows[0]


def _live_item_unique_id(item: Any) -> str | None:
    getter = getattr(item, "GetUniqueId", None)
    if not callable(getter):
        return None
    try:
        value = str(getter() or "").strip()
    except Exception:
        return None
    return value or None


def _assert_exact_live_item_id(live_item: Any, *, expected_item_id: str, role: str) -> None:
    actual_item_id = _live_item_unique_id(live_item)
    if actual_item_id != expected_item_id:
        raise ValidationError(
            "Selected live timeline item does not match the exact Project.db item ID.",
            details={
                "reason": "fairlight_live_db_item_id_mismatch",
                "role": role,
                "expected_item_id": expected_item_id,
                "actual_native_item_id": actual_item_id,
                "possible_mutation": False,
            },
        )


def _fetch_db_row_for_exact_live_item(
    cursor: sqlite3.Cursor,
    *,
    live_item: Any,
    target: TimelineItemDurationTarget,
    timeline_name: str,
) -> dict[str, Any]:
    """Map one live item to Project.db without using names or coincident geometry."""

    if not timeline_name:
        raise ValidationError(
            "Exact Fairlight item identity requires a named timeline.",
            details={
                "reason": "fairlight_exact_timeline_identity_unavailable",
                "possible_mutation": False,
            },
        )
    native_id = _live_item_unique_id(live_item)
    if not native_id:
        raise ValidationError(
            "Timeline item does not expose a native unique ID for exact Project.db mapping.",
            details={
                "reason": "fairlight_native_item_id_unavailable",
                "track_type": target.track_type,
                "track_index": target.track_index,
                "possible_mutation": False,
            },
        )
    try:
        native_row = _fetch_db_row_by_item_id(
            cursor,
            item_id=native_id,
            timeline_name=timeline_name,
            track_type=target.track_type,
            track_index=target.track_index,
        )
    except ClipNotFound as exc:
        raise ValidationError(
            "Native timeline-item ID did not map to an exact Project.db row on the selected track.",
            details={
                "reason": "fairlight_native_item_id_not_mapped",
                "track_type": target.track_type,
                "track_index": target.track_index,
                "native_item_id": native_id,
                "possible_mutation": False,
            },
        ) from exc
    if (
        _int_cell(native_row.get("Start") or 0, field="Start") != int(target.start)
        or _int_cell(native_row.get("Duration") or 0, field="Duration") != int(target.duration)
    ):
        raise ValidationError(
            "Native timeline-item identity disagreed with Project.db geometry.",
            details={
                "reason": "fairlight_native_item_id_geometry_mismatch",
                "native_item_id": native_id,
                "target": asdict(target),
                "possible_mutation": False,
            },
        )
    return native_row


def _is_simple_timemap(value: Any) -> bool:
    if value in (None, b"", ""):
        return True
    blob = bytes(value)
    return len(blob) == 9 and blob[:1] == b"\x02"


def _updates_for_duration(
    row: dict[str, Any],
    *,
    new_duration: int,
    fps: float,
    preserve_source_timemap: bool = False,
) -> dict[str, Any]:
    updates: dict[str, Any] = {"Duration": str(int(new_duration))}
    if not preserve_source_timemap and "MediaTimemapBA" in row and _is_simple_timemap(row.get("MediaTimemapBA")):
        updates["MediaTimemapBA"] = retime_db.default_timemap(int(new_duration), fps)
    return updates


def _next_item_on_track(cursor: sqlite3.Cursor, *, target_row: dict[str, Any]) -> dict[str, Any] | None:
    track_id = str(target_row.get("relation_track_id") or target_row.get("Sm2TiTrack_id") or "")
    if not track_id:
        return None
    current_id = str(target_row.get("Sm2TiItem_id") or "")
    current_start = _int_cell(target_row.get("Start"), field="Start")
    rows = _fetch_item_rows_for_track_ids(cursor, track_ids=[track_id])
    later = []
    for row in rows:
        if str(row.get("Sm2TiItem_id") or "") == current_id:
            continue
        try:
            row_start = _int_cell(row.get("Start") or 0, field="Start")
        except Exception:
            continue
        if row_start >= current_start:
            later.append(row)
    if not later:
        return None
    return sorted(later, key=lambda row: (_int_cell(row.get("Start") or 0, field="Start"), str(row.get("Sm2TiItem_id") or "")))[0]


def _track_type_from_db_row(row: dict[str, Any], fallback: str | None) -> str:
    if fallback:
        return fallback
    db_type = str(row.get("DbType") or "")
    if "Audio" in db_type:
        return "audio"
    if "Subtitle" in db_type:
        return "subtitle"
    return "video"


def _track_id_from_row(row: dict[str, Any]) -> str:
    return str(row.get("relation_track_id") or row.get("Sm2TiTrack_id") or "")


def _item_duration_frames(value: Any) -> int | None:
    try:
        text = str(value or "").strip()
    except Exception:
        return None
    if not text:
        return None
    prefix = text.split("|", 1)[0].strip()
    try:
        return int(prefix)
    except Exception:
        return None


def _linked_video_companions(
    cursor: sqlite3.Cursor,
    *,
    target_row: dict[str, Any],
    timeline_name: str | None,
    item_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    if str(target_row.get("DbType") or "") != "Sm2TiAudioClip":
        return []
    if item_ids is not None:
        companions: list[dict[str, Any]] = []
        for item_id in item_ids:
            row = _fetch_db_row_by_item_id(
                cursor,
                item_id=str(item_id),
                timeline_name=timeline_name,
                track_type="video",
                track_index=None,
            )
            start = _int_cell(row.get("Start"), field="Start")
            duration = _int_cell(row.get("Duration"), field="Duration")
            companions.append(
                {
                    "item_id": str(row.get("Sm2TiItem_id") or ""),
                    "name": str(row.get("Name") or ""),
                    "start": start,
                    "duration": duration,
                    "end": start + duration,
                    "track_id": _track_id_from_row(row),
                    "item_db_index": row.get("item_db_index"),
                }
            )
        return companions

    name = str(target_row.get("Name") or "").strip()
    if not name:
        return []
    try:
        start = _int_cell(target_row.get("Start"), field="Start")
    except Exception:
        return []
    duration = _item_duration_frames(target_row.get("Duration"))
    if duration is None:
        return []
    try:
        rows = cursor.execute(
            """
            SELECT
                item.Sm2TiItem_id,
                item.Name,
                item.Start,
                item.Duration,
                item.Sm2TiTrack_id,
                rel.DbOwner AS relation_track_id,
                rel.DbIndex AS item_db_index
            FROM Sm2TiItem item
            LEFT JOIN Sm2TiItem_Sm2TiTrack rel
              ON rel.DbAssociate = item.Sm2TiItem_id
             AND rel.DbPropertyName = 'Items'
            WHERE item.DbType = 'Sm2TiVideoClip'
              AND item.Name = ?
              AND item.Start = ?
            """,
            (name, str(start)),
        ).fetchall()
    except sqlite3.OperationalError:
        return []

    allowed_track_ids: set[str] | None = None
    if timeline_name:
        try:
            track_rows = _timeline_track_ids(cursor, timeline_name=timeline_name, track_type="video", track_index=None)
        except Exception:
            track_rows = []
        allowed_track_ids = {str(row.get("track_id") or row.get("Sm2TiTrack_id") or row) for row in track_rows} or None

    companions: list[dict[str, Any]] = []
    for raw in rows:
        row = db_timeline_rows._row_to_dict(cursor, raw)
        row_duration = _item_duration_frames(row.get("Duration"))
        if row_duration is None or abs(row_duration - duration) > 1:
            continue
        track_id = _track_id_from_row(row)
        if allowed_track_ids is not None and track_id not in allowed_track_ids:
            continue
        companions.append(
            {
                "item_id": str(row.get("Sm2TiItem_id") or ""),
                "name": str(row.get("Name") or ""),
                "start": start,
                "duration": row_duration,
                "end": start + row_duration,
                "track_id": track_id,
                "item_db_index": row.get("item_db_index"),
            }
        )
    return companions


def _linked_video_rows(
    cursor: sqlite3.Cursor,
    *,
    companions: list[dict[str, Any]],
    timeline_name: str | None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for companion in companions:
        rows.append(
            _fetch_db_row_by_item_id(
                cursor,
                item_id=str(companion["item_id"]),
                timeline_name=timeline_name,
                track_type="video",
                track_index=None,
            )
        )
    return rows


def capture_timeline_edit_structural_state(
    cursor: sqlite3.Cursor,
    *,
    timeline_name: str | None,
) -> dict[str, Any]:
    """Capture the structural timeline fields protected by clip edits."""

    if not timeline_name:
        raise ValidationError(
            "Verified timeline clip edits require an exact timeline name.",
            details={"reason": "fairlight_clip_edit_timeline_unverified"},
        )
    track_ids: list[str] = []
    for track_type in ("video", "audio", "subtitle"):
        try:
            track_ids.extend(
                str(row["track_id"])
                for row in _timeline_track_ids(
                    cursor,
                    timeline_name=timeline_name,
                    track_type=track_type,
                    track_index=None,
                )
            )
        except (sqlite3.Error, ValidationError):
            if track_type in {"video", "audio"}:
                raise
    unique_track_ids = sorted(set(track_ids))
    if not unique_track_ids:
        raise ValidationError(
            "Verified timeline clip edits could not resolve timeline tracks.",
            details={"reason": "fairlight_clip_edit_tracks_unverified", "timeline_name": timeline_name},
        )

    available_columns = {
        str(row[1])
        for row in cursor.execute("PRAGMA table_info('Sm2TiItem')").fetchall()
    }
    protected_columns = [
        column
        for column in ("DbType", "Name", "Start", "Duration", "In", "Sm2TiTrack_id")
        if column in available_columns
    ]
    placeholders = ",".join("?" for _ in unique_track_ids)
    selected = ", ".join(f'item."{column}"' for column in protected_columns)
    rows = cursor.execute(
        f"""
        SELECT
            item.Sm2TiItem_id,
            {selected},
            rel.DbOwner AS relation_track_id,
            rel.DbIndex AS item_db_index
        FROM Sm2TiItem item
        JOIN Sm2TiItem_Sm2TiTrack rel
          ON rel.DbAssociate = item.Sm2TiItem_id
         AND rel.DbPropertyName = 'Items'
        WHERE rel.DbOwner IN ({placeholders})
        ORDER BY item.Sm2TiItem_id, rel.DbOwner, rel.DbIndex
        """,
        unique_track_ids,
    ).fetchall()
    items: dict[str, list[dict[str, Any]]] = {}
    for raw in rows:
        row = db_timeline_rows._row_to_dict(cursor, raw)
        item_id = str(row.pop("Sm2TiItem_id") or "")
        normalized = {str(key): row[key] for key in sorted(row)}
        items.setdefault(item_id, []).append(normalized)
    return {
        "timeline_name": timeline_name,
        "track_ids": unique_track_ids,
        "columns": protected_columns,
        "items": items,
    }


def verify_protected_timeline_edit_state(
    session: Any,
    mutation_result: dict[str, Any],
) -> dict[str, Any]:
    """Prove that no non-target timeline item structurally changed."""

    before = mutation_result.get("protected_state_before")
    if not isinstance(before, dict):
        return {
            "name": "protected_timeline_items",
            "ok": False,
            "error": "Mutation result did not retain a protected structural pre-state.",
        }
    updated_ids = {
        str(item.get("item_id") or "")
        for item in mutation_result.get("updated_items", [])
        if str(item.get("item_id") or "")
    }
    connection = sqlite3.connect(str(session.project_db_path), timeout=5.0)
    connection.row_factory = sqlite3.Row
    try:
        after = capture_timeline_edit_structural_state(
            connection.cursor(),
            timeline_name=str(before.get("timeline_name") or "") or None,
        )
    finally:
        connection.close()
    before_items = {
        item_id: value
        for item_id, value in dict(before.get("items") or {}).items()
        if item_id not in updated_ids
    }
    after_items = {
        item_id: value
        for item_id, value in dict(after.get("items") or {}).items()
        if item_id not in updated_ids
    }
    changed_ids = sorted(
        item_id
        for item_id in set(before_items) | set(after_items)
        if before_items.get(item_id) != after_items.get(item_id)
    )
    return {
        "name": "protected_timeline_items",
        "ok": not changed_ids,
        "protected_item_count": len(before_items),
        "updated_item_ids": sorted(updated_ids),
        "changed_item_ids": changed_ids,
        "evidence_modality": "project_db_structural_readback",
    }


def _raise_linked_audio_only_blocker(
    *,
    operation: str,
    item_id: str,
    target_row: dict[str, Any],
    old_start: int,
    old_end: int,
    new_start: int,
    new_end: int,
    linked_video_companions: list[dict[str, Any]],
) -> None:
    raise ValidationError(
        f"Fairlight audio-only {operation} would desynchronize a linked audio/video clip.",
        details={
            "item_id": item_id,
            "name": str(target_row.get("Name") or ""),
            "old_start": old_start,
            "old_end": old_end,
            "new_start": int(new_start),
            "new_end": int(new_end),
            "linked_video_companions": linked_video_companions,
            "precondition": f"linked_av_audio_only_{operation}_blocked",
            "available_native_readback": "cutagent fairlight clip linked list CLIP --json uses TimelineItem.GetLinkedItems(), but it does not expose group trim/slip mutation semantics.",
            "override": "--allow-linked-audio-only",
            "live_evidence_artifact": "/tmp/cutagent_linked_clip_move_probe_20260620_065919/08_move_linked_audio_plus12.json",
            "db_blocker_note": (
                "The verified Fairlight edit route writes audio Sm2TiItem rows only. A live DaVinci Resolve 21 linked A/V "
                "probe proved audio-only DB edits can leave the linked video item unchanged, so linked A/V items "
                "are blocked unless the caller explicitly opts into audio-only editing."
            ),
        },
    )


def _track_index_from_db_row(cursor: sqlite3.Cursor, *, row: dict[str, Any], timeline_name: str | None, track_type: str) -> int:
    track_id = str(row.get("relation_track_id") or row.get("Sm2TiTrack_id") or "")
    if timeline_name:
        for track_row in _timeline_track_ids(cursor, timeline_name=timeline_name, track_type=track_type):
            if str(track_row["track_id"]) == track_id:
                return int(track_row["db_track_index"]) + 1
    return 1


def _target_from_db_row(
    cursor: sqlite3.Cursor,
    *,
    row: dict[str, Any],
    item_id: str,
    timeline_name: str | None,
    fallback_track_type: str | None,
) -> TimelineItemDurationTarget:
    row_start = _int_cell(row.get("Start"), field="Start")
    row_duration = _int_cell(row.get("Duration"), field="Duration")
    row_track_type = _track_type_from_db_row(row, fallback_track_type)
    return TimelineItemDurationTarget(
        item_id=str(item_id),
        track_type=row_track_type,
        track_index=_track_index_from_db_row(cursor, row=row, timeline_name=timeline_name, track_type=row_track_type),
        name=str(row.get("Name") or ""),
        start=row_start,
        duration=row_duration,
        end=row_start + row_duration,
    )


def _read_item_id_target_before_db_close(
    conn: Any,
    *,
    item_id: str,
    timeline_name: str | None,
    track_type: str | None,
) -> TimelineItemDurationTarget:
    current_database = db_session.resolve_current_disk_project_db(
        conn,
        allow_project_name_inference=True,
    )
    project_db_path = str(current_database["project_db_path"])
    connection = sqlite3.connect(project_db_path, timeout=5.0)
    connection.row_factory = sqlite3.Row
    try:
        cursor = connection.cursor()
        row = _fetch_db_row_by_item_id(
            cursor,
            item_id=str(item_id),
            timeline_name=timeline_name,
            track_type=track_type,
            track_index=None,
        )
        return _target_from_db_row(
            cursor,
            row=row,
            item_id=str(item_id),
            timeline_name=timeline_name,
            fallback_track_type=track_type,
        )
    finally:
        connection.close()


def _normalized_edit_row_identity(row: dict[str, Any]) -> dict[str, Any]:
    identity: dict[str, Any] = {
        "item_id": str(row.get("Sm2TiItem_id") or ""),
        "db_type": str(row.get("DbType") or ""),
        "name": str(row.get("Name") or ""),
        "track_id": _track_id_from_row(row),
        "item_db_index": row.get("item_db_index"),
    }
    for public_name, column in (("start", "Start"), ("duration", "Duration"), ("source_in", "In")):
        if column in row:
            identity[public_name] = _int_cell(row.get(column) or 0, field=column)
    return identity


def _assert_edit_row_identity(row: dict[str, Any], expected: dict[str, Any], *, role: str) -> None:
    actual = _normalized_edit_row_identity(row)
    if actual != expected:
        raise ValidationError(
            "Fairlight clip edit target changed after preflight.",
            details={
                "reason": "stale_fairlight_clip_edit_target",
                "role": role,
                "expected": expected,
                "actual": actual,
                "possible_mutation": False,
            },
        )


def _live_track_identity(item: Any) -> tuple[str, int]:
    getter = getattr(item, "GetTrackTypeAndIndex", None)
    if not callable(getter):
        raise ValidationError(
            "Linked timeline item does not expose an exact track identity.",
            details={"reason": "fairlight_linked_item_track_identity_unavailable"},
        )
    try:
        result = getter()
        track_type = _normalize_selector_track_type(str(result[0]))
        track_index = timeline_ops.validate_timeline_track_index(result[1])
    except Exception as exc:
        raise ValidationError(
            "Linked timeline item returned an invalid track identity.",
            details={"reason": "fairlight_linked_item_track_identity_invalid", "value": result if "result" in locals() else None},
        ) from exc
    return track_type, track_index


def prepare_fairlight_clip_edit_identity(
    conn: Any,
    *,
    target: TimelineItemDurationTarget,
    live_item: Any,
    timeline_name: str | None,
) -> dict[str, Any]:
    """Bind one live audio item and its native links to exact Project.db ids."""

    if target.track_type != "audio":
        raise ValidationError(
            "Fairlight clip editing requires an audio timeline item.",
            details={"reason": "fairlight_clip_edit_requires_audio", "target": asdict(target)},
        )
    current_database = db_session.resolve_current_disk_project_db(conn, allow_project_name_inference=True)
    project_db_path = str(current_database["project_db_path"])
    database_uri = Path(project_db_path).resolve().as_uri() + "?mode=ro"
    connection = sqlite3.connect(database_uri, uri=True, timeout=5.0)
    connection.row_factory = sqlite3.Row
    try:
        cursor = connection.cursor()
        if target.item_id:
            _assert_exact_live_item_id(
                live_item,
                expected_item_id=str(target.item_id),
                role="audio_target",
            )
            target_row = _fetch_db_row_by_item_id(
                cursor,
                item_id=str(target.item_id),
                timeline_name=timeline_name,
                track_type="audio",
                track_index=None,
            )
        else:
            target_row = _fetch_db_row_for_exact_live_item(
                cursor,
                live_item=live_item,
                target=target,
                timeline_name=timeline_name or "",
            )
        target_identity = _normalized_edit_row_identity(target_row)
        if target_identity["db_type"] != "Sm2TiAudioClip":
            raise ValidationError(
                "Fairlight clip edit target is not an audio clip row.",
                details={"reason": "fairlight_clip_edit_db_type_mismatch", "target": target_identity},
            )

        getter = getattr(live_item, "GetLinkedItems", None)
        if not callable(getter):
            raise ValidationError(
                "Fairlight clip edits require native linked-item readback before mutation.",
                details={"reason": "fairlight_linked_item_readback_unavailable", "target": target_identity},
            )
        try:
            linked_items = list(getter() or [])
        except Exception as exc:
            raise ValidationError(
                "Fairlight clip linked-item readback failed before mutation.",
                details={"reason": "fairlight_linked_item_readback_failed", "target": target_identity, "error": str(exc)},
            ) from exc

        linked_companions = [linked_item for linked_item in linked_items if linked_item is not live_item]
        if len(linked_companions) > 1:
            raise ValidationError(
                "Fairlight clip edit supports only a simple native link group with at most one companion.",
                details={
                    "reason": "fairlight_non_simple_link_group_unsupported",
                    "target": target_identity,
                    "native_link_count": len(linked_items),
                    "linked_companion_count": len(linked_companions),
                    "possible_mutation": False,
                },
            )

        linked_video: list[dict[str, Any]] = []
        unsupported_links: list[dict[str, Any]] = []
        for linked_item in linked_companions:
            linked_track_type, linked_track_index = _live_track_identity(linked_item)
            linked_target = _target_from_live_item(
                linked_item,
                track_type=linked_track_type,
                track_index=linked_track_index,
            )
            summary = {
                "track_type": linked_track_type,
                "track_index": linked_track_index,
                "name": linked_target.name,
                "start": linked_target.start,
                "duration": linked_target.duration,
                "end": linked_target.end,
            }
            if linked_track_type != "video":
                unsupported_links.append(summary)
                continue
            linked_row = _fetch_db_row_for_exact_live_item(
                cursor,
                live_item=linked_item,
                target=linked_target,
                timeline_name=timeline_name or "",
            )
            linked_identity = _normalized_edit_row_identity(linked_row)
            if linked_identity["db_type"] != "Sm2TiVideoClip":
                raise ValidationError(
                    "Native linked video item did not map to a video clip row.",
                    details={"reason": "fairlight_linked_video_db_type_mismatch", "linked_item": summary, "db_identity": linked_identity},
                )
            linked_video.append(
                {
                    **summary,
                    "item_id": linked_identity["item_id"],
                    "db_identity": linked_identity,
                    "source_bounds": _live_source_bounds(linked_item),
                }
            )

        for linked_item, linked in zip(
            [item for item in linked_companions if _live_track_identity(item)[0] == "video"],
            linked_video,
            strict=True,
        ):
            reciprocal_getter = getattr(linked_item, "GetLinkedItems", None)
            if not callable(reciprocal_getter):
                raise ValidationError(
                    "Fairlight linked video reciprocal readback is unavailable before mutation.",
                    details={
                        "reason": "fairlight_link_group_not_reciprocal",
                        "target": target_identity,
                        "linked_video": linked,
                        "possible_mutation": False,
                    },
                )
            try:
                reciprocal_items = list(reciprocal_getter() or [])
                reciprocal_ids: list[str] = []
                for reciprocal_item in reciprocal_items:
                    reciprocal_track_type, reciprocal_track_index = _live_track_identity(reciprocal_item)
                    reciprocal_target = _target_from_live_item(
                        reciprocal_item,
                        track_type=reciprocal_track_type,
                        track_index=reciprocal_track_index,
                    )
                    reciprocal_row = _fetch_db_row_for_exact_live_item(
                        cursor,
                        live_item=reciprocal_item,
                        target=reciprocal_target,
                        timeline_name=timeline_name or "",
                    )
                    reciprocal_id = str(reciprocal_row.get("Sm2TiItem_id") or "")
                    if reciprocal_id and reciprocal_id != str(linked["item_id"]):
                        reciprocal_ids.append(reciprocal_id)
            except Exception as exc:
                raise ValidationError(
                    "Fairlight linked video reciprocal readback failed before mutation.",
                    details={
                        "reason": "fairlight_link_group_not_reciprocal",
                        "target": target_identity,
                        "linked_video": linked,
                        "possible_mutation": False,
                        "error": str(exc),
                    },
                ) from exc
            expected_reciprocal_ids = [str(target_identity["item_id"])]
            if sorted(reciprocal_ids) != expected_reciprocal_ids:
                raise ValidationError(
                    "Fairlight clip edit requires an exact reciprocal closed audio/video link group.",
                    details={
                        "reason": "fairlight_link_group_not_reciprocal",
                        "target": target_identity,
                        "linked_video": linked,
                        "expected_reciprocal_item_ids": expected_reciprocal_ids,
                        "actual_reciprocal_item_ids": sorted(reciprocal_ids),
                        "possible_mutation": False,
                    },
                )

        if unsupported_links:
            raise ValidationError(
                "Fairlight clip edit does not support linked non-video companions.",
                details={
                    "reason": "fairlight_complex_link_group_unsupported",
                    "target": target_identity,
                    "unsupported_linked_items": unsupported_links,
                    "possible_mutation": False,
                },
            )
        return {
            "target_item_id": target_identity["item_id"],
            "target_db_identity": target_identity,
            "linked_video": linked_video,
            "native_link_count": len(linked_items),
            "timeline_name": timeline_name,
            "identity_source": "TimelineItem.GetLinkedItems + exact native unique-id Project.db mapping",
        }
    finally:
        connection.close()


def fairlight_edit_track_lock_targets(
    *,
    target: TimelineItemDurationTarget,
    plan: dict[str, Any],
    destination_audio_track_index: int | None = None,
) -> tuple[tuple[str, int, str], ...]:
    """Resolve the exact affected track set once for both lock checks."""

    tracks: set[tuple[str, int, str]] = {
        ("audio", int(target.track_index), "source"),
    }
    if destination_audio_track_index is not None:
        tracks.add(("audio", int(destination_audio_track_index), "destination"))
    for linked in plan.get("linked_video", []):
        tracks.add(("video", int(linked["track_index"]), "linked"))
    return tuple(sorted(tracks))


def require_fairlight_edit_timeline_identity(
    conn: Any,
    *,
    expected: FairlightEditTimelineIdentity | None = None,
) -> FairlightEditTimelineIdentity:
    """Read or revalidate the exact timeline that owns the planned DB mutation."""

    timeline = getattr(conn, "timeline", None)
    unique_id_getter = getattr(timeline, "GetUniqueId", None)
    name = str(_timeline_name(conn) or "").strip()
    try:
        unique_id = str(unique_id_getter() or "").strip() if callable(unique_id_getter) else ""
    except Exception:
        unique_id = ""

    failure_truth = {
        "possible_mutation": False,
        "revalidation_phase": "locked_pre_close",
        "mutation_started": False,
        "backup_written": False,
        "project_closed": False,
        "sqlite_write_started": False,
    } if expected is not None else {"possible_mutation": False}

    if not name or not unique_id:
        raise ValidationError(
            "Fairlight clip edits require authoritative timeline identity before mutation.",
            details={
                "reason": "fairlight_exact_timeline_identity_unavailable",
                "timeline_name": name or None,
                "timeline_unique_id": unique_id or None,
                **failure_truth,
            },
        )

    actual = FairlightEditTimelineIdentity(name=name, unique_id=unique_id)
    if expected is not None and actual != expected:
        raise ValidationError(
            "The active timeline changed before the Fairlight clip edit mutation boundary.",
            details={
                "reason": "fairlight_active_timeline_changed_before_mutation",
                "expected_timeline_name": expected.name,
                "active_timeline_name": actual.name,
                "expected_timeline_unique_id": expected.unique_id,
                "active_timeline_unique_id": actual.unique_id,
                **failure_truth,
            },
        )
    return actual


def require_fairlight_edit_tracks_unlocked(
    conn: Any,
    *,
    target: TimelineItemDurationTarget,
    plan: dict[str, Any],
    destination_audio_track_index: int | None = None,
    track_targets: tuple[tuple[str, int, str], ...] | None = None,
    phase: str = "initial_preflight",
) -> list[dict[str, Any]]:
    """Fail closed unless every source, destination, and native-linked track is unlocked."""

    def _failure_truth() -> dict[str, Any]:
        if phase != "locked_pre_close":
            return {}
        return {
            "revalidation_phase": phase,
            "mutation_started": False,
            "backup_written": False,
            "project_closed": False,
            "sqlite_write_started": False,
        }

    getter = getattr(getattr(conn, "timeline", None), "GetIsTrackLocked", None)
    if not callable(getter):
        raise ValidationError(
            "Fairlight clip edits require authoritative track-lock readback before mutation.",
            details={
                "reason": "fairlight_track_lock_readback_unavailable",
                "required_method": "Timeline.GetIsTrackLocked",
                "possible_mutation": False,
                **_failure_truth(),
            },
        )

    tracks = track_targets or fairlight_edit_track_lock_targets(
        target=target,
        plan=plan,
        destination_audio_track_index=destination_audio_track_index,
    )
    evidence: list[dict[str, Any]] = []
    for track_type, track_index, role in tracks:
        try:
            locked = getter(track_type, track_index)
        except Exception as exc:
            raise ValidationError(
                "Fairlight clip edit track-lock readback failed before mutation.",
                details={
                    "reason": "fairlight_track_lock_readback_failed",
                    "track_type": track_type,
                    "track_index": track_index,
                    "role": role,
                    "possible_mutation": False,
                    **_failure_truth(),
                },
            ) from exc
        if not isinstance(locked, bool):
            raise ValidationError(
                "Fairlight clip edit track-lock state was not authoritative.",
                details={
                    "reason": "fairlight_track_lock_state_unverified",
                    "track_type": track_type,
                    "track_index": track_index,
                    "role": role,
                    "locked": None,
                    "possible_mutation": False,
                    **_failure_truth(),
                },
            )
        evidence.append(
            {
                "track_type": track_type,
                "track_index": track_index,
                "role": role,
                "locked": locked,
            }
        )
        if locked:
            raise ValidationError(
                "Fairlight clip edit cannot mutate a locked affected track.",
                details={
                    "reason": "fairlight_track_locked",
                    "track_type": track_type,
                    "track_index": track_index,
                    "role": role,
                    "locked": True,
                    "possible_mutation": False,
                    **_failure_truth(),
                },
            )
    return evidence


def fairlight_edit_pre_close_validator(
    *,
    target: TimelineItemDurationTarget,
    plan: dict[str, Any],
    track_targets: tuple[tuple[str, int, str], ...],
    intended_timeline: FairlightEditTimelineIdentity,
):
    """Bind the intended timeline and preflight-resolved tracks to the mutation boundary."""

    expected_timeline_name = intended_timeline.name
    planned_timeline_name = str(plan.get("timeline_name") or "").strip()
    if not expected_timeline_name or planned_timeline_name != expected_timeline_name:
        raise ValidationError(
            "Fairlight clip edit requires one exact intended timeline before mutation.",
            details={
                "reason": "fairlight_exact_timeline_identity_unavailable",
                "expected_timeline_name": expected_timeline_name or None,
                "planned_timeline_name": planned_timeline_name or None,
                "possible_mutation": False,
            },
        )

    def _validate(locked_conn: Any, _session: db_session.DiskDbMutationSession) -> list[dict[str, Any]]:
        require_fairlight_edit_timeline_identity(locked_conn, expected=intended_timeline)
        return require_fairlight_edit_tracks_unlocked(
            locked_conn,
            target=target,
            plan=plan,
            track_targets=track_targets,
            phase="locked_pre_close",
        )

    return _validate


def fairlight_clip_edit_no_change(
    *,
    action: str,
    timeline_name: str | None,
    target: TimelineItemDurationTarget,
    requested: dict[str, Any],
    plan: dict[str, Any],
    reason: str,
) -> dict[str, Any]:
    """Return explicit pre-mutation truth for an absolute Fairlight no-op."""

    return {
        "action": action,
        "timeline_name": timeline_name,
        "requested": requested,
        "outcome": "no_change",
        "changed": False,
        "affected_count": 0,
        "before": asdict(target),
        "after": None,
        "updated_items": [],
        "linked_video_included": False,
        "native_link_identity": plan,
        "verification": {
            "status": "verified",
            "checks": [
                {
                    "name": "absolute_request_matches_current_state",
                    "ok": True,
                    "reason": reason,
                    "evidence_modality": "pre_mutation_live_and_project_db_readback",
                }
            ],
            "audition": {"required": False, "status": "not_run"},
        },
        "recovery": {
            "required": False,
            "manual_recovery_required": False,
            "state": "none",
        },
        "possible_mutation": False,
        "mutation_started": False,
        "db_session_entered": False,
        "backup_written": False,
        "project_closed": False,
        "sqlite_write_started": False,
        "no_change_reason": reason,
    }


def assert_fairlight_clip_edit_identity(
    cursor: sqlite3.Cursor,
    *,
    plan: dict[str, Any],
    timeline_name: str | None,
) -> tuple[dict[str, Any], list[str], dict[str, dict[str, Any] | None]]:
    target_row = _fetch_db_row_by_item_id(
        cursor,
        item_id=str(plan["target_item_id"]),
        timeline_name=timeline_name,
        track_type="audio",
        track_index=None,
    )
    _assert_edit_row_identity(target_row, dict(plan["target_db_identity"]), role="audio_target")
    linked_video_ids: list[str] = []
    source_bounds: dict[str, dict[str, Any] | None] = {}
    for linked in plan.get("linked_video", []):
        linked_id = str(linked["item_id"])
        linked_row = _fetch_db_row_by_item_id(
            cursor,
            item_id=linked_id,
            timeline_name=timeline_name,
            track_type="video",
            track_index=None,
        )
        _assert_edit_row_identity(linked_row, dict(linked["db_identity"]), role="linked_video")
        linked_video_ids.append(linked_id)
        source_bounds[linked_id] = linked.get("source_bounds")
    return target_row, linked_video_ids, source_bounds


def _apply_duration_update(
    cursor: sqlite3.Cursor,
    *,
    target_row: dict[str, Any],
    new_duration: int,
    new_end: int,
    new_start: int | None = None,
    allow_overlap: bool,
    fps: float,
    allow_linked_audio_only: bool = False,
    include_linked_video: bool = False,
    preserve_source_timemap: bool = False,
    timeline_name: str | None = None,
    linked_video_item_ids: list[str] | None = None,
    linked_video_source_bounds: dict[str, dict[str, Any] | None] | None = None,
) -> dict[str, Any]:
    item_id = str(target_row.get("Sm2TiItem_id") or "")
    old_start = _int_cell(target_row.get("Start"), field="Start")
    old_duration = _int_cell(target_row.get("Duration"), field="Duration")
    old_in = _int_cell(target_row.get("In") or 0, field="In") if "In" in target_row else None
    old_end = old_start + old_duration
    resolved_new_start = old_start if new_start is None else int(new_start)
    if new_duration <= 0 or new_end <= resolved_new_start:
        raise ValidationError(
            "Timeline item duration must keep end after start.",
            details={"item_id": item_id, "start": resolved_new_start, "new_duration": new_duration, "new_end": new_end},
        )

    if _track_type_from_db_row(target_row, None) == "audio":
        linked_video_companions = _linked_video_companions(
            cursor,
            target_row=target_row,
            timeline_name=timeline_name,
            item_ids=linked_video_item_ids,
        )
        if linked_video_companions and not allow_linked_audio_only and not include_linked_video:
            _raise_linked_audio_only_blocker(
                operation="trim",
                item_id=item_id,
                target_row=target_row,
                old_start=old_start,
                old_end=old_end,
                new_start=resolved_new_start,
                new_end=int(new_end),
                linked_video_companions=linked_video_companions,
            )
        linked_video_rows = _linked_video_rows(cursor, companions=linked_video_companions, timeline_name=timeline_name) if include_linked_video else []
        transition_conflicts: list[dict[str, Any]] = []
        seen_transition_ids: set[str] = set()
        for start, end in ((old_start, old_end), (old_start, int(new_end))):
            for conflict in _transition_conflicts_for_item_range(cursor, target_row=target_row, start=start, end=end):
                conflict_id = str(conflict.get("item_id") or "")
                if conflict_id and conflict_id in seen_transition_ids:
                    continue
                if conflict_id:
                    seen_transition_ids.add(conflict_id)
                transition_conflicts.append(conflict)
        if transition_conflicts:
            raise ValidationError(
                "Tail trim would leave or collide with Fairlight transition rows.",
                details={
                    "item_id": item_id,
                    "old_start": old_start,
                    "old_end": old_end,
                    "new_start": old_start,
                    "new_end": int(new_end),
                    "transition_conflicts": transition_conflicts,
                    "hint": "Remove or recreate adjacent Fairlight transitions before tail-trimming this audio item.",
                    **fairlight_transition_adjacent_edit_blocker_evidence(
                        available_db_route=(
                            "Simple Fairlight tail trim writes Sm2TiItem.Duration and duration metadata "
                            "while preserving the item start with reopen/readback verification."
                        ),
                        supported_columns=[
                            "Sm2TiItem.Duration",
                            "Sm2TiItem.MediaTimemapBA",
                        ],
                        unsupported_operation="transition-aware Fairlight audio tail trim",
                    ),
                },
            )
    else:
        linked_video_rows = []

    if resolved_new_start != old_start and not allow_overlap:
        range_conflicts = _item_conflicts_for_item_range(cursor, target_row=target_row, start=resolved_new_start, end=int(new_end))
        if range_conflicts:
            raise ValidationError(
                "Timeline item duration/start would overlap another item on the same track.",
                details={
                    "item_id": item_id,
                    "new_start": resolved_new_start,
                    "new_end": int(new_end),
                    "conflicts": range_conflicts,
                    "hint": "Pass --allow-overlap only when overlapping timeline items on this track is intended.",
                },
            )

    next_item = _next_item_on_track(cursor, target_row=target_row)
    if resolved_new_start == old_start and not allow_overlap and next_item is not None:
        next_start = _int_cell(next_item.get("Start"), field="Start")
        if int(new_end) > next_start:
            raise ValidationError(
                "Timeline item duration would overlap the next item on the same track.",
                details={
                    "item_id": item_id,
                    "requested_end": int(new_end),
                    "next_item": {
                        "item_id": str(next_item.get("Sm2TiItem_id") or ""),
                        "name": str(next_item.get("Name") or ""),
                        "start": next_start,
                    },
                    "hint": "Pass --allow-overlap only when overlapping timeline items on this track is intended.",
                },
            )

    linked_video_updates: list[dict[str, Any]] = []
    for linked_row in linked_video_rows:
        linked_old_start = _int_cell(linked_row.get("Start"), field="Start")
        linked_old_duration = _int_cell(linked_row.get("Duration"), field="Duration")
        linked_old_in = _int_cell(linked_row.get("In") or 0, field="In") if "In" in linked_row else None
        duration_delta = int(new_duration) - old_duration
        linked_new_duration = linked_old_duration + duration_delta
        if linked_new_duration <= 0:
            raise ValidationError(
                "Linked video companion tail trim would remove the entire item.",
                details={
                    "item_id": str(linked_row.get("Sm2TiItem_id") or ""),
                    "old_duration": linked_old_duration,
                    "duration_delta_frames": duration_delta,
                    "new_duration": linked_new_duration,
                },
            )
        if duration_delta > 0 and linked_video_source_bounds is not None:
            linked_id = str(linked_row.get("Sm2TiItem_id") or "")
            bounds = linked_video_source_bounds.get(linked_id)
            if bounds is None:
                raise ValidationError(
                    "Cannot verify linked video source bounds for tail-trim expansion.",
                    details={
                        "reason": "fairlight_linked_video_source_bounds_unavailable",
                        "item_id": linked_id,
                        "duration_delta_frames": duration_delta,
                    },
                )
            right_offset = bounds.get("right_offset")
            if right_offset is None or duration_delta > int(right_offset):
                raise ValidationError(
                    "Linked video companion tail trim exceeds available source extent.",
                    details={
                        "item_id": linked_id,
                        "duration_delta_frames": duration_delta,
                        "right_offset": right_offset,
                    },
                )
        linked_new_end = linked_old_start + linked_new_duration
        linked_transition_conflicts = _transition_conflicts_for_item_ranges(
            cursor,
            target_row=linked_row,
            ranges=(
                (linked_old_start, linked_old_start + linked_old_duration),
                (linked_old_start, linked_new_end),
            ),
        )
        if linked_transition_conflicts:
            raise ValidationError(
                "Linked video companion tail trim would leave or collide with transition rows.",
                details={
                    "item_id": str(linked_row.get("Sm2TiItem_id") or ""),
                    "old_start": linked_old_start,
                    "old_end": linked_old_start + linked_old_duration,
                    "new_start": linked_old_start,
                    "new_end": linked_new_end,
                    "transition_conflicts": linked_transition_conflicts,
                    "precondition": "linked_av_video_tail_trim_transition_blocked",
                    "possible_mutation": False,
                    "hint": "Remove or recreate adjacent video transitions before tail-trimming this linked A/V item.",
                },
            )
        linked_next_item = _next_item_on_track(cursor, target_row=linked_row)
        if linked_next_item is not None and not allow_overlap:
            linked_next_start = _int_cell(linked_next_item.get("Start"), field="Start")
            if linked_new_end > linked_next_start:
                raise ValidationError(
                    "Linked video companion tail trim would overlap the next item on the same video track.",
                    details={
                        "item_id": str(linked_row.get("Sm2TiItem_id") or ""),
                        "requested_end": linked_new_end,
                        "next_item": {
                            "item_id": str(linked_next_item.get("Sm2TiItem_id") or ""),
                            "name": str(linked_next_item.get("Name") or ""),
                            "start": linked_next_start,
                        },
                        "precondition": "linked_av_video_tail_trim_overlap_blocked",
                    },
                )
        linked_video_updates.append(
            {
                "row": linked_row,
                "old_start": linked_old_start,
                "old_duration": linked_old_duration,
                "old_end": linked_old_start + linked_old_duration,
                "old_in": linked_old_in,
                "new_start": linked_old_start,
                "new_duration": linked_new_duration,
                "new_end": linked_new_end,
                "new_in": linked_old_in,
                "updates": _updates_for_duration(
                    linked_row,
                    new_duration=linked_new_duration,
                    fps=fps,
                    preserve_source_timemap=preserve_source_timemap,
                ),
            }
        )

    updates = _updates_for_duration(
        target_row,
        new_duration=int(new_duration),
        fps=fps,
        preserve_source_timemap=preserve_source_timemap,
    )
    if resolved_new_start != old_start:
        updates["Start"] = str(int(resolved_new_start))
    db_timeline_rows.update_row(cursor, "Sm2TiItem", "Sm2TiItem_id", item_id, updates)
    for update in linked_video_updates:
        db_timeline_rows.update_row(
            cursor,
            "Sm2TiItem",
            "Sm2TiItem_id",
            str(update["row"].get("Sm2TiItem_id") or ""),
            update["updates"],
        )
    return {
        "item_id": item_id,
        "db_type": str(target_row.get("DbType") or ""),
        "name": str(target_row.get("Name") or ""),
        "track_id": str(target_row.get("relation_track_id") or target_row.get("Sm2TiTrack_id") or ""),
        "old_start": old_start,
        "old_duration": old_duration,
        "old_end": old_end,
        "old_in": old_in,
        "new_start": resolved_new_start,
        "new_duration": int(new_duration),
        "new_end": int(new_end),
        "new_in": old_in,
        "updated_columns": sorted(updates.keys()),
        "linked_video_updates": [
            {
                "item_id": str(update["row"].get("Sm2TiItem_id") or ""),
                "db_type": str(update["row"].get("DbType") or ""),
                "name": str(update["row"].get("Name") or ""),
                "track_id": _track_id_from_row(update["row"]),
                "old_start": int(update["old_start"]),
                "old_duration": int(update["old_duration"]),
                "old_end": int(update["old_end"]),
                "old_in": update["old_in"],
                "new_start": int(update["new_start"]),
                "new_duration": int(update["new_duration"]),
                "new_end": int(update["new_end"]),
                "new_in": update["new_in"],
                "updated_columns": sorted(str(key) for key in update["updates"].keys()),
            }
            for update in linked_video_updates
        ],
    }


def _ranges_overlap(left_start: int, left_end: int, right_start: int, right_end: int) -> bool:
    return int(left_start) < int(right_end) and int(right_start) < int(left_end)


def _source_in_from_row(row: dict[str, Any]) -> int:
    if "In" not in row:
        raise ValidationError(
            "Project.db row does not expose source In offset required for this source-offset edit.",
            details={"item_id": str(row.get("Sm2TiItem_id") or ""), "available_columns": sorted(str(key) for key in row.keys())},
        )
    value = row.get("In")
    if value in (None, ""):
        return 0
    return _int_cell(value, field="In")


def _source_in_cell_with_offset(value: Any, offset_frames: int) -> str:
    """Advance a native source-In cell without discarding its fractional suffix."""
    if value in (None, ""):
        return str(int(offset_frames))
    text = value.decode("utf-8", errors="replace") if isinstance(value, bytes) else str(value)
    match = re.fullmatch(r"\s*([+-]?\d+)(\|[0-9a-fA-F]{16})?\s*", text)
    if match is not None:
        return f"{int(match[1]) + int(offset_frames)}{match[2] or ''}"
    if "|" in text:
        raise ValidationError(
            "Project.db row contains an invalid integer field.",
            details={"field": "In", "value": value},
        )
    return str(_int_cell(value, field="In") + int(offset_frames))


def _transition_conflicts_for_item_range(cursor: sqlite3.Cursor, *, target_row: dict[str, Any], start: int, end: int) -> list[dict[str, Any]]:
    track_id = str(target_row.get("relation_track_id") or target_row.get("Sm2TiTrack_id") or "")
    item_id = str(target_row.get("Sm2TiItem_id") or "")
    conflicts: list[dict[str, Any]] = []
    for row in _fetch_item_rows_for_track_ids(cursor, track_ids=[track_id]):
        row_id = str(row.get("Sm2TiItem_id") or "")
        if row_id == item_id or str(row.get("DbType") or "") != "Sm2TiTransition":
            continue
        try:
            row_start = _int_cell(row.get("Start") or 0, field="Start")
            row_duration = _int_cell(row.get("Duration") or 0, field="Duration")
        except Exception:
            continue
        row_end = row_start + row_duration
        if not _ranges_overlap(row_start, row_end, int(start), int(end)):
            continue
        conflicts.append(
            {
                "item_id": row_id,
                "name": str(row.get("Name") or row.get("PrettyType") or ""),
                "db_type": str(row.get("DbType") or ""),
                "start": row_start,
                "end": row_end,
                "duration": row_duration,
            }
        )
    return conflicts


def _transition_conflicts_for_item_ranges(
    cursor: sqlite3.Cursor,
    *,
    target_row: dict[str, Any],
    ranges: tuple[tuple[int, int], ...],
) -> list[dict[str, Any]]:
    conflicts: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for start, end in ranges:
        for conflict in _transition_conflicts_for_item_range(cursor, target_row=target_row, start=start, end=end):
            conflict_id = str(conflict.get("item_id") or "")
            if conflict_id and conflict_id in seen_ids:
                continue
            if conflict_id:
                seen_ids.add(conflict_id)
            conflicts.append(conflict)
    return conflicts


def _item_conflicts_for_item_range(cursor: sqlite3.Cursor, *, target_row: dict[str, Any], start: int, end: int) -> list[dict[str, Any]]:
    track_id = str(target_row.get("relation_track_id") or target_row.get("Sm2TiTrack_id") or "")
    item_id = str(target_row.get("Sm2TiItem_id") or "")
    conflicts: list[dict[str, Any]] = []
    for row in _fetch_item_rows_for_track_ids(cursor, track_ids=[track_id]):
        row_id = str(row.get("Sm2TiItem_id") or "")
        if row_id == item_id:
            continue
        try:
            row_start = _int_cell(row.get("Start") or 0, field="Start")
            row_duration = _int_cell(row.get("Duration") or 0, field="Duration")
        except Exception:
            continue
        row_end = row_start + row_duration
        if not _ranges_overlap(row_start, row_end, int(start), int(end)):
            continue
        conflicts.append(
            {
                "item_id": row_id,
                "name": str(row.get("Name") or row.get("PrettyType") or ""),
                "db_type": str(row.get("DbType") or ""),
                "start": row_start,
                "end": row_end,
                "duration": row_duration,
            }
        )
    return conflicts


def _apply_source_slip_update(
    cursor: sqlite3.Cursor,
    *,
    target_row: dict[str, Any],
    new_in: int,
    allow_linked_audio_only: bool = False,
    include_linked_video: bool = False,
    timeline_name: str | None = None,
    linked_video_item_ids: list[str] | None = None,
    linked_video_source_bounds: dict[str, dict[str, Any] | None] | None = None,
) -> dict[str, Any]:
    item_id = str(target_row.get("Sm2TiItem_id") or "")
    old_start = _int_cell(target_row.get("Start"), field="Start")
    duration = _int_cell(target_row.get("Duration"), field="Duration")
    old_in = _source_in_from_row(target_row)
    old_end = old_start + duration
    if duration <= 0:
        raise ValidationError("Timeline item slip requires a positive item duration.", details={"item_id": item_id, "duration": duration})
    if int(new_in) < 0:
        raise ValidationError(
            "Slip would require source audio before frame 0.",
            details={"item_id": item_id, "old_in": old_in, "new_in": int(new_in)},
        )

    linked_video_companions = _linked_video_companions(
        cursor,
        target_row=target_row,
        timeline_name=timeline_name,
        item_ids=linked_video_item_ids,
    )
    if linked_video_companions and not allow_linked_audio_only and not include_linked_video:
        _raise_linked_audio_only_blocker(
            operation="slip",
            item_id=item_id,
            target_row=target_row,
            old_start=old_start,
            old_end=old_end,
            new_start=old_start,
            new_end=old_end,
            linked_video_companions=linked_video_companions,
        )
    linked_video_rows = _linked_video_rows(cursor, companions=linked_video_companions, timeline_name=timeline_name) if include_linked_video else []

    transition_conflicts = _transition_conflicts_for_item_range(cursor, target_row=target_row, start=old_start, end=old_end)
    if transition_conflicts:
        raise ValidationError(
            "Slip would edit source audio under Fairlight transition rows.",
            details={
                "item_id": item_id,
                "start": old_start,
                "end": old_end,
                "transition_conflicts": transition_conflicts,
                "hint": "Remove or recreate adjacent Fairlight transitions before slipping this audio item.",
                **fairlight_transition_adjacent_edit_blocker_evidence(
                    available_db_route=(
                        "Simple Fairlight source slip writes Sm2TiItem.In while preserving Sm2TiItem.Start, "
                        "Duration, and End with reopen/readback verification."
                    ),
                    supported_columns=["Sm2TiItem.In"],
                    unsupported_operation="transition-aware Fairlight audio source slip",
                ),
            },
        )

    linked_video_updates: list[dict[str, Any]] = []
    source_delta = int(new_in) - old_in
    for linked_row in linked_video_rows:
        linked_old_start = _int_cell(linked_row.get("Start"), field="Start")
        linked_old_duration = _int_cell(linked_row.get("Duration"), field="Duration")
        linked_transition_conflicts = _transition_conflicts_for_item_range(
            cursor,
            target_row=linked_row,
            start=linked_old_start,
            end=linked_old_start + linked_old_duration,
        )
        if linked_transition_conflicts:
            raise ValidationError(
                "Linked video companion slip would edit source video under transition rows.",
                details={
                    "item_id": str(linked_row.get("Sm2TiItem_id") or ""),
                    "start": linked_old_start,
                    "end": linked_old_start + linked_old_duration,
                    "transition_conflicts": linked_transition_conflicts,
                    "precondition": "linked_av_video_source_slip_transition_blocked",
                    "possible_mutation": False,
                    "hint": "Remove or recreate adjacent video transitions before slipping this linked A/V item.",
                },
            )
        linked_old_in = _source_in_from_row(linked_row)
        linked_new_in = linked_old_in + source_delta
        if linked_new_in < 0:
            raise ValidationError(
                "Linked video companion slip would require source video before frame 0.",
                details={
                    "item_id": str(linked_row.get("Sm2TiItem_id") or ""),
                    "old_in": linked_old_in,
                    "source_delta_frames": source_delta,
                    "new_in": linked_new_in,
                    "precondition": "linked_av_video_source_before_zero_blocked",
                },
            )
        if source_delta > 0 and linked_video_source_bounds is not None:
            linked_id = str(linked_row.get("Sm2TiItem_id") or "")
            bounds = linked_video_source_bounds.get(linked_id)
            if bounds is None:
                raise ValidationError(
                    "Cannot verify linked video source bounds for a positive source slip.",
                    details={
                        "reason": "fairlight_linked_video_source_bounds_unavailable",
                        "item_id": linked_id,
                        "source_delta_frames": source_delta,
                    },
                )
            right_offset = bounds.get("right_offset")
            if right_offset is None or source_delta > int(right_offset):
                raise ValidationError(
                    "Linked video companion source slip exceeds available source extent.",
                    details={
                        "item_id": linked_id,
                        "source_delta_frames": source_delta,
                        "right_offset": right_offset,
                    },
                )
        linked_video_updates.append(
            {
                "row": linked_row,
                "old_start": linked_old_start,
                "old_duration": linked_old_duration,
                "old_in": linked_old_in,
                "new_in": linked_new_in,
            }
        )

    db_timeline_rows.update_row(cursor, "Sm2TiItem", "Sm2TiItem_id", item_id, {"In": str(int(new_in))})
    for update in linked_video_updates:
        db_timeline_rows.update_row(
            cursor,
            "Sm2TiItem",
            "Sm2TiItem_id",
            str(update["row"].get("Sm2TiItem_id") or ""),
            {"In": str(int(update["new_in"]))},
        )
    return {
        "item_id": item_id,
        "db_type": str(target_row.get("DbType") or ""),
        "name": str(target_row.get("Name") or ""),
        "track_id": str(target_row.get("relation_track_id") or target_row.get("Sm2TiTrack_id") or ""),
        "old_start": old_start,
        "old_duration": duration,
        "old_end": old_end,
        "old_in": old_in,
        "new_start": old_start,
        "new_duration": duration,
        "new_end": old_end,
        "new_in": int(new_in),
        "source_delta_frames": int(new_in) - old_in,
        "updated_columns": ["In"],
        "linked_video_updates": [
            {
                "item_id": str(update["row"].get("Sm2TiItem_id") or ""),
                "db_type": str(update["row"].get("DbType") or ""),
                "name": str(update["row"].get("Name") or ""),
                "track_id": _track_id_from_row(update["row"]),
                "old_start": int(update["old_start"]),
                "old_duration": int(update["old_duration"]),
                "old_end": int(update["old_start"]) + int(update["old_duration"]),
                "old_in": int(update["old_in"]),
                "new_start": int(update["old_start"]),
                "new_duration": int(update["old_duration"]),
                "new_end": int(update["old_start"]) + int(update["old_duration"]),
                "new_in": int(update["new_in"]),
                "source_delta_frames": source_delta,
                "updated_columns": ["In"],
            }
            for update in linked_video_updates
        ],
    }


def _apply_head_trim_update(
    cursor: sqlite3.Cursor,
    *,
    target_row: dict[str, Any],
    new_start: int,
    allow_overlap: bool,
    fps: float,
    allow_linked_audio_only: bool = False,
    include_linked_video: bool = False,
    preserve_source_timemap: bool = False,
    timeline_name: str | None = None,
    linked_video_item_ids: list[str] | None = None,
    timeline_start_frame: int = 0,
) -> dict[str, Any]:
    item_id = str(target_row.get("Sm2TiItem_id") or "")
    old_start = _int_cell(target_row.get("Start"), field="Start")
    old_duration = _int_cell(target_row.get("Duration"), field="Duration")
    old_in = _source_in_from_row(target_row)
    old_end = old_start + old_duration
    delta = int(new_start) - old_start
    new_duration = old_duration - delta
    new_in = old_in + delta
    new_end = old_end

    if new_duration <= 0 or int(new_start) >= old_end:
        raise ValidationError(
            "Head trim must keep the item start before its current end.",
            details={"item_id": item_id, "old_start": old_start, "old_end": old_end, "new_start": int(new_start), "new_duration": new_duration},
        )
    if new_in < 0:
        raise ValidationError(
            "Head trim would require source audio before frame 0.",
            details={"item_id": item_id, "old_in": old_in, "delta_frames": delta, "new_in": new_in},
        )

    linked_video_companions = _linked_video_companions(
        cursor,
        target_row=target_row,
        timeline_name=timeline_name,
        item_ids=linked_video_item_ids,
    )
    if linked_video_companions and not allow_linked_audio_only and not include_linked_video:
        _raise_linked_audio_only_blocker(
            operation="trim",
            item_id=item_id,
            target_row=target_row,
            old_start=old_start,
            old_end=old_end,
            new_start=int(new_start),
            new_end=new_end,
            linked_video_companions=linked_video_companions,
        )
    linked_video_rows = _linked_video_rows(cursor, companions=linked_video_companions, timeline_name=timeline_name) if include_linked_video else []

    track_id = str(target_row.get("relation_track_id") or target_row.get("Sm2TiTrack_id") or "")
    clip_conflicts: list[dict[str, Any]] = []
    transition_conflicts: list[dict[str, Any]] = []
    for row in _fetch_item_rows_for_track_ids(cursor, track_ids=[track_id]):
        row_id = str(row.get("Sm2TiItem_id") or "")
        if row_id == item_id:
            continue
        try:
            row_start = _int_cell(row.get("Start") or 0, field="Start")
            row_duration = _int_cell(row.get("Duration") or 0, field="Duration")
        except Exception:
            continue
        row_end = row_start + row_duration
        summary = {
            "item_id": row_id,
            "name": str(row.get("Name") or row.get("PrettyType") or ""),
            "db_type": str(row.get("DbType") or ""),
            "start": row_start,
            "end": row_end,
            "duration": row_duration,
        }
        if str(row.get("DbType") or "") == "Sm2TiTransition":
            if _ranges_overlap(row_start, row_end, old_start, old_end) or _ranges_overlap(row_start, row_end, int(new_start), new_end):
                transition_conflicts.append(summary)
            continue
        if _ranges_overlap(row_start, row_end, int(new_start), new_end):
            clip_conflicts.append(summary)

    if transition_conflicts:
        raise ValidationError(
            "Head trim would leave or collide with Fairlight transition rows.",
            details={
                "item_id": item_id,
                "old_start": old_start,
                "old_end": old_end,
                "new_start": int(new_start),
                "new_end": new_end,
                "transition_conflicts": transition_conflicts,
                "hint": "Remove or recreate adjacent Fairlight transitions before head-trimming this audio item.",
                **fairlight_transition_adjacent_edit_blocker_evidence(
                    available_db_route=(
                        "Simple Fairlight head trim writes Sm2TiItem.Start, Duration, In, and duration metadata "
                        "while preserving the item end with reopen/readback verification."
                    ),
                    supported_columns=[
                        "Sm2TiItem.Start",
                        "Sm2TiItem.Duration",
                        "Sm2TiItem.In",
                        "Sm2TiItem.MediaTimemapBA",
                    ],
                    unsupported_operation="transition-aware Fairlight audio head trim",
                ),
            },
        )
    if clip_conflicts and not allow_overlap:
        raise ValidationError(
            "Head trim would overlap another item on the same track.",
            details={
                "item_id": item_id,
                "new_start": int(new_start),
                "new_end": new_end,
                "conflicts": clip_conflicts,
                "hint": "Pass --allow-overlap only when overlapping items on this track is intended.",
            },
        )

    linked_video_updates: list[dict[str, Any]] = []
    for linked_row in linked_video_rows:
        linked_old_start = _int_cell(linked_row.get("Start"), field="Start")
        linked_old_duration = _int_cell(linked_row.get("Duration"), field="Duration")
        linked_old_in = _source_in_from_row(linked_row)
        linked_delta = int(new_start) - old_start
        linked_new_start = linked_old_start + linked_delta
        linked_new_duration = linked_old_duration - linked_delta
        linked_new_in = linked_old_in + linked_delta
        linked_new_end = linked_old_start + linked_old_duration
        linked_transition_conflicts = _transition_conflicts_for_item_ranges(
            cursor,
            target_row=linked_row,
            ranges=((linked_old_start, linked_new_end), (linked_new_start, linked_new_end)),
        )
        if linked_transition_conflicts:
            raise ValidationError(
                "Linked video companion head trim would leave or collide with transition rows.",
                details={
                    "item_id": str(linked_row.get("Sm2TiItem_id") or ""),
                    "old_start": linked_old_start,
                    "old_end": linked_new_end,
                    "new_start": linked_new_start,
                    "new_end": linked_new_end,
                    "transition_conflicts": linked_transition_conflicts,
                    "precondition": "linked_av_video_head_trim_transition_blocked",
                    "possible_mutation": False,
                    "hint": "Remove or recreate adjacent video transitions before head-trimming this linked A/V item.",
                },
            )
        if linked_new_start < 0:
            raise ValidationError(
                "Linked video companion head trim would place the item before frame 0.",
                details={
                    "item_id": str(linked_row.get("Sm2TiItem_id") or ""),
                    "old_start": linked_old_start,
                    "head_delta_frames": linked_delta,
                    "new_start": linked_new_start,
                    "precondition": "linked_av_video_record_before_zero_blocked",
                },
            )
        if timeline_start_frame and linked_old_start >= timeline_start_frame and linked_new_start < timeline_start_frame:
            raise ValidationError(
                "Linked video companion head trim would place the item before the timeline start frame.",
                details={
                    "item_id": str(linked_row.get("Sm2TiItem_id") or ""),
                    "old_start": linked_old_start,
                    "head_delta_frames": linked_delta,
                    "new_start": linked_new_start,
                    "timeline_start_frame": timeline_start_frame,
                    "precondition": "linked_av_video_record_before_timeline_start_blocked",
                },
            )
        if linked_new_duration <= 0 or linked_new_start >= linked_new_end:
            raise ValidationError(
                "Linked video companion head trim must keep the item start before its current end.",
                details={
                    "item_id": str(linked_row.get("Sm2TiItem_id") or ""),
                    "old_start": linked_old_start,
                    "old_end": linked_new_end,
                    "new_start": linked_new_start,
                    "new_duration": linked_new_duration,
                    "precondition": "linked_av_video_head_trim_duration_blocked",
                },
            )
        if linked_new_in < 0:
            raise ValidationError(
                "Linked video companion head trim would require source video before frame 0.",
                details={
                    "item_id": str(linked_row.get("Sm2TiItem_id") or ""),
                    "old_in": linked_old_in,
                    "delta_frames": linked_delta,
                    "new_in": linked_new_in,
                    "precondition": "linked_av_video_head_trim_source_before_zero_blocked",
                },
            )
        linked_track_id = _track_id_from_row(linked_row)
        linked_clip_conflicts: list[dict[str, Any]] = []
        for row in _fetch_item_rows_for_track_ids(cursor, track_ids=[linked_track_id]):
            row_id = str(row.get("Sm2TiItem_id") or "")
            if row_id == str(linked_row.get("Sm2TiItem_id") or ""):
                continue
            try:
                row_start = _int_cell(row.get("Start") or 0, field="Start")
                row_duration = _int_cell(row.get("Duration") or 0, field="Duration")
            except Exception:
                continue
            row_end = row_start + row_duration
            if _ranges_overlap(row_start, row_end, linked_new_start, linked_new_end):
                linked_clip_conflicts.append(
                    {
                        "item_id": row_id,
                        "name": str(row.get("Name") or row.get("PrettyType") or ""),
                        "db_type": str(row.get("DbType") or ""),
                        "start": row_start,
                        "end": row_end,
                        "duration": row_duration,
                    }
                )
        if linked_clip_conflicts and not allow_overlap:
            raise ValidationError(
                "Linked video companion head trim would overlap another item on the same video track.",
                details={
                    "item_id": str(linked_row.get("Sm2TiItem_id") or ""),
                    "new_start": linked_new_start,
                    "new_end": linked_new_end,
                    "conflicts": linked_clip_conflicts,
                    "precondition": "linked_av_video_head_trim_overlap_blocked",
                },
            )
        linked_updates = _updates_for_duration(
            linked_row,
            new_duration=int(linked_new_duration),
            fps=fps,
            preserve_source_timemap=preserve_source_timemap,
        )
        linked_updates.update(
            {
                "Start": str(int(linked_new_start)),
                "In": _source_in_cell_with_offset(linked_row.get("In"), linked_delta),
            }
        )
        linked_video_updates.append(
            {
                "row": linked_row,
                "old_start": linked_old_start,
                "old_duration": linked_old_duration,
                "old_end": linked_new_end,
                "old_in": linked_old_in,
                "new_start": linked_new_start,
                "new_duration": linked_new_duration,
                "new_end": linked_new_end,
                "new_in": linked_new_in,
                "updates": linked_updates,
            }
        )

    updates = _updates_for_duration(
        target_row,
        new_duration=int(new_duration),
        fps=fps,
        preserve_source_timemap=preserve_source_timemap,
    )
    updates.update(
        {
            "Start": str(int(new_start)),
            "In": _source_in_cell_with_offset(target_row.get("In"), delta),
        }
    )
    db_timeline_rows.update_row(cursor, "Sm2TiItem", "Sm2TiItem_id", item_id, updates)
    for update in linked_video_updates:
        db_timeline_rows.update_row(
            cursor,
            "Sm2TiItem",
            "Sm2TiItem_id",
            str(update["row"].get("Sm2TiItem_id") or ""),
            update["updates"],
        )
    return {
        "item_id": item_id,
        "db_type": str(target_row.get("DbType") or ""),
        "name": str(target_row.get("Name") or ""),
        "track_id": track_id,
        "old_start": old_start,
        "old_duration": old_duration,
        "old_end": old_end,
        "old_in": old_in,
        "new_start": int(new_start),
        "new_duration": int(new_duration),
        "new_end": new_end,
        "new_in": int(new_in),
        "head_delta_frames": delta,
        "updated_columns": sorted(updates.keys()),
        "linked_video_updates": [
            {
                "item_id": str(update["row"].get("Sm2TiItem_id") or ""),
                "db_type": str(update["row"].get("DbType") or ""),
                "name": str(update["row"].get("Name") or ""),
                "track_id": _track_id_from_row(update["row"]),
                "old_start": int(update["old_start"]),
                "old_duration": int(update["old_duration"]),
                "old_end": int(update["old_end"]),
                "old_in": int(update["old_in"]),
                "new_start": int(update["new_start"]),
                "new_duration": int(update["new_duration"]),
                "new_end": int(update["new_end"]),
                "new_in": int(update["new_in"]),
                "head_delta_frames": delta,
                "updated_columns": sorted(str(key) for key in update["updates"].keys()),
            }
            for update in linked_video_updates
        ],
    }


def verify_native_fairlight_link_state(
    fresh_conn: Any,
    mutation_result: dict[str, Any],
    session: Any | None = None,
) -> dict[str, Any]:
    """Verify native linked-item membership after a Fairlight clip edit."""

    plan = mutation_result.get("native_link_identity")
    if not isinstance(plan, dict):
        return {"name": "native_link_membership", "ok": False, "error": "Native link preflight evidence is missing."}
    audio_items = [item for item in mutation_result.get("updated_items", []) if item.get("track_type") == "audio"]
    if len(audio_items) != 1:
        return {"name": "native_link_membership", "ok": False, "error": "Expected exactly one edited audio item."}
    audio = audio_items[0]
    expected_start = int(audio.get("new_start") or 0)
    expected_end = int(audio.get("new_end") or 0)
    expected_names = {
        str(value)
        for value in audio.get("readback_name_candidates", [])
        if str(value or "").strip()
    }
    candidates = _readback_range_candidates(expected_start, expected_end, _timeline_start_frame(fresh_conn))
    live_matches: list[Any] = []
    for live_item in fresh_conn.timeline.GetItemListInTrack("audio", int(audio.get("track_index") or 1)) or []:
        try:
            live_name = str(live_item.GetName() or "")
            live_start = timeline_item_mutation.timeline_item_start(live_item)
            live_end = timeline_item_mutation.timeline_item_end(live_item)
        except Exception:
            continue
        if (live_start, live_end) not in candidates:
            continue
        if expected_names and live_name not in expected_names:
            continue
        live_matches.append(live_item)
    if len(live_matches) != 1:
        return {
            "name": "native_link_membership",
            "ok": False,
            "error": "Edited audio item could not be identified uniquely after reopen.",
            "match_count": len(live_matches),
        }

    project_db_path = getattr(session, "project_db_path", None)
    if not project_db_path:
        return {
            "name": "native_link_membership",
            "ok": False,
            "error": "Exact Project.db identity readback is unavailable after reopen.",
        }
    timeline_name = str(plan.get("timeline_name") or mutation_result.get("timeline_name") or "")
    identity_connection = sqlite3.connect(str(project_db_path), timeout=5.0)
    identity_connection.row_factory = sqlite3.Row
    identity_cursor = identity_connection.cursor()
    try:
        audio_target = _target_from_live_item(
            live_matches[0],
            track_type="audio",
            track_index=int(audio.get("track_index") or 1),
        )
        audio_row = _fetch_db_row_for_exact_live_item(
            identity_cursor,
            live_item=live_matches[0],
            target=audio_target,
            timeline_name=timeline_name,
        )
        actual_audio_item_id = str(audio_row.get("Sm2TiItem_id") or "")
    except Exception as exc:
        identity_connection.close()
        return {
            "name": "native_link_membership",
            "ok": False,
            "error": f"Edited audio item exact identity could not be proved after reopen: {exc}",
        }
    expected_audio_item_id = str(plan.get("target_item_id") or audio.get("item_id") or "")
    if not expected_audio_item_id or actual_audio_item_id != expected_audio_item_id:
        identity_connection.close()
        return {
            "name": "native_link_membership",
            "ok": False,
            "error": "Edited audio item identity changed after reopen.",
            "expected_audio_item_id": expected_audio_item_id,
            "actual_audio_item_id": actual_audio_item_id,
        }

    getter = getattr(live_matches[0], "GetLinkedItems", None)
    if not callable(getter):
        identity_connection.close()
        return {"name": "native_link_membership", "ok": False, "error": "GetLinkedItems is unavailable after reopen."}
    actual: list[dict[str, Any]] = []
    unsupported: list[dict[str, Any]] = []
    try:
        linked_items = list(getter() or [])
    except Exception as exc:
        identity_connection.close()
        return {"name": "native_link_membership", "ok": False, "error": str(exc)}
    try:
        for linked_item in linked_items:
            if linked_item is live_matches[0]:
                continue
            try:
                linked_track_type, linked_track_index = _live_track_identity(linked_item)
                linked_target = _target_from_live_item(
                    linked_item,
                    track_type=linked_track_type,
                    track_index=linked_track_index,
                )
                linked_row = _fetch_db_row_for_exact_live_item(
                    identity_cursor,
                    live_item=linked_item,
                    target=linked_target,
                    timeline_name=timeline_name,
                )
            except Exception as exc:
                unsupported.append({"error": str(exc)})
                continue
            summary = {
                "item_id": str(linked_row.get("Sm2TiItem_id") or ""),
                "track_type": linked_track_type,
                "track_index": linked_track_index,
                "name": linked_target.name,
                "start": linked_target.start,
                "duration": linked_target.duration,
                "end": linked_target.end,
            }
            if linked_track_type == "video":
                actual.append(summary)
            else:
                unsupported.append(summary)

        reciprocal_groups: list[dict[str, Any]] = []
        for expected_linked in plan.get("linked_video", []):
            linked_item_id = str(expected_linked.get("item_id") or "")
            linked_track_index = int(expected_linked.get("track_index") or 1)
            linked_item = None
            try:
                candidates = fresh_conn.timeline.GetItemListInTrack("video", linked_track_index) or []
                for candidate in candidates:
                    candidate_target = _target_from_live_item(
                        candidate,
                        track_type="video",
                        track_index=linked_track_index,
                    )
                    candidate_row = _fetch_db_row_for_exact_live_item(
                        identity_cursor,
                        live_item=candidate,
                        target=candidate_target,
                        timeline_name=timeline_name,
                    )
                    if str(candidate_row.get("Sm2TiItem_id") or "") == linked_item_id:
                        linked_item = candidate
                        break
            except Exception as exc:
                unsupported.append({"item_id": linked_item_id, "error": f"Expected linked video identity readback failed: {exc}"})
                continue
            if linked_item is None:
                unsupported.append({"item_id": linked_item_id, "error": "Expected linked video was absent after reopen."})
                continue
            reciprocal_getter = getattr(linked_item, "GetLinkedItems", None)
            if not callable(reciprocal_getter):
                unsupported.append({"item_id": linked_item_id, "error": "GetLinkedItems is unavailable on linked video."})
                continue
            reciprocal_ids: list[str] = []
            try:
                for reciprocal_item in list(reciprocal_getter() or []):
                    reciprocal_track_type, reciprocal_track_index = _live_track_identity(reciprocal_item)
                    reciprocal_target = _target_from_live_item(
                        reciprocal_item,
                        track_type=reciprocal_track_type,
                        track_index=reciprocal_track_index,
                    )
                    reciprocal_row = _fetch_db_row_for_exact_live_item(
                        identity_cursor,
                        live_item=reciprocal_item,
                        target=reciprocal_target,
                        timeline_name=timeline_name,
                    )
                    reciprocal_id = str(reciprocal_row.get("Sm2TiItem_id") or "")
                    if reciprocal_id and reciprocal_id != linked_item_id:
                        reciprocal_ids.append(reciprocal_id)
            except Exception as exc:
                unsupported.append({"item_id": linked_item_id, "error": f"Reciprocal linked-item readback failed: {exc}"})
                continue
            reciprocal_group = {
                "item_id": linked_item_id,
                "expected_reciprocal_item_ids": [expected_audio_item_id],
                "actual_reciprocal_item_ids": sorted(reciprocal_ids),
            }
            reciprocal_groups.append(reciprocal_group)
            if sorted(reciprocal_ids) != [expected_audio_item_id]:
                unsupported.append({**reciprocal_group, "error": "Linked video membership is not exact and reciprocal."})
    finally:
        identity_connection.close()

    updated_video = {
        str(item.get("item_id") or ""): item
        for item in mutation_result.get("updated_items", [])
        if item.get("track_type") == "video"
    }
    expected: list[dict[str, Any]] = []
    for linked in plan.get("linked_video", []):
        changed = updated_video.get(str(linked.get("item_id") or ""))
        expected_item = changed or linked
        expected_start = changed.get("new_start") if changed else linked.get("start")
        expected_duration = changed.get("new_duration") if changed else linked.get("duration")
        expected_end = changed.get("new_end") if changed else linked.get("end")
        expected.append(
            {
                "item_id": str(expected_item.get("item_id") or linked.get("item_id") or ""),
                "track_type": "video",
                "track_index": int(expected_item.get("track_index") or 1),
                "name": str(expected_item.get("name") or ""),
                "start": int(expected_start or 0),
                "duration": int(expected_duration or 0),
                "end": int(expected_end or 0),
            }
        )
    def sort_key(item: dict[str, Any]) -> tuple[str, int, int, int, str]:
        return item["item_id"], item["track_index"], item["start"], item["end"], item["name"]
    expected = sorted(expected, key=sort_key)
    actual = sorted(actual, key=sort_key)
    return {
        "name": "native_link_membership",
        "ok": not unsupported and actual == expected,
        "expected": expected,
        "actual": actual,
        "unsupported_linked_items": unsupported,
        "reciprocal_groups": reciprocal_groups,
        "expected_audio_item_id": expected_audio_item_id,
        "actual_audio_item_id": actual_audio_item_id,
        "evidence_modality": "TimelineItem.GetLinkedItems",
    }


def _verify_duration_readback(fresh_conn: Any, mutation_result: dict[str, Any], session: Any) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    for item in mutation_result.get("updated_items", []):
        track_type = str(item.get("track_type") or "video")
        track_index = int(item.get("track_index") or 1)
        expected_start = int(item.get("new_start") or 0)
        expected_end = int(item.get("new_end") or 0)
        expected_duration = int(item.get("new_duration") or 0)
        expected_names = {str(value) for value in item.get("readback_name_candidates", []) if str(value or "").strip()}
        expected_name = str(item.get("name") or "")
        if expected_name:
            expected_names.add(expected_name)
        timeline_start = _timeline_start_frame(fresh_conn)
        candidates = _readback_range_candidates(expected_start, expected_end, timeline_start)
        start_candidates = {start for start, _end in candidates}
        matches = []
        try:
            live_items = fresh_conn.timeline.GetItemListInTrack(track_type, track_index) or []
        except Exception as exc:
            checks.append({"ok": False, "item_id": item.get("item_id"), "error": str(exc), "track_type": track_type, "track_index": track_index})
            continue
        for live_item in live_items:
            try:
                live_name = str(live_item.GetName() or "")
                live_start = timeline_item_mutation.timeline_item_start(live_item)
                live_end = timeline_item_mutation.timeline_item_end(live_item)
                live_duration = timeline_item_mutation.timeline_item_duration(live_item)
            except Exception:
                continue
            if live_start is None or live_end is None or live_duration is None:
                continue
            if live_start not in start_candidates:
                continue
            if expected_names and live_name not in expected_names:
                continue
            matches.append({"name": live_name, "start": live_start, "end": live_end, "duration": live_duration})
        ok = any((row["start"], row["end"]) in candidates and row["duration"] == expected_duration for row in matches)
        checks.append(
            {
                "ok": ok,
                "item_id": item.get("item_id"),
                "expected": {
                    "start": expected_start,
                    "end": expected_end,
                    "duration": expected_duration,
                    "name": expected_name,
                    "name_candidates": sorted(expected_names),
                },
                "matches": matches,
                "track_type": track_type,
                "track_index": track_index,
            }
        )
    protected_check = None
    if "protected_state_before" in mutation_result and session is not None:
        protected_check = verify_protected_timeline_edit_state(session, mutation_result)
        checks.append(protected_check)
    native_link_check = None
    if mutation_result.get("native_link_identity") is not None:
        native_link_check = verify_native_fairlight_link_state(fresh_conn, mutation_result, session)
        checks.append(native_link_check)
    return {
        "status": "verified" if checks and all(check["ok"] for check in checks) else "failed",
        "checks": checks,
        "protected_state_check": protected_check,
        "native_link_check": native_link_check,
        "evidence_modalities": ["live_timeline_readback", "project_db_structural_readback", "TimelineItem.GetLinkedItems"],
    }


def _verify_head_trim_readback(fresh_conn: Any, mutation_result: dict[str, Any], session: Any) -> dict[str, Any]:
    live = _verify_duration_readback(fresh_conn, mutation_result, session)
    db_checks: list[dict[str, Any]] = []
    connection = sqlite3.connect(session.project_db_path, timeout=5.0)
    try:
        cursor = connection.cursor()
        for item in mutation_result.get("updated_items", []):
            row = cursor.execute(
                'SELECT Start, Duration, "In" FROM Sm2TiItem WHERE Sm2TiItem_id = ?',
                (item.get("item_id"),),
            ).fetchone()
            expected = {
                "start": str(int(item.get("new_start") or 0)),
                "duration": str(int(item.get("new_duration") or 0)),
                "in": str(int(item.get("new_in") or 0)),
            }
            actual = None
            ok = False
            if row is not None:
                actual = {
                    "start": None if row[0] is None else str(row[0]),
                    "duration": None if row[1] is None else str(row[1]),
                    "in": None if row[2] is None else str(row[2]),
                }
                try:
                    actual_ints = {
                        "start": _int_cell(row[0], field="Start"),
                        "duration": _int_cell(row[1], field="Duration"),
                        "in": _int_cell(row[2] or 0, field="In"),
                    }
                    expected_ints = {
                        "start": int(item.get("new_start") or 0),
                        "duration": int(item.get("new_duration") or 0),
                        "in": int(item.get("new_in") or 0),
                    }
                    ok = actual_ints == expected_ints
                except ValidationError:
                    ok = False
            db_checks.append(
                {
                    "name": "db_head_trim_fields",
                    "ok": ok,
                    "item_id": item.get("item_id"),
                    "expected": expected,
                    "actual": actual,
                }
            )
    finally:
        connection.close()

    live_checks = list(live.get("checks") or [])
    checks = live_checks + db_checks
    return {
        "status": "verified" if checks and all(check.get("ok") for check in checks) else "failed",
        "checks": checks,
        "live_status": live.get("status"),
    }


def _verify_tail_trim_readback(fresh_conn: Any, mutation_result: dict[str, Any], session: Any) -> dict[str, Any]:
    live = _verify_duration_readback(fresh_conn, mutation_result, session)
    db_checks: list[dict[str, Any]] = []
    connection = sqlite3.connect(session.project_db_path, timeout=5.0)
    try:
        cursor = connection.cursor()
        for item in mutation_result.get("updated_items", []):
            expected_in = item.get("new_in")
            row = cursor.execute(
                'SELECT Start, Duration, "In" FROM Sm2TiItem WHERE Sm2TiItem_id = ?',
                (item.get("item_id"),),
            ).fetchone()
            expected = {
                "start": str(int(item.get("new_start") or 0)),
                "duration": str(int(item.get("new_duration") or 0)),
                "in": None if expected_in is None else str(int(expected_in)),
            }
            actual = None
            ok = False
            if row is not None:
                actual = {
                    "start": None if row[0] is None else str(row[0]),
                    "duration": None if row[1] is None else str(row[1]),
                    "in": None if row[2] is None else str(row[2]),
                }
                try:
                    actual_ints = {
                        "start": _int_cell(row[0], field="Start"),
                        "duration": _int_cell(row[1], field="Duration"),
                    }
                    expected_ints = {
                        "start": int(item.get("new_start") or 0),
                        "duration": int(item.get("new_duration") or 0),
                    }
                    if expected_in is not None:
                        actual_ints["in"] = _int_cell(row[2] or 0, field="In")
                        expected_ints["in"] = int(expected_in)
                    ok = actual_ints == expected_ints
                except ValidationError:
                    ok = False
            db_checks.append(
                {
                    "name": "db_tail_trim_fields",
                    "ok": ok,
                    "item_id": item.get("item_id"),
                    "expected": expected,
                    "actual": actual,
                }
            )
    finally:
        connection.close()

    checks = list(live.get("checks") or []) + db_checks
    return {
        "status": "verified" if checks and all(check.get("ok") for check in checks) else "failed",
        "checks": checks,
        "live_status": live.get("status"),
    }


def _verify_source_slip_readback(fresh_conn: Any, mutation_result: dict[str, Any], session: Any) -> dict[str, Any]:
    live = _verify_duration_readback(fresh_conn, mutation_result, session)
    db_checks: list[dict[str, Any]] = []
    connection = sqlite3.connect(session.project_db_path, timeout=5.0)
    try:
        cursor = connection.cursor()
        for item in mutation_result.get("updated_items", []):
            row = cursor.execute(
                'SELECT Start, Duration, "In" FROM Sm2TiItem WHERE Sm2TiItem_id = ?',
                (item.get("item_id"),),
            ).fetchone()
            expected = {
                "start": str(int(item.get("new_start") or 0)),
                "duration": str(int(item.get("new_duration") or 0)),
                "in": str(int(item.get("new_in") or 0)),
            }
            actual = None
            ok = False
            if row is not None:
                actual = {
                    "start": None if row[0] is None else str(row[0]),
                    "duration": None if row[1] is None else str(row[1]),
                    "in": None if row[2] is None else str(row[2]),
                }
                try:
                    actual_ints = {
                        "start": _int_cell(row[0], field="Start"),
                        "duration": _int_cell(row[1], field="Duration"),
                        "in": _int_cell(row[2] or 0, field="In"),
                    }
                    expected_ints = {
                        "start": int(item.get("new_start") or 0),
                        "duration": int(item.get("new_duration") or 0),
                        "in": int(item.get("new_in") or 0),
                    }
                    ok = actual_ints == expected_ints
                except ValidationError:
                    ok = False
            db_checks.append(
                {
                    "name": "db_source_slip_fields",
                    "ok": ok,
                    "item_id": item.get("item_id"),
                    "expected": expected,
                    "actual": actual,
                }
            )
    finally:
        connection.close()

    checks = list(live.get("checks") or []) + db_checks
    return {
        "status": "verified" if checks and all(check.get("ok") for check in checks) else "failed",
        "checks": checks,
        "live_status": live.get("status"),
    }


def slip_timeline_item_source(
    conn: Any,
    *,
    timeline_name: str | None = None,
    item_id: str | None = None,
    track_type: str = "video",
    track_index: int = 1,
    start_frame: str | None = None,
    current_end_frame: str | None = None,
    name: str | None = None,
    source_start_frame: str | None = None,
    delta: str | None = None,
    allow_linked_audio_only: bool = False,
    include_linked_video: bool = False,
    require_fairlight_edit_contract: bool = False,
) -> dict[str, Any]:
    """Slip one timeline item's source In frame using the Disk Project.db route."""
    normalized_track_type = _normalize_selector_track_type(track_type)
    normalized_track_index = timeline_ops.validate_timeline_track_index(track_index)
    if timeline_name:
        timeline_ops.switch_timeline(conn, name=timeline_name)
    target_timeline = _timeline_name(conn)

    live_target: TimelineItemDurationTarget | None = None
    live_item: Any | None = None
    live_source_bounds: dict[str, Any] | None = None
    live_source_bounds_error: Exception | None = None
    if not item_id:
        live_target, live_item = _select_live_item(
            conn,
            track_type=normalized_track_type,
            track_index=normalized_track_index,
            start_ref=start_frame,
            current_end_ref=current_end_frame,
            name=name,
        )
        live_source_bounds = _live_source_bounds(live_item)
        finite_source_bounds, media_type = _uses_finite_source_bounds(live_item)
        if finite_source_bounds and live_source_bounds is None:
            live_source_bounds_error = ValidationError(
                "Live source bounds are unavailable for the selected finite media item.",
                details={"media_type": media_type, "selector": asdict(live_target)},
            )
        new_in = -1
        requested = {"mode": "pending_db_row"}
    else:
        if start_frame or current_end_frame or name:
            raise ValidationError(
                "--item-id is mutually exclusive with --start-frame, --current-end-frame, and --name.",
                details={"item_id": item_id, "start_frame": start_frame, "current_end_frame": current_end_frame, "name": name},
            )
        new_in = -1
        requested = {"mode": "pending_db_row"}
        try:
            current_database = db_session.resolve_current_disk_project_db(conn, allow_project_name_inference=True)
            project_db_path = str(current_database["project_db_path"])
            prelookup_connection = sqlite3.connect(project_db_path, timeout=5.0)
            prelookup_connection.row_factory = sqlite3.Row
            try:
                prelookup_cursor = prelookup_connection.cursor()
                row = _fetch_db_row_by_item_id(
                    prelookup_cursor,
                    item_id=str(item_id),
                    timeline_name=target_timeline,
                    track_type=normalized_track_type if track_type else None,
                    track_index=None,
                )
                row_start = _int_cell(row.get("Start"), field="Start")
                row_duration = _int_cell(row.get("Duration"), field="Duration")
                prelookup_target = TimelineItemDurationTarget(
                    item_id=str(item_id),
                    track_type=_track_type_from_db_row(row, normalized_track_type),
                    track_index=_track_index_from_db_row(
                        prelookup_cursor,
                        row=row,
                        timeline_name=target_timeline,
                        track_type=normalized_track_type,
                    ),
                    name=str(row.get("Name") or ""),
                    start=row_start,
                    duration=row_duration,
                    end=row_start + row_duration,
                )
            finally:
                prelookup_connection.close()
            _bounds_target, live_item = _select_live_item(
                conn,
                track_type=prelookup_target.track_type,
                track_index=prelookup_target.track_index,
                start_ref=f"{prelookup_target.start}f",
                current_end_ref=f"{prelookup_target.end}f",
                name=prelookup_target.name or None,
            )
            live_source_bounds = _live_source_bounds(live_item)
            finite_source_bounds, media_type = _uses_finite_source_bounds(live_item)
            live_source_bounds_error = (
                ValidationError(
                    "Live source bounds are unavailable for the selected finite media item.",
                    details={"media_type": media_type, "selector": asdict(prelookup_target)},
                )
                if finite_source_bounds and live_source_bounds is None
                else None
            )
        except Exception as exc:
            live_source_bounds = None
            live_source_bounds_error = exc

    edit_identity: dict[str, Any] | None = None
    fairlight_lock_targets: tuple[tuple[str, int, str], ...] | None = None
    fairlight_timeline_identity: FairlightEditTimelineIdentity | None = None
    if require_fairlight_edit_contract:
        if live_target is None:
            live_target = _read_item_id_target_before_db_close(
                conn,
                item_id=str(item_id),
                timeline_name=target_timeline,
                track_type="audio",
            )
            _selected_target, live_item = _select_live_item(
                conn,
                track_type=live_target.track_type,
                track_index=live_target.track_index,
                start_ref=f"{live_target.start}f",
                current_end_ref=f"{live_target.end}f",
                name=live_target.name or None,
            )
        assert live_item is not None
        edit_identity = prepare_fairlight_clip_edit_identity(
            conn,
            target=live_target,
            live_item=live_item,
            timeline_name=target_timeline,
        )
        current_in = int(edit_identity["target_db_identity"]["source_in"])
        new_in, requested = _resolve_source_slip_in(
            conn,
            current_in=current_in,
            source_start_frame=source_start_frame,
            delta=delta,
        )
        if int(new_in) == current_in:
            return fairlight_clip_edit_no_change(
                action="timeline.items.slip_source",
                timeline_name=target_timeline,
                target=live_target,
                requested=requested,
                plan=edit_identity,
                reason="fairlight_clip_slip_absolute_no_change",
            )
        fairlight_lock_targets = fairlight_edit_track_lock_targets(
            target=live_target,
            plan=edit_identity,
        )
        fairlight_timeline_identity = require_fairlight_edit_timeline_identity(conn)
        require_fairlight_edit_tracks_unlocked(
            conn,
            target=live_target,
            plan=edit_identity,
            track_targets=fairlight_lock_targets,
        )

    def _writer(_connection: sqlite3.Connection, cursor: sqlite3.Cursor, _session: db_session.DiskDbMutationSession) -> dict[str, Any]:
        nonlocal new_in, requested, live_source_bounds, live_source_bounds_error
        linked_video_item_ids: list[str] | None = None
        linked_video_source_bounds: dict[str, dict[str, Any] | None] | None = None
        if edit_identity is not None:
            row, linked_video_item_ids, linked_video_source_bounds = assert_fairlight_clip_edit_identity(
                cursor,
                plan=edit_identity,
                timeline_name=target_timeline,
            )
            result_target = _target_from_db_row(
                cursor,
                row=row,
                item_id=str(edit_identity["target_item_id"]),
                timeline_name=target_timeline,
                fallback_track_type="audio",
            )
        elif item_id:
            row = _fetch_db_row_by_item_id(
                cursor,
                item_id=str(item_id),
                timeline_name=target_timeline,
                track_type=normalized_track_type if track_type else None,
                track_index=None,
            )
            row_start = _int_cell(row.get("Start"), field="Start")
            row_duration = _int_cell(row.get("Duration"), field="Duration")
            result_target = TimelineItemDurationTarget(
                item_id=str(item_id),
                track_type=_track_type_from_db_row(row, normalized_track_type),
                track_index=_track_index_from_db_row(cursor, row=row, timeline_name=target_timeline, track_type=normalized_track_type),
                name=str(row.get("Name") or ""),
                start=row_start,
                duration=row_duration,
                end=row_start + row_duration,
            )
            if live_source_bounds is None and getattr(conn, "timeline", None) is not None:
                _bounds_target, live_item = _select_live_item(
                    conn,
                    track_type=result_target.track_type,
                    track_index=result_target.track_index,
                    start_ref=f"{row_start}f",
                    current_end_ref=f"{row_start + row_duration}f",
                    name=result_target.name or None,
                )
                live_source_bounds = _live_source_bounds(live_item)
                live_source_bounds_error = None
        else:
            assert live_target is not None
            row = _fetch_db_row_for_live_target(cursor, target=live_target, timeline_name=target_timeline or "")
            result_target = live_target

        current_in = _source_in_from_row(row)
        new_in, requested = _resolve_source_slip_in(
            conn,
            current_in=current_in,
            source_start_frame=source_start_frame,
            delta=delta,
        )
        if live_source_bounds is not None:
            _validate_source_slip_bounds(
                current_in=current_in,
                new_in=int(new_in),
                right_offset=live_source_bounds.get("right_offset"),
                item_duration=_int_cell(row.get("Duration"), field="Duration"),
                media_type=live_source_bounds.get("media_type"),
                name=str(row.get("Name") or result_target.name or ""),
            )
        elif (
            live_source_bounds_error is not None
            and int(new_in) > int(current_in)
            and (item_id is not None or require_fairlight_edit_contract)
        ):
            raise ValidationError(
                "Cannot verify the selected item_id source slip against live source bounds.",
                details={
                    "item_id": str(item_id),
                    "current_in": int(current_in),
                    "requested_in": int(new_in),
                    "selector": asdict(result_target),
                    "live_lookup_error": str(live_source_bounds_error),
                },
            )
        protected_state_before = (
            capture_timeline_edit_structural_state(cursor, timeline_name=target_timeline)
            if require_fairlight_edit_contract
            else None
        )
        updated = _apply_source_slip_update(
            cursor,
            target_row=row,
            new_in=int(new_in),
            allow_linked_audio_only=allow_linked_audio_only,
            include_linked_video=include_linked_video,
            timeline_name=target_timeline,
            linked_video_item_ids=linked_video_item_ids,
            linked_video_source_bounds=linked_video_source_bounds,
        )
        updated.update(
            {
                "track_type": result_target.track_type,
                "track_index": result_target.track_index,
                "selector": asdict(result_target),
                "readback_name_candidates": sorted(
                    {
                        str(value)
                        for value in (updated.get("name"), result_target.name, *result_target.aliases)
                        if str(value or "").strip()
                    }
                ),
            }
        )
        linked_video_items: list[dict[str, Any]] = []
        for linked_update in updated.get("linked_video_updates", []):
            linked_update = dict(linked_update)
            linked_update.update(
                {
                    "track_type": "video",
                    "track_index": _track_index_from_db_row(
                        cursor,
                        row=_fetch_db_row_by_item_id(
                            cursor,
                            item_id=str(linked_update.get("item_id") or ""),
                            timeline_name=target_timeline,
                            track_type="video",
                            track_index=None,
                        ),
                        timeline_name=target_timeline,
                        track_type="video",
                    ),
                    "selector": {
                        "item_id": linked_update.get("item_id"),
                        "track_type": "video",
                        "name": linked_update.get("name"),
                        "start": linked_update.get("old_start"),
                        "duration": linked_update.get("old_duration"),
                        "end": linked_update.get("old_end"),
                    },
                    "readback_name_candidates": sorted({str(linked_update.get("name") or "")} - {""}),
                }
            )
            linked_video_items.append(linked_update)
        result = {
            "action": "timeline.items.slip_source",
            "timeline_name": target_timeline,
            "requested": requested,
            "updated_items": [updated, *linked_video_items],
            "linked_video_included": bool(linked_video_items),
            "native_link_identity": edit_identity,
        }
        if protected_state_before is not None:
            result["protected_state_before"] = protected_state_before
        return result

    result = db_session.execute_sqlite_disk_db_mutation(
        conn,
        context="DB-backed timeline item source slip",
        writer=_writer,
        verifier=_verify_source_slip_readback,
        pre_close_validator=(
            fairlight_edit_pre_close_validator(
                target=live_target,
                plan=edit_identity,
                track_targets=fairlight_lock_targets,
                intended_timeline=fairlight_timeline_identity,
            )
            if edit_identity is not None
            and live_target is not None
            and fairlight_lock_targets is not None
            and fairlight_timeline_identity is not None
            else None
        ),
        allow_project_name_inference=True,
        require_verified=True,
    )
    verification = result.get("verification") if isinstance(result, dict) else None
    if isinstance(verification, dict) and verification.get("status") != "verified":
        raise APICallFailed(
            "Timeline item source slip DB write did not verify after DaVinci Resolve reopened the project.",
            details={"mutation": result, "verification": verification},
        )
    return result


def trim_timeline_item_head(
    conn: Any,
    *,
    timeline_name: str | None = None,
    item_id: str | None = None,
    track_type: str = "video",
    track_index: int = 1,
    start_frame: str | None = None,
    current_end_frame: str | None = None,
    name: str | None = None,
    target_start_frame: str | None = None,
    head_delta: str | None = None,
    allow_overlap: bool = False,
    allow_linked_audio_only: bool = False,
    include_linked_video: bool = False,
    require_fairlight_edit_contract: bool = False,
) -> dict[str, Any]:
    """Trim one timeline item's left edge using the Disk Project.db route."""
    normalized_track_type = _normalize_selector_track_type(track_type)
    normalized_track_index = timeline_ops.validate_timeline_track_index(track_index)
    if timeline_name:
        timeline_ops.switch_timeline(conn, name=timeline_name)
    target_timeline = _timeline_name(conn)
    timeline_start_frame = _timeline_start_frame(conn)

    live_target: TimelineItemDurationTarget | None = None
    live_item: Any | None = None
    if not item_id:
        live_target, live_item = _select_live_item(
            conn,
            track_type=normalized_track_type,
            track_index=normalized_track_index,
            start_ref=start_frame,
            current_end_ref=current_end_frame,
            name=name,
        )
        new_start, requested = _resolve_head_trim_start(
            conn,
            current_start=live_target.start,
            current_end=live_target.end,
            target_start_frame=target_start_frame,
            head_delta=head_delta,
        )
    else:
        if start_frame or current_end_frame or name:
            raise ValidationError(
                "--item-id is mutually exclusive with --start-frame, --current-end-frame, and --name.",
                details={"item_id": item_id, "start_frame": start_frame, "current_end_frame": current_end_frame, "name": name},
            )
        new_start = -1
        requested = {"mode": "pending_db_row"}

    edit_identity: dict[str, Any] | None = None
    fairlight_lock_targets: tuple[tuple[str, int, str], ...] | None = None
    fairlight_timeline_identity: FairlightEditTimelineIdentity | None = None
    if require_fairlight_edit_contract:
        if live_target is None:
            live_target = _read_item_id_target_before_db_close(
                conn,
                item_id=str(item_id),
                timeline_name=target_timeline,
                track_type="audio",
            )
            _selected_target, live_item = _select_live_item(
                conn,
                track_type=live_target.track_type,
                track_index=live_target.track_index,
                start_ref=f"{live_target.start}f",
                current_end_ref=f"{live_target.end}f",
                name=live_target.name or None,
            )
        assert live_item is not None
        edit_identity = prepare_fairlight_clip_edit_identity(
            conn,
            target=live_target,
            live_item=live_item,
            timeline_name=target_timeline,
        )
        new_start, requested = _resolve_head_trim_start(
            conn,
            current_start=live_target.start,
            current_end=live_target.end,
            target_start_frame=target_start_frame,
            head_delta=head_delta,
        )
        if int(new_start) == int(live_target.start):
            return fairlight_clip_edit_no_change(
                action="timeline.items.trim_head",
                timeline_name=target_timeline,
                target=live_target,
                requested=requested,
                plan=edit_identity,
                reason="fairlight_clip_head_trim_absolute_no_change",
            )
        fairlight_lock_targets = fairlight_edit_track_lock_targets(
            target=live_target,
            plan=edit_identity,
        )
        fairlight_timeline_identity = require_fairlight_edit_timeline_identity(conn)
        require_fairlight_edit_tracks_unlocked(
            conn,
            target=live_target,
            plan=edit_identity,
            track_targets=fairlight_lock_targets,
        )

    def _writer(_connection: sqlite3.Connection, cursor: sqlite3.Cursor, _session: db_session.DiskDbMutationSession) -> dict[str, Any]:
        nonlocal new_start, requested
        linked_video_item_ids: list[str] | None = None
        if edit_identity is not None:
            row, linked_video_item_ids, _linked_source_bounds = assert_fairlight_clip_edit_identity(
                cursor,
                plan=edit_identity,
                timeline_name=target_timeline,
            )
            result_target = _target_from_db_row(
                cursor,
                row=row,
                item_id=str(edit_identity["target_item_id"]),
                timeline_name=target_timeline,
                fallback_track_type="audio",
            )
            row_start = _int_cell(row.get("Start"), field="Start")
            row_duration = _int_cell(row.get("Duration"), field="Duration")
            new_start, requested = _resolve_head_trim_start(
                conn,
                current_start=row_start,
                current_end=row_start + row_duration,
                target_start_frame=target_start_frame,
                head_delta=head_delta,
            )
        elif item_id:
            row = _fetch_db_row_by_item_id(
                cursor,
                item_id=str(item_id),
                timeline_name=target_timeline,
                track_type=normalized_track_type if track_type else None,
                track_index=None,
            )
            row_start = _int_cell(row.get("Start"), field="Start")
            row_duration = _int_cell(row.get("Duration"), field="Duration")
            new_start, requested = _resolve_head_trim_start(
                conn,
                current_start=row_start,
                current_end=row_start + row_duration,
                target_start_frame=target_start_frame,
                head_delta=head_delta,
            )
            result_target = TimelineItemDurationTarget(
                item_id=str(item_id),
                track_type=_track_type_from_db_row(row, normalized_track_type),
                track_index=_track_index_from_db_row(cursor, row=row, timeline_name=target_timeline, track_type=normalized_track_type),
                name=str(row.get("Name") or ""),
                start=row_start,
                duration=row_duration,
                end=row_start + row_duration,
            )
        else:
            assert live_target is not None
            row = _fetch_db_row_for_live_target(cursor, target=live_target, timeline_name=target_timeline or "")
            result_target = live_target

        protected_state_before = (
            capture_timeline_edit_structural_state(cursor, timeline_name=target_timeline)
            if require_fairlight_edit_contract
            else None
        )
        updated = _apply_head_trim_update(
            cursor,
            target_row=row,
            new_start=int(new_start),
            allow_overlap=allow_overlap,
            fps=conn.fps,
            allow_linked_audio_only=allow_linked_audio_only,
            include_linked_video=include_linked_video,
            timeline_name=target_timeline,
            linked_video_item_ids=linked_video_item_ids,
            timeline_start_frame=timeline_start_frame,
        )
        updated.update(
            {
                "track_type": result_target.track_type,
                "track_index": result_target.track_index,
                "selector": asdict(result_target),
                "readback_name_candidates": sorted(
                    {
                        str(value)
                        for value in (updated.get("name"), result_target.name, *result_target.aliases)
                        if str(value or "").strip()
                    }
                ),
            }
        )
        linked_video_items: list[dict[str, Any]] = []
        for linked_update in updated.get("linked_video_updates", []):
            linked_update = dict(linked_update)
            linked_update.update(
                {
                    "track_type": "video",
                    "track_index": _track_index_from_db_row(
                        cursor,
                        row=_fetch_db_row_by_item_id(
                            cursor,
                            item_id=str(linked_update.get("item_id") or ""),
                            timeline_name=target_timeline,
                            track_type="video",
                            track_index=None,
                        ),
                        timeline_name=target_timeline,
                        track_type="video",
                    ),
                    "selector": {
                        "item_id": linked_update.get("item_id"),
                        "track_type": "video",
                        "name": linked_update.get("name"),
                        "start": linked_update.get("old_start"),
                        "duration": linked_update.get("old_duration"),
                        "end": linked_update.get("old_end"),
                    },
                    "readback_name_candidates": sorted({str(linked_update.get("name") or "")} - {""}),
                }
            )
            linked_video_items.append(linked_update)
        result = {
            "action": "timeline.items.trim_head",
            "timeline_name": target_timeline,
            "requested": requested,
            "allow_overlap": bool(allow_overlap),
            "updated_items": [updated, *linked_video_items],
            "linked_video_included": bool(linked_video_items),
            "native_link_identity": edit_identity,
        }
        if protected_state_before is not None:
            result["protected_state_before"] = protected_state_before
        return result

    result = db_session.execute_sqlite_disk_db_mutation(
        conn,
        context="DB-backed timeline item head trim",
        writer=_writer,
        verifier=_verify_head_trim_readback,
        pre_close_validator=(
            fairlight_edit_pre_close_validator(
                target=live_target,
                plan=edit_identity,
                track_targets=fairlight_lock_targets,
                intended_timeline=fairlight_timeline_identity,
            )
            if edit_identity is not None
            and live_target is not None
            and fairlight_lock_targets is not None
            and fairlight_timeline_identity is not None
            else None
        ),
        allow_project_name_inference=True,
        require_verified=True,
    )
    verification = result.get("verification") if isinstance(result, dict) else None
    if isinstance(verification, dict) and verification.get("status") != "verified":
        raise APICallFailed(
            "Timeline item head trim DB write did not verify after DaVinci Resolve reopened the project.",
            details={"mutation": result, "verification": verification},
        )
    return result


def set_timeline_item_duration(
    conn: Any,
    *,
    timeline_name: str | None = None,
    item_id: str | None = None,
    track_type: str = "video",
    track_index: int = 1,
    start_frame: str | None = None,
    current_end_frame: str | None = None,
    name: str | None = None,
    duration: str | None = None,
    target_end_frame: str | None = None,
    allow_overlap: bool = False,
    enforce_source_bounds: bool = True,
    allow_linked_audio_only: bool = False,
    include_linked_video: bool = False,
    require_fairlight_edit_contract: bool = False,
) -> dict[str, Any]:
    """Set one timeline item's public duration/end using the Disk Project.db route."""
    normalized_track_type = _normalize_selector_track_type(track_type)
    normalized_track_index = timeline_ops.validate_timeline_track_index(track_index)
    if timeline_name:
        timeline_ops.switch_timeline(conn, name=timeline_name)
    target_timeline = _timeline_name(conn)

    live_target: TimelineItemDurationTarget | None = None
    live_item = None
    if not item_id:
        live_target, live_item = _select_live_item(
            conn,
            track_type=normalized_track_type,
            track_index=normalized_track_index,
            start_ref=start_frame,
            current_end_ref=current_end_frame,
            name=name,
        )
        new_duration, new_end, requested = _resolve_new_duration(
            conn,
            item_start=live_target.start,
            duration=duration,
            target_end_frame=target_end_frame,
        )
        right_offset = _live_item_right_offset(live_item)
        finite_source_bounds, media_type = _uses_finite_source_bounds(live_item)
        if (
            require_fairlight_edit_contract
            and enforce_source_bounds
            and finite_source_bounds
            and right_offset is None
            and new_duration > live_target.duration
        ):
            raise ValidationError(
                "Cannot verify tail-trim expansion against live source bounds.",
                details={
                    "reason": "fairlight_source_bounds_unavailable",
                    "media_type": media_type,
                    "selector": asdict(live_target),
                    "requested_duration": new_duration,
                },
            )
        if enforce_source_bounds and finite_source_bounds and right_offset is not None and new_duration > live_target.duration + right_offset:
            _validate_duration_source_bounds(
                name=live_target.name,
                start=live_target.start,
                current_duration=live_target.duration,
                requested_duration=new_duration,
                live_source_bounds={"right_offset": right_offset, "media_type": media_type},
                live_lookup_error=None,
            )
    else:
        if start_frame or current_end_frame or name:
            raise ValidationError(
                "--item-id is mutually exclusive with --start-frame, --current-end-frame, and --name.",
                details={"item_id": item_id, "start_frame": start_frame, "current_end_frame": current_end_frame, "name": name},
            )
        new_duration = -1
        new_end = -1
        requested = {"mode": "pending_db_row"}

    item_id_live_bounds = None
    item_id_live_error = None
    if item_id and enforce_source_bounds:
        try:
            preflight_target = _read_item_id_target_before_db_close(
                conn,
                item_id=str(item_id),
                timeline_name=target_timeline,
                track_type=normalized_track_type,
            )
        except Exception as exc:
            item_id_live_error = exc
        else:
            item_id_live_bounds, item_id_live_error = _item_id_live_source_bounds_for_duration(conn, target=preflight_target)
            preflight_duration, _preflight_end, _preflight_requested = _resolve_new_duration(
                conn,
                item_start=preflight_target.start,
                duration=duration,
                target_end_frame=target_end_frame,
            )
            _validate_duration_source_bounds(
                item_id=str(item_id),
                name=preflight_target.name,
                start=preflight_target.start,
                current_duration=preflight_target.duration,
                requested_duration=int(preflight_duration),
                live_source_bounds=item_id_live_bounds,
                live_lookup_error=item_id_live_error,
            )

    edit_identity: dict[str, Any] | None = None
    fairlight_lock_targets: tuple[tuple[str, int, str], ...] | None = None
    fairlight_timeline_identity: FairlightEditTimelineIdentity | None = None
    if require_fairlight_edit_contract:
        if live_target is None:
            live_target = _read_item_id_target_before_db_close(
                conn,
                item_id=str(item_id),
                timeline_name=target_timeline,
                track_type="audio",
            )
            _selected_target, live_item = _select_live_item(
                conn,
                track_type=live_target.track_type,
                track_index=live_target.track_index,
                start_ref=f"{live_target.start}f",
                current_end_ref=f"{live_target.end}f",
                name=live_target.name or None,
            )
        assert live_item is not None
        edit_identity = prepare_fairlight_clip_edit_identity(
            conn,
            target=live_target,
            live_item=live_item,
            timeline_name=target_timeline,
        )
        new_duration, new_end, requested = _resolve_new_duration(
            conn,
            item_start=live_target.start,
            duration=duration,
            target_end_frame=target_end_frame,
        )
        if (
            int(new_duration) == int(live_target.duration)
            and int(new_end) == int(live_target.end)
        ):
            return fairlight_clip_edit_no_change(
                action="timeline.items.set_duration",
                timeline_name=target_timeline,
                target=live_target,
                requested=requested,
                plan=edit_identity,
                reason="fairlight_clip_tail_trim_absolute_no_change",
            )
        fairlight_lock_targets = fairlight_edit_track_lock_targets(
            target=live_target,
            plan=edit_identity,
        )
        fairlight_timeline_identity = require_fairlight_edit_timeline_identity(conn)
        require_fairlight_edit_tracks_unlocked(
            conn,
            target=live_target,
            plan=edit_identity,
            track_targets=fairlight_lock_targets,
        )

    def _writer(_connection: sqlite3.Connection, cursor: sqlite3.Cursor, _session: db_session.DiskDbMutationSession) -> dict[str, Any]:
        nonlocal new_duration, new_end, requested
        linked_video_item_ids: list[str] | None = None
        linked_video_source_bounds: dict[str, dict[str, Any] | None] | None = None
        if edit_identity is not None:
            row, linked_video_item_ids, linked_video_source_bounds = assert_fairlight_clip_edit_identity(
                cursor,
                plan=edit_identity,
                timeline_name=target_timeline,
            )
            row_start = _int_cell(row.get("Start"), field="Start")
            new_duration, new_end, requested = _resolve_new_duration(
                conn,
                item_start=row_start,
                duration=duration,
                target_end_frame=target_end_frame,
            )
            result_target = _target_from_db_row(
                cursor,
                item_id=str(edit_identity["target_item_id"]),
                row=row,
                timeline_name=target_timeline,
                fallback_track_type="audio",
            )
        elif item_id:
            row = _fetch_db_row_by_item_id(
                cursor,
                item_id=str(item_id),
                timeline_name=target_timeline,
                track_type=normalized_track_type if track_type else None,
                track_index=None,
            )
            row_start = _int_cell(row.get("Start"), field="Start")
            new_duration, new_end, requested = _resolve_new_duration(
                conn,
                item_start=row_start,
                duration=duration,
                target_end_frame=target_end_frame,
            )
            result_target = _target_from_db_row(
                cursor,
                item_id=str(item_id),
                row=row,
                timeline_name=target_timeline,
                fallback_track_type=normalized_track_type,
            )
        else:
            assert live_target is not None
            row = _fetch_db_row_for_live_target(cursor, target=live_target, timeline_name=target_timeline or "")
            result_target = live_target
        protected_state_before = (
            capture_timeline_edit_structural_state(cursor, timeline_name=target_timeline)
            if require_fairlight_edit_contract
            else None
        )
        updated = _apply_duration_update(
            cursor,
            target_row=row,
            new_duration=int(new_duration),
            new_end=int(new_end),
            allow_overlap=allow_overlap,
            fps=conn.fps,
            allow_linked_audio_only=allow_linked_audio_only,
            include_linked_video=include_linked_video,
            timeline_name=target_timeline,
            linked_video_item_ids=linked_video_item_ids,
            linked_video_source_bounds=linked_video_source_bounds,
        )
        if item_id and enforce_source_bounds:
            _validate_duration_source_bounds(
                item_id=str(item_id),
                name=result_target.name,
                start=result_target.start,
                current_duration=result_target.duration,
                requested_duration=int(new_duration),
                live_source_bounds=item_id_live_bounds,
                live_lookup_error=item_id_live_error,
            )
        updated.update(
            {
                "track_type": result_target.track_type,
                "track_index": result_target.track_index,
                "selector": asdict(result_target),
                "readback_name_candidates": sorted(
                    {
                        str(value)
                        for value in (updated.get("name"), result_target.name, *result_target.aliases)
                        if str(value or "").strip()
                    }
                ),
            }
        )
        linked_video_items: list[dict[str, Any]] = []
        for linked_update in updated.get("linked_video_updates", []):
            linked_update = dict(linked_update)
            linked_update.update(
                {
                    "track_type": "video",
                    "track_index": _track_index_from_db_row(
                        cursor,
                        row=_fetch_db_row_by_item_id(
                            cursor,
                            item_id=str(linked_update.get("item_id") or ""),
                            timeline_name=target_timeline,
                            track_type="video",
                            track_index=None,
                        ),
                        timeline_name=target_timeline,
                        track_type="video",
                    ),
                    "selector": {
                        "item_id": linked_update.get("item_id"),
                        "track_type": "video",
                        "name": linked_update.get("name"),
                        "start": linked_update.get("old_start"),
                        "duration": linked_update.get("old_duration"),
                        "end": linked_update.get("old_end"),
                    },
                    "readback_name_candidates": sorted({str(linked_update.get("name") or "")} - {""}),
                }
            )
            linked_video_items.append(linked_update)
        result = {
            "action": "timeline.items.set_duration",
            "timeline_name": target_timeline,
            "requested": requested,
            "allow_overlap": bool(allow_overlap),
            "updated_items": [updated, *linked_video_items],
            "linked_video_included": bool(linked_video_items),
            "native_link_identity": edit_identity,
        }
        if protected_state_before is not None:
            result["protected_state_before"] = protected_state_before
        return result

    result = db_session.execute_sqlite_disk_db_mutation(
        conn,
        context="DB-backed timeline item duration set",
        writer=_writer,
        verifier=_verify_tail_trim_readback,
        pre_close_validator=(
            fairlight_edit_pre_close_validator(
                target=live_target,
                plan=edit_identity,
                track_targets=fairlight_lock_targets,
                intended_timeline=fairlight_timeline_identity,
            )
            if edit_identity is not None
            and live_target is not None
            and fairlight_lock_targets is not None
            and fairlight_timeline_identity is not None
            else None
        ),
        allow_project_name_inference=True,
        require_verified=True,
    )
    verification = result.get("verification") if isinstance(result, dict) else None
    if isinstance(verification, dict) and verification.get("status") != "verified":
        raise APICallFailed(
            "Timeline item duration DB write did not verify after DaVinci Resolve reopened the project.",
            details={"mutation": result, "verification": verification},
        )
    return result


def set_timeline_item_durations(
    conn: Any,
    entries: list[dict[str, Any]],
    *,
    timeline_name: str | None = None,
    allow_overlap: bool = False,
    enforce_source_bounds: bool = True,
) -> dict[str, Any]:
    """Set multiple timeline item durations/ends in one Disk Project.db mutation."""
    if not entries:
        raise ValidationError(
            "Timeline item duration batch requires at least one entry.",
            details={"entry_count": 0},
            recoverability="not_applicable",
        )

    first_entry_timeline = None
    for entry in entries:
        if isinstance(entry, dict):
            first_entry_timeline = entry.get("timeline_name") or entry.get("timeline")
            if first_entry_timeline:
                break
    requested_timeline_name = str(timeline_name or first_entry_timeline or "").strip() or None
    if requested_timeline_name:
        timeline_ops.switch_timeline(conn, name=requested_timeline_name)
    target_timeline = _timeline_name(conn)

    prepared: list[dict[str, Any]] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ValidationError(
                "Timeline item duration batch entries must be JSON objects.",
                details={"index": index, "entry": entry},
                recoverability="not_applicable",
            )
        entry_timeline = str(entry.get("timeline_name") or entry.get("timeline") or "").strip() or None
        if entry_timeline and target_timeline and entry_timeline != target_timeline:
            raise ValidationError(
                "Timeline item duration batch supports one timeline per batch.",
                details={"index": index, "entry_timeline": entry_timeline, "batch_timeline": target_timeline},
                recoverability="not_applicable",
            )

        normalized_track_type = _normalize_selector_track_type(str(entry.get("track_type") or "video"))
        normalized_track_index = timeline_ops.validate_timeline_track_index(entry.get("track_index", entry.get("track", 1)))
        item_id = entry.get("item_id")
        start_frame = entry.get("start_frame")
        current_end_frame = entry.get("current_end_frame", entry.get("current_end"))
        name = entry.get("name")
        duration = entry.get("duration")
        target_end_frame = entry.get("target_end_frame", entry.get("end_frame"))
        target_start_frame = entry.get("target_start_frame", entry.get("to_start_frame"))
        if bool(duration) == bool(target_end_frame):
            raise ValidationError(
                "Each duration batch entry must provide exactly one of duration or target_end_frame/end_frame.",
                details={"index": index, "duration": duration, "target_end_frame": target_end_frame},
                recoverability="not_applicable",
            )

        entry_allow_overlap = bool(entry["allow_overlap"]) if "allow_overlap" in entry else bool(allow_overlap)
        if "enforce_source_bounds" in entry:
            entry_enforce_source_bounds = bool(entry["enforce_source_bounds"])
        elif "no_source_bounds" in entry:
            entry_enforce_source_bounds = not bool(entry["no_source_bounds"])
        else:
            entry_enforce_source_bounds = bool(enforce_source_bounds)

        live_target: TimelineItemDurationTarget | None = None
        if not item_id:
            live_target, live_item = _select_live_item(
                conn,
                track_type=normalized_track_type,
                track_index=normalized_track_index,
                start_ref=str(start_frame) if start_frame is not None else None,
                current_end_ref=str(current_end_frame) if current_end_frame is not None else None,
                name=str(name) if name is not None else None,
            )
            new_duration, new_end, requested = _resolve_new_duration(
                conn,
                item_start=live_target.start,
                duration=str(duration) if duration is not None else None,
                target_end_frame=str(target_end_frame) if target_end_frame is not None else None,
            )
            new_start = int(live_target.start)
            if target_start_frame is not None:
                new_start = _target_record_frame(conn, str(target_start_frame))
                requested = {**requested, "target_start_frame": str(target_start_frame), "target_start_frames": int(new_start)}
                if target_end_frame is not None:
                    new_end = _target_record_frame(conn, str(target_end_frame))
                    new_duration = int(new_end) - int(new_start)
                    if new_duration <= 0:
                        raise ValidationError(
                            "Timeline item duration batch target_end_frame must be after target_start_frame.",
                            details={"index": index, "target_start_frame": target_start_frame, "target_end_frame": target_end_frame},
                            recoverability="not_applicable",
                        )
                    requested = {**requested, "target_end_frames": int(new_end)}
                else:
                    new_end = int(new_start) + int(new_duration)
            right_offset = _live_item_right_offset(live_item)
            finite_source_bounds, media_type = _uses_finite_source_bounds(live_item)
            if (
                entry_enforce_source_bounds
                and finite_source_bounds
                and right_offset is not None
                and new_duration > live_target.duration + right_offset
            ):
                _validate_duration_source_bounds(
                    name=live_target.name,
                    start=live_target.start,
                    current_duration=live_target.duration,
                    requested_duration=new_duration,
                    live_source_bounds={"right_offset": right_offset, "media_type": media_type},
                    live_lookup_error=None,
                    batch_index=index,
                )
        else:
            if start_frame or current_end_frame or name:
                raise ValidationError(
                    "item_id is mutually exclusive with start_frame, current_end_frame, and name.",
                    details={"index": index, "item_id": item_id, "start_frame": start_frame, "current_end_frame": current_end_frame, "name": name},
                    recoverability="not_applicable",
                )
            new_duration = -1
            new_end = -1
            new_start = -1
            requested = {"mode": "pending_db_row"}

        item_id_live_bounds = None
        item_id_live_error = None
        if item_id and entry_enforce_source_bounds:
            try:
                preflight_target = _read_item_id_target_before_db_close(
                    conn,
                    item_id=str(item_id),
                    timeline_name=target_timeline,
                    track_type=normalized_track_type,
                )
            except Exception as exc:
                item_id_live_error = exc
            else:
                item_id_live_bounds, item_id_live_error = _item_id_live_source_bounds_for_duration(conn, target=preflight_target)
                preflight_start = int(preflight_target.start)
                if target_start_frame is not None:
                    preflight_start = _target_record_frame(conn, str(target_start_frame))
                if target_start_frame is not None and target_end_frame is not None:
                    preflight_end = _target_record_frame(conn, str(target_end_frame))
                    preflight_duration = int(preflight_end) - int(preflight_start)
                    if preflight_duration <= 0:
                        raise ValidationError(
                            "Timeline item duration batch target_end_frame must be after target_start_frame.",
                            details={"index": index, "target_start_frame": target_start_frame, "target_end_frame": target_end_frame},
                            recoverability="not_applicable",
                        )
                else:
                    preflight_duration, _preflight_end, _preflight_requested = _resolve_new_duration(
                        conn,
                        item_start=preflight_start,
                        duration=str(duration) if duration is not None else None,
                        target_end_frame=str(target_end_frame) if target_end_frame is not None else None,
                    )
                _validate_duration_source_bounds(
                    item_id=str(item_id),
                    name=preflight_target.name,
                    start=preflight_target.start,
                    current_duration=preflight_target.duration,
                    requested_duration=int(preflight_duration),
                    live_source_bounds=item_id_live_bounds,
                    live_lookup_error=item_id_live_error,
                    batch_index=index,
                )

        prepared.append(
            {
                "index": index,
                "item_id": str(item_id) if item_id is not None else None,
                "track_type": normalized_track_type,
                "track_index": normalized_track_index,
                "start_frame": str(start_frame) if start_frame is not None else None,
                "current_end_frame": str(current_end_frame) if current_end_frame is not None else None,
                "name": str(name) if name is not None else None,
                "duration": str(duration) if duration is not None else None,
                "target_end_frame": str(target_end_frame) if target_end_frame is not None else None,
                "target_start_frame": str(target_start_frame) if target_start_frame is not None else None,
                "allow_overlap": entry_allow_overlap,
                "enforce_source_bounds": entry_enforce_source_bounds,
                "live_target": live_target,
                "new_start": new_start,
                "new_duration": new_duration,
                "new_end": new_end,
                "requested": requested,
                "item_id_live_bounds": item_id_live_bounds,
                "item_id_live_error": item_id_live_error,
            }
        )

    def _writer(_connection: sqlite3.Connection, cursor: sqlite3.Cursor, _session: db_session.DiskDbMutationSession) -> dict[str, Any]:
        updated_items: list[dict[str, Any]] = []
        requested_items: list[dict[str, Any]] = []
        for prepared_entry in prepared:
            item_id = prepared_entry["item_id"]
            if item_id:
                row = _fetch_db_row_by_item_id(
                    cursor,
                    item_id=str(item_id),
                    timeline_name=target_timeline,
                    track_type=prepared_entry["track_type"],
                    track_index=None,
                )
                row_start = _int_cell(row.get("Start"), field="Start")
                new_duration, new_end, requested = _resolve_new_duration(
                    conn,
                    item_start=row_start,
                    duration=prepared_entry["duration"],
                    target_end_frame=prepared_entry["target_end_frame"],
                )
                new_start = row_start
                if prepared_entry.get("target_start_frame") is not None:
                    new_start = _target_record_frame(conn, str(prepared_entry["target_start_frame"]))
                    requested = {**requested, "target_start_frame": str(prepared_entry["target_start_frame"]), "target_start_frames": int(new_start)}
                    if prepared_entry.get("target_end_frame") is not None:
                        new_end = _target_record_frame(conn, str(prepared_entry["target_end_frame"]))
                        new_duration = int(new_end) - int(new_start)
                        if new_duration <= 0:
                            raise ValidationError(
                                "Timeline item duration batch target_end_frame must be after target_start_frame.",
                                details={
                                    "index": prepared_entry["index"],
                                    "target_start_frame": prepared_entry["target_start_frame"],
                                    "target_end_frame": prepared_entry["target_end_frame"],
                                },
                                recoverability="not_applicable",
                            )
                        requested = {**requested, "target_end_frames": int(new_end)}
                    else:
                        new_end = int(new_start) + int(new_duration)
                result_target = _target_from_db_row(
                    cursor,
                    item_id=str(item_id),
                    row=row,
                    timeline_name=target_timeline,
                    fallback_track_type=prepared_entry["track_type"],
                )
            else:
                result_target = prepared_entry["live_target"]
                assert result_target is not None
                row = _fetch_db_row_for_live_target(cursor, target=result_target, timeline_name=target_timeline or "")
                new_start = int(prepared_entry["new_start"])
                new_duration = int(prepared_entry["new_duration"])
                new_end = int(prepared_entry["new_end"])
                requested = prepared_entry["requested"]

            updated = _apply_duration_update(
                cursor,
                target_row=row,
                new_duration=int(new_duration),
                new_end=int(new_end),
                new_start=int(new_start),
                allow_overlap=bool(prepared_entry["allow_overlap"]),
                fps=conn.fps,
            )
            if item_id and bool(prepared_entry["enforce_source_bounds"]):
                _validate_duration_source_bounds(
                    item_id=str(item_id),
                    name=result_target.name,
                    start=result_target.start,
                    current_duration=result_target.duration,
                    requested_duration=int(new_duration),
                    live_source_bounds=prepared_entry["item_id_live_bounds"],
                    live_lookup_error=prepared_entry["item_id_live_error"],
                    batch_index=int(prepared_entry["index"]),
                )
            updated.update(
                {
                    "batch_index": prepared_entry["index"],
                    "track_type": result_target.track_type,
                    "track_index": result_target.track_index,
                    "selector": asdict(result_target),
                    "readback_name_candidates": sorted(
                        {
                            str(value)
                            for value in (updated.get("name"), result_target.name, *result_target.aliases)
                            if str(value or "").strip()
                        }
                    ),
                }
            )
            updated_items.append(updated)
            requested_items.append({"index": prepared_entry["index"], **dict(requested)})

        return {
            "action": "timeline.items.set_duration.batch",
            "timeline_name": target_timeline,
            "requested": requested_items,
            "allow_overlap": bool(allow_overlap),
            "updated_items": updated_items,
            "requested_count": len(prepared),
        }

    result = db_session.execute_sqlite_disk_db_mutation(
        conn,
        context="DB-backed timeline item duration batch set",
        writer=_writer,
        verifier=_verify_duration_readback,
        allow_project_name_inference=True,
    )
    verification = result.get("verification") if isinstance(result, dict) else None
    if isinstance(verification, dict) and verification.get("status") != "verified":
        raise APICallFailed(
            "Timeline item duration batch DB write did not verify after DaVinci Resolve reopened the project.",
            details={"mutation": result, "verification": verification},
        )
    return result
