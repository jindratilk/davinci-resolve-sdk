"""Workflow-owned GUI-assisted Color Page Power Window tracker route."""

from __future__ import annotations

import hashlib
import json
import platform
import sqlite3
import subprocess
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from ..errors import APICallFailed, ColorPageNotReady, GuiPermissionMissing, ReadinessFailed, ResolveWindowNotReady, ValidationError
from ..output import set_recoverability, set_verification_status
from ..runtime_health import resolve_current_disk_project_db
from . import project_ops
from ._color_page_db.version_body import decompress_version_body
from .magic_mask_gui_route import MacOSMagicMaskGuiDriver, _post_mouse_drag

ROUTE = "color.page_power_window_track_gui"
ENGINE = "resolve_gui"
DEFAULT_PROOF_DIR = Path("artifacts") / "power-window-track-gui"
PROCESS_NAMES = ("DaVinci Resolve", "Resolve")
ALLOWED_SHAPES = {"current", "circle", "linear", "rectangle", "polygon", "curve", "gradient"}
DIRECTION_LABELS = {
    "forward": "Track Forward",
    "reverse": "Track Reverse",
    "one-frame-forward": "Track One Frame Forward",
    "one-frame-reverse": "Track One Frame Reverse",
    "forward-reverse": "Track Forward and Reverse",
}


@dataclass(frozen=True)
class Rect:
    x: int
    y: int
    width: int
    height: int

    def as_payload(self) -> dict[str, int]:
        return asdict(self)


@dataclass(frozen=True)
class GradeFingerprint:
    clip_id: str
    clip_name: str
    version_id: str
    body_size: int
    body_sha256: str
    proto_size: int
    proto_sha256: str

    def as_payload(self) -> dict[str, Any]:
        return asdict(self)


def normalize_shape(value: str | None) -> str:
    token = str(value or "current").strip().lower().replace("_", "-")
    aliases = {"rect": "rectangle", "power-window": "current", "window": "current"}
    token = aliases.get(token, token)
    if token not in ALLOWED_SHAPES:
        raise ValidationError(
            "Color Page Power Window tracker shape must be one of current, circle, linear, rectangle, polygon, curve, or gradient.",
            details={"shape": value, "allowed": sorted(ALLOWED_SHAPES)},
            recoverability="not_applicable",
        )
    return token


def normalize_direction(value: str | None) -> str:
    token = str(value or "forward").strip().lower().replace("_", "-")
    aliases = {
        "f": "forward",
        "b": "reverse",
        "backward": "reverse",
        "back": "reverse",
        "ff": "one-frame-forward",
        "bf": "one-frame-reverse",
        "forward-and-reverse": "forward-reverse",
        "both": "forward-reverse",
        "bi": "forward-reverse",
    }
    token = aliases.get(token, token)
    if token not in DIRECTION_LABELS:
        raise ValidationError(
            "Color Page Power Window tracker direction must be one of forward, reverse, one-frame-forward, one-frame-reverse, or forward-reverse.",
            details={"direction": value, "allowed": sorted(DIRECTION_LABELS)},
            recoverability="not_applicable",
        )
    return token


def validate_wait_seconds(value: float | int | None) -> float:
    try:
        numeric = float(2.0 if value is None else value)
    except (TypeError, ValueError) as exc:
        raise ValidationError("Color Page Power Window tracker wait seconds must be numeric.", details={"wait_seconds": value}) from exc
    if numeric < 0.25 or numeric > 120:
        raise ValidationError(
            "Color Page Power Window tracker wait seconds must be between 0.25 and 120.",
            details={"wait_seconds": numeric, "minimum": 0.25, "maximum": 120},
            recoverability="not_applicable",
        )
    return numeric


