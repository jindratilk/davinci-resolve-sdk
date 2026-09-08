from __future__ import annotations

from typing import Any, Optional

from ...errors import APICallFailed, ValidationError
from .. import media_pool
from ..sdk_live_inspection import documented_unique_id

_FRAME_DOMAINS = {"auto", "offset", "source", "raw"}


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _first_item_int(item: Any, method_names: tuple[str, ...]) -> int | None:
    for method_name in method_names:
        method = getattr(item, method_name, None)
        if not callable(method):
            continue
        try:
            value = _int_or_none(method())
        except Exception:
            continue
        if value is not None:
            return value
    return None


def _clip_marker_frame_context(item: Any) -> dict[str, int | None]:
    start = _first_item_int(item, ("GetStart",))
    end = _first_item_int(item, ("GetEnd",))
    duration = _first_item_int(item, ("GetDuration",))
    if duration is None and start is not None and end is not None:
        duration = max(0, end - start)

    source_start = _first_item_int(
        item, ("GetSourceStartFrame", "GetSourceStart", "GetLeftOffset")
    )
    if source_start is None:
        source_start = 0
    source_end = _first_item_int(item, ("GetSourceEndFrame", "GetSourceEnd"))
    if source_end is None and duration is not None:
        source_end = source_start + duration

    return {
        "start": start,
        "end": end,
        "duration": duration,
        "source_start": source_start,
        "source_end": source_end,
    }


def _marker_offset(frame: int, context: dict[str, int | None]) -> int | None:
    source_start = context.get("source_start")
    source_end = context.get("source_end")
    if source_start is None:
        return None
    if source_end is not None and not (source_start <= frame < source_end):
        return None
    if source_end is None and frame < source_start:
        return None
    return frame - source_start


def _marker_record_frame(frame: int, context: dict[str, int | None]) -> int | None:
    offset = _marker_offset(frame, context)
    start = context.get("start")
    if offset is None or start is None:
        return None
    return start + offset


def _call_optional(obj: Any, method_name: str, *args: Any) -> Any:
    method = getattr(obj, method_name, None)
    if not callable(method):
        return None
    try:
        return method(*args)
    except Exception:
        return None


def _object_identifier(obj: Any) -> str | None:
    for method_name in ("GetUniqueId", "GetUniqueID", "GetId", "GetID"):
        value = _call_optional(obj, method_name)
        if value not in (None, ""):
            return str(value)
    props = _call_optional(obj, "GetProperty")
    if isinstance(props, dict):
        for key in ("UniqueId", "Unique ID", "unique_id", "Id", "ID"):
            value = props.get(key)
            if value not in (None, ""):
                return str(value)
    return None


def _clip_display_name(item: Any) -> str:
    name = _call_optional(item, "GetName")
    if name not in (None, ""):
        return str(name)
    media_pool_item = _call_optional(item, "GetMediaPoolItem")
    media_pool_name = (
        _call_optional(media_pool_item, "GetName")
        if media_pool_item is not None
        else None
    )
    if media_pool_name not in (None, ""):
        return str(media_pool_name)
    return "?"


def _marker_dict(obj: Any) -> dict[Any, Any]:
    getter = getattr(obj, "GetMarkers", None)
    if not callable(getter):
        return {}
    try:
        markers = getter() or {}
    except Exception:
        return {}
    return markers if isinstance(markers, dict) else {}


def _timeline_item_marker_sources(item: Any) -> list[tuple[str, dict[Any, Any]]]:
    sources: list[tuple[str, dict[Any, Any]]] = []
    item_markers = _marker_dict(item)
    if item_markers:
        sources.append(("timeline_item", item_markers))

    media_pool_item = _call_optional(item, "GetMediaPoolItem")
    if media_pool_item is not None:
        media_pool_markers = _marker_dict(media_pool_item)
        if media_pool_markers:
            sources.append(("media_pool_item", media_pool_markers))

    return sources


def _marker_identity(
    source_frame: int, marker_data: dict[str, Any]
) -> tuple[int, str, str, str, str]:
    return (
        source_frame,
        str(marker_data.get("color", "") or "").lower(),
        str(marker_data.get("name", "") or ""),
        str(marker_data.get("note", "") or ""),
        repr(marker_data.get("duration", "")),
    )


