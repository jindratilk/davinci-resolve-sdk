"""Disk DB delete-through-edit merge helpers."""

from __future__ import annotations

import sqlite3
from typing import Any

from ..errors import APICallFailed, ValidationError
from ..utils.timecode import frames_to_timecode
from . import db_session, db_timeline_rows
from .db_timeline_selection import LiveItemRef


def _timeline_name(conn: Any) -> str | None:
    timeline = getattr(conn, "timeline", None)
    if timeline is None:
        return None
    try:
        return str(timeline.GetName() or "")
    except Exception:
        return None


def _item_ref(item: Any, *, track_type: str, track_index: int) -> LiveItemRef:
    name = str(item.GetName() or "")
    start = int(item.GetStart())
    end = int(item.GetEnd())
    aliases: tuple[str, ...] = ()
    try:
        from . import clip_ops

        aliases = tuple(sorted(clip_ops._item_name_candidates(item)))  # type: ignore[attr-defined]
    except Exception:
        aliases = ()
    return LiveItemRef(
        track_type=track_type,
        track_index=int(track_index),
        name=name,
        start=start,
        duration=max(0, end - start),
        aliases=aliases,
    )


def _db_type(track_type: str) -> str:
    return "Sm2TiAudioClip" if track_type == "audio" else "Sm2TiVideoClip"


def _as_int(row: dict[str, Any], key: str, default: int = 0) -> int:
    try:
        return int(float(str(row.get(key, default))))
    except Exception:
        return int(default)


def _row_for_ref(
    cursor: sqlite3.Cursor,
    *,
    item_ref: LiveItemRef,
    db_type: str,
    timeline_name: str | None,
) -> dict[str, Any]:
    return db_timeline_rows.find_ti_item_row(
        cursor,
        item=item_ref,
        db_type=db_type,
        timeline_name=timeline_name,
    )


def _optional_row_for_ref(
    cursor: sqlite3.Cursor,
    *,
    item_ref: LiveItemRef,
    db_type: str,
    timeline_name: str | None,
) -> dict[str, Any] | None:
    try:
        return _row_for_ref(cursor, item_ref=item_ref, db_type=db_type, timeline_name=timeline_name)
    except ValidationError as exc:
        if getattr(exc, "details", {}).get("match_count") == 0:
            return None
        raise


def _track_relation(cursor: sqlite3.Cursor, *, item_id: str, track_id: str | None) -> sqlite3.Row | None:
    if track_id:
        row = cursor.execute(
            """
            SELECT rowid, DbOwner, DbAssociate, DbIndex
            FROM Sm2TiItem_Sm2TiTrack
            WHERE DbAssociate = ? AND DbOwner = ? AND DbPropertyName = 'Items'
            """,
            (item_id, track_id),
        ).fetchone()
        if row:
            return row
    return cursor.execute(
        """
        SELECT rowid, DbOwner, DbAssociate, DbIndex
        FROM Sm2TiItem_Sm2TiTrack
        WHERE DbAssociate = ? AND DbPropertyName = 'Items'
        ORDER BY DbIndex LIMIT 1
        """,
        (item_id,),
    ).fetchone()


def _validate_db_pair(
    *,
    left_row: dict[str, Any],
    right_row: dict[str, Any],
    boundary: int,
) -> None:
    left_start = _as_int(left_row, "Start")
    left_duration = _as_int(left_row, "Duration")
    right_start = _as_int(right_row, "Start")
    right_duration = _as_int(right_row, "Duration")
    left_boundary = left_start + left_duration
    if (left_boundary != boundary and left_boundary + 1 != boundary) or right_start != boundary:
        raise ValidationError(
            "Project.db through-edit rows do not match the resolved timeline boundary.",
            details={
                "boundary": boundary,
                "left": {"start": left_start, "duration": left_duration},
                "right": {"start": right_start, "duration": right_duration},
            },
            recoverability="not_applicable",
        )
    left_in = _as_int(left_row, "In")
    right_in = _as_int(right_row, "In")
    left_source_boundary = left_in + left_duration
    if left_source_boundary != right_in and left_source_boundary + 1 != right_in:
        raise ValidationError(
            "Edit point is not a through edit: Project.db source ranges are not contiguous.",
            details={
                "boundary": boundary,
                "left_source_end": left_source_boundary,
                "right_source_start": right_in,
            },
            recoverability="not_applicable",
        )


