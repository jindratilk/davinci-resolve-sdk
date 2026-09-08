"""Workflow-owned GUI-assisted Color Page scope control route.

The route is intentionally narrow: it only drives DaVinci Resolve's native
Color Page Scopes panel controls exposed by the public ``color page scope-set``
command. It does not expose generic screen automation.
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

ROUTE = "color.page_scope_set_gui"
ENGINE = "resolve_gui"
DEFAULT_PROOF_DIR = Path("artifacts") / "color-scope-gui"
PROCESS_NAMES = ("DaVinci Resolve", "Resolve")
MODE_LABELS = {
    "parade": "Parade",
    "waveform": "Waveform",
    "vectorscope": "Vectorscope",
    "histogram": "Histogram",
    "cie": "CIE Chromaticity",
    "cie_chromaticity": "CIE Chromaticity",
}
Y_RGB_LABELS = {"y": "Y", "cbcr": "CbCr", "rgb": "RGB"}
ZOOM_LABELS = {"1x": False, "2x": True}


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

    @property
    def right(self) -> int:
        return self.x + self.width


@dataclass(frozen=True)
class ScopeHeader:
    mode: str
    window_rect: Rect
    panel_rect: Rect
    title_rect: Rect
    mode_rect: Rect
    settings_rect: Rect

    def as_payload(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "window_rect": self.window_rect.as_payload(),
            "panel_rect": self.panel_rect.as_payload(),
            "title_rect": self.title_rect.as_payload(),
            "mode_rect": self.mode_rect.as_payload(),
            "settings_rect": self.settings_rect.as_payload(),
        }


@dataclass(frozen=True)
class ScopeSettingsState:
    y_rgb: str | None
    colorize: bool | None
    skin_tone_indicator: bool | None
    zoom: str | None
    screenshot_path: str
    popover_rect: Rect

    def as_payload(self) -> dict[str, Any]:
        return {
            "y_rgb": self.y_rgb,
            "colorize": self.colorize,
            "skin_tone_indicator": self.skin_tone_indicator,
            "zoom": self.zoom,
            "screenshot_path": self.screenshot_path,
            "popover_rect": self.popover_rect.as_payload(),
        }


def normalize_scope_mode(value: str) -> str:
    token = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if token not in MODE_LABELS:
        raise ValidationError(
            "Color Page scope mode must be one of parade, waveform, vectorscope, histogram, or cie.",
            details={"mode": value, "allowed": sorted(MODE_LABELS)},
            recoverability="not_applicable",
        )
    return token


def normalize_y_rgb(value: str) -> str:
    token = str(value or "").strip().lower().replace("-", "").replace("_", "")
    if token not in Y_RGB_LABELS:
        raise ValidationError(
            "Color Page scope Y/RGB mode must be one of y, cbcr, or rgb.",
            details={"y_rgb": value, "allowed": sorted(Y_RGB_LABELS)},
            recoverability="not_applicable",
        )
    return token


def normalize_zoom(value: str) -> str:
    token = str(value or "").strip().lower()
    if token not in ZOOM_LABELS:
        raise ValidationError(
            "Color Page scope zoom must be 1x or 2x.",
            details={"zoom": value, "allowed": sorted(ZOOM_LABELS)},
            recoverability="not_applicable",
        )
    return token


class MacOSColorScopeGuiDriver:
    process_names = PROCESS_NAMES

    def preflight_permissions(self) -> dict[str, Any]:
        if platform.system() != "Darwin":
            raise GuiPermissionMissing(
                "Color Page scope GUI-assisted route requires macOS.",
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

    def ensure_scope_panel(self) -> ScopeHeader:
        payload = self._read_scope_payload()
        if payload.get("ok"):
            return _payload_to_header(payload)
        # Color Page bottom-right panel tabs are Keyframes, Scopes, and Info.
        # The middle tab switches the lower-right panel back to Scopes.
        switcher = payload.get("scope_tab_switcher")
        if not switcher:
            raise ResolveWindowNotReady(
                "DaVinci Resolve Color Page Scopes panel is not visible and no Scopes tab switcher was found.",
                details=payload,
            )
        _post_mouse_click(_rect_from_payload(switcher).center)
        time.sleep(0.25)
        payload = self._read_scope_payload()
        if not payload.get("ok"):
            raise ResolveWindowNotReady(
                "DaVinci Resolve Color Page Scopes panel did not become visible after selecting the Scopes tab.",
                details=payload,
            )
        return _payload_to_header(payload)

    def read_header(self) -> ScopeHeader:
        return _payload_to_header(self._read_scope_payload(require_ok=True))

    def set_mode(self, mode: str) -> dict[str, Any]:
        target_label = MODE_LABELS[mode]
        before = self.ensure_scope_panel()
        if before.mode == target_label:
            return {"changed": False, "before": before, "after": before}
        _post_mouse_click(before.mode_rect.center)
        time.sleep(0.12)
        _post_mouse_click(_mode_menu_point(before.mode_rect, mode))
        time.sleep(0.25)
        after = self.read_header()
        if after.mode != target_label:
            raise ReadinessFailed(
                "DaVinci Resolve Color Page Scopes mode did not reach requested value.",
                details={"requested_mode": target_label, "before": before.as_payload(), "after": after.as_payload()},
            )
        return {"changed": True, "before": before, "after": after}

    def open_settings_and_capture(self, header: ScopeHeader, path: Path) -> ScopeSettingsState:
        if not self._scope_options_is_open():
            _post_mouse_click(header.settings_rect.center)
            time.sleep(0.2)
        path.parent.mkdir(parents=True, exist_ok=True)
        proc = subprocess.run(["screencapture", "-x", "-t", "png", str(path)], capture_output=True, text=True, timeout=10)
        if proc.returncode != 0 or not path.is_file():
            raise ReadinessFailed(
                "Failed to capture DaVinci Resolve Color Page Scopes settings proof screenshot.",
                details={"screenshot_path": str(path), "stderr": proc.stderr[-500:]},
            )
        mode = _mode_token_from_label(header.mode)
        payload = self._read_scope_options_payload()
        return _payload_to_settings_state(payload, path, mode)

    def set_settings(
        self,
        header: ScopeHeader,
        *,
        y_rgb: str,
        colorize: bool,
        skin_tone_indicator: bool,
        zoom: str,
    ) -> list[dict[str, Any]]:
        actions: list[dict[str, Any]] = []
        mode = _mode_token_from_label(header.mode)
        if mode in {"parade", "waveform"}:
            actions.append(self._click_settings_control(header, mode, "y_rgb", y_rgb))
            actions.append(self._click_settings_control(header, mode, "colorize", bool(colorize)))
        elif mode == "vectorscope":
            actions.append(self._click_settings_control(header, mode, "colorize", bool(colorize)))
            actions.append(self._click_settings_control(header, mode, "skin_tone_indicator", bool(skin_tone_indicator)))
            actions.append(self._click_settings_control(header, mode, "zoom", zoom))
        elif skin_tone_indicator or zoom == "2x":
            raise ValidationError(
                "Color Page scope skin-tone indicator and 2x zoom apply only to Vectorscope mode.",
                details={"mode": mode, "skin_tone_indicator": skin_tone_indicator, "zoom": zoom},
                recoverability="not_applicable",
            )
        return actions

    def _click_settings_control(self, header: ScopeHeader, mode: str, control: str, value: Any) -> dict[str, Any]:
        # Open settings, capture/read current pixels, click only if a change is needed.
        with tempfile.TemporaryDirectory(prefix="cutagent-scope-settings-") as tmpdir:
            probe_path = Path(tmpdir) / "settings.png"
            before = self.open_settings_and_capture(header, probe_path)
            point = _settings_control_point_from_payload(self._read_scope_options_payload(), mode, control, value)
            current = getattr(before, control)
            if current == value:
                _post_mouse_click(header.settings_rect.center)
                time.sleep(0.08)
                return {"control": control, "changed": False, "before": before.as_payload(), "after": before.as_payload()}
            _post_mouse_click(point)
            time.sleep(0.15)
            # The settings popover usually remains open after checkbox/segment clicks.
            after_path = Path(tmpdir) / "settings-after.png"
            proc = subprocess.run(["screencapture", "-x", "-t", "png", str(after_path)], capture_output=True, text=True, timeout=10)
            if proc.returncode != 0 or not after_path.is_file():
                raise ReadinessFailed(
                    "Failed to capture DaVinci Resolve Color Page Scopes settings readback screenshot.",
                    details={"stderr": proc.stderr[-500:]},
                )
            after = _payload_to_settings_state(self._read_scope_options_payload(), after_path, mode)
            if getattr(after, control) != value:
                raise ReadinessFailed(
                    "DaVinci Resolve Color Page Scopes setting did not reach requested value.",
                    details={
                        "control": control,
                        "requested": value,
                        "before": before.as_payload(),
                        "after": after.as_payload(),
                        "click_point": {"x": point[0], "y": point[1]},
                    },
                )
            _post_mouse_click(header.settings_rect.center)
            time.sleep(0.08)
            return {"control": control, "changed": True, "before": before.as_payload(), "after": after.as_payload()}

    def _read_scope_payload(self, *, require_ok: bool = False) -> dict[str, Any]:
        proc = _run_osascript(_SCOPE_PANEL_JXA, language="JavaScript", timeout=20.0)
        if proc.returncode != 0:
            raise ResolveWindowNotReady(
                "Could not inspect DaVinci Resolve Color Page Scopes controls through macOS Accessibility.",
                details={"stderr": proc.stderr[-1000:], "stdout": proc.stdout[-500:]},
            )
        try:
            payload = json.loads(proc.stdout.strip())
        except json.JSONDecodeError as exc:
            raise ResolveWindowNotReady(
                "DaVinci Resolve Color Page Scopes probe returned invalid data.",
                details={"stdout": proc.stdout[-1000:]},
            ) from exc
        if require_ok and not payload.get("ok"):
            error_cls = ResolveWindowNotFound if payload.get("reason") in {"process_not_found", "window_not_found"} else ReadinessFailed
            raise error_cls("DaVinci Resolve Color Page Scopes controls are not available.", details=payload)
        return payload

    def _read_scope_options_payload(self) -> dict[str, Any]:
        proc = _run_osascript(_SCOPE_OPTIONS_JXA, language="JavaScript", timeout=10.0)
        if proc.returncode != 0:
            raise ResolveWindowNotReady(
                "Could not inspect DaVinci Resolve Color Page Scopes settings popover through macOS Accessibility.",
                details={"stderr": proc.stderr[-1000:], "stdout": proc.stdout[-500:]},
            )
        try:
            payload = json.loads(proc.stdout.strip())
        except json.JSONDecodeError as exc:
            raise ResolveWindowNotReady(
                "DaVinci Resolve Color Page Scopes settings probe returned invalid data.",
                details={"stdout": proc.stdout[-1000:]},
            ) from exc
        if not payload.get("ok"):
            raise ResolveWindowNotReady(
                "DaVinci Resolve Color Page Scopes settings popover is not available.",
                details=payload,
            )
        return payload

    def _scope_options_is_open(self) -> bool:
        try:
            return bool(self._read_scope_options_payload().get("ok"))
        except Exception:
            return False

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


def run_scope_set(
    conn: Any,
    *,
    mode: str,
    y_rgb: str,
    colorize: bool,
    skin_tone_indicator: bool,
    zoom: str,
    proof_dir: Path | None = None,
    driver: MacOSColorScopeGuiDriver | None = None,
) -> dict[str, Any]:
    normalized_mode = normalize_scope_mode(mode)
    normalized_y_rgb = normalize_y_rgb(y_rgb)
    normalized_zoom = normalize_zoom(zoom)
    if normalized_mode not in {"parade", "waveform"} and normalized_y_rgb != "rgb":
        raise ValidationError(
            "Color Page scope Y/RGB mode applies only to Parade and Waveform modes.",
            details={"mode": normalized_mode, "y_rgb": normalized_y_rgb},
            recoverability="not_applicable",
        )
    if normalized_mode != "vectorscope" and (skin_tone_indicator or normalized_zoom == "2x"):
        raise ValidationError(
            "Color Page scope skin-tone indicator and 2x zoom apply only to Vectorscope mode.",
            details={"mode": normalized_mode, "skin_tone_indicator": skin_tone_indicator, "zoom": normalized_zoom},
            recoverability="not_applicable",
        )

    active_driver = driver or MacOSColorScopeGuiDriver()
    permission_state = active_driver.preflight_permissions()
    page_state = _ensure_color_page(conn)
    mode_result = active_driver.set_mode(normalized_mode)
    header = mode_result["after"]
    setting_actions = active_driver.set_settings(
        header,
        y_rgb=normalized_y_rgb,
        colorize=bool(colorize),
        skin_tone_indicator=bool(skin_tone_indicator),
        zoom=normalized_zoom,
    )
    header = active_driver.read_header()
    proof_root = _proof_root(proof_dir)
    proof_path = _proof_path(proof_root)
    final_settings = active_driver.open_settings_and_capture(header, proof_path)
    expected = _expected_settings_for_mode(
        _mode_token_from_label(header.mode),
        y_rgb=normalized_y_rgb,
        colorize=bool(colorize),
        skin_tone_indicator=bool(skin_tone_indicator),
        zoom=normalized_zoom,
    )
    mismatches = {
        key: {"expected": value, "actual": getattr(final_settings, key)}
        for key, value in expected.items()
        if getattr(final_settings, key) != value
    }
    if mismatches or header.mode != MODE_LABELS[normalized_mode]:
        raise ReadinessFailed(
            "DaVinci Resolve Color Page Scopes state did not verify after scope-set.",
            details={"mode": header.mode, "expected_mode": MODE_LABELS[normalized_mode], "mismatches": mismatches},
        )
    _post_mouse_click(header.settings_rect.center)
    set_verification_status("verified")
    set_recoverability("manual")
    return {
        "action": "color.page.scope_set",
        "route": ROUTE,
        "requested": {
            "mode": normalized_mode,
            "y_rgb": normalized_y_rgb,
            "colorize": bool(colorize),
            "skin_tone_indicator": bool(skin_tone_indicator),
            "zoom": normalized_zoom,
        },
        "mode": header.mode,
        "settings": final_settings.as_payload(),
        "changed": bool(mode_result.get("changed")) or any(bool(a.get("changed")) for a in setting_actions),
        "mode_change": {
            "changed": bool(mode_result.get("changed")),
            "before": mode_result["before"].as_payload(),
            "after": mode_result["after"].as_payload(),
        },
        "setting_actions": setting_actions,
        "proof": {"screenshot_path": str(proof_path), "bytes": proof_path.stat().st_size},
        "preflight": {"permissions": permission_state, "page": page_state},
    }


def _ensure_color_page(conn: Any) -> dict[str, Any]:
    resolve = getattr(conn, "resolve", None)
    if resolve is None:
        raise ReadinessFailed(
            "DaVinci Resolve connection does not expose a resolve object for Color page switching.",
            details={"required_page": "color"},
        )
    try:
        current = resolve.GetCurrentPage()
    except Exception:
        current = None
    if current != "color":
        try:
            opened = resolve.OpenPage("color")
        except Exception as exc:
            raise ReadinessFailed(
                "Failed to switch DaVinci Resolve to the Color page.",
                details={"current_page": current, "required_page": "color", "error": str(exc)},
            ) from exc
        if opened is False:
            raise ReadinessFailed(
                "DaVinci Resolve refused to switch to the Color page.",
                details={"current_page": current, "required_page": "color", "api_result": opened},
            )
    try:
        final = resolve.GetCurrentPage()
    except Exception:
        final = "color"
    if final != "color":
        raise ReadinessFailed(
            "DaVinci Resolve is not on the Color page after page switch.",
            details={"current_page": final, "required_page": "color"},
        )
    return {"required_page": "color", "previous_page": current, "current_page": final}


def _payload_to_header(payload: dict[str, Any]) -> ScopeHeader:
    try:
        return ScopeHeader(
            mode=str(payload["mode"]["label"]),
            window_rect=_rect_from_payload(payload["window"]),
            panel_rect=_rect_from_payload(payload["panel"]),
            title_rect=_rect_from_payload(payload["title"]),
            mode_rect=_rect_from_payload(payload["mode"]),
            settings_rect=_rect_from_payload(payload["settings"]),
        )
    except Exception as exc:
        raise ResolveWindowNotReady(
            "DaVinci Resolve Color Page Scopes probe did not include usable controls.",
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


def _mode_token_from_label(label: str) -> str:
    normalized = str(label or "").strip().lower()
    for token, expected in MODE_LABELS.items():
        if normalized == expected.lower():
            return "cie" if token == "cie_chromaticity" else token
    raise ResolveWindowNotReady("Unknown DaVinci Resolve Scopes mode label.", details={"mode_label": label})


def _mode_menu_point(mode_rect: Rect, mode: str) -> tuple[int, int]:
    order = ["parade", "waveform", "vectorscope", "histogram", "cie"]
    try:
        index = order.index(mode)
    except ValueError as exc:
        raise ValidationError("Unsupported Color Page scope mode.", details={"mode": mode}) from exc
    return (mode_rect.x + max(20, min(55, mode_rect.width // 2)), mode_rect.y + mode_rect.height + 16 + index * 20)


def _settings_popover_rect(header: ScopeHeader, mode: str) -> Rect:
    height = 460 if mode == "vectorscope" else 440
    return Rect(x=header.panel_rect.right - 231, y=header.panel_rect.y - height, width=231, height=height)


def _settings_control_point(popover: Rect, mode: str, control: str, value: Any) -> tuple[int, int]:
    if control == "y_rgb":
        offsets = {"y": 55, "cbcr": 115, "rgb": 176}
        return (popover.x + offsets[str(value)], popover.y + 27)
    if control == "colorize":
        return (popover.x + 25, popover.y + (74 if mode == "vectorscope" else 140))
    if control == "skin_tone_indicator":
        return (popover.x + 25, popover.y + 370)
    if control == "zoom":
        return (popover.x + 25, popover.y + 348)
    raise ValueError(f"unknown settings control {control}")


def _settings_control_point_from_payload(payload: dict[str, Any], mode: str, control: str, value: Any) -> tuple[int, int]:
    controls = {str(item.get("label") or item.get("title") or ""): item for item in payload.get("controls") or []}
    label = None
    if control == "y_rgb":
        if mode == "parade":
            label = {"rgb": "RGB", "y": "YRGB", "cbcr": "YCbCr"}[str(value)]
        else:
            label = {"rgb": "RGB", "y": "Y", "cbcr": "CbCr"}[str(value)]
    elif control == "colorize":
        label = "Colorize"
    elif control == "skin_tone_indicator":
        label = "Show Skin Tone Indicator"
    elif control == "zoom":
        label = "Show 2x Zoom"
    if not label or label not in controls:
        popover = _rect_from_payload(payload["window"])
        return _settings_control_point(popover, mode, control, value)
    return _rect_from_payload(controls[label]).center


def _payload_to_settings_state(payload: dict[str, Any], path: Path, mode: str) -> ScopeSettingsState:
    y_rgb: str | None = None
    colorize: bool | None = None
    skin: bool | None = None
    zoom: str | None = None
    controls = {str(item.get("label") or item.get("title") or ""): item for item in payload.get("controls") or []}
    if mode in {"parade", "waveform"}:
        aliases = (
            {"rgb": "RGB", "y": "YRGB", "cbcr": "YCbCr"}
            if mode == "parade"
            else {"rgb": "RGB", "y": "Y", "cbcr": "CbCr"}
        )
        for token, label in aliases.items():
            if str(controls.get(label, {}).get("value")) == "1":
                y_rgb = token
                break
        colorize = str(controls.get("Colorize", {}).get("value")) == "1"
    elif mode == "vectorscope":
        colorize = str(controls.get("Colorize", {}).get("value")) == "1"
        skin = str(controls.get("Show Skin Tone Indicator", {}).get("value")) == "1"
        zoom = "2x" if str(controls.get("Show 2x Zoom", {}).get("value")) == "1" else "1x"
    popover = _rect_from_payload(payload["window"])
    return ScopeSettingsState(
        y_rgb=y_rgb,
        colorize=colorize,
        skin_tone_indicator=skin,
        zoom=zoom,
        screenshot_path=str(path),
        popover_rect=popover,
    )


def _expected_settings_for_mode(mode: str, *, y_rgb: str, colorize: bool, skin_tone_indicator: bool, zoom: str) -> dict[str, Any]:
    if mode in {"parade", "waveform"}:
        return {"y_rgb": y_rgb, "colorize": bool(colorize)}
    if mode == "vectorscope":
        return {"colorize": bool(colorize), "skin_tone_indicator": bool(skin_tone_indicator), "zoom": zoom}
    return {}


def _proof_root(proof_dir: Path | None) -> Path:
    root = (proof_dir or DEFAULT_PROOF_DIR).expanduser()
    if not root.is_absolute():
        root = Path.cwd() / root
    root = root.resolve(strict=False)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _proof_path(root: Path) -> Path:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    return root / f"color-scope-set-{stamp}.png"


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
            raise ReadinessFailed("macOS failed to create Color Page scope mouse event.", details={"point": point})
        try:
            app_services.CGEventPost(0, event)
        finally:
            app_services.CFRelease(event)
        time.sleep(delay_seconds)


_SCOPE_PANEL_JXA = r"""
const se = Application("System Events");
const processNames = ["DaVinci Resolve", "Resolve"];
const modeLabels = ["Parade", "Waveform", "Vectorscope", "Histogram", "CIE Chromaticity"];
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
function pack(el) {
  let pos = [0, 0], size = [0, 0], title = "", value = "", role = "";
  try { pos = el.position(); } catch (e) {}
  try { size = el.size(); } catch (e) {}
  try { title = String(el.title()); } catch (e) {}
  try { value = String(el.value()); } catch (e) {}
  try { role = String(el.role()); } catch (e) {}
  const label = title && title !== "null" ? title : value;
  return { role, label, title, value, pos, size };
}
function largestWindow(windows) {
  let best = null, bestArea = 0;
  for (const win of windows) {
    try {
      const size = win.size();
      const area = Number(size[0] || 0) * Number(size[1] || 0);
      if (area > bestArea) { best = win; bestArea = area; }
    } catch (e) {}
  }
  return best;
}
if (!proc) {
  JSON.stringify({ ok: false, reason: "process_not_found", process_names: processNames });
} else {
  const windows = proc.windows();
  if (windows.length === 0) {
    JSON.stringify({ ok: false, reason: "window_not_found", process_name: processName });
  } else {
    const best = largestWindow(windows);
    const windowPack = pack(best);
    const root = best.uiElements().find(e => {
      try { return String(e.role()) === "AXGroup" && e.size()[0] > 1800 && e.size()[1] > 900; } catch (err) { return false; }
    });
    if (!root) {
      JSON.stringify({ ok: false, reason: "main_group_not_found", window: windowPack });
    } else {
      const rootKids = root.uiElements();
      const tabSwitchers = rootKids
        .filter(e => {
          try {
            const pos = e.position(), size = e.size();
            return String(e.role()) === "AXCheckBox" && size[0] >= 50 && size[0] <= 70 && pos[0] >= windowPack.pos[0] + windowPack.size[0] - 220;
          } catch (err) { return false; }
        })
        .map(pack)
        .sort((a, b) => a.pos[0] - b.pos[0]);
      const scopeSwitcher = tabSwitchers.length >= 2 ? tabSwitchers[1] : null;
      const panelEl = rootKids.find(e => {
        try {
          const pos = e.position(), size = e.size();
          return String(e.role()) === "AXGroup" && pos[0] >= windowPack.pos[0] + windowPack.size[0] - 520 && pos[1] >= windowPack.pos[1] + 600 && size[0] >= 400 && size[1] >= 250;
        } catch (err) { return false; }
      });
      if (!panelEl) {
        JSON.stringify({ ok: false, reason: "scope_panel_group_not_found", window: windowPack, scope_tab_switcher: scopeSwitcher });
      } else {
        const panel = pack(panelEl);
        const kids = panelEl.uiElements().map(pack);
        const title = kids.find(e => e.label === "Scopes");
        const mode = kids.find(e => modeLabels.indexOf(e.label) >= 0);
        const settings = kids.find(e => e.role === "AXCheckBox" && e.pos[0] > panel.pos[0] + panel.size[0] - 120);
        if (!title) {
          JSON.stringify({ ok: false, reason: "scopes_panel_not_visible", window: windowPack, panel, scope_tab_switcher: scopeSwitcher });
        } else if (!mode || !settings) {
          JSON.stringify({ ok: false, reason: "scope_controls_incomplete", window: windowPack, panel, title, mode, settings, scope_tab_switcher: scopeSwitcher });
        } else {
          JSON.stringify({ ok: true, process_name: processName, window: windowPack, panel, title, mode, settings, scope_tab_switcher: scopeSwitcher });
        }
      }
    }
  }
}
"""

_SCOPE_OPTIONS_JXA = r"""
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
function pack(el) {
  let pos = [0, 0], size = [0, 0], title = "", value = "", role = "";
  try { pos = el.position(); } catch (e) {}
  try { size = el.size(); } catch (e) {}
  try { title = String(el.title()); } catch (e) {}
  try { value = String(el.value()); } catch (e) {}
  try { role = String(el.role()); } catch (e) {}
  const label = title && title !== "null" ? title : value;
  return { role, label, title, value, pos, size };
}
if (!proc) {
  JSON.stringify({ ok: false, reason: "process_not_found", process_names: processNames });
} else {
  const windows = proc.windows();
  const option = windows.find(w => {
    try { return String(w.title()) === "Scope Option"; } catch (e) { return false; }
  });
  if (!option) {
    JSON.stringify({ ok: false, reason: "scope_option_not_found", process_name: processName });
  } else {
    const controls = option.uiElements().map(pack);
    JSON.stringify({ ok: true, process_name: processName, window: pack(option), controls });
  }
}
"""
