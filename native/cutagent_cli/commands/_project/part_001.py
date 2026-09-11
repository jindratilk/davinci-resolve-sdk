"""Project management commands."""

from __future__ import annotations

import os
import time
from typing import Optional

import typer

from ..connection import get_connection
from ..errors import APICallFailed, CLIError, CapabilityNegotiationFailed, ConfirmationRequired, NoProjectOpen, ValidationError, handle_errors
from ..output import (
    dry_run_message,
    is_dry_run,
    is_machine_mode,
    mutation_payload,
    output,
    set_execution_engine,
    set_verification_status,
    success,
    warning,
)
from ..policy import enforce_mutation_policy, require_api_method
from ..runtime_health import close_current_project_with_runtime_health, get_current_database_details, try_current_database_details
from ..state_contracts import (
    current_project_folder_name,
    looks_like_project_manager_placeholder,
    project_folder_path_label,
)
from ..core import project_library_ops, project_ops, timeline_ops
from ..core.sdk_live_inspection import require_project_mutation_guard

app = typer.Typer(help="Project management.")

_PROJECT_SETTING_VALUE_ALIASES: dict[tuple[str, str], str] = {
    ("colorSpaceTimeline", "davinci wide gamut intermediate"): "DaVinci WG/Intermediate",
    ("colorSpaceTimeline", "davinci wide gamut / intermediate"): "DaVinci WG/Intermediate",
    ("colorSpaceTimeline", "davinci wide gamut/intermediate"): "DaVinci WG/Intermediate",
    ("colorSpaceTimeline", "davinci wg intermediate"): "DaVinci WG/Intermediate",
    ("colorSpaceTimeline", "dwg intermediate"): "DaVinci WG/Intermediate",
    ("colorSpaceTimeline", "dwg/intermediate"): "DaVinci WG/Intermediate",
}

_COMBINED_TIMELINE_COLOR_SPACES = {"DaVinci WG/Intermediate"}
_DEFAULT_SCRATCH_PROJECT_PREFIXES = (
    "CA CLI Color Proof",
    "CA Color Slice",
    "CA Color Warper",
    "CA Local Color",
    "CA ResolveFX",
    "CA Sky Isolation",
    "CutAgent Color Proof",
    "CutAgent ResolveFX",
    "CutAgent Scratch",
)


def _normalize_project_setting_value(key: str, value: str) -> tuple[str, dict[str, str] | None]:
    normalized = _PROJECT_SETTING_VALUE_ALIASES.get((key, value.strip().lower()))
    if normalized is None:
        return value, None
    return normalized, {"requested_value": value, "normalized_value": normalized}


def _read_project_setting(project, key: str, settings_map: object | None = None):
    if isinstance(settings_map, dict) and key in settings_map:
        return settings_map[key]
    getter = getattr(project, "GetSetting", None)
    if not callable(getter):
        return None
    try:
        refreshed = getter()
    except Exception:
        refreshed = None
    if isinstance(refreshed, dict) and key in refreshed:
        return refreshed[key]
    try:
        return getter(key)
    except Exception:
        return None


def _project_setting_values_match(actual: object, expected: object) -> bool:
    if actual is None:
        return False

    actual_str = str(actual).strip()
    expected_str = str(expected).strip()
    if actual_str == expected_str:
        return True

    try:
        return float(actual_str) == float(expected_str)
    except (TypeError, ValueError):
        return False


def _project_unique_id(project) -> str | None:
    getter = getattr(project, "GetUniqueId", None)
    if not callable(getter):
        return None
    try:
        value = getter()
    except Exception:
        return None
    return str(value) if value not in (None, "") else None


def _folder_exists(conn, name: str) -> bool:
    folders = conn.project_manager.GetFolderListInCurrentFolder() or []
    return str(name) in {str(folder) for folder in folders}


def _project_exists_in_current_folder(conn, name: str) -> bool | None:
    get_projects = getattr(conn.project_manager, "GetProjectListInCurrentFolder", None)
    if not callable(get_projects):
        return None
    try:
        projects = get_projects() or []
    except Exception:
        return None
    return str(name) in {str(project) for project in projects}


def _read_project_exists_for_open(conn, name: str) -> bool:
    """Read current-folder membership without allowing an ambiguous open."""
    get_projects = require_api_method(
        conn.project_manager,
        "GetProjectListInCurrentFolder",
        capability_id="project.open",
        runtime_object="ProjectManager",
    )
    try:
        projects = get_projects()
    except CLIError:
        raise
    except Exception as exc:
        raise APICallFailed(
            "Failed to list projects before opening a DaVinci Resolve project.",
            details={
                "method": "ProjectManager.GetProjectListInCurrentFolder",
                "reason": "runtime_project_open_list_exception",
                "error_type": exc.__class__.__name__,
            },
        ) from exc
    if not isinstance(projects, list):
        raise APICallFailed(
            "DaVinci Resolve did not return a verifiable project list before opening a project.",
            details={
                "method": "ProjectManager.GetProjectListInCurrentFolder",
                "reason": "runtime_project_open_list_unavailable",
                "result_type": type(projects).__name__,
            },
        )
    return str(name) in {str(project) for project in projects}


