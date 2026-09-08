from __future__ import annotations

import hashlib
import json
import sqlite3
import struct
from typing import Any

from ...errors import ValidationError
from ...multicam_support import SOURCE_CLIP_COUNT_PER_ANGLE_LIMIT, SOURCE_ITEM_REPRESENTATION


def _revision_json_value(value: Any) -> Any:
    if isinstance(value, bytes):
        return {"blob_sha256": hashlib.sha256(value).hexdigest(), "blob_size": len(value)}
    if isinstance(value, dict):
        return {str(key): _revision_json_value(item) for key, item in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [_revision_json_value(item) for item in value]
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return str(value)


def _table_exists(cursor: sqlite3.Cursor, table: str) -> bool:
    return cursor.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ? LIMIT 1",
        (table,),
    ).fetchone() is not None


def _column_exists(cursor: sqlite3.Cursor, table: str, column: str) -> bool:
    return any(str(row[1]) == column for row in cursor.execute(f'PRAGMA table_info("{table}")').fetchall())


def _row_dict(cursor: sqlite3.Cursor, query: str, params: tuple[Any, ...]) -> dict[str, Any] | None:
    row = cursor.execute(query, params).fetchone()
    if row is None:
        return None
    return {str(column[0]): value for column, value in zip(cursor.description or (), row)}


