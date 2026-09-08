"""Native multicam embedded-audio strip helpers."""

from __future__ import annotations

import sqlite3
from typing import Any

from ...errors import ValidationError
from .. import db_session


def _placeholders(values: list[str]) -> str:
    if not values:
        raise ValueError("Cannot build SQL placeholders for an empty value list.")
    return ",".join("?" for _ in values)


def _row_to_target(row: sqlite3.Row | tuple[Any, ...]) -> dict[str, Any]:
    return {
        "multicam_media_id": str(row[0] or ""),
        "multicam_name": str(row[1] or ""),
        "multicam_sequence_id": str(row[2] or ""),
    }


def resolve_multicam_strip_target(
    cursor: sqlite3.Cursor,
    *,
    multicam_name: str | None = None,
    media_id: str | None = None,
    sequence_id: str | None = None,
) -> dict[str, Any]:
    normalized_name = str(multicam_name or "").strip()
    normalized_media_id = str(media_id or "").strip()
    normalized_sequence_id = str(sequence_id or "").strip()
    if not normalized_name and not normalized_media_id and not normalized_sequence_id:
        raise ValidationError(
            "Multicam embedded audio strip requires --multicam-name, --media-id, or --sequence-id.",
            details={"reason": "missing_multicam_identifier"},
        )

    clauses = ["media.DbType = 'Sm2MpMulticamClip'"]
    params: list[Any] = []
    if normalized_name:
        clauses.append("media.Name = ?")
        params.append(normalized_name)
    if normalized_media_id:
        clauses.append("media.Sm2MpMedia_id = ?")
        params.append(normalized_media_id)
    if normalized_sequence_id:
        clauses.append("seq.Sm2Sequence_id = ?")
        params.append(normalized_sequence_id)

    rows = cursor.execute(
        f"""
        SELECT media.Sm2MpMedia_id, media.Name, seq.Sm2Sequence_id
        FROM Sm2MpMedia media
        JOIN Sm2Sequence seq ON seq.Sm2MpMedia_id = media.Sm2MpMedia_id
        WHERE {" AND ".join(clauses)}
        ORDER BY LOWER(media.Name), media.Sm2MpMedia_id, seq.Sm2Sequence_id
        """,
        tuple(params),
    ).fetchall()
    candidates = [_row_to_target(row) for row in rows]
    if not rows:
        raise ValidationError(
            "Could not find a native multicam clip matching the requested selector.",
            details={
                "reason": "multicam_not_found",
                "multicam_name": normalized_name or None,
                "multicam_media_id": normalized_media_id or None,
                "multicam_sequence_id": normalized_sequence_id or None,
                "candidates": [],
            },
        )
    if len(rows) > 1:
        raise ValidationError(
            "Multicam name is ambiguous; provide --media-id or --sequence-id.",
            details={
                "reason": "ambiguous_multicam_name",
                "multicam_name": normalized_name or None,
                "candidates": candidates,
            },
        )
    return candidates[0]


def _fetch_track_ids(cursor: sqlite3.Cursor, *, sequence_id: str, track_type: int) -> list[str]:
    rows = cursor.execute(
        """
        SELECT Sm2TiTrack_id
        FROM Sm2TiTrack
        WHERE Sequence = ? AND Type = ?
        ORDER BY UserDefinedName, Sm2TiTrack_id
        """,
        (sequence_id, int(track_type)),
    ).fetchall()
    return [str(row[0]) for row in rows if row and row[0]]


def _fetch_audio_item_ids(cursor: sqlite3.Cursor, *, audio_track_ids: list[str]) -> list[str]:
    if not audio_track_ids:
        return []
    rows = cursor.execute(
        f"""
        SELECT rel.DbAssociate
        FROM Sm2TiItem_Sm2TiTrack rel
        WHERE rel.DbOwner IN ({_placeholders(audio_track_ids)}) AND rel.DbPropertyName = 'Items'
        """,
        tuple(audio_track_ids),
    ).fetchall()
    return [str(row[0]) for row in rows if row and row[0]]


def _count_track_items(cursor: sqlite3.Cursor, *, sequence_id: str, track_type: int) -> int:
    row = cursor.execute(
        """
        SELECT COUNT(DISTINCT rel.DbAssociate)
        FROM Sm2TiItem_Sm2TiTrack rel
        JOIN Sm2TiTrack track ON track.Sm2TiTrack_id = rel.DbOwner
        JOIN Sm2TiItem item ON item.Sm2TiItem_id = rel.DbAssociate
        WHERE track.Sequence = ?
          AND track.Type = ?
          AND rel.DbPropertyName = 'Items'
        """,
        (sequence_id, int(track_type)),
    ).fetchone()
    return int((row[0] if row else 0) or 0)


def _count_tracks(cursor: sqlite3.Cursor, *, sequence_id: str, track_type: int) -> int:
    row = cursor.execute(
        "SELECT COUNT(*) FROM Sm2TiTrack WHERE Sequence = ? AND Type = ?",
        (sequence_id, int(track_type)),
    ).fetchone()
    return int((row[0] if row else 0) or 0)


