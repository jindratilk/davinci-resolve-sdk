"""Persistent native multicam angle and source-item editing."""

from __future__ import annotations

import os
import sqlite3
import struct
import tempfile
from typing import Any

from ...errors import SdkMutationStaleRevision, ValidationError
from .. import db_session
from .strip_audio import resolve_multicam_strip_target

_DISABLED_TRACK_FLAG = 2


def _container_id(cursor: sqlite3.Cursor, sequence_id: str) -> str:
    row = cursor.execute(
        "SELECT Sm2SequenceContainer_id FROM Sm2SequenceContainer WHERE Sm2Sequence_id = ?",
        (sequence_id,),
    ).fetchone()
    if not row or not row[0]:
        raise ValidationError(
            "Native multicam sequence container could not be found.",
            details={"reason": "multicam_sequence_container_missing", "sequence_id": sequence_id},
        )
    return str(row[0])


def _sequence_start_frame(cursor: sqlite3.Cursor, sequence_id: str) -> int:
    row = cursor.execute(
        "SELECT FrameRate, MediaExtents FROM Sm2Sequence WHERE Sm2Sequence_id = ?",
        (sequence_id,),
    ).fetchone()
    if not row or not row[1] or len(row[1]) < 16:
        raise ValidationError(
            "Native multicam sequence start could not be decoded.",
            details={"reason": "multicam_sequence_extents_missing", "sequence_id": sequence_id},
        )
    fps = 24.0
    if row[0] and len(row[0]) >= 8:
        fps = float(struct.unpack("<d", row[0][:8])[0]) or 24.0
    start_seconds, _duration_seconds = struct.unpack("<dd", row[1][:16])
    return int(round(float(start_seconds) * fps))


def _track(cursor: sqlite3.Cursor, *, container_id: str, track_type: int, angle_index: int) -> dict[str, Any] | None:
    property_name = "AudioTrackVec" if track_type == 1 else "VideoTrackVec"
    row = cursor.execute(
        """
        SELECT track.Sm2TiTrack_id, track.UserDefinedName, COALESCE(track.Flags, 0)
        FROM Sm2SequenceContainer_Sm2TiTrack rel
        JOIN Sm2TiTrack track ON track.Sm2TiTrack_id = rel.DbAssociate
        WHERE rel.DbOwner = ? AND rel.DbPropertyName = ? AND rel.DbIndex = ? AND track.Type = ?
        """,
        (container_id, property_name, angle_index, track_type),
    ).fetchone()
    if not row:
        return None
    return {
        "track_id": str(row[0]),
        "name": str(row[1] or "") or None,
        "flags": int(row[2] or 0),
        "type": track_type,
        "property_name": property_name,
        "angle_index": angle_index,
    }


def _selected_tracks(
    cursor: sqlite3.Cursor,
    *,
    container_id: str,
    angle_number: int,
    media_type: str,
) -> list[dict[str, Any]]:
    if angle_number < 1:
        raise ValidationError("Multicam angle number must be one or greater.", details={"angle_number": angle_number})
    normalized_media_type = str(media_type or "both").strip().lower()
    if normalized_media_type not in {"both", "video", "audio"}:
        raise ValidationError(
            "Multicam angle media_type must be both, video, or audio.",
            details={"media_type": media_type},
        )
    types = [0, 1] if normalized_media_type == "both" else [0] if normalized_media_type == "video" else [1]
    tracks = [
        row
        for track_type in types
        if (row := _track(cursor, container_id=container_id, track_type=track_type, angle_index=angle_number - 1))
    ]
    if not tracks:
        raise ValidationError(
            "Requested native multicam angle track was not found.",
            details={"reason": "multicam_angle_not_found", "angle_number": angle_number, "media_type": media_type},
        )
    return tracks


