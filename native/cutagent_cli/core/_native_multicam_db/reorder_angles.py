"""Native multicam angle reorder helpers."""

from __future__ import annotations

import os
import sqlite3
from typing import Any

from ...errors import ValidationError
from .. import db_session
from .strip_audio import resolve_multicam_strip_target


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _normalized_lower(value: Any) -> str:
    return _normalize_text(value).lower()


def _expand_path(value: Any) -> str:
    normalized = _normalize_text(value)
    if not normalized:
        return ""
    return os.path.abspath(os.path.expanduser(normalized))


def _track_row_summary(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "track_id": row["track_id"],
        "current_index": row["current_index"],
        "user_defined_name": row["user_defined_name"],
        "clip_name": row["clip_name"],
        "media_file_path": row["media_file_path"],
    }


def _fetch_sequence_container_id(cursor: sqlite3.Cursor, *, sequence_id: str) -> str:
    row = cursor.execute(
        "SELECT Sm2SequenceContainer_id FROM Sm2SequenceContainer WHERE Sm2Sequence_id = ?",
        (sequence_id,),
    ).fetchone()
    if not row or not row[0]:
        raise ValidationError(
            "Native multicam sequence container could not be found.",
            details={
                "reason": "multicam_sequence_container_missing",
                "multicam_sequence_id": sequence_id,
            },
        )
    return str(row[0])


def _fetch_track_rows(
    cursor: sqlite3.Cursor,
    *,
    container_id: str,
    track_type: int,
    property_name: str,
) -> list[dict[str, Any]]:
    rows = cursor.execute(
        """
        SELECT
          track.Sm2TiTrack_id AS TrackId,
          rel.DbIndex AS CurrentIndex,
          track.UserDefinedName AS UserDefinedName,
          item.Name AS ClipName,
          item.MediaFilePath AS MediaFilePath
        FROM Sm2TiTrack track
        LEFT JOIN Sm2SequenceContainer_Sm2TiTrack rel
          ON rel.DbOwner = ?
         AND rel.DbAssociate = track.Sm2TiTrack_id
         AND rel.DbPropertyName = ?
        LEFT JOIN Sm2TiItem item ON item.Sm2TiTrack_id = track.Sm2TiTrack_id
        WHERE track.Sm2SequenceContainer_id = ?
          AND track.Type = ?
        ORDER BY
          CASE WHEN rel.DbIndex IS NULL THEN 1 ELSE 0 END,
          rel.DbIndex,
          track.Sm2TiTrack_id
        """,
        (container_id, property_name, container_id, int(track_type)),
    ).fetchall()

    deduped: list[dict[str, Any]] = []
    seen_track_ids: set[str] = set()
    for row in rows:
        track_id = _normalize_text(row[0])
        if not track_id or track_id in seen_track_ids:
            continue
        seen_track_ids.add(track_id)
        deduped.append(
            {
                "track_id": track_id,
                "current_index": int(row[1]) if row[1] not in (None, "") else None,
                "user_defined_name": _normalize_text(row[2]) or None,
                "clip_name": _normalize_text(row[3]) or None,
                "media_file_path": _normalize_text(row[4]) or None,
                "property_name": property_name,
                "track_type": int(track_type),
            }
        )
    return deduped


def _count_track_rows(cursor: sqlite3.Cursor, *, sequence_id: str, track_type: int) -> int:
    row = cursor.execute(
        "SELECT COUNT(*) FROM Sm2TiTrack WHERE Sequence = ? AND Type = ?",
        (sequence_id, int(track_type)),
    ).fetchone()
    return int((row[0] if row else 0) or 0)


def _count_track_items(cursor: sqlite3.Cursor, *, sequence_id: str, track_type: int) -> int:
    row = cursor.execute(
        """
        SELECT COUNT(*)
        FROM Sm2TiItem item
        JOIN Sm2TiTrack track ON track.Sm2TiTrack_id = item.Sm2TiTrack_id
        WHERE track.Sequence = ?
          AND track.Type = ?
        """,
        (sequence_id, int(track_type)),
    ).fetchone()
    return int((row[0] if row else 0) or 0)


def _build_counts(cursor: sqlite3.Cursor, *, sequence_id: str) -> dict[str, int]:
    return {
        "video_tracks": _count_track_rows(cursor, sequence_id=sequence_id, track_type=0),
        "video_items": _count_track_items(cursor, sequence_id=sequence_id, track_type=0),
        "audio_tracks": _count_track_rows(cursor, sequence_id=sequence_id, track_type=1),
        "audio_items": _count_track_items(cursor, sequence_id=sequence_id, track_type=1),
    }