def _current_project_name_matches(conn, name: str) -> bool:
    project = getattr(conn, "project", None)
    get_name = getattr(project, "GetName", None)
    if not callable(get_name):
        return False
    try:
        return str(get_name()) == str(name)
    except Exception:
        return False


def _refresh_connection(conn) -> None:
    refresh = getattr(conn, "refresh", None)
    if callable(refresh):
        try:
            refresh()
        except Exception:
            pass


def _read_project_exists_for_delete(conn, name: str) -> bool:
    get_projects = getattr(conn.project_manager, "GetProjectListInCurrentFolder", None)
    if not callable(get_projects):
        raise APICallFailed(
            "DaVinci Resolve cannot verify the project list after deletion.",
            details={
                "method": "ProjectManager.GetProjectListInCurrentFolder",
                "reason": "runtime_project_delete_readback_unavailable",
                "project_name": name,
                "result_type": "method_unavailable",
            },
        )
    try:
        projects = get_projects()
    except APICallFailed:
        raise
    except Exception as exc:
        raise APICallFailed(
            "DaVinci Resolve failed while reading the project list for deletion verification.",
            details={
                "method": "ProjectManager.GetProjectListInCurrentFolder",
                "reason": "runtime_project_delete_readback_exception",
                "project_name": name,
                "error_type": exc.__class__.__name__,
            },
        ) from exc
    if not isinstance(projects, list):
        raise APICallFailed(
            "DaVinci Resolve did not return a verifiable project list for deletion.",
            details={
                "method": "ProjectManager.GetProjectListInCurrentFolder",
                "reason": "runtime_project_delete_readback_unavailable",
                "project_name": name,
                "result_type": type(projects).__name__,
            },
        )
    return str(name) in {str(project) for project in projects}


def _wait_for_project_deleted(conn, name: str, *, existed_before: bool) -> bool:
    if not existed_before:
        return False
    last_error: APICallFailed | None = None
    for attempt in range(6):
        try:
            if not _read_project_exists_for_delete(conn, name):
                return True
            last_error = None
        except APICallFailed as exc:
            last_error = exc
        if attempt < 5:
            _refresh_connection(conn)
            time.sleep(0.1)
    if last_error is not None:
        raise last_error
    return False


def _project_names_in_current_folder(conn) -> list[str]:
    get_projects = getattr(conn.project_manager, "GetProjectListInCurrentFolder", None)
    if not callable(get_projects):
        raise CapabilityNegotiationFailed(
            "Project cleanup requires GetProjectListInCurrentFolder.",
            details={
                "capability_id": "project.cleanup_scratch",
                "required_method": "ProjectManager.GetProjectListInCurrentFolder",
                "runtime_object": "project_manager",
            },
        )
    try:
        projects = get_projects()
    except CLIError:
        raise
    except Exception as exc:
        raise APICallFailed(
            "Failed to list projects before scratch cleanup.",
            details={
                "method": "ProjectManager.GetProjectListInCurrentFolder",
                "reason": "runtime_project_cleanup_list_exception",
                "error_type": exc.__class__.__name__,
            },
        ) from exc
    if not isinstance(projects, list):
        raise APICallFailed(
            "DaVinci Resolve did not return a verifiable project list for scratch cleanup.",
            details={
                "method": "ProjectManager.GetProjectListInCurrentFolder",
                "reason": "runtime_project_cleanup_list_unavailable",
                "result_type": type(projects).__name__,
            },
        )
    return [str(project) for project in projects]


def _current_project_name(conn) -> str | None:
    project = getattr(conn, "project", None)
    if project is None:
        return None
    get_name = getattr(project, "GetName", None)
    if not callable(get_name):
        raise CapabilityNegotiationFailed(
            "Project cleanup cannot protect the current project because GetName is unavailable.",
            details={
                "capability_id": "project.cleanup_scratch",
                "required_method": "Project.GetName",
                "runtime_object": "Project",
            },
        )
    try:
        name = str(get_name() or "").strip()
    except CLIError:
        raise
    except Exception as exc:
        raise APICallFailed(
            "Failed to read the current project before scratch cleanup.",
            details={
                "method": "Project.GetName",
                "reason": "runtime_project_cleanup_current_name_exception",
                "error_type": exc.__class__.__name__,
            },
        ) from exc
    if not name:
        raise APICallFailed(
            "DaVinci Resolve did not return a verifiable current project name for scratch cleanup.",
            details={
                "method": "Project.GetName",
                "reason": "runtime_project_cleanup_current_name_unavailable",
            },
        )
    return name


def _normalize_scratch_prefixes(prefixes: list[str] | None) -> list[str]:
    values = list(prefixes or _DEFAULT_SCRATCH_PROJECT_PREFIXES)
    normalized = [str(value).strip() for value in values if str(value or "").strip()]
    if not normalized:
        raise ValidationError(
            "Project scratch cleanup requires at least one non-empty --prefix.",
            details={"prefixes": prefixes},
            recoverability="not_applicable",
        )
    return normalized


