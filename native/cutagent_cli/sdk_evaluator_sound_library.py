"""Private read-only Sound Library evidence for the native SDK evaluator.

This module is deliberately outside the public SDK action inventory.  It reads an
already-selected DaVinci Resolve Sound Library SQLite database and never writes,
restores, or claims that DaVinci Resolve consumed the observed rows.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat as stat_module
from typing import Any

from .errors import ReadinessFailed, ValidationError


_TABLES = ("FLAssetBaseClip", "FLAssetBaseFile", "FLAssetBaseContainer")
_MAX_ROWS = 10_000
_MAX_HASH_BYTES = 512 * 1024 * 1024


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _fail(message: str, *, details: dict[str, Any] | None = None) -> None:
    raise ReadinessFailed(message, details=details or {}, recoverability="not_applicable")


def _selected_database(database_path: str | Path, scope: str) -> tuple[Path, os.stat_result]:
    if scope not in {"project", "user"}:
        raise ValidationError(
            "The evaluator Sound Library scope must be project or user.",
            details={"scope": scope},
            recoverability="not_applicable",
        )
    supplied = Path(database_path).expanduser()
    if not supplied.is_absolute():
        _fail("The evaluator Sound Library database path must be absolute.")
    try:
        link_stat = supplied.lstat()
        canonical = supplied.resolve(strict=True)
        stat = canonical.stat()
    except OSError as exc:
        _fail("The selected evaluator Sound Library database is unavailable.", details={"error": exc.__class__.__name__})
    expected_name = "Project.db" if scope == "project" else "User.db"
    if supplied.is_symlink() or not canonical.is_file() or canonical.name != expected_name:
        _fail(
            "The selected evaluator Sound Library database has the wrong identity.",
            details={"scope": scope, "expected_name": expected_name},
        )
    if (link_stat.st_dev, link_stat.st_ino) != (stat.st_dev, stat.st_ino):
        _fail("The selected evaluator Sound Library database was redirected.")
    return canonical, stat


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in connection.execute(f'PRAGMA table_info("{table}")').fetchall()}


def _require_schema(connection: sqlite3.Connection) -> None:
    present = {
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name IN (?, ?, ?)", _TABLES
        ).fetchall()
    }
    missing = [table for table in _TABLES if table not in present]
    required = {
        "FLAssetBaseClip": {"FLAssetBaseClip_id", "file_cookie"},
        "FLAssetBaseFile": {"FLAssetBaseFile_id", "cookie", "container_cookie", "path"},
        "FLAssetBaseContainer": {"FLAssetBaseContainer_id", "cookie", "path", "data_path"},
    }
    missing_columns = {
        table: sorted(columns - _columns(connection, table))
        for table, columns in required.items()
        if table in present and columns - _columns(connection, table)
    }
    if missing or missing_columns:
        _fail(
            "The selected evaluator database is not a supported Sound Library database.",
            details={"missing_tables": missing, "missing_columns": missing_columns},
        )


def _evidence_value(value: Any) -> Any:
    if isinstance(value, bytes):
        return {"kind": "bytes", "byteCount": len(value), "sha256": f"sha256:{hashlib.sha256(value).hexdigest()}"}
    if value is None or isinstance(value, (str, int, float)):
        return value
    return str(value)


def _complete_table_rows(connection: sqlite3.Connection, table: str, id_column: str) -> dict[str, str]:
    rows = connection.execute(
        f'SELECT * FROM "{table}" ORDER BY CAST("{id_column}" AS TEXT) LIMIT ?',
        (_MAX_ROWS + 1,),
    ).fetchall()
    if len(rows) > _MAX_ROWS:
        _fail("The selected Sound Library table exceeds the evaluator evidence bound.")
    result: dict[str, str] = {}
    for row in rows:
        identity = str(row[id_column] or "")
        if not identity or identity in result:
            _fail("The selected Sound Library table has an empty or duplicate row identity.")
        complete = {str(column): _evidence_value(row[column]) for column in row.keys()}
        result[identity] = _canonical_sha256(complete)
    return result


def _absolute(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    candidate = Path(text).expanduser()
    return str(candidate.resolve(strict=False)) if candidate.is_absolute() else None


def _under(path_value: str | None, root: Path) -> bool:
    if path_value is None:
        return False
    try:
        Path(path_value).relative_to(root)
        return True
    except ValueError:
        return False


def _file_sha256(file_path: str | None, root: Path) -> str | None:
    if not _under(file_path, root):
        return None
    candidate = Path(str(file_path))
    try:
        stat = candidate.lstat()
    except OSError:
        return None
    if not stat_module.S_ISREG(stat.st_mode) or candidate.is_symlink() or stat.st_nlink != 1 or stat.st_size > _MAX_HASH_BYTES:
        return None
    digest = hashlib.sha256()
    with candidate.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    after = candidate.lstat()
    if (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) != (
        stat.st_dev,
        stat.st_ino,
        stat.st_size,
        stat.st_mtime_ns,
    ):
        _fail("An evaluator-owned Sound Library source changed while it was hashed.")
    return f"sha256:{digest.hexdigest()}"


def observe_sound_library_database(
    database_path: str | Path,
    *,
    scope: str,
    source_root: str | Path,
    phase: str,
) -> dict[str, Any]:
    """Read exact rows from one selected database without mutating it."""

    if phase not in {"before", "mutated", "restored"}:
        raise ValidationError(
            "The evaluator Sound Library phase is invalid.",
            details={"phase": phase},
            recoverability="not_applicable",
        )
    source = Path(source_root).expanduser()
    if not source.is_absolute():
        _fail("The evaluator Sound Library source root must be absolute.")
    source = source.resolve(strict=False)
    database, before_stat = _selected_database(database_path, scope)
    uri = f"{database.as_uri()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True, timeout=2.0)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("BEGIN")
        _require_schema(connection)
        schema_version = int(connection.execute("PRAGMA schema_version").fetchone()[0])
        user_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        container_records = [
            {
                "kind": "container",
                "id": str(row["id"] or ""),
                "cookie": str(row["cookie"] or ""),
                "sourcePath": _absolute(row["source_path"]),
            }
            for row in connection.execute(
                """
                SELECT CAST(FLAssetBaseContainer_id AS TEXT) AS id, CAST(cookie AS TEXT) AS cookie,
                       COALESCE(NULLIF(path, ''), NULLIF(data_path, '')) AS source_path
                FROM FLAssetBaseContainer ORDER BY id LIMIT ?
                """,
                (_MAX_ROWS + 1,),
            ).fetchall()
        ]
        file_records = [
            {
                "kind": "file",
                "id": str(row["id"] or ""),
                "cookie": str(row["cookie"] or ""),
                "containerCookie": str(row["container_cookie"] or ""),
                "path": _absolute(row["file_path"]),
            }
            for row in connection.execute(
                """
                SELECT CAST(FLAssetBaseFile_id AS TEXT) AS id, CAST(cookie AS TEXT) AS cookie,
                       CAST(container_cookie AS TEXT) AS container_cookie, path AS file_path
                FROM FLAssetBaseFile ORDER BY id LIMIT ?
                """,
                (_MAX_ROWS + 1,),
            ).fetchall()
        ]
        clip_records = [
            {
                "kind": "clip",
                "id": str(row["id"] or ""),
                "fileCookie": str(row["file_cookie"] or ""),
            }
            for row in connection.execute(
                """
                SELECT CAST(FLAssetBaseClip_id AS TEXT) AS id, CAST(file_cookie AS TEXT) AS file_cookie
                FROM FLAssetBaseClip ORDER BY id LIMIT ?
                """,
                (_MAX_ROWS + 1,),
            ).fetchall()
        ]
        if any(len(records) > _MAX_ROWS for records in (container_records, file_records, clip_records)):
            _fail("The selected Sound Library table exceeds the evaluator evidence bound.")
        complete_row_digests = {
            "container": _complete_table_rows(connection, "FLAssetBaseContainer", "FLAssetBaseContainer_id"),
            "file": _complete_table_rows(connection, "FLAssetBaseFile", "FLAssetBaseFile_id"),
            "clip": _complete_table_rows(connection, "FLAssetBaseClip", "FLAssetBaseClip_id"),
        }
        owned_container_refs = {
            reference
            for row in container_records
            if _under(row["sourcePath"], source)
            for reference in (row["id"], row["cookie"])
            if reference
        }
        owned_file_refs = {
            reference
            for row in file_records
            if _under(row["path"], source) or row["containerCookie"] in owned_container_refs
            for reference in (row["id"], row["cookie"])
            if reference
        }
        database_records = []
        for row in container_records:
            database_records.append({
                **row,
                "ownedSource": row["id"] in owned_container_refs or row["cookie"] in owned_container_refs,
                "completeRowSha256": complete_row_digests["container"][row["id"]],
            })
        for row in file_records:
            owned = row["id"] in owned_file_refs or row["cookie"] in owned_file_refs
            database_records.append({
                **row,
                "ownedSource": owned,
                "contentSha256": _file_sha256(row["path"], source) if owned else None,
                "completeRowSha256": complete_row_digests["file"][row["id"]],
            })
        for row in clip_records:
            database_records.append({
                **row,
                "ownedSource": row["fileCookie"] in owned_file_refs,
                "completeRowSha256": complete_row_digests["clip"][row["id"]],
            })
        database_records.sort(key=lambda row: (str(row["kind"]), str(row["id"])))
        rows = connection.execute(
            """
            SELECT DISTINCT
                CAST(clip.FLAssetBaseClip_id AS TEXT) AS clip_id,
                CAST(library_file.FLAssetBaseFile_id AS TEXT) AS file_id,
                CAST(container.FLAssetBaseContainer_id AS TEXT) AS container_id,
                library_file.path AS file_path,
                COALESCE(NULLIF(container.path, ''), NULLIF(container.data_path, '')) AS source_path
            FROM FLAssetBaseClip clip
            LEFT JOIN FLAssetBaseFile library_file
              ON CAST(library_file.FLAssetBaseFile_id AS TEXT) = CAST(clip.file_cookie AS TEXT)
              OR CAST(library_file.cookie AS TEXT) = CAST(clip.file_cookie AS TEXT)
            LEFT JOIN FLAssetBaseContainer container
              ON CAST(container.FLAssetBaseContainer_id AS TEXT) = CAST(library_file.container_cookie AS TEXT)
              OR CAST(container.cookie AS TEXT) = CAST(library_file.container_cookie AS TEXT)
            ORDER BY clip_id, file_id, container_id, file_path
            LIMIT ?
            """,
            (_MAX_ROWS + 1,),
        ).fetchall()
        if len(rows) > _MAX_ROWS:
            _fail("The selected Sound Library inventory exceeds the evaluator evidence bound.")
        canonical_rows = []
        for row in rows:
            file_path = _absolute(row["file_path"])
            source_path = _absolute(row["source_path"])
            canonical_rows.append(
                {
                    "clipId": str(row["clip_id"] or ""),
                    "fileId": str(row["file_id"] or ""),
                    "containerId": str(row["container_id"] or ""),
                    "path": file_path,
                    "sourcePath": source_path,
                    "ownedSource": _under(file_path, source) or _under(source_path, source),
                    "contentSha256": _file_sha256(file_path, source),
                }
            )
        connection.execute("COMMIT")
    except Exception:
        try:
            connection.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise
    finally:
        connection.close()

    after_stat = database.stat()
    before_identity = (before_stat.st_dev, before_stat.st_ino, before_stat.st_size, before_stat.st_mtime_ns)
    after_identity = (after_stat.st_dev, after_stat.st_ino, after_stat.st_size, after_stat.st_mtime_ns)
    if before_identity != after_identity:
        _fail("The selected Sound Library database changed during evaluator observation.")

    owned_rows = [row for row in canonical_rows if row["ownedSource"]]
    owned_database_records = [row for row in database_records if row["ownedSource"]]
    owned_database_record_evidence = [
        {"kind": row["kind"], "id": row["id"], "completeRowSha256": row["completeRowSha256"]}
        for row in owned_database_records
    ]
    foreign_records = [row for row in database_records if not row["ownedSource"]]
    snapshot = {
        "scope": scope,
        "sourceRoot": str(source),
        "databaseRecords": database_records,
        "foreignRowsSha256": _canonical_sha256(foreign_records),
    }
    return {
        "schemaVersion": "1.0.0",
        "kind": "cutagent_sdk_evaluator_sound_library_observation",
        "phase": phase,
        "scope": scope,
        "sourceRoot": str(source),
        "databaseIdentity": {
            "canonicalPath": str(database),
            "device": str(after_stat.st_dev),
            "inode": str(after_stat.st_ino),
            "sizeBytes": after_stat.st_size,
            "mtimeNs": str(after_stat.st_mtime_ns),
            "schemaVersion": schema_version,
            "userVersion": user_version,
        },
        "rows": canonical_rows,
        "ownedRowCount": len(owned_rows),
        "ownedDatabaseRecordCount": len(owned_database_records),
        "ownedDatabaseRecords": owned_database_record_evidence,
        "foreignRowsSha256": snapshot["foreignRowsSha256"],
        "snapshotSha256": _canonical_sha256(snapshot),
        "nativeReadback": True,
        "davinciResolveReopened": False,
        "audioOrGuiProbe": {"status": "unavailable", "receiptSha256": None},
        "nativeEffectProven": False,
    }


def observe_active_sound_library_database(*, scope: str, source_root: str | Path, phase: str) -> dict[str, Any]:
    """Resolve the active project/user database through CutAgent CLI ownership."""

    from .commands import fairlight
    from .connection import get_connection
    from .runtime_health import resolve_current_disk_project_db

    connection = get_connection(require_project=True)
    current = resolve_current_disk_project_db(connection, allow_project_name_inference=True)
    if scope == "project":
        database_path = str(current.get("project_db_path") or "")
    elif scope == "user":
        database_path = fairlight._resolve_sound_library_user_db_target(connection)["user_db_path"]
    else:
        database_path = ""
    return observe_sound_library_database(database_path, scope=scope, source_root=source_root, phase=phase)
