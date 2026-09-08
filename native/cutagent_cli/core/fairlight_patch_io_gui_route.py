"""Workflow-owned GUI-assisted Fairlight Patch Input/Output route.

This module only drives DaVinci Resolve's native Fairlight
``Patch Input/Output`` dialog. It is intentionally scoped to this dialog and
does not expose a general GUI automation surface.
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
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

from ..errors import (
    GuiPermissionMissing,
    ReadinessFailed,
    ResolveWindowNotFound,
    ResolveWindowNotReady,
    ValidationError,
)
from ..output import set_recoverability, set_verification_status
from . import db_session, fairlight_ops

ROUTE = "fairlight.patch_io_gui"
ENGINE = "resolve_gui"
DEFAULT_PROOF_DIR = Path("artifacts") / "fairlight-patch-io-gui"
PROCESS_NAMES = ("DaVinci Resolve", "Resolve")

SOURCE_CATEGORIES = {
    "audio_inputs": {"label": "Audio Inputs", "index": 0},
    "bus_out": {"label": "Bus Out", "index": 1},
    "monitor_direct": {"label": "Monitor Direct", "index": 2},
    "monitor_out": {"label": "Monitor Out", "index": 3},
    "system_generator": {"label": "System Generator", "index": 4},
    "track_direct": {"label": "Track Direct", "index": 5},
    "track_reproduction": {"label": "Track Reproduction", "index": 6},
}
DESTINATION_CATEGORIES = {
    "audio_outputs": {"label": "Audio Outputs", "index": 0},
    "talkback": {"label": "Talkback", "index": 1},
    "track_input": {"label": "Track Input", "index": 2},
}
SYSTEM_GENERATOR_TILES = {"osc": 0, "noise": 1, "beeps": 2, "timecode": 3}


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
class PatchDialogState:
    window_rect: Rect
    title: str
    source_category: str | None
    destination_category: str | None
    source_summary: str | None
    destination_summary: str | None
    scanned: int

    def as_payload(self) -> dict[str, Any]:
        return {
            "window_rect": self.window_rect.as_payload(),
            "title": self.title,
            "source_category": self.source_category,
            "destination_category": self.destination_category,
            "source_summary": self.source_summary,
            "destination_summary": self.destination_summary,
            "scanned": self.scanned,
        }


@dataclass(frozen=True)
class PatchRequest:
    mode: str
    source_category_key: str
    destination_category_key: str
    source_tile_index: int
    destination_tile_index: int
    source_label: str
    destination_label: str
    verification: str

    def as_payload(self) -> dict[str, Any]:
        return asdict(self)


def build_patch_request(*, track: int | None, input_name: str | None, output_name: str | None) -> PatchRequest:
    if track is None or int(track) < 1:
        raise ValidationError(
            "Fairlight patch I/O requires --track with an audio track index.",
            details={"track": track, "required_option": "--track"},
            recoverability="not_applicable",
        )
    has_input = bool((input_name or "").strip())
    has_output = bool((output_name or "").strip())
    if has_input == has_output:
        raise ValidationError(
            "Fairlight patch I/O requires exactly one of --input or --output.",
            details={"input": input_name, "output": output_name},
            recoverability="not_applicable",
        )

    first_track_tile = _first_track_channel_tile(int(track))
    if has_output:
        destination_index = _parse_one_based_tile_index(output_name, option="--output")
        return PatchRequest(
            mode="track_direct_to_audio_output",
            source_category_key="track_direct",
            destination_category_key="audio_outputs",
            source_tile_index=first_track_tile,
            destination_tile_index=destination_index,
            source_label=f"Audio {int(track)}",
            destination_label=str(output_name).strip(),
            verification="native_dialog_screenshot_plus_fairlight_model_hash",
        )

    source_index, source_label = _input_source_tile(input_name)
    return PatchRequest(
        mode="source_to_track_input",
        source_category_key="system_generator" if _normalize(input_name) in SYSTEM_GENERATOR_TILES else "audio_inputs",
        destination_category_key="track_input",
        source_tile_index=source_index,
        destination_tile_index=first_track_tile,
        source_label=source_label,
        destination_label=f"Audio {int(track)}",
        verification="native_dialog_screenshot_plus_reopened_dialog_readback",
    )


class MacOSFairlightPatchIoGuiDriver:
    """Internal macOS driver scoped to the Fairlight Patch Input/Output dialog."""

    process_names = PROCESS_NAMES

    def preflight_permissions(self) -> dict[str, Any]:
        if platform.system() != "Darwin":
            raise GuiPermissionMissing(
                "Fairlight Patch Input/Output GUI-assisted route requires macOS.",
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

    def open_dialog(self) -> PatchDialogState:
        proc = _run_osascript(_OPEN_PATCH_IO_JXA, language="JavaScript", timeout=20.0)
        if proc.returncode != 0:
            raise ResolveWindowNotReady(
                "Could not open DaVinci Resolve Fairlight Patch Input/Output dialog.",
                details={"stderr": proc.stderr[-1000:], "stdout": proc.stdout[-500:]},
            )
        payload = _json_payload(proc.stdout, "DaVinci Resolve Patch Input/Output open probe returned invalid data.")
        if not payload.get("ok"):
            error_cls = ResolveWindowNotFound if payload.get("reason") in {"process_not_found", "window_not_found"} else ReadinessFailed
            raise error_cls("DaVinci Resolve Fairlight Patch Input/Output dialog is not available.", details=payload)
        return _payload_to_state(payload)

    def read_dialog(self) -> PatchDialogState:
        proc = _run_osascript(_INSPECT_PATCH_IO_JXA, language="JavaScript", timeout=10.0)
        if proc.returncode != 0:
            raise ResolveWindowNotReady(
                "Could not inspect DaVinci Resolve Fairlight Patch Input/Output dialog.",
                details={"stderr": proc.stderr[-1000:], "stdout": proc.stdout[-500:]},
            )
        payload = _json_payload(proc.stdout, "DaVinci Resolve Patch Input/Output inspect probe returned invalid data.")
        if not payload.get("ok"):
            raise ResolveWindowNotReady(
                "DaVinci Resolve Fairlight Patch Input/Output dialog is not available for readback.",
                details=payload,
            )
        return _payload_to_state(payload)

    def patch(self, request: PatchRequest) -> dict[str, Any]:
        dialog = self.open_dialog()
        self._select_source_category(dialog.window_rect, request.source_category_key)
        self._select_destination_category(dialog.window_rect, request.destination_category_key)
        time.sleep(0.2)
        source_rect = _source_tile_rect(dialog.window_rect, request.source_tile_index)
        destination_rect = _destination_tile_rect(dialog.window_rect, request.destination_tile_index)
        _post_mouse_click(source_rect.center)
        time.sleep(0.15)
        _post_mouse_click(destination_rect.center)
        time.sleep(0.25)
        selected = self.read_dialog()
        patch_rect = _patch_button_rect(dialog.window_rect)
        _post_mouse_click(patch_rect.center)
        time.sleep(0.5)
        after = self.read_dialog()
        return {
            "dialog": dialog,
            "selected": selected,
            "after": after,
            "source_rect": source_rect,
            "destination_rect": destination_rect,
            "patch_button_rect": patch_rect,
        }

    def close_dialog(self, state: PatchDialogState) -> None:
        close_rect = _close_button_rect(state.window_rect)
        _post_mouse_click(close_rect.center)
        time.sleep(0.4)

    def capture_proof(self, state: PatchDialogState, path: Path) -> dict[str, Any]:
        path.parent.mkdir(parents=True, exist_ok=True)
        rect = state.window_rect
        region = f"{rect.x},{rect.y},{rect.width},{rect.height}"
        proc = subprocess.run(
            ["screencapture", "-x", "-t", "png", "-R", region, str(path)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if proc.returncode != 0 or not path.is_file():
            raise ReadinessFailed(
                "Failed to capture Fairlight Patch Input/Output proof screenshot.",
                details={"screenshot_path": str(path), "region": rect.as_payload(), "stderr": proc.stderr[-500:]},
            )
        return {"screenshot_path": str(path), "bytes": path.stat().st_size, "region": rect.as_payload()}

    def _select_source_category(self, window_rect: Rect, key: str) -> None:
        category = SOURCE_CATEGORIES[key]
        _post_mouse_click(_source_combo_rect(window_rect).center)
        time.sleep(0.12)
        _post_mouse_click(_source_combo_item_rect(window_rect, int(category["index"])).center)
        time.sleep(0.35)

    def _select_destination_category(self, window_rect: Rect, key: str) -> None:
        category = DESTINATION_CATEGORIES[key]
        _post_mouse_click(_destination_combo_rect(window_rect).center)
        time.sleep(0.12)
        _post_mouse_click(_destination_combo_item_rect(window_rect, int(category["index"])).center)
        time.sleep(0.35)

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


def run_patch_io(
    conn: Any,
    *,
    track: int | None,
    input_name: str | None,
    output_name: str | None,
    proof_dir: Path | None = None,
    driver: MacOSFairlightPatchIoGuiDriver | None = None,
) -> dict[str, Any]:
    request = build_patch_request(track=track, input_name=input_name, output_name=output_name)
    timeline_name = _timeline_name(conn)
    if not timeline_name:
        raise ReadinessFailed(
            "No active timeline is available for Fairlight Patch Input/Output.",
            details={"route": ROUTE, "required": "active_timeline"},
        )
    active_driver = driver or MacOSFairlightPatchIoGuiDriver()
    permission_state = active_driver.preflight_permissions()
    page_state = _ensure_fairlight_page(conn)
    request = _with_live_track_tile(conn, request)
    before_model_hash = None
    db_state = None
    if request.mode == "track_direct_to_audio_output":
        db_state = _fairlight_model_state(conn, timeline_name=timeline_name)
        before_model_hash = _sha256(db_state["model"])
    result = active_driver.patch(request)
    proof_root = _proof_root(proof_dir)
    proof = active_driver.capture_proof(result["after"], _proof_path(proof_root, request.mode))
    readback: dict[str, Any] = {
        "timeline_name": timeline_name,
        "verification": request.verification,
        "dialog_after": result["after"].as_payload(),
    }
    changed = True
    after_model_hash = None
    if db_state is not None and before_model_hash is not None:
        after_model_hash, readback_polls = _poll_fairlight_model_hash(
            db_state["project_db_path"],
            timeline_name=timeline_name,
            before_hash=before_model_hash,
        )
        changed = before_model_hash != after_model_hash
        readback.update(
            {
                "db_blob": "Sm2Sequence.FieldsBlob.FLStudioModelBA",
                "project_db_path": db_state["project_db_path"],
                "polls": readback_polls,
            }
        )
    active_driver.close_dialog(result["after"])
    set_verification_status("verified")
    set_recoverability("manual")
    return {
        "action": "fairlight.io.patch",
        "route": ROUTE,
        "mode": request.mode,
        "changed": bool(changed),
        "request": request.as_payload(),
        "track": int(track) if track else None,
        "input": input_name,
        "output": output_name,
        "before_model_hash": before_model_hash,
        "after_model_hash": after_model_hash,
        "model_hash_changed": (before_model_hash != after_model_hash) if before_model_hash and after_model_hash else None,
        "dialog": result["dialog"].as_payload(),
        "selected": result["selected"].as_payload(),
        "after": result["after"].as_payload(),
        "source_rect": result["source_rect"].as_payload(),
        "destination_rect": result["destination_rect"].as_payload(),
        "patch_button_rect": result["patch_button_rect"].as_payload(),
        "readback": readback,
        "proof": proof,
        "preflight": {"permissions": permission_state, "page": page_state},
    }


def _input_source_tile(input_name: str | None) -> tuple[int, str]:
    text = str(input_name or "").strip()
    norm = _normalize(text)
    if norm in SYSTEM_GENERATOR_TILES:
        return SYSTEM_GENERATOR_TILES[norm], text
    return _parse_one_based_tile_index(text, option="--input"), text


def _parse_one_based_tile_index(value: str | None, *, option: str) -> int:
    text = str(value or "").strip()
    match = re.match(r"^(\d+)(?:\b|[:\\-\\s])", text)
    if not match:
        raise ValidationError(
            f"Fairlight Patch Input/Output {option} must start with a one-based visible tile index unless it is a known System Generator source.",
            details={"value": value, "option": option, "examples": ["1", "1: MacBook Speakers Control Room-L", "Osc"]},
            recoverability="not_applicable",
        )
    index = int(match.group(1))
    if index < 1:
        raise ValidationError(
            f"Fairlight Patch Input/Output {option} tile index must be 1 or greater.",
            details={"value": value, "option": option, "min": 1},
            recoverability="not_applicable",
        )
    return index - 1


def _first_track_channel_tile(track: int) -> int:
    if track < 1:
        raise ValidationError(
            "Fairlight Patch Input/Output track index must be 1 or greater.",
            details={"track": track, "min": 1},
            recoverability="not_applicable",
        )
    return track - 1


def _with_live_track_tile(conn: Any, request: PatchRequest) -> PatchRequest:
    track = _track_index_from_label(request.source_label if request.mode == "track_direct_to_audio_output" else request.destination_label)
    if track is None:
        return request
    tile_index = _first_track_channel_tile_from_live_tracks(conn, track)
    if request.mode == "track_direct_to_audio_output":
        return replace(request, source_tile_index=tile_index)
    return replace(request, destination_tile_index=tile_index)


def _track_index_from_label(value: str) -> int | None:
    match = re.search(r"\bAudio\s+(\d+)\b", value, flags=re.IGNORECASE)
    return int(match.group(1)) if match else None


def _first_track_channel_tile_from_live_tracks(conn: Any, track: int) -> int:
    try:
        rows = fairlight_ops.list_audio_tracks(conn)
    except Exception:
        return _first_track_channel_tile(track)
    if len(rows) < track:
        return _first_track_channel_tile(track)
    offset = 0
    for row in rows[: track - 1]:
        offset += _track_channel_count(row.get("format"))
    return offset


def _track_channel_count(track_format: Any) -> int:
    normalized = str(track_format or "mono").strip().lower()
    channels_by_type = getattr(fairlight_ops, "FAIRLIGHT_TRACK_CHANNELS_BY_TYPE", {})
    try:
        return max(1, int(channels_by_type.get(normalized, 1)))
    except Exception:
        return 1


def _normalize(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")


def _timeline_name(conn: Any) -> str | None:
    timeline = getattr(conn, "timeline", None)
    if timeline is not None and hasattr(timeline, "GetName"):
        try:
            name = timeline.GetName()
            if name:
                return str(name)
        except Exception:
            pass
    resolve = getattr(conn, "resolve", None)
    if resolve is not None:
        try:
            project = resolve.GetProjectManager().GetCurrentProject()
            timeline = project.GetCurrentTimeline() if project else None
            name = timeline.GetName() if timeline else None
            if name:
                return str(name)
        except Exception:
            pass
    return None


def _fairlight_model_state(conn: Any, *, timeline_name: str) -> dict[str, Any]:
    current_database = db_session.resolve_current_disk_project_db(conn, allow_project_name_inference=True)
    project_db_path = str(current_database["project_db_path"])
    return {
        "project_db_path": project_db_path,
        "model": _read_fairlight_model(project_db_path, timeline_name=timeline_name),
    }


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


def _payload_to_state(payload: dict[str, Any]) -> PatchDialogState:
    try:
        window = payload["window"]
        return PatchDialogState(
            window_rect=_rect_from_payload(window),
            title=str(payload.get("title") or "Patch Input/Output"),
            source_category=_optional_str(payload.get("source_category")),
            destination_category=_optional_str(payload.get("destination_category")),
            source_summary=_optional_str(payload.get("source_summary")),
            destination_summary=_optional_str(payload.get("destination_summary")),
            scanned=int(payload.get("scanned") or 0),
        )
    except Exception as exc:
        raise ResolveWindowNotReady(
            "DaVinci Resolve Patch Input/Output probe did not include a usable dialog.",
            details={"payload": payload},
        ) from exc


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


def _source_combo_rect(window_rect: Rect) -> Rect:
    return Rect(window_rect.x + 77, window_rect.y + 50, 200, 20)


def _destination_combo_rect(window_rect: Rect) -> Rect:
    return Rect(window_rect.x + 635, window_rect.y + 50, 180, 20)


def _source_combo_item_rect(window_rect: Rect, index: int) -> Rect:
    return Rect(window_rect.x + 78, window_rect.y + 75 + index * 22, 198, 22)


def _destination_combo_item_rect(window_rect: Rect, index: int) -> Rect:
    return Rect(window_rect.x + 636, window_rect.y + 75 + index * 18, 180, 18)


def _source_tile_rect(window_rect: Rect, index: int) -> Rect:
    col = index % 5
    row = index // 5
    return Rect(window_rect.x + 23 + col * 100, window_rect.y + 104 + row * 50, 90, 40)


def _destination_tile_rect(window_rect: Rect, index: int) -> Rect:
    col = index % 5
    row = index // 5
    return Rect(window_rect.x + 553 + col * 100, window_rect.y + 104 + row * 50, 90, 40)


def _patch_button_rect(window_rect: Rect) -> Rect:
    return Rect(window_rect.x + window_rect.width - 126, window_rect.y + window_rect.height - 43, 110, 24)


def _close_button_rect(window_rect: Rect) -> Rect:
    return Rect(window_rect.x + 6, window_rect.y + 5, 20, 20)


def _proof_root(proof_dir: Path | None) -> Path:
    root = (proof_dir or DEFAULT_PROOF_DIR).expanduser()
    if not root.is_absolute():
        root = Path.cwd() / root
    root = root.resolve(strict=False)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _proof_path(root: Path, stem: str) -> Path:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    return root / f"fairlight-patch-io-{stem}-{stamp}.png"


def _json_payload(stdout: str, message: str) -> dict[str, Any]:
    try:
        return json.loads(stdout.strip())
    except json.JSONDecodeError as exc:
        raise ResolveWindowNotReady(message, details={"stdout": stdout[-1000:]}) from exc


def _run_osascript(script: str, *, language: str | None = None, timeout: float = 5.0) -> subprocess.CompletedProcess[str]:
    cmd = ["osascript"]
    if language:
        cmd.extend(["-l", language])
    cmd.extend(["-e", script])
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
                "macOS failed to create Fairlight Patch Input/Output mouse event.",
                details={"event_type": event_type, "point": point},
            )
        try:
            app_services.CGEventPost(0, event)
        finally:
            app_services.CFRelease(event)
        time.sleep(delay_seconds)


_PATCH_IO_INSPECT_BODY = r"""
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
function safe(fn, fallback) {
  try { return fn(); } catch (e) { return fallback; }
}
function rectPayload(item) {
  return { pos: safe(() => item.position(), []), size: safe(() => item.size(), []) };
}
function inspectDialog() {
  const windows = proc.windows();
  let scanned = 0;
  for (let i = 0; i < windows.length; i++) {
    const title = safe(() => String(windows[i].title() || ""), "");
    const queue = [windows[i]];
    const comboTitles = [];
    const summaries = [];
    let hasPatchTitle = title === "Patch Input/Output";
    let hasSource = false;
    let hasDestination = false;
    while (queue.length && scanned < 2600) {
      const item = queue.shift();
      scanned += 1;
      const role = safe(() => String(item.role() || ""), "");
      const value = safe(() => String(item.value() || ""), "");
      const itemTitle = safe(() => String(item.title() || ""), "");
      if (value === "Patch Input/Output" || itemTitle === "Patch Input/Output") hasPatchTitle = true;
      if (value === "Source" || itemTitle === "Source") hasSource = true;
      if (value === "Destination" || itemTitle === "Destination") hasDestination = true;
      if (role === "AXComboBox" && itemTitle) comboTitles.push(itemTitle);
      if (role === "AXStaticText" && /Selected|Patched/.test(value)) summaries.push(value);
      const children = safe(() => item.uiElements(), []);
      for (let j = 0; j < children.length; j++) queue.push(children[j]);
    }
    if (hasPatchTitle && hasSource && hasDestination) {
      return {
        ok: true,
        process_name: processName,
        title: title || "Patch Input/Output",
        scanned,
        window: rectPayload(windows[i]),
        source_category: comboTitles.length > 0 ? comboTitles[0] : null,
        destination_category: comboTitles.length > 1 ? comboTitles[1] : null,
        source_summary: summaries.length > 0 ? summaries[0] : null,
        destination_summary: summaries.length > 1 ? summaries[1] : null,
      };
    }
  }
  return { ok: false, reason: "patch_io_dialog_not_found", process_name: processName, scanned };
}
"""


_INSPECT_PATCH_IO_JXA = _PATCH_IO_INSPECT_BODY + r"""
if (!proc) {
  JSON.stringify({ ok: false, reason: "process_not_found", process_names: processNames });
} else {
  JSON.stringify(inspectDialog());
}
"""


_OPEN_PATCH_IO_JXA = _PATCH_IO_INSPECT_BODY + r"""
if (!proc) {
  JSON.stringify({ ok: false, reason: "process_not_found", process_names: processNames });
} else {
  let before = inspectDialog();
  if (before.ok) {
    JSON.stringify(before);
  } else {
    try {
      const item = proc.menuBars[0].menuBarItems.byName("Fairlight").menus[0].menuItems.byName("Patch Input/Output…");
      item.click();
    } catch (e) {
      JSON.stringify({ ok: false, reason: "patch_io_menu_unavailable", process_name: processName, error: String(e) });
    }
    delay(0.5);
    JSON.stringify(inspectDialog());
  }
}
"""
