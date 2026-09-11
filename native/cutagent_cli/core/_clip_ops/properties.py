from __future__ import annotations

import math
from typing import Any, Optional

from ...errors import APICallFailed, ValidationError
from ...policy import require_api_method

VALID_CLIP_LIST_TRACK_TYPES = {"video", "audio", "subtitle"}

_CLIP_COLOR_CANONICAL = {
    color.lower(): color
    for color in (
        "Apricot",
        "Blue",
        "Brown",
        "Cocoa",
        "Cream",
        "Cyan",
        "Fuchsia",
        "Green",
        "Lavender",
        "Lemon",
        "Lime",
        "Mint",
        "Navy",
        "Olive",
        "Orange",
        "Pink",
        "Purple",
        "Red",
        "Rose",
        "Sand",
        "Sky",
        "Teal",
        "Violet",
        "Yellow",
    )
}


def normalize_clip_list_track_type(track_type: str = "video") -> str:
    normalized_track_type = str(track_type or "").strip().lower()
    if normalized_track_type not in VALID_CLIP_LIST_TRACK_TYPES:
        raise ValidationError(
            "Track type must be one of: video, audio, subtitle.",
            details={"track_type": track_type, "allowed": sorted(VALID_CLIP_LIST_TRACK_TYPES)},
            recoverability="not_applicable",
        )
    return normalized_track_type


def validate_clip_list_track_index(index: int = 1) -> int:
    if int(index) < 1:
        raise ValidationError(
            "Track index must be 1 or greater.",
            details={"track": index},
            recoverability="not_applicable",
        )
    return int(index)


def validate_clip_list_request(conn, track_type: str = "video", index: int = 1) -> tuple[str, int]:
    normalized_track_type = normalize_clip_list_track_type(track_type)
    normalized_index = validate_clip_list_track_index(index)

    get_track_count = getattr(conn.timeline, "GetTrackCount", None)
    if callable(get_track_count):
        try:
            track_count = int(get_track_count(normalized_track_type) or 0)
        except Exception:
            track_count = None
        if track_count is not None and normalized_index > track_count:
            raise ValidationError(
                (
                    f"{normalized_track_type.title()} track {normalized_index} is out of range; "
                    f"timeline has {track_count} {normalized_track_type} track(s)."
                ),
                details={
                    "track_type": normalized_track_type,
                    "track": normalized_index,
                    "track_count": track_count,
                },
                recoverability="not_applicable",
            )

    return normalized_track_type, normalized_index


def normalize_clip_color(color: str) -> str:
    normalized = str(color).strip().lower()
    canonical = _CLIP_COLOR_CANONICAL.get(normalized)
    if canonical is None:
        raise ValidationError(
            "Clip color must be a supported DaVinci Resolve color name.",
            details={"color": color, "allowed": sorted(_CLIP_COLOR_CANONICAL.values())},
            recoverability="not_applicable",
        )
    return canonical


def normalize_clip_flag_color(color: str) -> str:
    normalized = str(color).strip().lower()
    canonical = _CLIP_COLOR_CANONICAL.get(normalized)
    if canonical is None:
        raise ValidationError(
            "Clip flag color must be a supported DaVinci Resolve color name.",
            details={"color": color, "allowed": sorted(_CLIP_COLOR_CANONICAL.values())},
            recoverability="not_applicable",
        )
    return canonical


def normalize_cache_type(cache_type: str) -> str:
    normalized_type = str(cache_type).strip().lower()
    if normalized_type not in {"color", "fusion"}:
        raise ValidationError(
            "Cache type must be 'color' or 'fusion'.",
            details={"cache_type": cache_type},
            recoverability="not_applicable",
        )
    return normalized_type


_CACHE_MODE_TO_NATIVE_VALUE = {
    "disable": 0,
    "enable": 1,
    "auto": -1,
}
_CACHE_NATIVE_VALUE_TO_MODE = {
    0: "disable",
    1: "enable",
    -1: "auto",
}


