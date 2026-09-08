"""Idempotent timeline layer operations."""

from __future__ import annotations

from pathlib import Path
import time
from typing import Any

from ..connection import ResolveConnection
from ..errors import APICallFailed, TimelineConflict, ValidationError
from . import db_session, media_pool, timeline_item_duration_db, timeline_ops
from .timeline_item_mutation import set_timeline_item_end_or_duration, timeline_item_range

MATCH_NAME_VALUES = ("exact", "contains")


def _ensure_video_track(conn: Any, track: int) -> dict[str, Any]:
    normalized_track = timeline_ops.validate_timeline_track_index(track)
    timeline = conn.timeline
    try:
        before = int(timeline.GetTrackCount("video") or 0)
    except Exception:
        before = 0
    added = 0
    count = before
    while count < normalized_track:
        result = timeline.AddTrack("video")
        if result is False:
            raise APICallFailed(
                "Failed to add required video track.",
                details={"track": normalized_track, "current_video_tracks": count, "api_call": "Timeline.AddTrack"},
            )
        added += 1
        try:
            count = int(timeline.GetTrackCount("video") or 0)
        except Exception:
            count += 1
        if added > normalized_track + 5:
            raise APICallFailed(
                "Unable to verify required video track after adding tracks.",
                details={"track": normalized_track, "current_video_tracks": count},
            )
    return {"requested_track": normalized_track, "pre_video_tracks": before, "final_video_tracks": count, "added_tracks": added}


def _call_string_method(obj: Any, method_name: str) -> str | None:
    method = getattr(obj, method_name, None)
    if not callable(method):
        return None
    try:
        value = method()
    except Exception:
        return None
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _clip_property(item: Any, key: str) -> str | None:
    getter = getattr(item, "GetClipProperty", None)
    if not callable(getter):
        return None
    try:
        value = getter(key)
    except Exception:
        return None
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _media_pool_item(item: Any) -> Any | None:
    getter = getattr(item, "GetMediaPoolItem", None)
    if not callable(getter):
        return None
    try:
        return getter()
    except Exception:
        return None


def _media_id(obj: Any, props: dict[str, Any] | None = None) -> str | None:
    for method_name in ("GetMediaId", "GetUniqueId"):
        value = _call_string_method(obj, method_name)
        if value:
            return value
    for key in ("MediaId", "Media ID", "media_id", "Id", "ID"):
        value = (props or {}).get(key)
        if value:
            return str(value)
    return None


def _item_media_signals(item: Any) -> dict[str, Any]:
    props = {}
    prop_getter = getattr(item, "GetClipProperty", None)
    if callable(prop_getter):
        try:
            raw_props = prop_getter()
            if isinstance(raw_props, dict):
                props = raw_props
        except Exception:
            props = {}
    mpi = _media_pool_item(item)
    file_name = props.get("File Name") or _clip_property(item, "File Name")
    file_path = props.get("File Path") or _clip_property(item, "File Path")
    signals = {
        "timeline_item_name": _call_string_method(item, "GetName"),
        "media_pool_item_name": _call_string_method(mpi, "GetName") if mpi is not None else None,
        "file_name": str(file_name) if file_name else None,
        "file_path": str(file_path) if file_path else None,
        "media_id": _media_id(mpi, props) if mpi is not None else _media_id(item, props),
    }
    return {key: value for key, value in signals.items() if value}


def _string_matches(candidate: str | None, needle: str, match_name: str) -> bool:
    if not candidate:
        return False
    if match_name == "contains":
        return needle in candidate
    return candidate == needle


def _item_matches_media(item: Any, media: str, match_name: str) -> bool:
    signals = _item_media_signals(item)
    needles = {str(media)}
    path = Path(str(media)).expanduser()
    needles.add(path.name)
    needles.add(str(path))
    for value in signals.values():
        text = str(value)
        if any(_string_matches(text, needle, match_name) for needle in needles if needle):
            return True
        if signals.get("file_path") and any(_string_matches(Path(text).name, needle, match_name) for needle in needles if needle):
            return True
    return False


def _summary(item: Any) -> dict[str, Any]:
    data = {"name": _call_string_method(item, "GetName")}
    data.update(timeline_item_range(item))
    return data


