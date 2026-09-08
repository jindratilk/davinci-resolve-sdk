"""Safe Disk project-library create, backup, and restore workflows.

DaVinci Resolve's public scripting API can list and switch registered project
libraries, but it does not expose create/backup/restore methods.  These
workflows therefore own the filesystem and ``dblist.conf`` boundary. Creating
or restoring a library additionally requires a connection-owned activation
strategy that can restart and reattach the exact Resolve process; the public
API remains the authority for reopen and context readback.
"""

from __future__ import annotations

from contextlib import contextmanager
import ctypes
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sqlite3
import stat
import sys
import tempfile
import time
from typing import Any, Iterator
from uuid import uuid4

from ..errors import APICallFailed, DiskDbLocked, ValidationError
from ..output import set_recoverability, set_verification_status
from ..state_contracts import looks_like_project_manager_placeholder


BACKUP_SCHEMA_VERSION = 1
BACKUP_MANIFEST = "cutagent-library-backup.json"
BACKUP_PAYLOAD = "payload"
LIBRARY_MARKER = ".cutagent-library.json"
LIBRARY_FORMAT = "davinci_resolve_disk_library"
_LOCK_NAME = ".cutagent-project-library.lock"
_SQLITE_SUFFIXES = {".db", ".sqlite", ".sqlite3"}
_USER_CATALOG_RELATIVE = Path("Resolve Projects") / "Users" / "guest" / "User.db"
_RegularIdentity = tuple[int, int, int, int, int]


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _validation(message: str, *, reason: str, **details: Any) -> ValidationError:
    return ValidationError(
        message,
        details={
            "reason": reason,
            "possible_mutation": False,
            "manual_recovery_required": False,
            **details,
        },
        recoverability="not_applicable",
    )


def _failure(
    message: str,
    *,
    phase: str,
    possible_mutation: bool,
    manual_recovery_required: bool,
    recovery: dict[str, Any],
    error: BaseException,
    steps: list[str],
) -> APICallFailed:
    return APICallFailed(
        message,
        details={
            "phase": phase,
            "possible_mutation": possible_mutation,
            "manual_recovery_required": manual_recovery_required,
            "mutation_state": (
                "manual_recovery_required"
                if manual_recovery_required
                else "restored"
                if possible_mutation
                else "not_started"
            ),
            "recovery": recovery,
            "steps": steps,
            "original_error": {
                "type": error.__class__.__name__,
                "message": str(error),
                "details": dict(getattr(error, "details", {}) or {}),
            },
        },
        recoverability="manual" if manual_recovery_required else "retryable",
    )


def _supports_posix_ownership() -> bool:
    return os.name == "posix"


def _is_redirect(path: Path) -> bool:
    return path.is_symlink() or bool(hasattr(path, "is_junction") and path.is_junction())


def _assert_owned(path: Path, *, reason: str) -> None:
    if not _supports_posix_ownership():
        return
    try:
        owner = path.stat(follow_symlinks=False).st_uid
    except OSError as exc:
        raise _validation(
            "Project-library path metadata could not be read safely.",
            reason=reason,
            path=str(path),
            error_type=exc.__class__.__name__,
        ) from exc
    if owner != os.getuid():
        raise _validation(
            "Project-library path is not owned by the current user.",
            reason=reason,
            path=str(path),
        )


def _assert_no_redirect_chain(path: Path, *, include_leaf: bool, reason: str) -> None:
    absolute = Path(os.path.abspath(path.expanduser()))
    candidates = list(reversed(absolute.parents))
    if include_leaf:
        candidates.append(absolute)
    for candidate in candidates:
        if candidate == Path(candidate.anchor) or not candidate.exists():
            continue
        if _is_redirect(candidate):
            raise _validation(
                "Project-library paths must not contain symbolic links or junctions.",
                reason=reason,
                path=str(candidate),
            )


def _normalize_explicit_path(raw: str, *, kind: str, must_exist: bool) -> Path:
    value = str(raw or "").strip()
    if not value:
        raise _validation(f"An explicit {kind} path is required.", reason=f"{kind}_path_missing")
    supplied = Path(value).expanduser()
    if ".." in supplied.parts:
        raise _validation(
            f"The explicit {kind} path must not contain parent traversal.",
            reason=f"{kind}_path_traversal",
            path=value,
        )
    absolute = Path(os.path.abspath(supplied))
    _assert_no_redirect_chain(absolute, include_leaf=must_exist or absolute.exists(), reason=f"{kind}_path_redirect")
    if must_exist and not absolute.exists():
        raise _validation(
            f"The explicit {kind} path does not exist.",
            reason=f"{kind}_path_missing",
            path=str(absolute),
        )
    parent = absolute.parent
    if not parent.exists() or not parent.is_dir():
        raise _validation(
            f"The explicit {kind} parent directory does not exist.",
            reason=f"{kind}_parent_missing",
            path=str(absolute),
            parent=str(parent),
        )
    _assert_owned(parent, reason=f"{kind}_parent_wrong_owner")
    return absolute


def _normalize_name(name: str) -> str:
    value = str(name or "").strip()
    if not value:
        raise _validation("An explicit project-library name is required.", reason="library_name_missing")
    if value in {".", ".."} or any(character in value for character in ("/", "\\", ":", "\n", "\r", "\0")):
        raise _validation(
            "Project-library name contains unsupported path or configuration characters.",
            reason="library_name_invalid",
            name=value,
        )
    return value


def _dblist_path() -> Path:
    configured = str(os.environ.get("CUTAGENT_RESOLVE_DBLIST_PATH") or "").strip()
    if configured:
        return Path(os.path.abspath(Path(configured).expanduser()))
    if sys.platform == "win32":
        appdata = str(os.environ.get("APPDATA") or "").strip()
        base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
        return base / "Blackmagic Design" / "DaVinci Resolve" / "Support" / "Preferences" / "dblist.conf"
    return Path.home() / "Library" / "Preferences" / "Blackmagic Design" / "DaVinci Resolve" / "dblist.conf"


def _read_registry_bytes(path: Path) -> bytes:
    _assert_no_redirect_chain(path, include_leaf=True, reason="database_registry_redirect")
    if not path.exists() or not path.is_file():
        raise _validation(
            "DaVinci Resolve project-library registry was not found.",
            reason="database_registry_missing",
            registry_path=str(path),
        )
    _assert_owned(path, reason="database_registry_wrong_owner")
    try:
        return path.read_bytes()
    except OSError as exc:
        raise _validation(
            "DaVinci Resolve project-library registry could not be read.",
            reason="database_registry_unreadable",
            registry_path=str(path),
            error_type=exc.__class__.__name__,
        ) from exc


def _parse_disk_registry(data: bytes, *, path: Path) -> list[dict[str, str]]:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _validation(
            "DaVinci Resolve project-library registry is not valid UTF-8.",
            reason="database_registry_invalid_encoding",
            registry_path=str(path),
        ) from exc
    rows: list[dict[str, str]] = []
    for index, raw_line in enumerate(text.splitlines(), 1):
        line = raw_line.strip()
        if not line or not line.upper().endswith(":*:::DISK"):
            continue
        body = line[: -len(":*:::DISK")]
        name, separator, raw_root = body.partition(":")
        if not separator or not name.strip() or not raw_root.strip():
            raise _validation(
                "DaVinci Resolve project-library registry contains an invalid Disk entry.",
                reason="database_registry_invalid_entry",
                registry_path=str(path),
                line=index,
            )
        rows.append({"name": name.strip(), "root": raw_root.strip(), "line": raw_line})
    return rows


def _registry_state() -> tuple[Path, bytes, list[dict[str, str]]]:
    path = _dblist_path()
    data = _read_registry_bytes(path)
    return path, data, _parse_disk_registry(data, path=path)


def _registry_line(name: str, root: Path) -> str:
    return f"{name}:{root}:*:::DISK"


def _canonical_registry_root(value: str | Path) -> str:
    path = Path(value).expanduser()
    try:
        canonical = path.resolve(strict=False)
    except OSError:
        canonical = Path(os.path.abspath(os.path.normpath(str(path))))
    return os.path.normcase(str(canonical))


def _registry_roots_equal(left: str | Path, right: str | Path) -> bool:
    if _canonical_registry_root(left) == _canonical_registry_root(right):
        return True
    try:
        left_metadata = Path(left).expanduser().stat()
        right_metadata = Path(right).expanduser().stat()
    except OSError:
        return False
    return (left_metadata.st_dev, left_metadata.st_ino) == (
        right_metadata.st_dev,
        right_metadata.st_ino,
    )


def _atomic_write(path: Path, data: bytes) -> None:
    temp = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temp.open("xb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if _supports_posix_ownership():
            temp.chmod(stat.S_IMODE(path.stat().st_mode))
        temp.replace(path)
        if os.name == "posix":
            directory_fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    finally:
        if temp.exists():
            temp.unlink(missing_ok=True)


def _append_registry_entry(path: Path, *, name: str, root: Path) -> None:
    """Append one registry record without replacing or truncating existing data.

    DaVinci Resolve and other processes do not honor CutAgent's private lock. An
    O_APPEND write preserves records appended by another writer, while a
    whole-file rewrite could silently discard them.
    """
    current = _read_registry_bytes(path)
    registry_identity = _path_identity(path)
    rows = _parse_disk_registry(current, path=path)
    for row in rows:
        if row["name"] == name or _registry_roots_equal(row["root"], root):
            raise _validation(
                "Project-library name or target path is already registered.",
                reason="library_registration_collision",
                name=name,
                target_root=str(root),
                conflicting_name=row["name"],
                overwrite_supported=False,
            )
    payload = (b"" if not current or current.endswith(b"\n") else b"\n") + (
        _registry_line(name, root) + "\n"
    ).encode("utf-8")
    descriptor = os.open(path, os.O_WRONLY | os.O_APPEND | int(getattr(os, "O_NOFOLLOW", 0)))
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) != registry_identity or not stat.S_ISREG(opened.st_mode):
            raise _validation(
                "DaVinci Resolve project-library registry identity changed before append.",
                reason="database_registry_identity_changed",
                registry_path=str(path),
            )
        written = os.write(descriptor, payload)
        if written != len(payload):
            raise OSError("short append to DaVinci Resolve project-library registry")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    if _path_identity(path) != registry_identity:
        raise APICallFailed(
            "DaVinci Resolve project-library registry path changed during append.",
            details={"registry_path": str(path), "possible_mutation": True},
            recoverability="manual",
        )
    readback = _read_registry_bytes(path)
    if not readback.startswith(current):
        raise APICallFailed(
            "DaVinci Resolve project-library registry changed destructively during append.",
            details={
                "registry_path": str(path),
                "preserved_prefix": False,
                "possible_mutation": True,
            },
            recoverability="manual",
        )
    readback_rows = _parse_disk_registry(readback, path=path)
    name_matches = [row for row in readback_rows if row["name"] == name]
    root_matches = [
        row
        for row in readback_rows
        if _registry_roots_equal(row["root"], root)
    ]
    exact_matches = [row for row in name_matches if row in root_matches]
    if len(name_matches) != 1 or len(root_matches) != 1 or len(exact_matches) != 1:
        raise APICallFailed(
            "DaVinci Resolve project-library registration append could not be verified.",
            details={
                "name": name,
                "root": str(root),
                "name_collision_count": len(name_matches),
                "root_collision_count": len(root_matches),
                "exact_match_count": len(exact_matches),
                "possible_mutation": True,
            },
            recoverability="manual",
        )


@contextmanager
def _library_lock(registry_path: Path) -> Iterator[None]:
    lock_path = registry_path.parent / _LOCK_NAME
    _assert_no_redirect_chain(lock_path, include_leaf=lock_path.exists(), reason="library_lock_redirect")
    descriptor: int | None = None
    try:
        descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.write(descriptor, f"pid={os.getpid()}\n".encode("ascii"))
    except FileExistsError as exc:
        raise DiskDbLocked(
            "Another CutAgent project-library operation is active.",
            details={
                "reason": "project_library_operation_locked",
                "possible_mutation": False,
                "manual_recovery_required": False,
            },
        ) from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
    try:
        yield
    finally:
        try:
            lock_path.unlink(missing_ok=True)
        except OSError:
            # The operation result must not be rewritten after all durable work
            # has completed solely because a zero-byte coordination file could
            # not be removed. A later invocation still fails closed on the lock.
            pass


def _assert_new_target(name: str, root: Path, rows: list[dict[str, str]]) -> None:
    if root.exists():
        raise _validation(
            "Project-library target already exists; overwrite is not supported.",
            reason="library_target_collision",
            name=name,
            target_root=str(root),
            overwrite_supported=False,
        )
    for row in rows:
        if row["name"] == name or _registry_roots_equal(row["root"], root):
            raise _validation(
                "Project-library name or target path is already registered.",
                reason="library_registration_collision",
                name=name,
                target_root=str(root),
                conflicting_name=row["name"],
                overwrite_supported=False,
            )


def _registered_library(
    name: str, rows: list[dict[str, str]]
) -> tuple[Path, dict[str, str], _RegularIdentity]:
    matches = [row for row in rows if row["name"] == name]
    if len(matches) != 1:
        raise _validation(
            "The explicit Disk project-library name did not resolve uniquely.",
            reason="library_registration_not_unique",
            name=name,
            match_count=len(matches),
        )
    root = _normalize_explicit_path(matches[0]["root"], kind="library_source", must_exist=True)
    _validate_library_root(root, require_databases=True)
    catalog = root / _USER_CATALOG_RELATIVE
    if not catalog.is_file():
        raise _validation(
            "Disk project-library layout is missing its per-user catalog.",
            reason="user_catalog_missing",
            path=str(catalog),
        )
    _catalog, catalog_identity = _validate_bound_user_catalog_identity(catalog)
    return root, matches[0], catalog_identity


def _validate_library_root(root: Path, *, require_databases: bool) -> None:
    if not root.is_dir():
        raise _validation("Disk project-library root is not a directory.", reason="library_root_invalid", path=str(root))
    _assert_owned(root, reason="library_root_wrong_owner")
    resolve_projects = root / "Resolve Projects"
    users = resolve_projects / "Users"
    if not resolve_projects.is_dir() or not users.is_dir():
        raise _validation(
            "Disk project-library layout is missing Resolve Projects/Users.",
            reason="library_layout_incompatible",
            path=str(root),
        )
    databases = [path for path in resolve_projects.rglob("*.db") if path.is_file()]
    if require_databases and not databases:
        raise _validation(
            "Disk project-library contains no database files.",
            reason="library_layout_incompatible",
            path=str(root),
        )


_RESOLVE_SCHEMA_COLUMNS = {
    "CoVersionTable": {"CoVersionTable_id", "DbType"},
    "SM_Project": {"SM_Project_id", "DbType", "ProjectName"},
    "SM_User": {"SM_User_id", "DbType"},
    "Sm2MediaPool": {"Sm2MediaPool_id", "DbType", "SM_Project_id", "RootFolder"},
}
_RESOLVE_SCHEMA_TABLES = set(_RESOLVE_SCHEMA_COLUMNS)
_USER_CATALOG_SCHEMA_COLUMNS = {
    **_RESOLVE_SCHEMA_COLUMNS,
    "SM_User": {
        "SM_User_id",
        "DbType",
        "Id",
        "Name",
        "Status",
        "UserConfig",
        "pView",
        "MediaPool",
    },
    "SM_UserSetup": {"SM_UserSetup_id", "DbType", "ResolveVersion", "LastWorkingProject"},
    "SM_ProjectFolder": {"SM_ProjectFolder_id", "DbType", "User", "ParentFolder", "Name"},
    "SM_Config": {"SM_Config_id", "DbType", "User", "Setup", "SM_User_id"},
    "Gallery::GyView": {"Gallery::GyView_id", "DbType", "SM_User_id", "Gallery::GyGallery_id"},
    "ListMgt::LmVersion": {"ListMgt::LmVersion_id", "DbType", "Name", "Body"},
    "Sm2MpFolder": {"Sm2MpFolder_id", "DbType", "Name", "MediaPool"},
    "database_upgrade_log": {"log_id", "version", "time"},
}


