"""Disk-DB backed timeline item start/move mutation."""

from __future__ import annotations

from dataclasses import asdict
import sqlite3
from typing import Any

from ..errors import APICallFailed, ClipNotFound, EditMutationRecoveryFailed, EditMutationRestored, ValidationError
from ..utils.frame_math import parse_frame_quantity
from . import db_session, db_timeline_rows, timeline_item_duration_db, timeline_item_mutation, timeline_ops


def _parse_signed_duration_frames(raw: str, fps: float, *, allow_zero: bool = False) -> int:
    frames = parse_frame_quantity(raw, fps, field="delta", allow_signed=True)
    if frames == 0 and not allow_zero:
        raise ValidationError("Move delta must be greater than 0.", details={"delta": raw})
    return frames


def _resolve_new_start(
    conn: Any,
    *,
    current_start: int,
    target_start_frame: str | None,
    delta: str | None,
    allow_unchanged: bool = False,
    allow_zero_delta: bool = False,
) -> tuple[int, dict[str, Any]]:
    if target_start_frame and delta:
        raise ValidationError(
            "Provide exactly one of --to-start-frame or --delta.",
            details={"target_start_frame": target_start_frame, "delta": delta},
        )
    if not target_start_frame and not delta:
        if allow_unchanged:
            return int(current_start), {"mode": "track_only"}
        raise ValidationError(
            "Provide exactly one of --to-start-frame or --delta.",
            details={"target_start_frame": target_start_frame, "delta": delta},
        )
    timeline_start = timeline_item_duration_db._timeline_start_frame(conn)
    if target_start_frame:
        parsed = timeline_item_duration_db._target_record_frame(conn, str(target_start_frame))
        if timeline_start and int(current_start) < timeline_start <= int(parsed):
            parsed = int(parsed) - int(timeline_start)
        new_start = int(parsed)
        requested = {"mode": "target_start_frame", "target_start_frame": target_start_frame}
    else:
        delta_frames = _parse_signed_duration_frames(str(delta), conn.fps, allow_zero=allow_zero_delta)
        new_start = int(current_start) + int(delta_frames)
        requested = {"mode": "delta", "delta": delta, "delta_frames": int(delta_frames)}

    if new_start < 0:
        raise ValidationError("Timeline item move would place the item before frame 0.", details={"new_start": new_start})
    if timeline_start and int(current_start) >= timeline_start and new_start < timeline_start:
        raise ValidationError(
            "Timeline item move would place the item before the timeline start frame.",
            details={"new_start": new_start, "timeline_start_frame": timeline_start},
        )
    return new_start, requested


def _ranges_overlap(left_start: int, left_end: int, right_start: int, right_end: int) -> bool:
    return int(left_start) < int(right_end) and int(right_start) < int(left_end)


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


def _fetch_exact_db_row_for_live_target(
    cursor: sqlite3.Cursor,
    *,
    target: timeline_item_duration_db.TimelineItemDurationTarget,
    timeline_name: str,
) -> dict[str, Any]:
    if not target.item_id:
        return timeline_item_duration_db._fetch_db_row_for_live_target(
            cursor,
            target=target,
            timeline_name=timeline_name,
        )
    try:
        row = timeline_item_duration_db._fetch_db_row_by_item_id(
            cursor,
            item_id=str(target.item_id),
            timeline_name=timeline_name,
            track_type=target.track_type,
            track_index=target.track_index,
        )
    except (ClipNotFound, ValidationError) as exc:
        raise ValidationError(
            "The durable timeline-item identity could not be bound to the exact live target.",
            details={"track_type": target.track_type, "track_index": target.track_index},
        ) from exc
    row_start = timeline_item_duration_db._int_cell(row.get("Start"), field="Start")
    row_duration = _item_duration_frames(row.get("Duration"))
    row_track_index = timeline_item_duration_db._track_index_from_db_row(
        cursor,
        row=row,
        timeline_name=timeline_name,
        track_type=target.track_type,
    )
    expected_names = {str(value).lower() for value in (target.name, *target.aliases) if str(value or "").strip()}
    row_name = str(row.get("Name") or "")
    if (
        row_start != int(target.start)
        or row_duration != int(target.duration)
        or row_track_index != int(target.track_index)
        or (expected_names and row_name.lower() not in expected_names)
    ):
        raise ValidationError(
            "The durable timeline-item identity does not match the exact live target.",
            details={
                "track_type": target.track_type,
                "track_index": target.track_index,
                "record_start": target.start,
                "record_end": target.end,
                "name": target.name,
            },
        )
    return row


def _linked_video_companions(
    cursor: sqlite3.Cursor,
    *,
    target_row: dict[str, Any],
    timeline_name: str | None,
) -> list[dict[str, Any]]:
    if str(target_row.get("DbType") or "") != "Sm2TiAudioClip":
        return []
    name = str(target_row.get("Name") or "").strip()
    if not name:
        return []
    try:
        start = timeline_item_duration_db._int_cell(target_row.get("Start"), field="Start")
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
            track_rows = timeline_item_duration_db._timeline_track_ids(
                cursor,
                timeline_name=timeline_name,
                track_type="video",
                track_index=None,
            )
        except Exception:
            track_rows = []
        # If timeline scoping cannot prove video track ids, fall back to
        # same-name/start/duration matching rather than treating absence as proof.
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


