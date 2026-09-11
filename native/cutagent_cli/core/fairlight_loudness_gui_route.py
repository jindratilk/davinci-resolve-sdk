"""Workflow-owned GUI-assisted Fairlight loudness read/normalize route.

This module reads DaVinci Resolve's native Fairlight Loudness panel from a
screenshot using macOS Vision OCR. It does not expose generic GUI automation.
"""

from __future__ import annotations

import json
import math
import platform
import re
import subprocess
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from ..errors import CLIError, GuiPermissionMissing, ReadinessFailed, ResolveWindowNotReady, ValidationError
from ..output import set_execution_engine, set_recoverability, set_verification_status
from .fairlight_track_visibility_gui_route import _post_mouse_click, _proof_root, _run_osascript
from . import fairlight_ops, timeline_ops

ROUTE_ANALYZE = "fairlight.loudness_analyze_gui"
ROUTE_NORMALIZE = "fairlight.loudness_normalize_gui_clip_gain_db"
ENGINE = "resolve_gui"
DEFAULT_PROOF_DIR = Path("artifacts") / "fairlight-loudness-gui"
PROCESS_NAMES = ("DaVinci Resolve", "Resolve")

LOUDNESS_CROP_WIDTH = 380
LOUDNESS_CROP_HEIGHT = 230
LOUDNESS_CROP_RIGHT_OFFSET = 390
LOUDNESS_CROP_TOP_OFFSET = 35
NORMALIZE_TOLERANCE_LUFS = 0.6
MAX_NORMALIZE_GAIN_STEP_DB = 12.0

_NUMBER_RE = re.compile(r"[-+]?\d+(?:\.\d+)?")


@dataclass(frozen=True)
class Rect:
    x: int
    y: int
    width: int
    height: int

    def as_payload(self) -> dict[str, int]:
        return asdict(self)


