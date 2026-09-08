"""Workflow-owned GUI-assisted Color Page ColorSlice route."""

from __future__ import annotations

import json
import math
import platform
import subprocess
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from ..errors import GuiPermissionMissing, ReadinessFailed, ResolveWindowNotReady, ValidationError
from ..output import set_recoverability, set_verification_status
from .magic_mask_gui_route import MacOSMagicMaskGuiDriver, _post_mouse_drag as _post_focus_free_mouse_drag

ROUTE = "color.page_color_slice_gui"
ENGINE = "resolve_gui"
DEFAULT_PROOF_DIR = Path("artifacts") / "color-slice-gui"
PROCESS_NAMES = ("DaVinci Resolve", "Resolve")
VECTORS = ("red", "skin", "yellow", "green", "cyan", "blue", "magenta")
HUE_MIN = -0.10
HUE_MAX = 0.10
HUE_TOLERANCE = 0.011
SATURATION_MIN = 0.0
SATURATION_MAX = 200.0
DENSITY_MIN = 0.0
DENSITY_MAX = 100.0
SLIDER_TOLERANCE = 0.51
SLIDER_UNITS_PER_PIXEL = 2.9


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
class ColorSliceVectorState:
    vector: str
    center: float
    hue: float
    saturation: float
    density: float
    center_raw: str
    hue_raw: str
    saturation_raw: str
    density_raw: str
    hue_label_rect: Rect
    saturation_slider_rect: Rect
    density_slider_rect: Rect
    reset_rect: Rect

    def as_payload(self) -> dict[str, Any]:
        return {
            "vector": self.vector,
            "center": self.center,
            "hue": self.hue,
            "saturation": self.saturation,
            "density": self.density,
            "center_raw": self.center_raw,
            "hue_raw": self.hue_raw,
            "saturation_raw": self.saturation_raw,
            "density_raw": self.density_raw,
            "hue_label_rect": self.hue_label_rect.as_payload(),
            "saturation_slider_rect": self.saturation_slider_rect.as_payload(),
            "density_slider_rect": self.density_slider_rect.as_payload(),
            "reset_rect": self.reset_rect.as_payload(),
        }


def normalize_vector(value: str | None) -> str:
    token = str(value or "red").strip().lower()
    if token not in VECTORS:
        raise ValidationError(
            "ColorSlice vector must be one of red, skin, yellow, green, cyan, blue, or magenta.",
            details={"vector": value, "allowed": list(VECTORS)},
            recoverability="not_applicable",
        )
    return token


def validate_hue(value: float | None) -> float | None:
    if value is None:
        return None
    numeric = _finite_float(value, "hue")
    if numeric < HUE_MIN or numeric > HUE_MAX:
        raise ValidationError(
            "ColorSlice hue uses DaVinci Resolve UI units and must be between -0.10 and 0.10.",
            details={"hue": value, "minimum": HUE_MIN, "maximum": HUE_MAX, "unit": "colorslice_ui"},
            recoverability="not_applicable",
        )
    return round(numeric, 2)


def validate_saturation(value: float | None) -> float | None:
    if value is None:
        return None
    return _bounded_float(value, "saturation", SATURATION_MIN, SATURATION_MAX)


def validate_density(value: float | None) -> float | None:
    if value is None:
        return None
    return _bounded_float(value, "luma", DENSITY_MIN, DENSITY_MAX)


