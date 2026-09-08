"""Workflow-owned GUI-assisted native Color Page Auto Color route."""

from __future__ import annotations

import ctypes
import platform
import subprocess
import time
from pathlib import Path
from typing import Any

from ..errors import GuiPermissionMissing, ReadinessFailed, ResolveWindowNotFound, ValidationError
from ..output import set_recoverability, set_verification_status

ROUTE = "ai_neural.auto_color_ai_gui"
ENGINE = "resolve_gui"
DEFAULT_PROOF_DIR = Path("artifacts") / "auto-color-ai-proof"
PROCESS_NAMES = ("DaVinci Resolve", "Resolve")


class MacOSAutoColorAiGuiDriver:
    process_names = PROCESS_NAMES

    def preflight_permissions(self) -> dict[str, Any]:
        if platform.system() != "Darwin":
            raise GuiPermissionMissing(
                "Native DaVinci Resolve Auto Color GUI route requires macOS.",
                details={"platform": platform.system(), "required": ["macOS"]},
            )
        accessibility = self._accessibility_enabled()
        if not accessibility:
            raise GuiPermissionMissing(
                "Enable macOS Accessibility for the process running CutAgent CLI.",
                details={"missing": ["Accessibility"], "accessibility": accessibility, "target_process_names": list(self.process_names)},
            )
        return {"accessibility": True}

    def click_auto_color(self) -> dict[str, Any]:
        return self._click_menu_item("Color", "Auto Color")

    def click_undo(self) -> dict[str, Any]:
        return self._click_menu_item("Edit", "Undo")

    def _click_menu_item(self, top_level: str, item_name: str) -> dict[str, Any]:
        script = f'''
tell application "System Events"
  tell process "Resolve"
    set frontmost to true
    set mi to menu item "{item_name}" of menu 1 of menu bar item "{top_level}" of menu bar 1
    if enabled of mi is false then error "disabled: {top_level} > {item_name}"
    click mi
  end tell
end tell
'''
        proc = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=10)
        if proc.returncode != 0:
            raise ReadinessFailed(
                "Could not invoke native DaVinci Resolve menu item.",
                details={
                    "menu_path": f"{top_level} > {item_name}",
                    "stderr": proc.stderr[-500:],
                    "stdout": proc.stdout[-500:],
                },
            )
        return {
            "method": "native_menu_item_click",
            "menu_path": f"{top_level} > {item_name}",
            "stdout": proc.stdout.strip(),
        }

    def _accessibility_enabled(self) -> bool:
        proc = subprocess.run(
            ["osascript", "-e", 'tell application "System Events" to get UI elements enabled'],
            capture_output=True,
            text=True,
            timeout=3,
        )
        return proc.returncode == 0 and proc.stdout.strip().lower() == "true"

    def _accessibility_trusted(self) -> bool:
        try:
            app_services = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices")
            app_services.AXIsProcessTrusted.restype = ctypes.c_bool
            return bool(app_services.AXIsProcessTrusted())
        except Exception:
            return False


def ensure_color_page(conn: Any) -> dict[str, Any]:
    resolve = getattr(conn, "resolve", None)
    if resolve is None:
        raise ReadinessFailed("DaVinci Resolve connection does not expose a resolve object.", details={"required_page": "color"})
    try:
        current = resolve.GetCurrentPage()
    except Exception:
        current = None
    if current != "color":
        try:
            opened = resolve.OpenPage("color")
        except Exception as exc:
            raise ReadinessFailed(
                "Failed to switch DaVinci Resolve to the Color page.",
                details={"current_page": current, "required_page": "color", "error": str(exc)},
            ) from exc
        if opened is False:
            raise ReadinessFailed(
                "DaVinci Resolve refused to switch to the Color page.",
                details={"current_page": current, "required_page": "color", "api_result": opened},
            )
    try:
        final = resolve.GetCurrentPage()
    except Exception:
        final = "color"
    if final != "color":
        raise ReadinessFailed("DaVinci Resolve is not on the Color page.", details={"current_page": final, "required_page": "color"})
    return {"required_page": "color", "previous_page": current, "current_page": final}


def verify_current_clip_target(conn: Any, clip_name: str | None) -> dict[str, Any]:
    timeline = getattr(conn, "timeline", None)
    current = None
    if timeline is not None and hasattr(timeline, "GetCurrentVideoItem"):
        try:
            current = timeline.GetCurrentVideoItem()
        except Exception:
            current = None
    current_name = None
    if current is not None and hasattr(current, "GetName"):
        try:
            current_name = current.GetName()
        except Exception:
            current_name = None
    requested = str(clip_name).strip() if clip_name else None
    if requested and current_name and requested not in {current_name, Path(current_name).name}:
        raise ValidationError(
            "Native Auto Color GUI route can only target the current Color Page clip.",
            details={"requested_clip": requested, "current_clip": current_name},
            recoverability="manual",
        )
    return {"kind": "current_color_page_clip", "requested_clip": requested, "current_clip": current_name}


def proof_root(proof_dir: Path | None) -> Path:
    root = (proof_dir or DEFAULT_PROOF_DIR).expanduser()
    if not root.is_absolute():
        root = Path.cwd() / root
    root.mkdir(parents=True, exist_ok=True)
    return root


def process_ready() -> None:
    script = '''
tell application "System Events"
  if exists process "Resolve" then return "ok"
  if exists process "DaVinci Resolve" then return "ok"
  error "DaVinci Resolve process not found"
end tell
'''
    proc = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=5)
    if proc.returncode != 0:
        raise ResolveWindowNotFound("DaVinci Resolve process was not found.", details={"stderr": proc.stderr[-500:]})


def wait_for_auto_color(seconds: float = 4.0) -> None:
    time.sleep(max(0.0, float(seconds)))


def mark_verified() -> None:
    set_verification_status("verified")
    set_recoverability("manual")
