"""Shared DaVinci Resolve state predicates used across command and workflow layers."""

from __future__ import annotations

from typing import Any


def current_project_folder_name(conn: Any) -> str | None:
    project_manager = getattr(conn, "project_manager", None)
    get_current_folder = getattr(project_manager, "GetCurrentFolder", None)
    if not callable(get_current_folder):
        return None
    try:
        current = get_current_folder()
    except Exception:
        return None
    if current is None:
        return None
    return str(current)


def project_folder_path_label(current_folder: str | None) -> str:
    if current_folder:
        return f"Projects / {current_folder}"
    return "Projects"


def current_resolve_page(conn: Any) -> str | None:
    resolve = getattr(conn, "resolve", None)
    get_current_page = getattr(resolve, "GetCurrentPage", None)
    if not callable(get_current_page):
        return None
    try:
        page = get_current_page()
    except Exception:
        return None
    text = str(page or "").strip()
    return text or None


def _canonical_page_name(page: str | None) -> str:
    return str(page or "").replace("_", "").replace("-", "").lower()


def looks_like_project_manager_placeholder(
    conn: Any,
    project_name: str | None,
    timeline_count: int | None,
) -> bool:
    if project_name != "Untitled Project":
        return False
    if timeline_count not in (0, None):
        return False
    if getattr(conn, "timeline", None) is not None:
        return False
    page = current_resolve_page(conn)
    current_folder = current_project_folder_name(conn)
    if page is None or _canonical_page_name(page) == "projectmanager":
        return current_folder is not None

    # DaVinci Resolve Free's embedded transport can retain the last workspace
    # page after CloseProject while exposing an unsaved placeholder project.
    # A real saved project with the same name remains listed in this folder.
    project_manager = getattr(conn, "project_manager", None)
    list_projects = getattr(project_manager, "GetProjectListInCurrentFolder", None)
    if callable(list_projects):
        try:
            projects = list_projects() or []
            return project_name not in projects
        except Exception:
            pass
    return False


def project_is_closed_enough(state: dict[str, Any], *, original_project_name: str) -> bool:
    """Return True when the original project is no longer the active session.

    DaVinci Resolve may leave no project open after CloseProject, or it may auto-open a
    placeholder project such as "Untitled Project". Both outcomes are safe for
    operations that only require the original project to stop being current.
    """

    current_project = state.get("project")
    current_timeline = state.get("timeline")

    if current_project == original_project_name:
        return False

    if current_timeline is None:
        return True

    return isinstance(current_project, str) and bool(current_project.strip())
