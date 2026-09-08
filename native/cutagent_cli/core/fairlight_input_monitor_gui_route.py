"""Workflow-owned GUI-assisted Fairlight input monitor route.

This module only drives DaVinci Resolve's native Fairlight Index > Tracks
``Monitor`` checkbox. It is intentionally scoped to that visible control and
does not expose a general GUI automation surface.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..errors import ReadinessFailed, ResolveWindowNotReady
from ..output import set_recoverability, set_verification_status
from .fairlight_track_visibility_gui_route import (
    MacOSFairlightTrackVisibilityGuiDriver,
    Rect,
    _ensure_fairlight_page,
    _post_mouse_click,
    _proof_root,
    _run_osascript,
    _tracks_panel_applescript,
    _validate_audio_track,
)

ROUTE = "fairlight.track_input_monitor_gui"
ENGINE = "resolve_gui"
DEFAULT_PROOF_DIR = Path("artifacts") / "fairlight-input-monitor-gui"

MONITOR_COLUMN_X_OFFSET = 511
MONITOR_CELL_WIDTH = 28
ON_BRIGHT_COUNT_MIN = 8
ON_MAX_LUMA_MIN = 180.0


@dataclass(frozen=True)
class MonitorState:
    track: int
    label: str
    name: str | None
    monitor_rect: Rect
    enabled: bool
    brightness: dict[str, Any]

    def as_payload(self) -> dict[str, Any]:
        return {
            "track": self.track,
            "label": self.label,
            "name": self.name,
            "monitor_rect": self.monitor_rect.as_payload(),
            "enabled": self.enabled,
            "brightness": self.brightness,
        }


@dataclass(frozen=True)
class InputMonitorPanelState:
    window_rect: Rect
    tracks_panel_rect: Rect
    row: MonitorState
    scanned: int

    def as_payload(self) -> dict[str, Any]:
        return {
            "window_rect": self.window_rect.as_payload(),
            "tracks_panel_rect": self.tracks_panel_rect.as_payload(),
            "row": self.row.as_payload(),
            "scanned": self.scanned,
        }


class MacOSFairlightInputMonitorGuiDriver(MacOSFairlightTrackVisibilityGuiDriver):
    """Internal macOS driver scoped to Fairlight Index > Tracks Monitor cells."""

    def prepare_monitor_panel(self, *, track: int) -> InputMonitorPanelState:
        proc = _run_osascript(_tracks_panel_applescript(track=int(track), prepare=True), timeout=45.0)
        if proc.returncode != 0:
            raise ResolveWindowNotReady(
                "Could not prepare DaVinci Resolve Fairlight Index > Tracks panel for input monitoring.",
                details={"stderr": proc.stderr[-1000:], "stdout": proc.stdout[-1000:]},
            )
        payload = self._panel_payload(proc.stdout)
        return self.read_monitor_state(payload, track=track)

    def inspect_monitor_panel(self, *, track: int) -> InputMonitorPanelState:
        proc = _run_osascript(_tracks_panel_applescript(track=int(track), prepare=False), timeout=45.0)
        if proc.returncode != 0:
            raise ResolveWindowNotReady(
                "Could not inspect DaVinci Resolve Fairlight Index > Tracks panel for input monitoring.",
                details={"stderr": proc.stderr[-1000:], "stdout": proc.stdout[-1000:]},
            )
        payload = self._panel_payload(proc.stdout)
        return self.read_monitor_state(payload, track=track)

    def read_monitor_state(self, panel_payload: dict[str, Any], *, track: int) -> InputMonitorPanelState:
        if not panel_payload.get("ok"):
            raise ResolveWindowNotReady(
                "DaVinci Resolve Fairlight Index > Tracks panel is not available for input monitor readback.",
                details=panel_payload,
            )
        try:
            window_rect = _rect_from_payload(panel_payload["window"])
            tracks_panel_rect = _rect_from_payload(panel_payload["tracks_panel"])
            row_payload = panel_payload["row"]
            label_rect = _rect_from_payload(row_payload["label_rect"])
            monitor_rect = Rect(
                x=int(tracks_panel_rect.x + MONITOR_COLUMN_X_OFFSET),
                y=int(label_rect.y),
                width=MONITOR_CELL_WIDTH,
                height=int(label_rect.height),
            )
            brightness = self.measure_eye(monitor_rect)
            row = MonitorState(
                track=int(track),
                label=str(row_payload.get("label") or f"A{track}"),
                name=_optional_str(row_payload.get("name")),
                monitor_rect=monitor_rect,
                enabled=_brightness_is_checked(brightness),
                brightness=brightness,
            )
            return InputMonitorPanelState(
                window_rect=window_rect,
                tracks_panel_rect=tracks_panel_rect,
                row=row,
                scanned=int(panel_payload.get("scanned") or 0),
            )
        except Exception as exc:
            raise ResolveWindowNotReady(
                "DaVinci Resolve Fairlight Tracks panel probe did not include a usable input monitor row.",
                details={"payload": panel_payload, "track": track},
            ) from exc

    def set_input_monitor(self, *, track: int, enable: bool) -> dict[str, Any]:
        before = self.prepare_monitor_panel(track=track)
        clicked = False
        polls: list[dict[str, Any]] = []
        after = before
        if before.row.enabled != bool(enable):
            _post_mouse_click(before.row.monitor_rect.center)
            clicked = True
            after, polls = self._poll_monitor(track=track, enable=bool(enable))
        proof_root = _proof_root(DEFAULT_PROOF_DIR)
        proof = self.capture_proof(after.tracks_panel_rect, _proof_path(proof_root, "enable" if enable else "disable"))
        return {"clicked": clicked, "before": before, "after": after, "polls": polls, "proof": proof}

    def _poll_monitor(self, *, track: int, enable: bool) -> tuple[InputMonitorPanelState, list[dict[str, Any]]]:
        polls: list[dict[str, Any]] = []
        last: InputMonitorPanelState | None = None
        for attempt in range(1, 16):
            time.sleep(0.15)
            current = self.inspect_monitor_panel(track=track)
            last = current
            polls.append({"attempt": attempt, "enabled": current.row.enabled, "brightness": current.row.brightness})
            if current.row.enabled == enable:
                return current, polls
        raise ReadinessFailed(
            "DaVinci Resolve Fairlight input monitor did not reach requested state.",
            details={
                "route": ROUTE,
                "track": track,
                "requested_enabled": enable,
                "last_state": last.as_payload() if last else None,
                "polls": polls,
            },
        )

    def _panel_payload(self, stdout: str) -> dict[str, Any]:
        import json

        try:
            return json.loads(stdout.strip())
        except json.JSONDecodeError as exc:
            raise ResolveWindowNotReady(
                "DaVinci Resolve Fairlight Tracks panel input monitor probe returned invalid data.",
                details={"stdout": stdout[-1000:]},
            ) from exc


def run_input_monitor(
    conn: Any,
    *,
    track: int,
    enable: bool,
    driver: MacOSFairlightInputMonitorGuiDriver | None = None,
) -> dict[str, Any]:
    _validate_audio_track(conn, int(track))
    active_driver = driver or MacOSFairlightInputMonitorGuiDriver()
    permission_state = active_driver.preflight_permissions()
    page_state = _ensure_fairlight_page(conn)
    result = active_driver.set_input_monitor(track=int(track), enable=bool(enable))
    set_verification_status("verified")
    set_recoverability("manual")
    return {
        "action": "fairlight.track.input_monitor",
        "route": ROUTE,
        "engine_scope": "workflow_owned_resolve_gui",
        "track": int(track),
        "requested_enabled": bool(enable),
        "changed": bool(result["clicked"]),
        "before": result["before"].as_payload(),
        "after": result["after"].as_payload(),
        "readback": {
            "state": "enabled" if result["after"].row.enabled else "disabled",
            "verified": result["after"].row.enabled == bool(enable),
            "method": "native Fairlight Index > Tracks Monitor-checkbox screenshot brightness",
            "polls": result["polls"],
        },
        "proof": result["proof"],
        "preflight": {"permissions": permission_state, "page": page_state},
    }


def _brightness_is_checked(brightness: dict[str, Any]) -> bool:
    return int(brightness.get("bright_count") or 0) >= ON_BRIGHT_COUNT_MIN and float(brightness.get("max_luma") or 0.0) >= ON_MAX_LUMA_MIN


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text and text != "null" else None


def _rect_from_payload(payload: dict[str, Any]) -> Rect:
    pos = payload.get("pos") or payload.get("position")
    size = payload.get("size")
    if not isinstance(pos, list) or len(pos) < 2 or not isinstance(size, list) or len(size) < 2:
        raise ValueError("missing position/size")
    rect = Rect(x=int(pos[0]), y=int(pos[1]), width=int(size[0]), height=int(size[1]))
    if rect.width <= 0 or rect.height <= 0:
        raise ValueError("invalid rect")
    return rect


def _proof_path(root: Path, stem: str) -> Path:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    return root / f"fairlight-input-monitor-{stem}-{stamp}.png"
