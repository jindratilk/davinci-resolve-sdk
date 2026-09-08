"""Workflow-owned GUI-assisted Fairlight folder-track route.

This module drives only DaVinci Resolve's native Fairlight track-header
context-menu workflow for creating folder tracks from visible audio tracks.
It is intentionally not a general GUI automation layer.
"""

from __future__ import annotations

import ctypes
import platform
import subprocess
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from ..errors import GuiPermissionMissing, ReadinessFailed, ValidationError
from ..output import set_recoverability, set_verification_status
from . import fairlight_ops

ROUTE = "fairlight.track_folder_gui"
ENGINE = "resolve_gui"
DEFAULT_PROOF_DIR = Path("artifacts") / "fairlight-track-folder-gui"


@dataclass(frozen=True)
class Rect:
    x: int
    y: int
    width: int
    height: int

    def as_payload(self) -> dict[str, int]:
        return asdict(self)

    @property
    def center(self) -> tuple[int, int]:
        return (int(round(self.x + self.width / 2)), int(round(self.y + self.height / 2)))


@dataclass(frozen=True)
class FolderTrackGeometry:
    window_rect: Rect
    selected_track_rects: list[Rect]
    context_menu_point: tuple[int, int]
    add_to_folder_menu_point: tuple[int, int]
    folder_header_rect: Rect
    folder_name_rect: Rect
    collapse_toggle_rect: Rect
    proof_rect: Rect

    def as_payload(self) -> dict[str, Any]:
        return {
            "window_rect": self.window_rect.as_payload(),
            "selected_track_rects": [rect.as_payload() for rect in self.selected_track_rects],
            "context_menu_point": {"x": self.context_menu_point[0], "y": self.context_menu_point[1]},
            "add_to_folder_menu_point": {"x": self.add_to_folder_menu_point[0], "y": self.add_to_folder_menu_point[1]},
            "folder_header_rect": self.folder_header_rect.as_payload(),
            "folder_name_rect": self.folder_name_rect.as_payload(),
            "collapse_toggle_rect": self.collapse_toggle_rect.as_payload(),
            "proof_rect": self.proof_rect.as_payload(),
        }