def _item_grade_revision_digest(cursor: sqlite3.Cursor, item_id: str | None) -> str | None:
    """Digest local/remote grade rows without returning proprietary grade payloads."""
    if (
        not item_id
        or not _column_exists(cursor, "Sm2TiItem", "pLmVerTable")
        or not _table_exists(cursor, "ListMgt::LmVersionTable")
        or not _table_exists(cursor, "ListMgt::LmVersion")
    ):
        return None
    item = _row_dict(
        cursor,
        'SELECT pLmVerTable FROM Sm2TiItem WHERE Sm2TiItem_id = ? LIMIT 1',
        (item_id,),
    )
    table_id = str((item or {}).get("pLmVerTable") or "")
    if not table_id:
        return None
    evidence: list[dict[str, Any]] = []
    seen: set[str] = set()
    while table_id and table_id not in seen and len(seen) < 4:
        seen.add(table_id)
        table_row = _row_dict(
            cursor,
            'SELECT * FROM "ListMgt::LmVersionTable" WHERE "ListMgt::LmVersionTable_id" = ? LIMIT 1',
            (table_id,),
        )
        if table_row is None:
            break
        active_id = str(table_row.get("pActive") or "")
        version_row = (
            _row_dict(
                cursor,
                'SELECT * FROM "ListMgt::LmVersion" WHERE "ListMgt::LmVersion_id" = ? LIMIT 1',
                (active_id,),
            )
            if active_id
            else None
        )
        evidence.append({"table": table_row, "active_version": version_row})
        table_id = str(table_row.get("pRemoteTable") or "")
    if not evidence:
        return None
    encoded = json.dumps(
        _revision_json_value(evidence),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _items_are_contiguous(items: list[dict[str, Any]]) -> bool:
    ordered_items = sorted(
        (entry for entry in items if entry.get("source_media_id")),
        key=lambda item: (int(item.get("item_index") or 0), int(item.get("start_frame") or 0)),
    )
    return all(
        int(current["start_frame"])
        == int(previous["start_frame"]) + int(previous["duration_frames"])
        for previous, current in zip(ordered_items, ordered_items[1:])
    )


def _items_are_non_overlapping(items: list[dict[str, Any]]) -> bool:
    ordered_items = sorted(
        (entry for entry in items if entry.get("source_media_id")),
        key=lambda item: (int(item.get("start_frame") or 0), int(item.get("item_index") or 0)),
    )
    return all(
        int(current["start_frame"])
        >= int(previous["start_frame"]) + int(previous["duration_frames"])
        for previous, current in zip(ordered_items, ordered_items[1:])
    )


def _item_gaps(items: list[dict[str, Any]]) -> list[dict[str, int]]:
    ordered_items = sorted(
        (entry for entry in items if entry.get("source_media_id")),
        key=lambda item: (int(item.get("start_frame") or 0), int(item.get("item_index") or 0)),
    )
    gaps: list[dict[str, int]] = []
    for previous, current in zip(ordered_items, ordered_items[1:]):
        previous_end = int(previous["start_frame"]) + int(previous["duration_frames"])
        current_start = int(current["start_frame"])
        if current_start > previous_end:
            gaps.append(
                {
                    "after_item_index": int(previous["item_index"]),
                    "before_item_index": int(current["item_index"]),
                    "start_frame": previous_end,
                    "end_frame": current_start,
                    "duration_frames": current_start - previous_end,
                }
            )
    return gaps


def _inspect_multicam_bindings_with_cursor(
    cursor: sqlite3.Cursor,
    *,
    multicam_media_id: str | None = None,
    multicam_name: str | None = None,
    row_to_dict_fn,
    selector_signature_fn,
) -> dict[str, Any]:
    if not multicam_media_id and not multicam_name:
        raise ValidationError(
            "Multicam binding inspection requires multicam_media_id or multicam_name.",
            details={"reason": "missing_multicam_identifier"},
        )

    where_clauses: list[str] = []
    params: list[Any] = []
    if multicam_media_id:
        where_clauses.append("multicam.Sm2MpMedia_id = ?")
        params.append(multicam_media_id)
    if multicam_name:
        where_clauses.append("multicam.Name = ?")
        params.append(multicam_name)

    rows = cursor.execute(
        f"""
        SELECT
            multicam.Sm2MpMedia_id AS MulticamMediaId,
            multicam.Name AS MulticamName,
            seq.Sm2Sequence_id AS MulticamSequenceId,
            seq.FrameRate AS SequenceFrameRate,
            seq.MediaExtents AS SequenceMediaExtents,
            rel.DbIndex AS AngleIndex,
            track.Type AS TrackType,
            track.Sm2TiTrack_id AS TrackId,
            track.UserDefinedName AS TrackName,
            track.Flags AS TrackFlags,
            item.Sm2TiItem_id AS ItemId,
            (
                SELECT item_rel.DbIndex
                FROM Sm2TiItem_Sm2TiTrack item_rel
                WHERE item_rel.DbOwner = track.Sm2TiTrack_id
                  AND item_rel.DbAssociate = item.Sm2TiItem_id
                  AND item_rel.DbPropertyName = 'Items'
                LIMIT 1
            ) AS ItemIndex,
            item.Start AS ItemStart,
            item.Duration AS ItemDuration,
            item."In" AS ItemIn,
            item.MediaRef AS SourceMediaId,
            item.MediaFilePath AS MediaFilePath,
            item.CurrentSelectorIdx AS CurrentSelectorIdx,
            item.FieldsBlob AS ItemFieldsBlob,
            source.Name AS SourceClipName
        FROM Sm2MpMedia multicam
        JOIN Sm2Sequence seq ON seq.Sm2MpMedia_id = multicam.Sm2MpMedia_id
        JOIN Sm2SequenceContainer container ON container.Sm2Sequence_id = seq.Sm2Sequence_id
        JOIN Sm2SequenceContainer_Sm2TiTrack rel
          ON rel.DbOwner = container.Sm2SequenceContainer_id
        JOIN Sm2TiTrack track ON track.Sm2TiTrack_id = rel.DbAssociate
        LEFT JOIN Sm2TiItem item
          ON item.Sm2TiTrack_id = track.Sm2TiTrack_id
         AND (
            (track.Type = 0 AND item.DbType = 'Sm2TiVideoClip')
            OR (track.Type = 1 AND item.DbType = 'Sm2TiAudioClip')
         )
        LEFT JOIN Sm2MpMedia source ON source.Sm2MpMedia_id = item.MediaRef
        WHERE {" AND ".join(where_clauses)}
        ORDER BY track.Type, rel.DbIndex, ItemIndex, CAST(item.Start AS INTEGER), item.Sm2TiItem_id
        """,
        tuple(params),
    ).fetchall()
    if not rows:
        raise ValidationError(
            "Could not inspect multicam binding from Project.db.",
            details={
                "reason": "multicam_not_found",
                "multicam_media_id": multicam_media_id,
                "multicam_name": multicam_name,
            },
        )

    payload_rows = [row_to_dict_fn(cursor, row) for row in rows]
    first_row = payload_rows[0]
    sequence_fps = 24.0
    sequence_frame_rate_blob = first_row.get("SequenceFrameRate")
    if sequence_frame_rate_blob and len(sequence_frame_rate_blob) >= 8:
        try:
            sequence_fps = float(struct.unpack("<d", sequence_frame_rate_blob[:8])[0]) or 24.0
        except (struct.error, TypeError, ValueError):
            sequence_fps = 24.0
    sequence_start_frame: int | None = None
    sequence_duration_frames: int | None = None
    sequence_media_extents = first_row.get("SequenceMediaExtents")
    if sequence_media_extents and len(sequence_media_extents) >= 16:
        try:
            start_seconds, duration_seconds = struct.unpack("<dd", sequence_media_extents[:16])
            sequence_start_frame = int(round(float(start_seconds) * sequence_fps))
            sequence_duration_frames = int(round(float(duration_seconds) * sequence_fps))
        except (struct.error, TypeError, ValueError):
            sequence_start_frame = None
            sequence_duration_frames = None
    mappings: dict[str, list[dict[str, Any]]] = {"video": [], "audio": []}
    for payload in payload_rows:
        mapping_key = "audio" if int(payload["TrackType"] or 0) == 1 else "video"
        item_id = str(payload["ItemId"] or "") or None
        mappings[mapping_key].append(
            {
                "angle_index": int(payload["AngleIndex"] or 0),
                "track_id": str(payload["TrackId"] or ""),
                "track_name": str(payload["TrackName"] or ""),
                "track_enabled": not bool(int(payload["TrackFlags"] or 0) & 2),
                "item_id": item_id,
                "item_index": int(payload["ItemIndex"] or 0),
                "start_frame": int(payload["ItemStart"] or 0),
                "duration_frames": int(payload["ItemDuration"] or 0),
                "source_in_frame": int(payload["ItemIn"] or 0),
                "source_media_id": str(payload["SourceMediaId"] or "") or None,
                "clip_name": str(payload["SourceClipName"] or "").strip() or None,
                "media_file_path": str(payload["MediaFilePath"] or "").strip() or None,
                "current_selector_idx": (
                    int(payload["CurrentSelectorIdx"])
                    if payload["CurrentSelectorIdx"] not in (None, "")
                    else None
                ),
                "selector_signature": selector_signature_fn(payload["ItemFieldsBlob"]),
                "selector_blob_size": len(payload["ItemFieldsBlob"]) if payload["ItemFieldsBlob"] else 0,
                "grade_revision_digest": _item_grade_revision_digest(cursor, item_id),
                "is_placeholder": payload["SourceMediaId"] in (None, ""),
            }
        )

    mismatches: list[dict[str, Any]] = []
    video_track_ids = {entry["track_id"] for entry in mappings["video"]}
    audio_track_ids = {entry["track_id"] for entry in mappings["audio"]}
    if len(video_track_ids) != len(audio_track_ids):
        mismatches.append(
            {
                "kind": "track_count_mismatch",
                "video_track_count": len(video_track_ids),
                "audio_track_count": len(audio_track_ids),
            }
        )
    angle_indices = {
        int(entry["angle_index"])
        for mapping in mappings.values()
        for entry in mapping
    }
    max_angle_count = max(angle_indices) + 1 if angle_indices else 0
    video_by_angle = {
        angle_index: [
            entry for entry in mappings["video"]
            if int(entry["angle_index"]) == angle_index
        ]
        for angle_index in range(max_angle_count)
    }
    audio_by_angle = {
        angle_index: [
            entry for entry in mappings["audio"]
            if int(entry["angle_index"]) == angle_index
        ]
        for angle_index in range(max_angle_count)
    }
    for angle_index in range(max_angle_count):
        video_entries = video_by_angle.get(angle_index) or []
        audio_entries = audio_by_angle.get(angle_index) or []
        populated_video_entries = [entry for entry in video_entries if entry["source_media_id"] is not None]
        populated_audio_entries = [entry for entry in audio_entries if entry["source_media_id"] is not None]
        if not populated_video_entries:
            mismatches.append(
                {
                    "kind": "empty_video_angle",
                    "angle_index": angle_index,
                    "actual_source_media_id": None,
                }
            )
        if not populated_audio_entries:
            mismatches.append(
                {
                    "kind": "empty_audio_angle",
                    "angle_index": angle_index,
                    "actual_source_media_id": None,
                }
            )
        audio_by_item_index = {int(entry["item_index"]): entry for entry in populated_audio_entries}
        for video_entry in populated_video_entries:
            audio_entry = audio_by_item_index.get(int(video_entry["item_index"]))
            if (
                audio_entry is not None
                and audio_entry["source_media_id"] != video_entry["source_media_id"]
            ):
                mismatches.append(
                    {
                        "kind": "audio_video_binding_mismatch",
                        "angle_index": angle_index,
                        "item_index": int(video_entry["item_index"]),
                        "video_source_media_id": video_entry["source_media_id"],
                        "audio_source_media_id": audio_entry["source_media_id"],
                        "video_clip_name": video_entry["clip_name"],
                        "audio_clip_name": audio_entry["clip_name"],
                    }
                )
            if audio_entry is not None and any(
                int(audio_entry[field]) != int(video_entry[field])
                for field in ("start_frame", "duration_frames", "source_in_frame")
            ):
                mismatches.append(
                    {
                        "kind": "audio_video_timing_mismatch",
                        "angle_index": angle_index,
                        "item_index": int(video_entry["item_index"]),
                        "video_timing": {
                            field: int(video_entry[field])
                            for field in ("start_frame", "duration_frames", "source_in_frame")
                        },
                        "audio_timing": {
                            field: int(audio_entry[field])
                            for field in ("start_frame", "duration_frames", "source_in_frame")
                        },
                    }
                )

    mismatch_kinds = {str(entry.get("kind") or "") for entry in mismatches}
    separate_audio_angle_count = sum(
        1
        for entry in mismatches
        if entry.get("kind") == "audio_video_binding_mismatch"
    )
    empty_audio_angle_count = sum(
        1
        for angle_index in range(max_angle_count)
        if not any(entry.get("source_media_id") for entry in audio_by_angle.get(angle_index, []))
    )
    if not mismatches:
        audio_binding_mode = "video_embedded_audio"
    elif mismatch_kinds.issubset({"audio_video_binding_mismatch", "empty_audio_angle"}) and separate_audio_angle_count > 0:
        audio_binding_mode = "separate_audio_sources"
    else:
        audio_binding_mode = "inconsistent"

    angles = [
        {
            "angle_index": angle_index,
            "track_name": next(
                (
                    entry["track_name"]
                    for entry in video_by_angle.get(angle_index, [])
                    if entry.get("track_name")
                ),
                f"Angle {angle_index + 1}",
            ),
            "video_track_name": next((entry["track_name"] for entry in video_by_angle.get(angle_index, []) if entry.get("track_name")), f"Angle {angle_index + 1}"),
            "audio_track_name": next((entry["track_name"] for entry in audio_by_angle.get(angle_index, []) if entry.get("track_name")), f"Angle {angle_index + 1}"),
            "video_enabled": all(
                bool(entry["track_enabled"])
                for entry in video_by_angle.get(angle_index, [])
            ),
            "audio_enabled": all(
                bool(entry["track_enabled"])
                for entry in audio_by_angle.get(angle_index, [])
            ),
            "video_items": video_by_angle.get(angle_index, []),
            "audio_items": audio_by_angle.get(angle_index, []),
            "video_item_count": sum(
                1 for entry in video_by_angle.get(angle_index, []) if entry.get("source_media_id")
            ),
            "audio_item_count": sum(
                1 for entry in audio_by_angle.get(angle_index, []) if entry.get("source_media_id")
            ),
        }
        for angle_index in range(max_angle_count)
    ]
    populated_video_items = [entry for entry in mappings["video"] if entry.get("source_media_id")]
    video_item_ids = [entry["item_id"] for entry in populated_video_items if entry.get("item_id")]
    source_items_are_distinct = len(video_item_ids) == len(populated_video_items) == len(set(video_item_ids))
    source_items_contiguous_by_angle = all(
        _items_are_contiguous(video_by_angle.get(angle_index, []))
        and _items_are_contiguous(audio_by_angle.get(angle_index, []))
        for angle_index in range(max_angle_count)
    )
    source_items_non_overlapping_by_angle = all(
        _items_are_non_overlapping(video_by_angle.get(angle_index, []))
        and _items_are_non_overlapping(audio_by_angle.get(angle_index, []))
        for angle_index in range(max_angle_count)
    )
    source_item_gaps_by_angle = {
        str(angle_index): _item_gaps(video_by_angle.get(angle_index, []))
        for angle_index in range(max_angle_count)
    }
    source_item_edge_gaps_by_angle: dict[str, dict[str, int]] = {}
    if sequence_start_frame is not None and sequence_duration_frames is not None:
        sequence_end_frame = sequence_start_frame + sequence_duration_frames
        for angle_index in range(max_angle_count):
            angle_items = sorted(
                (
                    entry
                    for entry in video_by_angle.get(angle_index, [])
                    if entry.get("source_media_id")
                ),
                key=lambda item: int(item.get("start_frame") or 0),
            )
            if angle_items:
                first_start = int(angle_items[0]["start_frame"])
                last_end = max(
                    int(item["start_frame"]) + int(item["duration_frames"])
                    for item in angle_items
                )
                source_item_edge_gaps_by_angle[str(angle_index)] = {
                    "leading_gap_frames": max(0, first_start - sequence_start_frame),
                    "trailing_gap_frames": max(0, sequence_end_frame - last_end),
                }
    source_items_have_gaps = any(source_item_gaps_by_angle.values()) or any(
        gap["leading_gap_frames"] > 0 or gap["trailing_gap_frames"] > 0
        for gap in source_item_edge_gaps_by_angle.values()
    )
    return {
        "multicam_media_id": str(first_row["MulticamMediaId"] or ""),
        "multicam_name": str(first_row["MulticamName"] or multicam_name or ""),
        "multicam_sequence_id": str(first_row["MulticamSequenceId"] or ""),
        "angle_count": max_angle_count,
        "source_clip_count": sum(
            1 for entry in mappings["video"] if entry.get("source_media_id")
        ),
        "source_item_representation": SOURCE_ITEM_REPRESENTATION,
        "source_clip_count_per_angle_limit": SOURCE_CLIP_COUNT_PER_ANGLE_LIMIT,
        "creates_flattened_media": False,
        "source_items_are_distinct": source_items_are_distinct,
        "source_items_contiguous_by_angle": source_items_contiguous_by_angle,
        "source_items_non_overlapping_by_angle": source_items_non_overlapping_by_angle,
        "source_layout": "sparse" if source_items_have_gaps else "contiguous",
        "source_item_gaps_by_angle": source_item_gaps_by_angle,
        "source_item_edge_gaps_by_angle": source_item_edge_gaps_by_angle,
        "source_items_have_gaps": source_items_have_gaps,
        "sequence_start_frame": sequence_start_frame,
        "sequence_duration_frames": sequence_duration_frames,
        "angles": angles,
        "video_source_mapping": mappings["video"],
        "audio_source_mapping": mappings["audio"],
        "audio_binding_mode": audio_binding_mode,
        "separate_audio_angle_count": separate_audio_angle_count,
        "empty_audio_angle_count": empty_audio_angle_count,
        "binding_consistent": not mismatches,
        "mismatches": mismatches,
    }


def inspect_multicam_bindings(
    project_db_path: str,
    *,
    multicam_media_id: str | None = None,
    multicam_name: str | None = None,
    inspect_with_cursor_fn,
) -> dict[str, Any]:
    connection = sqlite3.connect(project_db_path)
    try:
        cursor = connection.cursor()
        return inspect_with_cursor_fn(
            cursor,
            multicam_media_id=multicam_media_id,
            multicam_name=multicam_name,
        )
    finally:
        connection.close()


def list_multicam_binding_summaries(project_db_path: str, *, row_to_dict_fn) -> list[dict[str, Any]]:
    connection = sqlite3.connect(project_db_path)
    try:
        cursor = connection.cursor()
        rows = cursor.execute(
            """
            SELECT
                multicam.Sm2MpMedia_id AS MulticamMediaId,
                multicam.Name AS MulticamName,
                seq.Sm2Sequence_id AS MulticamSequenceId,
                COUNT(DISTINCT CASE WHEN track.Type = 0 THEN track.Sm2TiTrack_id END) AS VideoAngleCount,
                COUNT(DISTINCT CASE WHEN track.Type = 1 THEN track.Sm2TiTrack_id END) AS AudioAngleCount
            FROM Sm2MpMedia multicam
            LEFT JOIN Sm2Sequence seq ON seq.Sm2MpMedia_id = multicam.Sm2MpMedia_id
            LEFT JOIN Sm2SequenceContainer container ON container.Sm2Sequence_id = seq.Sm2Sequence_id
            LEFT JOIN Sm2SequenceContainer_Sm2TiTrack rel
              ON rel.DbOwner = container.Sm2SequenceContainer_id
            LEFT JOIN Sm2TiTrack track ON track.Sm2TiTrack_id = rel.DbAssociate
            WHERE multicam.DbType = 'Sm2MpMulticamClip'
            GROUP BY multicam.Sm2MpMedia_id, multicam.Name, seq.Sm2Sequence_id
            ORDER BY LOWER(multicam.Name)
            """
        ).fetchall()
        summaries: list[dict[str, Any]] = []
        for row in rows:
            payload = row_to_dict_fn(cursor, row)
            video_count = int(payload["VideoAngleCount"] or 0)
            audio_count = int(payload["AudioAngleCount"] or 0)
            summaries.append(
                {
                    "multicam_media_id": str(payload["MulticamMediaId"] or ""),
                    "multicam_name": str(payload["MulticamName"] or ""),
                    "multicam_sequence_id": str(payload["MulticamSequenceId"] or "") or None,
                    "angle_count": max(video_count, audio_count),
                    "video_angle_count": video_count,
                    "audio_angle_count": audio_count,
                    "binding_inspectable": bool(payload["MulticamSequenceId"]),
                }
            )
        return summaries
    finally:
        connection.close()


def _validate_created_multicam_binding(
    cursor: sqlite3.Cursor,
    *,
    multicam_media_id: str,
    expected_source_rows: list[Any],
    expected_source_angle_labels: list[str] | None,
    expected_source_item_timing: list[dict[str, int]] | None,
    expected_video_selector_mapping: list[dict[str, Any]],
    inspect_with_cursor_fn,
    normalized_selector_idx_fn,
) -> dict[str, Any]:
    binding_state = inspect_with_cursor_fn(cursor, multicam_media_id=multicam_media_id)
    mismatches = list(binding_state["mismatches"])
    selector_mismatches: list[dict[str, Any]] = []
    labels = [str(value or "").strip() for value in list(expected_source_angle_labels or [])]
    if not labels:
        labels = [str(index + 1) for index in range(len(expected_source_rows))]
    angle_order = list(dict.fromkeys(labels))
    angle_index_by_label = {label: index for index, label in enumerate(angle_order)}
    next_item_index_by_angle = {label: 0 for label in angle_order}
    expected_timing = list(expected_source_item_timing or [])
    if expected_timing and len(expected_timing) != len(expected_source_rows):
        raise ValidationError(
            "Expected multicam source timing count must match expected source rows.",
            details={
                "expected_source_count": len(expected_source_rows),
                "expected_timing_count": len(expected_timing),
            },
        )
    expected_source_mapping: list[dict[str, Any]] = []
    for source_index, (source_row, label) in enumerate(zip(expected_source_rows, labels)):
        item_index = next_item_index_by_angle[label]
        next_item_index_by_angle[label] = item_index + 1
        expected_entry = {
            "source_index": source_index,
            "angle": label,
            "angle_index": angle_index_by_label[label],
            "item_index": item_index,
            "source_media_id": source_row.media_id,
            "clip_name": source_row.name,
            "media_file_path": source_row.source_path,
        }
        if expected_timing:
            expected_entry.update(
                {
                    "start_frame": int(expected_timing[source_index]["start_frame"]),
                    "duration_frames": int(expected_timing[source_index]["duration_frames"]),
                    "source_in_frame": int(expected_timing[source_index]["source_in_frame"]),
                }
            )
        expected_source_mapping.append(expected_entry)
    video_by_position = {
        (int(entry["angle_index"]), int(entry.get("item_index") or 0)): entry
        for entry in binding_state["video_source_mapping"]
        if entry.get("source_media_id")
    }
    audio_by_position = {
        (int(entry["angle_index"]), int(entry.get("item_index") or 0)): entry
        for entry in binding_state["audio_source_mapping"]
        if entry.get("source_media_id")
    }
    selector_entry_by_angle: dict[int, dict[str, Any]] = {}
    for entry in binding_state["video_source_mapping"]:
        angle_index = int(entry["angle_index"])
        if entry.get("source_media_id") and angle_index not in selector_entry_by_angle:
            selector_entry_by_angle[angle_index] = entry
    actual_video_selector_mapping = [
        {
            "angle_index": angle_index,
            "current_selector_idx": entry.get("current_selector_idx"),
            "selector_signature": entry.get("selector_signature"),
            "selector_blob_size": entry.get("selector_blob_size", 0),
            "is_placeholder": entry.get("is_placeholder", False),
        }
        for angle_index, entry in sorted(selector_entry_by_angle.items())
    ]
    expected_angle_count = len(angle_order)
    expected_source_count = len(expected_source_rows)
    if len(video_by_position) != expected_source_count:
        mismatches.append(
            {
                "kind": "video_source_count_mismatch",
                "expected_source_count": expected_source_count,
                "actual_source_count": len(video_by_position),
            }
        )
    if len(audio_by_position) != expected_source_count:
        mismatches.append(
            {
                "kind": "audio_source_count_mismatch",
                "expected_source_count": expected_source_count,
                "actual_source_count": len(audio_by_position),
            }
        )

    for expected in expected_source_mapping:
        position = (int(expected["angle_index"]), int(expected["item_index"]))
        video_entry = video_by_position.get(position)
        audio_entry = audio_by_position.get(position)
        if video_entry is None:
            mismatches.append(
                {
                    "kind": "missing_video_source_item",
                    **expected,
                }
            )
        elif video_entry["source_media_id"] != expected["source_media_id"]:
            mismatches.append(
                {
                    "kind": "unexpected_video_source",
                    "angle_index": expected["angle_index"],
                    "item_index": expected["item_index"],
                    "expected_source_media_id": expected["source_media_id"],
                    "actual_source_media_id": video_entry["source_media_id"],
                    "expected_clip_name": expected["clip_name"],
                    "actual_clip_name": video_entry["clip_name"],
                }
            )
        elif expected_timing and any(
            int(video_entry[field]) != int(expected[field])
            for field in ("start_frame", "duration_frames", "source_in_frame")
        ):
            mismatches.append(
                {
                    "kind": "unexpected_video_source_timing",
                    "angle_index": expected["angle_index"],
                    "item_index": expected["item_index"],
                    "expected_timing": {
                        field: int(expected[field])
                        for field in ("start_frame", "duration_frames", "source_in_frame")
                    },
                    "actual_timing": {
                        field: int(video_entry[field])
                        for field in ("start_frame", "duration_frames", "source_in_frame")
                    },
                }
            )
        if audio_entry is None:
            mismatches.append(
                {
                    "kind": "missing_audio_source_item",
                    **expected,
                }
            )
        elif audio_entry["source_media_id"] != expected["source_media_id"]:
            mismatches.append(
                {
                    "kind": "unexpected_audio_source",
                    "angle_index": expected["angle_index"],
                    "item_index": expected["item_index"],
                    "expected_source_media_id": expected["source_media_id"],
                    "actual_source_media_id": audio_entry["source_media_id"],
                    "expected_clip_name": expected["clip_name"],
                    "actual_clip_name": audio_entry["clip_name"],
                }
            )
        elif expected_timing and any(
            int(audio_entry[field]) != int(expected[field])
            for field in ("start_frame", "duration_frames", "source_in_frame")
        ):
            mismatches.append(
                {
                    "kind": "unexpected_audio_source_timing",
                    "angle_index": expected["angle_index"],
                    "item_index": expected["item_index"],
                    "expected_timing": {
                        field: int(expected[field])
                        for field in ("start_frame", "duration_frames", "source_in_frame")
                    },
                    "actual_timing": {
                        field: int(audio_entry[field])
                        for field in ("start_frame", "duration_frames", "source_in_frame")
                    },
                }
            )

    expected_selector_by_angle = {int(entry["angle_index"]): entry for entry in expected_video_selector_mapping}
    actual_selector_by_angle = {int(entry["angle_index"]): entry for entry in actual_video_selector_mapping}
    for index in range(expected_angle_count):
        expected_selector_entry = expected_selector_by_angle.get(index)
        actual_selector_entry = actual_selector_by_angle.get(index)
        if expected_selector_entry is None or actual_selector_entry is None:
            selector_mismatches.append(
                {
                    "kind": "missing_video_selector_state",
                    "angle_index": index,
                    "expected": expected_selector_entry,
                    "actual": actual_selector_entry,
                }
            )
            continue
        if (
            normalized_selector_idx_fn(actual_selector_entry.get("current_selector_idx"))
            != normalized_selector_idx_fn(expected_selector_entry.get("current_selector_idx"))
            or actual_selector_entry.get("selector_signature") != expected_selector_entry.get("selector_signature")
        ):
            selector_mismatches.append(
                {
                    "kind": "unexpected_video_selector_state",
                    "angle_index": index,
                    "expected": expected_selector_entry,
                    "actual": actual_selector_entry,
                }
            )

    actual_selector_states = {
        (normalized_selector_idx_fn(entry.get("current_selector_idx")), entry.get("selector_signature"))
        for entry in actual_video_selector_mapping
    }
    if len(actual_video_selector_mapping) != expected_angle_count:
        selector_mismatches.append(
            {
                "kind": "degenerate_video_selector_shape",
                "actual_video_selector_mapping": actual_video_selector_mapping,
            }
        )
    elif expected_angle_count in (3, 4) and (
        not any(entry.get("current_selector_idx") not in (None, 0) for entry in actual_video_selector_mapping)
        or len(actual_selector_states) < 2
    ):
        selector_mismatches.append(
            {
                "kind": "degenerate_video_selector_shape",
                "actual_video_selector_mapping": actual_video_selector_mapping,
            }
        )
    elif expected_angle_count >= 5:
        distinct_signatures = {
            entry.get("selector_signature")
            for entry in actual_video_selector_mapping
            if entry.get("selector_signature")
        }
        if len(distinct_signatures) != expected_angle_count:
            selector_mismatches.append(
                {
                    "kind": "degenerate_video_selector_shape",
                    "actual_video_selector_mapping": actual_video_selector_mapping,
                }
            )

    all_mismatches = [*mismatches, *selector_mismatches]
    return {
        **binding_state,
        "status": "verified" if not all_mismatches else "failed",
        "mismatches": all_mismatches,
        "expected_source_mapping": expected_source_mapping,
        "expected_video_selector_mapping": expected_video_selector_mapping,
        "actual_video_selector_mapping": actual_video_selector_mapping,
        "selector_mismatches": selector_mismatches,
        "switchable": not selector_mismatches,
    }
