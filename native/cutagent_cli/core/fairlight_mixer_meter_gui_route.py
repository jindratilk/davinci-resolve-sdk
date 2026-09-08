"""Workflow-owned GUI-assisted Fairlight mixer meter read route.

This module only reads DaVinci Resolve's visible Fairlight Mixer meter columns
from a screenshot. It does not expose generic GUI automation and does not start
or stop playback.
"""

from __future__ import annotations

import platform
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..errors import GuiPermissionMissing, ReadinessFailed, ResolveWindowNotReady, ValidationError
from ..output import set_recoverability, set_verification_status
from .fairlight_track_visibility_gui_route import (
    Rect,
    _ensure_fairlight_page,
    _proof_root,
    _read_png_rows,
    _run_osascript,
)
from . import fairlight_ops

ROUTE = "fairlight.mixer_meter_gui"
ENGINE = "resolve_gui"
DEFAULT_PROOF_DIR = Path("artifacts") / "fairlight-mixer-meter-gui"
PROCESS_NAMES = ("DaVinci Resolve", "Resolve")

MIXER_CROP_WIDTH = 360
MIXER_CROP_HEIGHT = 760
MIXER_CROP_TOP_OFFSET = 560
METER_TOP_Y = 388
METER_BOTTOM_Y = 700
METER_FLOOR_DBFS = -60.0
VISIBLE_TRACK_COLUMNS = {
    1: {"x": 204, "width": 22, "label": "A1"},
    2: {"x": 272, "width": 22, "label": "A2"},
}
VISIBLE_BUS_COLUMNS = {
    "bus 1": {"x": 340, "width": 22, "label": "Bus 1"},
    "bus1": {"x": 340, "width": 22, "label": "Bus 1"},
    "main": {"x": 340, "width": 22, "label": "Bus 1"},
}


@dataclass(frozen=True)
class MeterRead:
    target: dict[str, Any]
    meter_rect: Rect
    signal_present: bool
    dbfs_estimate: float | None
    floor_dbfs: float
    green_pixel_count: int
    green_bounds: dict[str, int] | None

    def as_payload(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "meter_rect": self.meter_rect.as_payload(),
            "signal_present": self.signal_present,
            "dbfs_estimate": self.dbfs_estimate,
            "floor_dbfs": self.floor_dbfs,
            "green_pixel_count": self.green_pixel_count,
            "green_bounds": self.green_bounds,
        }


