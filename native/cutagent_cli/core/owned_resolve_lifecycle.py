"""Exact lifecycle support for CutAgent-owned headless DaVinci Resolve workers.

DaVinci Resolve snapshots its Disk project-library registry at process start.
This module may rotate one UUID-pinned, isolated, headless worker only after
proving the worker home, identity file, process, command, and live project
context.  Ordinary GUI sessions and unpinned processes remain unsupported.
"""

from __future__ import annotations

import ipaddress
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from functools import partial
from typing import Any
from uuid import UUID, uuid4

from ..errors import APICallFailed, ValidationError


_STATE_FILE = ".cutagent-owned-resolve-lifecycle.json"
_LOG_DIRECTORY = ".cutagent-owned-resolve-lifecycle"
_IDENTITY_FILE = "cutagent-worker-identity.txt"
_SCHEMA_VERSION = 1
_MAX_STATE_BYTES = 32 * 1024
_MAX_LINEAGE = 32
_EXIT_TIMEOUT_SECONDS = 30.0
_START_TIMEOUT_SECONDS = 90.0
_LAUNCH_ENV_ALLOWLIST = frozenset({
    "CFFIXED_USER_HOME", "HOME", "LANG", "LC_ALL", "LOGNAME", "PATH", "SHELL", "TMPDIR", "USER",
})


def _failure(reason: str, message: str, **details: Any) -> ValidationError:
    return ValidationError(
        message,
        details={"reason": reason, "required_capability": "owned_process_restart_and_verified_reattachment", **details},
        recoverability="manual",
    )


def _canonical_uuid(value: Any, *, reason: str) -> str:
    try:
        canonical = str(UUID(str(value)))
    except (AttributeError, TypeError, ValueError):
        raise _failure(reason, "The owned DaVinci Resolve worker identity is invalid.") from None
    if str(value).casefold() != canonical:
        raise _failure(reason, "The owned DaVinci Resolve worker identity is not canonical.")
    return canonical


def _secure_regular_json(path: Path) -> dict[str, Any]:
    flags = os.O_RDONLY | int(getattr(os, "O_CLOEXEC", 0)) | int(getattr(os, "O_NOFOLLOW", 0))
    try:
        descriptor = os.open(path, flags)
    except OSError:
        raise _failure("owned_lifecycle_state_unavailable", "Owned DaVinci Resolve lifecycle state is unavailable.") from None
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or metadata.st_uid != os.getuid()
            or metadata.st_size <= 0
            or metadata.st_size > _MAX_STATE_BYTES
            or metadata.st_mode & 0o022
        ):
            raise _failure("owned_lifecycle_state_invalid", "Owned DaVinci Resolve lifecycle state has an unsafe identity.")
        payload = os.read(descriptor, _MAX_STATE_BYTES + 1)
    finally:
        os.close(descriptor)
    if len(payload) > _MAX_STATE_BYTES:
        raise _failure("owned_lifecycle_state_invalid", "Owned DaVinci Resolve lifecycle state is too large.")
    try:
        parsed = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise _failure("owned_lifecycle_state_invalid", "Owned DaVinci Resolve lifecycle state is malformed.") from None
    if not isinstance(parsed, dict):
        raise _failure("owned_lifecycle_state_invalid", "Owned DaVinci Resolve lifecycle state is malformed.")
    return parsed


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | int(getattr(os, "O_DIRECTORY", 0)) | int(getattr(os, "O_CLOEXEC", 0))
    try:
        descriptor = os.open(path, flags)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def _atomic_state_write(path: Path, payload: dict[str, Any]) -> None:
    encoded = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    if len(encoded) > _MAX_STATE_BYTES:
        raise _failure("owned_lifecycle_state_invalid", "Owned DaVinci Resolve lifecycle state is too large.")
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid4().hex}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | int(getattr(os, "O_CLOEXEC", 0)) | int(getattr(os, "O_NOFOLLOW", 0))
    descriptor = os.open(temporary, flags, 0o600)
    try:
        with os.fdopen(descriptor, "wb", closefd=True) as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _home_identity(home: Path) -> tuple[int, int]:
    metadata = home.stat(follow_symlinks=False)
    if not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != os.getuid():
        raise _failure("owned_worker_home_invalid", "The owned DaVinci Resolve worker home is unsafe.")
    return int(metadata.st_dev), int(metadata.st_ino)


