"""Read-only timeline layout planning helpers."""

from __future__ import annotations

import json
import re
from typing import Any

from ..errors import ValidationError
from ..utils.time_ref import parse_record_frame
from ..utils.timecode import parse_time_input, seconds_to_frames
from . import timeline_ops

_INT_RE = re.compile(r"^[+-]?\d+$")


def _parse_duration_frames(raw: str, *, fps: float, field: str) -> int:
    value = str(raw or "").strip()
    if not value:
        raise ValidationError(
            f"{field} must not be empty.",
            details={field: raw},
            recoverability="not_applicable",
        )
    try:
        if value.endswith("f"):
            frames = int(value[:-1].strip())
        elif _INT_RE.match(value):
            frames = int(value)
        else:
            frames = seconds_to_frames(parse_time_input(value, fps), fps)
    except Exception as exc:
        raise ValidationError(
            f"Cannot parse {field}.",
            details={field: raw, "fps": fps, "error": str(exc)},
            recoverability="not_applicable",
        ) from exc
    if frames < 0:
        raise ValidationError(
            f"{field} must be zero or greater.",
            details={field: raw, "resolved_frames": frames},
            recoverability="not_applicable",
        )
    return frames


def parse_candidate_stacks(
    raw: str | None,
    *,
    stack_size: int | None,
    min_track: int,
    max_track: int | None,
) -> list[list[int]]:
    """Parse explicit JSON stacks or generate contiguous stacks."""
    normalized_min = timeline_ops.validate_timeline_track_index(min_track)
    normalized_max = timeline_ops.validate_timeline_track_index(max_track) if max_track is not None else None
    if normalized_max is not None and normalized_max < normalized_min:
        raise ValidationError(
            "--max-track must be greater than or equal to --min-track.",
            details={"min_track": normalized_min, "max_track": normalized_max},
            recoverability="not_applicable",
        )

    if raw is not None:
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValidationError(
                "--candidate-stacks must be valid JSON.",
                details={"candidate_stacks": raw, "line": exc.lineno, "column": exc.colno},
                recoverability="not_applicable",
            ) from exc
        if not isinstance(parsed, list):
            raise ValidationError(
                "--candidate-stacks must be a JSON array of arrays.",
                details={"candidate_stacks": raw},
                recoverability="not_applicable",
            )
        stacks: list[list[int]] = []
        for candidate_index, stack in enumerate(parsed):
            if not isinstance(stack, list) or not stack:
                raise ValidationError(
                    "Each candidate stack must be a non-empty JSON array.",
                    details={"candidate_index": candidate_index, "stack": stack},
                    recoverability="not_applicable",
                )
            tracks = [timeline_ops.validate_timeline_track_index(track) for track in stack]
            if len(set(tracks)) != len(tracks):
                raise ValidationError(
                    "Candidate stack track indexes must be unique.",
                    details={"candidate_index": candidate_index, "tracks": tracks},
                    recoverability="not_applicable",
                )
            stacks.append(tracks)
        if not stacks:
            raise ValidationError(
                "--candidate-stacks must include at least one stack.",
                details={"candidate_stacks": raw},
                recoverability="not_applicable",
            )
        return stacks

    if stack_size is None:
        raise ValidationError(
            "Provide --candidate-stacks or --stack-size.",
            details={"candidate_stacks": raw, "stack_size": stack_size},
            recoverability="not_applicable",
        )
    normalized_size = timeline_ops.validate_timeline_track_index(stack_size)
    if normalized_max is None:
        raise ValidationError(
            "--max-track is required when generating stacks outside a timeline context.",
            details={"stack_size": normalized_size, "min_track": normalized_min, "max_track": max_track},
            recoverability="not_applicable",
        )
    last_start = normalized_max - normalized_size + 1
    if last_start < normalized_min:
        raise ValidationError(
            "No contiguous candidate stacks fit within the requested track range.",
            details={"stack_size": normalized_size, "min_track": normalized_min, "max_track": normalized_max},
            recoverability="not_applicable",
        )
    return [list(range(start, start + normalized_size)) for start in range(normalized_min, last_start + 1)]