class MacOSColorSliceGuiDriver(MacOSMagicMaskGuiDriver):
    def preflight_permissions(self) -> dict[str, Any]:
        if platform.system() != "Darwin":
            raise GuiPermissionMissing(
                "ColorSlice GUI-assisted route requires macOS.",
                details={"platform": platform.system(), "required": ["macOS"]},
            )
        accessibility = self._accessibility_probe_enabled()
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

    def read_state(self, vector: str) -> ColorSliceVectorState:
        payload = self._read_payload()
        return _payload_to_vector_state(payload, vector)

    def ensure_color_slice_panel(self) -> dict[str, Any]:
        opened = False
        try:
            self._read_payload()
        except ResolveWindowNotReady:
            toolbar_rect = self._find_color_slice_toolbar_rect()
            if toolbar_rect is not None:
                self._post_mouse_drag([toolbar_rect.center], delay_seconds=0.08)
                opened = True
            else:
                opened = self._click_accessibility_description_exact("ColorSlice")
            if not opened:
                opened = self._click_accessibility_label("ColorSlice")
            if opened:
                time.sleep(0.4)
            self._read_payload()
        return {"panel": "ColorSlice", "opened_by_route": opened}

    def _find_color_slice_toolbar_rect(self) -> Rect | None:
        rect = self._focus_free_target_window_rect()
        target = {
            "pid": self._focus_free_target_pid(),
            "name": self._focus_free_target_window_name(),
            "x": rect.x,
            "y": rect.y,
            "width": rect.width,
            "height": rect.height,
        }
        script = f"""
const se = Application("System Events");
const target = {json.dumps(target)};
const matches = se.applicationProcesses.whose({{ unixId: target.pid }})();
let result = null;
if (matches.length > 0) {{
  const roots = matches[0].windows().filter(win => {{
    try {{
      const position = win.position(); const size = win.size();
      return String(win.name() || "") === target.name &&
        Math.abs(Number(position[0]) - target.x) <= 3 && Math.abs(Number(position[1]) - target.y) <= 3 &&
        Math.abs(Number(size[0]) - target.width) <= 3 && Math.abs(Number(size[1]) - target.height) <= 3;
    }} catch (e) {{ return false; }}
  }});
  let elements = [];
  if (roots.length === 1) {{
    try {{ elements = roots[0].entireContents.get(); }} catch (e) {{ elements = []; }}
  }}
  for (const item of elements) {{
    let properties = {{}};
    try {{ properties = item.properties(); }} catch (e) {{ continue; }}
    if (String(properties.role || "") !== "AXCheckBox") continue;
    if (String(properties.description || "") !== "ColorSlice") continue;
    const position = properties.position;
    const size = properties.size;
    if (!position || !size) continue;
    result = {{
      x: Number(position[0]),
      y: Number(position[1]),
      width: Number(size[0]),
      height: Number(size[1]),
    }};
    break;
  }}
}}
JSON.stringify(result);
"""
        payload = _run_json_jxa(script, "Could not locate the ColorSlice toolbar control.")
        if not isinstance(payload, dict):
            return None
        try:
            rect = Rect(
                x=int(round(float(payload["x"]))),
                y=int(round(float(payload["y"]))),
                width=int(round(float(payload["width"]))),
                height=int(round(float(payload["height"]))),
            )
        except (KeyError, TypeError, ValueError):
            return None
        return rect if rect.width > 0 and rect.height > 0 else None

    def _post_mouse_drag(self, points: list[tuple[int, int]], *, delay_seconds: float = 0.025) -> None:
        _post_focus_free_mouse_drag(
            points,
            target_pid=self._focus_free_target_pid(),
            target_window_id=self._focus_free_target_window_id(),
            target_window_rect=self._focus_free_target_window_rect(),
            delay_seconds=delay_seconds,
        )

    def set_values(
        self,
        vector: str,
        *,
        hue: float | None,
        saturation: float | None,
        density: float | None,
    ) -> dict[str, Any]:
        before = self.read_state(vector)
        original_before = before
        actions: list[dict[str, Any]] = []
        if hue == 0 and saturation == 100 and density == 0:
            if (
                abs(before.hue) > HUE_TOLERANCE
                or abs(before.saturation - 100) > SLIDER_TOLERANCE
                or abs(before.density) > SLIDER_TOLERANCE
            ):
                actions.append(self._click_vector_reset(before))
                time.sleep(0.25)
                before = self.read_state(vector)
            if (
                abs(before.hue) <= HUE_TOLERANCE
                and abs(before.saturation - 100) <= SLIDER_TOLERANCE
                and abs(before.density) <= SLIDER_TOLERANCE
            ):
                return {"changed": bool(actions), "before": original_before, "after": before, "actions": actions}
        if saturation is not None and abs(before.saturation - saturation) > SLIDER_TOLERANCE:
            action = self._drive_slider_to_target(vector, "saturation", saturation, before)
            before = action.pop("_after_state")
            actions.append(action)
        if density is not None and abs(before.density - density) > SLIDER_TOLERANCE:
            action = self._drive_slider_to_target(vector, "density", density, before)
            before = action.pop("_after_state")
            actions.append(action)
        if hue is not None and abs(before.hue - hue) > HUE_TOLERANCE:
            actions.append(self._drag_hue(before, hue))
        time.sleep(0.2)
        after = self.read_state(vector)
        mismatches = []
        if saturation is not None and abs(after.saturation - saturation) > SLIDER_TOLERANCE:
            mismatches.append({"field": "saturation", "expected": saturation, "actual": after.saturation})
        if density is not None and abs(after.density - density) > SLIDER_TOLERANCE:
            mismatches.append({"field": "luma", "expected": density, "actual": after.density})
        if hue is not None and abs(after.hue - hue) > HUE_TOLERANCE:
            mismatches.append({"field": "hue", "expected": hue, "actual": after.hue})
        if mismatches:
            raise ReadinessFailed(
                "ColorSlice controls did not reach requested values.",
                details={"vector": vector, "before": before.as_payload(), "after": after.as_payload(), "mismatches": mismatches},
            )
        return {"changed": bool(actions), "before": original_before, "after": after, "actions": actions}

    def capture_proof(self, state: ColorSliceVectorState, path: Path) -> dict[str, Any]:
        path.parent.mkdir(parents=True, exist_ok=True)
        left = max(0, state.density_slider_rect.x - 35)
        top = max(0, state.reset_rect.y - 20)
        right = state.saturation_slider_rect.x + state.saturation_slider_rect.width + 35
        bottom = state.saturation_slider_rect.y + state.saturation_slider_rect.height + 25
        panel_rect = Rect(left, top, max(1, right - left), max(1, bottom - top))
        proof = self.capture_screenshot(self._focus_free_target_window_rect(), path)
        return {**proof, "panel_region": panel_rect.as_payload()}

    def _drag_slider(self, state: ColorSliceVectorState, field: str, target: float) -> dict[str, Any]:
        if field == "saturation":
            current = state.saturation
            rect = state.saturation_slider_rect
        elif field == "density":
            current = state.density
            rect = state.density_slider_rect
        else:
            raise ValueError(f"unknown ColorSlice slider {field}")
        start = rect.center
        pixels = math.ceil(abs(target - current) / SLIDER_UNITS_PER_PIXEL)
        direction = -1 if target > current else 1
        target_point = (start[0], start[1] + direction * max(1, pixels))
        self._post_mouse_drag([start, target_point], delay_seconds=0.05)
        return {
            "field": field,
            "method": "native_vertical_slider_drag",
            "from": current,
            "to": target,
            "start": [start[0], start[1]],
            "target": [target_point[0], target_point[1]],
            "units_per_pixel": SLIDER_UNITS_PER_PIXEL,
        }

    def _click_vector_reset(self, state: ColorSliceVectorState) -> dict[str, Any]:
        point = state.reset_rect.center
        self._post_mouse_drag([point, point], delay_seconds=0.025)
        return {"field": "vector", "method": "native_vector_reset_button", "point": [point[0], point[1]]}

    def _drag_slider_pixels(self, state: ColorSliceVectorState, field: str, pixels_y: int, *, reason: str) -> dict[str, Any]:
        if field == "saturation":
            current = state.saturation
            rect = state.saturation_slider_rect
        elif field == "density":
            current = state.density
            rect = state.density_slider_rect
        else:
            raise ValueError(f"unknown ColorSlice slider {field}")
        start = rect.center
        target_point = (start[0], start[1] + pixels_y)
        self._post_mouse_drag([start, target_point], delay_seconds=0.05)
        return {
            "field": field,
            "method": "native_vertical_slider_drag_pixels",
            "reason": reason,
            "from": current,
            "pixels_y": pixels_y,
            "start": [start[0], start[1]],
            "target": [target_point[0], target_point[1]],
        }

    def _drive_slider_to_target(
        self,
        vector: str,
        field: str,
        target: float,
        initial: ColorSliceVectorState,
    ) -> dict[str, Any]:
        state = initial
        attempts: list[dict[str, Any]] = []
        for _ in range(8):
            current = state.saturation if field == "saturation" else state.density
            if abs(current - target) <= SLIDER_TOLERANCE:
                return {
                    "field": field,
                    "method": "native_vertical_slider_drag_readback_loop",
                    "changed": bool(attempts),
                    "attempts": attempts,
                    "after": state.as_payload(),
                    "_after_state": state,
                }
            if 0.5 < abs(current - target) <= 1.5:
                attempts.append(self._drag_slider_pixels(state, field, -2, reason="parity_escape_overshoot"))
            else:
                attempts.append(self._drag_slider(state, field, target))
            time.sleep(0.25)
            state = self.read_state(vector)
        return {
            "field": field,
            "method": "native_vertical_slider_drag_readback_loop",
            "changed": bool(attempts),
            "attempts": attempts,
            "after": state.as_payload(),
            "_after_state": state,
        }

    def _drag_hue(self, state: ColorSliceVectorState, target: float) -> dict[str, Any]:
        center_x = int(round((state.saturation_slider_rect.center[0] + state.density_slider_rect.center[0]) / 2))
        half_width = 50.0
        y = int(round(min(state.saturation_slider_rect.y, state.density_slider_rect.y) - 22))
        start_x = int(round(center_x + (state.hue / 0.10) * half_width))
        target_x = int(round(center_x + (target / 0.10) * half_width))
        self._post_mouse_drag([(start_x, y), (target_x, y)], delay_seconds=0.05)
        return {"field": "hue", "method": "native_hue_strip_drag", "from": state.hue, "to": target, "start": [start_x, y], "target": [target_x, y]}

    def _read_payload(self) -> dict[str, Any]:
        target_window = self._focus_free_ax_window_target()
        script = _COLORSLICE_READ_JXA.replace("__TARGET_WINDOW_JSON__", json.dumps(target_window))
        payload = _run_json_jxa(script, "Could not inspect ColorSlice controls.")
        if not payload.get("ok"):
            raise ResolveWindowNotReady("DaVinci Resolve ColorSlice controls are not available.", details=payload)
        return payload

    def _accessibility_probe_enabled(self) -> bool:
        proc = _run_osascript(_ACCESSIBILITY_PROBE_JXA, timeout=5.0)
        if proc.returncode != 0:
            return False
        try:
            payload = json.loads(proc.stdout.strip())
        except json.JSONDecodeError:
            return False
        return bool(payload.get("ok"))

    def _screen_recording_enabled(self) -> bool:
        with tempfile.TemporaryDirectory(prefix="cutagent-screen-preflight-") as tmpdir:
            target = Path(tmpdir) / "probe.png"
            proc = subprocess.run(["screencapture", "-x", "-t", "png", "-R", "0,0,1,1", str(target)], capture_output=True, text=True, timeout=5)
            return proc.returncode == 0 and target.is_file() and target.stat().st_size > 0


