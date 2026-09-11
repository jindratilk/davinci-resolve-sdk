"""Shared Disk-DB mutation session helpers."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass, field, is_dataclass
import errno
import os
from pathlib import Path
import shutil
import sqlite3
import time
from typing import Any, Callable

from .sdk_live_inspection import SDK_COLOR_GUARD_ENV, documented_unique_id

try:
    import fcntl
except ImportError:  # pragma: no cover - non-POSIX fallback
    fcntl = None

try:
    import msvcrt
except ImportError:  # pragma: no cover - non-Windows fallback
    msvcrt = None

from ..connection import ResolveConnection
from ..errors import APICallFailed, CLIError, DiskDbLocked, EditMutationRecoveryFailed, ValidationError
from ..output import set_execution_engine, set_verification_status
from ..runtime_health import close_current_project_with_runtime_health, resolve_current_disk_project_db


@dataclass
class DiskDbMutationSession:
    project_name: str
    project_db_path: str
    backup_path: str
    current_database: dict[str, Any]
    lock_path: str | None = None
    steps: list[str] = field(default_factory=list)


_DB_MUTATION_LOCK_SUFFIX = ".cutagent.lock"
_DB_MUTATION_LOCK_TIMEOUT_SECONDS = 60.0
_DB_MUTATION_LOCK_POLL_SECONDS = 0.2


def _require_sdk_color_target_pre_close(conn, session: DiskDbMutationSession) -> None:
    """Revalidate an SDK Color target at the last safe point before close."""

    if SDK_COLOR_GUARD_ENV not in os.environ:
        return
    # Import locally so the general DB session remains independent of the
    # timeline compatibility facade unless an SDK Color mutation is active.
    from . import timeline_ops

    timeline_ops.require_sdk_color_mutation_guard(conn)
    session.steps.append("validate_sdk_color_target_pre_close")


def _is_color_db_mutation_context(context: str) -> bool:
    return str(context or "").strip().casefold().startswith("color ")


def _color_version_payload_for_item(item: Any) -> dict[str, Any] | None:
    payload: dict[str, Any] = {}
    try:
        name_getter = getattr(item, "GetName", None)
        if callable(name_getter):
            payload["clip"] = name_getter()
    except Exception:
        pass

    current_getter = getattr(item, "GetCurrentVersion", None)
    current: Any = None
    if callable(current_getter):
        try:
            current = current_getter()
        except Exception:
            current = None
    if isinstance(current, dict):
        if not current:
            return None
        payload.update(current)
        return payload
    if current is not None:
        payload["current_version"] = current
        return payload
    return None


def _current_color_version_payload(conn: Any) -> dict[str, Any] | None:
    timeline = getattr(conn, "timeline", None)
    getter = getattr(timeline, "GetCurrentVideoItem", None)
    if not callable(getter):
        return None
    try:
        item = getter()
    except Exception:
        return None
    if item is None:
        return None
    return _color_version_payload_for_item(item)


def _target_ref_payload(target_ref: Any) -> dict[str, Any]:
    if target_ref is None:
        return {}
    if isinstance(target_ref, dict):
        return dict(target_ref)
    if is_dataclass(target_ref):
        try:
            return asdict(target_ref)
        except Exception:
            pass
    payload: dict[str, Any] = {}
    for name in ("track_type", "track_index", "name", "start", "duration", "end", "aliases"):
        if hasattr(target_ref, name):
            try:
                value = getattr(target_ref, name)
            except Exception:
                continue
            if value is not None:
                payload[name] = value
    return payload


def _iter_color_target_refs(color_target_ref: Any) -> list[Any]:
    if color_target_ref is None:
        return []
    if isinstance(color_target_ref, (list, tuple, set)):
        return [ref for ref in color_target_ref if ref is not None]
    return [color_target_ref]


def _looks_like_color_target_ref(value: Any) -> bool:
    payload = _target_ref_payload(value)
    return bool(payload.get("name") and payload.get("start") is not None and payload.get("duration") is not None)


def _writer_color_target_ref(writer: Any) -> Any:
    closure = getattr(writer, "__closure__", None) or ()
    refs: list[Any] = []
    for cell in closure:
        try:
            value = cell.cell_contents
        except ValueError:
            continue
        if _looks_like_color_target_ref(value):
            refs.append(value)
            continue
        if isinstance(value, (list, tuple, set)):
            refs.extend(ref for ref in value if _looks_like_color_target_ref(ref))
    if not refs:
        return None
    return refs[0] if len(refs) == 1 else refs


def _item_matches_target_ref(item: Any, target_ref: Any) -> bool:
    target = _target_ref_payload(target_ref)
    if not target:
        return False
    try:
        item_name = str(item.GetName() or "")
        item_start = int(item.GetStart())
        item_end = int(item.GetEnd())
    except Exception:
        return False
    target_name = str(target.get("name") or "")
    if target_name and item_name != target_name:
        return False
    try:
        target_start = int(target.get("start"))
    except (TypeError, ValueError):
        return False
    if item_start != target_start:
        return False
    if target.get("duration") is not None:
        try:
            return (item_end - item_start) == int(target.get("duration"))
        except (TypeError, ValueError):
            return False
    if target.get("end") is not None:
        try:
            return item_end == int(target.get("end"))
        except (TypeError, ValueError):
            return False
    return True


def _target_color_version_payload(conn: Any, target_ref: Any) -> dict[str, Any] | None:
    timeline = getattr(conn, "timeline", None)
    if timeline is None or target_ref is None:
        return None
    target = _target_ref_payload(target_ref)
    track_type = str(target.get("track_type") or "video")
    try:
        track_index = int(target.get("track_index") or 1)
    except (TypeError, ValueError):
        track_index = 1
    getter = getattr(timeline, "GetItemListInTrack", None)
    if not callable(getter):
        return None
    try:
        items = getter(track_type, track_index) or []
    except Exception:
        return None
    matches = [item for item in items if _item_matches_target_ref(item, target_ref)]
    if len(matches) != 1:
        return None
    payload = _color_version_payload_for_item(matches[0])
    if payload is not None:
        payload["target_ref"] = target
    return payload


def _target_color_version_payload_from_project_db(
    project_db_path: str,
    *,
    timeline_name: str,
    target_ref: Any,
) -> dict[str, Any] | None:
    """Read the exact target's active Color version when the embedded API cannot."""
    from .db_timeline_rows import find_ti_item_row
    from .db_timeline_selection import LiveItemRef

    target = _target_ref_payload(target_ref)
    try:
        item_ref = target_ref if isinstance(target_ref, LiveItemRef) else LiveItemRef(
            track_type=str(target.get("track_type") or "video"),
            track_index=int(target.get("track_index") or 1),
            name=str(target["name"]),
            start=int(target["start"]),
            duration=int(target["duration"]),
            aliases=tuple(str(value) for value in target.get("aliases") or ()),
        )
    except (KeyError, TypeError, ValueError):
        return None

    connection: sqlite3.Connection | None = None
    try:
        database_uri = Path(project_db_path).resolve().as_uri() + "?mode=ro"
        connection = sqlite3.connect(database_uri, uri=True)
        connection.row_factory = sqlite3.Row
        cursor = connection.cursor()
        row = find_ti_item_row(
            cursor,
            item=item_ref,
            db_type="Sm2TiVideoClip",
            timeline_name=timeline_name,
            require_timeline_name=True,
        )
        version_table_id = row.get("pLmVerTable")
        if not version_table_id:
            return {
                "clip": item_ref.name,
                "versionName": None,
                "versionType": 0,
                "ungraded": True,
                "readback_source": "project_db_exact_ungraded_target",
                "target_ref": target,
            }
        version = cursor.execute(
            '''
            SELECT
              vt.VerType AS table_version_type,
              vt.pActive AS active_version_id,
              v.Name AS version_name,
              v.VerType AS version_type
            FROM "ListMgt::LmVersionTable" vt
            LEFT JOIN "ListMgt::LmVersion" v
              ON v."ListMgt::LmVersion_id" = vt.pActive
            WHERE vt."ListMgt::LmVersionTable_id" = ?
            LIMIT 1
            ''',
            (str(version_table_id),),
        ).fetchone()
        if version is None or not version["active_version_id"] or version["version_name"] is None:
            return None
        return {
            "clip": item_ref.name,
            "versionName": str(version["version_name"]),
            "versionType": int(version["version_type"] or version["table_version_type"] or 0),
            "version_id": str(version["active_version_id"]),
            "version_table_id": str(version_table_id),
            "readback_source": "project_db_exact_active_version",
            "target_ref": target,
        }
    except (OSError, sqlite3.Error, ValidationError):
        return None
    finally:
        if connection is not None:
            connection.close()


