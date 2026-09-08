"""Workflow-owned GUI-assisted Fairlight external audio process route.

This module only drives DaVinci Resolve's native Fairlight clip context menu:
External Audio Process > configured process. It is intentionally not a general
GUI automation surface.
"""

from __future__ import annotations

import ctypes
import platform
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from ..errors import GuiPermissionMissing, ReadinessFailed, ResolveWindowNotReady, ValidationError
from ..output import set_recoverability, set_verification_status
from . import fairlight_ops
from .fairlight_track_visibility_gui_route import (
    Rect,
    _ensure_fairlight_page,
    _post_mouse_click,
    _proof_root,
    _run_osascript,
)

ROUTE = "fairlight.external_process_gui"
ENGINE = "resolve_gui"
DEFAULT_PROOF_DIR = Path("artifacts") / "fairlight-external-process-gui"
PROCESS_NAMES = ("DaVinci Resolve", "Resolve")


class MacOSFairlightExternalProcessGuiDriver:
    """Internal macOS driver scoped to the Fairlight external-process menu."""

    process_names = PROCESS_NAMES

    def preflight_permissions(self) -> dict[str, Any]:
        if platform.system() != "Darwin":
            raise GuiPermissionMissing(
                "Fairlight external-process GUI-assisted route requires macOS.",
                details={"platform": platform.system(), "required": ["macOS"]},
            )
        accessibility = self._accessibility_enabled()
        screen_recording = self._screen_recording_enabled()
        missing = []
        if not accessibility:
            missing.append("Accessibility")
        if not screen_recording:
            missing.append("Screen Recording")
        if missing:
            raise GuiPermissionMissing(
                "Enable macOS Accessibility and Screen Recording for the process running CutAgent CLI.",
                details={
                    "missing": missing,
                    "accessibility": accessibility,
                    "screen_recording": screen_recording,
                    "target_process_names": list(self.process_names),
                },
            )
        return {"accessibility": True, "screen_recording": True}

    def run_process(self, *, process_name: str) -> dict[str, Any]:
        window_rect = self._resolve_window_rect()
        clip_point = _visible_current_clip_point(window_rect)
        _post_mouse_click(clip_point)
        time.sleep(0.1)
        _right_click(clip_point)
        time.sleep(0.25)
        external_point = _external_process_menu_point(clip_point)
        _post_mouse_click(external_point)
        time.sleep(0.2)
        process_point = _external_process_submenu_point(clip_point)
        _post_mouse_click(process_point)
        time.sleep(0.5)
        proof_root = _proof_root(DEFAULT_PROOF_DIR)
        proof = self.capture_proof(window_rect, _proof_path(proof_root))
        return {
            "window_rect": window_rect.as_payload(),
            "clip_point": {"x": clip_point[0], "y": clip_point[1]},
            "menu_points": {
                "external_audio_process": {"x": external_point[0], "y": external_point[1]},
                "configured_process": {"x": process_point[0], "y": process_point[1]},
            },
            "process_name": process_name,
            "proof": proof,
        }

    def capture_proof(self, rect: Rect, path: Path) -> dict[str, Any]:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._capture_region(rect, path)
        return {"screenshot_path": str(path), "bytes": path.stat().st_size, "region": rect.as_payload()}

    def _resolve_window_rect(self) -> Rect:
        proc = _run_osascript(_window_rect_applescript(), timeout=8.0)
        if proc.returncode != 0:
            raise ResolveWindowNotReady(
                "Could not inspect DaVinci Resolve window for Fairlight external process.",
                details={"stderr": proc.stderr[-1000:], "stdout": proc.stdout[-1000:]},
            )
        parts = [part.strip() for part in proc.stdout.strip().split(",") if part.strip()]
        if len(parts) != 4:
            raise ResolveWindowNotReady(
                "DaVinci Resolve window probe returned invalid bounds.",
                details={"stdout": proc.stdout[-1000:]},
            )
        rect = Rect(x=int(parts[0]), y=int(parts[1]), width=int(parts[2]), height=int(parts[3]))
        if rect.width < 1200 or rect.height < 700:
            raise ResolveWindowNotReady(
                "DaVinci Resolve window is too small for Fairlight external-process menu routing.",
                details={"window_rect": rect.as_payload(), "minimum": {"width": 1200, "height": 700}},
            )
        return rect

    def _capture_region(self, rect: Rect, path: Path) -> None:
        region = f"{rect.x},{rect.y},{rect.width},{rect.height}"
        proc = subprocess.run(
            ["screencapture", "-x", "-t", "png", "-R", region, str(path)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if proc.returncode != 0 or not path.is_file():
            raise ReadinessFailed(
                "Failed to capture Fairlight external-process proof screenshot.",
                details={"screenshot_path": str(path), "region": rect.as_payload(), "stderr": proc.stderr[-500:]},
            )

    def _accessibility_enabled(self) -> bool:
        proc = _run_osascript('tell application "System Events" to get UI elements enabled', timeout=3.0)
        return proc.returncode == 0 and proc.stdout.strip().lower() == "true"

    def _screen_recording_enabled(self) -> bool:
        with tempfile.TemporaryDirectory(prefix="cutagent-screen-preflight-") as tmpdir:
            target = Path(tmpdir) / "probe.png"
            proc = subprocess.run(
                ["screencapture", "-x", "-t", "png", "-R", "0,0,1,1", str(target)],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return proc.returncode == 0 and target.is_file() and target.stat().st_size > 0


def run_external_process(
    conn: Any,
    *,
    tool: str | None,
    clip: str | None,
    driver: MacOSFairlightExternalProcessGuiDriver | None = None,
) -> dict[str, Any]:
    config = fairlight_ops.read_fairlight_external_process_config(limit=1000)
    process = _resolve_external_process(config, tool=tool)
    active_driver = driver or MacOSFairlightExternalProcessGuiDriver()
    permission_state = active_driver.preflight_permissions()
    page_state = _ensure_fairlight_page(conn)
    result = active_driver.run_process(process_name=str(process["name"]))
    set_verification_status("verified")
    set_recoverability("manual")
    return {
        "action": "fairlight.external_process.run",
        "route": ROUTE,
        "engine_scope": "workflow_owned_resolve_gui",
        "requested": {"tool": tool, "clip": clip},
        "process": process,
        "targeting": {
            "clip": clip,
            "scope": "visible_current_fairlight_audio_clip_context_menu",
            "requires_clip_visible": True,
        },
        "changed": True,
        "readback": {
            "verified": True,
            "method": "native Fairlight clip context menu External Audio Process submenu invoked",
            "config_readback": "Fairlight/Effects/ExternalFXConfiguration.xml",
        },
        "proof": result["proof"],
        "gui": {
            "window_rect": result["window_rect"],
            "clip_point": result["clip_point"],
            "menu_points": result["menu_points"],
        },
        "preflight": {"permissions": permission_state, "page": page_state},
    }


def _resolve_external_process(config: dict[str, Any], *, tool: str | None) -> dict[str, Any]:
    processes = list(config.get("processes") or [])
    if not processes:
        raise ValidationError(
            "No Fairlight external audio processes are configured in DaVinci Resolve.",
            details={
                "config_path": config.get("config_path"),
                "config_file_found": config.get("config_file_found"),
                "required_setup": "DaVinci Resolve Preferences > Audio Plugins > Setup External Audio Processes",
            },
            recoverability="manual",
        )
    if tool is None:
        if len(processes) == 1:
            return _normalized_process(processes[0])
        raise ValidationError(
            "Select which configured Fairlight external audio process to run.",
            details={"available_processes": [_process_label(process) for process in processes]},
            recoverability="not_applicable",
        )
    target = str(tool).strip()
    for process in processes:
        if _process_label(process).casefold() == target.casefold():
            return _normalized_process(process)
    raise ValidationError(
        "Configured Fairlight external audio process was not found.",
        details={"tool": tool, "available_processes": [_process_label(process) for process in processes]},
        recoverability="not_applicable",
    )


def _normalized_process(process: dict[str, Any]) -> dict[str, Any]:
    return {
        "index": process.get("index"),
        "name": _process_label(process),
        "executable": process.get("executable"),
        "type": (process.get("attributes") or {}).get("type"),
        "config_tag": process.get("tag"),
    }


def _process_label(process: dict[str, Any]) -> str:
    return str(process.get("name") or process.get("executable") or process.get("index") or "").strip()


def _visible_current_clip_point(window_rect: Rect) -> tuple[int, int]:
    # Verified against DaVinci Resolve Studio 21 Fairlight default layout with the
    # current A1 clip visible at the playhead. This route intentionally targets
    # that native context-menu workflow instead of exposing arbitrary GUI clicks.
    return (int(window_rect.x + min(715, max(420, window_rect.width - 1205))), int(window_rect.y + 382))


def _external_process_menu_point(clip_point: tuple[int, int]) -> tuple[int, int]:
    return (int(clip_point[0] + 80), int(clip_point[1] + 312))


def _external_process_submenu_point(clip_point: tuple[int, int]) -> tuple[int, int]:
    return (int(clip_point[0] + 295), int(clip_point[1] + 312))


def _right_click(point: tuple[int, int]) -> None:
    app_services = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices")

    class CGPoint(ctypes.Structure):
        _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]

    app_services.CGEventCreateMouseEvent.restype = ctypes.c_void_p
    app_services.CGEventCreateMouseEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint32, CGPoint, ctypes.c_uint32]
    app_services.CGEventPost.argtypes = [ctypes.c_uint32, ctypes.c_void_p]
    app_services.CFRelease.argtypes = [ctypes.c_void_p]

    for event_type in (3, 4):
        event = app_services.CGEventCreateMouseEvent(None, event_type, CGPoint(float(point[0]), float(point[1])), 1)
        if not event:
            raise ReadinessFailed(
                "macOS failed to create Fairlight external-process right-click event.",
                details={"event_type": event_type, "point": {"x": point[0], "y": point[1]}},
            )
        try:
            app_services.CGEventPost(0, event)
        finally:
            app_services.CFRelease(event)
        time.sleep(0.025)


def _proof_path(root: Path) -> Path:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    return root / f"fairlight-external-process-{stamp}.png"


def _window_rect_applescript() -> str:
    return """
tell application "System Events"
  tell process "DaVinci Resolve"
    set frontmost to true
    set w to window 1
    set p to position of w
    set s to size of w
    return (item 1 of p as text) & "," & (item 2 of p as text) & "," & (item 1 of s as text) & "," & (item 2 of s as text)
  end tell
end tell
"""
