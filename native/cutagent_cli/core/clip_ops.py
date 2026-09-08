"""Clip / Timeline Item operations — Properties, color, flags, markers, takes, transform, composite, speed."""

from __future__ import annotations

import sys
import math
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..errors import APICallFailed, CapabilityNegotiationFailed, ValidationError
from ..utils.time_ref import parse_source_frame
from . import media_pool, render_engine
from ._clip_ops import fusion as _fusion_ops
from ._clip_ops import general as _general_ops
from ._clip_ops import markers as _marker_ops
from ._clip_ops import properties as _property_ops
from ._clip_ops.lookup import (
    _add_name_candidate,
    _item_name_candidates,
    find_item_by_name,
    find_item_by_track_record,
    get_current_item,
    cutagent_clip,
    cutagent_clip_by_selector,
)
from ._clip_ops.speed import _find_track_of_item, _readback_speed
from ._clip_ops.transform import _get_dynamic_zoom_ease_constant, _parse_zoom_tuple, _serialize_dynamic_zoom_ease

_COMPAT_EXPORTS = (
    media_pool,
    _add_name_candidate,
    _item_name_candidates,
    find_item_by_name,
    find_item_by_track_record,
    get_current_item,
    cutagent_clip_by_selector,
    _get_dynamic_zoom_ease_constant,
    _parse_zoom_tuple,
    _serialize_dynamic_zoom_ease,
    _find_track_of_item,
    _readback_speed,
)


def _ops_module():
    return sys.modules[__name__]


def list_clips(conn, track_type: str = "video", index: int = 1) -> List[Dict[str, Any]]:
    return _property_ops.list_clips(conn, track_type=track_type, index=index)


def normalize_clip_list_track_type(track_type: str = "video") -> str:
    return _property_ops.normalize_clip_list_track_type(track_type)


def validate_clip_list_track_index(index: int = 1) -> int:
    return _property_ops.validate_clip_list_track_index(index)


def validate_clip_list_request(conn, track_type: str = "video", index: int = 1) -> tuple[str, int]:
    return _property_ops.validate_clip_list_request(conn, track_type, index)


def get_clip_info(conn, name: Optional[str] = None) -> Dict[str, Any]:
    return _property_ops.get_clip_info(conn, name, ops_module=_ops_module())


def get_clip_property(conn, name: Optional[str], key: Optional[str] = None) -> Any:
    return _property_ops.get_clip_property(conn, name, key=key, ops_module=_ops_module())


def set_clip_property(conn, name: Optional[str], key: str, value: str) -> bool:
    return _property_ops.set_clip_property(conn, name, key, value, ops_module=_ops_module())


def get_clip_color(conn, name: Optional[str]) -> str:
    return _property_ops.get_clip_color(conn, name, ops_module=_ops_module())


def normalize_clip_color(color: str) -> str:
    return _property_ops.normalize_clip_color(color)


def set_clip_color(conn, name: Optional[str], color: str) -> None:
    _property_ops.set_clip_color(conn, name, color, ops_module=_ops_module())


def clear_clip_color(conn, name: Optional[str]) -> None:
    _property_ops.clear_clip_color(conn, name, ops_module=_ops_module())


def get_clip_flags(conn, name: Optional[str]) -> List[str]:
    return _property_ops.get_clip_flags(conn, name, ops_module=_ops_module())


def normalize_clip_flag_color(color: str) -> str:
    return _property_ops.normalize_clip_flag_color(color)


def add_clip_flag(conn, name: Optional[str], color: str) -> None:
    _property_ops.add_clip_flag(conn, name, color, ops_module=_ops_module())


def clear_clip_flags(conn, name: Optional[str]) -> None:
    _property_ops.clear_clip_flags(conn, name, ops_module=_ops_module())


def get_clip_transform(conn, name: Optional[str]) -> Dict[str, Any]:
    return _property_ops.get_clip_transform(conn, name, ops_module=_ops_module())


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
) -> None:
    _property_ops.set_clip_transform(
        conn,
        name,
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
        ops_module=_ops_module(),
    )