def _live_linked_targets(
    conn: Any,
    item: Any,
    *,
    track_type: str,
    expected_count: int | None = None,
    expected_targets: list[dict[str, Any]] | None = None,
) -> list[timeline_item_duration_db.TimelineItemDurationTarget]:
    getter = getattr(item, "GetLinkedItems", None)
    if not callable(getter):
        raise ValidationError(
            "DaVinci Resolve cannot authoritatively inspect linked timeline items for this move.",
            details={"required_method": "TimelineItem.GetLinkedItems", "track_type": track_type},
        )
    try:
        linked_items = list(getter() or [])
    except Exception as exc:
        raise ValidationError(
            "DaVinci Resolve failed to inspect linked timeline items for this move.",
            details={"required_method": "TimelineItem.GetLinkedItems", "track_type": track_type, "error": str(exc)},
        ) from exc

    if expected_count is not None and len(linked_items) != expected_count:
        raise ValidationError(
            "Live linked-item topology does not match the exact SDK preview.",
            details={"expected_linked_count": expected_count, "actual_linked_count": len(linked_items)},
        )

    def durable_id(candidate: Any) -> str | None:
        unique_id_getter = getattr(candidate, "GetUniqueId", None)
        if not callable(unique_id_getter):
            return None
        try:
            return str(unique_id_getter() or "") or None
        except Exception:
            return None

    group_items = [item, *linked_items]
    group_durable_ids = [durable_id(candidate) for candidate in group_items]
    uses_durable_topology = all(group_durable_ids)
    group_identity = (
        set(group_durable_ids)
        if uses_durable_topology
        else {id(candidate) for candidate in group_items}
    )
    if len(group_identity) != len(linked_items) + 1:
        raise ValidationError(
            "DaVinci Resolve returned a duplicate member in the linked-item topology.",
            details={"linked_count": len(linked_items)},
        )

    targets: list[timeline_item_duration_db.TimelineItemDurationTarget] = []
    for linked_index, linked_item in enumerate(linked_items):
        linked_track_index = 0
        track_getter = getattr(linked_item, "GetTrackTypeAndIndex", None)
        if callable(track_getter):
            try:
                linked_track_type, linked_track_index = track_getter()
            except Exception as exc:
                raise ValidationError(
                    "DaVinci Resolve failed to classify a linked timeline item.",
                    details={"required_method": "TimelineItem.GetTrackTypeAndIndex", "track_type": track_type},
                ) from exc
            if str(linked_track_type or "").lower() != track_type:
                raise ValidationError(
                    "The linked group contains an unsupported timeline item type.",
                    details={"expected_track_type": track_type, "actual_track_type": str(linked_track_type or "") or None},
                )
        else:
            count_getter = getattr(conn.timeline, "GetTrackCount", None)
            track_count = int(count_getter(track_type) or 0) if callable(count_getter) else 0
            for candidate_index in range(1, track_count + 1):
                if any(candidate is linked_item for candidate in (conn.timeline.GetItemListInTrack(track_type, candidate_index) or [])):
                    linked_track_index = candidate_index
                    break
            if linked_track_index <= 0:
                raise ValidationError(
                    "DaVinci Resolve could not prove the track for a linked timeline item.",
                    details={"track_type": track_type},
                )
        reverse_getter = getattr(linked_item, "GetLinkedItems", None)
        if not callable(reverse_getter):
            raise ValidationError(
                "DaVinci Resolve cannot prove reciprocal linked-item topology for this move.",
                details={"required_method": "TimelineItem.GetLinkedItems", "track_type": track_type},
            )
        try:
            reverse_items = list(reverse_getter() or [])
        except Exception as exc:
            raise ValidationError(
                "DaVinci Resolve failed to inspect reciprocal linked-item topology for this move.",
                details={"required_method": "TimelineItem.GetLinkedItems", "track_type": track_type},
            ) from exc
        if uses_durable_topology:
            reverse_identity = {durable_id(reverse_item) for reverse_item in reverse_items}
            reciprocal = group_durable_ids[0] in reverse_identity and None not in reverse_identity
        else:
            reverse_identity = {id(reverse_item) for reverse_item in reverse_items}
            reciprocal = id(item) in reverse_identity
        if not reciprocal or not reverse_identity.issubset(group_identity):
            raise ValidationError(
                "The linked A/V topology is not reciprocal and closed.",
                details={"linked_count": len(linked_items), "reverse_linked_count": len(reverse_items)},
            )
        linked_item_id = group_durable_ids[linked_index + 1] if uses_durable_topology else durable_id(linked_item)
        target = timeline_item_duration_db._target_from_live_item(
            linked_item,
            track_type=track_type,
            track_index=int(linked_track_index),
            item_id=linked_item_id,
        )
        targets.append(target)
    if expected_targets is not None:
        try:
            expected_signatures = sorted(
                (
                    str(expected.get("id") or ""),
                    int(expected["trackIndex"]),
                    str(expected["name"]),
                    int(expected["recordStartFrame"]),
                    int(expected["recordEndFrame"]),
                )
                for expected in expected_targets
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValidationError("The exact SDK linked-item target precondition is malformed.") from exc
        actual_signatures = sorted(
            (
                str(target.item_id or ""),
                target.track_index,
                target.name,
                target.start,
                target.end,
            )
            for target in targets
        )
        if actual_signatures != expected_signatures:
            raise ValidationError(
                "Live linked-item targets do not match the exact SDK preview.",
                details={"expected_linked_count": len(expected_signatures), "actual_linked_count": len(actual_signatures)},
            )
    return targets


def _require_authoritatively_unlocked_tracks(conn: Any, tracks: list[tuple[str, int]]) -> None:
    getter = getattr(conn.timeline, "GetIsTrackLocked", None)
    if not callable(getter):
        raise ValidationError(
            "DaVinci Resolve did not expose authoritative track-lock state for this move.",
            details={"required_method": "Timeline.GetIsTrackLocked"},
        )
    for track_type, track_index in sorted(set(tracks)):
        try:
            locked = getter(track_type, int(track_index))
        except Exception as exc:
            raise ValidationError(
                "DaVinci Resolve failed to inspect an affected track lock before this move.",
                details={"track_type": track_type, "track_index": int(track_index)},
            ) from exc
        if not isinstance(locked, bool) or locked is not False:
            raise ValidationError(
                "Timeline item move requires authoritative unlocked state for every affected track.",
                details={"track_type": track_type, "track_index": int(track_index), "locked": locked if isinstance(locked, bool) else None},
            )


def _track_item_conflicts(
    cursor: sqlite3.Cursor,
    *,
    target_row: dict[str, Any],
    target_track_id: str | None,
    old_start: int,
    old_end: int,
    new_start: int,
    new_end: int,
    moving_item_ids: set[str] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    source_track_id = _track_id_from_row(target_row)
    destination_track_id = str(target_track_id or source_track_id)
    excluded_item_ids = set(moving_item_ids or ())
    excluded_item_ids.add(str(target_row.get("Sm2TiItem_id") or ""))
    clip_conflicts: list[dict[str, Any]] = []
    transition_conflicts: list[dict[str, Any]] = []
    track_ids = sorted({track_id for track_id in (source_track_id, destination_track_id) if track_id})
    for row in timeline_item_duration_db._fetch_item_rows_for_track_ids(cursor, track_ids=track_ids):
        item_id = str(row.get("Sm2TiItem_id") or "")
        if item_id in excluded_item_ids:
            continue
        row_track_id = _track_id_from_row(row)
        try:
            row_start = timeline_item_duration_db._int_cell(row.get("Start") or 0, field="Start")
            row_duration = timeline_item_duration_db._int_cell(row.get("Duration") or 0, field="Duration")
        except Exception:
            continue
        row_end = row_start + row_duration
        summary = {
            "item_id": item_id,
            "name": str(row.get("Name") or row.get("PrettyType") or ""),
            "db_type": str(row.get("DbType") or ""),
            "start": row_start,
            "end": row_end,
            "duration": row_duration,
            "track_id": row_track_id,
        }
        if str(row.get("DbType") or "") == "Sm2TiTransition":
            conflicts_source_range = row_track_id == source_track_id and _ranges_overlap(row_start, row_end, old_start, old_end)
            conflicts_destination_range = row_track_id == destination_track_id and _ranges_overlap(row_start, row_end, new_start, new_end)
            if conflicts_source_range or conflicts_destination_range:
                transition_conflicts.append(summary)
            continue
        if row_track_id == destination_track_id and _ranges_overlap(row_start, row_end, new_start, new_end):
            clip_conflicts.append(summary)
    return clip_conflicts, transition_conflicts


def _next_item_db_index(cursor: sqlite3.Cursor, *, target_track_id: str, item_id: str) -> int:
    rows = cursor.execute(
        """
        SELECT DbIndex
        FROM Sm2TiItem_Sm2TiTrack
        WHERE DbOwner = ? AND DbPropertyName = 'Items' AND DbAssociate != ?
        """,
        (target_track_id, item_id),
    ).fetchall()
    max_index = -1
    for row in rows:
        try:
            max_index = max(max_index, int(row[0]))
        except Exception:
            continue
    return max_index + 1


def _update_item_track_binding(cursor: sqlite3.Cursor, *, item_id: str, target_track_id: str) -> tuple[int, list[str]]:
    relation_rows = cursor.execute(
        """
        SELECT rowid, DbOwner, DbIndex
        FROM Sm2TiItem_Sm2TiTrack
        WHERE DbAssociate = ? AND DbPropertyName = 'Items'
        """,
        (item_id,),
    ).fetchall()
    if len(relation_rows) > 1:
        raise ValidationError(
            "Project.db item matched multiple track relation rows.",
            details={"item_id": item_id, "relation_count": len(relation_rows)},
        )
    next_index = _next_item_db_index(cursor, target_track_id=target_track_id, item_id=item_id)
    updated_columns = ["Sm2TiTrack_id"]
    db_timeline_rows.update_row(cursor, "Sm2TiItem", "Sm2TiItem_id", item_id, {"Sm2TiTrack_id": target_track_id})
    if relation_rows:
        cursor.execute(
            """
            UPDATE Sm2TiItem_Sm2TiTrack
            SET DbOwner = ?, DbIndex = ?
            WHERE rowid = ?
            """,
            (target_track_id, next_index, relation_rows[0][0]),
        )
        updated_columns.extend(["Sm2TiItem_Sm2TiTrack.DbOwner", "Sm2TiItem_Sm2TiTrack.DbIndex"])
    else:
        db_timeline_rows.insert_row(
            cursor,
            "Sm2TiItem_Sm2TiTrack",
            {"DbOwner": target_track_id, "DbAssociate": item_id, "DbPropertyName": "Items", "DbIndex": next_index},
        )
        updated_columns.extend(["Sm2TiItem_Sm2TiTrack.insert", "Sm2TiItem_Sm2TiTrack.DbIndex"])
    return next_index, updated_columns


def _normalize_track_item_indexes(cursor: sqlite3.Cursor, *, track_ids: set[str]) -> None:
    """Keep each track's persisted Items vector in record-order after a DB move."""
    for track_id in sorted(value for value in track_ids if value):
        rows = cursor.execute(
            """
            SELECT rel.rowid, rel.DbAssociate, rel.DbIndex, item.Start
            FROM Sm2TiItem_Sm2TiTrack rel
            JOIN Sm2TiItem item ON item.Sm2TiItem_id = rel.DbAssociate
            WHERE rel.DbOwner = ? AND rel.DbPropertyName = 'Items'
            ORDER BY CAST(item.Start AS INTEGER), CAST(rel.DbIndex AS INTEGER), rel.DbAssociate
            """,
            (track_id,),
        ).fetchall()
        if not rows:
            continue
        existing_indexes = [int(row[2]) for row in rows]
        temporary_base = max(existing_indexes) + len(rows) + 1
        for offset, row in enumerate(rows):
            cursor.execute(
                "UPDATE Sm2TiItem_Sm2TiTrack SET DbIndex = ? WHERE rowid = ?",
                (temporary_base + offset, row[0]),
            )
        for index, row in enumerate(rows):
            cursor.execute(
                "UPDATE Sm2TiItem_Sm2TiTrack SET DbIndex = ? WHERE rowid = ?",
                (index, row[0]),
            )


def _target_track_row(
    cursor: sqlite3.Cursor,
    *,
    timeline_name: str | None,
    track_type: str,
    track_index: int,
) -> dict[str, Any]:
    if not timeline_name:
        raise ValidationError(
            "Target track moves require an active or explicit timeline name.",
            details={"track_type": track_type, "track_index": track_index},
        )
    rows = timeline_item_duration_db._timeline_track_ids(
        cursor,
        timeline_name=timeline_name,
        track_type=track_type,
        track_index=track_index,
    )
    if len(rows) != 1:
        raise ValidationError(
            "Target timeline track was not found in Project.db.",
            details={"timeline": timeline_name, "track_type": track_type, "track_index": track_index, "match_count": len(rows)},
        )
    return rows[0]


def _apply_move_update(
    cursor: sqlite3.Cursor,
    *,
    target_row: dict[str, Any],
    new_start: int,
    allow_overlap: bool,
    allow_linked_audio_only: bool = False,
    include_linked_video: bool = False,
    allow_linked_video_only: bool = False,
    include_linked_audio: bool = False,
    linked_audio_rows: list[dict[str, Any]] | None = None,
    timeline_name: str | None = None,
    target_track_id: str | None = None,
    update_start: bool = True,
    linked_video_item_ids: list[str] | None = None,
    timeline_start_frame: int = 0,
    additional_moving_item_ids: set[str] | None = None,
    normalize_track_indexes: bool = True,
) -> dict[str, Any]:
    item_id = str(target_row.get("Sm2TiItem_id") or "")
    old_start = timeline_item_duration_db._int_cell(target_row.get("Start"), field="Start")
    duration = timeline_item_duration_db._int_cell(target_row.get("Duration"), field="Duration")
    source_in = timeline_item_duration_db._source_in_from_row(target_row)
    old_end = old_start + duration
    new_end = int(new_start) + duration
    old_track_id = _track_id_from_row(target_row)
    new_track_id = str(target_track_id or old_track_id)
    if duration <= 0:
        raise ValidationError("Timeline item move requires a positive item duration.", details={"item_id": item_id, "duration": duration})

    linked_video_companions = timeline_item_duration_db._linked_video_companions(
        cursor,
        target_row=target_row,
        timeline_name=timeline_name,
        item_ids=linked_video_item_ids,
    )
    if linked_video_companions and not allow_linked_audio_only and not include_linked_video:
        raise ValidationError(
            "Fairlight audio-only move would desynchronize a linked audio/video clip.",
            details={
                "item_id": item_id,
                "name": str(target_row.get("Name") or ""),
                "old_start": old_start,
                "old_end": old_end,
                "new_start": int(new_start),
                "new_end": new_end,
                "linked_video_companions": linked_video_companions,
                "precondition": "linked_av_audio_only_move_blocked",
                "available_native_readback": "cutagent fairlight clip linked list CLIP --json uses TimelineItem.GetLinkedItems(), but it does not expose track-type/group move semantics.",
                "override": "--allow-linked-audio-only",
                "live_evidence_artifact": "/tmp/cutagent_linked_clip_move_probe_20260620_065919/08_move_linked_audio_plus12.json",
                "db_blocker_note": (
                    "The verified Fairlight move route writes audio Sm2TiItem rows only. A live DaVinci Resolve 21 A/V probe "
                    "proved the linked video item stays in place, so linked A/V items are blocked unless the caller "
                    "explicitly opts into audio-only movement."
                ),
            },
        )
    linked_video_rows: list[dict[str, Any]] = []
    if linked_video_companions and include_linked_video:
        for companion in linked_video_companions:
            linked_video_rows.append(
                timeline_item_duration_db._fetch_db_row_by_item_id(
                    cursor,
                    item_id=str(companion["item_id"]),
                    timeline_name=timeline_name,
                    track_type="video",
                    track_index=None,
                )
            )

    exact_linked_audio_rows = list(linked_audio_rows or [])
    moves_record_position = update_start and int(new_start) != old_start
    if exact_linked_audio_rows and moves_record_position and not allow_linked_video_only and not include_linked_audio:
        raise ValidationError(
            "Video-only move would desynchronize an authoritatively linked audio/video clip.",
            details={
                "item_id": item_id,
                "linked_audio_item_ids": [str(row.get("Sm2TiItem_id") or "") for row in exact_linked_audio_rows],
                "precondition": "linked_av_video_only_move_blocked",
                "override": "--allow-linked-video-only",
            },
        )
    linked_audio_rows_to_move = exact_linked_audio_rows if include_linked_audio and moves_record_position else []
    moving_item_ids = {
        str(row.get("Sm2TiItem_id") or "")
        for row in [target_row, *linked_video_rows, *linked_audio_rows_to_move]
    }
    moving_item_ids.update(additional_moving_item_ids or set())

    clip_conflicts, transition_conflicts = _track_item_conflicts(
        cursor,
        target_row=target_row,
        target_track_id=new_track_id,
        old_start=old_start,
        old_end=old_end,
        new_start=int(new_start),
        new_end=new_end,
        moving_item_ids=moving_item_ids,
    )
    if transition_conflicts:
        raise ValidationError(
            "Timeline item move would leave or collide with Fairlight transition rows.",
            details={
                "item_id": item_id,
                "old_start": old_start,
                "old_end": old_end,
                "new_start": int(new_start),
                "new_end": new_end,
                "transition_conflicts": transition_conflicts,
                "hint": "Remove or recreate adjacent Fairlight transitions before moving this audio item.",
                **timeline_item_duration_db.fairlight_transition_adjacent_edit_blocker_evidence(
                    available_db_route=(
                        "Simple Fairlight audio-item move/nudge writes Sm2TiItem.Start and, for track moves, "
                        "Sm2TiItem.Sm2TiTrack_id plus Sm2TiItem_Sm2TiTrack binding rows with reopen/readback verification."
                    ),
                    supported_columns=["Sm2TiItem.Start", "Sm2TiItem.Sm2TiTrack_id", "Sm2TiItem_Sm2TiTrack.DbOwner", "Sm2TiItem_Sm2TiTrack.DbIndex"],
                    unsupported_operation="transition-aware Fairlight audio-item move or track move",
                ),
            },
        )
    if clip_conflicts and not allow_overlap:
        raise ValidationError(
            "Timeline item move would overlap another item on the same track.",
            details={
                "item_id": item_id,
                "new_start": int(new_start),
                "new_end": new_end,
                "conflicts": clip_conflicts,
                "hint": "Pass --allow-overlap only when overlapping items on this track is intended.",
            },
        )

    linked_video_updates: list[dict[str, Any]] = []
    linked_delta = int(new_start) - old_start
    for linked_row in linked_video_rows:
        linked_old_start = timeline_item_duration_db._int_cell(linked_row.get("Start"), field="Start")
        linked_duration = timeline_item_duration_db._int_cell(linked_row.get("Duration"), field="Duration")
        linked_source_in = timeline_item_duration_db._source_in_from_row(linked_row)
        linked_new_start = linked_old_start + linked_delta
        linked_new_end = linked_new_start + linked_duration
        if linked_new_start < 0:
            raise ValidationError(
                "Linked video companion move would place the item before frame 0.",
                details={
                    "item_id": str(linked_row.get("Sm2TiItem_id") or ""),
                    "old_start": linked_old_start,
                    "record_delta_frames": linked_delta,
                    "new_start": linked_new_start,
                    "precondition": "linked_av_video_record_before_zero_blocked",
                },
            )
        if timeline_start_frame and linked_old_start >= timeline_start_frame and linked_new_start < timeline_start_frame:
            raise ValidationError(
                "Linked video companion move would place the item before the timeline start frame.",
                details={
                    "item_id": str(linked_row.get("Sm2TiItem_id") or ""),
                    "old_start": linked_old_start,
                    "record_delta_frames": linked_delta,
                    "new_start": linked_new_start,
                    "timeline_start_frame": timeline_start_frame,
                    "precondition": "linked_av_video_record_before_timeline_start_blocked",
                },
            )
        linked_clip_conflicts, linked_transition_conflicts = _track_item_conflicts(
            cursor,
            target_row=linked_row,
            target_track_id=None,
            old_start=linked_old_start,
            old_end=linked_old_start + linked_duration,
            new_start=linked_new_start,
            new_end=linked_new_end,
            moving_item_ids=moving_item_ids,
        )
        if linked_transition_conflicts:
            raise ValidationError(
                "Linked video companion move would leave or collide with transition rows.",
                details={
                    "item_id": str(linked_row.get("Sm2TiItem_id") or ""),
                    "old_start": linked_old_start,
                    "old_end": linked_old_start + linked_duration,
                    "new_start": linked_new_start,
                    "new_end": linked_new_end,
                    "transition_conflicts": linked_transition_conflicts,
                    "precondition": "linked_av_video_transition_move_blocked",
                },
            )
        if linked_clip_conflicts and not allow_overlap:
            raise ValidationError(
                "Linked video companion move would overlap another item on the same video track.",
                details={
                    "item_id": str(linked_row.get("Sm2TiItem_id") or ""),
                    "new_start": linked_new_start,
                    "new_end": linked_new_end,
                    "conflicts": linked_clip_conflicts,
                    "hint": "Pass --allow-overlap only when overlapping items on this video track is intended.",
                    "precondition": "linked_av_video_overlap_blocked",
                },
            )
        linked_video_updates.append(
            {
                "row": linked_row,
                "old_start": linked_old_start,
                "duration": linked_duration,
                "source_in": linked_source_in,
                "new_start": linked_new_start,
                "new_end": linked_new_end,
            }
        )

    linked_audio_updates: list[dict[str, Any]] = []
    for linked_row in linked_audio_rows_to_move:
        linked_old_start = timeline_item_duration_db._int_cell(linked_row.get("Start"), field="Start")
        linked_duration = timeline_item_duration_db._int_cell(linked_row.get("Duration"), field="Duration")
        linked_source_in = timeline_item_duration_db._source_in_from_row(linked_row)
        linked_new_start = linked_old_start + linked_delta
        linked_new_end = linked_new_start + linked_duration
        linked_clip_conflicts, linked_transition_conflicts = _track_item_conflicts(
            cursor,
            target_row=linked_row,
            target_track_id=None,
            old_start=linked_old_start,
            old_end=linked_old_start + linked_duration,
            new_start=linked_new_start,
            new_end=linked_new_end,
            moving_item_ids=moving_item_ids,
        )
        if linked_transition_conflicts:
            raise ValidationError(
                "Linked audio companion move would leave or collide with Fairlight transition rows.",
                details={
                    "item_id": str(linked_row.get("Sm2TiItem_id") or ""),
                    "transition_conflicts": linked_transition_conflicts,
                    "precondition": "linked_av_audio_transition_move_blocked",
                },
            )
        if linked_clip_conflicts and not allow_overlap:
            raise ValidationError(
                "Linked audio companion move would overlap another item on the same audio track.",
                details={
                    "item_id": str(linked_row.get("Sm2TiItem_id") or ""),
                    "new_start": linked_new_start,
                    "new_end": linked_new_end,
                    "conflicts": linked_clip_conflicts,
                    "precondition": "linked_av_audio_overlap_blocked",
                },
            )
        linked_audio_updates.append({
            "row": linked_row,
            "old_start": linked_old_start,
            "duration": linked_duration,
            "source_in": linked_source_in,
            "new_start": linked_new_start,
            "new_end": linked_new_end,
        })

    updated_columns: list[str] = []
    if update_start:
        db_timeline_rows.update_row(cursor, "Sm2TiItem", "Sm2TiItem_id", item_id, {"Start": str(int(new_start))})
        updated_columns.append("Start")
    item_db_index = target_row.get("item_db_index")
    if new_track_id and new_track_id != old_track_id:
        item_db_index, track_columns = _update_item_track_binding(cursor, item_id=item_id, target_track_id=new_track_id)
        updated_columns.extend(track_columns)
    for update in linked_video_updates:
        db_timeline_rows.update_row(
            cursor,
            "Sm2TiItem",
            "Sm2TiItem_id",
            str(update["row"].get("Sm2TiItem_id") or ""),
            {"Start": str(int(update["new_start"]))},
        )
    for update in linked_audio_updates:
        db_timeline_rows.update_row(
            cursor,
            "Sm2TiItem",
            "Sm2TiItem_id",
            str(update["row"].get("Sm2TiItem_id") or ""),
            {"Start": str(int(update["new_start"]))},
        )
    if normalize_track_indexes:
        affected_track_ids = {old_track_id, new_track_id}
        affected_track_ids.update(_track_id_from_row(update["row"]) for update in linked_video_updates)
        affected_track_ids.update(_track_id_from_row(update["row"]) for update in linked_audio_updates)
        _normalize_track_item_indexes(cursor, track_ids=affected_track_ids)
        item_index_row = cursor.execute(
            """
            SELECT DbIndex FROM Sm2TiItem_Sm2TiTrack
            WHERE DbAssociate = ? AND DbOwner = ? AND DbPropertyName = 'Items'
            """,
            (item_id, new_track_id),
        ).fetchone()
        if item_index_row is not None:
            item_db_index = int(item_index_row[0])
    return {
        "item_id": item_id,
        "db_type": str(target_row.get("DbType") or ""),
        "name": str(target_row.get("Name") or ""),
        "track_id": new_track_id,
        "old_track_id": old_track_id,
        "new_track_id": new_track_id,
        "item_db_index": item_db_index,
        "old_start": old_start,
        "old_duration": duration,
        "old_end": old_end,
        "old_in": source_in,
        "new_start": int(new_start),
        "new_duration": duration,
        "new_end": new_end,
        "new_in": source_in,
        "updated_columns": updated_columns,
        "linked_video_updates": [
            {
                "item_id": str(update["row"].get("Sm2TiItem_id") or ""),
                "db_type": str(update["row"].get("DbType") or ""),
                "name": str(update["row"].get("Name") or ""),
                "track_id": _track_id_from_row(update["row"]),
                "old_start": int(update["old_start"]),
                "old_duration": int(update["duration"]),
                "old_end": int(update["old_start"]) + int(update["duration"]),
                "old_in": int(update["source_in"]),
                "new_start": int(update["new_start"]),
                "new_duration": int(update["duration"]),
                "new_end": int(update["new_end"]),
                "new_in": int(update["source_in"]),
                "updated_columns": ["Start"],
            }
            for update in linked_video_updates
        ],
        "linked_audio_updates": [
            {
                "item_id": str(update["row"].get("Sm2TiItem_id") or ""),
                "db_type": str(update["row"].get("DbType") or ""),
                "name": str(update["row"].get("Name") or ""),
                "track_id": _track_id_from_row(update["row"]),
                "old_start": int(update["old_start"]),
                "old_duration": int(update["duration"]),
                "old_end": int(update["old_start"]) + int(update["duration"]),
                "old_in": int(update["source_in"]),
                "new_start": int(update["new_start"]),
                "new_duration": int(update["duration"]),
                "new_end": int(update["new_end"]),
                "new_in": int(update["source_in"]),
                "updated_columns": ["Start"],
            }
            for update in linked_audio_updates
        ],
    }


def _verify_move_readback(fresh_conn: Any, mutation_result: dict[str, Any], _session: Any) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    db_checks: list[dict[str, Any]] = []
    matched_live_items: dict[str, Any] = {}
    for item in mutation_result.get("updated_items", []):
        track_type = str(item.get("track_type") or "video")
        track_index = int(item.get("track_index") or 1)
        expected_start = int(item.get("new_start") or 0)
        expected_end = int(item.get("new_end") or 0)
        expected_duration = int(item.get("new_duration") or 0)
        expected_names = {str(value) for value in item.get("readback_name_candidates", []) if str(value or "").strip()}
        expected_item_id = str(item.get("item_id") or "")
        stable_identity_required = bool(item.get("stable_identity_required"))
        timeline_start = timeline_item_duration_db._timeline_start_frame(fresh_conn)
        candidates = timeline_item_duration_db._readback_range_candidates(expected_start, expected_end, timeline_start)
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
            live_item_id = ""
            if stable_identity_required:
                unique_id_getter = getattr(live_item, "GetUniqueId", None)
                try:
                    live_item_id = str(unique_id_getter() or "") if callable(unique_id_getter) else ""
                except Exception:
                    live_item_id = ""
                if not expected_item_id or live_item_id != expected_item_id:
                    continue
            matches.append({"name": live_name, "start": live_start, "end": live_end, "duration": live_duration})
            if live_duration == expected_duration and (live_start, live_end) in candidates:
                item_id = expected_item_id
                topology_target_id = str((mutation_result.get("linked_audio_topology") or {}).get("target_item_id") or "")
                if item_id == topology_target_id:
                    unique_id_getter = getattr(live_item, "GetUniqueId", None)
                    try:
                        live_item_id = str(unique_id_getter() or "") if callable(unique_id_getter) else ""
                    except Exception:
                        live_item_id = ""
                    if live_item_id != topology_target_id:
                        continue
                matched_live_items[item_id] = live_item
        ok = any((row["start"], row["end"]) in candidates and row["duration"] == expected_duration for row in matches)
        checks.append(
            {
                "ok": ok,
                "item_id": item.get("item_id"),
                "expected": {
                    "start": expected_start,
                    "end": expected_end,
                    "duration": expected_duration,
                    "name_candidates": sorted(expected_names),
                },
                "matches": matches,
                "track_type": track_type,
                "track_index": track_index,
            }
        )
        expected_track_id = str(item.get("new_track_id") or "")
        if getattr(_session, "project_db_path", None):
            item_id = str(item.get("item_id") or "")
            try:
                db_conn = sqlite3.connect(str(_session.project_db_path))
                db_conn.row_factory = sqlite3.Row
                try:
                    rows = db_conn.execute(
                        """
                        SELECT
                            item.Sm2TiTrack_id,
                            item.Start,
                            item.Duration,
                            item."In" AS source_in,
                            rel.rowid AS relation_rowid,
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
                finally:
                    db_conn.close()
                if not rows:
                    db_checks.append({"ok": False, "item_id": item_id, "error": "Project.db item row was not found."})
                else:
                    relation_rows = [row for row in rows if row["relation_rowid"] is not None]
                    if len(relation_rows) != 1:
                        db_checks.append(
                            {
                                "ok": False,
                                "item_id": item_id,
                                "expected_track_id": expected_track_id,
                                "relation_count": len(relation_rows),
                                "error": "Project.db item must have exactly one Items track relation after move.",
                            }
                        )
                        continue
                    row = relation_rows[0]
                    db_track_id = str(row["Sm2TiTrack_id"] or "")
                    relation_track_id = str(row["relation_track_id"] or "")
                    relation_ok = relation_track_id == expected_track_id
                    db_start = timeline_item_duration_db._int_cell(row["Start"], field="Start")
                    db_duration = timeline_item_duration_db._int_cell(row["Duration"], field="Duration")
                    db_source_in = timeline_item_duration_db._source_in_from_row({"In": row["source_in"]})
                    expected_source_in = int(item.get("new_in") if item.get("new_in") is not None else item.get("old_in") or 0)
                    track_ok = not expected_track_id or (db_track_id == expected_track_id and relation_ok)
                    geometry_ok = db_start == expected_start and db_duration == expected_duration and db_source_in == expected_source_in
                    ok = track_ok and geometry_ok
                    db_checks.append(
                        {
                            "ok": ok,
                            "item_id": item_id,
                            "expected_track_id": expected_track_id,
                            "sm2ti_track_id": db_track_id,
                            "relation_track_id": relation_track_id,
                            "item_db_index": row["item_db_index"],
                            "expected_start": expected_start,
                            "start": db_start,
                            "expected_duration": expected_duration,
                            "duration": db_duration,
                            "expected_source_in": expected_source_in,
                            "source_in": db_source_in,
                        }
                    )
            except Exception as exc:
                db_checks.append({"ok": False, "item_id": item_id, "expected_track_id": expected_track_id, "error": str(exc)})
    protected_check = None
    if "protected_state_before" in mutation_result and _session is not None:
        protected_check = timeline_item_duration_db.verify_protected_timeline_edit_state(_session, mutation_result)
    native_link_check = None
    if mutation_result.get("native_link_identity") is not None:
        native_link_check = timeline_item_duration_db.verify_native_fairlight_link_state(fresh_conn, mutation_result, _session)
    topology = mutation_result.get("linked_audio_topology")
    topology_checks: list[dict[str, Any]] = []
    if isinstance(topology, dict):
        target_item_id = str(topology.get("target_item_id") or "")
        target_live_item = matched_live_items.get(target_item_id)
        expected_members = list(topology.get("members") or [])
        if target_live_item is None:
            topology_checks.append({"ok": False, "error": "Moved video item was unavailable for linked-topology verification."})
        else:
            try:
                actual_targets = _live_linked_targets(
                    fresh_conn,
                    target_live_item,
                    track_type="audio",
                    expected_count=len(expected_members),
                )
                expected_signatures = sorted(
                    (str(member.get("item_id") or ""), int(member["track_index"]), str(member["name"]), int(member["start"]), int(member["end"]))
                    for member in expected_members
                )
                actual_signatures = sorted(
                    (str(target.item_id or ""), target.track_index, target.name, target.start, target.end)
                    for target in actual_targets
                )
                topology_checks.append({
                    "ok": actual_signatures == expected_signatures,
                    "expected_members": expected_signatures,
                    "actual_members": actual_signatures,
                })
            except ValidationError as exc:
                topology_checks.append({"ok": False, "error": str(exc), "details": dict(exc.details or {})})
    all_checks = (
        checks
        + db_checks
        + topology_checks
        + ([protected_check] if protected_check is not None else [])
        + ([native_link_check] if native_link_check is not None else [])
    )
    return {
        "status": "verified" if all_checks and all(check["ok"] for check in all_checks) else "failed",
        "checks": checks,
        "db_checks": db_checks,
        "protected_state_check": protected_check,
        "native_link_check": native_link_check,
        "evidence_modalities": ["live_timeline_readback", "project_db_structural_readback", "TimelineItem.GetLinkedItems"],
        "topology_checks": topology_checks,
    }


def move_timeline_items(
    conn: Any,
    *,
    moves: list[dict[str, Any]],
    expected_moves: list[dict[str, Any]],
) -> dict[str, Any]:
    """Move multiple exact SDK video items in one DB transaction and one reopen."""
    if not moves or len(moves) > 100 or len(expected_moves) != len(moves):
        raise ValidationError("Plural timeline item move requires matching lists of 1 to 100 moves and private targets.")
    target_timeline = timeline_item_duration_db._timeline_name(conn)
    timeline_start_frame = timeline_item_duration_db._timeline_start_frame(conn)
    prepared: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for move, private in zip(moves, expected_moves):
        target_input = move.get("target") or {}
        destination = move.get("destination") or {}
        private_target = private.get("privateTarget") or {}
        private_linked = private.get("privateLinkedAudioTargets") or []
        try:
            track_index = timeline_ops.validate_timeline_track_index(int(target_input["trackIndex"]))
            target_track_index = timeline_ops.validate_timeline_track_index(int(destination["trackIndex"]))
            start = int(target_input["recordStartFrame"])
            end = int(target_input["recordEndFrame"])
            new_start = int(destination["recordStartFrame"])
            expected_id = str(private_target["id"])
            name = str(target_input["name"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValidationError("A plural timeline item move is malformed.") from exc
        if not expected_id or end <= start or expected_id in seen_ids:
            raise ValidationError("Plural timeline item moves require unique positive-duration private targets.")
        seen_ids.add(expected_id)
        live_target, live_item = timeline_item_duration_db._select_live_item(
            conn, track_type="video", track_index=track_index, start_ref=f"{start}f",
            current_end_ref=f"{end}f", name=name, expected_item_id=expected_id,
        )
        if live_target.item_id != expected_id or live_target.start != start or live_target.end != end:
            raise ValidationError("A live video item does not match its exact plural SDK preview.")
        if new_start == live_target.start and target_track_index == live_target.track_index:
            raise ValidationError("A plural timeline item move contains a no-op target.")
        linked = _live_linked_targets(
            conn, live_item, track_type="audio", expected_count=len(private_linked), expected_targets=private_linked,
        )
        include_linked = move.get("linkedAudio") == "preserve" and new_start != start
        affected = [("video", track_index), ("video", target_track_index)]
        if include_linked:
            affected.extend(("audio", item.track_index) for item in linked)
        _require_authoritatively_unlocked_tracks(conn, affected)
        prepared.append({
            "move": move, "target": live_target, "linked": linked, "new_start": new_start,
            "target_track_index": target_track_index, "include_linked": include_linked,
        })

    def _writer(_connection: sqlite3.Connection, cursor: sqlite3.Cursor, _session: db_session.DiskDbMutationSession) -> dict[str, Any]:
        rows: list[dict[str, Any]] = []
        all_moving_ids: set[str] = set()
        for entry in prepared:
            target_row = _fetch_exact_db_row_for_live_target(cursor, target=entry["target"], timeline_name=target_timeline or "")
            linked_rows = [_fetch_exact_db_row_for_live_target(cursor, target=item, timeline_name=target_timeline or "") for item in entry["linked"]]
            target_track = _target_track_row(cursor, timeline_name=target_timeline, track_type="video", track_index=entry["target_track_index"])
            rows.append({"target": target_row, "linked": linked_rows, "target_track_id": str(target_track["track_id"])})
            all_moving_ids.add(str(target_row.get("Sm2TiItem_id") or ""))
            if entry["include_linked"]:
                all_moving_ids.update(str(row.get("Sm2TiItem_id") or "") for row in linked_rows)

        final_ranges: list[dict[str, Any]] = []
        for entry, row_group in zip(prepared, rows):
            target = entry["target"]
            final_ranges.append({"id": target.item_id, "track": row_group["target_track_id"], "start": entry["new_start"], "end": entry["new_start"] + target.duration, "allow": entry["move"].get("collisionPolicy") == "allow"})
            if entry["include_linked"]:
                delta = entry["new_start"] - target.start
                for linked, linked_row in zip(entry["linked"], row_group["linked"]):
                    final_ranges.append({"id": linked.item_id, "track": _track_id_from_row(linked_row), "start": linked.start + delta, "end": linked.end + delta, "allow": entry["move"].get("collisionPolicy") == "allow"})
        for index, left in enumerate(final_ranges):
            for right in final_ranges[index + 1:]:
                if left["track"] == right["track"] and left["start"] < right["end"] and right["start"] < left["end"] and not (left["allow"] and right["allow"]):
                    raise ValidationError("The jointly evaluated plural move destinations overlap.", details={"item_ids": [left["id"], right["id"]]})

        updated_items: list[dict[str, Any]] = []
        for entry, row_group in zip(prepared, rows):
            target = entry["target"]
            update = _apply_move_update(
                cursor, target_row=row_group["target"], new_start=entry["new_start"],
                allow_overlap=entry["move"].get("collisionPolicy") == "allow",
                allow_linked_video_only=entry["move"].get("linkedAudio") == "exclude",
                include_linked_audio=entry["include_linked"], linked_audio_rows=row_group["linked"],
                timeline_name=target_timeline, target_track_id=row_group["target_track_id"],
                update_start=entry["new_start"] != target.start, timeline_start_frame=timeline_start_frame,
                additional_moving_item_ids=all_moving_ids,
                normalize_track_indexes=False,
            )
            update.update({
                "track_type": "video", "track_index": entry["target_track_index"],
                "source_track_index": target.track_index, "target_track_index": entry["target_track_index"],
                "selector": asdict(target), "readback_name_candidates": [target.name], "stable_identity_required": True,
            })
            updated_items.append(update)
            for linked, linked_update in zip(entry["linked"], update.get("linked_audio_updates", [])):
                updated_items.append({
                    **linked_update, "track_type": "audio", "track_index": linked.track_index,
                    "source_track_index": linked.track_index, "target_track_index": None,
                    "old_track_id": linked_update.get("track_id"), "new_track_id": linked_update.get("track_id"),
                    "selector": asdict(linked), "readback_name_candidates": [linked.name], "stable_identity_required": True,
                })
        affected_track_ids = {
            str(track_id)
            for item in updated_items
            for track_id in (item.get("old_track_id"), item.get("new_track_id"), item.get("track_id"))
            if str(track_id or "")
        }
        _normalize_track_item_indexes(cursor, track_ids=affected_track_ids)
        for item in updated_items:
            index_row = cursor.execute(
                """
                SELECT DbIndex FROM Sm2TiItem_Sm2TiTrack
                WHERE DbAssociate = ? AND DbOwner = ? AND DbPropertyName = 'Items'
                """,
                (str(item.get("item_id") or ""), str(item.get("new_track_id") or item.get("track_id") or "")),
            ).fetchone()
            if index_row is not None:
                item["item_db_index"] = int(index_row[0])
        return {"action": "timeline.items.move", "timeline_name": target_timeline, "updated_items": updated_items, "move_count": len(prepared), "route": "db_native_plural"}

    def _verified_or_raise(fresh_conn: Any, mutation_result: dict[str, Any], session: Any) -> dict[str, Any]:
        verification = _verify_move_readback(fresh_conn, mutation_result, session)
        if verification.get("status") != "verified":
            raise APICallFailed("Plural timeline item move did not match native post-reopen readback.", details={"verification_status": verification.get("status")})
        return verification

    try:
        result = db_session.execute_sqlite_disk_db_mutation(
            conn, context="DB-backed plural timeline item move", writer=_writer,
            verifier=_verified_or_raise, allow_project_name_inference=True,
        )
    except APICallFailed as exc:
        details = dict(getattr(exc, "details", {}) or {})
        if details.get("reason") != "db_mutation_post_commit_failure":
            raise
        recovery = details.get("recovery") if isinstance(details.get("recovery"), dict) else {}
        restored = bool(recovery.get("rollback_performed")) and "reopen_project_after_rollback" in list(recovery.get("rollback_steps") or [])
        if restored:
            raise EditMutationRestored("Plural timeline item move failed verification and the original project state was restored.") from exc
        raise EditMutationRecoveryFailed("Plural timeline item move failed verification and recovery could not be proved.") from exc
    return result


def move_timeline_item(
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
    delta: str | None = None,
    target_track_index: int | None = None,
    allow_overlap: bool = False,
    allow_linked_audio_only: bool = False,
    include_linked_video: bool = False,
    require_fairlight_edit_contract: bool = False,
    allow_linked_video_only: bool = False,
    include_linked_audio: bool = False,
    expected_target: dict[str, Any] | None = None,
    expected_linked_audio_count: int | None = None,
    expected_linked_audio_targets: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Move one timeline item start frame using the Disk Project.db route."""
    normalized_track_type = timeline_item_duration_db._normalize_selector_track_type(track_type)
    normalized_track_index = timeline_ops.validate_timeline_track_index(track_index)
    normalized_target_track_index = timeline_ops.validate_timeline_track_index(target_track_index) if target_track_index is not None else None
    if timeline_name:
        timeline_ops.switch_timeline(conn, name=timeline_name)
    target_timeline = timeline_item_duration_db._timeline_name(conn)
    timeline_start_frame = timeline_item_duration_db._timeline_start_frame(conn)

    expected_target_id = None
    if expected_target is not None:
        try:
            expected_target_id = str(expected_target["id"] or "")
            expected_track_index = int(expected_target["trackIndex"])
            expected_name = str(expected_target["name"])
            expected_start = int(expected_target["recordStartFrame"])
            expected_end = int(expected_target["recordEndFrame"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValidationError("The exact SDK video-item target precondition is malformed.") from exc
        if not expected_target_id or expected_track_index != normalized_track_index or expected_end <= expected_start:
            raise ValidationError("The exact SDK video-item target precondition is malformed.")

    live_target = None
    live_item = None
    linked_audio_targets: list[timeline_item_duration_db.TimelineItemDurationTarget] = []
    if not item_id:
        live_target, live_item = timeline_item_duration_db._select_live_item(
            conn,
            track_type=normalized_track_type,
            track_index=normalized_track_index,
            start_ref=start_frame,
            current_end_ref=current_end_frame,
            name=name,
            expected_item_id=expected_target_id,
        )
        if expected_target is not None:
            expected_start_candidates = timeline_item_duration_db._frame_candidates(conn, f"{expected_start}f")
            expected_end_candidates = timeline_item_duration_db._frame_candidates(conn, f"{expected_end}f")
            if (
                live_target.item_id != expected_target_id
                or live_target.track_index != expected_track_index
                or live_target.name != expected_name
                or live_target.start not in expected_start_candidates
                or live_target.end not in expected_end_candidates
            ):
                raise ValidationError("The live video item does not match the exact SDK preview.")
        new_start, requested = _resolve_new_start(
            conn,
            current_start=live_target.start,
            target_start_frame=target_start_frame,
            delta=delta,
            allow_unchanged=normalized_target_track_index is not None,
            allow_zero_delta=require_fairlight_edit_contract,
        )
        if normalized_track_type == "video":
            linked_audio_targets = _live_linked_targets(
                conn,
                live_item,
                track_type="audio",
                expected_count=expected_linked_audio_count,
                expected_targets=expected_linked_audio_targets,
            )
    else:
        if normalized_track_type == "video":
            raise ValidationError(
                "Video item-id moves cannot prove linked-audio topology and track locks; use the exact live track/range selector.",
                details={"item_id": item_id, "required_selector": ["track_index", "start_frame", "current_end_frame", "name"]},
            )
        if start_frame or current_end_frame or name:
            raise ValidationError(
                "--item-id is mutually exclusive with --start-frame, --current-end-frame, and --name.",
                details={"item_id": item_id, "start_frame": start_frame, "current_end_frame": current_end_frame, "name": name},
            )
        new_start = -1
        requested = {"mode": "pending_db_row"}

    edit_identity: dict[str, Any] | None = None
    fairlight_lock_targets: tuple[tuple[str, int, str], ...] | None = None
    fairlight_timeline_identity: timeline_item_duration_db.FairlightEditTimelineIdentity | None = None
    if require_fairlight_edit_contract:
        if live_target is None:
            live_target = timeline_item_duration_db._read_item_id_target_before_db_close(
                conn,
                item_id=str(item_id),
                timeline_name=target_timeline,
                track_type="audio",
            )
            _selected_target, live_item = timeline_item_duration_db._select_live_item(
                conn,
                track_type=live_target.track_type,
                track_index=live_target.track_index,
                start_ref=f"{live_target.start}f",
                current_end_ref=f"{live_target.end}f",
                name=live_target.name or None,
            )
        assert live_item is not None
        edit_identity = timeline_item_duration_db.prepare_fairlight_clip_edit_identity(
            conn,
            target=live_target,
            live_item=live_item,
            timeline_name=target_timeline,
        )

    if live_target is not None and requested.get("mode") == "pending_db_row":
        new_start, requested = _resolve_new_start(
            conn,
            current_start=live_target.start,
            target_start_frame=target_start_frame,
            delta=delta,
            allow_unchanged=normalized_target_track_index is not None,
            allow_zero_delta=require_fairlight_edit_contract,
        )
    if (
        live_target is not None
        and int(new_start) == int(live_target.start)
        and (normalized_target_track_index is None or normalized_target_track_index == live_target.track_index)
    ):
        if require_fairlight_edit_contract:
            assert edit_identity is not None
            is_zero_delta = requested.get("mode") == "delta" and int(requested.get("delta_frames", 0)) == 0
            return timeline_item_duration_db.fairlight_clip_edit_no_change(
                action="fairlight.clip.nudge" if is_zero_delta else "fairlight.clip.move",
                timeline_name=target_timeline,
                target=live_target,
                requested=requested,
                plan=edit_identity,
                reason=(
                    "fairlight_clip_nudge_zero_no_change"
                    if is_zero_delta
                    else "fairlight_clip_move_absolute_no_change"
                ),
            )
        raise ValidationError(
            "Timeline item move would not change the item start or track.",
            details={
                "reason": "timeline_item_move_no_change",
                "item_id": live_target.item_id,
                "current_start": live_target.start,
                "requested_start": int(new_start),
                "current_track_index": live_target.track_index,
                "requested_track_index": normalized_target_track_index,
                "possible_mutation": False,
                "hint": "Choose a different destination track or request a non-zero record-position change.",
            },
        )
    if require_fairlight_edit_contract and edit_identity is not None:
        assert live_target is not None
        fairlight_lock_targets = timeline_item_duration_db.fairlight_edit_track_lock_targets(
            target=live_target,
            plan=edit_identity,
            destination_audio_track_index=normalized_target_track_index,
        )
        fairlight_timeline_identity = timeline_item_duration_db.require_fairlight_edit_timeline_identity(conn)
        timeline_item_duration_db.require_fairlight_edit_tracks_unlocked(
            conn,
            target=live_target,
            plan=edit_identity,
            destination_audio_track_index=normalized_target_track_index,
            track_targets=fairlight_lock_targets,
        )

    def _writer(_connection: sqlite3.Connection, cursor: sqlite3.Cursor, _session: db_session.DiskDbMutationSession) -> dict[str, Any]:
        nonlocal new_start, requested
        linked_video_item_ids: list[str] | None = None
        if edit_identity is not None:
            row, linked_video_item_ids, _linked_source_bounds = timeline_item_duration_db.assert_fairlight_clip_edit_identity(
                cursor,
                plan=edit_identity,
                timeline_name=target_timeline,
            )
            row_start = timeline_item_duration_db._int_cell(row.get("Start"), field="Start")
            new_start, requested = _resolve_new_start(
                conn,
                current_start=row_start,
                target_start_frame=target_start_frame,
                delta=delta,
                allow_unchanged=normalized_target_track_index is not None,
            )
            result_target = timeline_item_duration_db._target_from_db_row(
                cursor,
                row=row,
                item_id=str(edit_identity["target_item_id"]),
                timeline_name=target_timeline,
                fallback_track_type="audio",
            )
        elif item_id:
            row = timeline_item_duration_db._fetch_db_row_by_item_id(
                cursor,
                item_id=str(item_id),
                timeline_name=target_timeline,
                track_type=normalized_track_type if track_type else None,
                track_index=None,
            )
            row_start = timeline_item_duration_db._int_cell(row.get("Start"), field="Start")
            new_start, requested = _resolve_new_start(
                conn,
                current_start=row_start,
                target_start_frame=target_start_frame,
                delta=delta,
                allow_unchanged=normalized_target_track_index is not None,
            )
            result_target = timeline_item_duration_db.TimelineItemDurationTarget(
                item_id=str(item_id),
                track_type=timeline_item_duration_db._track_type_from_db_row(row, normalized_track_type),
                track_index=timeline_item_duration_db._track_index_from_db_row(cursor, row=row, timeline_name=target_timeline, track_type=normalized_track_type),
                name=str(row.get("Name") or ""),
                start=row_start,
                duration=timeline_item_duration_db._int_cell(row.get("Duration"), field="Duration"),
                end=row_start + timeline_item_duration_db._int_cell(row.get("Duration"), field="Duration"),
            )
        else:
            assert live_target is not None
            row = _fetch_exact_db_row_for_live_target(cursor, target=live_target, timeline_name=target_timeline or "")
            result_target = live_target

        target_track = (
            _target_track_row(
                cursor,
                timeline_name=target_timeline,
                track_type=normalized_track_type,
                track_index=normalized_target_track_index,
            )
            if normalized_target_track_index is not None
            else None
        )
        target_track_id = str(target_track["track_id"]) if target_track else None
        linked_audio_rows = [
            _fetch_exact_db_row_for_live_target(
                cursor,
                target=target,
                timeline_name=target_timeline or "",
            )
            for target in linked_audio_targets
        ]
        if normalized_target_track_index is not None:
            requested = {
                **requested,
                "target_track_index": normalized_target_track_index,
                "move_track": True,
                "move_start": requested.get("mode") != "track_only",
            }
        requested = {
            **requested,
            "include_linked_video": bool(include_linked_video),
            "allow_linked_audio_only": bool(allow_linked_audio_only),
            "allow_linked_video_only": bool(allow_linked_video_only),
            "include_linked_audio": bool(include_linked_audio),
        }
        protected_state_before = (
            timeline_item_duration_db.capture_timeline_edit_structural_state(
                cursor,
                timeline_name=target_timeline,
            )
            if require_fairlight_edit_contract
            else None
        )
        updated = _apply_move_update(
            cursor,
            target_row=row,
            new_start=int(new_start),
            allow_overlap=allow_overlap,
            allow_linked_audio_only=allow_linked_audio_only,
            include_linked_video=include_linked_video,
            allow_linked_video_only=allow_linked_video_only,
            include_linked_audio=include_linked_audio,
            linked_audio_rows=linked_audio_rows,
            timeline_name=target_timeline,
            target_track_id=target_track_id,
            update_start=requested.get("mode") != "track_only",
            linked_video_item_ids=linked_video_item_ids,
            timeline_start_frame=timeline_start_frame,
        )
        readback_track_index = normalized_target_track_index if normalized_target_track_index is not None else result_target.track_index
        updated.update(
            {
                "track_type": result_target.track_type,
                "track_index": readback_track_index,
                "source_track_index": result_target.track_index,
                "target_track_index": normalized_target_track_index,
                "selector": asdict(result_target),
                "readback_name_candidates": sorted(
                    {
                        str(value)
                        for value in (updated.get("name"), result_target.name, *result_target.aliases)
                        if str(value or "").strip()
                    }
                ),
                "stable_identity_required": expected_target is not None,
            }
        )
        linked_video_items: list[dict[str, Any]] = []
        for linked in updated.get("linked_video_updates", []):
            linked_track_index = timeline_item_duration_db._track_index_from_db_row(
                cursor,
                row={"relation_track_id": linked.get("track_id")},
                timeline_name=target_timeline,
                track_type="video",
            )
            linked_video_items.append(
                {
                    **linked,
                    "track_type": "video",
                    "track_index": linked_track_index,
                    "source_track_index": linked_track_index,
                    "target_track_index": None,
                    "old_track_id": linked.get("track_id"),
                    "new_track_id": linked.get("track_id"),
                    "item_db_index": None,
                    "selector": {
                        "item_id": linked.get("item_id"),
                        "track_type": "video",
                        "track_index": linked_track_index,
                        "name": linked.get("name"),
                        "start": linked.get("old_start"),
                        "duration": linked.get("old_duration"),
                        "end": linked.get("old_end"),
                    },
                    "readback_name_candidates": [str(linked.get("name") or "")],
                    "linked_from_audio_item_id": updated.get("item_id"),
                }
            )
        linked_audio_items: list[dict[str, Any]] = []
        for linked in updated.get("linked_audio_updates", []):
            linked_track_index = timeline_item_duration_db._track_index_from_db_row(
                cursor,
                row={"relation_track_id": linked.get("track_id")},
                timeline_name=target_timeline,
                track_type="audio",
            )
            linked_audio_items.append({
                **linked,
                "track_type": "audio",
                "track_index": linked_track_index,
                "source_track_index": linked_track_index,
                "target_track_index": None,
                "old_track_id": linked.get("track_id"),
                "new_track_id": linked.get("track_id"),
                "item_db_index": None,
                "selector": {
                    "item_id": linked.get("item_id"),
                    "track_type": "audio",
                    "track_index": linked_track_index,
                    "name": linked.get("name"),
                    "start": linked.get("old_start"),
                    "duration": linked.get("old_duration"),
                    "end": linked.get("old_end"),
                },
                "readback_name_candidates": [str(linked.get("name") or "")],
                "linked_from_video_item_id": updated.get("item_id"),
                "stable_identity_required": expected_linked_audio_targets is not None,
            })
        linked_delta = int(new_start) - int(result_target.start) if include_linked_audio else 0
        result = {
            "action": "timeline.items.move",
            "timeline_name": target_timeline,
            "requested": requested,
            "allow_overlap": bool(allow_overlap),
            "updated_items": [updated, *linked_video_items, *linked_audio_items],
            "linked_video_included": bool(linked_video_items),
            "native_link_identity": edit_identity,
            "linked_audio_included": bool(linked_audio_items),
            "linked_audio_topology": {
                "target_item_id": updated.get("item_id"),
                "members": [
                    {
                        "item_id": target.item_id,
                        "track_index": target.track_index,
                        "name": target.name,
                        "start": target.start + linked_delta,
                        "end": target.end + linked_delta,
                    }
                    for target in linked_audio_targets
                ],
            },
        }
        if protected_state_before is not None:
            result["protected_state_before"] = protected_state_before
        return result

    if normalized_track_type == "video":
        assert live_target is not None
        affected_tracks = [("video", normalized_track_index)]
        if normalized_target_track_index is not None:
            affected_tracks.append(("video", normalized_target_track_index))
        if include_linked_audio and int(new_start) != int(live_target.start):
            affected_tracks.extend(("audio", target.track_index) for target in linked_audio_targets)
        _require_authoritatively_unlocked_tracks(conn, affected_tracks)

    def _verified_or_raise(fresh_conn: Any, mutation_result: dict[str, Any], session: Any) -> dict[str, Any]:
        verification = _verify_move_readback(fresh_conn, mutation_result, session)
        if verification.get("status") != "verified":
            verification_checks = [
                *verification.get("checks", []),
                *verification.get("db_checks", []),
                *verification.get("topology_checks", []),
            ]
            raise APICallFailed(
                "Timeline item move did not match native post-reopen readback.",
                details={"verification_status": verification.get("status"), "failed_checks": sum(1 for check in verification_checks if not check.get("ok"))},
            )
        return verification

    try:
        result = db_session.execute_sqlite_disk_db_mutation(
            conn,
            context="DB-backed timeline item move",
            writer=_writer,
            verifier=_verified_or_raise,
            pre_close_validator=(
                timeline_item_duration_db.fairlight_edit_pre_close_validator(
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
        )
    except APICallFailed as exc:
        details = dict(getattr(exc, "details", {}) or {})
        if details.get("reason") != "db_mutation_post_commit_failure":
            raise
        recovery = details.get("recovery") if isinstance(details.get("recovery"), dict) else {}
        rollback_steps = list(recovery.get("rollback_steps") or [])
        restored = bool(recovery.get("rollback_performed")) and "reopen_project_after_rollback" in rollback_steps
        if target_timeline:
            restored = restored and "restore_timeline_after_rollback" in rollback_steps
        safe_details = {"reason": "timeline_item_move_post_commit_verification_failed", "failure_step": details.get("failure_step"), "recovery_state": "restored" if restored else "failed"}
        if restored:
            raise EditMutationRestored("Timeline item move failed verification and the original project state was restored.", details=safe_details) from exc
        raise EditMutationRecoveryFailed("Timeline item move failed verification and recovery could not be proved.", details=safe_details) from exc
    verification = result.get("verification") if isinstance(result, dict) else None
    if isinstance(verification, dict) and verification.get("status") != "verified":
        raise APICallFailed(
            "Timeline item move DB write did not verify after DaVinci Resolve reopened the project.",
            details={"mutation": result, "verification": verification},
        )
    return result
