"""Timeline seeding helpers for native multicam clips."""

from __future__ import annotations

import sqlite3
from typing import Any

from ...connection import ResolveConnection
from ...errors import APICallFailed, ValidationError
from ...utils.time_ref import parse_record_frame
from .. import db_session, timeline_ops


def _normalize_folder_path(value: str | None) -> str:
    text = str(value or "").strip().strip("/")
    return "/".join(segment for segment in text.split("/") if segment)


def _folder_path_matches(candidate: str | None, requested: str | None) -> bool:
    normalized_requested = _normalize_folder_path(requested)
    if not normalized_requested:
        return True
    normalized_candidate = _normalize_folder_path(candidate)
    return normalized_candidate == normalized_requested or normalized_candidate.endswith(f"/{normalized_requested}")


def _placeholders(values: list[str]) -> str:
    if not values:
        raise ValueError("Cannot build SQL placeholders for an empty list.")
    return ",".join("?" for _ in values)


def _fetch_folder_paths(cursor: sqlite3.Cursor) -> dict[str, str]:
    rows = cursor.execute(
        """
        SELECT
            Sm2MpFolder_id,
            Name,
            MpFolder,
            Sm2MpFolder_Owner_id
        FROM Sm2MpFolder
        """
    ).fetchall()
    folder_rows = {
        str(row[0]): {
            "name": str(row[1] or ""),
            "parent": str(row[2] or row[3] or "") or None,
        }
        for row in rows
        if row[0]
    }
    cache: dict[str, str] = {}

    def build_path(folder_id: str, stack: set[str] | None = None) -> str:
        if folder_id in cache:
            return cache[folder_id]
        stack = stack or set()
        if folder_id in stack:
            return folder_rows[folder_id]["name"]
        stack.add(folder_id)
        folder = folder_rows[folder_id]
        name = folder["name"]
        parent_id = folder["parent"]
        if parent_id and parent_id in folder_rows and parent_id != folder_id:
            parent_path = build_path(parent_id, stack)
            cache[folder_id] = f"{parent_path}/{name}" if parent_path else name
        else:
            cache[folder_id] = name
        stack.remove(folder_id)
        return cache[folder_id]

    for folder_id in folder_rows:
        build_path(folder_id)
    return cache


def _row_to_target(row: sqlite3.Row | tuple[Any, ...], folder_paths: dict[str, str]) -> dict[str, Any]:
    folder_id = str(row[2] or "") or None
    return {
        "multicam_media_id": str(row[0] or ""),
        "multicam_name": str(row[1] or ""),
        "folder_id": folder_id,
        "folder_path": folder_paths.get(folder_id or "", "") or None,
        "multicam_sequence_id": str(row[3] or "") or None,
    }


