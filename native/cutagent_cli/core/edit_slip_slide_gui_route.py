"""Workflow-owned GUI route for DaVinci Resolve Edit page Slip/Slide nudges."""

from __future__ import annotations

import ctypes
import math
import platform
import subprocess
import time
from dataclasses import asdict, dataclass, replace
from typing import Any

from ..errors import APICallFailed, GuiPermissionMissing, ReadinessFailed, ValidationError
from ..output import set_recoverability, set_verification_status
from ..utils.time_ref import parse_record_frame
from ..utils.timecode import frames_to_timecode
from . import db_timeline_selection, timeline_ops, timeline_precision_edit

ROUTE = "edit.slip_slide_gui"
ENGINE = "resolve_gui"
PROCESS_NAMES = ("DaVinci Resolve", "Resolve")


@dataclass(frozen=True)
class ClipState:
    track_type: str
    track_index: int
    name: str
    start: int
    end: int
    duration: int
    source_start: int
    source_end: int
    left_offset: int
    right_offset: int
    source_fps: float = 24.0
    item_id: str = ""
    linked_item_ids: tuple[str, ...] = ()

    def as_payload(self) -> dict[str, Any]:
        return asdict(self)


class MacOSEditSlipSlideGuiDriver:
    process_names = PROCESS_NAMES

    def preflight_permissions(self) -> dict[str, Any]:
        if platform.system() != "Darwin":
            raise GuiPermissionMissing(
                "Edit page Slip/Slide GUI-assisted route requires macOS.",
                details={"platform": platform.system(), "required": ["macOS"]},
            )
        accessibility = self._accessibility_enabled()
        if not accessibility:
            raise GuiPermissionMissing(
                "Enable macOS Accessibility for the process running CutAgent CLI.",
                details={"missing": ["Accessibility"], "accessibility": accessibility, "target_process_names": list(self.process_names)},
            )
        return {"accessibility": True}

    def click_menu_item(self, *path: str) -> dict[str, Any]:
        if len(path) == 2:
            top_level, item = path
            command = f'click menu item "{item}" of menu 1 of menu bar item "{top_level}" of menu bar 1'
        elif len(path) == 3:
            top_level, parent, item = path
            command = (
                f'click menu item "{item}" of menu 1 of menu item "{parent}" '
                f'of menu 1 of menu bar item "{top_level}" of menu bar 1'
            )
        else:
            raise ValueError("menu path must have two or three entries")
        script = f'''
tell application "System Events"
  tell process "DaVinci Resolve"
    set frontmost to true
    {command}
  end tell
end tell
'''
        proc = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=8)
        if proc.returncode != 0:
            raise ReadinessFailed(
                "Could not invoke native DaVinci Resolve Edit page menu item.",
                details={"menu_path": " > ".join(path), "stderr": proc.stderr[-500:], "stdout": proc.stdout[-500:]},
            )
        return {"method": "native_menu_item_click", "menu_path": " > ".join(path)}

    def _accessibility_enabled(self) -> bool:
        proc = subprocess.run(
            ["osascript", "-e", 'tell application "System Events" to get UI elements enabled'],
            capture_output=True,
            text=True,
            timeout=3,
        )
        return proc.returncode == 0 and proc.stdout.strip().lower() == "true"

    def _accessibility_trusted(self) -> bool:
        try:
            app_services = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices")
            app_services.AXIsProcessTrusted.restype = ctypes.c_bool
            return bool(app_services.AXIsProcessTrusted())
        except Exception:
            return False


def _ensure_edit_page(conn: Any) -> dict[str, Any]:
    resolve = getattr(conn, "resolve", None)
    if resolve is None:
        raise ReadinessFailed("DaVinci Resolve connection does not expose a resolve object.", details={"required_page": "edit"})
    try:
        before = resolve.GetCurrentPage()
    except Exception:
        before = None
    if before != "edit":
        try:
            opened = resolve.OpenPage("edit")
        except Exception as exc:
            raise ReadinessFailed("Failed to switch DaVinci Resolve to the Edit page.", details={"error": str(exc)}) from exc
        if opened is False:
            raise ReadinessFailed("DaVinci Resolve refused to switch to the Edit page.", details={"api_result": opened})
    try:
        after = resolve.GetCurrentPage()
    except Exception:
        after = "edit"
    if after != "edit":
        raise ReadinessFailed("DaVinci Resolve is not on the Edit page.", details={"current_page": after})
    return {"required_page": "edit", "previous_page": before, "current_page": after}


