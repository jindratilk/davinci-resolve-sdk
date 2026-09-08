"""Workflow-owned GUI-assisted Color Page Gallery still comparison route."""

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

from ..errors import ColorPageNotReady, GuiPermissionMissing, ReadinessFailed, ResolveWindowNotReady, ValidationError
from ..output import set_recoverability, set_verification_status
from . import gallery_ops

ROUTE = "color.page_still_match_gui"
ENGINE = "resolve_gui"
DEFAULT_PROOF_DIR = Path("artifacts") / "still-match-gui"
MODES = {"image-wipe", "split-screen", "side-by-side"}


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


def normalize_mode(value: str | None) -> str:
    token = str(value or "side-by-side").strip().lower().replace("_", "-")
    aliases = {"split": "split-screen", "side-by-side": "split-screen", "wipe": "image-wipe", "image": "image-wipe"}
    token = aliases.get(token, token)
    if token not in {"image-wipe", "split-screen"}:
        raise ValidationError(
            "Color Page still-match mode must be one of image-wipe, split-screen, or side-by-side.",
            details={"mode": value, "allowed": ["image-wipe", "split-screen", "side-by-side"]},
            recoverability="not_applicable",
        )
    return token


class MacOSStillMatchGuiDriver:
    def preflight_permissions(self) -> dict[str, Any]:
        if platform.system() != "Darwin":
            raise GuiPermissionMissing("Still Match GUI-assisted route requires macOS.", details={"platform": platform.system()})
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

    def read_controls(self) -> dict[str, Any]:
        payload = _run_json_jxa(_READ_CONTROLS_JXA, "Could not inspect DaVinci Resolve Gallery still-match controls.")
        if not payload.get("ok"):
            raise ReadinessFailed(
                "Open the DaVinci Resolve Color page Gallery panel before running still-match.",
                details=payload,
            )
        return payload

    def select_still_thumbnail(self, controls: dict[str, Any], index: int) -> dict[str, Any]:
        gallery_rect = _rect_from_payload(controls["gallery_grid"])
        if index < 1:
            raise ValidationError("Still selector resolved to an invalid index.", details={"index": index})
        columns = max(1, int(gallery_rect.width // 185) or 1)
        row = (index - 1) // columns
        col = (index - 1) % columns
        x = gallery_rect.x + 110 + col * 185
        y = gallery_rect.y + 35 + row * 125
        if x >= gallery_rect.x + gallery_rect.width or y >= gallery_rect.y + gallery_rect.height:
            raise ReadinessFailed(
                "Resolved still thumbnail is outside the visible Gallery grid.",
                details={"index": index, "columns": columns, "point": [x, y], "gallery_grid": gallery_rect.as_payload()},
            )
        _post_mouse_click((x, y))
        time.sleep(0.25)
        return {"index": index, "point": [x, y], "gallery_grid": gallery_rect.as_payload(), "columns": columns}

    def set_mode(self, controls: dict[str, Any], mode: str) -> dict[str, Any]:
        key = "image_wipe" if mode == "image-wipe" else "split_screen"
        rect = _rect_from_payload(controls[key])
        already_enabled = str(controls.get(key, {}).get("value")) == "1"
        if not already_enabled:
            _post_mouse_click(rect.center)
            time.sleep(0.35)
        return {
            "mode": mode,
            "control": key,
            "point": list(rect.center),
            "rect": rect.as_payload(),
            "changed": not already_enabled,
        }

    def capture_proof(self, controls: dict[str, Any], path: Path) -> dict[str, Any]:
        gallery = _rect_from_payload(controls["gallery_grid"])
        viewer = _rect_from_payload(controls["viewer"])
        left = min(gallery.x, viewer.x)
        top = min(gallery.y, viewer.y)
        right = max(gallery.x + gallery.width, viewer.x + viewer.width)
        bottom = max(gallery.y + gallery.height, viewer.y + viewer.height)
        rect = Rect(left, top, right - left, bottom - top)
        path.parent.mkdir(parents=True, exist_ok=True)
        proc = subprocess.run(
            ["screencapture", "-x", "-t", "png", "-R", f"{rect.x},{rect.y},{rect.width},{rect.height}", str(path)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if proc.returncode != 0 or not path.is_file():
            raise ReadinessFailed("Failed to capture Still Match proof screenshot.", details={"path": str(path), "stderr": proc.stderr[-500:]})
        return {"screenshot_path": str(path), "bytes": path.stat().st_size, "region": rect.as_payload()}

    def _accessibility_enabled(self) -> bool:
        proc = _run_osascript('tell application "System Events" to get UI elements enabled', timeout=3.0)
        return proc.returncode == 0 and proc.stdout.strip().lower() == "true"

    def _screen_recording_enabled(self) -> bool:
        with tempfile.TemporaryDirectory(prefix="cutagent-screen-preflight-") as tmpdir:
            target = Path(tmpdir) / "probe.png"
            proc = subprocess.run(["screencapture", "-x", "-t", "png", "-R", "0,0,1,1", str(target)], capture_output=True, text=True, timeout=5)
            return proc.returncode == 0 and target.is_file() and target.stat().st_size > 0


def run_still_match(
    conn: Any,
    *,
    target_clip: str | None,
    still: str | None,
    mode: str,
    proof_dir: Path | None = None,
    driver: MacOSStillMatchGuiDriver | None = None,
) -> dict[str, Any]:
    _ensure_color_page(conn)
    normalized_mode = normalize_mode(mode)
    selector = str(still or "1").strip() or "1"
    target_album, stills = gallery_ops._get_stills(conn, None)
    if not stills:
        raise ReadinessFailed("Still Match requires at least one Gallery still in the current album.", details={"album": "current"})
    resolved = gallery_ops._resolve_still(target_album, stills, selector)
    rows = gallery_ops._still_rows(target_album, stills)
    selected_index = next((row["index"] for row, item in zip(rows, stills) if item is resolved), None)
    if not selected_index:
        raise ReadinessFailed("Still Match could not map resolved still to a Gallery thumbnail index.", details={"selector": selector, "stills": rows})

    active_driver = driver or MacOSStillMatchGuiDriver()
    permissions = active_driver.preflight_permissions()
    controls_before = active_driver.read_controls()
    select_result = active_driver.select_still_thumbnail(controls_before, int(selected_index))
    mode_result = active_driver.set_mode(controls_before, normalized_mode)
    controls_after = active_driver.read_controls()
    mode_key = "image_wipe" if normalized_mode == "image-wipe" else "split_screen"
    if str(controls_after.get(mode_key, {}).get("value")) != "1":
        raise ReadinessFailed(
            "Still Match native viewer comparison control did not reach the requested mode.",
            details={"mode": normalized_mode, "mode_key": mode_key, "controls_before": controls_before, "controls_after": controls_after},
        )
    proof_root = _proof_root(proof_dir)
    proof = active_driver.capture_proof(controls_after, _proof_path(proof_root, normalized_mode))
    set_verification_status("verified")
    set_recoverability("manual")
    return {
        "action": "color.page.still_match",
        "route": ROUTE,
        "engine_scope": "workflow_owned_resolve_gui",
        "target_clip": target_clip,
        "still": {"selector": selector, "index": selected_index, "label": rows[int(selected_index) - 1].get("label", "")},
        "mode": normalized_mode,
        "selected": True,
        "changed": True,
        "proof": proof,
        "preflight": {"permissions": permissions, "controls_before": controls_before, "controls_after": controls_after},
        "selection": select_result,
        "mode_result": mode_result,
    }


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


def _proof_root(proof_dir: Path | None) -> Path:
    root = (proof_dir or DEFAULT_PROOF_DIR).expanduser()
    if not root.is_absolute():
        root = Path.cwd() / root
    root = root.resolve(strict=False)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _proof_path(root: Path, mode: str) -> Path:
    return root / f"still-match-{mode}-{time.strftime('%Y%m%d-%H%M%S')}.png"


def _rect_from_payload(payload: Any) -> Rect:
    if not isinstance(payload, dict):
        raise ResolveWindowNotReady("Still Match control rectangle is missing.", details={"rect": payload})
    return Rect(int(payload["x"]), int(payload["y"]), int(payload["width"]), int(payload["height"]))


def _run_osascript(script: str, *, timeout: float = 5.0) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(["osascript", "-l", "JavaScript", "-e", script], capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        return subprocess.CompletedProcess(["osascript"], 124, stdout=exc.stdout or "", stderr=exc.stderr or str(exc))


def _run_json_jxa(script: str, message: str) -> dict[str, Any]:
    proc = _run_osascript(script, timeout=20.0)
    if proc.returncode != 0:
        raise ResolveWindowNotReady(message, details={"stdout": proc.stdout[-1000:], "stderr": proc.stderr[-1000:]})
    try:
        return json.loads(proc.stdout.strip())
    except json.JSONDecodeError as exc:
        raise ResolveWindowNotReady(message, details={"stdout": proc.stdout[-1000:]}) from exc


def _post_mouse_click(point: tuple[int, int]) -> None:
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
            raise ReadinessFailed("macOS failed to create Still Match mouse event.", details={"event_type": event_type, "point": point})
        try:
            app_services.CGEventPost(0, event)
        finally:
            app_services.CFRelease(event)
        time.sleep(0.025)


_READ_CONTROLS_JXA = r"""
const se = Application("System Events");
const processNames = ["DaVinci Resolve", "Resolve"];
let proc = null;
for (const name of processNames) {
  const matches = se.processes.whose({ name })();
  if (matches.length > 0) { proc = matches[0]; break; }
}
function pack(e) {
  let pos = [0, 0], size = [0, 0], name = "", desc = "", role = "", value = "", title = "";
  try { pos = e.position(); } catch (_) {}
  try { size = e.size(); } catch (_) {}
  try { name = String(e.name()); } catch (_) {}
  try { desc = String(e.description()); } catch (_) {}
  try { role = String(e.role()); } catch (_) {}
  try { value = String(e.value()); } catch (_) {}
  try { title = String(e.title()); } catch (_) {}
  return { x: Number(pos[0] || 0), y: Number(pos[1] || 0), width: Number(size[0] || 0), height: Number(size[1] || 0), name, desc, role, value, title };
}
function largestWindow(windows) {
  let best = null, bestArea = 0;
  for (const win of windows) {
    try {
      const size = win.size();
      const area = Number(size[0] || 0) * Number(size[1] || 0);
      if (area > bestArea) { best = win; bestArea = area; }
    } catch (_) {}
  }
  return best;
}
if (!proc || proc.windows().length === 0) {
  JSON.stringify({ ok: false, reason: "process_or_window_not_found" });
} else {
  const win = largestWindow(proc.windows());
  const queue = [win];
  let scanned = 0, gallery = null, imageWipe = null, splitScreen = null;
  while (queue.length && scanned < 350 && (!gallery || !imageWipe || !splitScreen)) {
    const item = queue.shift();
    scanned += 1;
    const p = pack(item);
    const text = `${p.name} ${p.desc} ${p.value} ${p.title}`.toLowerCase();
    if (!gallery && text.includes("gallery") && p.role === "AXCheckBox") gallery = p;
    if (!imageWipe && text.includes("image wipe")) imageWipe = p;
    if (!splitScreen && text.includes("split screen")) splitScreen = p;
    try {
      const kids = item.uiElements();
      for (let i = 0; i < kids.length; i++) queue.push(kids[i]);
    } catch (_) {}
  }
  if (!gallery || !imageWipe || !splitScreen) {
    JSON.stringify({ ok: false, reason: "still_match_controls_not_found", scanned, gallery, imageWipe, splitScreen });
  } else {
    JSON.stringify({
      ok: true,
      scanned,
      gallery,
      image_wipe: imageWipe,
      split_screen: splitScreen,
      gallery_grid: { x: 0, y: 90, width: 614, height: 415 },
      viewer: { x: 615, y: 90, width: 690, height: 325 }
    });
  }
}
"""
