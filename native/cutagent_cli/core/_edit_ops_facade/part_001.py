"""Edit operations — split, insert, remove, silence detection, jump cuts."""

from __future__ import annotations

import logging
import os
import re
import subprocess
import tempfile
import time
from typing import Any, Dict, List, Optional, Tuple

from ..errors import APICallFailed, ClipNotFound, InvalidTimeReference, ReadinessFailed, ValidationError
from ..external_tools import resolve_tool
from ..utils.timecode import (
    frames_to_seconds,
    frames_to_timecode,
    parse_time_input,
    seconds_to_frames,
    seconds_to_timecode,
    timecode_to_seconds,
)
from ..utils.time_ref import parse_record_frame, parse_source_frame
from ..output import set_recoverability, set_verification_status

logger = logging.getLogger("cutagent-cli")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _record_frame_position(conn, position: str) -> int:
    """Parse a time string into an absolute frame number (timeline-relative).
    
    Adds the timeline start frame so that '00:00:05:00' means 5 seconds
    into the timeline, not absolute frame 120.
    """
    try:
        start_frame = int(conn.timeline.GetStartFrame())
    except Exception:
        start_frame = 0
    return parse_record_frame(position, conn.fps, start_frame)


def _source_frame_position(conn, position: str) -> int:
    """Parse source-domain time string to source-relative frame."""
    return parse_source_frame(position, conn.fps)


def find_clip_at_position(
    conn,
    frame: int,
    track_type: str = "video",
    track_index: int = 0,
) -> Tuple[Any, int, int]:
    """
    Find the TimelineItem that covers *frame*.

    If *track_index* is 0, searches all tracks of the given type.

    Returns (item, track_type_str, track_index).
    Raises ClipNotFound when nothing is under the position.
    """
    types_to_search = [track_type] if track_type else ["video", "audio"]
    candidate_frames = {int(frame)}
    try:
        timeline_start = int(conn.timeline.GetStartFrame())
    except Exception:
        timeline_start = 0
    if timeline_start:
        candidate_frames.add(int(frame) - timeline_start)

    for ttype in types_to_search:
        count = conn.timeline.GetTrackCount(ttype) or 0
        start_idx = track_index if track_index else 1
        end_idx = (track_index + 1) if track_index else (count + 1)

        for idx in range(start_idx, end_idx):
            items = conn.timeline.GetItemListInTrack(ttype, idx) or []
            for item in items:
                try:
                    s = int(item.GetStart())
                    e = int(item.GetEnd())
                    for candidate in candidate_frames:
                        if s <= candidate < e:
                            return item, ttype, idx
                except Exception:
                    continue

    raise ClipNotFound(f"No clip at frame {frame}.")


def _get_all_clips_in_range(
    conn,
    start_frame: int,
    end_frame: int,
    track_type: str = "video",
    track_index: int = 0,
) -> List[Tuple[Any, str, int]]:
    """Return all clips overlapping [start_frame, end_frame)."""
    results = []
    types_to_search = [track_type] if track_type else ["video", "audio"]

    for ttype in types_to_search:
        count = conn.timeline.GetTrackCount(ttype) or 0
        si = track_index if track_index else 1
        ei = (track_index + 1) if track_index else (count + 1)

        for idx in range(si, ei):
            items = conn.timeline.GetItemListInTrack(ttype, idx) or []
            for item in items:
                try:
                    s = int(item.GetStart())
                    e = int(item.GetEnd())
                    if s < end_frame and e > start_frame:
                        results.append((item, ttype, idx))
                except Exception:
                    continue
    return results


def _clip_source_info(item) -> Dict[str, Any]:
    """Extract source media info from a TimelineItem."""
    info: Dict[str, Any] = {
        "start": int(item.GetStart()),
        "end": int(item.GetEnd()),
        "duration": int(item.GetDuration()),
        "name": item.GetName(),
    }
    try:
        info["left_offset"] = int(item.GetLeftOffset())
    except Exception:
        info["left_offset"] = 0
    try:
        info["right_offset"] = int(item.GetRightOffset())
    except Exception:
        info["right_offset"] = 0

    mpi = None
    if hasattr(item, "GetMediaPoolItem"):
        mpi = item.GetMediaPoolItem()
    info["media_pool_item"] = mpi

    source_start = None
    for attr in ("GetSourceStartFrame", "GetSourceStart"):
        getter = getattr(item, attr, None)
        if callable(getter):
            try:
                source_start = int(getter())
                break
            except Exception:
                continue
    if source_start is None:
        source_start = int(info.get("left_offset") or 0)
    info["source_start"] = source_start
    info["source_end"] = source_start + int(info["duration"])
    return info


