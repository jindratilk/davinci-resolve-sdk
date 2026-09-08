"""Workflow-owned GUI-assisted Fairlight track visibility route.

This module only drives DaVinci Resolve's native Fairlight Index > Tracks
visibility eye cells. It is intentionally scoped to that panel and does not
expose a general GUI automation surface.
"""

from __future__ import annotations

import ctypes
import json
import platform
import subprocess
import tempfile
import time
import zlib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from ..errors import GuiPermissionMissing, ReadinessFailed, ResolveWindowNotFound, ResolveWindowNotReady, ValidationError
from ..output import set_recoverability, set_verification_status
from . import fairlight_ops

ROUTE = "fairlight.track_visibility_gui"
ENGINE = "resolve_gui"
DEFAULT_PROOF_DIR = Path("artifacts") / "fairlight-track-visibility-gui"
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
class TrackRowState:
    track: int
    label: str
    name: str | None
    label_rect: Rect
    eye_rect: Rect
    visible: bool
    brightness: dict[str, Any]

    def as_payload(self) -> dict[str, Any]:
        return {
            "track": self.track,
            "label": self.label,
            "name": self.name,
            "label_rect": self.label_rect.as_payload(),
            "eye_rect": self.eye_rect.as_payload(),
            "visible": self.visible,
            "brightness": self.brightness,
        }


@dataclass(frozen=True)
class TracksPanelState:
    window_rect: Rect
    tracks_panel_rect: Rect
    index_toggle_rect: Rect | None
    tracks_tab_rect: Rect | None
    row: TrackRowState
    scanned: int

    def as_payload(self) -> dict[str, Any]:
        return {
            "window_rect": self.window_rect.as_payload(),
            "tracks_panel_rect": self.tracks_panel_rect.as_payload(),
            "index_toggle_rect": self.index_toggle_rect.as_payload() if self.index_toggle_rect else None,
            "tracks_tab_rect": self.tracks_tab_rect.as_payload() if self.tracks_tab_rect else None,
            "row": self.row.as_payload(),
            "scanned": self.scanned,
        }


