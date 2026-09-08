"""Read-only Project.db readback for native video clip fade handles."""

from __future__ import annotations

import math
from pathlib import Path
import sqlite3
import struct
from typing import Any
from urllib.parse import quote

from . import clip_effects_db, db_session, db_timeline_rows, db_timeline_selection


_VIDEO_FADE_EFFECT_ID = 72
_VIDEO_FADE_PARAMETER_BY_EDGE = {"start": 138, "end": 139}


class VideoFadeReadbackError(ValueError):
    """The persisted video fade representation could not be read exactly."""


def _single_varint(fields: list[Any], number: int) -> int | None:
    matches = [
        int(field.value)
        for field in fields
        if field.number == number and field.wire_type == 0
    ]
    if not matches:
        return None
    if len(matches) != 1:
        raise VideoFadeReadbackError("duplicate varint field")
    return matches[0]


def _fade_parameter(message: bytes) -> tuple[str, int] | None:
    fields = clip_effects_db._parse_wire_fields(message)
    if fields is None:
        raise VideoFadeReadbackError("malformed video fade parameter")
    parameter_id = _single_varint(fields, 1)
    edge = next(
        (name for name, expected in _VIDEO_FADE_PARAMETER_BY_EDGE.items() if parameter_id == expected),
        None,
    )
    if edge is None:
        return None
    payloads = [
        field.value
        for field in fields
        if field.number == 3 and field.wire_type == 2 and isinstance(field.value, bytes)
    ]
    if len(payloads) != 1:
        raise VideoFadeReadbackError("video fade parameter has no unique value payload")
    wrappers = clip_effects_db._parse_wire_fields(payloads[0])
    if wrappers is None:
        raise VideoFadeReadbackError("malformed video fade value wrapper")
    values = [
        field.value
        for field in wrappers
        if field.number == 1 and field.wire_type == 2 and isinstance(field.value, bytes)
    ]
    if len(values) != 1:
        raise VideoFadeReadbackError("video fade parameter has no unique scalar wrapper")
    scalars = clip_effects_db._parse_wire_fields(values[0])
    if scalars is None:
        raise VideoFadeReadbackError("malformed video fade scalar")
    doubles = [
        field.value
        for field in scalars
        if field.number == 2 and field.wire_type == 1 and isinstance(field.value, bytes)
    ]
    if len(doubles) != 1 or len(doubles[0]) != 8:
        raise VideoFadeReadbackError("video fade parameter has no unique double value")
    duration = float(struct.unpack("<d", doubles[0])[0])
    if not math.isfinite(duration) or duration <= 0 or not duration.is_integer():
        raise VideoFadeReadbackError("video fade duration is not a positive whole frame count")
    return edge, int(duration)


def _entry_fades(entry: bytes) -> list[tuple[str, int]]:
    proto = clip_effects_db._effect_proto(entry)
    top_fields = clip_effects_db._parse_wire_fields(proto)
    if top_fields is None:
        raise VideoFadeReadbackError("malformed EffectFiltersBA entry")
    fades: list[tuple[str, int]] = []
    for top_field in top_fields:
        if top_field.number != 1 or top_field.wire_type != 2 or not isinstance(top_field.value, bytes):
            continue
        effect_fields = clip_effects_db._parse_wire_fields(top_field.value)
        if effect_fields is None:
            raise VideoFadeReadbackError("malformed effect message")
        if _single_varint(effect_fields, 1) != _VIDEO_FADE_EFFECT_ID:
            continue
        if not is_strict_video_fade_entry(entry):
            raise VideoFadeReadbackError("effect 72 does not match the exact retained video fade shape")
        parameters = [
            field.value
            for field in effect_fields
            if field.number == 9 and field.wire_type == 2 and isinstance(field.value, bytes) and field.value
        ]
        decoded = [_fade_parameter(parameter) for parameter in parameters]
        fades.extend(value for value in decoded if value is not None)
    return fades


def _is_strict_video_fade_parameter(message: bytes) -> bool:
    fields = clip_effects_db._parse_wire_fields(message)
    if fields is None or len(fields) != 2:
        return False
    parameter_id, value_wrapper = fields
    if not (
        parameter_id.number == 1
        and parameter_id.wire_type == 0
        and parameter_id.value in _VIDEO_FADE_PARAMETER_BY_EDGE.values()
        and value_wrapper.number == 3
        and value_wrapper.wire_type == 2
        and isinstance(value_wrapper.value, bytes)
    ):
        return False
    wrappers = clip_effects_db._parse_wire_fields(value_wrapper.value)
    if wrappers is None or len(wrappers) != 1:
        return False
    scalar_wrapper = wrappers[0]
    if not (
        scalar_wrapper.number == 1
        and scalar_wrapper.wire_type == 2
        and isinstance(scalar_wrapper.value, bytes)
    ):
        return False
    scalars = clip_effects_db._parse_wire_fields(scalar_wrapper.value)
    if scalars is None or len(scalars) != 1:
        return False
    scalar = scalars[0]
    if not (
        scalar.number == 2
        and scalar.wire_type == 1
        and isinstance(scalar.value, bytes)
        and len(scalar.value) == 8
    ):
        return False
    try:
        return _fade_parameter(message) is not None
    except VideoFadeReadbackError:
        return False