def _scratch_cleanup_candidates(
    project_names: list[str],
    *,
    prefixes: list[str],
    current_project: str | None,
    include_current: bool,
    limit: int,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    candidates: list[dict[str, object]] = []
    skipped: list[dict[str, object]] = []
    for name in project_names:
        matched_prefix = next((prefix for prefix in prefixes if name.startswith(prefix)), None)
        if matched_prefix is None:
            continue
        row = {
            "name": name,
            "matched_prefix": matched_prefix,
            "current": bool(current_project and name == current_project),
        }
        if row["current"] and not include_current:
            skipped.append({**row, "reason": "current_project"})
            continue
        candidates.append(row)
    if len(candidates) > limit:
        raise ValidationError(
            "Project scratch cleanup matched more projects than --limit allows.",
            details={
                "matched_count": len(candidates),
                "limit": limit,
                "prefixes": prefixes,
                "candidate_names": [row["name"] for row in candidates],
            },
            recoverability="not_applicable",
        )
    return candidates, skipped


def _resolve_archive_artifact_path(path: str) -> str | None:
    candidates = [os.path.abspath(path)]
    if not str(path).lower().endswith(".dra"):
        candidates.append(os.path.abspath(f"{path}.dra"))
    for candidate in candidates:
        if os.path.isdir(candidate):
            try:
                if os.listdir(candidate):
                    return candidate
            except OSError:
                continue
        elif os.path.isfile(candidate):
            return candidate
    return None


def _resolve_project_export_artifact_path(path: str) -> str | None:
    candidates = [os.path.abspath(path)]
    if not str(path).lower().endswith(".drp"):
        candidates.append(os.path.abspath(f"{path}.drp"))
    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate
    return None


def _normalize_project_export_output_path(path: str) -> str:
    expanded = os.path.abspath(os.path.expanduser(path))
    parent = os.path.dirname(expanded) or os.getcwd()
    if not os.path.isdir(parent):
        raise ValidationError(
            "Project export output parent directory does not exist.",
            details={
                "path": path,
                "export_path": expanded,
                "parent": parent,
            },
        )
    return expanded


def _normalize_archive_output_path(path: str) -> str:
    expanded = os.path.abspath(os.path.expanduser(path))
    parent = os.path.dirname(expanded) or os.getcwd()
    if not os.path.isdir(parent):
        raise ValidationError(
            "Archive output parent directory does not exist.",
            details={
                "path": path,
                "archive_path": expanded,
                "parent": parent,
            },
        )
    return expanded


def _api_method_not_available(exc: APICallFailed) -> bool:
    message = str(exc).lower()
    details = getattr(exc, "details", {}) or {}
    detail_text = " ".join(str(value).lower() for value in details.values())
    return "method not available" in message or "method not available" in detail_text


def _normalize_database_type_for_switch(db_type: str) -> str:
    normalized = str(db_type).strip().lower()
    if normalized == "disk":
        return "Disk"
    raise ValidationError(
        "Unsupported database type for project db switch.",
        details={
            "db_type": db_type,
            "allowed": ["Disk"],
            "reason": "This command can only switch Disk databases because PostgreSQL requires additional connection details.",
        },
    )


def _database_matches(db: dict, *, name: str, db_type: str) -> bool:
    return str(db.get("DbName", "")) == str(name) and str(db.get("DbType", "")) == str(db_type)


def _find_database(conn, *, name: str, db_type: str) -> dict | None:
    get_databases = getattr(conn.project_manager, "GetDatabaseList", None)
    if not callable(get_databases):
        return None
    databases = get_databases() or []
    for db in databases:
        if isinstance(db, dict) and _database_matches(db, name=name, db_type=db_type):
            return db
    return None


@app.command("list")
@handle_errors
def list_projects():
    """List all projects in the current database folder."""
    conn = get_connection(require_project=False)
    get_projects = require_api_method(
        conn.project_manager,
        "GetProjectListInCurrentFolder",
        capability_id="project.list",
        runtime_object="ProjectManager",
    )
    try:
        projects = get_projects()
    except CLIError:
        raise
    except Exception as exc:
        raise APICallFailed(
            "Failed to list projects in the current DaVinci Resolve project-library folder.",
            details={
                "method": "ProjectManager.GetProjectListInCurrentFolder",
                "error_type": exc.__class__.__name__,
            },
        ) from exc
    if not projects:
        output([])
        return

    current = conn.project.GetName() if conn.project else None
    rows = []
    for i, name in enumerate(projects, 1):
        rows.append({
            "index": i,
            "name": name,
            "current": "✓" if name == current else "",
        })
    output(rows, columns=[("index", "#"), ("name", "Name"), ("current", "Current")], title="Projects", quiet_key="name")


@app.command()
@handle_errors
def create(
    name: str = typer.Argument(..., help="Project name"),
    media_location: Optional[str] = typer.Option(None, "--media-location", help="Optional project media location path"),
):
    """Create a new project."""
    enforce_mutation_policy(
        "project.create",
        intended_engine="api_native",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        dry_run_message(f"Would create project: {name}")
        return
    conn = get_connection(require_project=False)
    require_project_mutation_guard(conn, list_timelines=timeline_ops.list_timelines)
    created = project_ops.create_project(conn, name, media_location_path=media_location)
    if created.get("used_gui"):
        set_execution_engine("resolve_gui", 1.0)
    set_verification_status("verified")
    output(
        mutation_payload(
            action="project.create",
            target={"kind": "project", "name": name},
            verification_status="verified",
            media_location_path=media_location,
            message=f"Created and opened project: {name}",
        )
    )


@app.command("rename")
@handle_errors
def rename_project(
    name: str = typer.Argument(..., help="New project name"),
):
    """Rename the current project."""
    enforce_mutation_policy("project.settings_write", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        dry_run_message(f"Would rename the current project to: {name}")
        return
    conn = get_connection(require_project=True)
    data = project_ops.rename_current_project(conn, name)
    set_verification_status("verified")
    message = f"Renamed project to: {name}" if data.get("renamed") else f"Project name unchanged: {name}"
    output(
        mutation_payload(
            action="project.rename",
            target={"kind": "project", "name": data.get("old_name")},
            changed=bool(data.get("renamed")),
            verification_status="verified",
            **data,
            message=message,
        )
    )


@app.command("open")
@handle_errors
def open_project(name: str = typer.Argument(..., help="Project name")):
    """Open an existing project."""
    enforce_mutation_policy("project.open", intended_engine="api_native", mutating=not is_dry_run())
    project_ops.validate_project_name(name)
    conn = get_connection(require_project=False)
    require_project_mutation_guard(conn, list_timelines=timeline_ops.list_timelines)
    current_project = getattr(conn, "project", None)
    get_current_name = None
    if current_project is not None:
        get_current_name = require_api_method(
            current_project,
            "GetName",
            capability_id="project.open",
            runtime_object="Project",
        )
    try:
        current_name = get_current_name() if get_current_name is not None else None
    except CLIError:
        raise
    except Exception as exc:
        raise APICallFailed(
            "Failed to read the current DaVinci Resolve project before opening another project.",
            details={"method": "Project.GetName", "error_type": exc.__class__.__name__},
        ) from exc
    project_exists = _read_project_exists_for_open(conn, name)
    already_open = current_name == name and project_exists
    if is_dry_run():
        output(
            mutation_payload(
                action="project.open",
                target={"kind": "project", "name": name},
                changed=False,
                would_open=not already_open and project_exists,
                already_open=already_open,
                current_project=current_name,
                project_exists=project_exists,
                runtime_open_called=False,
                message=(
                    f"DRY-RUN: Project already open: {name}"
                    if already_open
                    else (
                        f"DRY-RUN: Would open project: {name}"
                        if project_exists
                        else f"DRY-RUN: Project not found in the current folder: {name}"
                    )
                ),
            )
        )
        return

    if already_open:
        conn.wait_for_state(
            lambda state: state["project"] == name,
            description=f"project '{name}' to remain current",
        )
        set_verification_status("verified")
        output(
            mutation_payload(
                action="project.open",
                target={"kind": "project", "name": name},
                changed=False,
                verification_status="verified",
                message=f"Project already open: {name}",
            )
        )
        return
    if not project_exists:
        raise APICallFailed(
            f"Project '{name}' was not found in the current DaVinci Resolve project-library folder.",
            details={"name": name, "project_exists": False},
            recoverability="manual",
        )
    load_project = require_api_method(
        conn.project_manager,
        "LoadProject",
        capability_id="project.open",
        runtime_object="ProjectManager",
    )
    try:
        project = load_project(name)
    except CLIError:
        raise
    except Exception as exc:
        raise APICallFailed(
            f"DaVinci Resolve failed to open project '{name}'.",
            details={
                "name": name,
                "method": "ProjectManager.LoadProject",
                "error_type": exc.__class__.__name__,
            },
        ) from exc
    if not project:
        raise APICallFailed(
            f"Failed to open project '{name}'. Check the name.",
            details={"name": name, "method": "ProjectManager.LoadProject", "result": bool(project)},
        )
    conn.wait_for_state(
        lambda state: state["project"] == name,
        description=f"project '{name}' to become current",
    )
    set_verification_status("verified")
    output(
        mutation_payload(
            action="project.open",
            target={"kind": "project", "name": name},
            verification_status="verified",
            message=f"Opened project: {name}",
        )
    )


@app.command()
@handle_errors
def save():
    """Save the current project."""
    enforce_mutation_policy(
        "project.settings_write",
        intended_engine="api_native",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        output(
            mutation_payload(
                action="project.save",
                target={"kind": "project", "scope": "current"},
                changed=False,
                runtime_save_called=False,
                message="DRY-RUN: Would save the current project.",
            )
        )
        return

    conn = get_connection(require_project=True)
    get_name = require_api_method(
        conn.project,
        "GetName",
        capability_id="project.settings_write",
        runtime_object="Project",
    )
    try:
        project_name = str(get_name() or "").strip()
    except CLIError:
        raise
    except Exception as exc:
        raise APICallFailed(
            "Failed to read the current DaVinci Resolve project before saving.",
            details={"method": "Project.GetName", "error_type": exc.__class__.__name__},
        ) from exc
    if not project_name:
        raise NoProjectOpen(details={"project_name": project_name, "save_method_called": False})
    get_timeline_count = getattr(conn.project, "GetTimelineCount", None)
    try:
        timeline_count = int(get_timeline_count() or 0) if callable(get_timeline_count) else None
    except Exception:
        timeline_count = None
    if looks_like_project_manager_placeholder(conn, project_name, timeline_count):
        raise NoProjectOpen(
            details={
                "project_name": project_name,
                "project_manager_placeholder": True,
                "save_method_called": False,
            }
        )
    save_fn = require_api_method(
        conn.project_manager,
        "SaveProject",
        capability_id="project.settings_write",
        runtime_object="ProjectManager",
    )
    try:
        result = save_fn()
    except CLIError:
        raise
    except Exception as exc:
        raise APICallFailed(
            "DaVinci Resolve failed to save the current project.",
            details={"method": "ProjectManager.SaveProject", "error_type": exc.__class__.__name__},
        ) from exc
    if not result:
        raise APICallFailed(
            "DaVinci Resolve returned False while saving the current project.",
            details={"method": "ProjectManager.SaveProject", "result": bool(result), "project_name": project_name},
            recoverability="manual",
        )
    set_verification_status("pending_manual")
    output(
        mutation_payload(
            action="project.save",
            target={"kind": "project", "name": project_name},
            verification_status="pending_manual",
            api_method="ProjectManager.SaveProject",
            api_result=True,
            message=f"Saved project: {project_name}",
        )
    )


@app.command()
@handle_errors
def close():
    """Close the current project without saving."""
    enforce_mutation_policy(
        "project.close",
        intended_engine="api_native",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        dry_run_message("Would close the current project without saving.")
        return

    conn = get_connection(require_project=True)
    get_name = require_api_method(
        conn.project,
        "GetName",
        capability_id="project.close",
        runtime_object="Project",
    )
    try:
        name = str(get_name() or "").strip()
    except CLIError:
        raise
    except Exception as exc:
        raise APICallFailed(
            "Failed to read the current DaVinci Resolve project before closing it.",
            details={"method": "Project.GetName", "error_type": exc.__class__.__name__},
        ) from exc
    if not name:
        raise NoProjectOpen(details={"project_name": name, "close_method_called": False})
    get_timeline_count = getattr(conn.project, "GetTimelineCount", None)
    try:
        timeline_count = int(get_timeline_count() or 0) if callable(get_timeline_count) else None
    except Exception:
        timeline_count = None
    if looks_like_project_manager_placeholder(conn, name, timeline_count):
        raise NoProjectOpen(
            details={
                "project_name": name,
                "project_manager_placeholder": True,
                "close_method_called": False,
            }
        )
    close_project = require_api_method(
        conn.project_manager,
        "CloseProject",
        capability_id="project.close",
        runtime_object="ProjectManager",
    )
    close_current_project_with_runtime_health(
        conn,
        project_name=name,
        current_database=try_current_database_details(conn),
        description=f"project '{name}' to stop being current",
        close_project=close_project,
    )
    set_verification_status("verified")
    output(
        mutation_payload(
            action="project.close",
            target={"kind": "project", "name": name},
            verification_status="verified",
            message=f"Closed project: {name}",
        )
    )


@app.command()
@handle_errors
def delete(
    name: str = typer.Argument(..., help="Project name"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
):
    """Delete a project."""
    enforce_mutation_policy(
        "project.delete",
        intended_engine="api_native",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        dry_run_message(f"Would delete project: {name}")
        return
    if not force:
        if is_machine_mode():
            raise ConfirmationRequired(
                "Machine-mode mutation requires --force.",
                details={"action": "project.delete", "target_kind": "project", "target_name": name},
            )
        confirm = typer.confirm(f"Delete project '{name}'? This cannot be undone.")
        if not confirm:
            raise typer.Abort()

    conn = get_connection(require_project=False)

    require_api_method(
        conn.project_manager,
        "GetProjectListInCurrentFolder",
        capability_id="project.delete",
        runtime_object="ProjectManager",
    )
    delete_project = require_api_method(
        conn.project_manager,
        "DeleteProject",
        capability_id="project.delete",
        runtime_object="ProjectManager",
    )
    existed_before = _read_project_exists_for_delete(conn, name)

    # DaVinci Resolve's DeleteProject API fails on the currently open project.
    # Close it first so the deletion can proceed.
    if _current_project_name_matches(conn, name):
        close_project = require_api_method(
            conn.project_manager,
            "CloseProject",
            capability_id="project.delete",
            runtime_object="ProjectManager",
        )
        close_current_project_with_runtime_health(
            conn,
            project_name=name,
            current_database=try_current_database_details(conn),
            description=f"project '{name}' to stop being current before deletion",
            close_project=close_project,
        )
        require_api_method(
            conn.project_manager,
            "GetProjectListInCurrentFolder",
            capability_id="project.delete",
            runtime_object="ProjectManager",
        )
        delete_project = require_api_method(
            conn.project_manager,
            "DeleteProject",
            capability_id="project.delete",
            runtime_object="ProjectManager",
        )

    try:
        result = delete_project(name)
    except APICallFailed:
        raise
    except Exception as exc:
        raise APICallFailed(
            "DaVinci Resolve failed while deleting the project.",
            details={
                "method": "ProjectManager.DeleteProject",
                "reason": "runtime_project_delete_exception",
                "project_name": name,
                "error_type": exc.__class__.__name__,
            },
        ) from exc

    if _wait_for_project_deleted(conn, name, existed_before=existed_before):
        set_verification_status("verified")
        payload = mutation_payload(
            action="project.delete",
            target={"kind": "project", "name": name},
            message=f"Deleted project: {name}",
            verification_status="verified",
        )
        output(payload)
    else:
        raise APICallFailed(
            f"Failed to delete project '{name}'.",
            details={
                "method": "ProjectManager.DeleteProject",
                "reason": "runtime_project_delete_stuck" if existed_before else "runtime_project_delete_missing",
                "project_name": name,
                "existed_before": existed_before,
                "api_result": bool(result),
            },
        )


@app.command("cleanup-scratch")
@handle_errors
def cleanup_scratch_projects(
    prefix: Optional[list[str]] = typer.Option(
        None,
        "--prefix",
        help="Scratch project name prefix to match; repeat for multiple. Defaults to known CutAgent scratch prefixes.",
    ),
    force: bool = typer.Option(False, "--force", "-f", help="Actually delete matched scratch projects. Without --force this command only previews."),
    include_current: bool = typer.Option(False, "--include-current", help="Allow deleting the currently open project if it matches a scratch prefix."),
    limit: int = typer.Option(25, "--limit", min=1, help="Maximum matched projects allowed before cleanup refuses to run."),
):
    """Safely preview or delete CutAgent scratch/test projects in the current folder."""
    prefixes = _normalize_scratch_prefixes(prefix)
    enforce_mutation_policy(
        "project.cleanup_scratch",
        intended_engine="api_native",
        mutating=bool(force) and not is_dry_run(),
    )
    conn = get_connection(require_project=False)
    current_name = _current_project_name(conn)
    project_names = _project_names_in_current_folder(conn)
    candidates, skipped = _scratch_cleanup_candidates(
        project_names,
        prefixes=prefixes,
        current_project=current_name,
        include_current=bool(include_current),
        limit=int(limit),
    )

    base_payload = {
        "action": "project.cleanup_scratch",
        "target": {"kind": "project_folder", "name": current_project_folder_name(conn)},
        "prefixes": prefixes,
        "current_project": current_name,
        "include_current": bool(include_current),
        "limit": int(limit),
        "candidate_count": len(candidates),
        "candidates": candidates,
        "skipped": skipped,
    }
    if is_dry_run() or not force:
        set_verification_status("not_requested")
        output(
            mutation_payload(
                changed=False,
                would_delete=[row["name"] for row in candidates],
                deleted_count=0,
                deleted=[],
                deletion_attempted=False,
                message=(
                    "DRY-RUN: Would delete matching CutAgent scratch projects."
                    if is_dry_run()
                    else "Preview only. Rerun with --force to delete matching CutAgent scratch projects."
                ),
                **base_payload,
            ),
            title="Project Scratch Cleanup Preview",
        )
        return

    deleted: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []
    if candidates:
        require_api_method(
            conn.project_manager,
            "DeleteProject",
            capability_id="project.cleanup_scratch",
            runtime_object="ProjectManager",
    )
    for row in candidates:
        name = str(row["name"])
        try:
            active_name = _current_project_name(conn)
            if active_name == name:
                if not include_current:
                    raise APICallFailed(
                        "Scratch cleanup will not delete a project that became current during cleanup.",
                        details={
                            "project_name": name,
                            "reason": "runtime_project_cleanup_candidate_became_current",
                        },
                        recoverability="manual",
                    )
                close_project = require_api_method(
                    conn.project_manager,
                    "CloseProject",
                    capability_id="project.cleanup_scratch",
                    runtime_object="ProjectManager",
                )
                close_current_project_with_runtime_health(
                    conn,
                    project_name=name,
                    current_database=try_current_database_details(conn),
                    description=f"project '{name}' to stop being current before scratch cleanup",
                    close_project=close_project,
                )
            existed_before = name in set(_project_names_in_current_folder(conn))
            delete_project = require_api_method(
                conn.project_manager,
                "DeleteProject",
                capability_id="project.cleanup_scratch",
                runtime_object="ProjectManager",
            )
            try:
                result = delete_project(name)
            except CLIError:
                raise
            except Exception as exc:
                raise APICallFailed(
                    "DaVinci Resolve failed while deleting a scratch project.",
                    details={
                        "method": "ProjectManager.DeleteProject",
                        "reason": "runtime_project_cleanup_delete_exception",
                        "project_name": name,
                        "error_type": exc.__class__.__name__,
                    },
                ) from exc
            if _wait_for_project_deleted(conn, name, existed_before=existed_before):
                deleted.append({**row, "api_result": bool(result)})
            else:
                failures.append(
                    {
                        **row,
                        "api_result": bool(result),
                        "error": "DeleteProject did not produce verified project absence.",
                    }
                )
        except Exception as exc:
            failures.append(
                {
                    **row,
                    "error": str(exc) if isinstance(exc, CLIError) else "Project scratch cleanup failed for this candidate.",
                    "error_type": exc.__class__.__name__,
                }
            )

    try:
        remaining_projects = _project_names_in_current_folder(conn)
    except CLIError as exc:
        raise APICallFailed(
            "Project scratch cleanup could not verify the final project list.",
            details={
                "reason": "runtime_project_cleanup_final_readback_failed",
                "deleted_candidates": deleted,
                "candidate_failures": failures,
                "readback_error": exc.details,
            },
            recoverability="manual",
        ) from exc
    still_present = [row["name"] for row in deleted if str(row["name"]) in set(remaining_projects)]
    if still_present:
        failures.extend(
            {
                "name": name,
                "error": "Project still listed after deletion readback.",
                "error_type": "VerificationFailed",
            }
            for name in still_present
        )

    payload = mutation_payload(
        changed=bool(deleted),
        deleted_count=len(deleted),
        deleted=deleted,
        failed_count=len(failures),
        failures=failures,
        remaining_matching=[name for name in remaining_projects if any(name.startswith(value) for value in prefixes)],
        deletion_attempted=True,
        message=f"Deleted {len(deleted)} CutAgent scratch project(s).",
        **base_payload,
    )
    if failures:
        set_verification_status("failed")
        raise APICallFailed(
            "Project scratch cleanup had deletion failures.",
            details=payload,
            recoverability="manual",
        )
    set_verification_status("verified")
    payload["verification_status"] = "verified"
    output(payload, title="Project Scratch Cleanup")


@app.command("info")
@handle_errors
def project_info():
    """Show current project information."""
    conn = get_connection(require_project=False)
    if not conn.project:
        output(
            {
                "project_open": False,
                "context": "project_manager",
                "name": None,
                "timeline_count": None,
                "settings_available": False,
                "message": "No project is open in DaVinci Resolve.",
            },
            title="Project Info",
        )
        return

    name = conn.project.GetName()
    data = {"name": name}

    # Timeline count
    timeline_count = None
    try:
        timeline_count = conn.project.GetTimelineCount() or 0
        data["timeline_count"] = timeline_count
    except Exception:
        pass

    current_folder = current_project_folder_name(conn)
    if looks_like_project_manager_placeholder(conn, name, timeline_count):
        output(
            {
                "project_open": False,
                "context": "project_manager",
                "name": name,
                "timeline_count": timeline_count,
                "current_folder": current_folder or "",
                "current_path": project_folder_path_label(current_folder),
                "settings_available": False,
                "message": "DaVinci Resolve is in Project Manager context; no real project is open.",
            },
            title="Project Info",
        )
        return

    data["project_open"] = True
    data["context"] = "project"
    data["project_id"] = _project_unique_id(conn.project)
    data["settings_available"] = False

    # Current timeline
    if conn.timeline:
        data["current_timeline"] = conn.timeline.GetName()
        data["fps"] = conn.fps

    # Settings
    try:
        settings = conn.project.GetSetting()
        if isinstance(settings, dict):
            for key in [
                "timelineResolutionWidth", "timelineResolutionHeight",
                "timelineFrameRate", "timelinePlaybackFrameRate",
                "videoCaptureCodec", "videoPlayoutCodec",
                "superScale", "audioCaptureNumChannels",
            ]:
                if key in settings:
                    data[key] = settings[key]
            data["settings_available"] = True
    except Exception:
        pass

    output(data, title="Project Info")


@app.command("settings-get")
@app.command()
@handle_errors
def settings(
    key: Optional[str] = typer.Argument(None, help="Setting key to get"),
):
    """Show project settings (all or specific key)."""
    enforce_mutation_policy("project.settings_read", intended_engine="api_native", mutating=False)
    conn = get_connection(require_project=True)

    all_settings = conn.project.GetSetting()
    if isinstance(all_settings, dict):
        if key:
            if key not in all_settings:
                raise ValidationError(
                    f"Unknown project setting key: {key}",
                    details={
                        "key": key,
                        "available_keys": sorted(str(setting_key) for setting_key in all_settings.keys()),
                    },
                )
            output({key: all_settings[key]})
        else:
            output(all_settings, title="Project Settings")
        return

    if key:
        val = conn.project.GetSetting(key)
        if val == "":
            raise ValidationError(
                f"Unknown project setting key: {key}",
                details={"key": key, "available_keys": []},
            )
        output({key: val})
    else:
        output({"settings": str(all_settings)})


@app.command("settings-set")
@handle_errors
def settings_set(
    key: str = typer.Argument(..., help="Setting key"),
    value: str = typer.Argument(..., help="Setting value"),
):
    """Set a project setting."""
    enforce_mutation_policy("project.settings_write", intended_engine="api_native", mutating=not is_dry_run())
    conn = get_connection(require_project=True)
    all_settings = conn.project.GetSetting()
    requested_value = value
    runtime_value, alias = _normalize_project_setting_value(key, value)
    current_value = None
    key_validated = False
    if isinstance(all_settings, dict):
        if key not in all_settings:
            raise ValidationError(
                f"Unknown project setting key: {key}",
                details={
                    "key": key,
                    "available_keys": sorted(str(setting_key) for setting_key in all_settings.keys()),
                },
            )
        current_value = all_settings[key]
        key_validated = True

    if key == "colorSpaceTimeline" and runtime_value in _COMBINED_TIMELINE_COLOR_SPACES:
        separate_mode = str(_read_project_setting(conn.project, "separateColorSpaceAndGamma", all_settings) or "")
        if separate_mode == "1":
            raise ValidationError(
                "DaVinci Resolve expects DaVinci Wide Gamut Intermediate as a combined timeline color-space value.",
                suggested_fix=(
                    "Run `project settings-set separateColorSpaceAndGamma 0`, then "
                    "`project settings-set colorSpaceTimeline 'DaVinci Wide Gamut Intermediate'`."
                ),
                details={
                    "key": key,
                    "requested_value": requested_value,
                    "normalized_value": runtime_value,
                    "separateColorSpaceAndGamma": separate_mode,
                },
            )

    if is_dry_run():
        output(
            mutation_payload(
                action="project.settings_set",
                target={"kind": "project_setting", "name": key},
                changed=not _project_setting_values_match(current_value, runtime_value) if key_validated else True,
                previous_value=current_value,
                value=runtime_value,
                requested_value=requested_value,
                normalized_value=runtime_value,
                alias_applied=alias,
                key_validated=key_validated,
                runtime_write_called=False,
                value_validation="runtime_only",
                message=f"DRY-RUN: Would set {key} = {runtime_value}",
            )
        )
        return

    if key_validated and _project_setting_values_match(current_value, runtime_value):
        set_verification_status("verified")
        output(
            mutation_payload(
                action="project.settings_set",
                target={"kind": "project_setting", "name": key},
                changed=False,
                previous_value=current_value,
                value=runtime_value,
                requested_value=requested_value,
                normalized_value=runtime_value,
                alias_applied=alias,
                key_validated=True,
                runtime_write_called=False,
                readback_value=current_value,
                verified=True,
                message=f"Project setting already has requested value: {key} = {runtime_value}",
            )
        )
        return

    result = conn.project.SetSetting(key, runtime_value)
    if result:
        readback_value = _read_project_setting(conn.project, key)
        if not _project_setting_values_match(readback_value, runtime_value):
            raise APICallFailed(
                f"Project setting write did not verify by readback: {key}",
                details={
                    "key": key,
                    "requested_value": requested_value,
                    "normalized_value": runtime_value,
                    "previous_value": current_value,
                    "readback_value": readback_value,
                    "alias_applied": alias,
                    "api_result": result,
                },
            )
        set_verification_status("verified")
        output(
            mutation_payload(
                action="project.settings_set",
                target={"kind": "project_setting", "name": key},
                previous_value=current_value,
                value=runtime_value,
                requested_value=requested_value,
                normalized_value=runtime_value,
                alias_applied=alias,
                key_validated=key_validated,
                runtime_write_called=True,
                readback_value=readback_value,
                verified=True,
                message=f"Set {key} = {runtime_value}",
            )
        )
    else:
        raise APICallFailed(
            f"Failed to set {key}. The key may be read-only or invalid.",
            details={
                "key": key,
                "requested_value": requested_value,
                "normalized_value": runtime_value,
                "previous_value": current_value,
                "alias_applied": alias,
            },
        )


# --- Project Presets ---

from ..core import project_preset_api
from ..core.project_preset_api import SAVE_METHODS

preset_app = typer.Typer(help="Project preset operations.")
app.add_typer(preset_app, name="preset")


@preset_app.command("list")
@handle_errors
def preset_list():
    """List project presets."""
    conn = get_connection(require_project=True)
    rows = [
        {"index": index, "name": name}
        for index, name in enumerate(
            project_preset_api.project_preset_names_ordered(conn.project), 1
        )
    ]
    output(rows, columns=[("index", "#"), ("name", "Name")], title="Project Presets")


@preset_app.command("load")
@handle_errors
def preset_load(
    name: str = typer.Argument(..., help="Preset name"),
):
    """Load project preset by name."""
    project_preset_api.requested_project_preset_name(name)
    enforce_mutation_policy("project.preset_load", intended_engine="api_native", mutating=not is_dry_run())
    conn = get_connection(require_project=True)
    preset_names = project_preset_api.project_preset_names_ordered(conn.project)
    if is_dry_run():
        output(
            mutation_payload(
                action="project.preset.load",
                target={"kind": "project_preset", "name": name},
                changed=False,
                preset_exists=name in preset_names,
                available_presets=preset_names,
                runtime_load_called=False,
                message=f"DRY-RUN: Would load project preset: {name}",
            )
        )
        return

    output(project_preset_api.load_project_preset(conn.project, name), title="Project Preset Load")
