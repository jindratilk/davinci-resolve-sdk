"""Batch timeline clip-color helpers."""

from __future__ import annotations

from typing import Any

from ..errors import APICallFailed, CapabilityNegotiationFailed, ValidationError
from .clip_ops import normalize_clip_color
from . import timeline_ops

_CLEAR_COLOR_VALUES = {"", "clear", "none", "default", "null"}
_VALID_TRACK_TYPES = {"video", "audio", "all"}


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


def _coerce_ms(value: Any, *, field: str, index: int) -> float:
    if isinstance(value, bool):
        raise ValidationError(
            f"{field} must be numeric milliseconds.",
            details={"index": index, field: value},
            recoverability="not_applicable",
        )
    try:
        return float(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise ValidationError(
            f"{field} must be numeric milliseconds.",
            details={"index": index, field: value},
            recoverability="not_applicable",
        ) from exc


def normalize_requested_clip_color(value: Any) -> tuple[str | None, bool]:
    if value is None:
        return None, True
    normalized = str(value).strip()
    if normalized.lower() in _CLEAR_COLOR_VALUES:
        return None, True
    return normalize_clip_color(normalized), False


def validate_batch_entry_colors(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    validated: list[dict[str, Any]] = []
    for index, raw in enumerate(entries):
        color_value = _first_present(raw, "color", "clip_color", "timeline_clip_color")
        if color_value is None and not any(key in raw for key in ("color", "clip_color", "timeline_clip_color")):
            raise ValidationError(
                "Timeline clip-color batch entries require color, clip_color, or timeline_clip_color.",
                details={"index": index, "entry": raw},
                recoverability="not_applicable",
            )
        normalized_color, clear = normalize_requested_clip_color(color_value)
        validated.append(
            {
                "index": index,
                "raw": dict(raw),
                "normalized_color": normalized_color,
                "clear": clear,
            }
        )
    return validated


def _resolve_frame_bounds(raw: dict[str, Any], *, index: int, fps: float, timeline_start_frame: int) -> tuple[int, int]:
    frame_start = _first_present(
        raw,
        "start_frame",
        "output_start_frame",
        "record_start_frame",
        "start",
    )
    frame_end = _first_present(
        raw,
        "end_frame",
        "output_end_frame",
        "record_end_frame",
        "end",
    )
    ms_start = _first_present(raw, "output_start_ms", "start_ms")
    ms_end = _first_present(raw, "output_end_ms", "end_ms")
    using_frame_bounds = frame_start is not None or frame_end is not None
    using_ms_bounds = ms_start is not None or ms_end is not None
    if using_frame_bounds and using_ms_bounds:
        raise ValidationError(
            "Use either frame bounds or millisecond bounds for a timeline clip-color batch entry, not both.",
            details={"index": index, "entry": raw},
            recoverability="not_applicable",
        )
    if using_frame_bounds:
        if frame_start is None or frame_end is None:
            raise ValidationError(
                "Frame-bound timeline clip-color entries require both start and end values.",
                details={"index": index, "entry": raw},
                recoverability="not_applicable",
            )
        start_frame = _coerce_int(frame_start, field="start_frame", index=index)
        end_frame = _coerce_int(frame_end, field="end_frame", index=index)
    elif using_ms_bounds:
        if ms_start is None or ms_end is None:
            raise ValidationError(
                "Millisecond timeline clip-color entries require both start and end values.",
                details={"index": index, "entry": raw},
                recoverability="not_applicable",
            )
        start_frame = int(round((_coerce_ms(ms_start, field="start_ms", index=index) / 1000.0) * fps)) + timeline_start_frame
        end_frame = int(round((_coerce_ms(ms_end, field="end_ms", index=index) / 1000.0) * fps)) + timeline_start_frame
    else:
        raise ValidationError(
            "Timeline clip-color batch entries require frame or millisecond bounds.",
            details={"index": index, "entry": raw},
            recoverability="not_applicable",
        )
    if end_frame <= start_frame:
        raise ValidationError(
            "Timeline clip-color batch entry end must be after start.",
            details={"index": index, "start_frame": start_frame, "end_frame": end_frame},
            recoverability="not_applicable",
        )
    return start_frame, end_frame


def normalize_batch_entries(
    entries: list[dict[str, Any]],
    *,
    fps: float,
    timeline_start_frame: int,
) -> list[dict[str, Any]]:
    color_entries = validate_batch_entry_colors(entries)
    normalized: list[dict[str, Any]] = []
    for entry in color_entries:
        raw = entry["raw"]
        index = int(entry["index"])
        start_frame, end_frame = _resolve_frame_bounds(
            raw,
            index=index,
            fps=float(fps),
            timeline_start_frame=int(timeline_start_frame),
        )
        normalized.append(
            {
                "index": index,
                "start_frame": start_frame,
                "end_frame": end_frame,
                "color": entry["normalized_color"],
                "clear": bool(entry["clear"]),
                "kind": raw.get("kind"),
                "annotation_kind": raw.get("annotation_kind"),
                "label": raw.get("label"),
                "reason": raw.get("reason"),
                "raw": raw,
            }
        )
    return normalized


def _read_timeline_bound(item: Any, attr_name: str) -> int:
    getter = getattr(item, attr_name, None)
    if not callable(getter):
        raise APICallFailed(
            f"Timeline item does not expose {attr_name}.",
            details={"timeline_item": getattr(item, "GetName", lambda: None)()},
        )
    try:
        return int(getter(False))
    except TypeError:
        return int(getter())
    except Exception:
        return int(getter())


def normalize_track_type(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized not in _VALID_TRACK_TYPES:
        raise ValidationError(
            "Track type must be one of: video, audio, all.",
            details={"track_type": value, "allowed": sorted(_VALID_TRACK_TYPES)},
            recoverability="not_applicable",
        )
    return normalized


def _selected_track_specs(timeline: Any, *, track_type: str, track_index: int, all_tracks: bool) -> list[tuple[str, int]]:
    normalized_type = normalize_track_type(track_type)
    if not all_tracks and int(track_index) < 1:
        raise ValidationError(
            "Track index must be 1 or greater.",
            details={"track_index": track_index},
            recoverability="not_applicable",
        )
    track_types = ("video", "audio") if normalized_type == "all" else (normalized_type,)
    specs: list[tuple[str, int]] = []
    for current_type in track_types:
        try:
            count = int(timeline.GetTrackCount(current_type) or 0)
        except Exception:
            count = 0
        if all_tracks:
            specs.extend((current_type, index) for index in range(1, count + 1))
            continue
        if count and track_index > count:
            raise ValidationError(
                "Track index is out of range for the target timeline.",
                details={"track_type": current_type, "track_index": track_index, "track_count": count},
                recoverability="not_applicable",
            )
        specs.append((current_type, int(track_index)))
    return specs


def collect_timeline_items(
    timeline: Any,
    *,
    track_type: str,
    track_index: int,
    all_tracks: bool,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for current_type, current_index in _selected_track_specs(
        timeline,
        track_type=track_type,
        track_index=track_index,
        all_tracks=all_tracks,
    ):
        items = list(timeline.GetItemListInTrack(current_type, current_index) or [])
        for item in items:
            color = None
            getter = getattr(item, "GetClipColor", None)
            if callable(getter):
                try:
                    color = getter()
                except Exception:
                    color = None
            rows.append(
                {
                    "item": item,
                    "name": item.GetName() if hasattr(item, "GetName") else None,
                    "track_type": current_type,
                    "track_index": current_index,
                    "start_frame": _read_timeline_bound(item, "GetStart"),
                    "end_frame": _read_timeline_bound(item, "GetEnd"),
                    "current_color": color,
                }
            )
    rows.sort(key=lambda row: (row["start_frame"], row["end_frame"], row["track_type"], row["track_index"]))
    return rows


def _duplicate_bounds(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_bounds: dict[tuple[int, int], list[dict[str, Any]]] = {}
    for row in rows:
        bounds = (int(row["start_frame"]), int(row["end_frame"]))
        by_bounds.setdefault(bounds, []).append(row)
    duplicates: list[dict[str, Any]] = []
    for (start_frame, end_frame), entries in sorted(by_bounds.items()):
        if len(entries) <= 1:
            continue
        duplicates.append(
            {
                "start_frame": start_frame,
                "end_frame": end_frame,
                "count": len(entries),
            }
        )
    return duplicates


def _serialize_expected(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "index": int(entry["index"]),
            "start_frame": int(entry["start_frame"]),
            "end_frame": int(entry["end_frame"]),
            "color": entry["color"],
            "clear": bool(entry["clear"]),
            "kind": entry.get("kind"),
            "annotation_kind": entry.get("annotation_kind"),
            "label": entry.get("label"),
            "reason": entry.get("reason"),
        }
        for entry in entries
    ]


def _serialize_actual(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "name": row.get("name"),
            "track_type": row["track_type"],
            "track_index": int(row["track_index"]),
            "start_frame": int(row["start_frame"]),
            "end_frame": int(row["end_frame"]),
            "current_color": row.get("current_color"),
        }
        for row in rows
    ]


def build_batch_preflight(
    entries: list[dict[str, Any]],
    actual_rows: list[dict[str, Any]],
    *,
    require_count_match: bool,
) -> dict[str, Any]:
    duplicate_expected_bounds = _duplicate_bounds(entries)
    duplicate_bounds = _duplicate_bounds(actual_rows)
    actual_by_bounds = {
        (int(row["start_frame"]), int(row["end_frame"])): row
        for row in actual_rows
    }
    missing_expected_bounds = [
        {"start_frame": int(entry["start_frame"]), "end_frame": int(entry["end_frame"])}
        for entry in entries
        if (int(entry["start_frame"]), int(entry["end_frame"])) not in actual_by_bounds
    ]
    expected_bounds = {(int(entry["start_frame"]), int(entry["end_frame"])) for entry in entries}
    extra_actual_bounds = [
        {"start_frame": int(row["start_frame"]), "end_frame": int(row["end_frame"])}
        for row in actual_rows
        if (int(row["start_frame"]), int(row["end_frame"])) not in expected_bounds
    ]
    counts_match = len(entries) == len(actual_rows)
    frame_map_ok = not duplicate_expected_bounds and not duplicate_bounds and not missing_expected_bounds
    matched_entries = [
        entry
        for entry in entries
        if (int(entry["start_frame"]), int(entry["end_frame"])) in actual_by_bounds
    ]
    return {
        "expected_count": len(entries),
        "actual_count": len(actual_rows),
        "counts_match": counts_match,
        "frame_map_ok": frame_map_ok,
        "expected": _serialize_expected(entries),
        "actual": _serialize_actual(actual_rows),
        "mismatches": {
            "missing_expected_bounds": missing_expected_bounds,
            "extra_actual_bounds": extra_actual_bounds,
        },
        "duplicate_bounds": duplicate_bounds,
        "duplicate_expected_bounds": duplicate_expected_bounds,
        "matched_count": len(matched_entries),
        "ready": frame_map_ok and (counts_match or not require_count_match),
    }


def _timeline_start_frame(conn: Any, *, timeline: Any | None = None) -> int:
    timeline = timeline if timeline is not None else getattr(conn, "timeline", None)
    if timeline is not None and hasattr(timeline, "GetStartFrame"):
        try:
            return int(timeline.GetStartFrame())
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
            raise APICallFailed("DaVinci Resolve project handle is not available for timeline clip-color batch.")
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
        raise APICallFailed("No active timeline is available for timeline clip-color batch.")
    return {
        "timeline": timeline,
        "timeline_name": timeline.GetName() if hasattr(timeline, "GetName") else None,
        "timeline_index": None,
        "activation": None,
    }


def plan_timeline_clip_color_batch(
    conn: Any,
    *,
    entries: list[dict[str, Any]],
    timeline_name: str | None = None,
    track_type: str = "video",
    track_index: int = 1,
    all_tracks: bool = False,
    require_count_match: bool = True,
) -> dict[str, Any]:
    timeline_context = resolve_timeline_context(conn, timeline_name=timeline_name, activate=False)
    timeline = timeline_context["timeline"]
    if timeline is None:
        raise APICallFailed("No target timeline is available for timeline clip-color batch.")
    normalized_entries = normalize_batch_entries(
        entries,
        fps=float(getattr(conn, "fps", 24.0) or 24.0),
        timeline_start_frame=_timeline_start_frame(conn, timeline=timeline),
    )
    actual_rows = collect_timeline_items(
        timeline,
        track_type=track_type,
        track_index=track_index,
        all_tracks=all_tracks,
    )
    preflight = build_batch_preflight(
        normalized_entries,
        actual_rows,
        require_count_match=require_count_match,
    )
    return {
        "action": "timeline.clip_color.batch",
        "timeline_name": timeline_context["timeline_name"],
        "timeline_index": timeline_context["timeline_index"],
        "track_type": normalize_track_type(track_type),
        "track_index": int(track_index),
        "all_tracks": bool(all_tracks),
        "require_count_match": bool(require_count_match),
        "entries": normalized_entries,
        "preflight": preflight,
    }


def _clear_color_readback_ok(value: Any) -> bool:
    if value is None:
        return True
    normalized = str(value).strip().lower()
    return normalized in {"", "none", "default", "no color", "clear"}


def _verification_status(results: list[dict[str, Any]]) -> str:
    if any(result["status"] == "failed" for result in results):
        return "failed"
    if any(result["status"] == "pending_manual" for result in results):
        return "pending_manual"
    return "verified"


def apply_timeline_clip_color_batch(
    conn: Any,
    *,
    entries: list[dict[str, Any]],
    timeline_name: str | None = None,
    track_type: str = "video",
    track_index: int = 1,
    all_tracks: bool = False,
    require_count_match: bool = True,
    allow_partial: bool = False,
) -> dict[str, Any]:
    plan = plan_timeline_clip_color_batch(
        conn,
        entries=entries,
        timeline_name=timeline_name,
        track_type=track_type,
        track_index=track_index,
        all_tracks=all_tracks,
        require_count_match=require_count_match,
    )
    preflight = plan["preflight"]
    if not preflight["ready"] and not allow_partial:
        raise ValidationError(
            "Timeline clip-color batch preflight failed.",
            details={
                **preflight,
                "reason": "timeline_clip_color_batch_preflight_failed",
                "applied_count": 0,
                "cleared_count": 0,
                "failed_count": 0,
            },
            recoverability="not_applicable",
        )

    timeline_context = resolve_timeline_context(conn, timeline_name=timeline_name, activate=bool(timeline_name))
    timeline = timeline_context["timeline"]
    if timeline is None:
        raise APICallFailed("No target timeline is available for timeline clip-color batch.")
    actual_rows = collect_timeline_items(
        timeline,
        track_type=track_type,
        track_index=track_index,
        all_tracks=all_tracks,
    )
    actual_by_bounds = {
        (int(row["start_frame"]), int(row["end_frame"])): row
        for row in actual_rows
    }
    if preflight["duplicate_bounds"] or preflight["duplicate_expected_bounds"]:
        raise ValidationError(
            "Timeline clip-color batch preflight found duplicate bounds.",
            details={
                **preflight,
                "reason": "timeline_clip_color_batch_duplicate_bounds",
                "applied_count": 0,
                "cleared_count": 0,
                "failed_count": 0,
            },
            recoverability="not_applicable",
        )

    candidate_entries = [
        entry
        for entry in plan["entries"]
        if (int(entry["start_frame"]), int(entry["end_frame"])) in actual_by_bounds
    ]
    if not candidate_entries:
        raise ValidationError(
            "Timeline clip-color batch could not match any timeline items to the requested bounds.",
            details={
                **preflight,
                "reason": "timeline_clip_color_batch_no_matches",
                "applied_count": 0,
                "cleared_count": 0,
                "failed_count": 0,
            },
            recoverability="not_applicable",
        )

    results: list[dict[str, Any]] = []
    applied_count = 0
    cleared_count = 0
    failed_count = 0
    for entry in candidate_entries:
        bounds = (int(entry["start_frame"]), int(entry["end_frame"]))
        row = actual_by_bounds[bounds]
        item = row["item"]
        result: dict[str, Any] = {
            "start_frame": bounds[0],
            "end_frame": bounds[1],
            "track_type": row["track_type"],
            "track_index": int(row["track_index"]),
            "name": row.get("name"),
            "requested_color": entry["color"],
            "clear": bool(entry["clear"]),
            "kind": entry.get("kind"),
            "annotation_kind": entry.get("annotation_kind"),
            "label": entry.get("label"),
            "reason": entry.get("reason"),
            "status": "verified",
        }
        if entry["clear"]:
            clearer = getattr(item, "ClearClipColor", None)
            if not callable(clearer):
                raise CapabilityNegotiationFailed(
                    "Timeline item clip-color clear is not available through this DaVinci Resolve scripting runtime.",
                    details={
                        "capability_id": "timeline.clip_color_batch",
                        "required_native_api": "TimelineItem.ClearClipColor()",
                        "track_type": row["track_type"],
                        "track_index": int(row["track_index"]),
                    },
                )
            api_result = clearer()
            result["api_result"] = api_result
            if api_result is False:
                result["status"] = "failed"
                result["error"] = "clear_returned_false"
                failed_count += 1
                results.append(result)
                continue
        else:
            setter = getattr(item, "SetClipColor", None)
            if not callable(setter):
                raise CapabilityNegotiationFailed(
                    "Timeline item clip-color set is not available through this DaVinci Resolve scripting runtime.",
                    details={
                        "capability_id": "timeline.clip_color_batch",
                        "required_native_api": "TimelineItem.SetClipColor(color)",
                        "track_type": row["track_type"],
                        "track_index": int(row["track_index"]),
                    },
                )
            api_result = setter(entry["color"])
            result["api_result"] = api_result
            if api_result is False:
                result["status"] = "failed"
                result["error"] = "set_returned_false"
                failed_count += 1
                results.append(result)
                continue

        getter = getattr(item, "GetClipColor", None)
        if callable(getter):
            try:
                actual_color = getter()
            except Exception:
                actual_color = None
            result["actual_color"] = actual_color
            if entry["clear"]:
                if _clear_color_readback_ok(actual_color):
                    result["status"] = "verified"
                else:
                    result["status"] = "failed"
                    result["error"] = "clear_readback_mismatch"
                    failed_count += 1
            else:
                if actual_color == entry["color"]:
                    result["status"] = "verified"
                else:
                    result["status"] = "failed"
                    result["error"] = "set_readback_mismatch"
                    failed_count += 1
        else:
            result["status"] = "pending_manual"

        if result["status"] != "failed":
            if entry["clear"]:
                cleared_count += 1
            else:
                applied_count += 1
        results.append(result)

    return {
        "action": "timeline.clip_color.batch",
        "timeline_name": timeline_context["timeline_name"],
        "track_type": normalize_track_type(track_type),
        "track_index": int(track_index),
        "all_tracks": bool(all_tracks),
        "require_count_match": bool(require_count_match),
        "allow_partial": bool(allow_partial),
        "preflight": preflight,
        "results": results,
        "applied_count": applied_count,
        "cleared_count": cleared_count,
        "failed_count": failed_count,
        "verification": {"status": _verification_status(results)},
    }
