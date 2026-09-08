"""Utility commands: status, info, version, connect."""

from __future__ import annotations

import math
from pathlib import Path
import os
import subprocess
import sys
import time
import typer

from .. import adapters as instance_adapters
from ..capabilities import get_capabilities
from ..adapters import get_resolve_script_import_error, import_resolve_script, probe_resolve_process_running, transport_status
from ..connection import get_connection
from ..embedded_bridge import installed_script_status, terminate_embedded_script_hosts
from ..external_tools import probe_tool_version
from ..errors import (
    APICallFailed,
    ConfirmationRequired,
    EmbeddedBridgeAuthFailed,
    EmbeddedBridgeNotRunning,
    EmbeddedBridgeOutdated,
    EmbeddedBridgeTimeout,
    NoProjectOpen,
    ReadinessFailed,
    ResolveNotRunning,
    ResolveScriptingUnavailable,
    ValidationError,
    handle_errors,
)
from ..output import (
    is_dry_run,
    is_machine_mode,
    is_verbose,
    mutation_payload,
    output,
    set_recoverability,
    set_verification_status,
)
from ..policy import enforce_mutation_policy
from ..state_contracts import (
    current_project_folder_name,
    looks_like_project_manager_placeholder,
    project_folder_path_label,
)
from .. import __version__

app = typer.Typer(help="Utility commands.")

DEFAULT_RESOLVE_QUIT_TIMEOUT_SECONDS = 15.0
RESOLVE_QUIT_TIMEOUT_ENV = "CUTAGENT_RESOLVE_QUIT_TIMEOUT_S"


def _resolve_quit_timeout_seconds() -> float:
    raw = os.environ.get(RESOLVE_QUIT_TIMEOUT_ENV, "").strip()
    if not raw:
        return DEFAULT_RESOLVE_QUIT_TIMEOUT_SECONDS
    try:
        timeout = float(raw)
    except (TypeError, ValueError):
        return DEFAULT_RESOLVE_QUIT_TIMEOUT_SECONDS
    return timeout if math.isfinite(timeout) and timeout > 0 else DEFAULT_RESOLVE_QUIT_TIMEOUT_SECONDS


def _wait_for_resolve_exit(timeout_s: float | None = None, *, target_pid: int | None = None) -> bool:
    deadline = time.monotonic() + (timeout_s if timeout_s is not None else _resolve_quit_timeout_seconds())
    if target_pid is not None:
        while True:
            try:
                os.kill(target_pid, 0)
            except ProcessLookupError:
                return True
            except OSError as exc:
                raise APICallFailed(
                    "Could not verify that the targeted DaVinci Resolve instance exited.",
                    details={"method": "Quit", "process_probe": "unavailable", "pid": target_pid},
                ) from exc
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.2)
    process_running = probe_resolve_process_running()
    while process_running is not False:
        if process_running is None:
            raise APICallFailed(
                "Could not verify that DaVinci Resolve exited.",
                details={"method": "Quit", "process_probe": "unavailable"},
            )
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.2)
        process_running = probe_resolve_process_running()
    return True


def _resolve_error_payload(exc: Exception) -> dict:
    details = getattr(exc, "details", None)
    return {
        "code": getattr(exc, "code", exc.__class__.__name__),
        "message": str(exc),
        "recoverability": getattr(exc, "recoverability", None),
        "details": details if isinstance(details, dict) else {},
    }


def _doctor_resolve_context(conn) -> dict:
    project = getattr(conn, "project", None)
    timeline = getattr(conn, "timeline", None)
    project_name = project.GetName() if project else None
    timeline_name = timeline.GetName() if timeline else None
    get_timeline_count = getattr(project, "GetTimelineCount", None)
    timeline_count = get_timeline_count() if callable(get_timeline_count) else None
    if looks_like_project_manager_placeholder(conn, project_name, timeline_count):
        project_name = None
        timeline_name = None
    return {
        "active_transport": conn.transport.value if getattr(conn, "transport", None) else None,
        "project": project_name,
        "timeline": timeline_name,
    }


def _disconnected_status(transports: dict, ui_state: dict, exc: Exception | None = None) -> dict:
    data = {
        "status": "disconnected",
        "resolve": False,
        "project": None,
        "timeline": None,
        "active_transport": None,
        "transports": transports,
        "resolve_version": transports.get("resolve_version"),
        "product_name": transports.get("product_name"),
        "edition": transports.get("edition"),
    }
    if exc is not None:
        data["connection_error"] = _resolve_error_payload(exc)
    _attach_ui_state(data, ui_state)
    return data


def _decode_applescript_bool(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"true", "yes", "1"}