def normalize_cache_mode(cache_type: str, mode: str) -> str:
    normalized_type = normalize_cache_type(cache_type)
    normalized_mode = str(mode or "").strip().lower()
    if normalized_mode not in _CACHE_MODE_TO_NATIVE_VALUE:
        raise ValidationError(
            "Cache mode must be enable, disable, or auto.",
            details={
                "cache_type": normalized_type,
                "mode": mode,
                "allowed_modes": ["enable", "disable", "auto"],
            },
            recoverability="not_applicable",
        )
    if normalized_type == "color" and normalized_mode == "auto":
        raise ValidationError(
            "Color output cache does not support auto mode through this DaVinci Resolve API.",
            details={
                "cache_type": normalized_type,
                "mode": normalized_mode,
                "allowed_modes": ["enable", "disable"],
                "fusion_allowed_modes": ["enable", "disable", "auto"],
            },
            recoverability="not_applicable",
        )
    return normalized_mode


def _native_cache_value(value: Any) -> int | Any:
    if isinstance(value, bool):
        return 1 if value else 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return value


def _cache_state_payload(item, name: Optional[str], cache_type: str, raw_value: Any) -> dict[str, Any]:
    native_value = _native_cache_value(raw_value)
    mode = _CACHE_NATIVE_VALUE_TO_MODE.get(native_value, "unknown")
    enabled = True if mode == "enable" else False if mode == "disable" else None
    return {
        "clip": name or (item.GetName() if hasattr(item, "GetName") else None),
        "cache_type": cache_type,
        "mode": mode,
        "enabled": enabled,
        "native_value": native_value,
    }


def list_clips(conn, track_type: str = "video", index: int = 1) -> list[dict[str, Any]]:
    normalized_track_type, normalized_index = validate_clip_list_request(conn, track_type, index)
    items = conn.timeline.GetItemListInTrack(normalized_track_type, normalized_index) or []

    rows = []
    for item in items:
        name = item.GetName() if hasattr(item, "GetName") else "?"
        start = item.GetStart() if hasattr(item, "GetStart") else ""
        end = item.GetEnd() if hasattr(item, "GetEnd") else ""
        dur = item.GetDuration() if hasattr(item, "GetDuration") else ""
        rows.append({"name": name, "start": start, "end": end, "duration": dur})

    return rows


def get_clip_info(conn, name: Optional[str] = None, *, ops_module) -> dict[str, Any]:
    item = ops_module.cutagent_clip(conn, name)

    data = {"name": item.GetName() if hasattr(item, "GetName") else "?"}
    for attr in ["GetStart", "GetEnd", "GetDuration", "GetLeftOffset", "GetRightOffset"]:
        try:
            val = getattr(item, attr, lambda: None)()
            if val is not None:
                data[attr.replace("Get", "").lower()] = val
        except Exception:
            pass

    try:
        fc = item.GetFusionCompCount()
        data["fusion_comp_count"] = fc
    except Exception:
        pass

    try:
        props = item.GetProperty()
        if isinstance(props, dict):
            for k, v in props.items():
                data[k] = v
    except Exception:
        pass

    return data


def get_clip_property(conn, name: Optional[str], key: Optional[str] = None, *, ops_module) -> Any:
    item = ops_module.cutagent_clip(conn, name)

    if key:
        return item.GetProperty(key) if hasattr(item, "GetProperty") else None
    props = item.GetProperty() if hasattr(item, "GetProperty") else {}
    return props if isinstance(props, dict) else {"properties": str(props)}


def set_clip_property(conn, name: Optional[str], key: str, value: str, *, ops_module) -> bool:
    item = ops_module.cutagent_clip(conn, name)
    result = item.SetProperty(key, value)
    if result:
        return True
    raise APICallFailed(f"Failed to set property {key}.")


def get_clip_color(conn, name: Optional[str], *, ops_module) -> str:
    item = ops_module.cutagent_clip(conn, name)
    return item.GetClipColor()


def set_clip_color(conn, name: Optional[str], color: str, *, ops_module) -> None:
    item = ops_module.cutagent_clip(conn, name)
    item.SetClipColor(normalize_clip_color(color))


def clear_clip_color(conn, name: Optional[str], *, ops_module) -> None:
    item = ops_module.cutagent_clip(conn, name)
    item.ClearClipColor()


def get_clip_flags(conn, name: Optional[str], *, ops_module) -> list[str]:
    item = ops_module.cutagent_clip(conn, name)
    flags = item.GetFlagList()
    return flags if flags else []


def add_clip_flag(conn, name: Optional[str], color: str, *, ops_module) -> None:
    item = ops_module.cutagent_clip(conn, name)
    item.AddFlag(normalize_clip_flag_color(color))