def _timeline_name(conn: Any) -> str | None:
    name = _call_optional(getattr(conn, "timeline", None), "GetName")
    return str(name) if name not in (None, "") else None


def _timeline_start_frame(conn: Any) -> int:
    try:
        start_frame = int(getattr(conn, "start_frame", 0) or 0)
    except Exception:
        start_frame = 0
    if start_frame == 0:
        value = _call_optional(getattr(conn, "timeline", None), "GetStartFrame")
        try:
            start_frame = int(value or 0)
        except Exception:
            start_frame = 0
    return start_frame


def _record_timecode(conn: Any, record_frame: int | None) -> str | None:
    if record_frame is None:
        return None
    try:
        frame = int(record_frame)
    except Exception:
        return None
    start_frame = _timeline_start_frame(conn)
    display_frame = (
        frame - start_frame if start_frame and frame >= start_frame else frame
    )
    try:
        from ...utils.timecode import frames_to_seconds, seconds_to_timecode

        fps = float(getattr(conn, "fps", 24.0) or 24.0)
        return seconds_to_timecode(frames_to_seconds(display_frame, fps), fps)
    except Exception:
        return None


def _normalize_scan_track_type(track_type: str | None) -> tuple[str, list[str]]:
    normalized = str(track_type or "video").strip().lower()
    if normalized not in {"video", "audio", "all"}:
        raise ValidationError(
            "Track type must be one of: video, audio, all.",
            details={"track_type": track_type, "allowed": ["audio", "all", "video"]},
            recoverability="not_applicable",
        )
    return normalized, (["video", "audio"] if normalized == "all" else [normalized])


def _normalize_scan_tracks(
    tracks: list[int] | tuple[int, ...] | None,
) -> list[int] | None:
    if not tracks:
        return None
    normalized: list[int] = []
    for track in tracks:
        try:
            index = int(track)
        except Exception as exc:
            raise ValidationError(
                "Track index must be an integer.",
                details={"track": track},
                recoverability="not_applicable",
            ) from exc
        if index < 1:
            raise ValidationError(
                "Track index must be greater than or equal to 1.",
                details={"track": track},
                recoverability="not_applicable",
            )
        normalized.append(index)
    return normalized


def _sort_marker_occurrence(row: dict[str, object]) -> tuple[int, int, int, int]:
    record_frame = row.get("record_frame")
    source_frame = row.get("source_frame")
    track_index = row.get("track_index")
    try:
        record_sort = int(record_frame)
        missing_record = 0
    except Exception:
        record_sort = 0
        missing_record = 1
    try:
        track_sort = int(track_index)
    except Exception:
        track_sort = 0
    try:
        source_sort = int(source_frame)
    except Exception:
        source_sort = 0
    return missing_record, record_sort, track_sort, source_sort


def _normalize_frame_domain(frame_domain: str) -> str:
    normalized = str(frame_domain or "auto").strip().lower()
    if normalized not in _FRAME_DOMAINS:
        raise ValidationError(
            "Marker frame domain must be one of: auto, offset, source, raw.",
            details={"frame_domain": frame_domain, "allowed": sorted(_FRAME_DOMAINS)},
            recoverability="not_applicable",
        )
    return normalized


def _resolve_marker_frame(
    frame: int, context: dict[str, int | None], *, frame_domain: str = "auto"
) -> tuple[int, str, int | None]:
    requested = int(frame)
    if requested < 0:
        raise ValidationError(
            "Marker frame must be greater than or equal to 0.",
            details={"frame": frame},
            recoverability="not_applicable",
        )

    normalized_domain = _normalize_frame_domain(frame_domain)
    duration = context.get("duration")
    source_start = context.get("source_start") or 0
    source_end = context.get("source_end")

    if normalized_domain == "offset":
        return source_start + requested, "clip_offset", requested

    if normalized_domain == "source":
        return requested, "source", _marker_offset(requested, context)

    if normalized_domain == "raw":
        return requested, "raw", _marker_offset(requested, context)

    if duration is not None and 0 <= requested < duration:
        return source_start + requested, "clip_offset", requested

    if source_end is not None and source_start <= requested < source_end:
        return requested, "source", requested - source_start

    return requested, "raw", _marker_offset(requested, context)