def _validate_state(
    state: dict[str, Any],
    *,
    home: Path,
    configured_uuid: str,
    identity: dict[str, str],
) -> str:
    home_device, home_inode = _home_identity(home)
    lineage = state.get("uuidLineage")
    if (
        state.get("schemaVersion") != _SCHEMA_VERSION
        or state.get("scope") != "owned_headless_resolve_worker"
        or state.get("state") != "ready"
        or state.get("homeDevice") != home_device
        or state.get("homeInode") != home_inode
        or not isinstance(lineage, list)
        or not 2 <= len(lineage) <= _MAX_LINEAGE
        or len(set(lineage)) != len(lineage)
        or configured_uuid not in lineage
    ):
        raise _failure("owned_lifecycle_state_invalid", "Owned DaVinci Resolve lifecycle state does not bind this worker.")
    canonical_lineage = [_canonical_uuid(value, reason="owned_lifecycle_state_invalid") for value in lineage]
    active_uuid = _canonical_uuid(state.get("activeUuid"), reason="owned_lifecycle_state_invalid")
    active_pid = state.get("activePid")
    if (
        canonical_lineage != lineage
        or active_uuid != canonical_lineage[-1]
        or identity.get("uuid") != active_uuid
        or not isinstance(active_pid, int)
        or active_pid <= 1
        or str(active_pid) != identity.get("pid")
    ):
        raise _failure("owned_lifecycle_state_invalid", "Owned DaVinci Resolve lifecycle state has drifted from its exact process identity.")
    try:
        os.kill(active_pid, 0)
    except OSError:
        raise _failure("owned_lifecycle_process_unavailable", "The rotated owned DaVinci Resolve worker is not running.") from None
    return active_uuid


def resolve_rotated_instance_uuid(home: str, configured_uuid: str, identity: dict[str, str]) -> str:
    """Resolve only a durable, exact UUID rotation for one isolated worker."""

    canonical_configured = _canonical_uuid(configured_uuid, reason="owned_lifecycle_state_invalid")
    canonical_home = Path(home).resolve(strict=True)
    state = _secure_regular_json(canonical_home / _STATE_FILE)
    return _validate_state(
        state,
        home=canonical_home,
        configured_uuid=canonical_configured,
        identity=identity,
    )


def _process_identity(pid: int) -> tuple[int, str, str]:
    fields: list[str] = []
    try:
        for field in ("uid=", "comm=", "args="):
            completed = subprocess.run(
                ["/bin/ps", "-p", str(pid), "-o", field],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="strict",
                timeout=2.0,
                check=False,
            )
            value = completed.stdout.strip()
            if completed.returncode != 0 or not value:
                raise _failure(
                    "owned_process_identity_unavailable",
                    "The owned DaVinci Resolve process identity could not be inspected.",
                )
            fields.append(value)
    except (OSError, subprocess.SubprocessError, UnicodeError):
        raise _failure("owned_process_identity_unavailable", "The owned DaVinci Resolve process identity could not be inspected.") from None
    uid_text, executable, arguments = fields
    if not uid_text.isdigit() or not executable or not arguments:
        raise _failure("owned_process_identity_invalid", "The owned DaVinci Resolve process identity is malformed.")
    return int(uid_text), executable, arguments


def _process_environment(pid: int) -> str:
    try:
        completed = subprocess.run(
            ["/bin/ps", "eww", "-p", str(pid), "-o", "command="],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="strict",
            timeout=2.0,
            check=False,
        )
    except (OSError, subprocess.SubprocessError, UnicodeError):
        raise _failure("owned_process_environment_unavailable", "The owned worker environment could not be inspected.") from None
    output = completed.stdout.strip()
    if completed.returncode != 0 or not output:
        raise _failure("owned_process_environment_unavailable", "The owned worker environment could not be inspected.")
    return output


def _environment_value_matches(output: str, key: str, value: str) -> bool:
    pattern = rf"(?:^| ){re.escape(key)}={re.escape(value)}(?= [A-Za-z_][A-Za-z0-9_]*=|$)"
    return re.search(pattern, output) is not None


def _current_identity(home: Path) -> dict[str, str]:
    from ..adapters import _read_worker_identity

    return _read_worker_identity(str(home))


def _optional_identity(value: Any) -> str | None:
    getter = getattr(value, "GetUniqueId", None)
    if value is None or not callable(getter):
        return None
    result = getter()
    return str(result) if result else None


def _optional_name(value: Any) -> str | None:
    getter = getattr(value, "GetName", None)
    if value is None or not callable(getter):
        return None
    result = getter()
    return str(result) if result else None