def run_color_slice_set(
    conn: Any,
    *,
    clip_name: str | None,
    vector: str,
    hue: float | None,
    saturation: float | None,
    density: float | None,
    proof_dir: Path | None = None,
    driver: MacOSColorSliceGuiDriver | None = None,
) -> dict[str, Any]:
    _ensure_color_page(conn)
    target = _verify_current_clip_target(conn, clip_name)
    active_driver = driver or MacOSColorSliceGuiDriver()
    permissions = active_driver.preflight_permissions()
    window_rect = active_driver.find_resolve_window()
    panel = active_driver.ensure_color_slice_panel()
    result = active_driver.set_values(vector, hue=hue, saturation=saturation, density=density)
    after = result["after"]
    proof_root = _proof_root(proof_dir)
    proof = active_driver.capture_proof(after, _proof_path(proof_root, vector))
    set_verification_status("verified")
    set_recoverability("manual")
    return {
        "action": "color.page.color_slice_set",
        "route": ROUTE,
        "target": target,
        "vector": vector,
        "requested": {"hue": hue, "saturation": saturation, "luma": density},
        "changed": result["changed"],
        "before": result["before"].as_payload(),
        "after": after.as_payload(),
        "actions": result["actions"],
        "proof": proof,
        "preflight": {
            "permissions": permissions,
            "page": "color",
            "window_rect": window_rect.as_payload(),
            "panel": panel,
            "focus_mode": "pid_window_targeted_without_workspace_activation",
        },
    }


