"""Workflow-owned GUI-assisted Fairlight Control Room monitor route.

This module is intentionally narrow. It only drives the DaVinci Resolve
Fairlight Control Room monitor level slider and mute checkbox exposed in the
native UI; it does not expose generic screen automation primitives.
"""

from __future__ import annotations

import ctypes
import json
import platform
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

ROUTE = "fairlight.monitor_gui"
ENGINE = "resolve_gui"
DEFAULT_PROOF_DIR = Path("artifacts") / "fairlight-monitor-gui"
PROCESS_NAMES = ("DaVinci Resolve", "Resolve")
LEVEL_MIN_DB = -10.0
LEVEL_MAX_DB = 0.0
LEVEL_TOLERANCE_DB = 0.05


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
class MonitorState:
    level_db: float
    level_raw: str
    mute_enabled: bool
    mute_raw: str
    slider_rect: Rect
    mute_rect: Rect
    window_rect: Rect

    def as_payload(self) -> dict[str, Any]:
        return {
            "level_db": self.level_db,
            "level_raw": self.level_raw,
            "mute_enabled": self.mute_enabled,
            "mute_raw": self.mute_raw,
            "slider_rect": self.slider_rect.as_payload(),
            "mute_rect": self.mute_rect.as_payload(),
            "window_rect": self.window_rect.as_payload(),
        }


