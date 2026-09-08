"""Persisted nonlinear source authority, separate from linear clip boundaries."""
from __future__ import annotations

import math
import sqlite3
from pathlib import Path
from typing import Any

from ..errors import CLIError, ValidationError
from . import clip_speed_db, db_session, db_timeline_rows, retime_db
from .db_timeline_selection import LiveItemRef
from .retime_native_coordinates import exact_native_rate as _comparison_rate
from .retime_revision import time_map_digest
from .inspector_revision import inspector_state_digest
from .timeline_source_range import _number, _properties, _source_fps, _source_total_frames



def source_metadata(row: dict[str, Any], *, item_id: str, record_fps: float,
                    properties: dict[str, Any]) -> dict[str, Any]:
    """Require independent media-rate/length agreement before granting source bounds."""
    if not item_id or row.get("Sm2TiItem_id") != item_id:
        raise ValidationError("Retime source metadata requires the exact native item identity.")
    record_fps = _comparison_rate(record_fps)
    source_fps = clip_speed_db._source_fps(row, fallback_fps=math.nan)
    media_fps = _source_fps(properties, math.nan)
    if not all(math.isfinite(rate) and rate > 0 for rate in (record_fps, source_fps, media_fps)) \
            or not math.isclose(_comparison_rate(source_fps), _comparison_rate(media_fps), rel_tol=1e-9, abs_tol=1e-9):
        raise ValidationError("Retime source metadata requires matching native and media frame rates.")
    for key in ("Frames", "DurationFrames", "SourceFrames"):
        count = _number(properties.get(key))
        if count is not None and (not math.isfinite(count) or not count.is_integer()):
            raise ValidationError("Retime source metadata requires an integer media frame count.")
    total = _source_total_frames(properties, media_fps)
    decoded = retime_db.decode_timemap_blob(row.get("MediaTimemapBA")).get("decoded") or {}
    limit = (decoded.get("last_valid_seconds") if decoded.get("type") == "simple_default"
             else decoded.get("entries", {}).get("LastValidYOffset"))
    if total is None or total <= 0 or not isinstance(limit, (int, float)) \
            or not math.isfinite(limit) or abs(limit * source_fps - (total - 1)) > 1e-6:
        raise ValidationError("Retime source metadata requires matching persisted and media source bounds.")
    try:
        origin = clip_speed_db._record_in_frames(row) * source_fps / record_fps
    except (KeyError, TypeError, ValueError) as exc:
        raise ValidationError("Retime source metadata omitted its native coordinate origin.") from exc
    if not math.isfinite(origin) or not 0 <= origin < total:
        raise ValidationError("Retime source metadata has an invalid coordinate origin.")
    # Keep fractional source-frame origins; rounding would silently rebase points.
    return {"availableRange": {"domain": "source_range", "unit": "frames", "start": 0,
                               "endExclusive": total}, "originFrame": origin}


def enrich_track_source_metadata(conn: Any, rows: list[dict[str, Any]], items: list[Any], *,
                                 track_type: str, track_index: int) -> None:
    """Read one Disk DB snapshot per track; unsupported storage grants no authority."""
    if track_type not in {"video", "audio"}:
        return
    for row in rows:
        row["retime_source"] = None
        row["retime_time_map_digest"] = None
        row["inspector_state_digest"] = None
    try:
        current = db_session.resolve_current_disk_project_db(conn, allow_project_name_inference=True)
        uri = Path(current["project_db_path"]).resolve().as_uri() + "?mode=ro"
        connection = sqlite3.connect(uri, uri=True)
    except (CLIError, OSError, sqlite3.Error, AttributeError, KeyError):
        return
    try:
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("BEGIN")
        except sqlite3.Error:
            return
        for row, item in zip(rows, items):
            native_id = row.get("timeline_item_unique_id")
            if not native_id:
                continue
            try:
                ref = LiveItemRef(track_type, track_index, row["name"], int(row["start"]),
                                  int(row["duration"]), item_id=native_id)
                persisted = db_timeline_rows.find_ti_item_row(
                    connection.cursor(), item=ref, db_type="Sm2TiVideoClip" if track_type == "video" else "Sm2TiAudioClip",
                    timeline_name=conn.timeline.GetName(),
                )
                if persisted.get("Sm2TiItem_id") != native_id:
                    continue
                effects = persisted.get("EffectFiltersBA")
                if effects is None or isinstance(effects, (bytes, bytearray)):
                    row["inspector_state_digest"] = inspector_state_digest(bytes(effects or b""))
                blob = persisted.get("MediaTimemapBA")
                if isinstance(blob, (bytes, bytearray)):
                    row["retime_time_map_digest"] = time_map_digest(bytes(blob))
                row["retime_source"] = source_metadata(
                    persisted, item_id=native_id, record_fps=float(conn.fps),
                    properties=_properties(item.GetMediaPoolItem()),
                )
            except (CLIError, ValueError, TypeError, sqlite3.Error, AttributeError):
                continue
    finally:
        connection.close()
