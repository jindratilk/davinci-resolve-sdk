"""Resolve timeline or internal multicam frames to their underlying source media."""

from __future__ import annotations

import re
import sqlite3
import struct
from typing import Any

from ...errors import ValidationError
from .strip_audio import resolve_multicam_strip_target


def _decode_angle_number(fields_blob: bytes | None, current_selector_idx: Any) -> int | None:
    payload = bytes(fields_blob or b"")
    match = re.search(rb"(?:Camera|Angle)\s+([1-9][0-9]*)", payload, flags=re.IGNORECASE)
    if match:
        return int(match.group(1))
    if len(payload) >= 16 and payload[14] in {0x83, 0x86}:
        encoded = (payload[15] >> 4) & 0x0F
        if encoded:
            return encoded
    selector = int(current_selector_idx or 0)
    return selector + 1 if selector > 0 else None


def _sequence_start_frame(cursor: sqlite3.Cursor, sequence_id: str) -> int:
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
    start_seconds, _duration_seconds = struct.unpack("<dd", row[1][:16])
    return int(round(float(start_seconds) * (fps or 24.0)))


def _resolve_internal(
    cursor: sqlite3.Cursor,
    *,
    target: dict[str, Any],
    angle_number: int,
    record_frame: int,
    media_type: str,
) -> dict[str, Any]:
    track_type = 1 if media_type == "audio" else 0
    property_name = "AudioTrackVec" if track_type == 1 else "VideoTrackVec"
    sequence_id = str(target["multicam_sequence_id"])
    sequence_start = _sequence_start_frame(cursor, sequence_id)
    absolute_frame = sequence_start + int(record_frame)
    rows = cursor.execute(
        """
        SELECT track.Sm2TiTrack_id, track.UserDefinedName, rel_item.DbIndex,
               item.Sm2TiItem_id, item.Start, item.Duration, item."In", item.MediaRef,
               item.MediaFilePath, source.Name, source.UniqueMediaPoolItemId
        FROM Sm2SequenceContainer container
        JOIN Sm2SequenceContainer_Sm2TiTrack rel_track
          ON rel_track.DbOwner = container.Sm2SequenceContainer_id
         AND rel_track.DbPropertyName = ?
         AND rel_track.DbIndex = ?
        JOIN Sm2TiTrack track ON track.Sm2TiTrack_id = rel_track.DbAssociate
        JOIN Sm2TiItem_Sm2TiTrack rel_item
          ON rel_item.DbOwner = track.Sm2TiTrack_id
         AND rel_item.DbPropertyName = 'Items'
        JOIN Sm2TiItem item ON item.Sm2TiItem_id = rel_item.DbAssociate
        LEFT JOIN Sm2MpMedia source ON source.Sm2MpMedia_id = item.MediaRef
        WHERE container.Sm2Sequence_id = ?
          AND track.Type = ?
          AND CAST(item.Start AS INTEGER) <= ?
          AND CAST(item.Start AS INTEGER) + CAST(item.Duration AS INTEGER) > ?
        ORDER BY rel_item.DbIndex
        """,
        (property_name, int(angle_number) - 1, sequence_id, track_type, absolute_frame, absolute_frame),
    ).fetchall()
    if not rows:
        return {
            **target,
            "angle_number": int(angle_number),
            "media_type": media_type,
            "record_frame": int(record_frame),
            "absolute_multicam_frame": absolute_frame,
            "status": "intentional_gap",
            "source": None,
        }
    if len(rows) > 1:
        raise ValidationError(
            "Multiple multicam source items overlap at the requested frame.",
            details={"reason": "overlapping_source_items", "angle_number": angle_number, "record_frame": record_frame},
        )
    row = rows[0]
    item_start = int(row[4] or 0)
    source_in = int(row[6] or 0)
    return {
        **target,
        "angle_number": int(angle_number),
        "angle_index": int(angle_number) - 1,
        "angle_name": str(row[1] or "") or None,
        "media_type": media_type,
        "record_frame": int(record_frame),
        "absolute_multicam_frame": absolute_frame,
        "status": "matched",
        "source": {
            "item_index": int(row[2] or 0),
            "item_id": str(row[3]),
            "item_start_frame": item_start,
            "duration_frames": int(row[5] or 0),
            "source_in_frame": source_in,
            "source_frame": source_in + absolute_frame - item_start,
            "media_id": str(row[7] or "") or None,
            "source_path": str(row[8] or "") or None,
            "clip_name": str(row[9] or "") or None,
            "media_pool_unique_id": str(row[10] or "") or None,
        },
    }