def _verify_current_clip_target(conn: Any, clip_name: str | None) -> dict[str, Any]:
    timeline = getattr(conn, "timeline", None)
    current = None
    if timeline is not None and hasattr(timeline, "GetCurrentVideoItem"):
        try:
            current = timeline.GetCurrentVideoItem()
        except Exception:
            current = None
    current_name = None
    if current is not None and hasattr(current, "GetName"):
        try:
            current_name = current.GetName()
        except Exception:
            current_name = None
    requested = str(clip_name).strip() if clip_name else None
    if not current_name:
        raise ValidationError(
            "ColorSlice GUI route could not read back the current Color Page clip identity.",
            details={"requested_clip": requested, "current_clip": current_name},
            recoverability="manual",
        )
    if requested and requested not in {current_name, Path(current_name).name}:
        raise ValidationError(
            "ColorSlice GUI route can only target the current Color Page clip.",
            details={"requested_clip": requested, "current_clip": current_name},
            recoverability="manual",
        )
    return {"kind": "current_color_page_clip", "requested_clip": requested, "current_clip": current_name}


def _ensure_color_page(conn: Any) -> None:
    resolve = getattr(conn, "resolve", None)
    if resolve is None:
        raise ReadinessFailed("DaVinci Resolve connection does not expose a resolve object.", details={"required_page": "color"})
    try:
        current = resolve.GetCurrentPage()
    except Exception:
        current = None
    if current != "color":
        opened = resolve.OpenPage("color")
        if opened is False:
            raise ReadinessFailed("DaVinci Resolve refused to switch to the Color page.", details={"current_page": current})
    try:
        final = resolve.GetCurrentPage()
    except Exception:
        final = "color"
    if final != "color":
        raise ReadinessFailed("DaVinci Resolve is not on the Color page.", details={"current_page": final})