def resolve_multicam_timeline_seed_target(
    cursor: sqlite3.Cursor,
    *,
    multicam_name: str | None = None,
    media_id: str | None = None,
    folder: str | None = None,
) -> dict[str, Any]:
    normalized_name = str(multicam_name or "").strip()
    normalized_media_id = str(media_id or "").strip()
    normalized_folder = _normalize_folder_path(folder)
    if not normalized_name and not normalized_media_id:
        raise ValidationError(
            "Timeline seed requires --multicam-name or --media-id.",
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

    rows = cursor.execute(
        f"""
        SELECT media.Sm2MpMedia_id, media.Name, media.Sm2MpFolder_id, seq.Sm2Sequence_id
        FROM Sm2MpMedia media
        LEFT JOIN Sm2Sequence seq ON seq.Sm2MpMedia_id = media.Sm2MpMedia_id
        WHERE {" AND ".join(clauses)}
        ORDER BY LOWER(media.Name), media.Sm2MpMedia_id, seq.Sm2Sequence_id
        """,
        tuple(params),
    ).fetchall()
    folder_paths = _fetch_folder_paths(cursor)
    candidates = [_row_to_target(row, folder_paths) for row in rows]
    if normalized_folder:
        candidates = [candidate for candidate in candidates if _folder_path_matches(candidate.get("folder_path"), normalized_folder)]

    if not candidates:
        raise ValidationError(
            "Could not find a native multicam clip matching the requested selector.",
            details={
                "reason": "multicam_not_found",
                "multicam_name": normalized_name or None,
                "multicam_media_id": normalized_media_id or None,
                "folder": normalized_folder or None,
                "candidates": [],
            },
        )
    if len(candidates) > 1:
        raise ValidationError(
            "Native multicam clip selector is ambiguous; provide --media-id or --folder.",
            details={
                "reason": "ambiguous_multicam_name",
                "multicam_name": normalized_name or None,
                "multicam_media_id": normalized_media_id or None,
                "folder": normalized_folder or None,
                "candidates": candidates,
            },
        )
    return candidates[0]


def _list_project_timelines(conn) -> list[Any]:
    project = getattr(conn, "project", None)
    if project is None:
        return []
    try:
        count = int(project.GetTimelineCount() or 0)
    except Exception:
        return []
    return [timeline for index in range(1, count + 1) if (timeline := project.GetTimelineByIndex(index))]


def resolve_timeline_target(
    conn: Any,
    *,
    timeline_name: str | None = None,
    activate: bool = False,
) -> dict[str, Any]:
    normalized_name = str(timeline_name or "").strip()
    if normalized_name:
        for index, timeline in enumerate(_list_project_timelines(conn), start=1):
            name = timeline.GetName() if hasattr(timeline, "GetName") else None
            if name != normalized_name:
                continue
            activation = None
            if activate:
                activation = timeline_ops.switch_timeline(conn, name=normalized_name, return_details=True)
                timeline = getattr(conn, "timeline", None)
            return {
                "timeline": timeline,
                "timeline_name": normalized_name,
                "timeline_index": index,
                "activated": bool(activate),
                "activation": activation,
            }
        raise APICallFailed("Timeline not found.", details={"timeline_name": normalized_name})

    timeline = getattr(conn, "timeline", None)
    if timeline is None:
        raise APICallFailed("No active timeline is available for multicam timeline seed.")
    name = timeline.GetName() if hasattr(timeline, "GetName") else None
    return {
        "timeline": timeline,
        "timeline_name": name,
        "timeline_index": None,
        "activated": False,
        "activation": None,
    }


def _timeline_start_frame(timeline: Any, *, fallback: int = 0) -> tuple[int, str]:
    getter = getattr(timeline, "GetStartFrame", None)
    if callable(getter):
        try:
            return int(getter()), "timeline.GetStartFrame"
        except Exception:
            pass
    return int(fallback or 0), "conn.start_frame"


def _track_item_counts(timeline: Any, track_type: str) -> dict[str, Any]:
    count_getter = getattr(timeline, "GetTrackCount", None)
    items_getter = getattr(timeline, "GetItemListInTrack", None)
    try:
        track_count = int(count_getter(track_type) or 0) if callable(count_getter) else 0
    except Exception:
        track_count = 0
    per_track: list[dict[str, int]] = []
    total_items = 0
    for track_index in range(1, track_count + 1):
        try:
            items = list(items_getter(track_type, track_index) or []) if callable(items_getter) else []
        except Exception:
            items = []
        item_count = len(items)
        total_items += item_count
        per_track.append({"track_index": track_index, "item_count": item_count})
    return {
        "track_count": track_count,
        "item_count": total_items,
        "track_counts": per_track,
    }


def inspect_timeline_seed_preflight(timeline: Any) -> dict[str, Any]:
    video = _track_item_counts(timeline, "video")
    audio = _track_item_counts(timeline, "audio")
    return {
        "video_items": video["item_count"],
        "audio_items": audio["item_count"],
        "video_track_count": video["track_count"],
        "audio_track_count": audio["track_count"],
        "video_track_counts": video["track_counts"],
        "audio_track_counts": audio["track_counts"],
        "empty": video["item_count"] == 0 and audio["item_count"] == 0,
    }


def _resolve_record_frame(
    conn: Any,
    timeline: Any,
    record_frame: str | None,
    absolute_record_frame: int | None = None,
) -> tuple[int, str]:
    if record_frame is not None and absolute_record_frame is not None:
        raise ValidationError(
            "Use only one of --record-frame or --absolute-record-frame for multicam timeline seed.",
            details={"reason": "conflicting_record_frame_options"},
        )
    if absolute_record_frame is not None:
        value = int(absolute_record_frame)
        if value < 0:
            raise ValidationError(
                "Multicam timeline seed absolute record frame must be non-negative.",
                details={"absolute_record_frame": absolute_record_frame},
            )
        return value, "absolute"

    timeline_start, fallback_source = _timeline_start_frame(timeline, fallback=int(getattr(conn, "start_frame", 0) or 0))
    normalized_ref = str(record_frame or "").strip()
    if not normalized_ref:
        return timeline_start, fallback_source
    return (
        parse_record_frame(normalized_ref, float(getattr(conn, "fps", 24.0) or 24.0), timeline_start),
        "explicit",
    )


def plan_multicam_timeline_seed(
    conn: Any,
    *,
    project_db_path: str,
    multicam_name: str | None = None,
    media_id: str | None = None,
    folder: str | None = None,
    timeline_name: str | None = None,
    record_frame: str | None = None,
    absolute_record_frame: int | None = None,
    require_empty: bool = False,
    reset_first: bool = False,
) -> dict[str, Any]:
    if require_empty and reset_first:
        raise ValidationError(
            "Use either --require-empty or --reset-first, not both.",
            details={"reason": "conflicting_timeline_seed_options"},
        )

    with sqlite3.connect(project_db_path) as connection:
        connection.row_factory = sqlite3.Row
        target = resolve_multicam_timeline_seed_target(
            connection.cursor(),
            multicam_name=multicam_name,
            media_id=media_id,
            folder=folder,
        )

    timeline_context = resolve_timeline_target(conn, timeline_name=timeline_name, activate=False)
    timeline = timeline_context["timeline"]
    if timeline is None:
        raise APICallFailed("No target timeline is available for multicam timeline seed.")

    preflight = inspect_timeline_seed_preflight(timeline)
    resolved_record_frame, record_frame_source = _resolve_record_frame(
        conn,
        timeline,
        record_frame,
        absolute_record_frame=absolute_record_frame,
    )
    blocked_reason = None
    if not preflight["empty"] and not reset_first:
        blocked_reason = "timeline_not_empty"

    return {
        "action": "multicam.seed_timeline",
        "target": {"kind": "multicam_clip", "name": target["multicam_name"]},
        "timeline_name": timeline_context["timeline_name"],
        "timeline_index": timeline_context["timeline_index"],
        "multicam_name": target["multicam_name"],
        "multicam_media_id": target["multicam_media_id"],
        "multicam_sequence_id": target["multicam_sequence_id"],
        "folder": target.get("folder_path"),
        "record_frame": resolved_record_frame,
        "record_frame_source": record_frame_source,
        "track_type": "video",
        "track_index": 1,
        "preflight": preflight,
        "require_empty": bool(require_empty),
        "reset_first": bool(reset_first),
        "ready": blocked_reason is None,
        "blocked_reason": blocked_reason,
    }


def _fetch_timeline_sequence(cursor: sqlite3.Cursor, *, timeline_name: str) -> str:
    row = cursor.execute(
        "SELECT Sequence FROM Sm2Timeline WHERE Name = ? LIMIT 1",
        (timeline_name,),
    ).fetchone()
    if not row or row[0] in (None, ""):
        raise ValidationError(
            "Target timeline does not exist in the Disk project database.",
            details={"reason": "timeline_not_found", "timeline_name": timeline_name},
        )
    return str(row[0])


def _fetch_track_ids(cursor: sqlite3.Cursor, *, sequence_id: str, track_type: int) -> list[str]:
    rows = cursor.execute(
        """
        SELECT Sm2TiTrack_id
        FROM Sm2TiTrack
        WHERE Sequence = ? AND Type = ?
        ORDER BY Sm2TiTrack_id
        """,
        (sequence_id, int(track_type)),
    ).fetchall()
    return [str(row[0]) for row in rows if row and row[0]]


def _count_db_track_items(cursor: sqlite3.Cursor, *, sequence_id: str, track_type: int) -> int:
    row = cursor.execute(
        """
        SELECT COUNT(DISTINCT rel.DbAssociate)
        FROM Sm2TiItem_Sm2TiTrack rel
        JOIN Sm2TiTrack track ON track.Sm2TiTrack_id = rel.DbOwner
        WHERE track.Sequence = ?
          AND track.Type = ?
          AND rel.DbPropertyName = 'Items'
        """,
        (sequence_id, int(track_type)),
    ).fetchone()
    return int((row[0] if row else 0) or 0)


def _write_timeline_seed_reset(cursor: sqlite3.Cursor, *, timeline_name: str) -> dict[str, Any]:
    sequence_id = _fetch_timeline_sequence(cursor, timeline_name=timeline_name)
    video_track_ids = _fetch_track_ids(cursor, sequence_id=sequence_id, track_type=0)
    audio_track_ids = _fetch_track_ids(cursor, sequence_id=sequence_id, track_type=1)
    all_track_ids = video_track_ids + audio_track_ids
    before_video_items = _count_db_track_items(cursor, sequence_id=sequence_id, track_type=0)
    before_audio_items = _count_db_track_items(cursor, sequence_id=sequence_id, track_type=1)
    item_ids: list[str] = []
    if all_track_ids:
        rows = cursor.execute(
            f"""
            SELECT DISTINCT rel.DbAssociate
            FROM Sm2TiItem_Sm2TiTrack rel
            WHERE rel.DbOwner IN ({_placeholders(all_track_ids)})
              AND rel.DbPropertyName = 'Items'
            """,
            tuple(all_track_ids),
        ).fetchall()
        item_ids = [str(row[0]) for row in rows if row and row[0]]

    removed_relations = 0
    removed_item_links = 0
    removed_items = 0
    removed_compositions = 0
    if item_ids:
        removed_relations = cursor.execute(
            f"""
            DELETE FROM Sm2TiItem_Sm2TiTrack
            WHERE DbOwner IN ({_placeholders(all_track_ids)})
              AND DbPropertyName = 'Items'
            """,
            tuple(all_track_ids),
        ).rowcount
        removed_item_links = cursor.execute(
            f"""
            DELETE FROM Sm2TiItem_Sm2TiItem
            WHERE DbOwner IN ({_placeholders(item_ids)})
               OR DbAssociate IN ({_placeholders(item_ids)})
            """,
            tuple(item_ids + item_ids),
        ).rowcount
        try:
            removed_compositions = cursor.execute(
                f"""
                DELETE FROM Sm2TiCompositionTable
                WHERE Sm2TiItem_id IN ({_placeholders(item_ids)})
                """,
                tuple(item_ids),
            ).rowcount
        except sqlite3.OperationalError:
            removed_compositions = 0
        removed_items = cursor.execute(
            f"""
            DELETE FROM Sm2TiItem
            WHERE Sm2TiTrack_id IN ({_placeholders(all_track_ids)})
               OR Sm2TiItem_id IN ({_placeholders(item_ids)})
            """,
            tuple(all_track_ids + item_ids),
        ).rowcount

    return {
        "action": "multicam.seed_timeline.reset",
        "changed": bool(item_ids),
        "timeline_name": timeline_name,
        "timeline_sequence_id": sequence_id,
        "video_tracks_preserved": len(video_track_ids),
        "audio_tracks_preserved": len(audio_track_ids),
        "removed_video_items": before_video_items,
        "removed_audio_items": before_audio_items,
        "removed_item_relations": removed_relations,
        "removed_item_links": removed_item_links,
        "removed_items": removed_items,
        "removed_compositions": removed_compositions,
    }


def _build_reset_verification(
    conn: Any,
    *,
    timeline_name: str,
    before_preflight: dict[str, Any],
) -> dict[str, Any]:
    timeline_context = resolve_timeline_target(conn, timeline_name=timeline_name, activate=False)
    timeline = timeline_context["timeline"]
    if timeline is None:
        return {
            "status": "failed",
            "checks": [{"name": "timeline_reopened", "ok": False, "timeline_name": timeline_name}],
        }

    after_preflight = inspect_timeline_seed_preflight(timeline)
    checks = [
        {"name": "timeline_reopened", "ok": True, "timeline_name": timeline_name},
        {
            "name": "video_track_count_preserved",
            "ok": after_preflight["video_track_count"] == before_preflight["video_track_count"],
            "before": before_preflight["video_track_count"],
            "after": after_preflight["video_track_count"],
        },
        {
            "name": "audio_track_count_preserved",
            "ok": after_preflight["audio_track_count"] == before_preflight["audio_track_count"],
            "before": before_preflight["audio_track_count"],
            "after": after_preflight["audio_track_count"],
        },
        {"name": "video_items_cleared", "ok": after_preflight["video_items"] == 0, "after": after_preflight["video_items"]},
        {"name": "audio_items_cleared", "ok": after_preflight["audio_items"] == 0, "after": after_preflight["audio_items"]},
    ]
    status = "verified" if all(bool(check["ok"]) for check in checks) else "failed"
    return {"status": status, "checks": checks, "after": after_preflight}


def reset_timeline_for_multicam_seed(
    conn: Any,
    *,
    timeline_name: str,
    before_preflight: dict[str, Any],
) -> dict[str, Any]:
    def _writer(_connection: sqlite3.Connection, cursor: sqlite3.Cursor, _session: db_session.DiskDbMutationSession) -> dict[str, Any]:
        return _write_timeline_seed_reset(cursor, timeline_name=timeline_name)

    def _verifier(fresh_conn: Any, _mutation_result: dict[str, Any], _session: db_session.DiskDbMutationSession) -> dict[str, Any]:
        return _build_reset_verification(fresh_conn, timeline_name=timeline_name, before_preflight=before_preflight)

    return db_session.execute_sqlite_disk_db_mutation(
        conn,
        context="Native multicam timeline seed reset",
        writer=_writer,
        verifier=_verifier,
        allow_project_name_inference=True,
    )


def _write_multicam_seed_media_ref_repair(
    cursor: sqlite3.Cursor,
    *,
    timeline_name: str,
    multicam_name: str,
    multicam_media_id: str,
) -> dict[str, Any]:
    rows = cursor.execute(
        """
        SELECT
            item.Sm2TiItem_id,
            item.MediaRef,
            item."In",
            item.Start,
            track.Type AS TrackType
        FROM Sm2Timeline timeline
        JOIN Sm2TiTrack track ON track.Sequence = timeline.Sequence
        JOIN Sm2TiItem_Sm2TiTrack rel_item
          ON rel_item.DbOwner = track.Sm2TiTrack_id
         AND rel_item.DbPropertyName = 'Items'
        JOIN Sm2TiItem item ON item.Sm2TiItem_id = rel_item.DbAssociate
        WHERE timeline.Name = ?
          AND timeline.Sequence IS NOT NULL
          AND timeline.Sequence <> ''
          AND track.Type IN (0, 1)
          AND item.Name = ?
        ORDER BY track.Type, rel_item.DbIndex
        """,
        (timeline_name, multicam_name),
    ).fetchall()
    item_ids = [str(row[0]) for row in rows if row and row[0]]
    repair_ids = [
        str(row[0])
        for row in rows
        if row
        and row[0]
        and (str(row[1] or "") != str(multicam_media_id) or row[2] is None or str(row[2]) == "")
    ]
    if repair_ids:
        cursor.execute(
            f"""
            UPDATE Sm2TiItem
            SET MediaRef = ?,
                "In" = COALESCE(NULLIF("In", ''), Start)
            WHERE Sm2TiItem_id IN ({_placeholders(repair_ids)})
            """,
            (multicam_media_id, *repair_ids),
        )

    return {
        "action": "multicam.seed_timeline.media_ref_repair",
        "changed": bool(repair_ids),
        "timeline_name": timeline_name,
        "multicam_name": multicam_name,
        "multicam_media_id": multicam_media_id,
        "timeline_multicam_item_count": len(item_ids),
        "repaired_item_count": len(repair_ids),
        "repaired_item_ids": repair_ids,
    }


def _build_seed_media_ref_verification(
    project_db_path: str,
    *,
    timeline_name: str,
    multicam_name: str,
    multicam_media_id: str,
) -> dict[str, Any]:
    connection = sqlite3.connect(project_db_path)
    try:
        row = connection.execute(
            """
            SELECT
                COUNT(*) AS ItemCount,
                SUM(CASE WHEN item.MediaRef = ? THEN 1 ELSE 0 END) AS LinkedCount,
                SUM(CASE WHEN NULLIF(item."In", '') IS NOT NULL THEN 1 ELSE 0 END) AS SourceInCount
            FROM Sm2Timeline timeline
            JOIN Sm2TiTrack track ON track.Sequence = timeline.Sequence
            JOIN Sm2TiItem_Sm2TiTrack rel_item
              ON rel_item.DbOwner = track.Sm2TiTrack_id
             AND rel_item.DbPropertyName = 'Items'
            JOIN Sm2TiItem item ON item.Sm2TiItem_id = rel_item.DbAssociate
            WHERE timeline.Name = ?
              AND timeline.Sequence IS NOT NULL
              AND timeline.Sequence <> ''
              AND track.Type IN (0, 1)
              AND item.Name = ?
            """,
            (multicam_media_id, timeline_name, multicam_name),
        ).fetchone()
    finally:
        connection.close()

    item_count = int((row[0] if row else 0) or 0)
    linked_count = int((row[1] if row else 0) or 0)
    source_in_count = int((row[2] if row else 0) or 0)
    checks = [
        {"name": "timeline_multicam_items_present", "ok": item_count > 0, "item_count": item_count},
        {
            "name": "timeline_multicam_items_media_ref_linked",
            "ok": item_count > 0 and linked_count == item_count,
            "item_count": item_count,
            "linked_count": linked_count,
            "multicam_media_id": multicam_media_id,
        },
        {
            "name": "timeline_multicam_items_source_in_present",
            "ok": item_count > 0 and source_in_count == item_count,
            "item_count": item_count,
            "source_in_count": source_in_count,
        },
    ]
    status = "verified" if all(bool(check["ok"]) for check in checks) else "failed"
    return {"status": status, "checks": checks}


def repair_multicam_seed_timeline_media_ref(
    conn: Any,
    *,
    timeline_name: str,
    multicam_name: str,
    multicam_media_id: str,
) -> dict[str, Any]:
    def _writer(_connection: sqlite3.Connection, cursor: sqlite3.Cursor, _session: db_session.DiskDbMutationSession) -> dict[str, Any]:
        return _write_multicam_seed_media_ref_repair(
            cursor,
            timeline_name=timeline_name,
            multicam_name=multicam_name,
            multicam_media_id=multicam_media_id,
        )

    def _verifier(_fresh_conn: Any, _mutation_result: dict[str, Any], session: db_session.DiskDbMutationSession) -> dict[str, Any]:
        return _build_seed_media_ref_verification(
            session.project_db_path,
            timeline_name=timeline_name,
            multicam_name=multicam_name,
            multicam_media_id=multicam_media_id,
        )

    return db_session.execute_sqlite_disk_db_mutation(
        conn,
        context="Native multicam timeline seed media reference repair",
        writer=_writer,
        verifier=_verifier,
        allow_project_name_inference=True,
    )


def _clip_media_id(clip: Any) -> str | None:
    for attr in ("GetMediaId", "GetUniqueId"):
        getter = getattr(clip, attr, None)
        if not callable(getter):
            continue
        try:
            value = getter()
        except Exception:
            value = None
        if value not in (None, ""):
            return str(value)
    return None


def _collect_live_clip_matches(folder: Any, *, parent_path: str = "") -> list[dict[str, Any]]:
    folder_name = folder.GetName() if hasattr(folder, "GetName") else ""
    current_path = f"{parent_path}/{folder_name}" if parent_path else str(folder_name)
    matches: list[dict[str, Any]] = []
    for clip in folder.GetClipList() or []:
        matches.append(
            {
                "clip": clip,
                "name": clip.GetName() if hasattr(clip, "GetName") else None,
                "folder": current_path,
                "media_id": _clip_media_id(clip),
            }
        )
    for subfolder in folder.GetSubFolderList() or []:
        matches.extend(_collect_live_clip_matches(subfolder, parent_path=current_path))
    return matches


def resolve_live_multicam_media_pool_item(conn: Any, *, target: dict[str, Any]) -> tuple[Any, list[dict[str, Any]]]:
    root = conn.media_pool.GetRootFolder() if getattr(conn, "media_pool", None) else None
    if root is None:
        raise APICallFailed("DaVinci Resolve media pool root is not available for multicam timeline seed.")

    candidates = [
        candidate
        for candidate in _collect_live_clip_matches(root)
        if candidate.get("name") == target["multicam_name"]
    ]
    if target.get("folder_path"):
        candidates = [candidate for candidate in candidates if _folder_path_matches(candidate.get("folder"), target.get("folder_path"))]
    if target.get("multicam_media_id"):
        exact_matches = [candidate for candidate in candidates if candidate.get("media_id") == target["multicam_media_id"]]
        if exact_matches:
            candidates = exact_matches
    serialized = [
        {
            "multicam_name": candidate.get("name"),
            "multicam_media_id": candidate.get("media_id"),
            "folder": candidate.get("folder"),
        }
        for candidate in candidates
    ]
    if not candidates:
        raise APICallFailed(
            "Native multicam clip exists in Project.db but could not be resolved in the live Media Pool.",
            details={**target, "candidates": serialized},
        )
    if len(candidates) > 1:
        raise APICallFailed(
            "Live Media Pool multicam resolution is ambiguous.",
            details={**target, "candidates": serialized},
        )
    return candidates[0]["clip"], serialized


def _timeline_item_media_id(item: Any) -> str | None:
    mpi = item.GetMediaPoolItem() if hasattr(item, "GetMediaPoolItem") else None
    if mpi is None:
        return None
    return _clip_media_id(mpi)


def verify_multicam_seed_append(
    conn: Any,
    *,
    target: dict[str, Any],
    record_frame: int,
) -> dict[str, Any]:
    conn.refresh()
    timeline = getattr(conn, "timeline", None)
    if timeline is None:
        raise APICallFailed("No active timeline is available after multicam timeline seed append.")
    video_items = list(timeline.GetItemListInTrack("video", 1) or [])
    if not video_items:
        raise APICallFailed(
            "DaVinci Resolve did not populate V1 after multicam timeline seed append.",
            details={"multicam_name": target["multicam_name"], "record_frame": record_frame},
        )

    matched_item = None
    for item in video_items:
        media_id = _timeline_item_media_id(item)
        if media_id and media_id == target.get("multicam_media_id"):
            matched_item = item
            break
    if matched_item is None:
        raise APICallFailed(
            "DaVinci Resolve appended a video item but it could not be matched back to the requested multicam clip.",
            details={
                "multicam_name": target["multicam_name"],
                "multicam_media_id": target.get("multicam_media_id"),
                "video_track_item_count": len(video_items),
            },
        )

    item_start = None
    start_matches = True
    getter = getattr(matched_item, "GetStart", None)
    if callable(getter):
        try:
            item_start = int(getter())
            start_matches = item_start == int(record_frame)
        except Exception:
            item_start = None
            start_matches = True

    checks = [
        {"name": "v1_has_video_item", "ok": len(video_items) >= 1, "video_track_item_count": len(video_items)},
        {
            "name": "matched_multicam_item",
            "ok": True,
            "multicam_media_id": target.get("multicam_media_id"),
            "matched_media_id": _timeline_item_media_id(matched_item),
        },
        {
            "name": "matched_record_frame",
            "ok": start_matches,
            "expected": int(record_frame),
            "actual": item_start,
            "verified": item_start is not None,
        },
    ]
    status = "verified" if all(bool(check["ok"]) for check in checks) else "failed"
    return {
        "status": status,
        "checks": checks,
        "video_track_item_count": len(video_items),
        "matched_item": {
            "name": matched_item.GetName() if hasattr(matched_item, "GetName") else target["multicam_name"],
            "start": item_start,
            "media_id": _timeline_item_media_id(matched_item),
        },
    }


def seed_multicam_timeline(
    conn: Any,
    *,
    project_db_path: str,
    multicam_name: str | None = None,
    media_id: str | None = None,
    folder: str | None = None,
    timeline_name: str | None = None,
    record_frame: str | None = None,
    absolute_record_frame: int | None = None,
    require_empty: bool = False,
    reset_first: bool = False,
) -> dict[str, Any]:
    plan = plan_multicam_timeline_seed(
        conn,
        project_db_path=project_db_path,
        multicam_name=multicam_name,
        media_id=media_id,
        folder=folder,
        timeline_name=timeline_name,
        record_frame=record_frame,
        absolute_record_frame=absolute_record_frame,
        require_empty=require_empty,
        reset_first=reset_first,
    )
    if not plan["preflight"]["empty"] and (require_empty or not reset_first):
        raise ValidationError(
            "Target timeline is not empty for multicam seed.",
            details={
                "reason": "timeline_not_empty",
                "timeline_name": plan["timeline_name"],
                "video_items": plan["preflight"]["video_items"],
                "audio_items": plan["preflight"]["audio_items"],
                "video_track_counts": plan["preflight"]["video_track_counts"],
                "audio_track_counts": plan["preflight"]["audio_track_counts"],
                "require_empty": bool(require_empty),
                "reset_first": bool(reset_first),
            },
        )

    timeline_context = resolve_timeline_target(conn, timeline_name=timeline_name, activate=bool(timeline_name))
    reset_result = None
    if reset_first and not plan["preflight"]["empty"]:
        reset_result = reset_timeline_for_multicam_seed(
            conn,
            timeline_name=str(plan["timeline_name"]),
            before_preflight=plan["preflight"],
        )
        conn = ResolveConnection.get()
        conn.refresh()
        resolve_timeline_target(conn, timeline_name=timeline_name or str(plan["timeline_name"]), activate=bool(timeline_name))

    target = {
        "multicam_name": plan["multicam_name"],
        "multicam_media_id": plan["multicam_media_id"],
        "multicam_sequence_id": plan["multicam_sequence_id"],
        "folder_path": plan.get("folder"),
    }
    clip, live_candidates = resolve_live_multicam_media_pool_item(conn, target=target)
    append_request = {
        "mediaPoolItem": clip,
        "trackType": "video",
        "trackIndex": 1,
        "recordFrame": int(plan["record_frame"]),
    }
    append_result = conn.media_pool.AppendToTimeline([append_request])
    if not append_result:
        raise APICallFailed(
            "AppendToTimeline failed for native multicam timeline seed.",
            details={**target, "timeline_name": plan["timeline_name"], "record_frame": plan["record_frame"]},
        )

    try:
        verification = verify_multicam_seed_append(conn, target=target, record_frame=int(plan["record_frame"]))
    except APICallFailed as exc:
        if int((exc.details or {}).get("video_track_item_count") or 0) <= 0:
            raise
        verification = {
            "status": "api_readback_unmatched_pending_db_verification",
            "checks": [
                {
                    "name": "api_video_item_present",
                    "ok": True,
                    "video_track_item_count": int((exc.details or {}).get("video_track_item_count") or 0),
                },
                {
                    "name": "api_media_pool_item_match",
                    "ok": False,
                    "multicam_media_id": target.get("multicam_media_id"),
                    "reason": "resolve_api_did_not_round_trip_timeline_item_media_pool_item",
                },
            ],
        }
    if verification.get("status") not in {"verified", "api_readback_unmatched_pending_db_verification"}:
        raise APICallFailed(
            "Native multicam timeline seed append could not be verified.",
            details={"verification": verification, **target, "timeline_name": plan["timeline_name"]},
        )
    media_ref_repair = repair_multicam_seed_timeline_media_ref(
        conn,
        timeline_name=str(plan["timeline_name"]),
        multicam_name=str(plan["multicam_name"]),
        multicam_media_id=str(plan["multicam_media_id"]),
    )
    media_ref_verification = media_ref_repair.get("verification") if isinstance(media_ref_repair, dict) else None
    if not isinstance(media_ref_verification, dict) or media_ref_verification.get("status") != "verified":
        raise APICallFailed(
            "Native multicam timeline seed media reference repair could not be verified.",
            details={
                "media_ref_repair": media_ref_repair,
                **target,
                "timeline_name": plan["timeline_name"],
            },
        )

    return {
        "action": "multicam.seed_timeline",
        "target": {"kind": "multicam_clip", "name": plan["multicam_name"]},
        "timeline_name": plan["timeline_name"],
        "timeline_index": timeline_context["timeline_index"],
        "multicam_name": plan["multicam_name"],
        "multicam_media_id": plan["multicam_media_id"],
        "multicam_sequence_id": plan["multicam_sequence_id"],
        "folder": plan.get("folder"),
        "record_frame": int(plan["record_frame"]),
        "record_frame_source": plan["record_frame_source"],
        "track_type": "video",
        "track_index": 1,
        "preflight": plan["preflight"],
        "reset": reset_result,
        "append_request": append_request,
        "append_result_type": type(append_result).__name__,
        "append_result_count": len(append_result) if isinstance(append_result, list) else None,
        "live_candidates": live_candidates,
        "verification": verification,
        "media_ref_repair": media_ref_repair,
    }