def _validate_user_catalog(path: Path, *, require_empty: bool) -> dict[str, Any]:
    """Validate a private per-user Disk-library catalog.

    General library lookup, backup, and restore accept populated catalogs.
    Only the source used to seed a newly created library must be empty.
    """

    _sqlite_integrity(path, require_resolve_schema=True)
    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=2.0)
        tables = {
            str(row[0])
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
        }
        missing_tables: list[str] = []
        missing_columns: dict[str, list[str]] = {}
        for table, required_columns in _USER_CATALOG_SCHEMA_COLUMNS.items():
            if table not in tables:
                missing_tables.append(table)
                continue
            actual_columns = {
                str(row[1])
                for row in connection.execute(f'PRAGMA table_info("{table}")').fetchall()
            }
            missing = sorted(required_columns - actual_columns)
            if missing:
                missing_columns[table] = missing
        if missing_tables or missing_columns:
            raise _validation(
                "DaVinci Resolve Disk-library user catalog schema is not supported.",
                reason="user_catalog_schema_incompatible",
                missing_tables=sorted(missing_tables),
                missing_columns=missing_columns,
            )
        users = connection.execute(
            'SELECT "SM_User_id", "DbType", "Name", "Status", "MediaPool" FROM "SM_User"'
        ).fetchall()
        user_count = len(users)
        projects = connection.execute(
            'SELECT "SM_Project_id", "DbType", "ProjectName" FROM "SM_Project"'
        ).fetchall()
        project_count = len(projects)
        upgrade_count = int(
            connection.execute(
                "SELECT COUNT(*) FROM database_upgrade_log WHERE version IS NOT NULL AND TRIM(version) <> ''"
            ).fetchone()[0]
        )
    except sqlite3.Error as exc:
        raise _validation(
            "DaVinci Resolve Disk-library user catalog could not be validated.",
            reason="user_catalog_incompatible",
            sqlite_error_type=exc.__class__.__name__,
        ) from exc
    finally:
        if connection is not None:
            connection.close()
    if user_count < 1:
        raise _validation(
            "DaVinci Resolve Disk-library user catalog contains no user.",
            reason="user_catalog_user_missing",
        )
    invalid_users = [
        index
        for index, row in enumerate(users)
        if not str(row[0] or "").strip()
        or row[1] != "SM_User"
        or not str(row[2] or "").strip()
        or str(row[3] or "").upper() != "ACTIVE"
        or not str(row[4] or "").strip()
    ]
    if invalid_users:
        raise _validation(
            "DaVinci Resolve Disk-library user catalog contains an invalid user record.",
            reason="user_catalog_user_incompatible",
            invalid_user_rows=invalid_users,
        )
    invalid_projects = [
        index
        for index, row in enumerate(projects)
        if not str(row[0] or "").strip()
        or row[1] != "SM_Project"
        or not str(row[2] or "").strip()
    ]
    project_ids = [str(row[0]) for row in projects]
    if invalid_projects or len(set(project_ids)) != project_count:
        raise _validation(
            "DaVinci Resolve Disk-library user catalog contains invalid project records.",
            reason="user_catalog_project_incompatible",
            invalid_project_rows=invalid_projects,
            duplicate_project_ids=sorted(
                value for value in set(project_ids) if project_ids.count(value) > 1
            ),
        )
    if require_empty and project_count != 0:
        raise _validation(
            "DaVinci Resolve Disk-library user catalog is not an empty catalog.",
            reason="user_catalog_not_empty",
            project_count=project_count,
        )
    if upgrade_count < 1:
        raise _validation(
            "DaVinci Resolve Disk-library user catalog has no versioned schema history.",
            reason="user_catalog_version_incompatible",
        )
    return {"user_count": user_count, "project_count": project_count}


def _validate_empty_user_catalog(path: Path) -> dict[str, Any]:
    """Validate the empty catalog required only for new-library seeding."""

    return _validate_user_catalog(path, require_empty=True)


def _catalog_project_records(path: Path) -> dict[str, tuple[str, str]]:
    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=2.0)
        rows = connection.execute(
            'SELECT "SM_Project_id", "DbType", "ProjectName" FROM "SM_Project"'
        ).fetchall()
    finally:
        if connection is not None:
            connection.close()
    return {str(row[0]): (str(row[1]), str(row[2])) for row in rows}


def _validate_project_database_record(path: Path) -> tuple[str, str, str]:
    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=2.0)
        rows = connection.execute(
            'SELECT "SM_Project_id", "DbType", "ProjectName" FROM "SM_Project"'
        ).fetchall()
    except sqlite3.Error as exc:
        raise _validation(
            "DaVinci Resolve project database record could not be validated.",
            reason="project_database_record_incompatible",
            sqlite_error_type=exc.__class__.__name__,
        ) from exc
    finally:
        if connection is not None:
            connection.close()
    if len(rows) != 1:
        raise _validation(
            "DaVinci Resolve project database must contain exactly one project record.",
            reason="project_database_record_incompatible",
            project_record_count=len(rows),
        )
    project_id, database_type, project_name = (str(value or "").strip() for value in rows[0])
    if not project_id or database_type != "SM_Project" or not project_name:
        raise _validation(
            "DaVinci Resolve project database contains an invalid project record.",
            reason="project_database_record_incompatible",
            project_id=project_id or None,
            database_type=database_type or None,
            project_name=project_name or None,
        )
    return project_id, database_type, project_name


def _with_bound_regular(path: Path, callback: Any, *, return_identity: bool = False) -> Any:
    """Run ``callback`` against the exact opened regular-file identity."""

    _assert_no_redirect_chain(path, include_leaf=True, reason="library_entry_redirect")
    _assert_owned(path, reason="library_entry_wrong_owner")
    before = path.stat(follow_symlinks=False)
    if not stat.S_ISREG(before.st_mode):
        raise _validation(
            "Project-library source entry is not a regular file.",
            reason="library_entry_unsupported",
            path=str(path),
        )
    flags = os.O_RDONLY | int(getattr(os, "O_NOFOLLOW", 0))
    descriptor = os.open(path, flags)
    try:
        opened = os.fstat(descriptor)
        opened_identity = (opened.st_dev, opened.st_ino)
        if opened_identity != (before.st_dev, before.st_ino) or not stat.S_ISREG(opened.st_mode):
            raise _validation(
                "Project-library source identity changed while opening it.",
                reason="library_entry_identity_changed",
                path=str(path),
            )
        if os.name != "posix":
            raise _validation(
                "This platform does not yet have a proven descriptor-bound SQLite catalog route.",
                reason="sqlite_platform_binding_unavailable",
                platform=sys.platform,
            )
        result = callback(Path(f"/dev/fd/{descriptor}"))
        after = path.stat(follow_symlinks=False)
        if (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns) != (
            opened.st_dev,
            opened.st_ino,
            opened.st_size,
            opened.st_mtime_ns,
            opened.st_ctime_ns,
        ):
            raise _validation(
                "Project-library source identity or contents changed while it was open.",
                reason="library_entry_identity_changed",
                path=str(path),
            )
        identity = (
            int(opened.st_dev),
            int(opened.st_ino),
            int(opened.st_size),
            int(opened.st_mtime_ns),
            int(opened.st_ctime_ns),
        )
        return (result, identity) if return_identity else result
    finally:
        os.close(descriptor)


def _validate_bound_empty_user_catalog(path: Path) -> dict[str, Any]:
    return _with_bound_regular(path, _validate_empty_user_catalog)


def _validate_bound_empty_user_catalog_identity(
    path: Path,
) -> tuple[dict[str, Any], _RegularIdentity]:
    """Validate and return the identity of the same opened catalog descriptor."""

    return _with_bound_regular(path, _validate_empty_user_catalog, return_identity=True)


def _validate_bound_user_catalog(path: Path) -> dict[str, Any]:
    return _with_bound_regular(path, lambda bound: _validate_user_catalog(bound, require_empty=False))


def _validate_bound_user_catalog_identity(
    path: Path,
) -> tuple[dict[str, Any], _RegularIdentity]:
    """Validate a populated-or-empty catalog and bind the exact descriptor identity."""

    return _with_bound_regular(
        path,
        lambda bound: _validate_user_catalog(bound, require_empty=False),
        return_identity=True,
    )


def _walk_regular_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for current, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        _assert_owned(current_path, reason="library_entry_wrong_owner")
        for dirname in list(dirnames):
            child = current_path / dirname
            if _is_redirect(child):
                raise _validation(
                    "Project-library contents must not contain symbolic links or junctions.",
                    reason="library_entry_redirect",
                    path=str(child),
                )
            if not child.is_dir():
                raise _validation(
                    "Project-library contains an unsupported filesystem entry.",
                    reason="library_entry_unsupported",
                    path=str(child),
                )
            _assert_owned(child, reason="library_entry_wrong_owner")
        for filename in filenames:
            child = current_path / filename
            if _is_redirect(child) or not child.is_file():
                raise _validation(
                    "Project-library contains an unsupported or redirected file.",
                    reason="library_entry_unsupported",
                    path=str(child),
                )
            _assert_owned(child, reason="library_entry_wrong_owner")
            files.append(child)
    return sorted(files, key=lambda item: item.relative_to(root).as_posix())


def _bind_exact_regular_inventory(
    root: Path,
    expected_paths: set[Path],
    *,
    validated_bindings: dict[Path, _RegularIdentity] | None = None,
) -> dict[Path, _RegularIdentity]:
    files = _walk_regular_files(root)
    actual_paths = {path.relative_to(root) for path in files}
    if actual_paths != expected_paths:
        raise _validation(
            "Private project-library staging inventory changed before publication.",
            reason="internal_stage_inventory_changed",
            undeclared=sorted(path.as_posix() for path in actual_paths - expected_paths),
            missing=sorted(path.as_posix() for path in expected_paths - actual_paths),
        )
    retained = dict(validated_bindings or {})
    bindings: dict[Path, _RegularIdentity] = {}
    for path in files:
        relative = path.relative_to(root)
        _result, identity = _with_bound_regular(
            path, lambda _bound: None, return_identity=True
        )
        if relative in retained and identity != retained[relative]:
            raise _validation(
                "Private project-library staging changed after validation.",
                reason="internal_stage_identity_changed",
                relative_path=relative.as_posix(),
            )
        bindings[relative] = identity
    return bindings


def _backup_source_files(root: Path) -> list[Path]:
    return [
        path
        for path in _walk_regular_files(root)
        if path.name != LIBRARY_MARKER
        and not path.name.endswith(("-wal", "-shm", "-journal"))
    ]


def _assert_backup_source_inventory(
    root: Path,
    bindings: dict[Path, _RegularIdentity],
) -> None:
    _assert_regular_bindings(bindings, possible_mutation=False)
    expected = {path.relative_to(root) for path in bindings}
    actual = {path.relative_to(root) for path in _backup_source_files(root)}
    if actual != expected:
        raise APICallFailed(
            "Project-library source inventory changed during backup.",
            details={
                "added": sorted(path.as_posix() for path in actual - expected),
                "removed": sorted(path.as_posix() for path in expected - actual),
                "possible_mutation": False,
            },
            recoverability="retryable",
        )
    _assert_regular_bindings(bindings, possible_mutation=False)


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _sqlite_integrity(path: Path, *, require_resolve_schema: bool | None = None) -> dict[str, Any]:
    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=2.0)
        integrity = connection.execute("PRAGMA integrity_check").fetchone()
        if not integrity or str(integrity[0]).lower() != "ok":
            raise _validation(
                "Project-library SQLite database failed integrity validation.",
                reason="sqlite_integrity_failed",
                relative_name=path.name,
                integrity_result=integrity[0] if integrity else None,
            )
        tables = {
            str(row[0])
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
        }
        schema_required = path.name in {"Project.db", "User.db"} if require_resolve_schema is None else require_resolve_schema
        missing_tables = sorted(_RESOLVE_SCHEMA_TABLES - tables)
        if schema_required and missing_tables:
            raise _validation(
                "Project-library SQLite database does not match the DaVinci Resolve Disk-library schema.",
                reason="sqlite_resolve_schema_incompatible",
                relative_name=path.name,
                missing_tables=missing_tables,
            )
        if schema_required:
            missing_columns: dict[str, list[str]] = {}
            for table, required_columns in _RESOLVE_SCHEMA_COLUMNS.items():
                actual_columns = {
                    str(row[1])
                    for row in connection.execute(f'PRAGMA table_info("{table}")').fetchall()
                }
                missing = sorted(required_columns - actual_columns)
                if missing:
                    missing_columns[table] = missing
            if missing_columns:
                raise _validation(
                    "Project-library SQLite database has incompatible DaVinci Resolve table structure.",
                    reason="sqlite_resolve_schema_incompatible",
                    relative_name=path.name,
                    missing_columns=missing_columns,
                )
        return {
            "application_id": int(connection.execute("PRAGMA application_id").fetchone()[0]),
            "user_version": int(connection.execute("PRAGMA user_version").fetchone()[0]),
        }
    except sqlite3.Error as exc:
        raise _validation(
            "Project-library SQLite database could not be opened.",
            reason="sqlite_incompatible",
            relative_name=path.name,
            sqlite_error_type=exc.__class__.__name__,
        ) from exc
    finally:
        if connection is not None:
            connection.close()


def _sqlite_snapshot(source: Path, destination: Path) -> dict[str, Any]:
    source_connection: sqlite3.Connection | None = None
    destination_connection: sqlite3.Connection | None = None
    try:
        source_connection = sqlite3.connect(f"file:{source}?mode=ro", uri=True, timeout=5.0)
        destination_connection = sqlite3.connect(destination)
        source_connection.backup(destination_connection)
        destination_connection.commit()
    except sqlite3.Error as exc:
        raise APICallFailed(
            "Failed to create a consistent project-library SQLite snapshot.",
            details={"source_name": source.name, "error_type": exc.__class__.__name__},
            recoverability="retryable",
        ) from exc
    finally:
        if destination_connection is not None:
            destination_connection.close()
        if source_connection is not None:
            source_connection.close()
    return _sqlite_integrity(destination)