def _payload_to_vector_state(payload: dict[str, Any], vector: str) -> ColorSliceVectorState:
    entry = payload.get("vectors", {}).get(vector)
    if not isinstance(entry, dict):
        raise ResolveWindowNotReady("ColorSlice vector was not found.", details={"vector": vector, "payload": payload})
    return ColorSliceVectorState(
        vector=vector,
        center=float(entry["center"]["value"]),
        hue=float(entry["hue"]["value"]),
        saturation=float(entry["saturation"]["value"]),
        density=float(entry["density"]["value"]),
        center_raw=str(entry["center"]["raw"]),
        hue_raw=str(entry["hue"]["raw"]),
        saturation_raw=str(entry["saturation"]["raw"]),
        density_raw=str(entry["density"]["raw"]),
        hue_label_rect=_rect_from_payload(entry["hue_label"]),
        saturation_slider_rect=_rect_from_payload(entry["saturation"]),
        density_slider_rect=_rect_from_payload(entry["density"]),
        reset_rect=_rect_from_payload(entry["reset"]),
    )


def _rect_from_payload(payload: dict[str, Any]) -> Rect:
    rect = Rect(int(payload["x"]), int(payload["y"]), int(payload["width"]), int(payload["height"]))
    if rect.width <= 0 or rect.height <= 0:
        raise ValueError("invalid rect")
    return rect


