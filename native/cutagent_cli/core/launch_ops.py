"""DaVinci Resolve launch helpers (headless/no-gui workflow)."""

from __future__ import annotations

import math
import multiprocessing
import os
import re
import shutil
import subprocess
import sys
import time
from typing import Any, Optional

from ..config import get_config
from ..connection import ResolveConnection
from ..errors import APICallFailed, ExternalToolNotFound, ValidationError


_FREE_UTILITY_GRACE_S = 3.0
_FREE_UTILITY_RETRY_S = 1.0
_PROBE_TIMEOUT_S = 2.0


def _connection_probe_worker(queue: Any) -> None:
    """Run a connection attempt outside the CLI process so it can be bounded."""
    try:
        ResolveConnection.reset()
        conn = ResolveConnection.get()
        conn.connect()
        queue.put((True, None))
    except BaseException as exc:  # pragma: no cover - executed in child process
        queue.put((False, str(exc)))


def _bounded_scripting_bridge_probe(timeout_s: float = _PROBE_TIMEOUT_S) -> tuple[bool, Optional[str]]:
    """Probe transport readiness without allowing a backend call to exceed its budget."""
    context = multiprocessing.get_context("spawn" if sys.platform == "win32" else "fork")
    queue = context.Queue(maxsize=1)
    worker = context.Process(target=_connection_probe_worker, args=(queue,), daemon=True)
    worker.start()
    worker.join(timeout=max(0.05, timeout_s))
    if worker.is_alive():
        worker.terminate()
        worker.join(timeout=1.0)
        queue.close()
        return False, f"connection probe exceeded {timeout_s:.2f}s"
    try:
        connected, error = queue.get_nowait()
    except Exception:
        connected, error = False, f"connection probe exited with code {worker.exitcode}"
    queue.close()
    return bool(connected), error


def _start_free_utility_menu_action() -> Optional[subprocess.Popen[Any]]:
    """Start the DaVinci Resolve Free utility without waiting for its long-lived Lua loop."""
    if sys.platform != "darwin":
        return None
    script = '''
tell application "System Events"
    tell process "DaVinci Resolve"
        click menu item "CutAgent" of menu 1 of menu item "Scripts" of menu 1 of menu bar item "Workspace" of menu bar 1
    end tell
end tell
'''
    try:
        return subprocess.Popen(
            ["osascript", "-e", script],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError:
        return None


def _reap_helper(helper: Optional[subprocess.Popen[Any]]) -> None:
    if helper is None or helper.poll() is not None:
        return
    helper.terminate()
    try:
        helper.wait(timeout=1.0)
    except subprocess.TimeoutExpired:
        helper.kill()
        helper.wait(timeout=1.0)


def _terminate_spawned_process(proc: Optional[subprocess.Popen[Any]]) -> bool:
    """Stop only the DaVinci Resolve process created by this launch attempt."""
    if proc is None or proc.poll() is not None:
        return False
    proc.terminate()
    try:
        proc.wait(timeout=5.0)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5.0)
    return True


def _is_executable(path: str) -> bool:
    return os.path.isfile(path) and os.access(path, os.X_OK)


def resolve_binary_path(cli_path: Optional[str] = None) -> str:
    """Resolve DaVinci Resolve binary path with precedence: CLI -> config -> PATH/defaults."""
    if cli_path is not None:
        expanded = os.path.expanduser(cli_path)
        if _is_executable(expanded):
            return expanded
        raise ExternalToolNotFound(
            f"DaVinci Resolve binary is not executable: {expanded}",
            details={"tool": "resolve", "override": expanded},
        )

    cfg_path = get_config().get("tools", "resolve_path")
    if cfg_path:
        expanded = os.path.expanduser(str(cfg_path))
        if _is_executable(expanded):
            return expanded
        raise ExternalToolNotFound(
            f"Configured DaVinci Resolve binary is not executable: {expanded}",
            details={"tool": "resolve", "config_path": expanded},
        )

    if sys.platform == "win32":
        program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
        program_files_x86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
        candidates = [
            os.path.join(program_files, "Blackmagic Design", "DaVinci Resolve", "Resolve.exe"),
            os.path.join(program_files_x86, "Blackmagic Design", "DaVinci Resolve", "Resolve.exe"),
        ]
    else:
        candidates = [
            "/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/MacOS/Resolve",
            "/opt/resolve/bin/resolve",
            "/usr/bin/resolve",
        ]
    for candidate in candidates:
        if _is_executable(candidate):
            return candidate

    which = shutil.which("Resolve.exe" if sys.platform == "win32" else "resolve")
    if which:
        return which

    raise ExternalToolNotFound(
        "DaVinci Resolve binary not found. Pass --resolve-path or configure tools.resolve_path.",
        details={"tool": "resolve"},
    )