def list_clip_markers(
    conn, name: Optional[str], *, ops_module
) -> list[dict[str, object]]:
    item = ops_module.cutagent_clip(conn, name)
    markers = item.GetMarkers() if hasattr(item, "GetMarkers") else {}
    context = _clip_marker_frame_context(item)

    if not markers:
        return []

    rows = []
    for frame_id, data in sorted(markers.items()):
        frame = int(frame_id)
        offset = _marker_offset(frame, context)
        record_frame = _marker_record_frame(frame, context)
        rows.append(
            {
                "frame": frame,
                "color": data.get("color", ""),
                "name": data.get("name", ""),
                "note": data.get("note", ""),
                "duration": data.get("duration", ""),
                "customData": data.get("customData", data.get("custom_data", "")),
                "source_frame": frame,
                "offset": offset,
                "record_frame": record_frame,
            }
        )

    return rows


def list_timeline_clip_markers(
    conn,
    *,
    track_type: str = "video",
    tracks: list[int] | tuple[int, ...] | None = None,
    color: str | None = None,
    visible_only: bool = True,
    authoritative_ids: bool = False,
) -> dict[str, object]:
    normalized_track_type, scan_track_types = _normalize_scan_track_type(track_type)
    selected_tracks = _normalize_scan_tracks(list(tracks) if tracks else None)
    color_filter = str(color).strip().lower() if color not in (None, "") else None
    timeline = getattr(conn, "timeline", None)
    if timeline is None:
        raise APICallFailed("No active timeline is available for clip marker scan.")

    markers: list[dict[str, object]] = []
    tracks_scanned: list[dict[str, int | str]] = []
    scanned_item_count = 0

    for current_type in scan_track_types:
        try:
            track_count = int(timeline.GetTrackCount(current_type) or 0)
        except Exception as exc:
            raise APICallFailed(
                "Failed to read timeline track count for clip marker scan.",
                details={"track_type": current_type, "error": str(exc)},
            ) from exc
        track_indices = selected_tracks or list(range(1, track_count + 1))
        for track_index in track_indices:
            if track_index > track_count:
                raise ValidationError(
                    "Track index not found.",
                    details={
                        "track_type": current_type,
                        "index": track_index,
                        "track_count": track_count,
                    },
                    recoverability="not_applicable",
                )
            tracks_scanned.append({"track_type": current_type, "index": track_index})
            try:
                items = timeline.GetItemListInTrack(current_type, track_index) or []
            except Exception as exc:
                raise APICallFailed(
                    "Failed to read timeline track items for clip marker scan.",
                    details={
                        "track_type": current_type,
                        "track_index": track_index,
                        "error": str(exc),
                    },
                ) from exc
            scanned_item_count += len(items)
            for item in items:
                marker_sources = _timeline_item_marker_sources(item)
                if not marker_sources:
                    continue
                context = _clip_marker_frame_context(item)
                seen_markers: set[tuple[int, str, str, str, str]] = set()
                for marker_scope, raw_markers in marker_sources:
                    for frame_id, data in sorted(raw_markers.items()):
                        try:
                            source_frame = int(frame_id)
                        except Exception:
                            continue
                        marker_data = data if isinstance(data, dict) else {}
                        marker_key = _marker_identity(source_frame, marker_data)
                        if marker_key in seen_markers:
                            continue
                        seen_markers.add(marker_key)
                        marker_color = str(marker_data.get("color", "") or "")
                        if color_filter and marker_color.lower() != color_filter:
                            continue
                        offset = _marker_offset(source_frame, context)
                        if visible_only and offset is None:
                            continue
                        record_frame = _marker_record_frame(source_frame, context)
                        markers.append(
                            {
                                "track_type": current_type,
                                "track_index": track_index,
                                "clip_name": _clip_display_name(item),
                                "timeline_item_id": _object_identifier(item),
                                **(
                                    {
                                        "timeline_item_unique_id": documented_unique_id(
                                            item
                                        )
                                    }
                                    if authoritative_ids
                                    else {}
                                ),
                                "marker_scope": marker_scope,
                                "color": marker_color,
                                "name": marker_data.get("name", ""),
                                "note": marker_data.get("note", ""),
                                "duration": marker_data.get("duration", ""),
                                "source_frame": source_frame,
                                "offset": offset,
                                "record_frame": record_frame,
                                "timecode": _record_timecode(conn, record_frame),
                                "clip_start": context.get("start"),
                                "clip_end": context.get("end"),
                                "source_start": context.get("source_start"),
                                "source_end": context.get("source_end"),
                            }
                        )

    markers.sort(key=_sort_marker_occurrence)
    return {
        "timeline": _timeline_name(conn),
        "track_type": normalized_track_type,
        "tracks": selected_tracks,
        "tracks_scanned": tracks_scanned,
        "scanned_item_count": scanned_item_count,
        "marker_occurrence_count": len(markers),
        "color_filter": str(color).strip() if color not in (None, "") else None,
        "visible_only": bool(visible_only),
        "markers": markers,
    }