def _version_type_value(payload: dict[str, Any]) -> int | None:
    for key in ("versionType", "VersionType", "version_type", "type"):
        if key not in payload:
            continue
        value = payload.get(key)
        try:
            return int(value)
        except (TypeError, ValueError):
            text = str(value or "").strip().casefold()
            if text == "remote":
                return 1
            if text == "local":
                return 0
    return None


def _audit_color_db_mutation_version_scope(
    conn: Any,
    *,
    context: str,
    color_target_ref: Any = None,
    project_db_path: str | None = None,
    active_timeline_name: str | None = None,
) -> dict[str, Any] | None:
    if not _is_color_db_mutation_context(context):
        return None
    target_refs = _iter_color_target_refs(color_target_ref)
    if not target_refs:
        current_version = _current_color_version_payload(conn)
        if not current_version:
            raise ValidationError(
                "DB-backed Color Page edits require active Color version readback before mutation.",
                details={
                    "reason": "db_color_active_version_unverified",
                    "context": context,
                    "required_proof": (
                        "Verify the active Color version on the current timeline item before any Project.db write."
                    ),
                },
                recoverability="manual",
            )
        version_type = _version_type_value(current_version or {})
        return {
            "scope": "current_clip",
            "context": context,
            "active_remote": version_type == 1,
            "active_local": version_type == 0,
            "checked_versions": [current_version] if current_version else [],
            "targeting": "active_lm_version_table_pActive",
            "required_proof": (
                "DB-backed Color Page writes in Remote Grade scope must pass the normal "
                "Disk DB save/close/write/reopen verifier and, for visible grading changes, "
                "render proof on representative same-source instances."
            ),
        }

    checked_versions: list[dict[str, Any]] = []
    for target_ref in target_refs:
        target_payload = _target_ref_payload(target_ref)
        current_version = _target_color_version_payload(conn, target_ref)
        if not current_version and project_db_path and active_timeline_name:
            current_version = _target_color_version_payload_from_project_db(
                project_db_path,
                timeline_name=active_timeline_name,
                target_ref=target_ref,
            )
        if not current_version:
            raise ValidationError(
                "DB-backed Color Page edits require target Color version readback before mutation.",
                details={
                    "reason": "db_color_target_version_unverified",
                    "context": context,
                    "target_ref": target_payload,
                    "required_proof": "Resolve the target timeline item and verify its active Color version before any Project.db write.",
                },
                recoverability="manual",
            )
        if target_payload:
            current_version.setdefault("target_ref", target_payload)
        checked_versions.append(current_version)
    has_remote = any(_version_type_value(version) == 1 for version in checked_versions)
    has_local = any(_version_type_value(version) == 0 for version in checked_versions)
    return {
        "scope": "target_refs",
        "context": context,
        "active_remote": has_remote,
        "active_local": has_local,
        "checked_versions": checked_versions,
        "targeting": "active_lm_version_table_pActive",
        "required_proof": (
            "Targeted DB-backed Color Page writes in Remote Grade scope require target "
            "version readback before SQLite, the normal Disk DB save/close/write/reopen "
            "verifier, and render proof for visible grading changes."
        ),
    }


def _rollback_hint(session: DiskDbMutationSession) -> str:
    return (
        f"Restore the Disk project database backup by closing project '{session.project_name}', "
        f"copying '{session.backup_path}' over '{session.project_db_path}', and reopening the project."
    )