class MacOSFairlightMixerMeterGuiDriver:
    """Internal macOS driver scoped to visible Fairlight Mixer meter columns."""

    process_names = PROCESS_NAMES

    def preflight_permissions(self) -> dict[str, Any]:
        if platform.system() != "Darwin":
            raise GuiPermissionMissing(
                "Fairlight mixer meter GUI-assisted route requires macOS.",
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

    def read_meter(self, *, track: int | None, bus: str | None) -> dict[str, Any]:
        window_rect = self._resolve_window_rect()
        crop_rect = self._mixer_crop_rect(window_rect)
        proof_root = _proof_root(DEFAULT_PROOF_DIR)
        proof_path = _proof_path(proof_root)
        self._capture_region(crop_rect, proof_path)
        target = _meter_target(track=track, bus=bus)
        read = self._read_meter_from_crop(proof_path, crop_rect=crop_rect, target=target)
        return {
            "window_rect": window_rect.as_payload(),
            "mixer_crop_rect": crop_rect.as_payload(),
            "meter": read,
            "proof": {"screenshot_path": str(proof_path), "bytes": proof_path.stat().st_size, "region": crop_rect.as_payload()},
        }

    def _read_meter_from_crop(self, path: Path, *, crop_rect: Rect, target: dict[str, Any]) -> dict[str, Any]:
        rel_x = int(target["relative_x"])
        width = int(target["width"])
        meter_rect = Rect(
            x=int(crop_rect.x + rel_x),
            y=int(crop_rect.y + METER_TOP_Y),
            width=width,
            height=int(METER_BOTTOM_Y - METER_TOP_Y),
        )
        green_pixels = _green_pixels(path, x0=rel_x, y0=METER_TOP_Y, width=width, height=METER_BOTTOM_Y - METER_TOP_Y)
        signal_present = green_pixels["count"] >= 20
        dbfs_estimate = None
        bounds = green_pixels["bounds"]
        if signal_present and bounds is not None:
            top_y = int(bounds["min_y"])
            ratio = max(0.0, min(1.0, (top_y - METER_TOP_Y) / max(1, (METER_BOTTOM_Y - METER_TOP_Y))))
            dbfs_estimate = round(METER_FLOOR_DBFS * ratio, 2)
        read = MeterRead(
            target={"kind": target["kind"], "name": target["name"]},
            meter_rect=meter_rect,
            signal_present=signal_present,
            dbfs_estimate=dbfs_estimate,
            floor_dbfs=METER_FLOOR_DBFS,
            green_pixel_count=int(green_pixels["count"]),
            green_bounds=bounds,
        )
        return read.as_payload()

    def _resolve_window_rect(self) -> Rect:
        proc = _run_osascript(_window_rect_applescript(), timeout=8.0)
        if proc.returncode != 0:
            raise ResolveWindowNotReady(
                "Could not inspect DaVinci Resolve window for Fairlight mixer metering.",
                details={"stderr": proc.stderr[-1000:], "stdout": proc.stdout[-1000:]},
            )
        payload = _json_payload(proc.stdout)
        if not payload.get("ok"):
            raise ResolveWindowNotReady("DaVinci Resolve window is not available for Fairlight mixer metering.", details=payload)
        rect = Rect(
            x=int(payload["window"]["pos"][0]),
            y=int(payload["window"]["pos"][1]),
            width=int(payload["window"]["size"][0]),
            height=int(payload["window"]["size"][1]),
        )
        if rect.width < 900 or rect.height < 700:
            raise ResolveWindowNotReady(
                "DaVinci Resolve window is too small for Fairlight mixer meter readback.",
                details={"window_rect": rect.as_payload(), "minimum": {"width": 900, "height": 700}},
            )
        return rect

    def _mixer_crop_rect(self, window_rect: Rect) -> Rect:
        width = min(MIXER_CROP_WIDTH, window_rect.width)
        height = min(MIXER_CROP_HEIGHT, max(1, window_rect.height - MIXER_CROP_TOP_OFFSET))
        return Rect(
            x=int(window_rect.x + window_rect.width - width),
            y=int(window_rect.y + MIXER_CROP_TOP_OFFSET),
            width=int(width),
            height=int(height),
        )

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
                "Failed to capture Fairlight mixer meter proof screenshot.",
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


def run_mixer_meter(
    conn: Any,
    *,
    track: int | None,
    bus: str | None,
    include_peak_hold: bool,
    driver: MacOSFairlightMixerMeterGuiDriver | None = None,
) -> dict[str, Any]:
    if track is not None and bus:
        raise ValidationError(
            "Fairlight mixer meter accepts either --track or --bus, not both.",
            details={"track": track, "bus": bus},
            recoverability="not_applicable",
        )
    if track is None and not bus:
        track = 1
    if track is not None:
        _validate_visible_audio_track(conn, int(track))
    active_driver = driver or MacOSFairlightMixerMeterGuiDriver()
    permission_state = active_driver.preflight_permissions()
    page_state = _ensure_fairlight_page(conn)
    result = active_driver.read_meter(track=track, bus=bus)
    set_verification_status("verified")
    set_recoverability("manual")
    return {
        "action": "fairlight.mixer.meter",
        "route": ROUTE,
        "engine_scope": "workflow_owned_resolve_gui",
        "track": int(track) if track is not None else None,
        "bus": bus,
        "include_peak_hold": bool(include_peak_hold),
        "readback": {
            "verified": True,
            "method": "native Fairlight Mixer visible meter screenshot pixel readback",
            "value_type": "screen_read_dbfs_estimate",
            "peak_hold_supported": False,
            "requires_visible_mixer": True,
        },
        "meter": result["meter"],
        "proof": result["proof"],
        "preflight": {"permissions": permission_state, "page": page_state},
        "window_rect": result["window_rect"],
        "mixer_crop_rect": result["mixer_crop_rect"],
    }


def _validate_visible_audio_track(conn: Any, track: int) -> None:
    if track not in VISIBLE_TRACK_COLUMNS:
        raise ValidationError(
            "This Fairlight mixer meter GUI route currently reads visible A1/A2 mixer columns only.",
            details={"track": track, "visible_tracks": sorted(VISIBLE_TRACK_COLUMNS)},
            recoverability="not_applicable",
        )
    rows = fairlight_ops.list_audio_tracks(conn)
    if len(rows) < track:
        raise ValidationError(
            "Fairlight audio track index is out of range.",
            details={"track": track, "available_audio_tracks": len(rows)},
            recoverability="not_applicable",
        )


def _meter_target(*, track: int | None, bus: str | None) -> dict[str, Any]:
    if track is not None:
        spec = VISIBLE_TRACK_COLUMNS[int(track)]
        return {"kind": "track", "name": spec["label"], "relative_x": spec["x"], "width": spec["width"]}
    key = str(bus or "Bus 1").strip().lower()
    if key not in VISIBLE_BUS_COLUMNS:
        raise ValidationError(
            "This Fairlight mixer meter GUI route currently reads the visible Bus 1/Main mixer column only.",
            details={"bus": bus, "visible_buses": ["Bus 1"]},
            recoverability="not_applicable",
        )
    spec = VISIBLE_BUS_COLUMNS[key]
    return {"kind": "bus", "name": spec["label"], "relative_x": spec["x"], "width": spec["width"]}


def _green_pixels(path: Path, *, x0: int, y0: int, width: int, height: int) -> dict[str, Any]:
    png_width, png_height, channels, rows = _read_png_rows(path)
    x1 = min(png_width, x0 + width)
    y1 = min(png_height, y0 + height)
    count = 0
    min_x = min_y = 10**9
    max_x = max_y = -1
    for y in range(max(0, y0), y1):
        row = rows[y]
        for x in range(max(0, x0), x1):
            offset = x * channels
            r, g, b = row[offset], row[offset + 1], row[offset + 2]
            if g >= 150 and g > r * 1.4 and g > b * 1.2:
                count += 1
                min_x = min(min_x, x)
                max_x = max(max_x, x)
                min_y = min(min_y, y)
                max_y = max(max_y, y)
    bounds = None
    if count:
        bounds = {"min_x": min_x, "max_x": max_x, "min_y": min_y, "max_y": max_y}
    return {"count": count, "bounds": bounds}


def _json_payload(stdout: str) -> dict[str, Any]:
    import json

    try:
        return json.loads(stdout.strip())
    except json.JSONDecodeError as exc:
        raise ResolveWindowNotReady(
            "DaVinci Resolve Fairlight mixer meter window probe returned invalid data.",
            details={"stdout": stdout[-1000:]},
        ) from exc


def _window_rect_applescript() -> str:
    return '''
on jsonRect(posList, sizeList)
    return "{\\"pos\\":[" & (item 1 of posList as integer) & "," & (item 2 of posList as integer) & "],\\"size\\":[" & (item 1 of sizeList as integer) & "," & (item 2 of sizeList as integer) & "]}"
end jsonRect

tell application "System Events"
    set procName to missing value
    repeat with candidateName in {"DaVinci Resolve", "Resolve"}
        if exists process (candidateName as string) then
            set procName to candidateName as string
            exit repeat
        end if
    end repeat
    if procName is missing value then return "{\\"ok\\":false,\\"reason\\":\\"process_not_found\\"}"
    tell process procName
        if not (exists window 1) then return "{\\"ok\\":false,\\"reason\\":\\"window_not_found\\"}"
        set targetWindow to window 1
        return "{\\"ok\\":true,\\"window\\":" & my jsonRect(position of targetWindow, size of targetWindow) & "}"
    end tell
end tell
'''


def _proof_path(root: Path) -> Path:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    return root / f"fairlight-mixer-meter-{stamp}.png"
