"""Flatten timeline multicam wrappers into distinct underlying video/audio items."""

from __future__ import annotations

import os
import sqlite3
import struct
import tempfile
from typing import Any
import uuid

from ...errors import ValidationError
from .. import db_session
from .match_frame import _decode_angle_number


def _timeline_join(cursor: sqlite3.Cursor) -> str:
    columns = {str(row[1]) for row in cursor.execute("PRAGMA table_info(Sm2Sequence)").fetchall()}
    return (
        "sequence.Sm2Timeline_id = timeline.Sm2Timeline_id"
        if "Sm2Timeline_id" in columns
        else "sequence.Sm2Sequence_id = timeline.Sequence"
    )


def _sequence_start(cursor: sqlite3.Cursor, sequence_id: str) -> int:
    row = cursor.execute("SELECT FrameRate, MediaExtents FROM Sm2Sequence WHERE Sm2Sequence_id = ?", (sequence_id,)).fetchone()
    if not row or not row[1] or len(row[1]) < 16:
        raise ValidationError("Multicam sequence extents could not be decoded for flatten.")
    fps = float(struct.unpack("<d", row[0][:8])[0]) if row[0] and len(row[0]) >= 8 else 24.0
    start_seconds, _duration_seconds = struct.unpack("<dd", row[1][:16])
    return int(round(start_seconds * (fps or 24.0)))