def clear_clip_flags(conn, name: Optional[str], *, ops_module) -> None:
    item = ops_module.cutagent_clip(conn, name)
    item.ClearFlags("")


def get_clip_transform(conn, name: Optional[str], *, ops_module) -> dict[str, Any]:
    item = ops_module.cutagent_clip(conn, name)
    data = {}
    for prop in [
        "ZoomX",
        "ZoomY",
        "Pan",
        "Tilt",
        "RotationAngle",
        "AnchorPointX",
        "AnchorPointY",
        "Pitch",
        "Yaw",
        "FlipX",
        "FlipY",
        "CropLeft",
        "CropRight",
        "CropTop",
        "CropBottom",
        "Opacity",
        "CompositeMode",
        "Distortion",
        "DynamicZoomEase",
    ]:
        try:
            val = item.GetProperty(prop)
            if val is not None:
                if prop == "DynamicZoomEase":
                    val = ops_module._serialize_dynamic_zoom_ease(val)
                data[prop] = val
        except Exception:
            pass
    return data


def _transform_properties(
    conn,
    *,
    zoom_x: Optional[float] = None,
    zoom_y: Optional[float] = None,
    zoom: Optional[float] = None,
    position_x: Optional[float] = None,
    position_y: Optional[float] = None,
    rotation: Optional[float] = None,
    anchor_x: Optional[float] = None,
    anchor_y: Optional[float] = None,
    pitch: Optional[float] = None,
    yaw: Optional[float] = None,
    flip_x: Optional[bool] = None,
    flip_y: Optional[bool] = None,
    opacity: Optional[float] = None,
    crop_left: Optional[float] = None,
    crop_right: Optional[float] = None,
    crop_top: Optional[float] = None,
    crop_bottom: Optional[float] = None,
    distortion: Optional[float] = None,
    dynamic_zoom_ease: Optional[str] = None,
    ops_module,
) -> dict[str, Any]:
    props: dict[str, Any] = {}
    if zoom is not None:
        props["ZoomX"] = zoom
        props["ZoomY"] = zoom
    if zoom_x is not None:
        props["ZoomX"] = zoom_x
    if zoom_y is not None:
        props["ZoomY"] = zoom_y
    if position_x is not None:
        props["Pan"] = position_x
    if position_y is not None:
        props["Tilt"] = position_y
    if rotation is not None:
        props["RotationAngle"] = rotation
    if anchor_x is not None:
        props["AnchorPointX"] = anchor_x
    if anchor_y is not None:
        props["AnchorPointY"] = anchor_y
    if pitch is not None:
        props["Pitch"] = pitch
    if yaw is not None:
        props["Yaw"] = yaw
    if flip_x is not None:
        props["FlipX"] = flip_x
    if flip_y is not None:
        props["FlipY"] = flip_y
    if opacity is not None:
        props["Opacity"] = opacity
    if crop_left is not None:
        props["CropLeft"] = crop_left
    if crop_right is not None:
        props["CropRight"] = crop_right
    if crop_top is not None:
        props["CropTop"] = crop_top
    if crop_bottom is not None:
        props["CropBottom"] = crop_bottom
    if distortion is not None:
        props["Distortion"] = distortion
    if dynamic_zoom_ease is not None:
        props["DynamicZoomEase"] = ops_module._get_dynamic_zoom_ease_constant(conn, dynamic_zoom_ease)
    return props


def _apply_transform_properties(item, props: dict[str, Any]) -> list[str]:
    failed: list[str] = []
    for key, value in props.items():
        result = item.SetProperty(key, value)
        if result is False:
            failed.append(key)
    return failed


def _mismatched_transform_properties(item, props: dict[str, Any]) -> list[str]:
    """Read the changed Inspector section once and return values that did not stick."""

    try:
        actual = item.GetProperty()
    except Exception:
        return sorted(props)
    if not isinstance(actual, dict):
        return sorted(props)
    mismatched = []
    for key, expected in props.items():
        value = actual.get(key)
        if isinstance(expected, bool):
            matches = value is expected
        elif isinstance(expected, (int, float)) and not isinstance(expected, bool):
            matches = (
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and math.isfinite(float(value))
                and math.isclose(float(value), float(expected), rel_tol=0.0, abs_tol=1e-6)
            )
        else:
            matches = value == expected
        if not matches:
            mismatched.append(key)
    return sorted(mismatched)


def _item_display_name(item) -> str:
    try:
        return str(item.GetName() or "")
    except Exception:
        return ""