def _recovery_payload(
    session: DiskDbMutationSession,
    *,
    failure_step: str,
    rollback_performed: bool | None = None,
    rollback_error: str | None = None,
    rollback_steps: list[str] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "backup_path": session.backup_path,
        "rollback_hint": _rollback_hint(session),
        "failure_step": failure_step,
    }
    if rollback_performed is not None:
        payload["rollback_performed"] = rollback_performed
    if rollback_error:
        payload["rollback_error"] = rollback_error
    if rollback_steps is not None:
        payload["rollback_steps"] = rollback_steps
    return payload


def _restore_project_db_from_backup(
    conn: Any | None,
    session: DiskDbMutationSession,
    *,
    active_timeline_name: str | None = None,
) -> dict[str, Any]:
    rollback_steps: list[str] = []
    try:
        if conn is not None and getattr(conn, "project", None) is not None:
            try:
                close_current_project_with_runtime_health(
                    conn,
                    project_name=session.project_name,
                    current_database=session.current_database,
                    project_db_path=session.project_db_path,
                    description=f"project '{session.project_name}' to close before DB backup rollback",
                )
                rollback_steps.append("close_project_for_rollback")
            except Exception as exc:
                rollback_steps.append("close_project_for_rollback_failed")
                rollback_steps.append(f"close_project_for_rollback_error:{exc.__class__.__name__}")
                return {
                    "rollback_performed": False,
                    "rollback_error": (
                        f"Refusing to restore '{session.project_db_path}' from backup because "
                        f"project close failed before rollback: {exc}"
                    ),
                    "rollback_steps": rollback_steps,
                }
        shutil.copy2(session.backup_path, session.project_db_path)
        rollback_steps.append("restore_project_db_from_backup")

        restore_conn = _fresh_connected_resolve_connection()
        project_manager = getattr(restore_conn, "project_manager", None)
        loaded = _load_project_with_retry(project_manager, session.project_name)
        if loaded:
            rollback_steps.append("reopen_project_after_rollback")
            try:
                restore_conn.wait_for_state(
                    lambda state: state["project"] == session.project_name,
                    description=f"project '{session.project_name}' to reopen after DB backup rollback",
                )
            except Exception:
                restore_conn.refresh()
            if active_timeline_name:
                if _activate_timeline_by_name(restore_conn, active_timeline_name):
                    rollback_steps.append("restore_timeline_after_rollback")
                else:
                    rollback_steps.append("restore_timeline_after_rollback_failed")
                    return {
                        "rollback_performed": False,
                        "rollback_error": (
                            f"Project database was restored, but timeline '{active_timeline_name}' "
                            "could not be restored after rollback."
                        ),
                        "rollback_steps": rollback_steps,
                    }
        else:
            rollback_steps.append("reopen_project_after_rollback_failed")
            return {
                "rollback_performed": False,
                "rollback_error": (
                    f"Project database was restored, but project '{session.project_name}' "
                    "could not be reopened after rollback."
                ),
                "rollback_steps": rollback_steps,
            }
    except Exception as exc:
        return {
            "rollback_performed": False,
            "rollback_error": str(exc),
            "rollback_steps": rollback_steps,
        }
    return {
        "rollback_performed": True,
        "rollback_error": None,
        "rollback_steps": rollback_steps,
    }


def restore_project_db_backup_from_mutation_result(
    conn: Any,
    result: dict[str, Any],
    *,
    active_timeline_name: str | None = None,
) -> dict[str, Any]:
    """Restore a DB workaround backup after a later proof step rejects the mutation."""
    project_db_path = str((result or {}).get("project_db_path") or "")
    backup_path = str((result or {}).get("backup_path") or "")
    if not project_db_path or not backup_path:
        return {
            "rollback_performed": False,
            "rollback_error": "Mutation result did not include project_db_path and backup_path.",
            "rollback_steps": [],
        }
    current_database = resolve_current_disk_project_db(conn, allow_project_name_inference=True)
    project_name = str(current_database.get("project_name") or Path(project_db_path).parent.name)
    session = DiskDbMutationSession(
        project_name=project_name,
        project_db_path=project_db_path,
        backup_path=backup_path,
        current_database=current_database,
        lock_path=str((result or {}).get("lock_path") or "") or None,
        steps=list((result or {}).get("steps") or []),
    )
    if active_timeline_name is None:
        timeline = getattr(conn, "timeline", None)
        if timeline is not None and hasattr(timeline, "GetName"):
            try:
                active_timeline_name = timeline.GetName()
            except Exception:
                active_timeline_name = None
    return _restore_project_db_from_backup(
        conn,
        session,
        active_timeline_name=active_timeline_name,
    )


def _raise_post_commit_failure(
    *,
    context: str,
    session: DiskDbMutationSession,
    failure_step: str,
    error: Exception,
    fresh_conn: Any | None = None,
    active_timeline_name: str | None = None,
) -> None:
    set_verification_status("failed")
    rollback_result = _restore_project_db_from_backup(
        fresh_conn,
        session,
        active_timeline_name=active_timeline_name,
    )
    recovery = _recovery_payload(
        session,
        failure_step=failure_step,
        rollback_performed=bool(rollback_result.get("rollback_performed")),
        rollback_error=rollback_result.get("rollback_error"),
        rollback_steps=list(rollback_result.get("rollback_steps") or []),
    )
    original_error = {
        "type": error.__class__.__name__,
        "message": str(error),
    }
    details = getattr(error, "details", None)
    if isinstance(details, dict):
        original_error["details"] = details
    rollback_performed = bool(rollback_result.get("rollback_performed"))
    error_type = APICallFailed if rollback_performed else EditMutationRecoveryFailed
    raise error_type(
        (
            "Disk DB mutation committed, but the post-commit step failed; the project database backup was restored."
            if rollback_performed
            else "Disk DB mutation committed, and post-commit recovery could not restore the project database backup."
        ),
        details={
            "reason": "db_mutation_post_commit_failure",
            "context": context,
            "project_name": session.project_name,
            "project_db_path": session.project_db_path,
            "backup_path": session.backup_path,
            "failure_step": failure_step,
            "steps": list(session.steps),
            "recovery": recovery,
            "possible_mutation": not rollback_performed,
            "possible_mutation_state": "rolled_back" if rollback_performed else "unknown_requires_manual_recovery",
            "original_error": original_error,
        },
        recoverability="retry_possible" if rollback_performed else "manual",
    ) from error


