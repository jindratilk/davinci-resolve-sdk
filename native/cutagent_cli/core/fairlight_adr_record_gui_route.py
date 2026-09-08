"""Workflow-owned GUI-assisted Fairlight ADR record route.

This module only drives DaVinci Resolve's native Fairlight ADR panel:
open ADR, select a stored cue, click the ADR record control, wait for the cue
pass to complete or stop it, and capture proof. It is not a generic GUI layer.
"""

from __future__ import annotations

import platform
import subprocess
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from ..errors import GuiPermissionMissing, ReadinessFailed, ValidationError
from ..output import set_recoverability, set_verification_status
from . import fairlight_ops
from .fairlight_record_gui_route import _post_mouse_click

ROUTE = "fairlight.adr_record_gui"
ENGINE = "resolve_gui"
DEFAULT_PROOF_DIR = Path("artifacts") / "fairlight-adr-record-gui"


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
class AdrRecordState:
    record_brightness: dict[str, Any]
    transport_brightness: dict[str, Any]
    record_active: bool
    record_rect: Rect
    stop_rect: Rect
    cue_row_rect: Rect
    proof_rect: Rect
    window_rect: Rect

    def as_payload(self) -> dict[str, Any]:
        return {
            "record_brightness": self.record_brightness,
            "transport_brightness": self.transport_brightness,
            "record_active": self.record_active,
            "record_rect": self.record_rect.as_payload(),
            "stop_rect": self.stop_rect.as_payload(),
            "cue_row_rect": self.cue_row_rect.as_payload(),
            "proof_rect": self.proof_rect.as_payload(),
            "window_rect": self.window_rect.as_payload(),
        }


