"""Workflow-owned GUI-assisted Fairlight VCA assignment route.

This module only drives DaVinci Resolve's native Fairlight ``VCA Assign``
dialog. It is intentionally not a general GUI automation surface.
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

from ..errors import (
    GuiPermissionMissing,
    ReadinessFailed,
    ResolveWindowNotFound,
    ResolveWindowNotReady,
    ValidationError,
)
from ..output import set_recoverability, set_verification_status
from . import db_session, fairlight_ops

ROUTE = "fairlight.vca_assign_gui"
ENGINE = "resolve_gui"
DEFAULT_PROOF_DIR = Path("artifacts") / "fairlight-vca-gui"
PROCESS_NAMES = ("DaVinci Resolve", "Resolve")
VISIBLE_VCA_MIN = 1
VISIBLE_VCA_MAX = 20


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
class VcaDialogState:
    window_rect: Rect
    title: str
    scanned: int

    def as_payload(self) -> dict[str, Any]:
        return {
            "window_rect": self.window_rect.as_payload(),
            "title": self.title,
            "scanned": self.scanned,
        }


def parse_vca_index(value: str | int | None) -> int:
    text = str(value or "").strip()
    if not text:
        raise ValidationError(
            "Fairlight VCA assignment requires a VCA label or index.",
            details={"vca": value},
            recoverability="not_applicable",
        )
    match = re.fullmatch(r"(?:vca\s*)?(\d+)", text, flags=re.IGNORECASE)
    if not match:
        raise ValidationError(
            "Fairlight VCA assignment currently accepts VCA labels like 'VCA 1' or numeric VCA indices.",
            details={"vca": value, "examples": ["VCA 1", "1"]},
            recoverability="not_applicable",
        )
    index = int(match.group(1))
    if index < VISIBLE_VCA_MIN or index > VISIBLE_VCA_MAX:
        raise ValidationError(
            "Fairlight VCA GUI assignment currently supports the visible native VCA 1-20 grid.",
            details={"vca": value, "vca_index": index, "min": VISIBLE_VCA_MIN, "max": VISIBLE_VCA_MAX},
            recoverability="not_applicable",
        )
    return index


class MacOSFairlightVcaAssignGuiDriver:
    """Internal macOS driver scoped to Fairlight VCA assignment."""

    process_names = PROCESS_NAMES

    def preflight_permissions(self) -> dict[str, Any]:
        if platform.system() != "Darwin":
            raise GuiPermissionMissing(
                "Fairlight VCA assignment GUI-assisted route requires macOS.",
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

    def open_dialog(self) -> VcaDialogState:
        proc = _run_osascript(_OPEN_VCA_ASSIGN_JXA, language="JavaScript", timeout=20.0)
        if proc.returncode != 0:
            raise ResolveWindowNotReady(
                "Could not open DaVinci Resolve Fairlight VCA Assign dialog.",
                details={"stderr": proc.stderr[-1000:], "stdout": proc.stdout[-500:]},
            )
        payload = _json_payload(proc.stdout, "DaVinci Resolve VCA Assign open probe returned invalid data.")
        if not payload.get("ok"):
            error_cls = ResolveWindowNotFound if payload.get("reason") in {"process_not_found", "window_not_found"} else ReadinessFailed
            raise error_cls("DaVinci Resolve Fairlight VCA Assign dialog is not available.", details=payload)
        return _payload_to_state(payload)

    def assign(self, *, vca_index: int, track: int) -> dict[str, Any]:
        if track < 1:
            raise ValidationError(
                "Fairlight VCA assignment requires an audio track index of 1 or greater.",
                details={"track": track, "min": 1},
                recoverability="not_applicable",
            )
        dialog = self.open_dialog()
        vca_rect = _vca_tile_rect(dialog.window_rect, vca_index)
        track_rect = _track_tile_rect(dialog.window_rect, track)
        _post_mouse_click(vca_rect.center)
        time.sleep(0.15)
        _post_mouse_click(track_rect.center)
        time.sleep(0.35)
        return {
            "dialog": dialog,
            "vca_rect": vca_rect,
            "track_rect": track_rect,
        }

    def close_dialog(self, state: VcaDialogState) -> None:
        close_rect = _close_button_rect(state.window_rect)
        _post_mouse_click(close_rect.center)
        time.sleep(0.5)

    def capture_proof(self, state: VcaDialogState, path: Path) -> dict[str, Any]:
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
                "Failed to capture Fairlight VCA assignment proof screenshot.",
                details={"screenshot_path": str(path), "region": rect.as_payload(), "stderr": proc.stderr[-500:]},
            )
        return {"screenshot_path": str(path), "bytes": path.stat().st_size, "region": rect.as_payload()}

    def _accessibility_enabled(self) -> bool:
        proc = _run_osascript('tell application "System Events" to get UI elements enabled', timeout=3.0)
        return proc.returncode == 0 and proc.stdout.strip().lower() == "true"

    def _accessibility_trusted(self) -> bool:
        try:
            app_services = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices")
            app_services.AXIsProcessTrusted.restype = ctypes.c_bool
            return bool(app_services.AXIsProcessTrusted())
        except Exception:
            return False

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


def run_vca_assign(
    conn: Any,
    *,
    vca: str,
    track: int,
    proof_dir: Path | None = None,
    driver: MacOSFairlightVcaAssignGuiDriver | None = None,
) -> dict[str, Any]:
    vca_index = parse_vca_index(vca)
    if track < 1:
        raise ValidationError(
            "Fairlight VCA assignment requires an audio track index of 1 or greater.",
            details={"track": track, "min": 1},
            recoverability="not_applicable",
        )
    timeline_name = _timeline_name(conn)
    if not timeline_name:
        raise ReadinessFailed(
            "No active timeline is available for Fairlight VCA assignment.",
            details={"route": ROUTE, "required": "active_timeline"},
        )

    active_driver = driver or MacOSFairlightVcaAssignGuiDriver()
    permission_state = active_driver.preflight_permissions()
    page_state = _ensure_fairlight_page(conn)
    db_state = _fairlight_model_state(conn, timeline_name=timeline_name)
    before_model = db_state["model"]
    before_hash = _sha256(before_model)
    result = active_driver.assign(vca_index=vca_index, track=int(track))
    dialog = result["dialog"]
    proof_root = _proof_root(proof_dir)
    proof = active_driver.capture_proof(dialog, _proof_path(proof_root, "assign"))
    active_driver.close_dialog(dialog)
    after_hash, readback_polls = _poll_fairlight_model_hash(
        db_state["project_db_path"],
        timeline_name=timeline_name,
        before_hash=before_hash,
    )
    changed = before_hash != after_hash

    set_verification_status("verified")
    set_recoverability("manual")
    return {
        "action": "fairlight.vca.assign",
        "route": ROUTE,
        "requested_vca": vca,
        "vca_index": vca_index,
        "track": int(track),
        "changed": changed,
        "before_model_hash": before_hash,
        "after_model_hash": after_hash,
        "model_hash_changed": changed,
        "readback": {
            "timeline_name": timeline_name,
            "db_blob": "Sm2Sequence.FieldsBlob.FLStudioModelBA",
            "project_db_path": db_state["project_db_path"],
            "verification": "native_dialog_screenshot_plus_fairlight_model_hash",
            "polls": readback_polls,
        },
        "dialog": dialog.as_payload(),
        "vca_rect": result["vca_rect"].as_payload(),
        "track_rect": result["track_rect"].as_payload(),
        "proof": proof,
        "preflight": {"permissions": permission_state, "page": page_state},
    }


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


def _payload_to_state(payload: dict[str, Any]) -> VcaDialogState:
    try:
        window = payload["window"]
        return VcaDialogState(
            window_rect=_rect_from_payload(window),
            title=str(payload.get("title") or "VCA Assign"),
            scanned=int(payload.get("scanned") or 0),
        )
    except Exception as exc:
        raise ResolveWindowNotReady(
            "DaVinci Resolve VCA Assign probe did not include a usable dialog.",
            details={"payload": payload},
        ) from exc


def _rect_from_payload(payload: dict[str, Any]) -> Rect:
    pos = payload.get("pos") or payload.get("position")
    size = payload.get("size")
    if not isinstance(pos, list) or len(pos) < 2 or not isinstance(size, list) or len(size) < 2:
        raise ValueError("missing position/size")
    rect = Rect(x=int(pos[0]), y=int(pos[1]), width=int(size[0]), height=int(size[1]))
    if rect.width <= 0 or rect.height <= 0:
        raise ValueError("invalid rect")
    return rect


def _vca_tile_rect(window_rect: Rect, vca_index: int) -> Rect:
    zero = vca_index - 1
    col = zero % 10
    row = zero // 10
    return Rect(
        x=window_rect.x + 27 + col * 99,
        y=window_rect.y + 88 + row * 51,
        width=88,
        height=40,
    )


def _track_tile_rect(window_rect: Rect, track: int) -> Rect:
    zero = track - 1
    col = zero % 10
    row = zero // 10
    return Rect(
        x=window_rect.x + 27 + col * 99,
        y=window_rect.y + 286 + row * 50,
        width=88,
        height=40,
    )


def _close_button_rect(window_rect: Rect) -> Rect:
    return Rect(x=window_rect.x + window_rect.width - 126, y=window_rect.y + window_rect.height - 43, width=110, height=24)


def _proof_root(proof_dir: Path | None) -> Path:
    root = (proof_dir or DEFAULT_PROOF_DIR).expanduser()
    if not root.is_absolute():
        root = Path.cwd() / root
    root = root.resolve(strict=False)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _proof_path(root: Path, stem: str) -> Path:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    return root / f"fairlight-vca-{stem}-{stamp}.png"


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
                "macOS failed to create Fairlight VCA mouse event.",
                details={"event_type": event_type, "point": point},
            )
        try:
            app_services.CGEventPost(0, event)
        finally:
            app_services.CFRelease(event)
        time.sleep(delay_seconds)


_OPEN_VCA_ASSIGN_JXA = r"""
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
function inspectDialog() {
  const windows = proc.windows();
  let scanned = 0;
  for (let i = 0; i < windows.length; i++) {
    let title = "";
    try { title = String(windows[i].title() || ""); } catch (e) {}
    const queue = [windows[i]];
    let hasVcaAssign = false;
    let hasAvailableTracks = false;
    while (queue.length && scanned < 2400) {
      const item = queue.shift();
      scanned += 1;
      let value = "";
      let itemTitle = "";
      try { value = String(item.value() || ""); } catch (e) {}
      try { itemTitle = String(item.title() || ""); } catch (e) {}
      if (value === "VCA Assign" || itemTitle === "VCA Assign") hasVcaAssign = true;
      if (value === "Available Tracks" || itemTitle === "Available Tracks") hasAvailableTracks = true;
      try {
        const children = item.uiElements();
        for (let j = 0; j < children.length; j++) queue.push(children[j]);
      } catch (e) {}
    }
    if (hasVcaAssign && hasAvailableTracks) {
      return {
        ok: true,
        process_name: processName,
        title: title || "VCA Assign",
        scanned,
        window: rectPayload(windows[i]),
      };
    }
  }
  return { ok: false, reason: "vca_assign_dialog_not_found", process_name: processName, scanned };
}
if (!proc) {
  JSON.stringify({ ok: false, reason: "process_not_found", process_names: processNames });
} else {
  try {
    const item = proc.menuBars[0].menuBarItems.byName("Fairlight").menus[0].menuItems.byName("VCA Assign…");
    item.click();
  } catch (e) {
    JSON.stringify({ ok: false, reason: "vca_assign_menu_unavailable", process_name: processName, error: String(e) });
  }
  delay(0.5);
  JSON.stringify(inspectDialog());
}
"""