def _item(cursor: sqlite3.Cursor, *, track_id: str, item_index: int) -> dict[str, Any] | None:
    row = cursor.execute(
        """
        SELECT item.Sm2TiItem_id, item.Start, item.Duration, item."In", item.MediaRef, item.Name
        FROM Sm2TiItem_Sm2TiTrack rel
        JOIN Sm2TiItem item ON item.Sm2TiItem_id = rel.DbAssociate
        WHERE rel.DbOwner = ? AND rel.DbPropertyName = 'Items' AND rel.DbIndex = ?
        """,
        (track_id, item_index),
    ).fetchone()
    if not row:
        return None
    return {
        "item_id": str(row[0]),
        "start_frame": int(row[1] or 0),
        "duration_frames": int(row[2] or 0),
        "source_in_frame": int(row[3] or 0),
        "source_media_id": str(row[4] or "") or None,
        "clip_name": str(row[5] or "") or None,
        "item_index": item_index,
    }


def _reindex(cursor: sqlite3.Cursor, *, table: str, owner_column: str, owner: str, property_name: str) -> None:
    rows = cursor.execute(
        f"SELECT rowid FROM {table} WHERE {owner_column} = ? AND DbPropertyName = ? ORDER BY DbIndex, rowid",
        (owner, property_name),
    ).fetchall()
    for index, (rowid,) in enumerate(rows):
        cursor.execute(f"UPDATE {table} SET DbIndex = ? WHERE rowid = ?", (index, rowid))


def _validate_non_overlap(cursor: sqlite3.Cursor, *, track_id: str, item_id: str, start: int, duration: int) -> None:
    rows = cursor.execute(
        "SELECT Sm2TiItem_id, Start, Duration FROM Sm2TiItem WHERE Sm2TiTrack_id = ? AND Sm2TiItem_id != ?",
        (track_id, item_id),
    ).fetchall()
    end = start + duration
    conflicts = [
        {"item_id": str(row[0]), "start_frame": int(row[1]), "duration_frames": int(row[2])}
        for row in rows
        if start < int(row[1]) + int(row[2]) and int(row[1]) < end
    ]
    if conflicts:
        raise ValidationError(
            "Moving the multicam source item would overlap another item on the same angle.",
            details={"reason": "overlapping_source_items", "conflicts": conflicts},
        )


def _snapshot(cursor: sqlite3.Cursor, *, sequence_id: str) -> dict[str, Any]:
    rows = cursor.execute(
        """
        SELECT track.Type, rel.DbIndex, track.Sm2TiTrack_id, track.UserDefinedName, COALESCE(track.Flags, 0),
               item_rel.DbIndex, item.Sm2TiItem_id, item.Start, item.Duration, item."In", item.MediaRef
        FROM Sm2SequenceContainer container
        JOIN Sm2SequenceContainer_Sm2TiTrack rel ON rel.DbOwner = container.Sm2SequenceContainer_id
        JOIN Sm2TiTrack track ON track.Sm2TiTrack_id = rel.DbAssociate
        LEFT JOIN Sm2TiItem_Sm2TiTrack item_rel ON item_rel.DbOwner = track.Sm2TiTrack_id AND item_rel.DbPropertyName = 'Items'
        LEFT JOIN Sm2TiItem item ON item.Sm2TiItem_id = item_rel.DbAssociate
        WHERE container.Sm2Sequence_id = ?
        ORDER BY track.Type, rel.DbIndex, item_rel.DbIndex
        """,
        (sequence_id,),
    ).fetchall()
    return {
        "rows": [
            {
                "track_type": int(row[0]),
                "angle_index": int(row[1]),
                "track_id": str(row[2]),
                "track_name": str(row[3] or "") or None,
                "track_enabled": not bool(int(row[4] or 0) & _DISABLED_TRACK_FLAG),
                "item_index": int(row[5]) if row[5] is not None else None,
                "item_id": str(row[6]) if row[6] else None,
                "start_frame": int(row[7]) if row[7] is not None else None,
                "duration_frames": int(row[8]) if row[8] is not None else None,
                "source_in_frame": int(row[9]) if row[9] is not None else None,
                "source_media_id": str(row[10]) if row[10] else None,
            }
            for row in rows
        ]
    }