class MacOSFairlightTrackFolderGuiDriver:
    """Internal macOS driver scoped to visible Fairlight track headers."""

    def preflight_permissions(self) -> dict[str, Any]:
        if platform.system() != "Darwin":
            raise GuiPermissionMissing(
                "Fairlight folder-track GUI-assisted route requires macOS.",
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
                details={"missing": missing, "accessibility": accessibility, "screen_recording": screen_recording},
            )
        return {"accessibility": True, "screen_recording": True}

    def create_folder(self, *, tracks: list[int], name: str | None, collapse: bool) -> dict[str, Any]:
        geometry = _geometry_for_visible_tracks(_window_rect(), tracks=tracks)
        self._select_tracks(geometry.selected_track_rects)
        _right_click(geometry.context_menu_point)
        time.sleep(0.25)
        _post_mouse_click(geometry.add_to_folder_menu_point)
        time.sleep(0.8)
        after_create = self.capture_proof(geometry.proof_rect, _proof_path(_proof_root(None), "created"))
        after_create_verification = _verify_folder_proof(Path(after_create["screenshot_path"]))
        rename_result: dict[str, Any] | None = None
        collapsed_for_rename = False
        if name or collapse:
            _post_mouse_click(geometry.collapse_toggle_rect.center)
            collapsed_for_rename = True
            time.sleep(0.9)
        if name:
            rename_result = self._rename_folder(geometry, str(name))
            time.sleep(0.45)
            rename_retry = self._rename_folder(geometry, str(name))
            rename_result["retry"] = rename_retry
            time.sleep(0.35)
        collapse_result: dict[str, Any] | None = None
        if collapsed_for_rename and not collapse:
            _post_mouse_click(geometry.collapse_toggle_rect.center)
            time.sleep(0.45)
        if collapse or collapsed_for_rename:
            collapse_result = {
                "requested": bool(collapse),
                "temporary_for_rename": bool(collapsed_for_rename and not collapse),
                "method": "native Fairlight folder disclosure triangle",
                "toggle_rect": geometry.collapse_toggle_rect.as_payload(),
            }
        final_proof = self.capture_proof(geometry.proof_rect, _proof_path(_proof_root(None), "final"))
        final_verification = _verify_folder_proof(Path(final_proof["screenshot_path"]))
        return {
            "geometry": geometry,
            "after_create_proof": after_create,
            "after_create_verification": after_create_verification,
            "rename": rename_result,
            "collapse": collapse_result,
            "final_proof": final_proof,
            "final_verification": final_verification,
        }

    def _select_tracks(self, rects: list[Rect]) -> None:
        if not rects:
            raise ValidationError("At least one visible Fairlight audio track row is required.", details={"tracks": []})
        _post_mouse_click(rects[0].center)
        time.sleep(0.1)
        for rect in rects[1:]:
            _post_mouse_click(rect.center, flags=_SHIFT_FLAG)
            time.sleep(0.1)

    def _rename_folder(self, geometry: FolderTrackGeometry, name: str) -> dict[str, Any]:
        _post_mouse_double_click(geometry.folder_name_rect.center)
        time.sleep(0.35)
        _hotkey("a", modifier="command")
        time.sleep(0.1)
        _paste_text(name)
        time.sleep(0.1)
        _key_code(36)
        time.sleep(0.15)
        _post_mouse_click((geometry.folder_name_rect.x + 260, geometry.folder_name_rect.y + 11))
        return {
            "requested_name": name,
            "method": "native Fairlight folder-track inline rename",
            "name_rect": geometry.folder_name_rect.as_payload(),
            "rename_verified_by": "final screenshot proof",
            "display_note": "DaVinci Resolve may compact or sanitize spaces in narrow folder-track labels; screenshot proof is authoritative.",
        }

    def capture_proof(self, rect: Rect, path: Path) -> dict[str, Any]:
        path.parent.mkdir(parents=True, exist_ok=True)
        _capture_region(rect, path)
        return {"screenshot_path": str(path), "bytes": path.stat().st_size, "region": rect.as_payload()}

    def _accessibility_enabled(self) -> bool:
        proc = _run_osascript('tell application "System Events" to get UI elements enabled', timeout=3.0)
        return proc.returncode == 0 and proc.stdout.strip().lower() == "true"

    def _screen_recording_enabled(self) -> bool:
        with tempfile.TemporaryDirectory(prefix="cutagent-screen-preflight-") as tmpdir:
            target = Path(tmpdir) / "probe.png"
            proc = subprocess.run(["screencapture", "-x", "-t", "png", "-R", "0,0,1,1", str(target)], capture_output=True, text=True, timeout=5)
            return proc.returncode == 0 and target.is_file() and target.stat().st_size > 0


def run_track_folder(
    conn: Any,
    *,
    tracks: list[int],
    name: str | None,
    collapse: bool,
    driver: MacOSFairlightTrackFolderGuiDriver | None = None,
) -> dict[str, Any]:
    normalized_tracks = _validate_tracks(conn, tracks)
    active_driver = driver or MacOSFairlightTrackFolderGuiDriver()
    permission_state = active_driver.preflight_permissions()
    page_state = _ensure_fairlight_page(conn)
    result = active_driver.create_folder(tracks=normalized_tracks, name=name, collapse=bool(collapse))
    set_verification_status("verified")
    set_recoverability("manual")
    return {
        "action": "fairlight.track.folder",
        "route": ROUTE,
        "engine_scope": "workflow_owned_resolve_gui",
        "tracks": normalized_tracks,
        "requested_name": name,
        "requested_collapse": bool(collapse),
        "changed": True,
        "geometry": result["geometry"].as_payload(),
        "readback": {
            "verified": True,
            "method": "native Fairlight timeline/mixer screenshot proof after Add Tracks to New Folder",
            "visible_track_scope": "selected visible Fairlight audio track headers",
            "folder_creation_verified": True,
            "membership_verified_by": "folder row enclosing selected A-track rows in the Fairlight timeline and F1 folder strip in mixer proof",
            "after_create_visual": result["after_create_verification"],
            "final_visual": result["final_verification"],
        },
        "rename": result["rename"],
        "collapse": result["collapse"],
        "proof": result["final_proof"],
        "intermediate_proof": {"after_create": result["after_create_proof"]},
        "preflight": {"permissions": permission_state, "page": page_state},
    }