class MacOSFairlightLoudnessGuiDriver:
    """Internal macOS driver scoped to the visible Fairlight Loudness panel."""

    process_names = PROCESS_NAMES

    def preflight_permissions(self) -> dict[str, Any]:
        if platform.system() != "Darwin":
            raise GuiPermissionMissing(
                "Fairlight loudness GUI-assisted route requires macOS.",
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

    def read_loudness(self, *, require_integrated: bool = True) -> dict[str, Any]:
        window_rect = self._resolve_window_rect()
        crop_rect = self._loudness_crop_rect(window_rect)
        proof_root = _proof_root(DEFAULT_PROOF_DIR)
        proof_path = _proof_path(proof_root, "analyze")
        self._capture_region(crop_rect, proof_path)
        ocr = _run_vision_ocr(proof_path)
        readback = _parse_loudness_ocr(ocr.get("observations") or [], require_integrated=require_integrated)
        return {
            "window_rect": window_rect.as_payload(),
            "loudness_crop_rect": crop_rect.as_payload(),
            "readback": readback,
            "ocr": {
                "engine": "macos_vision",
                "observation_count": len(ocr.get("observations") or []),
                "observations": ocr.get("observations") or [],
            },
            "proof": {"screenshot_path": str(proof_path), "bytes": proof_path.stat().st_size, "region": crop_rect.as_payload()},
        }

    def refresh_loudness_meter(self, conn: Any, *, readback: dict[str, Any], playback_seconds: float = 6.0) -> dict[str, Any]:
        paused_existing_run = False
        if self._has_ocr_text(readback, "Pause"):
            paused_existing_run = self._click_ocr_text(readback, "Pause")
            time.sleep(0.35)
        reset_clicked = self._click_ocr_text(readback, "Reset")
        time.sleep(0.35)
        control_state = self.read_loudness(require_integrated=False)
        start_clicked = self._click_ocr_text(control_state, "Start")
        resume_clicked = False
        if not start_clicked:
            resume_clicked = self._click_ocr_text(control_state, "Resume")
        if not start_clicked and not resume_clicked:
            raise ReadinessFailed(
                "Could not start the native DaVinci Resolve Fairlight Loudness meter.",
                details={"readback": control_state["readback"], "proof": control_state["proof"]},
            )
        time.sleep(0.25)
        refresher = getattr(conn, "refresh", None)
        if callable(refresher):
            refresher()
        playhead = timeline_ops.set_playhead(conn, "0f", return_details=True)
        _press_space()
        time.sleep(max(0.5, float(playback_seconds)))
        _press_space()
        time.sleep(0.5)
        return {
            "paused_existing_run": paused_existing_run,
            "reset_clicked": reset_clicked,
            "start_clicked": start_clicked,
            "resume_clicked": resume_clicked,
            "playhead": playhead,
            "playback_seconds": float(playback_seconds),
            "control_proof": control_state["proof"],
        }

    def _resolve_window_rect(self) -> Rect:
        proc = _run_osascript(_window_rect_applescript(), timeout=8.0)
        if proc.returncode != 0:
            raise ResolveWindowNotReady(
                "Could not inspect DaVinci Resolve window for Fairlight loudness readback.",
                details={"stderr": proc.stderr[-1000:], "stdout": proc.stdout[-1000:]},
            )
        payload = _json_payload(proc.stdout)
        if not payload.get("ok"):
            raise ResolveWindowNotReady("DaVinci Resolve window is not available for Fairlight loudness readback.", details=payload)
        rect = Rect(
            x=int(payload["window"]["pos"][0]),
            y=int(payload["window"]["pos"][1]),
            width=int(payload["window"]["size"][0]),
            height=int(payload["window"]["size"][1]),
        )
        if rect.width < 900 or rect.height < 500:
            raise ResolveWindowNotReady(
                "DaVinci Resolve window is too small for Fairlight loudness readback.",
                details={"window_rect": rect.as_payload(), "minimum": {"width": 900, "height": 500}},
            )
        return rect

    def _loudness_crop_rect(self, window_rect: Rect) -> Rect:
        return Rect(
            x=int(window_rect.x + max(0, window_rect.width - LOUDNESS_CROP_RIGHT_OFFSET - LOUDNESS_CROP_WIDTH)),
            y=int(window_rect.y + LOUDNESS_CROP_TOP_OFFSET),
            width=int(min(LOUDNESS_CROP_WIDTH, window_rect.width)),
            height=int(min(LOUDNESS_CROP_HEIGHT, window_rect.height)),
        )

    def _capture_region(self, rect: Rect, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        region = f"{rect.x},{rect.y},{rect.width},{rect.height}"
        proc = subprocess.run(
            ["screencapture", "-x", "-t", "png", "-R", region, str(path)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if proc.returncode != 0 or not path.is_file():
            raise ReadinessFailed(
                "Failed to capture Fairlight loudness proof screenshot.",
                details={"screenshot_path": str(path), "region": rect.as_payload(), "stderr": proc.stderr[-500:]},
            )

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

    def _click_ocr_text(self, readback: dict[str, Any], text: str) -> bool:
        crop_payload = readback.get("loudness_crop_rect") or {}
        crop = Rect(
            x=int(crop_payload.get("x") or 0),
            y=int(crop_payload.get("y") or 0),
            width=int(crop_payload.get("width") or 0),
            height=int(crop_payload.get("height") or 0),
        )
        if crop.width <= 0 or crop.height <= 0:
            return False
        wanted = str(text).casefold()
        for item in (readback.get("ocr") or {}).get("observations") or []:
            if wanted not in str(item.get("text") or "").casefold():
                continue
            bbox = item.get("bbox") if isinstance(item.get("bbox"), dict) else {}
            x = crop.x + (float(bbox.get("x") or 0.0) + float(bbox.get("w") or 0.0) / 2.0) * crop.width
            y = crop.y + (1.0 - float(bbox.get("y") or 0.0) - float(bbox.get("h") or 0.0) / 2.0) * crop.height
            _post_mouse_click((int(round(x)), int(round(y))))
            time.sleep(0.25)
            return True
        return False

    def _has_ocr_text(self, readback: dict[str, Any], text: str) -> bool:
        wanted = str(text).casefold()
        return any(wanted in str(item.get("text") or "").casefold() for item in (readback.get("ocr") or {}).get("observations") or [])


def run_loudness_analyze(
    conn: Any,
    *,
    standard: str | None,
    driver: MacOSFairlightLoudnessGuiDriver | None = None,
) -> dict[str, Any]:
    active_driver = driver or MacOSFairlightLoudnessGuiDriver()
    permission_state = active_driver.preflight_permissions()
    page_state = _ensure_fairlight_page(conn)
    result, refresh = _read_loudness_with_fresh_measurement(active_driver, conn)
    readback = result["readback"]
    if standard and _normalize_standard(standard) not in _normalize_standard(readback.get("standard") or ""):
        raise ReadinessFailed(
            "Visible DaVinci Resolve Fairlight loudness standard does not match the requested standard.",
            details={"requested_standard": standard, "visible_standard": readback.get("standard")},
        )
    set_verification_status("verified")
    set_recoverability("manual")
    return {
        "action": "fairlight.loudness.analyze",
        "route": ROUTE_ANALYZE,
        "engine_scope": "workflow_owned_resolve_gui",
        "standard": standard,
        "readback": {
            "verified": True,
            "method": "native DaVinci Resolve Fairlight Loudness panel screenshot OCR",
            "value_type": "visible_loudness_panel_values",
            "requires_visible_loudness_panel": True,
        },
        "loudness": readback,
        "proof": result["proof"],
        "preflight": {"permissions": permission_state, "page": page_state},
        "refresh": refresh,
        "window_rect": result["window_rect"],
        "loudness_crop_rect": result["loudness_crop_rect"],
        "ocr": result["ocr"],
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
    return {"required_page": "fairlight", "previous_page": current, "current_page": final or "fairlight"}


def run_loudness_normalize(
    conn: Any,
    *,
    target_lufs: float | None,
    driver: MacOSFairlightLoudnessGuiDriver | None = None,
) -> dict[str, Any]:
    if target_lufs is None:
        raise ValidationError(
            "Fairlight loudness normalize requires --target-lufs.",
            details={"target_lufs": target_lufs},
            recoverability="not_applicable",
        )
    target = _validate_target_lufs(target_lufs)
    active_driver = driver or MacOSFairlightLoudnessGuiDriver()
    permission_state = active_driver.preflight_permissions()
    page_state = _ensure_fairlight_page(conn)
    before, initial_refresh = _read_loudness_with_fresh_measurement(active_driver, conn, force_refresh=True)
    integrated = before["readback"].get("integrated_lufs")
    if integrated is None:
        raise ReadinessFailed(
            "Visible DaVinci Resolve Fairlight loudness panel did not expose Integrated LUFS.",
            details={"readback": before["readback"], "proof": before["proof"]},
        )
    attempts: list[dict[str, Any]] = []
    after = before
    selectors = _default_audio_timeline_selectors(conn)
    target_preview = fairlight_ops.preview_audio_gain_batch(
        conn,
        gain_db=0.0,
        selectors=selectors,
        allow_empty=False,
        allow_multiple=True,
    )
    target_items = target_preview.get("updated_items") or []
    if not target_items:
        raise ReadinessFailed(
            "Fairlight loudness normalize could not resolve any audio timeline items.",
            details={"selectors": selectors, "preview": target_preview},
        )
    original_gains = {
        str(item.get("item_id") or ""): _gain_or_zero(item.get("previous_gain_db"))
        for item in target_items
        if str(item.get("item_id") or "")
    }
    current_gains = dict(original_gains)
    mutations: list[dict[str, Any]] = []
    delta = None
    try:
        for attempt in range(1, 4):
            current_integrated = after["readback"].get("integrated_lufs")
            if current_integrated is None:
                refresh = active_driver.refresh_loudness_meter(conn, readback=after)
                after = active_driver.read_loudness()
                current_integrated = after["readback"].get("integrated_lufs")
                attempts.append({"attempt": attempt, "refresh": refresh, "readback": after["readback"]})
            if current_integrated is None:
                break
            delta = round(target - float(current_integrated), 1)
            if abs(delta) > MAX_NORMALIZE_GAIN_STEP_DB:
                raise ReadinessFailed(
                    "Refusing unsafe Fairlight loudness normalization gain step.",
                    details={
                        "target_lufs": target,
                        "current_integrated_lufs": current_integrated,
                        "gain_delta_db": delta,
                        "max_gain_step_db": MAX_NORMALIZE_GAIN_STEP_DB,
                        "readback": after["readback"],
                        "proof": after["proof"],
                    },
                )
            attempt_mutations: list[dict[str, Any]] = []
            requested_gains: dict[str, float] = {}
            for item_id, current_gain in list(current_gains.items()):
                requested_gain = _validate_clip_gain(current_gain + delta)
                requested_gains[item_id] = requested_gain
            mutation = fairlight_ops.apply_audio_gain_entries(
                conn,
                entries=[
                    {"item_id": item_id, "gain_db": gain}
                    for item_id, gain in requested_gains.items()
                ],
            )
            current_gains.update(requested_gains)
            attempt_mutations.append(mutation)
            mutations.append(mutation)
            refresh = active_driver.refresh_loudness_meter(conn, readback=after)
            after = active_driver.read_loudness()
            after_integrated = after["readback"].get("integrated_lufs")
            attempts.append(
                {
                    "attempt": attempt,
                    "before_integrated_lufs": current_integrated,
                    "gain_delta_db": delta,
                    "item_count": len(current_gains),
                    "requested_item_gains_db": requested_gains,
                    "after_integrated_lufs": after_integrated,
                    "mutations": attempt_mutations,
                    "refresh": refresh,
                    "verified": after_integrated is not None and abs(float(after_integrated) - target) <= NORMALIZE_TOLERANCE_LUFS,
                }
            )
            if after_integrated is not None and abs(float(after_integrated) - target) <= NORMALIZE_TOLERANCE_LUFS:
                break
    except Exception as exc:
        if mutations:
            rollback = _rollback_item_gains(conn, original_gains)
            if isinstance(exc, CLIError):
                exc.details = {
                    **getattr(exc, "details", {}),
                    "rollback": rollback,
                    "mutations": mutations,
                    "original_item_gains_db": original_gains,
                    "current_item_gains_db": current_gains,
                }
        raise
    after_integrated = after["readback"].get("integrated_lufs")
    verified = after_integrated is not None and abs(float(after_integrated) - target) <= NORMALIZE_TOLERANCE_LUFS
    if not verified or not mutations:
        rollback = _rollback_item_gains(conn, original_gains)
        raise ReadinessFailed(
            "Fairlight loudness normalization did not verify against the visible native Loudness panel.",
            details={
                "target_lufs": target,
                "before_integrated_lufs": integrated,
                "after_integrated_lufs": after_integrated,
                "tolerance_lufs": NORMALIZE_TOLERANCE_LUFS,
                "attempts": attempts,
                "mutations": mutations,
                "original_item_gains_db": original_gains,
                "current_item_gains_db": current_gains,
                "rollback": rollback,
                "initial_refresh": initial_refresh,
            "before_proof": before["proof"],
            "after_proof": after["proof"],
            },
        )
    set_verification_status("verified")
    set_execution_engine("resolve_gui")
    set_recoverability("manual")
    return {
        "action": "fairlight.loudness.normalize",
        "route": ROUTE_NORMALIZE,
        "engine_scope": "workflow_owned_resolve_gui_plus_db_workaround",
        "target_lufs": target,
        "normalization": {
            "method": "native Fairlight Loudness panel readback plus relative DaVinci Resolve clip audio gain",
            "before_integrated_lufs": integrated,
            "after_integrated_lufs": after_integrated,
            "gain_delta_db": delta,
            "original_item_gains_db": original_gains,
            "new_item_gains_db": current_gains,
            "tolerance_lufs": NORMALIZE_TOLERANCE_LUFS,
            "verified": True,
            "attempts": attempts,
        },
        "mutations": mutations,
        "selectors": selectors,
        "target_preview": target_preview,
        "before": {"loudness": before["readback"], "proof": before["proof"], "ocr": before["ocr"]},
        "after": {"loudness": after["readback"], "proof": after["proof"], "ocr": after["ocr"]},
        "preflight": {"permissions": permission_state, "page": page_state},
        "initial_refresh": initial_refresh,
    }


def _read_loudness_with_fresh_measurement(
    driver: MacOSFairlightLoudnessGuiDriver,
    conn: Any,
    *,
    force_refresh: bool = False,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    result = driver.read_loudness(require_integrated=False)
    if not force_refresh and result["readback"].get("integrated_lufs") is not None:
        return result, None
    refresh = driver.refresh_loudness_meter(conn, readback=result)
    result = driver.read_loudness(require_integrated=True)
    return result, refresh


def _default_audio_timeline_selectors(conn: Any) -> list[dict[str, Any]]:
    timeline = getattr(conn, "timeline", None)
    if timeline is None:
        raise ReadinessFailed("Fairlight loudness normalize requires an active timeline.")
    try:
        track_count = int(timeline.GetTrackCount("audio") or 0)
    except Exception as exc:
        raise ReadinessFailed("Could not inspect active timeline audio tracks.", details={"track_type": "audio"}) from exc
    if track_count < 1:
        raise ReadinessFailed("Active timeline has no audio tracks for loudness normalization.")
    try:
        start_frame = int(timeline.GetStartFrame())
        end_frame = int(timeline.GetEndFrame())
    except Exception as exc:
        raise ReadinessFailed("Could not inspect active timeline frame range for loudness normalization.") from exc
    if end_frame <= start_frame:
        raise ReadinessFailed(
            "Active timeline has an empty frame range for loudness normalization.",
            details={"start_frame": start_frame, "end_frame": end_frame},
        )
    return [
        {"track_index": index, "start_frame": f"{start_frame}f", "end_frame": f"{end_frame}f"}
        for index in range(1, track_count + 1)
    ]


def _gain_or_zero(value: Any) -> float:
    if value is None:
        return 0.0
    return round(float(value), 1)


def _validate_clip_gain(value: float) -> float:
    return round(float(value), 1)


def _rollback_item_gains(conn: Any, original_gains: dict[str, float]) -> list[dict[str, Any]]:
    try:
        return [fairlight_ops.apply_audio_gain_entries(
            conn,
            entries=[
                {"item_id": item_id, "gain_db": float(gain)}
                for item_id, gain in original_gains.items()
            ],
        )]
    except Exception as batch_exc:  # pragma: no cover - live safety details.
        rollbacks: list[dict[str, Any]] = [{
            "status": "failed",
            "item_ids": list(original_gains),
            "error": str(batch_exc),
        }]
        # The plural native/DB primitive restores its own partial work before
        # raising. Preserve the older best-effort recovery contract by trying
        # each original value only on this exceptional recovery path.
        for item_id, gain in original_gains.items():
            try:
                rollbacks.append(fairlight_ops.apply_audio_gain_batch(
                    conn,
                    gain_db=float(gain),
                    selectors=[{"item_id": item_id}],
                    allow_empty=False,
                    allow_multiple=False,
                ))
            except Exception as exc:
                rollbacks.append({
                    "status": "failed", "item_id": item_id,
                    "gain_db": gain, "error": str(exc),
                })
        return rollbacks


def _run_vision_ocr(path: Path) -> dict[str, Any]:
    script = _vision_ocr_jxa(str(path))
    proc = subprocess.run(
        ["osascript", "-l", "JavaScript"],
        input=script,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=20,
    )
    if proc.returncode != 0:
        raise ReadinessFailed(
            "macOS Vision OCR failed for Fairlight loudness readback.",
            details={"stderr": proc.stderr[-1000:], "stdout": proc.stdout[-1000:], "screenshot_path": str(path)},
        )
    payload = _json_payload(proc.stdout.strip() or proc.stderr.strip())
    if not payload.get("ok"):
        raise ReadinessFailed("macOS Vision OCR did not complete for Fairlight loudness readback.", details=payload)
    return payload


def _press_space() -> None:
    proc = _run_osascript(
        '''
tell application "DaVinci Resolve" to activate
tell application "System Events" to key code 49
''',
        timeout=5.0,
    )
    if proc.returncode != 0:
        raise ReadinessFailed(
            "Failed to send scoped playback keypress to DaVinci Resolve for loudness refresh.",
            details={"stderr": proc.stderr[-500:], "stdout": proc.stdout[-500:]},
        )


def _parse_loudness_ocr(observations: list[dict[str, Any]], *, require_integrated: bool = True) -> dict[str, Any]:
    items = [item for item in observations if str(item.get("text") or "").strip()]
    standard = _first_text_matching(items, lambda text: "LUFS" in text.upper())
    numbers = [_number_item(item) for item in items]
    numbers = [item for item in numbers if item is not None]
    momentary = _number_near_x(numbers, x_min=0.35, x_max=0.62, prefer_y_min=0.55)
    if momentary is None:
        momentary = _number_below_standard(items, numbers)
    if momentary is not None and momentary > 0:
        momentary = -momentary
    short = _number_below_label(items, numbers, "Short")
    short_max = _number_below_label(items, numbers, "Short Max")
    loudness_range = _number_below_label(items, numbers, "Range")
    integrated = _number_below_label(items, numbers, "Integrated")
    short = _negative_lufs(short)
    short_max = _negative_lufs(short_max)
    integrated = _negative_lufs(integrated)
    if standard is None or (require_integrated and integrated is None):
        raise ReadinessFailed(
            "Could not parse DaVinci Resolve Fairlight Loudness panel OCR.",
            details={"standard": standard, "integrated_lufs": integrated, "observations": observations},
        )
    return {
        "standard": standard,
        "momentary_lufs": momentary,
        "short_lufs": short,
        "short_max_lufs": short_max,
        "range_lu": loudness_range,
        "integrated_lufs": integrated,
        "raw_text": [str(item.get("text") or "") for item in items],
    }


def _number_item(item: dict[str, Any]) -> dict[str, Any] | None:
    text = str(item.get("text") or "").strip()
    match = _NUMBER_RE.search(text)
    if not match:
        return None
    try:
        value = float(match.group(0))
    except ValueError:
        return None
    bbox = item.get("bbox") if isinstance(item.get("bbox"), dict) else {}
    return {
        "value": value,
        "text": text,
        "x": float(bbox.get("x") or 0.0),
        "y": float(bbox.get("y") or 0.0),
        "w": float(bbox.get("w") or 0.0),
        "h": float(bbox.get("h") or 0.0),
    }


def _first_text_matching(items: list[dict[str, Any]], predicate) -> str | None:
    for item in items:
        text = str(item.get("text") or "").strip()
        if predicate(text):
            return text
    return None


def _number_near_x(numbers: list[dict[str, Any]], *, x_min: float, x_max: float, prefer_y_min: float = 0.0) -> float | None:
    candidates = [item for item in numbers if x_min <= item["x"] <= x_max and item["y"] >= prefer_y_min]
    if not candidates:
        return None
    return sorted(candidates, key=lambda item: (-item["y"], item["x"]))[0]["value"]


def _number_below_label(items: list[dict[str, Any]], numbers: list[dict[str, Any]], label: str) -> float | None:
    label_key = label.casefold()
    label_items = [
        item
        for item in items
        if label_key in str(item.get("text") or "").casefold() and not _NUMBER_RE.search(str(item.get("text") or ""))
    ]
    if not label_items:
        return None
    label_box = label_items[0].get("bbox") if isinstance(label_items[0].get("bbox"), dict) else {}
    lx = float(label_box.get("x") or 0.0)
    ly = float(label_box.get("y") or 0.0)
    candidates = [
        item
        for item in numbers
        if abs(item["x"] - lx) <= 0.08 and item["y"] < ly and (ly - item["y"]) <= 0.12
    ]
    if not candidates:
        return None
    return sorted(candidates, key=lambda item: ly - item["y"])[0]["value"]


def _number_below_standard(items: list[dict[str, Any]], numbers: list[dict[str, Any]]) -> float | None:
    standard_items = [item for item in items if "LUFS" in str(item.get("text") or "").upper()]
    if not standard_items:
        return None
    box = standard_items[0].get("bbox") if isinstance(standard_items[0].get("bbox"), dict) else {}
    sx = float(box.get("x") or 0.0)
    sy = float(box.get("y") or 0.0)
    candidates = [
        item
        for item in numbers
        if abs(item["x"] - sx) <= 0.08 and item["y"] < sy and (sy - item["y"]) <= 0.16
    ]
    if not candidates:
        return None
    return sorted(candidates, key=lambda item: sy - item["y"])[0]["value"]


def _negative_lufs(value: float | None) -> float | None:
    if value is None:
        return None
    return -abs(float(value))


def _validate_target_lufs(value: float) -> float:
    try:
        target = float(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError("Target LUFS must be a finite number.", details={"target_lufs": value}) from exc
    if not math.isfinite(target) or target < -70.0 or target > 0.0:
        raise ValidationError(
            "Target LUFS must be finite and between -70 and 0.",
            details={"target_lufs": value, "min": -70.0, "max": 0.0},
            recoverability="not_applicable",
        )
    return round(target, 1)


def _normalize_standard(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").casefold())


def _json_payload(stdout: str) -> dict[str, Any]:
    try:
        return json.loads(stdout.strip())
    except json.JSONDecodeError as exc:
        raise ResolveWindowNotReady(
            "DaVinci Resolve Fairlight loudness probe returned invalid JSON.",
            details={"stdout": stdout[-1000:]},
        ) from exc


def _proof_path(root: Path, stem: str) -> Path:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    return root / f"fairlight-loudness-{stem}-{stamp}.png"


def _window_rect_applescript() -> str:
    return '''
on jsonRect(posList, sizeList)
    return "{\\"pos\\":[" & (item 1 of posList as integer) & "," & (item 2 of posList as integer) & "],\\"size\\":[" & (item 1 of sizeList as integer) & "," & (item 2 of sizeList as integer) & "]}"
end jsonRect

tell application "System Events"
    set procName to missing value
    repeat with candidateName in {"DaVinci Resolve", "Resolve"}
        if exists process (candidateName as string) then
            set procName to candidateName as string
            exit repeat
        end if
    end repeat
    if procName is missing value then return "{\\"ok\\":false,\\"reason\\":\\"process_not_found\\"}"
    tell process procName
        if not (exists window 1) then return "{\\"ok\\":false,\\"reason\\":\\"window_not_found\\"}"
        set targetWindow to missing value
        set bestArea to 0
        repeat with candidateWindow in windows
            set candidateSize to size of candidateWindow
            set candidateArea to (item 1 of candidateSize as integer) * (item 2 of candidateSize as integer)
            if candidateArea > bestArea then
                set targetWindow to candidateWindow
                set bestArea to candidateArea
            end if
        end repeat
        if targetWindow is missing value then return "{\\"ok\\":false,\\"reason\\":\\"window_not_found\\"}"
        return "{\\"ok\\":true,\\"window\\":" & my jsonRect(position of targetWindow, size of targetWindow) & "}"
    end tell
end tell
'''


def _vision_ocr_jxa(path: str) -> str:
    quoted_path = json.dumps(path)
    return f"""
ObjC.import('Foundation');
ObjC.import('Vision');
const path = {quoted_path};
let out = [];
try {{
  const req = $.VNRecognizeTextRequest.alloc.init;
  req.recognitionLevel = $.VNRequestTextRecognitionLevelAccurate;
  req.usesLanguageCorrection = false;
  const url = $.NSURL.fileURLWithPath(path);
  const handler = $.VNImageRequestHandler.alloc['initWithURL:options:'](url, $({{}}));
  const err = Ref();
  const ok = handler['performRequests:error:']($([req]), err);
  const results = req.results;
  const n = results ? results.count : 0;
  for (let i = 0; i < n; i++) {{
    const obs = results.objectAtIndex(i);
    const candidates = obs.topCandidates(1);
    if (candidates && candidates.count > 0) {{
      const c = candidates.objectAtIndex(0);
      const bb = obs.boundingBox;
      out.push({{
        text: ObjC.unwrap(c.string),
        confidence: Number(c.confidence),
        bbox: {{
          x: Number(bb.origin.x),
          y: Number(bb.origin.y),
          w: Number(bb.size.width),
          h: Number(bb.size.height)
        }}
      }});
    }}
  }}
  console.log(JSON.stringify({{ok: !!ok, observations: out}}));
}} catch (e) {{
  console.log(JSON.stringify({{ok: false, error: String(e), observations: out}}));
}}
"""