def _assert_context(conn: Any, context: dict[str, Any]) -> None:
    manager = getattr(conn, "project_manager", None)
    resolve = getattr(conn, "resolve", None)
    if manager is None or resolve is None:
        raise _failure("owned_context_unavailable", "The exact DaVinci Resolve context is unavailable before restart.")
    project = manager.GetCurrentProject()
    timeline = project.GetCurrentTimeline() if project is not None else None
    actual_database = manager.GetCurrentDatabase()
    actual_page = resolve.GetCurrentPage()
    actual_playhead = timeline.GetCurrentTimecode() if timeline is not None else None
    folder_getter = getattr(manager, "GetCurrentFolder", None)
    raw_folder = folder_getter() if callable(folder_getter) else None
    actual_folder = "root" if isinstance(raw_folder, str) and raw_folder.strip().casefold() in {"", "root", "projects"} else None
    expected_database = context.get("database")
    database_matches = isinstance(expected_database, dict) and isinstance(actual_database, dict) and all(
        str(actual_database.get(key) or "") == str(expected_database.get(key) or "")
        for key in ("DbType", "DbName", "IpAddress") if key in expected_database or key in actual_database
    )
    if not database_matches or {
        "project_name": _optional_name(project),
        "project_id": _optional_identity(project),
        "timeline_name": _optional_name(timeline),
        "timeline_id": _optional_identity(timeline),
        "timeline_present": timeline is not None,
        "playhead": actual_playhead,
        "page": actual_page,
        "folder": actual_folder,
    } != {
        key: context.get(key)
        for key in ("project_name", "project_id", "timeline_name", "timeline_id", "timeline_present", "playhead", "page", "folder")
    }:
        raise _failure("owned_context_changed", "The exact DaVinci Resolve context changed before the owned restart.")
    save = getattr(manager, "SaveProject", None)
    if project is not None and (not callable(save) or not bool(save())):
        raise _failure("owned_project_save_failed", "DaVinci Resolve could not save the protected project before restart.")


def _wait_for_exit(pid: int, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        except OSError:
            return False
        time.sleep(0.1)
    return False


@contextmanager
def _defer_termination_signals():
    """Finish the owned identity handoff before honoring normal cancellation."""

    if threading.current_thread() is not threading.main_thread():
        raise _failure(
            "owned_lifecycle_signal_guard_unavailable",
            "Owned DaVinci Resolve lifecycle changes must run on the main thread.",
        )
    pending: list[int] = []
    previous: dict[int, Any] = {}

    def defer(signum: int, _frame: Any) -> None:
        pending.append(signum)

    for signum in (signal.SIGINT, signal.SIGTERM):
        previous[signum] = signal.getsignal(signum)
        signal.signal(signum, defer)
    failed = False
    try:
        yield
    except BaseException:
        failed = True
        raise
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)
        if pending and not failed:
            if signal.SIGINT in pending:
                raise KeyboardInterrupt
            raise SystemExit(128 + pending[-1])


def _wait_for_new_identity(home: Path, process: subprocess.Popen[Any], old_uuid: str) -> dict[str, str]:
    deadline = time.monotonic() + _START_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise APICallFailed(
                "The owned DaVinci Resolve worker exited before publishing its new identity.",
                details={"reason": "owned_worker_relaunch_failed", "pid": process.pid, "returncode": process.returncode},
                recoverability="manual",
            )
        try:
            identity = _current_identity(home)
        except Exception:
            identity = None
        if identity is not None and identity.get("uuid") != old_uuid:
            if identity.get("pid") != str(process.pid):
                raise _failure("owned_worker_identity_mismatch", "The relaunched DaVinci Resolve worker published a different process identity.")
            return identity
        time.sleep(0.25)
    raise APICallFailed(
        "Timed out waiting for the owned DaVinci Resolve worker to publish its new identity.",
        details={"reason": "owned_worker_relaunch_timeout", "pid": process.pid, "timeout_s": _START_TIMEOUT_SECONDS},
        recoverability="manual",
    )


def _lineage(home: Path, configured_uuid: str, current_uuid: str) -> list[str]:
    path = home / _STATE_FILE
    if not path.exists():
        return [configured_uuid]
    state = _secure_regular_json(path)
    lineage = state.get("uuidLineage")
    if (
        state.get("schemaVersion") == _SCHEMA_VERSION
        and state.get("scope") == "owned_headless_resolve_worker"
        and state.get("state") == "ready"
        and isinstance(lineage, list)
        and current_uuid == state.get("activeUuid")
        and configured_uuid in lineage
        and len(lineage) < _MAX_LINEAGE
    ):
        return [_canonical_uuid(value, reason="owned_lifecycle_state_invalid") for value in lineage]
    raise _failure("owned_lifecycle_state_conflict", "An unresolved owned DaVinci Resolve lifecycle record already exists.")


