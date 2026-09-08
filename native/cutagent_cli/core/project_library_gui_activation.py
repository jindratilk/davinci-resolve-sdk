"""Workflow-owned Project Manager activation for an exact DaVinci Resolve GUI process."""

from __future__ import annotations

import ipaddress
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from functools import partial
from typing import Any

from ..errors import APICallFailed, GuiPermissionMissing, ReadinessFailed, ValidationError
from .owned_resolve_lifecycle import (
    _assert_context,
    _environment_value_matches,
    _process_environment,
    _process_identity,
)


_PROJECT_MANAGER_REFRESH_SECONDS = 2.0


def _failure(reason: str, message: str, **details: Any) -> ValidationError:
    return ValidationError(
        message,
        details={
            "reason": reason,
            "required_capability": "exact_project_manager_library_connect",
            **details,
        },
        recoverability="manual",
    )


def _assert_proxy_uuid(resolve: Any, instance_uuid: str) -> None:
    from .. import adapters

    adapters._assert_targeted_proxy_identity(resolve, instance_uuid)


def _resolve_gui_pids(binary: str) -> list[int]:
    try:
        # macOS pgrep accepts POSIX ERE, not Python/PCRE non-capturing groups.
        process_pattern = rf"^{re.escape(binary)}( -psn_[0-9_]+)?$"
        completed = subprocess.run(
            ["/usr/bin/pgrep", "-f", process_pattern],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="strict",
            timeout=2.0,
            check=False,
        )
    except (OSError, subprocess.SubprocessError, UnicodeError):
        raise _failure(
            "gui_process_inventory_unavailable",
            "The DaVinci Resolve GUI process inventory is unavailable.",
        ) from None
    if completed.returncode not in (0, 1):
        raise _failure(
            "gui_process_inventory_unavailable",
            "The DaVinci Resolve GUI process inventory is unavailable.",
        )
    pids: list[int] = []
    for raw in completed.stdout.splitlines():
        try:
            pid = int(raw.strip())
        except ValueError:
            raise _failure(
                "gui_process_inventory_invalid",
                "The DaVinci Resolve GUI process inventory is malformed.",
            ) from None
        if pid <= 1:
            raise _failure(
                "gui_process_inventory_invalid",
                "The DaVinci Resolve GUI process inventory is unsafe.",
            )
        uid, executable, arguments = _process_identity(pid)
        try:
            executable_matches = Path(executable).resolve(strict=True) == Path(binary).resolve(strict=True)
        except OSError:
            executable_matches = False
        launch_services_argument = re.fullmatch(rf"{re.escape(executable)} -psn_[0-9]+_[0-9]+", arguments)
        if uid == os.getuid() and executable_matches and (arguments == executable or launch_services_argument):
            pids.append(pid)
    return sorted(set(pids))


def _assert_gui_worker_binding(target_pid: int, instance_uuid: str) -> None:
    """Bind the native proxy, GUI process, and isolated worker environment."""

    from .. import adapters

    home_raw = os.environ.get("HOME", "").strip()
    account_home = adapters._account_home()
    if not home_raw or not account_home:
        raise _failure(
            "gui_process_binding_unavailable",
            "Project Manager activation requires authoritative worker process provenance.",
        )
    home = os.path.realpath(home_raw)
    if home == account_home:
        # A normal account GUI has no secure UUID-to-PID identity record. Keep
        # mutation unavailable until the owning launcher can supply one.
        raise _failure(
            "gui_process_binding_unavailable",
            "Project Manager activation cannot prove the normal account GUI process identity.",
            target_pid=target_pid,
        )
    identity = adapters._read_worker_identity(home)
    if identity.get("uuid", "").casefold() != instance_uuid or identity.get("pid") != str(target_pid):
        raise _failure(
            "gui_process_identity_mismatch",
            "The explicit GUI PID and SDK instance UUID do not identify the same worker.",
            target_pid=target_pid,
        )
    process_environment = _process_environment(target_pid)
    for name in ("HOME", "CFFIXED_USER_HOME", "TMPDIR"):
        expected = os.environ.get(name, "").strip()
        if not expected or not _environment_value_matches(process_environment, name, expected):
            raise _failure(
                "gui_process_environment_mismatch",
                "The explicit GUI process does not use the selected isolated worker environment.",
                target_pid=target_pid,
                environment=name,
            )