def _write(
    cursor: sqlite3.Cursor,
    *,
    operation: str,
    multicam_name: str | None = None,
    media_id: str | None = None,
    sequence_id: str | None = None,
    angle_number: int,
    media_type: str = "both",
    item_index: int | None = None,
    record_start_frame: int | None = None,
    name: str | None = None,
    enabled: bool | None = None,
    expected_source_media_id: str | None = None,
) -> dict[str, Any]:
    target = resolve_multicam_strip_target(
        cursor,
        multicam_name=multicam_name,
        media_id=media_id,
        sequence_id=sequence_id,
    )
    resolved_sequence_id = str(target["multicam_sequence_id"])
    container_id = _container_id(cursor, resolved_sequence_id)
    tracks = _selected_tracks(
        cursor,
        container_id=container_id,
        angle_number=int(angle_number),
        media_type=media_type,
    )
    before = _snapshot(cursor, sequence_id=resolved_sequence_id)
    normalized_operation = str(operation).strip().lower().replace("-", "_")

    if normalized_operation == "rename":
        normalized_name = str(name or "").strip()
        if not normalized_name:
            raise ValidationError("Multicam angle rename requires a non-empty name.")
        for track in tracks:
            cursor.execute("UPDATE Sm2TiTrack SET UserDefinedName = ? WHERE Sm2TiTrack_id = ?", (normalized_name, track["track_id"]))
    elif normalized_operation == "set_enabled":
        if enabled is None:
            raise ValidationError("Multicam angle enable operation requires enabled=true or false.")
        for track in tracks:
            flags = int(track["flags"])
            flags = flags & ~_DISABLED_TRACK_FLAG if enabled else flags | _DISABLED_TRACK_FLAG
            cursor.execute("UPDATE Sm2TiTrack SET Flags = ? WHERE Sm2TiTrack_id = ?", (flags, track["track_id"]))
    elif normalized_operation == "move_item":
        if item_index is None or item_index < 0 or record_start_frame is None or record_start_frame < 0:
            raise ValidationError("Moving a multicam source item requires non-negative item_index and record_start_frame.")
        absolute_start = _sequence_start_frame(cursor, resolved_sequence_id) + int(record_start_frame)
        for track in tracks:
            selected_item = _item(cursor, track_id=track["track_id"], item_index=int(item_index))
            if selected_item is None:
                raise ValidationError(
                    "Requested multicam source item was not found.",
                    details={"reason": "multicam_source_item_not_found", "angle_number": angle_number, "item_index": item_index},
                )
            if expected_source_media_id and selected_item["source_media_id"] != expected_source_media_id:
                raise SdkMutationStaleRevision("The exact SDK multicam source identity changed before execution.", details={"reason": "sdk_multicam_source_guard_mismatch"})
            _validate_non_overlap(
                cursor,
                track_id=track["track_id"],
                item_id=selected_item["item_id"],
                start=absolute_start,
                duration=int(selected_item["duration_frames"]),
            )
            cursor.execute("UPDATE Sm2TiItem SET Start = ? WHERE Sm2TiItem_id = ?", (str(absolute_start), selected_item["item_id"]))
    elif normalized_operation == "remove_item":
        if item_index is None or item_index < 0:
            raise ValidationError("Removing a multicam source item requires a non-negative item_index.")
        for track in tracks:
            selected_item = _item(cursor, track_id=track["track_id"], item_index=int(item_index))
            if selected_item is None:
                raise ValidationError(
                    "Requested multicam source item was not found.",
                    details={"reason": "multicam_source_item_not_found", "angle_number": angle_number, "item_index": item_index},
                )
            if expected_source_media_id and selected_item["source_media_id"] != expected_source_media_id:
                raise SdkMutationStaleRevision("The exact SDK multicam source identity changed before execution.", details={"reason": "sdk_multicam_source_guard_mismatch"})
            cursor.execute("DELETE FROM Sm2TiItem_Sm2TiTrack WHERE DbOwner = ? AND DbAssociate = ?", (track["track_id"], selected_item["item_id"]))
            cursor.execute("DELETE FROM Sm2TiItem WHERE Sm2TiItem_id = ?", (selected_item["item_id"],))
            _reindex(
                cursor,
                table="Sm2TiItem_Sm2TiTrack",
                owner_column="DbOwner",
                owner=track["track_id"],
                property_name="Items",
            )
    elif normalized_operation == "remove_angle":
        video_count = cursor.execute(
            "SELECT COUNT(*) FROM Sm2SequenceContainer_Sm2TiTrack WHERE DbOwner = ? AND DbPropertyName = 'VideoTrackVec'",
            (container_id,),
        ).fetchone()[0]
        if int(video_count or 0) <= 2:
            raise ValidationError(
                "A native multicam clip must retain at least two video angles.",
                details={"reason": "minimum_multicam_angle_count", "angle_count": int(video_count or 0)},
            )
        tracks = _selected_tracks(cursor, container_id=container_id, angle_number=int(angle_number), media_type="both")
        for track in tracks:
            item_ids = [
                str(row[0])
                for row in cursor.execute("SELECT DbAssociate FROM Sm2TiItem_Sm2TiTrack WHERE DbOwner = ?", (track["track_id"],)).fetchall()
            ]
            cursor.execute("DELETE FROM Sm2SequenceContainer_Sm2TiTrack WHERE DbOwner = ? AND DbAssociate = ?", (container_id, track["track_id"]))
            cursor.execute("DELETE FROM Sm2TiItem_Sm2TiTrack WHERE DbOwner = ?", (track["track_id"],))
            for selected_item_id in item_ids:
                cursor.execute("DELETE FROM Sm2TiItem WHERE Sm2TiItem_id = ?", (selected_item_id,))
            cursor.execute("DELETE FROM Sm2TiTrack WHERE Sm2TiTrack_id = ?", (track["track_id"],))
        _reindex(cursor, table="Sm2SequenceContainer_Sm2TiTrack", owner_column="DbOwner", owner=container_id, property_name="VideoTrackVec")
        _reindex(cursor, table="Sm2SequenceContainer_Sm2TiTrack", owner_column="DbOwner", owner=container_id, property_name="AudioTrackVec")
    else:
        raise ValidationError(
            "Unsupported native multicam angle edit operation.",
            details={"operation": operation, "supported_operations": ["rename", "set_enabled", "move_item", "remove_item", "remove_angle"]},
        )

    after = _snapshot(cursor, sequence_id=resolved_sequence_id)
    return {
        "action": f"multicam.{normalized_operation}",
        "changed": before != after,
        **target,
        "operation": normalized_operation,
        "angle_number": int(angle_number),
        "media_type": media_type,
        "item_index": item_index,
        "record_start_frame": record_start_frame,
        "name": name,
        "enabled": enabled,
        "before": before,
        "after": after,
        "_expected_after": after,
    }


