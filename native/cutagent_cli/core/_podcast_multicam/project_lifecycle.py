"""Project lifecycle helpers for DB-backed multicam orchestration."""

from __future__ import annotations

import time
from typing import Any

from ...errors import APICallFailed, CLIError, ValidationError
from ...output import set_recoverability, set_verification_status
from ...runtime_health import close_current_project_with_runtime_health, get_current_database_details
from ...state_contracts import project_is_closed_enough
from .. import media_pool


def _set_workflow_verification(status: str) -> None:
    set_verification_status(status)
    set_recoverability("not_applicable" if status in {"verified", "not_requested"} else "manual")


def _current_database_details(conn, *, get_current_database_details_fn=None) -> dict[str, Any]:
    resolver = get_current_database_details_fn or get_current_database_details
    return resolver(conn)


def _require_live_project_name(
    conn,
    *,
    context: str,
    attempts: int = 6,
    delay: float = 0.1,
) -> str:
    project = getattr(conn, "project", None)
    getter = getattr(project, "GetName", None) if project is not None else None
    if callable(getter):
        try:
            project_name = str(getter() or "").strip()
        except Exception:
            project_name = ""
        if project_name:
            return project_name

    wait_for_state = getattr(conn, "wait_for_state", None)
    if not callable(wait_for_state):
        raise APICallFailed(
            f"Cannot determine the current project name for {context}.",
            details={"context": context},
        )

    try:
        state = wait_for_state(
            lambda live_state: bool(str(live_state.get("project") or "").strip()),
            description=f"an open DaVinci Resolve project for {context}",
            attempts=attempts,
            delay=delay,
        )
    except Exception as exc:
        raise APICallFailed(
            f"Cannot determine the current project name for {context}.",
            details={"context": context},
        ) from exc

    project_name = str(state.get("project") or "").strip()
    if not project_name:
        raise APICallFailed(
            f"Cannot determine the current project name for {context}.",
            details={"context": context},
        )
    conn.refresh()
    return project_name


def _project_closed_enough_for_db_write(
    state: dict[str, Any],
    *,
    original_project_name: str,
    project_is_closed_enough_fn=None,
) -> bool:
    checker = project_is_closed_enough_fn or project_is_closed_enough
    return checker(state, original_project_name=original_project_name)


def _timeline_exists(conn, timeline_name: str) -> bool:
    count = conn.project.GetTimelineCount() or 0
    for index in range(1, count + 1):
        timeline = conn.project.GetTimelineByIndex(index)
        if timeline and hasattr(timeline, "GetName") and timeline.GetName() == timeline_name:
            return True
    return False


def _ensure_target_timeline_name_available(conn, *, timeline_name: str) -> None:
    if _timeline_exists(conn, timeline_name):
        raise ValidationError(
            "Target timeline already exists. Choose a new timeline name and rerun.",
            details={
                "reason": "target_timeline_already_exists",
                "timeline_name": timeline_name,
            },
        )


def _close_current_project(
    conn,
    *,
    project_name: str,
    current_database: dict[str, Any] | None = None,
    project_db_path: str | None = None,
    save: bool,
    save_step_name: str = "project_save",
    close_step_name: str = "project_close",
    wait_description: str | None = None,
    close_current_project_with_runtime_health_fn=None,
    current_database_details_fn=None,
) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    if save:
        project_manager = getattr(conn, "project_manager", None)
        save_fn = getattr(project_manager, "SaveProject", None) if project_manager is not None else None
        if callable(save_fn):
            save_result = save_fn()
            steps.append({"name": save_step_name, "ok": save_result is not False, "project_name": project_name})
        else:
            steps.append({"name": save_step_name, "ok": True, "project_name": project_name, "mode": "autosave"})

    closer = close_current_project_with_runtime_health_fn or close_current_project_with_runtime_health
    close_state = closer(
        conn,
        project_name=project_name,
        current_database=current_database
        or _current_database_details(
            conn,
            get_current_database_details_fn=current_database_details_fn,
        ),
        description=wait_description or f"project '{project_name}' to stop being current before Project.db write",
        project_db_path=project_db_path,
    )
    steps.append(
        {
            "name": close_step_name,
            "ok": True,
            "project_name": project_name,
            "resolved_project": close_state.get("project"),
            "resolved_timeline": close_state.get("timeline"),
        }
    )
    return steps


def _save_and_close_current_project(
    conn,
    *,
    project_name: str,
    current_database: dict[str, Any] | None = None,
    project_db_path: str | None = None,
    close_current_project_with_runtime_health_fn=None,
    current_database_details_fn=None,
) -> list[dict[str, Any]]:
    return _close_current_project(
        conn,
        project_name=project_name,
        current_database=current_database,
        project_db_path=project_db_path,
        save=True,
        close_current_project_with_runtime_health_fn=close_current_project_with_runtime_health_fn,
        current_database_details_fn=current_database_details_fn,
    )


def _reopen_project(
    conn,
    *,
    project_name: str,
    attempts: int = 8,
    delay: float = 0.25,
) -> dict[str, Any]:
    reopened = None
    for attempt in range(1, attempts + 1):
        reopened = conn.project_manager.LoadProject(project_name)
        if reopened:
            break
        if attempt < attempts:
            time.sleep(delay)
    if not reopened:
        raise APICallFailed(
            "Failed to reopen the project after DB-backed multicam creation.",
            details={"project_name": project_name, "attempts": attempts},
        )
    conn.wait_for_state(
        lambda state: state.get("project") == project_name,
        description=f"project '{project_name}' to reopen after Project.db write",
    )
    conn.refresh()
    return {"name": "project_reopen", "ok": True, "project_name": project_name}