# ---------------------------------------------------------------------------
# Split
# ---------------------------------------------------------------------------

def split_clip_at(conn, position: str, track_type: str = "video", track_index: int = 0) -> Dict[str, Any]:
    """
    Split the clip at *position* into two pieces.

    Workaround: remember source info, delete original, re-append two halves.

    Returns dict with info about the two new clips.
    """
    frame = _record_frame_position(conn, position)
    item, ttype, tidx = find_clip_at_position(conn, frame, track_type, track_index)
    pre_count = _timeline_track_item_count(conn, ttype, tidx)
    src = _clip_source_info(item)

    clip_start = src["start"]
    clip_end = src["end"]
    left_offset = src["left_offset"]
    mpi = src["media_pool_item"]

    if frame <= clip_start or frame >= clip_end:
        raise APICallFailed(f"Split point {frame} is not inside clip ({clip_start}–{clip_end}).")

    if not mpi:
        raise APICallFailed("Cannot get MediaPoolItem for this clip — split not possible.")

    # Source frame offsets
    source_start = left_offset
    source_end = left_offset + (clip_end - clip_start)
    split_in_source = source_start + (frame - clip_start)

    # Delete original via timeline item deletion
    ok = conn.timeline.DeleteClips([item])
    if ok is False:
        # Fallback: try disabling (some DaVinci Resolve versions)
        raise APICallFailed("Failed to delete the original clip for split.")

    # Re-append two halves
    media_type = 1 if ttype == "video" else 2
    clip_a = {
        "mediaPoolItem": mpi,
        "startFrame": source_start,
        "endFrame": split_in_source,
        "recordFrame": clip_start,
        "trackIndex": tidx,
        "mediaType": media_type,
    }
    clip_b = {
        "mediaPoolItem": mpi,
        "startFrame": split_in_source,
        "endFrame": source_end,
        "recordFrame": frame,
        "trackIndex": tidx,
        "mediaType": media_type,
    }

    result = conn.media_pool.AppendToTimeline([clip_a, clip_b])
    if result is False:
        rollback_steps = [
            "Open the timeline and navigate to the original track/record range.",
            "Append the original source range back at the original record start frame.",
            "Delete any duplicate split halves if partial inserts were created.",
        ]
        raise APICallFailed(
            "AppendToTimeline failed when reinserting split halves.",
            details={
                "operation": "split_clip_at",
                "recovery": {
                    "original_clip": src["name"],
                    "record_start": clip_start,
                    "record_end": clip_end,
                    "source_start": source_start,
                    "source_end": source_end,
                    "split_frame": frame,
                    "track_type": ttype,
                    "track_index": tidx,
                    "rollback_instructions": rollback_steps,
                },
            },
        )
    post_count = _wait_for_split_item_count(conn, ttype, tidx, pre_count + 1)
    verification = {
        "status": "verified" if post_count >= pre_count + 1 else "failed",
        "track_type": ttype,
        "track_index": tidx,
        "pre_item_count": pre_count,
        "post_item_count": post_count,
        "expected_post_item_count": pre_count + 1,
    }
    if verification["status"] != "verified":
        set_verification_status("failed")
        raise APICallFailed(
            "Split did not produce the expected timeline item count.",
            details={
                "operation": "split_clip_at",
                "verification": verification,
                "split_at_frame": frame,
                "track_type": ttype,
                "track_index": tidx,
            },
        )

    set_verification_status("verified")

    return {
        "split_at_frame": frame,
        "split_at_tc": frames_to_timecode(frame, conn.fps),
        "clip_a": {"record_start": clip_start, "record_end": frame, "source_in": source_start, "source_out": split_in_source},
        "clip_b": {"record_start": frame, "record_end": clip_end, "source_in": split_in_source, "source_out": source_end},
        "verification": verification,
    }


def _timeline_track_item_count(conn, track_type: str, track_index: int) -> int:
    try:
        return len(conn.timeline.GetItemListInTrack(track_type, track_index) or [])
    except Exception:
        return 0


def _wait_for_split_item_count(
    conn,
    track_type: str,
    track_index: int,
    expected_count: int,
    *,
    timeout_s: float = 3.0,
) -> int:
    deadline = time.monotonic() + timeout_s
    latest = _timeline_track_item_count(conn, track_type, track_index)
    while time.monotonic() < deadline:
        if latest >= expected_count:
            return latest
        time.sleep(0.05)
        latest = _timeline_track_item_count(conn, track_type, track_index)
    return latest


# ---------------------------------------------------------------------------
# Delete Through Edit
# ---------------------------------------------------------------------------