def _clip_states(conn: Any, track_type: str | None = "video") -> list[ClipState]:
    states: list[ClipState] = []
    snapshot = timeline_precision_edit.snapshot_timeline(conn)
    for item_state in snapshot.items:
        if track_type is not None and item_state.track_type != track_type:
            continue
        native_item = snapshot.native_items[item_state.item_id]
        if item_state.source_start is None or item_state.source_end is None:
            raise ValidationError(
                "Slip/Slide requires source-range readback for every protected A/V timeline item.",
                details={"item": item_state.payload()},
                recoverability="manual",
            )
        try:
            left_offset = int(native_item.GetLeftOffset(False))
            right_offset = int(native_item.GetRightOffset(False))
        except TypeError:
            left_offset = int(native_item.GetLeftOffset())
            right_offset = int(native_item.GetRightOffset())
        except Exception as exc:
            raise ValidationError(
                "Slip/Slide requires source-handle readback for every protected A/V timeline item.",
                details={"item": item_state.payload(), "error": str(exc)},
                recoverability="manual",
            ) from exc
        try:
            media_pool_item = native_item.GetMediaPoolItem()
            properties = media_pool_item.GetClipProperty() or {}
            raw_source_fps = properties.get("FPS") if isinstance(properties, dict) else None
            source_fps = float(str(raw_source_fps).strip())
            if not math.isfinite(source_fps) or source_fps <= 0:
                raise ValueError(f"invalid FPS value: {raw_source_fps!r}")
        except Exception as exc:
            raise ValidationError(
                "Slip/Slide requires the source media frame rate for exact boundary verification.",
                details={"item": item_state.payload(), "required_property": "MediaPoolItem.FPS", "error": str(exc)},
                recoverability="manual",
            ) from exc
        states.append(
            ClipState(
                track_type=item_state.track_type,
                track_index=item_state.track_index,
                name=item_state.name,
                start=item_state.start,
                end=item_state.end,
                duration=item_state.duration,
                source_start=item_state.source_start,
                source_end=item_state.source_end,
                left_offset=left_offset,
                right_offset=right_offset,
                source_fps=source_fps,
                item_id=item_state.item_id,
                linked_item_ids=item_state.linked_item_ids,
            )
        )
    return states


def _timeline_binding(conn: Any) -> dict[str, Any]:
    timeline = getattr(conn, "timeline", None)
    if timeline is None:
        raise ValidationError("Slip/Slide requires an active timeline binding.", recoverability="manual")
    try:
        timeline_id = timeline.GetUniqueId()
        start_frame = timeline.GetStartFrame()
        if not timeline_id or start_frame is None or isinstance(start_frame, bool):
            raise TypeError(f"invalid timeline binding: id={timeline_id!r}, start={start_frame!r}")
        return {"timeline_id": str(timeline_id), "start_frame": int(start_frame)}
    except Exception as exc:
        raise ValidationError(
            "Slip/Slide could not read the stable timeline ID and absolute start frame.",
            details={"required_methods": ["Timeline.GetUniqueId", "Timeline.GetStartFrame"], "error": str(exc)},
            recoverability="manual",
        ) from exc


def _bound_clip_states(conn: Any) -> tuple[list[ClipState], dict[str, Any]]:
    binding_before = _timeline_binding(conn)
    rows = _clip_states(conn, None)
    binding_after = _timeline_binding(conn)
    if binding_before != binding_after:
        raise ValidationError(
            "Slip/Slide timeline binding changed during state capture.",
            details={"binding_before": binding_before, "binding_after": binding_after},
            recoverability="manual",
        )
    return rows, binding_after


def _refresh_live_state(conn: Any, *, stage: str) -> None:
    try:
        conn.refresh()
    except Exception as exc:
        raise ReadinessFailed(
            "Could not refresh live DaVinci Resolve state required for native Slip/Slide targeting.",
            details={"failure_step": stage, "error": str(exc)},
            recoverability="manual",
        ) from exc


def _state_matches_ref(state: ClipState, ref: db_timeline_selection.LiveItemRef) -> bool:
    return (
        state.track_type == ref.track_type
        and state.track_index == int(ref.track_index)
        and state.start == int(ref.start)
        and state.end == int(ref.end)
        and state.name == ref.name
    )


