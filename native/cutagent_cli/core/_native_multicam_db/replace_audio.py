"""Native multicam internal audio replacement helpers."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import sqlite3
from typing import Any
import uuid

from ...errors import APICallFailed, ValidationError
from .. import db_session, media_pool
from .blob_codec import _decode_rate_blob, _encode_media_timemap_ba
from .source_rows import resolve_source_media_rows as _source_rows_resolve_source_media_rows
from .strip_audio import resolve_multicam_strip_target

_MULTICAM_INTERNAL_TRACKS = "multicam_internal_tracks"
_SUPPORTED_UNMAPPED_AUDIO_POLICIES = {"keep", "remove", "error"}


@dataclass(frozen=True)
class ResolvedAudioMediaRow:
    media_id: str
    name: str
    folder_id: str | None
    folder_path: str
    db_type: str
    source_path: str | None = None
    duration_frames: int | None = None
    fps: float | None = None
    cur_playhead_position: str | None = None
    slate_tc: str | None = None
    media_start_time: float | None = None


def _row_to_dict(cursor: sqlite3.Cursor, row: tuple[Any, ...] | sqlite3.Row) -> dict[str, Any]:
    return {cursor.description[index][0]: value for index, value in enumerate(row)}


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_audio_sources(raw: Any, *, allow_empty: bool = False) -> list[dict[str, Any]]:
    if raw is None:
        raw = []
    if not isinstance(raw, list) or (not raw and not allow_empty):
        raise ValidationError(
            "Native multicam audio replacement requires audio_sources[].",
            details={"audio_sources": raw},
        )
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise ValidationError("Audio source entries must be objects.", details={"index": index, "entry": entry})
        source_id = _normalize_text(entry.get("id") or entry.get("source_id"))
        path = _normalize_text(entry.get("path") or entry.get("source_path") or entry.get("file"))
        if not source_id or not path:
            raise ValidationError(
                "Each audio source must include id and path.",
                details={"index": index, "entry": entry},
            )
        if source_id in seen:
            raise ValidationError("Audio source ids must be unique.", details={"audio_source_id": source_id})
        seen.add(source_id)
        expanded_path = str(Path(path).expanduser())
        clip_name = _normalize_text(entry.get("clip_name") or entry.get("name")) or os.path.basename(expanded_path)
        normalized_entry: dict[str, Any] = {
            "id": source_id,
            "path": expanded_path,
            "clip_name": clip_name,
            "source_path": _normalize_text(entry.get("source_path")) or expanded_path,
        }
        if entry.get("duration_frames") not in (None, ""):
            normalized_entry["duration_frames"] = int(entry["duration_frames"])
        if entry.get("fps") not in (None, ""):
            normalized_entry["fps"] = float(entry["fps"])
        normalized.append(normalized_entry)
    return normalized


def _normalize_audio_angle_map(raw: Any) -> dict[str, str]:
    if not isinstance(raw, dict) or not raw:
        raise ValidationError(
            "Native multicam audio replacement requires audio_angle_map.",
            details={"audio_angle_map": raw},
        )
    parsed = {_normalize_text(key): _normalize_text(value) for key, value in raw.items()}
    missing = [key for key, value in parsed.items() if not key or not value]
    if missing:
        raise ValidationError(
            "audio_angle_map entries must use non-empty source ids and angle targets.",
            details={"audio_angle_map": raw},
        )
    return parsed


def _normalize_offsets(raw: Any) -> dict[str, int]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValidationError("Audio replacement offsets must be an object.", details={"offsets": raw})
    return {str(key): int(value) for key, value in raw.items()}


def _normalize_angle_order(raw: Any) -> list[str]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValidationError("angle_order must be an array of angle labels.", details={"angle_order": raw})
    return [_normalize_text(value) for value in raw if _normalize_text(value)]


def _normalize_angle_indices(raw: Any) -> list[int]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValidationError("empty_angle_indices must be an array of zero-based angle indexes.", details={"empty_angle_indices": raw})
    normalized: list[int] = []
    seen: set[int] = set()
    for value in raw:
        index = int(value)
        if index < 0:
            raise ValidationError("Angle indexes must be zero or greater.", details={"angle_index": index})
        if index in seen:
            raise ValidationError("Angle indexes must be unique.", details={"angle_index": index})
        seen.add(index)
        normalized.append(index)
    return normalized


def _normalize_unmapped_audio(value: Any) -> str:
    normalized = _normalize_text(value or "keep").lower()
    if normalized not in _SUPPORTED_UNMAPPED_AUDIO_POLICIES:
        raise ValidationError(
            "Unsupported unmapped audio replacement policy.",
            details={
                "unmapped_audio": value,
                "supported": sorted(_SUPPORTED_UNMAPPED_AUDIO_POLICIES),
            },
        )
    return normalized


def normalize_multicam_audio_replacement_settings(raw: Any) -> dict[str, Any] | None:
    if raw in (None, False):
        return None
    if not isinstance(raw, dict):
        raise ValidationError("program_audio must be an object.", details={"program_audio": raw})
    mode = _normalize_text(raw.get("mode") or _MULTICAM_INTERNAL_TRACKS)
    if mode != _MULTICAM_INTERNAL_TRACKS:
        raise ValidationError(
            "Unsupported program_audio mode.",
            details={"mode": mode, "supported_modes": [_MULTICAM_INTERNAL_TRACKS]},
        )
    empty_angle_indices = _normalize_angle_indices(raw.get("empty_angle_indices"))
    sources = _normalize_audio_sources(raw.get("sources"), allow_empty=bool(empty_angle_indices))
    return {
        "mode": mode,
        "sources": sources,
        "audio_angle_map": _normalize_audio_angle_map(raw.get("audio_angle_map")) if sources else {},
        "angle_order": _normalize_angle_order(raw.get("angle_order")),
        "offsets": _normalize_offsets(raw.get("offsets")),
        "unmapped_audio": _normalize_unmapped_audio(raw.get("unmapped_audio", "remove")),
        "empty_angle_indices": empty_angle_indices,
    }


def _resolve_target_angle_index(target: str, *, angle_order: list[str]) -> int:
    normalized = _normalize_text(target)
    if normalized.isdigit():
        return int(normalized)
    if angle_order and normalized in angle_order:
        return angle_order.index(normalized)
    raise ValidationError(
        "Audio replacement target must be a zero-based angle index or a value from angle_order.",
        details={
            "target": target,
            "angle_order": angle_order,
        },
    )


def _fetch_sequence_container_id(cursor: sqlite3.Cursor, *, sequence_id: str) -> str:
    row = cursor.execute(
        "SELECT Sm2SequenceContainer_id FROM Sm2SequenceContainer WHERE Sm2Sequence_id = ?",
        (sequence_id,),
    ).fetchone()
    if not row or not row[0]:
        raise ValidationError(
            "Native multicam sequence container could not be found.",
            details={"reason": "multicam_sequence_container_missing", "multicam_sequence_id": sequence_id},
        )
    return str(row[0])


def _fetch_audio_tracks(cursor: sqlite3.Cursor, *, container_id: str) -> list[dict[str, Any]]:
    rows = cursor.execute(
        """
        SELECT
          track.Sm2TiTrack_id AS TrackId,
          rel.DbIndex AS AngleIndex,
          track.UserDefinedName AS TrackName,
          track.SubType AS TrackSubType,
          track.FieldsBlob AS TrackFieldsBlob,
          item.Sm2TiItem_id AS ItemId,
          item.Name AS ItemName,
          item.Start AS ItemStart,
          item.Duration AS ItemDuration,
          item."In" AS InValue,
          item.MediaRef AS MediaRef,
          item.MediaStartTime AS MediaStartTime,
          item.MediaFilePath AS MediaFilePath,
          item.MediaTimemapBA AS MediaTimemapBA,
          item.MediaFrameRate AS MediaFrameRate,
          item.VirtualAudioTrackBA AS VirtualAudioTrackBA,
          item.MediaTrackIdx AS MediaTrackIdx,
          item.CurrentSelectorIdx AS CurrentSelectorIdx,
          item.FieldsBlob AS ItemFieldsBlob
        FROM Sm2TiTrack track
        JOIN Sm2SequenceContainer_Sm2TiTrack rel
          ON rel.DbOwner = ?
         AND rel.DbAssociate = track.Sm2TiTrack_id
         AND rel.DbPropertyName = 'AudioTrackVec'
        LEFT JOIN Sm2TiItem_Sm2TiTrack item_rel
          ON item_rel.DbOwner = track.Sm2TiTrack_id
         AND item_rel.DbPropertyName = 'Items'
        LEFT JOIN Sm2TiItem item
          ON item.Sm2TiItem_id = item_rel.DbAssociate
         AND item.DbType = 'Sm2TiAudioClip'
        WHERE track.Sm2SequenceContainer_id = ?
          AND track.Type = 1
        ORDER BY rel.DbIndex, item_rel.DbIndex, track.Sm2TiTrack_id
        """,
        (container_id, container_id),
    ).fetchall()
    tracks: list[dict[str, Any]] = []
    item_counts: dict[str, int] = {}
    for row in rows:
        payload = _row_to_dict(cursor, row)
        track_id = _normalize_text(payload["TrackId"])
        if track_id and _normalize_text(payload["ItemId"]):
            item_counts[track_id] = item_counts.get(track_id, 0) + 1
    seen: set[str] = set()
    for row in rows:
        payload = _row_to_dict(cursor, row)
        track_id = _normalize_text(payload["TrackId"])
        if not track_id or track_id in seen:
            continue
        seen.add(track_id)
        tracks.append(
            {
                "track_id": track_id,
                "angle_index": int(payload["AngleIndex"] or 0),
                "track_name": _normalize_text(payload["TrackName"]) or None,
                "track_subtype": int(payload["TrackSubType"] or 257),
                "track_fields_blob": payload["TrackFieldsBlob"],
                "item_count": item_counts.get(track_id, 0),
                "item_id": _normalize_text(payload["ItemId"]) or None,
                "item_name": _normalize_text(payload["ItemName"]) or None,
                "item_start": int(payload["ItemStart"] or 0),
                "item_duration": int(payload["ItemDuration"] or 0),
                "in_value": payload["InValue"],
                "media_ref": _normalize_text(payload["MediaRef"]) or None,
                "media_start_time": float(payload["MediaStartTime"] or 0.0),
                "media_file_path": _normalize_text(payload["MediaFilePath"]) or None,
                "media_timemap_ba": payload["MediaTimemapBA"],
                "media_frame_rate": payload["MediaFrameRate"],
                "virtual_audio_track_ba": payload["VirtualAudioTrackBA"],
                "media_track_idx": payload["MediaTrackIdx"],
                "current_selector_idx": payload["CurrentSelectorIdx"],
                "item_fields_blob": payload["ItemFieldsBlob"],
            }
        )
    return tracks


def _fetch_sequence_fps(cursor: sqlite3.Cursor, *, sequence_id: str, media_id: str) -> float:
    row = cursor.execute(
        """
        SELECT seq.FrameRate, media.FrameRate
        FROM Sm2Sequence seq
        LEFT JOIN Sm2MpMedia media ON media.Sm2MpMedia_id = ?
        WHERE seq.Sm2Sequence_id = ?
        """,
        (media_id, sequence_id),
    ).fetchone()
    if row:
        for blob in (row[0], row[1]):
            value = _decode_rate_blob(blob)
            if value and value > 0:
                return float(value)
    return 24.0


def _fetch_sequence_span(cursor: sqlite3.Cursor, *, sequence_id: str) -> dict[str, int]:
    row = cursor.execute(
        """
        SELECT
          MIN(CAST(COALESCE(item.Start, '0') AS INTEGER)) AS StartFrame,
          MAX(CAST(COALESCE(item.Start, '0') AS INTEGER) + CAST(COALESCE(item.Duration, '0') AS INTEGER)) AS EndFrame
        FROM Sm2TiItem item
        JOIN Sm2TiTrack track ON track.Sm2TiTrack_id = item.Sm2TiTrack_id
        WHERE track.Sequence = ?
          AND track.Type = 0
          AND item.DbType = 'Sm2TiVideoClip'
        """,
        (sequence_id,),
    ).fetchone()
    start_frame = int((row[0] if row else 0) or 0)
    end_frame = int((row[1] if row else 0) or 0)
    if end_frame <= start_frame:
        row = cursor.execute(
            """
            SELECT
              MIN(CAST(COALESCE(item.Start, '0') AS INTEGER)) AS StartFrame,
              MAX(CAST(COALESCE(item.Start, '0') AS INTEGER) + CAST(COALESCE(item.Duration, '0') AS INTEGER)) AS EndFrame
            FROM Sm2TiItem item
            JOIN Sm2TiTrack track ON track.Sm2TiTrack_id = item.Sm2TiTrack_id
            WHERE track.Sequence = ?
            """,
            (sequence_id,),
        ).fetchone()
        start_frame = int((row[0] if row else 0) or 0)
        end_frame = int((row[1] if row else 0) or 0)
    if end_frame <= start_frame:
        raise ValidationError(
            "Native multicam sequence duration could not be derived.",
            details={"reason": "multicam_sequence_duration_missing", "multicam_sequence_id": sequence_id},
        )
    return {"start_frame": start_frame, "end_frame": end_frame, "duration_frames": end_frame - start_frame}


def _resolve_audio_source_rows(
    project_db_path: str,
    *,
    sources: list[dict[str, Any]],
) -> dict[str, ResolvedAudioMediaRow]:
    specs = [
        {
            "angle": source["id"],
            "clip_name": source["clip_name"],
            "source_path": source["source_path"],
            "duration_frames": source.get("duration_frames"),
            "fps": source.get("fps"),
        }
        for source in sources
    ]
    rows = _source_rows_resolve_source_media_rows(
        project_db_path,
        resolved_angles=specs,
        resolved_db_media_row_cls=ResolvedAudioMediaRow,
        row_to_dict_fn=_row_to_dict,
        temp_bin_prefix="__CutAgent Native Multicam ",
    )
    return {source["id"]: row for source, row in zip(sources, rows)}


def _build_replacement_plan(
    cursor: sqlite3.Cursor,
    *,
    project_db_path: str,
    multicam_name: str | None,
    media_id: str | None,
    sequence_id: str | None,
    audio_sources: list[dict[str, Any]],
    audio_angle_map: dict[str, str],
    angle_order: list[str],
    offsets: dict[str, int],
    unmapped_audio: str,
    empty_angle_indices: list[int],
) -> dict[str, Any]:
    target = resolve_multicam_strip_target(
        cursor,
        multicam_name=multicam_name,
        media_id=media_id,
        sequence_id=sequence_id,
    )
    resolved_sequence_id = target["multicam_sequence_id"]
    resolved_media_id = target["multicam_media_id"]
    container_id = _fetch_sequence_container_id(cursor, sequence_id=resolved_sequence_id)
    audio_tracks = _fetch_audio_tracks(cursor, container_id=container_id)
    if not audio_tracks:
        raise ValidationError(
            "Native multicam clip has no internal audio tracks to replace.",
            details={
                "reason": "multicam_audio_tracks_missing",
                **target,
                "hint": "Use this command before stripping all internal multicam audio, or recreate the multicam with audio tracks.",
            },
        )
    multi_item_angles = sorted(
        int(track["angle_index"])
        for track in audio_tracks
        if int(track.get("item_count") or 0) > 1
    )
    if multi_item_angles:
        raise ValidationError(
            "Audio replacement requires item-level targeting for multicam angles that contain multiple source clips.",
            details={
                "reason": "multi_item_angle_requires_item_target",
                "angle_indices": multi_item_angles,
                "angle_numbers": [index + 1 for index in multi_item_angles],
                "hint": "Keep the original embedded audio or recreate the multicam clip until item-level audio targeting is available.",
            },
        )
    tracks_by_angle = {int(track["angle_index"]): track for track in audio_tracks}
    empty_angle_set = set(_normalize_angle_indices(empty_angle_indices))
    unknown_empty_angles = sorted(index for index in empty_angle_set if index not in tracks_by_angle)
    if unknown_empty_angles:
        raise ValidationError(
            "Empty audio target references an internal multicam audio angle that does not exist.",
            details={
                "empty_angle_indices": unknown_empty_angles,
                "empty_angle_numbers": [index + 1 for index in unknown_empty_angles],
                "available_audio_angle_indices": sorted(tracks_by_angle),
                "available_audio_angle_numbers": [index + 1 for index in sorted(tracks_by_angle)],
            },
        )
    source_ids = {source["id"] for source in audio_sources}
    map_ids = set(audio_angle_map.keys())
    unknown_map_sources = sorted(map_ids - source_ids)
    unmapped_sources = sorted(source_ids - map_ids)
    if unknown_map_sources or unmapped_sources:
        raise ValidationError(
            "Native multicam audio replacement requires a one-to-one source-to-angle map.",
            details={
                "unknown_audio_angle_map_sources": unknown_map_sources,
                "unmapped_audio_sources": unmapped_sources,
                "audio_source_ids": sorted(source_ids),
            },
        )
    source_rows = _resolve_audio_source_rows(project_db_path, sources=audio_sources)
    sequence_span = _fetch_sequence_span(cursor, sequence_id=resolved_sequence_id)
    fps = _fetch_sequence_fps(cursor, sequence_id=resolved_sequence_id, media_id=resolved_media_id)

    used_indices: dict[int, str] = {}
    replacements: list[dict[str, Any]] = []
    for source in audio_sources:
        source_id = source["id"]
        angle_index = _resolve_target_angle_index(audio_angle_map[source_id], angle_order=angle_order)
        if angle_index in used_indices:
            raise ValidationError(
                "Native multicam audio replacement does not support multiple sources targeting the same angle.",
                details={
                    "angle_index": angle_index,
                    "audio_source_ids": [used_indices[angle_index], source_id],
                },
            )
        if angle_index in empty_angle_set:
            raise ValidationError(
                "Audio angle cannot be both replaced and emptied in the same operation.",
                details={
                    "angle_index": angle_index,
                    "angle_number": angle_index + 1,
                    "audio_source_id": source_id,
                },
            )
        used_indices[angle_index] = source_id
        if angle_index not in tracks_by_angle:
            raise ValidationError(
                "Audio replacement target angle does not have an internal audio track.",
                details={
                    "angle_index": angle_index,
                    "available_audio_angle_indices": sorted(tracks_by_angle),
                    "audio_source_id": source_id,
                },
            )
        source_row = source_rows[source_id]
        offset_frames = int(offsets.get(source_id, 0))
        item_start = sequence_span["start_frame"] + max(0, offset_frames)
        source_start_frames = max(0, -offset_frames)
        timeline_duration = max(0, sequence_span["end_frame"] - item_start)
        if timeline_duration <= 0:
            raise ValidationError(
                "Audio source does not overlap the multicam sequence after sync offset.",
                details={
                    "audio_source_id": source_id,
                    "offset_frames": offset_frames,
                    "sequence_span": sequence_span,
                },
            )
        source_duration = int(source_row.duration_frames or 0)
        if source_duration > 0:
            timeline_duration = min(timeline_duration, max(0, source_duration - source_start_frames))
        if timeline_duration <= 0:
            raise ValidationError(
                "Audio source range is empty after source-duration clipping.",
                details={
                    "audio_source_id": source_id,
                    "offset_frames": offset_frames,
                    "source_duration_frames": source_duration,
                    "source_start_frames": source_start_frames,
                },
            )
        track = tracks_by_angle[angle_index]
        replacements.append(
            {
                "audio_source_id": source_id,
                "angle_index": angle_index,
                "track_id": track["track_id"],
                "existing_item_id": track["item_id"],
                "source_media_id": source_row.media_id,
                "source_clip_name": source_row.name,
                "source_path": source_row.source_path or source["source_path"],
                "offset_frames": offset_frames,
                "item_start_frame": item_start,
                "source_start_frames": source_start_frames,
                "duration_frames": timeline_duration,
                "media_start_time_seconds": float(source_row.media_start_time or 0.0),
            }
        )

    removed_unmapped: list[dict[str, Any]] = []
    for angle_index in sorted(empty_angle_set):
        track = tracks_by_angle[angle_index]
        if track["item_id"]:
            removed_unmapped.append(
                {
                    "angle_index": angle_index,
                    "angle_number": angle_index + 1,
                    "track_id": track["track_id"],
                    "item_id": track["item_id"],
                    "media_ref": track["media_ref"],
                    "media_file_path": track["media_file_path"],
                    "remove_reason": "explicit_empty_angle",
                }
            )

    remaining_unmapped_with_audio: list[dict[str, Any]] = []
    for angle_index, track in sorted(tracks_by_angle.items()):
        if angle_index in used_indices or angle_index in empty_angle_set:
            continue
        if track["item_id"]:
            remaining_unmapped_with_audio.append(
                {
                    "angle_index": angle_index,
                    "angle_number": angle_index + 1,
                    "track_id": track["track_id"],
                    "item_id": track["item_id"],
                    "media_ref": track["media_ref"],
                    "media_file_path": track["media_file_path"],
                }
            )
    if unmapped_audio == "error" and remaining_unmapped_with_audio:
        raise ValidationError(
            "Native multicam audio replacement left existing internal audio on unmapped angles.",
            details={
                "reason": "unmapped_audio_angles_present",
                "unmapped_audio_angles": remaining_unmapped_with_audio,
                "hint": "Map those angles, pass explicit empty angles, or choose unmapped_audio=keep/remove.",
            },
        )
    if unmapped_audio == "remove":
        for item in remaining_unmapped_with_audio:
            removed_unmapped.append({**item, "remove_reason": "unmapped_audio_remove_policy"})

    return {
        "action": "multicam.replace_audio",
        **target,
        "container_id": container_id,
        "angle_order": angle_order,
        "sequence_span": sequence_span,
        "fps": fps,
        "audio_track_count": len(audio_tracks),
        "unmapped_audio": unmapped_audio,
        "empty_angle_indices": sorted(empty_angle_set),
        "empty_angle_numbers": [index + 1 for index in sorted(empty_angle_set)],
        "replacements": replacements,
        "removed_unmapped_audio_items": removed_unmapped,
    }


def _fetch_template_audio_item(cursor: sqlite3.Cursor, *, sequence_id: str) -> dict[str, Any] | None:
    row = cursor.execute(
        """
        SELECT
          item.MediaTimemapBA,
          item.MediaFrameRate,
          item.VirtualAudioTrackBA,
          item.MediaTrackIdx,
          item.CurrentSelectorIdx,
          item.FieldsBlob
        FROM Sm2TiItem item
        JOIN Sm2TiTrack track ON track.Sm2TiTrack_id = item.Sm2TiTrack_id
        WHERE track.Sequence = ?
          AND item.DbType = 'Sm2TiAudioClip'
        ORDER BY item.rowid DESC
        LIMIT 1
        """,
        (sequence_id,),
    ).fetchone()
    if row is None:
        return None
    return _row_to_dict(cursor, row)


def _write_replacement_item(
    cursor: sqlite3.Cursor,
    *,
    replacement: dict[str, Any],
    fps: float,
    template: dict[str, Any] | None,
) -> dict[str, Any]:
    item_id = _normalize_text(replacement.get("existing_item_id"))
    dynamic_timemap = sqlite3.Binary(_encode_media_timemap_ba(int(replacement["duration_frames"]), fps))
    if item_id:
        before = cursor.execute(
            """
            SELECT MediaRef, MediaFilePath, Start, Duration, MediaStartTime
            FROM Sm2TiItem
            WHERE Sm2TiItem_id = ?
            """,
            (item_id,),
        ).fetchone()
        cursor.execute(
            """
            UPDATE Sm2TiItem
            SET
              Name = ?,
              Start = ?,
              Duration = ?,
              "In" = ?,
              MediaRef = ?,
              MediaStartTime = ?,
              MediaFilePath = ?,
              MediaTimemapBA = ?,
              MediaTrackIdx = COALESCE(MediaTrackIdx, 0)
            WHERE Sm2TiItem_id = ?
              AND DbType = 'Sm2TiAudioClip'
            """,
            (
                replacement["source_clip_name"],
                str(replacement["item_start_frame"]),
                str(replacement["duration_frames"]),
                str(replacement["source_start_frames"]) if int(replacement["source_start_frames"]) > 0 else None,
                replacement["source_media_id"],
                float(replacement["media_start_time_seconds"]),
                replacement["source_path"],
                dynamic_timemap,
                item_id,
            ),
        )
        return {
            **replacement,
            "item_id": item_id,
            "operation": "updated",
            "before": {
                "media_ref": before[0] if before else None,
                "media_file_path": before[1] if before else None,
                "start": before[2] if before else None,
                "duration": before[3] if before else None,
                "media_start_time": before[4] if before else None,
            },
        }
    if template is None:
        raise ValidationError(
            "Cannot create missing multicam audio item because no audio item template exists.",
            details={
                "reason": "missing_audio_item_template",
                "track_id": replacement["track_id"],
                "audio_source_id": replacement["audio_source_id"],
            },
        )
    item_id = str(uuid.uuid4())
    cursor.execute(
        """
        INSERT INTO Sm2TiItem (
            Sm2TiItem_id, DbType, Name, Start, Duration, "In", MediaRef, MediaStartTime,
            MediaFilePath, MediaTimemapBA, MediaFrameRate, VirtualAudioTrackBA,
            MediaTrackIdx, Sm2TiTrack_id, UiMemento, Flags, PriorityIndex,
            ThumbnailDirtyFlag, RenderTextEnabled, RenderTextGanged, RenderTextPrefixed,
            IsForceConformed, MatchConflictState, IsPreConformed, MixedFrameRateAlignment,
            UseOppositeSrcForLeftEye, UseOppositeSrcForRightEye, WasDisbanded,
            CurrentSelectorIdx, FieldsBlob
        ) VALUES (
            ?, 'Sm2TiAudioClip', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 0,
            1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, ?, ?
        )
        """,
        (
            item_id,
            replacement["source_clip_name"],
            str(replacement["item_start_frame"]),
            str(replacement["duration_frames"]),
            str(replacement["source_start_frames"]) if int(replacement["source_start_frames"]) > 0 else None,
            replacement["source_media_id"],
            float(replacement["media_start_time_seconds"]),
            replacement["source_path"],
            dynamic_timemap,
            template.get("MediaFrameRate"),
            template.get("VirtualAudioTrackBA"),
            int(template.get("MediaTrackIdx") or 0),
            replacement["track_id"],
            int(template.get("CurrentSelectorIdx") or 0),
            template.get("FieldsBlob"),
        ),
    )
    cursor.execute(
        """
        INSERT INTO Sm2TiItem_Sm2TiTrack (
            DbOwner, DbAssociate, DbPropertyName, DbIndex
        ) VALUES (?, ?, 'Items', 0)
        """,
        (replacement["track_id"], item_id),
    )
    return {**replacement, "item_id": item_id, "operation": "created", "before": None}


def plan_multicam_audio_replacement(
    project_db_path: str,
    *,
    multicam_name: str | None = None,
    media_id: str | None = None,
    sequence_id: str | None = None,
    audio_sources: list[dict[str, Any]],
    audio_angle_map: dict[str, str],
    angle_order: list[str] | None = None,
    offsets: dict[str, int] | None = None,
    unmapped_audio: str = "keep",
    empty_angle_indices: list[int] | None = None,
) -> dict[str, Any]:
    normalized_order = _normalize_angle_order(angle_order)
    normalized_offsets = _normalize_offsets(offsets)
    normalized_unmapped = _normalize_unmapped_audio(unmapped_audio)
    normalized_empty_indices = _normalize_angle_indices(empty_angle_indices)
    normalized_sources = _normalize_audio_sources(audio_sources, allow_empty=bool(normalized_empty_indices))
    normalized_map = _normalize_audio_angle_map(audio_angle_map) if normalized_sources else {}
    connection = sqlite3.connect(project_db_path)
    try:
        cursor = connection.cursor()
        return _build_replacement_plan(
            cursor,
            project_db_path=project_db_path,
            multicam_name=multicam_name,
            media_id=media_id,
            sequence_id=sequence_id,
            audio_sources=normalized_sources,
            audio_angle_map=normalized_map,
            angle_order=normalized_order,
            offsets=normalized_offsets,
            unmapped_audio=normalized_unmapped,
            empty_angle_indices=normalized_empty_indices,
        )
    finally:
        connection.close()


def _write_multicam_audio_replacement(
    cursor: sqlite3.Cursor,
    *,
    project_db_path: str,
    multicam_name: str | None = None,
    media_id: str | None = None,
    sequence_id: str | None = None,
    audio_sources: list[dict[str, Any]],
    audio_angle_map: dict[str, str],
    angle_order: list[str] | None = None,
    offsets: dict[str, int] | None = None,
    unmapped_audio: str = "keep",
    empty_angle_indices: list[int] | None = None,
) -> dict[str, Any]:
    plan = _build_replacement_plan(
        cursor,
        project_db_path=project_db_path,
        multicam_name=multicam_name,
        media_id=media_id,
        sequence_id=sequence_id,
        audio_sources=_normalize_audio_sources(audio_sources, allow_empty=bool(_normalize_angle_indices(empty_angle_indices))),
        audio_angle_map=_normalize_audio_angle_map(audio_angle_map) if audio_sources else {},
        angle_order=_normalize_angle_order(angle_order),
        offsets=_normalize_offsets(offsets),
        unmapped_audio=_normalize_unmapped_audio(unmapped_audio),
        empty_angle_indices=_normalize_angle_indices(empty_angle_indices),
    )
    template = _fetch_template_audio_item(cursor, sequence_id=plan["multicam_sequence_id"])
    updated_items: list[dict[str, Any]] = []
    for replacement in plan["replacements"]:
        updated_items.append(
            _write_replacement_item(
                cursor,
                replacement=replacement,
                fps=float(plan["fps"]),
                template=template,
            )
        )
    for item in plan["removed_unmapped_audio_items"]:
        cursor.execute(
            "DELETE FROM Sm2TiItem_Sm2TiTrack WHERE DbAssociate = ? AND DbPropertyName = 'Items'",
            (item["item_id"],),
        )
        cursor.execute(
            "DELETE FROM Sm2TiItem WHERE Sm2TiItem_id = ? AND DbType = 'Sm2TiAudioClip'",
            (item["item_id"],),
        )
    return {
        **plan,
        "changed": bool(updated_items or plan["removed_unmapped_audio_items"]),
        "updated_audio_items": updated_items,
        "removed_unmapped_audio_item_count": len(plan["removed_unmapped_audio_items"]),
    }


def _build_verification(
    cursor: sqlite3.Cursor,
    *,
    mutation_result: dict[str, Any],
) -> dict[str, Any]:
    rows = cursor.execute(
        """
        SELECT
          rel.DbIndex AS AngleIndex,
          track.Sm2TiTrack_id AS TrackId,
          item.Sm2TiItem_id AS ItemId,
          item.MediaRef AS MediaRef,
          item.MediaFilePath AS MediaFilePath,
          item.Start AS StartFrame,
          item.Duration AS DurationFrames,
          item.MediaStartTime AS MediaStartTime,
          source.Name AS SourceClipName
        FROM Sm2SequenceContainer container
        JOIN Sm2SequenceContainer_Sm2TiTrack rel
          ON rel.DbOwner = container.Sm2SequenceContainer_id
         AND rel.DbPropertyName = 'AudioTrackVec'
        JOIN Sm2TiTrack track ON track.Sm2TiTrack_id = rel.DbAssociate
        LEFT JOIN Sm2TiItem item
          ON item.Sm2TiTrack_id = track.Sm2TiTrack_id
         AND item.DbType = 'Sm2TiAudioClip'
        LEFT JOIN Sm2MpMedia source ON source.Sm2MpMedia_id = item.MediaRef
        WHERE container.Sm2Sequence_id = ?
        ORDER BY rel.DbIndex
        """,
        (mutation_result["multicam_sequence_id"],),
    ).fetchall()
    by_angle: dict[int, dict[str, Any]] = {}
    for row in rows:
        payload = _row_to_dict(cursor, row)
        by_angle[int(payload["AngleIndex"] or 0)] = {
            "angle_index": int(payload["AngleIndex"] or 0),
            "track_id": _normalize_text(payload["TrackId"]),
            "item_id": _normalize_text(payload["ItemId"]) or None,
            "source_media_id": _normalize_text(payload["MediaRef"]) or None,
            "source_clip_name": _normalize_text(payload["SourceClipName"]) or None,
            "media_file_path": _normalize_text(payload["MediaFilePath"]) or None,
            "start_frame": int(payload["StartFrame"]) if payload["StartFrame"] not in (None, "") else None,
            "duration_frames": int(payload["DurationFrames"]) if payload["DurationFrames"] not in (None, "") else None,
            "media_start_time": float(payload["MediaStartTime"]) if payload["MediaStartTime"] not in (None, "") else None,
        }
    checks: list[dict[str, Any]] = []
    for replacement in mutation_result.get("updated_audio_items", []):
        actual = by_angle.get(int(replacement["angle_index"]))
        checks.append(
            {
                "name": "audio_angle_media_ref_replaced",
                "ok": bool(actual and actual["source_media_id"] == replacement["source_media_id"]),
                "angle_index": int(replacement["angle_index"]),
                "expected_source_media_id": replacement["source_media_id"],
                "actual": actual,
            }
        )
    for removed in mutation_result.get("removed_unmapped_audio_items", []):
        actual = by_angle.get(int(removed["angle_index"]))
        checks.append(
            {
                "name": "unmapped_audio_item_removed",
                "ok": bool(actual and actual["item_id"] is None),
                "angle_index": int(removed["angle_index"]),
                "removed_item_id": removed["item_id"],
                "actual": actual,
            }
        )
    status = "verified" if checks and all(bool(check["ok"]) for check in checks) else "failed"
    return {
        "status": status,
        "checks": checks,
        "audio_source_mapping": [by_angle[index] for index in sorted(by_angle)],
    }


def _resolve_or_import_audio_sources(conn: Any, sources: list[dict[str, Any]], *, allow_empty: bool = False) -> list[dict[str, Any]]:
    resolved_sources: list[dict[str, Any]] = []
    for source in _normalize_audio_sources(sources, allow_empty=allow_empty):
        path = str(source["path"])
        entry = {"path": path}
        try:
            resolved = media_pool.resolve_append_media_entry(conn, entry)
        except APICallFailed:
            expanded = os.path.expanduser(path)
            if not expanded or not os.path.exists(expanded):
                raise
            media_pool.import_media(conn, expanded)
            resolved = media_pool.resolve_append_media_entry(conn, entry)
        duration_frames = media_pool._source_total_frames(resolved["clip"], getattr(conn, "fps", 24.0) or 24.0)
        updated = {
            **source,
            "clip_name": str(resolved.get("name") or source["clip_name"]),
            "source_path": str(resolved.get("source_path") or source["source_path"]),
        }
        if duration_frames is not None:
            updated["duration_frames"] = int(duration_frames)
        resolved_sources.append(updated)
    return resolved_sources


def replace_multicam_audio(
    conn: Any,
    *,
    multicam_name: str | None = None,
    media_id: str | None = None,
    sequence_id: str | None = None,
    audio_sources: list[dict[str, Any]],
    audio_angle_map: dict[str, str],
    angle_order: list[str] | None = None,
    offsets: dict[str, int] | None = None,
    unmapped_audio: str = "keep",
    empty_angle_indices: list[int] | None = None,
) -> dict[str, Any]:
    normalized_empty_indices = _normalize_angle_indices(empty_angle_indices)
    resolved_sources = _resolve_or_import_audio_sources(conn, audio_sources, allow_empty=bool(normalized_empty_indices))

    def _writer(_connection: sqlite3.Connection, cursor: sqlite3.Cursor, session: db_session.DiskDbMutationSession) -> dict[str, Any]:
        return _write_multicam_audio_replacement(
            cursor,
            project_db_path=session.project_db_path,
            multicam_name=multicam_name,
            media_id=media_id,
            sequence_id=sequence_id,
            audio_sources=resolved_sources,
            audio_angle_map=audio_angle_map,
            angle_order=angle_order,
            offsets=offsets,
            unmapped_audio=unmapped_audio,
            empty_angle_indices=normalized_empty_indices,
        )

    def _verifier(_connection: Any, mutation_result: dict[str, Any], session: db_session.DiskDbMutationSession) -> dict[str, Any]:
        with sqlite3.connect(session.project_db_path) as fresh_connection:
            fresh_cursor = fresh_connection.cursor()
            return _build_verification(fresh_cursor, mutation_result=mutation_result)

    return db_session.execute_sqlite_disk_db_mutation(
        conn,
        context="Native multicam audio replacement",
        writer=_writer,
        verifier=_verifier,
        allow_project_name_inference=True,
    )