def _merge_rows(
    cursor: sqlite3.Cursor,
    *,
    left_row: dict[str, Any],
    right_row: dict[str, Any],
) -> dict[str, Any]:
    left_id = str(left_row["Sm2TiItem_id"])
    right_id = str(right_row["Sm2TiItem_id"])
    track_id = str(left_row.get("Sm2TiTrack_id") or "")
    right_track_id = str(right_row.get("Sm2TiTrack_id") or "")
    if track_id and right_track_id and track_id != right_track_id:
        raise ValidationError(
            "Through-edit halves resolved to different Project.db tracks.",
            details={"left_track_id": track_id, "right_track_id": right_track_id},
            recoverability="not_applicable",
        )

    left_duration = _as_int(left_row, "Duration")
    right_duration = _as_int(right_row, "Duration")
    merged_duration = left_duration + right_duration
    updates: dict[str, Any] = {
        "Duration": str(merged_duration),
    }
    if "End" in left_row:
        updates["End"] = str(_as_int(left_row, "Start") + merged_duration)
    db_timeline_rows.update_row(cursor, "Sm2TiItem", "Sm2TiItem_id", left_id, updates)
    cursor.execute("DELETE FROM Sm2TiItem_Sm2TiTrack WHERE DbAssociate = ?", (right_id,))
    cursor.execute("DELETE FROM Sm2TiItem WHERE Sm2TiItem_id = ?", (right_id,))
    if track_id:
        db_session.rebuild_track_item_indices(cursor, track_id=track_id)
    return {
        "left_item_id": left_id,
        "right_item_id": right_id,
        "track_id": track_id or None,
        "merged_duration": merged_duration,
        "deleted_item_ids": [right_id],
    }