class MacOSProjectLibraryGuiDriver:
    """Accessibility driver scoped only to Project Manager library connection."""

    def preflight_permissions(self, pid: int) -> dict[str, Any]:
        from .macos_project_library_accessibility import inspect_accessibility

        try:
            return inspect_accessibility(pid)
        except PermissionError as exc:
            raise GuiPermissionMissing(
                "Enable macOS Accessibility for the process running CutAgent CLI.",
                details={"missing": ["Accessibility"], "target_pid": pid},
            ) from exc
        except Exception as exc:
            raise ReadinessFailed(
                "The exact DaVinci Resolve GUI process is not ready for Project Manager accessibility.",
                details={"route": "project.library_connect_gui", "error": str(exc)},
            ) from exc

    def connect_library(self, pid: int, *, name: str, root: Path) -> dict[str, Any]:
        from .macos_project_library_accessibility import connect_project_library

        try:
            return connect_project_library(pid, name=name, root=root)
        except PermissionError as exc:
            raise GuiPermissionMissing(
                "Enable macOS Accessibility for the process running CutAgent CLI.",
                details={"missing": ["Accessibility"], "target_pid": pid},
            ) from exc
        except Exception as exc:
            raise ReadinessFailed(
                "The Project Manager accessibility route failed closed.",
                details={"route": "project.library_connect_gui", "target_pid": pid, "error": str(exc)},
            ) from exc

    def prepare_project_manager(self, pid: int) -> dict[str, Any]:
        from .macos_project_library_accessibility import show_project_manager

        try:
            return show_project_manager(pid)
        except PermissionError as exc:
            raise GuiPermissionMissing(
                "Enable macOS Accessibility for the process running CutAgent CLI.",
                details={"missing": ["Accessibility"], "target_pid": pid},
            ) from exc
        except Exception as exc:
            raise ReadinessFailed(
                "The exact owned Project Manager window could not be prepared.",
                details={"route": "project.library_connect_gui", "target_pid": pid, "error": str(exc)},
            ) from exc

    def create_project(self, pid: int, *, name: str) -> dict[str, Any]:
        from .macos_project_library_accessibility import create_project_via_project_manager

        try:
            return create_project_via_project_manager(pid, name=name)
        except PermissionError as exc:
            raise GuiPermissionMissing(
                "Enable macOS Accessibility for the process running CutAgent CLI.",
                details={"missing": ["Accessibility"], "target_pid": pid},
            ) from exc
        except Exception as exc:
            raise ReadinessFailed(
                "The exact owned Project Manager could not create the bootstrap project.",
                details={"route": "project.create", "target_pid": pid, "error": str(exc)},
            ) from exc


def _gui_custody(conn: Any, driver: MacOSProjectLibraryGuiDriver) -> tuple[int, str]:
    from .. import adapters
    from .launch_ops import resolve_binary_path

    if sys.platform != "darwin" or getattr(conn, "transport", None) != adapters.ResolveTransport.STUDIO_EXTERNAL:
        raise _failure("gui_activation_transport_unsupported", "Project Manager activation requires macOS Studio external scripting.")
    target = adapters._resolve_instance_target()
    if target is None:
        raise _failure("gui_instance_target_required", "Project Manager activation requires an exact SDK instance UUID.")
    host, instance_uuid = target
    try:
        if not ipaddress.ip_address(host).is_loopback:
            raise ValueError
    except ValueError:
        raise _failure(
            "gui_instance_must_be_local",
            "Project Manager activation cannot target a remote DaVinci Resolve instance.",
        ) from None
    _assert_proxy_uuid(getattr(conn, "resolve", None), instance_uuid)
    binary = str(Path(resolve_binary_path()).resolve(strict=True))
    target_pid = adapters._resolve_instance_pid()
    if target_pid is None:
        raise _failure(
            "gui_process_target_required",
            "Project Manager activation requires an explicit local DaVinci Resolve GUI process PID.",
        )
    pids = _resolve_gui_pids(binary)
    if target_pid not in pids:
        raise _failure(
            "gui_process_identity_mismatch",
            "The explicit process PID is not the selected non-headless DaVinci Resolve GUI instance.",
            target_pid=target_pid,
            matching_gui_pids=pids,
        )
    _assert_gui_worker_binding(target_pid, instance_uuid)
    driver.preflight_permissions(target_pid)
    return target_pid, instance_uuid