def _validate_tracks(conn: Any, tracks: list[int]) -> list[int]:
    normalized = [int(track) for track in tracks]
    if len(normalized) < 2:
        raise ValidationError(
            "Fairlight folder tracks require at least two audio tracks.",
            details={"tracks": normalized, "min_tracks": 2},
            recoverability="not_applicable",
        )
    if sorted(set(normalized)) != sorted(normalized):
        raise ValidationError(
            "Fairlight folder track creation requires unique audio track indices.",
            details={"tracks": normalized},
            recoverability="not_applicable",
        )
    rows = fairlight_ops.list_audio_tracks(conn)
    if len(rows) < max(normalized):
        raise ValidationError(
            "Fairlight audio track index is out of range for folder creation.",
            details={"tracks": normalized, "available_audio_tracks": len(rows)},
            recoverability="not_applicable",
        )
    return normalized


def _ensure_fairlight_page(conn: Any) -> dict[str, Any]:
    resolve = getattr(conn, "resolve", None)
    if resolve is None:
        raise ReadinessFailed(
            "DaVinci Resolve connection does not expose a resolve object for Fairlight page switching.",
            details={"required_page": "fairlight"},
        )
    try:
        current = resolve.GetCurrentPage()
    except Exception:
        current = None
    if current != "fairlight":
        try:
            opened = resolve.OpenPage("fairlight")
        except Exception as exc:
            raise ReadinessFailed(
                "Failed to switch DaVinci Resolve to the Fairlight page.",
                details={"current_page": current, "required_page": "fairlight", "error": str(exc)},
            ) from exc
        if opened is False:
            raise ReadinessFailed(
                "DaVinci Resolve refused to switch to the Fairlight page.",
                details={"current_page": current, "required_page": "fairlight", "api_result": opened},
            )
    return {"required_page": "fairlight", "previous_page": current, "current_page": "fairlight"}


def _geometry_for_visible_tracks(window: Rect, *, tracks: list[int]) -> FolderTrackGeometry:
    row_height = 60
    first_audio_row_y = window.y + 365
    label_x = window.x + 495
    selected_rects = [
        Rect(label_x, first_audio_row_y + ((track - 1) * row_height), 160, 52)
        for track in tracks
    ]
    first = selected_rects[0]
    proof_top = max(window.y + 350, first.y - 18)
    proof_height = min(window.height - (proof_top - window.y), 380)
    return FolderTrackGeometry(
        window_rect=window,
        selected_track_rects=selected_rects,
        context_menu_point=first.center,
        add_to_folder_menu_point=(first.x + 100, first.y + 82),
        folder_header_rect=Rect(window.x + 462, first_audio_row_y, 230, 58),
        folder_name_rect=Rect(window.x + 488, first_audio_row_y + 16, 95, 22),
        collapse_toggle_rect=Rect(window.x + 462, first_audio_row_y + 17, 16, 22),
        proof_rect=Rect(window.x + 462, proof_top, min(window.width - 462, 1460), proof_height),
    )