def validate_monitor_level(value: float) -> float:
    try:
        level = float(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(
            "Fairlight monitor level must be numeric.",
            details={"level_db": value},
            recoverability="not_applicable",
        ) from exc
    if not (LEVEL_MIN_DB <= level <= LEVEL_MAX_DB):
        raise ValidationError(
            "Fairlight Control Room monitor level must be between -10.0 dB and 0.0 dB.",
            details={"level_db": value, "min_db": LEVEL_MIN_DB, "max_db": LEVEL_MAX_DB},
            recoverability="not_applicable",
        )
    return round(level, 2)


class MacOSFairlightMonitorGuiDriver:
    """Internal macOS driver scoped to Fairlight Control Room monitoring."""

    process_names = PROCESS_NAMES

    @property
    def process_name(self) -> str:
        return self.process_names[0]

    def preflight_permissions(self) -> dict[str, Any]:
        if platform.system() != "Darwin":
            raise GuiPermissionMissing(
                "Fairlight monitor GUI-assisted route requires macOS.",
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

    def read_state(self) -> MonitorState:
        payload = self._read_monitor_payload()
        return _payload_to_state(payload)

    def set_level(self, target_db: float) -> dict[str, Any]:
        target = validate_monitor_level(target_db)
        before = self.read_state()
        if abs(before.level_db - target) <= LEVEL_TOLERANCE_DB:
            return {"changed": False, "before": before, "after": before, "attempts": []}

        target_raw = str(int(round(target * 100)))
        set_result = self._set_slider_value(target_raw)
        time.sleep(0.15)
        after = self.read_state()
        attempts = [
            {
                "attempt": 1,
                "method": "AXSlider.value",
                "from_level_db": before.level_db,
                "requested_raw": target_raw,
                "set_result": set_result,
                "to_level_db": after.level_db,
            }
        ]
        if abs(after.level_db - target) <= LEVEL_TOLERANCE_DB:
            return {"changed": True, "before": before, "after": after, "attempts": attempts}

        raise ReadinessFailed(
            "Fairlight Control Room monitor level did not reach requested value.",
            details={
                "requested_level_db": target,
                "before": before.as_payload(),
                "after": after.as_payload(),
                "attempts": attempts,
                "tolerance_db": LEVEL_TOLERANCE_DB,
            },
        )

    def set_mute(self, enabled: bool) -> dict[str, Any]:
        target = bool(enabled)
        before = self.read_state()
        if before.mute_enabled == target:
            return {"changed": False, "before": before, "after": before}
        _post_mouse_click(before.mute_rect.center)
        time.sleep(0.15)
        after = self.read_state()
        if after.mute_enabled != target:
            raise ReadinessFailed(
                "Fairlight Control Room mute state did not reach requested value.",
                details={
                    "requested_mute_enabled": target,
                    "before": before.as_payload(),
                    "after": after.as_payload(),
                },
            )
        return {"changed": True, "before": before, "after": after}

    def capture_proof(self, state: MonitorState, path: Path) -> dict[str, Any]:
        path.parent.mkdir(parents=True, exist_ok=True)
        rect = _control_room_proof_rect(state.window_rect, state.slider_rect)
        region = f"{rect.x},{rect.y},{rect.width},{rect.height}"
        proc = subprocess.run(
            ["screencapture", "-x", "-t", "png", "-R", region, str(path)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if proc.returncode != 0 or not path.is_file():
            raise ReadinessFailed(
                "Failed to capture Fairlight monitor proof screenshot.",
                details={"screenshot_path": str(path), "region": rect.as_payload(), "stderr": proc.stderr[-500:]},
            )
        return {"screenshot_path": str(path), "bytes": path.stat().st_size, "region": rect.as_payload()}

    def _read_monitor_payload(self) -> dict[str, Any]:
        proc = _run_osascript(_MONITOR_CONTROL_JXA, language="JavaScript", timeout=20.0)
        if proc.returncode != 0:
            raise ResolveWindowNotReady(
                "Could not inspect DaVinci Resolve Fairlight monitor controls through macOS Accessibility.",
                details={"stderr": proc.stderr[-1000:], "stdout": proc.stdout[-500:]},
            )
        try:
            payload = json.loads(proc.stdout.strip())
        except json.JSONDecodeError as exc:
            raise ResolveWindowNotReady(
                "DaVinci Resolve Fairlight monitor probe returned invalid data.",
                details={"stdout": proc.stdout[-1000:]},
            ) from exc
        if not payload.get("ok"):
            error_cls = ResolveWindowNotFound if payload.get("reason") in {"process_not_found", "window_not_found"} else ReadinessFailed
            raise error_cls(
                "DaVinci Resolve Fairlight Control Room monitor controls are not available.",
                details=payload,
            )
        return payload

    def _set_slider_value(self, raw_value: str) -> dict[str, Any]:
        script = _MONITOR_SET_LEVEL_JXA.replace("__TARGET_VALUE__", json.dumps(str(raw_value)))
        proc = _run_osascript(script, language="JavaScript", timeout=20.0)
        if proc.returncode != 0:
            raise ResolveWindowNotReady(
                "Could not set DaVinci Resolve Fairlight monitor level through macOS Accessibility.",
                details={"stderr": proc.stderr[-1000:], "stdout": proc.stdout[-500:]},
            )
        try:
            payload = json.loads(proc.stdout.strip())
        except json.JSONDecodeError as exc:
            raise ResolveWindowNotReady(
                "DaVinci Resolve Fairlight monitor level write returned invalid data.",
                details={"stdout": proc.stdout[-1000:]},
            ) from exc
        if not payload.get("ok"):
            raise ReadinessFailed(
                "DaVinci Resolve Fairlight monitor level slider was not writable.",
                details=payload,
            )
        return payload

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


def run_monitor_level(
    conn: Any,
    *,
    level_db: float | None,
    proof_dir: Path | None = None,
    driver: MacOSFairlightMonitorGuiDriver | None = None,
) -> dict[str, Any]:
    active_driver = driver or MacOSFairlightMonitorGuiDriver()
    permission_state = active_driver.preflight_permissions()
    page_state = _ensure_fairlight_page(conn)
    if level_db is None:
        before = active_driver.read_state()
        after = before
        changed = False
        attempts: list[dict[str, Any]] = []
        requested_level = None
    else:
        requested_level = validate_monitor_level(level_db)
        result = active_driver.set_level(requested_level)
        changed = bool(result["changed"])
        before = result["before"]
        after = result["after"]
        attempts = list(result.get("attempts") or [])

    proof_root = _proof_root(proof_dir)
    proof_path = _proof_path(proof_root, "level")
    proof = active_driver.capture_proof(after, proof_path)
    set_verification_status("verified")
    set_recoverability("manual")
    return {
        "action": "fairlight.monitor.level",
        "route": ROUTE,
        "requested_level_db": requested_level,
        "level_db": after.level_db,
        "level_raw": after.level_raw,
        "changed": changed,
        "before": before.as_payload(),
        "after": after.as_payload(),
        "attempts": attempts,
        "proof": proof,
        "preflight": {"permissions": permission_state, "page": page_state},
    }


def run_monitor_mute(
    conn: Any,
    *,
    enabled: bool,
    proof_dir: Path | None = None,
    driver: MacOSFairlightMonitorGuiDriver | None = None,
) -> dict[str, Any]:
    active_driver = driver or MacOSFairlightMonitorGuiDriver()
    permission_state = active_driver.preflight_permissions()
    page_state = _ensure_fairlight_page(conn)
    result = active_driver.set_mute(bool(enabled))
    after = result["after"]
    proof_root = _proof_root(proof_dir)
    proof_path = _proof_path(proof_root, "mute")
    proof = active_driver.capture_proof(after, proof_path)
    set_verification_status("verified")
    set_recoverability("manual")
    return {
        "action": "fairlight.monitor.mute",
        "route": ROUTE,
        "requested_mute_enabled": bool(enabled),
        "mute_enabled": after.mute_enabled,
        "mute_raw": after.mute_raw,
        "changed": bool(result["changed"]),
        "before": result["before"].as_payload(),
        "after": after.as_payload(),
        "proof": proof,
        "preflight": {"permissions": permission_state, "page": page_state},
    }


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


def _payload_to_state(payload: dict[str, Any]) -> MonitorState:
    try:
        slider = payload["slider"]
        mute = payload["mute"]
        window = payload["window"]
        level_raw = str(slider.get("value") or "0")
        level_db = round(float(level_raw) / 100.0, 2)
        mute_raw = str(mute.get("value") or "")
        return MonitorState(
            level_db=level_db,
            level_raw=level_raw,
            mute_enabled=mute_raw == "1",
            mute_raw=mute_raw,
            slider_rect=_rect_from_payload(slider),
            mute_rect=_rect_from_payload(mute),
            window_rect=_rect_from_payload(window),
        )
    except Exception as exc:
        raise ResolveWindowNotReady(
            "DaVinci Resolve Fairlight monitor probe did not include usable controls.",
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


def _control_room_proof_rect(window_rect: Rect, slider_rect: Rect) -> Rect:
    left = max(window_rect.x, slider_rect.x - 170)
    top = max(window_rect.y, slider_rect.y - 70)
    right = min(window_rect.x + window_rect.width, slider_rect.x + 190)
    bottom = min(window_rect.y + window_rect.height, slider_rect.y + 70)
    return Rect(x=left, y=top, width=max(1, right - left), height=max(1, bottom - top))


def _proof_root(proof_dir: Path | None) -> Path:
    root = (proof_dir or DEFAULT_PROOF_DIR).expanduser()
    if not root.is_absolute():
        root = Path.cwd() / root
    root = root.resolve(strict=False)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _proof_path(root: Path, stem: str) -> Path:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    return root / f"fairlight-monitor-{stem}-{stamp}.png"


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
    _post_mouse_event_sequence([(1, point), (2, point)], delay_seconds=delay_seconds)


def _post_mouse_drag(points: list[tuple[int, int]], *, delay_seconds: float = 0.025) -> None:
    if not points:
        raise ReadinessFailed("Cannot drag an empty Fairlight monitor slider path.", details={"points": points})
    events = [(1, points[0])]
    events.extend((6, point) for point in points[1:])
    events.append((2, points[-1]))
    _post_mouse_event_sequence(events, delay_seconds=delay_seconds)


def _post_mouse_event_sequence(events: list[tuple[int, tuple[int, int]]], *, delay_seconds: float) -> None:
    app_services = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices")

    class CGPoint(ctypes.Structure):
        _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]

    app_services.CGEventCreateMouseEvent.restype = ctypes.c_void_p
    app_services.CGEventCreateMouseEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint32, CGPoint, ctypes.c_uint32]
    app_services.CGEventPost.argtypes = [ctypes.c_uint32, ctypes.c_void_p]
    app_services.CFRelease.argtypes = [ctypes.c_void_p]

    for event_type, point in events:
        event = app_services.CGEventCreateMouseEvent(None, event_type, CGPoint(float(point[0]), float(point[1])), 0)
        if not event:
            raise ReadinessFailed(
                "macOS failed to create Fairlight monitor mouse event.",
                details={"event_type": event_type, "point": point},
            )
        try:
            app_services.CGEventPost(0, event)
        finally:
            app_services.CFRelease(event)
        time.sleep(delay_seconds)


_MONITOR_CONTROL_JXA = r"""
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
if (!proc) {
  JSON.stringify({ ok: false, reason: "process_not_found", process_names: processNames });
} else {
  const windows = proc.windows();
  if (windows.length === 0) {
    JSON.stringify({ ok: false, reason: "window_not_found", process_name: processName });
  } else {
    let best = null;
    let bestArea = 0;
    for (let i = 0; i < windows.length; i++) {
      try {
        const size = windows[i].size();
        const area = Number(size[0] || 0) * Number(size[1] || 0);
        if (area > bestArea) {
          best = windows[i];
          bestArea = area;
        }
      } catch (e) {}
    }
    const elements = [];
    const queue = [best];
    let scanned = 0;
    while (queue.length && scanned < 2600) {
      const item = queue.shift();
      scanned += 1;
      let role = "";
      let desc = "";
      let name = "";
      let value = "";
      let pos = [];
      let size = [];
      try { role = String(item.role() || ""); } catch (e) {}
      try { desc = String(item.description() || ""); } catch (e) {}
      try { name = String(item.name() || ""); } catch (e) {}
      try { value = String(item.value() || ""); } catch (e) {}
      try { pos = item.position(); } catch (e) {}
      try { size = item.size(); } catch (e) {}
      elements.push({ role, desc, name, value, pos, size });
      try {
        const children = item.uiElements();
        for (let i = 0; i < children.length; i++) queue.push(children[i]);
      } catch (e) {}
    }
    const muteCandidates = elements.filter(e => e.role === "AXCheckBox" && e.desc === "Mute");
    let selected = null;
    for (const mute of muteCandidates) {
      const mx = Number(mute.pos[0] || 0);
      const my = Number(mute.pos[1] || 0);
      const sliders = elements.filter(e => {
        const x = Number(e.pos[0] || 0);
        const y = Number(e.pos[1] || 0);
        return e.role === "AXSlider" && x > mx && x < mx + 180 && Math.abs(y - my) <= 12;
      });
      if (sliders.length > 0) {
        sliders.sort((a, b) => Number(a.pos[0] || 0) - Number(b.pos[0] || 0));
        selected = { mute, slider: sliders[0] };
        break;
      }
    }
    if (!selected) {
      JSON.stringify({
        ok: false,
        reason: "fairlight_monitor_controls_not_found",
        scanned,
        mute_candidate_count: muteCandidates.length,
        process_name: processName,
      });
    } else {
      let position = [];
      let size = [];
      try { position = best.position(); } catch (e) {}
      try { size = best.size(); } catch (e) {}
      JSON.stringify({
        ok: true,
        process_name: processName,
        scanned,
        window: { position, size },
        mute: selected.mute,
        slider: selected.slider,
      });
    }
  }
}
"""

_MONITOR_SET_LEVEL_JXA = r"""
const targetValue = __TARGET_VALUE__;
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
function collect(root) {
  const elements = [];
  const queue = [root];
  let scanned = 0;
  while (queue.length && scanned < 2600) {
    const item = queue.shift();
    scanned += 1;
    let role = "";
    let desc = "";
    let name = "";
    let value = "";
    let pos = [];
    let size = [];
    try { role = String(item.role() || ""); } catch (e) {}
    try { desc = String(item.description() || ""); } catch (e) {}
    try { name = String(item.name() || ""); } catch (e) {}
    try { value = String(item.value() || ""); } catch (e) {}
    try { pos = item.position(); } catch (e) {}
    try { size = item.size(); } catch (e) {}
    elements.push({ item, role, desc, name, value, pos, size });
    try {
      const children = item.uiElements();
      for (let i = 0; i < children.length; i++) queue.push(children[i]);
    } catch (e) {}
  }
  return { elements, scanned };
}
if (!proc) {
  JSON.stringify({ ok: false, reason: "process_not_found", process_names: processNames });
} else {
  const windows = proc.windows();
  if (windows.length === 0) {
    JSON.stringify({ ok: false, reason: "window_not_found", process_name: processName });
  } else {
    let best = null;
    let bestArea = 0;
    for (let i = 0; i < windows.length; i++) {
      try {
        const size = windows[i].size();
        const area = Number(size[0] || 0) * Number(size[1] || 0);
        if (area > bestArea) {
          best = windows[i];
          bestArea = area;
        }
      } catch (e) {}
    }
    const collected = collect(best);
    const elements = collected.elements;
    const muteCandidates = elements.filter(e => e.role === "AXCheckBox" && e.desc === "Mute");
    let selected = null;
    for (const mute of muteCandidates) {
      const mx = Number(mute.pos[0] || 0);
      const my = Number(mute.pos[1] || 0);
      const sliders = elements.filter(e => {
        const x = Number(e.pos[0] || 0);
        const y = Number(e.pos[1] || 0);
        return e.role === "AXSlider" && x > mx && x < mx + 180 && Math.abs(y - my) <= 12;
      });
      if (sliders.length > 0) {
        sliders.sort((a, b) => Number(a.pos[0] || 0) - Number(b.pos[0] || 0));
        selected = sliders[0];
        break;
      }
    }
    if (!selected) {
      JSON.stringify({
        ok: false,
        reason: "fairlight_monitor_slider_not_found",
        scanned: collected.scanned,
        mute_candidate_count: muteCandidates.length,
        process_name: processName,
      });
    } else {
      let before = "";
      let after = "";
      let setError = "";
      try { before = String(selected.item.value() || ""); } catch (e) {}
      try {
        selected.item.value = targetValue;
      } catch (e) {
        setError = String(e);
      }
      if (setError) {
        JSON.stringify({
          ok: false,
          reason: "fairlight_monitor_slider_set_failed",
          error: setError,
          before,
          requested_raw: targetValue,
        });
      } else {
        delay(0.1);
        try { after = String(selected.item.value() || ""); } catch (e) {}
        JSON.stringify({
          ok: true,
          process_name: processName,
          before,
          after,
          requested_raw: targetValue,
        });
      }
    }
  }
}
"""
