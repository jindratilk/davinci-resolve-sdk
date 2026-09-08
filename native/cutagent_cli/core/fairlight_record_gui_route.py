"""Workflow-owned GUI-assisted Fairlight transport recording route.

This module only drives the native DaVinci Resolve Fairlight transport
Record and Stop controls. It is intentionally not a general GUI automation
surface and does not claim per-track record-arm or input-patch control.
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

from ..errors import GuiPermissionMissing, ReadinessFailed, ResolveWindowNotFound, ResolveWindowNotReady
from ..output import set_recoverability, set_verification_status

ROUTE = "fairlight.record_transport_gui"
ENGINE = "resolve_gui"
DEFAULT_PROOF_DIR = Path("artifacts") / "fairlight-record-gui"
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
class RecordTransportState:
    record_enabled: bool
    record_raw: str
    stop_enabled: bool
    stop_raw: str
    record_rect: Rect
    stop_rect: Rect
    window_rect: Rect

    def as_payload(self) -> dict[str, Any]:
        return {
            "record_enabled": self.record_enabled,
            "record_raw": self.record_raw,
            "stop_enabled": self.stop_enabled,
            "stop_raw": self.stop_raw,
            "record_rect": self.record_rect.as_payload(),
            "stop_rect": self.stop_rect.as_payload(),
            "window_rect": self.window_rect.as_payload(),
        }


class MacOSFairlightRecordTransportGuiDriver:
    """Internal macOS driver scoped to Fairlight transport Record/Stop."""

    process_names = PROCESS_NAMES

    def preflight_permissions(self) -> dict[str, Any]:
        if platform.system() != "Darwin":
            raise GuiPermissionMissing(
                "Fairlight record transport GUI-assisted route requires macOS.",
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

    def read_state(self) -> RecordTransportState:
        payload = self._read_transport_payload()
        return _payload_to_state(payload)

    def start(self) -> dict[str, Any]:
        before = self.read_state()
        if before.record_enabled:
            return {"changed": False, "before": before, "after": before}
        _post_mouse_click(before.record_rect.center)
        time.sleep(0.3)
        after = self.read_state()
        if not after.record_enabled:
            raise ReadinessFailed(
                "DaVinci Resolve Fairlight transport did not enter recording state.",
                details={
                    "before": before.as_payload(),
                    "after": after.as_payload(),
                    "likely_reason": "No Fairlight audio track is armed/patched for recording, or DaVinci Resolve rejected transport recording.",
                },
            )
        return {"changed": True, "before": before, "after": after}

    def stop(self) -> dict[str, Any]:
        before = self.read_state()
        if not before.record_enabled:
            return {"changed": False, "before": before, "after": before}
        _post_mouse_click(before.stop_rect.center)
        time.sleep(0.3)
        after = self.read_state()
        if after.record_enabled:
            raise ReadinessFailed(
                "DaVinci Resolve Fairlight transport did not leave recording state.",
                details={"before": before.as_payload(), "after": after.as_payload()},
            )
        return {"changed": True, "before": before, "after": after}

    def capture_proof(self, state: RecordTransportState, path: Path) -> dict[str, Any]:
        path.parent.mkdir(parents=True, exist_ok=True)
        rect = _transport_proof_rect(state.window_rect, state.record_rect)
        region = f"{rect.x},{rect.y},{rect.width},{rect.height}"
        proc = subprocess.run(
            ["screencapture", "-x", "-t", "png", "-R", region, str(path)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if proc.returncode != 0 or not path.is_file():
            raise ReadinessFailed(
                "Failed to capture Fairlight record transport proof screenshot.",
                details={"screenshot_path": str(path), "region": rect.as_payload(), "stderr": proc.stderr[-500:]},
            )
        return {"screenshot_path": str(path), "bytes": path.stat().st_size, "region": rect.as_payload()}

    def _read_transport_payload(self) -> dict[str, Any]:
        proc = _run_osascript(_TRANSPORT_CONTROL_JXA, language="JavaScript", timeout=20.0)
        if proc.returncode != 0:
            raise ResolveWindowNotReady(
                "Could not inspect DaVinci Resolve Fairlight record transport through macOS Accessibility.",
                details={"stderr": proc.stderr[-1000:], "stdout": proc.stdout[-500:]},
            )
        try:
            payload = json.loads(proc.stdout.strip())
        except json.JSONDecodeError as exc:
            raise ResolveWindowNotReady(
                "DaVinci Resolve Fairlight record transport probe returned invalid data.",
                details={"stdout": proc.stdout[-1000:]},
            ) from exc
        if not payload.get("ok"):
            error_cls = ResolveWindowNotFound if payload.get("reason") in {"process_not_found", "window_not_found"} else ReadinessFailed
            raise error_cls(
                "DaVinci Resolve Fairlight record transport controls are not available.",
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


def run_record_start(
    conn: Any,
    *,
    track: int | None = None,
    proof_dir: Path | None = None,
    driver: MacOSFairlightRecordTransportGuiDriver | None = None,
) -> dict[str, Any]:
    active_driver = driver or MacOSFairlightRecordTransportGuiDriver()
    permission_state = active_driver.preflight_permissions()
    page_state = _ensure_fairlight_page(conn)
    result = active_driver.start()
    after = result["after"]
    proof_root = _proof_root(proof_dir)
    proof = active_driver.capture_proof(after, _proof_path(proof_root, "start"))
    set_verification_status("verified")
    set_recoverability("manual")
    return {
        "action": "fairlight.record.start",
        "route": ROUTE,
        "requested_track": int(track) if track else None,
        "changed": bool(result["changed"]),
        "record_enabled": after.record_enabled,
        "record_raw": after.record_raw,
        "stop_enabled": after.stop_enabled,
        "stop_raw": after.stop_raw,
        "before": result["before"].as_payload(),
        "after": after.as_payload(),
        "proof": proof,
        "preflight": {"permissions": permission_state, "page": page_state},
    }


def run_record_stop(
    conn: Any,
    *,
    proof_dir: Path | None = None,
    driver: MacOSFairlightRecordTransportGuiDriver | None = None,
) -> dict[str, Any]:
    active_driver = driver or MacOSFairlightRecordTransportGuiDriver()
    permission_state = active_driver.preflight_permissions()
    page_state = _ensure_fairlight_page(conn)
    result = active_driver.stop()
    after = result["after"]
    proof_root = _proof_root(proof_dir)
    proof = active_driver.capture_proof(after, _proof_path(proof_root, "stop"))
    set_verification_status("verified")
    set_recoverability("manual")
    return {
        "action": "fairlight.record.stop",
        "route": ROUTE,
        "changed": bool(result["changed"]),
        "record_enabled": after.record_enabled,
        "record_raw": after.record_raw,
        "stop_enabled": after.stop_enabled,
        "stop_raw": after.stop_raw,
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


def _payload_to_state(payload: dict[str, Any]) -> RecordTransportState:
    try:
        record = payload["record"]
        stop = payload["stop"]
        window = payload["window"]
        record_raw = _raw_control_value(record)
        stop_raw = _raw_control_value(stop)
        return RecordTransportState(
            record_enabled=record_raw == "1",
            record_raw=record_raw,
            stop_enabled=stop_raw == "1",
            stop_raw=stop_raw,
            record_rect=_rect_from_payload(record),
            stop_rect=_rect_from_payload(stop),
            window_rect=_rect_from_payload(window),
        )
    except Exception as exc:
        raise ResolveWindowNotReady(
            "DaVinci Resolve Fairlight record transport probe did not include usable controls.",
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


def _raw_control_value(payload: dict[str, Any]) -> str:
    value = payload.get("value")
    return "" if value is None else str(value)


def _transport_proof_rect(window_rect: Rect, record_rect: Rect) -> Rect:
    left = max(window_rect.x, record_rect.x - 170)
    top = max(window_rect.y, record_rect.y - 60)
    right = min(window_rect.x + window_rect.width, record_rect.x + 150)
    bottom = min(window_rect.y + window_rect.height, record_rect.y + 65)
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
    return root / f"fairlight-record-{stem}-{stamp}.png"


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
                "macOS failed to create Fairlight record transport mouse event.",
                details={"event_type": event_type, "point": point},
            )
        try:
            app_services.CGEventPost(0, event)
        finally:
            app_services.CFRelease(event)
        time.sleep(delay_seconds)


_TRANSPORT_CONTROL_JXA = r"""
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
function snapshot(item) {
  let role = "";
  let desc = "";
  let name = "";
  let value = "";
  let pos = [];
  let size = [];
  try { role = String(item.role() || ""); } catch (e) {}
  try { desc = String(item.description() || ""); } catch (e) {}
  try { name = String(item.name() || ""); } catch (e) {}
  try { value = String(item.value()); } catch (e) {}
  try { pos = item.position(); } catch (e) {}
  try { size = item.size(); } catch (e) {}
  return { item, role, desc, name, value, pos, size };
}
function publicControl(control) {
  return {
    role: control.role,
    desc: control.desc,
    name: control.name,
    value: control.value,
    pos: control.pos,
    size: control.size,
  };
}
function collectLimited(root) {
  const elements = [];
  const queue = [root];
  let scanned = 0;
  while (queue.length && scanned < 200) {
    const item = queue.shift();
    scanned += 1;
    elements.push(snapshot(item));
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
    let content = best;
    let directScanned = 0;
    try {
      const children = best.uiElements();
      let bestContentArea = 0;
      for (let i = 0; i < children.length; i++) {
        directScanned += 1;
        const candidate = snapshot(children[i]);
        const area = Number(candidate.size[0] || 0) * Number(candidate.size[1] || 0);
        if (candidate.role === "AXGroup" && area > bestContentArea) {
          content = children[i];
          bestContentArea = area;
        }
      }
    } catch (e) {}
    let elements = [];
    try {
      const children = content.uiElements();
      for (let i = 0; i < children.length; i++) {
        directScanned += 1;
        elements.push(snapshot(children[i]));
      }
    } catch (e) {}
    let collected = { elements, scanned: directScanned };
    if (elements.filter(e => e.role === "AXCheckBox" && e.desc === "Record").length === 0) {
      collected = collectLimited(content);
      elements = collected.elements;
    }
    const recordCandidates = elements.filter(e => e.role === "AXCheckBox" && e.desc === "Record");
    const stopCandidates = elements.filter(e => e.role === "AXCheckBox" && e.desc === "Stop");
    let selected = null;
    for (const record of recordCandidates) {
      const rx = Number(record.pos[0] || 0);
      const ry = Number(record.pos[1] || 0);
      const stops = stopCandidates.filter(e => {
        const x = Number(e.pos[0] || 0);
        const y = Number(e.pos[1] || 0);
        return x < rx && Math.abs(y - ry) <= 8 && rx - x < 80;
      });
      if (stops.length > 0) {
        stops.sort((a, b) => Number(b.pos[0] || 0) - Number(a.pos[0] || 0));
        selected = { record, stop: stops[0] };
        break;
      }
    }
    if (!selected) {
      JSON.stringify({
        ok: false,
        reason: "fairlight_record_transport_controls_not_found",
        scanned: collected.scanned,
        record_candidate_count: recordCandidates.length,
        stop_candidate_count: stopCandidates.length,
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
        scanned: collected.scanned,
        window: { position, size },
        record: publicControl(selected.record),
        stop: publicControl(selected.stop),
      });
    }
  }
}
"""
