"""Authoritative source-range readback for timeline items."""

from __future__ import annotations

import math
import re
import sqlite3
import struct
from typing import Any

from ..utils.time_ref import parse_source_frame
from . import retime_db
from .audio_source_extent import audio_file_duration


def _call(target: Any, method_name: str, *args: Any) -> Any:
    method = getattr(target, method_name, None)
    if not callable(method):
        return None
    try:
        return method(*args)
    except Exception:
        return None


def _number(value: Any) -> float | None:
    if value is None:
        return None
    match = re.search(r"-?\d+(?:[.,]\d+)?", str(value))
    if not match:
        return None
    try:
        return float(match.group(0).replace(",", "."))
    except ValueError:
        return None


def _properties(media_pool_item: Any) -> dict[str, Any]:
    value = _call(media_pool_item, "GetClipProperty")
    return value if isinstance(value, dict) else {}


def _source_fps(properties: dict[str, Any], fallback: float) -> float:
    for key in ("FPS", "Frame Rate", "Video Frame Rate", "Clip Frame Rate", "MediaFrameRate"):
        parsed = _number(properties.get(key))
        if parsed and parsed > 0:
            return parsed
    return float(fallback)


def _source_total_frames(properties: dict[str, Any], source_fps: float) -> int | None:
    for key in ("Frames", "DurationFrames", "SourceFrames"):
        parsed = _number(properties.get(key))
        if parsed is not None and parsed >= 0:
            return int(parsed)
    duration = properties.get("Duration")
    if isinstance(duration, str) and duration.strip():
        try:
            return int(parse_source_frame(duration.strip(), source_fps))
        except Exception:
            return None
    return None


def _first_frame(item: Any, method_names: tuple[str, ...]) -> int | None:
    for method_name in method_names:
        value = _call(item, method_name)
        if isinstance(value, (int, float)):
            return int(value)
    return None


def _timeline_item_offset(item: Any, method_name: str) -> float | int | None:
    """Read an item offset without discarding mixed-rate subframes.

    DaVinci Resolve accepts a boolean subframe flag for these getters. Older
    builds and test doubles expose only the no-argument form, so retain that
    compatibility fallback without weakening subsequent conflict detection.
    """

    value = _call(item, method_name, True)
    if isinstance(value, (int, float)):
        return value
    value = _call(item, method_name)
    return value if isinstance(value, (int, float)) else None


def ordinary_source_mapping_proven(conn: Any, item: Any) -> bool:
    """Prove the exact timeline item has a decoded native identity time map."""

    native_id = _call(item, "GetUniqueId")
    duration = _first_frame(item, ("GetDuration",))
    if not isinstance(native_id, str) or not native_id or duration is None:
        return False
    try:
        db_path = conn.disk_db_path(allow_project_name_inference=True)
        database = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        database.row_factory = sqlite3.Row
        try:
            row = database.execute(
                "SELECT Duration, MediaTimemapBA FROM Sm2TiItem WHERE Sm2TiItem_id = ?",
                (native_id,),
            ).fetchone()
        finally:
            database.close()
    except Exception:
        return False
    if row is None or row["MediaTimemapBA"] in (None, b""):
        return False
    try:
        db_duration = int(str(row["Duration"]).split("|", 1)[0])
    except (TypeError, ValueError):
        return False
    decoded = retime_db.decode_timemap_blob(row["MediaTimemapBA"]).get("decoded")
    return (
        db_duration == duration
        and isinstance(decoded, dict)
        and decoded.get("type") == "simple_default"
    )


def _compound_frame_value(value: Any) -> float | None:
    """Decode DaVinci Resolve's integer-plus-fraction frame cell."""

    if value in (None, ""):
        return 0.0
    whole, separator, fraction = str(value).partition("|")
    try:
        result = float(whole)
        if separator:
            raw = bytes.fromhex(fraction)
            if len(raw) != 8:
                return None
            result += float(struct.unpack("<d", raw)[0])
        return result if math.isfinite(result) else None
    except (ValueError, struct.error):
        return None


def _ordinary_db_source_range(
    conn: Any,
    item: Any,
    *,
    timeline_fps: float,
    source_fps: float,
) -> tuple[int, int] | None:
    """Read a simple linear source range when native audio offsets are absent."""

    native_id = _call(item, "GetUniqueId")
    native_duration = _first_frame(item, ("GetDuration",))
    if not isinstance(native_id, str) or not native_id or native_duration is None:
        return None
    try:
        db_path = conn.disk_db_path(allow_project_name_inference=True)
        database = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        database.row_factory = sqlite3.Row
        try:
            row = database.execute(
                'SELECT Duration, "In", MediaTimemapBA FROM Sm2TiItem WHERE Sm2TiItem_id = ?',
                (native_id,),
            ).fetchone()
        finally:
            database.close()
    except Exception:
        return None
    if row is None or row["MediaTimemapBA"] in (None, b""):
        return None
    decoded = retime_db.decode_timemap_blob(row["MediaTimemapBA"]).get("decoded")
    duration = _compound_frame_value(row["Duration"])
    source_in = _compound_frame_value(row["In"])
    if (
        not isinstance(decoded, dict)
        or decoded.get("type") != "simple_default"
        or duration is None
        or source_in is None
        or abs(duration - native_duration) >= 1
        or timeline_fps <= 0
    ):
        return None
    start = int(round(source_in * source_fps / timeline_fps))
    end = int(round((source_in + duration) * source_fps / timeline_fps))
    return (start, end) if 0 <= start < end else None