def _copy_bound_regular(
    source: Path,
    destination: Path,
    *,
    sqlite_file: bool,
    expected_identity: _RegularIdentity | None = None,
) -> dict[str, Any] | None:
    """Copy the exact regular-file identity checked by this invocation.

    On POSIX, O_NOFOLLOW plus `/dev/fd` binds SQLite's online backup to the
    opened inode. On other platforms, pre/open/post identities still fail
    closed if the path changes while the handle is held.
    """
    _assert_no_redirect_chain(source, include_leaf=True, reason="library_entry_redirect")
    _assert_owned(source, reason="library_entry_wrong_owner")
    before = source.stat(follow_symlinks=False)
    if not stat.S_ISREG(before.st_mode):
        raise _validation(
            "Project-library source entry is not a regular file.",
            reason="library_entry_unsupported",
            path=str(source),
        )
    flags = os.O_RDONLY | int(getattr(os, "O_NOFOLLOW", 0))
    descriptor = os.open(source, flags)
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino) or not stat.S_ISREG(opened.st_mode):
            raise _validation(
                "Project-library source identity changed while opening it.",
                reason="library_entry_identity_changed",
                path=str(source),
            )
        opened_identity = (
            int(opened.st_dev),
            int(opened.st_ino),
            int(opened.st_size),
            int(opened.st_mtime_ns),
            int(opened.st_ctime_ns),
        )
        if expected_identity is not None and opened_identity != expected_identity:
            raise _validation(
                "Project-library source changed after descriptor-backed validation.",
                reason="library_entry_identity_changed",
                path=str(source),
            )
        destination.parent.mkdir(parents=True, exist_ok=True)
        if sqlite_file:
            if os.name != "posix":
                raise _validation(
                    "This platform does not yet have a proven descriptor-bound SQLite snapshot route.",
                    reason="sqlite_platform_binding_unavailable",
                    platform=sys.platform,
                )
            bound_source = Path(f"/dev/fd/{descriptor}")
            result = _sqlite_snapshot(bound_source, destination)
        else:
            with os.fdopen(os.dup(descriptor), "rb") as source_handle, destination.open("xb") as destination_handle:
                shutil.copyfileobj(source_handle, destination_handle, length=1024 * 1024)
                destination_handle.flush()
                os.fsync(destination_handle.fileno())
            os.chmod(destination, stat.S_IMODE(opened.st_mode))
            result = None
        after = source.stat(follow_symlinks=False)
        if (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns) != (
            opened.st_dev,
            opened.st_ino,
            opened.st_size,
            opened.st_mtime_ns,
            opened.st_ctime_ns,
        ):
            raise APICallFailed(
                "Project-library source changed during its bound copy.",
                details={"path": str(source)},
                recoverability="retryable",
            )
        return result
    finally:
        os.close(descriptor)


def _safe_relative(raw: str) -> Path:
    pure = PurePosixPath(str(raw or ""))
    if not pure.parts or pure.is_absolute() or ".." in pure.parts or "." in pure.parts:
        raise _validation(
            "Backup manifest contains an unsafe relative path.",
            reason="backup_manifest_path_traversal",
            relative_path=raw,
        )
    return Path(*pure.parts)


def _manifest_identity(files: list[dict[str, Any]]) -> str:
    canonical = json.dumps(
        [{"path": row["path"], "sha256": row["sha256"], "size": row["size"]} for row in files],
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(canonical).hexdigest()}"


def inspect_backup(path: str) -> dict[str, Any]:
    root = _normalize_explicit_path(path, kind="backup_source", must_exist=True)
    if not root.is_dir():
        raise _validation("Project-library backup source is not a directory.", reason="backup_source_not_directory", path=str(root))
    manifest_path = root / BACKUP_MANIFEST
    payload_root = root / BACKUP_PAYLOAD
    _assert_no_redirect_chain(manifest_path, include_leaf=True, reason="backup_manifest_redirect")
    _assert_no_redirect_chain(payload_root, include_leaf=True, reason="backup_payload_redirect")
    if not manifest_path.is_file() or not payload_root.is_dir():
        raise _validation(
            "Project-library backup is missing its manifest or payload.",
            reason="backup_layout_invalid",
            backup_path=str(root),
        )
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _validation(
            "Project-library backup manifest is corrupt.",
            reason="backup_manifest_corrupt",
            backup_path=str(root),
            error_type=exc.__class__.__name__,
        ) from exc
    required = {
        "schema_version": BACKUP_SCHEMA_VERSION,
        "library_format": LIBRARY_FORMAT,
        "database_type": "Disk",
        "source_platform": sys.platform,
    }
    for key, expected in required.items():
        if manifest.get(key) != expected:
            raise _validation(
                "Project-library backup is incompatible with this CutAgent runtime.",
                reason="backup_incompatible",
                field=key,
                expected=expected,
                actual=manifest.get(key),
            )
    rows = manifest.get("files")
    if not isinstance(rows, list) or not rows:
        raise _validation("Project-library backup has no file inventory.", reason="backup_manifest_corrupt")
    actual_paths = {file.relative_to(payload_root).as_posix() for file in _walk_regular_files(payload_root)}
    declared_paths: set[str] = set()
    database_count = 0
    catalog_identity: _RegularIdentity | None = None
    file_identities: dict[Path, _RegularIdentity] = {}
    catalog_projects: dict[str, tuple[str, str]] | None = None
    project_records: dict[Path, tuple[str, str, str]] = {}
    catalog_relative = _USER_CATALOG_RELATIVE.as_posix()
    for row in rows:
        if not isinstance(row, dict):
            raise _validation("Project-library backup file inventory is corrupt.", reason="backup_manifest_corrupt")
        relative = _safe_relative(str(row.get("path") or ""))
        relative_text = relative.as_posix()
        if relative_text in declared_paths:
            raise _validation("Project-library backup contains duplicate file identities.", reason="backup_manifest_duplicate", relative_path=relative_text)
        declared_paths.add(relative_text)
        candidate = payload_root / relative
        if not candidate.is_file() or _is_redirect(candidate):
            raise _validation("Project-library backup payload is incomplete.", reason="backup_payload_missing", relative_path=relative_text)
        expected_size = row.get("size")
        expected_sqlite = candidate.suffix.lower() in _SQLITE_SUFFIXES
        if bool(row.get("sqlite")) != expected_sqlite:
            raise _validation(
                "Project-library backup SQLite classification does not match its file type.",
                reason="backup_manifest_corrupt",
                relative_path=relative_text,
            )
        is_catalog = relative_text == catalog_relative
        (bound_result, bound_identity) = _with_bound_regular(
            candidate,
            lambda bound: {
                "sha256": _hash_file(bound),
                "sqlite": (
                    _sqlite_integrity(
                        bound,
                        require_resolve_schema=candidate.name in {"Project.db", "User.db"},
                    )
                    if expected_sqlite
                    else None
                ),
                "catalog": (
                    _validate_user_catalog(bound, require_empty=False) if is_catalog else None
                ),
                "catalog_projects": _catalog_project_records(bound) if is_catalog else None,
                "project_record": (
                    _validate_project_database_record(bound)
                    if candidate.name == "Project.db"
                    else None
                ),
            },
            return_identity=True,
        )
        if not isinstance(expected_size, int) or bound_identity[2] != expected_size:
            raise _validation("Project-library backup file size does not match its manifest.", reason="backup_integrity_mismatch", relative_path=relative_text)
        if bound_result["sha256"] != row.get("sha256"):
            raise _validation("Project-library backup hash does not match its manifest.", reason="backup_integrity_mismatch", relative_path=relative_text)
        if expected_sqlite:
            database_count += 1
        if is_catalog:
            catalog_identity = bound_identity
            catalog_projects = bound_result["catalog_projects"]
        if bound_result["project_record"] is not None:
            project_records[relative] = bound_result["project_record"]
        file_identities[relative] = bound_identity
    if declared_paths != actual_paths:
        raise _validation(
            "Project-library backup payload contains untracked or missing files.",
            reason="backup_inventory_mismatch",
            undeclared=sorted(actual_paths - declared_paths),
            missing=sorted(declared_paths - actual_paths),
        )
    identity = _manifest_identity(rows)
    if identity != manifest.get("backup_id"):
        raise _validation("Project-library backup identity does not match its contents.", reason="backup_identity_mismatch")
    if database_count < 1:
        raise _validation("Project-library backup contains no validated SQLite databases.", reason="backup_incompatible")
    if catalog_relative not in declared_paths:
        raise _validation(
            "Project-library backup is missing its per-user catalog.",
            reason="user_catalog_missing",
        )
    if catalog_identity is None:
        raise _validation(
            "Project-library backup catalog could not be bound to its manifest.",
            reason="backup_integrity_mismatch",
            relative_path=catalog_relative,
        )
    if catalog_projects is None:
        raise _validation(
            "Project-library backup catalog project records could not be validated.",
            reason="backup_integrity_mismatch",
            relative_path=catalog_relative,
        )
    project_prefix = ("Resolve Projects", "Users", "guest", "Projects")
    records_by_id: dict[str, tuple[str, str]] = {}
    for relative, (project_id, database_type, project_name) in project_records.items():
        if (
            relative.parts[: len(project_prefix)] != project_prefix
            or len(relative.parts) < len(project_prefix) + 2
            or relative.name != "Project.db"
            or relative.parent.name != project_name
        ):
            raise _validation(
                "Project-library backup project path does not match its project record.",
                reason="project_database_record_incompatible",
                relative_path=relative.as_posix(),
                project_name=project_name,
            )
        if project_id in records_by_id:
            raise _validation(
                "Project-library backup contains duplicate project database identities.",
                reason="project_database_record_incompatible",
                project_id=project_id,
            )
        records_by_id[project_id] = (database_type, project_name)
    # Native Disk libraries can leave User.db's SM_Project table empty while
    # enumerating saved projects from their individual Project.db files. Keep
    # those databases intact; a populated catalog must still match exactly.
    if catalog_projects and records_by_id != catalog_projects:
        raise _validation(
            "Project-library backup project databases do not match the user catalog.",
            reason="project_database_catalog_mismatch",
            catalog_project_ids=sorted(catalog_projects),
            database_project_ids=sorted(records_by_id),
        )
    _assert_regular_bindings(
        {payload_root / relative: identity for relative, identity in file_identities.items()},
        possible_mutation=False,
    )
    final_paths = {
        file.relative_to(payload_root).as_posix()
        for file in _walk_regular_files(payload_root)
    }
    if final_paths != declared_paths:
        raise _validation(
            "Project-library backup payload inventory changed during inspection.",
            reason="backup_inventory_mismatch",
            undeclared=sorted(final_paths - declared_paths),
            missing=sorted(declared_paths - final_paths),
        )
    _assert_regular_bindings(
        {payload_root / relative: identity for relative, identity in file_identities.items()},
        possible_mutation=False,
    )
    return {
        "root": root,
        "payload_root": payload_root,
        "manifest": manifest,
        "catalog_identity": catalog_identity,
        "file_identities": file_identities,
    }


def _runtime_database(conn: Any) -> dict[str, Any]:
    getter = getattr(conn.project_manager, "GetCurrentDatabase", None)
    if not callable(getter):
        raise _validation(
            "DaVinci Resolve cannot provide exact current project-library identity.",
            reason="current_library_identity_unavailable",
        )
    current = getter()
    if not isinstance(current, dict) or not str(current.get("DbName") or "").strip() or not str(current.get("DbType") or "").strip():
        raise _validation(
            "DaVinci Resolve returned incomplete current project-library identity.",
            reason="current_library_identity_unavailable",
        )
    return {key: current[key] for key in ("DbType", "DbName", "IpAddress") if key in current}


