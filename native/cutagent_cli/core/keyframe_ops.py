"""Timeline item keyframe operations."""

from __future__ import annotations

from typing import Optional, Dict, Any

from ..errors import APICallFailed, CapabilityNegotiationFailed, ValidationError
from ..output import set_capability_context, set_execution_engine, set_recoverability, set_verification_status
from .clip_ops import cutagent_clip
from . import keyframe_db

_VIDEO_PROPERTIES = [
    "Pan",
    "Tilt",
    "ZoomX",
    "ZoomY",
    "Rotation",
    "AnchorPointX",
    "AnchorPointY",
    "Pitch",
    "Yaw",
    "Opacity",
    "CropLeft",
    "CropRight",
    "CropTop",
    "CropBottom",
]
_AUDIO_PROPERTIES = ["Volume", "Pan"]
_INTERPOLATION_MAP = {
    "linear": 0,
    "bezier": 1,
    "ease-in": 2,
    "ease-out": 3,
}
_KEYFRAME_READ_METHODS = ("GetKeyframeCount", "GetKeyframeAtIndex")
_KEYFRAME_VALUE_METHOD = "GetPropertyAtKeyframeIndex"


def _resolve_item(conn, clip_name: Optional[str]):
    return cutagent_clip(conn, clip_name)


def _available_keyframe_methods(item) -> list[str]:
    return sorted(name for name in dir(item) if "key" in name.lower())


def _require_keyframe_methods(
    item,
    method_names,
    *,
    operation: str,
    property_name: Optional[str] = None,
    extra_details: Optional[Dict[str, Any]] = None,
):
    missing = [name for name in method_names if not callable(getattr(item, name, None))]
    if not missing:
        return

    set_execution_engine("not_available")
    set_capability_context("clip.keyframe_crud", "unsupported")
    set_verification_status("failed")
    set_recoverability("manual")
    raise CapabilityNegotiationFailed(
        "Timeline item keyframes are not available through this DaVinci Resolve scripting runtime.",
        details={
            "capability_id": "clip.keyframe_crud",
            "operation": operation,
            "property": property_name,
            "runtime_object": "TimelineItem",
            "missing_methods": missing,
            "required_methods": list(method_names),
            "available_keyframe_methods": _available_keyframe_methods(item),
            "workaround": (
                "Use Fusion tool/input keyframes for Fusion-owned parameters. "
                "Timeline item Inspector keyframes require a DaVinci Resolve scripting runtime that exposes "
                "TimelineItem keyframe APIs."
            ),
            **(extra_details or {}),
        },
    )


def _check_frame_in_item_range(item, frame: int) -> None:
    try:
        start = int(item.GetStart())
        end = int(item.GetEnd())
    except Exception:
        return
    if frame < start or frame > end:
        raise ValidationError(
            "Frame is outside clip bounds.",
            details={"frame": frame, "clip_start": start, "clip_end": end},
        )


def _candidate_keyframe_frames(item, frame: int) -> list[int]:
    candidates: list[int] = []

    def _append(value) -> None:
        try:
            candidate = int(value)
        except Exception:
            return
        if candidate not in candidates:
            candidates.append(candidate)

    _append(frame)
    try:
        _append(frame - int(item.GetStart()))
    except Exception:
        pass

    try:
        local = frame - int(item.GetStart())
        _append(local + int(item.GetLeftOffset()))
    except Exception:
        pass

    return candidates


def _map_frame_to_resolved_keyframe_domain(
    item,
    frame: int,
    *,
    reference_frame: int,
    reference_resolved_frame: int,
) -> int:
    reference_candidates = _candidate_keyframe_frames(item, reference_frame)
    target_candidates = _candidate_keyframe_frames(item, frame)
    try:
        candidate_index = reference_candidates.index(reference_resolved_frame)
    except ValueError:
        return frame
    if 0 <= candidate_index < len(target_candidates):
        return target_candidates[candidate_index]
    return frame


def _keyframe_frame_value(keyframe) -> Optional[int]:
    if isinstance(keyframe, dict):
        for key in ("frame", "Frame", "time", "Time"):
            if key in keyframe:
                try:
                    return int(keyframe[key])
                except Exception:
                    continue
    try:
        return int(keyframe)
    except Exception:
        return None