def _timeline_candidate_frames(conn, frame: int) -> set[int]:
    frames = {int(frame)}
    try:
        timeline_start = int(conn.timeline.GetStartFrame())
    except Exception:
        timeline_start = 0
    if timeline_start:
        frames.add(int(frame) - timeline_start)
    return frames


def _media_pool_item_key(item: Any) -> tuple[str, str] | None:
    mpi = item.GetMediaPoolItem() if hasattr(item, "GetMediaPoolItem") else None
    if not mpi:
        return None
    for attr in ("GetUniqueId", "GetMediaId"):
        getter = getattr(mpi, attr, None)
        if callable(getter):
            try:
                value = getter()
            except Exception:
                value = None
            if value not in (None, ""):
                return (attr, str(value))
    if hasattr(mpi, "GetClipProperty"):
        try:
            props = mpi.GetClipProperty() or {}
        except Exception:
            props = {}
        if isinstance(props, dict):
            for key in ("File Path", "FileName", "Path"):
                value = props.get(key)
                if value not in (None, ""):
                    return (key, str(value))
    if hasattr(mpi, "GetName"):
        try:
            name = mpi.GetName()
        except Exception:
            name = None
        if name not in (None, ""):
            return ("name", str(name))
    return ("object", str(id(mpi)))


def _same_media_pool_item(left: Any, right: Any) -> bool:
    left_mpi = left.GetMediaPoolItem() if hasattr(left, "GetMediaPoolItem") else None
    right_mpi = right.GetMediaPoolItem() if hasattr(right, "GetMediaPoolItem") else None
    if left_mpi is not None and left_mpi is right_mpi:
        return True
    left_key = _media_pool_item_key(left)
    right_key = _media_pool_item_key(right)
    return left_key is not None and left_key == right_key


def _delete_clips_no_ripple(conn, items: list[Any]) -> bool:
    try:
        result = conn.timeline.DeleteClips(items, False)
    except TypeError:
        result = conn.timeline.DeleteClips(items)
    return result is not False


def _media_key_payload(key: tuple[str, str] | None) -> dict[str, str] | None:
    if key is None:
        return None
    return {"kind": key[0], "value": key[1]}


def _through_edit_candidate(
    left: Any,
    right: Any,
    track_type: str,
    track_index: int,
) -> dict[str, Any] | None:
    try:
        left_info = _clip_source_info(left)
        right_info = _clip_source_info(right)
    except Exception:
        return None

    left_end = int(left_info["end"])
    right_start = int(right_info["start"])
    if left_end == right_start:
        boundary = left_end
    elif left_end + 1 == right_start:
        boundary = right_start
    else:
        return None

    candidate: dict[str, Any] = {
        "left": left,
        "right": right,
        "track_type": track_type,
        "track_index": track_index,
        "boundary": boundary,
        "left_info": left_info,
        "right_info": right_info,
        "valid": True,
        "reason": None,
        "message": None,
        "details": {},
    }
    if not _same_media_pool_item(left, right):
        candidate.update(
            {
                "valid": False,
                "reason": "different_media",
                "message": "Edit point is not a through edit: adjacent items reference different media.",
                "details": {
                    "track_type": track_type,
                    "track_index": track_index,
                    "edit_frame": boundary,
                    "left_clip": left_info.get("name"),
                    "right_clip": right_info.get("name"),
                },
            }
        )
        return candidate

    left_source_end = int(left_info["source_end"])
    right_source_start = int(right_info["source_start"])
    if left_source_end != right_source_start and left_source_end + 1 != right_source_start:
        candidate.update(
            {
                "valid": False,
                "reason": "source_gap",
                "message": "Edit point is not a through edit: source ranges are not contiguous.",
                "details": {
                    "track_type": track_type,
                    "track_index": track_index,
                    "edit_frame": boundary,
                    "left_source_end": left_source_end,
                    "right_source_start": right_source_start,
                },
            }
        )
        return candidate

    return candidate


def _through_edit_candidates(
    conn,
    track_type: str = "video",
    track_index: int = 0,
) -> list[dict[str, Any]]:
    types_to_search = [track_type] if track_type else ["video", "audio"]
    candidates: list[dict[str, Any]] = []
    for ttype in types_to_search:
        count = conn.timeline.GetTrackCount(ttype) or 0
        start_idx = track_index if track_index else 1
        end_idx = (track_index + 1) if track_index else (count + 1)
        for idx in range(start_idx, end_idx):
            items = conn.timeline.GetItemListInTrack(ttype, idx) or []
            try:
                sorted_items = sorted(items, key=lambda item: int(item.GetStart()))
            except Exception:
                sorted_items = list(items)
            for left, right in zip(sorted_items, sorted_items[1:]):
                candidate = _through_edit_candidate(left, right, ttype, idx)
                if candidate is not None:
                    candidates.append(candidate)
    return candidates


