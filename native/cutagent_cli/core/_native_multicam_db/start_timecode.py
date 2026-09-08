"""Persistent start-timecode editing for native multicam sequences."""

from __future__ import annotations

import os
import sqlite3
import struct
import tempfile
from typing import Any

from ...errors import ValidationError
from ...utils.timecode import frames_to_timecode, timecode_to_seconds
from .. import db_session
from .strip_audio import resolve_multicam_strip_target


def _snapshot(cursor: sqlite3.Cursor, sequence_id: str) -> dict[str, Any]:
    row = cursor.execute(
        "SELECT FrameRate, MediaExtents FROM Sm2Sequence WHERE Sm2Sequence_id = ?",
        (sequence_id,),
    ).fetchone()
    if not row or not row[1] or len(row[1]) < 16:
        raise ValidationError(
            "Native multicam sequence extents could not be decoded.",
            details={"reason": "multicam_sequence_extents_missing", "sequence_id": sequence_id},
        )
    fps = float(struct.unpack("<d", row[0][:8])[0]) if row[0] and len(row[0]) >= 8 else 24.0
    fps = fps or 24.0
    start_seconds, duration_seconds = struct.unpack("<dd", row[1][:16])
    items = cursor.execute(
        """
        SELECT item.Sm2TiItem_id, CAST(item.Start AS INTEGER)
        FROM Sm2SequenceContainer container
        JOIN Sm2SequenceContainer_Sm2TiTrack track_rel ON track_rel.DbOwner = container.Sm2SequenceContainer_id
        JOIN Sm2TiItem_Sm2TiTrack item_rel ON item_rel.DbOwner = track_rel.DbAssociate
        JOIN Sm2TiItem item ON item.Sm2TiItem_id = item_rel.DbAssociate
        WHERE container.Sm2Sequence_id = ?
        ORDER BY item.Sm2TiItem_id
        """,
        (sequence_id,),
    ).fetchall()
    start_frame = int(round(float(start_seconds) * fps))
    return {
        "fps": fps,
        "start_frame": start_frame,
        "start_timecode": frames_to_timecode(start_frame, fps),
        "duration_frames": int(round(float(duration_seconds) * fps)),
        "item_starts": [{"item_id": str(item_id), "start_frame": int(start)} for item_id, start in items],
        "media_extents": bytes(row[1]),
    }


def _write(
    cursor: sqlite3.Cursor,
    *,
    start_timecode: str,
    multicam_name: str | None = None,
    media_id: str | None = None,
    sequence_id: str | None = None,
) -> dict[str, Any]:
    target = resolve_multicam_strip_target(
        cursor,
        multicam_name=multicam_name,
        media_id=media_id,
        sequence_id=sequence_id,
    )
    resolved_sequence_id = str(target["multicam_sequence_id"])
    before = _snapshot(cursor, resolved_sequence_id)
    normalized = str(start_timecode or "").strip()
    try:
        requested_frame = int(round(timecode_to_seconds(normalized, float(before["fps"])) * float(before["fps"])))
    except Exception as exc:
        raise ValidationError(
            "Multicam start_timecode must be a valid HH:MM:SS:FF or HH:MM:SS;FF value.",
            details={"start_timecode": start_timecode, "fps": before["fps"]},
        ) from exc
    delta = requested_frame - int(before["start_frame"])
    old_blob = bytes(before["media_extents"])
    duration_seconds = float(before["duration_frames"]) / float(before["fps"])
    new_blob = struct.pack("<dd", requested_frame / float(before["fps"]), duration_seconds) + old_blob[16:]
    cursor.execute("UPDATE Sm2Sequence SET MediaExtents = ? WHERE Sm2Sequence_id = ?", (new_blob, resolved_sequence_id))
    if delta:
        cursor.execute(
            """
            UPDATE Sm2TiItem
            SET Start = CAST(CAST(Start AS INTEGER) + ? AS TEXT)
            WHERE Sm2TiItem_id IN (
                SELECT item_rel.DbAssociate
                FROM Sm2SequenceContainer container
                JOIN Sm2SequenceContainer_Sm2TiTrack track_rel ON track_rel.DbOwner = container.Sm2SequenceContainer_id
                JOIN Sm2TiItem_Sm2TiTrack item_rel ON item_rel.DbOwner = track_rel.DbAssociate
                WHERE container.Sm2Sequence_id = ?
            )
            """,
            (delta, resolved_sequence_id),
        )
    after = _snapshot(cursor, resolved_sequence_id)
    return {
        "action": "multicam.start_timecode_set",
        "changed": before != after,
        **target,
        "requested_start_timecode": normalized,
        "delta_frames": delta,
        "before": {key: value for key, value in before.items() if key != "media_extents"},
        "after": {key: value for key, value in after.items() if key != "media_extents"},
        "_expected_after": after,
    }


def plan_multicam_start_timecode(project_db_path: str, **kwargs: Any) -> dict[str, Any]:
    with tempfile.NamedTemporaryFile(prefix="cutagent-multicam-start-tc-plan-", suffix=".db", delete=False) as handle:
        working_path = handle.name
    source = sqlite3.connect(project_db_path)
    target = sqlite3.connect(working_path)
    try:
        source.backup(target)
    finally:
        source.close()
        target.close()
    try:
        connection = sqlite3.connect(working_path)
        try:
            result = _write(connection.cursor(), **kwargs)
            connection.rollback()
        finally:
            connection.close()
        result.pop("_expected_after", None)
        result["would_change"] = bool(result.pop("changed"))
        return result
    finally:
        try:
            os.remove(working_path)
        except FileNotFoundError:
            pass


def set_multicam_start_timecode(conn: Any, **kwargs: Any) -> dict[str, Any]:
    def writer(_connection: sqlite3.Connection, cursor: sqlite3.Cursor, _session: db_session.DiskDbMutationSession) -> dict[str, Any]:
        return _write(cursor, **kwargs)

    def verifier(_connection: sqlite3.Connection, result: dict[str, Any], session: db_session.DiskDbMutationSession) -> dict[str, Any]:
        with sqlite3.connect(session.project_db_path) as fresh:
            actual = _snapshot(fresh.cursor(), str(result["multicam_sequence_id"]))
        expected = result["_expected_after"]
        return {
            "status": "verified" if actual == expected else "failed",
            "checks": [{"name": "multicam_start_timecode_readback", "ok": actual == expected, "actual": actual, "expected": expected}],
        }

    result = db_session.execute_sqlite_disk_db_mutation(
        conn,
        context="Native multicam start timecode",
        writer=writer,
        verifier=verifier,
    )
    result.pop("_expected_after", None)
    return result