def _resolve_before_state(conn: Any, ref: db_timeline_selection.LiveItemRef) -> ClipState:
    matches = [state for state in _clip_states(conn, ref.track_type) if _state_matches_ref(state, ref)]
    if len(matches) != 1:
        raise ValidationError(
            "Selected clip is not uniquely addressable for native Slip/Slide.",
            details={"selection": asdict(ref), "match_count": len(matches)},
            recoverability="manual",
        )
    return matches[0]


def _target_selection_frame(target: db_timeline_selection.LiveItemRef, at: str | None, conn: Any) -> int:
    if at:
        frame = db_timeline_selection.resolve_record_frame(conn, at=at)
        if not (target.start <= frame < target.end):
            raise ValidationError(
                "--at must be inside the selected clip for native Slip/Slide.",
                details={"at": at, "record_frame": frame, "selection": asdict(target)},
                recoverability="not_applicable",
            )
        return int(frame)
    duration = int(target.duration)
    if duration <= 0:
        raise ValidationError(
            "Selected clip has no positive record duration for native Slip/Slide.",
            details={"selection": asdict(target)},
            recoverability="manual",
        )
    return int(target.start) if duration == 1 else int(target.start) + duration // 2


def _adjacent_states(before: list[ClipState], target: ClipState) -> tuple[ClipState | None, ClipState | None]:
    track_rows = sorted(
        [state for state in before if state.track_type == target.track_type and state.track_index == target.track_index],
        key=lambda state: (state.start, state.end, state.source_start),
    )
    left = next((state for state in reversed(track_rows) if state.end == target.start), None)
    right = next((state for state in track_rows if state.start == target.end), None)
    return left, right


def _find_after_slip(after: list[ClipState], before: ClipState) -> ClipState | None:
    if before.item_id:
        matches = [state for state in after if state.item_id == before.item_id]
        return matches[0] if len(matches) == 1 else None
    matches = [
        state
        for state in after
        if state.track_type == before.track_type
        and state.track_index == before.track_index
        and state.name == before.name
        and state.start == before.start
        and state.end == before.end
        and state.duration == before.duration
    ]
    return matches[0] if len(matches) == 1 else None


def _find_after_slide(after: list[ClipState], before: ClipState) -> ClipState | None:
    if before.item_id:
        matches = [state for state in after if state.item_id == before.item_id]
        return matches[0] if len(matches) == 1 else None
    matches = [
        state
        for state in after
        if state.track_type == before.track_type
        and state.track_index == before.track_index
        and state.name == before.name
        and state.duration == before.duration
        and state.source_start == before.source_start
        and state.source_end == before.source_end
    ]
    return matches[0] if len(matches) == 1 else None


def _verify_slip(before: ClipState, after: ClipState | None, expected_delta: int) -> dict[str, Any]:
    if after is None:
        return {"status": "failed", "reason": "target_not_found_after_slip"}
    record_unchanged = after.start == before.start and after.end == before.end and after.duration == before.duration
    source_delta = after.source_start - before.source_start
    source_end_delta = after.source_end - before.source_end
    source_changed = source_delta == int(expected_delta) and source_end_delta == int(expected_delta)
    return {
        "status": "verified" if record_unchanged and source_changed else "failed",
        "record_unchanged": record_unchanged,
        "source_delta_frames": source_delta,
        "source_end_delta_frames": source_end_delta,
        "expected_delta_frames": int(expected_delta),
        "expected_abs_delta_frames": abs(int(expected_delta)),
    }


def _verify_slide(before_rows: list[ClipState], after_rows: list[ClipState], before: ClipState, after: ClipState | None, expected_delta: int) -> dict[str, Any]:
    if after is None:
        return {"status": "failed", "reason": "target_not_found_after_slide"}
    left_before, right_before = _adjacent_states(before_rows, before)
    if left_before is None or right_before is None:
        return {"status": "failed", "reason": "slide_requires_adjacent_clips"}
    left_after = next((state for state in after_rows if state.name == left_before.name and state.start == left_before.start), None)
    right_after = next((state for state in after_rows if state.name == right_before.name and state.end == right_before.end), None)
    target_delta = after.start - before.start
    source_unchanged = after.source_start == before.source_start and after.source_end == before.source_end and after.duration == before.duration
    adjacent_reflow = (
        left_after is not None
        and right_after is not None
        and left_after.end == after.start
        and right_after.start == after.end
        and left_after.duration != left_before.duration
        and right_after.duration != right_before.duration
    )
    moved = target_delta == int(expected_delta)
    return {
        "status": "verified" if moved and source_unchanged and adjacent_reflow else "failed",
        "target_delta_frames": target_delta,
        "expected_delta_frames": int(expected_delta),
        "expected_abs_delta_frames": abs(int(expected_delta)),
        "source_unchanged": source_unchanged,
        "adjacent_reflow_verified": adjacent_reflow,
        "left_before": left_before.as_payload(),
        "right_before": right_before.as_payload(),
        "left_after": left_after.as_payload() if left_after else None,
        "right_after": right_after.as_payload() if right_after else None,
    }