def _parse_resolve_ui_probe(raw: str) -> dict:
    status = {
        "available": False,
        "running": False,
        "frontmost": None,
        "blocked": False,
        "active_modal": None,
        "windows": [],
        "probe": "macos_system_events",
    }
    modals: list[dict] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("AVAILABLE="):
            status["available"] = _decode_applescript_bool(line.split("=", 1)[1])
            continue
        if line.startswith("RUNNING="):
            status["running"] = _decode_applescript_bool(line.split("=", 1)[1])
            continue
        if line.startswith("FRONTMOST="):
            status["frontmost"] = _decode_applescript_bool(line.split("=", 1)[1])
            continue
        parts = line.split("|")
        if parts[0] == "WINDOW" and len(parts) >= 5:
            try:
                sheet_count = int(parts[4])
            except ValueError:
                sheet_count = 0
            status["windows"].append(
                {
                    "title": parts[1] or None,
                    "role": parts[2] or None,
                    "subrole": parts[3] or None,
                    "sheet_count": sheet_count,
                }
            )
            continue
        if parts[0] == "MODAL" and len(parts) >= 7:
            modal = {
                "title": parts[1] or None,
                "role": parts[2] or None,
                "subrole": parts[3] or None,
                "message": parts[4] or None,
                "buttons": [button for button in parts[5].split(",") if button],
                "parent_window": parts[6] or None,
            }
            modals.append(modal)

    if modals:
        status["blocked"] = True
        status["active_modal"] = modals[0]
        status["modals"] = modals
    return status


def _resolve_ui_probe_script(pid: int | None = None) -> list[str]:
    process = (
        f'(first application process whose unix id is {pid} and name is "Resolve")'
        if pid is not None
        else 'process "DaVinci Resolve"'
    )
    return [
        'tell application "System Events"',
        f'if not (exists {process}) then',
        'return "AVAILABLE=true" & linefeed & "RUNNING=false"',
        'end if',
        f'tell {process}',
        'set out to "AVAILABLE=true" & linefeed & "RUNNING=true" & linefeed & "FRONTMOST=" & (frontmost as text) & linefeed',
        'repeat with w in windows',
        'set titleText to name of w as text',
        'set roleText to role of w as text',
        'set subroleText to ""',
        'try',
        'set subroleText to subrole of w as text',
        'end try',
        'set sheetCount to count of sheets of w',
        'set out to out & "WINDOW|" & titleText & "|" & roleText & "|" & subroleText & "|" & (sheetCount as text) & linefeed',
        'if sheetCount > 0 then',
        'repeat with s in sheets of w',
        'set modalRole to role of s as text',
        'set modalSubrole to ""',
        'try',
        'set modalSubrole to subrole of s as text',
        'end try',
        'set modalMessage to ""',
        'try',
        'repeat with uiText in static texts of s',
        'set modalMessage to modalMessage & (value of uiText as text) & " "',
        'end repeat',
        'end try',
        'set buttonNames to ""',
        'try',
        'repeat with b in buttons of s',
        'set buttonNames to buttonNames & (name of b as text) & ","',
        'end repeat',
        'end try',
        'set out to out & "MODAL|" & titleText & "|" & modalRole & "|" & modalSubrole & "|" & modalMessage & "|" & buttonNames & "|" & titleText & linefeed',
        'end repeat',
        'else if roleText is "AXDialog" or subroleText is "AXDialog" then',
        'set modalMessage to ""',
        'try',
        'repeat with uiText in static texts of w',
        'set modalMessage to modalMessage & (value of uiText as text) & " "',
        'end repeat',
        'end try',
        'set buttonNames to ""',
        'try',
        'repeat with b in buttons of w',
        'set buttonNames to buttonNames & (name of b as text) & ","',
        'end repeat',
        'end try',
        'set out to out & "MODAL|" & titleText & "|" & roleText & "|" & subroleText & "|" & modalMessage & "|" & buttonNames & "|" & titleText & linefeed',
        'end if',
        'end repeat',
        'return out',
        'end tell',
        'end tell',
    ]