def _launch_environment() -> dict[str, str]:
    """Pass only ordinary process environment, never invocation authorization."""

    return {
        key: value for key, value in os.environ.items()
        if key in _LAUNCH_ENV_ALLOWLIST and isinstance(value, str) and value
    }


def _rebind_connection(conn: Any, new_uuid: str) -> None:
    disk_connection = getattr(conn, "_disk_db_conn", None)
    if disk_connection is not None:
        try:
            disk_connection.close()
        except Exception:
            pass
    for key, value in (
        ("_disk_db_conn", None), ("_disk_db_conn_path", None), ("adapter", None),
        ("transport", None), ("resolve", None), ("project_manager", None),
        ("project", None), ("media_pool", None), ("timeline", None),
    ):
        setattr(conn, key, value)
    conn.__dict__.pop("activate_project_library_registration", None)
    os.environ["CUTAGENT_RESOLVE_UUID"] = new_uuid
    conn.connect()


def _activation_custody(conn: Any) -> tuple[str, Path, dict[str, str], int, str, str]:
    """Return exact restart custody or fail without changing native state."""

    from .. import adapters
    from .launch_ops import resolve_binary_path

    if sys.platform != "darwin":
        raise _failure("owned_lifecycle_platform_unsupported", "Owned project-library activation is unavailable on this platform.")
    if getattr(conn, "transport", None) != adapters.ResolveTransport.STUDIO_EXTERNAL:
        raise _failure(
            "owned_lifecycle_transport_unsupported",
            "Project-library activation requires an exact Studio external worker connection.",
        )
    target = adapters._resolve_instance_target()
    if target is None:
        raise _failure("owned_instance_target_required", "Project-library activation cannot restart an unpinned DaVinci Resolve instance.")
    host, active_uuid = target
    try:
        if not ipaddress.ip_address(host).is_loopback:
            raise ValueError
    except ValueError:
        raise _failure("owned_instance_must_be_local", "Project-library activation cannot restart a remote DaVinci Resolve instance.") from None
    home_raw = os.environ.get("HOME", "")
    account_home = adapters._account_home()
    if not home_raw or not os.path.isabs(home_raw):
        raise _failure("owned_worker_home_required", "Project-library activation requires an isolated worker home.")
    home = Path(home_raw).resolve(strict=True)
    if account_home and home == Path(account_home).resolve():
        raise _failure("owned_gui_instance_forbidden", "Project-library activation cannot restart a user-owned DaVinci Resolve GUI instance.")
    identity = _current_identity(home)
    if identity.get("uuid") != active_uuid:
        raise _failure("owned_worker_identity_mismatch", "The targeted DaVinci Resolve worker identity changed before restart.")
    pid = int(identity["pid"])
    if pid <= 1:
        raise _failure("owned_process_identity_invalid", "The owned worker process identity is unsafe.")
    uid, executable, arguments = _process_identity(pid)
    process_environment = _process_environment(pid)
    binary = str(Path(resolve_binary_path()).resolve(strict=True))
    try:
        executable_matches = str(Path(executable).resolve(strict=True)) == binary
    except OSError:
        executable_matches = False
    expected_environment = {
        "HOME": str(home),
        "CFFIXED_USER_HOME": str(home),
        "TMPDIR": os.environ.get("TMPDIR", ""),
    }
    environment_matches = all(
        value and _environment_value_matches(process_environment, key, value)
        for key, value in expected_environment.items()
    )
    if (
        uid != os.getuid()
        or not executable_matches
        or arguments != f"{executable} -nogui"
        or not environment_matches
    ):
        raise _failure(
            "owned_process_identity_invalid",
            "Project-library activation requires the exact owned headless DaVinci Resolve process.",
            pid=pid,
        )
    configured_uuid = _canonical_uuid(os.environ.get(adapters.CUTAGENT_RESOLVE_UUID_ENV), reason="owned_instance_target_required")
    return active_uuid, home, identity, pid, binary, configured_uuid


def configure_project_library_activation(conn: Any) -> bool:
    """Expose the callback only when exact restart custody is already proven."""

    conn.__dict__.pop("activate_project_library_registration", None)
    try:
        _activation_custody(conn)
    except Exception:
        return False
    conn.activate_project_library_registration = partial(activate_project_library_registration, conn)
    return True


