"""Preflight and cleanup helpers for stale native multicam target names."""

from __future__ import annotations

import shutil
import sqlite3
from typing import Any


def _quote_identifier(value: str) -> str:
    return '"' + str(value).replace('"', '""') + '"'


def _table_exists(cursor: sqlite3.Cursor, table_name: str) -> bool:
    row = cursor.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def _table_columns(cursor: sqlite3.Cursor, table_name: str) -> set[str]:
    if not _table_exists(cursor, table_name):
        return set()
    return {str(row[1]) for row in cursor.execute(f"PRAGMA table_info({_quote_identifier(table_name)})").fetchall()}


def _fetch_folder_paths(cursor: sqlite3.Cursor) -> dict[str, str]:
    if not _table_exists(cursor, "Sm2MpFolder"):
        return {}
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
        str(row["Sm2MpFolder_id"]): {
            "name": str(row["Name"] or ""),
            "parent": str(row["MpFolder"] or row["Sm2MpFolder_Owner_id"] or "") or None,
        }
        for row in rows
        if row["Sm2MpFolder_id"]
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
        parent_id = folder["parent"]
        name = folder["name"]
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


def _media_rows(cursor: sqlite3.Cursor, *, name: str, db_type: str) -> list[dict[str, Any]]:
    if not _table_exists(cursor, "Sm2MpMedia"):
        return []
    columns = _table_columns(cursor, "Sm2MpMedia")
    select_columns = [
        "Sm2MpMedia_id",
        "DbType",
        "Name",
        "Sm2MpFolder_id",
        "MpFolder",
        "Sequence",
    ]
    if "UniqueMediaPoolItemId" in columns:
        select_columns.append("UniqueMediaPoolItemId")
    rows = cursor.execute(
        f"""
        SELECT {", ".join(_quote_identifier(column) for column in select_columns)}
        FROM {_quote_identifier("Sm2MpMedia")}
        WHERE Name = ? AND DbType = ?
        ORDER BY LOWER(Name), Sm2MpMedia_id
        """,
        (name, db_type),
    ).fetchall()
    folder_paths = _fetch_folder_paths(cursor)
    targets: list[dict[str, Any]] = []
    for row in rows:
        folder_id = str(row["Sm2MpFolder_id"] or row["MpFolder"] or "") or None
        targets.append(
            {
                "kind": "multicam" if db_type == "Sm2MpMulticamClip" else "timeline",
                "name": str(row["Name"] or ""),
                "media_id": str(row["Sm2MpMedia_id"] or ""),
                "db_type": str(row["DbType"] or ""),
                "folder_id": folder_id,
                "folder_path": folder_paths.get(folder_id or "", "") or None,
                "sequence_id": str(row["Sequence"] or "") or None,
                "unique_media_pool_item_id": (
                    str(row["UniqueMediaPoolItemId"] or "") if "UniqueMediaPoolItemId" in row.keys() else None
                )
                or None,
                "source": "Sm2MpMedia",
            }
        )
    return targets


def _timeline_rows(cursor: sqlite3.Cursor, *, name: str) -> list[dict[str, Any]]:
    if not _table_exists(cursor, "Sm2Timeline"):
        return []
    columns = _table_columns(cursor, "Sm2Timeline")
    select_columns = ["Sm2Timeline_id", "DbType", "Name"]
    for column in ("Sequence", "Sm2MpMedia_id"):
        if column in columns:
            select_columns.append(column)
    rows = cursor.execute(
        f"""
        SELECT {", ".join(_quote_identifier(column) for column in select_columns)}
        FROM Sm2Timeline
        WHERE Name = ?
        ORDER BY LOWER(Name), Sm2Timeline_id
        """,
        (name,),
    ).fetchall()
    targets: list[dict[str, Any]] = []
    for row in rows:
        targets.append(
            {
                "kind": "timeline",
                "name": str(row["Name"] or ""),
                "timeline_id": str(row["Sm2Timeline_id"] or ""),
                "db_type": str(row["DbType"] or ""),
                "sequence_id": str(row["Sequence"] or "") if "Sequence" in row.keys() else None,
                "media_id": str(row["Sm2MpMedia_id"] or "") if "Sm2MpMedia_id" in row.keys() else None,
                "source": "Sm2Timeline",
            }
        )
    return targets


