"""Project-level version checkpoints backed by local DaVinci Resolve Project.db snapshots."""

from __future__ import annotations

from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import stat
import sys
from typing import Any
from uuid import uuid4

from ..connection import ResolveConnection
from ..errors import APICallFailed, ValidationError
from ..output import set_recoverability, set_verification_status
from ..runtime_health import (
    close_current_project_with_runtime_health,
    resolve_current_disk_project_db,
)


CHECKPOINT_SCHEMA_VERSION = 2
RESTORE_STRATEGY = "project_db_snapshot"
CHECKPOINT_KINDS = {
    "before_prompt",
    "after_prompt",
    "manual_commit",
}
UNSUPPORTED_DB_MESSAGE = (
    "Version history requires a local DaVinci Resolve Disk project library. "
    "Blackmagic Cloud and Project Server projects are not supported for local DB snapshots yet."
)
PROJECT_DB_IDENTITY_UNAVAILABLE_MESSAGE = (
    "Version history could not identify the active DaVinci Resolve Disk Project.db. "
    "Update or reinstall the CutAgent embedded bridge, then try again."
)


def _now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _unsafe_checkpoint_store(
    *, reason: str, error: str | None = None
) -> ValidationError:
    details: dict[str, Any] = {"reason": reason}
    if error:
        details["error"] = error
    return ValidationError(
        "CutAgent could not use its private checkpoint storage safely. Restart CutAgent and try again. "
        "If the problem continues, repair the ownership of the CutAgent application-data folder.",
        details=details,
        recoverability="manual",
    )


def _supports_posix_checkpoint_permissions() -> bool:
    """Return whether chmod/uid checks have POSIX filesystem semantics."""

    return os.name == "posix"


def _set_private_checkpoint_mode(path: Path, mode: int) -> None:
    if _supports_posix_checkpoint_permissions():
        path.chmod(mode)


def _is_checkpoint_path_redirect(path: Path) -> bool:
    """Reject links and Windows junctions before following checkpoint paths."""

    return path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction())


def _checkpoint_store_dir() -> Path:
    configured = os.environ.get("CUTAGENT_CHECKPOINT_DIR")
    if configured and configured.strip():
        raw_store = Path(configured).expanduser()
    elif sys.platform == "win32":
        appdata = os.environ.get("APPDATA", "").strip()
        roaming_root = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
        raw_store = roaming_root / "CutAgent" / "checkpoints"
    else:
        raw_store = (
            Path.home() / "Library" / "Application Support" / "CutAgent" / "checkpoints"
        )

    store = Path(os.path.abspath(raw_store))
    candidates = [*reversed(store.parents), store]
    for candidate in candidates:
        if candidate == Path(candidate.anchor):
            continue
        if _is_checkpoint_path_redirect(candidate):
            raise _unsafe_checkpoint_store(reason="checkpoint_store_symlink")
        if candidate.exists() and not candidate.is_dir():
            raise _unsafe_checkpoint_store(reason="checkpoint_store_not_directory")

    try:
        store.mkdir(parents=True, exist_ok=True, mode=0o700)
    except OSError as exc:
        raise _unsafe_checkpoint_store(
            reason="checkpoint_store_unavailable", error=str(exc)
        ) from exc

    # Recheck after creation so an existing symlink or non-directory cannot be
    # hidden by pathlib's normal path resolution. The app controls this root;
    # fail closed instead of falling back to a user-writable arbitrary path.
    if _is_checkpoint_path_redirect(store) or not store.is_dir():
        raise _unsafe_checkpoint_store(reason="checkpoint_store_unsafe")
    try:
        if _supports_posix_checkpoint_permissions():
            metadata = store.stat()
            if metadata.st_uid != os.getuid():
                raise _unsafe_checkpoint_store(reason="checkpoint_store_wrong_owner")
            _set_private_checkpoint_mode(store, 0o700)
            if stat.S_IMODE(store.stat().st_mode) != 0o700:
                raise _unsafe_checkpoint_store(reason="checkpoint_store_permissions")
    except ValidationError:
        raise
    except OSError as exc:
        raise _unsafe_checkpoint_store(
            reason="checkpoint_store_unavailable", error=str(exc)
        ) from exc
    return store


def _index_path() -> Path:
    return _checkpoint_store_dir() / "index.json"


def _checkpoint_subdir(name: str) -> Path:
    store = _checkpoint_store_dir()
    target = store / name
    if _is_checkpoint_path_redirect(target):
        raise _unsafe_checkpoint_store(reason="checkpoint_store_symlink")
    try:
        target.mkdir(mode=0o700, exist_ok=True)
        if _is_checkpoint_path_redirect(target) or not target.is_dir():
            raise _unsafe_checkpoint_store(reason="checkpoint_store_unsafe")
        if _supports_posix_checkpoint_permissions():
            metadata = target.stat()
            if metadata.st_uid != os.getuid():
                raise _unsafe_checkpoint_store(reason="checkpoint_store_wrong_owner")
            _set_private_checkpoint_mode(target, 0o700)
    except ValidationError:
        raise
    except OSError as exc:
        raise _unsafe_checkpoint_store(
            reason="checkpoint_store_unavailable", error=str(exc)
        ) from exc
    return target


def _snapshot_dir() -> Path:
    return _checkpoint_subdir("snapshots")


def _snapshot_path(db_hash: str) -> Path:
    digest = db_hash.replace("sha256:", "")
    return _snapshot_dir() / f"{digest}.Project.db.gz"


def _read_index() -> dict[str, Any]:
    path = _index_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"schema_version": CHECKPOINT_SCHEMA_VERSION, "checkpoints": []}

    checkpoints = raw.get("checkpoints")
    if not isinstance(checkpoints, list):
        checkpoints = []
    return {
        "schema_version": int(raw.get("schema_version") or CHECKPOINT_SCHEMA_VERSION),
        "checkpoints": [
            item
            for item in checkpoints
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        ],
    }