def add_clip_marker(
    conn,
    clip_name: Optional[str],
    frame: int,
    color: str = "Blue",
    name: str = "",
    note: str = "",
    duration: int = 1,
    frame_domain: str = "auto",
    *,
    ops_module,
) -> bool:
    item = ops_module.cutagent_clip(conn, clip_name)
    context = _clip_marker_frame_context(item)
    marker_frame, _domain, _offset = _resolve_marker_frame(
        int(frame), context, frame_domain=frame_domain
    )
    result = item.AddMarker(marker_frame, color, name, note, duration)
    if result:
        return True
    raise APICallFailed("Failed to add marker.")


def delete_clip_marker(
    conn,
    clip_name: Optional[str],
    frame: int,
    frame_domain: str = "auto",
    *,
    ops_module,
) -> dict[str, object]:
    item = ops_module.cutagent_clip(conn, clip_name)
    context = _clip_marker_frame_context(item)
    marker_frame, domain, offset = _resolve_marker_frame(
        int(frame), context, frame_domain=frame_domain
    )
    deleter = getattr(item, "DeleteMarkerAtFrame", None)
    if not callable(deleter):
        raise APICallFailed("DeleteMarkerAtFrame not available.")
    result = deleter(marker_frame)
    if result is False:
        raise APICallFailed(
            "Failed to delete marker.",
            details={
                "clip": clip_name,
                "frame": marker_frame,
                "requested_frame": int(frame),
                "frame_domain": domain,
            },
        )
    return {
        "clip": clip_name or ops_module._clip_display_name(item),
        "requested_frame": int(frame),
        "frame": marker_frame,
        "frame_domain": domain,
        "offset": offset,
        "deleted": bool(result),
    }


def _take_count(item) -> int:
    try:
        return int(item.GetTakesCount() or 0)
    except Exception as exc:
        raise APICallFailed(
            "Failed to read take count.", details={"method": "GetTakesCount"}
        ) from exc


def _selected_take_index(item) -> int:
    try:
        return int(item.GetSelectedTakeIndex() or 0)
    except Exception:
        return 0


def _format_take_info(take) -> str:
    if not isinstance(take, dict):
        return str(take) if take else "?"

    parts: list[str] = []
    mpi = take.get("mediaPoolItem")
    if mpi is not None and hasattr(mpi, "GetName"):
        try:
            parts.append(str(mpi.GetName()))
        except Exception:
            pass
    if "startFrame" in take or "endFrame" in take:
        parts.append(f"{take.get('startFrame', '?')}..{take.get('endFrame', '?')}")
    return " ".join(parts) if parts else str(take)


def list_takes(conn, name: Optional[str], *, ops_module) -> list[dict[str, object]]:
    return list_takes_summary(conn, name, ops_module=ops_module)["takes"]


