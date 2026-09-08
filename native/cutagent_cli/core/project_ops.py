"""Project manager operations not tied to command parsing."""

from __future__ import annotations

from typing import Any, Optional

from ..errors import APICallFailed, CLIError, CapabilityNegotiationFailed, ValidationError
from ..state_contracts import looks_like_project_manager_placeholder


def _require_project_manager(conn):
    manager = getattr(conn, "project_manager", None)
    if manager is None:
        raise APICallFailed("Project manager is not available.")
    return manager


def _refresh(conn) -> None:
    refresh = getattr(conn, "refresh", None)
    if callable(refresh):
        try:
            refresh()
        except Exception:
            pass


def validate_project_name(name: str) -> None:
    """Reject names that cannot identify a persisted DaVinci Resolve project."""
    if not str(name or "").strip():
        raise ValidationError("Project name is required.", details={"name": name})
    if any(ord(char) < 32 or ord(char) == 127 for char in name):
        raise ValidationError(
            "Project name cannot contain control characters.",
            details={"name": name},
        )


def save_current_project_if_available(conn) -> bool:
    """Save the active project through the runtime object that exposes SaveProject."""
    candidates = (
        getattr(conn, "project_manager", None),
        getattr(conn, "project", None),
    )
    for target in candidates:
        save_project = getattr(target, "SaveProject", None)
        if not callable(save_project):
            continue
        try:
            return bool(save_project())
        except Exception as exc:
            raise APICallFailed(
                "DaVinci Resolve failed to save the current project.",
                details={"runtime_object": type(target).__name__, "error": str(exc)},
                recoverability="manual",
            ) from exc
    return False


def create_project(conn, name: str, media_location_path: Optional[str] = None) -> dict[str, Any]:
    """Create and open a project, optionally passing DaVinci Resolve's mediaLocationPath."""
    validate_project_name(name)
    if media_location_path is not None:
        if not media_location_path.strip():
            raise ValidationError(
                "Project media location path cannot be empty.",
                details={"media_location_path": media_location_path},
            )
        if any(ord(char) < 32 or ord(char) == 127 for char in media_location_path):
            raise ValidationError(
                "Project media location path cannot contain control characters.",
                details={"media_location_path": media_location_path},
            )

    manager = _require_project_manager(conn)
    creator = getattr(manager, "CreateProject", None)
    if not callable(creator):
        raise CapabilityNegotiationFailed(
            "Project creation is not available through this DaVinci Resolve scripting API.",
            details={"capability_id": "project.create", "required_method": "ProjectManager.CreateProject"},
        )

    try:
        if media_location_path is not None:
            project = creator(name, media_location_path)
        else:
            project = creator(name)
    except CLIError:
        raise
    except TypeError as exc:
        if media_location_path is not None:
            raise CapabilityNegotiationFailed(
                "This DaVinci Resolve scripting API does not accept mediaLocationPath for ProjectManager.CreateProject.",
                details={
                    "capability_id": "project.create",
                    "required_method": "ProjectManager.CreateProject(projectName, mediaLocationPath)",
                    "name": name,
                    "media_location_path": media_location_path,
                },
            ) from exc
        raise APICallFailed(
            "DaVinci Resolve failed to create the project.",
            details={"name": name, "media_location_path": None, "error_type": "TypeError"},
        ) from exc
    except Exception as exc:
        raise APICallFailed(
            "DaVinci Resolve failed to create the project.",
            details={
                "name": name,
                "media_location_path": media_location_path,
                "error_type": exc.__class__.__name__,
            },
        ) from exc

    used_gui = False
    if not project and media_location_path is None:
        gui_creator = getattr(conn, "create_project_in_gui", None)
        if callable(gui_creator):
            gui_creator(name=name)
            waiter = getattr(conn, "wait_for_state", None)
            if callable(waiter):
                waiter(
                    lambda state: state["project"] == name,
                    description=f"project '{name}' to open after Project Manager creation",
                    attempts=30,
                    delay=0.2,
                )
            else:
                _refresh(conn)
            current = getattr(conn, "project", None)
            get_name = getattr(current, "GetName", None)
            project = current if callable(get_name) and str(get_name() or "").strip() == name else None
            used_gui = project is not None
    if not project:
        raise APICallFailed(
            f"Failed to create project '{name}'. It may already exist.",
            details={"name": name, "media_location_path": media_location_path},
        )

    waiter = getattr(conn, "wait_for_state", None)
    if callable(waiter):
        waiter(lambda state: state["project"] == name, description=f"project '{name}' to open after creation")
    else:
        _refresh(conn)
    return {"name": name, "media_location_path": media_location_path, "created": True, "used_gui": used_gui}


