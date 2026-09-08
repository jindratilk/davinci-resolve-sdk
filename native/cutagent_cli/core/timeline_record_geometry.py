"""Frame-grid projection with retained native subframe evidence."""

import math

from ..errors import ReadinessFailed


def _read(item, name):
    getter = getattr(item, name, None)
    if not callable(getter):
        return None
    try:
        value = getter(True)
    except TypeError:
        value = getter()
    if value is None:
        value = getter()
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ReadinessFailed("DaVinci Resolve returned invalid timeline subframe geometry.")
    return value


def timeline_record_geometry(item):
    """Project boundaries by nearest frame without changing source playback."""
    start = _read(item, "GetStart")
    end = _read(item, "GetEnd")
    duration = _read(item, "GetDuration")
    if start is None or end is None or end <= start:
        raise ReadinessFailed("DaVinci Resolve omitted valid timeline record boundaries.")
    if duration is None:
        duration = end - start
    if duration < 0 or not math.isclose(duration, end - start, rel_tol=0, abs_tol=1e-6):
        raise ReadinessFailed("DaVinci Resolve returned inconsistent timeline subframe geometry.")
    projected_start = math.floor(start + 0.5)
    # The existing source-to-record contract keeps every positive span at least
    # one frame wide, even when the native audio duration is below half a frame.
    projected_end = max(projected_start + 1, math.floor(end + 0.5))
    return {
        "start": projected_start,
        "end": projected_end,
        "duration": projected_end - projected_start,
        "record_subframes": {"start": start, "end_exclusive": end, "duration": duration},
    }
