"""Workflow-owned GUI-assisted Fairlight track record-arm route.

This module only drives DaVinci Resolve's native Fairlight record-arm controls.
It uses the visible timeline track-header R button for arming and the visible
Index > Tracks R control for disarming, then verifies against the timeline
track-header button brightness. It does not expose a general GUI automation
surface.
"""

from __future__ import annotations

import platform
import subprocess
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from ..errors import GuiPermissionMissing, ReadinessFailed, ValidationError
from ..output import set_recoverability, set_verification_status
from . import fairlight_ops, fairlight_track_visibility_gui_route as visibility_gui

ROUTE = "fairlight.record_arm_gui"
ENGINE = "resolve_gui"
DEFAULT_PROOF_DIR = Path("artifacts") / "fairlight-record-arm-gui"
PROCESS_NAMES = ("DaVinci Resolve", "Resolve")


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
class RecordArmState:
    track: int
    armed: bool
    button_rect: Rect
    proof_rect: Rect
    brightness: dict[str, Any]

    def as_payload(self) -> dict[str, Any]:
        return {
            "track": self.track,
            "armed": self.armed,
            "button_rect": self.button_rect.as_payload(),
            "proof_rect": self.proof_rect.as_payload(),
            "brightness": self.brightness,
        }


class MacOSFairlightRecordArmGuiDriver:
    """Internal macOS driver scoped to Fairlight visible record-arm controls."""

    process_names = PROCESS_NAMES

    def preflight_permissions(self) -> dict[str, Any]:
        if platform.system() != "Darwin":
            raise GuiPermissionMissing(
                "Fairlight record-arm GUI-assisted route requires macOS.",
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

    def read_state(self, *, track: int) -> RecordArmState:
        rects = _timeline_record_arm_rects(track, window_y=self._window_y())
        brightness = self.measure_button(rects["button"])
        return RecordArmState(
            track=int(track),
            armed=_brightness_is_armed(brightness),
            button_rect=rects["button"],
            proof_rect=rects["proof"],
            brightness=brightness,
        )

    def set_arm(self, *, track: int, enable: bool) -> dict[str, Any]:
        before = self.read_state(track=track)
        clicked = False
        click_rect: Rect | None = None
        polls: list[dict[str, Any]] = []
        after = before
        if before.armed != bool(enable):
            self.activate_resolve()
            click_rect = before.button_rect if enable else self._index_record_arm_rect(track=track)
            visibility_gui._post_mouse_click(click_rect.center)
            clicked = True
            after, polls = self._poll_arm(track=track, enable=bool(enable))
        proof_root = _proof_root(None)
        proof = self.capture_proof(after.proof_rect, _proof_path(proof_root, "enable" if enable else "disable"))
        return {"clicked": clicked, "click_rect": click_rect, "before": before, "after": after, "polls": polls, "proof": proof}

    def _index_record_arm_rect(self, *, track: int) -> Rect:
        panel = visibility_gui.MacOSFairlightTrackVisibilityGuiDriver().prepare_tracks_panel(track=track)
        return _index_record_arm_rect_from_label(panel.row.label_rect)

    def _poll_arm(self, *, track: int, enable: bool) -> tuple[RecordArmState, list[dict[str, Any]]]:
        polls: list[dict[str, Any]] = []
        last: RecordArmState | None = None
        for attempt in range(1, 16):
            time.sleep(0.15)
            current = self.read_state(track=track)
            last = current
            polls.append({"attempt": attempt, "armed": current.armed, "brightness": current.brightness})
            if current.armed == enable:
                return current, polls
        set_verification_status("failed")
        raise ReadinessFailed(
            "DaVinci Resolve Fairlight record-arm button did not reach requested state.",
            details={
                "route": ROUTE,
                "track": track,
                "requested_enabled": enable,
                "last_state": last.as_payload() if last else None,
                "polls": polls,
            },
        )

    def measure_button(self, rect: Rect) -> dict[str, Any]:
        with tempfile.TemporaryDirectory(prefix="cutagent-record-arm-") as tmpdir:
            path = Path(tmpdir) / "record-arm.png"
            self._capture_region(rect, path)
            return visibility_gui._measure_png_brightness(path)

    def capture_proof(self, rect: Rect, path: Path) -> dict[str, Any]:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._capture_region(rect, path)
        return {"screenshot_path": str(path), "bytes": path.stat().st_size, "region": rect.as_payload()}

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
                "Failed to capture Fairlight record-arm proof screenshot.",
                details={"screenshot_path": str(path), "region": rect.as_payload(), "stderr": proc.stderr[-500:]},
            )

    def _accessibility_enabled(self) -> bool:
        proc = visibility_gui._run_osascript('tell application "System Events" to get UI elements enabled', timeout=3.0)
        return proc.returncode == 0 and proc.stdout.strip().lower() == "true"

    def activate_resolve(self) -> None:
        script = (
            'tell application "System Events"\n'
            '  if exists process "DaVinci Resolve" then\n'
            '    set frontmost of process "DaVinci Resolve" to true\n'
            '  else\n'
            '    set frontmost of process "Resolve" to true\n'
            "  end if\n"
            "end tell"
        )
        proc = visibility_gui._run_osascript(script, timeout=3.0)
        if proc.returncode != 0:
            raise ReadinessFailed(
                "Could not activate DaVinci Resolve for Fairlight record-arm.",
                details={"stderr": proc.stderr[-500:], "stdout": proc.stdout[-500:]},
            )
        time.sleep(0.1)

    def _window_y(self) -> int:
        script = (
            'tell application "System Events"\n'
            '  if exists process "DaVinci Resolve" then\n'
            '    tell process "DaVinci Resolve" to set windowPosition to position of window 1\n'
            '  else\n'
            '    tell process "Resolve" to set windowPosition to position of window 1\n'
            "  end if\n"
            "  return item 2 of windowPosition\n"
            "end tell"
        )
        proc = visibility_gui._run_osascript(script, timeout=3.0)
        if proc.returncode != 0:
            raise ReadinessFailed(
                "Could not read DaVinci Resolve window position for Fairlight record-arm.",
                details={"stderr": proc.stderr[-500:], "stdout": proc.stdout[-500:]},
            )
        try:
            return int(float(proc.stdout.strip()))
        except ValueError as exc:
            raise ReadinessFailed(
                "DaVinci Resolve window position readback was not numeric.",
                details={"stdout": proc.stdout[-500:]},
            ) from exc

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


