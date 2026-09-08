"""Read text and image metadata from Media Pool template clips."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..errors import (
    AmbiguousMediaPoolItem,
    MediaPoolItemNotFound,
    TempAppendFailed,
    TempAppendNotAllowed,
    TemplateFieldNotFound,
)
from ..utils.timecode import parse_time_input, seconds_to_frames
from . import fusion_common, media_pool

TEXT_PROPERTY_KEYS = ("StyledText", "Styled Text", "Text", "Text1", "Title", "Subtitle")
IMAGE_PROPERTY_KEYS = ("File Path", "FilePath", "Source File", "Path", "Filename", "File Name", "Clip Path", "Media Path")
TEXT_TOOL_INPUT_KEYS = ("StyledText", "Styled Text", "Text", "Text1", "Title", "Subtitle")
IMAGE_TOOL_INPUT_KEYS = ("Filename", "Clip", "ClipName", "MediaSource", "MediaID", "Input7")
FIELD_ORDER = ("text", "image")


def parse_fields(value: str | list[str] | tuple[str, ...] | None) -> list[str]:
    if value is None:
        return list(FIELD_ORDER)
    if isinstance(value, str):
        raw_fields = value.split(",")
    else:
        raw_fields = []
        for item in value:
            raw_fields.extend(str(item).split(","))
    fields = []
    for raw in raw_fields:
        field = raw.strip().lower()
        if not field:
            continue
        if field not in FIELD_ORDER:
            raise TemplateFieldNotFound(
                "Unsupported template field.",
                details={"field": raw, "allowed_fields": list(FIELD_ORDER)},
            )
        if field not in fields:
            fields.append(field)
    return fields or list(FIELD_ORDER)


def parse_duration_frames(value: str | int | float, fps: float) -> int:
    if isinstance(value, int):
        frames = value
    else:
        frames = seconds_to_frames(parse_time_input(str(value), fps), fps)
    if frames <= 0:
        raise TemplateFieldNotFound("Duration must be greater than zero.", details={"duration": value, "fps": fps})
    return int(frames)


def _safe_name(obj: Any) -> str:
    getter = getattr(obj, "GetName", None)
    if callable(getter):
        try:
            value = getter()
        except Exception:
            value = None
        if value:
            return str(value)
    return ""


def _safe_props(item: Any) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    getter = getattr(item, "GetClipProperty", None)
    if callable(getter):
        try:
            props = getter() or {}
        except Exception:
            props = {}
        if isinstance(props, dict):
            merged.update(props)
    for method_name in ("GetMetadata", "GetThirdPartyMetadata"):
        metadata_getter = getattr(item, method_name, None)
        if not callable(metadata_getter):
            continue
        try:
            metadata = metadata_getter() or {}
        except Exception:
            metadata = {}
        if isinstance(metadata, dict):
            for key, value in metadata.items():
                merged.setdefault(str(key), value)
    return merged


def _read_property(item: Any, key: str) -> Any:
    props = _safe_props(item)
    if key in props:
        return props.get(key)
    getter = getattr(item, "GetClipProperty", None)
    if callable(getter):
        try:
            return getter(key)
        except Exception:
            return None
    return None


def _string_value(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (list, tuple, dict)):
        return None
    text = str(value).strip()
    return text or None


def _folder_matches(candidate: str, requested: str | None) -> bool:
    if not requested:
        return True
    candidate_norm = str(candidate or "").strip().strip("/")
    requested_norm = str(requested or "").strip().strip("/")
    return candidate_norm == requested_norm or candidate_norm.endswith("/" + requested_norm)


def _canonical_path(value: str) -> str:
    try:
        return str(Path(value).expanduser())
    except Exception:
        return str(value)


def _clip_id(clip: Any, props: dict[str, Any]) -> str | None:
    for method_name in ("GetMediaId", "GetUniqueId"):
        method = getattr(clip, method_name, None)
        if callable(method):
            try:
                value = method()
            except Exception:
                value = None
            if value:
                return str(value)
    for key in ("MediaId", "Media ID", "media_id", "Id", "ID"):
        value = props.get(key)
        if value:
            return str(value)
    return None


def _all_media_pool_matches(conn: Any) -> list[dict[str, Any]]:
    root = conn.media_pool.GetRootFolder()
    if not root:
        return []
    matches: list[dict[str, Any]] = []
    media_pool._collect_clip_object_matches(root, matches)  # source-of-truth traversal helper.
    return matches


def _candidate_summary(match: dict[str, Any]) -> dict[str, Any]:
    props = match.get("props") or {}
    clip = match.get("clip")
    return {
        "name": match.get("name"),
        "folder": match.get("folder"),
        "media_id": _clip_id(clip, props),
        "source_path": media_pool._canonical_source_path(props, clip),
    }


def _cutagent_clip(conn: Any, clip_ref: str, *, exact: bool = False, folder: str | None = None) -> dict[str, Any]:
    ref = str(clip_ref or "").strip()
    matches = _all_media_pool_matches(conn)
    ref_path = _canonical_path(ref)
    exact_matches = []
    fuzzy_matches = []
    for match in matches:
        if not _folder_matches(str(match.get("folder", "")), folder):
            continue
        props = match.get("props") or {}
        clip = match["clip"]
        name = str(match.get("name") or "")
        source_path = media_pool._canonical_source_path(props, clip)
        source_candidates = {str(source_path or ""), _canonical_path(str(source_path or ""))}
        media_id = _clip_id(clip, props)
        is_exact = ref in {name, str(media_id or ""), *source_candidates} or ref_path in source_candidates
        if is_exact:
            exact_matches.append(match)
            continue
        if not exact and ref.lower() in name.lower():
            fuzzy_matches.append(match)
    candidates = exact_matches or fuzzy_matches
    if not candidates:
        raise MediaPoolItemNotFound(details={"clip": clip_ref, "folder": folder})
    if len(candidates) > 1:
        raise AmbiguousMediaPoolItem(details={"clip": clip_ref, "folder": folder, "candidates": [_candidate_summary(m) for m in candidates]})
    return candidates[0]


def _attempt(attempts: list[dict[str, Any]], source: str, field: str, found: bool, **extra: Any) -> None:
    row = {"source": source, "field": field, "found": bool(found)}
    row.update({key: value for key, value in extra.items() if value is not None})
    attempts.append(row)


def _property_result(source: str, field: str, item: Any, attempts: list[dict[str, Any]]) -> dict[str, Any] | None:
    keys = TEXT_PROPERTY_KEYS if field == "text" else IMAGE_PROPERTY_KEYS
    props = _safe_props(item)
    for key in keys:
        value = _string_value(props.get(key) if key in props else _read_property(item, key))
        if value:
            _attempt(attempts, source, field, True, property=key)
            return {"value": value, "source": source, "property": key}
    if field == "text":
        candidates = [
            (key, _string_value(value))
            for key, value in props.items()
            if "text" in str(key).lower() or "title" in str(key).lower()
        ]
        candidates = [(key, value) for key, value in candidates if value]
        if candidates:
            key, value = max(candidates, key=lambda row: len(row[1] or ""))
            _attempt(attempts, source, field, True, property=str(key), heuristic="longest_text_or_title_property")
            return {"value": value, "source": source, "property": str(key), "heuristic": "longest_text_or_title_property"}
    _attempt(attempts, source, field, False)
    return None


def _tool_result(source: str, field: str, holder: Any, attempts: list[dict[str, Any]]) -> dict[str, Any] | None:
    keys = TEXT_TOOL_INPUT_KEYS if field == "text" else IMAGE_TOOL_INPUT_KEYS
    tools = fusion_common.iter_tool_list(holder, False)
    for tool in tools:
        tool_name = fusion_common.tool_name(tool)
        for key in keys:
            value = _string_value(fusion_common.read_tool_input(tool, key))
            if value:
                _attempt(attempts, source, field, True, tool=tool_name, input=key)
                return {"value": value, "source": source, "tool": tool_name, "input": key}
    _attempt(attempts, source, field, False)
    return None


def _fusion_result(source: str, field: str, item: Any, attempts: list[dict[str, Any]]) -> dict[str, Any] | None:
    comp = fusion_common.get_fusion_comp_for_item(item)
    if not comp:
        _attempt(attempts, source, field, False, reason="fusion_comp_unavailable")
        return None
    return _tool_result(source, field, comp, attempts)


def _timeline_end(conn: Any) -> int:
    timeline = getattr(conn, "timeline", None)
    if timeline is None:
        return 0
    getter = getattr(timeline, "GetEndFrame", None)
    if callable(getter):
        try:
            return int(getter() or 0)
        except Exception:
            pass
    end = 0
    track_count = 0
    try:
        track_count = int(timeline.GetTrackCount("video") or 0)
    except Exception:
        track_count = 0
    for index in range(1, track_count + 1):
        try:
            items = timeline.GetItemListInTrack("video", index) or []
        except Exception:
            items = []
        for item in items:
            getter = getattr(item, "GetEnd", None)
            if callable(getter):
                try:
                    end = max(end, int(getter() or 0))
                except Exception:
                    pass
    return end


def _ensure_track(conn: Any, track_index: int) -> dict[str, Any]:
    timeline = conn.timeline
    try:
        before = int(timeline.GetTrackCount("video") or 0)
    except Exception:
        before = 0
    count = before
    added = 0
    while count < track_index:
        adder = getattr(timeline, "AddTrack", None)
        if not callable(adder):
            raise TempAppendFailed("Timeline.AddTrack is unavailable.", details={"track": track_index, "current_video_tracks": count})
        result = adder("video")
        if result is False:
            raise TempAppendFailed("Failed to add required video track.", details={"track": track_index, "current_video_tracks": count})
        added += 1
        try:
            count = int(timeline.GetTrackCount("video") or 0)
        except Exception:
            count += 1
    return {"requested_track": track_index, "pre_video_tracks": before, "final_video_tracks": count, "added_tracks": added}


def _find_appended_item(conn: Any, track_index: int, record_frame: int) -> Any | None:
    try:
        items = conn.timeline.GetItemListInTrack("video", track_index) or []
    except Exception:
        items = []
    for item in items:
        getter = getattr(item, "GetStart", None)
        if callable(getter):
            try:
                if int(getter() or 0) == int(record_frame):
                    return item
            except Exception:
                continue
    return None


def _append_temp_item(conn: Any, clip: Any, *, track_index: int, duration_frames: int, gap_frames: int) -> tuple[Any, dict[str, Any]]:
    _ensure_track(conn, track_index)
    record_frame = _timeline_end(conn) + int(gap_frames)
    clip_info = {
        "mediaPoolItem": clip,
        "startFrame": 0,
        "endFrame": int(duration_frames),
        "trackIndex": int(track_index),
        "recordFrame": int(record_frame),
        "trackType": "video",
    }
    try:
        result = conn.media_pool.AppendToTimeline([clip_info])
    except Exception as exc:
        raise TempAppendFailed(str(exc), details={"clip_info": {**clip_info, "mediaPoolItem": _safe_name(clip)}}) from exc
    if not result:
        raise TempAppendFailed(details={"clip_info": {**clip_info, "mediaPoolItem": _safe_name(clip)}, "append_result": result})
    item = result[0] if isinstance(result, list) and result else result
    if item is True:
        item = _find_appended_item(conn, track_index, record_frame)
    if not item:
        raise TempAppendFailed("Temporary item could not be found after append.", details={"record_frame": record_frame, "track_index": track_index})
    return item, {"track_index": int(track_index), "record_frame": int(record_frame), "duration_frames": int(duration_frames)}


def _delete_temp_item(conn: Any, item: Any) -> dict[str, Any]:
    deleter = getattr(conn.timeline, "DeleteClips", None)
    if not callable(deleter):
        return {"temporary_item_deleted": False, "cleanup_error": "Timeline.DeleteClips unavailable"}
    try:
        result = deleter([item], False)
    except TypeError:
        try:
            result = deleter([item])
        except Exception as exc:
            return {"temporary_item_deleted": False, "cleanup_error": str(exc)}
    except Exception as exc:
        return {"temporary_item_deleted": False, "cleanup_error": str(exc)}
    return {"temporary_item_deleted": result is not False, "cleanup_api_result": result}


def _nested_items(item: Any) -> list[Any]:
    nested = []
    for method_name in ("GetTimeline", "GetNestedTimeline", "GetCompoundTimeline"):
        method = getattr(item, method_name, None)
        if callable(method):
            try:
                timeline = method()
            except Exception:
                timeline = None
            if timeline:
                nested.append(timeline)
    return nested


def _nested_result(field: str, item: Any, attempts: list[dict[str, Any]]) -> dict[str, Any] | None:
    for timeline in _nested_items(item):
        track_count = 0
        try:
            track_count = int(timeline.GetTrackCount("video") or 0)
        except Exception:
            track_count = 0
        for index in range(1, track_count + 1):
            try:
                items = timeline.GetItemListInTrack("video", index) or []
            except Exception:
                items = []
            for nested_item in items:
                result = _property_result("nested_timeline_text", field, nested_item, attempts)
                if result:
                    return result
                result = _fusion_result("nested_timeline_text", field, nested_item, attempts)
                if result:
                    return result
    _attempt(attempts, "nested_timeline_text", field, False)
    return None


def _missing_result(result: dict[str, Any], missing_fields: list[str], *, allow_temp_append: bool) -> TemplateFieldNotFound:
    hint = "allow_temp_append_required" if not allow_temp_append else "field_not_exposed_by_resolve"
    return TemplateFieldNotFound(
        details={
            "reason": hint,
            "missing_fields": missing_fields,
            "attempts": result["attempts"],
            "result": result,
        }
    )


def extract_media_template(
    conn: Any,
    clip_ref: str,
    fields: str | list[str] | tuple[str, ...] | None,
    exact: bool = False,
    folder: str | None = None,
    allow_temp_append: bool = False,
    temp_track: int | None = None,
    temp_duration_frames: int = 24,
    include_nested: bool = True,
    cleanup: bool = True,
    temp_gap_frames: int = 24,
) -> dict[str, Any]:
    requested_fields = parse_fields(fields)
    match = _cutagent_clip(conn, clip_ref, exact=exact, folder=folder)
    clip = match["clip"]
    result: dict[str, Any] = {
        "clip": clip_ref,
        "matched_clip": _candidate_summary(match),
        "fields_requested": requested_fields,
        "attempts": [],
        "cleanup": {
            "temporary_item_created": False,
            "temporary_item_deleted": None,
            "requested": bool(cleanup),
        },
    }
    found: dict[str, dict[str, Any] | None] = {field: None for field in requested_fields}

    for field in requested_fields:
        found[field] = _property_result("media_pool_properties", field, clip, result["attempts"])
        if found[field] is None:
            found[field] = _fusion_result("media_pool_fusion_comp", field, clip, result["attempts"])

    temp_item = None
    if any(value is None for value in found.values()):
        if not allow_temp_append:
            raise _missing_result(result, [field for field, value in found.items() if value is None], allow_temp_append=False)
        timeline = getattr(conn, "timeline", None)
        if timeline is None:
            raise TempAppendNotAllowed(details={"reason": "active_timeline_required", "result": result})
        track_index = int(temp_track) if temp_track is not None else max(1, int(getattr(timeline, "GetTrackCount", lambda _kind: 0)("video") or 0))
        temp_item, temp_details = _append_temp_item(
            conn,
            clip,
            track_index=track_index,
            duration_frames=temp_duration_frames,
            gap_frames=temp_gap_frames,
        )
        result["cleanup"].update({"temporary_item_created": True, "temporary_item_deleted": False, "temporary_item": temp_details})
        try:
            for field in requested_fields:
                if found[field] is not None:
                    continue
                found[field] = _property_result("temp_timeline_item_properties", field, temp_item, result["attempts"])
                if found[field] is None:
                    found[field] = _fusion_result("temp_timeline_fusion_tool", field, temp_item, result["attempts"])
                if found[field] is None and include_nested:
                    found[field] = _nested_result(field, temp_item, result["attempts"])
        finally:
            if cleanup and temp_item is not None:
                result["cleanup"].update(_delete_temp_item(conn, temp_item))
            elif temp_item is not None:
                result["cleanup"]["temporary_item_deleted"] = False
                result["cleanup"]["kept_by_request"] = True

    missing_fields = []
    for field in requested_fields:
        result[field] = found[field]
        if found[field] is None:
            missing_fields.append(field)
            _attempt(result["attempts"], "not_found", field, False)

    if result["cleanup"].get("temporary_item_created") is False:
        result["cleanup"]["temporary_item_deleted"] = False
    if result["cleanup"].get("requested") and result["cleanup"].get("temporary_item_created") and result["cleanup"].get("temporary_item_deleted") is False:
        result.setdefault("warnings", []).append({"code": "TEMP_CLEANUP_FAILED", "message": "Temporary timeline item was not deleted."})

    if missing_fields:
        raise _missing_result(result, missing_fields, allow_temp_append=allow_temp_append)
    return result