def _candidate_distance(candidate: dict[str, Any], candidate_frames: set[int]) -> int:
    boundary = int(candidate["boundary"])
    return min(abs(boundary - int(frame)) for frame in candidate_frames)


def _raise_invalid_through_edit_candidate(candidate: dict[str, Any]) -> None:
    raise APICallFailed(
        str(candidate.get("message") or "Edit point is not a through edit."),
        details=dict(candidate.get("details") or {}),
    )


def _raise_ambiguous_through_edit(
    *,
    frame: int,
    track_type: str,
    track_index: int,
    candidates: list[dict[str, Any]],
    mode: str,
) -> None:
    raise APICallFailed(
        "Through edit target is ambiguous; specify --at closer to the edit point or set --track.",
        details={
            "frame": frame,
            "track_type": track_type,
            "track_index": track_index,
            "mode": mode,
            "candidates": [
                {
                    "track_type": candidate["track_type"],
                    "track_index": candidate["track_index"],
                    "edit_frame": candidate["boundary"],
                    "left_clip": candidate["left_info"].get("name"),
                    "right_clip": candidate["right_info"].get("name"),
                }
                for candidate in candidates
            ],
        },
    )


def _frame_inside(info: dict[str, Any], candidate_frames: set[int]) -> tuple[bool, int | None]:
    for candidate in sorted(candidate_frames):
        if int(info["start"]) <= int(candidate) < int(info["end"]):
            return True, int(candidate)
    return False, None


def _selection_for_candidate(
    candidate: dict[str, Any],
    *,
    requested_frame: int,
    candidate_frames: set[int],
    mode: str,
    containing_side: str | None = None,
    containing_frame: int | None = None,
) -> dict[str, Any]:
    distance = _candidate_distance(candidate, candidate_frames)
    payload = {
        "mode": mode,
        "requested_frame": int(requested_frame),
        "candidate_frames": sorted(int(frame) for frame in candidate_frames),
        "resolved_edit_frame": int(candidate["boundary"]),
        "distance_frames": int(distance),
        "track_type": candidate["track_type"],
        "track_index": candidate["track_index"],
    }
    if containing_side is not None:
        payload["containing_side"] = containing_side
    if containing_frame is not None:
        payload["containing_frame"] = int(containing_frame)
    return payload


def _resolve_through_edit_pair(
    conn,
    frame: int,
    track_type: str = "video",
    track_index: int = 0,
    *,
    tolerance_frames: int = 0,
) -> dict[str, Any]:
    candidate_frames = _timeline_candidate_frames(conn, frame)
    candidates = _through_edit_candidates(conn, track_type, track_index)

    boundary_matches = [
        {**candidate, "distance": _candidate_distance(candidate, candidate_frames)}
        for candidate in candidates
        if _candidate_distance(candidate, candidate_frames) <= tolerance_frames
    ]
    if boundary_matches:
        nearest_distance = min(int(candidate["distance"]) for candidate in boundary_matches)
        nearest = [candidate for candidate in boundary_matches if int(candidate["distance"]) == nearest_distance]
        if len(nearest) > 1:
            _raise_ambiguous_through_edit(
                frame=frame,
                track_type=track_type,
                track_index=track_index,
                candidates=nearest,
                mode="boundary_tolerance",
            )
        selected = nearest[0]
        if not selected.get("valid"):
            _raise_invalid_through_edit_candidate(selected)
        mode = "boundary_exact" if int(selected["distance"]) == 0 else "boundary_tolerance"
        selected["selection"] = _selection_for_candidate(
            selected,
            requested_frame=frame,
            candidate_frames=candidate_frames,
            mode=mode,
        )
        return selected

    inside_matches: list[dict[str, Any]] = []
    invalid_inside_matches: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, int, int]] = set()
    for candidate in candidates:
        for side in ("left", "right"):
            inside, containing_frame = _frame_inside(candidate[f"{side}_info"], candidate_frames)
            if not inside:
                continue
            key = (str(candidate["track_type"]), int(candidate["track_index"]), int(candidate["boundary"]))
            if key in seen_keys:
                continue
            seen_keys.add(key)
            matched = {
                **candidate,
                "selection": _selection_for_candidate(
                    candidate,
                    requested_frame=frame,
                    candidate_frames=candidate_frames,
                    mode="containing_clip_adjacent",
                    containing_side=side,
                    containing_frame=containing_frame,
                ),
            }
            if matched.get("valid"):
                inside_matches.append(matched)
            else:
                invalid_inside_matches.append(matched)

    if len(inside_matches) == 1:
        return inside_matches[0]
    if len(inside_matches) > 1:
        _raise_ambiguous_through_edit(
            frame=frame,
            track_type=track_type,
            track_index=track_index,
            candidates=inside_matches,
            mode="containing_clip_adjacent",
        )
    if len(invalid_inside_matches) == 1:
        _raise_invalid_through_edit_candidate(invalid_inside_matches[0])
    if len(invalid_inside_matches) > 1:
        _raise_ambiguous_through_edit(
            frame=frame,
            track_type=track_type,
            track_index=track_index,
            candidates=invalid_inside_matches,
            mode="containing_clip_adjacent",
        )

    raise ClipNotFound(
        f"No through edit found at frame {frame}.",
        details={
            "frame": frame,
            "track_type": track_type,
            "track_index": track_index,
            "tolerance_frames": tolerance_frames,
        },
    )


