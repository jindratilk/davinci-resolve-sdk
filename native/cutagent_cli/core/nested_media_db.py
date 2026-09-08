"""Read-only exact-identity inspection for nested timeline media in Project.db."""

from __future__ import annotations

import hashlib
import math
from pathlib import Path
import sqlite3
import struct
from typing import Any

from ..errors import ValidationError


NESTED_MEDIA_TYPES = {
    "Sm2MpCompoundClip": "compound",
    "Sm2MpMulticamClip": "multicam",
    "Sm2MpTimelineClip": "timeline",
}


def _integer(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _blob_summary(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, bytes) or not value:
        return None
    return {"bytes": len(value), "sha256": hashlib.sha256(value).hexdigest()}


def _sequence_timing(frame_rate: Any, media_extents: Any) -> dict[str, Any]:
    fps = None
    if isinstance(frame_rate, bytes) and len(frame_rate) >= 8:
        try:
            fps = float(struct.unpack("<d", frame_rate[:8])[0])
            if not math.isfinite(fps) or fps <= 0:
                fps = None
        except (struct.error, TypeError, ValueError):
            fps = None
    start_frame = duration_frames = None
    if fps and isinstance(media_extents, bytes) and len(media_extents) >= 16:
        try:
            start_seconds, duration_seconds = struct.unpack("<dd", media_extents[:16])
            start_frame = int(round(start_seconds * fps))
            duration_frames = int(round(duration_seconds * fps))
        except (struct.error, TypeError, ValueError):
            start_frame = duration_frames = None
    return {
        "fps": fps,
        "start_frame": start_frame,
        "duration_frames": duration_frames,
        "end_frame_exclusive": (
            start_frame + duration_frames
            if start_frame is not None and duration_frames is not None
            else None
        ),
    }


def _row(cursor: sqlite3.Cursor, query: str, params: tuple[Any, ...]) -> dict[str, Any] | None:
    value = cursor.execute(query, params).fetchone()
    if value is None:
        return None
    return {str(column[0]): item for column, item in zip(cursor.description or (), value)}


def _rows(cursor: sqlite3.Cursor, query: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
    values = cursor.execute(query, params).fetchall()
    columns = [str(column[0]) for column in cursor.description or ()]
    return [dict(zip(columns, value)) for value in values]


def _table_exists(cursor: sqlite3.Cursor, name: str) -> bool:
    return cursor.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (name,),
    ).fetchone() is not None


def _inspect_wrapper(cursor: sqlite3.Cursor, wrapper_item_id: str, media_id: str) -> dict[str, Any]:
    wrapper = _row(
        cursor,
        '''
        SELECT Sm2TiItem_id, DbType, Name, Start, Duration, "In" AS SourceIn,
               MediaRef, Sm2TiTrack_id, CurrentSelectorIdx, FieldsBlob
        FROM Sm2TiItem WHERE Sm2TiItem_id = ? LIMIT 1
        ''',
        (wrapper_item_id,),
    )
    if wrapper is None or str(wrapper.get("MediaRef") or "") != media_id:
        raise ValidationError(
            "Nested media wrapper does not reference the requested media id.",
            details={"reason": "wrapper_media_mismatch", "wrapper_item_id": wrapper_item_id, "media_id": media_id},
        )
    linked_item_ids: list[str] = []
    if _table_exists(cursor, "Sm2TiItem_Sm2TiItem"):
        links = cursor.execute(
            """
            SELECT DbOwner, DbAssociate FROM Sm2TiItem_Sm2TiItem
            WHERE DbOwner = ? OR DbAssociate = ? ORDER BY DbPropertyName, DbIndex
            """,
            (wrapper_item_id, wrapper_item_id),
        ).fetchall()
        linked_item_ids = sorted({
            str(associate if str(owner) == wrapper_item_id else owner)
            for owner, associate in links
            if owner and associate and str(owner) != str(associate)
        })
    start = _integer(wrapper.get("Start"))
    duration = _integer(wrapper.get("Duration"))
    source_in = _integer(wrapper.get("SourceIn"))
    selector = _integer(wrapper.get("CurrentSelectorIdx"))
    unsupported: list[dict[str, str]] = []
    for field_name, raw_value, decoded, required in (
        ("start_frame", wrapper.get("Start"), start, True),
        ("duration_frames", wrapper.get("Duration"), duration, True),
        ("source_in_frame", wrapper.get("SourceIn"), source_in, False),
        ("current_selector_idx", wrapper.get("CurrentSelectorIdx"), selector, False),
    ):
        if decoded is None and (required or raw_value not in (None, "")):
            unsupported.append({
                "path": field_name,
                "reason": "required_value_missing" if raw_value in (None, "") else "integer_not_strictly_decodable",
            })
    return {
        "item_id": wrapper_item_id,
        "db_type": str(wrapper.get("DbType") or ""),
        "name": str(wrapper.get("Name") or "") or None,
        "track_id": str(wrapper.get("Sm2TiTrack_id") or "") or None,
        "start_frame": start,
        "duration_frames": duration,
        "end_frame_exclusive": start + duration if start is not None and duration is not None else None,
        "source_in_frame": source_in,
        "current_selector_idx": selector,
        "selector_blob": _blob_summary(wrapper.get("FieldsBlob")),
        "linked_item_ids": linked_item_ids,
        "unsupported": unsupported,
    }


def _inspect_graph(
    cursor: sqlite3.Cursor,
    *,
    media_id: str,
    depth: int,
    max_depth: int,
    ancestors: tuple[str, ...],
) -> dict[str, Any]:
    media = _row(
        cursor,
        "SELECT Sm2MpMedia_id, DbType, Name, Sequence FROM Sm2MpMedia WHERE Sm2MpMedia_id = ? LIMIT 1",
        (media_id,),
    )
    if media is None:
        raise ValidationError(
            "Nested media id was not found in Project.db.",
            details={"reason": "nested_media_not_found", "media_id": media_id},
        )
    db_type = str(media.get("DbType") or "")
    if db_type not in NESTED_MEDIA_TYPES:
        raise ValidationError(
            "Media id is not a timeline, compound clip, or multicam clip.",
            details={"reason": "media_is_not_nested", "media_id": media_id, "db_type": db_type},
        )
    sequence_id = str(media.get("Sequence") or "")
    if not sequence_id:
        raise ValidationError(
            "Nested media has no exact sequence binding.",
            details={"reason": "nested_sequence_unbound", "media_id": media_id, "db_type": db_type},
        )
    sequence = _row(
        cursor,
        "SELECT Sm2Sequence_id, FrameRate, MediaExtents FROM Sm2Sequence WHERE Sm2Sequence_id = ? LIMIT 1",
        (sequence_id,),
    )
    if sequence is None:
        raise ValidationError(
            "Nested media sequence was not found in Project.db.",
            details={"reason": "nested_sequence_not_found", "media_id": media_id, "sequence_id": sequence_id},
        )

    container = _row(
        cursor,
        "SELECT Sm2SequenceContainer_id FROM Sm2SequenceContainer WHERE Sm2Sequence_id = ? LIMIT 1",
        (sequence_id,),
    )
    if container is None:
        raise ValidationError(
            "Nested media sequence has no inspectable track container.",
            details={"reason": "nested_track_container_not_found", "media_id": media_id, "sequence_id": sequence_id},
        )
    container_id = str(container["Sm2SequenceContainer_id"])
    track_rows = _rows(
        cursor,
        """
        SELECT rel.DbIndex AS TrackIndex, rel.DbPropertyName AS TrackRelation,
               track.Sm2TiTrack_id AS TrackId, track.Type AS TrackType,
               track.SubType AS TrackSubType, track.UserDefinedName AS TrackName,
               track.Flags AS TrackFlags
        FROM Sm2SequenceContainer_Sm2TiTrack rel
        JOIN Sm2TiTrack track ON track.Sm2TiTrack_id = rel.DbAssociate
        WHERE rel.DbOwner = ?
        ORDER BY track.Type, rel.DbIndex, track.Sm2TiTrack_id
        """,
        (container_id,),
    )
    track_ids = [str(track["TrackId"]) for track in track_rows]
    item_rows_by_track: dict[str, list[dict[str, Any]]] = {track_id: [] for track_id in track_ids}
    if track_ids:
        placeholders = ",".join("?" for _ in track_ids)
        for item in _rows(
            cursor,
            f"""
            SELECT rel.DbOwner AS TrackId, rel.DbIndex AS ItemIndex,
                   rel.DbPropertyName AS ItemRelation, item.Sm2TiItem_id AS ItemId,
                   item.DbType AS ItemType, item.Name AS ItemName, item.Start AS ItemStart,
                   item.Duration AS ItemDuration, item."In" AS SourceIn,
                   item.MediaRef AS SourceMediaId, item.MediaFilePath AS MediaFilePath,
                   item.CurrentSelectorIdx AS CurrentSelectorIdx, item.FieldsBlob AS FieldsBlob,
                   source.Name AS SourceName, source.DbType AS SourceType, source.Sequence AS SourceSequence
            FROM Sm2TiItem_Sm2TiTrack rel
            JOIN Sm2TiItem item ON item.Sm2TiItem_id = rel.DbAssociate
            LEFT JOIN Sm2MpMedia source ON source.Sm2MpMedia_id = item.MediaRef
            WHERE rel.DbOwner IN ({placeholders})
            ORDER BY rel.DbOwner, rel.DbIndex, item.Sm2TiItem_id
            """,
            tuple(track_ids),
        ):
            item_rows_by_track[str(item["TrackId"])].append(item)

    all_item_ids = [str(item["ItemId"]) for values in item_rows_by_track.values() for item in values]
    linked_by_item: dict[str, set[str]] = {item_id: set() for item_id in all_item_ids}
    link_edges: list[dict[str, Any]] = []
    if all_item_ids and _table_exists(cursor, "Sm2TiItem_Sm2TiItem"):
        placeholders = ",".join("?" for _ in all_item_ids)
        relations = _rows(
            cursor,
            f"""
            SELECT DbOwner, DbAssociate, DbPropertyName, DbIndex
            FROM Sm2TiItem_Sm2TiItem
            WHERE DbOwner IN ({placeholders}) OR DbAssociate IN ({placeholders})
            ORDER BY DbOwner, DbPropertyName, DbIndex, DbAssociate
            """,
            tuple(all_item_ids + all_item_ids),
        )
        seen_edges: set[tuple[str, str, str, int | None]] = set()
        for relation in relations:
            owner = str(relation.get("DbOwner") or "")
            associate = str(relation.get("DbAssociate") or "")
            if not owner or not associate:
                continue
            relation_name = str(relation.get("DbPropertyName") or "")
            edge = (owner, associate, relation_name, _integer(relation.get("DbIndex")))
            if edge not in seen_edges:
                seen_edges.add(edge)
                link_edges.append({
                    "owner_item_id": owner,
                    "associate_item_id": associate,
                    "relation": relation_name or None,
                    "index": edge[3],
                })
            if owner in linked_by_item:
                linked_by_item[owner].add(associate)
            if associate in linked_by_item:
                linked_by_item[associate].add(owner)

    sequence_timing = _sequence_timing(sequence.get("FrameRate"), sequence.get("MediaExtents"))
    unsupported: list[dict[str, str]] = [
        {"path": "tracks[].items[].effects", "reason": "effect_payloads_not_decoded"},
        {"path": "tracks[].items[].retime", "reason": "retime_payload_not_decoded"},
    ]
    if sequence_timing["fps"] is None:
        unsupported.append({
            "path": "sequence.fps",
            "reason": "required_value_missing" if sequence.get("FrameRate") is None else "frame_rate_not_strictly_decodable",
        })
    if sequence_timing["start_frame"] is None or sequence_timing["duration_frames"] is None:
        extent_reason = "required_value_missing" if sequence.get("MediaExtents") is None else "media_extents_not_strictly_decodable"
        unsupported.append({"path": "sequence.start_frame", "reason": extent_reason})
        unsupported.append({"path": "sequence.duration_frames", "reason": extent_reason})
    if db_type == "Sm2MpMulticamClip":
        unsupported.append({"path": "tracks[].items[].selector_blob", "reason": "selector_angle_semantics_not_decoded"})

    nested: dict[str, Any] = {}
    tracks: list[dict[str, Any]] = []
    for track in track_rows:
        track_id = str(track["TrackId"])
        items: list[dict[str, Any]] = []
        for raw in item_rows_by_track.get(track_id, []):
            item_id = str(raw["ItemId"])
            item_index = _integer(raw.get("ItemIndex"))
            start = _integer(raw.get("ItemStart"))
            duration = _integer(raw.get("ItemDuration"))
            source_in = _integer(raw.get("SourceIn"))
            selector = _integer(raw.get("CurrentSelectorIdx"))
            for field_name, raw_value, decoded, required in (
                ("index", raw.get("ItemIndex"), item_index, True),
                ("start_frame", raw.get("ItemStart"), start, True),
                ("duration_frames", raw.get("ItemDuration"), duration, True),
                ("source_in_frame", raw.get("SourceIn"), source_in, False),
                ("current_selector_idx", raw.get("CurrentSelectorIdx"), selector, False),
            ):
                if decoded is None and (required or raw_value not in (None, "")):
                    unsupported.append({
                        "path": f"tracks[{track_id}].items[{item_id}].{field_name}",
                        "reason": "required_value_missing" if raw_value in (None, "") else "integer_not_strictly_decodable",
                    })
            source_id = str(raw.get("SourceMediaId") or "") or None
            source_type = str(raw.get("SourceType") or "") or None
            items.append({
                "item_id": item_id,
                "index": item_index,
                "relation": str(raw.get("ItemRelation") or "") or None,
                "db_type": str(raw.get("ItemType") or ""),
                "name": str(raw.get("ItemName") or "") or None,
                "start_frame": start,
                "duration_frames": duration,
                "end_frame_exclusive": start + duration if start is not None and duration is not None else None,
                "source_in_frame": source_in,
                "source_media_id": source_id,
                "source_name": str(raw.get("SourceName") or "") or None,
                "source_db_type": source_type,
                "source_sequence_id": str(raw.get("SourceSequence") or "") or None,
                "media_file_path": str(raw.get("MediaFilePath") or "") or None,
                "current_selector_idx": selector,
                "selector_blob": _blob_summary(raw.get("FieldsBlob")),
                "linked_item_ids": sorted(linked_by_item.get(item_id, set())),
            })
            if source_id and source_type in NESTED_MEDIA_TYPES and source_id not in nested:
                if source_id in ancestors or source_id == media_id:
                    nested[source_id] = {"status": "unsupported", "reason": "nested_media_cycle"}
                elif depth >= max_depth:
                    nested[source_id] = {"status": "unsupported", "reason": "max_depth_reached"}
                else:
                    nested[source_id] = _inspect_graph(
                        cursor,
                        media_id=source_id,
                        depth=depth + 1,
                        max_depth=max_depth,
                        ancestors=(*ancestors, media_id),
                    )
        track_index = _integer(track.get("TrackIndex"))
        track_type = _integer(track.get("TrackType"))
        track_subtype = _integer(track.get("TrackSubType"))
        track_flags = _integer(track.get("TrackFlags"))
        for field_name, raw_value, decoded in (
            ("index", track.get("TrackIndex"), track_index),
            ("type_code", track.get("TrackType"), track_type),
            ("subtype", track.get("TrackSubType"), track_subtype),
            ("enabled", track.get("TrackFlags"), track_flags),
        ):
            if decoded is None:
                unsupported.append({
                    "path": f"tracks[{track_id}].{field_name}",
                    "reason": "required_value_missing" if raw_value in (None, "") else "integer_not_strictly_decodable",
                })
        tracks.append({
            "track_id": track_id,
            "index": track_index,
            "angle_index": (
                track_index
                if db_type == "Sm2MpMulticamClip"
                else None
            ),
            "relation": str(track.get("TrackRelation") or "") or None,
            "type": "video" if track_type == 0 else "audio" if track_type == 1 else "subtitle" if track_type == 2 else "unknown",
            "type_code": track_type,
            "subtype": track_subtype,
            "name": str(track.get("TrackName") or "") or None,
            "enabled": None if track_flags is None else not bool(track_flags & 2),
            "items": items,
        })

    return {
        "status": "inspected",
        "media": {
            "media_id": media_id,
            "name": str(media.get("Name") or "") or None,
            "db_type": db_type,
            "kind": NESTED_MEDIA_TYPES[db_type],
            "sequence_id": sequence_id,
        },
        "sequence": {"sequence_id": sequence_id, **sequence_timing},
        "tracks": tracks,
        "item_links": link_edges,
        "nested_media": nested,
        "unsupported": unsupported,
    }


def inspect_nested_media_graph(
    project_db_path: str | Path,
    *,
    media_id: str,
    wrapper_item_id: str | None = None,
    max_depth: int = 8,
) -> dict[str, Any]:
    """Inspect a nested timeline/compound/multicam graph without opening the DB writable."""
    normalized_media_id = str(media_id or "").strip()
    if not normalized_media_id:
        raise ValidationError("Nested media inspection requires an exact media id.", details={"reason": "missing_media_id"})
    if not isinstance(max_depth, int) or not 0 <= max_depth <= 16:
        raise ValidationError("Nested media max_depth must be between 0 and 16.", details={"reason": "invalid_max_depth"})
    db_path = Path(project_db_path).expanduser().resolve()
    connection = sqlite3.connect(f"{db_path.as_uri()}?mode=ro", uri=True)
    try:
        cursor = connection.cursor()
        result = _inspect_graph(cursor, media_id=normalized_media_id, depth=0, max_depth=max_depth, ancestors=())
        result["wrapper"] = (
            _inspect_wrapper(cursor, str(wrapper_item_id), normalized_media_id)
            if wrapper_item_id
            else None
        )
        return result
    finally:
        connection.close()