def resolve_layout_range(
    conn,
    *,
    start_ref: str,
    end_ref: str | None,
    duration_ref: str | None,
) -> dict[str, int]:
    """Resolve a record-domain start/end or start/duration pair."""
    if end_ref is None and duration_ref is None:
        raise ValidationError(
            "Provide --end-frame or --duration.",
            details={"start_frame": start_ref, "end_frame": end_ref, "duration": duration_ref},
            recoverability="not_applicable",
        )
    if end_ref is not None and duration_ref is not None:
        raise ValidationError(
            "Provide either --end-frame or --duration, not both.",
            details={"start_frame": start_ref, "end_frame": end_ref, "duration": duration_ref},
            recoverability="not_applicable",
        )

    timeline_start = timeline_ops._timeline_start_frame(conn)
    start_frame = parse_record_frame(str(start_ref), conn.fps, timeline_start)
    if end_ref is not None:
        end_frame = parse_record_frame(str(end_ref), conn.fps, timeline_start)
        duration_frames = end_frame - start_frame
    else:
        duration_frames = _parse_duration_frames(str(duration_ref), fps=conn.fps, field="duration")
        end_frame = start_frame + duration_frames

    if end_frame <= start_frame:
        raise ValidationError(
            "Timeline layout end frame must be after start frame.",
            details={
                "start_frame": start_ref,
                "end_frame": end_ref,
                "duration": duration_ref,
                "resolved_start_frame": start_frame,
                "resolved_end_frame": end_frame,
            },
            recoverability="not_applicable",
        )
    return {
        "start_frame": int(start_frame),
        "end_frame": int(end_frame),
        "duration_frames": int(duration_frames),
    }


def _item_start_end(item: Any) -> tuple[int, int] | None:
    try:
        return int(item.GetStart()), int(item.GetEnd())
    except Exception:
        return None


def _blocking_item_descriptor(item: Any, *, track_type: str, track_index: int, padding_frames: int) -> dict[str, object]:
    bounds = _item_start_end(item)
    start_frame = bounds[0] if bounds else None
    end_frame = bounds[1] if bounds else None
    data: dict[str, object] = {
        "track_type": track_type,
        "track_index": track_index,
        "name": None,
        "start_frame": start_frame,
        "end_frame": end_frame,
        "duration_frames": None if start_frame is None or end_frame is None else end_frame - start_frame,
        "blocking_end_frame": None if end_frame is None else end_frame + padding_frames,
    }
    if hasattr(item, "GetName"):
        try:
            data["name"] = item.GetName()
        except Exception:
            pass
    return data


def collect_blocking_items(
    timeline,
    *,
    track_type: str,
    track_index: int,
    start_frame: int,
    end_frame: int,
    padding_frames: int,
) -> list[dict[str, object]]:
    """Collect items that overlap the requested range plus padding."""
    normalized_type = timeline_ops.normalize_timeline_track_type(track_type)
    normalized_index = timeline_ops.validate_timeline_track_index(track_index)
    items = timeline.GetItemListInTrack(normalized_type, normalized_index) or []
    requested_start = int(start_frame) - int(padding_frames)
    requested_end = int(end_frame) + int(padding_frames)
    blocking: list[dict[str, object]] = []
    for item in items:
        bounds = _item_start_end(item)
        if bounds is None:
            continue
        item_start, item_end = bounds
        if item_start < requested_end and item_end > requested_start:
            blocking.append(
                _blocking_item_descriptor(
                    item,
                    track_type=normalized_type,
                    track_index=normalized_index,
                    padding_frames=int(padding_frames),
                )
            )
    return blocking


def _timeline_track_count(timeline, track_type: str) -> int:
    try:
        return int(timeline.GetTrackCount(track_type) or 0)
    except Exception:
        return 0