def _write_index(index: dict[str, Any]) -> None:
    path = _index_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f"{path.name}.{uuid4().hex}.tmp")
    temp.write_text(json.dumps(index, indent=2, sort_keys=True), encoding="utf-8")
    _set_private_checkpoint_mode(temp, 0o600)
    temp.replace(path)
    _set_private_checkpoint_mode(path, 0o600)


def _upsert_checkpoint(record: dict[str, Any]) -> dict[str, Any]:
    index = _read_index()
    if "sequence" not in record:
        existing_sequences = [
            int(item.get("sequence") or 0)
            for item in index["checkpoints"]
            if isinstance(item.get("sequence"), int)
        ]
        record["sequence"] = (max(existing_sequences) if existing_sequences else 0) + 1
    checkpoints = [
        item for item in index["checkpoints"] if item.get("id") != record["id"]
    ]
    checkpoints.append(record)
    checkpoints.sort(
        key=lambda item: (
            str(item.get("created_at") or ""),
            int(item.get("sequence") or 0),
        ),
        reverse=True,
    )
    index["schema_version"] = CHECKPOINT_SCHEMA_VERSION
    index["checkpoints"] = checkpoints
    _write_index(index)
    return record


def _checkpoint_id() -> str:
    return (
        f"chk_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{uuid4().hex[:8]}"
    )


def _call_optional(target: Any, method_names: tuple[str, ...]) -> Any:
    for method_name in method_names:
        method = getattr(target, method_name, None)
        if not callable(method):
            continue
        try:
            return method()
        except Exception:
            continue
    return None


def _timeline_identity(conn) -> dict[str, str | None]:
    project_name = (
        conn.project.GetName()
        if conn.project and hasattr(conn.project, "GetName")
        else None
    )
    timeline_name = (
        conn.timeline.GetName()
        if conn.timeline and hasattr(conn.timeline, "GetName")
        else None
    )
    if not project_name:
        raise ValidationError(
            "No active DaVinci Resolve project for checkpoint creation."
        )
    if not timeline_name:
        raise ValidationError(
            "No active DaVinci Resolve timeline for checkpoint creation."
        )

    raw_timeline_id = _call_optional(
        conn.timeline, ("GetUniqueId", "GetUniqueID", "GetId", "GetID")
    )
    raw_project_id = _call_optional(
        conn.project, ("GetUniqueId", "GetUniqueID", "GetId", "GetID")
    )
    if raw_timeline_id is None:
        raw_timeline_id = hashlib.sha256(
            f"{project_name}:{timeline_name}".encode("utf-8")
        ).hexdigest()[:16]
    return {
        "project_id": str(raw_project_id) if raw_project_id is not None else None,
        "project_name": str(project_name),
        "timeline_name": str(timeline_name),
        "timeline_id": str(raw_timeline_id),
    }


def _raise_unsupported_project_database(error: Exception) -> None:
    details = dict(getattr(error, "details", {}) or {})
    original_message = str(error)
    if "Unsupported embedded DaVinci Resolve method" in original_message:
        raise ValidationError(
            PROJECT_DB_IDENTITY_UNAVAILABLE_MESSAGE,
            details={
                "reason": "embedded_method_unsupported",
                "supported_database_type": "Disk",
                "original_error": {
                    "type": error.__class__.__name__,
                    "message": original_message,
                    "details": details,
                },
            },
            recoverability="manual",
        ) from error

    current_database = details.get("current_database")
    db_type = (
        current_database.get("DbType") if isinstance(current_database, dict) else None
    )
    reason = (
        "unsupported_project_database"
        if db_type and str(db_type) != "Disk"
        else "project_db_unavailable"
    )
    raise ValidationError(
        UNSUPPORTED_DB_MESSAGE,
        details={
            "reason": reason,
            "supported_database_type": "Disk",
            "active_database_type": db_type,
            "current_database": current_database,
            "original_error": {
                "type": error.__class__.__name__,
                "message": original_message,
                "details": details,
            },
        },
        recoverability="manual",
    ) from error


def _resolve_project_db(conn) -> dict[str, Any]:
    try:
        return resolve_current_disk_project_db(conn)
    except (ValidationError, APICallFailed) as exc:
        _raise_unsupported_project_database(exc)
        raise


def _save_project(conn) -> bool:
    project_manager = getattr(conn, "project_manager", None)
    save_project = (
        getattr(project_manager, "SaveProject", None)
        if project_manager is not None
        else None
    )
    if not callable(save_project):
        return False
    try:
        return bool(save_project())
    except Exception as exc:
        raise APICallFailed(
            "DaVinci Resolve failed to save the project before creating a version checkpoint.",
            details={"error": str(exc)},
            recoverability="manual",
        ) from exc


def _hash_file(path: Path) -> str:
    sha = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            sha.update(chunk)
    return f"sha256:{sha.hexdigest()}"


def _sqlite_backup_copy(source_path: Path, dest_path: Path) -> None:
    source_uri = f"file:{source_path}?mode=ro"
    source = None
    dest = None
    try:
        source = sqlite3.connect(source_uri, uri=True, timeout=5.0)
        dest = sqlite3.connect(str(dest_path), timeout=5.0)
        source.backup(dest)
    except sqlite3.Error as exc:
        raise APICallFailed(
            "Failed to create a consistent Project.db snapshot.",
            details={
                "project_db_path": str(source_path),
                "sqlite_error_type": exc.__class__.__name__,
                "sqlite_error": str(exc),
            },
            recoverability="manual",
        ) from exc
    finally:
        if dest is not None:
            dest.close()
        if source is not None:
            source.close()
    _set_private_checkpoint_mode(dest_path, 0o600)