def project_library_inventory_identity(conn: Any) -> dict[str, Any]:
    """Return one exact, bounded native project-library enumeration.

    The public scripting API owns cross-library identity.  Filesystem-backed
    Disk operations add their stricter registry/catalog checks when they run,
    but signed admission must first bind the complete API enumeration instead
    of selecting the first matching display name.
    """

    current = _runtime_database(conn)
    getter = getattr(conn.project_manager, "GetDatabaseList", None)
    if not callable(getter):
        raise _validation(
            "DaVinci Resolve cannot enumerate exact project-library identities.",
            reason="library_inventory_unavailable",
        )
    raw_rows = getter()
    if not isinstance(raw_rows, list) or len(raw_rows) > 1024:
        raise _validation(
            "DaVinci Resolve returned an invalid or unbounded project-library inventory.",
            reason="library_inventory_invalid",
            row_count=len(raw_rows) if isinstance(raw_rows, list) else None,
        )
    rows: list[dict[str, str]] = []
    for raw in raw_rows:
        if not isinstance(raw, dict):
            raise _validation(
                "DaVinci Resolve returned a malformed project-library identity.",
                reason="library_inventory_invalid",
            )
        db_type = raw.get("DbType")
        db_name = raw.get("DbName")
        if db_type not in {"Disk", "PostgreSQL"} or not isinstance(db_name, str) or not db_name.strip():
            raise _validation(
                "DaVinci Resolve returned an incomplete project-library identity.",
                reason="library_inventory_invalid",
            )
        row = {"DbType": db_type, "DbName": db_name}
        if db_type == "PostgreSQL":
            address = raw.get("IpAddress")
            if not isinstance(address, str) or not address.strip():
                raise _validation(
                    "DaVinci Resolve omitted a PostgreSQL project-library address.",
                    reason="library_inventory_invalid",
                    database_name=db_name,
                )
            row["IpAddress"] = address
        rows.append(row)
    rows.sort(
        key=lambda row: json.dumps(
            row, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        ).encode("utf-8")
    )
    canonical_rows = [
        json.dumps(row, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        for row in rows
    ]
    if len(set(canonical_rows)) != len(rows):
        raise _validation(
            "DaVinci Resolve returned duplicate project-library identities.",
            reason="library_inventory_ambiguous",
        )
    if sum(1 for row in rows if _database_matches(row, current) and _database_matches(current, row)) != 1:
        raise _validation(
            "The current project library is not represented exactly once in the native inventory.",
            reason="current_library_inventory_mismatch",
            current=current,
        )
    return {"current_database": current, "databases": rows}


def _optional_name(target: Any) -> str | None:
    getter = getattr(target, "GetName", None)
    if not callable(getter):
        return None
    value = getter()
    return str(value) if value not in (None, "") else None


def _optional_id(target: Any) -> str | None:
    for name in ("GetUniqueId", "GetUniqueID", "GetId", "GetID"):
        getter = getattr(target, name, None)
        if callable(getter):
            value = getter()
            if value not in (None, ""):
                return str(value)
    return None


def _current_page(conn: Any) -> str:
    getter = getattr(getattr(conn, "resolve", None), "GetCurrentPage", None)
    if not callable(getter):
        raise _validation(
            "DaVinci Resolve cannot provide exact current-page readback for context restoration.",
            reason="current_page_readback_unavailable",
        )
    value = getter()
    if not isinstance(value, str) or not value.strip():
        raise _validation(
            "DaVinci Resolve returned an invalid current-page identity.",
            reason="current_page_identity_unavailable",
        )
    return value


def _timeline_playhead(timeline: Any, *, required: bool) -> str | None:
    if timeline is None:
        return None
    getter = getattr(timeline, "GetCurrentTimecode", None)
    if not callable(getter):
        if required:
            raise _validation(
                "DaVinci Resolve cannot provide exact playhead readback for context restoration.",
                reason="current_playhead_readback_unavailable",
            )
        return None
    value = getter()
    if not isinstance(value, str) or not value.strip():
        if required:
            raise _validation(
                "DaVinci Resolve returned an invalid playhead identity.",
                reason="current_playhead_identity_unavailable",
            )
        return None
    return value


def _direct_root_project_id(library_root: Path, project_name: str) -> str | None:
    """Read a project's stable identity only from the registered direct root."""

    projects_root = library_root / "Resolve Projects" / "Users" / "guest" / "Projects"
    if not projects_root.is_dir() or _is_redirect(projects_root):
        return None
    with os.scandir(projects_root) as entries:
        matches = [entry for entry in entries if entry.name == project_name]
    if len(matches) != 1 or matches[0].is_symlink() or not matches[0].is_dir(follow_symlinks=False):
        return None
    project_db = Path(matches[0].path) / "Project.db"
    if _is_redirect(project_db) or not project_db.is_file():
        return None
    _assert_owned(project_db, reason="current_project_root_identity_wrong_owner")
    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(f"file:{project_db}?mode=ro", uri=True, timeout=2.0)
        rows = connection.execute(
            "SELECT SM_Project_id, ProjectName FROM SM_Project WHERE ProjectName = ?",
            (project_name,),
        ).fetchall()
    finally:
        if connection is not None:
            connection.close()
    if len(rows) != 1 or not str(rows[0][0] or "").strip() or str(rows[0][1] or "") != project_name:
        return None
    return str(rows[0][0])


def current_project_folder_identity(conn: Any) -> dict[str, Any] | None:
    """Resolve the exact browsed Disk-library folder and child inventory.

    The Project Manager API exposes only a leaf folder label.  The on-disk
    hierarchy plus the complete API folder/project listing disambiguates that
    label without assuming the open project lives in the browsed folder.
    Non-Disk libraries and ambiguous layouts deliberately return no identity.
    """

    try:
        database = _runtime_database(conn)
        if database.get("DbType") != "Disk":
            return None
        _registry_path, _registry_bytes, rows = _registry_state()
        library_root, _registered_row, _catalog_identity = _registered_library(
            str(database["DbName"]), rows
        )
        projects_root = (
            library_root / "Resolve Projects" / "Users" / "guest" / "Projects"
        )
        if not projects_root.is_dir() or _is_redirect(projects_root):
            return None
        def directory_identity(target: Path) -> str:
            _assert_no_redirect_chain(
                target, include_leaf=True, reason="current_project_folder_identity_redirect"
            )
            _assert_owned(target, reason="current_project_folder_identity_wrong_owner")
            target_stat = target.stat(follow_symlinks=False)
            if not stat.S_ISDIR(target_stat.st_mode):
                raise ValueError("Project-folder inventory contains a non-directory.")
            return f"{target_stat.st_dev}:{target_stat.st_ino}"

        inventory: list[dict[str, Any]] = []
        pending: list[tuple[Path, tuple[str, ...]]] = [(projects_root, ("Projects",))]
        visited = 0
        while pending:
            folder, path_parts = pending.pop()
            visited += 1
            if visited > 100_000:
                return None
            native_id = directory_identity(folder)
            child_folders: list[dict[str, str]] = []
            projects: list[str] = []
            with os.scandir(folder) as entries:
                children = sorted(
                    (entry for entry in entries if entry.is_dir(follow_symlinks=False)),
                    key=lambda entry: entry.name,
                )
            for entry in children:
                child = Path(entry.path)
                project_db = child / "Project.db"
                if project_db.is_file() and not _is_redirect(project_db):
                    projects.append(entry.name)
                    continue
                child_identity = directory_identity(child)
                child_path_parts = (*path_parts, entry.name)
                child_folders.append(
                    {
                        "name": entry.name,
                        "path": " / ".join(child_path_parts),
                        "native_id": child_identity,
                    }
                )
                pending.append((child, child_path_parts))
            inventory.append(
                {
                    "directory": folder,
                    "path_parts": path_parts,
                    "native_id": native_id,
                    "filesystem_path": str(folder),
                    "children": child_folders,
                    "projects": sorted(projects),
                }
            )

        raw_current = conn.project_manager.GetCurrentFolder()
        listed_folders = conn.project_manager.GetFolderListInCurrentFolder()
        listed_projects = conn.project_manager.GetProjectListInCurrentFolder()
        if not isinstance(raw_current, str) or not isinstance(listed_folders, list) or not isinstance(listed_projects, list):
            return None
        if not all(isinstance(item, str) for item in [*listed_folders, *listed_projects]):
            return None
        api_folders = sorted(listed_folders)
        api_projects = sorted(listed_projects)
        matches = [
            candidate
            for candidate in inventory
            if (
                (candidate["path_parts"] == ("Projects",) and raw_current.strip().casefold() in {"", "root", "projects"})
                or candidate["path_parts"][-1] == raw_current
            )
            and [child["name"] for child in candidate["children"]] == api_folders
            and candidate["projects"] == api_projects
        ]
        if len(matches) != 1:
            return None
        current = matches[0]
        open_project_native_id = None
        open_project = getattr(conn, "project", None)
        open_project_name = None
        open_project_id = None
        if open_project is not None:
            try:
                open_project_name = open_project.GetName()
            except Exception:
                open_project_name = None
            open_project_id = _optional_id(open_project)
        if (
            isinstance(open_project_name, str)
            and open_project_name in current["projects"]
            and isinstance(open_project_id, str)
            and open_project_id
        ):
            project_db = current["directory"] / open_project_name / "Project.db"
            if project_db.is_file() and not _is_redirect(project_db):
                _assert_owned(project_db, reason="current_project_folder_identity_wrong_owner")
                connection: sqlite3.Connection | None = None
                try:
                    connection = sqlite3.connect(f"file:{project_db}?mode=ro", uri=True, timeout=2.0)
                    project_rows = connection.execute(
                        "SELECT SM_Project_id, ProjectName FROM SM_Project WHERE ProjectName = ?",
                        (open_project_name,),
                    ).fetchall()
                finally:
                    if connection is not None:
                        connection.close()
                if (
                    len(project_rows) == 1
                    and str(project_rows[0][0] or "") == open_project_id
                    and str(project_rows[0][1] or "") == open_project_name
                ):
                    open_project_native_id = open_project_id
        ancestor_paths = [" / ".join(current["path_parts"][:index]) for index in range(1, len(current["path_parts"]) + 1)]
        by_path = {" / ".join(candidate["path_parts"]): candidate for candidate in inventory}
        project_records: list[dict[str, str]] = []
        current_filesystem_path = Path(current["filesystem_path"])
        for project_name in current["projects"]:
            project_db = current_filesystem_path / project_name / "Project.db"
            _assert_owned(project_db, reason="current_project_folder_identity_wrong_owner")
            project_id, _database_type, database_project_name = _validate_project_database_record(project_db)
            if database_project_name != project_name:
                return None
            project_records.append({"name": project_name, "native_id": project_id})

        return {
            "path": " / ".join(current["path_parts"]),
            "native_id": current["native_id"],
            "open_project_native_id": open_project_native_id,
            "children": current["children"],
            "projects": current["projects"],
            "project_records": sorted(project_records, key=lambda row: row["name"].encode("utf-8")),
            "ancestors": [
                {"path": path, "native_id": by_path[path]["native_id"]}
                for path in ancestor_paths
            ],
        }
    except Exception:
        return None


def current_project_folder_project_identity(conn: Any, name: str) -> str | None:
    """Return one verified Disk `SM_Project_id` in the exact browsed folder."""

    folder = current_project_folder_identity(conn)
    if not isinstance(folder, dict):
        return None
    matches = [
        row.get("native_id") for row in folder.get("project_records", [])
        if isinstance(row, dict) and row.get("name") == name
    ]
    return str(matches[0]) if len(matches) == 1 and matches[0] else None


def _canonical_root_project_folder(
    conn: Any,
    raw_folder: Any,
    *,
    database: dict[str, Any],
    project_name: str | None,
    project_id: str | None,
    timeline_id: str | None,
    timeline_present: bool,
) -> tuple[str | None, dict[str, Any]]:
    """Return the canonical root identity only from exact live evidence.

    Some DaVinci Resolve runtimes expose the project-library root as the
    empty string. An arbitrary falsey value is not sufficient: the blank
    representation is accepted only when read-only project-manager evidence
    binds it to the exact current project and timeline context.
    """

    if isinstance(raw_folder, str):
        stripped = raw_folder.strip()
        if stripped.casefold() in {"root", "projects"}:
            return "root", {"representation": "named_root", "current_path": "Projects"}

    evidence: dict[str, Any] = {"representation": "unproven", "raw_type": type(raw_folder).__name__}
    if not isinstance(raw_folder, str) or raw_folder != "":
        return None, evidence

    manager = conn.project_manager
    goto_root = getattr(manager, "GotoRootFolder", None)
    list_projects = getattr(manager, "GetProjectListInCurrentFolder", None)
    get_current_project = getattr(manager, "GetCurrentProject", None)
    if not callable(goto_root) or not callable(list_projects) or not callable(get_current_project):
        evidence["root_api_available"] = callable(goto_root)
        evidence["project_list_available"] = callable(list_projects)
        evidence["current_project_readback_available"] = callable(get_current_project)
        return None, evidence
    if not project_name or not project_id:
        evidence["exact_project_context_available"] = False
        return None, evidence
    if database.get("DbType") != "Disk" or not str(database.get("DbName") or "").strip():
        evidence["direct_disk_root_available"] = False
        return None, evidence

    try:
        projects = list_projects()
        current_project = get_current_project()
        current_project_id = _optional_id(current_project) if current_project is not None else None
        current_timeline_getter = getattr(current_project, "GetCurrentTimeline", None)
        if current_project is not None and not callable(current_timeline_getter):
            evidence["current_timeline_readback_available"] = False
            return None, evidence
        current_timeline = current_timeline_getter() if callable(current_timeline_getter) else None
        current_timeline_id = _optional_id(current_timeline) if current_timeline is not None else None
        _registry_path, _registry_bytes, rows = _registry_state()
        library_root, _registered_row, _catalog_identity = _registered_library(
            str(database["DbName"]), rows
        )
        direct_root_project_id = _direct_root_project_id(library_root, project_name)
    except Exception as exc:
        evidence["readback_error_type"] = exc.__class__.__name__
        return None, evidence

    if not isinstance(projects, list):
        evidence["project_list_type"] = type(projects).__name__
        return None, evidence
    matching_projects = sum(1 for item in projects if isinstance(item, str) and item == project_name)
    exact_timeline = (current_timeline is not None) == timeline_present and (
        not timeline_present or bool(timeline_id and current_timeline_id == timeline_id)
    )
    evidence.update(
        {
            "root_api_available": True,
            "project_list_available": True,
            "current_project_readback_available": True,
            "exact_project_context_available": current_project_id == project_id,
            "current_project_list_matches": matching_projects,
            "exact_timeline_context_available": exact_timeline,
            "direct_disk_root_available": True,
            "direct_root_project_identity_matches": direct_root_project_id == project_id,
        }
    )
    if (
        current_project_id != project_id
        or matching_projects != 1
        or not exact_timeline
        or direct_root_project_id != project_id
    ):
        return None, evidence
    return "root", {**evidence, "representation": "proven_blank_root", "current_path": "Projects"}


def _capture_context(conn: Any, *, save_project: bool = True) -> dict[str, Any]:
    database = _runtime_database(conn)
    page = _current_page(conn)
    project_getter = getattr(conn.project_manager, "GetCurrentProject", None)
    if not callable(project_getter):
        raise _validation(
            "DaVinci Resolve cannot provide exact current-project readback for context restoration.",
            reason="current_project_readback_unavailable",
        )
    project = project_getter()
    project_name = _optional_name(project) if project is not None else None
    project_id = _optional_id(project) if project is not None else None
    if project is not None and (not project_name or not project_id):
        raise _validation(
            "DaVinci Resolve cannot provide an exact current-project identity for context restoration.",
            reason="current_project_identity_unavailable",
            project_name=project_name,
        )
    timeline_getter = getattr(project, "GetCurrentTimeline", None) if project is not None else None
    if project is not None and not callable(timeline_getter):
        raise _validation(
            "DaVinci Resolve cannot provide exact current-timeline readback for context restoration.",
            reason="current_timeline_readback_unavailable",
            project_name=project_name,
        )
    timeline = timeline_getter() if callable(timeline_getter) else None
    timeline_name = _optional_name(timeline) if timeline is not None else None
    timeline_id = _optional_id(timeline) if timeline is not None else None
    playhead = _timeline_playhead(timeline, required=timeline is not None)
    folder_getter = getattr(conn.project_manager, "GetCurrentFolder", None)
    if not callable(folder_getter):
        raise _validation(
            "DaVinci Resolve cannot provide exact project-folder readback for context restoration.",
            reason="current_project_folder_readback_unavailable",
        )
    raw_folder = folder_getter()
    folder, folder_evidence = _canonical_root_project_folder(
        conn,
        raw_folder,
        database=database,
        project_name=project_name,
        project_id=project_id,
        timeline_id=timeline_id,
        timeline_present=timeline is not None,
    )
    if folder is None:
        raise _validation(
            "DaVinci Resolve cannot provide an exact nested project-folder path for safe context restoration.",
            reason="current_project_folder_identity_ambiguous",
            current_folder=raw_folder if isinstance(raw_folder, (str, int, float, bool)) or raw_folder is None else None,
            root_evidence=folder_evidence,
        )
    if project is not None:
        if timeline is not None and not timeline_id:
            raise _validation(
                "DaVinci Resolve cannot provide an exact current-timeline identity for context restoration.",
                reason="current_timeline_identity_unavailable",
                project_name=project_name,
                timeline_name=timeline_name,
            )
        if save_project:
            save = getattr(conn.project_manager, "SaveProject", None)
            if not callable(save) or not bool(save()):
                raise _validation(
                    "DaVinci Resolve could not save the current project before the project-library operation.",
                    reason="current_project_save_failed",
                    project_name=project_name,
                )
    return {
        "database": database,
        "project_name": project_name,
        "project_id": project_id,
        "timeline_name": timeline_name,
        "timeline_id": timeline_id,
        "timeline_present": timeline is not None,
        "playhead": playhead,
        "folder": folder,
        "page": page,
    }


def _refresh(conn: Any) -> None:
    refresh = getattr(conn, "refresh", None)
    if callable(refresh):
        refresh()


def _registration_activation_strategy(conn: Any) -> Any:
    """Require a connection-owned way to make a new registry row live.

    Resolve snapshots ``dblist.conf`` at process startup.  Appending a durable
    row is therefore not enough to prove that a newly created or restored Disk
    library can be opened.  The public scripting API has no reload primitive,
    and restarting a Resolve process is safe only when the connection runtime
    owns that exact process and can reattach this object to its new UUID.

    A runtime that provides that custody may expose
    ``activate_project_library_registration``.  Until it does, fail before the
    filesystem target or registry can be changed.
    """

    activation = getattr(conn, "activate_project_library_registration", None)
    if not callable(activation):
        failure = _validation(
            "Creating or restoring a Disk project library requires an owned "
            "DaVinci Resolve restart and verified instance reattachment.",
            reason="live_library_registration_unavailable",
            required_capability="owned_process_restart_and_verified_reattachment",
        )
        # The prepared-action host must not infer uncertainty from a capability
        # denial that is deliberately raised before staging or registry writes.
        failure.possible_mutation = "none"
        failure.usage = "released"
        raise failure
    return activation


def _database_matches(actual: dict[str, Any], expected: dict[str, Any]) -> bool:
    keys = ["DbType", "DbName"] + (["IpAddress"] if "IpAddress" in expected else [])
    return all(str(actual.get(key) or "") == str(expected.get(key) or "") for key in keys)


def _enumerated_database_target(conn: Any, *, expected: dict[str, Any], refresh: bool) -> dict[str, Any]:
    if refresh:
        _refresh(conn)
    manager = getattr(conn, "project_manager", None)
    getter = getattr(manager, "GetDatabaseList", None)
    if not callable(getter):
        raise APICallFailed(
            "DaVinci Resolve cannot enumerate the registered Disk project library.",
            details={"target": expected, "enumeration": "unavailable"},
            recoverability="manual",
        )
    rows = getter()
    if not isinstance(rows, list):
        raise APICallFailed(
            "DaVinci Resolve returned an invalid project-library enumeration.",
            details={"target": expected, "enumeration_type": type(rows).__name__},
            recoverability="manual",
        )
    matches = [
        row
        for row in rows
        if isinstance(row, dict) and _database_matches(row, expected)
    ]
    if len(matches) != 1:
        raise APICallFailed(
            "DaVinci Resolve did not enumerate the registered Disk project library exactly once.",
            details={"target": expected, "match_count": len(matches)},
            recoverability="manual",
        )
    match = matches[0]
    return {key: match[key] for key in ("DbType", "DbName", "IpAddress") if key in match}


def _enumerated_disk_target(conn: Any, *, name: str, refresh: bool) -> dict[str, Any]:
    return _enumerated_database_target(
        conn,
        expected={"DbType": "Disk", "DbName": name},
        refresh=refresh,
    )


def _switch_database(conn: Any, target: dict[str, Any]) -> None:
    enumerated_target = _enumerated_database_target(conn, expected=target, refresh=True)
    setter = getattr(conn.project_manager, "SetCurrentDatabase", None)
    if not callable(setter) or not bool(setter(enumerated_target)):
        raise APICallFailed(
            "DaVinci Resolve could not switch project libraries.",
            details={"target": enumerated_target},
            recoverability="manual",
        )
    _refresh(conn)
    current = _runtime_database(conn)
    if not _database_matches(current, enumerated_target):
        raise APICallFailed(
            "DaVinci Resolve project-library switch readback did not match the requested target.",
            details={"target": enumerated_target, "readback": current},
            recoverability="manual",
        )


def switch_library(conn: Any, *, target: dict[str, Any]) -> dict[str, Any]:
    """Switch to one carrier-bound native database record and verify readback."""

    previous = _runtime_database(conn)
    _switch_database(conn, target)
    return {"previous": previous, "current": _runtime_database(conn)}


def _activate_timeline(conn: Any, *, name: str | None, identity: str | None) -> bool:
    if not name and not identity:
        return True
    project = getattr(conn, "project", None)
    setter = getattr(project, "SetCurrentTimeline", None)
    if project is None or not callable(setter):
        return False
    count = int(project.GetTimelineCount() or 0)
    for index in range(1, count + 1):
        timeline = project.GetTimelineByIndex(index)
        if timeline is None:
            continue
        actual_id = _optional_id(timeline)
        actual_name = _optional_name(timeline)
        matches = actual_id == identity if identity else bool(name and actual_name == name)
        if matches:
            if not bool(setter(timeline)):
                return False
            _refresh(conn)
            return True
    return False


def _restore_playhead(conn: Any, expected: str | None) -> None:
    if expected is None:
        return
    project_getter = getattr(conn.project_manager, "GetCurrentProject", None)
    project = project_getter() if callable(project_getter) else None
    timeline_getter = getattr(project, "GetCurrentTimeline", None) if project is not None else None
    timeline = timeline_getter() if callable(timeline_getter) else None
    setter = getattr(timeline, "SetCurrentTimecode", None)
    if timeline is None or not callable(setter) or not bool(setter(expected)):
        raise APICallFailed(
            "DaVinci Resolve could not restore the original playhead exactly.",
            details={"expected_playhead": expected},
        )
    actual = _timeline_playhead(timeline, required=True)
    if actual != expected:
        raise APICallFailed(
            "DaVinci Resolve playhead readback did not restore the exact timecode.",
            details={"expected_playhead": expected, "actual_playhead": actual},
        )


def _restore_page(conn: Any, expected: str) -> None:
    opener = getattr(getattr(conn, "resolve", None), "OpenPage", None)
    if not callable(opener) or not bool(opener(expected)):
        raise APICallFailed(
            "DaVinci Resolve could not restore the original page exactly.",
            details={"expected_page": expected},
        )
    actual = _current_page(conn)
    if actual != expected:
        raise APICallFailed(
            "DaVinci Resolve page readback did not restore the exact page.",
            details={"expected_page": expected, "actual_page": actual},
        )


def _restore_context(conn: Any, context: dict[str, Any]) -> None:
    _switch_database(conn, dict(context["database"]))
    project_name = context.get("project_name")
    if not project_name:
        current_project_getter = getattr(conn.project_manager, "GetCurrentProject", None)
        folder_getter = getattr(conn.project_manager, "GetCurrentFolder", None)
        if not callable(current_project_getter) or current_project_getter() is not None:
            raise APICallFailed("DaVinci Resolve did not restore the original no-project context exactly.")
        raw_folder = folder_getter() if callable(folder_getter) else None
        canonical_folder, _root_evidence = _canonical_root_project_folder(
            conn,
            raw_folder,
            database=dict(context["database"]),
            project_name=None,
            project_id=None,
            timeline_id=None,
            timeline_present=False,
        )
        if canonical_folder is None:
            raise APICallFailed("DaVinci Resolve did not restore the original root project folder exactly.")
        _restore_page(conn, str(context["page"]))
        return
    goto_root = getattr(conn.project_manager, "GotoRootFolder", None)
    if callable(goto_root) and not bool(goto_root()):
        raise APICallFailed("DaVinci Resolve could not restore the original project folder.")
    loaded = conn.project_manager.LoadProject(project_name)
    if not loaded:
        raise APICallFailed(
            "DaVinci Resolve could not reopen the original project after the project-library operation.",
            details={"project_name": project_name},
        )
    loaded_id = _optional_id(loaded)
    if not loaded_id or loaded_id != context.get("project_id"):
        raise APICallFailed(
            "DaVinci Resolve reopened a project with the requested name but a different stable identity.",
            details={
                "project_name": project_name,
                "expected_project_id": context.get("project_id"),
                "actual_project_id": loaded_id,
            },
        )
    conn.project = loaded
    _refresh(conn)
    if not _activate_timeline(conn, name=context.get("timeline_name"), identity=context.get("timeline_id")):
        raise APICallFailed(
            "DaVinci Resolve could not restore the original timeline after the project-library operation.",
            details={"project_name": project_name, "timeline_name": context.get("timeline_name")},
        )
    _restore_playhead(conn, context.get("playhead"))
    current_project_getter = getattr(conn.project_manager, "GetCurrentProject", None)
    if not callable(current_project_getter):
        raise APICallFailed("DaVinci Resolve current-project readback is unavailable after context restoration.")
    current_project = current_project_getter()
    if _optional_id(current_project) != context.get("project_id"):
        raise APICallFailed(
            "DaVinci Resolve current-project readback did not restore the exact stable identity.",
            details={"expected_project_id": context.get("project_id"), "actual_project_id": _optional_id(current_project)},
        )
    timeline_getter = getattr(current_project, "GetCurrentTimeline", None)
    if not callable(timeline_getter):
        raise APICallFailed("DaVinci Resolve current-timeline readback is unavailable after context restoration.")
    current_timeline = timeline_getter()
    expected_timeline_present = bool(context.get("timeline_present"))
    if (current_timeline is not None) != expected_timeline_present or (
        expected_timeline_present and _optional_id(current_timeline) != context.get("timeline_id")
    ):
        raise APICallFailed(
            "DaVinci Resolve current-timeline readback did not restore the exact stable identity.",
            details={
                "expected_timeline_present": expected_timeline_present,
                "actual_timeline_present": current_timeline is not None,
                "expected_timeline_id": context.get("timeline_id"),
                "actual_timeline_id": _optional_id(current_timeline),
            },
        )
    folder_getter = getattr(conn.project_manager, "GetCurrentFolder", None)
    if not callable(folder_getter):
        raise APICallFailed("DaVinci Resolve project-folder readback is unavailable after context restoration.")
    raw_folder = folder_getter()
    canonical_folder, root_evidence = _canonical_root_project_folder(
        conn,
        raw_folder,
        database=dict(context["database"]),
        project_name=context.get("project_name"),
        project_id=context.get("project_id"),
        timeline_id=context.get("timeline_id"),
        timeline_present=expected_timeline_present,
    )
    if canonical_folder is None:
        raise APICallFailed(
            "DaVinci Resolve project-folder readback did not restore the root folder.",
            details={"actual_folder": raw_folder, "root_evidence": root_evidence},
        )
    _restore_page(conn, str(context["page"]))


def _probe_library(
    conn: Any,
    *,
    name: str,
    context: dict[str, Any],
    expected_projects: list[str],
    catalog_binding: tuple[Path, _RegularIdentity] | None = None,
    regular_bindings: dict[Path, _RegularIdentity] | None = None,
    inventory_root: Path | None = None,
    capture_post_activation_inventory: bool = False,
) -> dict[str, Any]:
    rounds: list[dict[str, Any]] = []
    retained_bindings = dict(regular_bindings or {})
    captured_inventory: set[Path] | None = None
    activation_observed = False
    if catalog_binding is not None:
        retained_bindings[catalog_binding[0]] = catalog_binding[1]

    def assert_retained(*, allow_capture: bool = False) -> None:
        nonlocal activation_observed, captured_inventory
        def assert_activation_safe_bindings() -> None:
            for path, identity in retained_bindings.items():
                if path.suffix.casefold() == ".db":
                    _assert_no_redirect_chain(path, include_leaf=True, reason="library_entry_redirect")
                    _sqlite_integrity(path)
                else:
                    _assert_regular_identity(path, identity, possible_mutation=True)

        if inventory_root is None:
            _assert_regular_bindings(retained_bindings, possible_mutation=True)
        elif capture_post_activation_inventory:
            if activation_observed or allow_capture:
                assert_activation_safe_bindings()
            else:
                _assert_regular_bindings(retained_bindings, possible_mutation=True)
            actual = {path.relative_to(inventory_root) for path in _walk_regular_files(inventory_root)}
            if captured_inventory is None and allow_capture:
                retained = {path.relative_to(inventory_root) for path in retained_bindings}
                if not retained.issubset(actual):
                    raise APICallFailed(
                        "Project-library activation removed a published file.",
                        details={"missing": sorted(path.as_posix() for path in retained - actual), "possible_mutation": True},
                        recoverability="manual",
                    )
                captured_inventory = actual
                activation_observed = True
            elif captured_inventory is None:
                _assert_exact_bound_inventory(
                    inventory_root, retained_bindings, possible_mutation=True
                )
            elif actual != captured_inventory:
                raise APICallFailed(
                    "Project-library file inventory changed after activation readback.",
                    details={
                        "added": sorted(path.as_posix() for path in actual - captured_inventory),
                        "removed": sorted(path.as_posix() for path in captured_inventory - actual),
                        "possible_mutation": True,
                    },
                    recoverability="manual",
                )
            if activation_observed:
                assert_activation_safe_bindings()
            else:
                _assert_regular_bindings(retained_bindings, possible_mutation=True)
        else:
            _assert_exact_bound_inventory(
                inventory_root, retained_bindings, possible_mutation=True
            )

    for round_index in range(1, 3):
        assert_retained()
        target = {"DbType": "Disk", "DbName": name}
        _switch_database(conn, target)
        assert_retained(allow_capture=True)
        goto_root = getattr(conn.project_manager, "GotoRootFolder", None)
        if not callable(goto_root) or not bool(goto_root()):
            raise APICallFailed(
                "DaVinci Resolve could not navigate to the project-library root for verification.",
                details={"name": name, "round": round_index},
            )
        folder_getter = getattr(conn.project_manager, "GetCurrentFolder", None)
        raw_folder = folder_getter() if callable(folder_getter) else None
        canonical_folder, root_evidence = _canonical_root_project_folder(
            conn,
            raw_folder,
            database=_runtime_database(conn),
            project_name=None,
            project_id=None,
            timeline_id=None,
            timeline_present=False,
        )
        list_projects = getattr(conn.project_manager, "GetProjectListInCurrentFolder", None)
        projects = list_projects() if callable(list_projects) else None
        if not isinstance(projects, list):
            raise APICallFailed(
                "DaVinci Resolve could not read the restored project library.",
                details={"name": name, "round": round_index},
            )
        if not all(isinstance(item, str) for item in projects):
            raise APICallFailed(
                "DaVinci Resolve returned invalid project identities after reopening the project library.",
                details={"name": name, "round": round_index},
            )
        expected = sorted(expected_projects)
        actual = sorted(projects)
        if actual != expected:
            raise APICallFailed(
                "DaVinci Resolve reopened the project library but did not expose the exact expected projects.",
                details={
                    "name": name,
                    "round": round_index,
                    "expected_projects": expected,
                    "actual_projects": actual,
                    "missing_projects": sorted(set(expected) - set(actual)),
                    "unexpected_projects": sorted(set(actual) - set(expected)),
                },
            )
        observed_ephemeral_project = False
        observed_restored_project = False
        if canonical_folder is None and raw_folder == "":
            current_project_getter = getattr(conn.project_manager, "GetCurrentProject", None)
            current_project = current_project_getter() if callable(current_project_getter) else None
            timeline_getter = getattr(current_project, "GetCurrentTimeline", None)
            current_timeline = timeline_getter() if callable(timeline_getter) else object()
            ephemeral_id = _optional_id(current_project)
            if _optional_name(current_project) == "Untitled Project" and ephemeral_id and current_timeline is None:
                observed_ephemeral_project = True
                canonical_folder = "root"
                root_evidence = {
                    "representation": "resolve_ephemeral_empty_library",
                    "project_id": ephemeral_id,
                    "durable_project_count": len(expected),
                }
        if canonical_folder is None and raw_folder == "" and expected:
            current_project_getter = getattr(conn.project_manager, "GetCurrentProject", None)
            current_project = current_project_getter() if callable(current_project_getter) else None
            project_name = _optional_name(current_project)
            project_id = _optional_id(current_project)
            if project_name in expected and project_id:
                observed_restored_project = True
                canonical_folder = "root"
                root_evidence = {
                    "representation": "resolve_restored_library_current_project",
                    "project_id": project_id,
                    "project_name": project_name,
                    "durable_project_count": len(expected),
                }
        if canonical_folder is None:
            current_project_getter = getattr(conn.project_manager, "GetCurrentProject", None)
            current_project = (
                current_project_getter() if callable(current_project_getter) else object()
            )
            if raw_folder != "" or current_project is not None:
                raise APICallFailed(
                    "DaVinci Resolve did not confirm the project-library root before verification.",
                    details={
                        "name": name,
                        "round": round_index,
                        "actual_folder": raw_folder,
                        "root_evidence": root_evidence,
                        "current_project_present": current_project is not None,
                    },
                )
        rounds.append({"round": round_index, "current_database": _runtime_database(conn), "project_count": len(projects), "observed_ephemeral_project": observed_ephemeral_project, "observed_restored_project": observed_restored_project})
        _restore_context(conn, context)
        assert_retained()
    _enumerated_disk_target(conn, name=name, refresh=True)
    final_context = _capture_context(conn, save_project=False)
    if final_context != context:
        raise APICallFailed(
            "DaVinci Resolve context changed during final project-library registration readback.",
            details={"expected_context": context, "actual_context": final_context},
            recoverability="manual",
        )
    assert_retained()
    return {
        "rounds": rounds,
        "context_restored": True,
        "registration_readback": True,
        "post_activation_inventory": (
            sorted(path.as_posix() for path in captured_inventory)
            if captured_inventory is not None
            else None
        ),
    }


def _created_marker(name: str, *, operation_id: str, backup_id: str | None = None) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "owner": "CutAgent CLI",
        "library_name": name,
        "operation_id": operation_id,
        "created_at": _now_iso(),
        "backup_id": backup_id,
    }