def validate_timeout(timeout_s: float) -> None:
    """Reject timeout values that would fail immediately or wait forever."""
    if not math.isfinite(timeout_s) or timeout_s <= 0:
        raise ValidationError(
            "Launch wait timeout must be a finite positive number.",
            details={"timeout_s": timeout_s},
        )


def _scripting_bridge_is_reachable() -> bool:
    """Return whether an existing DaVinci Resolve session is already usable."""
    connected, _error = _bounded_scripting_bridge_probe()
    return connected


def _resolve_process_is_running(binary: str) -> bool:
    """Avoid probing a stale transport when no DaVinci Resolve process exists."""
    try:
        if sys.platform == "win32":
            # Import lazily because the adapter imports connection code that also
            # reaches this module. Its process probe resolves tasklist.exe through
            # the kernel-reported system directory and parses exact CSV names.
            from ..adapters import is_resolve_process_running

            return is_resolve_process_running()
        pgrep = next(
            (candidate for candidate in ("/usr/bin/pgrep", "/bin/pgrep") if _is_executable(candidate)),
            None,
        )
        if pgrep is None:
            return False
        result = subprocess.run(
            [pgrep, "-f", f"^{re.escape(binary)}([[:space:]]|$)"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=2,
            check=False,
        )
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def launch_resolve(
    *,
    headless: bool = False,
    wait: bool = True,
    timeout_s: float = 60.0,
    resolve_path: Optional[str] = None,
) -> dict[str, Any]:
    """Launch DaVinci Resolve process and optionally wait for scripting bridge readiness."""
    validate_timeout(timeout_s)
    binary = resolve_binary_path(resolve_path)
    process_was_running = _resolve_process_is_running(binary)
    if process_was_running and _scripting_bridge_is_reachable():
        return {
            "pid": None,
            "path": binary,
            "headless": headless,
            "wait": wait,
            "connected": True,
            "launched": False,
            "already_running": True,
        }
    proc: Optional[subprocess.Popen[Any]] = None
    if not process_was_running:
        cmd = [binary]
        if headless:
            cmd.append("-nogui")
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )

    result: dict[str, Any] = {
        "pid": proc.pid if proc is not None else None,
        "path": binary,
        "headless": headless,
        "wait": wait,
        "connected": False,
        "launched": proc is not None,
        "already_running": process_was_running,
    }
    if not wait:
        return result

    deadline = time.monotonic() + timeout_s
    started_at = time.monotonic()
    last_error: Optional[str] = None
    helper: Optional[subprocess.Popen[Any]] = None
    utility_last_attempt_at: Optional[float] = None
    try:
        while time.monotonic() < deadline:
            if proc is not None and proc.poll() is not None:
                raise APICallFailed(
                    "DaVinci Resolve process exited before scripting bridge became available.",
                    details={"pid": proc.pid, "returncode": proc.returncode, "path": binary},
                )
            remaining = deadline - time.monotonic()
            connected, last_error = _bounded_scripting_bridge_probe(min(_PROBE_TIMEOUT_S, remaining))
            if connected:
                result["connected"] = True
                return result
            now = time.monotonic()
            helper_finished = helper is not None and helper.poll() is not None
            retry_due = utility_last_attempt_at is None or now - utility_last_attempt_at >= _FREE_UTILITY_RETRY_S
            if (
                not headless
                and now - started_at >= _FREE_UTILITY_GRACE_S
                and (helper is None or helper_finished)
                and retry_due
            ):
                helper = _start_free_utility_menu_action()
                utility_last_attempt_at = now
            time.sleep(min(0.5, max(0.0, deadline - time.monotonic())))
    except BaseException:
        _terminate_spawned_process(proc)
        raise
    finally:
        _reap_helper(helper)

    process_terminated = _terminate_spawned_process(proc)

    raise APICallFailed(
        "Timed out waiting for DaVinci Resolve scripting bridge.",
        details={
            "pid": proc.pid if proc is not None else None,
            "path": binary,
            "timeout_s": timeout_s,
            "last_error": last_error,
            "process_terminated": process_terminated,
        },
    )