def _compress_db_snapshot(source_path: Path, snapshot_path: Path) -> int:
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    temp = snapshot_path.with_name(f"{snapshot_path.name}.{uuid4().hex}.tmp")
    try:
        with source_path.open("rb") as source, temp.open("wb") as raw_dest:
            with gzip.GzipFile(
                filename="", mode="wb", fileobj=raw_dest, compresslevel=6, mtime=0
            ) as dest:
                shutil.copyfileobj(source, dest, length=1024 * 1024)
        _set_private_checkpoint_mode(temp, 0o600)
        temp.replace(snapshot_path)
        _set_private_checkpoint_mode(snapshot_path, 0o600)
    finally:
        if temp.exists():
            temp.unlink(missing_ok=True)
    return snapshot_path.stat().st_size


def _create_db_snapshot(project_db_path: str) -> dict[str, Any]:
    source = Path(project_db_path).expanduser()
    if not source.exists() or not source.is_file():
        raise ValidationError(
            "Resolved Project.db path is missing from disk.",
            details={
                "reason": "project_db_missing",
                "project_db_path": str(source),
            },
            recoverability="manual",
        )

    temp_dir = _checkpoint_subdir("tmp")
    temp_db = temp_dir / f"Project.{uuid4().hex}.db"
    try:
        _sqlite_backup_copy(source, temp_db)
        db_hash = _hash_file(temp_db)
        snapshot_path = _snapshot_path(db_hash)
        if snapshot_path.exists():
            compressed_size = snapshot_path.stat().st_size
            deduplicated = True
        else:
            compressed_size = _compress_db_snapshot(temp_db, snapshot_path)
            deduplicated = False
        return {
            "state_hash": db_hash,
            "db_hash": db_hash,
            "snapshot_path": str(snapshot_path),
            "snapshot_deduplicated": deduplicated,
            "db_size": temp_db.stat().st_size,
            "snapshot_size": compressed_size,
        }
    finally:
        temp_db.unlink(missing_ok=True)


def _stable_project_db_hash(project_db_path: str) -> str:
    temp_dir = _checkpoint_subdir("tmp")
    temp_db = temp_dir / f"status.{uuid4().hex}.Project.db"
    try:
        _sqlite_backup_copy(Path(project_db_path).expanduser(), temp_db)
        return _hash_file(temp_db)
    finally:
        temp_db.unlink(missing_ok=True)


def _decompress_snapshot(checkpoint: dict[str, Any], *, checkpoint_id: str) -> Path:
    source = _validate_checkpoint_snapshot_path(checkpoint, checkpoint_id=checkpoint_id)
    temp_dir = _checkpoint_subdir("tmp")
    dest = temp_dir / f"restore.{uuid4().hex}.Project.db"
    try:
        with gzip.open(source, "rb") as compressed, dest.open("wb") as restored:
            shutil.copyfileobj(compressed, restored, length=1024 * 1024)
    except OSError as exc:
        dest.unlink(missing_ok=True)
        raise APICallFailed(
            "Failed to read Project.db snapshot.",
            details={"snapshot_path": str(source), "error": str(exc)},
            recoverability="manual",
        ) from exc
    return dest


def create_checkpoint(
    conn,
    *,
    label: str,
    kind: str = "manual_commit",
    session_id: str | None = None,
    prompt_event_id: str | None = None,
    parent_checkpoint_id: str | None = None,
    expected_parent_checkpoint_digest: str | None = None,
    exact_checkpoint_id: str | None = None,
) -> dict[str, Any]:
    normalized_kind = str(kind or "").strip()
    if normalized_kind not in CHECKPOINT_KINDS:
        raise ValidationError(
            "Unsupported checkpoint kind.",
            details={"kind": kind, "allowed": sorted(CHECKPOINT_KINDS)},
            recoverability="not_applicable",
        )

    # Storage safety is a preflight: an unsafe app-data path must not cause a
    # project save or any other DaVinci Resolve state change.
    _checkpoint_store_dir()
    conn.require_timeline()
    identity = _timeline_identity(conn)
    project_db = _resolve_project_db(conn)
    parent_checkpoint = (
        inspect_checkpoint(parent_checkpoint_id) if parent_checkpoint_id else None
    )
    if expected_parent_checkpoint_digest is not None and (
        parent_checkpoint is None
        or checkpoint_binding_digest(parent_checkpoint)
        != expected_parent_checkpoint_digest
    ):
        raise ValidationError(
            "Parent checkpoint changed after prepared-action authorization.",
            details={"reason": "parent_checkpoint_binding_mismatch"},
            recoverability="not_applicable",
        )
    checkpoint_id = str(exact_checkpoint_id or _checkpoint_id()).strip()
    if (
        not checkpoint_id
        or len(checkpoint_id) > 160
        or any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-" for character in checkpoint_id)
    ):
        raise ValidationError(
            "Exact checkpoint identity is invalid.",
            details={"checkpoint_id": checkpoint_id},
            recoverability="not_applicable",
        )
    if exact_checkpoint_id is not None and get_checkpoint(checkpoint_id) is not None:
        raise ValidationError(
            "Exact checkpoint identity already exists.",
            details={"checkpoint_id": checkpoint_id},
            recoverability="not_applicable",
        )
    save_called = _save_project(conn)
    snapshot = _create_db_snapshot(str(project_db["project_db_path"]))

    record = {
        "id": checkpoint_id,
        "created_at": _now_iso(),
        "kind": normalized_kind,
        "project_name": identity["project_name"],
        "timeline_name": identity["timeline_name"],
        "timeline_id": identity["timeline_id"],
        "session_id": session_id,
        "prompt_event_id": prompt_event_id,
        "label": str(label or "").strip()
        or f"{normalized_kind.replace('_', ' ').title()}: {identity['project_name']}",
        "restore_strategy": RESTORE_STRATEGY,
        "state_hash": snapshot["state_hash"],
        "db_hash": snapshot["db_hash"],
        "project_db_path": str(project_db["project_db_path"]),
        "database_name": project_db.get("DbName"),
        "database_type": project_db.get("DbType"),
        "snapshot_path": snapshot["snapshot_path"],
        "snapshot_deduplicated": snapshot["snapshot_deduplicated"],
        "db_size": snapshot["db_size"],
        "snapshot_size": snapshot["snapshot_size"],
        "project_save_called": save_called,
        "parent_checkpoint_id": parent_checkpoint_id,
        "changed_from_parent": (
            None
            if parent_checkpoint is None
            else snapshot["state_hash"] != parent_checkpoint.get("state_hash")
        ),
    }
    set_verification_status("verified")
    set_recoverability("manual")
    return _upsert_checkpoint(record)