def rename_current_project(conn, new_name: str) -> dict[str, Any]:
    """Rename the current project using the best native API exposed by DaVinci Resolve."""
    validate_project_name(new_name)

    project = getattr(conn, "project", None)
    manager = _require_project_manager(conn)
    if project is None:
        raise APICallFailed("No active project to rename.")

    get_name = getattr(project, "GetName", None)
    if not callable(get_name):
        raise CapabilityNegotiationFailed(
            "Project rename cannot read the active DaVinci Resolve project name.",
            details={
                "capability_id": "project.settings_write",
                "required_method": "Project.GetName",
                "runtime_object": "Project",
            },
        )
    try:
        old_name = get_name()
    except CLIError:
        raise
    except Exception as exc:
        raise APICallFailed(
            "DaVinci Resolve failed to read the active project before renaming it.",
            details={"method": "Project.GetName", "error_type": exc.__class__.__name__},
        ) from exc
    if not old_name:
        raise APICallFailed("Could not determine current project name.")

    get_timeline_count = getattr(project, "GetTimelineCount", None)
    timeline_count = None
    if callable(get_timeline_count):
        try:
            timeline_count = int(get_timeline_count())
        except Exception:
            timeline_count = None
    if looks_like_project_manager_placeholder(conn, str(old_name), timeline_count):
        raise APICallFailed(
            "No active project to rename.",
            details={"project_name": old_name, "project_manager_placeholder": True},
        )

    if old_name == new_name:
        return {"old_name": old_name, "new_name": new_name, "renamed": False}

    attempted_methods: list[str] = []
    for target, method_names, args in (
        (project, ("SetName", "Rename"), (new_name,)),
        (manager, ("RenameProject",), (old_name, new_name)),
    ):
        for method_name in method_names:
            method = getattr(target, method_name, None)
            if not callable(method):
                continue
            attempted_methods.append(method_name)
            try:
                result = method(*args)
            except CLIError:
                raise
            except Exception as exc:
                raise APICallFailed(
                    "DaVinci Resolve failed to rename the project.",
                    details={
                        "old_name": old_name,
                        "new_name": new_name,
                        "method": method_name,
                        "error_type": exc.__class__.__name__,
                    },
                ) from exc
            if result is False:
                continue
            waiter = getattr(conn, "wait_for_state", None)
            if callable(waiter):
                waiter(
                    lambda state: state["project"] == new_name,
                    description=f"project '{new_name}' after rename",
                )
            else:
                _refresh(conn)
                refreshed_project = getattr(conn, "project", project)
                readback = refreshed_project.GetName() if hasattr(refreshed_project, "GetName") else None
                if readback != new_name:
                    raise APICallFailed(
                        "Project rename did not match DaVinci Resolve readback.",
                        details={
                            "old_name": old_name,
                            "new_name": new_name,
                            "actual_name": readback,
                            "method": method_name,
                        },
                    )
            return {"old_name": old_name, "new_name": new_name, "renamed": True, "method": method_name}

    if attempted_methods:
        raise APICallFailed(
            "DaVinci Resolve rejected the project rename.",
            details={
                "old_name": old_name,
                "new_name": new_name,
                "attempted_methods": attempted_methods,
            },
        )

    raise CapabilityNegotiationFailed(
        "Project rename is not available through this DaVinci Resolve scripting API.",
        details={
            "capability_id": "project.settings_write",
            "required_method": [
                "Project.SetName",
                "Project.Rename",
                "ProjectManager.RenameProject",
            ],
            "old_name": old_name,
            "new_name": new_name,
        },
    )


def goto_project_folder_root(conn) -> dict[str, Any]:
    """Navigate the project database browser to the root folder."""
    manager = _require_project_manager(conn)
    root_method = getattr(manager, "GotoRootFolder", None)
    if callable(root_method):
        result = root_method()
        if result is False:
            raise APICallFailed("Failed to navigate to the project folder root.")
        return {"folder": "root", "method": "GotoRootFolder"}

    parent = getattr(manager, "GotoParentFolder", None)
    if not callable(parent):
        raise CapabilityNegotiationFailed(
            "Project folder root navigation is not available.",
            details={"capability_id": "project.folder_management", "required_method": "ProjectManager.GotoRootFolder"},
        )

    steps = 0
    for _ in range(128):
        result = parent()
        if not result:
            break
        steps += 1
    return {"folder": "root", "method": "GotoParentFolder", "steps": steps}


def delete_project_folder(conn, name: str) -> dict[str, Any]:
    """Delete a project database folder in the current folder."""
    if not str(name or "").strip():
        raise ValidationError("Folder name is required.", details={"name": name})
    manager = _require_project_manager(conn)
    deleter = getattr(manager, "DeleteFolder", None)
    if not callable(deleter):
        raise CapabilityNegotiationFailed(
            "Project folder deletion is not available.",
            details={"capability_id": "project.folder_management", "required_method": "ProjectManager.DeleteFolder"},
        )
    result = deleter(name)
    if result is False:
        raise APICallFailed("Failed to delete project folder.", details={"name": name})
    return {"name": name, "deleted": bool(result)}


def _resolve_constant(conn, name: str, fallback: str) -> Any:
    resolve = getattr(conn, "resolve", None)
    return getattr(resolve, name, fallback)