def _item_name_matches(item, expected_name: str, *, ops_module) -> bool:
    expected = str(expected_name or "").strip().lower()
    if not expected:
        return True
    candidates = set()
    try:
        candidates.update(str(value).strip().lower() for value in ops_module._item_name_candidates(item))
    except Exception:
        pass
    name = _item_display_name(item).strip().lower()
    if name:
        candidates.add(name)
    return expected in {value for value in candidates if value}


def _resolve_transform_item(
    conn,
    *,
    name: Optional[str],
    track_type: str,
    track: int | None,
    record_frame: str | int | None,
    ops_module,
):
    if (track is None) != (record_frame is None):
        raise ValidationError(
            "Batch clip transform entries must provide track and record_frame together.",
            details={"clip": name, "track": track, "record_frame": record_frame},
            recoverability="not_applicable",
        )
    if track is not None and record_frame is not None:
        item = ops_module.find_item_by_track_record(conn, track, record_frame, track_type=track_type)
        if name and not _item_name_matches(item, str(name), ops_module=ops_module):
            raise ValidationError(
                "Timeline item matched by track/record_frame did not match the requested name.",
                details={
                    "clip": name,
                    "track_type": track_type,
                    "track": track,
                    "record_frame": record_frame,
                    "matched_name": _item_display_name(item),
                },
                recoverability="not_applicable",
            )
        return item
    return ops_module.cutagent_clip(conn, name)


def set_clip_transform(
    conn,
    name: Optional[str],
    zoom_x: Optional[float] = None,
    zoom_y: Optional[float] = None,
    zoom: Optional[float] = None,
    position_x: Optional[float] = None,
    position_y: Optional[float] = None,
    rotation: Optional[float] = None,
    anchor_x: Optional[float] = None,
    anchor_y: Optional[float] = None,
    pitch: Optional[float] = None,
    yaw: Optional[float] = None,
    flip_x: Optional[bool] = None,
    flip_y: Optional[bool] = None,
    opacity: Optional[float] = None,
    crop_left: Optional[float] = None,
    crop_right: Optional[float] = None,
    crop_top: Optional[float] = None,
    crop_bottom: Optional[float] = None,
    distortion: Optional[float] = None,
    dynamic_zoom_ease: Optional[str] = None,
    *,
    ops_module,
) -> None:
    item = ops_module.cutagent_clip(conn, name)
    props = _transform_properties(
        conn,
        zoom_x=zoom_x,
        zoom_y=zoom_y,
        zoom=zoom,
        position_x=position_x,
        position_y=position_y,
        rotation=rotation,
        anchor_x=anchor_x,
        anchor_y=anchor_y,
        pitch=pitch,
        yaw=yaw,
        flip_x=flip_x,
        flip_y=flip_y,
        opacity=opacity,
        crop_left=crop_left,
        crop_right=crop_right,
        crop_top=crop_top,
        crop_bottom=crop_bottom,
        distortion=distortion,
        dynamic_zoom_ease=dynamic_zoom_ease,
        ops_module=ops_module,
    )
    failed = _apply_transform_properties(item, props)
    if failed:
        applied = sorted(set(props) - set(failed))
        raise APICallFailed(
            "DaVinci Resolve rejected one or more clip transform properties.",
            details={"failed_properties": sorted(failed), "applied_properties": applied},
        )
    mismatched = _mismatched_transform_properties(item, props)
    if mismatched:
        raise APICallFailed(
            "DaVinci Resolve clip transform readback did not match the requested values.",
            details={"mismatched_properties": mismatched},
        )