def _best_effort_reopen_project(conn, *, project_name: str, failure_step: str) -> dict[str, Any] | None:
    try:
        reopened = _reopen_project(conn, project_name=project_name)
    except Exception as reopen_exc:
        details: dict[str, Any] = {"step": failure_step}
        if isinstance(reopen_exc, CLIError):
            details.update(dict(reopen_exc.details))
        details.update({"project_name": project_name, "reopen_failed": True})
        raise APICallFailed(
            "Native multicam create failed and DaVinci Resolve could not restore the original project afterwards.",
            details=details,
            recoverability="manual",
        ) from reopen_exc

    reopened["name"] = f"{failure_step}_project_restore"
    reopened["restore_after_failure"] = True
    return reopened


def _wait_for_multicam_clip_exposure(
    conn,
    *,
    multicam_name: str,
    attempts: int = 16,
    delay: float = 0.25,
) -> tuple[Any, int]:
    last_lookup_error: dict[str, Any] | None = None

    for attempt in range(1, attempts + 1):
        conn.refresh()
        try:
            created_clip = media_pool.find_clip(conn, multicam_name)
        except ValidationError as exc:
            last_lookup_error = dict(exc.details)
            created_clip = None
        if created_clip:
            return created_clip, attempt
        if attempt < attempts:
            time.sleep(delay)

    details: dict[str, Any] = {"multicam_name": multicam_name, "attempts": attempts}
    if last_lookup_error:
        details["lookup_error"] = last_lookup_error
    raise APICallFailed(
        "DB-backed multicam clip was written but DaVinci Resolve did not expose it after reopening the project.",
        details=details,
    )


def _materialize_multicam_timeline(
    conn,
    *,
    created_clip: Any,
    multicam_name: str,
    timeline_name: str,
    ops_module,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    _ensure_target_timeline_name_available(conn, timeline_name=timeline_name)
    verification_checks = [
        {"name": "multicam_clip_exists", "ok": True, "multicam_name": multicam_name},
    ]

    creator = getattr(conn.media_pool, "CreateEmptyTimeline", None)
    timeline = creator(timeline_name) if callable(creator) else None
    if not timeline:
        fallback_creator = getattr(conn.media_pool, "CreateTimelineFromClips", None)
        timeline = fallback_creator(timeline_name, [created_clip]) if callable(fallback_creator) else None
    if not timeline:
        raise APICallFailed(
            "Failed to create the target timeline for the DB-backed multicam clip.",
            details={"timeline_name": timeline_name, "multicam_name": multicam_name},
        )

    project = getattr(conn, "project", None)
    setter = getattr(project, "SetCurrentTimeline", None) if project is not None else None
    if callable(setter):
        set_result = setter(timeline)
        if set_result is False:
            raise APICallFailed(
                "DaVinci Resolve created the target timeline but refused to make it current.",
                details={"timeline_name": timeline_name, "multicam_name": multicam_name},
            )

    wait_for_state = getattr(conn, "wait_for_state", None)
    if callable(wait_for_state):
        try:
            wait_for_state(
                lambda state: str(state.get("timeline") or "").strip() == timeline_name,
                description=f"timeline '{timeline_name}' to become current after multicam materialization",
                attempts=8,
                delay=0.1,
            )
        except Exception:
            pass

    ops_module._append_multicam_clip_to_active_timeline(
        conn,
        created_clip=created_clip,
        multicam_name=multicam_name,
    )

    project_manager = getattr(conn, "project_manager", None)
    save_fn = getattr(project_manager, "SaveProject", None) if project_manager is not None else None
    if callable(save_fn) and save_fn() is False:
        raise APICallFailed(
            "DaVinci Resolve created the target timeline but refused to save the project afterwards.",
            details={"timeline_name": timeline_name, "multicam_name": multicam_name},
        )

    conn.refresh()
    verification_checks.append({"name": "timeline_exists", "ok": True, "timeline_name": timeline_name})
    verification_checks.append(
        {
            "name": "timeline_active",
            "ok": True,
            "timeline_name": timeline_name,
        }
    )

    current_timeline = getattr(conn, "timeline", None)
    item_getter = getattr(current_timeline, "GetItemListInTrack", None)
    if callable(item_getter):
        video_items = item_getter("video", 1) or []
        if not video_items:
            raise APICallFailed(
                "The target timeline was created, but the DB-backed multicam clip did not populate it.",
                details={"timeline_name": timeline_name, "multicam_name": multicam_name},
            )
        verification_checks.append(
            {
                "name": "timeline_populated",
                "ok": True,
                "timeline_name": timeline_name,
                "video_item_count": len(video_items),
            }
        )
    else:
        verification_checks.append(
            {
                "name": "timeline_populated",
                "ok": True,
                "timeline_name": timeline_name,
                "verification_source": "append_result",
            }
        )
    return {
        "name": "timeline_materialization",
        "ok": True,
        "timeline_name": timeline_name,
        "multicam_name": multicam_name,
    }, verification_checks


def _raise_step_failure(step: str, exc: Exception, *, extra: dict[str, Any] | None = None) -> None:
    details: dict[str, Any] = {"step": step}
    if isinstance(exc, CLIError):
        details.update(dict(exc.details))
    if extra:
        details.update(extra)

    if isinstance(exc, ValidationError):
        raise ValidationError(str(exc), details=details, recoverability=exc.recoverability) from exc
    if isinstance(exc, APICallFailed):
        raise APICallFailed(str(exc), details=details, recoverability=exc.recoverability) from exc
    raise APICallFailed(str(exc), details=details) from exc
