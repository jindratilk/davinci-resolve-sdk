from __future__ import annotations

from .lookup import _item_name_candidates


def _find_track_of_item(conn, item, track_type: str) -> int:
    def _frame_range(candidate) -> tuple[int, int] | None:
        try:
            return int(candidate.GetStart()), int(candidate.GetEnd())
        except Exception:
            return None

    def _timeline_start_frame() -> int:
        try:
            value = int(getattr(conn, "start_frame", 0) or 0)
        except Exception:
            value = 0
        if value == 0 and getattr(conn, "timeline", None) and hasattr(conn.timeline, "GetStartFrame"):
            try:
                value = int(conn.timeline.GetStartFrame())
            except Exception:
                value = 0
        return value

    def _range_candidates(frame_range: tuple[int, int] | None, timeline_start: int) -> set[tuple[int, int]]:
        if frame_range is None:
            return set()
        start, end = frame_range
        ranges = {(start, end)}
        if timeline_start:
            ranges.add((start - timeline_start, end - timeline_start))
            ranges.add((start + timeline_start, end + timeline_start))
        return ranges

    def _ranges_match(candidate_range: tuple[int, int] | None, target_ranges: set[tuple[int, int]]) -> bool:
        if candidate_range is None or not target_ranges:
            return False
        if candidate_range in target_ranges:
            return True
        candidate_start, candidate_end = candidate_range
        for target_start, target_end in target_ranges:
            if candidate_start == target_start or candidate_end == target_end:
                return True
            overlap = min(candidate_end, target_end) - max(candidate_start, target_start)
            shortest = min(candidate_end - candidate_start, target_end - target_start)
            if shortest > 0 and overlap / shortest >= 0.95:
                return True
        return False

    target_range = _frame_range(item)
    target_ranges = _range_candidates(target_range, _timeline_start_frame())
    target_names = {name.lower() for name in _item_name_candidates(item)}
    name_only_matches: list[int] = []

    track_count = conn.timeline.GetTrackCount(track_type) or 0
    for idx in range(1, track_count + 1):
        items = conn.timeline.GetItemListInTrack(track_type, idx) or []
        for track_item in items:
            if track_item is item:
                return idx
            candidate_range = _frame_range(track_item)
            candidate_names = {name.lower() for name in _item_name_candidates(track_item)}
            names_match = not target_names or not candidate_names or target_names.intersection(candidate_names)
            if _ranges_match(candidate_range, target_ranges) and names_match:
                return idx
            if target_names and candidate_names and target_names.intersection(candidate_names):
                name_only_matches.append(idx)
    if len(set(name_only_matches)) == 1:
        return name_only_matches[0]
    return 0


def _readback_speed(item):
    if not hasattr(item, "GetProperty"):
        return None
    try:
        raw = item.GetProperty("Speed")
    except Exception:
        return None
    if raw is None:
        return None
    try:
        raw_f = float(raw)
    except Exception:
        return None
    if raw_f > 10:
        return raw_f / 100.0
    return raw_f
