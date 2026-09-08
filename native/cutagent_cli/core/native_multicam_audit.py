"""Internal graph snapshot and diff helpers for native multicam DB forensics."""

from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from typing import Any

_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)

_TIMESTAMP_FIELDS = {
    "DbSavedTime",
    "LastChangedTime",
    "LastRenderedTime",
    "ModTimeInSecs",
    "CreateTimeInSecs",
}

_BLOB_PRESENCE_FIELDS = {
    "FieldsBlob",
    "PinsBA",
    "ImportExportMetadataBA",
    "RenderCacheBA",
    "AuxRenderCacheBA",
    "VideoMetadata",
    "VirtualAudioTracksBA",
    "PreConformMediaExtents",
    "MediaFrameRate",
    "MediaTimemapBA",
    "VirtualAudioTrackBA",
    "CompositionBA",
}

_SNAPSHOT_TABLES = (
    "Sm2MpMedia",
    "Sm2Sequence",
    "Sm2SequenceContainer",
    "Sm2TiTrack",
    "Sm2TiItem",
    "ListMgt::LmVersionTable",
    "ListMgt::LmVersion",
    "BtLockableBlob",
    "BtLockableBlobMap",
    "Sm2TiCompositionTable",
)

_RELATION_TABLES = (
    "Sm2MpFolder_Sm2MpMedia",
    "Sm2SequenceContainer_Sm2TiTrack",
    "Sm2Sequence_Sm2TiTrack",
    "Sm2TiItem_Sm2TiTrack",
    "Sm2TiItem_Sm2TiItem",
    "Sm2TiTrack_Sm2TiTrack",
    "ListMgt::LmVersion_ListMgt::LmVersionTable",
)

_TABLE_VALUE_FIELDS = {
    "Sm2MpMedia": [
        "AudioSource",
        "CurPlayheadPosition",
        "SlateTC",
        "FieldsBlob",
        "VideoMetadata",
        "VirtualAudioTracksBA",
        "DbSavedTime",
    ],
    "Sm2Sequence": [
        "FrameRate",
        "Resolution",
        "MediaExtents",
        "RenderCacheBA",
        "AuxRenderCacheBA",
        "FieldsBlob",
        "DbSavedTime",
    ],
    "Sm2SequenceContainer": [
        "FieldsBlob",
        "DbSavedTime",
    ],
    "Sm2TiTrack": [
        "Type",
        "SubType",
        "UserDefinedName",
        "FieldsBlob",
    ],
    "Sm2TiItem": [
        "DbType",
        "Start",
        "Duration",
        "In",
        "MediaStartTime",
        "MediaFilePath",
        "MediaTimemapBA",
        "MediaFrameRate",
        "VirtualAudioTrackBA",
        "PreConformMediaExtents",
        "FieldsBlob",
        "MediaTrackIdx",
        "Position",
    ],
}

_RELATION_VALUE_FIELDS = {
    "Sm2MpFolder_Sm2MpMedia": ["DbPropertyName"],
    "Sm2SequenceContainer_Sm2TiTrack": ["DbPropertyName", "DbIndex"],
    "Sm2TiItem_Sm2TiTrack": ["DbPropertyName", "DbIndex"],
}


@dataclass(frozen=True)
class AuditReferenceConfig:
    reference_multicam_name: str = "Native Reference Multicam"
    secondary_timeline_name: str = "Podcast Multicam"


def _row_to_dict(cursor: sqlite3.Cursor, row: tuple[Any, ...]) -> dict[str, Any]:
    return {cursor.description[index][0]: value for index, value in enumerate(row)}


def _encode_value(value: Any) -> Any:
    if isinstance(value, bytes):
        return base64.b64encode(value).decode("ascii")
    return value


def _table_exists(cursor: sqlite3.Cursor, table_name: str) -> bool:
    row = cursor.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (table_name,),
    ).fetchone()
    return row is not None


def _fetch_one(cursor: sqlite3.Cursor, query: str, params: tuple[Any, ...]) -> dict[str, Any] | None:
    row = cursor.execute(query, params).fetchone()
    if row is None:
        return None
    return {key: _encode_value(value) for key, value in _row_to_dict(cursor, row).items()}


