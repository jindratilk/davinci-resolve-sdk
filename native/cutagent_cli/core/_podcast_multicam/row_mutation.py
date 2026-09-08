from __future__ import annotations

import sqlite3
import struct
from typing import Any

from ...errors import APICallFailed


def _clone_item_row_with_segment(
    base_row: dict[str, Any],
    *,
    item_id: str,
    start: str,
    duration: str,
    in_value: str | None,
    current_selector_idx: int,
    fields_blob: bytes,
    media_timemap_ba: bytes | None = None,
    effect_filters_ba: bytes | None = None,
) -> dict[str, Any]:
    row = dict(base_row)
    row["Sm2TiItem_id"] = item_id
    row["Start"] = start
    row["Duration"] = duration
    row["In"] = in_value
    row["CurrentSelectorIdx"] = current_selector_idx
    row["FieldsBlob"] = fields_blob
    if media_timemap_ba is not None:
        row["MediaTimemapBA"] = media_timemap_ba
    if effect_filters_ba is not None or "EffectFiltersBA" in row:
        row["EffectFiltersBA"] = effect_filters_ba
    return row


def _decode_frame_rate_blob(value: Any) -> float | None:
    if not isinstance(value, (bytes, bytearray)) or len(value) < 8:
        return None
    try:
        fps = float(struct.unpack("<d", bytes(value[:8]))[0])
    except Exception:
        return None
    if fps <= 0:
        return None
    return fps


def _encode_media_extents(start_seconds: float, duration_seconds: float) -> bytes:
    return struct.pack("<dd", float(start_seconds), float(duration_seconds))


def _quote_identifier(identifier: str) -> str:
    return '"' + str(identifier).replace('"', '""') + '"'


def _insert_row(cursor: sqlite3.Cursor, table_name: str, row: dict[str, Any]) -> None:
    table_columns = {
        str(info[1])
        for info in cursor.execute(f"PRAGMA table_info({_quote_identifier(table_name)})").fetchall()
    }
    columns = [column for column in row.keys() if column in table_columns]
    if not columns:
        raise APICallFailed(
            "Could not map any columns for native multicam DB row insertion.",
            details={"table_name": table_name},
        )
    column_sql = ", ".join(_quote_identifier(column) for column in columns)
    placeholders = ", ".join("?" for _ in columns)
    cursor.execute(
        f"INSERT INTO {table_name} ({column_sql}) VALUES ({placeholders})",
        [row[column] for column in columns],
    )


def _update_row(cursor: sqlite3.Cursor, table_name: str, row_id_column: str, row_id: Any, updates: dict[str, Any]) -> None:
    table_columns = {
        str(info[1])
        for info in cursor.execute(f"PRAGMA table_info({_quote_identifier(table_name)})").fetchall()
    }
    columns = [column for column in updates.keys() if column in table_columns and column != row_id_column]
    if not columns:
        return
    assignments = ", ".join(f"{_quote_identifier(column)} = ?" for column in columns)
    cursor.execute(
        f"UPDATE {table_name} SET {assignments} WHERE {_quote_identifier(row_id_column)} = ?",
        [updates[column] for column in columns] + [row_id],
    )


def _delete_track_items(cursor: sqlite3.Cursor, *, track_id: str) -> None:
    item_ids = [
        str(row[0])
        for row in cursor.execute(
            """
            SELECT DbAssociate
            FROM Sm2TiItem_Sm2TiTrack
            WHERE DbOwner = ? AND DbPropertyName = 'Items'
            """,
            (track_id,),
        ).fetchall()
        if row[0]
    ]
    if not item_ids:
        return
    cursor.executemany(
        "DELETE FROM Sm2TiItem_Sm2TiTrack WHERE DbAssociate = ?",
        [(item_id,) for item_id in item_ids],
    )
    cursor.executemany(
        "DELETE FROM Sm2TiItem WHERE Sm2TiItem_id = ?",
        [(item_id,) for item_id in item_ids],
    )


def _delete_items(cursor: sqlite3.Cursor, *, item_ids: list[str]) -> None:
    normalized = [str(item_id) for item_id in item_ids if str(item_id or "").strip()]
    if not normalized:
        return
    cursor.executemany(
        "DELETE FROM Sm2TiItem_Sm2TiTrack WHERE DbAssociate = ?",
        [(item_id,) for item_id in normalized],
    )
    cursor.executemany(
        "DELETE FROM Sm2TiItem WHERE Sm2TiItem_id = ?",
        [(item_id,) for item_id in normalized],
    )
