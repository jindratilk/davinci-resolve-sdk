"""Workflow-owned GUI-assisted Color Page Magic Mask route.

This module is intentionally narrow. It does not expose general screen
automation primitives to agents or users; it only implements the internal
steps required by `color page magic-mask-draw-stroke`.
"""

from __future__ import annotations

import ctypes
import json
import math
import os
import platform
import subprocess
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

from ..errors import (
    APICallFailed,
    ColorPageNotReady,
    GuiPermissionMissing,
    MagicMaskPanelNotReady,
    MagicMaskProofFailed,
    MagicMaskTrackFailed,
    ResolveWindowNotFound,
    ResolveWindowNotReady,
    StrokeMappingFailed,
    ValidationError,
    ViewerGeometryNotFound,
)
from ..output import set_recoverability, set_verification_status
from ..utils.timecode import frames_to_timecode
from . import clip_ops

ROUTE = "color.page_magic_mask_gui"
ENGINE = "resolve_gui"
ALLOWED_MODES = {"person", "object"}
DEFAULT_PROOF_DIR = Path("artifacts") / "magic-mask-gui"
VIEWER_RECT_ENV = "CUTAGENT_MAGIC_MASK_VIEWER_RECT"
PANEL_CHECK_BYPASS_ENV = "CUTAGENT_MAGIC_MASK_SKIP_PANEL_CHECK"
PROCESS_NAMES = ("DaVinci Resolve", "Resolve")


@dataclass(frozen=True)
class Rect:
    x: int
    y: int
    width: int
    height: int

    def as_payload(self) -> dict[str, int]:
        return asdict(self)


@dataclass(frozen=True)
class MagicMaskProofPaths:
    screenshot_path: Path
    export_path: Path


ProofExporter = Callable[[Path], dict[str, Any]]