def plan_multicam_angle_edit(project_db_path: str, **kwargs: Any) -> dict[str, Any]:
    with tempfile.NamedTemporaryFile(prefix="cutagent-multicam-angle-plan-", suffix=".db", delete=False) as handle:
        working_path = handle.name
    source = sqlite3.connect(project_db_path)
    target = sqlite3.connect(working_path)
    try:
        source.backup(target)
    finally:
        source.close()
        target.close()
    try:
        with sqlite3.connect(working_path) as connection:
            result = _write(connection.cursor(), **kwargs)
            connection.rollback()
        result.pop("_expected_after", None)
        result["would_change"] = bool(result.pop("changed"))
        return result
    finally:
        try:
            os.remove(working_path)
        except FileNotFoundError:
            pass


def edit_multicam_angle(conn: Any, **kwargs: Any) -> dict[str, Any]:
    def writer(_connection: sqlite3.Connection, cursor: sqlite3.Cursor, _session: db_session.DiskDbMutationSession) -> dict[str, Any]:
        return _write(cursor, **kwargs)

    def verifier(_connection: sqlite3.Connection, mutation_result: dict[str, Any], session: db_session.DiskDbMutationSession) -> dict[str, Any]:
        with sqlite3.connect(session.project_db_path) as fresh_connection:
            actual = _snapshot(fresh_connection.cursor(), sequence_id=str(mutation_result["multicam_sequence_id"]))
        expected = mutation_result["_expected_after"]
        return {
            "status": "verified" if actual == expected else "failed",
            "checks": [{"name": "multicam_angle_edit_readback", "ok": actual == expected, "actual": actual, "expected": expected}],
        }

    result = db_session.execute_sqlite_disk_db_mutation(
        conn,
        context="Native multicam angle edit",
        writer=writer,
        verifier=verifier,
    )
    result.pop("_expected_after", None)
    return result