def _bounded_float(value: float, name: str, minimum: float, maximum: float) -> float:
    numeric = _finite_float(value, name)
    if numeric < minimum or numeric > maximum:
        raise ValidationError(
            f"ColorSlice {name} must be between {minimum:g} and {maximum:g}.",
            details={name: value, "minimum": minimum, "maximum": maximum},
            recoverability="not_applicable",
        )
    return round(numeric, 2)


def _finite_float(value: float, name: str) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"ColorSlice {name} must be numeric.", details={name: value}, recoverability="not_applicable") from exc
    if numeric != numeric or numeric in {float("inf"), float("-inf")}:
        raise ValidationError(f"ColorSlice {name} must be finite.", details={name: value}, recoverability="not_applicable")
    return numeric


def _proof_root(proof_dir: Path | None) -> Path:
    root = (proof_dir or DEFAULT_PROOF_DIR).expanduser()
    if not root.is_absolute():
        root = Path.cwd() / root
    root = root.resolve(strict=False)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _proof_path(root: Path, vector: str) -> Path:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    return root / f"color-slice-{vector}-{stamp}.png"


def _run_osascript(script: str, *, timeout: float = 5.0) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(["osascript", "-l", "JavaScript", "-e", script], capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        return subprocess.CompletedProcess(["osascript"], 124, stdout=exc.stdout or "", stderr=exc.stderr or str(exc))


def _run_json_jxa(script: str, message: str) -> dict[str, Any]:
    proc = _run_osascript(script, timeout=45.0)
    if proc.returncode != 0:
        raise ResolveWindowNotReady(message, details={"stdout": proc.stdout[-1000:], "stderr": proc.stderr[-1000:]})
    try:
        return json.loads(proc.stdout.strip())
    except json.JSONDecodeError as exc:
        raise ResolveWindowNotReady(message, details={"stdout": proc.stdout[-1000:]}) from exc


_COLORSLICE_READ_JXA = r"""
const se = Application("System Events");
const targetWindow = __TARGET_WINDOW_JSON__;
const matches = se.applicationProcesses.whose({ unixId: targetWindow.pid })();
const proc = matches.length === 1 ? matches[0] : null;
function parseNumber(v) {
  const n = Number(String(v || "").trim());
  return Number.isFinite(n) ? n : null;
}
function pack(e) {
  let pos = [0, 0], size = [0, 0], label = "", role = "", desc = "";
  try { pos = e.position(); } catch (_) {}
  try { size = e.size(); } catch (_) {}
  try { label = String(e.value()); } catch (_) { try { label = String(e.title()); } catch (_) {} }
  try { role = String(e.role()); } catch (_) {}
  try { desc = String(e.description()); } catch (_) {}
  return {
    x: Number(pos[0] || 0),
    y: Number(pos[1] || 0),
    width: Number(size[0] || 0),
    height: Number(size[1] || 0),
    label,
    raw: label,
    role,
    desc,
    value: parseNumber(label)
  };
}
function colorSlicePanel(rootKids) {
  for (const candidate of rootKids) {
    try {
      if (String(candidate.role()) !== "AXGroup") continue;
      const pos = candidate.position();
      const size = candidate.size();
      if (Number(pos[1] || 0) < 600 || Number(size[0] || 0) < 500 || Number(size[1] || 0) < 250) continue;
      const kids = candidate.uiElements();
      const title = kids.find(e => {
        try { return String(e.role()) === "AXStaticText" && String(e.value()) === "ColorSlice"; } catch (_) { return false; }
      });
      if (title) return { panel: candidate, kids };
    } catch (_) {}
  }
  return { panel: null, kids: [] };
}
if (!proc || proc.windows().length === 0) {
  JSON.stringify({ ok: false, reason: "process_or_window_not_found" });
} else {
  const roots = proc.windows().filter(win => {
    try {
      const position = win.position(); const size = win.size();
      return String(win.name() || "") === targetWindow.name &&
        Math.abs(Number(position[0]) - targetWindow.x) <= 3 && Math.abs(Number(position[1]) - targetWindow.y) <= 3 &&
        Math.abs(Number(size[0]) - targetWindow.width) <= 3 && Math.abs(Number(size[1]) - targetWindow.height) <= 3;
    } catch (_) { return false; }
  });
  const win = roots.length === 1 ? roots[0] : null;
  if (!win) {
    JSON.stringify({ ok: false, reason: "exact_target_window_not_unique", matched_window_count: roots.length });
  } else {
  const windowPack = pack(win);
  const rootGroups = win.uiElements().filter(e => {
    try { return String(e.role()) === "AXGroup" && e.size()[0] > 600 && e.size()[1] > 360; } catch (_) { return false; }
  }).sort((a, b) => {
    try { return (b.size()[0] * b.size()[1]) - (a.size()[0] * a.size()[1]); } catch (_) { return 0; }
  });
  const root = rootGroups.length > 0 ? rootGroups[0] : null;
  if (!root) {
    JSON.stringify({ ok: false, reason: "main_group_not_found", window: windowPack });
  } else {
  const found = colorSlicePanel(root.uiElements());
  const title = found.kids.find(e => {
    try { return String(e.role()) === "AXStaticText" && String(e.value()) === "ColorSlice"; } catch (_) { return false; }
  });
  const all = found.kids.map(pack);
  const names = ["Red", "Skin", "Yellow", "Green", "Cyan", "Blue", "Magenta"];
  const vectors = {};
  for (const name of names) {
    const index = all.findIndex(e => e.role === "AXStaticText" && e.label === name);
    if (index < 0) continue;
    const label = all[index];
    const reset = all.slice(index + 1, index + 4).find(e => e.role === "AXButton" && e.desc === "Reset");
    const centerLabel = all[index + 2];
    const centerValue = all[index + 3];
    const hueValue = all[index + 5];
    const sliders = all.slice(index + 6, index + 10).filter(e => e.role === "AXSlider");
    if (centerLabel && centerValue && hueValue && sliders.length >= 2 && reset) {
      const sorted = sliders.slice().sort((a,b) => a.x - b.x);
      const density = sorted[0];
      const saturation = sorted[1];
      const hueLabel = {
        x: Math.round((density.x + saturation.x) / 2 - 50),
        y: Math.round(Math.min(density.y, saturation.y) - 41),
        width: 100,
        height: 16,
        label: "Hue",
        raw: "Hue",
        role: "AXStaticText",
        desc: "",
        value: null
      };
      vectors[name.toLowerCase()] = {
        label,
        reset,
        center_label: centerLabel,
        hue_label: hueLabel,
        center: centerValue,
        hue: hueValue,
        density,
        saturation
      };
    }
  }
  JSON.stringify({ ok: Boolean(title) && Object.keys(vectors).length === 7, window: windowPack, title: title ? pack(title) : null, vectors, vector_count: Object.keys(vectors).length });
  }
  }
}
"""


_ACCESSIBILITY_PROBE_JXA = r"""
const se = Application("System Events");
const processNames = ["DaVinci Resolve", "Resolve"];
let ok = false;
let processName = null;
for (const name of processNames) {
  const matches = se.processes.whose({ name })();
  if (matches.length === 0) continue;
  processName = name;
  try {
    matches[0].windows();
    ok = true;
  } catch (_) {
    ok = false;
  }
  break;
}
JSON.stringify({ ok, process_name: processName });
"""