def _raise_required_verification_failure(
    *,
    context: str,
    session: DiskDbMutationSession,
    mutation_result: Any,
    verification: dict[str, Any],
    fresh_conn: Any,
    active_timeline_name: str | None,
) -> None:
    """Restore the pre-edit backup when a mandatory verifier returns failure."""

    set_verification_status("failed")
    rollback_result = _restore_project_db_from_backup(
        fresh_conn,
        session,
        active_timeline_name=active_timeline_name,
    )
    rollback_performed = bool(rollback_result.get("rollback_performed"))
    recovery = _recovery_payload(
        session,
        failure_step="verification_failed",
        rollback_performed=rollback_performed,
        rollback_error=rollback_result.get("rollback_error"),
        rollback_steps=list(rollback_result.get("rollback_steps") or []),
    )
    error_type = APICallFailed if rollback_performed else EditMutationRecoveryFailed
    raise error_type(
        (
            "Disk DB mutation did not pass required readback; the project database backup was restored."
            if rollback_performed
            else "Disk DB mutation did not pass required readback, and backup restoration failed."
        ),
        details={
            "reason": (
                "db_mutation_verification_failed_rolled_back"
                if rollback_performed
                else "db_mutation_verification_failed_rollback_failed"
            ),
            "context": context,
            "project_name": session.project_name,
            "project_db_path": session.project_db_path,
            "backup_path": session.backup_path,
            "possible_mutation": not rollback_performed,
            "possible_mutation_state": "rolled_back" if rollback_performed else "unknown_requires_manual_recovery",
            "steps": list(session.steps),
            "verification": verification,
            "mutation": mutation_result,
            "recovery": recovery,
        },
        recoverability="retry_possible" if rollback_performed else "manual",
    )


def _recover_project_after_precommit_failure(
    *,
    session: DiskDbMutationSession,
    active_timeline_name: str | None,
) -> dict[str, Any]:
    steps: list[str] = []
    fresh_conn = None
    try:
        fresh_conn = _fresh_connected_resolve_connection()
        steps.append("connect")

        loaded = _load_project_with_retry(fresh_conn.project_manager, session.project_name)
        if not loaded:
            raise APICallFailed(
                "DaVinci Resolve could not reopen the project after DB mutation failed before commit.",
                details={"project_name": session.project_name, "project_db_path": session.project_db_path},
            )
        steps.append("reopen_project")

        try:
            fresh_conn.wait_for_state(
                lambda state: state["project"] == session.project_name,
                description=f"project '{session.project_name}' to reopen after failed DB mutation",
            )
        except Exception:
            fresh_conn.refresh()

        if active_timeline_name:
            if not _activate_timeline_by_name(fresh_conn, active_timeline_name):
                raise APICallFailed(
                    "DaVinci Resolve could not restore the active timeline after DB mutation failed before commit.",
                    details={"timeline_name": active_timeline_name},
                )
            steps.append("restore_timeline")

        return {"status": "restored", "steps": steps}
    except Exception as exc:
        return {
            "status": "failed",
            "steps": steps,
            "error": {"type": exc.__class__.__name__, "message": str(exc)},
        }


def _recover_after_keyboard_interrupt(
    interrupt: KeyboardInterrupt,
    *,
    session: DiskDbMutationSession,
    active_timeline_name: str | None,
    committed: bool,
    fresh_conn: Any | None = None,
) -> None:
    """Restore the original project state, then let cancellation keep unwinding."""

    if committed:
        recovery = _restore_project_db_from_backup(
            fresh_conn,
            session,
            active_timeline_name=active_timeline_name,
        )
        restored = bool(recovery.get("rollback_performed"))
    else:
        recovery = _recover_project_after_precommit_failure(
            session=session,
            active_timeline_name=active_timeline_name,
        )
        restored = recovery.get("status") == "restored"
    if not restored:
        setattr(interrupt, "cutagent_stop_recovery", recovery)


def _raise_precommit_failure(
    *,
    context: str,
    session: DiskDbMutationSession,
    active_timeline_name: str | None,
    error: Exception,
) -> None:
    set_verification_status("failed")
    recovery = _recover_project_after_precommit_failure(
        session=session,
        active_timeline_name=active_timeline_name,
    )
    if isinstance(error, CLIError):
        if recovery.get("status") != "restored":
            raise APICallFailed(
                "Disk DB mutation failed before commit, and project recovery failed.",
                details={
                    "reason": "db_mutation_pre_commit_recovery_failed",
                    "context": context,
                    "project_name": session.project_name,
                    "timeline_name": active_timeline_name,
                    "project_db_path": session.project_db_path,
                    "steps": list(session.steps),
                    "recovery": recovery,
                    "original_error": {
                        "type": error.__class__.__name__,
                        "code": error.code,
                        "message": str(error),
                        "details": dict(getattr(error, "details", {}) or {}),
                    },
                },
                recoverability="manual",
            ) from error

        error.details = {
            **dict(getattr(error, "details", {}) or {}),
            "recovery": {
                "reason": "db_mutation_pre_commit_failure",
                "context": context,
                "project_name": session.project_name,
                "timeline_name": active_timeline_name,
                **recovery,
            },
        }
        raise error

    if recovery.get("status") == "restored":
        raise error

    raise APICallFailed(
        "Disk DB mutation failed before commit, and project recovery failed.",
        details={
            "reason": "db_mutation_pre_commit_recovery_failed",
            "context": context,
            "project_name": session.project_name,
            "timeline_name": active_timeline_name,
            "project_db_path": session.project_db_path,
            "steps": list(session.steps),
            "recovery": recovery,
            "original_error": {
                "type": error.__class__.__name__,
                "message": str(error),
            },
        },
        recoverability="manual",
    ) from error


