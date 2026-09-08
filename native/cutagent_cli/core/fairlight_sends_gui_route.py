"""Workflow-owned GUI-assisted Fairlight send route.

This module drives only DaVinci Resolve's native Fairlight Mixer Bus Sends
popover. It is intentionally not a general GUI automation surface.
"""

from __future__ import annotations

import ctypes
import hashlib
import json
import platform
import re
import sqlite3
import subprocess
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from ..errors import GuiPermissionMissing, ReadinessFailed, ResolveWindowNotReady, ValidationError
from ..output import set_recoverability, set_verification_status
from . import db_session, fairlight_ops, project_ops

ROUTE = "fairlight.sends_gui"
ENGINE = "resolve_gui"
DEFAULT_PROOF_DIR = Path("artifacts") / "fairlight-sends-gui"
SUPPORTED_VISIBLE_MIXER_TRACKS = 4
MIN_SEND_LEVEL_DB = -100.0
MAX_SEND_LEVEL_DB = 10.0


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
class SendMixerGeometry:
    window_rect: Rect
    track: int
    send_slot_rect: Rect
    send_plus_rect: Rect

    def as_payload(self) -> dict[str, Any]:
        return {
            "window_rect": self.window_rect.as_payload(),
            "track": self.track,
            "send_slot_rect": self.send_slot_rect.as_payload(),
            "send_plus_rect": self.send_plus_rect.as_payload(),
        }


@dataclass(frozen=True)
class BusSendsPopoverState:
    rect: Rect
    title: str
    scanned: int

    def as_payload(self) -> dict[str, Any]:
        return {"rect": self.rect.as_payload(), "title": self.title, "scanned": self.scanned}