def _rows_by_id(rows: list[ClipState]) -> dict[str, ClipState]:
    result: dict[str, ClipState] = {}
    for row in rows:
        if not row.item_id or row.item_id in result:
            raise ValidationError(
                "Slip/Slide timeline snapshot does not have unique stable item identities.",
                details={"item_id": row.item_id, "item": row.as_payload()},
                recoverability="manual",
            )
        result[row.item_id] = row
    return result


def _compare_expected_rows(expected: dict[str, ClipState], after_rows: list[ClipState]) -> dict[str, Any]:
    after = _rows_by_id(after_rows)
    mismatches = []
    for item_id, expected_row in expected.items():
        actual = after.get(item_id)
        if actual != expected_row:
            mismatches.append(
                {
                    "item_id": item_id,
                    "expected": expected_row.as_payload(),
                    "actual": actual.as_payload() if actual else None,
                }
            )
    unexpected = sorted(set(after) - set(expected))
    return {
        "status": "verified" if not mismatches and not unexpected else "failed",
        "mismatches": mismatches,
        "unexpected_item_ids": unexpected,
        "protected_state_verified": not mismatches and not unexpected,
    }


def _selected_group(before_rows: list[ClipState], target: ClipState) -> list[ClipState]:
    by_id = _rows_by_id(before_rows)
    selected_ids = {target.item_id, *target.linked_item_ids}
    missing = sorted(selected_ids - set(by_id))
    if missing:
        raise ValidationError(
            "Slip/Slide linked selection is incomplete in the stable timeline snapshot.",
            details={"target": target.as_payload(), "missing_linked_item_ids": missing},
            recoverability="manual",
        )
    return [by_id[item_id] for item_id in sorted(selected_ids)]


def _reject_stacked_selection(
    before_rows: list[ClipState],
    selected: list[ClipState],
    selection_frame: int,
) -> None:
    selected_ids = {row.item_id for row in selected}
    protected_covering = [
        row
        for row in before_rows
        if row.track_type in {"video", "audio"}
        and row.start <= int(selection_frame) < row.end
        and row.item_id not in selected_ids
    ]
    if protected_covering:
        raise ValidationError(
            "Native Slip/Slide cannot safely select the linked group while unrelated A/V items cover the selection frame.",
            details={
                "selection_frame": int(selection_frame),
                "selected_item_ids": sorted(selected_ids),
                "protected_covering_items": [row.as_payload() for row in protected_covering],
                "selection_method": "Trim > Select All Clips Under Playhead",
            },
            recoverability="not_applicable",
        )


def _expected_slip(before_rows: list[ClipState], selected: list[ClipState], source_delta: int) -> dict[str, ClipState]:
    expected = _rows_by_id(before_rows)
    for row in selected:
        new_left = row.left_offset + int(source_delta)
        new_right = row.right_offset - int(source_delta)
        if new_left < 0 or new_right < 0:
            raise ValidationError(
                "Requested slip exceeds an A/V item's available source handles.",
                details={
                    "item": row.as_payload(),
                    "source_delta_frames": int(source_delta),
                    "resulting_left_offset": new_left,
                    "resulting_right_offset": new_right,
                },
                recoverability="not_applicable",
            )
        expected[row.item_id] = replace(
            row,
            source_start=row.source_start + int(source_delta),
            source_end=row.source_end + int(source_delta),
            left_offset=new_left,
            right_offset=new_right,
        )
    return expected