def normalize_magic_mask_mode(value: str) -> str:
    normalized = str(value or "").strip().lower()
    aliases = {
        "p": "person",
        "people": "person",
        "human": "person",
        "o": "object",
        "obj": "object",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized not in ALLOWED_MODES:
        raise ValidationError(
            "Magic Mask GUI mode must be one of person or object.",
            details={"mode": value, "allowed": sorted(ALLOWED_MODES)},
            recoverability="not_applicable",
        )
    return normalized


def parse_normalized_stroke(value: str) -> list[tuple[float, float]]:
    raw = str(value or "").strip()
    if not raw:
        raise ValidationError(
            "Magic Mask stroke must not be empty.",
            details={"stroke": value},
            recoverability="not_applicable",
        )

    points: list[tuple[float, float]] = []
    for index, pair in enumerate(raw.split(";"), start=1):
        pieces = [part.strip() for part in pair.split(",")]
        if len(pieces) != 2 or not all(pieces):
            raise ValidationError(
                "Magic Mask stroke points must use x,y pairs separated by semicolons.",
                details={"stroke": value, "point_index": index, "point": pair},
                recoverability="not_applicable",
            )
        try:
            x = float(pieces[0])
            y = float(pieces[1])
        except ValueError as exc:
            raise ValidationError(
                "Magic Mask stroke coordinates must be numeric.",
                details={"stroke": value, "point_index": index, "point": pair},
                recoverability="not_applicable",
            ) from exc
        if not (math.isfinite(x) and math.isfinite(y)):
            raise ValidationError(
                "Magic Mask stroke coordinates must be finite.",
                details={"stroke": value, "point_index": index, "point": pair},
                recoverability="not_applicable",
            )
        if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
            raise ValidationError(
                "Magic Mask stroke coordinates must be normalized between 0 and 1.",
                details={"stroke": value, "point_index": index, "point": [x, y]},
                recoverability="not_applicable",
            )
        points.append((x, y))

    if len(points) < 2:
        raise ValidationError(
            "Magic Mask stroke requires at least two points.",
            details={"stroke": value, "point_count": len(points)},
            recoverability="not_applicable",
        )
    return points


def map_stroke_to_viewer_pixels(points: Iterable[tuple[float, float]], viewer_rect: Rect) -> list[tuple[int, int]]:
    if viewer_rect.width <= 0 or viewer_rect.height <= 0:
        raise StrokeMappingFailed(
            "Viewer rectangle has invalid dimensions.",
            details={"viewer_rect": viewer_rect.as_payload()},
        )
    mapped: list[tuple[int, int]] = []
    for x, y in points:
        if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
            raise StrokeMappingFailed(
                "Normalized stroke point is outside the viewer frame.",
                details={"point": [x, y], "viewer_rect": viewer_rect.as_payload()},
            )
        mapped.append(
            (
                int(round(viewer_rect.x + x * viewer_rect.width)),
                int(round(viewer_rect.y + y * viewer_rect.height)),
            )
        )
    if len(mapped) < 2:
        raise StrokeMappingFailed(
            "Mapped stroke requires at least two points.",
            details={"mapped_point_count": len(mapped), "viewer_rect": viewer_rect.as_payload()},
        )
    return mapped


def validate_clip_target(value: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValidationError(
            "Magic Mask GUI workflow requires an explicit clip target.",
            details={"clip": value},
            recoverability="not_applicable",
        )
    return normalized


def _run_osascript(script: str, *, language: str | None = None, timeout: float = 5.0) -> subprocess.CompletedProcess[str]:
    cmd = ["osascript"]
    if language:
        cmd.extend(["-l", language])
    cmd.extend(["-e", script])
    try:
        return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        return subprocess.CompletedProcess(cmd, 124, stdout=exc.stdout or "", stderr=exc.stderr or str(exc))


def _swift_resolve_window_onscreen_probe(rect: Rect, *, expected_pid: int | None = None) -> dict[str, Any]:
    script = f"""
import CoreGraphics
import Foundation

let target: [String: Double] = [
    "x": {float(rect.x)},
    "y": {float(rect.y)},
    "width": {float(rect.width)},
    "height": {float(rect.height)}
]
let expectedPid = {int(expected_pid or 0)}

func number(_ value: Any?) -> Double {{
    if let value = value as? NSNumber {{ return value.doubleValue }}
    if let value = value as? Double {{ return value }}
    if let value = value as? Int {{ return Double(value) }}
    return 0
}}

func overlapRatio(_ a: [String: Double], _ b: [String: Double]) -> Double {{
    let left = max(a["x"] ?? 0, b["x"] ?? 0)
    let top = max(a["y"] ?? 0, b["y"] ?? 0)
    let right = min((a["x"] ?? 0) + (a["width"] ?? 0), (b["x"] ?? 0) + (b["width"] ?? 0))
    let bottom = min((a["y"] ?? 0) + (a["height"] ?? 0), (b["y"] ?? 0) + (b["height"] ?? 0))
    let width = max(0, right - left)
    let height = max(0, bottom - top)
    return (width * height) / max(1, (a["width"] ?? 0) * (a["height"] ?? 0))
}}

let windows = CGWindowListCopyWindowInfo(.optionOnScreenOnly, kCGNullWindowID) as? [[String: Any]] ?? []
var candidates: [[String: Any]] = []
var matched: [String: Any]? = nil
for window in windows {{
    let owner = window[kCGWindowOwnerName as String] as? String ?? ""
    let title = window[kCGWindowName as String] as? String ?? ""
    if !owner.contains("DaVinci") && !owner.contains("Resolve") && !title.contains("DaVinci") && !title.contains("Resolve") {{
        continue
    }}
    let rawBounds = window[kCGWindowBounds as String] as? [String: Any] ?? [:]
    let bounds: [String: Double] = [
        "x": number(rawBounds["X"]),
        "y": number(rawBounds["Y"]),
        "width": number(rawBounds["Width"]),
        "height": number(rawBounds["Height"])
    ]
    let alpha = number(window[kCGWindowAlpha as String])
    let layer = number(window[kCGWindowLayer as String])
    let ownerPid = number(window[kCGWindowOwnerPID as String])
    var candidate: [String: Any] = [
        "owner": owner,
        "name": title,
        "window_id": number(window[kCGWindowNumber as String]),
        "owner_pid": ownerPid,
        "alpha": alpha,
        "layer": layer,
        "bounds": bounds,
        "overlap_ratio": overlapRatio(target, bounds)
    ]
    candidates.append(candidate)
    if (expectedPid <= 0 || Int(ownerPid) == expectedPid) && alpha > 0 && layer == 0 && (bounds["width"] ?? 0) >= 640 && (bounds["height"] ?? 0) >= 360 && (candidate["overlap_ratio"] as? Double ?? 0) >= 0.6 {{
        matched = candidate
        break
    }}
}}
let payload: [String: Any] = ["ok": matched != nil, "matched": matched as Any, "candidates": Array(candidates.prefix(10))]
let data = try! JSONSerialization.data(withJSONObject: payload, options: [])
print(String(data: data, encoding: .utf8)!)
"""
    try:
        proc = subprocess.run(
            ["swift", "-"],
            input=script,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return {"ok": False, "error": "swift_probe_timed_out", "stderr": exc.stderr or str(exc)}
    if proc.returncode != 0:
        return {"ok": False, "error": "swift_probe_failed", "stderr": proc.stderr[-500:]}
    try:
        payload = json.loads(proc.stdout.strip())
    except json.JSONDecodeError:
        return {"ok": False, "error": "swift_probe_invalid_json", "stdout": proc.stdout[-500:]}
    return payload if isinstance(payload, dict) else {"ok": False, "error": "swift_probe_non_object"}


def _rect_from_cg_window_candidate(candidate: Any) -> Rect | None:
    if not isinstance(candidate, dict):
        return None
    bounds = candidate.get("bounds")
    if not isinstance(bounds, dict):
        return None
    try:
        rect = Rect(
            x=int(round(float(bounds.get("x") if bounds.get("x") is not None else bounds.get("X")))),
            y=int(round(float(bounds.get("y") if bounds.get("y") is not None else bounds.get("Y")))),
            width=int(round(float(bounds.get("width") if bounds.get("width") is not None else bounds.get("Width")))),
            height=int(round(float(bounds.get("height") if bounds.get("height") is not None else bounds.get("Height")))),
        )
    except (TypeError, ValueError):
        return None
    if rect.width < 640 or rect.height < 360:
        return None
    return rect


def _cg_resolve_front_window_probe() -> dict[str, Any]:
    script = """
ObjC.import("CoreGraphics");
const list = $.CGWindowListCopyWindowInfo($.kCGWindowListOptionOnScreenOnly, $.kCGNullWindowID);
const count = list ? list.count : 0;
let candidates = [];
let matched = null;
for (let i = 0; i < count; i++) {
  const raw = ObjC.deepUnwrap(list.objectAtIndex(i));
  const owner = String(raw.kCGWindowOwnerName || "");
  const title = String(raw.kCGWindowName || "");
  if (!owner.includes("Resolve") && !owner.includes("DaVinci") && !title.includes("Resolve") && !title.includes("DaVinci")) continue;
  const bounds = raw.kCGWindowBounds || {};
  const candidate = {
    owner,
    name: title,
    window_id: Number(raw.kCGWindowNumber || 0),
    owner_pid: Number(raw.kCGWindowOwnerPID || 0),
    alpha: Number(raw.kCGWindowAlpha || 0),
    layer: Number(raw.kCGWindowLayer || 0),
    onscreen: raw.kCGWindowIsOnscreen === undefined ? null : Boolean(raw.kCGWindowIsOnscreen),
    bounds: {
      x: Number(bounds.X || 0),
      y: Number(bounds.Y || 0),
      width: Number(bounds.Width || 0),
      height: Number(bounds.Height || 0),
    },
  };
  candidates.push(candidate);
  if (
    candidate.alpha > 0 &&
    candidate.layer === 0 &&
    candidate.onscreen === true &&
    candidate.bounds.width >= 640 &&
    candidate.bounds.height >= 360 &&
    (candidate.name.includes("DaVinci Resolve") || candidate.owner.includes("DaVinci Resolve"))
  ) {
    matched = candidate;
    break;
  }
}
JSON.stringify({ ok: matched !== null, matched, candidates: candidates.slice(0, 10) });
"""
    proc = _run_osascript(script, language="JavaScript", timeout=5.0)
    if proc.returncode != 0:
        return {"ok": False, "error": "cg_probe_failed", "stderr": proc.stderr[-500:]}
    try:
        payload = json.loads(proc.stdout.strip())
    except json.JSONDecodeError:
        return {"ok": False, "error": "cg_probe_invalid_json", "stdout": proc.stdout[-500:]}
    return payload if isinstance(payload, dict) else {"ok": False, "error": "cg_probe_non_object"}


def _resolve_rect_from_cg_probe_payload(payload: dict[str, Any]) -> Rect | None:
    if not isinstance(payload, dict) or not payload.get("ok"):
        return None
    if isinstance(payload.get("candidates"), list):
        return _preferred_resolve_rect_from_candidates(payload)
    return _rect_from_cg_window_candidate(payload.get("matched"))


def _resolve_rect_matching_ax_window(payload: dict[str, Any], ax_payload: dict[str, Any]) -> Rect | None:
    """Map display-local Qt AX coordinates to global CoreGraphics coordinates."""

    candidates = payload.get("candidates") if isinstance(payload, dict) else None
    ax_size = ax_payload.get("size")
    if not isinstance(candidates, list) or not isinstance(ax_size, (list, tuple)) or len(ax_size) < 2:
        return None
    try:
        ax_width = int(round(float(ax_size[0])))
        ax_height = int(round(float(ax_size[1])))
    except (TypeError, ValueError):
        return None
    ax_name = str(ax_payload.get("name") or "")
    ranked: list[tuple[int, Rect]] = []
    for candidate in candidates:
        rect = _rect_from_cg_window_candidate(candidate)
        if rect is None or abs(rect.width - ax_width) > 3 or abs(rect.height - ax_height) > 3:
            continue
        candidate_name = str(candidate.get("name") or "") if isinstance(candidate, dict) else ""
        title_score = 2 if ax_name and candidate_name == ax_name else 1 if not ax_name and not candidate_name else 0
        ranked.append((title_score, rect))
    if not ranked:
        return None
    ranked.sort(key=lambda row: row[0], reverse=True)
    if len(ranked) > 1 and ranked[0][0] == ranked[1][0]:
        return None
    return ranked[0][1]


def _preferred_resolve_rect_from_candidates(payload: dict[str, Any]) -> Rect | None:
    candidates = payload.get("candidates") if isinstance(payload, dict) else None
    if not isinstance(candidates, list):
        return None
    ranked_by_identity: dict[tuple[Any, ...], tuple[int, int, Rect]] = {}
    for candidate in candidates:
        rect = _rect_from_cg_window_candidate(candidate)
        if rect is None or not isinstance(candidate, dict):
            continue
        identity = (
            int(candidate.get("owner_pid") or 0),
            int(candidate.get("window_id") or 0),
            str(candidate.get("name") or ""),
            rect,
        )
        ranked_by_identity[identity] = (1 if str(candidate.get("name") or "").strip() else 0, rect.width * rect.height, rect)
    ranked = list(ranked_by_identity.values())
    if not ranked:
        return None
    ranked.sort(key=lambda row: (row[0], row[1]), reverse=True)
    if len(ranked) > 1 and ranked[0][:2] == ranked[1][:2]:
        return None
    return ranked[0][2]


def _parse_rect_env(value: str) -> Rect:
    pieces = [piece.strip() for piece in value.split(",")]
    if len(pieces) != 4:
        raise ViewerGeometryNotFound(
            f"{VIEWER_RECT_ENV} must be x,y,width,height.",
            details={"env": VIEWER_RECT_ENV, "value": value},
        )
    try:
        x, y, width, height = (int(float(piece)) for piece in pieces)
    except ValueError as exc:
        raise ViewerGeometryNotFound(
            f"{VIEWER_RECT_ENV} must contain numeric values.",
            details={"env": VIEWER_RECT_ENV, "value": value},
        ) from exc
    if width <= 0 or height <= 0:
        raise ViewerGeometryNotFound(
            f"{VIEWER_RECT_ENV} width and height must be positive.",
            details={"env": VIEWER_RECT_ENV, "value": value},
        )
    return Rect(x=x, y=y, width=width, height=height)


def _configured_resolve_pid() -> int | None:
    raw = str(os.environ.get("CUTAGENT_RESOLVE_PID") or "").strip()
    if not raw:
        return None
    try:
        pid = int(raw)
    except ValueError:
        return None
    return pid if pid > 0 else None


class MacOSMagicMaskGuiDriver:
    """Internal macOS driver scoped to DaVinci Resolve Magic Mask only."""

    process_names = PROCESS_NAMES

    @property
    def process_name(self) -> str:
        return self.process_names[0]

    def _process_names_payload(self) -> list[str]:
        return list(self.process_names)

    def preflight_permissions(self) -> dict[str, Any]:
        if platform.system() != "Darwin":
            raise GuiPermissionMissing(
                "Magic Mask GUI-assisted route requires macOS.",
                details={"platform": platform.system(), "required": ["macOS"]},
            )

        missing: list[str] = []
        accessibility = self._accessibility_enabled()
        screen_recording = self._screen_recording_enabled()
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
                    "target_application": self.process_name,
                    "target_process_names": self._process_names_payload(),
                },
            )
        return {"accessibility": True, "screen_recording": True}

    def find_resolve_window(self) -> Rect:
        configured_pid = _configured_resolve_pid()
        script = r"""
const se = Application("System Events");
const processNames = ["DaVinci Resolve", "Resolve"];
const configuredPid = __CONFIGURED_PID__;
let proc = null;
let matchedName = null;
if (configuredPid > 0) {
  const candidate = se.processes.whose({ unixId: { _equals: configuredPid } })[0];
  try {
    if (candidate.exists()) {
      proc = candidate;
      matchedName = String(candidate.name() || "");
    }
  } catch (e) {}
} else {
  for (const name of processNames) {
    const candidate = se.processes.whose({ name: { _equals: name } })[0];
    try {
      if (candidate.exists()) {
        proc = candidate;
        matchedName = name;
        break;
      }
    } catch (e) {}
  }
}
if (!proc) {
  JSON.stringify({ ok: false, reason: "process_not_found" });
} else {
  const windows = proc.windows;
  if (windows.length === 0) {
    JSON.stringify({ ok: false, reason: "window_not_found" });
  } else {
    let best = null;
    let bestScore = -1;
    for (let i = 0; i < windows.length; i++) {
      const candidate = windows[i];
      try {
        const size = candidate.size();
        const area = Number(size[0] || 0) * Number(size[1] || 0);
        let title = "";
        try { title = String(candidate.name() || "").trim(); } catch (e) {}
        const score = (title ? 1000000000 : 0) + area;
        if (score > bestScore) {
          best = candidate;
          bestScore = score;
        }
      } catch (e) {}
    }
    if (!best) {
      JSON.stringify({ ok: false, reason: "window_geometry_not_found" });
    } else {
      JSON.stringify({ ok: true, process_name: matchedName, name: best.name(), position: best.position(), size: best.size() });
    }
  }
}
"""
        script = script.replace("__CONFIGURED_PID__", str(configured_pid or 0))
        proc = _run_osascript(script, language="JavaScript", timeout=5.0)
        if proc.returncode != 0:
            raise ResolveWindowNotFound(
                "Could not inspect DaVinci Resolve windows through macOS Accessibility.",
                details={"stderr": proc.stderr[-500:]},
            )
        try:
            payload = json.loads(proc.stdout.strip())
        except json.JSONDecodeError as exc:
            raise ResolveWindowNotReady(
                "DaVinci Resolve window probe returned invalid data.",
                details={"stdout": proc.stdout[-500:]},
            ) from exc
        if not payload.get("ok"):
            cg_payload = _cg_resolve_front_window_probe()
            cg_rect = _resolve_rect_from_cg_probe_payload(cg_payload)
            if cg_rect is None:
                swift_inventory = _swift_resolve_window_onscreen_probe(Rect(x=0, y=0, width=1, height=1))
                cg_rect = _preferred_resolve_rect_from_candidates(swift_inventory)
                cg_payload = {**cg_payload, "swift_window_inventory": swift_inventory}
            if cg_rect is not None and payload.get("reason") in {
                "window_not_found",
                "window_geometry_not_found",
                "process_not_found",
            }:
                self._remember_window_target(cg_payload, cg_rect)
                self._verify_resolve_window_onscreen(cg_rect, ax_payload={**payload, "cg_window_probe": cg_payload})
                return cg_rect
            raise ResolveWindowNotFound(
                "No DaVinci Resolve window is available for Magic Mask GUI-assisted route.",
                details={**payload, "cg_window_probe": cg_payload},
            )
        try:
            position = payload["position"]
            size = payload["size"]
            rect = Rect(x=int(position[0]), y=int(position[1]), width=int(size[0]), height=int(size[1]))
        except Exception as exc:
            raise ResolveWindowNotReady(
                "DaVinci Resolve window probe did not include usable geometry.",
                details=payload,
            ) from exc
        if rect.width <= 0 or rect.height <= 0:
            raise ResolveWindowNotReady(
                "DaVinci Resolve front window has invalid geometry.",
                details={"window_rect": rect.as_payload(), "payload": payload},
            )
        swift_payload = _swift_resolve_window_onscreen_probe(rect, expected_pid=configured_pid)
        global_rect = _resolve_rect_matching_ax_window(swift_payload, payload)
        if global_rect is None:
            raise ResolveWindowNotReady(
                "DaVinci Resolve window identity is ambiguous across Accessibility and CoreGraphics.",
                details={"ax_window": payload, "swift_window_probe": swift_payload},
            )
        self._remember_window_target(swift_payload, global_rect, preferred_name=str(payload.get("name") or ""))
        self._verify_resolve_window_onscreen(global_rect, ax_payload={**payload, "swift_window_probe": swift_payload})
        return global_rect

    def _remember_window_target(self, payload: dict[str, Any], rect: Rect, *, preferred_name: str = "") -> None:
        candidates = payload.get("candidates") if isinstance(payload, dict) else None
        matched = payload.get("matched") if isinstance(payload, dict) else None
        rows = [matched] if isinstance(matched, dict) else []
        if isinstance(candidates, list):
            rows.extend(candidate for candidate in candidates if isinstance(candidate, dict))

        ranked_by_identity: dict[tuple[Any, ...], tuple[int, dict[str, Any]]] = {}
        for candidate in rows:
            candidate_rect = _rect_from_cg_window_candidate(candidate)
            if candidate_rect != rect:
                continue
            name = str(candidate.get("name") or "")
            identity = (
                int(candidate.get("owner_pid") or 0),
                int(candidate.get("window_id") or 0),
                name,
                candidate_rect,
            )
            ranked_by_identity[identity] = (2 if preferred_name and name == preferred_name else 1 if name else 0, candidate)
        ranked = list(ranked_by_identity.values())
        if not ranked:
            raise ResolveWindowNotReady(
                "DaVinci Resolve window identity could not be proven for focus-free Magic Mask input.",
                details={"window_rect": rect.as_payload(), "preferred_name": preferred_name},
            )
        ranked.sort(key=lambda row: row[0], reverse=True)
        if len(ranked) > 1 and ranked[0][0] == ranked[1][0]:
            raise ResolveWindowNotReady(
                "DaVinci Resolve window identity is ambiguous for focus-free Magic Mask input.",
                details={
                    "window_rect": rect.as_payload(),
                    "preferred_name": preferred_name,
                    "candidate_count": len(ranked),
                },
            )
        candidate = ranked[0][1]
        try:
            window_id = int(candidate.get("window_id") or 0)
            owner_pid = int(candidate.get("owner_pid") or 0)
        except (TypeError, ValueError):
            window_id = 0
            owner_pid = 0
        if window_id <= 0 or owner_pid <= 0:
            raise ResolveWindowNotReady(
                "DaVinci Resolve window PID/window ID is unavailable for focus-free Magic Mask input.",
                details={"window_rect": rect.as_payload(), "candidate": candidate},
            )
        self._resolve_window_id = window_id
        self._resolve_pid = owner_pid
        self._resolve_window_rect = rect
        self._resolve_window_name = str(candidate.get("name") or preferred_name or "")

    def _verify_resolve_window_onscreen(self, rect: Rect, *, ax_payload: dict[str, Any]) -> None:
        script = f"""
ObjC.import("CoreGraphics");
const target = {json.dumps(rect.as_payload())};
const list = $.CGWindowListCopyWindowInfo($.kCGWindowListOptionOnScreenOnly, $.kCGNullWindowID);
const count = list ? list.count : 0;
let candidates = [];
let matched = null;
function overlapRatio(a, b) {{
  const left = Math.max(a.x, b.x);
  const top = Math.max(a.y, b.y);
  const right = Math.min(a.x + a.width, b.x + b.width);
  const bottom = Math.min(a.y + a.height, b.y + b.height);
  const width = Math.max(0, right - left);
  const height = Math.max(0, bottom - top);
  const overlap = width * height;
  const targetArea = Math.max(1, a.width * a.height);
  return overlap / targetArea;
}}
for (let i = 0; i < count; i++) {{
  const raw = ObjC.deepUnwrap(list.objectAtIndex(i));
  const owner = String(raw.kCGWindowOwnerName || "");
  if (!owner.includes("Resolve") && !owner.includes("DaVinci")) continue;
  const bounds = raw.kCGWindowBounds || {{}};
  const candidate = {{
    owner,
    name: String(raw.kCGWindowName || ""),
    window_id: Number(raw.kCGWindowNumber || 0),
    owner_pid: Number(raw.kCGWindowOwnerPID || 0),
    alpha: Number(raw.kCGWindowAlpha || 0),
    layer: Number(raw.kCGWindowLayer || 0),
    bounds: {{
      x: Number(bounds.X || 0),
      y: Number(bounds.Y || 0),
      width: Number(bounds.Width || 0),
      height: Number(bounds.Height || 0),
    }},
  }};
  candidate.overlap_ratio = overlapRatio(target, candidate.bounds);
  candidates.push(candidate);
  if (
    candidate.alpha > 0 &&
    candidate.layer === 0 &&
    candidate.bounds.width >= 640 &&
    candidate.bounds.height >= 360 &&
    candidate.overlap_ratio >= 0.6
  ) {{
    matched = candidate;
    break;
  }}
}}
JSON.stringify({{ ok: matched !== null, matched, candidates: candidates.slice(0, 10) }});
"""
        proc = _run_osascript(script, language="JavaScript", timeout=5.0)
        if proc.returncode != 0:
            raise ResolveWindowNotReady(
                "Could not verify that the DaVinci Resolve window is visible on the current macOS Space.",
                details={"stderr": proc.stderr[-500:], "window_rect": rect.as_payload(), "ax_payload": ax_payload},
            )
        try:
            payload = json.loads(proc.stdout.strip())
        except json.JSONDecodeError as exc:
            raise ResolveWindowNotReady(
                "DaVinci Resolve on-screen window probe returned invalid data.",
                details={"stdout": proc.stdout[-500:], "window_rect": rect.as_payload(), "ax_payload": ax_payload},
            ) from exc
        if not payload.get("ok"):
            swift_payload = _swift_resolve_window_onscreen_probe(rect, expected_pid=getattr(self, "_resolve_pid", None))
            if swift_payload.get("ok"):
                return
            raise ResolveWindowNotReady(
                "DaVinci Resolve window is not visible on the current macOS Space; refusing GUI proof capture.",
                details={
                    "reason": "resolve_window_not_onscreen",
                    "window_rect": rect.as_payload(),
                    "ax_payload": ax_payload,
                    "onscreen_probe": payload,
                    "swift_onscreen_probe": swift_payload,
                },
            )

    def ensure_magic_mask_panel(self, mode: str) -> dict[str, Any]:
        if os.environ.get(PANEL_CHECK_BYPASS_ENV) == "1":
            return {"panel": "bypassed_by_env", "mode": mode}
        mode_label = str(mode).strip().title()
        labels = ["AI Magic Mask 2", "Magic Mask"]
        # `Magic Mask` is also a substring of the always-present palette
        # button description. Only the AI Magic Mask 2 panel heading or an
        # actual legacy Person/Object control proves that the panel is open.
        found = {"AI Magic Mask 2": self._accessibility_text_exists("AI Magic Mask 2"), "Magic Mask": False}
        mode_state: dict[str, Any] = {}
        if not found["AI Magic Mask 2"]:
            mode_state = self._accessibility_control_state(mode_label)
        opened = False
        if not found["AI Magic Mask 2"] and not mode_state.get("found"):
            opened = self._click_accessibility_description_exact("AI Magic Mask")
            if opened:
                time.sleep(0.4)
                found = {label: self._accessibility_text_exists(label) for label in labels}
                if not found.get("AI Magic Mask 2"):
                    mode_state = self._accessibility_control_state(mode_label)
        if not found.get("AI Magic Mask 2") and not mode_state.get("found"):
            raise MagicMaskPanelNotReady(
                "Open the DaVinci Resolve Color page Magic Mask panel before running this workflow.",
                details={"searched": labels, "found": found},
            )

        # DaVinci Resolve 21 exposes the unified AI Magic Mask 2 panel. It no
        # longer has separate Person/Object controls: the positive input tells
        # the model which person or object to select. Preserve the public mode
        # intent in the result while proving the unified panel identity.
        if found.get("AI Magic Mask 2") and not mode_state.get("found"):
            return {
                "panel": "AI Magic Mask 2",
                "mode": mode,
                "mode_selected": {
                    "found": False,
                    "selected": True,
                    "enabled": True,
                    "selection_model": "unified_ai_magic_mask_2",
                    "requested_mode": mode,
                    "verified_by": "panel_heading",
                },
                "mode_clicked": False,
                "found": found,
                "opened_by_route": opened,
            }

        mode_clicked = False
        if mode_state.get("found") and mode_state.get("enabled") and not mode_state.get("selected"):
            mode_clicked = self._click_accessibility_label(mode_label)
            time.sleep(0.25)
            mode_state = self._accessibility_control_state(mode_label)
        if not mode_state.get("found") or not mode_state.get("enabled") or not mode_state.get("selected"):
            raise MagicMaskPanelNotReady(
                "DaVinci Resolve Magic Mask mode could not be selected and read back.",
                details={"requested_mode": mode, "control_label": mode_label, "control_state": mode_state},
            )
        return {
            "panel": "Magic Mask",
            "mode": mode,
            "mode_selected": mode_state,
            "mode_clicked": mode_clicked,
            "found": found,
            "opened_by_route": opened,
        }

    def prepare_paint_stroke(self) -> dict[str, Any]:
        state = self._accessibility_control_state("Add Paint Stroke")
        clicked = False
        if state.get("found") and state.get("enabled") and not state.get("selected"):
            clicked = self._click_accessibility_description_exact("Add Paint Stroke")
            time.sleep(0.25)
            state = self._accessibility_control_state("Add Paint Stroke")
        if state.get("found") and state.get("enabled") and not state.get("selected"):
            position = state.get("position")
            size = state.get("size")
            if isinstance(position, list) and len(position) >= 2 and isinstance(size, list) and len(size) >= 2:
                center = (
                    int(round(float(position[0]) + float(size[0]) / 2.0)),
                    int(round(float(position[1]) + float(size[1]) / 2.0)),
                )
                _post_mouse_drag(
                    [center, center],
                    target_pid=self._focus_free_target_pid(),
                    target_window_id=self._focus_free_target_window_id(),
                    target_window_rect=self._focus_free_target_window_rect(),
                )
                clicked = True
                time.sleep(0.25)
                state = self._accessibility_control_state("Add Paint Stroke")
        if state.get("found") and state.get("enabled") and state.get("selected"):
            self._magic_mask_input_mode = "paint_stroke"
            return {"control": "Add Paint Stroke", "selected": True, "clicked": clicked, "input_mode": "paint_stroke"}

        add_click = self._accessibility_control_state("Add Click")
        if not add_click.get("selected"):
            self._click_accessibility_description_exact("Add Click")
            time.sleep(0.2)
            add_click = self._accessibility_control_state("Add Click")
        if not add_click.get("found") or not add_click.get("selected"):
            raise MagicMaskPanelNotReady(
                "Magic Mask positive input mode could not be selected before drawing.",
                details={"paint_stroke": state, "add_click": add_click},
            )
        self._magic_mask_input_mode = "add_click"
        return {
            "control": "Add Click",
            "selected": True,
            "clicked": False,
            "input_mode": "add_click",
            "paint_stroke_unavailable": not bool(state.get("enabled")),
        }

    def capture_viewer_geometry(self, window_rect: Rect, *, frame_aspect: float | None = None) -> Rect:
        override = os.environ.get(VIEWER_RECT_ENV)
        if override:
            return _parse_rect_env(override)

        if window_rect.width < 640 or window_rect.height < 360:
            raise ViewerGeometryNotFound(
                "DaVinci Resolve window is too small to infer Color page viewer geometry.",
                details={"window_rect": window_rect.as_payload()},
            )

        # DaVinci Resolve exposes no stable public viewer-rect API. This
        # conservative Color-page geometry is proof-gated and can be overridden
        # with CUTAGENT_MAGIC_MASK_VIEWER_RECT in packaged/live environments.
        inferred = Rect(
            x=int(round(window_rect.x + window_rect.width * 0.333)),
            y=int(round(window_rect.y + window_rect.height * 0.094)),
            width=int(round(window_rect.width * 0.334)),
            height=int(round(window_rect.height * 0.331)),
        )
        if frame_aspect is None or not math.isfinite(frame_aspect) or frame_aspect <= 0:
            return inferred
        viewer_aspect = inferred.width / max(1, inferred.height)
        if viewer_aspect > frame_aspect:
            content_width = max(1, int(round(inferred.height * frame_aspect)))
            return Rect(
                x=inferred.x + (inferred.width - content_width) // 2,
                y=inferred.y,
                width=content_width,
                height=inferred.height,
            )
        content_height = max(1, int(round(inferred.width / frame_aspect)))
        return Rect(
            x=inferred.x,
            y=inferred.y + (inferred.height - content_height) // 2,
            width=inferred.width,
            height=content_height,
        )

    def draw_stroke(self, points: list[tuple[int, int]]) -> dict[str, Any]:
        try:
            input_mode = getattr(self, "_magic_mask_input_mode", "paint_stroke")
            if input_mode == "add_click":
                for point in points:
                    _post_mouse_drag(
                        [point, point],
                        target_pid=self._focus_free_target_pid(),
                        target_window_id=self._focus_free_target_window_id(),
                        target_window_rect=self._focus_free_target_window_rect(),
                    )
                    time.sleep(0.12)
            else:
                _post_mouse_drag(
                    points,
                    target_pid=self._focus_free_target_pid(),
                    target_window_id=self._focus_free_target_window_id(),
                    target_window_rect=self._focus_free_target_window_rect(),
                )
        except Exception as exc:
            raise StrokeMappingFailed(
                "Failed to draw Magic Mask stroke through macOS event posting.",
                details={"points": points, "error": str(exc)},
            ) from exc
        return {
            "input_mode": getattr(self, "_magic_mask_input_mode", "paint_stroke"),
            "point_count": len(points),
            "first_point": list(points[0]),
            "last_point": list(points[-1]),
        }

    def track_magic_mask(self) -> dict[str, Any]:
        if self._click_accessibility_description_exact("Track Forward and Reverse"):
            completion = self._wait_for_tracking_completion()
            return {"track_clicked": True, "direction": "forward_and_reverse", **completion}
        if self._click_accessibility_description_exact("Track Forward"):
            completion = self._wait_for_tracking_completion()
            return {"track_clicked": True, "direction": "forward", **completion}
        raise MagicMaskTrackFailed(
            "Magic Mask tracking button was not found.",
            details={"searched": ["Track Forward and Reverse", "Track Forward"], "target_application": self.process_name, "target_process_names": self._process_names_payload()},
        )

    def _wait_for_tracking_completion(self, *, timeout_seconds: float = 180.0) -> dict[str, Any]:
        started_at = time.monotonic()
        appearance_deadline = started_at + 3.0
        deadline = started_at + timeout_seconds
        observed_running = False
        while time.monotonic() < deadline:
            running = self._accessibility_text_exists("AI Magic Mask Tracking")
            if running:
                observed_running = True
            elif observed_running:
                return {
                    "tracking_completed": True,
                    "tracking_dialog_observed": True,
                    "tracking_duration_ms": int(round((time.monotonic() - started_at) * 1000)),
                }
            elif time.monotonic() >= appearance_deadline:
                # Some Qt modal dialogs are visible to native accessibility but
                # not to System Events. Proof export below remains the final
                # readiness gate in that case.
                return {
                    "tracking_completed": None,
                    "tracking_dialog_observed": False,
                    "tracking_duration_ms": int(round((time.monotonic() - started_at) * 1000)),
                }
            time.sleep(0.25)
        raise MagicMaskTrackFailed(
            "Magic Mask tracking did not finish before the timeout.",
            details={
                "timeout_seconds": timeout_seconds,
                "tracking_dialog_observed": observed_running,
            },
        )

    def capture_screenshot(self, rect: Rect, path: Path) -> dict[str, Any]:
        path.parent.mkdir(parents=True, exist_ok=True)
        window_id = int(getattr(self, "_resolve_window_id", 0) or 0)
        if window_id <= 0:
            raise MagicMaskProofFailed(
                "Focus-free Magic Mask proof capture requires a verified DaVinci Resolve window ID.",
                details={"viewer_rect": rect.as_payload(), "window_id": window_id},
            )
        proc = subprocess.run(
            ["screencapture", "-x", "-o", "-t", "png", "-l", str(window_id), str(path)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if proc.returncode != 0 or not path.is_file():
            raise MagicMaskProofFailed(
                "Failed to capture Magic Mask proof screenshot.",
                details={"screenshot_path": str(path), "viewer_rect": rect.as_payload(), "stderr": proc.stderr[-500:]},
            )
        return {
            "screenshot_path": str(path),
            "bytes": path.stat().st_size,
            "capture_scope": "resolve_window",
            "window_id": window_id,
        }

    def _focus_free_target_pid(self) -> int:
        pid = int(getattr(self, "_resolve_pid", 0) or 0)
        if pid <= 0:
            raise ResolveWindowNotReady(
                "Focus-free Magic Mask input requires a verified DaVinci Resolve process ID.",
                details={"target_application": self.process_name},
            )
        return pid

    def _focus_free_target_window_id(self) -> int:
        window_id = int(getattr(self, "_resolve_window_id", 0) or 0)
        if window_id <= 0:
            raise ResolveWindowNotReady(
                "Focus-free Magic Mask input requires a verified DaVinci Resolve window ID.",
                details={"target_application": self.process_name},
            )
        return window_id

    def _focus_free_target_window_rect(self) -> Rect:
        rect = getattr(self, "_resolve_window_rect", None)
        if not isinstance(rect, Rect):
            raise ResolveWindowNotReady(
                "Focus-free Magic Mask input requires verified DaVinci Resolve window geometry.",
                details={"target_application": self.process_name},
            )
        return rect

    def _focus_free_target_window_name(self) -> str:
        name = str(getattr(self, "_resolve_window_name", "") or "").strip()
        if not name:
            raise ResolveWindowNotReady(
                "Focus-free Magic Mask input requires a verified DaVinci Resolve window name.",
                details={"target_application": self.process_name},
            )
        return name

    def _focus_free_ax_window_target(self) -> dict[str, Any]:
        rect = self._focus_free_target_window_rect()
        return {
            "pid": self._focus_free_target_pid(),
            "name": self._focus_free_target_window_name(),
            "x": rect.x,
            "y": rect.y,
            "width": rect.width,
            "height": rect.height,
        }

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

    def _accessibility_text_exists(self, needle: str) -> bool:
        target_window = self._focus_free_ax_window_target()
        script = f"""
const needle = {json.dumps(str(needle).lower())};
const se = Application("System Events");
const targetWindow = {json.dumps(target_window)};
const matches = se.applicationProcesses.whose({{ unixId: targetWindow.pid }})();
if (matches.length === 0) false;
else {{
  const roots = matches[0].windows().filter(win => {{
    try {{
      const position = win.position(); const size = win.size();
      return String(win.name() || "") === targetWindow.name &&
        Math.abs(Number(position[0]) - targetWindow.x) <= 3 && Math.abs(Number(position[1]) - targetWindow.y) <= 3 &&
        Math.abs(Number(size[0]) - targetWindow.width) <= 3 && Math.abs(Number(size[1]) - targetWindow.height) <= 3;
    }} catch (e) {{ return false; }}
  }});
  const queue = roots.length === 1 ? [roots[0]] : [];
  let scanned = 0;
  let found = false;
  while (queue.length && scanned < 1500 && !found) {{
    const item = queue.shift();
    scanned += 1;
    for (const getter of ["name", "description", "value"]) {{
      try {{
        const value = item[getter]();
        if (String(value || "").toLowerCase().includes(needle)) {{
          found = true;
          break;
        }}
      }} catch (e) {{}}
    }}
    try {{
      const children = item.uiElements();
      for (let i = 0; i < children.length; i++) queue.push(children[i]);
    }} catch (e) {{}}
  }}
  found;
}}
"""
        proc = _run_osascript(script, language="JavaScript", timeout=8.0)
        return proc.returncode == 0 and proc.stdout.strip().lower() == "true"

    def _accessibility_control_state(self, description: str) -> dict[str, Any]:
        target_window = self._focus_free_ax_window_target()
        script = f"""
const target = {json.dumps(str(description))};
const se = Application("System Events");
const targetWindow = {json.dumps(target_window)};
const matches = se.applicationProcesses.whose({{ unixId: targetWindow.pid }})();
let result = {{ found: false, selected: false, enabled: false, position: null, size: null }};
if (matches.length > 0) {{
  const roots = matches[0].windows().filter(win => {{
    try {{
      const position = win.position(); const size = win.size();
      return String(win.name() || "") === targetWindow.name &&
        Math.abs(Number(position[0]) - targetWindow.x) <= 3 && Math.abs(Number(position[1]) - targetWindow.y) <= 3 &&
        Math.abs(Number(size[0]) - targetWindow.width) <= 3 && Math.abs(Number(size[1]) - targetWindow.height) <= 3;
    }} catch (e) {{ return false; }}
  }});
  const queue = roots.length === 1 ? [roots[0]] : [];
  let scanned = 0;
  while (queue.length && scanned < 1800 && !result.found) {{
    const item = queue.shift();
    scanned += 1;
    let role = "";
    let desc = ""; let name = ""; let valueText = "";
    try {{ role = String(item.role() || ""); }} catch (e) {{}}
    try {{ desc = String(item.description() || ""); }} catch (e) {{}}
    try {{ name = String(item.name() || ""); }} catch (e) {{}}
    try {{ valueText = String(item.value() || ""); }} catch (e) {{}}
    if ((role === "AXCheckBox" || role === "AXButton" || role === "AXRadioButton") && [desc, name, valueText].includes(target)) {{
      let value = false;
      let enabled = false;
      let position = null;
      let size = null;
      try {{
        const rawValue = item.value();
        const normalizedValue = String(rawValue || "").toLowerCase();
        value = rawValue === true || Number(rawValue) === 1 || normalizedValue === "selected" || normalizedValue === "on";
      }} catch (e) {{}}
      try {{ enabled = Boolean(item.enabled()); }} catch (e) {{}}
      try {{ position = item.position(); }} catch (e) {{}}
      try {{ size = item.size(); }} catch (e) {{}}
      result = {{ found: true, selected: value, enabled, position, size }};
      break;
    }}
    try {{
      const children = item.uiElements();
      for (let i = 0; i < children.length; i++) queue.push(children[i]);
    }} catch (e) {{}}
  }}
}}
JSON.stringify(result);
"""
        proc = _run_osascript(script, language="JavaScript", timeout=20.0)
        if proc.returncode != 0:
            return {"found": False, "selected": False, "enabled": False, "stderr": proc.stderr[-500:]}
        try:
            payload = json.loads(proc.stdout.strip())
        except json.JSONDecodeError:
            return {"found": False, "selected": False, "enabled": False, "stdout": proc.stdout[-500:]}
        return payload if isinstance(payload, dict) else {"found": False, "selected": False, "enabled": False}

    def _click_accessibility_description_exact(self, description: str) -> bool:
        target_window = self._focus_free_ax_window_target()
        script = f"""
const target = {json.dumps(str(description))};
const se = Application("System Events");
const targetWindow = {json.dumps(target_window)};
const matches = se.applicationProcesses.whose({{ unixId: targetWindow.pid }})();
let clicked = false;
if (matches.length > 0) {{
  const roots = matches[0].windows().filter(win => {{
    try {{
      const position = win.position(); const size = win.size();
      return String(win.name() || "") === targetWindow.name &&
        Math.abs(Number(position[0]) - targetWindow.x) <= 3 && Math.abs(Number(position[1]) - targetWindow.y) <= 3 &&
        Math.abs(Number(size[0]) - targetWindow.width) <= 3 && Math.abs(Number(size[1]) - targetWindow.height) <= 3;
    }} catch (e) {{ return false; }}
  }});
  const queue = roots.length === 1 ? [roots[0]] : [];
  let scanned = 0;
  while (queue.length && scanned < 1800 && !clicked) {{
    const item = queue.shift();
    scanned += 1;
    let role = "";
    let desc = "";
    try {{ role = String(item.role() || ""); }} catch (e) {{}}
    try {{ desc = String(item.description() || ""); }} catch (e) {{}}
    if ((role === "AXCheckBox" || role === "AXButton") && desc === target) {{
      try {{ item.click(); clicked = true; break; }} catch (e) {{}}
    }}
    try {{
      const children = item.uiElements();
      for (let i = 0; i < children.length; i++) queue.push(children[i]);
    }} catch (e) {{}}
  }}
}}
clicked;
"""
        proc = _run_osascript(script, language="JavaScript", timeout=8.0)
        return proc.returncode == 0 and proc.stdout.strip().lower() == "true"

    def _click_accessibility_label(self, label: str) -> bool:
        target_window = self._focus_free_ax_window_target()
        script = f"""
const needle = {json.dumps(str(label).lower())};
const se = Application("System Events");
const targetWindow = {json.dumps(target_window)};
const matches = se.applicationProcesses.whose({{ unixId: targetWindow.pid }})();
let clicked = false;
if (matches.length > 0) {{
  const roots = matches[0].windows().filter(win => {{
    try {{
      const position = win.position(); const size = win.size();
      return String(win.name() || "") === targetWindow.name &&
        Math.abs(Number(position[0]) - targetWindow.x) <= 3 && Math.abs(Number(position[1]) - targetWindow.y) <= 3 &&
        Math.abs(Number(size[0]) - targetWindow.width) <= 3 && Math.abs(Number(size[1]) - targetWindow.height) <= 3;
    }} catch (e) {{ return false; }}
  }});
  const queue = roots.length === 1 ? [roots[0]] : [];
  let scanned = 0;
  while (queue.length && scanned < 1500 && !clicked) {{
    const item = queue.shift();
    scanned += 1;
    let text = "";
    for (const getter of ["name", "description", "value"]) {{
      try {{ text += " " + String(item[getter]() || ""); }} catch (e) {{}}
    }}
    if (text.toLowerCase().includes(needle)) {{
      try {{
        item.click();
        clicked = true;
        break;
      }} catch (e) {{}}
    }}
    try {{
      const children = item.uiElements();
      for (let i = 0; i < children.length; i++) queue.push(children[i]);
    }} catch (e) {{}}
  }}
}}
clicked;
"""
        proc = _run_osascript(script, language="JavaScript", timeout=8.0)
        return proc.returncode == 0 and proc.stdout.strip().lower() == "true"


def _post_mouse_drag(
    points: list[tuple[int, int]],
    *,
    target_pid: int,
    target_window_id: int,
    target_window_rect: Rect,
    delay_seconds: float = 0.025,
    mouse_button: str = "left",
    deactivate_after: bool = True,
) -> None:
    if not points:
        raise StrokeMappingFailed("Cannot draw an empty stroke.", details={"points": points})

    app_services = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices")
    objc = ctypes.cdll.LoadLibrary("/usr/lib/libobjc.A.dylib")
    ctypes.cdll.LoadLibrary("/System/Library/Frameworks/AppKit.framework/AppKit")

    class CGPoint(ctypes.Structure):
        _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]

    objc.objc_getClass.restype = ctypes.c_void_p
    objc.objc_getClass.argtypes = [ctypes.c_char_p]
    objc.sel_registerName.restype = ctypes.c_void_p
    objc.sel_registerName.argtypes = [ctypes.c_char_p]
    app_services.CGEventPostToPid.argtypes = [ctypes.c_int32, ctypes.c_void_p]
    app_services.CGEventSetLocation.argtypes = [ctypes.c_void_p, CGPoint]
    app_services.CGEventSetWindowLocation.argtypes = [ctypes.c_void_p, CGPoint]
    app_services.CGEventSetIntegerValueField.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int64]

    if int(target_pid) <= 0 or int(target_window_id) <= 0:
        raise StrokeMappingFailed(
            "Cannot post Magic Mask input without a verified DaVinci Resolve PID and window ID."
        )

    ns_event_class = objc.objc_getClass(b"NSEvent")
    if not ns_event_class:
        raise StrokeMappingFailed("macOS NSEvent is unavailable for focus-free Magic Mask input.")

    event_to_cg_event = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)(
        ("objc_msgSend", objc)
    )
    mouse_event_message = ctypes.CFUNCTYPE(
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_ulong,
        CGPoint,
        ctypes.c_ulonglong,
        ctypes.c_double,
        ctypes.c_longlong,
        ctypes.c_void_p,
        ctypes.c_longlong,
        ctypes.c_longlong,
        ctypes.c_float,
    )(("objc_msgSend", objc))
    app_focus_event_message = ctypes.CFUNCTYPE(
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_ulong,
        CGPoint,
        ctypes.c_ulonglong,
        ctypes.c_double,
        ctypes.c_longlong,
        ctypes.c_void_p,
        ctypes.c_short,
        ctypes.c_longlong,
        ctypes.c_longlong,
    )(("objc_msgSend", objc))
    cg_event_selector = objc.sel_registerName(b"CGEvent")
    mouse_event_selector = objc.sel_registerName(
        b"mouseEventWithType:location:modifierFlags:timestamp:windowNumber:context:eventNumber:clickCount:pressure:"
    )
    focus_event_selector = objc.sel_registerName(
        b"otherEventWithType:location:modifierFlags:timestamp:windowNumber:context:subtype:data1:data2:"
    )

    def decorate(cg_event: int, point: tuple[int, int], *, button_number: int = 0) -> None:
        screen_point = CGPoint(float(point[0]), float(point[1]))
        window_point = CGPoint(
            float(point[0] - target_window_rect.x),
            float(point[1] - target_window_rect.y),
        )
        app_services.CGEventSetLocation(cg_event, screen_point)
        # Qt requires the window-local location as well as the process/window
        # identity. This targets DaVinci Resolve without moving the real cursor
        # or changing the system-frontmost application.
        app_services.CGEventSetWindowLocation(cg_event, window_point)
        for field, value in (
            (3, button_number),
            (7, 3),
            (91, int(target_window_id)),
            (92, int(target_window_id)),
        ):
            app_services.CGEventSetIntegerValueField(cg_event, field, value)

    def post_focus_state(active: bool, point: tuple[int, int]) -> None:
        # AppKit-defined activate/deactivate events affect only the target
        # process' synthetic focus state. They deliberately do not call an
        # application activation API and cannot steal the user's foreground.
        ns_event = app_focus_event_message(
            ns_event_class,
            focus_event_selector,
            13,
            CGPoint(float(point[0]), float(point[1])),
            0xC0000,
            0.0,
            int(target_window_id),
            None,
            1 if active else 2,
            0,
            0,
        )
        if not ns_event:
            raise StrokeMappingFailed("macOS failed to create a focus-free application-state event.")
        cg_event = event_to_cg_event(ns_event, cg_event_selector)
        if not cg_event:
            raise StrokeMappingFailed("macOS failed to convert the application-state event.")
        decorate(cg_event, point)
        app_services.CGEventPostToPid(int(target_pid), cg_event)
        time.sleep(delay_seconds)

    def post_window_key_state(active: bool) -> None:
        # Computer Use also tells the target process that key-window focus was
        # synthetically returned/removed. Qt needs this in addition to the
        # application-state event for canvas gestures and context menus, but it
        # still does not activate the application at the Workspace level.
        ns_event = app_focus_event_message(
            ns_event_class,
            focus_event_selector,
            21,
            CGPoint(0.0, 0.0),
            0,
            0.0,
            0,
            None,
            -32768 if active else 16384,
            0,
            0,
        )
        if not ns_event:
            raise StrokeMappingFailed("macOS failed to create a focus-free key-window event.")
        cg_event = event_to_cg_event(ns_event, cg_event_selector)
        if not cg_event:
            raise StrokeMappingFailed("macOS failed to convert the key-window event.")
        app_services.CGEventPostToPid(int(target_pid), cg_event)
        time.sleep(delay_seconds)

    event_number = 0

    def post(event_type: int, point: tuple[int, int], *, button_number: int = 0) -> None:
        nonlocal event_number
        event_number += 1
        ns_event = mouse_event_message(
            ns_event_class,
            mouse_event_selector,
            event_type,
            CGPoint(float(point[0]), float(point[1])),
            0,
            0.0,
            int(target_window_id),
            None,
            event_number,
            1,
            1.0,
        )
        if not ns_event:
            raise StrokeMappingFailed("macOS failed to create mouse event.", details={"event_type": event_type, "point": point})
        cg_event = event_to_cg_event(ns_event, cg_event_selector)
        if not cg_event:
            raise StrokeMappingFailed("macOS failed to convert mouse event.", details={"event_type": event_type, "point": point})
        decorate(cg_event, point, button_number=button_number)
        app_services.CGEventPostToPid(int(target_pid), cg_event)
        time.sleep(delay_seconds)

    button = mouse_button.strip().lower()
    if button not in {"left", "right"}:
        raise StrokeMappingFailed(
            "Focus-free mouse input only supports left or right mouse buttons.",
            details={"mouse_button": mouse_button},
        )
    down_type, dragged_type, up_type, button_number = (1, 6, 2, 0) if button == "left" else (3, 7, 4, 1)

    post_focus_state(True, points[0])
    post_window_key_state(True)
    try:
        post(5, points[0])
        post(down_type, points[0], button_number=button_number)
        for point in points[1:]:
            post(dragged_type, point, button_number=button_number)
        post(up_type, points[-1], button_number=button_number)
    finally:
        if deactivate_after:
            post_window_key_state(False)
            post_focus_state(False, points[-1])


