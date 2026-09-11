"""SQLite row helpers for Project.db timeline mutations."""

from __future__ import annotations

from functools import lru_cache
import re
import sqlite3
from typing import Any

from ..errors import ValidationError
from .db_timeline_selection import LiveItemRef


def _row_to_dict(cursor: sqlite3.Cursor, row: tuple[Any, ...] | sqlite3.Row) -> dict[str, Any]:
    if isinstance(row, sqlite3.Row):
        return {key: row[key] for key in row.keys()}
    return {cursor.description[index][0]: value for index, value in enumerate(row)}


@lru_cache(maxsize=128)
def _cached_table_columns(path: str, table_name: str) -> tuple[str, ...]:
    conn = sqlite3.connect(path)
    try:
        rows = conn.execute(f'PRAGMA table_info("{table_name}")').fetchall()
    finally:
        conn.close()
    return tuple(str(row[1]) for row in rows)


def table_columns(cursor: sqlite3.Cursor, table_name: str) -> set[str]:
    db_path = cursor.connection.execute("PRAGMA database_list").fetchone()[2]
    if not str(db_path):
        rows = cursor.execute(f'PRAGMA table_info("{table_name}")').fetchall()
        return {str(row[1]) for row in rows}
    return set(_cached_table_columns(str(db_path), str(table_name)))


def insert_row(cursor: sqlite3.Cursor, table_name: str, values: dict[str, Any]) -> None:
    available = table_columns(cursor, table_name)
    payload = {key: value for key, value in values.items() if key in available}
    if not payload:
        raise ValidationError("Insert payload did not match table columns.", details={"table": table_name})
    columns = list(payload.keys())
    placeholders = ", ".join("?" for _ in columns)
    quoted_columns = ", ".join(f'"{column}"' for column in columns)
    sql = f'INSERT INTO "{table_name}" ({quoted_columns}) VALUES ({placeholders})'
    cursor.execute(sql, [payload[column] for column in columns])


def update_row(
    cursor: sqlite3.Cursor,
    table_name: str,
    key_column: str,
    key_value: Any,
    updates: dict[str, Any],
) -> None:
    available = table_columns(cursor, table_name)
    payload = {key: value for key, value in updates.items() if key in available}
    if not payload:
        return
    assignments = ", ".join(f'"{column}" = ?' for column in payload)
    sql = f'UPDATE "{table_name}" SET {assignments} WHERE "{key_column}" = ?'
    cursor.execute(sql, [payload[column] for column in payload] + [key_value])


def _timeline_track_ids(
    cursor: sqlite3.Cursor,
    *,
    timeline_name: str,
    track_type: str,
    track_index: int,
) -> list[str]:
    property_name = {"video": "VideoTrackVec", "audio": "AudioTrackVec"}.get(str(track_type))
    if property_name is None:
        return []
    db_index = int(track_index) - 1
    if db_index < 0:
        return []
    try:
        rows = cursor.execute(
            """
            SELECT tr.Sm2TiTrack_id
            FROM Sm2Timeline tl
            JOIN Sm2SequenceContainer sc ON sc.Sm2Sequence_id = tl.Sequence
            JOIN Sm2SequenceContainer_Sm2TiTrack rel
              ON rel.DbOwner = sc.Sm2SequenceContainer_id
             AND rel.DbPropertyName = ?
             AND rel.DbIndex = ?
            JOIN Sm2TiTrack tr ON tr.Sm2TiTrack_id = rel.DbAssociate
            WHERE tl.Name = ?
            """,
            (property_name, db_index, timeline_name),
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    return [str(row[0]) for row in rows]


def _db_name_candidates(item: LiveItemRef) -> tuple[str, ...]:
    candidates: list[str] = []
    for raw_name in (item.name, *tuple(item.aliases or ())):
        try:
            name = str(raw_name).strip()
        except Exception:
            continue
        if not name:
            continue
        candidates.append(name)
        angle_stripped = re.sub(r"\s+-\s+Angle\s+\d+\s*$", "", name, flags=re.IGNORECASE).strip()
        if angle_stripped and angle_stripped != name:
            candidates.append(angle_stripped)

    seen: set[str] = set()
    unique: list[str] = []
    for name in candidates:
        key = name.casefold()
        if key in seen:
            continue
        seen.add(key)
        unique.append(name)
    return tuple(unique)


def _duration_frame_prefix(value: Any) -> int | None:
    try:
        text = str(value).strip()
    except Exception:
        return None
    if not text:
        return None
    prefix = text.split("|", 1)[0].strip()
    if not re.fullmatch(r"[+-]?\d+", prefix):
        return None
    try:
        return int(prefix)
    except Exception:
        return None


def _duration_matches(row_duration: Any, item: LiveItemRef) -> bool:
    expected = int(item.duration)
    if str(row_duration) == str(expected):
        return True
    stored = _duration_frame_prefix(row_duration)
    if stored is None:
        return False
    if stored == expected:
        return True
    # DaVinci Resolve can persist audio item duration cells as "N|<binary-ish suffix>"
    # where the live TimelineItem reports N + 1 frames for the same selected item.
    return str(item.track_type) == "audio" and "|" in str(row_duration) and abs(stored - expected) <= 1


def _filter_rows_to_track_owners(
    cursor: sqlite3.Cursor,
    *,
    rows: list[dict[str, Any]],
    allowed_track_ids: set[str],
) -> list[dict[str, Any]]:
    """Restrict item rows to the selected track using the strongest available ownership proof."""
    relation_table_exists = cursor.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'Sm2TiItem_Sm2TiTrack'"
    ).fetchone()
    if not relation_table_exists:
        raise ValidationError(
            "Could not verify timeline item ownership in Project.db.",
            details={"missing_table": "Sm2TiItem_Sm2TiTrack"},
        )

    item_ids = [str(row.get("Sm2TiItem_id") or "") for row in rows if row.get("Sm2TiItem_id")]
    if not item_ids:
        return []
    placeholders = ", ".join("?" for _ in item_ids)
    ownership_rows = cursor.execute(
        f"""
        SELECT DbAssociate, DbOwner
        FROM Sm2TiItem_Sm2TiTrack
        WHERE DbAssociate IN ({placeholders}) AND DbPropertyName = 'Items'
        """,
        item_ids,
    ).fetchall()
    owners_by_item: dict[str, set[str]] = {}
    for item_id, owner_id in ownership_rows:
        owners_by_item.setdefault(str(item_id), set()).add(str(owner_id))
    verified_rows: list[dict[str, Any]] = []
    for row in rows:
        item_id = str(row.get("Sm2TiItem_id") or "")
        relation_owners = owners_by_item.get(item_id, set())
        direct_owner = str(row.get("Sm2TiTrack_id") or "")
        if len(relation_owners) != 1:
            continue
        relation_owner = next(iter(relation_owners))
        if relation_owner != direct_owner:
            continue
        if relation_owner in allowed_track_ids:
            verified_rows.append(row)
    return verified_rows


