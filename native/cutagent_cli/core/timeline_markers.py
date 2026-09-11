"""Batch timeline marker helpers."""

from __future__ import annotations

from typing import Any

from ..errors import APICallFailed, ValidationError
from ..output import set_recoverability, set_verification_status
from ..utils.time_ref import parse_record_frame
from ..utils.timecode import parse_time_input, seconds_to_frames
from . import timeline_ops

VALID_MARKER_COLORS = {
    "Blue",
    "Cyan",
    "Green",
    "Yellow",
    "Red",
    "Pink",
    "Purple",
    "Fuchsia",
    "Rose",
    "Lavender",
    "Sky",
    "Mint",
    "Lemon",
    "Sand",
    "Cocoa",
    "Cream",
}

MARKER_COLOR_ALIASES = {
    "orange": "Yellow",
    "amber": "Yellow",
    "gold": "Yellow",
    "teal": "Cyan",
    "magenta": "Pink",
    "violet": "Purple",
}


def normalize_timeline_marker_color(color: Any) -> str:
    raw = str(color or "").strip()
    if not raw:
        return "Blue"
    if raw in VALID_MARKER_COLORS:
        return raw
    return MARKER_COLOR_ALIASES.get(raw.lower(), "Blue")


def _timeline_start_frame(conn: Any, *, timeline: Any | None = None) -> int:
    current_timeline = timeline if timeline is not None else getattr(conn, "timeline", None)
    if current_timeline is not None and hasattr(current_timeline, "GetStartFrame"):
        try:
            return int(current_timeline.GetStartFrame())
        except Exception:
            pass
    return int(getattr(conn, "start_frame", 0) or 0)


def resolve_timeline_context(
    conn: Any,
    *,
    timeline_name: str | None = None,
    activate: bool = False,
) -> dict[str, Any]:
    normalized_name = str(timeline_name or "").strip()
    if normalized_name:
        project = getattr(conn, "project", None)
        if project is None:
            raise APICallFailed("DaVinci Resolve project handle is not available for timeline marker batch.")
        try:
            count = int(project.GetTimelineCount() or 0)
        except Exception:
            count = 0
        for index in range(1, count + 1):
            timeline = project.GetTimelineByIndex(index)
            name = timeline.GetName() if timeline and hasattr(timeline, "GetName") else None
            if name != normalized_name:
                continue
            activation = None
            if activate:
                activation = timeline_ops.switch_timeline(conn, name=normalized_name, return_details=True)
                timeline = getattr(conn, "timeline", None)
            return {
                "timeline": timeline,
                "timeline_name": normalized_name,
                "timeline_index": index,
                "activation": activation,
            }
        raise APICallFailed("Timeline not found.", details={"timeline_name": normalized_name})

    timeline = getattr(conn, "timeline", None)
    if timeline is None:
        raise APICallFailed("No active timeline is available for timeline marker batch.")
    return {
        "timeline": timeline,
        "timeline_name": timeline.GetName() if hasattr(timeline, "GetName") else None,
        "timeline_index": None,
        "activation": None,
    }