def _timeline_items(
    cursor: sqlite3.Cursor,
    *,
    timeline_name: str,
    multicam_media_id: str | None = None,
    timeline_native_id: str | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    cursor.row_factory = sqlite3.Row
    rows = cursor.execute(
        f"""
        SELECT sequence.Sm2Sequence_id AS TimelineSequenceId, track.Type AS TrackType,
               track.Sm2TiTrack_id AS TrackId, rel_item.DbIndex AS ItemIndex, item.*
        FROM Sm2Timeline timeline
        JOIN Sm2Sequence sequence ON {_timeline_join(cursor)}
        JOIN Sm2SequenceContainer container ON container.Sm2Sequence_id = sequence.Sm2Sequence_id
        JOIN Sm2SequenceContainer_Sm2TiTrack rel_track ON rel_track.DbOwner = container.Sm2SequenceContainer_id
        JOIN Sm2TiTrack track ON track.Sm2TiTrack_id = rel_track.DbAssociate
        JOIN Sm2TiItem_Sm2TiTrack rel_item ON rel_item.DbOwner = track.Sm2TiTrack_id AND rel_item.DbPropertyName = 'Items'
        JOIN Sm2TiItem item ON item.Sm2TiItem_id = rel_item.DbAssociate
        JOIN Sm2MpMedia media ON media.Sm2MpMedia_id = item.MediaRef AND media.DbType = 'Sm2MpMulticamClip'
        WHERE timeline.Name = ?
          AND (? IS NULL OR timeline.Sm2Timeline_id = ?)
          AND track.Type IN (0, 1)
          AND (? IS NULL OR item.MediaRef = ?)
        ORDER BY track.Type, rel_track.DbIndex, rel_item.DbIndex
        """,
        (timeline_name, timeline_native_id, timeline_native_id, multicam_media_id, multicam_media_id),
    ).fetchall()
    if not rows:
        raise ValidationError(
            "The target timeline contains no native multicam items to flatten.",
            details={"reason": "timeline_multicam_items_missing", "timeline_name": timeline_name},
        )
    sequence_id = str(rows[0]["TimelineSequenceId"])
    return sequence_id, [dict(row) for row in rows]


def _inner_items(
    cursor: sqlite3.Cursor,
    *,
    multicam_media_id: str,
    angle_number: int,
    track_type: int,
) -> tuple[int, list[dict[str, Any]]]:
    cursor.row_factory = sqlite3.Row
    media = cursor.execute(
        "SELECT Sequence FROM Sm2MpMedia WHERE Sm2MpMedia_id = ? AND DbType = 'Sm2MpMulticamClip'",
        (multicam_media_id,),
    ).fetchone()
    if not media or not media[0]:
        raise ValidationError("Timeline multicam source no longer has an internal sequence.")
    sequence_id = str(media[0])
    property_name = "AudioTrackVec" if track_type == 1 else "VideoTrackVec"
    rows = cursor.execute(
        """
        SELECT item.*, rel_item.DbIndex AS InnerItemIndex, source.Name AS SourceClipName
        FROM Sm2SequenceContainer container
        JOIN Sm2SequenceContainer_Sm2TiTrack rel_track
          ON rel_track.DbOwner = container.Sm2SequenceContainer_id
         AND rel_track.DbPropertyName = ? AND rel_track.DbIndex = ?
        JOIN Sm2TiTrack track ON track.Sm2TiTrack_id = rel_track.DbAssociate AND track.Type = ?
        JOIN Sm2TiItem_Sm2TiTrack rel_item ON rel_item.DbOwner = track.Sm2TiTrack_id AND rel_item.DbPropertyName = 'Items'
        JOIN Sm2TiItem item ON item.Sm2TiItem_id = rel_item.DbAssociate
        LEFT JOIN Sm2MpMedia source ON source.Sm2MpMedia_id = item.MediaRef
        WHERE container.Sm2Sequence_id = ?
        ORDER BY rel_item.DbIndex
        """,
        (property_name, int(angle_number) - 1, track_type, sequence_id),
    ).fetchall()
    return _sequence_start(cursor, sequence_id), [dict(row) for row in rows]


def _clone_columns(cursor: sqlite3.Cursor) -> list[str]:
    return [str(row[1]) for row in cursor.execute("PRAGMA table_info(Sm2TiItem)").fetchall()]


def _insert_item(cursor: sqlite3.Cursor, *, columns: list[str], values: dict[str, Any]) -> None:
    selected = [column for column in columns if column in values]
    quoted_columns = ", ".join(f'"{column}"' for column in selected)
    placeholders = ", ".join("?" for _ in selected)
    cursor.execute(
        f"INSERT INTO Sm2TiItem ({quoted_columns}) VALUES ({placeholders})",
        tuple(values[column] for column in selected),
    )


def _reindex_track(cursor: sqlite3.Cursor, *, track_id: str) -> None:
    rows = cursor.execute(
        """
        SELECT rel.rowid
        FROM Sm2TiItem_Sm2TiTrack rel
        JOIN Sm2TiItem item ON item.Sm2TiItem_id = rel.DbAssociate
        WHERE rel.DbOwner = ? AND rel.DbPropertyName = 'Items'
        ORDER BY CAST(item.Start AS INTEGER), rel.DbIndex, rel.rowid
        """,
        (track_id,),
    ).fetchall()
    for index, (rowid,) in enumerate(rows):
        cursor.execute("UPDATE Sm2TiItem_Sm2TiTrack SET DbIndex = ? WHERE rowid = ?", (index, rowid))


def _write_flatten(
    cursor: sqlite3.Cursor,
    *,
    timeline_name: str,
    grade_policy: str = "copy_multicam",
    angle_number: int | None = None,
    scope: str = "both",
    multicam_media_id: str | None = None,
    timeline_native_id: str | None = None,
) -> dict[str, Any]:
    normalized_grade_policy = str(grade_policy or "copy_multicam").strip().lower().replace("-", "_")
    if normalized_grade_policy not in {"copy_multicam", "retain_angle"}:
        raise ValidationError(
            "Multicam flatten grade_policy must be copy_multicam or retain_angle.",
            details={"grade_policy": grade_policy},
        )
    normalized_scope = str(scope or "both").strip().lower()
    if normalized_scope not in {"both", "video", "audio"}:
        raise ValidationError("Multicam flatten scope must be both, video, or audio.")
    allowed_types = {0, 1} if normalized_scope == "both" else {0} if normalized_scope == "video" else {1}
    timeline_sequence_id, wrappers = _timeline_items(
        cursor,
        timeline_name=timeline_name,
        multicam_media_id=multicam_media_id,
        timeline_native_id=timeline_native_id,
    )
    columns = _clone_columns(cursor)
    flattened: list[dict[str, Any]] = []
    affected_tracks: set[str] = set()
    for wrapper in wrappers:
        track_type = int(wrapper["TrackType"])
        if track_type not in allowed_types:
            continue
        selected_angle = int(angle_number) if angle_number is not None else _decode_angle_number(
            wrapper.get("FieldsBlob"),
            wrapper.get("CurrentSelectorIdx"),
        )
        if selected_angle is None:
            raise ValidationError(
                "A timeline multicam selector could not be decoded during flatten; provide --angle.",
                details={"reason": "multicam_selected_angle_unknown", "timeline_item_id": wrapper["Sm2TiItem_id"]},
            )
        sequence_start, inner_items = _inner_items(
            cursor,
            multicam_media_id=str(wrapper["MediaRef"]),
            angle_number=selected_angle,
            track_type=track_type,
        )
        wrapper_in = int(wrapper.get("In") or 0)
        wrapper_duration = int(wrapper.get("Duration") or 0)
        source_start = sequence_start + wrapper_in
        source_end = source_start + wrapper_duration
        pieces: list[dict[str, Any]] = []
        for inner in inner_items:
            inner_start = int(inner.get("Start") or 0)
            inner_end = inner_start + int(inner.get("Duration") or 0)
            overlap_start = max(source_start, inner_start)
            overlap_end = min(source_end, inner_end)
            if overlap_end <= overlap_start:
                continue
            piece = dict(wrapper)
            piece_id = str(uuid.uuid4())
            piece["Sm2TiItem_id"] = piece_id
            piece["Name"] = inner.get("SourceClipName") or inner.get("Name")
            piece["Start"] = str(int(wrapper["Start"] or 0) + overlap_start - source_start)
            piece["Duration"] = str(overlap_end - overlap_start)
            piece["In"] = str(int(inner.get("In") or 0) + overlap_start - inner_start)
            for field in (
                "MediaRef",
                "MediaStartTime",
                "MediaFilePath",
                "MediaTimemapBA",
                "PreConformMediaExtents",
                "MediaFrameRate",
                "VirtualAudioTrackBA",
                "MediaTrackIdx",
                "CurrentSelectorIdx",
                "FieldsBlob",
            ):
                if field in inner:
                    piece[field] = inner[field]
            if normalized_grade_policy == "retain_angle" and "pLmVerTable" in inner:
                piece["pLmVerTable"] = inner["pLmVerTable"]
            piece.pop("TimelineSequenceId", None)
            piece.pop("TrackType", None)
            piece.pop("TrackId", None)
            piece.pop("ItemIndex", None)
            _insert_item(cursor, columns=columns, values=piece)
            cursor.execute(
                "INSERT INTO Sm2TiItem_Sm2TiTrack (DbOwner, DbAssociate, DbPropertyName, DbIndex) VALUES (?, ?, 'Items', ?)",
                (wrapper["TrackId"], piece_id, int(wrapper["ItemIndex"] or 0) + len(pieces)),
            )
            pieces.append(
                {
                    "item_id": piece_id,
                    "track_type": track_type,
                    "angle_number": selected_angle,
                    "start_frame": int(piece["Start"]),
                    "duration_frames": int(piece["Duration"]),
                    "source_in_frame": int(piece["In"]),
                    "source_media_id": str(piece.get("MediaRef") or ""),
                    "clip_name": str(piece.get("Name") or ""),
                }
            )
        cursor.execute(
            "DELETE FROM Sm2TiItem_Sm2TiTrack WHERE DbOwner = ? AND DbAssociate = ?",
            (wrapper["TrackId"], wrapper["Sm2TiItem_id"]),
        )
        cursor.execute("DELETE FROM Sm2TiItem WHERE Sm2TiItem_id = ?", (wrapper["Sm2TiItem_id"],))
        affected_tracks.add(str(wrapper["TrackId"]))
        flattened.append(
            {
                "wrapper_item_id": str(wrapper["Sm2TiItem_id"]),
                "track_type": track_type,
                "selected_angle_number": selected_angle,
                "piece_count": len(pieces),
                "pieces": pieces,
            }
        )
    for track_id in affected_tracks:
        _reindex_track(cursor, track_id=track_id)
    remaining = cursor.execute(
        """
        SELECT COUNT(*)
        FROM Sm2SequenceContainer container
        JOIN Sm2SequenceContainer_Sm2TiTrack rel_track
          ON rel_track.DbOwner = container.Sm2SequenceContainer_id
        JOIN Sm2TiTrack track ON track.Sm2TiTrack_id = rel_track.DbAssociate
        JOIN Sm2TiItem_Sm2TiTrack rel_item
          ON rel_item.DbOwner = track.Sm2TiTrack_id
         AND rel_item.DbPropertyName = 'Items'
        JOIN Sm2TiItem item ON item.Sm2TiItem_id = rel_item.DbAssociate
        JOIN Sm2MpMedia media ON media.Sm2MpMedia_id = item.MediaRef
        WHERE container.Sm2Sequence_id = ? AND media.DbType = 'Sm2MpMulticamClip'
        """,
        (timeline_sequence_id,),
    ).fetchone()[0]
    return {
        "action": "multicam.flatten",
        "changed": bool(flattened),
        "timeline_name": timeline_name,
        "timeline_sequence_id": timeline_sequence_id,
        "grade_policy": normalized_grade_policy,
        "scope": normalized_scope,
        "flattened_wrappers": flattened,
        "flattened_wrapper_count": len(flattened),
        "created_source_item_count": sum(row["piece_count"] for row in flattened),
        "remaining_multicam_item_count": int(remaining or 0),
        "_expected_remaining": int(remaining or 0),
    }


def plan_multicam_flatten(project_db_path: str, **kwargs: Any) -> dict[str, Any]:
    """Plan flatten against an isolated DB copy without mutating the project."""
    with tempfile.NamedTemporaryFile(prefix="cutagent-multicam-flatten-plan-", suffix=".db", delete=False) as handle:
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
            result = _write_flatten(connection.cursor(), **kwargs)
            connection.rollback()
        result.pop("_expected_remaining", None)
        result["would_change"] = bool(result.pop("changed"))
        return result
    finally:
        try:
            os.remove(working_path)
        except FileNotFoundError:
            pass


def flatten_multicam_timeline(
    conn: Any,
    *,
    timeline_name: str,
    grade_policy: str = "copy_multicam",
    angle_number: int | None = None,
    scope: str = "both",
    multicam_media_id: str | None = None,
    timeline_native_id: str | None = None,
) -> dict[str, Any]:
    def writer(_connection: sqlite3.Connection, cursor: sqlite3.Cursor, _session: db_session.DiskDbMutationSession) -> dict[str, Any]:
        return _write_flatten(
            cursor,
            timeline_name=timeline_name,
            grade_policy=grade_policy,
            angle_number=angle_number,
            scope=scope,
            multicam_media_id=multicam_media_id,
            timeline_native_id=timeline_native_id,
        )

    def verifier(_connection: sqlite3.Connection, mutation_result: dict[str, Any], session: db_session.DiskDbMutationSession) -> dict[str, Any]:
        with sqlite3.connect(session.project_db_path) as fresh:
            remaining = fresh.execute(
                """
                SELECT COUNT(*)
                FROM Sm2SequenceContainer container
                JOIN Sm2SequenceContainer_Sm2TiTrack rel_track
                  ON rel_track.DbOwner = container.Sm2SequenceContainer_id
                JOIN Sm2TiTrack track ON track.Sm2TiTrack_id = rel_track.DbAssociate
                JOIN Sm2TiItem_Sm2TiTrack rel_item
                  ON rel_item.DbOwner = track.Sm2TiTrack_id
                 AND rel_item.DbPropertyName = 'Items'
                JOIN Sm2TiItem item ON item.Sm2TiItem_id = rel_item.DbAssociate
                JOIN Sm2MpMedia media ON media.Sm2MpMedia_id = item.MediaRef
                WHERE container.Sm2Sequence_id = ? AND media.DbType = 'Sm2MpMulticamClip'
                """,
                (mutation_result["timeline_sequence_id"],),
            ).fetchone()[0]
        expected = int(mutation_result["_expected_remaining"])
        return {
            "status": "verified" if int(remaining or 0) == expected else "failed",
            "checks": [{"name": "multicam_wrappers_removed", "ok": int(remaining or 0) == expected, "actual": int(remaining or 0), "expected": expected}],
        }

    result = db_session.execute_sqlite_disk_db_mutation(
        conn,
        context="Native multicam flatten",
        writer=writer,
        verifier=verifier,
    )
    result.pop("_expected_remaining", None)
    return result
