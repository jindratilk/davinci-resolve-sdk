"""Timeline materialization helpers for native multicam switch flows."""

from __future__ import annotations

import sqlite3
import time
from dataclasses import replace
from typing import Any

from ...errors import APICallFailed, ValidationError
from ...multicam_support import support_tier_for_angle_count
from ...utils.timecode import timecode_to_seconds
from .. import media_pool, multicam_switch_families, native_multicam_db, timeline_ops
from .._native_multicam_db.seed_timeline import resolve_live_multicam_media_pool_item


def _resolve_current_project_db_path(conn, *, ops_module) -> str:
    project_name = ops_module._require_live_project_name(conn, context="native multicam switching")
    resolution = native_multicam_db.resolve_disk_project_db_path(project_name=project_name)
    return str(resolution["project_db_path"])


def _timeline_track_items(conn, track_type: str) -> list[Any]:
    getter = getattr(conn.timeline, "GetItemListInTrack", None)
    if not callable(getter):
        return []
    try:
        count = int(conn.timeline.GetTrackCount(track_type) or 0)
    except Exception:
        count = 0
    items: list[Any] = []
    for index in range(1, count + 1):
        items.extend(getter(track_type, index) or [])
    return items


def _snapshot_untouched_timeline_items(conn, *, switch_scope: str) -> list[dict[str, Any]]:
    normalized_scope = _normalize_switch_scope(switch_scope)
    changed_types = {"video", "audio"} if normalized_scope == "linked" else {normalized_scope}
    timeline = getattr(conn, "timeline", None)
    count_getter = getattr(timeline, "GetTrackCount", None)
    item_getter = getattr(timeline, "GetItemListInTrack", None)
    if not callable(count_getter) or not callable(item_getter):
        raise APICallFailed(
            "Cannot verify preserved timeline item positions because timeline track readback is unavailable.",
            details={"switch_scope": normalized_scope},
        )
    rows: list[dict[str, Any]] = []
    for track_type in ("video", "audio", "subtitle"):
        if track_type in changed_types:
            continue
        try:
            raw_track_count = count_getter(track_type)
            if isinstance(raw_track_count, bool) or raw_track_count is None:
                raise TypeError("track count is not numeric")
            track_count = int(raw_track_count)
            if track_count < 0:
                raise ValueError("track count is negative")
        except Exception as exc:
            raise APICallFailed(
                "Cannot verify preserved timeline item positions because track-count readback failed.",
                details={"switch_scope": normalized_scope, "track_type": track_type},
            ) from exc
        for track_index in range(1, track_count + 1):
            try:
                track_items = item_getter(track_type, track_index)
            except Exception as exc:
                raise APICallFailed(
                    "Cannot verify preserved timeline item positions because track-item readback failed.",
                    details={"switch_scope": normalized_scope, "track_type": track_type, "track_index": track_index},
                ) from exc
            if not isinstance(track_items, (list, tuple)):
                raise APICallFailed(
                    "Cannot verify preserved timeline item positions because track-item readback was malformed.",
                    details={"switch_scope": normalized_scope, "track_type": track_type, "track_index": track_index},
                )
            for item in track_items:
                item_id = timeline_ops.documented_sdk_unique_id(item)
                start_getter = getattr(item, "GetStart", None)
                end_getter = getattr(item, "GetEnd", None)
                if not item_id or not callable(start_getter) or not callable(end_getter):
                    raise APICallFailed(
                        "Cannot verify preserved timeline item positions for the scoped multicam switch.",
                        details={"switch_scope": normalized_scope, "track_type": track_type, "track_index": track_index},
                    )
                try:
                    row = {
                        "item_id": str(item_id),
                        "track_type": track_type,
                        "track_index": track_index,
                        "start": int(start_getter()),
                        "end": int(end_getter()),
                    }
                except Exception as exc:
                    raise APICallFailed(
                        "Cannot verify preserved timeline item positions because item timing readback failed.",
                        details={"switch_scope": normalized_scope, "track_type": track_type, "track_index": track_index, "item_id": str(item_id)},
                    ) from exc
                rows.append(row)
    if len({row["item_id"] for row in rows}) != len(rows):
        raise APICallFailed(
            "Cannot verify preserved timeline item positions because item identities were not unique.",
            details={"switch_scope": normalized_scope},
        )
    return sorted(rows, key=lambda row: row["item_id"])