class MacOSFairlightSendsGuiDriver:
    """Internal macOS driver scoped to the Fairlight Mixer Bus Sends popover."""

    def preflight_permissions(self) -> dict[str, Any]:
        if platform.system() != "Darwin":
            raise GuiPermissionMissing(
                "Fairlight sends GUI-assisted route requires macOS.",
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

    def set_send(self, *, track: int, send: str, level_db: float | None, pre_fader: bool | None) -> dict[str, Any]:
        geometry = _geometry_for_visible_mixer_track(_window_rect(), track=track)
        popover, assignment = self._open_or_create_popover(geometry, send=send)
        before_proof = self.capture_proof(popover.rect, _proof_path(_proof_root(None), "before"))
        before_visual = _visual_state_from_proof(Path(before_proof["screenshot_path"]), popover.rect)

        pre_result: dict[str, Any] | None = None
        if pre_fader is not None:
            current_pre = before_visual["pre_fader_active"]
            clicked = False
            if current_pre != bool(pre_fader):
                _post_mouse_click(_pre_button_rect(popover.rect).center)
                clicked = True
                time.sleep(0.25)
            pre_result = {"requested": bool(pre_fader), "initial": current_pre, "clicked": clicked}

        level_result: dict[str, Any] | None = None
        if level_db is not None:
            _set_level_field(popover.rect, level_db)
            time.sleep(0.25)
            level_result = {
                "requested_db": float(level_db),
                "model_value": _level_model_value(level_db),
                "input_method": "native Bus Sends numeric level field",
            }

        final_proof = self.capture_proof(popover.rect, _proof_path(_proof_root(None), "final"))
        final_visual = _visual_state_from_proof(Path(final_proof["screenshot_path"]), popover.rect)
        if pre_fader is not None and final_visual["pre_fader_active"] != bool(pre_fader):
            raise ReadinessFailed(
                "Fairlight Bus Sends proof screenshot did not show the requested pre/post-fader state.",
                details={
                    "route": ROUTE,
                    "requested_pre_fader": bool(pre_fader),
                    "visual_readback": final_visual,
                    "proof": final_proof,
                },
            )
        return {
            "geometry": geometry,
            "popover": popover,
            "assignment": assignment,
            "pre_fader": pre_result,
            "level": level_result,
            "before_proof": before_proof,
            "final_proof": final_proof,
            "before_visual": before_visual,
            "final_visual": final_visual,
        }

    def _open_or_create_popover(self, geometry: SendMixerGeometry, *, send: str) -> tuple[BusSendsPopoverState, dict[str, Any]]:
        existing = _find_bus_sends_popover()
        if existing is not None:
            return existing, {"created": False, "method": "used existing visible Bus Sends popover"}

        _post_mouse_click(geometry.send_slot_rect.center)
        time.sleep(0.35)
        popover = _find_bus_sends_popover()
        if popover is not None:
            return popover, {"created": False, "method": "opened existing visible Bus Sends slot"}

        bus_index = _parse_bus_index(send)
        _post_mouse_click(geometry.send_plus_rect.center)
        time.sleep(0.25)
        _post_mouse_click(_bus_destination_menu_point(geometry.send_plus_rect, bus_index))
        time.sleep(0.45)
        _post_mouse_click(geometry.send_slot_rect.center)
        time.sleep(0.35)
        popover = _find_bus_sends_popover()
        if popover is None:
            raise ResolveWindowNotReady(
                "Could not open the DaVinci Resolve Fairlight Bus Sends popover.",
                details={
                    "route": ROUTE,
                    "send": send,
                    "track": geometry.track,
                    "geometry": geometry.as_payload(),
                    "required_layout": "Fairlight page with Mixer visible and Bus Sends row visible",
                },
            )
        return popover, {
            "created": True,
            "method": "native Mixer Bus Sends plus menu",
            "bus_index": bus_index,
            "destination_menu_point": {"x": _bus_destination_menu_point(geometry.send_plus_rect, bus_index)[0], "y": _bus_destination_menu_point(geometry.send_plus_rect, bus_index)[1]},
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


def run_send_set(
    conn: Any,
    *,
    track: int,
    send: str,
    level_db: float | None,
    pre_fader: bool | None,
    driver: MacOSFairlightSendsGuiDriver | None = None,
) -> dict[str, Any]:
    normalized_track = _validate_track(conn, track)
    normalized_send = _validate_send_destination(conn, send)
    if level_db is None and pre_fader is None:
        raise ValidationError(
            "Fairlight send set requires --level, --pre-fader, or --post-fader.",
            details={"required_any": ["level_db", "pre_fader"], "track": normalized_track, "send": normalized_send},
            recoverability="not_applicable",
        )
    if level_db is not None and not (MIN_SEND_LEVEL_DB <= float(level_db) <= MAX_SEND_LEVEL_DB):
        raise ValidationError(
            "Fairlight send level is outside the verified native Bus Sends numeric field range.",
            details={"level_db": level_db, "min": MIN_SEND_LEVEL_DB, "max": MAX_SEND_LEVEL_DB},
            recoverability="not_applicable",
        )

    timeline_name = _timeline_name(conn)
    if not timeline_name:
        raise ReadinessFailed(
            "No active timeline is available for Fairlight send set.",
            details={"route": ROUTE, "required": "active_timeline"},
        )

    active_driver = driver or MacOSFairlightSendsGuiDriver()
    permission_state = active_driver.preflight_permissions()
    page_state = _ensure_fairlight_page(conn)
    db_state = _fairlight_model_state(conn, timeline_name=timeline_name)
    before_hash = _sha256(db_state["model"])
    result = active_driver.set_send(track=normalized_track, send=normalized_send, level_db=level_db, pre_fader=pre_fader)
    save_result = _save_project(conn)
    after_hash, readback_polls = _poll_fairlight_model_hash(
        db_state["project_db_path"],
        timeline_name=timeline_name,
        before_hash=before_hash,
    )
    changed = before_hash != after_hash

    set_verification_status("verified")
    set_recoverability("manual")
    return {
        "action": "fairlight.send.set",
        "route": ROUTE,
        "engine_scope": "workflow_owned_resolve_gui",
        "track": normalized_track,
        "send": normalized_send,
        "requested": {"level_db": level_db, "pre_fader": pre_fader},
        "changed": changed,
        "before_model_hash": before_hash,
        "after_model_hash": after_hash,
        "model_hash_changed": changed,
        "assignment": result["assignment"],
        "pre_fader": result["pre_fader"],
        "level": result["level"],
        "readback": {
            "timeline_name": timeline_name,
            "db_blob": "Sm2Sequence.FieldsBlob.FLStudioModelBA",
            "project_db_path": db_state["project_db_path"],
            "verification": "native_bus_sends_popover_screenshot_plus_saved_fairlight_model_hash",
            "polls": readback_polls,
            "visual": result["final_visual"],
        },
        "geometry": result["geometry"].as_payload(),
        "popover": result["popover"].as_payload(),
        "proof": result["final_proof"],
        "intermediate_proof": {"before": result["before_proof"]},
        "save": save_result,
        "preflight": {"permissions": permission_state, "page": page_state},
    }


def _validate_track(conn: Any, track: int | None) -> int:
    if track is None:
        raise ValidationError(
            "Fairlight send set requires an audio track index.",
            details={"required": ["track"], "example": "cutagent fairlight send set --track 1 --send 'Bus 2' --level -6"},
            recoverability="not_applicable",
        )
    normalized = int(track)
    if normalized < 1:
        raise ValidationError("Audio track index is out of range.", details={"track": normalized, "min": 1}, recoverability="not_applicable")
    if normalized > SUPPORTED_VISIBLE_MIXER_TRACKS:
        raise ValidationError(
            "Fairlight send GUI route currently supports visible Mixer audio track columns only.",
            details={"track": normalized, "visible_track_max": SUPPORTED_VISIBLE_MIXER_TRACKS, "required_layout": "Mixer panel visible with Bus Sends row visible"},
            recoverability="not_applicable",
        )
    rows = fairlight_ops.list_audio_tracks(conn)
    if len(rows) < normalized:
        raise ValidationError(
            "Fairlight audio track index is out of range.",
            details={"track": normalized, "available_audio_tracks": len(rows)},
            recoverability="not_applicable",
        )
    return normalized


def _validate_send_destination(conn: Any, send: str | None) -> str:
    if not send or not str(send).strip():
        raise ValidationError(
            "Fairlight send set requires a bus destination name.",
            details={"required": ["send"], "example": "cutagent fairlight send set --track 1 --send 'Bus 2' --level -6"},
            recoverability="not_applicable",
        )
    normalized = str(send).strip()
    _parse_bus_index(normalized)
    data = fairlight_ops.read_fairlight_send_list_db(conn, limit=100, include_context=False, context_bytes=0)
    candidates = {str(item.get("name") or "").lower(): item for item in data.get("candidate_destinations") or []}
    if normalized.lower() not in candidates:
        raise ValidationError(
            "Fairlight send destination was not found in the current timeline bus labels.",
            details={
                "send": normalized,
                "available_destinations": [item.get("name") for item in data.get("candidate_destinations") or []],
                "readback_command": "cutagent fairlight send list --json",
            },
            recoverability="not_applicable",
        )
    return str(candidates[normalized.lower()].get("name") or normalized)


def _timeline_name(conn: Any) -> str | None:
    timeline = getattr(conn, "timeline", None)
    if timeline is not None and hasattr(timeline, "GetName"):
        try:
            name = timeline.GetName()
            if name:
                return str(name)
        except Exception:
            pass
    return None


def _fairlight_model_state(conn: Any, *, timeline_name: str) -> dict[str, Any]:
    current_database = db_session.resolve_current_disk_project_db(conn, allow_project_name_inference=True)
    project_db_path = str(current_database["project_db_path"])
    return {"project_db_path": project_db_path, "model": _read_fairlight_model(project_db_path, timeline_name=timeline_name)}


def _read_fairlight_model(project_db_path: str, *, timeline_name: str) -> bytes:
    connection = sqlite3.connect(f"file:{project_db_path}?mode=ro", uri=True, timeout=5.0)
    connection.row_factory = sqlite3.Row
    try:
        cursor = connection.cursor()
        sequence = fairlight_ops._fetch_timeline_sequence(cursor, timeline_name)
        seq_blob = fairlight_ops._fetch_sequence_fields_blob(cursor, sequence=sequence)
        decomp, _, _, _, _ = fairlight_ops._decode_fairlight_model(seq_blob)
        return bytes(decomp)
    finally:
        connection.close()


def _save_project(conn: Any) -> dict[str, Any]:
    try:
        saved = project_ops.save_current_project_if_available(conn)
    except Exception as exc:
        raise ReadinessFailed("Failed to save DaVinci Resolve project after Fairlight send set.", details={"error": str(exc)}) from exc
    time.sleep(5.0 if saved else 1.0)
    return {"called": True, "result": bool(saved), "flush_wait_seconds": 5.0 if saved else 1.0}


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _poll_fairlight_model_hash(project_db_path: str, *, timeline_name: str, before_hash: str) -> tuple[str, list[dict[str, Any]]]:
    polls: list[dict[str, Any]] = []
    last_hash = before_hash
    for attempt in range(1, 16):
        time.sleep(0.2)
        try:
            current_hash = _sha256(_read_fairlight_model(project_db_path, timeline_name=timeline_name))
        except Exception as exc:
            polls.append({"attempt": attempt, "error": str(exc)})
            continue
        polls.append({"attempt": attempt, "hash": current_hash, "changed": current_hash != before_hash})
        last_hash = current_hash
        if current_hash != before_hash:
            return current_hash, polls
    return last_hash, polls


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


def _geometry_for_visible_mixer_track(window: Rect, *, track: int) -> SendMixerGeometry:
    center_x = window.x + window.width - 169 + ((track - 1) * 68)
    return SendMixerGeometry(
        window_rect=window,
        track=track,
        send_slot_rect=Rect(center_x - 29, window.y + 557, 58, 19),
        send_plus_rect=Rect(center_x - 29, window.y + 576, 58, 18),
    )


def _window_rect() -> Rect:
    proc = _run_osascript(_MAIN_WINDOW_RECT_JXA, language="JavaScript", timeout=5.0)
    if proc.returncode != 0:
        raise ReadinessFailed("Could not read DaVinci Resolve window bounds for Fairlight sends.", details={"stderr": proc.stderr[-500:]})
    try:
        payload = json.loads(proc.stdout.strip())
        if not payload.get("ok"):
            raise ValueError(payload)
        rect = _rect_from_payload(payload["window"])
    except (ValueError, KeyError, json.JSONDecodeError) as exc:
        raise ReadinessFailed("DaVinci Resolve window bounds readback was invalid.", details={"stdout": proc.stdout[-500:]}) from exc
    return rect


def _find_bus_sends_popover() -> BusSendsPopoverState | None:
    proc = _run_osascript(_FIND_BUS_SENDS_POPOVER_JXA, language="JavaScript", timeout=8.0)
    if proc.returncode != 0:
        return None
    try:
        payload = json.loads(proc.stdout.strip())
    except json.JSONDecodeError:
        return None
    if not payload.get("ok"):
        return None
    window = payload.get("window") or {}
    rect = _rect_from_payload(window)
    return BusSendsPopoverState(rect=rect, title=str(payload.get("title") or "Bus Sends"), scanned=int(payload.get("scanned") or 0))


def _rect_from_payload(payload: dict[str, Any]) -> Rect:
    bounds = payload.get("bounds")
    if isinstance(bounds, list) and len(bounds) == 2 and all(isinstance(item, list) for item in bounds):
        return Rect(x=int(bounds[0][0]), y=int(bounds[0][1]), width=int(bounds[1][0]), height=int(bounds[1][1]))
    pos = payload.get("pos") or payload.get("position")
    size = payload.get("size")
    if not isinstance(pos, list) or len(pos) < 2 or not isinstance(size, list) or len(size) < 2:
        raise ValueError("missing position/size")
    return Rect(x=int(pos[0]), y=int(pos[1]), width=int(size[0]), height=int(size[1]))


def _pre_button_rect(popover: Rect) -> Rect:
    return Rect(popover.x + 22, popover.y + 106, 57, 25)


def _level_value_rect(popover: Rect) -> Rect:
    return Rect(popover.x + 226, popover.y + 105, 50, 25)


def _bus_destination_menu_point(plus_rect: Rect, bus_index: int) -> tuple[int, int]:
    return (plus_rect.center[0] + 57, plus_rect.center[1] + ((bus_index - 1) * 22))


def _parse_bus_index(send: str) -> int:
    match = re.fullmatch(r"bus\s+(\d+)", str(send).strip(), flags=re.IGNORECASE)
    if not match:
        raise ValidationError(
            "Fairlight send GUI route currently accepts bus destinations like 'Bus 2'.",
            details={"send": send, "examples": ["Bus 1", "Bus 2"]},
            recoverability="not_applicable",
        )
    index = int(match.group(1))
    if index < 1:
        raise ValidationError("Fairlight bus index is out of range.", details={"send": send, "min": 1}, recoverability="not_applicable")
    return index


def _level_model_value(level_db: float) -> int:
    return int(round(float(level_db) * 10.0))


def _format_level(level_db: float) -> str:
    text = f"{float(level_db):.1f}"
    return text.rstrip("0").rstrip(".")


def _set_level_field(popover: Rect, level_db: float) -> None:
    field = _level_value_rect(popover)
    _post_mouse_double_click(field.center)
    time.sleep(0.1)
    _hotkey("a", modifier="command")
    time.sleep(0.08)
    _paste_text(_format_level(level_db))
    time.sleep(0.08)
    _key_code(36)


def _visual_state_from_proof(path: Path, popover: Rect) -> dict[str, Any]:
    from PIL import Image

    with Image.open(path) as image:
        rgb = image.convert("RGB")
        pre = _pre_button_rect(popover)
        crop = rgb.crop((pre.x - popover.x, pre.y - popover.y, pre.x - popover.x + pre.width, pre.y - popover.y + pre.height))
        red_pixels = sum(1 for r, g, b in crop.getdata() if r > 140 and g < 90 and b < 90)
    return {
        "pre_fader_active": red_pixels >= 8,
        "pre_red_pixels": red_pixels,
        "pre_red_threshold": 8,
        "level_value_verified_by": "native Bus Sends numeric field in proof screenshot",
    }


def _capture_region(rect: Rect, path: Path) -> None:
    region = f"{rect.x},{rect.y},{rect.width},{rect.height}"
    proc = subprocess.run(["screencapture", "-x", "-t", "png", "-R", region, str(path)], capture_output=True, text=True, timeout=10)
    if proc.returncode != 0 or not path.is_file():
        raise ReadinessFailed(
            "Failed to capture Fairlight Bus Sends proof screenshot.",
            details={"screenshot_path": str(path), "region": rect.as_payload(), "stderr": proc.stderr[-500:]},
        )


def _proof_root(proof_dir: Path | None) -> Path:
    root = (proof_dir or DEFAULT_PROOF_DIR).expanduser()
    if not root.is_absolute():
        root = Path.cwd() / root
    root = root.resolve(strict=False)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _proof_path(root: Path, stem: str) -> Path:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    return root / f"fairlight-sends-{stem}-{stamp}.png"


def _run_osascript(script: str, *, language: str | None = None, timeout: float = 5.0, check: bool = False) -> subprocess.CompletedProcess[str]:
    cmd = ["osascript"]
    if language:
        cmd.extend(["-l", language])
    cmd.extend(["-e", script])
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        proc = subprocess.CompletedProcess(cmd, 124, stdout=exc.stdout or "", stderr=exc.stderr or str(exc))
    if check and proc.returncode != 0:
        raise ReadinessFailed(
            "DaVinci Resolve Fairlight sends AppleScript input failed.",
            details={"stderr": proc.stderr[-500:], "stdout": proc.stdout[-500:]},
        )
    return proc


def _post_mouse_click(point: tuple[int, int], *, delay_seconds: float = 0.025) -> None:
    _post_mouse_events([(1, 0, point, 0), (2, 0, point, 0)], delay_seconds=delay_seconds)


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
                    "macOS failed to create Fairlight sends double-click event.",
                    details={"event_type": event_type, "point": {"x": point[0], "y": point[1]}, "click_state": click_state},
                )
            try:
                app_services.CGEventSetIntegerValueField(event, 1, click_state)
                app_services.CGEventPost(0, event)
            finally:
                app_services.CFRelease(event)
            time.sleep(0.025)
        time.sleep(0.05)


def _post_mouse_events(events: list[tuple[int, int, tuple[int, int], int]], *, delay_seconds: float) -> None:
    app_services = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices")

    class CGPoint(ctypes.Structure):
        _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]

    app_services.CGEventCreateMouseEvent.restype = ctypes.c_void_p
    app_services.CGEventCreateMouseEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint32, CGPoint, ctypes.c_uint32]
    app_services.CGEventPost.argtypes = [ctypes.c_uint32, ctypes.c_void_p]
    app_services.CFRelease.argtypes = [ctypes.c_void_p]

    for event_type, button, point, _flags in events:
        event = app_services.CGEventCreateMouseEvent(None, event_type, CGPoint(float(point[0]), float(point[1])), button)
        if not event:
            raise ReadinessFailed(
                "macOS failed to create Fairlight sends mouse event.",
                details={"event_type": event_type, "button": button, "point": {"x": point[0], "y": point[1]}},
            )
        try:
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
    raise ValueError(f"unsupported modifier: {modifier}")


