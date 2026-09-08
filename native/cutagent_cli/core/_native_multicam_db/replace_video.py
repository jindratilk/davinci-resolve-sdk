"""Native multicam internal video replacement helpers."""

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


@dataclass(frozen=True)
class ResolvedVideoMediaRow:
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


def _normalize_video_targets(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list) or not raw:
        raise ValidationError("Native multicam video replacement requires video_targets[].", details={"video_targets": raw})
    normalized: list[dict[str, Any]] = []
    seen: set[int] = set()
    for index, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise ValidationError("Video target entries must be objects.", details={"index": index, "entry": entry})
        angle_index = int(entry.get("angle_index"))
        if angle_index < 0:
            raise ValidationError("Video replacement angle indexes must be zero or greater.", details={"angle_index": angle_index})
        if angle_index in seen:
            raise ValidationError("Video replacement angle targets must be unique.", details={"angle_index": angle_index})
        path = _normalize_text(entry.get("path") or entry.get("source_path") or entry.get("file"))
        if not path:
            raise ValidationError("Each video target must include path.", details={"index": index, "entry": entry})
        seen.add(angle_index)
        expanded_path = str(Path(path).expanduser())
        normalized.append(
            {
                "angle_index": angle_index,
                "angle_number": angle_index + 1,
                "path": expanded_path,
                "source_path": _normalize_text(entry.get("source_path")) or expanded_path,
                "clip_name": _normalize_text(entry.get("clip_name") or entry.get("name")) or os.path.basename(expanded_path),
            }
        )
    return normalized


def _normalize_frame_map(raw: Any, *, name: str) -> dict[int, int]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValidationError(f"{name} must be an object keyed by zero-based angle index.", details={name: raw})
    normalized: dict[int, int] = {}
    for key, value in raw.items():
        angle_index = int(key)
        if angle_index < 0:
            raise ValidationError(f"{name} angle indexes must be zero or greater.", details={"angle_index": angle_index})
        normalized[angle_index] = int(value)
    return normalized


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


def _fetch_video_tracks(cursor: sqlite3.Cursor, *, container_id: str) -> list[dict[str, Any]]:
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
          item.PreConformMediaExtents AS PreConformMediaExtents,
          item.MediaFrameRate AS MediaFrameRate,
          item.CurrentSelectorIdx AS CurrentSelectorIdx,
          item.FieldsBlob AS ItemFieldsBlob
        FROM Sm2TiTrack track
        JOIN Sm2SequenceContainer_Sm2TiTrack rel
          ON rel.DbOwner = ?
         AND rel.DbAssociate = track.Sm2TiTrack_id
         AND rel.DbPropertyName = 'VideoTrackVec'
        LEFT JOIN Sm2TiItem_Sm2TiTrack item_rel
          ON item_rel.DbOwner = track.Sm2TiTrack_id
         AND item_rel.DbPropertyName = 'Items'
        LEFT JOIN Sm2TiItem item
          ON item.Sm2TiItem_id = item_rel.DbAssociate
         AND item.DbType = 'Sm2TiVideoClip'
        WHERE track.Sm2SequenceContainer_id = ?
          AND track.Type = 0
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
                "angle_number": int(payload["AngleIndex"] or 0) + 1,
                "track_name": _normalize_text(payload["TrackName"]) or None,
                "track_subtype": int(payload["TrackSubType"] or 0),
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
                "preconform_media_extents": payload["PreConformMediaExtents"],
                "media_frame_rate": payload["MediaFrameRate"],
                "current_selector_idx": payload["CurrentSelectorIdx"],
                "item_fields_blob": payload["ItemFieldsBlob"],
            }
        )
    return tracks


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
        raise ValidationError(
            "Native multicam sequence video duration could not be derived.",
            details={"reason": "multicam_sequence_video_duration_missing", "multicam_sequence_id": sequence_id},
        )
    return {"start_frame": start_frame, "end_frame": end_frame, "duration_frames": end_frame - start_frame}


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


def _resolve_video_source_rows(project_db_path: str, *, targets: list[dict[str, Any]]) -> dict[int, ResolvedVideoMediaRow]:
    specs = [
        {
            "angle": str(target["angle_number"]),
            "clip_name": target["clip_name"],
            "source_path": target["source_path"],
            "duration_frames": target.get("duration_frames"),
            "fps": target.get("fps"),
        }
        for target in targets
    ]
    rows = _source_rows_resolve_source_media_rows(
        project_db_path,
        resolved_angles=specs,
        resolved_db_media_row_cls=ResolvedVideoMediaRow,
        row_to_dict_fn=_row_to_dict,
        temp_bin_prefix="__CutAgent Native Multicam ",
    )
    return {int(target["angle_index"]): row for target, row in zip(targets, rows)}