def _ranges_overlap(start_a: int, end_a: int, start_b: int, end_b: int) -> bool:
    return start_a < end_b and end_a > start_b


def _gap_frames(start_a: int, end_a: int, start_b: int, end_b: int) -> int:
    if _ranges_overlap(start_a, end_a, start_b, end_b):
        return 0
    if end_a <= start_b:
        return start_b - end_a
    return start_a - end_b


def _resolve_media_entry(conn: Any, media: str) -> dict[str, Any]:
    raw = str(media).strip()
    if not raw:
        raise ValidationError("--media must not be empty.", details={"media": media}, recoverability="not_applicable")
    candidates: list[dict[str, Any]] = [{"name": raw}, {"media_id": raw}]
    path = Path(raw).expanduser()
    if path.is_absolute() or "/" in raw or "\\" in raw:
        candidates.insert(0, {"path": raw})
    last_error: Exception | None = None
    for entry in candidates:
        try:
            return media_pool.resolve_append_media_entry(conn, entry)
        except APICallFailed as exc:
            last_error = exc
            continue
        except ValidationError:
            raise
    raise APICallFailed(
        "Timeline layer media was not found in the Media Pool.",
        details={"media": media, "mode": "failed_media_not_found", "last_error": str(last_error) if last_error else None},
        recoverability="manual",
    )


def _target_payload(*, media: str, track: int, start_frame: int, duration_frames: int) -> dict[str, Any]:
    return {
        "kind": "timeline_media_layer",
        "media": media,
        "track_type": "video",
        "track_index": track,
        "range": {"start": start_frame, "end": start_frame + duration_frames},
    }


def _range_covers_target(range_data: dict[str, Any], *, target_start: int, target_end: int) -> bool:
    start = range_data.get("start")
    end = range_data.get("end")
    return start is not None and end is not None and int(start) <= int(target_start) and int(end) >= int(target_end)


def _db_set_item_duration(
    conn: Any,
    *,
    timeline_name: str | None,
    track: int,
    item_start: int,
    current_end: int | None,
    name: str | None,
    duration_frames: int,
) -> dict[str, Any]:
    return timeline_item_duration_db.set_timeline_item_duration(
        conn,
        timeline_name=timeline_name,
        track_type="video",
        track_index=int(track),
        start_frame=f"{int(item_start)}f",
        current_end_frame=f"{int(current_end)}f" if current_end is not None else None,
        name=name,
        duration=f"{int(duration_frames)}f",
        allow_overlap=False,
        enforce_source_bounds=False,
    )


def _duration_result_from_db(
    conn: Any,
    *,
    timeline_name: str | None,
    track: int,
    item_start: int,
    current_end: int | None,
    name: str | None,
    duration_frames: int,
) -> dict[str, Any]:
    db_result = _db_set_item_duration(
        conn,
        timeline_name=timeline_name,
        track=track,
        item_start=item_start,
        current_end=current_end,
        name=name,
        duration_frames=duration_frames,
    )
    summary = _updated_item_summary_from_db(db_result, default_name=name)
    return {
        "applied": True,
        "engine": "db_workaround",
        "route": "timeline.items.set_duration",
        "requested_duration_frames": int(duration_frames),
        "db_result": db_result,
        "readback": {"start": summary.get("new_start"), "end": summary.get("new_end")} if summary else None,
        "selected_item": summary,
    }


def _ensure_item_duration(
    conn: Any,
    item: Any,
    *,
    timeline_name: str | None,
    track: int,
    item_start: int,
    current_end: int | None,
    name: str | None,
    duration_frames: int,
    target_start: int,
    target_end: int,
    dry_run: bool,
) -> dict[str, Any]:
    if dry_run:
        return {
            "applied": False,
            "dry_run": True,
            "engine": "planned",
            "route": "planned_duration_update",
            "requested_duration_frames": int(duration_frames),
            "readback": {"start": int(item_start), "end": int(item_start) + int(duration_frames)},
        }

    api_result = set_timeline_item_end_or_duration(
        item,
        end_frame=int(item_start) + int(duration_frames),
        duration_frames=int(duration_frames),
        start_frame=int(item_start),
    )
    api_readback = timeline_item_range(item)
    if bool(api_result.get("duration_applied")) and _range_covers_target(api_readback, target_start=target_start, target_end=target_end):
        return {
            "applied": True,
            "engine": "api_native",
            "route": api_result.get("duration_property") or "TimelineItem duration API",
            "requested_duration_frames": int(duration_frames),
            "api_result": api_result,
            "readback": api_readback,
        }

    db_result = _duration_result_from_db(
        conn,
        timeline_name=timeline_name,
        track=track,
        item_start=item_start,
        current_end=current_end,
        name=name,
        duration_frames=duration_frames,
    )
    db_result["api_result"] = api_result
    return db_result


