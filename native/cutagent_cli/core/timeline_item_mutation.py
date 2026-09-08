"""Reusable TimelineItem mutation helpers."""

from __future__ import annotations

from typing import Any


def timeline_item_start(item: Any) -> int | None:
    getter = getattr(item, "GetStart", None)
    if not callable(getter):
        return None
    for args in ((False,), ()):
        try:
            return int(getter(*args))
        except TypeError:
            continue
        except Exception:
            continue
    return None


def timeline_item_end(item: Any) -> int | None:
    getter = getattr(item, "GetEnd", None)
    if not callable(getter):
        return None
    for args in ((False,), ()):
        try:
            return int(getter(*args))
        except TypeError:
            continue
        except Exception:
            continue
    return None


def timeline_item_duration(item: Any) -> int | None:
    getter = getattr(item, "GetDuration", None)
    if callable(getter):
        try:
            return int(getter())
        except Exception:
            pass
    start = timeline_item_start(item)
    end = timeline_item_end(item)
    if start is not None and end is not None:
        return end - start
    return None


def timeline_item_range(item: Any) -> dict[str, int | None]:
    start = timeline_item_start(item)
    end = timeline_item_end(item)
    duration = timeline_item_duration(item)
    return {"start": start, "end": end, "duration": duration}


def _readback_covers(item: Any, *, start_frame: int | None, end_frame: int, duration_frames: int) -> bool:
    readback = timeline_item_range(item)
    current_start = readback["start"]
    current_end = readback["end"]
    current_duration = readback["duration"]
    if start_frame is not None and current_start is not None and current_end is not None:
        return current_start <= start_frame and current_end >= end_frame
    if current_end is not None and current_end >= end_frame:
        return True
    return current_duration == duration_frames


def set_timeline_item_name(item: Any, name: str) -> dict[str, Any]:
    result: dict[str, Any] = {"name_requested": name, "name_applied": False}
    name_setter = getattr(item, "SetName", None)
    if callable(name_setter):
        try:
            result["name_applied"] = name_setter(name) is not False
            if result["name_applied"]:
                result["name_route"] = "SetName"
        except Exception:
            pass

    setter = getattr(item, "SetProperty", None)
    if not result["name_applied"] and callable(setter):
        for key in ("Name", "Clip Name", "ClipName"):
            try:
                if setter(key, name) is not False:
                    result["name_applied"] = True
                    result["name_route"] = f"SetProperty:{key}"
                    break
            except Exception:
                continue

    getter = getattr(item, "GetName", None)
    if callable(getter):
        try:
            result["name_readback"] = getter()
            if result["name_readback"] == name:
                result["name_applied"] = True
        except Exception:
            pass
    return result


def set_timeline_item_end_or_duration(
    item: Any,
    *,
    end_frame: int,
    duration_frames: int,
    start_frame: int | None = None,
) -> dict[str, Any]:
    """Try known DaVinci Resolve TimelineItem duration/end mutation routes with readback after each."""
    result: dict[str, Any] = {
        "end_requested_frame": int(end_frame),
        "duration_requested_frames": int(duration_frames),
        "duration_applied": False,
        "attempts": [],
    }

    setter = getattr(item, "SetProperty", None)
    if callable(setter):
        for key, value in (("End", int(end_frame)), ("Duration", int(duration_frames))):
            attempt: dict[str, Any] = {"route": f"SetProperty:{key}", "value": value}
            try:
                attempt["api_result"] = setter(key, value)
            except Exception as exc:
                attempt["error"] = str(exc)
            attempt["readback"] = timeline_item_range(item)
            result["attempts"].append(attempt)
            if attempt.get("api_result") is not False and _readback_covers(
                item,
                start_frame=start_frame,
                end_frame=int(end_frame),
                duration_frames=int(duration_frames),
            ):
                result["duration_applied"] = True
                result["duration_property"] = attempt["route"]
                break

    for method_name, value in (("SetDuration", int(duration_frames)), ("SetEnd", int(end_frame))):
        if result["duration_applied"]:
            break
        method = getattr(item, method_name, None)
        if not callable(method):
            continue
        attempt = {"route": method_name, "value": value}
        try:
            attempt["api_result"] = method(value)
        except Exception as exc:
            attempt["error"] = str(exc)
        attempt["readback"] = timeline_item_range(item)
        result["attempts"].append(attempt)
        if attempt.get("api_result") is not False and _readback_covers(
            item,
            start_frame=start_frame,
            end_frame=int(end_frame),
            duration_frames=int(duration_frames),
        ):
            result["duration_applied"] = True
            result["duration_property"] = method_name
            break

    result.update(timeline_item_range(item))
    readback_duration = result.get("duration")
    if readback_duration is not None:
        result["duration_readback_frames"] = readback_duration
        if readback_duration == int(duration_frames):
            result["duration_applied"] = True
    return result


def apply_timeline_item_name_and_duration(item: Any, *, name: str, duration_frames: int) -> dict[str, Any]:
    start = timeline_item_start(item)
    end_frame = int(start or 0) + int(duration_frames)
    result: dict[str, Any] = {
        "name_requested": name,
        "name_applied": False,
        "duration_requested_frames": int(duration_frames),
        "duration_applied": False,
    }
    result.update(set_timeline_item_name(item, name))
    duration_result = set_timeline_item_end_or_duration(
        item,
        end_frame=end_frame,
        duration_frames=int(duration_frames),
        start_frame=start,
    )
    result.update(duration_result)
    if "start" not in result:
        current_start = timeline_item_start(item)
        if current_start is not None:
            result["start"] = current_start
    if "end" not in result:
        current_end = timeline_item_end(item)
        if current_end is not None:
            result["end"] = current_end
    return result