def _find_keyframe(item, property_name: str, frame: int) -> tuple[int, int]:
    counter = getattr(item, "GetKeyframeCount", None)
    getter = getattr(item, "GetKeyframeAtIndex", None)
    if not callable(counter) or not callable(getter):
        raise CapabilityNegotiationFailed(
            "Timeline item keyframe readback is not available through this DaVinci Resolve scripting API.",
            details={
                "capability_id": "clip.keyframe_crud",
                "required_methods": ["TimelineItem.GetKeyframeCount", "TimelineItem.GetKeyframeAtIndex"],
                "property": property_name,
                "frame": frame,
            },
        )
    try:
        keyframe_count = int(counter(property_name) or 0)
    except Exception as exc:
        raise APICallFailed(
            "Failed to read keyframe count.",
            details={"property": property_name, "exception": str(exc)},
        ) from exc

    candidate_frames = set(_candidate_keyframe_frames(item, frame))
    for i in range(keyframe_count):
        try:
            kf = item.GetKeyframeAtIndex(property_name, i)
        except Exception:
            continue
        keyframe_frame = _keyframe_frame_value(kf)
        if keyframe_frame in candidate_frames:
            return i, int(keyframe_frame)

    raise APICallFailed(
        "No keyframe found at frame.",
        details={"property": property_name, "frame": frame, "candidate_frames": sorted(candidate_frames)},
    )


def _find_keyframe_index(item, property_name: str, frame: int) -> int:
    index, _ = _find_keyframe(item, property_name, frame)
    return index


def _delete_keyframe_native(item, property_name: str, frame: int, *, requested_frame: int) -> bool:
    _require_keyframe_methods(
        item,
        ("DeleteKeyframe",),
        operation="delete",
        property_name=property_name,
        extra_details={"frame": requested_frame, "resolved_frame": frame},
    )
    deleter = getattr(item, "DeleteKeyframe", None)

    try:
        result = deleter(property_name, frame)
    except Exception as exc:
        raise APICallFailed(
            "DeleteKeyframe API call failed.",
            details={"property": property_name, "frame": requested_frame, "resolved_frame": frame},
        ) from exc

    if result:
        return True
    return False


def _add_keyframe_native(
    item,
    property_name: str,
    frame: int,
    value: float,
    *,
    interpolation: Optional[int] = None,
    require_interpolation: bool = False,
) -> bool:
    _require_keyframe_methods(
        item,
        ("AddKeyframe",),
        operation="add",
        property_name=property_name,
        extra_details={"frame": frame},
    )
    adder = getattr(item, "AddKeyframe", None)

    if interpolation is not None:
        try:
            if adder(property_name, frame, value, interpolation):
                return True
        except TypeError:
            if require_interpolation:
                raise CapabilityNegotiationFailed(
                    "Timeline item keyframe interpolation is not available through this DaVinci Resolve scripting API.",
                    details={
                        "capability_id": "clip.keyframe_crud",
                        "required_method": "TimelineItem.AddKeyframe(property, frame, value, interpolation)",
                        "property": property_name,
                        "frame": frame,
                        "interpolation": interpolation,
                    },
                )
        except Exception as exc:
            raise APICallFailed(
                "AddKeyframe API call failed.",
                details={
                    "property": property_name,
                    "frame": frame,
                    "value": value,
                    "interpolation": interpolation,
                },
            ) from exc

        if require_interpolation:
            raise CapabilityNegotiationFailed(
                "Timeline item keyframe interpolation was not accepted by this DaVinci Resolve scripting API.",
                details={
                    "capability_id": "clip.keyframe_crud",
                    "required_method": "TimelineItem.AddKeyframe(property, frame, value, interpolation)",
                    "property": property_name,
                    "frame": frame,
                    "interpolation": interpolation,
                },
            )

    try:
        return bool(adder(property_name, frame, value))
    except Exception as exc:
        raise APICallFailed(
            "AddKeyframe API call failed.",
            details={"property": property_name, "frame": frame, "value": value},
        ) from exc


def _restore_keyframe_best_effort(item, property_name: str, frame: int, value: float) -> None:
    try:
        _add_keyframe_native(item, property_name, frame, value)
    except Exception:
        pass


def _set_keyframe_interpolation_direct(item, property_name: str, frame: int, interpolation: int) -> Optional[bool]:
    for method_name in (
        "SetKeyframeInterpolation",
        "SetKeyFrameInterpolation",
        "SetKeyframeEase",
        "SetKeyFrameEase",
    ):
        method = getattr(item, method_name, None)
        if not callable(method):
            continue
        for args in (
            (property_name, frame, interpolation),
            (property_name, interpolation, frame),
        ):
            try:
                if method(*args):
                    return True
            except TypeError:
                continue
            except Exception as exc:
                raise APICallFailed(
                    f"{method_name} API call failed.",
                    details={
                        "property": property_name,
                        "frame": frame,
                        "interpolation": interpolation,
                        "method": method_name,
                    },
                ) from exc
    return None