def _flush_project_after_timeline_append(conn: Any) -> dict[str, Any]:
    result: dict[str, Any] = {"attempted": False, "api_result": None, "wait_seconds": 0.5}
    project_manager = getattr(conn, "project_manager", None)
    save_fn = getattr(project_manager, "SaveProject", None) if project_manager is not None else None
    if callable(save_fn):
        result["attempted"] = True
        try:
            result["api_result"] = save_fn()
        except Exception as exc:
            result["error"] = str(exc)
    time.sleep(0.5)
    return result


def _timeline_name(conn: Any, requested: str | None = None) -> str | None:
    if requested:
        return requested
    try:
        return conn.timeline.GetName()
    except Exception:
        return None


def _fresh_connection_after_append(*, timeline_name: str | None) -> tuple[Any, dict[str, Any]]:
    steps: list[str] = []
    ResolveConnection.reset()
    fresh_conn = ResolveConnection.get()
    fresh_conn.connect()
    steps.append("connect")
    fresh_conn.refresh()
    if timeline_name:
        if not db_session._activate_timeline_by_name(fresh_conn, timeline_name):
            raise APICallFailed(
                "DaVinci Resolve could not activate the timeline after timeline layer append.",
                details={"timeline_name": timeline_name},
            )
        steps.append("activate_timeline")
    return fresh_conn, {"timeline_name": timeline_name, "steps": steps}


def _updated_item_summary_from_db(result: dict[str, Any], *, default_name: str | None) -> dict[str, Any] | None:
    updated_items = result.get("updated_items") if isinstance(result, dict) else None
    if not isinstance(updated_items, list) or not updated_items:
        return None
    item = updated_items[0]
    return {
        "name": item.get("name") or default_name,
        "new_start": item.get("new_start"),
        "new_end": item.get("new_end"),
    }