def _requested_order(values: list[str] | None) -> list[str]:
    requested = [_normalize_text(value) for value in list(values or []) if _normalize_text(value)]
    if not requested:
        raise ValidationError(
            "Native multicam angle reorder requires at least one --angle-order value.",
            details={"reason": "missing_angle_order"},
        )
    duplicates = sorted({value for value in requested if requested.count(value) > 1})
    if duplicates:
        raise ValidationError(
            "Native multicam angle reorder does not allow duplicate requested angle-order values.",
            details={
                "reason": "duplicate_angle_order_values",
                "duplicates": duplicates,
                "requested_order": requested,
            },
        )
    return requested


def _match_labels(row: dict[str, Any], requested_value: str) -> list[str]:
    requested_raw = _normalize_text(requested_value)
    requested_lower = requested_raw.lower()
    requested_path = _expand_path(requested_raw)
    requested_path_lower = requested_path.lower()
    requested_basename_lower = os.path.basename(requested_path or requested_raw).lower()

    labels: list[str] = []
    media_path = _normalize_text(row.get("media_file_path"))
    clip_name = _normalize_text(row.get("clip_name"))
    if media_path and requested_lower == media_path.lower():
        labels.append("media_file_path")
    expanded_media_path = _expand_path(media_path)
    if expanded_media_path and requested_path_lower == expanded_media_path.lower():
        labels.append("media_file_path")
    if media_path and requested_basename_lower == os.path.basename(media_path).lower():
        labels.append("basename")
    if clip_name and requested_lower == clip_name.lower():
        labels.append("clip_name")
    return list(dict.fromkeys(labels))


def _resolve_track_order(
    rows: list[dict[str, Any]],
    *,
    requested_order: list[str],
    strict: bool,
    property_name: str,
) -> dict[str, Any]:
    remaining = list(rows)
    matched_rows: list[dict[str, Any]] = []
    updated_relation_rows: list[dict[str, Any]] = []

    for requested_index, requested_value in enumerate(requested_order):
        candidates: list[tuple[dict[str, Any], list[str]]] = []
        for row in remaining:
            labels = _match_labels(row, requested_value)
            if labels:
                candidates.append((row, labels))
        if not candidates:
            raise ValidationError(
                "Requested multicam angle-order value did not match any track.",
                details={
                    "reason": "angle_order_value_not_found",
                    "property_name": property_name,
                    "value": requested_value,
                    "available_tracks": [_track_row_summary(row) for row in rows],
                },
            )
        if len(candidates) > 1:
            raise ValidationError(
                "Requested multicam angle-order value matched multiple tracks.",
                details={
                    "reason": "angle_order_value_ambiguous",
                    "property_name": property_name,
                    "value": requested_value,
                    "candidates": [
                        {
                            **_track_row_summary(candidate_row),
                            "matched_by": candidate_labels,
                        }
                        for candidate_row, candidate_labels in candidates
                    ],
                },
            )

        matched_row, labels = candidates[0]
        remaining = [row for row in remaining if row["track_id"] != matched_row["track_id"]]
        matched_rows.append(
            {
                **matched_row,
                "matched_value": requested_value,
                "matched_by": labels[0],
            }
        )

    if strict and remaining:
        raise ValidationError(
            "Strict native multicam angle reorder requires every track to be covered exactly once.",
            details={
                "reason": "angle_order_incomplete",
                "property_name": property_name,
                "requested_order": requested_order,
                "unmatched_tracks": [_track_row_summary(row) for row in remaining],
                "track_count": len(rows),
            },
        )

    after_rows = matched_rows + remaining
    ordered_after_rows: list[dict[str, Any]] = []
    for new_index, row in enumerate(after_rows):
        ordered_row = {**row, "new_index": new_index}
        ordered_after_rows.append(ordered_row)
        updated_relation_rows.append(
            {
                "property_name": property_name,
                "track_id": row["track_id"],
                "old_index": row["current_index"],
                "new_index": new_index,
                "clip_name": row["clip_name"],
                "media_file_path": row["media_file_path"],
                "matched_value": row.get("matched_value"),
                "matched_by": row.get("matched_by"),
                "changed": row.get("current_index") != new_index,
            }
        )
    return {
        "before_rows": [{**row} for row in rows],
        "after_rows": ordered_after_rows,
        "updated_relation_rows": updated_relation_rows,
        "unmatched_rows": [_track_row_summary(row) for row in remaining],
    }