def _activate_timeline_by_name(conn, timeline_name: str | None) -> bool:
    if not timeline_name:
        return False
    project = getattr(conn, "project", None)
    if project is None:
        return False
    count = int(project.GetTimelineCount() or 0)
    setter = getattr(project, "SetCurrentTimeline", None)
    if not callable(setter):
        return False
    expected_native_id = os.environ.get("CUTAGENT_SDK_EXPECTED_TIMELINE_NATIVE_ID", "").strip() or None
    matches = []
    for index in range(1, count + 1):
        timeline = project.GetTimelineByIndex(index)
        if (timeline and timeline.GetName() == timeline_name
            and (expected_native_id is None or documented_unique_id(timeline) == expected_native_id)):
            matches.append(timeline)
    if len(matches) != 1 or setter(matches[0]) is False:
        return False
    conn.refresh()
    active = getattr(conn, "timeline", None)
    if active is None:
        current_getter = getattr(project, "GetCurrentTimeline", None)
        active = current_getter() if callable(current_getter) else getattr(project, "current_timeline", None)
    active_name = str(active.GetName() or "").strip() if active and hasattr(active, "GetName") else ""
    active_id = documented_unique_id(active) if active is not None else None
    return active_name == timeline_name and (expected_native_id is None or active_id == expected_native_id)


def _load_project_with_retry(
    project_manager: Any,
    project_name: str,
    *,
    attempts: int = 6,
    delay_seconds: float = 0.5,
) -> bool:
    load_project = getattr(project_manager, "LoadProject", None)
    if not callable(load_project):
        return False
    for attempt in range(max(1, int(attempts))):
        if load_project(project_name):
            return True
        if attempt < attempts - 1:
            time.sleep(delay_seconds)
    return False


def _looks_like_resolve_not_running(error: Exception) -> bool:
    code = getattr(error, "code", None)
    if code == "RESOLVE_NOT_RUNNING":
        return True
    message = str(error)
    return "DaVinci Resolve is not running" in message or "DaVinci Resolve is not running" in message


def _fresh_connected_resolve_connection(*, relaunch_if_not_running: bool = True) -> Any:
    ResolveConnection.reset()
    fresh_conn = ResolveConnection.get()
    try:
        fresh_conn.connect()
        return fresh_conn
    except Exception as exc:
        if not relaunch_if_not_running or not _looks_like_resolve_not_running(exc):
            raise

    from . import launch_ops

    launch_ops.launch_resolve(wait=True, timeout_s=60.0)
    ResolveConnection.reset()
    fresh_conn = ResolveConnection.get()
    fresh_conn.connect()
    return fresh_conn


def next_db_index(cursor: sqlite3.Cursor, *, table_name: str, owner_value: str, property_name: str) -> int:
    row = cursor.execute(
        f'SELECT COALESCE(MAX(DbIndex), -1) + 1 FROM "{table_name}" WHERE DbOwner = ? AND DbPropertyName = ?',
        (owner_value, property_name),
    ).fetchone()
    return int(row[0] or 0)


def rebuild_track_item_indices(cursor: sqlite3.Cursor, *, track_id: str) -> None:
    rows = cursor.execute(
        """
        SELECT
            rel.rowid AS rel_rowid,
            rel.DbAssociate,
            rel.DbIndex,
            item.DbType,
            CAST(COALESCE(item.Start, '0') AS INTEGER) AS start_frame,
            CAST(COALESCE(item.AlignmentType, item.Position, 0) AS INTEGER) AS alignment_type
        FROM Sm2TiItem_Sm2TiTrack rel
        LEFT JOIN Sm2TiItem item ON item.Sm2TiItem_id = rel.DbAssociate
        WHERE rel.DbOwner = ? AND rel.DbPropertyName = 'Items'
        ORDER BY rel.DbIndex
        """,
        (track_id,),
    ).fetchall()
    if not rows:
        return

    def sort_key(row: sqlite3.Row | tuple[Any, ...]) -> tuple[int, int, int, int]:
        db_type = row[3]
        type_priority = 0 if db_type == "Sm2TiTransition" else 1
        alignment = int(row[5] or 0)
        return (int(row[4] or 0), type_priority, alignment, int(row[2] or 0))

    sorted_rows = sorted(rows, key=sort_key)
    for new_index, row in enumerate(sorted_rows):
        cursor.execute(
            "UPDATE Sm2TiItem_Sm2TiTrack SET DbIndex = ? WHERE rowid = ?",
            (new_index + 1000000, row[0]),
        )
    for new_index, row in enumerate(sorted_rows):
        cursor.execute(
            "UPDATE Sm2TiItem_Sm2TiTrack SET DbIndex = ? WHERE rowid = ?",
            (new_index, row[0]),
        )


def _begin_disk_db_transaction(
    connection: sqlite3.Connection,
    *,
    max_attempts: int = 10,
    delay_seconds: float = 0.2,
) -> None:
    last_error: sqlite3.OperationalError | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            connection.execute("BEGIN")
            return
        except sqlite3.OperationalError as exc:
            if "locked" not in str(exc).lower() or attempt == max_attempts:
                raise
            last_error = exc
            time.sleep(delay_seconds)
    if last_error is not None:
        raise last_error


def _is_locked_operational_error(exc: sqlite3.OperationalError) -> bool:
    message = str(exc).strip().lower()
    return "locked" in message or "busy" in message


def _raise_disk_db_locked(
    *,
    context: str,
    project_db_path: str,
    step: str,
    error: sqlite3.OperationalError,
) -> None:
    raise DiskDbLocked(
        (
            "Disk project database is locked by another DaVinci Resolve or CLI mutation. "
            "Run DB-backed commands sequentially and retry."
        ),
        details={
            "reason": "db_locked",
            "context": context,
            "project_db_path": project_db_path,
            "step": step,
            "sqlite_error": str(error),
            "hint": "Do not run multiple DB-backed mutations in parallel against the same Disk project.",
        },
    ) from error


def _project_db_lock_path(project_db_path: str) -> str:
    return f"{project_db_path}{_DB_MUTATION_LOCK_SUFFIX}"


def _disk_db_lock_path(project_db_path: str) -> str:
    return _project_db_lock_path(project_db_path)