def trusted_timeline_item_source_range(
    item: Any,
    timeline_fps: float,
    *,
    ordinary_mapping_proven: bool = False,
    audio_only: bool = False,
    connection: Any | None = None,
) -> dict[str, Any]:
    """Return the source boundaries that the timeline actually renders.

    DaVinci Resolve can expose native source-frame getters one frame low when
    integer-rate media is placed on a different-rate timeline. Timeline-item
    offsets are in the record-rate domain and provide the rendered boundary.
    A disagreement larger than one frame remains a fail-closed conflict unless
    both reads bracket the exact endpoint implied by the item's record duration.
    """

    media_pool_item = _call(item, "GetMediaPoolItem")
    properties = _properties(media_pool_item) if media_pool_item is not None else {}
    source_fps = _source_fps(properties, timeline_fps)
    total_source_frames = _source_total_frames(properties, source_fps)
    audio_duration = audio_file_duration(media_pool_item) if audio_only else None
    if audio_duration is not None:
        # Offset getters retain subframes. Preserve the fractional source extent
        # until subtracting the exact right offset; the formatted Duration label
        # may use a different frame-rate domain for audio-only media.
        sample_count, sample_rate = audio_duration
        total_source_frames = sample_count * source_fps / sample_rate
    left_offset = _timeline_item_offset(item, "GetLeftOffset")
    right_offset = _timeline_item_offset(item, "GetRightOffset")
    offset_start = (
        int(round(float(left_offset) * source_fps / timeline_fps))
        if isinstance(left_offset, (int, float))
        else None
    )
    offset_end = (
        int(round(total_source_frames - (float(right_offset) * source_fps / timeline_fps)))
        if total_source_frames is not None and isinstance(right_offset, (int, float))
        else None
    )
    native_start = _first_frame(item, ("GetSourceStartFrame", "GetSourceStart"))
    native_end_inclusive = _first_frame(item, ("GetSourceEndFrame", "GetSourceEnd"))
    # DaVinci Resolve's timeline-item source-end getter identifies the last
    # rendered source frame. Normalize that inclusive boundary to the
    # half-open convention used by CutAgent plans and verification.
    native_end = native_end_inclusive + 1 if native_end_inclusive is not None else None
    offset_complete = offset_start is not None and offset_end is not None
    native_complete = native_start is not None and native_end is not None
    db_range = (
        _ordinary_db_source_range(
            connection,
            item,
            timeline_fps=timeline_fps,
            source_fps=source_fps,
        )
        if audio_only and ordinary_mapping_proven and connection is not None
        else None
    )
    record_duration = _first_frame(item, ("GetDuration",))
    duration_end = (
        native_start
        + int(round(record_duration * source_fps / timeline_fps))
        if native_start is not None
        and record_duration is not None
        and record_duration >= 0
        and timeline_fps > 0
        else None
    )
    duration_bracketed = bool(
        ordinary_mapping_proven
        and
        offset_complete
        and native_complete
        and duration_end is not None
        and offset_start == native_start
        and abs(offset_end - duration_end) <= 1
        and abs(native_end - duration_end) <= 1
    )
    db_bracketed = bool(
        db_range is not None
        and native_complete
        and duration_end is not None
        and db_range[0] == native_start
        and abs(db_range[1] - native_end) <= 1
        and abs(db_range[1] - duration_end) <= 1
    )
    conflict = bool(
        offset_complete
        and native_complete
        and max(abs(offset_start - native_start), abs(offset_end - native_end)) > 1
        and not duration_bracketed
        and not db_bracketed
    )
    use_duration = duration_bracketed and abs(offset_end - native_end) > 1
    use_offsets = offset_complete and not conflict and not use_duration
    use_db_range = db_range is not None and (db_bracketed or (not offset_complete and not native_complete))
    return {
        "start": db_range[0] if use_db_range else native_start if use_duration else offset_start if use_offsets else native_start,
        "end_exclusive": db_range[1] if use_db_range else duration_end if use_duration else offset_end if use_offsets else native_end,
        "source_fps": source_fps,
        "authoritative": bool((use_db_range or use_duration or use_offsets or native_complete) and not conflict),
        "selected": (
            "db_simple_audio_mapping"
            if use_db_range
            else "record_duration_bracket"
            if use_duration
            else "timeline_item_offsets"
            if use_offsets
            else "native_source_frames"
        ),
        "native_start": native_start,
        "native_end_exclusive": native_end,
        "offset_start": offset_start,
        "offset_end_exclusive": offset_end,
        "conflict": conflict,
    }