class MacOSFairlightAdrRecordGuiDriver:
    """Internal macOS driver scoped to the Fairlight ADR panel."""

    def preflight_permissions(self) -> dict[str, Any]:
        if platform.system() != "Darwin":
            raise GuiPermissionMissing(
                "Fairlight ADR record GUI-assisted route requires macOS.",
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

    def prepare_panel(self, *, cue_index: int) -> AdrRecordState:
        window = _window_rect()
        _post_mouse_click(_adr_record_tab_rect(window).center)
        time.sleep(0.2)
        state = self.read_state(cue_index=cue_index)
        if not _adr_panel_visible(state):
            _post_mouse_click(_adr_toolbar_rect(window).center)
            time.sleep(0.25)
            _post_mouse_click(_adr_record_tab_rect(window).center)
            time.sleep(0.2)
        cue_rect = _cue_row_rect(window, cue_index=cue_index)
        _post_mouse_click(cue_rect.center)
        time.sleep(0.2)
        return self.read_state(cue_index=cue_index)

    def read_state(self, *, cue_index: int) -> AdrRecordState:
        window = _window_rect()
        record_rect = _adr_record_button_rect(window)
        stop_rect = _adr_stop_button_rect(window)
        transport_rect = _transport_record_button_rect(window)
        record_brightness = self.measure_rect(record_rect)
        transport_brightness = self.measure_rect(transport_rect)
        record_active = _is_red_active(record_brightness) or _is_red_active(transport_brightness)
        return AdrRecordState(
            record_brightness=record_brightness,
            transport_brightness=transport_brightness,
            record_active=record_active,
            record_rect=record_rect,
            stop_rect=stop_rect,
            cue_row_rect=_cue_row_rect(window, cue_index=cue_index),
            proof_rect=_adr_proof_rect(window),
            window_rect=window,
        )

    def record_once(self, *, cue_index: int, max_wait_seconds: float = 8.0) -> dict[str, Any]:
        before = self.prepare_panel(cue_index=cue_index)
        _post_mouse_click(before.record_rect.center)
        time.sleep(0.35)
        started = self.read_state(cue_index=cue_index)
        if not started.record_active:
            raise ReadinessFailed(
                "DaVinci Resolve Fairlight ADR record control did not enter recording state.",
                details={
                    "route": ROUTE,
                    "before": before.as_payload(),
                    "after_click": started.as_payload(),
                    "required_setup": [
                        "ADR cue selected",
                        "ADR Record and Playback Setup source selected",
                        "ADR Record and Playback Setup track selected",
                        "Fairlight track armed and input patched",
                    ],
                },
            )
        polls: list[dict[str, Any]] = []
        deadline = time.monotonic() + max(0.5, float(max_wait_seconds))
        stopped = started
        while time.monotonic() < deadline:
            time.sleep(0.25)
            current = self.read_state(cue_index=cue_index)
            polls.append({"record_active": current.record_active, "record_brightness": current.record_brightness})
            stopped = current
            if not current.record_active:
                break
        if stopped.record_active:
            _post_mouse_click(stopped.stop_rect.center)
            time.sleep(0.5)
            stopped = self.read_state(cue_index=cue_index)
        if stopped.record_active:
            raise ReadinessFailed(
                "DaVinci Resolve Fairlight ADR record control did not stop.",
                details={"route": ROUTE, "started": started.as_payload(), "after_stop": stopped.as_payload(), "polls": polls},
            )
        return {"before": before, "started": started, "after": stopped, "polls": polls}

    def measure_rect(self, rect: Rect) -> dict[str, Any]:
        with tempfile.TemporaryDirectory(prefix="cutagent-adr-record-") as tmpdir:
            path = Path(tmpdir) / "probe.png"
            _capture_region(rect, path)
            return _measure_png_color(path)

    def capture_proof(self, state: AdrRecordState, path: Path) -> dict[str, Any]:
        path.parent.mkdir(parents=True, exist_ok=True)
        _capture_region(state.proof_rect, path)
        return {"screenshot_path": str(path), "bytes": path.stat().st_size, "region": state.proof_rect.as_payload()}

    def _accessibility_enabled(self) -> bool:
        proc = _run_osascript('tell application "System Events" to get UI elements enabled', timeout=3.0)
        return proc.returncode == 0 and proc.stdout.strip().lower() == "true"

    def _screen_recording_enabled(self) -> bool:
        with tempfile.TemporaryDirectory(prefix="cutagent-screen-preflight-") as tmpdir:
            target = Path(tmpdir) / "probe.png"
            proc = subprocess.run(["screencapture", "-x", "-t", "png", "-R", "0,0,1,1", str(target)], capture_output=True, text=True, timeout=5)
            return proc.returncode == 0 and target.is_file() and target.stat().st_size > 0


def run_adr_record(
    conn: Any,
    *,
    cue: str | None,
    proof_dir: Path | None = None,
    driver: MacOSFairlightAdrRecordGuiDriver | None = None,
) -> dict[str, Any]:
    cue_info = fairlight_ops.read_fairlight_adr_info_db(conn, limit=200)
    cues = _flatten_cues(cue_info)
    selected = _select_cue(cues, cue)
    active_driver = driver or MacOSFairlightAdrRecordGuiDriver()
    permission_state = active_driver.preflight_permissions()
    page_state = _ensure_fairlight_page(conn)
    result = active_driver.record_once(cue_index=int(selected["cue_index"]))
    proof_root = _proof_root(proof_dir)
    proof = active_driver.capture_proof(result["after"], _proof_path(proof_root, "record"))
    post_info = fairlight_ops.read_fairlight_adr_info_db(conn, limit=200)
    set_verification_status("verified")
    set_recoverability("manual")
    return {
        "action": "fairlight.adr.record",
        "route": ROUTE,
        "engine_scope": "workflow_owned_resolve_gui",
        "cue": selected,
        "changed": True,
        "started_recording": True,
        "record_active_after": result["after"].record_active,
        "before": result["before"].as_payload(),
        "started": result["started"].as_payload(),
        "after": result["after"].as_payload(),
        "polls": result["polls"],
        "proof": proof,
        "readback": {
            "cue_list_before": cue_info.get("adr_model_candidates", []),
            "cue_list_after": post_info.get("adr_model_candidates", []),
            "take_persistence_verified": False,
            "take_persistence_note": "DaVinci Resolve ADR record start/stop is verified by native UI state; take rows are not yet exposed in a stable Project.db schema.",
        },
        "preflight": {"permissions": permission_state, "page": page_state},
    }


def _flatten_cues(info: dict[str, Any]) -> list[dict[str, Any]]:
    cues: list[dict[str, Any]] = []
    for candidate in [*(info.get("strong_candidates", []) or []), *(info.get("adr_model_candidates", []) or [])]:
        for idx, row in enumerate(candidate.get("rows") or [], start=1):
            payload = row.get("row") if isinstance(row, dict) and "row" in row else row
            cue_index = row.get("cue_index") if isinstance(row, dict) else idx
            cues.append(
                {
                    "cue_index": int(cue_index or idx),
                    "table": candidate.get("table"),
                    "kind": candidate.get("kind"),
                    "source": row.get("source") if isinstance(row, dict) else candidate.get("source"),
                    "row": payload,
                }
            )
    return cues


def _select_cue(cues: list[dict[str, Any]], cue: str | None) -> dict[str, Any]:
    if not cues:
        raise ReadinessFailed(
            "No stored ADR cues were found for Fairlight ADR record.",
            details={"route": ROUTE, "preflight_command": "cutagent fairlight adr cue-list --json"},
        )
    if not cue:
        return cues[0]
    wanted = str(cue).strip().lower()
    for candidate in cues:
        row = candidate.get("row") or {}
        values = [str(candidate.get("cue_index") or ""), str(row.get("CueName") or ""), str(row.get("Dialogue") or ""), str(row.get("PromptText") or "")]
        if any(value.strip().lower() == wanted for value in values):
            return candidate
    raise ValidationError(
        "Requested ADR cue was not found.",
        details={"cue": cue, "available": cues},
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
    return {"required_page": "fairlight", "previous_page": current, "current_page": "fairlight"}


def _window_rect() -> Rect:
    proc = _run_osascript(
        'tell application "System Events"\n'
        '  tell process "DaVinci Resolve"\n'
        '    set p to position of window 1\n'
        '    set s to size of window 1\n'
        "  end tell\n"
        '  return (item 1 of p as text) & "," & (item 2 of p as text) & "," & (item 1 of s as text) & "," & (item 2 of s as text)\n'
        "end tell",
        timeout=3.0,
    )
    if proc.returncode != 0:
        raise ReadinessFailed("Could not read DaVinci Resolve window bounds for ADR record.", details={"stderr": proc.stderr[-500:]})
    try:
        x, y, w, h = [int(float(part)) for part in proc.stdout.strip().split(",")]
    except ValueError as exc:
        raise ReadinessFailed("DaVinci Resolve window bounds readback was invalid.", details={"stdout": proc.stdout[-500:]}) from exc
    return Rect(x=x, y=y, width=w, height=h)


def _adr_toolbar_rect(window: Rect) -> Rect:
    return Rect(window.x + 625, window.y + 5, 60, 30)


def _adr_record_tab_rect(window: Rect) -> Rect:
    return Rect(window.x + 200, window.y + 68, 54, 24)


def _adr_record_button_rect(window: Rect) -> Rect:
    return Rect(window.x + 118, window.y + 142, 20, 18)


def _adr_stop_button_rect(window: Rect) -> Rect:
    return Rect(window.x + 88, window.y + 142, 20, 18)


def _transport_record_button_rect(window: Rect) -> Rect:
    return Rect(window.x + 1119, window.y + 244, 20, 20)


def _cue_row_rect(window: Rect, *, cue_index: int) -> Rect:
    return Rect(window.x + 4, window.y + 411 + ((max(1, int(cue_index)) - 1) * 38), 456, 36)


def _adr_proof_rect(window: Rect) -> Rect:
    return Rect(window.x, window.y + 92, 462, 430)


def _capture_region(rect: Rect, path: Path) -> None:
    region = f"{rect.x},{rect.y},{rect.width},{rect.height}"
    proc = subprocess.run(["screencapture", "-x", "-t", "png", "-R", region, str(path)], capture_output=True, text=True, timeout=10)
    if proc.returncode != 0 or not path.is_file():
        raise ReadinessFailed(
            "Failed to capture Fairlight ADR record proof screenshot.",
            details={"screenshot_path": str(path), "region": rect.as_payload(), "stderr": proc.stderr[-500:]},
        )


def _measure_png_color(path: Path) -> dict[str, Any]:
    from PIL import Image

    with Image.open(path) as image:
        rgb = image.convert("RGB")
        pixels = list(rgb.getdata())
    count = len(pixels) or 1
    red_count = sum(1 for r, g, b in pixels if r > 180 and g < 120 and b < 120)
    max_red = max((r for r, _g, _b in pixels), default=0)
    mean_red = round(sum(r for r, _g, _b in pixels) / count, 3)
    return {"width": rgb.width, "height": rgb.height, "pixel_count": count, "red_count": red_count, "max_red": max_red, "mean_red": mean_red}


def _is_red_active(sample: dict[str, Any]) -> bool:
    return int(sample.get("red_count") or 0) >= 8 and int(sample.get("max_red") or 0) >= 200


def _adr_panel_visible(state: AdrRecordState) -> bool:
    sample = state.record_brightness
    return int(sample.get("max_red") or 0) >= 50


def _proof_root(proof_dir: Path | None) -> Path:
    root = (proof_dir or DEFAULT_PROOF_DIR).expanduser()
    if not root.is_absolute():
        root = Path.cwd() / root
    root = root.resolve(strict=False)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _proof_path(root: Path, stem: str) -> Path:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    return root / f"fairlight-adr-{stem}-{stamp}.png"


def _run_osascript(script: str, *, timeout: float = 5.0) -> subprocess.CompletedProcess[str]:
    cmd = ["osascript", "-e", script]
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        return subprocess.CompletedProcess(cmd, 124, stdout=exc.stdout or "", stderr=exc.stderr or str(exc))