def _raise_project_db_mutation_locked(
    *,
    context: str,
    project_db_path: str,
    lock_path: str,
    step: str,
    error: BaseException | None = None,
) -> None:
    raise DiskDbLocked(
        (
            "A DB-backed DaVinci Resolve mutation is already running for this Disk project. "
            "Run DB-backed commands sequentially and retry."
        ),
        details={
            "reason": "db_mutation_lock_held",
            "context": context,
            "project_db_path": project_db_path,
            "lock_path": lock_path,
            "step": step,
            "hint": "Do not run multiple DB-backed mutations in parallel against the same Disk project.",
        },
    ) from error


def _acquire_disk_db_mutation_lock(
    *,
    context: str,
    project_db_path: str,
    timeout_seconds: float = _DB_MUTATION_LOCK_TIMEOUT_SECONDS,
    poll_seconds: float = _DB_MUTATION_LOCK_POLL_SECONDS,
) -> Any | None:
    if fcntl is None and msvcrt is None:
        return None

    lock_path = _project_db_lock_path(project_db_path)
    handle = open(lock_path, "a+")
    deadline = time.monotonic() + max(0.0, float(timeout_seconds))
    last_error: BaseException | None = None
    try:
        while True:
            try:
                _lock_disk_db_mutation_file(handle)
                handle.seek(0)
                handle.truncate()
                handle.write(f"{context}\n")
                handle.flush()
                return handle
            except BlockingIOError as exc:
                last_error = exc
            except OSError as exc:
                if exc.errno not in (errno.EACCES, errno.EAGAIN):
                    raise
                last_error = exc

            if timeout_seconds <= 0 or time.monotonic() >= deadline:
                _raise_project_db_mutation_locked(
                    context=context,
                    project_db_path=project_db_path,
                    lock_path=lock_path,
                    step="project_db_mutation_lock",
                    error=last_error,
                )
            time.sleep(max(float(poll_seconds), 0.01))
    except Exception:
        handle.close()
        raise


def _lock_disk_db_mutation_file(lock_file: Any) -> None:
    if fcntl is not None:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return
    if msvcrt is None:  # pragma: no cover - supported platforms provide one backend
        return

    lock_file.seek(0, 2)
    if lock_file.tell() == 0:
        lock_file.write("\0")
        lock_file.flush()
    lock_file.seek(0)
    msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)


def _unlock_disk_db_mutation_file(lock_file: Any) -> None:
    if fcntl is not None:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        return
    if msvcrt is None:  # pragma: no cover - supported platforms provide one backend
        return

    lock_file.seek(0)
    msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)


def _release_disk_db_mutation_lock(lock_file: Any | None) -> None:
    if lock_file is None:
        return
    try:
        _unlock_disk_db_mutation_file(lock_file)
    finally:
        lock_file.close()


@contextmanager
def _exclusive_disk_db_mutation_lock(
    *,
    context: str,
    project_db_path: str,
    timeout_seconds: float = _DB_MUTATION_LOCK_TIMEOUT_SECONDS,
    poll_seconds: float = _DB_MUTATION_LOCK_POLL_SECONDS,
):
    lock_path = _project_db_lock_path(project_db_path)
    lock_file = _acquire_disk_db_mutation_lock(
        context=context,
        project_db_path=project_db_path,
        timeout_seconds=timeout_seconds,
        poll_seconds=poll_seconds,
    )
    try:
        yield lock_path
    finally:
        _release_disk_db_mutation_lock(lock_file)


def _is_unsaved_default_project_name(project_name: str | None) -> bool:
    return str(project_name or "").strip().casefold().startswith("untitled project")


def _is_save_project_method_unavailable_error(exc: Exception) -> bool:
    message = str(exc)
    details = getattr(exc, "details", None)
    method = details.get("method") if isinstance(details, dict) else None
    if method is not None and method != "SaveProject":
        return False
    lowered = message.casefold()
    return "method not available" in lowered or "unsupported embedded resolve method" in lowered