def _rename_track_rows(rows: list[dict[str, Any]], *, property_name: str) -> list[dict[str, Any]]:
    renamed_rows: list[dict[str, Any]] = []
    for row in rows:
        new_name = f"Angle {int(row['new_index']) + 1}"
        old_name = row.get("user_defined_name")
        renamed_rows.append(
            {
                "property_name": property_name,
                "track_id": row["track_id"],
                "old_name": old_name,
                "new_name": new_name,
                "changed": old_name != new_name,
            }
        )
    return renamed_rows


def _plan_reorder(
    cursor: sqlite3.Cursor,
    *,
    multicam_name: str | None,
    media_id: str | None,
    sequence_id: str | None,
    requested_order: list[str],
    rename_tracks: bool,
    include_audio: bool,
    strict: bool,
) -> dict[str, Any]:
    target = resolve_multicam_strip_target(
        cursor,
        multicam_name=multicam_name,
        media_id=media_id,
        sequence_id=sequence_id,
    )
    resolved_sequence_id = str(target["multicam_sequence_id"])
    container_id = _fetch_sequence_container_id(cursor, sequence_id=resolved_sequence_id)
    before_counts = _build_counts(cursor, sequence_id=resolved_sequence_id)
    video_rows = _fetch_track_rows(cursor, container_id=container_id, track_type=0, property_name="VideoTrackVec")
    if not video_rows:
        raise ValidationError(
            "Native multicam clip has no video angle tracks to reorder.",
            details={
                "reason": "multicam_video_tracks_missing",
                **target,
            },
        )

    video_plan = _resolve_track_order(
        video_rows,
        requested_order=requested_order,
        strict=strict,
        property_name="VideoTrackVec",
    )

    audio_rows = _fetch_track_rows(cursor, container_id=container_id, track_type=1, property_name="AudioTrackVec")
    audio_plan: dict[str, Any] | None = None
    audio_status = "skipped"
    if include_audio and audio_rows:
        audio_plan = _resolve_track_order(
            audio_rows,
            requested_order=requested_order,
            strict=strict,
            property_name="AudioTrackVec",
        )
        audio_status = "planned"
    elif include_audio:
        audio_status = "missing"

    renamed_track_rows = _rename_track_rows(video_plan["after_rows"], property_name="VideoTrackVec") if rename_tracks else []
    if rename_tracks and audio_plan is not None:
        renamed_track_rows.extend(_rename_track_rows(audio_plan["after_rows"], property_name="AudioTrackVec"))

    relation_rows = list(video_plan["updated_relation_rows"])
    if audio_plan is not None:
        relation_rows.extend(audio_plan["updated_relation_rows"])

    relation_changed = any(bool(row["changed"]) for row in relation_rows)
    rename_changed = any(bool(row["changed"]) for row in renamed_track_rows)
    return {
        "action": "multicam.reorder_angles",
        "selector": {
            "multicam_name": _normalize_text(multicam_name) or None,
            "media_id": _normalize_text(media_id) or None,
            "sequence_id": _normalize_text(sequence_id) or None,
        },
        **target,
        "requested_order": list(requested_order),
        "rename_tracks": bool(rename_tracks),
        "include_audio": bool(include_audio),
        "strict": bool(strict),
        "before": {
            "video": video_plan["before_rows"],
            "audio": audio_plan["before_rows"] if audio_plan is not None else audio_rows,
        },
        "after": {
            "video": video_plan["after_rows"],
            "audio": audio_plan["after_rows"] if audio_plan is not None else audio_rows,
        },
        "updated_relation_rows": relation_rows,
        "renamed_track_rows": renamed_track_rows,
        "audio_status": audio_status,
        "would_change": relation_changed or rename_changed,
        "before_counts": before_counts,
        "_container_id": container_id,
        "_expected_after_video": video_plan["after_rows"],
        "_expected_after_audio": audio_plan["after_rows"] if audio_plan is not None else [],
    }


def _apply_relation_order(
    cursor: sqlite3.Cursor,
    *,
    container_id: str,
    property_name: str,
    rows: list[dict[str, Any]],
) -> None:
    cursor.execute(
        """
        DELETE FROM Sm2SequenceContainer_Sm2TiTrack
        WHERE DbOwner = ?
          AND DbPropertyName = ?
        """,
        (container_id, property_name),
    )
    for row in rows:
        cursor.execute(
            """
            INSERT INTO Sm2SequenceContainer_Sm2TiTrack (DbOwner, DbAssociate, DbPropertyName, DbIndex)
            VALUES (?, ?, ?, ?)
            """,
            (container_id, row["track_id"], property_name, int(row["new_index"])),
        )