def _activate_project_library_registration(conn: Any, *, name: str, context: dict[str, Any]) -> None:
    """Restart and rebind one exact CutAgent-owned headless worker."""

    if not isinstance(name, str) or not name.strip() or not isinstance(context, dict):
        raise _failure("owned_lifecycle_input_invalid", "Owned project-library activation input is invalid.")
    active_uuid, home, _identity, pid, binary, configured_uuid = _activation_custody(conn)
    _assert_context(conn, context)

    lineage = _lineage(home, configured_uuid, active_uuid)
    home_device, home_inode = _home_identity(home)
    operation_id = uuid4().hex
    state_path = home / _STATE_FILE
    state = {
        "schemaVersion": _SCHEMA_VERSION,
        "scope": "owned_headless_resolve_worker",
        "state": "stopping",
        "operationId": operation_id,
        "activationName": name.strip(),
        "homeDevice": home_device,
        "homeInode": home_inode,
        "uuidLineage": lineage,
        "previousUuid": active_uuid,
        "previousPid": pid,
        "activeUuid": active_uuid,
        "activePid": pid,
    }
    _atomic_state_write(state_path, state)
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        state["state"] = "stop_failed"
        _atomic_state_write(state_path, state)
        raise _failure("owned_process_stop_failed", "The exact owned DaVinci Resolve process could not be stopped.", pid=pid) from None
    if not _wait_for_exit(pid, _EXIT_TIMEOUT_SECONDS):
        state["state"] = "stop_timeout"
        _atomic_state_write(state_path, state)
        raise APICallFailed(
            "The exact owned DaVinci Resolve process did not exit; no replacement was launched.",
            details={"reason": "owned_process_stop_timeout", "pid": pid, "timeout_s": _EXIT_TIMEOUT_SECONDS},
            recoverability="manual",
        )

    log_directory = home / _LOG_DIRECTORY
    log_directory.mkdir(mode=0o700, exist_ok=True)
    if log_directory.is_symlink() or not log_directory.is_dir() or log_directory.stat().st_uid != os.getuid():
        state["state"] = "launch_log_invalid"
        _atomic_state_write(state_path, state)
        raise _failure("owned_launch_log_invalid", "The owned DaVinci Resolve launch-log directory is unsafe.")
    log_path = log_directory / f"{operation_id}.log"
    log_descriptor = os.open(
        log_path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | int(getattr(os, "O_CLOEXEC", 0)) | int(getattr(os, "O_NOFOLLOW", 0)),
        0o600,
    )
    environment = _launch_environment()
    with os.fdopen(log_descriptor, "wb", closefd=True) as log:
        process = subprocess.Popen(
            [binary, "-nogui"],
            env=environment,
            stdout=log,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
    state.update(state="launched", activePid=process.pid, launchLog=str(log_path))
    _atomic_state_write(state_path, state)
    new_identity = _wait_for_new_identity(home, process, active_uuid)
    new_uuid = _canonical_uuid(new_identity["uuid"], reason="owned_worker_identity_mismatch")
    if new_uuid in lineage:
        state["state"] = "identity_reused"
        _atomic_state_write(state_path, state)
        raise _failure("owned_worker_identity_reused", "The relaunched DaVinci Resolve worker reused an earlier native identity.")
    lineage.append(new_uuid)
    state.update(
        state="reattaching",
        uuidLineage=lineage,
        activeUuid=new_uuid,
        activePid=process.pid,
        activationVerified=False,
    )
    _atomic_state_write(state_path, state)
    try:
        _rebind_connection(conn, new_uuid)
        manager = getattr(conn, "project_manager", None)
        getter = getattr(manager, "GetDatabaseList", None)
        rows = getter() if callable(getter) else None
        matches = [
            row for row in rows or []
            if isinstance(row, dict) and row.get("DbType") == "Disk" and row.get("DbName") == name.strip()
        ]
        if not isinstance(rows, list) or len(matches) != 1:
            raise APICallFailed(
                "The restarted DaVinci Resolve worker did not enumerate the new project library exactly once.",
                details={"reason": "owned_library_activation_unverified", "name": name.strip(), "match_count": len(matches)},
                recoverability="manual",
            )
    except BaseException as exc:
        state.update(state="activation_failed", failureType=type(exc).__name__)
        _atomic_state_write(state_path, state)
        raise
    state.update(state="ready", activationVerified=True)
    _atomic_state_write(state_path, state)
    setattr(conn, "_owned_resolve_process", process)


def activate_project_library_registration(conn: Any, *, name: str, context: dict[str, Any]) -> None:
    """Activate a registry row while deferring cancellation across UUID rotation."""

    with _defer_termination_signals():
        _activate_project_library_registration(conn, name=name, context=context)