def ensure_media_layer(
    conn: Any,
    media: str,
    track: int,
    start_frame: int,
    duration_frames: int,
    extend_gap_frames: int = 0,
    *,
    timeline: str | None = None,
    match_name: str = "exact",
    allow_insert: bool = True,
    allow_extend: bool = True,
    dry_run: bool = False,
) -> dict[str, Any]:
    normalized_track = timeline_ops.validate_timeline_track_index(track)
    normalized_match = str(match_name or "exact").strip().lower()
    if normalized_match not in MATCH_NAME_VALUES:
        raise ValidationError(
            "--match-name must be exact or contains.",
            details={"match_name": match_name, "allowed": list(MATCH_NAME_VALUES)},
            recoverability="not_applicable",
        )
    if int(duration_frames) <= 0:
        raise ValidationError("--duration must be greater than zero.", details={"duration": duration_frames}, recoverability="not_applicable")
    if int(start_frame) < 0:
        raise ValidationError("--start-frame must not be negative.", details={"start_frame": start_frame}, recoverability="not_applicable")
    if int(extend_gap_frames) < 0:
        raise ValidationError("--extend-gap must not be negative.", details={"extend_gap": extend_gap_frames}, recoverability="not_applicable")

    if timeline:
        timeline_ops.switch_timeline(conn, name=timeline)
    track_preflight = _ensure_video_track(conn, normalized_track) if not dry_run else {"requested_track": normalized_track, "dry_run": True}
    target_start = int(start_frame)
    target_end = target_start + int(duration_frames)
    target = _target_payload(media=media, track=normalized_track, start_frame=target_start, duration_frames=int(duration_frames))

    try:
        items = conn.timeline.GetItemListInTrack("video", normalized_track) or []
    except Exception as exc:
        raise APICallFailed(
            "Failed to read timeline items for target video track.",
            details={"track": normalized_track, "api_call": "Timeline.GetItemListInTrack", "error": str(exc)},
        ) from exc

    matching: list[tuple[Any, dict[str, Any]]] = []
    conflicts: list[dict[str, Any]] = []
    for item in items:
        item_range = timeline_item_range(item)
        item_start = item_range["start"]
        item_end = item_range["end"]
        if item_start is None or item_end is None:
            continue
        is_match = _item_matches_media(item, media, normalized_match)
        if is_match:
            matching.append((item, {"start": item_start, "end": item_end, "duration": item_range.get("duration")}))
        elif _ranges_overlap(int(item_start), int(item_end), target_start, target_end):
            conflicts.append(_summary(item))

    if conflicts:
        conflict = conflicts[0]
        raise TimelineConflict(
            "Target timeline range already contains a different clip.",
            details={
                "mode": "failed_conflict",
                "track": normalized_track,
                "conflicting_item_name": conflict.get("name"),
                "start": conflict.get("start"),
                "end": conflict.get("end"),
                "target_range": {"start": target_start, "end": target_end},
            },
        )

    covering = [
        (item, info)
        for item, info in matching
        if int(info["start"]) <= target_start and int(info["end"]) >= target_end
    ]
    if covering:
        item, info = covering[0]
        return {
            "action": "timeline.layer.ensure_media",
            "changed": False,
            "mode": "noop",
            "media": media,
            "track_type": "video",
            "track_index": normalized_track,
            "target": target,
            "target_range": {"start": target_start, "end": target_end},
            "selected_item": {
                "name": _call_string_method(item, "GetName"),
                "previous_start": info["start"],
                "previous_end": info["end"],
                "new_start": info["start"],
                "new_end": info["end"],
            },
            "verification": {"covers_target_range": True},
            "track_preflight": track_preflight,
        }

    extendable = [
        (item, info)
        for item, info in matching
        if _gap_frames(int(info["start"]), int(info["end"]), target_start, target_end) <= int(extend_gap_frames)
    ]
    if extendable:
        if not allow_extend:
            raise ValidationError(
                "A matching timeline item is close enough to extend, but extension is disabled.",
                details={"mode": "failed_duration_update", "target_range": {"start": target_start, "end": target_end}, "track": normalized_track},
            )
        item, info = min(extendable, key=lambda pair: _gap_frames(int(pair[1]["start"]), int(pair[1]["end"]), target_start, target_end))
        selected_name = _call_string_method(item, "GetName") or _item_media_signals(item).get("media_pool_item_name") or media
        new_start = min(int(info["start"]), target_start)
        new_end = max(int(info["end"]), target_end)
        new_duration = new_end - new_start
        if new_start != int(info["start"]):
            raise APICallFailed(
                "Cannot extend timeline item earlier than its current start frame.",
                details={
                    "mode": "failed_duration_update",
                    "track": normalized_track,
                    "target_range": {"start": target_start, "end": target_end},
                    "selected_item": _summary(item),
                    "requested_start": new_start,
                },
                recoverability="manual",
            )
        duration_result = _ensure_item_duration(
            conn,
            item,
            timeline_name=timeline,
            track=normalized_track,
            item_start=int(info["start"]),
            current_end=int(info["end"]),
            name=str(selected_name),
            duration_frames=new_duration,
            target_start=target_start,
            target_end=target_end,
            dry_run=dry_run,
        )
        covers = bool(dry_run) or bool(duration_result.get("applied"))
        if not covers:
            raise APICallFailed(
                "Failed to extend timeline item to cover target range.",
                details={
                    "mode": "failed_duration_update",
                    "track": normalized_track,
                    "target_range": {"start": target_start, "end": target_end},
                    "selected_item": _summary(item),
                    "duration_result": duration_result,
                },
                recoverability="manual",
            )
        readback = duration_result.get("readback") or (timeline_item_range(item) if not dry_run else {"start": new_start, "end": new_end})
        return {
            "action": "timeline.layer.ensure_media",
            "changed": not dry_run,
            "mode": "extended",
            "media": media,
            "track_type": "video",
            "track_index": normalized_track,
            "target": target,
            "target_range": {"start": target_start, "end": target_end},
            "selected_item": {
                "name": selected_name,
                "previous_start": info["start"],
                "previous_end": info["end"],
                "new_start": readback.get("start"),
                "new_end": readback.get("end"),
            },
            "verification": {"covers_target_range": bool(readback.get("start", new_start) <= target_start and readback.get("end", new_end) >= target_end)},
            "duration_result": duration_result,
            "track_preflight": track_preflight,
            "dry_run": bool(dry_run),
        }

    if not allow_insert:
        raise ValidationError(
            "No matching media layer exists and insertion is disabled.",
            details={"mode": "failed_media_not_found", "target_range": {"start": target_start, "end": target_end}, "track": normalized_track},
        )

    resolved = _resolve_media_entry(conn, media)
    if dry_run:
        item_summary = {"name": resolved.get("name") or media, "previous_start": None, "previous_end": None, "new_start": target_start, "new_end": target_end}
        append_details = {"dry_run": True, "resolved": {key: value for key, value in resolved.items() if key != "clip"}}
    else:
        clip_info = {
            "mediaPoolItem": resolved["clip"],
            "startFrame": 0,
            "endFrame": int(duration_frames),
            "recordFrame": target_start,
            "trackIndex": normalized_track,
            "trackType": "video",
            "mediaType": 1,
        }
        append_result = conn.media_pool.AppendToTimeline([clip_info])
        if not append_result:
            raise APICallFailed(
                "Failed to append timeline layer media.",
                details={"media": media, "track": normalized_track, "target_range": {"start": target_start, "end": target_end}},
            )
        appended_items = append_result if isinstance(append_result, list) else [append_result]
        appended_item = appended_items[0] if appended_items else None
        appended_range = timeline_item_range(appended_item) if appended_item is not None else {}
        appended = {"name": _call_string_method(appended_item, "GetName") if appended_item is not None else resolved.get("name"), **appended_range}
        append_details = {
            "clip": resolved.get("name") or media,
            "folder": resolved.get("folder"),
            "source_path": resolved.get("source_path"),
            "track_type": "video",
            "track_index": normalized_track,
            "record_frame": target_start,
            "clip_info": {**clip_info, "mediaPoolItem": resolved.get("name") or media},
            "append_result_count": len(appended_items),
            "timeline_items": [appended],
        }
        append_details["flush"] = _flush_project_after_timeline_append(conn)
        item_summary = {
            "name": appended.get("name") or resolved.get("name") or media,
            "previous_start": None,
            "previous_end": None,
            "new_start": appended.get("start"),
            "new_end": appended.get("end"),
        }

    covers = bool(item_summary.get("new_start", target_start) <= target_start and item_summary.get("new_end", target_end) >= target_end)
    if not covers and not dry_run:
        fresh_conn, reconnect_details = _fresh_connection_after_append(timeline_name=_timeline_name(conn, timeline))
        append_details["duration_connection"] = reconnect_details
        duration_result = _duration_result_from_db(
            fresh_conn,
            timeline_name=timeline,
            track=normalized_track,
            item_start=int(item_summary.get("new_start") or target_start),
            current_end=int(item_summary["new_end"]) if item_summary.get("new_end") is not None else None,
            name=str(item_summary.get("name") or resolved.get("name") or media),
            duration_frames=int(duration_frames),
        )
        append_details["duration_result"] = duration_result
        duration_summary = duration_result.get("selected_item")
        if isinstance(duration_summary, dict):
            item_summary.update({key: value for key, value in duration_summary.items() if value is not None})
        covers = bool(item_summary.get("new_start", target_start) <= target_start and item_summary.get("new_end", target_end) >= target_end)
    if not covers and not dry_run:
        raise APICallFailed(
            "Inserted timeline layer media does not cover target range.",
            details={
                "mode": "failed_duration_update",
                "track": normalized_track,
                "target_range": {"start": target_start, "end": target_end},
                "selected_item": item_summary,
                "append": append_details,
            },
            recoverability="manual",
        )
    return {
        "action": "timeline.layer.ensure_media",
        "changed": not dry_run,
        "mode": "inserted",
        "media": media,
        "track_type": "video",
        "track_index": normalized_track,
        "target": target,
        "target_range": {"start": target_start, "end": target_end},
        "selected_item": item_summary,
        "verification": {"covers_target_range": covers},
        "append": append_details,
        "track_preflight": track_preflight,
        "dry_run": bool(dry_run),
    }