def _find_through_edit_pair(
    conn,
    frame: int,
    track_type: str = "video",
    track_index: int = 0,
    *,
    tolerance_frames: int = 0,
) -> tuple[Any, Any, str, int, int, Dict[str, Any], Dict[str, Any]]:
    resolved = _resolve_through_edit_pair(
        conn,
        frame,
        track_type,
        track_index,
        tolerance_frames=tolerance_frames,
    )
    return (
        resolved["left"],
        resolved["right"],
        resolved["track_type"],
        resolved["track_index"],
        resolved["boundary"],
        resolved["left_info"],
        resolved["right_info"],
    )


def _through_edit_readback_summary(item: Any) -> dict[str, Any]:
    try:
        info = _clip_source_info(item)
    except Exception:
        info = {}
        for key, attr in (("name", "GetName"), ("start", "GetStart"), ("end", "GetEnd"), ("duration", "GetDuration")):
            getter = getattr(item, attr, None)
            if callable(getter):
                try:
                    info[key] = int(getter()) if key in {"start", "end", "duration"} else getter()
                except Exception:
                    pass
    media_key = _media_pool_item_key(item)
    return {
        "name": info.get("name"),
        "record_start": info.get("start"),
        "record_end": info.get("end"),
        "duration": info.get("duration"),
        "source_start": info.get("source_start"),
        "source_end": info.get("source_end"),
        "media_key": _media_key_payload(media_key),
    }


def _build_through_edit_verification(
    conn,
    *,
    track_type: str,
    track_index: int,
    pre_count: int,
    expected_count: int,
    expected_media_key: tuple[str, str] | None,
    left_info: dict[str, Any],
    right_info: dict[str, Any],
    boundary: int,
    selection: dict[str, Any],
) -> dict[str, Any]:
    try:
        items = conn.timeline.GetItemListInTrack(track_type, track_index) or []
    except Exception as exc:
        return {
            "status": "failed",
            "track_type": track_type,
            "track_index": track_index,
            "pre_item_count": pre_count,
            "post_item_count": None,
            "expected_post_item_count": expected_count,
            "selection": selection,
            "checks": [
                {"name": "track_readback", "ok": False, "error": str(exc)},
            ],
        }

    summaries = [_through_edit_readback_summary(item) for item in items]
    post_count = len(summaries)
    expected_record_start = int(left_info["start"])
    expected_record_end = int(right_info["end"])
    expected_source_start = int(left_info["source_start"])
    expected_source_end = int(right_info["source_end"])

    record_matches = [
        summary
        for summary in summaries
        if summary.get("record_start") == expected_record_start
        and summary.get("record_end") == expected_record_end
    ]
    media_matches = [
        summary
        for summary in record_matches
        if expected_media_key is None or summary.get("media_key") == _media_key_payload(expected_media_key)
    ]
    source_matches = [
        summary
        for summary in media_matches
        if summary.get("source_start") == expected_source_start
        and summary.get("source_end") == expected_source_end
    ]
    boundary_items = [
        summary
        for summary in summaries
        if summary.get("record_start") == int(boundary) or summary.get("record_end") == int(boundary)
    ]
    checks = [
        {
            "name": "track_item_count_decreased",
            "ok": post_count == expected_count,
            "before": pre_count,
            "after": post_count,
            "expected": expected_count,
        },
        {
            "name": "merged_record_range",
            "ok": bool(record_matches),
            "expected": {"record_start": expected_record_start, "record_end": expected_record_end},
            "matches": record_matches,
        },
        {
            "name": "merged_media_identity",
            "ok": bool(media_matches),
            "expected_media_key": _media_key_payload(expected_media_key),
        },
        {
            "name": "merged_source_range",
            "ok": bool(source_matches),
            "expected": {"source_start": expected_source_start, "source_end": expected_source_end},
        },
        {
            "name": "old_boundary_removed",
            "ok": not boundary_items,
            "boundary": int(boundary),
            "matches": boundary_items,
        },
    ]
    return {
        "status": "verified" if all(check["ok"] for check in checks) else "failed",
        "track_type": track_type,
        "track_index": track_index,
        "pre_item_count": pre_count,
        "post_item_count": post_count,
        "expected_post_item_count": expected_count,
        "selection": selection,
        "checks": checks,
    }