def match_multicam_frame(
    project_db_path: str,
    *,
    multicam_name: str | None = None,
    media_id: str | None = None,
    sequence_id: str | None = None,
    angle_number: int,
    record_frame: int,
    media_type: str = "video",
) -> dict[str, Any]:
    normalized_media_type = str(media_type or "video").strip().lower()
    if normalized_media_type not in {"video", "audio"}:
        raise ValidationError("Multicam match frame media_type must be video or audio.")
    if int(angle_number) < 1 or int(record_frame) < 0:
        raise ValidationError("Multicam match frame requires a one-based angle and non-negative record frame.")
    with sqlite3.connect(project_db_path) as connection:
        cursor = connection.cursor()
        target = resolve_multicam_strip_target(
            cursor,
            multicam_name=multicam_name,
            media_id=media_id,
            sequence_id=sequence_id,
        )
        return _resolve_internal(
            cursor,
            target=target,
            angle_number=int(angle_number),
            record_frame=int(record_frame),
            media_type=normalized_media_type,
        )


def match_timeline_multicam_frame(
    project_db_path: str,
    *,
    timeline_name: str,
    timeline_frame: int,
    media_type: str = "video",
    angle_number: int | None = None,
) -> dict[str, Any]:
    normalized_media_type = str(media_type or "video").strip().lower()
    if normalized_media_type not in {"video", "audio"}:
        raise ValidationError("Timeline multicam match frame media_type must be video or audio.")
    track_type = 1 if normalized_media_type == "audio" else 0
    with sqlite3.connect(project_db_path) as connection:
        cursor = connection.cursor()
        sequence_columns = {str(row[1]) for row in cursor.execute("PRAGMA table_info(Sm2Sequence)").fetchall()}
        timeline_sequence_join = (
            "sequence.Sm2Timeline_id = timeline.Sm2Timeline_id"
            if "Sm2Timeline_id" in sequence_columns
            else "sequence.Sm2Sequence_id = timeline.Sequence"
        )
        rows = cursor.execute(
            f"""
            SELECT item.Sm2TiItem_id, item.Start, item.Duration, item."In", item.MediaRef,
                   item.CurrentSelectorIdx, item.FieldsBlob, media.Name, media.Sequence
            FROM Sm2Timeline timeline
            JOIN Sm2Sequence sequence ON {timeline_sequence_join}
            JOIN Sm2SequenceContainer container ON container.Sm2Sequence_id = sequence.Sm2Sequence_id
            JOIN Sm2SequenceContainer_Sm2TiTrack rel_track ON rel_track.DbOwner = container.Sm2SequenceContainer_id
            JOIN Sm2TiTrack track ON track.Sm2TiTrack_id = rel_track.DbAssociate
            JOIN Sm2TiItem_Sm2TiTrack rel_item ON rel_item.DbOwner = track.Sm2TiTrack_id
            JOIN Sm2TiItem item ON item.Sm2TiItem_id = rel_item.DbAssociate
            JOIN Sm2MpMedia media ON media.Sm2MpMedia_id = item.MediaRef AND media.DbType = 'Sm2MpMulticamClip'
            WHERE timeline.Name = ? AND track.Type = ?
              AND CAST(item.Start AS INTEGER) <= ?
              AND CAST(item.Start AS INTEGER) + CAST(item.Duration AS INTEGER) > ?
            ORDER BY rel_track.DbIndex DESC
            """,
            (timeline_name, track_type, int(timeline_frame), int(timeline_frame)),
        ).fetchall()
        if not rows:
            raise ValidationError(
                "No native multicam timeline item covers the requested frame.",
                details={"reason": "timeline_multicam_item_not_found", "timeline_name": timeline_name, "timeline_frame": timeline_frame},
            )
        if len(rows) > 1:
            raise ValidationError(
                "Multiple native multicam items cover the requested timeline frame.",
                details={"reason": "timeline_multicam_match_ambiguous", "item_ids": [str(row[0]) for row in rows]},
            )
        row = rows[0]
        selected_angle = int(angle_number) if angle_number is not None else _decode_angle_number(row[6], row[5])
        if selected_angle is None:
            raise ValidationError(
                "The selected multicam angle could not be decoded; provide angle_number explicitly.",
                details={"reason": "multicam_selected_angle_unknown", "timeline_item_id": str(row[0])},
            )
        item_offset = int(row[3] or 0) + int(timeline_frame) - int(row[1] or 0)
        target = resolve_multicam_strip_target(cursor, media_id=str(row[4]), multicam_name=None, sequence_id=None)
        result = _resolve_internal(
            cursor,
            target=target,
            angle_number=selected_angle,
            record_frame=item_offset,
            media_type=normalized_media_type,
        )
        result["timeline"] = {
            "timeline_name": timeline_name,
            "timeline_frame": int(timeline_frame),
            "timeline_item_id": str(row[0]),
            "timeline_item_start_frame": int(row[1] or 0),
            "timeline_item_duration_frames": int(row[2] or 0),
            "timeline_item_source_in_frame": int(row[3] or 0),
            "selected_angle_source": "explicit" if angle_number is not None else "selector_blob",
        }
        return result