def _apply_track_renames(cursor: sqlite3.Cursor, *, renamed_track_rows: list[dict[str, Any]]) -> None:
    for row in renamed_track_rows:
        cursor.execute(
            "UPDATE Sm2TiTrack SET UserDefinedName = ? WHERE Sm2TiTrack_id = ?",
            (row["new_name"], row["track_id"]),
        )


def _row_track_signature(rows: list[dict[str, Any]]) -> list[tuple[str, int | None]]:
    return [(str(row["track_id"]), int(row["new_index"]) if row.get("new_index") is not None else None) for row in rows]


def _verification_track_rows(
    cursor: sqlite3.Cursor,
    *,
    sequence_id: str,
    expected_rows: list[dict[str, Any]],
    property_name: str,
    track_type: int,
) -> list[dict[str, Any]]:
    container_id = _fetch_sequence_container_id(cursor, sequence_id=sequence_id)
    rows = _fetch_track_rows(cursor, container_id=container_id, track_type=track_type, property_name=property_name)
    return [{**row, "new_index": row.get("current_index")} for row in rows]


def _build_verification(
    cursor: sqlite3.Cursor,
    *,
    sequence_id: str,
    expected_video_rows: list[dict[str, Any]],
    expected_audio_rows: list[dict[str, Any]],
    before_counts: dict[str, int],
    rename_tracks: bool,
    include_audio: bool,
) -> dict[str, Any]:
    video_rows = _verification_track_rows(
        cursor,
        sequence_id=sequence_id,
        expected_rows=expected_video_rows,
        property_name="VideoTrackVec",
        track_type=0,
    )
    audio_rows = _verification_track_rows(
        cursor,
        sequence_id=sequence_id,
        expected_rows=expected_audio_rows,
        property_name="AudioTrackVec",
        track_type=1,
    )
    after_counts = _build_counts(cursor, sequence_id=sequence_id)

    checks = [
        {
            "name": "video_track_order",
            "ok": _row_track_signature(video_rows) == _row_track_signature(expected_video_rows),
            "actual": _row_track_signature(video_rows),
            "expected": _row_track_signature(expected_video_rows),
        },
        {
            "name": "video_track_count_preserved",
            "ok": after_counts["video_tracks"] == before_counts["video_tracks"],
            "before": before_counts["video_tracks"],
            "after": after_counts["video_tracks"],
        },
        {
            "name": "video_item_count_preserved",
            "ok": after_counts["video_items"] == before_counts["video_items"],
            "before": before_counts["video_items"],
            "after": after_counts["video_items"],
        },
    ]
    if rename_tracks:
        checks.append(
            {
                "name": "video_track_names_renamed",
                "ok": [
                    _normalize_text(row.get("user_defined_name"))
                    for row in video_rows
                ] == [f"Angle {index}" for index in range(1, len(video_rows) + 1)],
                "actual": [_normalize_text(row.get("user_defined_name")) for row in video_rows],
            }
        )
    if include_audio and expected_audio_rows:
        checks.extend(
            [
                {
                    "name": "audio_track_order",
                    "ok": _row_track_signature(audio_rows) == _row_track_signature(expected_audio_rows),
                    "actual": _row_track_signature(audio_rows),
                    "expected": _row_track_signature(expected_audio_rows),
                },
                {
                    "name": "audio_track_count_preserved",
                    "ok": after_counts["audio_tracks"] == before_counts["audio_tracks"],
                    "before": before_counts["audio_tracks"],
                    "after": after_counts["audio_tracks"],
                },
                {
                    "name": "audio_item_count_preserved",
                    "ok": after_counts["audio_items"] == before_counts["audio_items"],
                    "before": before_counts["audio_items"],
                    "after": after_counts["audio_items"],
                },
            ]
        )
        if rename_tracks:
            checks.append(
                {
                    "name": "audio_track_names_renamed",
                    "ok": [
                        _normalize_text(row.get("user_defined_name"))
                        for row in audio_rows
                    ] == [f"Angle {index}" for index in range(1, len(audio_rows) + 1)],
                    "actual": [_normalize_text(row.get("user_defined_name")) for row in audio_rows],
                }
            )
    elif include_audio:
        checks.append(
            {
                "name": "audio_tracks_missing_tolerated",
                "ok": after_counts["audio_tracks"] == 0,
                "after": after_counts["audio_tracks"],
            }
        )

    status = "verified" if all(bool(check["ok"]) for check in checks) else "failed"
    return {
        "status": status,
        "checks": checks,
        "counts": after_counts,
    }


