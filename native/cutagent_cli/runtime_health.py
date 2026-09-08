"""Shared DaVinci Resolve runtime health helpers for DB-backed workflows."""

from __future__ import annotations

from pathlib import Path
import sqlite3
import time
from typing import Any, Callable

from .connection import ResolveConnection
from .errors import APICallFailed, ValidationError
from .state_contracts import project_is_closed_enough


def _is_embedded_current_database_unavailable(error: APICallFailed) -> bool:
    details = getattr(error, "details", {}) or {}
    message = str(error)
    method = details.get("method")
    mentions_current_database = method == "GetCurrentDatabase" or "GetCurrentDatabase" in message
    if not mentions_current_database:
        return False

    has_embedded_signal = (
        bool(details.get("embedded_error_code"))
        or details.get("source") == "CutAgent.lua"
        or "Unsupported embedded DaVinci Resolve method" in message
    )
    if not has_embedded_signal:
        return False

    return "Unsupported embedded DaVinci Resolve method" in message or "method not available" in message


def infer_disk_current_database(conn) -> dict[str, Any] | None:
    """Infer a Disk database from the current project when DaVinci Resolve omits DB details."""
    project = getattr(conn, "project", None)
    project_name = project.GetName() if project and hasattr(project, "GetName") else None
    if not project_name:
        return None

    from .core import native_multicam_db

    try:
        db_resolution = native_multicam_db.resolve_disk_project_db_path(project_name=project_name)
    except Exception:
        return None

    return {
        "DbType": "Disk",
        "DbName": None,
        "inferred_from_project_db": True,
        "project_name": project_name,
        "project_db_path": db_resolution.get("project_db_path"),
    }


def try_current_database_details(
    conn,
    *,
    allow_project_name_inference: bool = True,
) -> dict[str, Any] | None:
    getter = getattr(conn.project_manager, "GetCurrentDatabase", None)
    try:
        details = getter() if callable(getter) else None
    except APICallFailed as exc:
        if allow_project_name_inference and _is_embedded_current_database_unavailable(exc):
            inferred = infer_disk_current_database(conn)
            if inferred is not None:
                return inferred
        raise
    if isinstance(details, dict) and str(details.get("DbType") or "").strip():
        return details
    if not allow_project_name_inference:
        return None
    return infer_disk_current_database(conn)


def get_current_database_details(
    conn,
    *,
    allow_project_name_inference: bool = True,
) -> dict[str, Any]:
    """Return current DB details or raise a deterministic runtime-health error."""
    details = try_current_database_details(
        conn,
        allow_project_name_inference=allow_project_name_inference,
    )
    if details is not None:
        return details

    project = getattr(conn, "project", None)
    project_name = project.GetName() if project and hasattr(project, "GetName") else None
    raise APICallFailed(
        "DaVinci Resolve runtime returned invalid current database details.",
        details={
            "reason": "runtime_current_database_invalid",
            "project_name": project_name,
        },
    )


def _current_project_name(conn) -> str | None:
    project = getattr(conn, "project", None)
    if project and hasattr(project, "GetName"):
        return project.GetName()
    return None


def _validate_disk_project_db_path(
    project_db_path: str | Path,
    *,
    project_name: str | None,
    db_path_source: str,
    current_database: dict[str, Any],
) -> str:
    normalized_path = str(project_db_path or "").strip()
    path = Path(normalized_path).expanduser()
    if not normalized_path or not path.exists() or not path.is_file():
        raise APICallFailed(
            "Resolved Project.db path is missing or invalid.",
            details={
                "reason": "project_db_validation_failed",
                "project_name": project_name,
                "project_db_path": normalized_path,
                "db_path_source": db_path_source,
                "current_database": current_database,
                "path_exists": path.exists() if normalized_path else False,
                "is_file": path.is_file() if normalized_path else False,
            },
        )

    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=1.0)
        connection.execute("PRAGMA schema_version").fetchone()
    except sqlite3.Error as exc:
        raise APICallFailed(
            "Resolved Project.db path failed SQLite validation.",
            details={
                "reason": "project_db_validation_failed",
                "project_name": project_name,
                "project_db_path": str(path),
                "db_path_source": db_path_source,
                "current_database": current_database,
                "sqlite_error_type": exc.__class__.__name__,
                "sqlite_error": str(exc),
            },
        ) from exc
    finally:
        if connection is not None:
            connection.close()

    return str(path)