def _collect_property_keyframes(item, property_name: str) -> list[Dict[str, Any]]:
    counter = getattr(item, "GetKeyframeCount", None)
    getter = getattr(item, "GetKeyframeAtIndex", None)
    value_getter = getattr(item, "GetPropertyAtKeyframeIndex", None)
    if not callable(counter) or not callable(getter) or not callable(value_getter):
        raise CapabilityNegotiationFailed(
            "Timeline item keyframe readback is not available through this DaVinci Resolve scripting API.",
            details={
                "capability_id": "clip.keyframe_crud",
                "required_methods": [
                    "TimelineItem.GetKeyframeCount",
                    "TimelineItem.GetKeyframeAtIndex",
                    "TimelineItem.GetPropertyAtKeyframeIndex",
                ],
                "property": property_name,
            },
        )
    rows: list[Dict[str, Any]] = []
    try:
        keyframe_count = int(counter(property_name) or 0)
    except Exception:
        return rows

    for i in range(keyframe_count):
        try:
            kf = getter(property_name, i) or {}
            value = value_getter(property_name, i)
        except Exception:
            continue
        rows.append(
            {
                "index": i,
                "frame": kf.get("frame") if isinstance(kf, dict) else None,
                "value": value,
                "interpolation": kf.get("interpolation") if isinstance(kf, dict) else None,
            }
        )
    return rows


def add_keyframe(
    conn,
    clip_name: Optional[str],
    property_name: str,
    frame: int,
    value: float,
    interpolation: Optional[int] = None,
) -> Dict[str, Any]:
    return keyframe_db.add_keyframe(conn, clip_name, property_name, frame, value, interpolation)


def get_keyframes(
    conn,
    clip_name: Optional[str],
    property_name: Optional[str] = None,
) -> Dict[str, Any]:
    return keyframe_db.get_keyframes(conn, clip_name, property_name)


def modify_keyframe(
    conn,
    clip_name: Optional[str],
    property_name: str,
    frame: int,
    *,
    new_value: Optional[float] = None,
    new_frame: Optional[int] = None,
) -> bool:
    if new_value is None and new_frame is None:
        raise ValidationError("Specify at least one of: new_value, new_frame.")

    item = _resolve_item(conn, clip_name)
    idx, resolved_frame = _find_keyframe(item, property_name, frame)
    current_value = item.GetPropertyAtKeyframeIndex(property_name, idx)
    kf = item.GetKeyframeAtIndex(property_name, idx) or {}
    interpolation = kf.get("interpolation") if isinstance(kf, dict) else None

    target_frame = int(new_frame if new_frame is not None else frame)
    target_api_frame = _map_frame_to_resolved_keyframe_domain(
        item,
        target_frame,
        reference_frame=frame,
        reference_resolved_frame=resolved_frame,
    )
    target_value = float(new_value if new_value is not None else current_value)

    _check_frame_in_item_range(item, target_frame)

    deleted = _delete_keyframe_native(item, property_name, resolved_frame, requested_frame=frame)
    if deleted is False:
        raise APICallFailed(
            "Failed to delete existing keyframe before modify.",
            details={"property": property_name, "frame": frame, "resolved_frame": resolved_frame},
        )

    result = _add_keyframe_native(item, property_name, target_api_frame, target_value, interpolation=interpolation)

    if result:
        return True
    raise APICallFailed(
        "Failed to write modified keyframe.",
        details={
            "property": property_name,
            "old_frame": frame,
            "new_frame": target_frame,
            "resolved_new_frame": target_api_frame,
            "new_value": target_value,
            "interpolation": interpolation,
        },
    )


def delete_keyframe(
    conn,
    clip_name: Optional[str],
    property_name: str,
    frame: int,
) -> Dict[str, Any]:
    return keyframe_db.delete_keyframe(conn, clip_name, property_name, frame)


def set_keyframe_interpolation(
    conn,
    clip_name: Optional[str],
    property_name: str,
    frame: int,
    interpolation_type: str,
) -> Dict[str, Any]:
    return keyframe_db.set_keyframe_interpolation(conn, clip_name, property_name, frame, interpolation_type)