def _probe_resolve_ui_state() -> dict:
    """Best-effort read-only macOS accessibility probe for blocking DaVinci Resolve modals."""
    base = {
        "available": False,
        "running": None,
        "frontmost": None,
        "blocked": None,
        "active_modal": None,
        "windows": [],
        "probe": "macos_system_events",
    }
    if sys.platform != "darwin":
        return {**base, "error": "unsupported_platform"}
    pid = None
    if instance_adapters.resolve_instance_target_configured():
        try:
            _host, instance_uuid = instance_adapters._resolve_instance_target()
            identity = instance_adapters._read_worker_identity(os.path.realpath(os.environ.get("HOME", "")))
            if identity["uuid"].casefold() != instance_uuid:
                raise ValueError("UI instance identity mismatch")
            pid = int(identity["pid"])
            if pid <= 1:
                raise ValueError("Invalid UI instance process")
        except Exception:
            # A UUID-pinned connection must never borrow another instance's
            # windows or modal state, including the ordinary GUI supervisor.
            return {**base, "error": "targeted_ui_process_unavailable"}
    try:
        args = ["osascript"]
        for line in _resolve_ui_probe_script(pid):
            args.extend(["-e", line])
        completed = subprocess.run(
            args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=2.0,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {**base, "error": str(exc)}
    if completed.returncode != 0:
        error = completed.stderr.strip() or completed.stdout.strip() or f"osascript exited {completed.returncode}"
        return {**base, "error": error}
    parsed = _parse_resolve_ui_probe(completed.stdout)
    parsed["available"] = True
    if pid is not None:
        parsed["pid"] = pid
        if not parsed["running"] or not parsed["windows"]:
            parsed.update(blocked=None, error="targeted_ui_window_unavailable")
    return parsed


def _disabled_resolve_ui_state() -> dict:
    return {
        "available": False,
        "running": None,
        "frontmost": None,
        "blocked": None,
        "active_modal": None,
        "windows": [],
        "probe": "disabled",
        "error": "ui_probe_requires_explicit_automation_permission",
    }


def _attach_ui_state(data: dict, ui_state: dict | None = None) -> None:
    if ui_state is None:
        ui_state = _probe_resolve_ui_state()
    data["ui"] = ui_state
    data["ui_blocked"] = bool(ui_state.get("blocked"))
    data["active_modal"] = ui_state.get("active_modal")
    if data["ui_blocked"]:
        set_verification_status("pending_manual")
        set_recoverability("manual")


@app.command()
@handle_errors
def status(
    include_ui: bool = typer.Option(
        False,
        "--include-ui",
        help="Include the System Events UI probe. This can request macOS Automation permission.",
    ),
):
    """Show connection status, current project, and timeline."""
    transports = transport_status()
    ui_state = _probe_resolve_ui_state() if include_ui is True else _disabled_resolve_ui_state()
    try:
        conn = get_connection(require_project=False)
        state = conn.current_state()
    except (
        ResolveNotRunning,
        ResolveScriptingUnavailable,
        EmbeddedBridgeNotRunning,
        EmbeddedBridgeOutdated,
        EmbeddedBridgeTimeout,
        EmbeddedBridgeAuthFailed,
        APICallFailed,
    ) as exc:
        output(_disconnected_status(transports, ui_state, exc))
        return

    project_name = state["project"]
    timeline_count = state["timeline_count"]
    current_folder = current_project_folder_name(conn)
    project_manager_placeholder = looks_like_project_manager_placeholder(conn, project_name, timeline_count)
    if project_manager_placeholder:
        project_name = None
    project_open = isinstance(project_name, str) and bool(project_name.strip())

    data = {
        "status": "connected",
        "resolve": True,
        "active_transport": conn.transport.value if getattr(conn, "transport", None) else transports.get("active_transport"),
        "transports": transports,
        "resolve_version": transports.get("resolve_version"),
        "product_name": transports.get("product_name"),
        "edition": transports.get("edition"),
        "project": project_name if project_open else None,
        "timeline": state["timeline"],
        "timeline_count": timeline_count,
        "fps": state["fps"],
        "start_frame": state["start_frame"],
        "project_open": project_open,
        "context": "project" if project_open else "project_manager",
    }
    if project_manager_placeholder:
        data["raw_project_name"] = state["project"]
        data["current_folder"] = current_folder or ""
        data["current_path"] = project_folder_path_label(current_folder)
        data["message"] = "DaVinci Resolve is in Project Manager context; no real project is open."

    # Try to get current page
    if conn.resolve:
        try:
            page = conn.resolve.GetCurrentPage()
            data["page"] = page
        except Exception:
            pass

    _attach_ui_state(data, ui_state)
    output(data, title="DaVinci Resolve Status")


@app.command()
@handle_errors
def context():
    """One-call orientation snapshot: project, timeline, page, playhead, in/out, current item.

    Designed for agents: everything a turn needs to know about "where am I"
    in one fast call with a compact payload. GUI clip selection is not
    exposed by the DaVinci Resolve scripting API and is deliberately absent.
    """
    from ..core import timeline_ops
    from ..utils.timecode import frames_to_seconds, seconds_to_timecode

    conn = get_connection(require_timeline=True)

    def frame_tc(frame) -> str:
        return seconds_to_timecode(frames_to_seconds(int(frame), conn.fps), conn.fps)

    data: dict = {}

    def safe(key, getter):
        # Orientation must degrade per-field, never fail as a whole.
        try:
            value = getter()
        except Exception:
            return
        if value not in (None, "", {}):
            data[key] = value

    safe("project", lambda: conn.project.GetName())
    safe("timeline", lambda: conn.timeline.GetName())
    safe("fps", lambda: conn.fps)
    safe("page", lambda: str(conn.resolve.GetCurrentPage() or "").lower() or None)
    safe("playhead", lambda: timeline_ops.get_playhead(conn).get("timecode"))
    safe("end", lambda: conn.timeline.GetEndTimecode())
    safe(
        "tracks",
        lambda: (
            f"{conn.timeline.GetTrackCount('video') or 0}V"
            f"/{conn.timeline.GetTrackCount('audio') or 0}A"
            f"/{conn.timeline.GetTrackCount('subtitle') or 0}S"
        ),
    )

    def mark_in_out():
        marks = timeline_ops.get_mark_in_out(conn).get("marks")
        if not isinstance(marks, dict):
            return None
        compact = {}
        for kind, value in marks.items():
            if isinstance(value, dict) and value.get("in") is not None and value.get("out") is not None:
                compact[str(kind)] = f"{frame_tc(value['in'])}–{frame_tc(value['out'])}"
        return compact or None

    safe("in_out", mark_in_out)

    def current_item():
        item = conn.timeline.GetCurrentVideoItem()
        if not item:
            return None
        entry: dict = {}
        try:
            entry["name"] = item.GetName()
        except Exception:
            pass
        try:
            entry["range"] = f"{frame_tc(item.GetStart())}–{frame_tc(item.GetEnd())}"
        except Exception:
            pass
        try:
            track_type, track_index = item.GetTrackTypeAndIndex()
            prefix = {"video": "V", "audio": "A", "subtitle": "ST"}.get(str(track_type), str(track_type))
            entry["track"] = f"{prefix}{track_index}"
        except Exception:
            pass
        return entry or None

    safe("current_item", current_item)
    output(data, title="Context")


@app.command()
@handle_errors
def info():
    """Comprehensive info about current project and timeline."""
    conn = get_connection(require_project=True)
    project_name = conn.project.GetName()
    try:
        timeline_count = conn.project.GetTimelineCount() or 0
    except Exception:
        timeline_count = None
    if looks_like_project_manager_placeholder(conn, project_name, timeline_count):
        raise NoProjectOpen()

    data = {
        "project": project_name,
        "timeline": conn.timeline.GetName() if conn.timeline else None,
        "fps": conn.fps if conn.timeline else None,
        "start_frame": conn.start_frame if conn.timeline else None,
    }

    if conn.timeline:
        try:
            video_tracks = conn.timeline.GetTrackCount("video") or 0
            audio_tracks = conn.timeline.GetTrackCount("audio") or 0
            subtitle_tracks = conn.timeline.GetTrackCount("subtitle") or 0
            data["video_tracks"] = video_tracks
            data["audio_tracks"] = audio_tracks
            data["subtitle_tracks"] = subtitle_tracks
        except Exception:
            pass

        try:
            tc_start = conn.timeline.GetStartTimecode()
            tc_end = conn.timeline.GetEndTimecode()
            data["start_timecode"] = tc_start
            data["end_timecode"] = tc_end
        except Exception:
            pass

    # Timeline count
    try:
        if timeline_count is None:
            timeline_count = conn.project.GetTimelineCount() or 0
        data["timeline_count"] = timeline_count
    except Exception:
        pass

    # Project settings
    try:
        settings = conn.project.GetSetting()
        if isinstance(settings, dict):
            for key in ["timelineResolutionWidth", "timelineResolutionHeight", "timelineFrameRate"]:
                if key in settings:
                    data[key] = settings[key]
    except Exception:
        pass

    output(data, title="Project Info")


@app.command()
@handle_errors
def version():
    """Show CLI and DaVinci Resolve versions."""
    data = {"cli_version": __version__}
    transports = transport_status()
    data["transports"] = transports
    data["transport_status_resolve_version"] = transports.get("resolve_version")
    data["product_name"] = transports.get("product_name")
    data["edition"] = transports.get("edition")

    direct_version = None
    direct_version_string = None

    try:
        conn = get_connection(require_project=False)
        data["active_transport"] = conn.transport.value if getattr(conn, "transport", None) else None
        if conn.resolve:
            direct_version = conn.resolve.GetVersion()
            data["resolve_version"] = direct_version if direct_version else "unknown"
            direct_version_string = conn.resolve.GetVersionString()
            if direct_version_string:
                data["resolve_version_string"] = direct_version_string
    except ResolveScriptingUnavailable:
        data["active_transport"] = transports.get("active_transport")
        data["resolve_version"] = transports.get("resolve_version") or "scripting unavailable"
    except (
        ResolveNotRunning,
        EmbeddedBridgeNotRunning,
        EmbeddedBridgeOutdated,
        EmbeddedBridgeTimeout,
        EmbeddedBridgeAuthFailed,
        APICallFailed,
    ):
        data["active_transport"] = transports.get("active_transport")
        data["resolve_version"] = "not running"

    version_sources = {
        "direct_resolve_api": {
            "available": direct_version is not None or direct_version_string is not None,
            "version": direct_version,
            "version_string": direct_version_string,
        },
        "transport_status": {
            "available": bool(transports.get("resolve_version")),
            "active_transport": transports.get("active_transport"),
            "version": transports.get("resolve_version"),
            "product_name": transports.get("product_name"),
            "edition": transports.get("edition"),
        },
    }
    data["version_sources"] = version_sources

    direct_matches_transport = None
    transport_version = transports.get("resolve_version")
    if direct_version_string and transport_version:
        direct_matches_transport = str(direct_version_string) == str(transport_version)

    tuple_matches_string = None
    if direct_version and direct_version_string:
        expected_parts = [str(part) for part in direct_version if part is not None]
        tuple_matches_string = all(part in str(direct_version_string) for part in expected_parts)

    data["version_consistency"] = {
        "direct_matches_transport": direct_matches_transport,
        "tuple_matches_string": tuple_matches_string,
    }
    checks = [value for value in (direct_matches_transport, tuple_matches_string) if value is not None]
    if checks and all(checks):
        set_verification_status("verified")
        set_recoverability("not_applicable")

    output(data, title="Version")


@app.command()
@handle_errors
def connect():
    """Test connection to DaVinci Resolve."""
    conn = get_connection(require_project=False)
    project_name = conn.project.GetName() if conn.project else None
    if conn.project:
        try:
            timeline_count = conn.project.GetTimelineCount() or 0
        except Exception:
            timeline_count = None
        if looks_like_project_manager_placeholder(conn, project_name, timeline_count):
            project_name = None
    output(
        {
            "connected": True,
            "active_transport": conn.transport.value if getattr(conn, "transport", None) else None,
            "project": project_name,
            "timeline": conn.timeline.GetName() if conn.timeline else None,
            "fps": conn.fps if conn.timeline else None,
        },
        title="Connection",
    )


@app.command()
@handle_errors
def product():
    """Get DaVinci Resolve product name."""
    # Product identity is application-level state. DaVinci Resolve Free can
    # expose GetProductName while project-manager methods are unavailable.
    conn = get_connection(require_project=False, read_project_state=False)
    product_name = conn.resolve.GetProductName()
    if not isinstance(product_name, str) or not product_name.strip():
        raise APICallFailed(
            "DaVinci Resolve returned an empty product name.",
            details={"method": "GetProductName"},
        )
    output({"product": product_name.strip()})


@app.command()
@handle_errors
def quit(
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
):
    """Quit DaVinci Resolve."""
    enforce_mutation_policy("system.resolve_quit", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        output(
            mutation_payload(
                action="quit",
                target={"kind": "resolve"},
                changed=False,
                message="DRY-RUN: would quit DaVinci Resolve.",
            )
        )
        return
    if not force:
        if is_machine_mode():
            raise ConfirmationRequired(
                "Machine-mode mutation requires --force.",
                details={"action": "quit", "target_kind": "resolve"},
            )
        confirm = typer.confirm("Quit DaVinci Resolve? Unsaved changes will be lost.")
        if not confirm:
            raise typer.Abort()

    # Quitting is application-level state and must remain available from
    # Project Manager, where project APIs can be intentionally unavailable.
    conn = get_connection(require_project=False, read_project_state=False)
    active_transport = getattr(getattr(conn, "transport", None), "value", None)
    result = conn.resolve.Quit()
    if result is not True:
        raise APICallFailed(
            "DaVinci Resolve did not confirm the quit request.",
            details={"method": "Quit", "result": result},
        )
    target_pid = instance_adapters._resolve_instance_pid()
    exited = _wait_for_resolve_exit(target_pid=target_pid) if target_pid is not None else _wait_for_resolve_exit()
    if not exited:
        raise APICallFailed(
            "DaVinci Resolve accepted the quit request but remained running.",
            details={
                "method": "Quit",
                "timeout_s": _resolve_quit_timeout_seconds(),
                **({"pid": target_pid} if target_pid is not None else {}),
            },
        )
    script_host_cleanup = (
        terminate_embedded_script_hosts()
        if active_transport == "embedded_free"
        else {"matched": 0, "terminated": 0, "remaining": 0}
    )
    if script_host_cleanup["remaining"]:
        raise APICallFailed(
            "DaVinci Resolve quit, but its CutAgent embedded script host remained running.",
            details={"method": "Quit", "script_host_cleanup": script_host_cleanup},
        )
    cleanup_data = (
        {"embedded_script_hosts_terminated": script_host_cleanup["terminated"]}
        if active_transport == "embedded_free"
        else {}
    )
    output(
        mutation_payload(
            action="quit",
            target={"kind": "resolve"},
            message="DaVinci Resolve quit successfully.",
            **cleanup_data,
        )
    )


# --- Layout Presets ---

layout_app = typer.Typer(help="Layout preset management.")
app.add_typer(layout_app, name="layout")


_LAYOUT_API_HINT = (
    "DaVinci Resolve exposes layout presets only through the DaVinci Resolve-level "
    "Load/Save/Export/Delete/ImportLayoutPreset APIs. There is no public API "
    "to list presets before selecting one."
)


def _normalize_layout_name(name: str) -> str:
    normalized = str(name or "").strip()
    if not normalized:
        raise ValidationError(
            "Layout preset name is required.",
            details={"argument": "name", "example": "cutagent layout save \"Podcast Edit\" --json"},
        )
    return normalized


def _prepare_layout_export_path(path: str) -> str:
    normalized = str(path or "").strip()
    if not normalized:
        raise ValidationError(
            "Layout export path is required.",
            details={"argument": "path", "example": "cutagent layout export \"Podcast Edit\" /tmp/podcast-layout.drfx --json"},
        )
    export_path = Path(normalized).expanduser()
    if export_path.exists() and export_path.is_dir():
        raise ValidationError(
            "Layout export path must be a file, not a directory.",
            details={"path": str(export_path)},
        )
    return str(export_path)


def _prepare_layout_import_path(path: str) -> str:
    normalized = str(path or "").strip()
    if not normalized:
        raise ValidationError(
            "Layout import path is required.",
            details={"argument": "path", "example": "cutagent layout import /tmp/podcast-layout.drfx --json"},
        )
    import_path = Path(normalized).expanduser()
    if not import_path.exists():
        raise ValidationError(
            "Layout import file does not exist.",
            details={"path": str(import_path)},
        )
    if not import_path.is_file():
        raise ValidationError(
            "Layout import path must be a file.",
            details={"path": str(import_path)},
        )
    return str(import_path)


def _layout_api_failed(method: str, *, name: str | None = None, path: str | None = None, result=None) -> APICallFailed:
    return APICallFailed(
        f"DaVinci Resolve {method} failed for layout preset.",
        details={
            "api_method": method,
            "layout_name": name,
            "path": path,
            "api_result": result,
            "hint": _LAYOUT_API_HINT,
        },
    )


def _call_layout_api(conn, method: str, *args, name: str | None = None, path: str | None = None):
    func = getattr(conn.resolve, method, None)
    if not callable(func):
        raise _layout_api_failed(method, name=name, path=path, result="method_not_available")
    try:
        result = func(*args)
    except Exception as exc:
        raise _layout_api_failed(method, name=name, path=path, result=str(exc)) from exc
    if result is False:
        raise _layout_api_failed(method, name=name, path=path, result=False)
    return result


@layout_app.command("load")
@handle_errors
def layout_load(
    name: str = typer.Argument(..., help="Layout preset name"),
):
    """Load a layout preset."""
    layout_name = _normalize_layout_name(name)
    enforce_mutation_policy("system.layout_preset", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        output(mutation_payload(
            action="layout.load",
            target={"kind": "layout", "name": layout_name},
            changed=False,
            message=f"DRY-RUN: would load layout preset '{layout_name}'.",
        ))
        return
    conn = get_connection(require_project=False)
    result = _call_layout_api(conn, "LoadLayoutPreset", layout_name, name=layout_name)
    set_verification_status("verified")
    output(
        mutation_payload(
            action="layout.load",
            target={"kind": "layout", "name": layout_name},
            verification_status="verified",
            api_method="LoadLayoutPreset",
            api_result=result,
            message=f"Loaded layout: {layout_name}",
        )
    )


@layout_app.command("save")
@layout_app.command("update")
@handle_errors
def layout_save(
    name: str = typer.Argument(..., help="Layout preset name"),
):
    """Save or update the current layout as a preset."""
    layout_name = _normalize_layout_name(name)
    enforce_mutation_policy("system.layout_preset", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        output(mutation_payload(
            action="layout.save",
            target={"kind": "layout", "name": layout_name},
            changed=False,
            message=f"DRY-RUN: would save current layout as '{layout_name}'.",
        ))
        return
    conn = get_connection(require_project=False)
    result = _call_layout_api(conn, "SaveLayoutPreset", layout_name, name=layout_name)
    set_verification_status("verified")
    output(
        mutation_payload(
            action="layout.save",
            target={"kind": "layout", "name": layout_name},
            verification_status="verified",
            api_method="SaveLayoutPreset",
            api_result=result,
            message=f"Saved layout: {layout_name}",
        )
    )


@layout_app.command("delete")
@handle_errors
def layout_delete(
    name: str = typer.Argument(..., help="Layout preset name"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
):
    """Delete a layout preset."""
    layout_name = _normalize_layout_name(name)
    enforce_mutation_policy("system.layout_preset", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        output(mutation_payload(
            action="layout.delete",
            target={"kind": "layout", "name": layout_name},
            changed=False,
            message=f"DRY-RUN: would delete layout preset '{layout_name}'.",
        ))
        return
    if not force:
        if is_machine_mode():
            raise ConfirmationRequired(
                "Machine-mode mutation requires --force.",
                details={"action": "layout.delete", "target_kind": "layout", "target_name": layout_name},
            )
        confirm = typer.confirm(f"Delete layout preset '{layout_name}'?")
        if not confirm:
            raise typer.Abort()
    
    conn = get_connection(require_project=False)
    result = _call_layout_api(conn, "DeleteLayoutPreset", layout_name, name=layout_name)
    set_verification_status("verified")
    output(
        mutation_payload(
            action="layout.delete",
            target={"kind": "layout", "name": layout_name},
            verification_status="verified",
            api_method="DeleteLayoutPreset",
            api_result=result,
            message=f"Deleted layout: {layout_name}",
        )
    )


@layout_app.command("export")
@handle_errors
def layout_export(
    name: str = typer.Argument(..., help="Layout preset name"),
    path: str = typer.Argument(..., help="Export path"),
):
    """Export a layout preset to file."""
    layout_name = _normalize_layout_name(name)
    export_path = _prepare_layout_export_path(path)
    enforce_mutation_policy("system.layout_preset", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        output(mutation_payload(
            action="layout.export",
            target={"kind": "layout", "name": layout_name},
            changed=False,
            path=export_path,
            message=f"DRY-RUN: would export layout preset '{layout_name}' to '{export_path}'.",
        ))
        return
    Path(export_path).parent.mkdir(parents=True, exist_ok=True)
    conn = get_connection(require_project=False)
    result = _call_layout_api(conn, "ExportLayoutPreset", layout_name, export_path, name=layout_name, path=export_path)
    if not Path(export_path).is_file():
        raise _layout_api_failed("ExportLayoutPreset", name=layout_name, path=export_path, result="export_file_missing")
    set_verification_status("verified")
    output(
        mutation_payload(
            action="layout.export",
            target={"kind": "layout", "name": layout_name},
            verification_status="verified",
            api_method="ExportLayoutPreset",
            api_result=result,
            path=export_path,
            message=f"Exported layout '{layout_name}' to: {export_path}",
        )
    )


@layout_app.command("import")
@handle_errors
def layout_import(
    path: str = typer.Argument(..., help="Layout preset file path"),
    name: str | None = typer.Argument(None, help="Preset name (optional)"),
):
    """Import a layout preset from file."""
    import_path = _prepare_layout_import_path(path)
    layout_name = _normalize_layout_name(name) if name is not None else None
    enforce_mutation_policy("system.layout_preset", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        output(mutation_payload(
            action="layout.import",
            target={"kind": "layout", "name": layout_name},
            changed=False,
            path=import_path,
            message=f"DRY-RUN: would import layout preset from '{import_path}'.",
        ))
        return

    conn = get_connection(require_project=False)
    args = (import_path, layout_name) if layout_name is not None else (import_path,)
    result = _call_layout_api(conn, "ImportLayoutPreset", *args, name=layout_name, path=import_path)
    set_verification_status("verified")
    output(
        mutation_payload(
            action="layout.import",
            target={"kind": "layout", "name": layout_name},
            verification_status="verified",
            api_method="ImportLayoutPreset",
            api_result=result,
            path=import_path,
            message=f"Imported layout from: {import_path}",
        )
    )


# --- LUT Management ---

@app.command("lut-refresh")
@handle_errors
def lut_refresh():
    """Refresh the LUT list in the current project."""
    enforce_mutation_policy("system.lut_refresh", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        output(mutation_payload(
            action="lut.refresh",
            changed=False,
            message="DRY-RUN: would refresh LUT list.",
        ))
        return
    conn = get_connection(require_project=True)
    refresher = getattr(conn.project, "RefreshLUTList", None)
    if not callable(refresher):
        raise APICallFailed(
            "RefreshLUTList is not available.",
            details={"api_method": "RefreshLUTList", "api_result": "method_not_available"},
        )
    try:
        result = refresher()
    except Exception as exc:
        raise APICallFailed(
            "RefreshLUTList failed.",
            details={"api_method": "RefreshLUTList", "api_result": str(exc)},
        ) from exc
    if result is False:
        raise APICallFailed(
            "RefreshLUTList returned False.",
            details={"api_method": "RefreshLUTList", "api_result": False},
        )
    set_verification_status("pending_manual")
    output(
        mutation_payload(
            action="lut.refresh",
            verification_status="pending_manual",
            api_method="RefreshLUTList",
            api_result=result,
            message="Refreshed LUT list.",
        ),
        quiet_key="message",
    )


@app.command()
@handle_errors
def doctor(
    full: bool = typer.Option(False, "--full", help="Include full external tool version details"),
):
    """Run environment readiness checks for DaVinci Resolve automation."""
    checks = []
    verbose = is_verbose() or full
    transports = transport_status()

    # DaVinci Resolve runtime
    try:
        conn = get_connection(require_project=False)
        checks.append(
            {
                "check": "resolve_connection",
                "ok": True,
                "details": _doctor_resolve_context(conn),
            }
        )
    except Exception as exc:
        checks.append(
            {
                "check": "resolve_connection",
                "ok": False,
                "details": {"error": str(exc)},
            }
        )

    # Scripting module availability
    try:
        if import_resolve_script() is None:
            raise ImportError(get_resolve_script_import_error() or "DaVinciResolveScript module not found")
        checks.append({"check": "scripting_module", "ok": True, "details": {"transport": "studio_external"}})
    except Exception as exc:
        checks.append({"check": "scripting_module", "ok": False, "details": {"error": str(exc), "transport": "studio_external"}})

    embedded_script = installed_script_status()
    checks.append(
        {
            "check": "embedded_script_installed",
            "ok": bool(embedded_script.get("current")),
            "details": embedded_script,
        }
    )
    checks.append(
        {
            "check": "embedded_bridge_runtime",
            "ok": bool(transports.get("embedded_free", {}).get("connected")),
            "details": transports.get("embedded_free", {}),
        }
    )

    # External tools
    for tool in ("ffmpeg", "ffprobe"):
        try:
            details = probe_tool_version(tool)
            compact_details = {
                "tool": details.get("tool"),
                "path": details.get("path"),
                "ok": details.get("ok", True),
            }
            if verbose and "version" in details:
                compact_details["version"] = details["version"]
            checks.append({"check": f"{tool}_binary", "ok": True, "details": compact_details})
        except Exception as exc:
            checks.append(
                {
                    "check": f"{tool}_binary",
                    "ok": False,
                    "details": {"error": str(exc)},
                }
            )

    # Permission guidance (macOS-first static precheck)
    checks.append(
        {
            "check": "macos_permissions",
            "ok": True,
            "details": {
                "note": "Verify Accessibility, Automation and Screen Recording permissions for GUI automation providers.",
            },
        }
    )

    runtime_ok = any(
        check["check"] in {"resolve_connection", "embedded_bridge_runtime"} and check.get("ok")
        for check in checks
    )
    report = {"ok": runtime_ok and all(c["ok"] for c in checks if c["check"] not in {"scripting_module", "embedded_script_installed", "embedded_bridge_runtime"}), "checks": checks, "transports": transports}
    if report["ok"]:
        output(report, title="Doctor")
        return

    failed_checks = [check for check in checks if not check.get("ok", False)]
    raise ReadinessFailed(
        "Doctor readiness checks failed.",
        details={
            **report,
            "failed_checks": failed_checks,
        },
    )


@app.command()
@handle_errors
def capabilities(
    feature_id: str | None = typer.Argument(None, help="Optional capability/feature id lookup"),
    full: bool = typer.Option(False, "--full", help="Return the full capability payload"),
):
    """Machine-readable capability matrix for agent routing."""
    transports = transport_status()
    active_transport = transports.get("active_transport")
    try:
        payload = get_capabilities(transport=active_transport, transport_status=transports)
    except TypeError:
        payload = get_capabilities()
    if feature_id:
        feature = payload.get("feature_graph", {}).get(feature_id)
        if feature is None:
            raise ValidationError(
                f"Unknown feature id '{feature_id}'.",
                details={"feature_id": feature_id},
            )
        output(
            {
                "feature_id": feature_id,
                **feature,
            },
            title="Capability",
        )
        return

    if full or is_verbose():
        output(payload, title="Capabilities")
        return

    compact = {
        "capabilities_schema_version": payload["capabilities_schema_version"],
        "feature_count": len(payload["feature_graph"]),
        "feature_graph": payload["feature_graph"],
    }
    output(compact, title="Capabilities")