def resolve_current_disk_project_db(
    conn,
    *,
    validate: bool = True,
    allow_project_name_inference: bool = True,
) -> dict[str, Any]:
    """Resolve and validate the current Disk project DB path from the live runtime."""
    current_database = get_current_database_details(
        conn,
        allow_project_name_inference=allow_project_name_inference,
    )
    if str(current_database.get("DbType") or "").strip() != "Disk":
        raise ValidationError(
            "Current project is not backed by a Disk project database.",
            details={"current_database": current_database},
        )

    project_name = str(
        current_database.get("project_name")
        or _current_project_name(conn)
        or ""
    ).strip() or None
    resolved = dict(current_database)
    if project_name:
        resolved["project_name"] = project_name

    current_db_path = str(current_database.get("project_db_path") or "").strip()
    if current_db_path:
        resolved_path = (
            _validate_disk_project_db_path(
                current_db_path,
                project_name=project_name,
                db_path_source="current_database",
                current_database=current_database,
            )
            if validate
            else str(Path(current_db_path).expanduser())
        )
        resolved["project_db_path"] = resolved_path
        resolved["db_path_source"] = "current_database"
        resolved["validated"] = bool(validate)
        return resolved

    if not project_name:
        raise APICallFailed(
            "DaVinci Resolve runtime did not provide enough information to locate Project.db.",
            details={
                "reason": "project_db_validation_failed",
                "current_database": current_database,
            },
        )

    if not allow_project_name_inference:
        raise APICallFailed(
            "DaVinci Resolve runtime did not provide an unambiguous active Disk Project.db identity.",
            details={
                "reason": "project_db_identity_unavailable",
                "project_name": project_name,
                "current_database": current_database,
                "required": [
                    "DbType must be Disk",
                    "current database details must include project_db_path for DB-backed mutations",
                ],
                "rejected_fallback": "project_name_inference",
            },
        )

    from .core import native_multicam_db

    db_resolution = native_multicam_db.resolve_disk_project_db_path(project_name=project_name)
    inferred_path = str(db_resolution.get("project_db_path") or "")
    resolved_path = (
        _validate_disk_project_db_path(
            inferred_path,
            project_name=project_name,
            db_path_source="project_name_inference",
            current_database=current_database,
        )
        if validate
        else str(Path(inferred_path).expanduser())
    )
    resolved["project_db_path"] = resolved_path
    resolved["db_path_source"] = "project_name_inference"
    resolved["inferred_from_project_db"] = True
    resolved["validated"] = bool(validate)
    candidates = list(db_resolution.get("candidates") or [])
    if candidates:
        resolved["project_db_candidates"] = candidates
    return resolved


def _read_fresh_runtime_state() -> dict[str, Any]:
    ResolveConnection.reset()
    fresh_conn = ResolveConnection.get()
    fresh_conn.connect()
    return fresh_conn.current_state()