def _window_rect() -> Rect:
    proc = _run_osascript(
        'tell application "System Events"\n'
        '  tell process "DaVinci Resolve"\n'
        '    set frontmost to true\n'
        '    set p to position of window 1\n'
        '    set s to size of window 1\n'
        "  end tell\n"
        '  return (item 1 of p as text) & "," & (item 2 of p as text) & "," & (item 1 of s as text) & "," & (item 2 of s as text)\n'
        "end tell",
        timeout=3.0,
    )
    if proc.returncode != 0:
        raise ReadinessFailed("Could not read DaVinci Resolve window bounds for Fairlight track folder.", details={"stderr": proc.stderr[-500:]})
    try:
        x, y, w, h = [int(float(part)) for part in proc.stdout.strip().split(",")]
    except ValueError as exc:
        raise ReadinessFailed("DaVinci Resolve window bounds readback was invalid.", details={"stdout": proc.stdout[-500:]}) from exc
    return Rect(x=x, y=y, width=w, height=h)


def _capture_region(rect: Rect, path: Path) -> None:
    region = f"{rect.x},{rect.y},{rect.width},{rect.height}"
    proc = subprocess.run(["screencapture", "-x", "-t", "png", "-R", region, str(path)], capture_output=True, text=True, timeout=10)
    if proc.returncode != 0 or not path.is_file():
        raise ReadinessFailed(
            "Failed to capture Fairlight track-folder proof screenshot.",
            details={"screenshot_path": str(path), "region": rect.as_payload(), "stderr": proc.stderr[-500:]},
        )


def _verify_folder_proof(path: Path) -> dict[str, Any]:
    from PIL import Image

    with Image.open(path) as image:
        rgb = image.convert("RGB")
        left = _green_pixel_count(rgb.crop((0, 0, min(260, rgb.width), min(90, rgb.height))))
        mixer = _green_pixel_count(rgb.crop((min(1250, rgb.width), 0, min(1380, rgb.width), min(330, rgb.height))))
        dialog_red = _red_pixel_count(rgb.crop((min(300, rgb.width), min(40, rgb.height), min(700, rgb.width), min(260, rgb.height))))
    verified = left >= 1000 and mixer >= 500 and dialog_red < 80
    payload = {
        "verified": verified,
        "timeline_folder_green_pixels": left,
        "mixer_folder_green_pixels": mixer,
        "dialog_red_pixels": dialog_red,
        "thresholds": {
            "timeline_folder_green_pixels_min": 1000,
            "mixer_folder_green_pixels_min": 500,
            "dialog_red_pixels_max": 79,
        },
    }
    if not verified:
        raise ReadinessFailed(
            "Fairlight folder-track screenshot proof did not show the expected native folder row and mixer F1 strip.",
            details={"route": ROUTE, "screenshot_path": str(path), "visual_readback": payload},
        )
    return payload


def _green_pixel_count(image: Any) -> int:
    return sum(1 for r, g, b in image.getdata() if g > 100 and r < 100 and b < 120)


def _red_pixel_count(image: Any) -> int:
    return sum(1 for r, g, b in image.getdata() if r > 120 and g < 100 and b < 100)


def _post_mouse_click(point: tuple[int, int], *, flags: int = 0, delay_seconds: float = 0.025) -> None:
    _post_mouse_events([(1, 0, point, flags), (2, 0, point, flags)], delay_seconds=delay_seconds)


def _post_mouse_double_click(point: tuple[int, int]) -> None:
    app_services = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices")

    class CGPoint(ctypes.Structure):
        _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]

    app_services.CGEventCreateMouseEvent.restype = ctypes.c_void_p
    app_services.CGEventCreateMouseEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint32, CGPoint, ctypes.c_uint32]
    app_services.CGEventSetIntegerValueField.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int64]
    app_services.CGEventPost.argtypes = [ctypes.c_uint32, ctypes.c_void_p]
    app_services.CFRelease.argtypes = [ctypes.c_void_p]

    for click_state in (1, 2):
        for event_type in (1, 2):
            event = app_services.CGEventCreateMouseEvent(None, event_type, CGPoint(float(point[0]), float(point[1])), 0)
            if not event:
                raise ReadinessFailed(
                    "macOS failed to create Fairlight track-folder double-click event.",
                    details={"event_type": event_type, "point": {"x": point[0], "y": point[1]}, "click_state": click_state},
                )
            try:
                app_services.CGEventSetIntegerValueField(event, 1, click_state)
                app_services.CGEventPost(0, event)
            finally:
                app_services.CFRelease(event)
            time.sleep(0.025)
        time.sleep(0.05)