def _first_present(raw: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in raw:
            return raw[key]
    return None


def _coerce_int(value: Any, *, field: str, index: int) -> int:
    if isinstance(value, bool):
        raise ValidationError(
            f"{field} must be an integer.",
            details={"index": index, field: value},
            recoverability="not_applicable",
        )
    try:
        return int(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise ValidationError(
            f"{field} must be an integer.",
            details={"index": index, field: value},
            recoverability="not_applicable",
        ) from exc


def _coerce_float(value: Any, *, field: str, index: int) -> float:
    if isinstance(value, bool):
        raise ValidationError(
            f"{field} must be numeric seconds.",
            details={"index": index, field: value},
            recoverability="not_applicable",
        )
    try:
        return float(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise ValidationError(
            f"{field} must be numeric seconds.",
            details={"index": index, field: value},
            recoverability="not_applicable",
        ) from exc


def _normalize_duration(value: Any, *, index: int) -> int:
    if value is None:
        return 1
    return max(1, _coerce_int(value, field="duration_frames", index=index))


def _position_to_marker_frame(value: Any, *, fps: float, index: int) -> int:
    raw = str(value or "").strip()
    if not raw:
        raise ValidationError(
            "Marker batch position must not be empty.",
            details={"index": index, "position": value},
            recoverability="not_applicable",
        )
    try:
        seconds = parse_time_input(raw, fps)
    except Exception as exc:
        raise ValidationError(
            "Marker batch position could not be parsed.",
            details={"index": index, "position": value, "fps": fps},
            recoverability="not_applicable",
        ) from exc
    return seconds_to_frames(seconds, fps)


def _record_ref_to_marker_frame(value: Any, *, fps: float, timeline_start_frame: int, field: str, index: int) -> int:
    try:
        record_frame = parse_record_frame(str(value).strip(), fps, timeline_start_frame)
    except Exception as exc:
        raise ValidationError(
            f"{field} could not be parsed as a record-domain reference.",
            details={"index": index, field: value, "fps": fps, "timeline_start_frame": timeline_start_frame},
            recoverability="not_applicable",
        ) from exc
    return int(record_frame) - int(timeline_start_frame)


def _absolute_record_frame_to_marker_frame(value: Any, *, timeline_start_frame: int, field: str, index: int) -> int:
    return _coerce_int(value, field=field, index=index) - int(timeline_start_frame)


def _resolve_range_bounds(raw: dict[str, Any], *, fps: float, timeline_start_frame: int, index: int) -> tuple[int, int] | None:
    raw_start = _first_present(raw, "start_frame")
    raw_end = _first_present(raw, "end_frame")
    if raw_start is not None or raw_end is not None:
        if raw_start is None or raw_end is None:
            raise ValidationError(
                "Marker batch frame ranges require both start_frame and end_frame.",
                details={"index": index, "entry": raw},
                recoverability="not_applicable",
            )
        return (
            _coerce_int(raw_start, field="start_frame", index=index),
            _coerce_int(raw_end, field="end_frame", index=index),
        )

    record_start_frame = _first_present(raw, "record_start_frame")
    record_end_frame = _first_present(raw, "record_end_frame")
    if record_start_frame is not None or record_end_frame is not None:
        if record_start_frame is None or record_end_frame is None:
            raise ValidationError(
                "Marker batch record frame ranges require both record_start_frame and record_end_frame.",
                details={"index": index, "entry": raw},
                recoverability="not_applicable",
            )
        return (
            _absolute_record_frame_to_marker_frame(
                record_start_frame,
                timeline_start_frame=timeline_start_frame,
                field="record_start_frame",
                index=index,
            ),
            _absolute_record_frame_to_marker_frame(
                record_end_frame,
                timeline_start_frame=timeline_start_frame,
                field="record_end_frame",
                index=index,
            ),
        )

    record_start = _first_present(raw, "record_start")
    record_end = _first_present(raw, "record_end")
    if record_start is not None or record_end is not None:
        if record_start is None or record_end is None:
            raise ValidationError(
                "Marker batch record ranges require both record_start and record_end.",
                details={"index": index, "entry": raw},
                recoverability="not_applicable",
            )
        return (
            _record_ref_to_marker_frame(
                record_start,
                fps=fps,
                timeline_start_frame=timeline_start_frame,
                field="record_start",
                index=index,
            ),
            _record_ref_to_marker_frame(
                record_end,
                fps=fps,
                timeline_start_frame=timeline_start_frame,
                field="record_end",
                index=index,
            ),
        )

    seconds_start = _first_present(raw, "start")
    seconds_end = _first_present(raw, "end")
    if seconds_start is not None or seconds_end is not None:
        if seconds_start is None or seconds_end is None:
            raise ValidationError(
                "Marker batch second ranges require both start and end.",
                details={"index": index, "entry": raw},
                recoverability="not_applicable",
            )
        return (
            seconds_to_frames(max(0.0, _coerce_float(seconds_start, field="start", index=index)), fps),
            seconds_to_frames(max(0.0, _coerce_float(seconds_end, field="end", index=index)), fps),
        )
    return None


def normalize_marker_batch_entries(
    entries: list[dict[str, Any]],
    *,
    fps: float,
    timeline_start_frame: int,
    default_color: str = "Blue",
    prefix: str = "",
    default_title: str | None = None,
) -> list[dict[str, Any]]:
    normalized_default_color = normalize_timeline_marker_color(default_color)
    normalized_entries: list[dict[str, Any]] = []
    for index, raw in enumerate(entries):
        position = _first_present(raw, "position")
        range_bounds = _resolve_range_bounds(
            raw,
            fps=float(fps),
            timeline_start_frame=int(timeline_start_frame),
            index=index,
        )
        if position is not None and range_bounds is not None:
            raise ValidationError(
                "Marker batch entries must use either position or a start/end range, not both.",
                details={"index": index, "entry": raw},
                recoverability="not_applicable",
            )
        if position is not None:
            requested_frame = _position_to_marker_frame(position, fps=float(fps), index=index)
            duration_frames = _normalize_duration(
                _first_present(raw, "duration_frames", "duration"),
                index=index,
            )
        elif range_bounds is not None:
            requested_frame = int(range_bounds[0])
            end_frame = int(range_bounds[1])
            if end_frame < requested_frame:
                raise ValidationError(
                    "Marker batch range end must not be before start.",
                    details={"index": index, "start_frame": requested_frame, "end_frame": end_frame},
                    recoverability="not_applicable",
                )
            duration_frames = max(1, end_frame - requested_frame)
        else:
            raise ValidationError(
                "Marker batch entries require position or a supported range.",
                details={"index": index, "entry": raw},
                recoverability="not_applicable",
            )

        if requested_frame < 0:
            raise ValidationError(
                "Marker batch frame must not be negative.",
                details={"index": index, "requested_frame": requested_frame},
                recoverability="not_applicable",
            )

        requested_color = raw.get("color")
        color = normalize_timeline_marker_color(requested_color if requested_color is not None else normalized_default_color)
        title_base = (
            default_title
            if default_title is not None
            else raw["title"]
            if "title" in raw
            else raw.get("label") or raw.get("reason") or "Marker"
        )
        title = f"{prefix}{title_base}"
        note = raw["note"] if "note" in raw else raw.get("sentence") or raw.get("reason") or title

        normalized_entries.append(
            {
                "index": index,
                "requested_frame": requested_frame,
                "duration_frames": duration_frames,
                "requested_color": requested_color,
                "color": color,
                "name": title,
                "note": note,
                "shifted": False,
                "shifted_by_frames": 0,
                "kind": raw.get("kind"),
                "label": raw.get("label"),
                "reason": raw.get("reason"),
                "sentence": raw.get("sentence"),
                "raw": dict(raw),
            }
        )
    return normalized_entries


def _read_markers(timeline: Any) -> dict[int, dict[str, Any]]:
    getter = getattr(timeline, "GetMarkers", None)
    if not callable(getter):
        raise APICallFailed("Timeline marker APIs are not available in this DaVinci Resolve runtime.")
    try:
        raw_markers = getter() or {}
    except Exception as exc:
        raise APICallFailed("Failed to read timeline markers.", details={"error": str(exc)}) from exc

    markers: dict[int, dict[str, Any]] = {}
    for key, value in raw_markers.items():
        try:
            markers[int(key)] = dict(value or {})
        except Exception:
            continue
    return markers


def plan_timeline_marker_batch(
    conn: Any,
    *,
    entries: list[dict[str, Any]],
    timeline_name: str | None = None,
    default_color: str = "Blue",
    prefix: str = "",
    default_title: str | None = None,
    shift_occupied: bool = True,
) -> dict[str, Any]:
    timeline_context = resolve_timeline_context(conn, timeline_name=timeline_name, activate=False)
    timeline = timeline_context["timeline"]
    if timeline is None:
        raise APICallFailed("No target timeline is available for timeline marker batch.")
    normalized_entries = normalize_marker_batch_entries(
        entries,
        fps=float(getattr(conn, "fps", 24.0) or 24.0),
        timeline_start_frame=_timeline_start_frame(conn, timeline=timeline),
        default_color=default_color,
        prefix=prefix,
        default_title=default_title,
    )
    existing_markers = _read_markers(timeline)
    occupied = set(existing_markers.keys())
    planned_markers: list[dict[str, Any]] = []
    collisions: list[dict[str, Any]] = []
    shifted_count = 0
    for entry in normalized_entries:
        planned = dict(entry)
        actual_frame = int(entry["requested_frame"])
        if shift_occupied:
            while actual_frame in occupied:
                actual_frame += 1
            if actual_frame != int(entry["requested_frame"]):
                planned["shifted"] = True
                planned["shifted_by_frames"] = actual_frame - int(entry["requested_frame"])
                shifted_count += 1
            planned["actual_frame"] = actual_frame
            occupied.add(actual_frame)
        else:
            if actual_frame in occupied:
                collisions.append(
                    {
                        "index": int(entry["index"]),
                        "requested_frame": int(entry["requested_frame"]),
                        "reason": "occupied",
                    }
                )
            planned["actual_frame"] = actual_frame
            occupied.add(actual_frame)
        planned_markers.append(planned)

    preflight = {
        "requested_count": len(normalized_entries),
        "existing_marker_count": len(existing_markers),
        "shift_occupied": bool(shift_occupied),
        "ready": not collisions,
        "shifted_count": shifted_count,
        "collisions": collisions,
        "existing_frames": sorted(existing_markers.keys()),
        "planned_markers": [
            {
                "index": int(marker["index"]),
                "requested_frame": int(marker["requested_frame"]),
                "actual_frame": int(marker["actual_frame"]),
                "shifted": bool(marker["shifted"]),
                "shifted_by_frames": int(marker["shifted_by_frames"]),
                "duration_frames": int(marker["duration_frames"]),
                "requested_color": marker["requested_color"],
                "color": marker["color"],
                "name": marker["name"],
                "note": marker["note"],
            }
            for marker in planned_markers
        ],
    }
    return {
        "action": "timeline.marker.batch",
        "timeline_name": timeline_context["timeline_name"],
        "timeline_index": timeline_context["timeline_index"],
        "default_color": normalized_default_color if (normalized_default_color := normalize_timeline_marker_color(default_color)) else "Blue",
        "prefix": prefix,
        "shift_occupied": bool(shift_occupied),
        "entries": planned_markers,
        "preflight": preflight,
    }


def _markers_equal(expected: dict[str, Any], actual: dict[str, Any]) -> bool:
    return (
        actual.get("color") == expected["color"]
        and actual.get("name", "") == expected["name"]
        and actual.get("note", "") == expected["note"]
        and int(actual.get("duration", 1) or 1) == int(expected["duration_frames"])
    )


def apply_timeline_marker_batch(
    conn: Any,
    *,
    entries: list[dict[str, Any]],
    timeline_name: str | None = None,
    default_color: str = "Blue",
    prefix: str = "",
    default_title: str | None = None,
    shift_occupied: bool = True,
) -> dict[str, Any]:
    plan = plan_timeline_marker_batch(
        conn,
        entries=entries,
        timeline_name=timeline_name,
        default_color=default_color,
        prefix=prefix,
        default_title=default_title,
        shift_occupied=shift_occupied,
    )
    preflight = plan["preflight"]
    if not preflight["ready"]:
        raise ValidationError(
            "Timeline marker batch preflight failed.",
            details={
                **preflight,
                "reason": "timeline_marker_batch_preflight_failed",
                "created_count": 0,
                "failed_count": 0,
            },
            recoverability="not_applicable",
        )

    timeline_context = resolve_timeline_context(conn, timeline_name=timeline_name, activate=bool(timeline_name))
    timeline = timeline_context["timeline"]
    if timeline is None:
        raise APICallFailed("No target timeline is available for timeline marker batch.")

    results: list[dict[str, Any]] = []
    created_count = 0
    failed_count = 0
    for entry in plan["entries"]:
        actual_frame = int(entry["actual_frame"])
        result: dict[str, Any] = {
            "index": int(entry["index"]),
            "requested_frame": int(entry["requested_frame"]),
            "actual_frame": actual_frame,
            "shifted": bool(entry["shifted"]),
            "shifted_by_frames": int(entry["shifted_by_frames"]),
            "duration_frames": int(entry["duration_frames"]),
            "requested_color": entry["requested_color"],
            "color": entry["color"],
            "name": entry["name"],
            "note": entry["note"],
            "verified": False,
        }
        api_result = timeline.AddMarker(
            actual_frame,
            entry["color"],
            entry["name"],
            entry["note"],
            int(entry["duration_frames"]),
        )
        result["api_result"] = api_result
        if api_result in (False, None):
            result["status"] = "failed"
            result["error"] = "add_marker_returned_false"
            failed_count += 1
            results.append(result)
            break
        created_count += 1
        result["status"] = "created"
        results.append(result)

    markers_after = _read_markers(timeline)
    for result in results:
        if result["status"] == "failed":
            continue
        marker = markers_after.get(int(result["actual_frame"]))
        if marker and _markers_equal(result, marker):
            result["verified"] = True
            result["status"] = "verified"
            result["readback"] = {
                "color": marker.get("color"),
                "name": marker.get("name"),
                "note": marker.get("note"),
                "duration": int(marker.get("duration", 1) or 1),
            }
        else:
            result["status"] = "failed"
            result["error"] = "marker_readback_mismatch"
            result["readback"] = marker
            failed_count += 1
            created_count -= 1

    verification_status = "verified" if failed_count == 0 else "failed"
    set_verification_status(verification_status)
    set_recoverability("not_applicable" if verification_status == "verified" else "manual")
    return {
        "action": "timeline.marker.batch",
        "timeline_name": timeline_context["timeline_name"],
        "default_color": normalize_timeline_marker_color(default_color),
        "prefix": prefix,
        "shift_occupied": bool(shift_occupied),
        "requested_count": len(plan["entries"]),
        "created_count": created_count,
        "failed_count": failed_count,
        "preflight": preflight,
        "markers": results,
        "verification": {"status": verification_status},
    }