def _take_rows(
    item, *, count: int, selected: int, ops_module
) -> list[dict[str, object]]:
    rows = []
    for i in range(1, count + 1):
        try:
            take = item.GetTakeByIndex(i)
            rows.append(
                {
                    "index": i,
                    "selected": i == selected,
                    "info": ops_module._format_take_info(take),
                }
            )
        except Exception:
            rows.append({"index": i, "selected": i == selected, "info": "?"})
    return rows


def list_takes_summary(conn, name: Optional[str], *, ops_module) -> dict[str, object]:
    item = ops_module.cutagent_clip(conn, name)
    count = ops_module._take_count(item)
    selected = ops_module._selected_take_index(item)
    return {
        "clip": ops_module._clip_display_name(item, name),
        "take_count": count,
        "selected_take_index": selected,
        "takes": _take_rows(
            item, count=count, selected=selected, ops_module=ops_module
        ),
    }


def add_take(
    conn,
    clip_name: Optional[str],
    media_name: str,
    start_frame: Optional[int] = None,
    end_frame: Optional[int] = None,
    *,
    ops_module,
) -> bool:
    item = ops_module.cutagent_clip(conn, clip_name)
    media_item = media_pool.find_clip(conn, media_name)
    if not media_item:
        raise ValidationError(
            "Media Pool item for take was not found.", details={"media": media_name}
        )

    adder = getattr(item, "AddTake", None)
    if not callable(adder):
        raise APICallFailed("AddTake API is not available on this timeline item.")

    args = [media_item]
    if start_frame is not None:
        args.append(int(start_frame))
        if end_frame is not None:
            args.append(int(end_frame))
    elif end_frame is not None:
        raise ValidationError(
            "Specify --start-frame when using --end-frame.",
            details={"end_frame": end_frame},
        )

    try:
        result = bool(adder(*args))
    except Exception as exc:
        raise APICallFailed(
            "AddTake API call failed.",
            details={
                "clip": clip_name,
                "media": media_name,
                "start_frame": start_frame,
                "end_frame": end_frame,
            },
        ) from exc
    if result:
        return True
    raise APICallFailed(
        "Failed to add take.",
        details={
            "clip": clip_name,
            "media": media_name,
            "start_frame": start_frame,
            "end_frame": end_frame,
        },
    )


def select_take(conn, clip_name: Optional[str], index: int, *, ops_module) -> bool:
    if index < 1:
        raise ValidationError(
            "Take index must be 1 or greater.", details={"index": index}
        )

    item = ops_module.cutagent_clip(conn, clip_name)
    count = ops_module._take_count(item)
    if count < 1:
        raise ValidationError(
            "No takes available on this clip. Add a take first with `clip take add`.",
            details={"clip": clip_name, "take_count": count},
        )
    if index > count:
        raise ValidationError(
            f"Take index {index} is out of range; clip has {count} take(s).",
            details={"clip": clip_name, "index": index, "take_count": count},
        )

    selector = getattr(item, "SelectTakeByIndex", None)
    if not callable(selector):
        raise APICallFailed(
            "SelectTakeByIndex API is not available on this timeline item."
        )

    try:
        result = bool(selector(index))
    except Exception as exc:
        raise APICallFailed(
            "SelectTakeByIndex API call failed.",
            details={"clip": clip_name, "index": index},
        ) from exc
    if result:
        return True
    raise APICallFailed(
        f"Failed to select take {index}.",
        details={"clip": clip_name, "index": index, "take_count": count},
    )


def finalize_take(conn, clip_name: Optional[str], *, ops_module) -> bool:
    item = ops_module.cutagent_clip(conn, clip_name)
    count = ops_module._take_count(item)
    if count < 1:
        raise ValidationError(
            "No takes available on this clip. Add a take first with `clip take add`.",
            details={"clip": clip_name, "take_count": count},
        )
    finalizer = getattr(item, "FinalizeTake", None)
    if not callable(finalizer):
        raise APICallFailed("FinalizeTake API is not available on this timeline item.")
    try:
        result = bool(finalizer())
    except Exception as exc:
        raise APICallFailed(
            "FinalizeTake API call failed.", details={"clip": clip_name}
        ) from exc
    if result:
        return True
    raise APICallFailed(
        "Failed to finalize takes.", details={"clip": clip_name, "take_count": count}
    )