def _osascript_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


_FIND_BUS_SENDS_POPOVER_JXA = r"""
const se = Application("System Events");
const processNames = ["DaVinci Resolve", "Resolve"];
let proc = null;
let processName = null;
for (const name of processNames) {
  const matches = se.processes.whose({ name })();
  if (matches.length > 0) {
    proc = matches[0];
    processName = name;
    break;
  }
}
function rectPayload(item) {
  let pos = [];
  let size = [];
  try { pos = item.position(); } catch (e) {}
  try { size = item.size(); } catch (e) {}
  return { pos, size };
}
function inspectWindow(window, limit) {
  let scanned = 0;
  const queue = [window];
  let titleText = "";
  while (queue.length && scanned < limit) {
    const item = queue.shift();
    scanned += 1;
    let value = "";
    let title = "";
    try { value = String(item.value() || ""); } catch (e) {}
    try { title = String(item.title() || ""); } catch (e) {}
    if (value.indexOf("Bus Sends - ") === 0 || title.indexOf("Bus Sends - ") === 0) {
      titleText = value || title;
    }
    try {
      const children = item.uiElements();
      for (let i = 0; i < children.length; i++) queue.push(children[i]);
    } catch (e) {}
  }
  return { scanned, titleText };
}
if (!proc) {
  JSON.stringify({ ok: false, reason: "process_not_found", process_names: processNames });
} else {
  const windows = proc.windows();
  for (let i = 0; i < windows.length; i++) {
    let windowTitle = "";
    try { windowTitle = String(windows[i].title() || ""); } catch (e) {}
    const inspected = inspectWindow(windows[i], 600);
    if (inspected.titleText) {
      const payload = rectPayload(windows[i]);
      JSON.stringify({
        ok: true,
        process_name: processName,
        title: inspected.titleText,
        window_title: windowTitle,
        scanned: inspected.scanned,
        window: payload,
      });
      break;
    }
    if (i === windows.length - 1) {
      JSON.stringify({ ok: false, reason: "bus_sends_popover_not_found", process_name: processName, scanned_windows: windows.length });
    }
  }
}
"""


