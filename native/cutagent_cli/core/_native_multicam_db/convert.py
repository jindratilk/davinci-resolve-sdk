"""Convert an existing timeline or compound clip into a native multicam clip."""

from __future__ import annotations

import os
import sqlite3
import tempfile
from typing import Any

from ...errors import ValidationError
from .. import db_session


def _column_names(cursor: sqlite3.Cursor, table: str) -> set[str]:
    return {str(row[1]) for row in cursor.execute(f'PRAGMA table_info("{table}")').fetchall()}


def _resolve_source(
    cursor: sqlite3.Cursor,
    *,
    timeline_name: str | None,
    compound_name: str | None,
    media_id: str | None,
) -> dict[str, Any]:
    supplied = [bool(str(timeline_name or "").strip()), bool(str(compound_name or "").strip()), bool(str(media_id or "").strip())]
    if sum(supplied) != 1:
        raise ValidationError(
            "Multicam conversion requires exactly one timeline, compound clip, or media id source.",
            details={"timeline_name": timeline_name, "compound_name": compound_name, "media_id": media_id},
        )
    if timeline_name:
        row = cursor.execute(
            """
            SELECT media.Sm2MpMedia_id, media.Name, media.DbType,
                   timeline.Sm2Timeline_id, timeline.Sequence
            FROM Sm2Timeline timeline
            JOIN Sm2MpMedia media ON media.Sm2MpMedia_id = timeline.Sm2MpMedia_id
            WHERE timeline.Name = ? AND media.DbType = 'Sm2MpTimelineClip'
            """,
            (str(timeline_name).strip(),),
        ).fetchall()
    elif compound_name:
        row = cursor.execute(
            """
            SELECT Sm2MpMedia_id, Name, DbType, NULL, Sequence
            FROM Sm2MpMedia
            WHERE Name = ? AND DbType = 'Sm2MpCompoundClip'
            """,
            (str(compound_name).strip(),),
        ).fetchall()
    else:
        row = cursor.execute(
            """
            SELECT media.Sm2MpMedia_id, media.Name, media.DbType,
                   timeline.Sm2Timeline_id, COALESCE(media.Sequence, timeline.Sequence)
            FROM Sm2MpMedia media
            LEFT JOIN Sm2Timeline timeline ON timeline.Sm2MpMedia_id = media.Sm2MpMedia_id
            WHERE media.Sm2MpMedia_id = ? AND media.DbType IN ('Sm2MpTimelineClip', 'Sm2MpCompoundClip')
            """,
            (str(media_id).strip(),),
        ).fetchall()
    if len(row) != 1:
        raise ValidationError(
            "The timeline or compound clip source for multicam conversion was not found or was ambiguous.",
            details={
                "reason": "multicam_convert_source_not_unique",
                "timeline_name": timeline_name,
                "compound_name": compound_name,
                "media_id": media_id,
                "matches": len(row),
            },
        )
    selected = row[0]
    if not selected[4]:
        raise ValidationError(
            "The conversion source has no persistent sequence.",
            details={"reason": "multicam_convert_sequence_missing", "source_media_id": str(selected[0])},
        )
    return {
        "source_media_id": str(selected[0]),
        "source_name": str(selected[1]),
        "source_type": str(selected[2]),
        "timeline_id": str(selected[3]) if selected[3] else None,
        "sequence_id": str(selected[4]),
    }


def _tracks(cursor: sqlite3.Cursor, *, sequence_id: str) -> list[dict[str, Any]]:
    rows = cursor.execute(
        """
        SELECT rel.DbPropertyName, rel.DbIndex, track.Sm2TiTrack_id,
               track.Type, track.SubType, COALESCE(track.Flags, 0), track.UserDefinedName,
               (SELECT COUNT(*) FROM Sm2TiItem_Sm2TiTrack item_rel
                WHERE item_rel.DbOwner = track.Sm2TiTrack_id
                  AND item_rel.DbPropertyName = 'Items')
        FROM Sm2SequenceContainer container
        JOIN Sm2SequenceContainer_Sm2TiTrack rel
          ON rel.DbOwner = container.Sm2SequenceContainer_id
        JOIN Sm2TiTrack track ON track.Sm2TiTrack_id = rel.DbAssociate
        WHERE container.Sm2Sequence_id = ?
          AND rel.DbPropertyName IN ('VideoTrackVec', 'AudioTrackVec')
        ORDER BY track.Type, rel.DbIndex
        """,
        (sequence_id,),
    ).fetchall()
    return [
        {
            "property_name": str(row[0]),
            "angle_index": int(row[1]),
            "angle_number": int(row[1]) + 1,
            "track_id": str(row[2]),
            "track_type": int(row[3]),
            "track_subtype": int(row[4] or 0),
            "track_flags": int(row[5] or 0),
            "track_name": str(row[6] or "") or None,
            "item_count": int(row[7] or 0),
        }
        for row in rows
    ]