def configure_project_library_gui_activation(conn: Any, *, driver: MacOSProjectLibraryGuiDriver | None = None) -> bool:
    conn.__dict__.pop("activate_project_library_registration", None)
    conn.__dict__.pop("create_project_in_gui", None)
    active_driver = driver or MacOSProjectLibraryGuiDriver()
    try:
        _gui_custody(conn, active_driver)
    except Exception:
        return False
    conn.activate_project_library_registration = partial(
        activate_project_library_registration,
        conn,
        driver=active_driver,
    )
    conn.create_project_in_gui = partial(create_project_in_gui, conn, driver=active_driver)
    return True


def create_project_in_gui(
    conn: Any,
    *,
    name: str,
    driver: MacOSProjectLibraryGuiDriver | None = None,
) -> dict[str, Any]:
    active_driver = driver or MacOSProjectLibraryGuiDriver()
    pid, instance_uuid = _gui_custody(conn, active_driver)
    result = active_driver.create_project(pid, name=name)
    _assert_proxy_uuid(getattr(conn, "resolve", None), instance_uuid)
    return result


def _database_matches(row: Any, *, name: str) -> bool:
    return isinstance(row, dict) and row.get("DbType") == "Disk" and row.get("DbName") == name


def activate_project_library_registration(
    conn: Any,
    *,
    name: str,
    context: dict[str, Any],
    driver: MacOSProjectLibraryGuiDriver | None = None,
) -> None:
    from . import project_library_ops

    if not isinstance(name, str) or not name.strip() or not isinstance(context, dict):
        raise _failure("gui_activation_input_invalid", "Project Manager activation input is invalid.")
    active_driver = driver or MacOSProjectLibraryGuiDriver()
    pid, instance_uuid = _gui_custody(conn, active_driver)
    _assert_context(conn, context)
    _registry_path, _raw, rows = project_library_ops._registry_state()
    root, _row, _catalog_identity = project_library_ops._registered_library(name.strip(), rows)
    manager = getattr(conn, "project_manager", None)
    prepare = getattr(active_driver, "prepare_project_manager", None)
    if callable(prepare):
        prepare(pid)
    project = manager.GetCurrentProject() if manager is not None else None
    close = getattr(manager, "CloseProject", None)
    if project is not None and (not callable(close) or not bool(close(project))):
        raise APICallFailed(
            "DaVinci Resolve could not close the protected project for Project Manager activation.",
            details={"reason": "gui_project_close_failed", "project_name": context.get("project_name")},
            recoverability="manual",
        )
    try:
        deadline = time.monotonic() + _PROJECT_MANAGER_REFRESH_SECONDS
        while time.monotonic() < deadline:
            current_rows = manager.GetDatabaseList()
            matches = [row for row in current_rows or [] if _database_matches(row, name=name.strip())]
            if len(matches) == 1:
                break
            time.sleep(0.1)
        else:
            active_driver.connect_library(pid, name=name.strip(), root=root)
        deadline = time.monotonic() + 5.0
        matches: list[dict[str, Any]] = []
        current_rows: Any = None
        while time.monotonic() < deadline:
            current_rows = manager.GetDatabaseList()
            matches = [row for row in current_rows or [] if _database_matches(row, name=name.strip())]
            if isinstance(current_rows, list) and len(matches) == 1:
                break
            time.sleep(0.1)
        else:
            raise APICallFailed(
                "Project Manager did not enumerate the registered project library exactly once.",
                details={"reason": "gui_library_activation_unverified", "name": name.strip(), "match_count": len(matches)},
                recoverability="manual",
            )
        _assert_proxy_uuid(getattr(conn, "resolve", None), instance_uuid)
        _post_registry_path, _post_raw, post_rows = project_library_ops._registry_state()
        registered = [row for row in post_rows if row["name"] == name.strip()]
        if (
            len(registered) != 1
            or not project_library_ops._registry_roots_equal(registered[0]["root"], root)
        ):
            raise APICallFailed(
                "Project Manager changed the durable library registration ambiguously.",
                details={
                    "reason": "gui_library_registry_ambiguous",
                    "name": name.strip(),
                    "registration_count": len(registered),
                },
                recoverability="manual",
            )
    except BaseException:
        try:
            project_library_ops._restore_context(conn, context)
        except Exception:
            pass
        raise
    else:
        project_library_ops._restore_context(conn, context)