def plan_free_stack(
    conn,
    *,
    timeline_name: str | None,
    track_type: str,
    start_ref: str,
    end_ref: str | None,
    duration_ref: str | None,
    candidate_stacks: list[list[int]],
    padding_ref: str,
    shift: bool,
    allow_missing_tracks: bool,
) -> dict[str, object]:
    """Plan the first free timeline stack without mutating DaVinci Resolve."""
    normalized_type = timeline_ops.normalize_timeline_track_type(track_type)
    if timeline_name:
        timeline_ops.switch_timeline(conn, name=timeline_name)

    target_timeline = timeline_ops._timeline_name(conn)
    range_info = resolve_layout_range(conn, start_ref=start_ref, end_ref=end_ref, duration_ref=duration_ref)
    padding_frames = _parse_duration_frames(padding_ref, fps=conn.fps, field="padding")
    track_count = _timeline_track_count(conn.timeline, normalized_type)

    candidates: list[dict[str, object]] = []
    first_available: dict[str, object] | None = None
    best_suggestion: dict[str, object] | None = None
    for candidate_index, stack in enumerate(candidate_stacks):
        tracks = [timeline_ops.validate_timeline_track_index(track) for track in stack]
        missing_tracks = [track for track in tracks if track > track_count]
        track_exists = not missing_tracks
        blocking_items: list[dict[str, object]] = []
        if not missing_tracks or allow_missing_tracks:
            for track in tracks:
                if track <= track_count:
                    blocking_items.extend(
                        collect_blocking_items(
                            conn.timeline,
                            track_type=normalized_type,
                            track_index=track,
                            start_frame=range_info["start_frame"],
                            end_frame=range_info["end_frame"],
                            padding_frames=padding_frames,
                        )
                    )

        available = (not blocking_items) and (track_exists or allow_missing_tracks)
        requires_track_creation = bool(missing_tracks)
        suggested_start_frame = None
        suggested_end_frame = None
        if blocking_items:
            blocking_ends = [
                int(item["blocking_end_frame"])
                for item in blocking_items
                if item.get("blocking_end_frame") is not None
            ]
            if blocking_ends:
                suggested_start_frame = max(blocking_ends)
                suggested_end_frame = suggested_start_frame + range_info["duration_frames"]

        candidate: dict[str, object] = {
            "candidate_index": candidate_index,
            "tracks": tracks,
            "available": available,
            "track_exists": track_exists,
            "missing_tracks": missing_tracks,
            "requires_track_creation": requires_track_creation,
            "blocking_items": blocking_items,
        }
        if suggested_start_frame is not None:
            candidate["suggested_start_frame"] = suggested_start_frame
            candidate["suggested_end_frame"] = suggested_end_frame
        candidates.append(candidate)

        if available and first_available is None:
            first_available = candidate
        if suggested_start_frame is not None and (best_suggestion is None or suggested_start_frame < int(best_suggestion["start_frame"])):
            best_suggestion = {
                "tracks": tracks,
                "candidate_index": candidate_index,
                "start_frame": suggested_start_frame,
                "end_frame": suggested_end_frame,
                "requires_track_creation": requires_track_creation,
            }

    selected: dict[str, object] | None
    ready: bool
    message: str
    if first_available is not None:
        selected = {
            "tracks": first_available["tracks"],
            "candidate_index": first_available["candidate_index"],
            "start_frame": range_info["start_frame"],
            "end_frame": range_info["end_frame"],
            "shifted": False,
            "requires_track_creation": first_available["requires_track_creation"],
        }
        ready = True
        message = "Selected free timeline stack."
    elif shift and best_suggestion is not None:
        selected = {
            "tracks": best_suggestion["tracks"],
            "candidate_index": best_suggestion["candidate_index"],
            "start_frame": best_suggestion["start_frame"],
            "end_frame": best_suggestion["end_frame"],
            "shifted": True,
            "shift_reason": "after_blocking_item",
            "requires_track_creation": best_suggestion["requires_track_creation"],
        }
        ready = True
        message = "Selected shifted timeline stack."
    else:
        selected = None
        ready = False
        message = "No free timeline stack found."

    return {
        "action": "timeline.layout.free_stack",
        "changed": False,
        "target": {"kind": "timeline", "name": target_timeline},
        "track_type": normalized_type,
        "track_count": track_count,
        "requested": {
            **range_info,
            "padding_frames": padding_frames,
        },
        "selected": selected,
        "ready": ready,
        "suggested": best_suggestion,
        "candidates": candidates,
        "message": message,
    }