def wait_for_fresh_runtime_state(
    predicate: Callable[[dict[str, Any]], bool],
    *,
    description: str,
    attempts: int = 20,
    delay: float = 0.25,
    read_state: Callable[[], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Poll DaVinci Resolve with fresh connection snapshots until a predicate matches."""
    state_reader = read_state or _read_fresh_runtime_state
    last_state: dict[str, Any] | None = None

    for attempt in range(1, attempts + 1):
        state = state_reader()
        last_state = state
        if predicate(state):
            return state
        if attempt < attempts:
            time.sleep(delay)

    raise APICallFailed(
        f"DaVinci Resolve state did not converge to {description}.",
        details={
            "description": description,
            "last_state": last_state or {},
            "attempts": attempts,
        },
    )


def _candidate_switch_projects(conn, *, original_project_name: str) -> list[str]:
    list_projects = getattr(conn.project_manager, "GetProjectListInCurrentFolder", None)
    if not callable(list_projects):
        return []

    try:
        projects = list_projects() or []
    except Exception:
        return []

    candidates: list[str] = []
    for name in projects:
        if not isinstance(name, str):
            continue
        normalized = name.strip()
        if not normalized or normalized == original_project_name:
            continue
        candidates.append(normalized)
    return candidates


def _switch_away_from_project(
    conn,
    *,
    original_project_name: str,
    description: str,
    attempts: int,
    delay: float,
    read_state: Callable[[], dict[str, Any]],
) -> dict[str, Any] | None:
    load_project = getattr(conn.project_manager, "LoadProject", None)
    if not callable(load_project):
        return None

    for candidate_name in _candidate_switch_projects(conn, original_project_name=original_project_name):
        try:
            loaded = load_project(candidate_name)
        except Exception:
            continue
        if not loaded:
            continue

        try:
            switched_state = wait_for_fresh_runtime_state(
                lambda state: project_is_closed_enough(state, original_project_name=original_project_name),
                description=description,
                attempts=attempts,
                delay=delay,
                read_state=read_state,
            )
        except APICallFailed:
            continue

        try:
            conn.refresh()
        except Exception:
            pass
        return switched_state

    return None


def close_current_project_with_runtime_health(
    conn,
    *,
    project_name: str,
    current_database: dict[str, Any] | None = None,
    project_db_path: str | None = None,
    description: str | None = None,
    close_attempts: int = 3,
    attempts: int = 20,
    delay: float = 0.25,
    read_state: Callable[[], dict[str, Any]] | None = None,
    close_project: Callable[[Any], Any] | None = None,
) -> dict[str, Any]:
    """Close the current project and verify with fresh runtime state polling."""
    timeline = getattr(conn, "timeline", None)
    timeline_name = timeline.GetName() if timeline and hasattr(timeline, "GetName") else None
    state_reader = read_state or _read_fresh_runtime_state
    close_result = False
    close_attempt = 0

    for close_attempt in range(1, max(int(close_attempts), 1) + 1):
        active_project = getattr(conn, "project", None)
        if active_project is None:
            break

        close_fn = close_project if close_attempt == 1 and close_project is not None else getattr(conn.project_manager, "CloseProject", None)
        if not callable(close_fn):
            raise APICallFailed(
                "DaVinci Resolve cannot close the current project because the runtime method is unavailable.",
                details={
                    "method": "ProjectManager.CloseProject",
                    "reason": "runtime_project_close_method_unavailable",
                    "project_name": project_name,
                },
            )
        try:
            close_result = close_fn(active_project)
        except APICallFailed:
            raise
        except Exception as exc:
            raise APICallFailed(
                "DaVinci Resolve failed while closing the current project.",
                details={
                    "method": "ProjectManager.CloseProject",
                    "reason": "runtime_project_close_exception",
                    "project_name": project_name,
                    "error_type": exc.__class__.__name__,
                },
            ) from exc
        if close_result is not False:
            break

        try:
            close_state = state_reader()
        except Exception:
            close_state = None
        if close_state and project_is_closed_enough(close_state, original_project_name=project_name):
            try:
                conn.refresh()
            except Exception:
                pass
            return close_state

        if close_attempt < max(int(close_attempts), 1):
            time.sleep(delay)
            try:
                conn.refresh()
            except Exception:
                pass

    if close_result is False:
        switched_state = _switch_away_from_project(
            conn,
            original_project_name=project_name,
            description=description or f"project '{project_name}' to stop being current",
            attempts=attempts,
            delay=delay,
            read_state=state_reader,
        )
        if switched_state is not None:
            return switched_state

        raise APICallFailed(
            "Failed to close the project before continuing.",
            details={
                "reason": "runtime_project_close_failed",
                "project_name": project_name,
                "timeline_name": timeline_name,
                "current_database": current_database,
                "project_db_path": project_db_path,
                "close_attempts": close_attempt,
            },
            recoverability="manual",
        )

    try:
        close_state = wait_for_fresh_runtime_state(
            lambda state: project_is_closed_enough(state, original_project_name=project_name),
            description=description or f"project '{project_name}' to stop being current",
            attempts=attempts,
            delay=delay,
            read_state=state_reader,
        )
    except APICallFailed as exc:
        switched_state = _switch_away_from_project(
            conn,
            original_project_name=project_name,
            description=description or f"project '{project_name}' to stop being current",
            attempts=attempts,
            delay=delay,
            read_state=state_reader,
        )
        if switched_state is not None:
            return switched_state

        details = dict(exc.details)
        details.update(
            {
                "reason": "runtime_project_close_stuck",
                "project_name": project_name,
                "timeline_name": timeline_name,
                "current_database": current_database,
                "project_db_path": project_db_path,
            }
        )
        raise APICallFailed(
            "DaVinci Resolve runtime could not close the current project cleanly.",
            details=details,
            recoverability="manual",
        ) from exc

    try:
        conn.refresh()
    except Exception:
        pass
    return close_state