def _fetch_media_audio_fields(cursor: sqlite3.Cursor, *, media_id: str) -> dict[str, Any]:
    row = cursor.execute(
        "SELECT AudioSource, VirtualAudioTracksBA FROM Sm2MpMedia WHERE Sm2MpMedia_id = ?",
        (media_id,),
    ).fetchone()
    if not row:
        return {"audio_source": None, "virtual_audio_tracks_ba": None}
    return {"audio_source": row[0], "virtual_audio_tracks_ba": row[1]}


def _audio_item_ids_remaining(cursor: sqlite3.Cursor, *, audio_item_ids: list[str]) -> int:
    if not audio_item_ids:
        return 0
    row = cursor.execute(
        f"SELECT COUNT(*) FROM Sm2TiItem WHERE Sm2TiItem_id IN ({_placeholders(audio_item_ids)})",
        tuple(audio_item_ids),
    ).fetchone()
    return int((row[0] if row else 0) or 0)


def _build_counts(cursor: sqlite3.Cursor, *, sequence_id: str, audio_item_ids: list[str] | None = None) -> dict[str, int]:
    return {
        "audio_tracks": _count_tracks(cursor, sequence_id=sequence_id, track_type=1),
        "audio_items": _count_track_items(cursor, sequence_id=sequence_id, track_type=1),
        "removed_audio_items_remaining": _audio_item_ids_remaining(cursor, audio_item_ids=list(audio_item_ids or [])),
        "video_tracks": _count_tracks(cursor, sequence_id=sequence_id, track_type=0),
        "video_items": _count_track_items(cursor, sequence_id=sequence_id, track_type=0),
    }


def _build_verification(
    cursor: sqlite3.Cursor,
    *,
    media_id: str,
    sequence_id: str,
    removed_audio_item_ids: list[str],
) -> dict[str, Any]:
    fields = _fetch_media_audio_fields(cursor, media_id=media_id)
    counts = _build_counts(cursor, sequence_id=sequence_id, audio_item_ids=removed_audio_item_ids)
    audio_source_disabled = fields["audio_source"] is None
    virtual_audio_tracks_cleared = fields["virtual_audio_tracks_ba"] is None
    audio_tracks_removed = counts["audio_tracks"] == 0
    audio_items_removed = counts["audio_items"] == 0 and counts["removed_audio_items_remaining"] == 0
    video_tracks_preserved = counts["video_tracks"] > 0
    video_items_preserved = counts["video_items"] > 0
    checks = [
        {"name": "multicam_audio_source_disabled", "ok": audio_source_disabled, "audio_source": fields["audio_source"]},
        {
            "name": "multicam_virtual_audio_tracks_cleared",
            "ok": virtual_audio_tracks_cleared,
            "has_virtual_audio_tracks": fields["virtual_audio_tracks_ba"] is not None,
        },
        {
            "name": "multicam_audio_tracks_removed",
            "ok": audio_tracks_removed,
            "remaining_tracks": counts["audio_tracks"],
        },
        {
            "name": "multicam_audio_items_removed",
            "ok": audio_items_removed,
            "remaining_items": counts["audio_items"],
            "removed_item_rows_remaining": counts["removed_audio_items_remaining"],
        },
        {
            "name": "multicam_video_tracks_preserved",
            "ok": video_tracks_preserved,
            "remaining_video_tracks": counts["video_tracks"],
        },
        {
            "name": "multicam_video_items_preserved",
            "ok": video_items_preserved,
            "remaining_video_items": counts["video_items"],
        },
    ]
    status = "verified" if all(bool(check["ok"]) for check in checks) else "failed"
    return {"status": status, "checks": checks, "counts": counts}


def plan_multicam_embedded_audio_strip(
    project_db_path: str,
    *,
    multicam_name: str | None = None,
    media_id: str | None = None,
    sequence_id: str | None = None,
    allow_missing_audio: bool = False,
) -> dict[str, Any]:
    connection = sqlite3.connect(project_db_path)
    try:
        cursor = connection.cursor()
        target = resolve_multicam_strip_target(
            cursor,
            multicam_name=multicam_name,
            media_id=media_id,
            sequence_id=sequence_id,
        )
        audio_track_ids = _fetch_track_ids(cursor, sequence_id=target["multicam_sequence_id"], track_type=1)
        audio_item_ids = _fetch_audio_item_ids(cursor, audio_track_ids=audio_track_ids)
        if not audio_track_ids and not allow_missing_audio:
            raise ValidationError(
                "Native multicam clip has no embedded audio tracks to strip.",
                details={
                    "reason": "multicam_audio_already_missing",
                    **target,
                    "required_option": "--allow-missing-audio",
                },
            )
        fields = _fetch_media_audio_fields(cursor, media_id=target["multicam_media_id"])
        counts = _build_counts(cursor, sequence_id=target["multicam_sequence_id"], audio_item_ids=audio_item_ids)
        return {
            **target,
            "would_remove_audio_tracks": len(audio_track_ids),
            "would_remove_audio_items": len(audio_item_ids),
            "video_tracks_preserved": counts["video_tracks"],
            "video_items_preserved": counts["video_items"],
            "audio_source_would_clear": fields["audio_source"] is not None,
            "virtual_audio_tracks_would_clear": fields["virtual_audio_tracks_ba"] is not None,
            "counts": counts,
        }
    finally:
        connection.close()