class MacOSFairlightTrackVisibilityGuiDriver:
    """Internal macOS driver scoped to Fairlight Index > Tracks eye cells."""

    process_names = PROCESS_NAMES

    def preflight_permissions(self) -> dict[str, Any]:
        if platform.system() != "Darwin":
            raise GuiPermissionMissing(
                "Fairlight track visibility GUI-assisted route requires macOS.",
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

    def prepare_tracks_panel(self, *, track: int) -> TracksPanelState:
        proc = _run_osascript(_tracks_panel_applescript(track=int(track), prepare=True), timeout=8.0)
        if proc.returncode != 0:
            raise ResolveWindowNotReady(
                "Could not prepare DaVinci Resolve Fairlight Index > Tracks panel.",
                details={"stderr": proc.stderr[-1000:], "stdout": proc.stdout[-1000:]},
            )
        payload = _json_payload(proc.stdout, "DaVinci Resolve Fairlight Tracks panel probe returned invalid data.")
        if not payload.get("ok"):
            error_cls = ResolveWindowNotFound if payload.get("reason") in {"process_not_found", "window_not_found"} else ReadinessFailed
            raise error_cls("DaVinci Resolve Fairlight Index > Tracks panel is not available.", details=payload)
        return self.read_track_state(payload, track=track)

    def read_track_state(self, panel_payload: dict[str, Any], *, track: int) -> TracksPanelState:
        state = _payload_to_panel_state(panel_payload, track=track, brightness=None)
        brightness = self.measure_eye(state.row.eye_rect)
        visible = _brightness_is_visible(brightness)
        row = TrackRowState(
            track=state.row.track,
            label=state.row.label,
            name=state.row.name,
            label_rect=state.row.label_rect,
            eye_rect=state.row.eye_rect,
            visible=visible,
            brightness=brightness,
        )
        return TracksPanelState(
            window_rect=state.window_rect,
            tracks_panel_rect=state.tracks_panel_rect,
            index_toggle_rect=state.index_toggle_rect,
            tracks_tab_rect=state.tracks_tab_rect,
            row=row,
            scanned=state.scanned,
        )

    def inspect_tracks_panel(self, *, track: int) -> TracksPanelState:
        proc = _run_osascript(_tracks_panel_applescript(track=int(track), prepare=False), timeout=8.0)
        if proc.returncode != 0:
            raise ResolveWindowNotReady(
                "Could not inspect DaVinci Resolve Fairlight Index > Tracks panel.",
                details={"stderr": proc.stderr[-1000:], "stdout": proc.stdout[-1000:]},
            )
        payload = _json_payload(proc.stdout, "DaVinci Resolve Fairlight Tracks panel inspect probe returned invalid data.")
        if not payload.get("ok"):
            raise ResolveWindowNotReady("DaVinci Resolve Fairlight Index > Tracks panel is not available for readback.", details=payload)
        return self.read_track_state(payload, track=track)

    def set_visibility(self, *, track: int, visible: bool) -> dict[str, Any]:
        before = self.prepare_tracks_panel(track=track)
        clicked = False
        polls: list[dict[str, Any]] = []
        after = before
        if before.row.visible != bool(visible):
            _post_mouse_click(before.row.eye_rect.center)
            clicked = True
            after, polls = self._poll_visibility(track=track, visible=bool(visible))
        proof_root = _proof_root(None)
        proof = self.capture_proof(after.tracks_panel_rect, _proof_path(proof_root, "show" if visible else "hide"))
        return {
            "clicked": clicked,
            "before": before,
            "after": after,
            "polls": polls,
            "proof": proof,
        }

    def _poll_visibility(self, *, track: int, visible: bool) -> tuple[TracksPanelState, list[dict[str, Any]]]:
        polls: list[dict[str, Any]] = []
        last: TracksPanelState | None = None
        for attempt in range(1, 16):
            time.sleep(0.15)
            current = self.inspect_tracks_panel(track=track)
            last = current
            polls.append({"attempt": attempt, "visible": current.row.visible, "brightness": current.row.brightness})
            if current.row.visible == visible:
                return current, polls
        raise ReadinessFailed(
            "DaVinci Resolve Fairlight track visibility did not reach requested state.",
            details={
                "route": ROUTE,
                "track": track,
                "requested_visible": visible,
                "last_state": last.as_payload() if last else None,
                "polls": polls,
            },
        )

    def measure_eye(self, rect: Rect) -> dict[str, Any]:
        with tempfile.TemporaryDirectory(prefix="cutagent-track-eye-") as tmpdir:
            path = Path(tmpdir) / "eye.png"
            self._capture_region(rect, path)
            return _measure_png_brightness(path)

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
                "Failed to capture Fairlight track visibility proof screenshot.",
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


def run_track_visibility(
    conn: Any,
    *,
    track: int,
    visible: bool,
    driver: MacOSFairlightTrackVisibilityGuiDriver | None = None,
) -> dict[str, Any]:
    _validate_audio_track(conn, int(track))
    active_driver = driver or MacOSFairlightTrackVisibilityGuiDriver()
    permission_state = active_driver.preflight_permissions()
    page_state = _ensure_fairlight_page(conn)
    result = active_driver.set_visibility(track=int(track), visible=bool(visible))
    set_verification_status("verified")
    set_recoverability("manual")
    return {
        "action": "fairlight.track.show" if visible else "fairlight.track.hide",
        "route": ROUTE,
        "engine_scope": "workflow_owned_resolve_gui",
        "track": int(track),
        "requested_visible": bool(visible),
        "changed": bool(result["clicked"]),
        "before": result["before"].as_payload(),
        "after": result["after"].as_payload(),
        "readback": {
            "state": "visible" if result["after"].row.visible else "hidden",
            "verified": result["after"].row.visible == bool(visible),
            "method": "native Fairlight Index > Tracks eye-cell screenshot brightness",
            "polls": result["polls"],
        },
        "proof": result["proof"],
        "preflight": {"permissions": permission_state, "page": page_state},
    }


def _validate_audio_track(conn: Any, track: int) -> None:
    if track < 1:
        raise ValidationError(
            "Fairlight track visibility requires an audio track index of 1 or greater.",
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


def _payload_to_panel_state(payload: dict[str, Any], *, track: int, brightness: dict[str, Any] | None) -> TracksPanelState:
    try:
        row_payload = payload["row"]
        label_rect = _rect_from_payload(row_payload["label_rect"])
        eye_rect = _rect_from_payload(row_payload["eye_rect"])
        row = TrackRowState(
            track=int(track),
            label=str(row_payload.get("label") or f"A{track}"),
            name=_optional_str(row_payload.get("name")),
            label_rect=label_rect,
            eye_rect=eye_rect,
            visible=_brightness_is_visible(brightness or {}),
            brightness=brightness or {},
        )
        return TracksPanelState(
            window_rect=_rect_from_payload(payload["window"]),
            tracks_panel_rect=_rect_from_payload(payload["tracks_panel"]),
            index_toggle_rect=_optional_rect(payload.get("index_toggle")),
            tracks_tab_rect=_optional_rect(payload.get("tracks_tab")),
            row=row,
            scanned=int(payload.get("scanned") or 0),
        )
    except Exception as exc:
        raise ResolveWindowNotReady(
            "DaVinci Resolve Fairlight Tracks panel probe did not include a usable track row.",
            details={"payload": payload, "track": track},
        ) from exc


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text and text != "null" else None


def _optional_rect(payload: Any) -> Rect | None:
    if not payload:
        return None
    return _rect_from_payload(payload)


def _rect_from_payload(payload: dict[str, Any]) -> Rect:
    pos = payload.get("pos") or payload.get("position")
    size = payload.get("size")
    if not isinstance(pos, list) or len(pos) < 2 or not isinstance(size, list) or len(size) < 2:
        raise ValueError("missing position/size")
    rect = Rect(x=int(pos[0]), y=int(pos[1]), width=int(size[0]), height=int(size[1]))
    if rect.width <= 0 or rect.height <= 0:
        raise ValueError("invalid rect")
    return rect


def _brightness_is_visible(brightness: dict[str, Any]) -> bool:
    return int(brightness.get("bright_count") or 0) >= 8 and float(brightness.get("max_luma") or 0.0) >= 180.0


def _measure_png_brightness(path: Path) -> dict[str, Any]:
    width, height, channels, rows = _read_png_rows(path)
    bright_count = 0
    max_luma = 0.0
    total_luma = 0.0
    pixel_count = width * height
    for row in rows:
        for offset in range(0, len(row), channels):
            r, g, b = row[offset], row[offset + 1], row[offset + 2]
            luma = (float(r) + float(g) + float(b)) / 3.0
            total_luma += luma
            max_luma = max(max_luma, luma)
            if luma >= 130.0:
                bright_count += 1
    return {
        "width": width,
        "height": height,
        "pixel_count": pixel_count,
        "bright_count": bright_count,
        "max_luma": round(max_luma, 3),
        "mean_luma": round(total_luma / max(1, pixel_count), 3),
    }


def _read_png_rows(path: Path) -> tuple[int, int, int, list[bytes]]:
    data = path.read_bytes()
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ReadinessFailed("Track visibility screenshot is not a PNG file.", details={"path": str(path)})
    offset = 8
    width = height = channels = 0
    idat = bytearray()
    while offset + 8 <= len(data):
        length = int.from_bytes(data[offset : offset + 4], "big")
        chunk_type = data[offset + 4 : offset + 8]
        chunk_data = data[offset + 8 : offset + 8 + length]
        offset += 12 + length
        if chunk_type == b"IHDR":
            width = int.from_bytes(chunk_data[0:4], "big")
            height = int.from_bytes(chunk_data[4:8], "big")
            bit_depth = chunk_data[8]
            color_type = chunk_data[9]
            if bit_depth != 8 or color_type not in {2, 6}:
                raise ReadinessFailed(
                    "Track visibility screenshot PNG format is unsupported.",
                    details={"path": str(path), "bit_depth": bit_depth, "color_type": color_type},
                )
            channels = 4 if color_type == 6 else 3
        elif chunk_type == b"IDAT":
            idat.extend(chunk_data)
        elif chunk_type == b"IEND":
            break
    if width <= 0 or height <= 0 or channels <= 0:
        raise ReadinessFailed("Track visibility screenshot PNG header is invalid.", details={"path": str(path)})
    raw = zlib.decompress(bytes(idat))
    stride = width * channels
    rows: list[bytes] = []
    previous = bytearray(stride)
    cursor = 0
    for _ in range(height):
        filter_type = raw[cursor]
        cursor += 1
        scanline = bytearray(raw[cursor : cursor + stride])
        cursor += stride
        recon = _unfilter_png_row(filter_type, scanline, previous, channels)
        rows.append(bytes(recon))
        previous = recon
    return width, height, channels, rows


def _unfilter_png_row(filter_type: int, row: bytearray, previous: bytearray, channels: int) -> bytearray:
    recon = bytearray(len(row))
    for i, value in enumerate(row):
        left = recon[i - channels] if i >= channels else 0
        up = previous[i] if previous else 0
        up_left = previous[i - channels] if previous and i >= channels else 0
        if filter_type == 0:
            predictor = 0
        elif filter_type == 1:
            predictor = left
        elif filter_type == 2:
            predictor = up
        elif filter_type == 3:
            predictor = (left + up) // 2
        elif filter_type == 4:
            predictor = _paeth(left, up, up_left)
        else:
            raise ReadinessFailed("Track visibility screenshot PNG filter is unsupported.", details={"filter_type": filter_type})
        recon[i] = (int(value) + predictor) & 0xFF
    return recon


def _paeth(left: int, up: int, up_left: int) -> int:
    p = left + up - up_left
    pa = abs(p - left)
    pb = abs(p - up)
    pc = abs(p - up_left)
    if pa <= pb and pa <= pc:
        return left
    if pb <= pc:
        return up
    return up_left


def _proof_root(proof_dir: Path | None) -> Path:
    root = (proof_dir or DEFAULT_PROOF_DIR).expanduser()
    if not root.is_absolute():
        root = Path.cwd() / root
    root = root.resolve(strict=False)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _proof_path(root: Path, stem: str) -> Path:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    return root / f"fairlight-track-visibility-{stem}-{stamp}.png"


def _tracks_panel_applescript(*, track: int, prepare: bool) -> str:
    label = f"A{int(track)}"
    name = f"Audio {int(track)}"
    prepare_script = """
    if (value of checkbox "Effects" of group 1 as string) is "1" then click checkbox "Effects" of group 1
    if (value of checkbox "Index" of group 1 as string) is not "1" then click checkbox "Index" of group 1
    delay 0.15
    if (value of checkbox "Tracks" as string) is not "1" then click checkbox "Tracks"
    delay 0.15
""" if prepare else ""
    return f'''
on jsonRect(posList, sizeList)
    return "{{\\"pos\\":[" & (item 1 of posList as integer) & "," & (item 2 of posList as integer) & "],\\"size\\":[" & (item 1 of sizeList as integer) & "," & (item 2 of sizeList as integer) & "]}}"
end jsonRect

on jsonString(valueText)
    set escapedText to my replaceText(valueText as string, "\\\\", "\\\\\\\\")
    set escapedText to my replaceText(escapedText, "\\"", "\\\\\\"")
    return "\\"" & escapedText & "\\""
end jsonString

on replaceText(sourceText, searchText, replacementText)
    set oldDelimiters to AppleScript's text item delimiters
    set AppleScript's text item delimiters to searchText
    set parts to text items of sourceText
    set AppleScript's text item delimiters to replacementText
    set joinedText to parts as string
    set AppleScript's text item delimiters to oldDelimiters
    return joinedText
end replaceText

tell application "System Events"
    set procName to missing value
    repeat with candidateName in {{"DaVinci Resolve", "Resolve"}}
        if exists process (candidateName as string) then
            set procName to candidateName as string
            exit repeat
        end if
    end repeat
    if procName is missing value then
        return "{{\\"ok\\":false,\\"reason\\":\\"process_not_found\\"}}"
    end if
    tell process procName
        if not (exists window 1) then return "{{\\"ok\\":false,\\"reason\\":\\"window_not_found\\",\\"process_name\\":" & my jsonString(procName) & "}}"
        set targetWindow to window 1
        set winPos to position of targetWindow
        set winSize to size of targetWindow
        tell group 1 of targetWindow
{prepare_script}
            try
                set indexPos to position of checkbox "Index" of group 1
                set indexSize to size of checkbox "Index" of group 1
                set tracksPos to position of checkbox "Tracks"
                set tracksSize to size of checkbox "Tracks"
                set panelPos to position of group 2
                set panelSize to size of group 2
                set tableGroup to group 1 of group 2
                set labelGroup to first group of tableGroup whose title is "{label}"
                set labelPos to position of labelGroup
                set labelSize to size of labelGroup
                set rowName to missing value
                try
                    set nameGroup to first group of tableGroup whose title is "{name}"
                    set rowName to title of nameGroup
                end try
                set eyePos to {{(item 1 of labelPos as integer) - 28, item 2 of labelPos as integer}}
                set eyeSize to {{28, item 2 of labelSize as integer}}
                set proofHeight to ((item 2 of labelPos as integer) - (item 2 of panelPos as integer) + 80)
                if proofHeight < 140 then set proofHeight to 140
                if proofHeight > 360 then set proofHeight to 360
                set panelProofSize to {{item 1 of panelSize as integer, proofHeight}}
                set rowNameJson to "null"
                if rowName is not missing value then set rowNameJson to my jsonString(rowName)
                return "{{\\"ok\\":true,\\"process_name\\":" & my jsonString(procName) & ",\\"scanned\\":5,\\"window\\":" & my jsonRect(winPos, winSize) & ",\\"tracks_panel\\":" & my jsonRect(panelPos, panelProofSize) & ",\\"index_toggle\\":" & my jsonRect(indexPos, indexSize) & ",\\"tracks_tab\\":" & my jsonRect(tracksPos, tracksSize) & ",\\"row\\":{{\\"label\\":\\"{label}\\",\\"name\\":" & rowNameJson & ",\\"label_rect\\":" & my jsonRect(labelPos, labelSize) & ",\\"eye_rect\\":" & my jsonRect(eyePos, eyeSize) & "}}}}"
            on error errMsg
                return "{{\\"ok\\":false,\\"reason\\":\\"track_row_not_found\\",\\"process_name\\":" & my jsonString(procName) & ",\\"requested_track\\":{int(track)},\\"error\\":" & my jsonString(errMsg) & "}}"
            end try
        end tell
    end tell
end tell
'''


def _json_payload(stdout: str, message: str) -> dict[str, Any]:
    try:
        return json.loads(stdout.strip())
    except json.JSONDecodeError as exc:
        raise ResolveWindowNotReady(message, details={"stdout": stdout[-1000:]}) from exc


def _run_osascript(
    script: str,
    *,
    language: str | None = None,
    timeout: float = 5.0,
    input_payload: dict[str, Any] | None = None,
) -> subprocess.CompletedProcess[str]:
    cmd = ["osascript"]
    if language:
        cmd.extend(["-l", language])
    cmd.extend(["-e", script])
    if input_payload is not None:
        cmd.append(json.dumps(input_payload))
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        return subprocess.CompletedProcess(cmd, 124, stdout=exc.stdout or "", stderr=exc.stderr or str(exc))


def _post_mouse_click(point: tuple[int, int], *, delay_seconds: float = 0.025) -> None:
    app_services = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices")

    class CGPoint(ctypes.Structure):
        _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]

    app_services.CGEventCreateMouseEvent.restype = ctypes.c_void_p
    app_services.CGEventCreateMouseEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint32, CGPoint, ctypes.c_uint32]
    app_services.CGEventPost.argtypes = [ctypes.c_uint32, ctypes.c_void_p]
    app_services.CFRelease.argtypes = [ctypes.c_void_p]

    for event_type in (1, 2):
        event = app_services.CGEventCreateMouseEvent(None, event_type, CGPoint(float(point[0]), float(point[1])), 0)
        if not event:
            raise ReadinessFailed(
                "macOS failed to create Fairlight track visibility mouse event.",
                details={"event_type": event_type, "point": point},
            )
        try:
            app_services.CGEventPost(0, event)
        finally:
            app_services.CFRelease(event)
        time.sleep(delay_seconds)