def delete_through_edit_at(
    conn: Any,
    position: str,
    *,
    track_type: str = "video",
    track_index: int = 0,
    tolerance_frames: int = 0,
) -> dict[str, Any]:
    if tolerance_frames < 0:
        raise ValidationError(
            "Tolerance must be zero or greater.",
            details={"tolerance_frames": tolerance_frames},
            recoverability="not_applicable",
        )

    from . import edit_ops

    frame = edit_ops._record_frame_position(conn, position)  # type: ignore[attr-defined]
    resolved = edit_ops._resolve_through_edit_pair(  # type: ignore[attr-defined]
        conn,
        frame,
        track_type,
        track_index,
        tolerance_frames=tolerance_frames,
    )
    boundary = int(resolved["boundary"])
    ttype = str(resolved["track_type"])
    tidx = int(resolved["track_index"])
    left_info = dict(resolved["left_info"])
    right_info = dict(resolved["right_info"])
    selection = dict(resolved["selection"])
    timeline_name = _timeline_name(conn)
    left_ref = _item_ref(resolved["left"], track_type=ttype, track_index=tidx)
    right_ref = _item_ref(resolved["right"], track_type=ttype, track_index=tidx)

    linked_track_type = "audio" if ttype == "video" else "video"
    linked_left_ref = LiveItemRef(
        track_type=linked_track_type,
        track_index=tidx,
        name=left_ref.name,
        start=left_ref.start,
        duration=left_ref.duration,
        aliases=left_ref.aliases,
    )
    linked_right_ref = LiveItemRef(
        track_type=linked_track_type,
        track_index=tidx,
        name=right_ref.name,
        start=right_ref.start,
        duration=right_ref.duration,
        aliases=right_ref.aliases,
    )

    def writer(_connection: Any, cursor: sqlite3.Cursor, session: db_session.DiskDbMutationSession) -> dict[str, Any]:
        left_row = _row_for_ref(
            cursor,
            item_ref=left_ref,
            db_type=_db_type(ttype),
            timeline_name=timeline_name,
        )
        right_row = _row_for_ref(
            cursor,
            item_ref=right_ref,
            db_type=_db_type(ttype),
            timeline_name=timeline_name,
        )
        _validate_db_pair(left_row=left_row, right_row=right_row, boundary=boundary)
        pre_count = cursor.execute(
            "SELECT COUNT(*) FROM Sm2TiItem WHERE Sm2TiTrack_id = ?",
            (left_row.get("Sm2TiTrack_id"),),
        ).fetchone()[0]
        mutation = _merge_rows(cursor, left_row=left_row, right_row=right_row)
        session.steps.append("merge_through_edit_rows")

        linked_merges: list[dict[str, Any]] = []
        linked_left_row = _optional_row_for_ref(
            cursor,
            item_ref=linked_left_ref,
            db_type=_db_type(linked_track_type),
            timeline_name=timeline_name,
        )
        linked_right_row = _optional_row_for_ref(
            cursor,
            item_ref=linked_right_ref,
            db_type=_db_type(linked_track_type),
            timeline_name=timeline_name,
        )
        if bool(linked_left_row) != bool(linked_right_row):
            raise ValidationError(
                "Through-edit linked audio/video halves are incomplete in Project.db.",
                details={
                    "linked_track_type": linked_track_type,
                    "left_found": bool(linked_left_row),
                    "right_found": bool(linked_right_row),
                },
                recoverability="not_applicable",
            )
        if linked_left_row and linked_right_row:
            _validate_db_pair(left_row=linked_left_row, right_row=linked_right_row, boundary=boundary)
            linked_merges.append(_merge_rows(cursor, left_row=linked_left_row, right_row=linked_right_row))
            session.steps.append("merge_linked_through_edit_rows")

        return {
            "action": "delete_through_edit",
            "edit_frame": boundary,
            "edit_tc": frames_to_timecode(boundary, getattr(conn, "fps", 24.0)),
            "track_type": ttype,
            "track_index": tidx,
            "selection": selection,
            "removed": [
                {
                    "name": left_info.get("name"),
                    "record_start": left_info["start"],
                    "record_end": left_info["end"],
                    "source_start": left_info["source_start"],
                    "source_end": left_info["source_end"],
                },
                {
                    "name": right_info.get("name"),
                    "record_start": right_info["start"],
                    "record_end": right_info["end"],
                    "source_start": right_info["source_start"],
                    "source_end": right_info["source_end"],
                },
            ],
            "merged": {
                "record_start": left_info["start"],
                "record_end": right_info["end"],
                "source_start": left_info["source_start"],
                "source_end": right_info["source_end"],
            },
            "db_merge": mutation,
            "linked_db_merges": linked_merges,
            "pre_item_count": int(pre_count),
            "expected_post_item_count": max(0, int(pre_count) - 1),
        }

    def verifier(_fresh_conn: Any, mutation_result: dict[str, Any], session: db_session.DiskDbMutationSession) -> dict[str, Any]:
        connection = sqlite3.connect(session.project_db_path)
        connection.row_factory = sqlite3.Row
        linked_failures: list[dict[str, Any]] = []
        try:
            cursor = connection.cursor()
            left_id = mutation_result["db_merge"]["left_item_id"]
            right_id = mutation_result["db_merge"]["right_item_id"]
            left = cursor.execute("SELECT * FROM Sm2TiItem WHERE Sm2TiItem_id = ?", (left_id,)).fetchone()
            left_dict = db_timeline_rows._row_to_dict(cursor, left) if left else None  # type: ignore[attr-defined]
            right = cursor.execute("SELECT * FROM Sm2TiItem WHERE Sm2TiItem_id = ?", (right_id,)).fetchone()
            track_id = mutation_result["db_merge"]["track_id"]
            post_count = cursor.execute(
                "SELECT COUNT(*) FROM Sm2TiItem WHERE Sm2TiTrack_id = ?",
                (track_id,),
            ).fetchone()[0]
            for linked in mutation_result.get("linked_db_merges", []):
                linked_left = cursor.execute(
                    "SELECT * FROM Sm2TiItem WHERE Sm2TiItem_id = ?",
                    (linked["left_item_id"],),
                ).fetchone()
                linked_left_dict = db_timeline_rows._row_to_dict(cursor, linked_left) if linked_left else None  # type: ignore[attr-defined]
                linked_right = cursor.execute(
                    "SELECT * FROM Sm2TiItem WHERE Sm2TiItem_id = ?",
                    (linked["right_item_id"],),
                ).fetchone()
                linked_expected_duration = int(linked["merged_duration"])
                if not linked_left_dict or linked_right or _as_int(linked_left_dict, "Duration") != linked_expected_duration:
                    linked_failures.append(
                        {
                            "left_item_id": linked["left_item_id"],
                            "right_item_id": linked["right_item_id"],
                            "expected_duration": linked_expected_duration,
                        }
                    )
        finally:
            connection.close()
        expected_duration = int(mutation_result["db_merge"]["merged_duration"])
        ok = bool(left_dict and not right and _as_int(left_dict, "Duration") == expected_duration)
        ok = ok and int(post_count) == int(mutation_result["expected_post_item_count"])
        ok = ok and not linked_failures
        if not ok:
            raise APICallFailed(
                "Delete-through-edit DB merge did not verify after project reload.",
                details={
                    "left_item_id": mutation_result["db_merge"]["left_item_id"],
                    "right_item_id": mutation_result["db_merge"]["right_item_id"],
                    "expected_duration": expected_duration,
                    "post_item_count": int(post_count),
                    "expected_post_item_count": mutation_result["expected_post_item_count"],
                    "linked_failures": linked_failures,
                },
                recoverability="manual",
            )
        return {
            "status": "verified",
            "left_item_id": mutation_result["db_merge"]["left_item_id"],
            "deleted_item_ids": mutation_result["db_merge"]["deleted_item_ids"],
            "linked_deleted_item_ids": [
                deleted_id
                for linked in mutation_result.get("linked_db_merges", [])
                for deleted_id in linked.get("deleted_item_ids", [])
            ],
            "post_item_count": int(post_count),
            "expected_post_item_count": mutation_result["expected_post_item_count"],
        }

    result = db_session.execute_sqlite_disk_db_mutation(
        conn,
        context="edit delete-through-edit",
        writer=writer,
        verifier=verifier,
        allow_project_name_inference=True,
    )
    db_session_route = result.pop("route", None)
    result["route"] = "delete_through_edit_db"
    result["db_session_route"] = db_session_route
    return result