def _expected_slide(
    before_rows: list[ClipState],
    selected: list[ClipState],
    record_delta: int,
    *,
    timeline_fps: float = 24.0,
) -> dict[str, ClipState]:
    if not math.isfinite(float(timeline_fps)) or float(timeline_fps) <= 0:
        raise ValidationError(
            "Native slide-selected requires a positive timeline frame rate.",
            details={"timeline_fps": timeline_fps},
            recoverability="manual",
        )
    expected = _rows_by_id(before_rows)
    selected_ids = {row.item_id for row in selected}
    adjacent_ids: set[str] = set()
    for row in selected:
        left, right = _adjacent_states(before_rows, row)
        if left is None or right is None:
            raise ValidationError(
                "Native slide-selected requires adjacent clips on both sides of every linked A/V item.",
                details={"selection": row.as_payload()},
                recoverability="not_applicable",
            )
        if left.item_id in selected_ids or right.item_id in selected_ids:
            raise ValidationError(
                "Native slide-selected cannot use another selected linked item as an adjacent handle.",
                details={"selection": row.as_payload(), "left": left.as_payload(), "right": right.as_payload()},
                recoverability="not_applicable",
            )
        if left.item_id in adjacent_ids or right.item_id in adjacent_ids:
            raise ValidationError(
                "Native slide-selected resolved one adjacent item for multiple selected tracks.",
                details={"selection": row.as_payload()},
                recoverability="manual",
            )
        adjacent_ids.update({left.item_id, right.item_id})
        left_duration = left.duration + int(record_delta)
        right_duration = right.duration - int(record_delta)
        left_source_end = left.source_start + math.ceil(left_duration * left.source_fps / float(timeline_fps))
        right_source_start = right.source_end - math.floor(right_duration * right.source_fps / float(timeline_fps))
        left_right_offset = left.right_offset - int(record_delta)
        right_left_offset = right.left_offset + int(record_delta)
        if min(left_duration, right_duration, left_right_offset, right_left_offset) < 0 or left_duration == 0 or right_duration == 0:
            raise ValidationError(
                "Requested slide exceeds adjacent clip duration or source handles.",
                details={
                    "selection": row.as_payload(),
                    "left": left.as_payload(),
                    "right": right.as_payload(),
                    "record_delta_frames": int(record_delta),
                },
                recoverability="not_applicable",
            )
        expected[left.item_id] = replace(
            left,
            end=left.end + int(record_delta),
            duration=left_duration,
            source_end=left_source_end,
            right_offset=left_right_offset,
        )
        expected[right.item_id] = replace(
            right,
            start=right.start + int(record_delta),
            duration=right_duration,
            source_start=right_source_start,
            left_offset=right_left_offset,
        )
        expected[row.item_id] = replace(
            row,
            start=row.start + int(record_delta),
            end=row.end + int(record_delta),
        )
    return expected


def _restore_ui_state(
    conn: Any,
    *,
    previous_page: str | None,
    previous_timecode: str | None,
    expected_binding: dict[str, Any],
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "page": False,
        "playhead": False,
        "timeline_binding": {"status": "not_required"},
        "warnings": [],
    }
    if previous_timecode:
        try:
            conn.refresh()
            actual_binding = _timeline_binding(conn)
            result["timeline_binding"] = {
                "status": "verified" if actual_binding == expected_binding else "failed",
                "expected": expected_binding,
                "actual": actual_binding,
            }
            if actual_binding != expected_binding:
                result["warnings"].append(
                    {
                        "state": "playhead",
                        "reason": "timeline_binding_changed_before_restore",
                        "expected_binding": expected_binding,
                        "actual_binding": actual_binding,
                    }
                )
            elif conn.timeline.SetCurrentTimecode(previous_timecode) is False:
                result["warnings"].append(
                    {"state": "playhead", "reason": "playhead_restore_rejected", "timecode": previous_timecode}
                )
            else:
                result["playhead"] = True
        except Exception as exc:
            result["timeline_binding"] = {"status": "failed", "expected": expected_binding}
            result["warnings"].append(
                {
                    "state": "playhead",
                    "reason": "fresh_timeline_binding_unavailable_before_restore",
                    "error": str(exc),
                }
            )
    if previous_page and previous_page != "edit":
        try:
            if conn.resolve.OpenPage(previous_page) is False:
                result["warnings"].append(
                    {"state": "page", "reason": "page_restore_rejected", "page": previous_page}
                )
            else:
                result["page"] = True
        except Exception as exc:
            result["warnings"].append({"state": "page", "error": str(exc)})
    else:
        result["page"] = True
    return result