def _fetch_template_video_item(cursor: sqlite3.Cursor, *, sequence_id: str) -> dict[str, Any] | None:
    row = cursor.execute(
        """
        SELECT
          item.MediaTimemapBA,
          item.PreConformMediaExtents,
          item.MediaFrameRate,
          item.CurrentSelectorIdx,
          item.FieldsBlob
        FROM Sm2TiItem item
        JOIN Sm2TiTrack track ON track.Sm2TiTrack_id = item.Sm2TiTrack_id
        WHERE track.Sequence = ?
          AND item.DbType = 'Sm2TiVideoClip'
        ORDER BY item.rowid DESC
        LIMIT 1
        """,
        (sequence_id,),
    ).fetchone()
    if row is None:
        return None
    return _row_to_dict(cursor, row)


def _parse_in_value(value: Any) -> int:
    if value in (None, ""):
        return 0
    return int(value)


def _build_replacement_plan(
    cursor: sqlite3.Cursor,
    *,
    project_db_path: str,
    multicam_name: str | None,
    media_id: str | None,
    sequence_id: str | None,
    video_targets: list[dict[str, Any]],
    source_in_frames: dict[int, int],
    start_frames: dict[int, int],
    duration_frames: dict[int, int],
    allow_short_source: bool,
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
    video_tracks = _fetch_video_tracks(cursor, container_id=container_id)
    if not video_tracks:
        raise ValidationError(
            "Native multicam clip has no internal video tracks to replace.",
            details={"reason": "multicam_video_tracks_missing", **target},
        )
    tracks_by_angle = {int(track["angle_index"]): track for track in video_tracks}
    unknown_targets = sorted(int(item["angle_index"]) for item in video_targets if int(item["angle_index"]) not in tracks_by_angle)
    if unknown_targets:
        raise ValidationError(
            "Video replacement target references an internal multicam angle that does not exist.",
            details={
                "angle_indices": unknown_targets,
                "angle_numbers": [index + 1 for index in unknown_targets],
                "available_angle_indices": sorted(tracks_by_angle),
                "available_angle_numbers": [index + 1 for index in sorted(tracks_by_angle)],
            },
        )
    multi_item_targets = sorted(
        int(item["angle_index"])
        for item in video_targets
        if int(tracks_by_angle[int(item["angle_index"])].get("item_count") or 0) > 1
    )
    if multi_item_targets:
        raise ValidationError(
            "Video replacement requires item-level targeting for multicam angles that contain multiple source clips.",
            details={
                "reason": "multi_item_angle_requires_item_target",
                "angle_indices": multi_item_targets,
                "angle_numbers": [index + 1 for index in multi_item_targets],
                "hint": "Replace individual source items only after item-level targeting is available, or recreate the multicam clip.",
            },
        )

    source_rows = _resolve_video_source_rows(project_db_path, targets=video_targets)
    sequence_span = _fetch_sequence_span(cursor, sequence_id=resolved_sequence_id)
    fps = _fetch_sequence_fps(cursor, sequence_id=resolved_sequence_id, media_id=resolved_media_id)
    replacements: list[dict[str, Any]] = []
    for target_entry in video_targets:
        angle_index = int(target_entry["angle_index"])
        track = tracks_by_angle[angle_index]
        source_row = source_rows[angle_index]
        item_start = int(start_frames.get(angle_index, track["item_start"] if track["item_id"] else sequence_span["start_frame"]))
        source_start = int(source_in_frames.get(angle_index, _parse_in_value(track.get("in_value")) if track["item_id"] else 0))
        duration = int(duration_frames.get(angle_index, track["item_duration"] if track["item_id"] else sequence_span["duration_frames"]))
        if duration <= 0:
            raise ValidationError(
                "Video replacement duration must be greater than zero.",
                details={"angle_index": angle_index, "angle_number": angle_index + 1, "duration_frames": duration},
            )
        source_duration = int(source_row.duration_frames or 0)
        if source_duration > 0 and not allow_short_source and source_start + duration > source_duration:
            raise ValidationError(
                "Replacement video source does not cover the requested internal angle range.",
                details={
                    "angle_index": angle_index,
                    "angle_number": angle_index + 1,
                    "source_duration_frames": source_duration,
                    "source_start_frames": source_start,
                    "duration_frames": duration,
                    "required_frames": source_start + duration,
                    "hint": "Choose a shorter --duration, lower --source-in, or pass --allow-short-source.",
                },
            )
        replacements.append(
            {
                "angle_index": angle_index,
                "angle_number": angle_index + 1,
                "track_id": track["track_id"],
                "existing_item_id": track["item_id"],
                "source_media_id": source_row.media_id,
                "source_clip_name": source_row.name,
                "source_path": source_row.source_path or target_entry["source_path"],
                "source_db_type": source_row.db_type,
                "item_start_frame": item_start,
                "source_start_frames": source_start,
                "duration_frames": duration,
                "media_start_time_seconds": float(source_row.media_start_time or 0.0),
            }
        )
    return {
        "action": "multicam.replace_video",
        **target,
        "container_id": container_id,
        "sequence_span": sequence_span,
        "fps": fps,
        "video_track_count": len(video_tracks),
        "allow_short_source": bool(allow_short_source),
        "replacements": replacements,
    }


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
            SELECT MediaRef, MediaFilePath, Start, Duration, "In", MediaStartTime
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
              MediaTimemapBA = ?
            WHERE Sm2TiItem_id = ?
              AND DbType = 'Sm2TiVideoClip'
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
                "in": before[4] if before else None,
                "media_start_time": before[5] if before else None,
            },
        }
    if template is None:
        raise ValidationError(
            "Cannot create missing multicam video item because no video item template exists.",
            details={
                "reason": "missing_video_item_template",
                "track_id": replacement["track_id"],
                "angle_index": replacement["angle_index"],
                "angle_number": replacement["angle_number"],
            },
        )
    item_id = str(uuid.uuid4())
    cursor.execute(
        """
        INSERT INTO Sm2TiItem (
            Sm2TiItem_id, DbType, Name, Start, Duration, "In", MediaRef, MediaStartTime,
            MediaFilePath, MediaTimemapBA, PreConformMediaExtents, MediaFrameRate,
            Sm2TiTrack_id, UiMemento, Flags, PriorityIndex,
            ThumbnailDirtyFlag, RenderTextEnabled, RenderTextGanged, RenderTextPrefixed,
            IsForceConformed, MatchConflictState, IsPreConformed, MixedFrameRateAlignment,
            UseOppositeSrcForLeftEye, UseOppositeSrcForRightEye, WasDisbanded,
            CurrentSelectorIdx, FieldsBlob
        ) VALUES (
            ?, 'Sm2TiVideoClip', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 0,
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
            template.get("PreConformMediaExtents"),
            template.get("MediaFrameRate"),
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


def plan_multicam_video_replacement(
    project_db_path: str,
    *,
    multicam_name: str | None = None,
    media_id: str | None = None,
    sequence_id: str | None = None,
    video_targets: list[dict[str, Any]],
    source_in_frames: dict[int, int] | None = None,
    start_frames: dict[int, int] | None = None,
    duration_frames: dict[int, int] | None = None,
    allow_short_source: bool = False,
) -> dict[str, Any]:
    normalized_targets = _normalize_video_targets(video_targets)
    connection = sqlite3.connect(project_db_path)
    try:
        cursor = connection.cursor()
        return _build_replacement_plan(
            cursor,
            project_db_path=project_db_path,
            multicam_name=multicam_name,
            media_id=media_id,
            sequence_id=sequence_id,
            video_targets=normalized_targets,
            source_in_frames=_normalize_frame_map(source_in_frames, name="source_in_frames"),
            start_frames=_normalize_frame_map(start_frames, name="start_frames"),
            duration_frames=_normalize_frame_map(duration_frames, name="duration_frames"),
            allow_short_source=allow_short_source,
        )
    finally:
        connection.close()


def _write_multicam_video_replacement(
    cursor: sqlite3.Cursor,
    *,
    project_db_path: str,
    multicam_name: str | None = None,
    media_id: str | None = None,
    sequence_id: str | None = None,
    video_targets: list[dict[str, Any]],
    source_in_frames: dict[int, int] | None = None,
    start_frames: dict[int, int] | None = None,
    duration_frames: dict[int, int] | None = None,
    allow_short_source: bool = False,
) -> dict[str, Any]:
    plan = _build_replacement_plan(
        cursor,
        project_db_path=project_db_path,
        multicam_name=multicam_name,
        media_id=media_id,
        sequence_id=sequence_id,
        video_targets=_normalize_video_targets(video_targets),
        source_in_frames=_normalize_frame_map(source_in_frames, name="source_in_frames"),
        start_frames=_normalize_frame_map(start_frames, name="start_frames"),
        duration_frames=_normalize_frame_map(duration_frames, name="duration_frames"),
        allow_short_source=allow_short_source,
    )
    template = _fetch_template_video_item(cursor, sequence_id=plan["multicam_sequence_id"])
    updated_items = [
        _write_replacement_item(cursor, replacement=replacement, fps=float(plan["fps"]), template=template)
        for replacement in plan["replacements"]
    ]
    return {
        **plan,
        "changed": bool(updated_items),
        "updated_video_items": updated_items,
    }


def _build_verification(cursor: sqlite3.Cursor, *, mutation_result: dict[str, Any]) -> dict[str, Any]:
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
          item."In" AS InValue,
          source.Name AS SourceClipName
        FROM Sm2SequenceContainer container
        JOIN Sm2SequenceContainer_Sm2TiTrack rel
          ON rel.DbOwner = container.Sm2SequenceContainer_id
         AND rel.DbPropertyName = 'VideoTrackVec'
        JOIN Sm2TiTrack track ON track.Sm2TiTrack_id = rel.DbAssociate
        LEFT JOIN Sm2TiItem item
          ON item.Sm2TiTrack_id = track.Sm2TiTrack_id
         AND item.DbType = 'Sm2TiVideoClip'
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
            "angle_number": int(payload["AngleIndex"] or 0) + 1,
            "track_id": _normalize_text(payload["TrackId"]),
            "item_id": _normalize_text(payload["ItemId"]) or None,
            "source_media_id": _normalize_text(payload["MediaRef"]) or None,
            "source_clip_name": _normalize_text(payload["SourceClipName"]) or None,
            "media_file_path": _normalize_text(payload["MediaFilePath"]) or None,
            "start_frame": int(payload["StartFrame"]) if payload["StartFrame"] not in (None, "") else None,
            "duration_frames": int(payload["DurationFrames"]) if payload["DurationFrames"] not in (None, "") else None,
            "in": payload["InValue"],
        }
    checks: list[dict[str, Any]] = []
    for replacement in mutation_result.get("updated_video_items", []):
        actual = by_angle.get(int(replacement["angle_index"]))
        checks.append(
            {
                "name": "video_angle_media_ref_replaced",
                "ok": bool(actual and actual["source_media_id"] == replacement["source_media_id"]),
                "angle_index": int(replacement["angle_index"]),
                "angle_number": int(replacement["angle_number"]),
                "expected_source_media_id": replacement["source_media_id"],
                "actual": actual,
            }
        )
    status = "verified" if checks and all(bool(check["ok"]) for check in checks) else "failed"
    return {
        "status": status,
        "checks": checks,
        "video_source_mapping": [by_angle[index] for index in sorted(by_angle)],
    }


def _resolve_or_import_video_targets(conn: Any, targets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    resolved_targets: list[dict[str, Any]] = []
    for target in _normalize_video_targets(targets):
        path = str(target["path"])
        entry = {"path": path}
        try:
            resolved = media_pool.resolve_append_media_entry(conn, entry)
        except APICallFailed:
            expanded = os.path.expanduser(path)
            if not expanded or not os.path.exists(expanded):
                raise
            media_pool.import_media(conn, expanded)
            resolved = media_pool.resolve_append_media_entry(conn, entry)
        duration = media_pool._source_total_frames(resolved["clip"], getattr(conn, "fps", 24.0) or 24.0)
        updated = {
            **target,
            "clip_name": str(resolved.get("name") or target["clip_name"]),
            "source_path": str(resolved.get("source_path") or target["source_path"]),
        }
        if duration is not None:
            updated["duration_frames"] = int(duration)
        resolved_targets.append(updated)
    return resolved_targets


def replace_multicam_video(
    conn: Any,
    *,
    multicam_name: str | None = None,
    media_id: str | None = None,
    sequence_id: str | None = None,
    video_targets: list[dict[str, Any]],
    source_in_frames: dict[int, int] | None = None,
    start_frames: dict[int, int] | None = None,
    duration_frames: dict[int, int] | None = None,
    allow_short_source: bool = False,
) -> dict[str, Any]:
    resolved_targets = _resolve_or_import_video_targets(conn, video_targets)

    def _writer(_connection: sqlite3.Connection, cursor: sqlite3.Cursor, session: db_session.DiskDbMutationSession) -> dict[str, Any]:
        return _write_multicam_video_replacement(
            cursor,
            project_db_path=session.project_db_path,
            multicam_name=multicam_name,
            media_id=media_id,
            sequence_id=sequence_id,
            video_targets=resolved_targets,
            source_in_frames=source_in_frames,
            start_frames=start_frames,
            duration_frames=duration_frames,
            allow_short_source=allow_short_source,
        )

    def _verifier(_connection: Any, mutation_result: dict[str, Any], session: db_session.DiskDbMutationSession) -> dict[str, Any]:
        with sqlite3.connect(session.project_db_path) as fresh_connection:
            fresh_cursor = fresh_connection.cursor()
            return _build_verification(fresh_cursor, mutation_result=mutation_result)

    return db_session.execute_sqlite_disk_db_mutation(
        conn,
        context="Native multicam video replacement",
        writer=_writer,
        verifier=_verifier,
        allow_project_name_inference=True,
    )