def list_checkpoints(
    *,
    project_name: str | None = None,
    timeline_name: str | None = None,
    session_id: str | None = None,
) -> list[dict[str, Any]]:
    rows = list(_read_index()["checkpoints"])
    if project_name:
        rows = [row for row in rows if row.get("project_name") == project_name]
    if timeline_name:
        rows = [row for row in rows if row.get("timeline_name") == timeline_name]
    if session_id:
        rows = [row for row in rows if row.get("session_id") == session_id]
    return sorted(
        rows,
        key=lambda item: (
            str(item.get("created_at") or ""),
            int(item.get("sequence") or 0),
        ),
        reverse=True,
    )


def _commit_checkpoint_prune(
    *,
    index: dict[str, Any],
    removed: list[dict[str, Any]],
    remaining: list[dict[str, Any]],
    session_id: str,
) -> dict[str, Any]:
    index["schema_version"] = CHECKPOINT_SCHEMA_VERSION
    index["checkpoints"] = remaining
    _write_index(index)

    remaining_snapshot_paths = {
        str(row.get("snapshot_path") or "")
        for row in remaining
        if row.get("snapshot_path")
    }
    snapshot_root = _snapshot_dir().resolve()
    deleted_snapshot_count = 0
    deleted_snapshot_bytes = 0
    skipped_snapshot_count = 0
    retained_snapshot_count = 0
    failed_snapshot_delete_count = 0
    seen_snapshot_paths: set[str] = set()

    for row in removed:
        snapshot_path = str(row.get("snapshot_path") or "")
        if (
            not snapshot_path
            or snapshot_path in remaining_snapshot_paths
            or snapshot_path in seen_snapshot_paths
        ):
            if snapshot_path:
                skipped_snapshot_count += 1
                retained_snapshot_count += 1
            continue
        seen_snapshot_paths.add(snapshot_path)
        try:
            candidate = Path(snapshot_path).expanduser().resolve()
            if snapshot_root not in candidate.parents:
                skipped_snapshot_count += 1
                failed_snapshot_delete_count += 1
                continue
            if not candidate.exists() or not candidate.is_file():
                skipped_snapshot_count += 1
                failed_snapshot_delete_count += 1
                continue
            size = candidate.stat().st_size
            candidate.unlink()
            deleted_snapshot_count += 1
            deleted_snapshot_bytes += size
        except Exception:
            skipped_snapshot_count += 1
            failed_snapshot_delete_count += 1

    result = {
        "session_id": session_id,
        "pruned_checkpoint_ids": sorted(str(row["id"]) for row in removed),
        "pruned_checkpoint_count": len(removed),
        "remaining_checkpoint_count": len(remaining),
        "deleted_snapshot_count": deleted_snapshot_count,
        "deleted_snapshot_bytes": deleted_snapshot_bytes,
        "skipped_snapshot_count": skipped_snapshot_count,
        "retained_snapshot_count": retained_snapshot_count,
        "failed_snapshot_delete_count": failed_snapshot_delete_count,
    }
    if failed_snapshot_delete_count:
        set_verification_status("failed")
        set_recoverability("manual")
        raise APICallFailed(
            "Checkpoint records were pruned, but one or more private snapshots could not be deleted.",
            details={
                "reason": "checkpoint_snapshot_delete_failed",
                "pruned_checkpoint_count": len(removed),
                "failed_snapshot_delete_count": failed_snapshot_delete_count,
            },
            recoverability="manual",
        )
    set_verification_status("verified")
    set_recoverability("manual")
    return result


def prune_checkpoints_exact(
    session_id: str,
    checkpoint_ids: list[str] | tuple[str, ...],
    *,
    project_name: str,
    timeline_id: str,
) -> dict[str, Any]:
    """Delete exactly the prepared checkpoint identities and no later additions."""

    normalized_session_id = str(session_id or "").strip()
    normalized_project_name = str(project_name or "").strip()
    normalized_timeline_id = str(timeline_id or "").strip()
    normalized_ids = [
        str(checkpoint_id or "").strip() for checkpoint_id in checkpoint_ids
    ]
    if not normalized_session_id:
        raise ValidationError(
            "Session id is required for checkpoint pruning.",
            details={"reason": "missing_session_id"},
            recoverability="not_applicable",
        )
    if not normalized_project_name or not normalized_timeline_id:
        raise ValidationError(
            "Exact project and timeline identity are required for checkpoint pruning.",
            details={"reason": "missing_checkpoint_context"},
            recoverability="not_applicable",
        )
    if not normalized_ids or any(not checkpoint_id for checkpoint_id in normalized_ids):
        raise ValidationError(
            "Exact checkpoint ids are required for prepared checkpoint pruning.",
            details={"reason": "missing_checkpoint_ids"},
            recoverability="not_applicable",
        )
    if len(set(normalized_ids)) != len(normalized_ids):
        raise ValidationError(
            "Prepared checkpoint pruning contains duplicate checkpoint ids.",
            details={"reason": "duplicate_checkpoint_ids"},
            recoverability="not_applicable",
        )

    index = _read_index()
    requested = set(normalized_ids)
    removed = [row for row in index["checkpoints"] if row.get("id") in requested]
    resolved_ids = [str(row.get("id") or "") for row in removed]
    if set(resolved_ids) != requested or len(resolved_ids) != len(requested):
        raise ValidationError(
            "Prepared checkpoint identities are missing or ambiguous.",
            details={"reason": "checkpoint_set_changed"},
            recoverability="not_applicable",
        )
    if any(row.get("session_id") != normalized_session_id for row in removed):
        raise ValidationError(
            "Prepared checkpoint identity belongs to a different session.",
            details={"reason": "checkpoint_session_mismatch"},
            recoverability="not_applicable",
        )
    if any(
        row.get("project_name") != normalized_project_name
        or row.get("timeline_id") != normalized_timeline_id
        for row in removed
    ):
        raise ValidationError(
            "Prepared checkpoint identity belongs to a different project or timeline.",
            details={"reason": "checkpoint_context_mismatch"},
            recoverability="not_applicable",
        )
    remaining = [row for row in index["checkpoints"] if row.get("id") not in requested]
    return _commit_checkpoint_prune(
        index=index,
        removed=removed,
        remaining=remaining,
        session_id=normalized_session_id,
    )