def _wait_for_through_edit_verification(
    conn,
    *,
    track_type: str,
    track_index: int,
    pre_count: int,
    expected_count: int,
    expected_media_key: tuple[str, str] | None,
    left_info: dict[str, Any],
    right_info: dict[str, Any],
    boundary: int,
    selection: dict[str, Any],
    timeout_s: float = 3.0,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_s
    latest = _build_through_edit_verification(
        conn,
        track_type=track_type,
        track_index=track_index,
        pre_count=pre_count,
        expected_count=expected_count,
        expected_media_key=expected_media_key,
        left_info=left_info,
        right_info=right_info,
        boundary=boundary,
        selection=selection,
    )
    while time.monotonic() < deadline:
        if latest["status"] == "verified":
            return latest
        time.sleep(0.05)
        latest = _build_through_edit_verification(
            conn,
            track_type=track_type,
            track_index=track_index,
            pre_count=pre_count,
            expected_count=expected_count,
            expected_media_key=expected_media_key,
            left_info=left_info,
            right_info=right_info,
            boundary=boundary,
            selection=selection,
        )
    return latest


def delete_through_edit_at(
    conn,
    position: str,
    track_type: str = "video",
    track_index: int = 0,
    *,
    tolerance_frames: int = 0,
) -> Dict[str, Any]:
    """
    Remove a redundant edit between adjacent pieces of the same source clip.

    DaVinci Resolve does not expose the UI's "Delete Through Edit" command directly, so
    this emulates it by replacing two contiguous timeline items with one item
    that spans the same source and record range.
    """
    if tolerance_frames < 0:
        raise ValidationError(
            "Tolerance must be zero or greater.",
            details={"tolerance_frames": tolerance_frames},
            recoverability="not_applicable",
        )
    frame = _record_frame_position(conn, position)
    resolved = _resolve_through_edit_pair(
        conn,
        frame,
        track_type,
        track_index,
        tolerance_frames=tolerance_frames,
    )
    left = resolved["left"]
    right = resolved["right"]
    ttype = resolved["track_type"]
    tidx = resolved["track_index"]
    boundary = int(resolved["boundary"])
    left_info = resolved["left_info"]
    right_info = resolved["right_info"]
    selection = dict(resolved["selection"])
    pre_count = _timeline_track_item_count(conn, ttype, tidx)
    expected_media_key = _media_pool_item_key(left)
    mpi = left_info.get("media_pool_item")
    if not mpi:
        raise APICallFailed(
            "Cannot get MediaPoolItem for the through edit.",
            details={"track_type": ttype, "track_index": tidx, "edit_frame": boundary},
        )

    if not _delete_clips_no_ripple(conn, [left, right]):
        raise APICallFailed(
            "Failed to delete through-edit halves.",
            details={"track_type": ttype, "track_index": tidx, "edit_frame": boundary},
        )

    media_type = 1 if ttype == "video" else 2
    merged_clip = {
        "mediaPoolItem": mpi,
        "startFrame": int(left_info["source_start"]),
        "endFrame": int(right_info["source_end"]),
        "recordFrame": int(left_info["start"]),
        "trackIndex": tidx,
        "mediaType": media_type,
    }
    result = conn.media_pool.AppendToTimeline([merged_clip])
    if result is False or result is None or result == []:
        raise APICallFailed(
            "AppendToTimeline failed when reinserting merged through edit.",
            details={
                "operation": "delete_through_edit_at",
                "track_type": ttype,
                "track_index": tidx,
                "edit_frame": boundary,
                "merged_clip": {
                    "source_start": merged_clip["startFrame"],
                    "source_end": merged_clip["endFrame"],
                    "record_start": merged_clip["recordFrame"],
                },
            },
        )

    expected_count = max(0, pre_count - 1)
    verification = _wait_for_through_edit_verification(
        conn,
        track_type=ttype,
        track_index=tidx,
        pre_count=pre_count,
        expected_count=expected_count,
        expected_media_key=expected_media_key,
        left_info=left_info,
        right_info=right_info,
        boundary=boundary,
        selection=selection,
    )
    if verification["status"] != "verified":
        set_verification_status("failed")
        raise APICallFailed(
            "Delete-through-edit did not produce the expected timeline item count.",
            details={
                "operation": "delete_through_edit_at",
                "verification": verification,
                "edit_frame": boundary,
                "track_type": ttype,
                "track_index": tidx,
            },
        )

    set_verification_status("verified")
    return {
        "action": "delete_through_edit",
        "edit_frame": boundary,
        "edit_tc": frames_to_timecode(boundary, conn.fps),
        "track_type": ttype,
        "track_index": tidx,
        "selection": selection,
        "removed": [
            {
                "name": left_info.get("name"),
                "record_start": left_info["start"],
                "record_end": left_info["end"],
                "source_start": left_info["source_start"],
                "source_end": left_info["source_end"],
            },
            {
                "name": right_info.get("name"),
                "record_start": right_info["start"],
                "record_end": right_info["end"],
                "source_start": right_info["source_start"],
                "source_end": right_info["source_end"],
            },
        ],
        "merged": {
            "record_start": merged_clip["recordFrame"],
            "record_end": int(right_info["end"]),
            "source_start": merged_clip["startFrame"],
            "source_end": merged_clip["endFrame"],
        },
        "verification": verification,
    }


# ---------------------------------------------------------------------------
# Insert / Overwrite
# ---------------------------------------------------------------------------

def _find_media_pool_item_by_name(conn, name: str):
    """Find a MediaPoolItem in the pool by name (searches current folder recursively)."""
    root = conn.media_pool.GetRootFolder()
    return _search_folder(root, name)


def _search_folder(folder, name: str):
    clips = folder.GetClipList() or []
    for clip in clips:
        if clip.GetName() == name:
            return clip
    subfolders = folder.GetSubFolderList() or []
    for sf in subfolders:
        result = _search_folder(sf, name)
        if result:
            return result
    return None


def _parse_int_maybe(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(str(value).strip())
    except Exception:
        return None


def _parse_float_maybe(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        text = str(value).strip().replace(",", ".")
        if not text:
            return None
        if "/" in text:
            left, right = text.split("/", 1)
            denominator = float(right.strip())
            if denominator:
                return float(left.strip()) / denominator
        match = re.search(r"-?\d+(?:\.\d+)?", text)
        if not match:
            return None
        return float(match.group(0))
    except Exception:
        return None


def _round_frame_count(value: float) -> int:
    if value >= 0:
        return int(value + 0.5)
    return int(value - 0.5)


def _convert_frame_count(frame_count: int, *, from_fps: Optional[float], to_fps: Optional[float]) -> int:
    frames = int(frame_count)
    if frames == 0:
        return 0
    if not from_fps or not to_fps or from_fps <= 0 or to_fps <= 0:
        return max(0, frames)
    if abs(float(from_fps) - float(to_fps)) < 0.0001:
        return max(0, frames)
    converted = _round_frame_count(frames * float(to_fps) / float(from_fps))
    return max(1, converted) if frames > 0 else converted


def _timeline_to_source_frame_count(timeline_frames: int, *, source_fps: Optional[float], timeline_fps: float) -> int:
    return _convert_frame_count(timeline_frames, from_fps=timeline_fps, to_fps=source_fps)


def _source_to_timeline_frame_count(source_frames: int, *, source_fps: Optional[float], timeline_fps: float) -> int:
    return _convert_frame_count(source_frames, from_fps=source_fps, to_fps=timeline_fps)


def _media_pool_item_frame_rate(mpi: Any, fallback_fps: Optional[float] = None) -> Optional[float]:
    """Best-effort media/source frame rate from MediaPoolItem properties."""
    if not mpi or not hasattr(mpi, "GetClipProperty"):
        return fallback_fps
    getter = mpi.GetClipProperty
    keys = (
        "FPS",
        "Frame Rate",
        "Video Frame Rate",
        "Clip Frame Rate",
        "MediaFrameRate",
        "Camera FPS",
        "Camera Frame Rate",
    )
    props: Dict[str, Any] = {}
    try:
        raw_props = getter()
        props = raw_props if isinstance(raw_props, dict) else {}
    except Exception:
        props = {}

    for key in keys:
        parsed = _parse_float_maybe(props.get(key))
        if parsed and parsed > 0:
            return parsed

    for key in keys:
        try:
            parsed = _parse_float_maybe(getter(key))
        except Exception:
            parsed = None
        if parsed and parsed > 0:
            return parsed

    return fallback_fps


def _source_total_frames(mpi, fps: float) -> Optional[int]:
    """Best-effort source clip duration in frames from clip properties."""
    if not hasattr(mpi, "GetClipProperty"):
        return None
    props = mpi.GetClipProperty() or {}
    if not isinstance(props, dict):
        return None

    # Prefer explicit frame-count fields when available.
    for key in ("Frames", "DurationFrames", "SourceFrames"):
        parsed = _parse_int_maybe(props.get(key))
        if parsed is not None and parsed >= 0:
            return parsed

    dur = props.get("Duration")
    if dur is None:
        return None

    try:
        dur_s = str(dur).strip()
        if ":" in dur_s or dur_s.endswith(("f", "s")):
            return max(0, seconds_to_frames(parse_time_input(dur_s, fps), fps))
        parsed = _parse_int_maybe(dur_s)
        if parsed is not None and parsed >= 0:
            return parsed
    except Exception:
        return None

    return None


def _validate_source_bounds(
    *,
    clip_name: str,
    start_frame: Optional[int],
    end_frame: Optional[int],
    source_total_frames: Optional[int],
) -> None:
    """Validate source-domain in/out frame bounds when source duration is known."""
    if source_total_frames is None:
        return
    if start_frame is not None and start_frame > source_total_frames:
        raise InvalidTimeReference(
            "source in is out of source clip range.",
            details={
                "clip": clip_name,
                "startFrame": start_frame,
                "source_total_frames": source_total_frames,
            },
        )
    if end_frame is not None and end_frame > source_total_frames:
        raise InvalidTimeReference(
            "source out is out of source clip range.",
            details={
                "clip": clip_name,
                "endFrame": end_frame,
                "source_total_frames": source_total_frames,
            },
        )


def _summarize_timeline_item(item) -> Dict[str, Any]:
    row: Dict[str, Any] = {
        "name": item.GetName() if hasattr(item, "GetName") else None,
        "start": int(item.GetStart()) if hasattr(item, "GetStart") else None,
        "end": int(item.GetEnd()) if hasattr(item, "GetEnd") else None,
    }
    if row["start"] is not None and row["end"] is not None:
        row["duration"] = max(0, row["end"] - row["start"])
    elif hasattr(item, "GetDuration"):
        try:
            row["duration"] = int(item.GetDuration())
        except Exception:
            row["duration"] = None
    if hasattr(item, "GetMediaPoolItem"):
        try:
            mpi = item.GetMediaPoolItem()
            if mpi and hasattr(mpi, "GetName"):
                row["media_pool_item"] = mpi.GetName()
        except Exception:
            pass
    return row


def _timeline_track_snapshot(conn, track_index: int) -> Dict[str, Any]:
    timeline = getattr(conn, "timeline", None)
    items: List[Dict[str, Any]] = []
    track_count = 0
    if timeline and hasattr(timeline, "GetTrackCount"):
        try:
            track_count = int(timeline.GetTrackCount("video") or 0)
        except Exception:
            track_count = 0
    if timeline and hasattr(timeline, "GetItemListInTrack") and track_index > 0 and (track_count <= 0 or track_index <= track_count):
        try:
            raw_items = timeline.GetItemListInTrack("video", track_index) or []
        except Exception:
            raw_items = []
        items = [_summarize_timeline_item(item) for item in raw_items]
    return {
        "track_type": "video",
        "track_index": track_index,
        "track_count": track_count,
        "item_count": len(items),
        "items": items,
    }


def _expected_insert_duration(
    clip_info: Dict[str, Any],
    source_total_frames: Optional[int],
    *,
    source_fps: Optional[float] = None,
    timeline_fps: Optional[float] = None,
) -> Optional[int]:
    start = clip_info.get("startFrame")
    end = clip_info.get("endFrame")
    source_duration: Optional[int] = None
    if start is not None and end is not None:
        source_duration = max(0, int(end) - int(start))
    elif source_total_frames is not None:
        source_duration = max(0, int(source_total_frames) - int(start or 0))
    if source_duration is None:
        return None
    if timeline_fps:
        return _source_to_timeline_frame_count(source_duration, source_fps=source_fps, timeline_fps=float(timeline_fps))
    return source_duration


def _row_matches_clip(row: Dict[str, Any], clip_name: str) -> bool:
    target = str(clip_name or "").strip()
    for key in ("name", "media_pool_item"):
        value = row.get(key)
        if isinstance(value, str) and value.strip() == target:
            return True
    return False


def _find_inserted_row(
    rows: List[Dict[str, Any]],
    *,
    clip_name: str,
    record_frame: int,
    expected_duration: Optional[int],
) -> Optional[Dict[str, Any]]:
    candidates = [row for row in rows if _row_matches_clip(row, clip_name)]
    for row in candidates:
        if row.get("start") == record_frame:
            if expected_duration is None or row.get("duration") in (None, expected_duration):
                return row
    if expected_duration is not None:
        return None
    for row in candidates:
        start = row.get("start")
        end = row.get("end")
        if isinstance(start, int) and isinstance(end, int) and start <= record_frame < end:
            return row
    return candidates[-1] if candidates else None