def _readback(cursor: sqlite3.Cursor, *, media_id: str) -> dict[str, Any]:
    media = cursor.execute(
        "SELECT DbType, Name, Sequence, TimelineSharedHandle FROM Sm2MpMedia WHERE Sm2MpMedia_id = ?",
        (media_id,),
    ).fetchone()
    if not media:
        return {"exists": False}
    sequence_id = str(media[2] or "")
    sequence_columns = _column_names(cursor, "Sm2Sequence")
    sequence = cursor.execute(
        "SELECT Parent, Sm2MpMedia_id, "
        + ("Sm2Timeline_id" if "Sm2Timeline_id" in sequence_columns else "NULL")
        + " FROM Sm2Sequence WHERE Sm2Sequence_id = ?",
        (sequence_id,),
    ).fetchone()
    timeline_count = cursor.execute(
        "SELECT COUNT(*) FROM Sm2Timeline WHERE Sm2MpMedia_id = ?",
        (media_id,),
    ).fetchone()[0]
    return {
        "exists": True,
        "media_id": media_id,
        "name": str(media[1] or ""),
        "db_type": str(media[0] or ""),
        "sequence_id": sequence_id,
        "timeline_shared_handle": str(media[3]) if media[3] else None,
        "sequence_parent": str(sequence[0]) if sequence and sequence[0] else None,
        "sequence_media_id": str(sequence[1]) if sequence and sequence[1] else None,
        "sequence_timeline_id": str(sequence[2]) if sequence and sequence[2] else None,
        "timeline_row_count": int(timeline_count or 0),
        "tracks": _tracks(cursor, sequence_id=sequence_id),
    }


def _write_convert(
    cursor: sqlite3.Cursor,
    *,
    timeline_name: str | None = None,
    compound_name: str | None = None,
    media_id: str | None = None,
    multicam_name: str | None = None,
) -> dict[str, Any]:
    source = _resolve_source(
        cursor,
        timeline_name=timeline_name,
        compound_name=compound_name,
        media_id=media_id,
    )
    sequence_id = source["sequence_id"]
    tracks = _tracks(cursor, sequence_id=sequence_id)
    video_tracks = [track for track in tracks if track["track_type"] == 0]
    if not 2 <= len(video_tracks) <= 6:
        raise ValidationError(
            "Timeline/compound multicam conversion supports two through six video tracks.",
            details={
                "reason": "multicam_convert_angle_count_out_of_range",
                "video_track_count": len(video_tracks),
                "supported_min": 2,
                "supported_max": 6,
            },
        )
    target_name = str(multicam_name or source["source_name"]).strip()
    if not target_name:
        raise ValidationError("Converted multicam name cannot be empty.")
    collision = cursor.execute(
        "SELECT Sm2MpMedia_id FROM Sm2MpMedia WHERE DbType = 'Sm2MpMulticamClip' AND Name = ? AND Sm2MpMedia_id != ?",
        (target_name, source["source_media_id"]),
    ).fetchone()
    if collision:
        raise ValidationError(
            "A native multicam clip with the requested name already exists.",
            details={"reason": "multicam_name_exists", "multicam_name": target_name},
        )
    before = _readback(cursor, media_id=source["source_media_id"])
    cursor.execute(
        """
        UPDATE Sm2MpMedia
        SET DbType = 'Sm2MpMulticamClip', Name = ?, Sequence = ?, TimelineSharedHandle = NULL
        WHERE Sm2MpMedia_id = ?
        """,
        (target_name, sequence_id, source["source_media_id"]),
    )
    sequence_assignments = ["Parent = ?", "Sm2MpMedia_id = ?"]
    sequence_values: list[Any] = [source["source_media_id"], source["source_media_id"]]
    if "Sm2Timeline_id" in _column_names(cursor, "Sm2Sequence"):
        sequence_assignments.append("Sm2Timeline_id = NULL")
    sequence_values.append(sequence_id)
    cursor.execute(
        f"UPDATE Sm2Sequence SET {', '.join(sequence_assignments)} WHERE Sm2Sequence_id = ?",
        tuple(sequence_values),
    )
    if source["timeline_id"]:
        cursor.execute("DELETE FROM Sm2Timeline WHERE Sm2Timeline_id = ?", (source["timeline_id"],))
    for track in tracks:
        cursor.execute(
            "UPDATE Sm2TiTrack SET UserDefinedName = ? WHERE Sm2TiTrack_id = ?",
            (f"Angle {track['angle_number']}", track["track_id"]),
        )
    after = _readback(cursor, media_id=source["source_media_id"])
    return {
        "action": "multicam.convert",
        "changed": before != after,
        "source_kind": "timeline" if source["source_type"] == "Sm2MpTimelineClip" else "compound",
        "source_name": source["source_name"],
        "multicam_name": target_name,
        "multicam_media_id": source["source_media_id"],
        "multicam_sequence_id": sequence_id,
        "angle_count": len(video_tracks),
        "audio_track_count": sum(1 for track in tracks if track["track_type"] == 1),
        "before": before,
        "after": after,
        "_expected_after": after,
    }


