"""Workflow-owned GUI-assisted Fairlight group assignment route.

This module drives only DaVinci Resolve's native Fairlight ``Create Group``
dialog. It is intentionally scoped to assigning one visible audio channel to a
named Fairlight group and does not expose a general GUI automation surface.
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

from ..errors import GuiPermissionMissing, ReadinessFailed, ResolveWindowNotFound, ResolveWindowNotReady, ValidationError
from ..output import set_recoverability, set_verification_status
from . import fairlight_ops

ROUTE = "fairlight.group_assign_gui"
ENGINE = "resolve_gui"
DEFAULT_PROOF_DIR = Path("artifacts") / "fairlight-group-gui"
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
class GroupDialogState:
    window_rect: Rect
    title: str
    name_rect: Rect
    add_button_rect: Rect
    save_button_rect: Rect
    available_channels: list[dict[str, Any]]
    added_channels: list[dict[str, Any]]
    scanned: int

    def as_payload(self) -> dict[str, Any]:
        return {
            "window_rect": self.window_rect.as_payload(),
            "title": self.title,
            "name_rect": self.name_rect.as_payload(),
            "add_button_rect": self.add_button_rect.as_payload(),
            "save_button_rect": self.save_button_rect.as_payload(),
            "available_channels": self.available_channels,
            "added_channels": self.added_channels,
            "scanned": self.scanned,
        }


class MacOSFairlightGroupAssignGuiDriver:
    """Internal macOS driver scoped to Fairlight group assignment."""

    process_names = PROCESS_NAMES

    def preflight_permissions(self) -> dict[str, Any]:
        if platform.system() != "Darwin":
            raise GuiPermissionMissing(
                "Fairlight group assignment GUI-assisted route requires macOS.",
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

    def open_dialog(self) -> GroupDialogState:
        existing = _inspect_group_dialog_payload()
        if existing.get("ok"):
            return _payload_to_state(existing)
        if existing.get("reason") == "process_not_found":
            raise ResolveWindowNotFound("DaVinci Resolve is not running.", details=existing)
        _post_mouse_click(_groups_create_button_point())
        time.sleep(0.8)
        payload = _inspect_group_dialog_payload()
        if not payload.get("ok"):
            raise ResolveWindowNotReady("DaVinci Resolve Fairlight Create Group dialog is not available.", details=payload)
        return _payload_to_state(payload)

    def assign(self, *, group: str, channel_label: str) -> dict[str, Any]:
        dialog = self.open_dialog()
        target = _find_channel(dialog.available_channels, channel_label)
        if target is None:
            raise ReadinessFailed(
                "The requested Fairlight audio track is not visible in the native Create Group dialog.",
                details={
                    "requested_channel": channel_label,
                    "available_channels": dialog.available_channels,
                    "route": ROUTE,
                },
            )
        _post_mouse_click(dialog.name_rect.center)
        time.sleep(0.1)
        _hotkey("a", modifier="command")
        time.sleep(0.05)
        _paste_text(group)
        time.sleep(0.2)
        channel_rect = _rect_from_payload(target["rect"])
        _post_mouse_drag(
            (channel_rect.x + 22, channel_rect.y + int(round(channel_rect.height / 2))),
            (channel_rect.x + 407, channel_rect.y + int(round(channel_rect.height / 2))),
        )
        time.sleep(0.3)
        _post_mouse_click(dialog.add_button_rect.center)
        time.sleep(0.45)
        after_add = self.inspect_dialog()
        if _find_channel(after_add.added_channels, channel_label) is None:
            raise ReadinessFailed(
                "DaVinci Resolve did not move the requested channel into the native Channels Added list.",
                details={
                    "requested_channel": channel_label,
                    "available_channels": after_add.available_channels,
                    "added_channels": after_add.added_channels,
                    "route": ROUTE,
                },
            )
        return {"before": dialog, "after_add": after_add, "channel_rect": channel_rect}

    def inspect_dialog(self) -> GroupDialogState:
        payload = _inspect_group_dialog_payload()
        if not payload.get("ok"):
            raise ResolveWindowNotReady("DaVinci Resolve Fairlight Create Group dialog is not available.", details=payload)
        return _payload_to_state(payload)

    def save_dialog(self, state: GroupDialogState) -> None:
        _post_mouse_click(state.save_button_rect.center)
        time.sleep(0.8)

    def capture_proof(self, state: GroupDialogState, path: Path) -> dict[str, Any]:
        path.parent.mkdir(parents=True, exist_ok=True)
        _capture_region(state.window_rect, path)
        return {"screenshot_path": str(path), "bytes": path.stat().st_size, "region": state.window_rect.as_payload()}

    def capture_window_proof(self, path: Path) -> dict[str, Any]:
        path.parent.mkdir(parents=True, exist_ok=True)
        rect = _window_rect()
        _capture_region(rect, path)
        return {"screenshot_path": str(path), "bytes": path.stat().st_size, "region": rect.as_payload()}

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


def run_group_assign(
    conn: Any,
    *,
    group: str,
    track: int,
    proof_dir: Path | None = None,
    driver: MacOSFairlightGroupAssignGuiDriver | None = None,
) -> dict[str, Any]:
    group_name = str(group or "").strip()
    if not group_name:
        raise ValidationError(
            "Fairlight group assignment requires a group name.",
            details={"group": group},
            recoverability="not_applicable",
        )
    if track < 1:
        raise ValidationError(
            "Fairlight group assignment requires an audio track index of 1 or greater.",
            details={"track": track, "min": 1},
            recoverability="not_applicable",
        )
    tracks = fairlight_ops.list_audio_tracks(conn)
    if len(tracks) < track:
        raise ValidationError(
            "Fairlight audio track index is out of range for group assignment.",
            details={"track": track, "available_audio_tracks": len(tracks)},
            recoverability="not_applicable",
        )
    track_row = tracks[track - 1]
    channel_label = str(track_row.get("name") or f"Audio {track}").strip() or f"Audio {track}"
    active_driver = driver or MacOSFairlightGroupAssignGuiDriver()
    permission_state = active_driver.preflight_permissions()
    page_state = _ensure_fairlight_page(conn)
    result = active_driver.assign(group=group_name, channel_label=channel_label)
    proof_root = _proof_root(proof_dir)
    dialog_proof = active_driver.capture_proof(result["after_add"], _proof_path(proof_root, "dialog"))
    active_driver.save_dialog(result["after_add"])
    saved_proof = active_driver.capture_window_proof(_proof_path(proof_root, "saved"))

    set_verification_status("verified")
    set_recoverability("manual")
    return {
        "action": "fairlight.group.assign",
        "route": ROUTE,
        "engine_scope": "workflow_owned_resolve_gui",
        "group": group_name,
        "track": int(track),
        "track_name": channel_label,
        "changed": True,
        "readback": {
            "verified": True,
            "method": "native Create Group dialog AX readback plus screenshot proof",
            "group_name_set_via": "native Name field",
            "membership_verified_by": "Channels Added list contains requested audio track before Save",
            "saved_via": "native Save button",
            "added_channels": result["after_add"].added_channels,
        },
        "dialog": result["after_add"].as_payload(),
        "channel_rect": result["channel_rect"].as_payload(),
        "proof": dialog_proof,
        "saved_proof": saved_proof,
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


def _find_channel(channels: list[dict[str, Any]], label: str) -> dict[str, Any] | None:
    normalized = label.strip().lower()
    for channel in channels:
        if str(channel.get("label") or "").strip().lower() == normalized:
            return channel
    return None


def _payload_to_state(payload: dict[str, Any]) -> GroupDialogState:
    try:
        return GroupDialogState(
            window_rect=_rect_from_payload(payload["window"]),
            title=str(payload.get("title") or "Create Group"),
            name_rect=_rect_from_payload(payload["name_field"]),
            add_button_rect=_rect_from_payload(payload["add_button"]),
            save_button_rect=_rect_from_payload(payload["save_button"]),
            available_channels=list(payload.get("available_channels") or []),
            added_channels=list(payload.get("added_channels") or []),
            scanned=int(payload.get("scanned") or 0),
        )
    except Exception as exc:
        raise ResolveWindowNotReady(
            "DaVinci Resolve Fairlight group dialog probe did not include usable controls.",
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


def _proof_root(proof_dir: Path | None) -> Path:
    root = (proof_dir or DEFAULT_PROOF_DIR).expanduser()
    if not root.is_absolute():
        root = Path.cwd() / root
    root = root.resolve(strict=False)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _proof_path(root: Path, stem: str) -> Path:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    return root / f"fairlight-group-{stem}-{stamp}.png"


def _inspect_group_dialog_payload() -> dict[str, Any]:
    proc = _run_osascript(_INSPECT_GROUP_DIALOG_JXA, language="JavaScript", timeout=5.0)
    if proc.returncode != 0:
        raise ResolveWindowNotReady(
            "Could not inspect DaVinci Resolve Fairlight Create Group dialog.",
            details={"stderr": proc.stderr[-1000:], "stdout": proc.stdout[-500:]},
        )
    return _json_payload(proc.stdout, "DaVinci Resolve group dialog inspect probe returned invalid data.")


def _groups_create_button_point() -> tuple[int, int]:
    rect = _window_rect()
    return (rect.x + 436, rect.y + rect.height - 201)


def _window_rect() -> Rect:
    proc = _run_osascript(
        'tell application "System Events"\n'
        '  tell process "DaVinci Resolve"\n'
        '    set frontmost to true\n'
        '    set p to position of window 1\n'
        '    set s to size of window 1\n'
        "  end tell\n"
        '  return (item 1 of p as text) & "," & (item 2 of p as text) & "," & (item 1 of s as text) & "," & (item 2 of s as text)\n'
        "end tell",
        timeout=3.0,
    )
    if proc.returncode != 0:
        raise ReadinessFailed("Could not read DaVinci Resolve window bounds for Fairlight group proof.", details={"stderr": proc.stderr[-500:]})
    try:
        x, y, w, h = [int(float(part)) for part in proc.stdout.strip().split(",")]
    except ValueError as exc:
        raise ReadinessFailed("DaVinci Resolve window bounds readback was invalid.", details={"stdout": proc.stdout[-500:]}) from exc
    return Rect(x=x, y=y, width=w, height=h)


def _capture_region(rect: Rect, path: Path) -> None:
    region = f"{rect.x},{rect.y},{rect.width},{rect.height}"
    proc = subprocess.run(["screencapture", "-x", "-t", "png", "-R", region, str(path)], capture_output=True, text=True, timeout=10)
    if proc.returncode != 0 or not path.is_file():
        raise ReadinessFailed(
            "Failed to capture Fairlight group assignment proof screenshot.",
            details={"screenshot_path": str(path), "region": rect.as_payload(), "stderr": proc.stderr[-500:]},
        )


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
                "macOS failed to create Fairlight group mouse event.",
                details={"event_type": event_type, "point": {"x": point[0], "y": point[1]}},
            )
        try:
            app_services.CGEventPost(0, event)
        finally:
            app_services.CFRelease(event)
        time.sleep(delay_seconds)


def _post_mouse_drag(start: tuple[int, int], end: tuple[int, int]) -> None:
    app_services = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices")

    class CGPoint(ctypes.Structure):
        _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]

    app_services.CGEventCreateMouseEvent.restype = ctypes.c_void_p
    app_services.CGEventCreateMouseEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint32, CGPoint, ctypes.c_uint32]
    app_services.CGEventPost.argtypes = [ctypes.c_uint32, ctypes.c_void_p]
    app_services.CFRelease.argtypes = [ctypes.c_void_p]

    points = [start]
    steps = 10
    for step in range(1, steps + 1):
        x = start[0] + ((end[0] - start[0]) * step / steps)
        y = start[1] + ((end[1] - start[1]) * step / steps)
        points.append((int(round(x)), int(round(y))))
    events = [(1, start)]
    events.extend((6, point) for point in points[1:])
    events.append((2, end))
    for event_type, point in events:
        event = app_services.CGEventCreateMouseEvent(None, event_type, CGPoint(float(point[0]), float(point[1])), 0)
        if not event:
            raise ReadinessFailed(
                "macOS failed to create Fairlight group drag event.",
                details={"event_type": event_type, "point": {"x": point[0], "y": point[1]}},
            )
        try:
            app_services.CGEventPost(0, event)
        finally:
            app_services.CFRelease(event)
        time.sleep(0.12)


def _hotkey(key: str, *, modifier: str) -> None:
    _run_osascript(
        f'tell application "System Events" to keystroke "{_osascript_string(key)}" using {_osascript_modifier(modifier)} down',
        timeout=3.0,
        check=True,
    )


def _paste_text(text: str) -> None:
    escaped = _osascript_string(text)
    _run_osascript(
        'set the clipboard to "' + escaped + '"\n'
        'tell application "System Events" to keystroke "v" using command down',
        timeout=3.0,
        check=True,
    )


def _osascript_modifier(modifier: str) -> str:
    if modifier == "command":
        return "command"
    raise ValueError(f"unsupported modifier: {modifier}")


def _osascript_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _json_payload(stdout: str, message: str) -> dict[str, Any]:
    try:
        return json.loads(stdout.strip())
    except json.JSONDecodeError as exc:
        raise ResolveWindowNotReady(message, details={"stdout": stdout[-1000:]}) from exc


def _run_osascript(
    script: str,
    *,
    language: str | None = None,
    timeout: float = 5.0,
    check: bool = False,
) -> subprocess.CompletedProcess[str]:
    cmd = ["osascript"]
    if language:
        cmd.extend(["-l", language])
    cmd.extend(["-e", script])
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        proc = subprocess.CompletedProcess(cmd, 124, stdout=exc.stdout or "", stderr=exc.stderr or str(exc))
    if check and proc.returncode != 0:
        raise ReadinessFailed(
            "DaVinci Resolve Fairlight group AppleScript input failed.",
            details={"stderr": proc.stderr[-500:], "stdout": proc.stdout[-500:]},
        )
    return proc


_INSPECT_GROUP_DIALOG_JXA = r"""
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
function textOf(item) {
  let value = "";
  let title = "";
  try { value = String(item.value() || ""); } catch (e) {}
  try { title = String(item.title() || ""); } catch (e) {}
  return title || value;
}
function flatten(root, limit) {
  const out = [];
  const queue = [root];
  while (queue.length && out.length < limit) {
    const item = queue.shift();
    let role = "";
    try { role = String(item.role() || ""); } catch (e) {}
    out.push({ item, role, text: textOf(item), rect: rectPayload(item) });
    try {
      const children = item.uiElements();
      for (let i = 0; i < children.length; i++) queue.push(children[i]);
    } catch (e) {}
  }
  return out;
}
function channelsFor(group) {
  const kids = group.uiElements();
  const rows = [];
  for (let i = 0; i < kids.length; i++) {
    let role = "";
    let label = "";
    try { role = String(kids[i].role() || ""); } catch (e) {}
    try { label = String(kids[i].title() || ""); } catch (e) {}
    if (role === "AXGroup" && label) {
      rows.push({ label, rect: rectPayload(kids[i]) });
    }
  }
  return rows;
}
function inspectDialog() {
  const windows = proc.windows();
  let scanned = 0;
  for (let i = 0; i < windows.length; i++) {
    let title = "";
    try { title = String(windows[i].title() || ""); } catch (e) {}
    if (title !== "Create Group" && title !== "Modify Group") continue;
    const all = flatten(windows[i], 3000);
    scanned += all.length;
    const nameField = all.find(e => e.role === "AXTextField");
    const addButton = all.find(e => e.role === "AXButton" && e.text === ">");
    const saveButton = all.find(e => e.role === "AXButton" && e.text === "Save");
    let availableGroup = null;
    let addedGroup = null;
    for (const entry of all) {
      if (entry.role !== "AXGroup") continue;
      let children = [];
      try { children = entry.item.uiElements(); } catch (e) {}
      for (let c = 0; c < children.length; c++) {
        let childRole = "";
        let childTitle = "";
        try { childRole = String(children[c].role() || ""); } catch (e) {}
        try { childTitle = String(children[c].title() || ""); } catch (e) {}
        if (childRole === "AXColumn" && childTitle === "Add Channels") availableGroup = entry.item;
        if (childRole === "AXColumn" && childTitle === "Channels Added") addedGroup = entry.item;
      }
    }
    if (nameField && addButton && saveButton && availableGroup && addedGroup) {
      return {
        ok: true,
        process_name: processName,
        title,
        scanned,
        window: rectPayload(windows[i]),
        name_field: nameField.rect,
        add_button: addButton.rect,
        save_button: saveButton.rect,
        available_channels: channelsFor(availableGroup),
        added_channels: channelsFor(addedGroup),
      };
    }
    return { ok: false, reason: "group_dialog_controls_missing", title, scanned };
  }
  return { ok: false, reason: "group_dialog_not_found", process_name: processName, scanned };
}
if (!proc) {
  JSON.stringify({ ok: false, reason: "process_not_found", process_names: processNames });
} else {
  JSON.stringify(inspectDialog());
}
"""


_OPEN_CREATE_GROUP_JXA = r"""
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
function textOf(item) {
  let value = "";
  let title = "";
  try { value = String(item.value() || ""); } catch (e) {}
  try { title = String(item.title() || ""); } catch (e) {}
  return title || value;
}
function flatten(root, limit) {
  const out = [];
  const queue = [root];
  while (queue.length && out.length < limit) {
    const item = queue.shift();
    let role = "";
    try { role = String(item.role() || ""); } catch (e) {}
    out.push({ item, role, text: textOf(item), rect: rectPayload(item) });
    try {
      const children = item.uiElements();
      for (let i = 0; i < children.length; i++) queue.push(children[i]);
    } catch (e) {}
  }
  return out;
}
function channelsFor(group) {
  const kids = group.uiElements();
  const rows = [];
  for (let i = 0; i < kids.length; i++) {
    let role = "";
    let label = "";
    try { role = String(kids[i].role() || ""); } catch (e) {}
    try { label = String(kids[i].title() || ""); } catch (e) {}
    if (role === "AXGroup" && label) {
      rows.push({ label, rect: rectPayload(kids[i]) });
    }
  }
  return rows;
}
function inspectDialog() {
  const windows = proc.windows();
  let scanned = 0;
  for (let i = 0; i < windows.length; i++) {
    let title = "";
    try { title = String(windows[i].title() || ""); } catch (e) {}
    if (title !== "Create Group" && title !== "Modify Group") continue;
    const all = flatten(windows[i], 3000);
    scanned += all.length;
    const nameField = all.find(e => e.role === "AXTextField");
    const addButton = all.find(e => e.role === "AXButton" && e.text === ">");
    const saveButton = all.find(e => e.role === "AXButton" && e.text === "Save");
    let availableGroup = null;
    let addedGroup = null;
    for (const entry of all) {
      if (entry.role !== "AXGroup") continue;
      let children = [];
      try { children = entry.item.uiElements(); } catch (e) {}
      for (let c = 0; c < children.length; c++) {
        let childRole = "";
        let childTitle = "";
        try { childRole = String(children[c].role() || ""); } catch (e) {}
        try { childTitle = String(children[c].title() || ""); } catch (e) {}
        if (childRole === "AXColumn" && childTitle === "Add Channels") availableGroup = entry.item;
        if (childRole === "AXColumn" && childTitle === "Channels Added") addedGroup = entry.item;
      }
    }
    if (nameField && addButton && saveButton && availableGroup && addedGroup) {
      return {
        ok: true,
        process_name: processName,
        title,
        scanned,
        window: rectPayload(windows[i]),
        name_field: nameField.rect,
        add_button: addButton.rect,
        save_button: saveButton.rect,
        available_channels: channelsFor(availableGroup),
        added_channels: channelsFor(addedGroup),
      };
    }
  }
  return { ok: false, reason: "group_dialog_not_found", process_name: processName, scanned };
}
function clickCenter(entry) {
  const pos = entry.rect.pos || [];
  const size = entry.rect.size || [];
  if (pos.length < 2 || size.length < 2) return false;
  entry.item.click();
  return true;
}
function openCreateGroup() {
  let existing = inspectDialog();
  if (existing.ok) return existing;
  proc.frontmost = true;
  delay(0.2);
  const windows = proc.windows();
  if (windows.length < 1) return { ok: false, reason: "window_not_found", process_name: processName };
  const front = windows[0];
  let all = flatten(front, 5000);
  const groupsToggle = all.find(e => e.role === "AXCheckBox" && e.text === "Groups");
  if (groupsToggle) {
    let value = "";
    try { value = String(groupsToggle.item.value()); } catch (e) {}
    if (value !== "1") {
      groupsToggle.item.click();
      delay(0.4);
      all = flatten(front, 5000);
    }
  }
  const groupHeaders = all.filter(e => e.role === "AXStaticText" && e.text === "Groups");
  groupHeaders.sort((a, b) => (b.rect.pos[1] || 0) - (a.rect.pos[1] || 0));
  const header = groupHeaders[0];
  if (!header) return { ok: false, reason: "groups_panel_header_not_found", process_name: processName };
  const hy = header.rect.pos[1] || 0;
  const hx = header.rect.pos[0] || 0;
  const button = all.find(e => {
    if (e.role !== "AXButton") return false;
    const x = e.rect.pos[0] || 0;
    const y = e.rect.pos[1] || 0;
    const w = e.rect.size[0] || 0;
    const h = e.rect.size[1] || 0;
    return x > hx + 250 && Math.abs(y - hy) <= 6 && w >= 20 && w <= 40 && h >= 18 && h <= 28;
  });
  if (!button) return { ok: false, reason: "groups_create_button_not_found", process_name: processName, header_rect: header.rect };
  button.item.click();
  delay(0.7);
  return inspectDialog();
}
if (!proc) {
  JSON.stringify({ ok: false, reason: "process_not_found", process_names: processNames });
} else {
  JSON.stringify(openCreateGroup());
}
"""