def _normalize_live_candidates(candidates: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for candidate in list(candidates or []):
        if not isinstance(candidate, dict):
            continue
        normalized.append(
            {
                "name": str(candidate.get("name") or candidate.get("multicam_name") or ""),
                "folder": str(candidate.get("folder") or candidate.get("folder_path") or "") or None,
                "media_id": str(candidate.get("media_id") or candidate.get("multicam_media_id") or "") or None,
                "unique_media_pool_item_id": str(candidate.get("unique_media_pool_item_id") or "") or None,
            }
        )
    return normalized


def _live_multicam_identifier_set(live_multicams: list[dict[str, Any]]) -> set[str]:
    identifiers: set[str] = set()
    for item in live_multicams:
        for key in ("media_id", "unique_media_pool_item_id"):
            value = str(item.get(key) or "").strip()
            if value:
                identifiers.add(value)
    return identifiers


def _db_multicam_identifier_set(row: dict[str, Any]) -> set[str]:
    identifiers: set[str] = set()
    for key in ("media_id", "unique_media_pool_item_id"):
        value = str(row.get(key) or "").strip()
        if value:
            identifiers.add(value)
    return identifiers


def inspect_multicam_create_preflight(
    project_db_path: str,
    *,
    multicam_name: str,
    timeline_name: str,
    live_multicam_candidates: list[dict[str, Any]] | None = None,
    live_timeline_names: list[str] | set[str] | None = None,
) -> dict[str, Any]:
    """Compare target names in Project.db against live DaVinci Resolve API exposure."""
    normalized_multicam_name = str(multicam_name or "").strip()
    normalized_timeline_name = str(timeline_name or "").strip()
    live_multicams = _normalize_live_candidates(live_multicam_candidates)
    live_multicam_ids = _live_multicam_identifier_set(live_multicams)
    live_timelines = {str(name) for name in (live_timeline_names or []) if str(name)}

    connection = sqlite3.connect(f"file:{project_db_path}?mode=ro", uri=True, timeout=5.0)
    connection.row_factory = sqlite3.Row
    try:
        cursor = connection.cursor()
        db_multicams = _media_rows(cursor, name=normalized_multicam_name, db_type="Sm2MpMulticamClip")
        db_timeline_media = _media_rows(cursor, name=normalized_timeline_name, db_type="Sm2MpTimelineClip")
        db_timeline_rows = _timeline_rows(cursor, name=normalized_timeline_name)
    finally:
        connection.close()

    if not live_multicams:
        db_only_multicams = db_multicams
        visible_multicam_conflicts: list[dict[str, Any]] = []
    elif live_multicam_ids:
        db_only_multicams = [row for row in db_multicams if not (_db_multicam_identifier_set(row) & live_multicam_ids)]
        visible_multicam_conflicts = [
            row for row in db_multicams if _db_multicam_identifier_set(row) & live_multicam_ids
        ] or live_multicams
    else:
        db_only_multicams = []
        visible_multicam_conflicts = db_multicams or live_multicams

    timeline_visible = normalized_timeline_name in live_timelines
    db_timeline_targets = db_timeline_media + [
        row
        for row in db_timeline_rows
        if row.get("media_id") not in {item.get("media_id") for item in db_timeline_media if item.get("media_id")}
        and row.get("timeline_id") not in {item.get("timeline_id") for item in db_timeline_media if item.get("timeline_id")}
    ]
    db_only_timelines = [] if timeline_visible else db_timeline_targets
    visible_timeline_conflicts = db_timeline_targets if timeline_visible else []
    if timeline_visible and not visible_timeline_conflicts:
        visible_timeline_conflicts = [{"kind": "timeline", "name": normalized_timeline_name, "source": "DaVinci Resolve API"}]

    stale = {
        "multicams": db_only_multicams,
        "timelines": db_only_timelines,
    }
    visible_conflicts = {
        "multicams": visible_multicam_conflicts,
        "timelines": visible_timeline_conflicts,
    }
    has_stale = bool(db_only_multicams or db_only_timelines)
    has_visible = bool(visible_multicam_conflicts or visible_timeline_conflicts)
    status = "clear"
    if has_visible:
        status = "target_exists"
    elif has_stale:
        status = "stale_targets"

    return {
        "status": status,
        "project_db_path": project_db_path,
        "multicam_name": normalized_multicam_name,
        "timeline_name": normalized_timeline_name,
        "db": {
            "multicams": db_multicams,
            "timelines": db_timeline_targets,
        },
        "live": {
            "multicam_candidates": live_multicams,
            "timeline_names": sorted(live_timelines),
        },
        "stale": stale,
        "visible_conflicts": visible_conflicts,
        "cleanup_supported": has_stale and not has_visible,
        "cleanup_required": has_stale,
    }


def _fetch_values(
    cursor: sqlite3.Cursor,
    table_name: str,
    column_name: str,
    *,
    where_column: str,
    values: set[str],
    extra_where: str = "",
) -> set[str]:
    if not values or not _table_exists(cursor, table_name):
        return set()
    columns = _table_columns(cursor, table_name)
    if column_name not in columns or where_column not in columns:
        return set()
    placeholders = ", ".join("?" for _ in values)
    rows = cursor.execute(
        f"""
        SELECT {_quote_identifier(column_name)}
        FROM {_quote_identifier(table_name)}
        WHERE {_quote_identifier(where_column)} IN ({placeholders})
        {extra_where}
        """,
        tuple(values),
    ).fetchall()
    return {str(row[0]) for row in rows if row and row[0]}


def _delete_in(cursor: sqlite3.Cursor, table_name: str, column_name: str, values: set[str]) -> int:
    if not values or not _table_exists(cursor, table_name):
        return 0
    if column_name not in _table_columns(cursor, table_name):
        return 0
    placeholders = ", ".join("?" for _ in values)
    return cursor.execute(
        f"DELETE FROM {_quote_identifier(table_name)} WHERE {_quote_identifier(column_name)} IN ({placeholders})",
        tuple(values),
    ).rowcount


def _collect_graph_ids(cursor: sqlite3.Cursor, *, media_ids: set[str], timeline_ids: set[str]) -> dict[str, set[str]]:
    sequence_ids = set()
    sequence_ids.update(_fetch_values(cursor, "Sm2MpMedia", "Sequence", where_column="Sm2MpMedia_id", values=media_ids))
    sequence_ids.update(_fetch_values(cursor, "Sm2Sequence", "Sm2Sequence_id", where_column="Sm2MpMedia_id", values=media_ids))
    sequence_ids.update(_fetch_values(cursor, "Sm2Sequence", "Sm2Sequence_id", where_column="Parent", values=media_ids))
    sequence_ids.update(_fetch_values(cursor, "Sm2Timeline", "Sequence", where_column="Sm2Timeline_id", values=timeline_ids))
    sequence_ids.update(_fetch_values(cursor, "Sm2Timeline", "Sequence", where_column="Sm2MpMedia_id", values=media_ids))

    container_ids = _fetch_values(
        cursor,
        "Sm2SequenceContainer",
        "Sm2SequenceContainer_id",
        where_column="Sm2Sequence_id",
        values=sequence_ids,
    )
    track_ids = _fetch_values(cursor, "Sm2TiTrack", "Sm2TiTrack_id", where_column="Sequence", values=sequence_ids)
    track_ids.update(
        _fetch_values(
            cursor,
            "Sm2TiTrack",
            "Sm2TiTrack_id",
            where_column="Sm2SequenceContainer_id",
            values=container_ids,
        )
    )
    track_ids.update(
        _fetch_values(
            cursor,
            "Sm2SequenceContainer_Sm2TiTrack",
            "DbAssociate",
            where_column="DbOwner",
            values=container_ids,
        )
    )
    item_ids = _fetch_values(cursor, "Sm2TiItem", "Sm2TiItem_id", where_column="Sm2TiTrack_id", values=track_ids)
    item_ids.update(_fetch_values(cursor, "Sm2TiItem_Sm2TiTrack", "DbAssociate", where_column="DbOwner", values=track_ids))
    return {
        "media_ids": media_ids,
        "timeline_ids": timeline_ids,
        "sequence_ids": sequence_ids,
        "container_ids": container_ids,
        "track_ids": track_ids,
        "item_ids": item_ids,
    }


def _delete_optional_version_rows(cursor: sqlite3.Cursor, *, graph: dict[str, set[str]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    version_table_ids: set[str] = set()
    owner_sets = {
        "Sm2MpMedia_id": graph["media_ids"],
        "Sm2Sequence_id": graph["sequence_ids"],
        "Sm2TiItem_id": graph["item_ids"],
    }
    for column_name, values in owner_sets.items():
        version_table_ids.update(
            _fetch_values(
                cursor,
                "ListMgt::LmVersionTable",
                "ListMgt::LmVersionTable_id",
                where_column=column_name,
                values=values,
            )
        )
    version_ids = _fetch_values(
        cursor,
        "ListMgt::LmVersion",
        "ListMgt::LmVersion_id",
        where_column="ListMgt::LmVersionTable_id",
        values=version_table_ids,
    )
    version_ids.update(
        _fetch_values(
            cursor,
            "ListMgt::LmVersion_ListMgt::LmVersionTable",
            "DbAssociate",
            where_column="DbOwner",
            values=version_table_ids,
        )
    )
    counts["ListMgt::LmVersion_ListMgt::LmVersionTable.owner"] = _delete_in(
        cursor,
        "ListMgt::LmVersion_ListMgt::LmVersionTable",
        "DbOwner",
        version_table_ids,
    )
    counts["ListMgt::LmVersion_ListMgt::LmVersionTable.associate"] = _delete_in(
        cursor,
        "ListMgt::LmVersion_ListMgt::LmVersionTable",
        "DbAssociate",
        version_ids,
    )
    counts["ListMgt::LmVersion"] = _delete_in(cursor, "ListMgt::LmVersion", "ListMgt::LmVersion_id", version_ids)
    counts["ListMgt::LmVersionTable"] = _delete_in(
        cursor,
        "ListMgt::LmVersionTable",
        "ListMgt::LmVersionTable_id",
        version_table_ids,
    )
    return counts


def _delete_optional_blob_rows(cursor: sqlite3.Cursor, *, graph: dict[str, set[str]]) -> dict[str, int]:
    blob_owners = set().union(*graph.values())
    blob_ids = _fetch_values(cursor, "BtLockableBlob", "BtLockableBlob_id", where_column="BlobOwner", values=blob_owners)
    blob_map_ids = _fetch_values(cursor, "BtLockableBlob", "BtLockableBlobMap_id", where_column="BlobOwner", values=blob_owners)
    return {
        "BtLockableBlob": _delete_in(cursor, "BtLockableBlob", "BtLockableBlob_id", blob_ids),
        "BtLockableBlobMap": _delete_in(cursor, "BtLockableBlobMap", "BtLockableBlobMap_id", blob_map_ids),
    }


def cleanup_stale_multicam_create_targets(
    project_db_path: str,
    *,
    preflight: dict[str, Any],
    backup_path: str | None = None,
) -> dict[str, Any]:
    """Remove preflight-confirmed DB-only target rows from a closed Disk Project.db."""
    stale = preflight.get("stale") if isinstance(preflight, dict) else {}
    multicams = list((stale or {}).get("multicams") or [])
    timelines = list((stale or {}).get("timelines") or [])
    targets = multicams + timelines
    if not targets:
        return {
            "action": "multicam.stale_target_cleanup",
            "changed": False,
            "project_db_path": project_db_path,
            "removed_targets": [],
            "row_counts": {},
            "backup_path": None,
        }

    resolved_backup_path = backup_path or f"{project_db_path}.stale-targets.bak"
    shutil.copy2(project_db_path, resolved_backup_path)

    connection = sqlite3.connect(project_db_path, timeout=5.0)
    connection.row_factory = sqlite3.Row
    row_counts: dict[str, int] = {}
    try:
        cursor = connection.cursor()
        cursor.execute("BEGIN")
        media_ids = {str(target.get("media_id")) for target in targets if target.get("media_id")}
        timeline_ids = {str(target.get("timeline_id")) for target in targets if target.get("timeline_id")}
        graph = _collect_graph_ids(cursor, media_ids=media_ids, timeline_ids=timeline_ids)

        row_counts.update(_delete_optional_version_rows(cursor, graph=graph))
        row_counts.update(_delete_optional_blob_rows(cursor, graph=graph))
        row_counts["Sm2MpFolder_Sm2MpMedia"] = _delete_in(
            cursor,
            "Sm2MpFolder_Sm2MpMedia",
            "DbAssociate",
            graph["media_ids"],
        )
        row_counts["Sm2SequenceContainer_Sm2TiTrack.owner"] = _delete_in(
            cursor,
            "Sm2SequenceContainer_Sm2TiTrack",
            "DbOwner",
            graph["container_ids"],
        )
        row_counts["Sm2SequenceContainer_Sm2TiTrack.associate"] = _delete_in(
            cursor,
            "Sm2SequenceContainer_Sm2TiTrack",
            "DbAssociate",
            graph["track_ids"],
        )
        row_counts["Sm2Sequence_Sm2TiTrack.owner"] = _delete_in(
            cursor,
            "Sm2Sequence_Sm2TiTrack",
            "DbOwner",
            graph["sequence_ids"],
        )
        row_counts["Sm2Sequence_Sm2TiTrack.associate"] = _delete_in(
            cursor,
            "Sm2Sequence_Sm2TiTrack",
            "DbAssociate",
            graph["track_ids"],
        )
        row_counts["Sm2TiItem_Sm2TiTrack.owner"] = _delete_in(
            cursor,
            "Sm2TiItem_Sm2TiTrack",
            "DbOwner",
            graph["track_ids"],
        )
        row_counts["Sm2TiItem_Sm2TiTrack.associate"] = _delete_in(
            cursor,
            "Sm2TiItem_Sm2TiTrack",
            "DbAssociate",
            graph["item_ids"],
        )
        row_counts["Sm2TiItem_Sm2TiItem.owner"] = _delete_in(
            cursor,
            "Sm2TiItem_Sm2TiItem",
            "DbOwner",
            graph["item_ids"],
        )
        row_counts["Sm2TiItem_Sm2TiItem.associate"] = _delete_in(
            cursor,
            "Sm2TiItem_Sm2TiItem",
            "DbAssociate",
            graph["item_ids"],
        )
        row_counts["Sm2TiTrack_Sm2TiTrack.owner"] = _delete_in(
            cursor,
            "Sm2TiTrack_Sm2TiTrack",
            "DbOwner",
            graph["track_ids"],
        )
        row_counts["Sm2TiTrack_Sm2TiTrack.associate"] = _delete_in(
            cursor,
            "Sm2TiTrack_Sm2TiTrack",
            "DbAssociate",
            graph["track_ids"],
        )
        row_counts["Sm2TiCompositionTable.item"] = _delete_in(
            cursor,
            "Sm2TiCompositionTable",
            "Sm2TiItem_id",
            graph["item_ids"],
        )
        row_counts["Sm2TiCompositionTable.media"] = _delete_in(
            cursor,
            "Sm2TiCompositionTable",
            "Sm2MpMedia_id",
            graph["media_ids"],
        )
        row_counts["Sm2TiItem"] = _delete_in(cursor, "Sm2TiItem", "Sm2TiItem_id", graph["item_ids"])
        row_counts["Sm2TiTrack"] = _delete_in(cursor, "Sm2TiTrack", "Sm2TiTrack_id", graph["track_ids"])
        row_counts["Sm2SequenceContainer"] = _delete_in(
            cursor,
            "Sm2SequenceContainer",
            "Sm2SequenceContainer_id",
            graph["container_ids"],
        )
        row_counts["Sm2Timeline.timeline"] = _delete_in(cursor, "Sm2Timeline", "Sm2Timeline_id", graph["timeline_ids"])
        row_counts["Sm2Timeline.media"] = _delete_in(cursor, "Sm2Timeline", "Sm2MpMedia_id", graph["media_ids"])
        row_counts["Sm2Sequence"] = _delete_in(cursor, "Sm2Sequence", "Sm2Sequence_id", graph["sequence_ids"])
        row_counts["Sm2MpMedia"] = _delete_in(cursor, "Sm2MpMedia", "Sm2MpMedia_id", graph["media_ids"])
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

    return {
        "action": "multicam.stale_target_cleanup",
        "changed": any(count > 0 for count in row_counts.values()),
        "project_db_path": project_db_path,
        "backup_path": resolved_backup_path,
        "removed_targets": targets,
        "row_counts": row_counts,
    }