def _normalize_switch_scope(value: str | None) -> str:
    normalized = str(value or "linked").strip().lower().replace("_", "-")
    aliases = {
        "both": "linked",
        "all": "linked",
        "video-only": "video",
        "audio-only": "audio",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized not in {"linked", "video", "audio"}:
        raise ValidationError(
            "Multicam switch scope must be linked, video, or audio.",
            details={"switch_scope": value, "supported": ["linked", "video", "audio"]},
        )
    return normalized


def _clear_active_timeline_items(conn, *, switch_scope: str = "linked") -> dict[str, int]:
    switch_scope = _normalize_switch_scope(switch_scope)
    track_types = ["video", "audio"] if switch_scope == "linked" else [switch_scope]
    items_by_type = {track_type: _timeline_track_items(conn, track_type) for track_type in track_types}
    items = [item for entries in items_by_type.values() for item in entries]
    if not items:
        return {"deleted_clip_count": 0, "deleted_video_clip_count": 0, "deleted_audio_clip_count": 0}

    deleter = getattr(conn.timeline, "DeleteClips", None)
    if not callable(deleter):
        raise APICallFailed(
            "DaVinci Resolve runtime does not expose DeleteClips for native multicam timeline rewriting.",
            details={"timeline_name": getattr(conn.timeline, "GetName", lambda: None)()},
        )

    deleted = deleter(items)
    if deleted is False:
        raise APICallFailed(
            "Failed to clear the active timeline before native multicam timeline rewriting.",
            details={"timeline_name": getattr(conn.timeline, "GetName", lambda: None)()},
        )
    return {
        "deleted_clip_count": len(items),
        "deleted_video_clip_count": len(items_by_type.get("video", [])),
        "deleted_audio_clip_count": len(items_by_type.get("audio", [])),
    }


def _activate_timeline_by_name(conn, timeline_name: str, timeline_native_id: str | None = None) -> Any:
    project = getattr(conn, "project", None)
    if project is None:
        raise APICallFailed("DaVinci Resolve project handle is not available when activating the target timeline.")
    count = int(project.GetTimelineCount() or 0)
    matches = []
    for index in range(1, count + 1):
        timeline = project.GetTimelineByIndex(index)
        if (timeline and timeline.GetName() == timeline_name
            and (timeline_native_id is None or timeline_ops.documented_sdk_unique_id(timeline) == timeline_native_id)):
            matches.append(timeline)
    if len(matches) == 1:
        setter = getattr(project, "SetCurrentTimeline", None)
        if callable(setter) and setter(matches[0]) is not False:
            conn.refresh()
            active = getattr(conn, "timeline", None)
            if active is None:
                current_getter = getattr(project, "GetCurrentTimeline", None)
                active = current_getter() if callable(current_getter) else getattr(project, "current_timeline", None)
            active_name = str(active.GetName() or "").strip() if active and hasattr(active, "GetName") else ""
            active_id = timeline_ops.documented_sdk_unique_id(active) if active is not None else None
            if active_name == timeline_name and (timeline_native_id is None or active_id == timeline_native_id):
                return active
    raise APICallFailed(
        "Failed to activate the target timeline after native multicam switch write.",
        details={"timeline_name": timeline_name, "reason": "timeline_activation_unverified"},
    )


def _capture_timeline_start_state(conn) -> dict[str, Any]:
    timeline = getattr(conn, "timeline", None)
    if timeline is None:
        return {"start_timecode": None, "start_frame": int(getattr(conn, "start_frame", 0) or 0)}
    start_timecode = None
    getter = getattr(timeline, "GetStartTimecode", None)
    if callable(getter):
        try:
            start_timecode = str(getter() or "").strip() or None
        except Exception:
            start_timecode = None
    start_frame = int(getattr(conn, "start_frame", 0) or 0)
    frame_getter = getattr(timeline, "GetStartFrame", None)
    if callable(frame_getter):
        try:
            start_frame = int(frame_getter())
        except Exception:
            pass
    return {"start_timecode": start_timecode, "start_frame": start_frame}


def _rebase_switch_segments_to_timeline_start(
    segments: list[Any],
    *,
    plan: dict[str, Any],
    timeline_start_state: dict[str, Any],
    fps: float,
    ops_module,
) -> tuple[list[Any], dict[str, Any]]:
    if "base_start_frame" not in plan:
        return segments, {"status": "not_requested", "changed": False}
    base_start_frame = int(plan.get("base_start_frame") or 0)
    target_start_frame = int(timeline_start_state.get("start_frame") or 0)
    delta = target_start_frame - base_start_frame
    if delta == 0:
        return segments, {
            "status": "already_aligned",
            "changed": False,
            "base_start_frame": base_start_frame,
            "target_start_frame": target_start_frame,
            "delta_frames": 0,
        }

    frames_to_timecode = getattr(ops_module, "frames_to_timecode", None)
    rebased = []
    for segment in segments:
        values = {
            "start_frame": int(getattr(segment, "start_frame")) + delta,
            "end_frame": int(getattr(segment, "end_frame")) + delta,
        }
        if getattr(segment, "record_start_frame", None) is not None:
            values["record_start_frame"] = int(getattr(segment, "record_start_frame")) + delta
        if getattr(segment, "record_end_frame", None) is not None:
            values["record_end_frame"] = int(getattr(segment, "record_end_frame")) + delta
        if callable(frames_to_timecode):
            values["start_tc"] = frames_to_timecode(values.get("record_start_frame", values["start_frame"]), fps)
            values["end_tc"] = frames_to_timecode(values.get("record_end_frame", values["end_frame"]), fps)
        rebased.append(replace(segment, **values))

    return rebased, {
        "status": "rebased",
        "changed": True,
        "base_start_frame": base_start_frame,
        "target_start_frame": target_start_frame,
        "delta_frames": delta,
    }


def _restore_timeline_start_state(conn, *, timeline_name: str, start_state: dict[str, Any]) -> dict[str, Any]:
    target_timecode = str(start_state.get("start_timecode") or "").strip()
    if not target_timecode:
        return {
            "status": "not_requested",
            "changed": False,
            "timeline_name": timeline_name,
            "target_timecode": None,
            "final_timecode": None,
        }
    timeline = getattr(conn, "timeline", None)
    if timeline is None:
        raise APICallFailed(
            "Cannot restore timeline start timecode after native multicam switch because no timeline is active.",
            details={"timeline_name": timeline_name, "target_timecode": target_timecode},
        )
    getter = getattr(timeline, "GetStartTimecode", None)
    setter = getattr(timeline, "SetStartTimecode", None)
    current_timecode = None
    if callable(getter):
        try:
            current_timecode = str(getter() or "").strip() or None
        except Exception:
            current_timecode = None
    if not callable(setter):
        raise APICallFailed(
            "Cannot restore timeline start timecode after native multicam switch because DaVinci Resolve did not expose SetStartTimecode.",
            details={
                "timeline_name": timeline_name,
                "target_timecode": target_timecode,
                "current_timecode": current_timecode,
            },
        )
    changed = current_timecode != target_timecode
    applied_record_delta_frames = 0
    if changed:
        if not current_timecode:
            raise APICallFailed(
                "Cannot preserve timeline item positions because the current timeline start timecode is unavailable.",
                details={"timeline_name": timeline_name, "target_timecode": target_timecode},
            )
        try:
            fps = float(getattr(conn, "fps", 24.0) or 24.0)
            current_frame = int(round(timecode_to_seconds(current_timecode, fps) * fps))
            applied_record_delta_frames = int(start_state.get("start_frame") or 0) - current_frame
        except Exception as exc:
            raise APICallFailed(
                "Cannot preserve timeline item positions while restoring the timeline start timecode.",
                details={"timeline_name": timeline_name, "target_timecode": target_timecode, "current_timecode": current_timecode},
            ) from exc
    if changed and setter(target_timecode) is False:
        raise APICallFailed(
            "DaVinci Resolve refused to restore the timeline start timecode after native multicam switch.",
            details={
                "timeline_name": timeline_name,
                "target_timecode": target_timecode,
                "current_timecode": current_timecode,
            },
        )
    conn.refresh()
    final_timecode = target_timecode
    timeline = getattr(conn, "timeline", timeline)
    getter = getattr(timeline, "GetStartTimecode", None)
    if callable(getter):
        try:
            final_timecode = str(getter() or "").strip() or None
        except Exception:
            final_timecode = None
    return {
        "status": "verified" if final_timecode == target_timecode else "mismatch",
        "changed": changed,
        "timeline_name": timeline_name,
        "target_timecode": target_timecode,
        "initial_timecode": current_timecode,
        "final_timecode": final_timecode,
        "start_frame": start_state.get("start_frame"),
        "applied_record_delta_frames": applied_record_delta_frames,
    }


def _append_multicam_clip_to_active_timeline(
    conn,
    *,
    created_clip: Any,
    multicam_name: str,
    project_db_path: str | None = None,
    allow_db_bootstrap: bool = False,
    record_frame: int | None = None,
    switch_scope: str = "linked",
) -> dict[str, Any]:
    switch_scope = _normalize_switch_scope(switch_scope)
    timeline = getattr(conn, "timeline", None)
    get_start_frame = getattr(timeline, "GetStartFrame", None) if timeline is not None else None
    if record_frame is None:
        try:
            record_frame = int(get_start_frame()) if callable(get_start_frame) else int(getattr(conn, "start_frame", 0) or 0)
        except Exception:
            record_frame = int(getattr(conn, "start_frame", 0) or 0)
    else:
        record_frame = int(record_frame)
    live_candidates: list[dict[str, Any]] = []
    live_resolution_error: str | None = None
    if project_db_path:
        try:
            binding_state = native_multicam_db.inspect_multicam_bindings(
                project_db_path,
                multicam_name=multicam_name,
            )
            target = {
                "multicam_name": binding_state["multicam_name"],
                "multicam_media_id": binding_state["multicam_media_id"],
                "multicam_sequence_id": binding_state["multicam_sequence_id"],
                "folder_path": None,
            }
            created_clip, live_candidates = resolve_live_multicam_media_pool_item(conn, target=target)
        except Exception as exc:
            live_resolution_error = str(exc)
    if created_clip is None:
        raise APICallFailed(
            "Native multicam clip exists in Project.db but could not be resolved in the live Media Pool before switch writing.",
            details={
                "multicam_name": multicam_name,
                "project_db_path": project_db_path,
                "live_candidates": live_candidates,
                "live_resolution_error": live_resolution_error,
            },
        )
    clip_info: dict[str, Any] = {
        "mediaPoolItem": created_clip,
        "trackIndex": 1,
        "trackType": "audio" if switch_scope == "audio" else "video",
        "recordFrame": record_frame,
    }
    if switch_scope == "video":
        clip_info["mediaType"] = 1
    elif switch_scope == "audio":
        clip_info["mediaType"] = 2
    append_result = conn.media_pool.AppendToTimeline([clip_info])
    if not append_result:
        if allow_db_bootstrap:
            return {
                "append_result": False,
                "api_video_item_count": 0,
                "db_bootstrap": True,
                "db_bootstrap_reason": "append_failed",
                "record_frame": record_frame,
                "live_candidates": live_candidates,
                "live_resolution_error": live_resolution_error,
            }
        raise APICallFailed(
            "Failed to append the native multicam clip into the active timeline before switch writing.",
            details={
                "multicam_name": multicam_name,
                "record_frame": record_frame,
                "project_db_path": project_db_path,
                "live_candidates": live_candidates,
                "live_resolution_error": live_resolution_error,
            },
        )
    video_items = []
    audio_items = []
    for attempt in range(1, 9):
        conn.refresh()
        video_items = conn.timeline.GetItemListInTrack("video", 1) or []
        audio_items = conn.timeline.GetItemListInTrack("audio", 1) or []
        scoped_items = audio_items if switch_scope == "audio" else video_items
        if scoped_items:
            break
        if attempt < 8:
            time.sleep(0.1)
    scoped_items = audio_items if switch_scope == "audio" else video_items
    if not scoped_items:
        if allow_db_bootstrap:
            return {
                "append_result": True,
                "api_video_item_count": 0,
                "api_audio_item_count": 0,
                "db_bootstrap": True,
                "db_bootstrap_reason": "api_video_readback_empty",
                "record_frame": record_frame,
                "live_candidates": live_candidates,
                "live_resolution_error": live_resolution_error,
            }
        raise APICallFailed(
            "DaVinci Resolve did not populate the active timeline after appending the native multicam clip.",
            details={
                "multicam_name": multicam_name,
                "record_frame": record_frame,
                "project_db_path": project_db_path,
                "live_candidates": live_candidates,
                "live_resolution_error": live_resolution_error,
            },
        )
    return {
        "append_result": True,
        "api_video_item_count": len(video_items),
        "api_audio_item_count": len(audio_items),
        "db_bootstrap": False,
        "db_bootstrap_reason": None,
        "record_frame": record_frame,
        "live_candidates": live_candidates,
        "live_resolution_error": live_resolution_error,
    }


def _split_multicam_items_for_segments(conn, *, segments: list[Any], ops_module) -> dict[str, Any]:
    return _db_only_split_summary(conn=conn, segments=segments, ops_module=ops_module)


def _db_only_split_summary(*, conn, segments: list[Any], ops_module) -> dict[str, Any]:
    timeline_start = int(getattr(conn, "start_frame", 0) or 0)
    split_positions = [ops_module._segment_record_start_frame(segment) - timeline_start for segment in segments[1:]]
    return {
        "split_count": len(split_positions),
        "video_item_count": 1,
        "audio_item_count": 1,
        "split_positions": split_positions,
        "strategy": "db_only",
    }


def _snapshot_timeline_multicam_segments_db(
    project_db_path: str,
    *,
    timeline_name: str,
    multicam_name: str,
    ops_module,
    multicam_media_id: str | None = None,
    timeline_native_id: str | None = None,
) -> dict[str, Any]:
    state = ops_module._load_timeline_multicam_track_state(
        project_db_path,
        timeline_name=timeline_name,
        multicam_name=multicam_name,
        multicam_media_id=multicam_media_id,
        timeline_native_id=timeline_native_id,
    )
    video_rows = state["video_items"]
    audio_rows = state["audio_items"]
    return {
        "multicam_media_id": state["multicam_media_id"],
        "video_item_count": len(video_rows),
        "audio_item_count": len(audio_rows),
        "video_items": [
            {
                "item_id": row["item_row"]["Sm2TiItem_id"],
                "start": row["item_row"].get("Start"),
                "duration": row["item_row"].get("Duration"),
                "in": row["item_row"].get("In"),
                "media_ref": row["item_row"].get("MediaRef"),
                "current_selector_idx": row["item_row"].get("CurrentSelectorIdx"),
                "track_id": row["track_id"],
            }
            for row in video_rows
        ],
        "audio_items": [
            {
                "item_id": row["item_row"]["Sm2TiItem_id"],
                "start": row["item_row"].get("Start"),
                "duration": row["item_row"].get("Duration"),
                "in": row["item_row"].get("In"),
                "media_ref": row["item_row"].get("MediaRef"),
                "current_selector_idx": row["item_row"].get("CurrentSelectorIdx"),
                "track_id": row["track_id"],
            }
            for row in audio_rows
        ],
    }


def _inspect_timeline_multicam_db_materialization(
    project_db_path: str,
    *,
    timeline_name: str,
    multicam_name: str,
) -> dict[str, Any]:
    connection = sqlite3.connect(project_db_path)
    try:
        connection.row_factory = sqlite3.Row
        timeline_exists = (
            connection.execute("SELECT 1 FROM Sm2Timeline WHERE Name = ? LIMIT 1", (timeline_name,)).fetchone()
            is not None
        )
        rows = connection.execute(
            """
            SELECT
                track.Type AS TrackType,
                COUNT(*) AS ItemCount
            FROM Sm2Timeline timeline
            JOIN Sm2Sequence seq ON seq.Sm2Timeline_id = timeline.Sm2Timeline_id
            JOIN Sm2SequenceContainer container ON container.Sm2Sequence_id = seq.Sm2Sequence_id
            JOIN Sm2MpMedia media ON media.Name = ?
            JOIN Sm2SequenceContainer_Sm2TiTrack rel_track ON rel_track.DbOwner = container.Sm2SequenceContainer_id
            JOIN Sm2TiTrack track ON track.Sm2TiTrack_id = rel_track.DbAssociate
            JOIN Sm2TiItem_Sm2TiTrack rel_item
              ON rel_item.DbOwner = track.Sm2TiTrack_id
             AND rel_item.DbPropertyName = 'Items'
            JOIN Sm2TiItem item ON item.Sm2TiItem_id = rel_item.DbAssociate
            WHERE timeline.Name = ?
              AND item.MediaRef = media.Sm2MpMedia_id
            GROUP BY track.Type
            """,
            (multicam_name, timeline_name),
        ).fetchall()
    finally:
        connection.close()

    counts = {int(row["TrackType"]): int(row["ItemCount"] or 0) for row in rows}
    return {
        "timeline_exists": timeline_exists,
        "video_item_count": counts.get(0, 0),
        "audio_item_count": counts.get(1, 0),
    }


def _wait_for_timeline_multicam_db_materialization(
    conn,
    *,
    project_db_path: str,
    timeline_name: str,
    multicam_name: str,
    allow_empty_items: bool = False,
    attempts: int = 8,
    delay: float = 0.15,
) -> dict[str, Any]:
    last_state: dict[str, Any] | None = None
    for attempt in range(1, attempts + 1):
        if conn is not None:
            conn.refresh()
        state = _inspect_timeline_multicam_db_materialization(
            project_db_path,
            timeline_name=timeline_name,
            multicam_name=multicam_name,
        )
        state["attempt"] = attempt
        last_state = state
        if state["timeline_exists"] and (
            allow_empty_items or (state["video_item_count"] >= 1 and state["audio_item_count"] >= 1)
        ):
            return state
        if attempt < attempts:
            time.sleep(delay)

    raise APICallFailed(
        "The target timeline did not materialize a native multicam base item in Project.db before switch writing.",
        details={
            "timeline_name": timeline_name,
            "multicam_name": multicam_name,
            "project_db_path": project_db_path,
            "last_state": last_state or {},
        },
    )


def _wait_for_timeline_db_existence(
    project_db_path: str,
    *,
    timeline_name: str,
    attempts: int = 8,
    delay: float = 0.15,
) -> dict[str, Any]:
    last_state: dict[str, Any] | None = None
    for attempt in range(1, attempts + 1):
        state = _inspect_timeline_multicam_db_materialization(
            project_db_path,
            timeline_name=timeline_name,
            multicam_name="",
        )
        state["attempt"] = attempt
        last_state = state
        if state["timeline_exists"]:
            return state
        if attempt < attempts:
            time.sleep(delay)

    raise APICallFailed(
        "The target timeline did not materialize in Project.db before native multicam insertion.",
        details={
            "timeline_name": timeline_name,
            "project_db_path": project_db_path,
            "last_state": last_state or {},
        },
    )


def _find_project_timeline_by_name(project: Any, timeline_name: str | None) -> Any | None:
    target_name = str(timeline_name or "").strip()
    if project is None or not target_name:
        return None
    count_getter = getattr(project, "GetTimelineCount", None)
    timeline_getter = getattr(project, "GetTimelineByIndex", None)
    if not callable(count_getter) or not callable(timeline_getter):
        return None
    for index in range(1, int(count_getter() or 0) + 1):
        timeline = timeline_getter(index)
        name_getter = getattr(timeline, "GetName", None) if timeline is not None else None
        if callable(name_getter) and str(name_getter() or "").strip() == target_name:
            return timeline
    return None


def _rollback_failed_new_timeline_materialization(
    conn,
    *,
    project_name: str,
    original_timeline_name: str | None,
    created_timeline_name: str,
    owned_created_timeline_name: str | None,
    ops_module,
) -> dict[str, Any]:
    """Restore the pre-operation timeline and remove only our failed new timeline."""

    steps: list[dict[str, Any]] = []
    errors: list[str] = []
    if str(owned_created_timeline_name or "").strip() != str(created_timeline_name or "").strip():
        return {
            "status": "not_attempted",
            "reason": "created_timeline_ownership_unverified",
            "project_name": project_name,
            "original_timeline_name": original_timeline_name,
            "created_timeline_name": created_timeline_name,
            "owned_created_timeline_name": owned_created_timeline_name,
            "steps": steps,
            "errors": ["created_timeline_ownership_unverified"],
        }
    try:
        conn.refresh()
    except Exception as exc:
        errors.append(f"refresh_before_rollback:{exc}")

    project = getattr(conn, "project", None)
    project_name_getter = getattr(project, "GetName", None) if project is not None else None
    try:
        current_project_name = str(project_name_getter() or "").strip() if callable(project_name_getter) else ""
    except Exception:
        current_project_name = ""
    if current_project_name != project_name:
        try:
            ops_module._reopen_project(conn, project_name=project_name)
            steps.append({"name": "reopen_original_project", "ok": True, "project_name": project_name})
        except Exception as exc:
            errors.append(f"reopen_original_project:{exc}")

    project = getattr(conn, "project", None)
    target_timeline = _find_project_timeline_by_name(project, created_timeline_name)
    original_timeline = _find_project_timeline_by_name(project, original_timeline_name)
    setter = getattr(project, "SetCurrentTimeline", None) if project is not None else None
    deleter = getattr(getattr(conn, "media_pool", None), "DeleteTimelines", None)

    if original_timeline_name and original_timeline is None:
        errors.append(f"restore_original_timeline:not_found:{original_timeline_name}")
    elif original_timeline is not None:
        try:
            if not callable(setter) or setter(original_timeline) is False:
                raise APICallFailed("DaVinci Resolve refused to restore the original timeline during rollback.")
            conn.refresh()
            steps.append({"name": "restore_original_timeline", "ok": True, "timeline_name": original_timeline_name})
        except Exception as exc:
            errors.append(f"restore_original_timeline:{exc}")

    if target_timeline is not None:
        try:
            if not callable(deleter) or deleter([target_timeline]) is False:
                raise APICallFailed("DaVinci Resolve refused to delete the failed target timeline during rollback.")
            conn.refresh()
            if _find_project_timeline_by_name(getattr(conn, "project", None), created_timeline_name) is not None:
                raise APICallFailed("The failed target timeline still exists after rollback deletion.")
            steps.append({"name": "delete_failed_target_timeline", "ok": True, "timeline_name": created_timeline_name})
        except Exception as exc:
            errors.append(f"delete_failed_target_timeline:{exc}")
    else:
        steps.append({"name": "delete_failed_target_timeline", "ok": True, "timeline_name": created_timeline_name, "status": "not_created"})

    project_manager = getattr(conn, "project_manager", None)
    save_fn = getattr(project_manager, "SaveProject", None) if project_manager is not None else None
    if callable(save_fn):
        try:
            if save_fn() is False:
                raise APICallFailed("DaVinci Resolve refused to save the restored project during rollback.")
            steps.append({"name": "save_rollback", "ok": True, "project_name": project_name})
        except Exception as exc:
            errors.append(f"save_rollback:{exc}")

    return {
        "status": "verified" if not errors else "incomplete",
        "project_name": project_name,
        "original_timeline_name": original_timeline_name,
        "created_timeline_name": created_timeline_name,
        "steps": steps,
        "errors": errors,
    }


def _materialize_timeline_from_switch_plan_unprotected(
    conn,
    *,
    timeline_name: str,
    multicam_name: str,
    plan: dict[str, Any],
    replace_active_timeline: bool,
    ops_module,
    switch_scope: str = "linked",
    multicam_media_id: str | None = None,
    timeline_native_id: str | None = None,
    mutation_state: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    switch_scope = _normalize_switch_scope(switch_scope)
    write_video = switch_scope in {"linked", "video"}
    write_audio = switch_scope in {"linked", "audio"}
    segment_fields = getattr(ops_module.SwitchSegment, "__dataclass_fields__", {})
    if segment_fields:
        allowed_fields = set(segment_fields.keys())
    else:
        allowed_fields = {
            "speaker_id",
            "angle",
            "clip_name",
            "start_frame",
            "end_frame",
            "start_tc",
            "end_tc",
            "text",
            "record_start_frame",
            "record_end_frame",
        }
    segments = [
        ops_module.SwitchSegment(**{key: value for key, value in dict(segment).items() if key in allowed_fields})
        for segment in plan.get("segments", [])
    ]
    if not segments:
        raise ValidationError("Switch plan has no segments.", details={"plan": plan})
    plan_multicam_settings = plan.get("multicam_settings") if isinstance(plan, dict) else None
    audio_angle_override = None
    if isinstance(plan_multicam_settings, dict):
        normalized_audio_mode = str(plan_multicam_settings.get("audio_mode") or "").strip().lower().replace("-", "_")
        if normalized_audio_mode == "reference_audio":
            audio_angle_override = str(
                plan_multicam_settings.get("reference_audio_clip_name")
                or plan_multicam_settings.get("reference_audio_angle_clip_name")
                or ""
            ).strip() or None
    planned_angle_order = plan_multicam_settings.get("angle_order") if isinstance(plan_multicam_settings, dict) else None
    if not planned_angle_order and isinstance(plan, dict):
        planned_angle_order = plan.get("angle_order")
    planned_angle_count = (
        len([item for item in planned_angle_order if str(item).strip()])
        if isinstance(planned_angle_order, list) and planned_angle_order
        else len({str(segment.angle or "").strip() for segment in segments if str(segment.angle or "").strip()})
    )
    if multicam_media_id:
        root = conn.media_pool.GetRootFolder()
        matches: list[dict[str, Any]] = []
        if root:
            media_pool._collect_clip_object_matches(root, matches)
        exact_matches = [
            match for match in matches
            if str(
                match.get("clip").GetUniqueId()
                if match.get("clip") is not None and callable(getattr(match.get("clip"), "GetUniqueId", None))
                else ""
            ) == multicam_media_id
            and str(match.get("name") or "") == multicam_name
        ]
        if len(exact_matches) != 1:
            raise ValidationError(
                "The exact native multicam target is no longer uniquely available.",
                details={"reason": "multicam_native_identity_unverified", "multicam_name": multicam_name},
            )
        created_clip = exact_matches[0]["clip"]
    else:
        created_clip = media_pool.find_clip(conn, multicam_name)
    project_db_path = ops_module._resolve_current_project_db_path(conn)
    expected_clip_names = list(
        dict.fromkeys(
            str(segment.clip_name or "").strip()
            for segment in segments
            if str(segment.clip_name or "").strip()
        )
    )
    if audio_angle_override and audio_angle_override not in expected_clip_names:
        expected_clip_names.append(audio_angle_override)
    angle_indices = ops_module._resolve_multicam_angle_indices(
        project_db_path,
        multicam_name=multicam_name,
        expected_clip_names=expected_clip_names,
        multicam_media_id=multicam_media_id,
    )
    missing_clip_names = [clip_name for clip_name in expected_clip_names if clip_name not in angle_indices]
    if missing_clip_names:
        raise ValidationError(
            "Switch plan references a clip that is not present in the native multicam angle order.",
            details={
                "reason": "switch_plan_angle_membership_unverified",
                "stage": "preflight_before_timeline_mutation",
                "multicam_name": multicam_name,
                "missing_clips": missing_clip_names,
                "known_clips": sorted(angle_indices.keys()),
            },
        )
    support_tier = support_tier_for_angle_count(planned_angle_count)
    if not bool(support_tier.get("switch_contract_supported")):
        raise ValidationError(
            "Native multicam switch execution is unsupported for this angle count.",
            details={
                "step": "unsupported_angle_count",
                "angle_count": planned_angle_count,
                "multicam_name": multicam_name,
                "support_tier": support_tier,
            },
        )
    if planned_angle_count <= 5:
        multicam_switch_families.ensure_switch_family_supported(planned_angle_count)
    elif planned_angle_count >= 4 and ops_module._load_matching_project_multicam_switch_fixture(
        project_db_path,
        multicam_name=multicam_name,
        angle_count=planned_angle_count,
    ) is None:
        multicam_switch_families.ensure_switch_family_supported(planned_angle_count)
    project_name = ops_module._require_live_project_name(conn, context="native multicam switching")
    current_database = ops_module._current_database_details(conn)
    initial_video_item_count = 0
    initial_audio_item_count = 0
    preserved_api_items_before: list[dict[str, Any]] = []

    if replace_active_timeline:
        active_timeline = getattr(conn, "timeline", None)
        active_name = active_timeline.GetName() if active_timeline and hasattr(active_timeline, "GetName") else None
        if not active_name:
            raise APICallFailed(
                "No active timeline is available for native multicam switch materialization.",
                details={"multicam_name": multicam_name},
            )
        timeline_start_state = _capture_timeline_start_state(conn)
        preserved_api_items_before = _snapshot_untouched_timeline_items(conn, switch_scope=switch_scope)
        timeline_name = active_name
        initial_video_item_count = len(active_timeline.GetItemListInTrack("video", 1) or [])
        initial_audio_item_count = len(active_timeline.GetItemListInTrack("audio", 1) or [])
        cleanup_summary = ops_module._clear_active_timeline_items(conn, switch_scope=switch_scope)
        append_summary = ops_module._append_multicam_clip_to_active_timeline(
            conn,
            created_clip=created_clip,
            multicam_name=multicam_name,
            project_db_path=project_db_path,
            allow_db_bootstrap=True,
            switch_scope=switch_scope,
        )
    else:
        cleanup_summary = {"deleted_clip_count": 0, "deleted_video_clip_count": 0, "deleted_audio_clip_count": 0}
        creator = getattr(conn.media_pool, "CreateEmptyTimeline", None)
        created_timeline = creator(timeline_name) if callable(creator) else None
        if not created_timeline:
            raise APICallFailed(
                "Failed to create the target timeline before native multicam insertion.",
                details={"timeline_name": timeline_name, "multicam_name": multicam_name},
            )
        created_name_getter = getattr(created_timeline, "GetName", None)
        created_name = str(created_name_getter() or "").strip() if callable(created_name_getter) else ""
        if created_name != timeline_name:
            raise APICallFailed(
                "DaVinci Resolve returned a timeline that could not be uniquely attributed to this creation attempt.",
                details={
                    "timeline_name": timeline_name,
                    "created_timeline_name": created_name or None,
                    "reason": "created_timeline_ownership_unverified",
                },
                recoverability="manual",
            )
        if mutation_state is not None:
            mutation_state.update(
                {
                    "mutation_started": True,
                    "owned_created_timeline_name": created_name,
                }
            )

        project = getattr(conn, "project", None)
        setter = getattr(project, "SetCurrentTimeline", None) if project is not None else None
        if callable(setter):
            set_result = setter(created_timeline)
            if set_result is False:
                raise APICallFailed(
                    "DaVinci Resolve created the target timeline but refused to make it current.",
                    details={"timeline_name": timeline_name, "multicam_name": multicam_name},
                )

        conn.refresh()
        wait_for_state = getattr(conn, "wait_for_state", None)
        if callable(wait_for_state):
            try:
                wait_for_state(
                    lambda state: str(state.get("timeline") or "").strip() == timeline_name,
                    description=f"timeline '{timeline_name}' to become current before native multicam insertion",
                    attempts=8,
                    delay=0.1,
                )
            except Exception:
                pass

        timeline_start_state = _capture_timeline_start_state(conn)
        try:
            conn.start_frame = int(timeline_start_state.get("start_frame") or 0)
        except Exception:
            pass

        ops_module._wait_for_timeline_db_existence(project_db_path, timeline_name=timeline_name)
        append_summary = ops_module._append_multicam_clip_to_active_timeline(
            conn,
            created_clip=created_clip,
            multicam_name=multicam_name,
            project_db_path=project_db_path,
            allow_db_bootstrap=True,
            record_frame=int(timeline_start_state.get("start_frame") or 0),
            switch_scope=switch_scope,
        )
        if not bool((append_summary or {}).get("db_bootstrap")):
            ops_module._wait_for_timeline_multicam_db_materialization(
                conn,
                project_db_path=project_db_path,
                timeline_name=timeline_name,
                multicam_name=multicam_name,
                allow_empty_items=True,
            )

    segments, timeline_start_rebase = _rebase_switch_segments_to_timeline_start(
        segments,
        plan=plan,
        timeline_start_state=timeline_start_state,
        fps=float(getattr(conn, "fps", 24.0) or 24.0),
        ops_module=ops_module,
    )

    split_summary = {"split_count": 0, "video_item_count": 1, "audio_item_count": 1, "split_positions": []}
    if replace_active_timeline and write_video:
        if bool((append_summary or {}).get("db_bootstrap")):
            split_summary = ops_module._db_only_split_summary(conn=conn, segments=segments)
        elif planned_angle_count >= 3 and len(segments) > 1:
            split_summary = ops_module._db_only_split_summary(conn=conn, segments=segments)
        else:
            split_summary = ops_module._split_multicam_items_for_segments(conn, segments=segments)
    elif replace_active_timeline and not write_video:
        split_summary = ops_module._db_only_split_summary(conn=conn, segments=segments)

    project_manager = getattr(conn, "project_manager", None)
    save_fn = getattr(project_manager, "SaveProject", None) if project_manager is not None else None
    if callable(save_fn) and save_fn() is False:
        raise APICallFailed(
            "DaVinci Resolve refused to save the project before native multicam switch DB patching.",
            details={"project_name": project_name, "timeline_name": timeline_name},
        )

    ops_module._close_current_project(
        conn,
        project_name=project_name,
        current_database=current_database,
        project_db_path=project_db_path,
        save=True,
        close_step_name="project_reload_close",
        wait_description=f"project '{project_name}' to stop being current before native multicam switch DB patch",
    )
    db_materialization = ops_module._wait_for_timeline_db_existence(project_db_path, timeline_name=timeline_name)
    segment_write = ops_module._rewrite_multicam_segments_db(
        project_db_path,
        timeline_name=timeline_name,
        multicam_name=multicam_name,
        segments=segments,
        switch_scope=switch_scope,
        audio_angle_override=audio_angle_override,
        multicam_media_id=multicam_media_id,
        timeline_native_id=timeline_native_id,
    )
    ops_module._reopen_project(conn, project_name=project_name)
    ops_module._activate_timeline_by_name(conn, timeline_name, timeline_native_id=timeline_native_id)
    if callable(save_fn) and save_fn() is False:
        raise APICallFailed(
            "DaVinci Resolve refused to save the project after native multicam switch DB patching.",
            details={"project_name": project_name, "timeline_name": timeline_name},
        )
    ops_module._close_current_project(
        conn,
        project_name=project_name,
        current_database=current_database,
        project_db_path=project_db_path,
        save=True,
        close_step_name="project_persist_close",
        wait_description=f"project '{project_name}' to stop being current after native multicam switch DB patch",
    )
    ops_module._reopen_project(conn, project_name=project_name)
    ops_module._activate_timeline_by_name(conn, timeline_name, timeline_native_id=timeline_native_id)
    timeline_start_restore = _restore_timeline_start_state(
        conn,
        timeline_name=timeline_name,
        start_state=timeline_start_state,
    )
    if timeline_start_restore.get("status") == "mismatch":
        raise APICallFailed(
            "Timeline start timecode did not verify after native multicam switch.",
            details=timeline_start_restore,
        )
    if bool(timeline_start_restore.get("changed")) and callable(save_fn) and save_fn() is False:
        raise APICallFailed(
            "DaVinci Resolve refused to save the project after restoring timeline start timecode.",
            details={"project_name": project_name, "timeline_name": timeline_name, "timeline_start_restore": timeline_start_restore},
        )
    timeline_start_record_rewrite: dict[str, Any] = {"status": "not_required", "changed": False}
    if bool(timeline_start_restore.get("changed")):
        ops_module._close_current_project(
            conn,
            project_name=project_name,
            current_database=current_database,
            project_db_path=project_db_path,
            save=True,
            close_step_name="project_timeline_start_record_rewrite_close",
            wait_description=f"project '{project_name}' to stop being current before timeline start record-domain rewrite",
        )
        ops_module._wait_for_timeline_db_existence(project_db_path, timeline_name=timeline_name)
        segment_write = ops_module._rewrite_multicam_segments_db(
            project_db_path,
            timeline_name=timeline_name,
            multicam_name=multicam_name,
            segments=segments,
            switch_scope=switch_scope,
            preserved_item_positions=segment_write.get("preserved_items_before") or [],
            final_start_delta=int(timeline_start_restore.get("applied_record_delta_frames") or 0),
            multicam_media_id=multicam_media_id,
            timeline_native_id=timeline_native_id,
        )
        ops_module._reopen_project(conn, project_name=project_name)
        ops_module._activate_timeline_by_name(conn, timeline_name, timeline_native_id=timeline_native_id)
        final_start_restore = _restore_timeline_start_state(
            conn,
            timeline_name=timeline_name,
            start_state=timeline_start_state,
        )
        if final_start_restore.get("status") == "mismatch":
            raise APICallFailed(
                "Timeline start timecode did not verify after native multicam record-domain rewrite.",
                details=final_start_restore,
            )
        if callable(save_fn) and save_fn() is False:
            raise APICallFailed(
                "DaVinci Resolve refused to save the project after timeline start record-domain rewrite.",
                details={
                    "project_name": project_name,
                    "timeline_name": timeline_name,
                    "timeline_start_restore": timeline_start_restore,
                    "final_start_restore": final_start_restore,
                },
            )
        timeline_start_record_rewrite = {
            "status": "applied",
            "changed": True,
            "reason": "timeline_start_timecode_restore_can_shift_record_positions",
            "target_timecode": timeline_start_restore.get("target_timecode"),
            "start_frame": timeline_start_restore.get("start_frame"),
            "final_start_restore": final_start_restore,
        }

    conn.refresh()
    preserved_api_items_after = _snapshot_untouched_timeline_items(conn, switch_scope=switch_scope)
    if preserved_api_items_after != preserved_api_items_before:
        raise APICallFailed(
            "Scoped multicam switching changed a timeline item outside the requested media domain.",
            details={"switch_scope": switch_scope, "before": preserved_api_items_before, "after": preserved_api_items_after},
        )
    db_snapshot = ops_module._snapshot_timeline_multicam_segments_db(
        project_db_path,
        timeline_name=timeline_name,
        multicam_name=multicam_name,
        multicam_media_id=multicam_media_id,
        timeline_native_id=timeline_native_id,
    )
    video_items = conn.timeline.GetItemListInTrack("video", 1) or []
    audio_items = conn.timeline.GetItemListInTrack("audio", 1) or []
    scoped_item_count = db_snapshot["video_item_count"] if write_video else db_snapshot["audio_item_count"]
    scoped_api_items = video_items if write_video else audio_items
    selected_multicam_items: list[dict[str, Any]] = []
    if write_video:
        selected_multicam_items.extend(db_snapshot["video_items"])
    if write_audio:
        selected_multicam_items.extend(db_snapshot["audio_items"])
    verification_checks = [
        {"name": "multicam_clip_exists", "ok": True, "multicam_name": multicam_name},
        {"name": "timeline_exists", "ok": True, "timeline_name": timeline_name},
        {"name": "timeline_active", "ok": True, "timeline_name": timeline_name},
        {
            "name": "timeline_populated",
            "ok": bool(scoped_item_count),
            "timeline_name": timeline_name,
            "switch_scope": switch_scope,
            "video_item_count": db_snapshot["video_item_count"],
            "audio_item_count": db_snapshot["audio_item_count"],
            "verification_source": "project_db",
        },
        {
            "name": "video_segment_count",
            "ok": (not write_video) or db_snapshot["video_item_count"] == len(segments),
            "expected": len(segments),
            "actual": db_snapshot["video_item_count"],
            "switch_scope": switch_scope,
        },
        {
            "name": "audio_segment_count",
            "ok": (not write_audio) or db_snapshot["audio_item_count"] == len(segments),
            "expected": len(segments),
            "actual": db_snapshot["audio_item_count"],
            "switch_scope": switch_scope,
        },
        {
            "name": "timeline_uses_multicam_clip",
            "ok": bool(selected_multicam_items)
            and all(item.get("media_ref") == db_snapshot["multicam_media_id"] for item in selected_multicam_items),
            "timeline_name": timeline_name,
            "multicam_name": multicam_name,
            "switch_scope": switch_scope,
            "verification_source": "project_db",
        },
        {
            "name": "timeline_multicam_items_only",
            "ok": bool(selected_multicam_items)
            and all(item.get("media_ref") == db_snapshot["multicam_media_id"] for item in selected_multicam_items),
            "timeline_name": timeline_name,
            "switch_scope": switch_scope,
            "verification_source": "project_db",
        },
        {
            "name": "timeline_api_readback_present",
            "ok": bool(scoped_api_items),
            "timeline_name": timeline_name,
            "verification_source": "resolve_api",
            "video_item_count": len(video_items),
            "audio_item_count": len(audio_items),
            "switch_scope": switch_scope,
        },
    ]
    if switch_scope == "video":
        verification_checks.append(
            {
                "name": "audio_scope_preserved",
                "ok": len(audio_items) == initial_audio_item_count,
                "expected": initial_audio_item_count,
                "actual": len(audio_items),
                "switch_scope": switch_scope,
                "verification_source": "resolve_api",
            }
        )
    elif switch_scope == "audio":
        verification_checks.append(
            {
                "name": "video_scope_preserved",
                "ok": len(video_items) == initial_video_item_count,
                "expected": initial_video_item_count,
                "actual": len(video_items),
                "switch_scope": switch_scope,
                "verification_source": "resolve_api",
            }
        )
    if timeline_start_restore.get("status") != "not_requested":
        verification_checks.append(
            {
                "name": "timeline_start_timecode_preserved",
                "ok": timeline_start_restore.get("status") == "verified",
                "timeline_name": timeline_name,
                "target_timecode": timeline_start_restore.get("target_timecode"),
                "final_timecode": timeline_start_restore.get("final_timecode"),
                "changed": bool(timeline_start_restore.get("changed")),
            }
        )
    verification_status = "verified" if all(check.get("ok") for check in verification_checks) else "pending_manual"
    ops_module._set_workflow_verification(verification_status)

    return {
        "name": "timeline_multicam_switch",
        "ok": True,
        "timeline_name": timeline_name,
        "multicam_name": multicam_name,
        "switch_scope": switch_scope,
        "segment_count": len(segments),
        "deleted_clip_count": cleanup_summary["deleted_clip_count"],
        "deleted_video_clip_count": cleanup_summary.get("deleted_video_clip_count", 0),
        "deleted_audio_clip_count": cleanup_summary.get("deleted_audio_clip_count", 0),
        "split_count": split_summary["split_count"],
        "video_item_count": db_snapshot["video_item_count"],
        "audio_item_count": db_snapshot["audio_item_count"],
        "video_changed": write_video,
        "audio_changed": write_audio,
        "initial_video_item_count": initial_video_item_count,
        "initial_audio_item_count": initial_audio_item_count,
        "segment_write": segment_write,
        "selector_patch": segment_write,
        "db_materialization": db_materialization,
        "db_snapshot": db_snapshot,
        "append": append_summary,
        "timeline_start_rebase": timeline_start_rebase,
        "timeline_start_restore": timeline_start_restore,
        "timeline_start_record_rewrite": timeline_start_record_rewrite,
    }, verification_checks


def _materialize_timeline_from_switch_plan(
    conn,
    *,
    timeline_name: str,
    multicam_name: str,
    plan: dict[str, Any],
    replace_active_timeline: bool,
    ops_module,
    switch_scope: str = "linked",
    multicam_media_id: str | None = None,
    timeline_native_id: str | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if replace_active_timeline:
        return _materialize_timeline_from_switch_plan_unprotected(
            conn,
            timeline_name=timeline_name,
            multicam_name=multicam_name,
            plan=plan,
            replace_active_timeline=True,
            switch_scope=switch_scope,
            multicam_media_id=multicam_media_id,
            timeline_native_id=timeline_native_id,
            ops_module=ops_module,
        )

    project_name = ops_module._require_live_project_name(conn, context="native multicam switching")
    original_timeline = getattr(conn, "timeline", None)
    original_name_getter = getattr(original_timeline, "GetName", None) if original_timeline is not None else None
    original_timeline_name = str(original_name_getter() or "").strip() if callable(original_name_getter) else None
    target_existed_before = _find_project_timeline_by_name(getattr(conn, "project", None), timeline_name) is not None
    if target_existed_before:
        raise ValidationError(
            "Target timeline already exists. Choose a new timeline name and rerun.",
            details={
                "reason": "target_timeline_already_exists",
                "stage": "preflight_before_timeline_mutation",
                "timeline_name": timeline_name,
            },
        )

    mutation_state: dict[str, Any] = {
        "mutation_started": False,
        "owned_created_timeline_name": None,
    }
    try:
        return _materialize_timeline_from_switch_plan_unprotected(
            conn,
            timeline_name=timeline_name,
            multicam_name=multicam_name,
            plan=plan,
            replace_active_timeline=False,
            switch_scope=switch_scope,
            multicam_media_id=multicam_media_id,
            timeline_native_id=timeline_native_id,
            ops_module=ops_module,
            mutation_state=mutation_state,
        )
    except Exception as operation_error:
        if not bool(mutation_state.get("mutation_started")):
            raise
        rollback = _rollback_failed_new_timeline_materialization(
            conn,
            project_name=project_name,
            original_timeline_name=original_timeline_name,
            created_timeline_name=timeline_name,
            owned_created_timeline_name=str(mutation_state.get("owned_created_timeline_name") or "") or None,
            ops_module=ops_module,
        )
        if rollback["status"] != "verified":
            raise APICallFailed(
                "Native multicam switch failed and the new-timeline rollback could not be fully verified.",
                details={
                    "operation_error": str(operation_error),
                    "timeline_name": timeline_name,
                    "multicam_name": multicam_name,
                    "rollback": rollback,
                },
                recoverability="manual",
            ) from operation_error
        if isinstance(operation_error, (APICallFailed, ValidationError)):
            operation_error.details = {**dict(operation_error.details), "rollback": rollback}
            raise
        raise APICallFailed(
            "Native multicam switch failed after creating a new timeline; the original timeline was restored.",
            details={
                "operation_error": str(operation_error),
                "timeline_name": timeline_name,
                "multicam_name": multicam_name,
                "rollback": rollback,
            },
        ) from operation_error