def _execute_sqlite_disk_db_mutation_unlocked(
    conn,
    *,
    context: str,
    writer: Callable[[Any, sqlite3.Cursor, DiskDbMutationSession], Any],
    verifier: Callable[[Any, Any, DiskDbMutationSession], Any] | None = None,
    pre_close_validator: Callable[[Any, DiskDbMutationSession], Any] | None = None,
    save_project: bool = True,
    allow_project_name_inference: bool = True,
    current_database: dict[str, Any] | None = None,
    acquired_lock_path: str | None = None,
    color_target_ref: Any = None,
    require_verified: bool = False,
) -> dict[str, Any]:
    if current_database is None:
        # DaVinci Resolve Studio's official scripting API never includes project_db_path in
        # GetCurrentDatabase, so DB-backed mutations may infer the path from the
        # open project name when the caller allows it. Inference still requires a
        # Disk DB, exactly one on-disk candidate, and SQLite validation.
        current_database = resolve_current_disk_project_db(
            conn,
            allow_project_name_inference=allow_project_name_inference,
        )
    project = getattr(conn, "project", None)
    project_name = project.GetName() if project and hasattr(project, "GetName") else None
    timeline = getattr(conn, "timeline", None)
    active_timeline_name = timeline.GetName() if timeline and hasattr(timeline, "GetName") else None
    if not project_name:
        raise APICallFailed("No project is open for Disk DB mutation.", details={"context": context})
    if _is_unsaved_default_project_name(project_name):
        raise ValidationError(
            "DB-backed edits require a saved, named DaVinci Resolve project.",
            details={
                "reason": "db_mutation_requires_saved_project",
                "context": context,
                "project_name": project_name,
                "required_action": "Save or rename the project before running DB-backed edits.",
            },
            recoverability="manual",
        )
    if _is_color_db_mutation_context(context) and not str(active_timeline_name or "").strip():
        raise ValidationError(
            "Color Page DB mutation requires an exact active timeline name.",
            details={
                "reason": "db_color_active_timeline_unverified",
                "context": context,
                "project_name": project_name,
            },
            recoverability="manual",
        )
    if color_target_ref is None:
        color_target_ref = _writer_color_target_ref(writer)
    color_version_scope = _audit_color_db_mutation_version_scope(
        conn,
        context=context,
        color_target_ref=color_target_ref,
        project_db_path=str(current_database["project_db_path"]),
        active_timeline_name=active_timeline_name,
    )

    project_db_path = str(current_database["project_db_path"])
    backup_path = f"{project_db_path}.bak"
    session = DiskDbMutationSession(
        project_name=project_name,
        project_db_path=project_db_path,
        backup_path=backup_path,
        current_database=current_database,
        lock_path=acquired_lock_path,
    )
    if acquired_lock_path:
        session.steps.append("acquire_project_db_lock")
    if color_version_scope is not None:
        session.steps.append("verify_color_version_scope")

    if save_project:
        project_manager = getattr(conn, "project_manager", None)
        save_fn = getattr(project_manager, "SaveProject", None) if project_manager is not None else None
        if callable(save_fn):
            try:
                save_result = save_fn()
            except Exception as exc:
                if _is_save_project_method_unavailable_error(exc):
                    session.steps.append("save_project_unavailable_auto_save")
                    time.sleep(5.0)
                    session.steps.append("auto_save_flush_wait")
                else:
                    raise APICallFailed(
                        "DaVinci Resolve project save failed before Disk DB mutation.",
                        details={
                            "reason": "project_save_failed_before_db_mutation",
                            "context": context,
                            "project_name": project_name,
                            "project_db_path": project_db_path,
                            "save_method": "ProjectManager.SaveProject",
                            "save_error": {"type": exc.__class__.__name__, "message": str(exc)},
                            "steps": list(session.steps),
                        },
                        recoverability="manual",
                    ) from exc
            else:
                if save_result is False:
                    session.steps.append("save_project_returned_false")
                    raise APICallFailed(
                        "DaVinci Resolve project save returned False before Disk DB mutation.",
                        details={
                            "reason": "project_save_failed_before_db_mutation",
                            "context": context,
                            "project_name": project_name,
                            "project_db_path": project_db_path,
                            "save_method": "ProjectManager.SaveProject",
                            "api_result": False,
                            "steps": list(session.steps),
                        },
                        recoverability="manual",
                    )
                session.steps.append("save_project")
                time.sleep(5.0)
                session.steps.append("save_project_flush_wait")
        else:
            session.steps.append("save_project_unavailable_auto_save")
            time.sleep(5.0)
            session.steps.append("auto_save_flush_wait")

    if pre_close_validator is not None:
        pre_close_validator(conn, session)
        session.steps.append("validate_pre_close_state")

    shutil.copy2(project_db_path, backup_path)
    session.steps.append("backup_project_db")

    # Saving and creating the backup can take long enough for the live target
    # to change. Once the project closes that race is sealed, so repeat the
    # exact private SDK guard here while the DB lock is still held.
    if pre_close_validator is not None:
        pre_close_validator(conn, session)
        session.steps.append("validate_post_backup_pre_close_state")
    _require_sdk_color_target_pre_close(conn, session)

    try:
        close_current_project_with_runtime_health(
            conn,
            project_name=project_name,
            current_database=current_database,
            project_db_path=project_db_path,
            description=f"project '{project_name}' to close before DB mutation",
        )
        session.steps.append("close_project")
    except KeyboardInterrupt as interrupt:
        _recover_after_keyboard_interrupt(
            interrupt,
            session=session,
            active_timeline_name=active_timeline_name,
            committed=False,
        )
        raise
    try:
        connection = sqlite3.connect(project_db_path, timeout=5.0)
        connection.row_factory = sqlite3.Row
    except KeyboardInterrupt as interrupt:
        _recover_after_keyboard_interrupt(
            interrupt,
            session=session,
            active_timeline_name=active_timeline_name,
            committed=False,
        )
        raise
    except sqlite3.OperationalError as exc:
        if _is_locked_operational_error(exc):
            try:
                _raise_disk_db_locked(context=context, project_db_path=project_db_path, step="sqlite_connect", error=exc)
            except Exception as locked_exc:
                _raise_precommit_failure(
                    context=context,
                    session=session,
                    active_timeline_name=active_timeline_name,
                    error=locked_exc,
                )
        _raise_precommit_failure(
            context=context,
            session=session,
            active_timeline_name=active_timeline_name,
            error=exc,
        )
        raise
    mutation_result: Any = None
    verification: Any = None
    commit_started = False
    try:
        connection.execute("PRAGMA busy_timeout = 5000")
        cursor = connection.cursor()
        try:
            _begin_disk_db_transaction(connection)
        except sqlite3.OperationalError as exc:
            if _is_locked_operational_error(exc):
                try:
                    _raise_disk_db_locked(context=context, project_db_path=project_db_path, step="sqlite_begin", error=exc)
                except Exception as locked_exc:
                    _raise_precommit_failure(
                        context=context,
                        session=session,
                        active_timeline_name=active_timeline_name,
                        error=locked_exc,
                    )
            _raise_precommit_failure(
                context=context,
                session=session,
                active_timeline_name=active_timeline_name,
                error=exc,
            )
        try:
            mutation_result = writer(connection, cursor, session)
            # An interrupt during sqlite commit has an ambiguous durable effect,
            # so recovery must conservatively restore the pre-edit backup.
            commit_started = True
            connection.commit()
            session.steps.append("sqlite_commit")
        except sqlite3.OperationalError as exc:
            connection.rollback()
            if _is_locked_operational_error(exc):
                try:
                    _raise_disk_db_locked(context=context, project_db_path=project_db_path, step="sqlite_write", error=exc)
                except Exception as locked_exc:
                    _raise_precommit_failure(
                        context=context,
                        session=session,
                        active_timeline_name=active_timeline_name,
                        error=locked_exc,
                    )
            _raise_precommit_failure(
                context=context,
                session=session,
                active_timeline_name=active_timeline_name,
                error=exc,
            )
        except Exception as exc:
            connection.rollback()
            _raise_precommit_failure(
                context=context,
                session=session,
                active_timeline_name=active_timeline_name,
                error=exc,
            )
    except KeyboardInterrupt as interrupt:
        if not commit_started:
            try:
                connection.rollback()
            except Exception:
                pass
        try:
            connection.close()
        except Exception:
            pass
        connection = None
        _recover_after_keyboard_interrupt(
            interrupt,
            session=session,
            active_timeline_name=active_timeline_name,
            committed=commit_started,
        )
        raise
    finally:
        if connection is not None:
            connection.close()

    fresh_conn = None
    try:
        fresh_conn = _fresh_connected_resolve_connection()

        loaded = _load_project_with_retry(fresh_conn.project_manager, project_name)
        if not loaded:
            raise APICallFailed(
                "DaVinci Resolve could not reopen the project after DB mutation.",
                details={"project_name": project_name, "project_db_path": project_db_path},
            )
        try:
            fresh_conn.wait_for_state(
                lambda state: state["project"] == project_name,
                description=f"project '{project_name}' to reopen",
            )
        except Exception:
            fresh_conn.refresh()
        session.steps.append("reopen_project")
    except KeyboardInterrupt as interrupt:
        _recover_after_keyboard_interrupt(
            interrupt,
            session=session,
            active_timeline_name=active_timeline_name,
            committed=True,
            fresh_conn=fresh_conn,
        )
        raise
    except Exception as exc:
        _raise_post_commit_failure(
            context=context,
            session=session,
            failure_step="reopen_project",
            error=exc,
            fresh_conn=fresh_conn,
            active_timeline_name=active_timeline_name,
        )
    if active_timeline_name:
        try:
            restored_timeline = _activate_timeline_by_name(fresh_conn, active_timeline_name)
            if not restored_timeline:
                raise APICallFailed(
                    "DaVinci Resolve could not restore the active timeline after DB mutation.",
                    details={"timeline_name": active_timeline_name},
                )
            session.steps.append("restore_timeline")
        except KeyboardInterrupt as interrupt:
            _recover_after_keyboard_interrupt(
                interrupt,
                session=session,
                active_timeline_name=active_timeline_name,
                committed=True,
                fresh_conn=fresh_conn,
            )
            raise
        except Exception as exc:
            _raise_post_commit_failure(
                context=context,
                session=session,
                failure_step="restore_timeline",
                error=exc,
                fresh_conn=fresh_conn,
                active_timeline_name=active_timeline_name,
            )
    if verifier:
        try:
            # Verifier runs after DaVinci Resolve reload; failures here need backup recovery, not SQLite rollback.
            verification = verifier(fresh_conn, mutation_result, session)
            session.steps.append("verify")
        except KeyboardInterrupt as interrupt:
            _recover_after_keyboard_interrupt(
                interrupt,
                session=session,
                active_timeline_name=active_timeline_name,
                committed=True,
                fresh_conn=fresh_conn,
            )
            raise
        except Exception as exc:
            _raise_post_commit_failure(
                context=context,
                session=session,
                failure_step="verifier",
                error=exc,
                fresh_conn=fresh_conn,
                active_timeline_name=active_timeline_name,
            )
    if require_verified and (not isinstance(verification, dict) or verification.get("status") != "verified"):
        try:
            _raise_required_verification_failure(
                context=context,
                session=session,
                mutation_result=mutation_result,
                verification=verification if isinstance(verification, dict) else {"status": "missing"},
                fresh_conn=fresh_conn,
                active_timeline_name=active_timeline_name,
            )
        except KeyboardInterrupt as interrupt:
            _recover_after_keyboard_interrupt(
                interrupt,
                session=session,
                active_timeline_name=active_timeline_name,
                committed=True,
                fresh_conn=fresh_conn,
            )
            raise

    set_execution_engine("db_workaround")
    verification_status = "verified"
    if isinstance(verification, dict) and verification.get("status"):
        verification_status = str(verification.get("status"))
    set_verification_status(verification_status)

    payload = mutation_result if isinstance(mutation_result, dict) else {"result": mutation_result}
    payload.update(
        {
            "route": "db_native",
            "project_db_path": project_db_path,
            "backup_path": backup_path,
            "lock_path": acquired_lock_path,
            "steps": list(session.steps),
        }
    )
    if verification is not None:
        payload["verification"] = verification
    if color_version_scope is not None:
        payload["color_version_scope"] = color_version_scope
    return payload