def set_clip_transform_batch(conn, entries: list[dict[str, Any]], *, ops_module) -> dict[str, Any]:
    if not entries:
        raise ValidationError(
            "Batch clip transform requires at least one entry.",
            details={"entry_count": 0},
            recoverability="not_applicable",
        )

    prepared: list[dict[str, Any]] = []
    for index, raw_entry in enumerate(entries):
        if not isinstance(raw_entry, dict):
            raise ValidationError(
                "Batch clip transform entries must be JSON objects.",
                details={"index": index, "entry": raw_entry},
                recoverability="not_applicable",
            )
        transform = raw_entry.get("transform") if isinstance(raw_entry.get("transform"), dict) else raw_entry
        name = raw_entry.get("clip") or raw_entry.get("name") or raw_entry.get("clip_name")
        track = raw_entry.get("track", raw_entry.get("track_index"))
        record_frame = raw_entry.get("record_frame", raw_entry.get("recordFrame", raw_entry.get("at")))
        track_type = str(raw_entry.get("track_type") or "video").strip().lower() or "video"

        props = _transform_properties(
            conn,
            zoom_x=transform.get("zoom_x"),
            zoom_y=transform.get("zoom_y"),
            zoom=transform.get("zoom"),
            position_x=transform.get("position_x"),
            position_y=transform.get("position_y"),
            rotation=transform.get("rotation"),
            anchor_x=transform.get("anchor_x"),
            anchor_y=transform.get("anchor_y"),
            pitch=transform.get("pitch"),
            yaw=transform.get("yaw"),
            flip_x=transform.get("flip_x"),
            flip_y=transform.get("flip_y"),
            opacity=transform.get("opacity"),
            crop_left=transform.get("crop_left"),
            crop_right=transform.get("crop_right"),
            crop_top=transform.get("crop_top"),
            crop_bottom=transform.get("crop_bottom"),
            distortion=transform.get("distortion"),
            dynamic_zoom_ease=transform.get("dynamic_zoom_ease"),
            ops_module=ops_module,
        )
        if not props:
            raise ValidationError(
                "Batch clip transform entry does not contain any transform properties.",
                details={"index": index, "entry": raw_entry},
                recoverability="not_applicable",
            )

        item = _resolve_transform_item(
            conn,
            name=str(name) if name is not None else None,
            track_type=track_type,
            track=int(track) if track is not None else None,
            record_frame=record_frame,
            ops_module=ops_module,
        )
        prepared.append(
            {
                "index": index,
                "raw_entry": raw_entry,
                "item": item,
                "clip": str(name) if name is not None else _item_display_name(item),
                "track_type": track_type,
                "track": int(track) if track is not None else None,
                "record_frame": record_frame,
                "properties": props,
            }
        )

    results: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for entry in prepared:
        index = int(entry["index"])
        item = entry["item"]
        props = entry["properties"]
        failed = _apply_transform_properties(item, props)
        if not failed:
            failed = _mismatched_transform_properties(item, props)
        if failed:
            failure = {
                "index": index,
                "clip": entry["clip"],
                "track_type": entry["track_type"],
                "track": entry["track"],
                "record_frame": entry["record_frame"],
                "properties": props,
                "applied": False,
                "failed_properties": failed,
            }
            failures.append(failure)
            results.append(failure)
            continue
        results.append(
            {
                "index": index,
                "clip": entry["clip"],
                "track_type": entry["track_type"],
                "track": entry["track"],
                "record_frame": entry["record_frame"],
                "properties": props,
                "applied": True,
            }
        )

    applied_count = sum(1 for row in results if row.get("applied") is True)
    payload = {
        "action": "clip.transform.batch",
        "status": "partial" if failures else "applied",
        "requested_count": len(entries),
        "applied_count": applied_count,
        "failed_count": len(failures),
        "results": results,
    }
    if failures:
        payload["failures"] = failures
        payload["warning"] = (
            "One or more transform entries failed after pre-validation. Successful entries are reported explicitly; "
            "the command does not raise a failed envelope after partial timeline mutation."
        )
    return payload


def reset_clip_transform(conn, name: Optional[str], *, ops_module) -> None:
    item = ops_module.cutagent_clip(conn, name)

    defaults = {
        "ZoomX": 1.0,
        "ZoomY": 1.0,
        "Pan": 0.0,
        "Tilt": 0.0,
        "RotationAngle": 0.0,
        "AnchorPointX": 0.0,
        "AnchorPointY": 0.0,
        "Pitch": 0.0,
        "Yaw": 0.0,
        "FlipX": False,
        "FlipY": False,
        "CropLeft": 0.0,
        "CropRight": 0.0,
        "CropTop": 0.0,
        "CropBottom": 0.0,
        "Opacity": 100.0,
        "Distortion": 0.0,
        "DynamicZoomEase": ops_module._get_dynamic_zoom_ease_constant(conn, "linear"),
    }
    for prop, value in defaults.items():
        item.SetProperty(prop, value)