def is_strict_video_fade_entry(entry: bytes) -> bool:
    """Return whether one packed entry has the exact retained video-fade shape.

    This deliberately recognizes only the native effect-72 fixture structure
    used by the clip fade writer.  Callers that need to distinguish a fade
    entry from another EffectFiltersBA container must not infer that identity
    from the effect id or a parameter name alone.
    """

    raw = bytes(entry)
    if len(raw) < 9:
        return False
    version, body_size = struct.unpack(">II", raw[:8])
    if version != 2 or body_size != len(raw) - 8:
        return False

    top_fields = clip_effects_db._parse_wire_fields(clip_effects_db._effect_proto(raw))
    if top_fields is None or len(top_fields) != 1:
        return False
    top = top_fields[0]
    if top.number != 1 or top.wire_type != 2 or not isinstance(top.value, bytes):
        return False

    effect_fields = clip_effects_db._parse_wire_fields(top.value)
    if effect_fields is None or len(effect_fields) != 4:
        return False
    effect_id, effect_version, empty_slot, parameter = effect_fields
    if not (
        effect_id.number == 1
        and effect_id.wire_type == 0
        and effect_id.value == _VIDEO_FADE_EFFECT_ID
        and effect_version.number == 3
        and effect_version.wire_type == 0
        and effect_version.value == 6
        and empty_slot.number == 9
        and empty_slot.wire_type == 2
        and empty_slot.value == b""
        and parameter.number == 9
        and parameter.wire_type == 2
        and isinstance(parameter.value, bytes)
        and bool(parameter.value)
    ):
        return False
    return _is_strict_video_fade_parameter(parameter.value)


def decode_video_fade_handles(effect_filters: bytes | None) -> dict[str, Any]:
    """Decode exact native head/tail fade durations from one video item blob.

    A structurally readable chain without parameter 138/139 proves an absent
    handle and therefore returns zero. Malformed or ambiguous chains raise so
    callers cannot turn unreadable state into a false zero.
    """

    if not effect_filters:
        entries: list[bytes] = []
    else:
        entries = clip_effects_db.split_packed_blob_chain(effect_filters)
        if len(entries) == 1 and entries[0] == bytes(effect_filters):
            raw = bytes(effect_filters)
            if len(raw) < 8:
                raise VideoFadeReadbackError("malformed packed EffectFiltersBA chain")
            version = int.from_bytes(raw[:4], "big")
            size = int.from_bytes(raw[4:8], "big")
            if version != 2 or size != len(raw) - 8:
                raise VideoFadeReadbackError("malformed packed EffectFiltersBA chain")
    found: dict[str, int] = {}
    for entry in entries:
        for edge, frames in _entry_fades(entry):
            if edge in found:
                raise VideoFadeReadbackError(f"duplicate video fade {edge} handle")
            found[edge] = frames
    return {
        "fadeInFrames": found.get("start", 0),
        "fadeOutFrames": found.get("end", 0),
        "source": "Project.db Sm2TiItem.EffectFiltersBA effect 72 parameters 138/139",
        "curve": None,
        "curveUnavailableReason": "native fade curve shape is not encoded by the retained duration fixture",
    }


def _read_only_connection(path: str) -> sqlite3.Connection:
    resolved = Path(path).expanduser().resolve(strict=True)
    connection = sqlite3.connect(f"file:{quote(str(resolved))}?mode=ro", uri=True, timeout=5.0)
    connection.row_factory = sqlite3.Row
    return connection


def list_video_fade_handles(conn: Any) -> dict[str, Any]:
    """Read native video fade handles for every identity-bound live item."""

    current_database = db_session.resolve_current_disk_project_db(
        conn, allow_project_name_inference=True
    )
    timeline_name = None
    try:
        timeline_name = str(conn.timeline.GetName() or "") or None
    except Exception:
        pass
    live_items = db_timeline_selection._read_live_items(conn, track_type="video")
    rows: list[dict[str, Any]] = []
    connection = _read_only_connection(str(current_database["project_db_path"]))
    try:
        cursor = connection.cursor()
        for item in live_items:
            base = {
                "itemId": item.item_id,
                "trackIndex": int(item.track_index),
                "recordStartFrame": int(item.start),
                "recordEndFrame": int(item.end),
            }
            if not item.item_id:
                rows.append({**base, "status": "unavailable", "reason": "native_item_identity_unavailable"})
                continue
            try:
                db_row = db_timeline_rows.find_ti_item_row(
                    cursor,
                    item=item,
                    db_type="Sm2TiVideoClip",
                    timeline_name=timeline_name,
                )
                if str(db_row.get("Sm2TiItem_id") or "") != item.item_id:
                    raise VideoFadeReadbackError(
                        "Project.db item identity does not match the live native item"
                    )
                fades = decode_video_fade_handles(db_row.get("EffectFiltersBA"))
            except Exception as exc:
                rows.append({
                    **base,
                    "status": "unavailable",
                    "reason": "project_db_video_fade_readback_unavailable",
                    "detail": str(exc),
                })
                continue
            rows.append({**base, "status": "available", **fades})
    finally:
        connection.close()
    return {
        "items": rows,
        "count": len(rows),
        "route": "project_db_read_only",
        "identitySource": "TimelineItem.GetUniqueId + exact Sm2TiItem mapping",
    }