def _write_multicam_embedded_audio_strip(
    cursor: sqlite3.Cursor,
    *,
    multicam_name: str | None = None,
    media_id: str | None = None,
    sequence_id: str | None = None,
    allow_missing_audio: bool = False,
) -> dict[str, Any]:
    target = resolve_multicam_strip_target(
        cursor,
        multicam_name=multicam_name,
        media_id=media_id,
        sequence_id=sequence_id,
    )
    resolved_media_id = target["multicam_media_id"]
    resolved_sequence_id = target["multicam_sequence_id"]
    audio_track_ids = _fetch_track_ids(cursor, sequence_id=resolved_sequence_id, track_type=1)
    audio_item_ids = _fetch_audio_item_ids(cursor, audio_track_ids=audio_track_ids)
    before_fields = _fetch_media_audio_fields(cursor, media_id=resolved_media_id)
    if not audio_track_ids and not allow_missing_audio:
        raise ValidationError(
            "Native multicam clip has no embedded audio tracks to strip.",
            details={
                "reason": "multicam_audio_already_missing",
                **target,
                "required_option": "--allow-missing-audio",
            },
        )

    if audio_track_ids:
        cursor.execute(
            f"DELETE FROM Sm2SequenceContainer_Sm2TiTrack WHERE DbAssociate IN ({_placeholders(audio_track_ids)})",
            tuple(audio_track_ids),
        )
        cursor.execute(
            f"DELETE FROM Sm2TiItem_Sm2TiTrack WHERE DbOwner IN ({_placeholders(audio_track_ids)})",
            tuple(audio_track_ids),
        )
        if audio_item_ids:
            cursor.execute(
                f"DELETE FROM Sm2TiItem WHERE Sm2TiItem_id IN ({_placeholders(audio_item_ids)})",
                tuple(audio_item_ids),
            )
        cursor.execute(
            f"DELETE FROM Sm2TiTrack WHERE Sm2TiTrack_id IN ({_placeholders(audio_track_ids)})",
            tuple(audio_track_ids),
        )
    cursor.execute(
        "UPDATE Sm2MpMedia SET AudioSource = NULL, VirtualAudioTracksBA = NULL WHERE Sm2MpMedia_id = ?",
        (resolved_media_id,),
    )
    after_counts = _build_counts(cursor, sequence_id=resolved_sequence_id, audio_item_ids=audio_item_ids)

    changed = bool(
        audio_track_ids
        or audio_item_ids
        or before_fields["audio_source"] is not None
        or before_fields["virtual_audio_tracks_ba"] is not None
    )
    return {
        "action": "multicam.strip_embedded_audio",
        "changed": changed,
        **target,
        "removed_audio_tracks": len(audio_track_ids),
        "removed_audio_items": len(audio_item_ids),
        "video_tracks_preserved": after_counts["video_tracks"],
        "video_items_preserved": after_counts["video_items"],
        "_removed_audio_item_ids": audio_item_ids,
    }


def strip_multicam_embedded_audio(
    conn: Any,
    *,
    multicam_name: str | None = None,
    media_id: str | None = None,
    sequence_id: str | None = None,
    allow_missing_audio: bool = False,
) -> dict[str, Any]:
    def _writer(_connection: sqlite3.Connection, cursor: sqlite3.Cursor, _session: db_session.DiskDbMutationSession) -> dict[str, Any]:
        return _write_multicam_embedded_audio_strip(
            cursor,
            multicam_name=multicam_name,
            media_id=media_id,
            sequence_id=sequence_id,
            allow_missing_audio=allow_missing_audio,
        )

    def _verifier(_connection: Any, mutation_result: dict[str, Any], session: db_session.DiskDbMutationSession) -> dict[str, Any]:
        with sqlite3.connect(session.project_db_path) as fresh_connection:
            fresh_cursor = fresh_connection.cursor()
            return _build_verification(
                fresh_cursor,
                media_id=str(mutation_result["multicam_media_id"]),
                sequence_id=str(mutation_result["multicam_sequence_id"]),
                removed_audio_item_ids=list(mutation_result.get("_removed_audio_item_ids") or []),
            )

    result = db_session.execute_sqlite_disk_db_mutation(
        conn,
        context="Native multicam embedded audio strip",
        writer=_writer,
        verifier=_verifier,
        allow_project_name_inference=True,
    )
    result.pop("_removed_audio_item_ids", None)
    return result