def run_record_arm(
    conn: Any,
    *,
    track: int,
    enable: bool,
    driver: MacOSFairlightRecordArmGuiDriver | None = None,
) -> dict[str, Any]:
    _validate_audio_track(conn, int(track))
    active_driver = driver or MacOSFairlightRecordArmGuiDriver()
    permission_state = active_driver.preflight_permissions()
    page_state = _ensure_fairlight_page(conn)
    visibility_state = _ensure_track_visible(track=int(track))
    result = active_driver.set_arm(track=int(track), enable=bool(enable))
    set_verification_status("verified")
    set_recoverability("manual")
    return {
        "action": "fairlight.record.arm",
        "route": ROUTE,
        "engine_scope": "workflow_owned_resolve_gui",
        "track": int(track),
        "requested_enabled": bool(enable),
        "changed": bool(result["clicked"]),
        "click_rect": result["click_rect"].as_payload() if result["click_rect"] else None,
        "before": result["before"].as_payload(),
        "after": result["after"].as_payload(),
        "readback": {
            "state": "armed" if result["after"].armed else "disarmed",
            "verified": result["after"].armed == bool(enable),
            "method": "native Fairlight timeline track header record-arm screenshot brightness",
            "polls": result["polls"],
        },
        "proof": result["proof"],
        "preflight": {"permissions": permission_state, "page": page_state, "track_visibility": visibility_state},
    }


def _ensure_track_visible(*, track: int) -> dict[str, Any]:
    driver = visibility_gui.MacOSFairlightTrackVisibilityGuiDriver()
    before = driver.prepare_tracks_panel(track=int(track))
    if before.row.visible:
        return {"changed": False, "after": before.as_payload()}
    result = driver.set_visibility(track=int(track), visible=True)
    return {
        "changed": bool(result["clicked"]),
        "before": result["before"].as_payload(),
        "after": result["after"].as_payload(),
        "proof": result["proof"],
    }


def _validate_audio_track(conn: Any, track: int) -> None:
    if track < 1:
        raise ValidationError(
            "Fairlight record-arm requires an audio track index of 1 or greater.",
            details={"track": track, "min": 1},
            recoverability="not_applicable",
        )
    rows = fairlight_ops.list_audio_tracks(conn)
    if len(rows) < track:
        raise ValidationError(
            "Fairlight audio track index is out of range.",
            details={"track": track, "available_audio_tracks": len(rows)},
            recoverability="not_applicable",
        )


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
    try:
        final = resolve.GetCurrentPage()
    except Exception:
        final = "fairlight"
    if final != "fairlight":
        raise ReadinessFailed(
            "DaVinci Resolve is not on the Fairlight page after page switch.",
            details={"current_page": final, "required_page": "fairlight"},
        )
    return {"required_page": "fairlight", "previous_page": current, "current_page": final}


def _timeline_record_arm_rects(track: int, *, window_y: int = 0) -> dict[str, Rect]:
    if int(track) > 8:
        raise ValidationError(
            "Fairlight record-arm GUI route currently requires the requested audio track to be visible in the timeline track header.",
            details={"track": int(track), "visible_track_header_limit": 8},
            recoverability="manual",
        )
    row_top = int(window_y) + 365 + (int(track) - 1) * 60
    button = Rect(x=575, y=row_top + 32, width=21, height=21)
    proof = Rect(x=482, y=max(0, row_top - 2), width=178, height=60)
    return {"button": button, "proof": proof}


def _brightness_is_armed(brightness: dict[str, Any]) -> bool:
    return float(brightness.get("mean_luma") or 0.0) >= 80.0 and float(brightness.get("max_luma") or 0.0) >= 220.0


def _index_record_arm_rect_from_label(label_rect: Any) -> Rect:
    return Rect(x=int(label_rect.x) + 216, y=int(label_rect.y) + 5, width=21, height=19)


def _proof_root(proof_dir: Path | None) -> Path:
    root = (proof_dir or DEFAULT_PROOF_DIR).expanduser()
    if not root.is_absolute():
        root = Path.cwd() / root
    root = root.resolve(strict=False)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _proof_path(root: Path, stem: str) -> Path:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    return root / f"fairlight-record-arm-{stem}-{stamp}.png"