def _write_marker(root: Path, marker: dict[str, Any]) -> None:
    path = root / LIBRARY_MARKER
    path.write_text(json.dumps(marker, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _path_identity(path: Path) -> tuple[int, int]:
    metadata = path.stat(follow_symlinks=False)
    return int(metadata.st_dev), int(metadata.st_ino)


def _new_internal_stage(kind: str) -> tuple[Path, tuple[int, int]]:
    path = Path(tempfile.mkdtemp(prefix=f"cutagent-{kind}-")).resolve(strict=True)
    path.chmod(0o700)
    return path, _path_identity(path)


def _remove_internal_stage(path: Path, identity: tuple[int, int]) -> None:
    if not path.exists():
        return
    _assert_no_redirect_chain(path, include_leaf=True, reason="internal_stage_redirect")
    if _path_identity(path) != identity:
        raise RuntimeError("Internal staging directory identity changed; refusing cleanup.")
    if not getattr(shutil.rmtree, "avoids_symlink_attacks", False):
        raise RuntimeError("This platform cannot safely remove the internal staging directory.")
    shutil.rmtree(path)


def _copy_tree_into_dirfd(
    source: Path,
    destination_fd: int,
    *,
    source_root: Path,
    bound_regulars: dict[Path, _RegularIdentity],
    seen_bound_regulars: set[Path],
    copied_bound_regulars: dict[Path, tuple[int, _RegularIdentity]],
) -> None:
    for entry in os.scandir(source):
        source_entry = Path(entry.path)
        if entry.is_symlink():
            raise _validation(
                "Private project-library staging contains a redirected entry.",
                reason="internal_stage_redirect",
                path=str(source_entry),
            )
        if entry.is_dir(follow_symlinks=False):
            os.mkdir(entry.name, mode=0o700, dir_fd=destination_fd)
            child_fd = os.open(
                entry.name,
                os.O_RDONLY | int(getattr(os, "O_DIRECTORY", 0)) | int(getattr(os, "O_NOFOLLOW", 0)),
                dir_fd=destination_fd,
            )
            try:
                _copy_tree_into_dirfd(
                    source_entry,
                    child_fd,
                    source_root=source_root,
                    bound_regulars=bound_regulars,
                    seen_bound_regulars=seen_bound_regulars,
                    copied_bound_regulars=copied_bound_regulars,
                )
                os.fsync(child_fd)
            finally:
                os.close(child_fd)
            continue
        if not entry.is_file(follow_symlinks=False):
            raise _validation(
                "Private project-library staging contains an unsupported entry.",
                reason="internal_stage_unsupported",
                path=str(source_entry),
            )
        source_fd = os.open(source_entry, os.O_RDONLY | int(getattr(os, "O_NOFOLLOW", 0)))
        relative = source_entry.relative_to(source_root)
        expected_identity = bound_regulars.get(relative)
        if bound_regulars and expected_identity is None:
            os.close(source_fd)
            raise _validation(
                "Private project-library staging gained an unvalidated file before publication.",
                reason="internal_stage_inventory_changed",
                relative_path=relative.as_posix(),
            )
        opened_source = os.fstat(source_fd)
        opened_identity = (
            int(opened_source.st_dev),
            int(opened_source.st_ino),
            int(opened_source.st_size),
            int(opened_source.st_mtime_ns),
            int(opened_source.st_ctime_ns),
        )
        if expected_identity is not None and opened_identity != expected_identity:
            os.close(source_fd)
            raise _validation(
                "Private project-library staging changed after descriptor-backed validation.",
                reason="internal_stage_identity_changed",
                relative_path=relative.as_posix(),
            )
        destination_file_fd = os.open(
            entry.name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            stat.S_IMODE(os.fstat(source_fd).st_mode),
            dir_fd=destination_fd,
        )
        try:
            while True:
                chunk = os.read(source_fd, 1024 * 1024)
                if not chunk:
                    break
                view = memoryview(chunk)
                while view:
                    written = os.write(destination_file_fd, view)
                    if written <= 0:
                        raise OSError("short write while publishing project-library staging")
                    view = view[written:]
            os.fsync(destination_file_fd)
            if expected_identity is not None:
                current = source_entry.stat(follow_symlinks=False)
                current_identity = (
                    int(current.st_dev),
                    int(current.st_ino),
                    int(current.st_size),
                    int(current.st_mtime_ns),
                    int(current.st_ctime_ns),
                )
                if current_identity != opened_identity:
                    raise _validation(
                        "Private project-library staging changed during publication.",
                        reason="internal_stage_identity_changed",
                        relative_path=relative.as_posix(),
                    )
                seen_bound_regulars.add(relative)
                copied_metadata = os.fstat(destination_file_fd)
                copied_identity = (
                    int(copied_metadata.st_dev),
                    int(copied_metadata.st_ino),
                    int(copied_metadata.st_size),
                    int(copied_metadata.st_mtime_ns),
                    int(copied_metadata.st_ctime_ns),
                )
                copied_bound_regulars[relative] = (
                    os.dup(destination_file_fd),
                    copied_identity,
                )
        finally:
            os.close(destination_file_fd)
            os.close(source_fd)


def _regular_identity_beneath_dirfd(root_fd: int, relative: Path) -> _RegularIdentity:
    """Bind a regular file beneath ``root_fd`` without following any path redirect."""

    parts = relative.parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise RuntimeError("invalid descriptor-relative project-library path")
    directory_fd = os.dup(root_fd)
    try:
        for part in parts[:-1]:
            child_fd = os.open(
                part,
                os.O_RDONLY
                | int(getattr(os, "O_DIRECTORY", 0))
                | int(getattr(os, "O_NOFOLLOW", 0)),
                dir_fd=directory_fd,
            )
            os.close(directory_fd)
            directory_fd = child_fd
        file_fd = os.open(
            parts[-1],
            os.O_RDONLY | int(getattr(os, "O_NOFOLLOW", 0)),
            dir_fd=directory_fd,
        )
        try:
            metadata = os.fstat(file_fd)
            if not stat.S_ISREG(metadata.st_mode):
                raise RuntimeError("descriptor-relative project-library path is not regular")
            return (
                int(metadata.st_dev),
                int(metadata.st_ino),
                int(metadata.st_size),
                int(metadata.st_mtime_ns),
                int(metadata.st_ctime_ns),
            )
        finally:
            os.close(file_fd)
    finally:
        os.close(directory_fd)


def _remove_tree_at(parent_fd: int, name: str, expected_identity: tuple[int, int]) -> None:
    child_fd = os.open(
        name,
        os.O_RDONLY | int(getattr(os, "O_DIRECTORY", 0)) | int(getattr(os, "O_NOFOLLOW", 0)),
        dir_fd=parent_fd,
    )
    try:
        opened = os.fstat(child_fd)
        if (int(opened.st_dev), int(opened.st_ino)) != expected_identity:
            raise RuntimeError("Private publication staging identity changed; refusing cleanup.")
        for entry in os.scandir(child_fd):
            if entry.is_dir(follow_symlinks=False):
                entry_metadata = entry.stat(follow_symlinks=False)
                _remove_tree_at(
                    child_fd,
                    entry.name,
                    (int(entry_metadata.st_dev), int(entry_metadata.st_ino)),
                )
            else:
                os.unlink(entry.name, dir_fd=child_fd)
    finally:
        os.close(child_fd)
    os.rmdir(name, dir_fd=parent_fd)


def _exclusive_publish_directory(
    stage: Path,
    stage_identity: tuple[int, int],
    target: Path,
    *,
    bound_regulars: dict[Path, _RegularIdentity] | None = None,
    published_regulars: dict[Path, _RegularIdentity] | None = None,
    expected_parent_identity: tuple[int, int] | None = None,
) -> tuple[int, int]:
    """Publish a fully built private stage without clobbering a raced target.

    macOS and Linux provide native no-replace directory rename primitives. The
    Windows path remains fail-closed until its handle-relative no-replace route
    is implemented and proven in the required activation matrix.
    """
    if sys.platform not in {"darwin"} and not sys.platform.startswith("linux"):
        raise _validation(
            "This platform does not yet have a proven handle-bound no-replace project-library publication route.",
            reason="library_target_platform_binding_unavailable",
            platform=sys.platform,
        )
    _assert_no_redirect_chain(target.parent, include_leaf=True, reason="library_target_parent_redirect")
    parent_identity = _path_identity(target.parent)
    if expected_parent_identity is not None and parent_identity != expected_parent_identity:
        raise _validation(
            "Project-library target parent differs from its carrier-owned identity.",
            reason="library_target_parent_identity_changed",
            parent=str(target.parent),
        )
    parent_flags = os.O_RDONLY | int(getattr(os, "O_DIRECTORY", 0)) | int(getattr(os, "O_NOFOLLOW", 0))
    parent_fd = os.open(target.parent, parent_flags)
    published = False
    try:
        opened_parent = os.fstat(parent_fd)
        if (opened_parent.st_dev, opened_parent.st_ino) != parent_identity:
            raise _validation(
                "Project-library target parent identity changed before publication.",
                reason="library_target_parent_identity_changed",
                parent=str(target.parent),
            )
        if _path_identity(stage) != stage_identity:
            raise _validation(
                "Private project-library staging identity changed before publication.",
                reason="internal_stage_identity_changed",
            )
        hidden_name = f".{target.name}.cutagent-publish-{uuid4().hex}.tmp"
        hidden_created = False
        hidden_fd = -1
        hidden_identity: tuple[int, int] | None = None
        identity: tuple[int, int] | None = None
        operation_error: BaseException | None = None
        copied_bound_regulars: dict[Path, tuple[int, _RegularIdentity]] = {}
        try:
            os.mkdir(hidden_name, mode=0o700, dir_fd=parent_fd)
            hidden_created = True
            hidden_fd = os.open(
                hidden_name,
                os.O_RDONLY | int(getattr(os, "O_DIRECTORY", 0)) | int(getattr(os, "O_NOFOLLOW", 0)),
                dir_fd=parent_fd,
            )
            initial_hidden = os.fstat(hidden_fd)
            hidden_identity = (int(initial_hidden.st_dev), int(initial_hidden.st_ino))
            required_regulars = dict(bound_regulars or {})
            seen_bound_regulars: set[Path] = set()
            _copy_tree_into_dirfd(
                stage,
                hidden_fd,
                source_root=stage,
                bound_regulars=required_regulars,
                seen_bound_regulars=seen_bound_regulars,
                copied_bound_regulars=copied_bound_regulars,
            )
            if seen_bound_regulars != set(required_regulars):
                raise _validation(
                    "Private project-library staging lost a descriptor-bound validated file.",
                    reason="internal_stage_identity_changed",
                    missing=[
                        path.as_posix()
                        for path in sorted(set(required_regulars) - seen_bound_regulars)
                    ],
                )
            os.fsync(hidden_fd)
            copied_hidden = os.fstat(hidden_fd)
            if (int(copied_hidden.st_dev), int(copied_hidden.st_ino)) != hidden_identity:
                raise RuntimeError("Private publication staging identity changed during copy.")
            for relative, (descriptor, copied_identity) in copied_bound_regulars.items():
                descriptor_metadata = os.fstat(descriptor)
                descriptor_identity = (
                    int(descriptor_metadata.st_dev),
                    int(descriptor_metadata.st_ino),
                    int(descriptor_metadata.st_size),
                    int(descriptor_metadata.st_mtime_ns),
                    int(descriptor_metadata.st_ctime_ns),
                )
                if descriptor_identity != copied_identity or _regular_identity_beneath_dirfd(
                    hidden_fd, relative
                ) != copied_identity:
                    raise _validation(
                        "Private publication catalog changed before exclusive publication.",
                        reason="internal_stage_identity_changed",
                        relative_path=relative.as_posix(),
                    )
            libc = ctypes.CDLL(None, use_errno=True)
            source = os.fsencode(hidden_name)
            destination = os.fsencode(target.name)
            if sys.platform == "darwin":
                rename_exclusive = libc.renameatx_np
                rename_exclusive.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
                result = rename_exclusive(parent_fd, source, parent_fd, destination, 0x00000004)  # RENAME_EXCL
            elif sys.platform.startswith("linux"):
                rename_exclusive = libc.renameat2
                rename_exclusive.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
                result = rename_exclusive(parent_fd, source, parent_fd, destination, 0x1)  # RENAME_NOREPLACE
            if result != 0:
                error_number = ctypes.get_errno()
                if error_number in {17, 39}:  # EEXIST / ENOTEMPTY
                    raise _validation(
                        "Project-library target appeared during publication; overwrite is not supported.",
                        reason="library_target_collision",
                        target_root=str(target),
                        overwrite_supported=False,
                    )
                raise OSError(error_number, os.strerror(error_number), str(target))
            published = True
            try:
                os.fsync(parent_fd)
                identity = _path_identity(target)
                if identity != hidden_identity:
                    raise OSError("published target identity mismatch")
                if _path_identity(target.parent) != parent_identity:
                    raise OSError("published target parent identity mismatch")
                for relative, (descriptor, copied_identity) in copied_bound_regulars.items():
                    descriptor_metadata = os.fstat(descriptor)
                    descriptor_identity = (
                        int(descriptor_metadata.st_dev),
                        int(descriptor_metadata.st_ino),
                        int(descriptor_metadata.st_size),
                        int(descriptor_metadata.st_mtime_ns),
                        int(descriptor_metadata.st_ctime_ns),
                    )
                    if descriptor_identity != copied_identity or _regular_identity_beneath_dirfd(
                        hidden_fd, relative
                    ) != copied_identity:
                        raise OSError("published descriptor-bound file identity mismatch")
                if published_regulars is not None:
                    published_regulars.update(
                        {
                            relative: copied_identity
                            for relative, (_descriptor, copied_identity) in copied_bound_regulars.items()
                        }
                    )
                os.close(hidden_fd)
                hidden_fd = -1
            except OSError as exc:
                raise APICallFailed(
                    "Published project-library path could not be read back after exclusive publication.",
                    details={"target_root": str(target), "possible_mutation": True},
                    recoverability="manual",
                ) from exc
        except BaseException as exc:
            operation_error = exc

        cleanup_error: BaseException | None = None
        for descriptor, _copied_identity in copied_bound_regulars.values():
            try:
                os.close(descriptor)
            except OSError as exc:
                cleanup_error = cleanup_error or exc
        if hidden_fd >= 0:
            try:
                os.close(hidden_fd)
            except OSError as exc:
                cleanup_error = exc
        if not published and hidden_created:
            if hidden_identity is None:
                cleanup_error = cleanup_error or RuntimeError(
                    "Private publication staging was created but its identity could not be bound for safe cleanup."
                )
            else:
                try:
                    _remove_tree_at(parent_fd, hidden_name, hidden_identity)
                except FileNotFoundError:
                    pass
                except Exception as exc:
                    cleanup_error = cleanup_error or exc
        if cleanup_error is not None:
            raise APICallFailed(
                "Private project-library publication staging could not be finalized safely.",
                details={
                    "target_root": str(target),
                    "private_stage_name": hidden_name,
                    "published": published,
                    "possible_mutation": True,
                },
                recoverability="manual",
            ) from cleanup_error
        if operation_error is not None:
            raise operation_error
        if identity is None:
            raise APICallFailed(
                "Project-library publication completed without an exact target identity readback.",
                details={"target_root": str(target), "possible_mutation": published},
                recoverability="manual",
            )
        return identity
    finally:
        try:
            os.close(parent_fd)
        except OSError as exc:
            raise APICallFailed(
                "Project-library publication parent handle could not be closed safely.",
                details={"target_root": str(target), "possible_mutation": True},
                recoverability="manual",
            ) from exc


def _assert_published_identity(target: Path, identity: tuple[int, int]) -> None:
    _assert_no_redirect_chain(target, include_leaf=True, reason="library_target_redirect")
    if _path_identity(target) != identity:
        raise APICallFailed(
            "Published project-library path identity changed during the operation.",
            details={"target_root": str(target), "possible_mutation": True},
            recoverability="manual",
        )


def _require_active_disk_database(conn: Any) -> dict[str, Any]:
    database = _runtime_database(conn)
    if database.get("DbType") != "Disk":
        raise _validation(
            "Project-library creation requires an active local Disk project library.",
            reason="active_library_type_unsupported",
            database_type=database.get("DbType"),
        )
    return database


def _active_seed_catalog(
    database: dict[str, Any], rows: list[dict[str, str]]
) -> tuple[Path, tuple[int, int], Path, _RegularIdentity]:
    name = str(database.get("DbName") or "")
    root, _row, _general_catalog_identity = _registered_library(name, rows)
    root_identity = _path_identity(root)
    catalog = root / _USER_CATALOG_RELATIVE
    _catalog, catalog_identity = _validate_bound_empty_user_catalog_identity(catalog)
    if _path_identity(root) != root_identity:
        raise _validation(
            "Active Disk project-library identity changed during seed validation.",
            reason="library_source_identity_changed",
            name=name,
        )
    return root, root_identity, catalog, catalog_identity


def _regular_identity(path: Path) -> _RegularIdentity:
    metadata = path.stat(follow_symlinks=False)
    if not stat.S_ISREG(metadata.st_mode):
        raise _validation(
            "Project-library catalog is not a regular file.",
            reason="library_entry_unsupported",
            path=str(path),
        )
    return (
        int(metadata.st_dev),
        int(metadata.st_ino),
        int(metadata.st_size),
        int(metadata.st_mtime_ns),
        int(metadata.st_ctime_ns),
    )


def _assert_regular_identity(path: Path, identity: _RegularIdentity, *, possible_mutation: bool) -> None:
    _assert_no_redirect_chain(path, include_leaf=True, reason="library_entry_redirect")
    try:
        actual = _regular_identity(path)
    except OSError as exc:
        raise APICallFailed(
            "Project-library file identity could not be read back.",
            details={"possible_mutation": possible_mutation},
            recoverability="manual" if possible_mutation else "retryable",
        ) from exc
    if actual != identity:
        raise APICallFailed(
            "Project-library file identity changed during the operation.",
            details={"possible_mutation": possible_mutation},
            recoverability="manual" if possible_mutation else "retryable",
        )
def _assert_regular_bindings(
    bindings: dict[Path, _RegularIdentity], *, possible_mutation: bool
) -> None:
    for path, identity in bindings.items():
        _assert_regular_identity(path, identity, possible_mutation=possible_mutation)


def _assert_exact_bound_inventory(
    root: Path,
    bindings: dict[Path, _RegularIdentity],
    *,
    possible_mutation: bool,
) -> None:
    _assert_regular_bindings(bindings, possible_mutation=possible_mutation)
    expected = {path.relative_to(root) for path in bindings}
    actual = {path.relative_to(root) for path in _walk_regular_files(root)}
    if actual != expected:
        raise APICallFailed(
            "Project-library file inventory changed during the operation.",
            details={
                "undeclared": sorted(path.as_posix() for path in actual - expected),
                "missing": sorted(path.as_posix() for path in expected - actual),
                "possible_mutation": possible_mutation,
            },
            recoverability="manual" if possible_mutation else "retryable",
        )
    _assert_regular_bindings(bindings, possible_mutation=possible_mutation)


def preflight_create(*, name: str, dir_path: str) -> dict[str, Any]:
    normalized_name = _normalize_name(name)
    target = _normalize_explicit_path(dir_path, kind="library_target", must_exist=False)
    registry_path, _original, rows = _registry_state()
    _assert_new_target(normalized_name, target, rows)
    return {"name": normalized_name, "target_root": target, "registry_path": registry_path}


def create_library(
    conn: Any, *, name: str, dir_path: str,
    expected_parent_identity: tuple[int, int] | None = None,
) -> dict[str, Any]:
    preflight = preflight_create(name=name, dir_path=dir_path)
    normalized_name = str(preflight["name"])
    target = Path(preflight["target_root"])
    registry_path = Path(preflight["registry_path"])
    activate_registration = _registration_activation_strategy(conn)
    active_database = _require_active_disk_database(conn)
    context = _capture_context(conn)
    if not _database_matches(context["database"], active_database):
        raise _validation(
            "Active project-library identity changed during context capture.",
            reason="current_library_identity_changed",
        )
    operation_id = uuid4().hex
    steps: list[str] = []
    stage: Path | None = None
    stage_identity: tuple[int, int] | None = None
    target_created = False
    target_identity: tuple[int, int] | None = None
    registration_attempted = False
    registry_changed = False
    with _library_lock(registry_path):
        try:
            registry_path, _registry_original, rows = _registry_state()
            _assert_new_target(normalized_name, target, rows)
            enumerated_source = _enumerated_database_target(
                conn,
                expected=active_database,
                refresh=True,
            )
            if not _database_matches(_runtime_database(conn), active_database):
                raise _validation(
                    "Active project-library identity changed before seed capture.",
                    reason="current_library_identity_changed",
                )
            seed_root, seed_root_identity, seed_catalog, seed_catalog_identity = _active_seed_catalog(
                enumerated_source, rows
            )
            stage, stage_identity = _new_internal_stage("library-create")
            _write_marker(stage, _created_marker(normalized_name, operation_id=operation_id))
            (stage / "Resolve Projects" / "Users" / "guest" / "Projects").mkdir(parents=True)
            (stage / "Resolve Projects" / "Users" / "guest" / "Configs").mkdir(parents=True)
            staged_catalog = stage / _USER_CATALOG_RELATIVE
            _copy_bound_regular(
                seed_catalog,
                staged_catalog,
                sqlite_file=True,
                expected_identity=seed_catalog_identity,
            )
            _staged_catalog, staged_catalog_identity = _validate_bound_empty_user_catalog_identity(
                staged_catalog
            )
            if _path_identity(seed_root) != seed_root_identity:
                raise _validation(
                    "Active Disk project-library identity changed while its catalog was snapshotted.",
                    reason="library_source_identity_changed",
                    name=active_database.get("DbName"),
                )
            steps.append("snapshot_empty_user_catalog")
            stage_bindings = _bind_exact_regular_inventory(
                stage,
                {Path(LIBRARY_MARKER), _USER_CATALOG_RELATIVE},
                validated_bindings={_USER_CATALOG_RELATIVE: staged_catalog_identity},
            )
            published_files: dict[Path, _RegularIdentity] = {}
            target_identity = _exclusive_publish_directory(
                stage,
                stage_identity,
                target,
                bound_regulars=stage_bindings,
                published_regulars=published_files,
                **({"expected_parent_identity": expected_parent_identity} if expected_parent_identity is not None else {}),
            )
            target_created = True
            steps.append("publish_seeded_library")
            _assert_published_identity(target, target_identity)
            target_catalog = target / _USER_CATALOG_RELATIVE
            _catalog_validation, target_catalog_identity = _validate_bound_empty_user_catalog_identity(
                target_catalog
            )
            if target_catalog_identity != published_files.get(_USER_CATALOG_RELATIVE):
                raise APICallFailed(
                    "Published project-library catalog identity changed after exclusive publication.",
                    details={"target_root": str(target), "possible_mutation": True},
                    recoverability="manual",
                )
            target_file_bindings = {
                target / relative: identity for relative, identity in published_files.items()
            }
            registration_attempted = True
            _assert_exact_bound_inventory(
                target, target_file_bindings, possible_mutation=True
            )
            _append_registry_entry(registry_path, name=normalized_name, root=target)
            _assert_published_identity(target, target_identity)
            _assert_exact_bound_inventory(
                target, target_file_bindings, possible_mutation=True
            )
            registry_changed = True
            steps.append("register_library")
            activate_registration(name=normalized_name, context=dict(context))
            steps.append("activate_registered_library")
            verification = _probe_library(
                conn,
                name=normalized_name,
                context=context,
                expected_projects=[],
                regular_bindings=target_file_bindings,
                inventory_root=target,
                capture_post_activation_inventory=True,
            )
            steps.extend(["reopen_readback_round_1", "reopen_readback_round_2", "restore_original_context"])
            _remove_internal_stage(stage, stage_identity)
            stage = None
            stage_identity = None
        except Exception as exc:
            cleanup_errors: list[str] = []
            uncertain_publication = bool((getattr(exc, "details", {}) or {}).get("possible_mutation"))
            if registration_attempted:
                try:
                    _restore_context(conn, context)
                except Exception as cleanup_exc:
                    cleanup_errors.append(f"context:{cleanup_exc.__class__.__name__}")
            if stage is not None and stage_identity is not None and stage.exists():
                try:
                    _remove_internal_stage(stage, stage_identity)
                except Exception as cleanup_exc:
                    cleanup_errors.append(f"internal_stage:{cleanup_exc.__class__.__name__}")
            # Once registration append is attempted, preserve both the target
            # and registry record. Deleting either could strand DaVinci Resolve
            # on a live library or race an external registry writer.
            manual_recovery = target_created or uncertain_publication or registration_attempted or bool(cleanup_errors)
            raise _failure(
                "Project-library creation failed.",
                phase="create",
                possible_mutation=target_created or uncertain_publication or registration_attempted,
                manual_recovery_required=manual_recovery,
                recovery={
                    "cleanup_errors": cleanup_errors,
                    "target_root": str(target),
                    "target_preserved": target_created or uncertain_publication,
                    "registration_append_attempted": registration_attempted,
                    "registration_verified": registry_changed,
                    "context_restored": not any(item.startswith("context:") for item in cleanup_errors),
                    "steps": [
                        "Confirm DaVinci Resolve is on the original Disk project library before changing files.",
                        f"Inspect the preserved target directory: {target}",
                        f"Inspect the append-only project-library registry entry in: {registry_path}",
                        "Reconcile the registration manually only after confirming DaVinci Resolve is not using the failed target.",
                    ],
                },
                error=exc,
                steps=steps,
            ) from exc
    set_verification_status("verified")
    set_recoverability("manual")
    return {
        "library": {"name": normalized_name, "type": "Disk", "root": str(target)},
        "changed": True,
        "verification": verification,
        "steps": steps,
        "possible_mutation": False,
        "manual_recovery_required": False,
    }


def preflight_backup(*, name: str, path: str) -> dict[str, Any]:
    normalized_name = _normalize_name(name)
    destination = _normalize_explicit_path(path, kind="backup_destination", must_exist=False)
    if destination.exists():
        raise _validation(
            "Project-library backup destination already exists; overwrite is not supported.",
            reason="backup_destination_collision",
            backup_path=str(destination),
            overwrite_supported=False,
        )
    registry_path, _original, rows = _registry_state()
    source, _row, _catalog_identity = _registered_library(normalized_name, rows)
    return {"name": normalized_name, "source_root": source, "destination": destination, "registry_path": registry_path}


def _close_current_project(conn: Any, context: dict[str, Any]) -> None:
    current_project_getter = getattr(conn.project_manager, "GetCurrentProject", None)
    if not callable(current_project_getter):
        raise APICallFailed("DaVinci Resolve current-project readback is unavailable before backup closure.")
    project = current_project_getter()
    if project is None:
        if context.get("project_id") is not None:
            raise APICallFailed(
                "DaVinci Resolve current-project state changed before backup closure.",
                details={"expected_project_id": context.get("project_id"), "actual_project_id": None},
                recoverability="retryable",
            )
        return
    project_id = _optional_id(project)
    if project_id != context.get("project_id"):
        raise APICallFailed(
            "DaVinci Resolve current-project identity changed before backup closure.",
            details={"expected_project_id": context.get("project_id"), "actual_project_id": project_id},
            recoverability="retryable",
        )
    close = getattr(conn.project_manager, "CloseProject", None)
    if not callable(close) or not bool(close(project)):
        raise APICallFailed(
            "DaVinci Resolve could not close the current project for a consistent project-library backup.",
            details={"project_name": context.get("project_name")},
        )
    last_project = project
    for attempt in range(20):
        conn.project = None
        conn.timeline = None
        _refresh(conn)
        refreshed_project_getter = getattr(conn.project_manager, "GetCurrentProject", None)
        if not callable(refreshed_project_getter):
            raise APICallFailed(
                "DaVinci Resolve current-project readback is unavailable after backup closure.",
                details={"possible_mutation": True},
                recoverability="manual",
            )
        last_project = refreshed_project_getter()
        if last_project is None:
            return
        name = _optional_name(last_project)
        timeline_count_getter = getattr(last_project, "GetTimelineCount", None)
        try:
            timeline_count = int(timeline_count_getter() or 0) if callable(timeline_count_getter) else None
        except Exception:
            timeline_count = None
        conn.project = last_project
        timeline_getter = getattr(last_project, "GetCurrentTimeline", None)
        conn.timeline = timeline_getter() if callable(timeline_getter) else None
        project_list_getter = getattr(conn.project_manager, "GetProjectListInCurrentFolder", None)
        try:
            projects = project_list_getter() if callable(project_list_getter) else None
        except Exception:
            projects = None
        if (
            looks_like_project_manager_placeholder(conn, name, timeline_count)
            and isinstance(projects, list)
            and name not in projects
        ):
            conn.project = None
            conn.timeline = None
            return
        if attempt < 19:
            time.sleep(0.25)
    raise APICallFailed(
        "DaVinci Resolve still reports an open project after backup closure.",
        details={"actual_project_id": _optional_id(last_project), "possible_mutation": True},
        recoverability="manual",
    )


def backup_library(conn: Any, *, name: str, path: str) -> dict[str, Any]:
    preflight = preflight_backup(name=name, path=path)
    normalized_name = str(preflight["name"])
    source = Path(preflight["source_root"])
    destination = Path(preflight["destination"])
    registry_path = Path(preflight["registry_path"])
    context = _capture_context(conn)
    current_target = context["database"].get("DbType") == "Disk" and context["database"].get("DbName") == normalized_name
    operation_id = uuid4().hex
    steps: list[str] = []
    stage: Path | None = None
    stage_identity: tuple[int, int] | None = None
    destination_created = False
    destination_identity: tuple[int, int] | None = None
    context_close_attempted = False
    with _library_lock(registry_path):
        try:
            _locked_registry, _locked_bytes, locked_rows = _registry_state()
            locked_source, _locked_row, _preclose_catalog_identity = _registered_library(
                normalized_name, locked_rows
            )
            locked_source_identity = _path_identity(locked_source)
            if locked_source_identity != _path_identity(source):
                raise _validation(
                    "Project-library source registration changed before backup started.",
                    reason="library_source_identity_changed",
                    name=normalized_name,
                )
            if current_target and context.get("project_name"):
                context_close_attempted = True
                _close_current_project(conn, context)
                steps.append("close_current_project")
            _catalog_validation, locked_catalog_identity = _validate_bound_user_catalog_identity(
                locked_source / _USER_CATALOG_RELATIVE
            )
            if _path_identity(locked_source) != locked_source_identity:
                raise _validation(
                    "Project-library source identity changed after backup closure.",
                    reason="library_source_identity_changed",
                    name=normalized_name,
                )
            stage, stage_identity = _new_internal_stage("library-backup")
            _write_marker(
                stage,
                _created_marker(normalized_name, operation_id=operation_id),
            )
            payload = stage / BACKUP_PAYLOAD
            payload.mkdir(parents=True, mode=0o700)
            inventory: list[dict[str, Any]] = []
            source_files = _backup_source_files(source)
            source_bindings: dict[Path, _RegularIdentity] = {}
            for source_file in source_files:
                _result, source_identity = _with_bound_regular(
                    source_file, lambda _bound: None, return_identity=True
                )
                source_bindings[source_file] = source_identity
            catalog_source = locked_source / _USER_CATALOG_RELATIVE
            if source_bindings.get(catalog_source) != locked_catalog_identity:
                raise _validation(
                    "Project-library catalog changed before backup inventory binding.",
                    reason="library_entry_identity_changed",
                    path=str(catalog_source),
                )
            _assert_backup_source_inventory(source, source_bindings)
            for source_file in source_files:
                relative = source_file.relative_to(source)
                relative_text = relative.as_posix()
                destination_file = payload / relative
                is_sqlite = source_file.suffix.lower() in _SQLITE_SUFFIXES
                sqlite_meta = _copy_bound_regular(
                    source_file,
                    destination_file,
                    sqlite_file=is_sqlite,
                    expected_identity=source_bindings[source_file],
                )
                inventory.append(
                    {
                        "path": relative_text,
                        "size": destination_file.stat().st_size,
                        "sha256": _hash_file(destination_file),
                        "sqlite": is_sqlite,
                        "sqlite_meta": sqlite_meta,
                    }
                )
            _assert_backup_source_inventory(source, source_bindings)
            backup_id = _manifest_identity(inventory)
            manifest = {
                "schema_version": BACKUP_SCHEMA_VERSION,
                "library_format": LIBRARY_FORMAT,
                "database_type": "Disk",
                "source_library_name": normalized_name,
                "created_at": _now_iso(),
                "source_platform": sys.platform,
                "backup_id": backup_id,
                "files": inventory,
            }
            (stage / BACKUP_MANIFEST).write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8")
            staged_backup = inspect_backup(str(stage))
            staged_backup_bindings = {
                Path(BACKUP_PAYLOAD) / relative: identity
                for relative, identity in staged_backup["file_identities"].items()
            }
            expected_stage_paths = {
                Path(LIBRARY_MARKER),
                Path(BACKUP_MANIFEST),
                *staged_backup_bindings.keys(),
            }
            stage_bindings = _bind_exact_regular_inventory(
                stage,
                expected_stage_paths,
                validated_bindings=staged_backup_bindings,
            )
            published_files: dict[Path, _RegularIdentity] = {}
            destination_identity = _exclusive_publish_directory(
                stage,
                stage_identity,
                destination,
                bound_regulars=stage_bindings,
                published_regulars=published_files,
            )
            destination_created = True
            _assert_published_identity(destination, destination_identity)
            published_backup = inspect_backup(str(destination))
            published_backup_bindings = {
                Path(BACKUP_PAYLOAD) / relative: identity
                for relative, identity in published_backup["file_identities"].items()
            }
            if any(
                published_files.get(relative) != identity
                for relative, identity in published_backup_bindings.items()
            ):
                raise APICallFailed(
                    "Published backup file identities changed after exclusive publication.",
                    details={"backup_path": str(destination), "possible_mutation": True},
                    recoverability="manual",
                )
            _assert_exact_bound_inventory(
                destination,
                {
                    destination / relative: identity
                    for relative, identity in published_files.items()
                },
                possible_mutation=True,
            )
            steps.extend(["snapshot_library", "verify_backup_integrity", "publish_backup"])
            if context_close_attempted:
                _restore_context(conn, context)
                steps.append("restore_original_context")
            _remove_internal_stage(stage, stage_identity)
            stage = None
            stage_identity = None
        except Exception as exc:
            cleanup_errors: list[str] = []
            uncertain_publication = bool((getattr(exc, "details", {}) or {}).get("possible_mutation"))
            if context_close_attempted:
                try:
                    _restore_context(conn, context)
                except Exception as cleanup_exc:
                    cleanup_errors.append(f"context:{cleanup_exc.__class__.__name__}")
            if stage is not None and stage_identity is not None and stage.exists():
                try:
                    _remove_internal_stage(stage, stage_identity)
                except Exception as cleanup_exc:
                    cleanup_errors.append(f"internal_stage:{cleanup_exc.__class__.__name__}")
            # Never recursively delete a caller-visible path after failure. A
            # same-user process can swap a path between validation and removal;
            # preserving the owned partial is safer and makes recovery explicit.
            if destination_created:
                cleanup_errors.append("destination:preserved_for_manual_recovery")
            raise _failure(
                "Project-library backup failed.",
                phase="backup",
                possible_mutation=destination_created or uncertain_publication or context_close_attempted,
                manual_recovery_required=destination_created or uncertain_publication or bool(cleanup_errors),
                recovery={
                    "cleanup_errors": cleanup_errors,
                    "source_library_unchanged": True,
                    "backup_path": str(destination),
                    "context_restored": not any(item.startswith("context:") for item in cleanup_errors),
                    "steps": [
                        "Confirm the original project library and project/timeline context in DaVinci Resolve.",
                        f"Inspect the preserved partial backup directory: {destination}",
                        "Remove the partial directory manually only after verifying it is still the exact failed-operation target.",
                        "Retry with a new explicit destination; overwrite is not supported.",
                    ],
                },
                error=exc,
                steps=steps,
            ) from exc
    set_verification_status("verified")
    set_recoverability("manual")
    return {
        "library": {"name": normalized_name, "type": "Disk"},
        "backup": {"path": str(destination), "id": backup_id, "file_count": len(inventory)},
        "changed": True,
        "verification": {"integrity": "verified", "context_restored": True},
        "steps": steps,
        "possible_mutation": False,
        "manual_recovery_required": False,
    }


def preflight_restore(*, path: str, name: str, dir_path: str) -> dict[str, Any]:
    backup = inspect_backup(path)
    normalized_name = _normalize_name(name)
    target = _normalize_explicit_path(dir_path, kind="library_target", must_exist=False)
    registry_path, _original, rows = _registry_state()
    _assert_new_target(normalized_name, target, rows)
    return {
        "backup": backup,
        "name": normalized_name,
        "target_root": target,
        "registry_path": registry_path,
    }


def restore_library(
    conn: Any, *, path: str, name: str, dir_path: str,
    expected_parent_identity: tuple[int, int] | None = None,
) -> dict[str, Any]:
    preflight = preflight_restore(path=path, name=name, dir_path=dir_path)
    backup = dict(preflight["backup"])
    normalized_name = str(preflight["name"])
    target = Path(preflight["target_root"])
    registry_path = Path(preflight["registry_path"])
    activate_registration = _registration_activation_strategy(conn)
    payload_root = Path(backup["payload_root"])
    manifest = dict(backup["manifest"])
    context = _capture_context(conn)
    operation_id = uuid4().hex
    steps: list[str] = []
    stage: Path | None = None
    stage_identity: tuple[int, int] | None = None
    target_created = False
    target_identity: tuple[int, int] | None = None
    registration_attempted = False
    registry_changed = False
    with _library_lock(registry_path):
        try:
            registry_path, _registry_original, rows = _registry_state()
            _assert_new_target(normalized_name, target, rows)
            locked_backup = inspect_backup(str(backup["root"]))
            if locked_backup["manifest"].get("backup_id") != manifest.get("backup_id"):
                raise _validation(
                    "Project-library backup identity changed before restore started.",
                    reason="backup_identity_changed",
                )
            payload_root = Path(locked_backup["payload_root"])
            manifest = dict(locked_backup["manifest"])
            locked_file_identities = dict(locked_backup["file_identities"])
            stage, stage_identity = _new_internal_stage("library-restore")
            _write_marker(
                stage,
                _created_marker(
                    normalized_name,
                    operation_id=operation_id,
                    backup_id=str(manifest["backup_id"]),
                ),
            )
            for row in manifest["files"]:
                relative = _safe_relative(str(row["path"]))
                _copy_bound_regular(
                    payload_root / relative,
                    stage / relative,
                    sqlite_file=bool(row.get("sqlite")),
                    expected_identity=locked_file_identities[relative],
                )
            restored_user_root = stage / "Resolve Projects" / "Users" / "guest"
            (restored_user_root / "Projects").mkdir(parents=True, exist_ok=True)
            (restored_user_root / "Configs").mkdir(parents=True, exist_ok=True)
            _assert_exact_bound_inventory(
                payload_root,
                {
                    payload_root / relative: identity
                    for relative, identity in locked_file_identities.items()
                },
                possible_mutation=False,
            )
            _validate_library_root(stage, require_databases=True)
            # Validate the exact copied bytes again; filesystem or interrupted
            # copy failures must be caught before registration.
            declared_paths = {str(row["path"]) for row in manifest["files"]}
            actual_paths = {
                item.relative_to(stage).as_posix()
                for item in _walk_regular_files(stage)
                if item.name != LIBRARY_MARKER
            }
            if actual_paths != declared_paths:
                raise APICallFailed(
                    "Restored project-library staging inventory did not match the backup manifest.",
                    details={
                        "undeclared": sorted(actual_paths - declared_paths),
                        "missing": sorted(declared_paths - actual_paths),
                    },
                )
            staged_file_identities: dict[Path, _RegularIdentity] = {}
            for row in manifest["files"]:
                copied = stage / _safe_relative(str(row["path"]))
                relative = _safe_relative(str(row["path"]))
                if not copied.is_file():
                    raise APICallFailed(
                        "Restored project-library staging copy failed integrity verification.",
                        details={"relative_path": row["path"]},
                    )
                (staged_result, staged_identity) = _with_bound_regular(
                    copied,
                    lambda bound: {
                        "sha256": _hash_file(bound),
                        "sqlite": (
                            _sqlite_integrity(
                                bound,
                                require_resolve_schema=copied.name
                                in {"Project.db", "User.db"},
                            )
                            if row.get("sqlite")
                            else None
                        ),
                        "catalog": (
                            _validate_user_catalog(bound, require_empty=False)
                            if relative == _USER_CATALOG_RELATIVE
                            else None
                        ),
                    },
                    return_identity=True,
                )
                if staged_result["sha256"] != row["sha256"]:
                    raise APICallFailed(
                        "Restored project-library staging copy failed integrity verification.",
                        details={"relative_path": row["path"]},
                    )
                staged_file_identities[relative] = staged_identity
            _assert_regular_bindings(
                {stage / relative: identity for relative, identity in staged_file_identities.items()},
                possible_mutation=False,
            )
            projects_prefix = ("Resolve Projects", "Users", "guest", "Projects")
            expected_projects = sorted(
                relative.parts[len(projects_prefix)]
                for relative in staged_file_identities
                if relative.parts[: len(projects_prefix)] == projects_prefix
                and len(relative.parts) == len(projects_prefix) + 2
                and relative.name == "Project.db"
            )
            stage_bindings = _bind_exact_regular_inventory(
                stage,
                {Path(LIBRARY_MARKER), *staged_file_identities.keys()},
                validated_bindings=staged_file_identities,
            )
            published_files: dict[Path, _RegularIdentity] = {}
            target_identity = _exclusive_publish_directory(
                stage,
                stage_identity,
                target,
                bound_regulars=stage_bindings,
                published_regulars=published_files,
                **({"expected_parent_identity": expected_parent_identity} if expected_parent_identity is not None else {}),
            )
            target_created = True
            steps.extend(["validate_backup", "stage_restore", "verify_staging_integrity"])
            _assert_published_identity(target, target_identity)
            target_catalog = target / _USER_CATALOG_RELATIVE
            _catalog_validation, target_catalog_identity = _validate_bound_user_catalog_identity(
                target_catalog
            )
            if target_catalog_identity != published_files.get(_USER_CATALOG_RELATIVE):
                raise APICallFailed(
                    "Published restored catalog identity changed after exclusive publication.",
                    details={"target_root": str(target), "possible_mutation": True},
                    recoverability="manual",
                )
            target_file_bindings = {
                target / relative: identity for relative, identity in published_files.items()
            }
            _assert_exact_bound_inventory(
                target, target_file_bindings, possible_mutation=True
            )
            registration_attempted = True
            _append_registry_entry(registry_path, name=normalized_name, root=target)
            _assert_published_identity(target, target_identity)
            _assert_exact_bound_inventory(
                target, target_file_bindings, possible_mutation=True
            )
            registry_changed = True
            steps.append("register_restored_library")
            activate_registration(name=normalized_name, context=dict(context))
            steps.append("activate_registered_library")
            verification = _probe_library(
                conn,
                name=normalized_name,
                context=context,
                expected_projects=expected_projects,
                regular_bindings=target_file_bindings,
                inventory_root=target,
                capture_post_activation_inventory=True,
            )
            steps.extend(["reopen_readback_round_1", "reopen_readback_round_2", "restore_original_context"])
            _remove_internal_stage(stage, stage_identity)
            stage = None
            stage_identity = None
        except Exception as exc:
            cleanup_errors: list[str] = []
            uncertain_publication = bool((getattr(exc, "details", {}) or {}).get("possible_mutation"))
            if registration_attempted:
                try:
                    _restore_context(conn, context)
                except Exception as cleanup_exc:
                    cleanup_errors.append(f"context:{cleanup_exc.__class__.__name__}")
            if stage is not None and stage_identity is not None and stage.exists():
                try:
                    _remove_internal_stage(stage, stage_identity)
                except Exception as cleanup_exc:
                    cleanup_errors.append(f"internal_stage:{cleanup_exc.__class__.__name__}")
            # Preserve target + registry after registration is attempted. This
            # prevents deleting the library DaVinci Resolve may still target.
            manual_recovery = target_created or uncertain_publication or registration_attempted or bool(cleanup_errors)
            raise _failure(
                "Project-library restore failed.",
                phase="restore",
                possible_mutation=target_created or uncertain_publication or registration_attempted,
                manual_recovery_required=manual_recovery,
                recovery={
                    "cleanup_errors": cleanup_errors,
                    "target_root": str(target),
                    "backup_id": manifest.get("backup_id"),
                    "target_preserved": target_created or uncertain_publication,
                    "registration_append_attempted": registration_attempted,
                    "registration_verified": registry_changed,
                    "context_restored": not any(item.startswith("context:") for item in cleanup_errors),
                    "steps": [
                        "Confirm DaVinci Resolve is on the original Disk project library before changing files.",
                        f"Inspect the preserved restore target: {target}",
                        f"Inspect the append-only project-library registry entry in: {registry_path}",
                        "Reconcile the registration or remove the target manually only after confirming DaVinci Resolve is not using it.",
                        f"Keep the source backup immutable: {backup['root']}",
                    ],
                },
                error=exc,
                steps=steps,
            ) from exc
    set_verification_status("verified")
    set_recoverability("manual")
    return {
        "library": {"name": normalized_name, "type": "Disk", "root": str(target)},
        "backup": {"path": str(backup["root"]), "id": manifest["backup_id"]},
        "changed": True,
        "verification": verification,
        "steps": steps,
        "possible_mutation": False,
        "manual_recovery_required": False,
    }