def get_clip_cache_state(
    conn,
    name: Optional[str] = None,
    *,
    cache_type: str = "color",
    ops_module,
) -> dict[str, Any]:
    item = ops_module.cutagent_clip(conn, name)
    normalized_type = normalize_cache_type(cache_type)
    getter_name = "GetIsColorOutputCacheEnabled" if normalized_type == "color" else "GetIsFusionOutputCacheEnabled"
    getter = require_api_method(
        item,
        getter_name,
        capability_id="clip.cache_control",
        runtime_object="timeline_item",
    )
    return _cache_state_payload(item, name, normalized_type, getter())


def set_clip_cache_state(
    conn,
    name: Optional[str] = None,
    *,
    cache_type: str = "color",
    enabled: Optional[bool] = None,
    mode: Optional[str] = None,
    ops_module,
) -> dict[str, Any]:
    item = ops_module.cutagent_clip(conn, name)
    normalized_type = normalize_cache_type(cache_type)
    if mode is None:
        if enabled is None:
            raise ValidationError(
                "Specify a cache mode or enabled state.",
                details={"cache_type": normalized_type, "mode": mode, "enabled": enabled},
                recoverability="not_applicable",
            )
        mode = "enable" if bool(enabled) else "disable"
    normalized_mode = normalize_cache_mode(normalized_type, mode)
    requested_value = _CACHE_MODE_TO_NATIVE_VALUE[normalized_mode]
    setter_name = "SetColorOutputCache" if normalized_type == "color" else "SetFusionOutputCache"
    setter = require_api_method(
        item,
        setter_name,
        capability_id="clip.cache_control",
        runtime_object="timeline_item",
    )
    result = setter(requested_value)
    readback = ops_module.get_clip_cache_state(conn, name, cache_type=normalized_type)
    readback["requested_mode"] = normalized_mode
    readback["requested_native_value"] = requested_value
    if result is False and readback["mode"] != normalized_mode:
        raise APICallFailed(
            "Failed to update clip cache state.",
            details={
                "clip": name or (item.GetName() if hasattr(item, "GetName") else None),
                "cache_type": normalized_type,
                "mode": normalized_mode,
                "native_value": requested_value,
                "actual_mode": readback["mode"],
                "actual_native_value": readback["native_value"],
            },
        )
    if readback["mode"] != normalized_mode:
        raise APICallFailed(
            "Clip cache state did not change to the requested value.",
            details={
                "clip": name or (item.GetName() if hasattr(item, "GetName") else None),
                "cache_type": normalized_type,
                "mode": normalized_mode,
                "native_value": requested_value,
                "actual_mode": readback["mode"],
                "actual_native_value": readback["native_value"],
            },
        )
    return readback


def get_clip_offsets(conn, name: Optional[str] = None, *, ops_module) -> dict[str, Any]:
    item = ops_module.cutagent_clip(conn, name)
    if not hasattr(item, "GetLeftOffset") and not hasattr(item, "GetRightOffset"):
        raise APICallFailed(
            "Clip offsets are not available for this timeline item.",
            details={"clip": name or (item.GetName() if hasattr(item, "GetName") else None)},
        )
    try:
        left_offset = item.GetLeftOffset() if hasattr(item, "GetLeftOffset") else None
        right_offset = item.GetRightOffset() if hasattr(item, "GetRightOffset") else None
    except Exception as exc:
        raise APICallFailed(f"Failed to get clip offsets: {exc}") from exc
    if left_offset is None and right_offset is None:
        raise APICallFailed(
            "Clip offsets are not available for this timeline item.",
            details={"clip": name or (item.GetName() if hasattr(item, "GetName") else None)},
        )
    return {
        "clip": name or (item.GetName() if hasattr(item, "GetName") else None),
        "left_offset": left_offset,
        "right_offset": right_offset,
    }


def get_clip_composite(conn, name: Optional[str], *, ops_module) -> dict[str, Any]:
    item = ops_module.cutagent_clip(conn, name)
    return {
        "composite_mode": item.GetProperty("CompositeMode"),
        "opacity": item.GetProperty("Opacity"),
    }


def set_clip_composite(
    conn,
    name: Optional[str],
    mode: Optional[str] = None,
    opacity: Optional[float] = None,
    *,
    ops_module,
) -> None:
    item = ops_module.cutagent_clip(conn, name)

    if mode:
        item.SetProperty("CompositeMode", ops_module.normalize_composite_mode(mode))
    if opacity is not None:
        item.SetProperty("Opacity", ops_module.validate_clip_opacity(opacity))
