from __future__ import annotations

from pathlib import Path

from ...errors import ClipNotFound, ValidationError
from ...utils.time_ref import parse_record_frame
from ..sdk_clip_motion import expected_target, resolve_exact_timeline_item


def get_current_item(conn) -> object:
    timeline = conn.timeline
    if timeline and hasattr(timeline, "GetCurrentVideoItem"):
        try:
            current_item = timeline.GetCurrentVideoItem()
            if current_item:
                return current_item
        except Exception:
            pass

    tc = timeline.GetCurrentTimecode() if timeline else None
    if not tc:
        return None

    try:
        from ...utils.timecode import timecode_to_seconds, seconds_to_frames

        current_frame = seconds_to_frames(timecode_to_seconds(tc, conn.fps), conn.fps)
    except Exception:
        return None

    start_frame = 0
    try:
        start_frame = int(getattr(conn, "start_frame", 0) or 0)
    except Exception:
        start_frame = 0
    if start_frame == 0 and timeline and hasattr(timeline, "GetStartFrame"):
        try:
            start_frame = int(timeline.GetStartFrame())
        except Exception:
            start_frame = 0

    candidate_frames = {current_frame}
    if start_frame:
        candidate_frames.add(current_frame - start_frame)

    for track_type in ("video", "audio"):
        track_count = timeline.GetTrackCount(track_type) or 0
        for i in range(1, track_count + 1):
            items = timeline.GetItemListInTrack(track_type, i) or []
            for item in items:
                try:
                    start = int(item.GetStart())
                    end = int(item.GetEnd())
                except Exception:
                    continue
                for frame in candidate_frames:
                    if start <= frame < end:
                        return item
    return None


def _add_name_candidate(values: set[str], value) -> None:
    if value is None:
        return
    try:
        text = str(value).strip()
    except Exception:
        return
    if not text:
        return
    values.add(text)
    values.add(Path(text).name)


def _item_name_candidates(item) -> set[str]:
    values: set[str] = set()

    if hasattr(item, "GetUniqueId"):
        try:
            _add_name_candidate(values, item.GetUniqueId())
        except Exception:
            pass

    if hasattr(item, "GetName"):
        try:
            _add_name_candidate(values, item.GetName())
        except Exception:
            pass

    if hasattr(item, "GetProperty"):
        for key in ("Clip Name", "File Name", "File Path", "Source File", "SourcePath"):
            try:
                _add_name_candidate(values, item.GetProperty(key))
            except Exception:
                continue

    mpi = item.GetMediaPoolItem() if hasattr(item, "GetMediaPoolItem") else None
    if mpi is not None:
        if hasattr(mpi, "GetName"):
            try:
                _add_name_candidate(values, mpi.GetName())
            except Exception:
                pass
        if hasattr(mpi, "GetClipProperty"):
            try:
                props = mpi.GetClipProperty() or {}
            except Exception:
                props = {}
            if isinstance(props, dict):
                for key in ("Clip Name", "File Name", "File Path", "Source File", "SourcePath"):
                    _add_name_candidate(values, props.get(key))
    return {value for value in values if value}


def find_item_by_name(conn, name: str, track_type: str = "video") -> object:
    query = str(name or "").strip()
    query_lower = query.lower()
    query_basename_lower = Path(query).name.lower() if query else ""

    count = conn.timeline.GetTrackCount(track_type) or 0
    for i in range(1, count + 1):
        items = conn.timeline.GetItemListInTrack(track_type, i) or []
        for item in items:
            item_names = _item_name_candidates(item)
            if query in item_names:
                return item
            lowered = {value.lower() for value in item_names}
            if query_lower in lowered or (query_basename_lower and query_basename_lower in lowered):
                return item
    return None


def _timeline_item_start(item) -> int | None:
    getter = getattr(item, "GetStart", None)
    if not callable(getter):
        return None
    try:
        return int(getter())
    except Exception:
        return None


def _timeline_item_end(item) -> int | None:
    getter = getattr(item, "GetEnd", None)
    if not callable(getter):
        return None
    try:
        return int(getter())
    except Exception:
        return None


def _record_frame_candidates(conn, record_frame: int) -> set[int]:
    candidates = {int(record_frame)}
    try:
        start_frame = int(getattr(conn, "start_frame", 0) or 0)
    except Exception:
        start_frame = 0
    if start_frame:
        candidates.add(int(record_frame) - start_frame)

    timeline = getattr(conn, "timeline", None)
    if timeline is not None and hasattr(timeline, "GetStartFrame"):
        try:
            timeline_start = int(timeline.GetStartFrame() or 0)
        except Exception:
            timeline_start = 0
        if timeline_start:
            candidates.add(int(record_frame) - timeline_start)
    return candidates


def find_item_by_track_record(conn, track: int, record_frame: str | int, track_type: str = "video") -> object:
    try:
        track_index = int(track)
    except (TypeError, ValueError) as exc:
        raise ValidationError("Track index must be an integer.", details={"track": track}) from exc
    if track_index < 1:
        raise ValidationError("Track index must be at least 1.", details={"track": track})

    timeline = getattr(conn, "timeline", None)
    if timeline is None:
        raise ClipNotFound("No current timeline is available.")

    try:
        track_count = int(timeline.GetTrackCount(track_type) or 0)
    except Exception:
        track_count = 0
    if track_index > track_count:
        raise ClipNotFound(
            f"{track_type.title()} track {track_index} is out of range.",
            details={"track_type": track_type, "track": track_index, "track_count": track_count},
        )

    parsed_record_frame = parse_record_frame(str(record_frame), getattr(conn, "fps", 24.0), getattr(conn, "start_frame", 0))
    candidates = _record_frame_candidates(conn, parsed_record_frame)

    items = timeline.GetItemListInTrack(track_type, track_index) or []
    matches = []
    for item in items:
        start = _timeline_item_start(item)
        end = _timeline_item_end(item)
        if start is None or end is None:
            continue
        if any(start <= candidate < end for candidate in candidates):
            matches.append(item)

    if not matches:
        raise ClipNotFound(
            "No timeline item matched track and record frame.",
            details={"track_type": track_type, "track": track_index, "record_frame": parsed_record_frame, "record_frame_candidates": sorted(candidates)},
        )
    if len(matches) > 1:
        raise ValidationError(
            "Multiple timeline items matched track and record frame.",
            details={"track_type": track_type, "track": track_index, "record_frame": parsed_record_frame, "match_count": len(matches)},
        )
    return matches[0]


def cutagent_clip_by_selector(conn, name=None, *, track: int | None = None, record_frame: str | int | None = None):
    if (track is None) != (record_frame is None):
        raise ValidationError(
            "Use --track and --record-frame together.",
            details={"clip": name, "track": track, "record_frame": record_frame},
        )
    if name and track is not None:
        raise ValidationError(
            "Use either clip name or --track with --record-frame, not both.",
            details={"clip": name, "track": track, "record_frame": record_frame},
        )
    if track is not None and record_frame is not None:
        return find_item_by_track_record(conn, track, record_frame)
    return cutagent_clip(conn, name)


def cutagent_clip(conn, name=None):
    if expected_target() is not None:
        return resolve_exact_timeline_item(conn)
    if name:
        item = find_item_by_name(conn, name)
        if not item:
            item = find_item_by_name(conn, name, "audio")
        if not item:
            raise ClipNotFound(f"Clip '{name}' not found on timeline.")
        return item

    item = get_current_item(conn)
    if not item:
        raise ClipNotFound("No clip under the playhead.")
    return item