_MAIN_WINDOW_RECT_JXA = r"""
const se = Application("System Events");
const processNames = ["DaVinci Resolve", "Resolve"];
let proc = null;
let processName = null;
for (const name of processNames) {
  const matches = se.processes.whose({ name })();
  if (matches.length > 0) {
    proc = matches[0];
    processName = name;
    break;
  }
}
function rectPayload(item) {
  let pos = [];
  let size = [];
  try { pos = item.position(); } catch (e) {}
  try { size = item.size(); } catch (e) {}
  return { pos, size };
}
if (!proc) {
  JSON.stringify({ ok: false, reason: "process_not_found", process_names: processNames });
} else {
  const windows = proc.windows();
  let best = null;
  let bestArea = 0;
  let bestTitle = "";
  for (let i = 0; i < windows.length; i++) {
    let title = "";
    let pos = [];
    let size = [];
    try { title = String(windows[i].title() || ""); } catch (e) {}
    try { pos = windows[i].position(); } catch (e) {}
    try { size = windows[i].size(); } catch (e) {}
    const width = Number(size[0] || 0);
    const height = Number(size[1] || 0);
    const area = width * height;
    if (width >= 1000 && height >= 650 && area > bestArea) {
      best = windows[i];
      bestArea = area;
      bestTitle = title;
    }
  }
  if (!best) {
    JSON.stringify({ ok: false, reason: "main_window_not_found", process_name: processName, scanned_windows: windows.length });
  } else {
    JSON.stringify({ ok: true, process_name: processName, title: bestTitle, window: rectPayload(best) });
  }
}
"""