def prune_checkpoints_for_session(session_id: str) -> dict[str, Any]:
    normalized_session_id = str(session_id or "").strip()
    if not normalized_session_id:
        raise ValidationError(
            "Session id is required for checkpoint pruning.",
            details={"reason": "missing_session_id"},
            recoverability="not_applicable",
        )

    index = _read_index()
    removed = [
        row
        for row in index["checkpoints"]
        if row.get("session_id") == normalized_session_id
    ]
    remaining = [
        row
        for row in index["checkpoints"]
        if row.get("session_id") != normalized_session_id
    ]
    result = _commit_checkpoint_prune(
        index=index,
        removed=removed,
        remaining=remaining,
        session_id=normalized_session_id,
    )
    result.pop("pruned_checkpoint_ids")
    return result


def get_checkpoint(checkpoint_id: str | None) -> dict[str, Any] | None:
    if not checkpoint_id:
        return None
    for checkpoint in _read_index()["checkpoints"]:
        if checkpoint.get("id") == checkpoint_id:
            return checkpoint
    return None


def inspect_checkpoint(checkpoint_id: str) -> dict[str, Any]:
    checkpoint = get_checkpoint(checkpoint_id)
    if checkpoint is None:
        raise ValidationError(
            "Checkpoint not found.",
            details={"checkpoint_id": checkpoint_id},
            recoverability="not_applicable",
        )
    return checkpoint