def _fetch_all(cursor: sqlite3.Cursor, query: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
    rows = cursor.execute(query, params).fetchall()
    return [{key: _encode_value(value) for key, value in _row_to_dict(cursor, row).items()} for row in rows]


def _fetch_optional_all(
    cursor: sqlite3.Cursor,
    table_name: str,
    query: str,
    params: tuple[Any, ...],
) -> list[dict[str, Any]]:
    if not _table_exists(cursor, table_name):
        return []
    return _fetch_all(cursor, query, params)


def _fetch_optional_one(
    cursor: sqlite3.Cursor,
    table_name: str,
    query: str,
    params: tuple[Any, ...],
) -> dict[str, Any] | None:
    if not _table_exists(cursor, table_name):
        return None
    return _fetch_one(cursor, query, params)


def find_named_media(
    project_db_path: str | Path,
    *,
    name: str,
) -> dict[str, Any] | None:
    connection = sqlite3.connect(str(project_db_path))
    try:
        cursor = connection.cursor()
        return _fetch_optional_one(
            cursor,
            "Sm2MpMedia",
            """
            SELECT rowid, Sm2MpMedia_id, Name, Sequence, Sm2MpFolder_id
            FROM Sm2MpMedia
            WHERE Name = ?
            ORDER BY rowid DESC
            LIMIT 1
            """,
            (name,),
        )
    finally:
        connection.close()


def find_named_timeline(
    project_db_path: str | Path,
    *,
    name: str,
) -> dict[str, Any] | None:
    connection = sqlite3.connect(str(project_db_path))
    try:
        cursor = connection.cursor()
        return _fetch_optional_one(
            cursor,
            "Sm2Timeline",
            """
            SELECT rowid, Sm2Timeline_id, Name, Sequence, Sm2MpMedia_id
            FROM Sm2Timeline
            WHERE Name = ?
            ORDER BY rowid DESC
            LIMIT 1
            """,
            (name,),
        )
    finally:
        connection.close()


def snapshot_multicam_graph(
    project_db_path: str | Path,
    *,
    media_id: str | None = None,
    sequence_id: str | None = None,
) -> dict[str, Any]:
    if not media_id and not sequence_id:
        raise ValueError("snapshot_multicam_graph requires media_id or sequence_id")

    connection = sqlite3.connect(str(project_db_path))
    try:
        cursor = connection.cursor()

        media_row = None
        if media_id:
            media_row = _fetch_one(
                cursor,
                "SELECT * FROM Sm2MpMedia WHERE Sm2MpMedia_id = ?",
                (media_id,),
            )
            if media_row is None:
                raise ValueError(f"Sm2MpMedia '{media_id}' was not found.")

        resolved_sequence_id = sequence_id or (str(media_row.get("Sequence") or "") if media_row else "")
        if not resolved_sequence_id:
            raise ValueError("Could not resolve sequence_id for graph snapshot.")

        sequence_row = _fetch_one(
            cursor,
            "SELECT * FROM Sm2Sequence WHERE Sm2Sequence_id = ?",
            (resolved_sequence_id,),
        )
        if sequence_row is None:
            raise ValueError(f"Sm2Sequence '{resolved_sequence_id}' was not found.")

        if media_row is None and sequence_row.get("Sm2MpMedia_id"):
            resolved_media_id = str(sequence_row["Sm2MpMedia_id"])
            media_row = _fetch_one(
                cursor,
                "SELECT * FROM Sm2MpMedia WHERE Sm2MpMedia_id = ?",
                (resolved_media_id,),
            )
        else:
            resolved_media_id = str(media_row.get("Sm2MpMedia_id") or "") if media_row else ""

        media_folder_id = None
        if media_row:
            media_folder_id = str(media_row.get("Sm2MpFolder_id") or media_row.get("MpFolder") or "") or None

        container_row = _fetch_optional_one(
            cursor,
            "Sm2SequenceContainer",
            "SELECT * FROM Sm2SequenceContainer WHERE Sm2Sequence_id = ?",
            (resolved_sequence_id,),
        )

        track_rows = _fetch_all(
            cursor,
            """
            SELECT *
            FROM Sm2TiTrack
            WHERE Sequence = ?
            ORDER BY Type, rowid
            """,
            (resolved_sequence_id,),
        )
        track_ids = [str(row["Sm2TiTrack_id"]) for row in track_rows]

        item_rows = _fetch_all(
            cursor,
            """
            SELECT i.*
            FROM Sm2TiItem i
            JOIN Sm2TiTrack t ON t.Sm2TiTrack_id = i.Sm2TiTrack_id
            WHERE t.Sequence = ?
            ORDER BY i.DbType, i.rowid
            """,
            (resolved_sequence_id,),
        )
        item_ids = [str(row["Sm2TiItem_id"]) for row in item_rows]

        version_table_ids: set[str] = set()
        for row in (media_row, sequence_row):
            if row and row.get("pLmVerTable"):
                version_table_ids.add(str(row["pLmVerTable"]))
            if row and row.get("pAuxLmVerTable"):
                version_table_ids.add(str(row["pAuxLmVerTable"]))
        for row in item_rows:
            if row.get("pLmVerTable"):
                version_table_ids.add(str(row["pLmVerTable"]))
            if row.get("pAuxLmVerTable"):
                version_table_ids.add(str(row["pAuxLmVerTable"]))

        version_tables: list[dict[str, Any]] = []
        if _table_exists(cursor, "ListMgt::LmVersionTable"):
            where_clauses = ["Sm2Sequence_id = ?"]
            params: list[Any] = [resolved_sequence_id]
            if resolved_media_id:
                where_clauses.append("Sm2MpMedia_id = ?")
                params.append(resolved_media_id)
            if item_ids:
                where_clauses.append(
                    f"Sm2TiItem_id IN ({', '.join('?' for _ in item_ids)})"
                )
                params.extend(item_ids)
            if version_table_ids:
                where_clauses.append(
                    f'"ListMgt::LmVersionTable_id" IN ({", ".join("?" for _ in version_table_ids)})'
                )
                params.extend(sorted(version_table_ids))
            version_tables = _fetch_all(
                cursor,
                f"""
                SELECT *
                FROM "ListMgt::LmVersionTable"
                WHERE {' OR '.join(where_clauses)}
                ORDER BY rowid
                """,
                tuple(params),
            )
            version_table_ids.update(str(row["ListMgt::LmVersionTable_id"]) for row in version_tables)

        version_rows = []
        if version_table_ids and _table_exists(cursor, "ListMgt::LmVersion"):
            version_rows = _fetch_all(
                cursor,
                """
                SELECT *
                FROM "ListMgt::LmVersion"
                WHERE "ListMgt::LmVersionTable_id" IN ({placeholders})
                ORDER BY rowid
                """.format(placeholders=", ".join("?" for _ in version_table_ids)),
                tuple(sorted(version_table_ids)),
            )

        composition_rows = []
        if _table_exists(cursor, "Sm2TiCompositionTable"):
            where_clauses = []
            params: list[Any] = []
            if resolved_media_id:
                where_clauses.append("Sm2MpMedia_id = ?")
                params.append(resolved_media_id)
            if item_ids:
                where_clauses.append(f"Sm2TiItem_id IN ({', '.join('?' for _ in item_ids)})")
                params.extend(item_ids)
            if where_clauses:
                composition_rows = _fetch_all(
                    cursor,
                    f"""
                    SELECT *
                    FROM Sm2TiCompositionTable
                    WHERE {' OR '.join(where_clauses)}
                    ORDER BY rowid
                    """,
                    tuple(params),
                )

        lockable_blob_rows = []
        lockable_blob_maps = []
        blob_owners = [owner for owner in [resolved_media_id, resolved_sequence_id, *item_ids] if owner]
        if blob_owners and _table_exists(cursor, "BtLockableBlob"):
            lockable_blob_rows = _fetch_all(
                cursor,
                """
                SELECT *
                FROM BtLockableBlob
                WHERE BlobOwner IN ({placeholders})
                ORDER BY rowid
                """.format(placeholders=", ".join("?" for _ in blob_owners)),
                tuple(blob_owners),
            )
            blob_map_ids = sorted(
                {str(row["BtLockableBlobMap_id"]) for row in lockable_blob_rows if row.get("BtLockableBlobMap_id")}
            )
            if blob_map_ids and _table_exists(cursor, "BtLockableBlobMap"):
                lockable_blob_maps = _fetch_all(
                    cursor,
                    """
                    SELECT *
                    FROM BtLockableBlobMap
                    WHERE BtLockableBlobMap_id IN ({placeholders})
                    ORDER BY rowid
                    """.format(placeholders=", ".join("?" for _ in blob_map_ids)),
                    tuple(blob_map_ids),
                )

        relation_rows: dict[str, list[dict[str, Any]]] = {table_name: [] for table_name in _RELATION_TABLES}
        if media_folder_id:
            relation_rows["Sm2MpFolder_Sm2MpMedia"] = _fetch_optional_all(
                cursor,
                "Sm2MpFolder_Sm2MpMedia",
                """
                SELECT *
                FROM Sm2MpFolder_Sm2MpMedia
                WHERE DbOwner = ? AND DbAssociate = ?
                ORDER BY DbIndex
                """,
                (media_folder_id, resolved_media_id),
            )
        if container_row and track_ids:
            relation_rows["Sm2SequenceContainer_Sm2TiTrack"] = _fetch_optional_all(
                cursor,
                "Sm2SequenceContainer_Sm2TiTrack",
                """
                SELECT *
                FROM Sm2SequenceContainer_Sm2TiTrack
                WHERE DbOwner = ?
                ORDER BY DbPropertyName, DbIndex
                """,
                (str(container_row["Sm2SequenceContainer_id"]),),
            )
        relation_rows["Sm2Sequence_Sm2TiTrack"] = _fetch_optional_all(
            cursor,
            "Sm2Sequence_Sm2TiTrack",
            """
            SELECT *
            FROM Sm2Sequence_Sm2TiTrack
            WHERE DbOwner = ?
            ORDER BY DbPropertyName, DbIndex
            """,
            (resolved_sequence_id,),
        )
        if track_ids:
            relation_rows["Sm2TiItem_Sm2TiTrack"] = _fetch_optional_all(
                cursor,
                "Sm2TiItem_Sm2TiTrack",
                """
                SELECT *
                FROM Sm2TiItem_Sm2TiTrack
                WHERE DbOwner IN ({placeholders})
                ORDER BY DbOwner, DbPropertyName, DbIndex
                """.format(placeholders=", ".join("?" for _ in track_ids)),
                tuple(track_ids),
            )
            relation_rows["Sm2TiTrack_Sm2TiTrack"] = _fetch_optional_all(
                cursor,
                "Sm2TiTrack_Sm2TiTrack",
                """
                SELECT *
                FROM Sm2TiTrack_Sm2TiTrack
                WHERE DbOwner IN ({placeholders})
                ORDER BY DbOwner, DbPropertyName, DbIndex
                """.format(placeholders=", ".join("?" for _ in track_ids)),
                tuple(track_ids),
            )
        if item_ids:
            relation_rows["Sm2TiItem_Sm2TiItem"] = _fetch_optional_all(
                cursor,
                "Sm2TiItem_Sm2TiItem",
                """
                SELECT *
                FROM Sm2TiItem_Sm2TiItem
                WHERE DbOwner IN ({placeholders})
                ORDER BY DbOwner, DbPropertyName, DbIndex
                """.format(placeholders=", ".join("?" for _ in item_ids)),
                tuple(item_ids),
            )
        if version_table_ids:
            relation_rows["ListMgt::LmVersion_ListMgt::LmVersionTable"] = _fetch_optional_all(
                cursor,
                "ListMgt::LmVersion_ListMgt::LmVersionTable",
                """
                SELECT *
                FROM "ListMgt::LmVersion_ListMgt::LmVersionTable"
                WHERE DbOwner IN ({placeholders})
                ORDER BY DbOwner, DbPropertyName, DbIndex
                """.format(placeholders=", ".join("?" for _ in version_table_ids)),
                tuple(sorted(version_table_ids)),
            )

        table_rows = {
            "Sm2MpMedia": [media_row] if media_row else [],
            "Sm2Sequence": [sequence_row],
            "Sm2SequenceContainer": [container_row] if container_row else [],
            "Sm2TiTrack": track_rows,
            "Sm2TiItem": item_rows,
            "ListMgt::LmVersionTable": version_tables,
            "ListMgt::LmVersion": version_rows,
            "BtLockableBlob": lockable_blob_rows,
            "BtLockableBlobMap": lockable_blob_maps,
            "Sm2TiCompositionTable": composition_rows,
        }

        return {
            "project_db_path": str(project_db_path),
            "root_media_id": resolved_media_id or None,
            "root_sequence_id": resolved_sequence_id,
            "tables": table_rows,
            "relations": relation_rows,
        }
    finally:
        connection.close()


def normalize_graph_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    uuid_tokens: dict[str, str] = {}

    def normalize_value(field: str, value: Any) -> Any:
        if isinstance(value, str):
            if _UUID_RE.match(value):
                token = uuid_tokens.get(value)
                if token is None:
                    token = f"@uuid{len(uuid_tokens) + 1}"
                    uuid_tokens[value] = token
                return token
            return value
        if isinstance(value, int) and field in _TIMESTAMP_FIELDS:
            return "@ts"
        if value is None:
            return None
        return value

    tables: dict[str, list[dict[str, Any]]] = {}
    for table_name, rows in snapshot.get("tables", {}).items():
        normalized_rows: list[dict[str, Any]] = []
        for row in rows:
            if row is None:
                continue
            normalized_row = {field: normalize_value(field, value) for field, value in row.items()}
            normalized_rows.append(normalized_row)
        tables[table_name] = sorted(normalized_rows, key=lambda row: json.dumps(row, sort_keys=True))

    relations: dict[str, list[dict[str, Any]]] = {}
    for table_name, rows in snapshot.get("relations", {}).items():
        normalized_rows = []
        for row in rows:
            normalized_rows.append({field: normalize_value(field, value) for field, value in row.items()})
        relations[table_name] = sorted(normalized_rows, key=lambda row: json.dumps(row, sort_keys=True))

    return {
        "root_media_id": normalize_value("root_media_id", snapshot.get("root_media_id")),
        "root_sequence_id": normalize_value("root_sequence_id", snapshot.get("root_sequence_id")),
        "tables": tables,
        "relations": relations,
    }


def _decode_base64_blob(value: Any) -> bytes | None:
    if value in (None, "") or not isinstance(value, str):
        return None
    try:
        return base64.b64decode(value)
    except Exception:
        return None


def _summarize_value(field: str, value: Any) -> Any:
    if field in _TIMESTAMP_FIELDS:
        if value in (None, "", 0):
            return value
        return "@ts"

    if field in _BLOB_PRESENCE_FIELDS:
        raw = _decode_base64_blob(value)
        if raw is None:
            return None
        return {
            "length": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
        }

    if field == "MediaFilePath":
        if not isinstance(value, str) or not value:
            return None
        path = Path(value)
        return {
            "absolute": path.is_absolute(),
            "suffix": path.suffix.lower(),
        }

    return value


def _row_key(table_name: str, row: dict[str, Any], index: int) -> str:
    if table_name in {"Sm2MpMedia", "Sm2Sequence", "Sm2SequenceContainer"}:
        return "root"
    if table_name == "Sm2TiTrack":
        return f"{row.get('Type', '?')}:{index}"
    if table_name == "Sm2TiItem":
        return f"{row.get('DbType', '?')}:{index}"
    if table_name == "Sm2MpFolder_Sm2MpMedia":
        return str(index)
    if table_name == "Sm2SequenceContainer_Sm2TiTrack":
        return f"{row.get('DbPropertyName', '?')}:{row.get('DbIndex', index)}"
    if table_name == "Sm2TiItem_Sm2TiTrack":
        return f"{index}"
    return str(index)


def _build_value_entries(snapshot: dict[str, Any]) -> dict[str, dict[str, dict[str, Any]]]:
    entries: dict[str, dict[str, dict[str, Any]]] = {}

    for table_name, fields in _TABLE_VALUE_FIELDS.items():
        rows = snapshot.get("tables", {}).get(table_name, [])
        table_entries: dict[str, dict[str, Any]] = {}
        for index, row in enumerate(rows):
            key = _row_key(table_name, row, index)
            table_entries[key] = {
                field: _summarize_value(field, row.get(field))
                for field in fields
                if field in row
            }
        entries[table_name] = table_entries

    for table_name, fields in _RELATION_VALUE_FIELDS.items():
        rows = snapshot.get("relations", {}).get(table_name, [])
        relation_entries: dict[str, dict[str, Any]] = {}
        for index, row in enumerate(rows):
            key = _row_key(table_name, row, index)
            relation_entries[key] = {
                field: _summarize_value(field, row.get(field))
                for field in fields
                if field in row
            }
        entries[table_name] = relation_entries

    return entries


def _is_meaningful(value: Any) -> bool:
    return value not in (None, "")


def diff_graph_snapshots(candidate: dict[str, Any], reference: dict[str, Any]) -> dict[str, Any]:
    normalized_candidate = normalize_graph_snapshot(candidate)
    normalized_reference = normalize_graph_snapshot(reference)

    table_counts = {
        table_name: {
            "candidate": len(normalized_candidate["tables"].get(table_name, [])),
            "reference": len(normalized_reference["tables"].get(table_name, [])),
        }
        for table_name in _SNAPSHOT_TABLES
    }
    relation_counts = {
        table_name: {
            "candidate": len(normalized_candidate["relations"].get(table_name, [])),
            "reference": len(normalized_reference["relations"].get(table_name, [])),
        }
        for table_name in _RELATION_TABLES
    }

    missing_edges = [
        {
            "relation": relation_name,
            "candidate": counts["candidate"],
            "reference": counts["reference"],
        }
        for relation_name, counts in relation_counts.items()
        if counts["candidate"] < counts["reference"]
    ]

    suspicious_fields = []
    for table_name, rows in normalized_reference["tables"].items():
        if not rows:
            continue
        candidate_rows = normalized_candidate["tables"].get(table_name, [])
        reference_presence: dict[str, bool] = {}
        candidate_presence: dict[str, bool] = {}
        for row in rows:
            for field, value in row.items():
                if field in _BLOB_PRESENCE_FIELDS or field in {
                    "pLmVerTable",
                    "pAuxLmVerTable",
                    "CompositionTable",
                    "BlobLockSysId",
                    "CompTableLockSysId",
                    "VersionTableLockSysId",
                    "LockSysId",
                }:
                    reference_presence[field] = reference_presence.get(field, False) or value not in (None, "", 0)
        for row in candidate_rows:
            for field, value in row.items():
                if field in reference_presence:
                    candidate_presence[field] = candidate_presence.get(field, False) or value not in (None, "", 0)
        for field, expected_present in sorted(reference_presence.items()):
            actual_present = candidate_presence.get(field, False)
            if expected_present and not actual_present:
                suspicious_fields.append(
                    {
                        "table": table_name,
                        "field": field,
                        "candidate_present": actual_present,
                        "reference_present": expected_present,
                    }
                )

    candidate_value_entries = _build_value_entries(candidate)
    reference_value_entries = _build_value_entries(reference)
    value_mismatches = []
    missing_non_null_fields = []
    unexpected_non_null_fields = []

    for table_name in sorted(set(candidate_value_entries) | set(reference_value_entries)):
        candidate_rows = candidate_value_entries.get(table_name, {})
        reference_rows = reference_value_entries.get(table_name, {})
        for key in sorted(set(candidate_rows) | set(reference_rows)):
            candidate_fields = candidate_rows.get(key, {})
            reference_fields = reference_rows.get(key, {})
            for field in sorted(set(candidate_fields) | set(reference_fields)):
                candidate_value = candidate_fields.get(field)
                reference_value = reference_fields.get(field)
                candidate_present = _is_meaningful(candidate_value)
                reference_present = _is_meaningful(reference_value)
                if reference_present and not candidate_present:
                    missing_non_null_fields.append(
                        {
                            "table": table_name,
                            "key": key,
                            "field": field,
                            "candidate": candidate_value,
                            "reference": reference_value,
                        }
                    )
                elif candidate_present and not reference_present:
                    unexpected_non_null_fields.append(
                        {
                            "table": table_name,
                            "key": key,
                            "field": field,
                            "candidate": candidate_value,
                            "reference": reference_value,
                        }
                    )
                elif candidate_present and reference_present and candidate_value != reference_value:
                    value_mismatches.append(
                        {
                            "table": table_name,
                            "key": key,
                            "field": field,
                            "candidate": candidate_value,
                            "reference": reference_value,
                        }
                    )

    row_differences = []
    for table_name in _SNAPSHOT_TABLES:
        candidate_rows = normalized_candidate["tables"].get(table_name, [])
        reference_rows = normalized_reference["tables"].get(table_name, [])
        if candidate_rows != reference_rows:
            row_differences.append(
                {
                    "table": table_name,
                    "candidate": candidate_rows,
                    "reference": reference_rows,
                }
            )

    return {
        "table_counts": table_counts,
        "relation_counts": relation_counts,
        "missing_edges": missing_edges,
        "suspicious_fields": suspicious_fields,
        "value_mismatches": value_mismatches,
        "missing_non_null_fields": missing_non_null_fields,
        "unexpected_non_null_fields": unexpected_non_null_fields,
        "row_differences": row_differences,
        "normalized_candidate": normalized_candidate,
        "normalized_reference": normalized_reference,
        "candidate_value_entries": candidate_value_entries,
        "reference_value_entries": reference_value_entries,
    }


def build_multicam_reference_audit(
    project_db_path: str | Path,
    *,
    candidate_media_id: str,
    config: AuditReferenceConfig | None = None,
) -> dict[str, Any]:
    reference_config = config or AuditReferenceConfig()

    candidate_snapshot = snapshot_multicam_graph(project_db_path, media_id=candidate_media_id)
    reference_media = find_named_media(project_db_path, name=reference_config.reference_multicam_name)
    timeline_reference = find_named_timeline(project_db_path, name=reference_config.secondary_timeline_name)

    reference_snapshot = (
        snapshot_multicam_graph(project_db_path, media_id=str(reference_media["Sm2MpMedia_id"]))
        if reference_media
        else None
    )
    timeline_snapshot = (
        snapshot_multicam_graph(project_db_path, sequence_id=str(timeline_reference["Sequence"]))
        if timeline_reference and timeline_reference.get("Sequence")
        else None
    )

    audit_unavailable_reason = None
    if reference_snapshot is None:
        audit_unavailable_reason = "reference_multicam_missing"

    diff = diff_graph_snapshots(candidate_snapshot, reference_snapshot) if reference_snapshot else None
    if diff is None:
        diff = {
            "audit_unavailable_reason": audit_unavailable_reason,
            "table_counts": {},
            "relation_counts": {},
            "missing_edges": [],
            "suspicious_fields": [],
            "value_mismatches": [],
            "missing_non_null_fields": [],
            "unexpected_non_null_fields": [],
            "row_differences": [],
        }

    return {
        "candidate_media_id": candidate_media_id,
        "reference_multicam_name": reference_config.reference_multicam_name,
        "timeline_reference_name": reference_config.secondary_timeline_name,
        "reference_media_id": reference_media.get("Sm2MpMedia_id") if reference_media else None,
        "reference_sequence_id": reference_media.get("Sequence") if reference_media else None,
        "timeline_reference_sequence_id": timeline_reference.get("Sequence") if timeline_reference else None,
        "audit_unavailable_reason": audit_unavailable_reason,
        "candidate_graph": candidate_snapshot,
        "reference_graph": reference_snapshot,
        "timeline_graph": timeline_snapshot,
        "structural_diff": diff,
        "missing_edges": diff.get("missing_edges") if diff else [],
    }