def execute_sqlite_disk_db_mutation(
    conn,
    *,
    context: str,
    writer: Callable[[Any, sqlite3.Cursor, DiskDbMutationSession], Any],
    verifier: Callable[[Any, Any, DiskDbMutationSession], Any] | None = None,
    pre_close_validator: Callable[[Any, DiskDbMutationSession], Any] | None = None,
    save_project: bool = True,
    allow_project_name_inference: bool = True,
    color_target_ref: Any = None,
    require_verified: bool = False,
) -> dict[str, Any]:
    current_database = resolve_current_disk_project_db(
        conn,
        allow_project_name_inference=allow_project_name_inference,
    )
    project_db_path = str(current_database["project_db_path"])
    with _exclusive_disk_db_mutation_lock(
        context=context,
        project_db_path=project_db_path,
        timeout_seconds=_DB_MUTATION_LOCK_TIMEOUT_SECONDS,
    ) as lock_path:
        refresh = getattr(conn, "refresh", None)
        if callable(refresh):
            try:
                refresh()
            except Exception:
                pass
        locked_current_database = resolve_current_disk_project_db(
            conn,
            allow_project_name_inference=allow_project_name_inference,
        )
        locked_project_db_path = str(locked_current_database["project_db_path"])
        if locked_project_db_path != project_db_path:
            raise APICallFailed(
                "Active Disk project changed while waiting for the DB mutation lock.",
                details={
                    "reason": "db_mutation_project_changed_while_waiting_for_lock",
                    "context": context,
                    "locked_project_db_path": project_db_path,
                    "active_project_db_path": locked_project_db_path,
                    "lock_path": lock_path,
                    "hint": "Retry the DB-backed command after confirming the intended project is active.",
                },
                recoverability="retry_possible",
            )
        return _execute_sqlite_disk_db_mutation_unlocked(
            conn,
            context=context,
            writer=writer,
            verifier=verifier,
            pre_close_validator=pre_close_validator,
            save_project=save_project,
            allow_project_name_inference=allow_project_name_inference,
            current_database=locked_current_database,
            acquired_lock_path=lock_path,
            color_target_ref=color_target_ref,
            require_verified=require_verified,
        )