def plan_multicam_angle_reorder(
    project_db_path: str,
    *,
    multicam_name: str | None = None,
    media_id: str | None = None,
    sequence_id: str | None = None,
    angle_order: list[str] | None = None,
    rename_tracks: bool = True,
    include_audio: bool = True,
    strict: bool = True,
) -> dict[str, Any]:
    requested_order = _requested_order(angle_order)
    connection = sqlite3.connect(project_db_path)
    try:
        cursor = connection.cursor()
        plan = _plan_reorder(
            cursor,
            multicam_name=multicam_name,
            media_id=media_id,
            sequence_id=sequence_id,
            requested_order=requested_order,
            rename_tracks=rename_tracks,
            include_audio=include_audio,
            strict=strict,
        )
        plan.pop("_container_id", None)
        plan.pop("_expected_after_video", None)
        plan.pop("_expected_after_audio", None)
        return plan
    finally:
        connection.close()


def _write_multicam_angle_reorder(
    cursor: sqlite3.Cursor,
    *,
    multicam_name: str | None = None,
    media_id: str | None = None,
    sequence_id: str | None = None,
    angle_order: list[str] | None = None,
    rename_tracks: bool = True,
    include_audio: bool = True,
    strict: bool = True,
) -> dict[str, Any]:
    requested_order = _requested_order(angle_order)
    plan = _plan_reorder(
        cursor,
        multicam_name=multicam_name,
        media_id=media_id,
        sequence_id=sequence_id,
        requested_order=requested_order,
        rename_tracks=rename_tracks,
        include_audio=include_audio,
        strict=strict,
    )
    container_id = str(plan.pop("_container_id"))
    expected_video_rows = list(plan.pop("_expected_after_video"))
    expected_audio_rows = list(plan.pop("_expected_after_audio"))
    before_counts = dict(plan["before_counts"])

    _apply_relation_order(
        cursor,
        container_id=container_id,
        property_name="VideoTrackVec",
        rows=expected_video_rows,
    )
    if include_audio and expected_audio_rows:
        _apply_relation_order(
            cursor,
            container_id=container_id,
            property_name="AudioTrackVec",
            rows=expected_audio_rows,
        )
    if rename_tracks and plan["renamed_track_rows"]:
        _apply_track_renames(cursor, renamed_track_rows=list(plan["renamed_track_rows"]))

    plan["changed"] = bool(plan["would_change"])
    plan["_expected_video_rows"] = expected_video_rows
    plan["_expected_audio_rows"] = expected_audio_rows
    plan["_before_counts"] = before_counts
    return plan


def reorder_multicam_angles(
    conn: Any,
    *,
    multicam_name: str | None = None,
    media_id: str | None = None,
    sequence_id: str | None = None,
    angle_order: list[str] | None = None,
    rename_tracks: bool = True,
    include_audio: bool = True,
    strict: bool = True,
) -> dict[str, Any]:
    def _writer(_connection: sqlite3.Connection, cursor: sqlite3.Cursor, _session: db_session.DiskDbMutationSession) -> dict[str, Any]:
        return _write_multicam_angle_reorder(
            cursor,
            multicam_name=multicam_name,
            media_id=media_id,
            sequence_id=sequence_id,
            angle_order=angle_order,
            rename_tracks=rename_tracks,
            include_audio=include_audio,
            strict=strict,
        )

    def _verifier(_connection: Any, mutation_result: dict[str, Any], session: db_session.DiskDbMutationSession) -> dict[str, Any]:
        with sqlite3.connect(session.project_db_path) as fresh_connection:
            fresh_cursor = fresh_connection.cursor()
            return _build_verification(
                fresh_cursor,
                sequence_id=str(mutation_result["multicam_sequence_id"]),
                expected_video_rows=list(mutation_result.get("_expected_video_rows") or []),
                expected_audio_rows=list(mutation_result.get("_expected_audio_rows") or []),
                before_counts=dict(mutation_result.get("_before_counts") or {}),
                rename_tracks=bool(rename_tracks),
                include_audio=bool(include_audio),
            )

    result = db_session.execute_sqlite_disk_db_mutation(
        conn,
        context="Native multicam angle reorder",
        writer=_writer,
        verifier=_verifier,
    )
    result.pop("_expected_video_rows", None)
    result.pop("_expected_audio_rows", None)
    result.pop("_before_counts", None)
    return result