def find_ti_item_row(
    cursor: sqlite3.Cursor,
    *,
    item: LiveItemRef,
    db_type: str,
    timeline_name: str | None = None,
    require_timeline_name: bool = False,
) -> dict[str, Any]:
    normalized_timeline_name = str(timeline_name or "").strip()
    if require_timeline_name and not normalized_timeline_name:
        raise ValidationError(
            "Project.db timeline item lookup requires an exact timeline name.",
            details={
                "track_type": item.track_type,
                "track_index": item.track_index,
                "timeline_name": timeline_name,
            },
        )
    names = _db_name_candidates(item)
    placeholders = ", ".join("?" for _ in names) or "?"
    query_names: tuple[str, ...] = names or (item.name,)
    exact_id_clause = " AND Sm2TiItem_id = ?" if item.item_id else ""
    exact_id_params: tuple[str, ...] = (str(item.item_id),) if item.item_id else ()
    raw_rows = cursor.execute(
        f"""
        SELECT *
        FROM Sm2TiItem
        WHERE DbType = ? AND Name IN ({placeholders}) AND Start = ?{exact_id_clause}
        """,
        (db_type, *query_names, str(item.start), *exact_id_params),
    ).fetchall()
    rows = [_row_to_dict(cursor, row) for row in raw_rows]
    if normalized_timeline_name:
        track_ids = _timeline_track_ids(
            cursor,
            timeline_name=normalized_timeline_name,
            track_type=item.track_type,
            track_index=item.track_index,
        )
        if len(track_ids) != 1:
            raise ValidationError(
                "Could not resolve a unique selected timeline track in Project.db.",
                details={
                    "track_type": item.track_type,
                    "track_index": item.track_index,
                    "timeline_name": normalized_timeline_name,
                    "track_owner_count": len(track_ids),
                },
            )
        rows = _filter_rows_to_track_owners(
            cursor,
            rows=rows,
            allowed_track_ids=set(track_ids),
        )
    duration_candidates = [row.get("Duration") for row in rows]
    rows = [row for row in rows if _duration_matches(row.get("Duration"), item)]
    if len(rows) != 1:
        raise ValidationError(
            "Could not resolve a unique Project.db row for the selected timeline item.",
            details={
                "track_type": item.track_type,
                "track_index": item.track_index,
                "db_type": db_type,
                "timeline_name": normalized_timeline_name,
                "name": item.name,
                "candidate_names": list(query_names),
                "start": item.start,
                "duration": item.duration,
                "item_id": item.item_id,
                "duration_candidates": duration_candidates,
                "match_count": len(rows),
            },
        )
    return rows[0]