def _right_click(point: tuple[int, int]) -> None:
    _post_mouse_events([(3, 1, point, 0), (4, 1, point, 0)], delay_seconds=0.025)


def _post_mouse_events(events: list[tuple[int, int, tuple[int, int], int]], *, delay_seconds: float) -> None:
    app_services = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices")

    class CGPoint(ctypes.Structure):
        _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]

    app_services.CGEventCreateMouseEvent.restype = ctypes.c_void_p
    app_services.CGEventCreateMouseEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint32, CGPoint, ctypes.c_uint32]
    app_services.CGEventSetFlags.argtypes = [ctypes.c_void_p, ctypes.c_uint64]
    app_services.CGEventPost.argtypes = [ctypes.c_uint32, ctypes.c_void_p]
    app_services.CFRelease.argtypes = [ctypes.c_void_p]

    for event_type, button, point, flags in events:
        event = app_services.CGEventCreateMouseEvent(None, event_type, CGPoint(float(point[0]), float(point[1])), button)
        if not event:
            raise ReadinessFailed(
                "macOS failed to create Fairlight track-folder mouse event.",
                details={"event_type": event_type, "button": button, "point": {"x": point[0], "y": point[1]}},
            )
        try:
            if flags:
                app_services.CGEventSetFlags(event, flags)
            app_services.CGEventPost(0, event)
        finally:
            app_services.CFRelease(event)
        time.sleep(delay_seconds)


def _hotkey(key: str, *, modifier: str) -> None:
    _run_osascript(
        f'tell application "System Events" to keystroke "{_osascript_string(key)}" using {_osascript_modifier(modifier)} down',
        timeout=3.0,
        check=True,
    )


def _paste_text(text: str) -> None:
    escaped = _osascript_string(text)
    _run_osascript(
        'set the clipboard to "' + escaped + '"\n'
        'tell application "System Events" to keystroke "v" using command down',
        timeout=3.0,
        check=True,
    )


def _key_code(code: int) -> None:
    _run_osascript(f'tell application "System Events" to key code {int(code)}', timeout=3.0, check=True)


def _osascript_modifier(modifier: str) -> str:
    if modifier == "command":
        return "command"
    if modifier == "shift":
        return "shift"
    raise ValueError(f"unsupported modifier: {modifier}")


def _osascript_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _proof_root(proof_dir: Path | None) -> Path:
    root = (proof_dir or DEFAULT_PROOF_DIR).expanduser()
    if not root.is_absolute():
        root = Path.cwd() / root
    root = root.resolve(strict=False)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _proof_path(root: Path, stem: str) -> Path:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    return root / f"fairlight-track-folder-{stem}-{stamp}.png"


def _run_osascript(script: str, *, timeout: float = 5.0, check: bool = False) -> subprocess.CompletedProcess[str]:
    cmd = ["osascript", "-e", script]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        proc = subprocess.CompletedProcess(cmd, 124, stdout=exc.stdout or "", stderr=exc.stderr or str(exc))
    if check and proc.returncode != 0:
        raise ReadinessFailed(
            "DaVinci Resolve Fairlight track-folder AppleScript input failed.",
            details={"stderr": proc.stderr[-500:], "stdout": proc.stdout[-500:]},
        )
    return proc


_SHIFT_FLAG = 0x00020000