def checkpoint_binding_digest(checkpoint: dict[str, Any]) -> str:
    """Bind the complete durable checkpoint record used by a prepared action."""

    if not isinstance(checkpoint, dict) or not checkpoint:
        raise ValidationError(
            "Checkpoint binding is unavailable.",
            details={"reason": "checkpoint_binding_unavailable"},
            recoverability="not_applicable",
        )
    payload = json.dumps(
        checkpoint,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _normalize_identity_value(value: Any) -> str:
    return str(value or "").strip()


def _paths_match(left: str | None, right: str | None) -> bool:
    if not left or not right:
        return False
    try:
        return Path(left).expanduser().resolve() == Path(right).expanduser().resolve()
    except Exception:
        return str(left) == str(right)


def _path_is_inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _active_project_name(conn) -> str | None:
    project = getattr(conn, "project", None)
    get_name = getattr(project, "GetName", None)
    if not callable(get_name):
        return None
    try:
        name = str(get_name() or "").strip()
    except Exception:
        return None
    return name or None


def _require_checkpoint_identity_fields(
    checkpoint: dict[str, Any], *, checkpoint_id: str, fields: list[str]
) -> None:
    missing = [
        field
        for field in fields
        if not _normalize_identity_value(checkpoint.get(field))
    ]
    if not missing:
        return
    raise ValidationError(
        "Checkpoint is missing restore identity metadata.",
        details={
            "reason": "checkpoint_identity_incomplete",
            "checkpoint_id": checkpoint_id,
            "missing_fields": missing,
        },
        recoverability="manual",
    )


def _validate_restore_session(
    checkpoint: dict[str, Any],
    *,
    checkpoint_id: str,
    expected_session_id: str | None,
) -> None:
    normalized_expected = _normalize_identity_value(expected_session_id)
    if not normalized_expected:
        return
    _require_checkpoint_identity_fields(
        checkpoint,
        checkpoint_id=checkpoint_id,
        fields=["session_id", "timeline_id", "project_db_path", "database_type"],
    )
    actual = _normalize_identity_value(checkpoint.get("session_id"))
    if actual != normalized_expected:
        raise ValidationError(
            "Checkpoint belongs to a different CutAgent chat.",
            details={
                "reason": "session_mismatch",
                "checkpoint_id": checkpoint_id,
                "expected_session_id": normalized_expected,
                "checkpoint_session_id": actual or None,
            },
            recoverability="manual",
        )


def _validate_restore_strategy(
    checkpoint: dict[str, Any], *, checkpoint_id: str
) -> None:
    if checkpoint.get("restore_strategy") != RESTORE_STRATEGY:
        raise ValidationError(
            "Unsupported checkpoint restore strategy.",
            details={
                "reason": "unsupported_restore_strategy",
                "checkpoint_id": checkpoint_id,
                "restore_strategy": checkpoint.get("restore_strategy"),
                "supported_restore_strategy": RESTORE_STRATEGY,
            },
            recoverability="manual",
        )


def _validate_restore_target_identity(
    checkpoint: dict[str, Any],
    *,
    checkpoint_id: str,
    active_identity: dict[str, str | None],
    active_project_db: dict[str, Any],
) -> None:
    if active_identity["project_name"] != checkpoint.get("project_name"):
        raise ValidationError(
            "Checkpoint belongs to a different DaVinci Resolve project.",
            details={
                "reason": "project_mismatch",
                "checkpoint_id": checkpoint_id,
                "expected_project_name": checkpoint.get("project_name"),
                "active_project_name": active_identity["project_name"],
            },
            recoverability="manual",
        )

    checkpoint_database_type = _normalize_identity_value(
        checkpoint.get("database_type")
    )
    active_database_type = _normalize_identity_value(active_project_db.get("DbType"))
    if (
        checkpoint_database_type
        and active_database_type
        and checkpoint_database_type != active_database_type
    ):
        raise ValidationError(
            "Checkpoint belongs to a different DaVinci Resolve project library type.",
            details={
                "reason": "database_type_mismatch",
                "checkpoint_id": checkpoint_id,
                "expected_database_type": checkpoint.get("database_type"),
                "active_database_type": active_project_db.get("DbType"),
            },
            recoverability="manual",
        )

    checkpoint_database_name = _normalize_identity_value(
        checkpoint.get("database_name")
    )
    active_database_name = _normalize_identity_value(active_project_db.get("DbName"))
    if (
        checkpoint_database_name
        and active_database_name
        and checkpoint_database_name != active_database_name
    ):
        raise ValidationError(
            "Checkpoint belongs to a different DaVinci Resolve project library.",
            details={
                "reason": "database_name_mismatch",
                "checkpoint_id": checkpoint_id,
                "expected_database_name": checkpoint.get("database_name"),
                "active_database_name": active_project_db.get("DbName"),
            },
            recoverability="manual",
        )

    checkpoint_db_path = _normalize_identity_value(checkpoint.get("project_db_path"))
    active_db_path = _normalize_identity_value(active_project_db.get("project_db_path"))
    if (
        checkpoint_db_path
        and active_db_path
        and not _paths_match(checkpoint_db_path, active_db_path)
    ):
        raise ValidationError(
            "Checkpoint belongs to a different DaVinci Resolve Project.db.",
            details={
                "reason": "project_db_path_mismatch",
                "checkpoint_id": checkpoint_id,
                "expected_project_db_path": checkpoint_db_path,
                "active_project_db_path": active_db_path,
            },
            recoverability="manual",
        )


def _resolve_known_project_db_path(project_name: str) -> Path | None:
    try:
        from . import native_multicam_db

        resolved = native_multicam_db.resolve_disk_project_db_path(
            project_name=project_name
        )
        project_db_path = str(resolved.get("project_db_path") or "").strip()
        if project_db_path:
            return Path(project_db_path).expanduser().resolve()
    except Exception:
        return None
    return None


def _validate_checkpoint_snapshot_path(
    checkpoint: dict[str, Any], *, checkpoint_id: str
) -> Path:
    raw_snapshot_path = _normalize_identity_value(checkpoint.get("snapshot_path"))
    if not raw_snapshot_path:
        raise ValidationError(
            "Checkpoint is missing restore snapshot metadata.",
            details={
                "reason": "checkpoint_identity_incomplete",
                "checkpoint_id": checkpoint_id,
                "missing_fields": ["snapshot_path"],
            },
            recoverability="manual",
        )

    source = Path(raw_snapshot_path).expanduser()
    if not source.name.endswith(".Project.db.gz"):
        raise ValidationError(
            "Checkpoint snapshot path is not a CutAgent Project.db snapshot.",
            details={
                "reason": "invalid_snapshot_path",
                "checkpoint_id": checkpoint_id,
                "snapshot_path": str(source),
            },
            recoverability="manual",
        )

    try:
        resolved_source = source.resolve()
        snapshot_root = _snapshot_dir().resolve()
    except Exception as exc:
        raise ValidationError(
            "Checkpoint snapshot path could not be resolved safely.",
            details={
                "reason": "invalid_snapshot_path",
                "checkpoint_id": checkpoint_id,
                "snapshot_path": str(source),
                "error": str(exc),
            },
            recoverability="manual",
        ) from exc

    if not _path_is_inside(resolved_source, snapshot_root):
        raise ValidationError(
            "Checkpoint snapshot path is outside the CutAgent checkpoint store.",
            details={
                "reason": "snapshot_path_outside_checkpoint_store",
                "checkpoint_id": checkpoint_id,
                "snapshot_path": str(resolved_source),
                "snapshot_root": str(snapshot_root),
            },
            recoverability="manual",
        )
    if not resolved_source.exists() or not resolved_source.is_file():
        raise ValidationError(
            "Project DB snapshot is missing from disk.",
            details={
                "reason": "snapshot_missing",
                "snapshot_path": str(resolved_source),
            },
            recoverability="manual",
        )
    return resolved_source


def _validate_closed_project_db_target(
    checkpoint: dict[str, Any], *, checkpoint_id: str
) -> Path:
    _require_checkpoint_identity_fields(
        checkpoint,
        checkpoint_id=checkpoint_id,
        fields=["project_name", "project_db_path", "database_type"],
    )

    if _normalize_identity_value(checkpoint.get("database_type")) != "Disk":
        raise ValidationError(
            UNSUPPORTED_DB_MESSAGE,
            details={
                "reason": "unsupported_project_database",
                "checkpoint_id": checkpoint_id,
                "supported_database_type": "Disk",
                "checkpoint_database_type": checkpoint.get("database_type"),
            },
            recoverability="manual",
        )

    project_name = _normalize_identity_value(checkpoint.get("project_name"))
    raw_target = Path(str(checkpoint["project_db_path"])).expanduser()
    if raw_target.name != "Project.db":
        raise ValidationError(
            "Checkpoint Project.db path is not a DaVinci Resolve Project.db file.",
            details={
                "reason": "invalid_project_db_path",
                "checkpoint_id": checkpoint_id,
                "project_db_path": str(raw_target),
                "required_file_name": "Project.db",
            },
            recoverability="manual",
        )
    if raw_target.is_symlink():
        raise ValidationError(
            "Checkpoint Project.db path must not be a symlink.",
            details={
                "reason": "project_db_path_symlink",
                "checkpoint_id": checkpoint_id,
                "project_db_path": str(raw_target),
            },
            recoverability="manual",
        )

    try:
        parent = raw_target.parent.resolve(strict=True)
    except Exception as exc:
        raise ValidationError(
            "Checkpoint Project.db parent directory is missing or unsafe.",
            details={
                "reason": "invalid_project_db_path",
                "checkpoint_id": checkpoint_id,
                "project_db_path": str(raw_target),
                "error": str(exc),
            },
            recoverability="manual",
        ) from exc

    target = parent / raw_target.name
    if target.exists() and (target.is_symlink() or not target.is_file()):
        raise ValidationError(
            "Checkpoint Project.db target is not a regular file.",
            details={
                "reason": "invalid_project_db_path",
                "checkpoint_id": checkpoint_id,
                "project_db_path": str(target),
                "path_exists": target.exists(),
                "is_file": target.is_file(),
            },
            recoverability="manual",
        )

    known_target = _resolve_known_project_db_path(project_name)
    if known_target is not None and not _paths_match(str(known_target), str(target)):
        raise ValidationError(
            "Checkpoint belongs to a different DaVinci Resolve Project.db.",
            details={
                "reason": "project_db_path_mismatch",
                "checkpoint_id": checkpoint_id,
                "expected_project_db_path": str(known_target),
                "checkpoint_project_db_path": str(target),
            },
            recoverability="manual",
        )

    if known_target is None:
        ancestor_names = {ancestor.name for ancestor in target.parents}
        if (
            target.parent.name != project_name
            or target.parent.parent.name != "Projects"
            or "Users" not in ancestor_names
            or "Resolve Projects" not in ancestor_names
        ):
            raise ValidationError(
                "Checkpoint Project.db path is outside a recognized DaVinci Resolve Disk project layout.",
                details={
                    "reason": "unrecognized_project_db_layout",
                    "checkpoint_id": checkpoint_id,
                    "project_name": project_name,
                    "project_db_path": str(target),
                },
                recoverability="manual",
            )

    return target


def _can_fallback_to_checkpoint_target_after_identity_error(error: Exception) -> bool:
    if isinstance(error, APICallFailed):
        return True
    if not isinstance(error, ValidationError):
        return False
    reason = str((getattr(error, "details", {}) or {}).get("reason") or "")
    return reason in {
        "embedded_method_unsupported",
        "project_db_unavailable",
        "project_db_validation_failed",
        "project_db_identity_unavailable",
        "runtime_current_database_invalid",
    }


def _timeline_matches_identity(
    timeline: Any, timeline_name: str | None, timeline_id: str | None
) -> bool:
    expected_timeline_id = _normalize_identity_value(timeline_id)
    actual_timeline_id = _normalize_identity_value(
        _call_optional(timeline, ("GetUniqueId", "GetUniqueID", "GetId", "GetID"))
    )
    if expected_timeline_id and actual_timeline_id:
        return actual_timeline_id == expected_timeline_id
    if not timeline_name:
        return False
    return timeline.GetName() == timeline_name


def _activate_timeline_by_identity(
    conn, timeline_name: str | None, timeline_id: str | None
) -> bool:
    if not timeline_name and not timeline_id:
        return False
    project = getattr(conn, "project", None)
    if project is None:
        return False
    setter = getattr(project, "SetCurrentTimeline", None)
    if not callable(setter):
        return False
    count = int(project.GetTimelineCount() or 0)
    for index in range(1, count + 1):
        timeline = project.GetTimelineByIndex(index)
        if timeline and _timeline_matches_identity(
            timeline, timeline_name, timeline_id
        ):
            setter(timeline)
            if hasattr(conn, "refresh"):
                conn.refresh()
            return True
    return False


def _reopen_project(
    project_name: str, timeline_name: str | None, timeline_id: str | None
) -> Any:
    ResolveConnection.reset()
    fresh_conn = ResolveConnection.get()
    fresh_conn.connect()
    loaded = fresh_conn.project_manager.LoadProject(project_name)
    if not loaded:
        raise APICallFailed(
            "DaVinci Resolve could not reopen the project after restoring a version checkpoint.",
            details={"project_name": project_name},
            recoverability="manual",
        )
    try:
        fresh_conn.wait_for_state(
            lambda state: state["project"] == project_name,
            description=f"project '{project_name}' to reopen after checkpoint restore",
        )
    except Exception:
        fresh_conn.refresh()
    if (timeline_name or timeline_id) and not _activate_timeline_by_identity(
        fresh_conn, timeline_name, timeline_id
    ):
        raise APICallFailed(
            "DaVinci Resolve restored the project DB but could not activate the checkpoint timeline.",
            details={
                "project_name": project_name,
                "timeline_name": timeline_name,
                "timeline_id": timeline_id,
            },
            recoverability="manual",
        )
    return fresh_conn


def restore_checkpoint(
    conn,
    checkpoint_id: str,
    *,
    session_id: str | None = None,
    expected_current_state_hash: str | None = None,
    expected_checkpoint_digest: str | None = None,
) -> dict[str, Any]:
    checkpoint = inspect_checkpoint(checkpoint_id)
    if expected_checkpoint_digest is not None and (
        checkpoint_binding_digest(checkpoint) != expected_checkpoint_digest
    ):
        raise ValidationError(
            "Checkpoint changed after prepared-action authorization.",
            details={"reason": "checkpoint_binding_mismatch"},
            recoverability="not_applicable",
        )
    _validate_restore_session(
        checkpoint, checkpoint_id=checkpoint_id, expected_session_id=session_id
    )
    _validate_restore_strategy(checkpoint, checkpoint_id=checkpoint_id)

    restored_db = _decompress_snapshot(checkpoint, checkpoint_id=checkpoint_id)
    expected_hash = str(checkpoint.get("db_hash") or checkpoint.get("state_hash") or "")
    restored_hash = _hash_file(restored_db)
    if expected_hash and restored_hash != expected_hash:
        restored_db.unlink(missing_ok=True)
        raise ValidationError(
            "Project DB snapshot hash does not match checkpoint metadata.",
            details={
                "reason": "snapshot_hash_mismatch",
                "checkpoint_id": checkpoint_id,
                "expected_hash": expected_hash,
                "actual_hash": restored_hash,
            },
            recoverability="manual",
        )

    checkpoint_project_name = _normalize_identity_value(checkpoint.get("project_name"))
    active_project_name = _active_project_name(conn)
    steps: list[str] = []
    active_project_db: dict[str, Any] | None = None
    target_project_is_active = bool(
        active_project_name and active_project_name == checkpoint_project_name
    )

    if target_project_is_active:
        try:
            active_project_db = _resolve_project_db(conn)
        except (ValidationError, APICallFailed) as exc:
            if not _can_fallback_to_checkpoint_target_after_identity_error(exc):
                raise
            target_db_path = _validate_closed_project_db_target(
                checkpoint, checkpoint_id=checkpoint_id
            )
            steps.append("active_project_db_identity_unavailable")
            steps.append(f"active_project_db_identity_error:{exc.__class__.__name__}")
        else:
            _validate_restore_target_identity(
                checkpoint,
                checkpoint_id=checkpoint_id,
                active_identity={"project_name": active_project_name},
                active_project_db=active_project_db,
            )
            target_db_path = Path(str(active_project_db["project_db_path"]))
    else:
        target_db_path = _validate_closed_project_db_target(
            checkpoint, checkpoint_id=checkpoint_id
        )
        steps.append(
            "target_project_not_active" if active_project_name else "no_active_project"
        )

    backup_path = target_db_path.with_name(
        f"{target_db_path.name}.restore-backup-{uuid4().hex}"
    )
    backup_created = False
    restore_temp: Path | None = None
    try:
        if expected_current_state_hash:
            current_hash = _stable_project_db_hash(str(target_db_path))
            if current_hash != expected_current_state_hash:
                raise ValidationError(
                    "Project state changed before checkpoint restore could begin.",
                    details={
                        "reason": "workflow_restore_precondition_mismatch",
                        "expected_current_state_hash": expected_current_state_hash,
                        "actual_current_state_hash": current_hash,
                    },
                    recoverability="manual",
                )
            steps.append("validate_current_project_state")
        if target_project_is_active:
            close_current_project_with_runtime_health(
                conn,
                project_name=str(checkpoint["project_name"]),
                current_database=active_project_db,
                project_db_path=str(target_db_path),
                description=f"project '{checkpoint['project_name']}' to close before version restore",
            )
            steps.append("close_project")
        if target_db_path.exists():
            shutil.copy2(target_db_path, backup_path)
            backup_created = True
            steps.append("backup_current_project_db")
        else:
            steps.append("target_project_db_missing")
        restore_temp = target_db_path.with_name(
            f"{target_db_path.name}.restore-{uuid4().hex}"
        )
        shutil.copy2(restored_db, restore_temp)
        restore_temp.replace(target_db_path)
        steps.append("restore_project_db_snapshot")
    except Exception as exc:
        try:
            if backup_created and backup_path.exists():
                shutil.copy2(backup_path, target_db_path)
                steps.append("rollback_current_project_db")
        except Exception:
            pass
        try:
            if restore_temp is not None and restore_temp.exists():
                restore_temp.unlink(missing_ok=True)
        except Exception:
            pass
        raise APICallFailed(
            "Failed to restore project checkpoint.",
            details={
                "checkpoint_id": checkpoint_id,
                "project_name": checkpoint.get("project_name"),
                "project_db_path": str(target_db_path),
                "snapshot_path": checkpoint.get("snapshot_path"),
                "steps": steps,
                "error": str(exc),
            },
            recoverability="manual",
        ) from exc
    finally:
        restored_db.unlink(missing_ok=True)

    reopened = False
    reopen_error: dict[str, Any] | None = None
    try:
        _reopen_project(
            str(checkpoint["project_name"]),
            str(checkpoint.get("timeline_name") or ""),
            str(checkpoint.get("timeline_id") or ""),
        )
        reopened = True
        steps.append("reopen_project")
    except Exception as exc:
        reopen_error = {
            "type": exc.__class__.__name__,
            "message": str(exc),
            "details": dict(getattr(exc, "details", {}) or {}),
        }
        steps.append("reopen_project_failed")

    verification_status = "verified" if reopened else "partial"
    set_verification_status(verification_status)
    set_recoverability("manual")
    return {
        "checkpoint": checkpoint,
        "restore_strategy": RESTORE_STRATEGY,
        "restored_project_name": checkpoint.get("project_name"),
        "restored_timeline_name": checkpoint.get("timeline_name"),
        "active_project_name": checkpoint.get("project_name") if reopened else None,
        "active_timeline_name": checkpoint.get("timeline_name") if reopened else None,
        "project_db_path": str(target_db_path),
        "backup_path": str(backup_path) if backup_created else None,
        "restored_on_disk": True,
        "reopened": reopened,
        "reopen_error": reopen_error,
        "steps": steps,
        "changed": True,
        "verified": reopened,
        "verification_status": verification_status,
    }


def version_status(
    conn,
    *,
    session_id: str | None = None,
    include_private_identity: bool = False,
) -> dict[str, Any]:
    conn.require_timeline()
    identity = _timeline_identity(conn)
    project_db = _resolve_project_db(conn)
    live_hash = _stable_project_db_hash(str(project_db["project_db_path"]))
    candidates = list_checkpoints(
        project_name=str(identity["project_name"]),
        session_id=session_id,
    )
    latest = candidates[0] if candidates else None
    return {
        **({"project_id": identity["project_id"]} if include_private_identity else {}),
        "project_name": identity["project_name"],
        "timeline_name": identity["timeline_name"],
        "timeline_id": identity["timeline_id"],
        "database_type": project_db.get("DbType"),
        "database_name": project_db.get("DbName"),
        "project_db_path": str(project_db["project_db_path"]),
        "state_hash": live_hash,
        "latest_checkpoint": latest,
        "has_changes": bool(latest and latest.get("state_hash") != live_hash),
        "checkpoint_count": len(candidates),
        "restore_strategy": RESTORE_STRATEGY,
    }