def set_clip_transform_batch(conn, entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    return _property_ops.set_clip_transform_batch(conn, entries, ops_module=_ops_module())


def reset_clip_transform(conn, name: Optional[str]) -> None:
    _property_ops.reset_clip_transform(conn, name, ops_module=_ops_module())


def get_clip_cache_state(
    conn,
    name: Optional[str] = None,
    *,
    cache_type: str = "color",
) -> Dict[str, Any]:
    return _property_ops.get_clip_cache_state(conn, name, cache_type=cache_type, ops_module=_ops_module())


def normalize_cache_type(cache_type: str) -> str:
    return _property_ops.normalize_cache_type(cache_type)


def normalize_cache_mode(cache_type: str, mode: str) -> str:
    return _property_ops.normalize_cache_mode(cache_type, mode)


def set_clip_cache_state(
    conn,
    name: Optional[str] = None,
    *,
    cache_type: str = "color",
    enabled: Optional[bool] = None,
    mode: Optional[str] = None,
) -> Dict[str, Any]:
    return _property_ops.set_clip_cache_state(
        conn,
        name,
        cache_type=cache_type,
        enabled=enabled,
        mode=mode,
        ops_module=_ops_module(),
    )


def get_clip_offsets(conn, name: Optional[str] = None) -> Dict[str, Any]:
    return _property_ops.get_clip_offsets(conn, name, ops_module=_ops_module())


def get_source_range(conn, name: Optional[str] = None) -> Dict[str, Any]:
    """Return source-domain range information for a timeline item."""
    item = cutagent_clip(conn, name)
    label = name or _clip_display_name(item)
    data: Dict[str, Any] = {"clip": label}
    for key, method_names in {
        "source_start": ("GetSourceStartFrame", "GetSourceStart"),
        "source_end": ("GetSourceEndFrame", "GetSourceEnd"),
        "left_offset": ("GetLeftOffset",),
        "right_offset": ("GetRightOffset",),
    }.items():
        for method_name in method_names:
            method = getattr(item, method_name, None)
            if callable(method):
                try:
                    data[key] = method()
                    break
                except Exception:
                    continue
    for key, method_name in (("start", "GetStart"), ("end", "GetEnd"), ("duration", "GetDuration")):
        method = getattr(item, method_name, None)
        if callable(method):
            try:
                data[key] = method()
            except Exception:
                pass
    return data


def list_linked_items(conn, name: Optional[str] = None) -> Dict[str, Any]:
    """List timeline items linked to a clip."""
    item = cutagent_clip(conn, name)
    getter = getattr(item, "GetLinkedItems", None)
    if not callable(getter):
        raise APICallFailed("GetLinkedItems not available.")
    linked = getter() or []
    return {
        "clip": name or _clip_display_name(item),
        "linked": [
            {
                "name": _clip_display_name(linked_item, str(linked_item)),
                "start": linked_item.GetStart() if hasattr(linked_item, "GetStart") else None,
                "end": linked_item.GetEnd() if hasattr(linked_item, "GetEnd") else None,
            }
            for linked_item in linked
        ],
    }


def get_track_info(conn, name: Optional[str] = None) -> Dict[str, Any]:
    """Return the track type/index for a timeline item."""
    item = cutagent_clip(conn, name)
    getter = getattr(item, "GetTrackTypeAndIndex", None)
    if callable(getter):
        track_type, track_index = getter()
    else:
        track_type = "video"
        track_index = _find_track_of_item(conn, item, track_type)
        if track_index <= 0:
            track_type = "audio"
            track_index = _find_track_of_item(conn, item, track_type)
    return {"clip": name or _clip_display_name(item), "track_type": track_type, "track_index": int(track_index or 0)}


def get_source_audio_mapping(conn, name: Optional[str] = None) -> Dict[str, Any]:
    """Return source audio channel mapping for a timeline item."""
    item = cutagent_clip(conn, name)
    getter = getattr(item, "GetSourceAudioChannelMapping", None)
    if not callable(getter):
        raise APICallFailed("GetSourceAudioChannelMapping not available.")
    return {"clip": name or _clip_display_name(item), "mapping": getter()}


def get_clip_composite(conn, name: Optional[str]) -> Dict[str, Any]:
    return _property_ops.get_clip_composite(conn, name, ops_module=_ops_module())


def set_clip_composite(
    conn,
    name: Optional[str],
    mode: Optional[str] = None,
    opacity: Optional[float] = None,
) -> None:
    _property_ops.set_clip_composite(conn, name, mode=mode, opacity=opacity, ops_module=_ops_module())


_COMPOSITE_MODE_CANONICAL = {
    mode.lower(): mode
    for mode in (
        "Add",
        "Color",
        "Color Burn",
        "Color Dodge",
        "Darken",
        "Difference",
        "Exclusion",
        "Hard Light",
        "Hard Mix",
        "Hue",
        "Lighten",
        "Lighter Color",
        "Linear Burn",
        "Linear Dodge",
        "Linear Light",
        "Luminosity",
        "Multiply",
        "Normal",
        "Overlay",
        "Pin Light",
        "Saturation",
        "Screen",
        "Soft Light",
        "Subtract",
        "Vivid Light",
    )
}


def normalize_composite_mode(mode: str) -> str:
    normalized = str(mode).strip().lower()
    canonical = _COMPOSITE_MODE_CANONICAL.get(normalized)
    if canonical is None:
        raise ValidationError(
            "Composite mode must be a supported DaVinci Resolve composite mode.",
            details={"mode": mode, "allowed": sorted(_COMPOSITE_MODE_CANONICAL.values())},
            recoverability="not_applicable",
        )
    return canonical


def validate_clip_opacity(opacity: float) -> float:
    value = float(opacity)
    if not math.isfinite(value):
        raise ValidationError(
            "Clip opacity must be a finite value from 0 to 100.",
            details={"opacity": str(opacity), "min": 0.0, "max": 100.0},
            recoverability="not_applicable",
        )
    if value < 0.0 or value > 100.0:
        raise ValidationError(
            "Clip opacity must be between 0 and 100.",
            details={"opacity": value, "min": 0.0, "max": 100.0},
            recoverability="not_applicable",
        )
    return value


def get_clip_speed(conn, name: Optional[str]) -> Dict[str, Any]:
    item = cutagent_clip(conn, name)
    try:
        speed = item.GetProperty("Speed")
        return {"speed": speed, "multiplier": float(speed) / 100 if speed else 1.0}
    except Exception:
        return {"speed": "unknown"}


def set_clip_speed(conn, name: Optional[str], speed: float) -> bool:
    item = cutagent_clip(conn, name)
    try:
        item.SetProperty("Speed", speed * 100)
        return True
    except Exception as e:
        raise APICallFailed(f"Speed change failed: {e}. " "Note: Speed changes may require using the Retime API.")


def enable_clip(conn, name: Optional[str]) -> Dict[str, Any]:
    return _general_ops.enable_clip(conn, name, ops_module=_ops_module())


def disable_clip(conn, name: Optional[str]) -> Dict[str, Any]:
    return _general_ops.disable_clip(conn, name, ops_module=_ops_module())


def rename_clip(conn, old_name: str, new_name: str) -> bool:
    return _general_ops.rename_clip(conn, old_name, new_name, ops_module=_ops_module())


def _cutagent_clips_by_names(conn, names: List[str]) -> List[object]:
    return _general_ops._cutagent_clips_by_names(conn, names, ops_module=_ops_module())


def _clip_display_name(item, fallback: Optional[str] = None) -> Optional[str]:
    return _general_ops._clip_display_name(item, fallback=fallback)


def normalize_explicit_clip_name(name: str, *, field: str = "clip_name") -> str:
    return _general_ops.normalize_explicit_clip_name(name, field=field)


def plan_clips_linked(conn, clip_names: List[str], linked: bool) -> Dict[str, Any]:
    return _general_ops.plan_clips_linked(conn, clip_names, linked, ops_module=_ops_module())


def set_clips_linked(conn, clip_names: List[str], linked: bool) -> bool:
    return _general_ops.set_clips_linked(conn, clip_names, linked, ops_module=_ops_module())


def unlink_clip(conn, clip_name: str) -> bool:
    return _general_ops.unlink_clip(conn, clip_name, ops_module=_ops_module())


def stabilize_clip(conn, clip_name: Optional[str] = None) -> bool:
    return _general_ops.stabilize_clip(conn, clip_name, ops_module=_ops_module())


def smart_reframe_clip(
    conn,
    clip_name: Optional[str] = None,
    *,
    item_id: Optional[str] = None,
    track: Optional[int] = None,
    record_frame: Optional[str] = None,
    operation_id: Optional[str] = None,
    progress_file: Optional[str] = None,
    cancel_request_file: Optional[str] = None,
    proof_dir: Optional[str] = None,
    poll_ms: int = 250,
) -> Dict[str, Any]:
    return _general_ops.smart_reframe_clip(
        conn,
        clip_name,
        item_id=item_id,
        track=track,
        record_frame=record_frame,
        operation_id=operation_id,
        progress_file=progress_file,
        cancel_request_file=cancel_request_file,
        proof_dir=proof_dir,
        poll_ms=poll_ms,
        ops_module=_ops_module(),
    )


def create_magic_mask(
    conn,
    clip_name: Optional[str] = None,
    mode: str = "BI",
    track: int | None = None,
    record_frame: str | int | None = None,
) -> Dict[str, Any]:
    return _general_ops.create_magic_mask(conn, clip_name, mode=mode, track=track, record_frame=record_frame, ops_module=_ops_module())


def regenerate_magic_mask(
    conn,
    clip_name: Optional[str] = None,
    *,
    track: int | None = None,
    record_frame: str | int | None = None,
) -> Dict[str, Any]:
    return _general_ops.regenerate_magic_mask(conn, clip_name, track=track, record_frame=record_frame, ops_module=_ops_module())


def get_voice_isolation(conn, clip_name: Optional[str] = None) -> Dict[str, Any]:
    return _general_ops.get_voice_isolation(conn, clip_name, ops_module=_ops_module())


def set_voice_isolation(
    conn,
    clip_name: Optional[str] = None,
    *,
    enabled: Optional[bool] = None,
    amount: Optional[int] = None,
) -> Dict[str, Any]:
    return _general_ops.set_voice_isolation(
        conn,
        clip_name,
        enabled=enabled,
        amount=amount,
        ops_module=_ops_module(),
    )


def _find_or_create_transform(comp) -> object:
    return _fusion_ops._find_or_create_transform(comp)


def validate_dynamic_zoom_request(
    *,
    start: str,
    end: str,
    source_in: Optional[str] = None,
    source_out: Optional[str] = None,
    ease: str = "linear",
    fps: float = 24.0,
) -> Dict[str, Any]:
    sx, sy, sz = _parse_zoom_tuple(start)
    ex, ey, ez = _parse_zoom_tuple(end)
    _get_dynamic_zoom_ease_constant(object(), ease)
    source_in_frame = parse_source_frame(source_in, fps) if source_in is not None else None
    source_out_frame = parse_source_frame(source_out, fps) if source_out is not None else None
    if source_in_frame is not None and source_out_frame is not None and source_out_frame <= source_in_frame:
        raise ValidationError(
            "Dynamic zoom source-out must be greater than source-in.",
            details={
                "source_in": source_in,
                "source_out": source_out,
                "in_frame": source_in_frame,
                "out_frame": source_out_frame,
            },
            recoverability="not_applicable",
        )
    return {
        "start": {"x": sx, "y": sy, "zoom": sz},
        "end": {"x": ex, "y": ey, "zoom": ez},
        "ease": str(ease).strip().lower(),
        "source_in_frame": source_in_frame,
        "source_out_frame": source_out_frame,
    }


def apply_dynamic_zoom(
    conn,
    clip_name: Optional[str],
    *,
    start: str,
    end: str,
    source_in: Optional[str] = None,
    source_out: Optional[str] = None,
    ease: str = "linear",
) -> Dict[str, Any]:
    return _fusion_ops.apply_dynamic_zoom(
        conn,
        clip_name,
        start=start,
        end=end,
        source_in=source_in,
        source_out=source_out,
        ease=ease,
        ops_module=_ops_module(),
    )


def list_fusion_comps(
    conn,
    name: Optional[str],
    *,
    track: int | None = None,
    record_frame: str | int | None = None,
) -> List[Dict[str, Any]]:
    return _fusion_ops.list_fusion_comps(conn, name, track=track, record_frame=record_frame, ops_module=_ops_module())


def add_fusion_comp(
    conn,
    name: Optional[str],
    *,
    track: int | None = None,
    record_frame: str | int | None = None,
) -> bool:
    return _fusion_ops.add_fusion_comp(conn, name, track=track, record_frame=record_frame, ops_module=_ops_module())


def _fusion_comp_count(item) -> Optional[int]:
    return _fusion_ops._fusion_comp_count(item)


def _fusion_comp_name_list(item) -> list[str]:
    return _fusion_ops._fusion_comp_name_list(item)


def _append_unique(values: list[str], value) -> None:
    _fusion_ops._append_unique(values, value)


def delete_fusion_comp(
    conn,
    clip_name: Optional[str],
    index: int,
    *,
    track: int | None = None,
    record_frame: str | int | None = None,
) -> bool:
    return _fusion_ops.delete_fusion_comp(conn, clip_name, index, track=track, record_frame=record_frame, ops_module=_ops_module())


def _fusion_comp_candidate_names(item, index: int) -> list[str]:
    return _fusion_ops._fusion_comp_candidate_names(item, index, ops_module=_ops_module())


def rename_fusion_comp(conn, clip_name: Optional[str], index: int, new_name: str) -> Dict[str, Any]:
    return _fusion_ops.rename_fusion_comp(conn, clip_name, index, new_name, ops_module=_ops_module())


def validate_fusion_comp_index(index: int) -> int:
    if int(index) < 1:
        raise ValidationError(
            "Fusion composition index must be 1 or greater.",
            details={"index": index},
            recoverability="not_applicable",
        )
    return int(index)


def _validate_fusion_export_path(path: str) -> str:
    output_path = Path(path).expanduser().resolve(strict=False)
    if output_path.exists():
        if output_path.is_dir():
            raise ValidationError(
                "Fusion composition export path is a directory, not a file.",
                details={"path": str(output_path), "path_type": "directory"},
                recoverability="not_applicable",
            )
        raise ValidationError(
            "Fusion composition export path already exists.",
            details={"path": str(output_path), "hint": "Pass a new output path or remove the existing file first."},
            recoverability="not_applicable",
        )
    parent = output_path.parent
    if parent and not parent.exists():
        raise ValidationError(
            "Fusion composition export directory does not exist.",
            details={"path": str(output_path), "parent": str(parent)},
            recoverability="not_applicable",
        )
    if parent and not parent.is_dir():
        raise ValidationError(
            "Fusion composition export parent path is not a directory.",
            details={"path": str(output_path), "parent": str(parent)},
            recoverability="not_applicable",
        )
    return str(output_path)


def validate_fusion_export_request(index: int, path: str) -> str:
    validate_fusion_comp_index(index)
    return _validate_fusion_export_path(path)


def export_fusion_comp(
    conn,
    clip_name: Optional[str],
    index: int,
    path: str,
    *,
    track: int | None = None,
    record_frame: str | int | None = None,
) -> bool:
    return _fusion_ops.export_fusion_comp(conn, clip_name, index, path, track=track, record_frame=record_frame, ops_module=_ops_module())


def import_fusion_comp(
    conn,
    clip_name: Optional[str],
    path: str,
    *,
    track: int | None = None,
    record_frame: str | int | None = None,
) -> bool:
    return _fusion_ops.import_fusion_comp(conn, clip_name, path, track=track, record_frame=record_frame, ops_module=_ops_module())


def list_fusion_tools(
    conn,
    clip_name: Optional[str],
    comp_index: int = 1,
    *,
    track: int | None = None,
    record_frame: str | int | None = None,
) -> List[Dict[str, Any]]:
    return _fusion_ops.list_fusion_tools(conn, clip_name, comp_index=comp_index, track=track, record_frame=record_frame, ops_module=_ops_module())


def get_fusion_tool_input(
    conn,
    clip_name: Optional[str],
    tool_name: str,
    input_name: str,
    comp_index: int = 1,
    *,
    track: int | None = None,
    record_frame: str | int | None = None,
) -> Any:
    return _fusion_ops.get_fusion_tool_input(
        conn,
        clip_name,
        tool_name,
        input_name,
        comp_index=comp_index,
        track=track,
        record_frame=record_frame,
        ops_module=_ops_module(),
    )


def set_fusion_tool_input(
    conn,
    clip_name: Optional[str],
    tool_name: str,
    input_name: str,
    value: str,
    comp_index: int = 1,
    *,
    track: int | None = None,
    record_frame: str | int | None = None,
) -> None:
    _fusion_ops.set_fusion_tool_input(
        conn,
        clip_name,
        tool_name,
        input_name,
        value,
        comp_index=comp_index,
        track=track,
        record_frame=record_frame,
        ops_module=_ops_module(),
    )


def list_clip_markers(conn, name: Optional[str]) -> List[Dict[str, Any]]:
    return _marker_ops.list_clip_markers(conn, name, ops_module=_ops_module())


def list_timeline_clip_markers(
    conn,
    *,
    track_type: str = "video",
    tracks: list[int] | tuple[int, ...] | None = None,
    color: str | None = None,
    visible_only: bool = True,
    authoritative_ids: bool = False,
) -> Dict[str, Any]:
    return _marker_ops.list_timeline_clip_markers(
        conn,
        track_type=track_type,
        tracks=tracks,
        color=color,
        visible_only=visible_only,
        authoritative_ids=authoritative_ids,
    )


def add_clip_marker(
    conn,
    clip_name: Optional[str],
    frame: int,
    color: str = "Blue",
    name: str = "",
    note: str = "",
    duration: int = 1,
    frame_domain: str = "auto",
) -> bool:
    return _marker_ops.add_clip_marker(
        conn,
        clip_name,
        frame,
        color=color,
        name=name,
        note=note,
        duration=duration,
        frame_domain=frame_domain,
        ops_module=_ops_module(),
    )


def delete_clip_marker(conn, name: Optional[str], frame: int, frame_domain: str = "auto") -> Dict[str, Any]:
    return _marker_ops.delete_clip_marker(conn, name, frame, frame_domain=frame_domain, ops_module=_ops_module())


def _take_count(item) -> int:
    return _marker_ops._take_count(item)


def _selected_take_index(item) -> int:
    return _marker_ops._selected_take_index(item)


def _format_take_info(take) -> str:
    return _marker_ops._format_take_info(take)


def list_takes_summary(conn, name: Optional[str]) -> Dict[str, Any]:
    return _marker_ops.list_takes_summary(conn, name, ops_module=_ops_module())


def list_takes(conn, name: Optional[str]) -> List[Dict[str, Any]]:
    return _marker_ops.list_takes(conn, name, ops_module=_ops_module())


def add_take(
    conn,
    clip_name: Optional[str],
    media_name: str,
    start_frame: Optional[int] = None,
    end_frame: Optional[int] = None,
) -> bool:
    return _marker_ops.add_take(
        conn,
        clip_name,
        media_name,
        start_frame=start_frame,
        end_frame=end_frame,
        ops_module=_ops_module(),
    )


def select_take(conn, clip_name: Optional[str], index: int) -> bool:
    return _marker_ops.select_take(conn, clip_name, index, ops_module=_ops_module())


def finalize_take(conn, clip_name: Optional[str]) -> bool:
    return _marker_ops.finalize_take(conn, clip_name, ops_module=_ops_module())


def delete_take(conn, clip_name: Optional[str], index: int) -> Dict[str, Any]:
    """Delete a take from a timeline clip."""
    if index < 1:
        raise ValidationError("Take index must be 1 or greater.", details={"index": index})
    item = cutagent_clip(conn, clip_name)
    count = _take_count(item)
    if index > count:
        raise ValidationError(
            f"Take index {index} is out of range; clip has {count} take(s).",
            details={"clip": clip_name, "index": index, "take_count": count},
        )
    deleter = getattr(item, "DeleteTakeByIndex", None)
    if not callable(deleter):
        raise CapabilityNegotiationFailed(
            "DeleteTakeByIndex API is not available on this timeline item.",
            details={"clip": clip_name, "index": index, "take_count": count},
        )
    try:
        result = deleter(index)
    except Exception as exc:
        raise APICallFailed("DeleteTakeByIndex API call failed.", details={"clip": clip_name, "index": index, "exception": str(exc)}) from exc
    after_count = _take_count(item)
    deleted = bool(result) or after_count < count
    if not deleted:
        raise CapabilityNegotiationFailed(
            "Failed to delete take.",
            details={"clip": clip_name, "index": index, "before_take_count": count, "after_take_count": after_count},
        )
    selected = _selected_take_index(item)
    return {
        "clip": clip_name or _clip_display_name(item),
        "index": index,
        "deleted": True,
        "native_result": bool(result),
        "before_take_count": count,
        "after_take_count": after_count,
        "takes": _marker_ops._take_rows(item, count=after_count, selected=selected, ops_module=_ops_module()),
    }


def load_fusion_comp_by_name(conn, clip_name: Optional[str], comp_name: str) -> Dict[str, Any]:
    """Load/switch to a Fusion composition by name."""
    item = cutagent_clip(conn, clip_name)
    loader = getattr(item, "LoadFusionCompByName", None)
    if not callable(loader):
        raise APICallFailed("LoadFusionCompByName not available.")
    result = loader(comp_name)
    if result is False:
        raise APICallFailed("Failed to load Fusion composition.", details={"clip": clip_name, "comp": comp_name})
    return {"clip": clip_name or _clip_display_name(item), "comp": comp_name, "loaded": bool(result)}


def _fusion_comp_entries(item) -> list[Dict[str, Any]]:
    count = _fusion_comp_count(item) or 0
    rows: list[Dict[str, Any]] = []
    for index in range(1, count + 1):
        name = f"Composition {index}"
        names = _fusion_comp_name_list(item)
        if 0 <= index - 1 < len(names):
            name = names[index - 1]
        else:
            try:
                comp = item.GetFusionCompByIndex(index)
                if comp and hasattr(comp, "GetAttrs"):
                    name = comp.GetAttrs().get("COMPS_Name", name)
            except Exception:
                pass
        rows.append({"index": index, "name": name})
    entries: list[Dict[str, Any]] = []
    for row in rows:
        index = int(row.get("index", len(entries) + 1))
        name = str(row.get("name") or f"Composition {index}")
        aliases: list[str] = []
        for alias in (name, f"Composition {index}", f"Composition{index}", f"Comp {index}", f"Comp{index}", str(index)):
            if alias not in aliases:
                aliases.append(alias)
        entries.append({"index": index, "name": aliases[0], "aliases": aliases})
    return entries


def get_fusion_comp_by_name(conn, clip_name: Optional[str], comp_name: str) -> Dict[str, Any]:
    """Return a Fusion composition by name or stable alias."""
    item = cutagent_clip(conn, clip_name)
    requested = str(comp_name).strip()
    getter = getattr(item, "GetFusionCompByName", None)
    if callable(getter):
        comp = getter(requested)
        if comp:
            return {"clip": clip_name or _clip_display_name(item), "comp": requested, "found": True, "lookup": "native_name"}
    entries = _fusion_comp_entries(item)
    normalized = requested.casefold()
    matches = [entry for entry in entries if normalized in {alias.casefold() for alias in entry["aliases"]}]
    if len(matches) == 1:
        return {
            "clip": clip_name or _clip_display_name(item),
            "requested_comp": requested,
            "found": True,
            "lookup": "exact_alias",
            "available_comps": entries,
            **matches[0],
        }
    raise ValidationError(
        "Fusion composition not found." if not matches else "Fusion composition selector is ambiguous.",
        details={"clip": clip_name or _clip_display_name(item), "requested_comp": requested, "available_comps": entries},
    )


def get_marker_by_custom_data(conn, clip_name: Optional[str], custom_data: str) -> Dict[str, Any]:
    """Read a clip marker by custom data."""
    item = cutagent_clip(conn, clip_name)
    getter = getattr(item, "GetMarkerByCustomData", None)
    if not callable(getter):
        raise APICallFailed("GetMarkerByCustomData not available.")
    return {"clip": clip_name or _clip_display_name(item), "custom_data": custom_data, "marker": getter(custom_data)}


def update_marker_custom_data(conn, clip_name: Optional[str], frame: int, custom_data: str) -> Dict[str, Any]:
    """Set custom data on a clip marker."""
    item = cutagent_clip(conn, clip_name)
    updater = getattr(item, "UpdateMarkerCustomData", None)
    if not callable(updater):
        raise APICallFailed("UpdateMarkerCustomData not available.")
    result = updater(int(frame), custom_data)
    if result is False:
        raise APICallFailed("Failed to update marker custom data.", details={"clip": clip_name, "frame": frame})
    return {"clip": clip_name or _clip_display_name(item), "frame": int(frame), "custom_data": custom_data, "updated": bool(result)}


def delete_marker_by_custom_data(conn, clip_name: Optional[str], custom_data: str) -> Dict[str, Any]:
    """Delete a clip marker by custom data."""
    item = cutagent_clip(conn, clip_name)
    deleter = getattr(item, "DeleteMarkerByCustomData", None)
    if not callable(deleter):
        raise APICallFailed("DeleteMarkerByCustomData not available.")
    result = deleter(custom_data)
    if result is False:
        raise APICallFailed("Failed to delete marker by custom data.", details={"clip": clip_name, "custom_data": custom_data})
    return {"clip": clip_name or _clip_display_name(item), "custom_data": custom_data, "deleted": bool(result)}


def reset_all_node_colors(conn, clip_name: Optional[str]) -> Dict[str, Any]:
    """Reset all node colors on a timeline item."""
    item = cutagent_clip(conn, clip_name)
    resetter = getattr(item, "ResetAllNodeColors", None)
    if not callable(resetter):
        raise APICallFailed("ResetAllNodeColors not available.")
    result = resetter()
    if result is False:
        raise APICallFailed("Failed to reset all node colors.", details={"clip": clip_name})
    return {"clip": clip_name or _clip_display_name(item), "reset": bool(result)}


def update_sidecar(conn, clip_name: Optional[str]) -> Dict[str, Any]:
    """Update sidecar files for a timeline item."""
    item = cutagent_clip(conn, clip_name)
    updater = getattr(item, "UpdateSidecar", None)
    if not callable(updater):
        raise APICallFailed("UpdateSidecar not available.")
    result = updater()
    if result is False:
        raise APICallFailed("Failed to update sidecar.", details={"clip": clip_name})
    return {"clip": clip_name or _clip_display_name(item), "updated": bool(result)}


def get_stereo_values(conn, clip_name: Optional[str]) -> Dict[str, Any]:
    """Read stereo 3D values from a timeline item."""
    item = cutagent_clip(conn, clip_name)
    data: Dict[str, Any] = {"clip": clip_name or _clip_display_name(item)}
    any_method = False
    for method_name in ("GetStereoConvergenceValues", "GetStereoLeftFloatingWindowParams", "GetStereoRightFloatingWindowParams"):
        method = getattr(item, method_name, None)
        if callable(method):
            any_method = True
            try:
                data[method_name] = method()
            except Exception as exc:
                data[method_name] = {"error": str(exc)}
    if not any_method:
        raise APICallFailed("Stereo value APIs are not available on this timeline item.")
    return data


def load_burnin_preset(conn, clip_name: Optional[str], name: str) -> Dict[str, Any]:
    """Load a burn-in preset on a timeline item when exposed by DaVinci Resolve."""
    item = cutagent_clip(conn, clip_name)
    loader = getattr(item, "LoadBurnInPreset", None)
    if not callable(loader):
        raise APICallFailed("LoadBurnInPreset not available on timeline item.")
    resolved_name, presets, unlisted_exact = render_engine._resolve_burnin_preset_selector(name, allow_unlisted_exact=True)
    result = loader(resolved_name)
    if result is False:
        if unlisted_exact:
            raise render_engine._burnin_preset_not_found_error(str(name), presets, attempted_exact_load=True)
        raise APICallFailed(
            "Failed to load burn-in preset on clip.",
            details={
                "clip": clip_name or _clip_display_name(item),
                "requested_preset": str(name),
                "resolved_preset": resolved_name,
                "available_presets": render_engine._summarize_burnin_presets(presets),
            },
        )
    return {
        "clip": clip_name or _clip_display_name(item),
        "preset": resolved_name,
        "requested_preset": str(name),
        "loaded": bool(result),
        "unlisted_exact": unlisted_exact,
    }


def get_keyframe_mode(conn) -> Dict[str, Any]:
    return _general_ops.get_keyframe_mode(conn)


def set_keyframe_mode(conn, mode: int) -> Dict[str, Any]:
    return _general_ops.set_keyframe_mode(conn, mode)


def export_current_frame_as_still(conn, path: str) -> Dict[str, Any]:
    return _general_ops.export_current_frame_as_still(conn, path)


def insert_audio_to_current_track(conn, media_path: str, start_offset: int = 0) -> Dict[str, Any]:
    return _general_ops.insert_audio_to_current_track(conn, media_path, start_offset)