def _ensure_color_page(conn: Any) -> dict[str, Any]:
    resolve = getattr(conn, "resolve", None)
    if resolve is None:
        raise ColorPageNotReady(
            "DaVinci Resolve connection does not expose a resolve object for page switching.",
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
            raise ColorPageNotReady(
                "Failed to switch DaVinci Resolve to the Color page.",
                details={"current_page": current, "required_page": "color", "error": str(exc)},
            ) from exc
        if opened is False:
            raise ColorPageNotReady(
                "DaVinci Resolve refused to switch to the Color page.",
                details={"current_page": current, "required_page": "color", "api_result": opened},
            )
    try:
        final = resolve.GetCurrentPage()
    except Exception:
        final = "color"
    if final != "color":
        raise ColorPageNotReady(
            "DaVinci Resolve is not on the Color page after page switch.",
            details={"current_page": final, "required_page": "color"},
        )
    return {"required_page": "color", "previous_page": current, "current_page": final}


def _timeline_item_name(item: Any) -> str | None:
    try:
        value = item.GetName()
    except Exception:
        return None
    normalized = str(value or "").strip()
    return normalized or None


def _timeline_item_frame(item: Any, getter_name: str) -> int | None:
    getter = getattr(item, getter_name, None)
    if not callable(getter):
        return None
    try:
        return int(getter())
    except Exception:
        return None


def _timeline_item_media_id(item: Any) -> str | None:
    media_pool_item_getter = getattr(item, "GetMediaPoolItem", None)
    try:
        media_pool_item = media_pool_item_getter() if callable(media_pool_item_getter) else None
    except Exception:
        media_pool_item = None
    media_id_getter = getattr(media_pool_item, "GetMediaId", None) if media_pool_item is not None else None
    try:
        media_id = str(media_id_getter() or "").strip() if callable(media_id_getter) else ""
    except Exception:
        media_id = ""
    return media_id or None


def _timeline_item_unique_id(item: Any) -> str | None:
    for getter_name in ("GetUniqueId", "GetUniqueID"):
        getter = getattr(item, getter_name, None)
        try:
            value = str(getter() or "").strip() if callable(getter) else ""
        except Exception:
            value = ""
        if value:
            return value
    return None


def _timeline_item_proxy_matches(left: Any, right: Any) -> bool:
    if left is right:
        return True
    left_unique_id = _timeline_item_unique_id(left)
    right_unique_id = _timeline_item_unique_id(right)
    if left_unique_id and right_unique_id:
        return left_unique_id == right_unique_id
    left_media_id = _timeline_item_media_id(left)
    right_media_id = _timeline_item_media_id(right)
    return bool(
        left_media_id
        and right_media_id
        and left_media_id == right_media_id
        and _timeline_item_name(left) == _timeline_item_name(right)
        and _timeline_item_frame(left, "GetStart") == _timeline_item_frame(right, "GetStart")
        and _timeline_item_frame(left, "GetEnd") == _timeline_item_frame(right, "GetEnd")
    )


def _timeline_item_track(conn: Any, item: Any) -> int | None:
    timeline = getattr(conn, "timeline", None)
    if timeline is None or item is None:
        return None
    try:
        track_count = int(timeline.GetTrackCount("video") or 0)
    except Exception:
        return None
    matches: list[int] = []
    for track_index in range(1, track_count + 1):
        try:
            items = timeline.GetItemListInTrack("video", track_index) or []
        except Exception:
            continue
        if any(_timeline_item_proxy_matches(candidate, item) for candidate in items):
            matches.append(track_index)
    return matches[0] if len(matches) == 1 else None


def _same_timeline_item(conn: Any, left: Any, right: Any) -> bool:
    if left is None or right is None:
        return False
    if left is right:
        return True
    left_unique_id = _timeline_item_unique_id(left)
    right_unique_id = _timeline_item_unique_id(right)
    if left_unique_id and right_unique_id and left_unique_id != right_unique_id:
        return False
    left_track = _timeline_item_track(conn, left)
    right_track = _timeline_item_track(conn, right)
    if left_track is None or right_track is None or left_track != right_track:
        return False
    left_media_id = _timeline_item_media_id(left)
    right_media_id = _timeline_item_media_id(right)
    if left_media_id and right_media_id and left_media_id != right_media_id:
        return False
    comparable = [
        (_timeline_item_name(left), _timeline_item_name(right)),
        (_timeline_item_frame(left, "GetStart"), _timeline_item_frame(right, "GetStart")),
        (_timeline_item_frame(left, "GetEnd"), _timeline_item_frame(right, "GetEnd")),
    ]
    populated = [(a, b) for a, b in comparable if a is not None and b is not None]
    return bool(populated) and all(a == b for a, b in populated)


def _resolve_unique_video_item(conn: Any, clip_name: str) -> tuple[Any, dict[str, Any]]:
    timeline = getattr(conn, "timeline", None)
    if timeline is None:
        raise MagicMaskProofFailed(
            "Magic Mask requires an active timeline before clip targeting.",
            details={"clip": clip_name, "reason": "timeline_unavailable"},
        )
    query = str(clip_name or "").strip()
    query_lower = query.lower()
    query_basename_lower = Path(query).name.lower()
    matches: list[tuple[Any, dict[str, Any]]] = []
    try:
        track_count = int(timeline.GetTrackCount("video") or 0)
    except Exception:
        track_count = 0
    for track_index in range(1, track_count + 1):
        try:
            items = timeline.GetItemListInTrack("video", track_index) or []
        except Exception:
            continue
        for item in items:
            names = clip_ops._item_name_candidates(item)
            lowered = {value.lower() for value in names}
            if query not in names and query_lower not in lowered and query_basename_lower not in lowered:
                continue
            start = _timeline_item_frame(item, "GetStart")
            end = _timeline_item_frame(item, "GetEnd")
            if start is None or end is None or end <= start:
                continue
            matches.append(
                (
                    item,
                    {
                        "track_type": "video",
                        "track": track_index,
                        "record_frame": start + max(0, (end - start - 1) // 2),
                        "start_frame": start,
                        "end_frame": end,
                        "media_id": _timeline_item_media_id(item),
                    },
                )
            )
    if len(matches) != 1:
        raise MagicMaskProofFailed(
            "Magic Mask clip targeting is ambiguous; use a unique timeline clip name before drawing a stroke.",
            details={
                "clip": clip_name,
                "reason": "timeline_clip_identity_ambiguous" if matches else "timeline_clip_not_found",
                "match_count": len(matches),
                "matches": [locator for _item, locator in matches],
            },
        )
    return matches[0]


def _current_video_item(conn: Any) -> Any | None:
    timeline = getattr(conn, "timeline", None)
    getter = getattr(timeline, "GetCurrentVideoItem", None)
    if callable(getter):
        try:
            current = getter()
            if current:
                return current
        except Exception:
            pass
    return getattr(conn, "item", None)


def _activate_clip_context(conn: Any, clip_name: str) -> dict[str, Any]:
    item, locator = _resolve_unique_video_item(conn, clip_name)
    readback_name = _timeline_item_name(item) or clip_name
    current = _current_video_item(conn)
    if _same_timeline_item(conn, current, item):
        return {
            "clip": clip_name,
            "clip_readback": readback_name,
            "target_locator": locator,
            "_item": item,
            "target_activation": {"status": "already_active", "verified": True},
        }

    timeline = getattr(conn, "timeline", None)
    setter = getattr(timeline, "SetCurrentTimecode", None)
    start = _timeline_item_frame(item, "GetStart")
    end = _timeline_item_frame(item, "GetEnd")
    if not callable(setter) or start is None or end is None or end <= start:
        raise MagicMaskProofFailed(
            "Magic Mask could not activate and verify the requested timeline clip.",
            details={
                "clip": clip_name,
                "clip_readback": readback_name,
                "reason": "missing_target_activation_contract",
                "item_start": start,
                "item_end": end,
                "has_timecode_setter": callable(setter),
            },
        )

    fps = float(getattr(conn, "fps", 24.0) or 24.0)
    midpoint = int(locator["record_frame"])
    attempts: list[dict[str, Any]] = []
    for frame in (midpoint,):
        timecode = frames_to_timecode(frame, fps)
        try:
            api_result = setter(timecode)
        except Exception as exc:
            attempts.append({"frame": frame, "timecode": timecode, "error": str(exc)})
            continue
        deadline = time.monotonic() + 1.5
        active = _current_video_item(conn)
        while not _same_timeline_item(conn, active, item) and time.monotonic() < deadline:
            time.sleep(0.05)
            active = _current_video_item(conn)
        verified = _same_timeline_item(conn, active, item)
        attempts.append(
            {
                "frame": frame,
                "timecode": timecode,
                "api_result": api_result,
                "verified": verified,
                "current_clip": _timeline_item_name(active),
            }
        )
        if verified:
            return {
                "clip": clip_name,
                "clip_readback": readback_name,
                "target_locator": locator,
                "_item": item,
                "target_activation": {"status": "activated", "verified": True, "attempts": attempts},
            }

    raise MagicMaskProofFailed(
        "Magic Mask could not activate the requested clip before drawing the GUI stroke.",
        details={"clip": clip_name, "clip_readback": readback_name, "attempts": attempts},
    )


def _verify_exact_clip_context(conn: Any, context: dict[str, Any]) -> dict[str, Any]:
    item = context.get("_item")
    locator = context.get("target_locator")
    if item is None or not isinstance(locator, dict):
        raise MagicMaskProofFailed(
            "Magic Mask lost the exact target clip identity before proof capture.",
            details={"reason": "target_locator_missing"},
        )
    try:
        locator_item = clip_ops.find_item_by_track_record(conn, int(locator["track"]), int(locator["record_frame"]))
    except Exception as exc:
        raise MagicMaskProofFailed(
            "Magic Mask could not re-resolve the exact target clip after GUI input.",
            details={"reason": "target_locator_readback_failed", "target_locator": locator, "error": str(exc)},
        ) from exc
    current = _current_video_item(conn)
    locator_verified = _same_timeline_item(conn, locator_item, item)
    current_verified = _same_timeline_item(conn, current, item)
    if not locator_verified or not current_verified:
        raise MagicMaskProofFailed(
            "Magic Mask target clip identity changed during GUI input.",
            details={
                "reason": "target_identity_changed",
                "target_locator": locator,
                "locator_verified": locator_verified,
                "current_verified": current_verified,
                "current_clip": _timeline_item_name(current),
            },
        )
    return {
        "status": "verified",
        "target_locator": locator,
        "locator_verified": True,
        "current_item_verified": True,
    }


def _proof_paths(proof_dir: Path, clip_name: str) -> MagicMaskProofPaths:
    safe_clip = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in clip_name).strip("_") or "clip"
    stamp = time.strftime("%Y%m%d-%H%M%S")
    return MagicMaskProofPaths(
        screenshot_path=proof_dir / f"{safe_clip}-magic-mask-{stamp}-viewer.png",
        export_path=proof_dir / f"{safe_clip}-magic-mask-{stamp}-export.png",
    )


def _timeline_frame_aspect(conn: Any) -> float | None:
    timeline = getattr(conn, "timeline", None)
    getter = getattr(timeline, "GetSetting", None)
    if not callable(getter):
        return None
    try:
        width = float(getter("timelineResolutionWidth") or 0)
        height = float(getter("timelineResolutionHeight") or 0)
    except (TypeError, ValueError):
        return None
    if width <= 0 or height <= 0:
        return None
    return width / height


def _export_proof_when_ready(
    proof_exporter: ProofExporter,
    path: Path,
    *,
    track_requested: bool,
    timeout_seconds: float = 180.0,
) -> tuple[dict[str, Any], dict[str, Any]]:
    started_at = time.monotonic()
    deadline = started_at + timeout_seconds
    attempts = 0
    while True:
        attempts += 1
        try:
            state = proof_exporter(path)
            return state, {
                "export_ready": True,
                "export_attempts": attempts,
                "export_wait_ms": int(round((time.monotonic() - started_at) * 1000)),
            }
        except APICallFailed as exc:
            retryable_tracking_export = (
                track_requested
                and exc.details.get("api_call") == "Project.ExportCurrentFrameAsStill"
                and exc.details.get("api_result") is None
                and time.monotonic() < deadline
            )
            if not retryable_tracking_export:
                raise
            time.sleep(0.75)


def run_magic_mask_draw_stroke(
    conn: Any,
    *,
    clip_name: str,
    mode: str,
    stroke_points: list[tuple[float, float]],
    track_requested: bool,
    proof_exporter: ProofExporter,
    proof_dir: Path | None = None,
    driver: MacOSMagicMaskGuiDriver | None = None,
) -> dict[str, Any]:
    normalized_clip = validate_clip_target(clip_name)
    normalized_mode = normalize_magic_mask_mode(mode)
    if len(stroke_points) < 2:
        raise ValidationError(
            "Magic Mask stroke requires at least two points.",
            details={"point_count": len(stroke_points)},
            recoverability="not_applicable",
        )

    active_driver = driver or MacOSMagicMaskGuiDriver()
    proof_root = (proof_dir or DEFAULT_PROOF_DIR).expanduser()
    if not proof_root.is_absolute():
        proof_root = Path.cwd() / proof_root
    proof_root = proof_root.resolve(strict=False)
    proof_root.mkdir(parents=True, exist_ok=True)

    permission_state = active_driver.preflight_permissions()
    context = _activate_clip_context(conn, normalized_clip)
    page_state = _ensure_color_page(conn)
    window_rect = active_driver.find_resolve_window()
    panel_state = active_driver.ensure_magic_mask_panel(normalized_mode)
    paint_mode_state = active_driver.prepare_paint_stroke()
    viewer_rect = active_driver.capture_viewer_geometry(window_rect, frame_aspect=_timeline_frame_aspect(conn))
    mapped_points = map_stroke_to_viewer_pixels(stroke_points, viewer_rect)
    stroke_state = active_driver.draw_stroke(mapped_points)
    track_state = active_driver.track_magic_mask() if track_requested else {"track_clicked": False}
    target_identity = _verify_exact_clip_context(conn, context)

    paths = _proof_paths(proof_root, normalized_clip)
    screenshot_state = active_driver.capture_screenshot(viewer_rect, paths.screenshot_path)
    export_state, export_readiness = _export_proof_when_ready(
        proof_exporter,
        paths.export_path,
        track_requested=track_requested,
    )
    if track_requested and track_state.get("tracking_completed") is None:
        track_state["tracking_completed"] = True
        track_state["completion_verified_by"] = "color_page_frame_export"
    track_state.update(export_readiness)
    if not paths.screenshot_path.is_file() or not paths.export_path.is_file():
        raise MagicMaskProofFailed(
            "Magic Mask GUI route did not create required proof artifacts.",
            details={
                "screenshot_path": str(paths.screenshot_path),
                "export_path": str(paths.export_path),
                "screenshot_exists": paths.screenshot_path.is_file(),
                "export_exists": paths.export_path.is_file(),
            },
        )

    set_verification_status("partial")
    set_recoverability("manual")
    return {
        "route": ROUTE,
        "clip": normalized_clip,
        "clip_readback": context.get("clip_readback"),
        "mode": normalized_mode,
        "stroke": {
            "points_normalized": [[x, y] for x, y in stroke_points],
            "points_viewer_pixels": [[x, y] for x, y in mapped_points],
        },
        "track_requested": bool(track_requested),
        "proof": {
            "screenshot_path": str(paths.screenshot_path),
            "export_path": str(paths.export_path),
            "viewer_rect": viewer_rect.as_payload(),
            "screenshot": screenshot_state,
            "export": export_state,
        },
        "preflight": {
            "permissions": permission_state,
            "window_rect": window_rect.as_payload(),
            "page": page_state,
            "panel": panel_state,
            "paint_mode": paint_mode_state,
            "target_activation": context.get("target_activation"),
            "target_identity": target_identity,
        },
        "stroke_result": stroke_state,
        "track_result": track_state,
    }