class MacOSPowerWindowTrackGuiDriver(MacOSMagicMaskGuiDriver):
    process_names = PROCESS_NAMES

    def preflight_permissions(self) -> dict[str, Any]:
        if platform.system() != "Darwin":
            raise GuiPermissionMissing(
                "Power Window tracking GUI-assisted route requires macOS.",
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

    def find_resolve_window(self) -> Rect:
        rect = super().find_resolve_window()
        return Rect(rect.x, rect.y, rect.width, rect.height)

    def ensure_tracker_panel(self) -> dict[str, Any]:
        script = _TRACKER_PANEL_JXA.replace("__TARGET_WINDOW_JSON__", json.dumps(self._focus_free_ax_window_target()))
        payload = _run_json_jxa(script, "Could not inspect DaVinci Resolve Tracker panel.")
        if not payload.get("ok"):
            raise ReadinessFailed(
                "Open the DaVinci Resolve Color page Tracker panel in Window mode before running Power Window tracking.",
                details=payload,
            )
        return payload

    def click_track_button(self, direction: str) -> dict[str, Any]:
        label = DIRECTION_LABELS[direction]
        script = (
            _CLICK_BUTTON_JXA.replace("__LABEL_JSON__", json.dumps(label.lower()))
            .replace("__TARGET_WINDOW_JSON__", json.dumps(self._focus_free_ax_window_target()))
        )
        payload = _run_json_jxa(script, f"Could not click DaVinci Resolve tracker button '{label}'.")
        if not payload.get("ok"):
            raise ReadinessFailed(
                "DaVinci Resolve Tracker button was not found.",
                details={"direction": direction, "label": label, "probe": payload},
            )
        button = payload.get("button") or {}
        center = (
            int(round(float(button.get("x") or 0) + float(button.get("width") or 0) / 2)),
            int(round(float(button.get("y") or 0) + float(button.get("height") or 0) / 2)),
        )
        if center[0] <= 0 or center[1] <= 0:
            raise ReadinessFailed(
                "DaVinci Resolve Tracker button geometry was unavailable.",
                details={"direction": direction, "label": label, "probe": payload},
            )
        _post_mouse_drag(
            [center],
            target_pid=int(self._focus_free_ax_window_target()["pid"]),
            target_window_id=self._focus_free_target_window_id(),
            target_window_rect=self._focus_free_target_window_rect(),
            delay_seconds=0.08,
            deactivate_after=False,
        )
        return {"direction": direction, "label": label, "button": button, "activation": "focus_free_mouse"}

    def capture_proof(self, panel_state: dict[str, Any], path: Path) -> dict[str, Any]:
        rect = _rect_from_payload(panel_state.get("panel_rect") or panel_state.get("window_rect"))
        proof = self.capture_screenshot(rect, path)
        return {**proof, "panel_region": rect.as_payload()}

    def _accessibility_enabled(self) -> bool:
        proc = _run_osascript('Application("System Events").uiElementsEnabled()', timeout=3.0)
        return proc.returncode == 0 and proc.stdout.strip().lower() == "true"

    def _screen_recording_enabled(self) -> bool:
        with tempfile.TemporaryDirectory(prefix="cutagent-screen-preflight-") as tmpdir:
            target = Path(tmpdir) / "probe.png"
            proc = subprocess.run(["screencapture", "-x", "-t", "png", "-R", "0,0,1,1", str(target)], capture_output=True, text=True, timeout=5)
            return proc.returncode == 0 and target.is_file() and target.stat().st_size > 0


def run_power_window_track(
    conn: Any,
    *,
    clip_name: str | None,
    shape: str,
    direction: str,
    wait_seconds: float = 2.0,
    proof_dir: Path | None = None,
    driver: MacOSPowerWindowTrackGuiDriver | None = None,
) -> dict[str, Any]:
    from .db_timeline_selection import resolve_video_group

    normalized_shape = normalize_shape(shape)
    normalized_direction = normalize_direction(direction)
    normalized_wait = validate_wait_seconds(wait_seconds)
    _ensure_color_page(conn)
    target = resolve_video_group(conn, clip_name=clip_name)["video"]
    timeline = getattr(conn, "timeline", None)
    timeline_name = timeline.GetName() if timeline and hasattr(timeline, "GetName") else None
    current_database = resolve_current_disk_project_db(conn, allow_project_name_inference=True)
    project_db_path = str(current_database["project_db_path"])

    active_driver = driver or MacOSPowerWindowTrackGuiDriver()
    permissions = active_driver.preflight_permissions()
    window_rect = active_driver.find_resolve_window()
    panel_before = active_driver.ensure_tracker_panel()

    save_before = _save_project_and_wait(conn)
    before = read_power_window_grade_fingerprint(project_db_path, item_ref=target, timeline_name=timeline_name)
    transport_before = _current_timeline_timecode(timeline)
    click_result = active_driver.click_track_button(normalized_direction)
    time.sleep(normalized_wait)
    save_after = _save_project_and_wait(conn)
    after = read_power_window_grade_fingerprint(project_db_path, item_ref=target, timeline_name=timeline_name)
    transport = _restore_timeline_timecode(timeline, transport_before)

    if before.version_id != after.version_id:
        raise APICallFailed(
            "Power Window tracking changed the active grade version unexpectedly.",
            details={"before": before.as_payload(), "after": after.as_payload()},
            recoverability="manual",
        )
    changed = before.body_sha256 != after.body_sha256 or before.proto_sha256 != after.proto_sha256
    if not changed:
        raise APICallFailed(
            "DaVinci Resolve Power Window tracking did not produce a persisted grade tracking change.",
            details={"before": before.as_payload(), "after": after.as_payload(), "direction": normalized_direction},
            recoverability="manual",
        )

    panel_after = active_driver.ensure_tracker_panel()
    proof_root = _proof_root(proof_dir)
    proof = active_driver.capture_proof(panel_after, _proof_path(proof_root, normalized_direction))
    set_verification_status("verified")
    set_recoverability("manual")
    return {
        "action": "color.page.power_window_track",
        "route": ROUTE,
        "engine_scope": "workflow_owned_resolve_gui",
        "clip": getattr(target, "name", None) or clip_name,
        "shape": normalized_shape,
        "direction": normalized_direction,
        "changed": True,
        "readback": {"before": before.as_payload(), "after": after.as_payload()},
        "proof": proof,
        "preflight": {
            "permissions": permissions,
            "window_rect": window_rect.as_payload(),
            "page": "color",
            "tracker_panel_before": panel_before,
            "tracker_panel_after": panel_after,
            "current_database": current_database,
            "save_before": save_before,
            "save_after": save_after,
            "transport": transport,
        },
        "track_result": click_result,
    }


def _current_timeline_timecode(timeline: Any) -> str:
    getter = getattr(timeline, "GetCurrentTimecode", None)
    if not callable(getter):
        raise APICallFailed("Power Window tracking requires readable timeline transport state.")
    value = str(getter() or "").strip()
    if not value:
        raise APICallFailed("Power Window tracking could not read the current timeline timecode.")
    return value


def _restore_timeline_timecode(timeline: Any, timecode: str) -> dict[str, Any]:
    setter = getattr(timeline, "SetCurrentTimecode", None)
    getter = getattr(timeline, "GetCurrentTimecode", None)
    if not callable(setter) or not callable(getter):
        raise APICallFailed("Power Window tracking requires restorable timeline transport state.")
    result = setter(timecode)
    restored = str(getter() or "").strip()
    if result is False or restored != timecode:
        raise APICallFailed(
            "Power Window tracking could not restore the original timeline playhead.",
            details={"requested_timecode": timecode, "restored_timecode": restored, "api_result": result},
            recoverability="manual",
        )
    return {"before": timecode, "after": restored, "restored": True}


def read_power_window_grade_fingerprint(project_db_path: str, *, item_ref: Any, timeline_name: str | None) -> GradeFingerprint:
    from .db_timeline_rows import find_ti_item_row

    connection = sqlite3.connect(project_db_path)
    connection.row_factory = sqlite3.Row
    try:
        cursor = connection.cursor()
        row = find_ti_item_row(cursor, item=item_ref, db_type="Sm2TiVideoClip", timeline_name=timeline_name)
        clip_id = str(row["Sm2TiItem_id"])
        ver_table_id = row["pLmVerTable"]
        if not ver_table_id:
            raise APICallFailed(
                "Power Window tracking readback requires an existing Color Page grade/version table.",
                details={"clip": getattr(item_ref, "name", None), "clip_id": clip_id},
                recoverability="manual",
            )
        ver = cursor.execute(
            '''SELECT v."ListMgt::LmVersion_id", v.Body
               FROM "ListMgt::LmVersion" v
               JOIN "ListMgt::LmVersion_ListMgt::LmVersionTable" rel
                 ON rel.DbAssociate = v."ListMgt::LmVersion_id"
               WHERE rel.DbOwner = ? AND v.HasCorrection = 1
               ORDER BY v.rowid DESC LIMIT 1''',
            (ver_table_id,),
        ).fetchone()
        if not ver or not ver["Body"]:
            raise APICallFailed(
                "Power Window tracking readback requires an existing Color Page grade body.",
                details={"clip": getattr(item_ref, "name", None), "clip_id": clip_id},
                recoverability="manual",
            )
        body = bytes(ver["Body"])
        proto = decompress_version_body(body)
        return GradeFingerprint(
            clip_id=clip_id,
            clip_name=str(getattr(item_ref, "name", None) or ""),
            version_id=str(ver["ListMgt::LmVersion_id"]),
            body_size=len(body),
            body_sha256=hashlib.sha256(body).hexdigest(),
            proto_size=len(proto),
            proto_sha256=hashlib.sha256(proto).hexdigest(),
        )
    finally:
        connection.close()


def _ensure_color_page(conn: Any) -> None:
    resolve = getattr(conn, "resolve", None)
    if resolve is None:
        raise ColorPageNotReady("DaVinci Resolve connection does not expose a resolve object.", details={"required_page": "color"})
    try:
        current = resolve.GetCurrentPage()
    except Exception:
        current = None
    if current != "color":
        opened = resolve.OpenPage("color")
        if opened is False:
            raise ColorPageNotReady("DaVinci Resolve refused to switch to the Color page.", details={"current_page": current})
    try:
        final = resolve.GetCurrentPage()
    except Exception:
        final = "color"
    if final != "color":
        raise ColorPageNotReady("DaVinci Resolve is not on the Color page.", details={"current_page": final})


def _save_project_and_wait(conn: Any) -> dict[str, Any]:
    saved = project_ops.save_current_project_if_available(conn)
    time.sleep(5.0 if saved else 1.0)
    return {"saved": bool(saved), "flush_wait_seconds": 5.0 if saved else 1.0}


def _proof_root(proof_dir: Path | None) -> Path:
    root = (proof_dir or DEFAULT_PROOF_DIR).expanduser()
    if not root.is_absolute():
        root = Path.cwd() / root
    root = root.resolve(strict=False)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _proof_path(root: Path, direction: str) -> Path:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    return root / f"power-window-track-{direction}-{stamp}.png"


def _rect_from_payload(payload: Any) -> Rect:
    if not isinstance(payload, dict):
        raise ResolveWindowNotReady("Power Window tracker proof rectangle is missing.", details={"rect": payload})
    rect = Rect(int(payload["x"]), int(payload["y"]), int(payload["width"]), int(payload["height"]))
    if rect.width <= 0 or rect.height <= 0:
        raise ResolveWindowNotReady("Power Window tracker proof rectangle has invalid geometry.", details={"rect": rect.as_payload()})
    return rect


def _run_osascript(script: str, *, timeout: float = 5.0) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(["osascript", "-l", "JavaScript", "-e", script], capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        return subprocess.CompletedProcess(["osascript"], 124, stdout=exc.stdout or "", stderr=exc.stderr or str(exc))


def _run_json_jxa(script: str, message: str) -> dict[str, Any]:
    proc = _run_osascript(script, timeout=30.0)
    if proc.returncode != 0:
        raise ResolveWindowNotReady(message, details={"stdout": proc.stdout[-1000:], "stderr": proc.stderr[-1000:]})
    try:
        return json.loads(proc.stdout.strip())
    except json.JSONDecodeError as exc:
        raise ResolveWindowNotReady(message, details={"stdout": proc.stdout[-1000:]}) from exc


_WINDOW_JXA = r"""
const se = Application("System Events");
const processNames = ["DaVinci Resolve", "Resolve"];
let proc = null;
let matchedName = null;
for (const name of processNames) {
  const matches = se.processes.whose({ name })();
  if (matches.length > 0) { proc = matches[0]; matchedName = name; break; }
}
if (!proc || proc.windows().length === 0) {
  JSON.stringify({ ok: false, reason: "process_or_window_not_found" });
} else {
  let best = null, bestArea = 0;
  for (const win of proc.windows()) {
    try {
      const size = win.size();
      const area = Number(size[0] || 0) * Number(size[1] || 0);
      if (area > bestArea) { best = win; bestArea = area; }
    } catch (_) {}
  }
  if (!best) {
    JSON.stringify({ ok: false, reason: "window_geometry_not_found" });
  } else {
    JSON.stringify({ ok: true, process_name: matchedName, name: best.name(), position: best.position(), size: best.size() });
  }
}
"""


_TRACKER_PANEL_JXA = r"""
const se = Application("System Events");
const targetWindow = __TARGET_WINDOW_JSON__;
const proc = se.applicationProcesses.whose({ unixId: { _equals: targetWindow.pid } })[0];
let procExists = false;
try { procExists = proc.exists(); } catch (_) {}
function pack(e) {
  let props = {};
  try { props = e.properties(); } catch (_) {}
  const pos = Array.isArray(props.position) ? props.position : [0, 0];
  const size = Array.isArray(props.size) ? props.size : [0, 0];
  const name = String(props.name || "");
  const desc = String(props.description || "");
  const role = String(props.role || "");
  const value = String(props.value || "");
  return { x: Number(pos[0] || 0), y: Number(pos[1] || 0), width: Number(size[0] || 0), height: Number(size[1] || 0), name, desc, role, value };
}
function textOf(e) {
  const p = pack(e);
  return `${p.name} ${p.desc} ${p.value}`.toLowerCase();
}
function unionRect(items) {
  let left = 999999, top = 999999, right = 0, bottom = 0;
  for (const item of items) {
    left = Math.min(left, item.x);
    top = Math.min(top, item.y);
    right = Math.max(right, item.x + item.width);
    bottom = Math.max(bottom, item.y + item.height);
  }
  return {
    x: Math.max(0, left - 24),
    y: Math.max(0, top - 30),
    width: Math.max(1, right - left + 48),
    height: Math.max(1, bottom - top + 90),
    name: "Tracker - Window proof region",
    desc: "",
    role: "AXGroup",
    value: ""
  };
}
if (!procExists || proc.windows.length === 0) {
  JSON.stringify({ ok: false, reason: "process_or_window_not_found" });
} else {
  const roots = [];
  for (let i = 0; i < proc.windows.length; i++) {
    const win = proc.windows[i];
    try {
      const position = win.position(); const size = win.size();
      if (String(win.name() || "") === targetWindow.name &&
        Math.abs(Number(position[0]) - targetWindow.x) <= 3 && Math.abs(Number(position[1]) - targetWindow.y) <= 3 &&
        Math.abs(Number(size[0]) - targetWindow.width) <= 3 && Math.abs(Number(size[1]) - targetWindow.height) <= 3) roots.push(win);
    } catch (_) {}
  }
  const win = roots.length === 1 ? roots[0] : null;
  if (!win) {
    JSON.stringify({ ok: false, reason: "exact_target_window_not_unique", matched_window_count: roots.length });
  } else {
  const queue = [win];
  let scanned = 0;
  const buttons = [];
  const labels = ["track one frame reverse", "track reverse", "stop tracking", "track forward and reverse", "track forward", "track one frame forward"];
  while (queue.length && scanned < 700 && buttons.length < 6) {
    const item = queue.shift();
    scanned += 1;
    const p = pack(item);
    const text = `${p.name} ${p.desc} ${p.value}`.toLowerCase();
    if (p.role === "AXButton" && labels.some(label => text.includes(label))) buttons.push(p);
    try {
      const kids = item.uiElements;
      for (let i = 0; i < kids.length; i++) queue.push(kids[i]);
    } catch (_) {}
  }
  if (buttons.length < 5) {
    JSON.stringify({ ok: false, reason: "tracker_window_buttons_not_found", scanned, buttons });
  } else {
    const usefulButtons = buttons.filter(b => (b.name + " " + b.desc + " " + b.value).toLowerCase().includes("track"));
    JSON.stringify({ ok: true, panel: "Tracker - Window", panel_rect: unionRect(usefulButtons), buttons: usefulButtons, scanned });
  }
  }
}
"""


_CLICK_BUTTON_JXA = r"""
const needle = __LABEL_JSON__;
const se = Application("System Events");
const targetWindow = __TARGET_WINDOW_JSON__;
const proc = se.applicationProcesses.whose({ unixId: { _equals: targetWindow.pid } })[0];
let procExists = false;
try { procExists = proc.exists(); } catch (_) {}
function pack(e) {
  let props = {};
  try { props = e.properties(); } catch (_) {}
  const pos = Array.isArray(props.position) ? props.position : [0, 0];
  const size = Array.isArray(props.size) ? props.size : [0, 0];
  const name = String(props.name || "");
  const desc = String(props.description || "");
  const role = String(props.role || "");
  const value = String(props.value || "");
  return { x: Number(pos[0] || 0), y: Number(pos[1] || 0), width: Number(size[0] || 0), height: Number(size[1] || 0), name, desc, role, value };
}
if (!procExists || proc.windows.length === 0) {
  JSON.stringify({ ok: false, reason: "process_or_window_not_found" });
} else {
  const roots = [];
  for (let i = 0; i < proc.windows.length; i++) {
    const win = proc.windows[i];
    try {
      const position = win.position(); const size = win.size();
      if (String(win.name() || "") === targetWindow.name &&
        Math.abs(Number(position[0]) - targetWindow.x) <= 3 && Math.abs(Number(position[1]) - targetWindow.y) <= 3 &&
        Math.abs(Number(size[0]) - targetWindow.width) <= 3 && Math.abs(Number(size[1]) - targetWindow.height) <= 3) roots.push(win);
    } catch (_) {}
  }
  const best = roots.length === 1 ? roots[0] : null;
  const queue = best ? [best] : [];
  let scanned = 0, found = false, button = null;
  while (queue.length && scanned < 700 && !found) {
    const item = queue.shift();
    scanned += 1;
    const p = pack(item);
    const labels = [p.name, p.desc, p.value].map(value => value.trim().toLowerCase()).filter(Boolean);
    if (p.role === "AXButton" && labels.some(value => value === needle)) {
      found = true; button = p; break;
    }
    try {
      const kids = item.uiElements;
      for (let i = 0; i < kids.length; i++) queue.push(kids[i]);
    } catch (_) {}
  }
  JSON.stringify({ ok: found, button, scanned, searched: needle });
}
"""