def run_selected_slip_slide(
    conn: Any,
    *,
    mode: str,
    clip_name: str | None,
    at: str | None,
    direction: str,
    steps: int,
    driver: MacOSEditSlipSlideGuiDriver | None = None,
) -> dict[str, Any]:
    normalized_mode = str(mode or "").strip().lower()
    if normalized_mode not in {"slip", "slide"}:
        raise ValidationError("Edit Slip/Slide mode must be slip or slide.", details={"mode": mode})
    normalized_direction = str(direction or "").strip().lower()
    if normalized_direction not in {"left", "right"}:
        raise ValidationError("--direction must be left or right.", details={"direction": direction})
    step_count = int(steps)
    if step_count < 1 or step_count > 100:
        raise ValidationError("--steps must be between 1 and 100.", details={"steps": steps})

    active_driver = driver or MacOSEditSlipSlideGuiDriver()
    permissions = active_driver.preflight_permissions()
    _refresh_live_state(conn, stage="initial_binding_refresh")
    try:
        previous_page = conn.resolve.GetCurrentPage()
    except Exception:
        previous_page = None
    try:
        previous_timecode = conn.timeline.GetCurrentTimecode()
    except Exception:
        previous_timecode = None

    before_rows, before_binding = _bound_clip_states(conn)
    if clip_name:
        target_ref = db_timeline_selection.resolve_video_group(conn, clip_name=clip_name, at=None)["video"]
    elif at:
        try:
            timeline_start = int(conn.timeline.GetStartFrame())
        except Exception as exc:
            raise ValidationError(
                "Could not read the active timeline start required for Slip/Slide record selection.",
                details={"at": at, "required_method": "Timeline.GetStartFrame", "error": str(exc)},
                recoverability="manual",
            ) from exc
        record_frame = parse_record_frame(str(at), conn.fps, timeline_start)
        covering = [
            state
            for state in before_rows
            if state.track_type == "video" and state.start <= record_frame < state.end
        ]
        if len(covering) != 1:
            raise ValidationError(
                "Video clip selection is ambiguous for native Slip/Slide at the requested absolute record frame.",
                details={
                    "at": at,
                    "record_frame": record_frame,
                    "matches": [state.as_payload() for state in covering],
                },
                recoverability="manual",
            )
        state = covering[0]
        target_ref = db_timeline_selection.LiveItemRef(
            track_type="video",
            track_index=state.track_index,
            name=state.name,
            start=state.start,
            duration=state.duration,
        )
    else:
        target_ref = db_timeline_selection.resolve_video_group(conn, clip_name=None, at=None)["video"]
    selection_frame = _target_selection_frame(target_ref, at, conn)
    before_matches = [state for state in before_rows if _state_matches_ref(state, target_ref)]
    if len(before_matches) != 1:
        raise ValidationError(
            "Selected clip is not uniquely addressable for native Slip/Slide.",
            details={"selection": asdict(target_ref), "match_count": len(before_matches)},
            recoverability="manual",
        )
    before = before_matches[0]
    selected = _selected_group(before_rows, before)
    _reject_stacked_selection(before_rows, selected, selection_frame)
    signed_nudge_delta = step_count if normalized_direction == "right" else -step_count
    source_delta = -signed_nudge_delta
    expected = (
        _expected_slip(before_rows, selected, source_delta)
        if normalized_mode == "slip"
        else _expected_slide(before_rows, selected, signed_nudge_delta, timeline_fps=conn.fps)
    )

    page: dict[str, Any] | None = None
    playhead: dict[str, Any] | None = None
    actions: list[dict[str, Any]] = []
    nudge_name = "One Frame Right" if normalized_direction == "right" else "One Frame Left"
    inverse_nudge_name = "One Frame Left" if normalized_direction == "right" else "One Frame Right"
    nudge_attempts = 0
    verification: dict[str, Any] = {"status": "failed", "reason": "mutation_not_attempted"}
    pre_mutation_revalidation: dict[str, Any] = {"status": "not_run"}
    after_rows: list[ClipState] = []
    restore: dict[str, Any] = {"page": False, "playhead": False, "warnings": []}
    pending_error: Exception | None = None
    pending_cause: Exception | None = None
    try:
        page = _ensure_edit_page(conn)
        playhead = timeline_ops.set_playhead(
            conn,
            frames_to_timecode(selection_frame, conn.fps),
            return_details=True,
        )
        actions.extend(
            [
                active_driver.click_menu_item("Trim", "Normal Edit Mode"),
                active_driver.click_menu_item("Trim", "Select All Clips Under Playhead"),
                active_driver.click_menu_item("Trim", "Select Nearest Clip To", normalized_mode.capitalize()),
            ]
        )
        _refresh_live_state(conn, stage="pre_mutation_refresh")
        current_rows, current_binding = _bound_clip_states(conn)
        pre_mutation_revalidation = _compare_expected_rows(_rows_by_id(before_rows), current_rows)
        pre_mutation_revalidation["timeline_binding"] = {
            "status": "verified" if current_binding == before_binding else "failed",
            "expected": before_binding,
            "actual": current_binding,
        }
        if current_binding != before_binding:
            pre_mutation_revalidation["status"] = "failed"
        if pre_mutation_revalidation.get("status") != "verified":
            raise ValidationError(
                "Timeline changed after Slip/Slide selection; refusing mutation before the first nudge.",
                details={"pre_mutation_revalidation": pre_mutation_revalidation},
                recoverability="manual",
            )
        for _ in range(step_count):
            nudge_attempts += 1
            actions.append(active_driver.click_menu_item("Trim", "Nudge", nudge_name))
            time.sleep(0.05)
        time.sleep(0.15)
        conn.refresh()
        after_rows, after_binding = _bound_clip_states(conn)
        verification = _compare_expected_rows(expected, after_rows)
        verification["timeline_binding"] = {
            "status": "verified" if after_binding == before_binding else "failed",
            "expected": before_binding,
            "actual": after_binding,
        }
        if after_binding != before_binding:
            verification["status"] = "failed"
        verification.update(
            {
                "mode": normalized_mode,
                "selected_item_ids": [state.item_id for state in selected],
                "linked_items_verified": len(selected) > 1,
                "expected_delta_frames": source_delta if normalized_mode == "slip" else signed_nudge_delta,
            }
        )
        if verification.get("status") != "verified":
            raise ReadinessFailed(
                f"Native {normalized_mode} readback did not verify the selected linked group and protected timeline state.",
                details={"mode": normalized_mode, "verification": verification},
            )
    except Exception as mutation_error:
        rollback_actions: list[dict[str, Any]] = []
        compensation_attempts = 0
        observed_applied_steps: int | None = 0 if not nudge_attempts else None
        observation: dict[str, Any] = {"status": "not_required" if not nudge_attempts else "failed"}
        rollback_verification: dict[str, Any] = {"status": "not_required" if not nudge_attempts else "failed"}
        compensation_binding: dict[str, Any] | None = None
        compensation_safe = False
        if nudge_attempts:
            try:
                conn.refresh()
                observed_rows, compensation_binding = _bound_clip_states(conn)
                if compensation_binding != before_binding:
                    observation = {
                        "status": "failed",
                        "reason": "timeline_binding_changed_before_compensation",
                        "expected_binding": before_binding,
                        "actual_binding": compensation_binding,
                    }
                else:
                    matching_steps: list[int] = []
                    comparisons: list[dict[str, Any]] = []
                    for candidate_steps in range(nudge_attempts + 1):
                        candidate_delta = (
                            (-1 if normalized_direction == "right" else 1) * candidate_steps
                            if normalized_mode == "slip"
                            else (1 if normalized_direction == "right" else -1) * candidate_steps
                        )
                        try:
                            if candidate_steps == 0:
                                candidate_expected = _rows_by_id(before_rows)
                            elif normalized_mode == "slip":
                                candidate_expected = _expected_slip(before_rows, selected, candidate_delta)
                            else:
                                candidate_expected = _expected_slide(
                                    before_rows,
                                    selected,
                                    candidate_delta,
                                    timeline_fps=conn.fps,
                                )
                            comparison = _compare_expected_rows(candidate_expected, observed_rows)
                        except ValidationError as candidate_error:
                            comparison = {"status": "failed", "error": str(candidate_error)}
                        comparisons.append({"steps": candidate_steps, **comparison})
                        if comparison.get("status") == "verified":
                            matching_steps.append(candidate_steps)
                    if len(matching_steps) == 1:
                        observed_applied_steps = matching_steps[0]
                        compensation_safe = True
                        observation = {
                            "status": "verified",
                            "observed_applied_steps": observed_applied_steps,
                            "matching_steps": matching_steps,
                            "timeline_binding": compensation_binding,
                        }
                    else:
                        observation = {
                            "status": "failed",
                            "reason": "applied_step_count_not_uniquely_observable",
                            "matching_steps": matching_steps,
                            "comparisons": comparisons,
                            "timeline_binding": compensation_binding,
                        }
            except Exception as observation_error:
                rollback_verification = {
                    "status": "failed",
                    "reason": "fresh_timeline_state_unavailable_before_compensation",
                    "error": str(observation_error),
                }
                observation = dict(rollback_verification)
        if nudge_attempts and compensation_safe and observed_applied_steps:
            compensation_error: Exception | None = None
            for _ in range(observed_applied_steps):
                try:
                    compensation_attempts += 1
                    rollback_actions.append(active_driver.click_menu_item("Trim", "Nudge", inverse_nudge_name))
                    time.sleep(0.05)
                except Exception as rollback_error:
                    compensation_error = rollback_error
                    break
            try:
                time.sleep(0.15)
                conn.refresh()
                rollback_rows, rollback_binding = _bound_clip_states(conn)
                rollback_verification = _compare_expected_rows(_rows_by_id(before_rows), rollback_rows)
                rollback_verification["timeline_binding"] = {
                    "status": "verified" if rollback_binding == before_binding else "failed",
                    "expected": before_binding,
                    "actual": rollback_binding,
                }
                if rollback_binding != before_binding:
                    rollback_verification["status"] = "failed"
                if compensation_error is not None:
                    rollback_verification["compensation_acknowledgement_error"] = str(compensation_error)
            except Exception as rollback_error:
                rollback_verification = {
                    "status": "failed",
                    "reason": "fresh_timeline_state_unavailable_after_compensation",
                    "error": str(rollback_error),
                    **({"compensation_acknowledgement_error": str(compensation_error)} if compensation_error else {}),
                }
        elif nudge_attempts and compensation_safe and observed_applied_steps == 0:
            rollback_verification = {
                "status": "verified",
                "reason": "observed_pre_mutation_state",
                "protected_state_verified": True,
            }
        elif nudge_attempts and observation.get("status") != "verified":
            rollback_verification = dict(observation)
        set_verification_status("failed")
        set_recoverability("not_applicable" if rollback_verification.get("status") == "verified" else "manual")
        details = dict(getattr(mutation_error, "details", {}) or {})
        details.update(
            {
                "mode": normalized_mode,
                "nudge_attempts": nudge_attempts,
                "applied_steps": observed_applied_steps,
                "observed_applied_steps": observed_applied_steps,
                "mutation_may_have_occurred": bool(nudge_attempts),
                "mutation_observation": observation,
                "rollback_actions": rollback_actions,
                "rollback_verification": rollback_verification,
                "mutation_state": "restored" if rollback_verification.get("status") == "verified" else "manual_recovery_required",
                "compensation": {
                    "available": bool(nudge_attempts and compensation_safe and observed_applied_steps),
                    "attempted": bool(compensation_attempts),
                    "attempted_steps": compensation_attempts,
                    "status": rollback_verification.get("status"),
                    "binding": compensation_binding,
                },
            }
        )
        error_type = APICallFailed if nudge_attempts else ReadinessFailed
        pending_error = error_type(
            f"Native {normalized_mode} failed; compensating nudges were {'verified' if rollback_verification.get('status') == 'verified' else 'not verified'}.",
            details=details,
            recoverability="not_applicable" if rollback_verification.get("status") == "verified" else "manual",
        )
        pending_cause = mutation_error
    finally:
        restore = _restore_ui_state(
            conn,
            previous_page=previous_page,
            previous_timecode=previous_timecode,
            expected_binding=before_binding,
        )

    if pending_error is not None:
        pending_error.details["ui_state_restore"] = restore
        if restore["warnings"]:
            pending_error.recoverability = "manual"
        raise pending_error from pending_cause

    after_by_id = _rows_by_id(after_rows)
    after = after_by_id.get(before.item_id)
    set_verification_status("verified")
    set_recoverability("manual" if restore["warnings"] else "not_applicable")
    return {
        "action": f"edit.{normalized_mode}_selected",
        "changed": True,
        "route": ROUTE,
        "engine_scope": "workflow_owned_resolve_gui",
        "native_ui": ["Trim > Select All Clips Under Playhead", f"Trim > Select Nearest Clip To > {normalized_mode.capitalize()}", f"Trim > Nudge > {nudge_name}"],
        "requested": {"clip": clip_name, "at": at, "direction": normalized_direction, "steps": step_count},
        "selection_frame": selection_frame,
        "selected_linked_group": [state.as_payload() for state in selected],
        "target_before": before.as_payload(),
        "target_after": after.as_payload() if after else None,
        "timeline_before": [state.as_payload() for state in before_rows],
        "timeline_after": [state.as_payload() for state in after_rows],
        "timeline_binding": before_binding,
        "verification": verification,
        "preflight": {
            "permissions": permissions,
            "page": page,
            "playhead": playhead,
            "pre_mutation_revalidation": pre_mutation_revalidation,
        },
        "ui_state_restore": restore,
        "actions": actions,
    }