def plan_multicam_convert(project_db_path: str, **kwargs: Any) -> dict[str, Any]:
    with tempfile.NamedTemporaryFile(prefix="cutagent-multicam-convert-plan-", suffix=".db", delete=False) as handle:
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
            result = _write_convert(connection.cursor(), **kwargs)
            connection.rollback()
        result.pop("_expected_after", None)
        result["would_change"] = bool(result.pop("changed"))
        return result
    finally:
        try:
            os.remove(working_path)
        except FileNotFoundError:
            pass


def convert_to_multicam(conn: Any, **kwargs: Any) -> dict[str, Any]:
    recovery_timeline: dict[str, Any] | None = None
    target_timeline_name = str(kwargs.get("timeline_name") or "").strip()
    active_timeline = getattr(conn, "timeline", None)
    active_name = str(active_timeline.GetName() or "").strip() if active_timeline is not None else ""
    if target_timeline_name and active_name == target_timeline_name:
        project = getattr(conn, "project", None)
        media_pool = getattr(conn, "media_pool", None)
        if project is None or media_pool is None:
            raise ValidationError("Converting the active timeline requires project and Media Pool APIs.")
        replacement = next(
            (
                project.GetTimelineByIndex(index)
                for index in range(1, int(project.GetTimelineCount() or 0) + 1)
                if str(project.GetTimelineByIndex(index).GetName() or "").strip() != target_timeline_name
            ),
            None,
        )
        created = False
        if replacement is None:
            replacement = media_pool.CreateEmptyTimeline("__CutAgent Multicam Conversion Recovery")
            created = True
        if replacement is None or not project.SetCurrentTimeline(replacement):
            raise ValidationError(
                "A safe recovery timeline could not be activated before one-way multicam conversion.",
                details={"reason": "multicam_convert_recovery_timeline_failed", "timeline_name": target_timeline_name},
            )
        refresh = getattr(conn, "refresh", None)
        if callable(refresh):
            refresh()
        recovery_timeline = {
            "name": str(replacement.GetName() or ""),
            "created": created,
            "reason": "conversion_source_timeline_is_one_way_removed",
        }

    def writer(
        _connection: sqlite3.Connection,
        cursor: sqlite3.Cursor,
        _session: db_session.DiskDbMutationSession,
    ) -> dict[str, Any]:
        return _write_convert(cursor, **kwargs)

    def verifier(
        _connection: sqlite3.Connection,
        mutation_result: dict[str, Any],
        session: db_session.DiskDbMutationSession,
    ) -> dict[str, Any]:
        with sqlite3.connect(session.project_db_path) as fresh:
            actual = _readback(fresh.cursor(), media_id=str(mutation_result["multicam_media_id"]))
        expected = mutation_result["_expected_after"]
        ok = actual == expected
        return {
            "status": "verified" if ok else "failed",
            "checks": [
                {
                    "name": "timeline_or_compound_converted_to_multicam",
                    "ok": ok,
                    "actual": actual,
                    "expected": expected,
                }
            ],
        }

    result = db_session.execute_sqlite_disk_db_mutation(
        conn,
        context="Timeline/compound to native multicam conversion",
        writer=writer,
        verifier=verifier,
    )
    result.pop("_expected_after", None)
    if recovery_timeline is not None:
        result["recovery_timeline"] = recovery_timeline
    return result