def _cloud_sync_mode(conn, sync_mode: Optional[str]) -> Any:
    if not sync_mode:
        return None
    normalized = str(sync_mode).strip().lower().replace("-", "_")
    mapping = {
        "none": "CLOUD_SYNC_NONE",
        "proxy": "CLOUD_SYNC_PROXY_ONLY",
        "proxy_only": "CLOUD_SYNC_PROXY_ONLY",
        "proxy_and_orig": "CLOUD_SYNC_PROXY_AND_ORIG",
        "proxy_and_original": "CLOUD_SYNC_PROXY_AND_ORIG",
        "original": "CLOUD_SYNC_PROXY_AND_ORIG",
    }
    constant_name = mapping.get(normalized)
    if constant_name:
        return _resolve_constant(conn, constant_name, normalized)
    return sync_mode


def _cloud_settings(
    conn,
    *,
    project_name: Optional[str] = None,
    media_path: Optional[str] = None,
    sync_mode: Optional[str] = None,
    collab: bool = False,
) -> dict[Any, Any]:
    settings: dict[Any, Any] = {}
    if project_name:
        settings[_resolve_constant(conn, "CLOUD_SETTING_PROJECT_NAME", "projectName")] = project_name
    if media_path:
        settings[_resolve_constant(conn, "CLOUD_SETTING_PROJECT_MEDIA_PATH", "projectMediaPath")] = media_path
    resolved_sync_mode = _cloud_sync_mode(conn, sync_mode)
    if resolved_sync_mode is not None:
        settings[_resolve_constant(conn, "CLOUD_SETTING_SYNC_MODE", "syncMode")] = resolved_sync_mode
    if collab:
        settings[_resolve_constant(conn, "CLOUD_SETTING_IS_COLLAB", "isCollab")] = True
    return settings


def _cloud_auth_warning() -> dict[str, Any]:
    return {
        "requires_cloud_account": True,
        "warning": "Blackmagic Cloud project operations can open DaVinci Resolve's Cloud login UI and require an authenticated Blackmagic Cloud account.",
        "required_manual_step": "Sign in to Blackmagic Cloud in DaVinci Resolve before relying on this command for unattended automation.",
    }


def _call_cloud_method(conn, action: str, method_names: tuple[str, ...], *args: Any) -> dict[str, Any]:
    manager = _require_project_manager(conn)
    attempted: list[str] = []
    for method_name in method_names:
        method = getattr(manager, method_name, None)
        if not callable(method):
            continue
        attempted.append(method_name)
        try:
            result = method(*args)
        except TypeError:
            continue
        if result is False or result is None:
            continue
        _refresh(conn)
        settings = args[-1] if args and isinstance(args[-1], dict) else {}
        return {"action": action, "method": method_name, "result": True, "settings": settings, **_cloud_auth_warning()}

    raise CapabilityNegotiationFailed(
        "Cloud project operation is not available through this DaVinci Resolve scripting API.",
        details={
            "capability_id": f"project.cloud.{action}",
            "required_method": list(method_names),
            "attempted_methods": attempted,
            "args": list(args),
            **_cloud_auth_warning(),
        },
    )


def create_cloud_project(conn, name: str, media_path: Optional[str], sync_mode: Optional[str], collab: bool) -> dict[str, Any]:
    """Create a cloud project when DaVinci Resolve exposes the cloud project API."""
    return _call_cloud_method(
        conn,
        "create",
        ("CreateCloudProject", "CreateProjectInCloud"),
        _cloud_settings(conn, project_name=name, media_path=media_path, sync_mode=sync_mode, collab=collab),
    )


def open_cloud_project(conn, name: str, media_path: Optional[str], sync_mode: Optional[str]) -> dict[str, Any]:
    """Open a cloud project when DaVinci Resolve exposes the cloud project API."""
    return _call_cloud_method(
        conn,
        "open",
        ("LoadCloudProject", "OpenCloudProject"),
        _cloud_settings(conn, project_name=name, media_path=media_path, sync_mode=sync_mode),
    )


def import_cloud_project(conn, file_path: str, name: Optional[str], media_path: Optional[str]) -> dict[str, Any]:
    """Import a cloud project archive when DaVinci Resolve exposes the cloud import API."""
    return _call_cloud_method(
        conn,
        "import",
        ("ImportCloudProject", "ImportProjectToCloud"),
        file_path,
        _cloud_settings(conn, project_name=name, media_path=media_path),
    )


def restore_cloud_project(conn, folder: str, name: Optional[str], media_path: Optional[str]) -> dict[str, Any]:
    """Restore a cloud project folder when DaVinci Resolve exposes the cloud restore API."""
    return _call_cloud_method(
        conn,
        "restore",
        ("RestoreCloudProject", "RestoreProjectToCloud"),
        folder,
        _cloud_settings(conn, project_name=name, media_path=media_path),
    )
