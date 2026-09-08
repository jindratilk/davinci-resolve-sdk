"""Production semantic owners for the eleven professional prepared actions.

The public action id is permanently bound to one CutAgent CLI command identity
here. The signed carrier still owns admission and Mutation Policy. Keyframe
execution uses the same typed native service as the CLI boundary; remaining
families retain their fixed handler execution until migrated separately.
"""

from __future__ import annotations

from contextlib import ExitStack, contextmanager
from copy import deepcopy
import hashlib
import inspect
import json
import math
import os
import re
from types import MappingProxyType
from typing import Any, Callable, Mapping

from ..core.keyframe_service import (
    AddKeyframe,
    DeleteKeyframe,
    GetKeyframes,
    KeyframeRequest,
    SetKeyframeInterpolation,
    execute_keyframe,
)
from ..errors import ValidationError
from ..output import capture_prepared_action_output
from ..policy import _prepared_action_admission_scope
from .professional_primitive_prepared_action import (
    _DEFINITIONS,
    _read_target_digests,
    REVIEWED_CLIP_PRIMITIVE_ACTION_IDS,
)


_HANDLERS = MappingProxyType({
    "cutagent.action.edit.fx.add": ("edit.fx.add", "fx_add"),
    "cutagent.action.clip.keyframe.add": ("clip.keyframe.add", "keyframe_add"),
    "cutagent.action.clip.keyframe.delete": ("clip.keyframe.delete", "keyframe_delete"),
    "cutagent.action.clip.keyframe.get": ("clip.keyframe.get", "keyframe_get"),
    "cutagent.action.clip.keyframe.set_interpolation": ("clip.keyframe.set_interpolation", "keyframe_set_interpolation"),
    "cutagent.action.clip.transform": ("clip.transform", "clip_transform"),
    "cutagent.action.clip.speed": ("clip.speed", "clip_speed"),
    "cutagent.action.clip.speed_ramp": ("clip.speed_ramp", "clip_speed_ramp"),
    "cutagent.action.clip.freeze": ("clip.freeze", "clip_freeze"),
    "cutagent.action.clip.reverse": ("clip.reverse", "clip_reverse"),
})
_RETIME = frozenset({
    "cutagent.action.clip.speed", "cutagent.action.clip.speed_ramp",
    "cutagent.action.clip.freeze", "cutagent.action.clip.reverse",
})
_EFFECT = "cutagent.action.edit.fx.add"

_CLIP_MOTION_TARGET_FIELDS = (
    "id", "trackType", "trackIndex", "recordStartFrame", "recordEndFrame", "name", "linkedItemIds",
)


def _clip_motion_target(private_target):
    return {key: private_target[key] for key in _CLIP_MOTION_TARGET_FIELDS}
_RESULT_DEFINITIONS = {definition.action_id: definition for definition in _DEFINITIONS}
_RESULT_FIELDS = {definition.action_id: definition.result_fields for definition in _DEFINITIONS}
_INTERPOLATION_NAMES = {
    "linear": "linear", "bezier": "bezier", "ease_in": "ease-in", "ease_out": "ease-out",
}
_PUBLIC_KEYFRAME_INTERPOLATIONS = {
    "linear": "linear", "bezier": "bezier", "ease-in": "ease_in", "ease-out": "ease_out",
}
_TRANSFORM_PROPERTIES = {
    "zoomX": "ZoomX", "zoomY": "ZoomY", "positionX": "Pan", "positionY": "Tilt",
    "rotation": "RotationAngle", "anchorX": "AnchorPointX", "anchorY": "AnchorPointY",
    "pitch": "Pitch", "yaw": "Yaw", "flipX": "FlipX", "flipY": "FlipY",
    "opacity": "Opacity", "cropLeft": "CropLeft", "cropRight": "CropRight",
    "cropTop": "CropTop", "cropBottom": "CropBottom", "distortion": "Distortion",
    "dynamicZoomEase": "DynamicZoomEase",
}


def _digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _timeline_targets(value: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    rows = []
    for key in ("target", "outgoing", "incoming"):
        if isinstance(value.get(key), Mapping):
            rows.append(value[key])
    rows.extend(value.get("linkedAudioTargets", ()))
    if not rows:
        raise ValidationError("Professional action omitted its exact target set.")
    identities = [row.get("id") for row in rows]
    if any(not isinstance(item, str) or not item for item in identities) \
            or len(set(identities)) != len(identities):
        raise ValidationError("Professional action target identity is incomplete or ambiguous.")
    return rows


def _locate(snapshot: Mapping[str, Any], target_id: str) -> Mapping[str, Any]:
    matches = [
        clip for track in snapshot.get("tracks", ()) for clip in track.get("clips", ())
        if clip.get("id") == target_id
    ]
    if len(matches) != 1:
        raise ValidationError("Professional action target is missing or ambiguous in fresh readback.")
    return matches[0]


def _protected_snapshot(
    snapshot: Mapping[str, Any], target_ids: set[str], *, action_id: str, value: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Canonical state outside the exact fields the action is allowed to change."""
    unrelated = []
    protected_targets = []
    edges = set()
    for track in snapshot.get("tracks", ()):
        for clip in track.get("clips", ()):
            clip_id = clip.get("id")
            if not isinstance(clip_id, str):
                continue
            linked = [item for item in clip.get("linkedItemIds", ()) if isinstance(item, str)]
            for other in linked:
                edges.add(tuple(sorted((clip_id, other))))
            if clip_id in target_ids:
                allowed = {"snapshotId", "snapshotRevision", "snapshotTrackId", "revision"}
                if action_id.endswith(".transform"):
                    requested = set(value.get("transform", {}))
                    transform = clip.get("transform")
                    stable_clip = {
                        key: deepcopy(item) for key, item in clip.items()
                        if key not in allowed | {"transform"}
                    }
                    if isinstance(transform, Mapping):
                        stable_clip["transform"] = {
                            key: deepcopy(item) for key, item in transform.items()
                            if key not in requested and key not in {_TRANSFORM_PROPERTIES.get(name) for name in requested}
                        }
                elif action_id in _RETIME:
                    stable_clip = {
                        key: deepcopy(item) for key, item in clip.items()
                        if key not in allowed | {
                            "recordRange", "sourceRange", "duration", "durationFrames", "speed",
                            "speedMultiplier", "reversed", "frozen", "timeMap", "retime",
                        }
                    }
                elif action_id == _EFFECT:
                    stable_clip = {
                        key: deepcopy(item) for key, item in clip.items()
                        if key not in allowed | {
                            "fusionCompositionCount", "fusionCompositionIds",
                            "fusionCompositions", "fusionGraphDigest",
                        }
                    }
                else:
                    stable_clip = {
                        key: deepcopy(item) for key, item in clip.items()
                        if key not in allowed | {"keyframes"}
                    }
                protected_targets.append({
                    "trackType": track.get("type"), "trackIndex": track.get("index"),
                    "clip": stable_clip,
                })
                continue
            stable_clip = {
                key: deepcopy(item) for key, item in clip.items()
                if key not in {"snapshotId", "snapshotRevision", "snapshotTrackId", "revision"}
            }
            unrelated.append({
                "trackType": track.get("type"),
                "trackIndex": track.get("index"),
                "clip": stable_clip,
            })
    return {
        "projectId": snapshot.get("project", {}).get("id"),
        "timelineId": snapshot.get("timeline", {}).get("id", snapshot.get("timelineId")),
        "unrelatedTimelineItems": sorted(unrelated, key=lambda item: str(item["clip"].get("id"))),
        "protectedTargetState": sorted(protected_targets, key=lambda item: str(item["clip"].get("id"))),
        "unrelatedLinkedEdges": [list(edge) for edge in sorted(edges)],
    }


@contextmanager
def _temporary_environment(values: Mapping[str, str]):
    prior = {key: os.environ.get(key) for key in values}
    os.environ.update(values)
    try:
        yield
    finally:
        for key, value in prior.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _handler_kwargs(action_id: str, value: Mapping[str, Any]) -> dict[str, Any]:
    target = value.get("target", {})
    name = target.get("name")
    if action_id == _EFFECT:
        effect = value["effect"]
        return {
            "name": effect["effectId"],
            "params": json.dumps(effect.get("parameters", {}), separators=(",", ":")),
            "verify": True,
        }
    if action_id.endswith(".transform"):
        names = {
            "zoomX": "zoom_x", "zoomY": "zoom_y", "positionX": "position_x",
            "positionY": "position_y", "anchorX": "anchor_x", "anchorY": "anchor_y",
            "flipX": "flip_x", "flipY": "flip_y", "cropLeft": "crop_left",
            "cropRight": "crop_right", "cropTop": "crop_top", "cropBottom": "crop_bottom",
            "dynamicZoomEase": "dynamic_zoom_ease",
        }
        return {"name": name, **{names.get(key, key): item for key, item in value["transform"].items()}}
    if action_id.endswith(".speed"):
        control = value["control"]
        kwargs = {
            "name": name, "ripple_timeline": False,
            "pitch_correction": value.get("pitchCorrection"),
            "keyframes": value["keyframes"].replace("_", "-"),
            "at": f"{target['recordRange']['start']}f",
        }
        if control["kind"] == "multiplier":
            kwargs["set_speed"] = control["multiplier"]
        else:
            kwargs["duration"] = f"{control['duration']['value']['value']}f"
        return kwargs
    if action_id.endswith(".freeze"):
        return {"name": name, "at": f"{target['recordRange']['start']}f"}
    if action_id.endswith(".reverse"):
        return {"name": name, "at": f"{target['recordRange']['start']}f"}
    if action_id.endswith(".speed_ramp"):
        kwargs = {
            "cut_at": f"{value['cut']['value']['value']}f",
            "out_frames": value["outDuration"]["value"]["value"],
            "in_frames": value["inDuration"]["value"]["value"],
            # The CLI peak only supplies omitted endpoint defaults and requires >1x.
            # SDK inputs declare every endpoint (or exact points), so keep that
            # unused default valid even for holds, 1x restoration and slow curves.
            "peak_speed": f"{max(2.0, value['outEndSpeed'], value['inStartSpeed'])}x",
            "curve": value["curve"].replace("_", "-"),
            "reverse_incoming": value["reverseIncoming"],
            "track": value["outgoing"]["trackIndex"],
            "out_start_speed": f"{value['outStartSpeed']}x",
            "out_end_speed": f"{value['outEndSpeed']}x",
            "in_start_speed": f"{value['inStartSpeed']}x",
            "in_end_speed": f"{value['inEndSpeed']}x",
        }
        curve_control = value.get("curveControl")
        if isinstance(curve_control, Mapping):
            for public_side, cli_side in (("outgoing", "out"), ("incoming", "in")):
                control = curve_control[public_side]
                if control["kind"] == "explicit_points":
                    kwargs[f"{cli_side}_point"] = [
                        _speed_ramp_point_spec(point) for point in control["points"]
                    ]
                    continue
                if "easing" in control:
                    kwargs[f"{cli_side}_ease"] = control["easing"].replace("_", "-")
                for public_name, cli_name in (
                    ("startHandle", "start_handle"), ("endHandle", "end_handle"),
                ):
                    if public_name in control:
                        kwargs[f"{cli_side}_{cli_name}"] = _speed_ramp_handle_spec(control[public_name])
                for public_name, cli_name in (
                    ("startInterpolationCode", "start_interp"),
                    ("endInterpolationCode", "end_interp"),
                ):
                    if public_name in control:
                        kwargs[f"{cli_side}_{cli_name}"] = control[public_name]
        return kwargs
    raise ValidationError("Professional action has no fixed CutAgent CLI lowering.")


def _seconds_spec(value: Mapping[str, Any]) -> str:
    return f"{value['value']}s"


def _speed_ramp_handle_spec(value: Mapping[str, Any]) -> str:
    return f"x={_seconds_spec(value['recordDelta'])},y={_seconds_spec(value['sourceDelta'])}"


def _speed_ramp_point_spec(value: Mapping[str, Any]) -> str:
    fields = [
        f"x={_seconds_spec(value['recordTime'])}",
        f"y={_seconds_spec(value['sourceTime'])}",
    ]
    for public_name, x_name, y_name in (
        ("incomingHandle", "xIn", "yIn"),
        ("outgoingHandle", "xOut", "yOut"),
    ):
        handle = value.get(public_name)
        if isinstance(handle, Mapping):
            fields.extend((
                f"{x_name}={_seconds_spec(handle['recordDelta'])}",
                f"{y_name}={_seconds_spec(handle['sourceDelta'])}",
            ))
    if "interpolationCode" in value:
        fields.append(f"interp={value['interpolationCode']}")
    return ",".join(fields)


def _keyframe_request(action_id: str, value: Mapping[str, Any]) -> KeyframeRequest:
    clip_name = value["target"]["name"]
    property_name = value["property"]
    if action_id.endswith("keyframe.add"):
        return AddKeyframe(
            clip_name, property_name, value["recordFrame"], value["value"],
            _INTERPOLATION_NAMES[value["interpolation"]],
        )
    if action_id.endswith("keyframe.delete"):
        return DeleteKeyframe(clip_name, property_name, value["recordFrame"])
    if action_id.endswith("keyframe.get"):
        return GetKeyframes(clip_name, property_name)
    if action_id.endswith("keyframe.set_interpolation"):
        return SetKeyframeInterpolation(
            clip_name, property_name, value["recordFrame"], _INTERPOLATION_NAMES[value["interpolation"]]
        )
    raise ValidationError("Professional keyframe action lacks a typed service request.")


def _materialize_handler_kwargs(function: Callable[..., Any], provided: Mapping[str, Any]) -> dict[str, Any]:
    """Replace Typer metadata defaults before invoking a command as Python."""
    result = dict(provided)
    for name, parameter in inspect.signature(function).parameters.items():
        if name in result or parameter.kind in {inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD}:
            continue
        default = parameter.default
        typer_default = getattr(default, "default", inspect.Parameter.empty)
        if typer_default is not inspect.Parameter.empty:
            default = typer_default
        if default is inspect.Parameter.empty or default is ...:
            raise ValidationError(f"Professional handler omitted required parameter: {name}.")
        result[name] = deepcopy(default)
    return result


def _project_transform_values(readback: Any) -> dict[str, Any]:
    observed = readback.get("value") if isinstance(readback, Mapping) else None
    if not isinstance(observed, Mapping):
        raise ValidationError("Professional transform result projection lacks independent readback.")
    inverse = {native: public for public, native in _TRANSFORM_PROPERTIES.items()}
    values = {inverse[name]: deepcopy(value) for name, value in observed.items() if name in inverse}
    if not values:
        raise ValidationError("Professional transform result projection contains no transform values.")
    return values


def _project_keyframe_rows(property_name: str, rows: Any) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        raise ValidationError("Professional keyframe result omitted exact native rows.")
    projected = []
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValidationError("Professional keyframe result contained a malformed native row.")
        record_frame = row.get("frame")
        if isinstance(record_frame, bool) or not isinstance(record_frame, int) \
                or record_frame < 0 or record_frame > 2**53 - 1:
            raise ValidationError("Professional keyframe result contained an invalid record frame.")
        try:
            public_value = float(row.get("value"))
        except (TypeError, ValueError):
            public_value = math.nan
        if not math.isfinite(public_value):
            raise ValidationError("Professional keyframe result contained a non-finite value.")
        native_interpolation = str(row.get("interpolation", "")).strip().lower().replace("_", "-")
        interpolation = _PUBLIC_KEYFRAME_INTERPOLATIONS.get(native_interpolation)
        if interpolation is None:
            raise ValidationError("Professional keyframe result contained an unsupported interpolation.")
        projected.append({
            "property": property_name,
            "recordFrame": record_frame,
            "value": public_value,
            "interpolation": interpolation,
        })
    return projected


def _time_map_state(timeline_item_id: str, value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "timelineItemId": timeline_item_id,
        "durationFrames": int(value["duration_frames"]),
        "speedMultiplier": float(value["speed_multiplier"]),
        "reversed": bool(value["reversed"]),
        "frozen": bool(value["frozen"]),
        "points": [{
            "recordFrame": int(point["record_frame"]),
            "sourceFrame": float(point["source_frame"]),
            "speed": float(point["speed"]),
            "interpolation": point["interpolation"],
        } for point in value["points"]],
    }


def _frame_range(value: Any, *, domain: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValidationError("Professional retime projection omitted an exact frame range.")
    start = value.get("start")
    end = value.get("endExclusive")
    if isinstance(start, bool) or isinstance(end, bool) \
            or not isinstance(start, int) or not isinstance(end, int) or end <= start:
        raise ValidationError("Professional retime projection contains an invalid frame range.")
    return {"domain": domain, "unit": "frames", "start": start, "endExclusive": end}


def _public_time_map_state(
    target: Mapping[str, Any], value: Mapping[str, Any]
) -> dict[str, Any]:
    points = []
    for point in value["points"]:
        source_frame = float(point["source_frame"])
        speed = float(point["speed"])
        if not math.isfinite(source_frame) or not math.isfinite(speed):
            raise ValidationError("Professional retime projection contains a non-finite time-map point.")
        points.append({
            "recordFrame": int(point["record_frame"]),
            # The public contract is a discrete frame-domain summary. The signed
            # terminal retains the exact decoded floating-point native map.
            "sourceFrame": int(round(source_frame)),
            "speed": speed,
            "interpolation": point["interpolation"],
        })
    return {
        "recordRange": _frame_range(target.get("recordRange"), domain="timeline_record_range"),
        "sourceRange": _frame_range(target.get("sourceRange"), domain="source_range"),
        "reversed": bool(value["reversed"]),
        "frozen": bool(value["frozen"]),
        "points": points,
    }


def _record_range(target: Mapping[str, Any]) -> tuple[int, int]:
    frame_range = target.get("recordRange")
    if isinstance(frame_range, Mapping):
        start = frame_range.get("start")
        end = frame_range.get("endExclusive")
    else:
        start = target.get("recordStartFrame")
        end = target.get("recordEndFrame")
    if isinstance(start, bool) or isinstance(end, bool) \
            or not isinstance(start, int) or not isinstance(end, int) or end <= start:
        raise ValidationError("Professional speed ramp target has an invalid record range.")
    return start, end


def _point_position(point: Mapping[str, Any]) -> float:
    try:
        position = float(point.get("record_position", point.get("record_frame")))
    except (TypeError, ValueError):
        position = math.nan
    if not math.isfinite(position):
        raise ValidationError("Professional speed ramp readback has an invalid point position.")
    return position


def _point_source_position(point: Mapping[str, Any], key: str = "source_frame") -> float:
    try:
        position = float(point[key])
    except (KeyError, TypeError, ValueError):
        position = math.nan
    if not math.isfinite(position):
        raise ValidationError("Professional speed ramp readback has an invalid source position.")
    return position


def _point_slope(start: Mapping[str, Any], end: Mapping[str, Any]) -> float:
    delta_record = _point_position(end) - _point_position(start)
    if abs(delta_record) <= 1e-9:
        raise ValidationError("Professional speed ramp readback has a zero-length curve segment.")
    return (_point_source_position(end) - _point_source_position(start)) / delta_record


def _handle_slope(point: Mapping[str, Any], suffix: str) -> float:
    handle = {
        "record_position": point.get(f"record_frame_{suffix}"),
        "source_frame": point.get(f"source_frame_{suffix}"),
    }
    return _point_slope(point, handle)


def _expected_speed_ramp_points(control: Mapping[str, Any]) -> list[dict[str, float | int]]:
    expected = []
    for point in control["points"]:
        incoming = point.get("incomingHandle", {})
        outgoing = point.get("outgoingHandle", {})
        expected.append({
            "x": float(point["recordTime"]["value"]),
            "y": float(point["sourceTime"]["value"]),
            "x_in": float(incoming.get("recordDelta", {}).get("value", 0.0)),
            "y_in": float(incoming.get("sourceDelta", {}).get("value", 0.0)),
            "x_out": float(outgoing.get("recordDelta", {}).get("value", 0.0)),
            "y_out": float(outgoing.get("sourceDelta", {}).get("value", 0.0)),
            "interp": int(point.get("interpolationCode", 0)),
        })
    return expected


def _assert_exact_speed_ramp_points(
    actual: list[dict[str, float | int]] | None,
    expected: list[dict[str, float | int]],
    *, role: str,
) -> None:
    if actual is None or len(actual) != len(expected):
        raise ValidationError(f"Professional speed ramp readback mismatched the {role} explicit point count.")
    for actual_point, expected_point in zip(actual, expected):
        if any(abs(float(actual_point[key]) - float(expected_point[key])) > 1e-7
               for key in ("x", "y", "x_in", "y_in", "x_out", "y_out")) \
                or int(actual_point["interp"]) != int(expected_point["interp"]):
            raise ValidationError(f"Professional speed ramp readback mismatched the {role} explicit points.")


def _validate_speed_ramp_curve_control(
    control: Mapping[str, Any] | None,
    exact_points: list[dict[str, float | int]] | None,
    *, role: str,
) -> None:
    if not isinstance(control, Mapping):
        return
    if control["kind"] == "explicit_points":
        _assert_exact_speed_ramp_points(
            exact_points, _expected_speed_ramp_points(control), role=role,
        )
        return
    if exact_points is None or len(exact_points) < 2:
        raise ValidationError(f"Professional speed ramp readback omitted the {role} native points.")
    start, end = (exact_points[-2], exact_points[-1]) if role == "outgoing" else (exact_points[0], exact_points[1])
    for public_name, point, x_key, y_key in (
        ("startHandle", start, "x_out", "y_out"),
        ("endHandle", end, "x_in", "y_in"),
    ):
        requested = control.get(public_name)
        if isinstance(requested, Mapping) and (
            abs(float(point[x_key]) - float(requested["recordDelta"]["value"])) > 1e-7
            or abs(float(point[y_key]) - float(requested["sourceDelta"]["value"])) > 1e-7
        ):
            raise ValidationError(f"Professional speed ramp readback mismatched the {role} {public_name}.")
    for public_name, point in (
        ("startInterpolationCode", start), ("endInterpolationCode", end),
    ):
        if public_name in control and int(point["interp"]) != int(control[public_name]):
            raise ValidationError(f"Professional speed ramp readback mismatched the {role} raw interpolation code.")
    easing = control.get("easing")
    if easing is not None:
        expected_handles = {
            "none": (False, False), "in": (False, True),
            "out": (True, False), "in_out": (True, True),
        }[easing]
        observed_handles = (
            abs(float(start["x_out"])) > 1e-12 or abs(float(start["y_out"])) > 1e-12,
            abs(float(end["x_in"])) > 1e-12 or abs(float(end["y_in"])) > 1e-12,
        )
        overridden = ("startHandle" in control, "endHandle" in control)
        if any(not overridden[index] and observed_handles[index] != expected_handles[index] for index in (0, 1)):
            raise ValidationError(f"Professional speed ramp readback mismatched the {role} easing mode.")


def _validate_speed_ramp_state(
    state: Mapping[str, Any], target: Mapping[str, Any], *, role: str,
    ramp_frames: int, start_speed: float, end_speed: float,
    curve: str, reversed_expected: bool,
    curve_control: Mapping[str, Any] | None = None,
    exact_points: list[dict[str, float | int]] | None = None,
) -> None:
    record_start, record_end = _record_range(target)
    full_duration = record_end - record_start
    points = state.get("points")
    duration = state.get("duration_frames")
    if isinstance(duration, bool) or not isinstance(duration, int) or duration != full_duration \
            or state.get("reversed") is not reversed_expected \
            or not isinstance(points, list) or len(points) < 2 \
            or any(not isinstance(point, Mapping) for point in points):
        raise ValidationError(f"Professional speed ramp readback mismatched the {role} time map.")
    _validate_speed_ramp_curve_control(curve_control, exact_points, role=role)
    if isinstance(curve_control, Mapping) and curve_control.get("kind") == "explicit_points":
        return
    ramp_start, ramp_end = (points[-2], points[-1]) if role == "outgoing" else (points[0], points[1])
    observed_span = _point_position(ramp_end) - _point_position(ramp_start)
    expected_span = min(int(ramp_frames), full_duration - 1)
    if abs(observed_span - expected_span) > 1e-4:
        raise ValidationError(f"Professional speed ramp readback mismatched the {role} ramp interval.")
    sign = -1.0 if reversed_expected else 1.0
    expected_start = sign * float(start_speed)
    expected_end = sign * float(end_speed)
    try:
        observed_segment_speed = float(ramp_start["speed"])
    except (KeyError, TypeError, ValueError):
        observed_segment_speed = math.nan
    if not math.isfinite(observed_segment_speed) \
            or abs(observed_segment_speed - ((expected_start + expected_end) / 2.0)) > 1e-4:
        raise ValidationError(f"Professional speed ramp readback mismatched the {role} speed curve.")
    if not any(point.get("interpolation") == "bezier" for point in (ramp_start, ramp_end)):
        raise ValidationError(f"Professional speed ramp readback mismatched the {role} curve interpolation.")
    encoded_segment_speed = _point_slope(ramp_start, ramp_end)
    if abs(encoded_segment_speed) <= 1e-9:
        raise ValidationError(f"Professional speed ramp readback has no {role} encoded curve motion.")
    observed_start_ratio = _handle_slope(ramp_start, "out") / encoded_segment_speed
    observed_end_ratio = _handle_slope(ramp_end, "in") / encoded_segment_speed
    expected_average = (expected_start + expected_end) / 2.0
    expected_start_ratio = expected_start / expected_average
    expected_end_ratio = expected_end / expected_average
    if (
        abs(observed_start_ratio - expected_start_ratio) > 1e-4
        or abs(observed_end_ratio - expected_end_ratio) > 1e-4
    ):
        raise ValidationError(f"Professional speed ramp readback mismatched the {role} ordered endpoint speeds.")


def _retime_projection(action_id: str, value: Mapping[str, Any], raw: Any, snapshot: Mapping[str, Any]) -> dict[str, Any]:
    payload = raw.get("data", raw) if isinstance(raw, Mapping) else None
    updates = payload.get("updated") if isinstance(payload, Mapping) else None
    verification = payload.get("verification") if isinstance(payload, Mapping) else None
    checks = verification.get("checks") if isinstance(verification, Mapping) else None
    if not isinstance(updates, list) or not updates or not isinstance(checks, list) or not checks \
            or any(not isinstance(check, Mapping) or check.get("ok") is not True for check in checks):
        raise ValidationError("Professional retime handler omitted exact structural proof.")
    declared = _timeline_targets(value)
    remaining = list(declared)
    observed = []
    before = []
    after = []
    native_before = {}
    native_after = {}
    for update in updates:
        if not isinstance(update, Mapping):
            raise ValidationError("Professional retime handler returned a malformed update row.")
        media_kind = update.get("media_kind")
        track_index = update.get("track_index")
        start = update.get("start")
        matches = [row for row in remaining if row.get("trackType") == media_kind
                   and row.get("trackIndex") == track_index
                   and row.get("recordRange", {}).get("start", row.get("recordStartFrame")) == start]
        if len(matches) != 1:
            raise ValidationError("Professional retime proof could not bind one declared target.")
        row = matches[0]
        remaining.remove(row)
        clip = _locate(snapshot, row["id"])
        role = "linked_audio" if row["trackType"] == "audio" else (
            "outgoing" if row is value.get("outgoing") else
            "incoming" if row is value.get("incoming") else "target"
        )
        # A nonlinear result may have no native linear interval. In that case
        # sourceRange retains the admitted source authority; curves carry the
        # actual mapping, including holds and reversals.
        observed.append({
            "id": row["id"], "role": role,
            "trackType": row["trackType"], "trackIndex": row["trackIndex"],
            "recordRange": deepcopy(clip.get("recordRange", row.get("recordRange"))),
            "sourceRange": deepcopy(clip.get("sourceRange") or row.get("sourceRange")),
            "linkedItemIds": list(clip.get("linkedItemIds", row.get("linkedItemIds", ()))),
        })
        native_before[row["id"]] = update["before_state"]
        native_after[row["id"]] = update["after_state"]
        before.append(_time_map_state(row["id"], update["before_state"]))
        after.append(_time_map_state(row["id"], update["after_state"]))
    if remaining:
        raise ValidationError("Professional retime proof omitted declared targets.")
    primary = [value["outgoing"], value["incoming"]] \
        if action_id == "cutagent.action.clip.speed_ramp" else [value["target"]]
    declared_ids = {row["id"] for row in declared}
    public_targets = []
    for requested in primary:
        clip = _locate(snapshot, requested["id"])
        track_type = requested["trackType"]
        track_index = requested["trackIndex"]
        track = next((candidate for candidate in snapshot.get("tracks", ())
                      if candidate.get("type") == track_type and candidate.get("index") == track_index), None)
        if not isinstance(track, Mapping):
            raise ValidationError("Professional retime projection lost its exact target track.")
        record_range = _frame_range(clip.get("recordRange"), domain="timeline_record_range")
        neighbors = []
        for other in track.get("clips", ()):
            if other.get("id") in declared_ids or not isinstance(other.get("recordRange"), Mapping):
                continue
            other_range = _frame_range(other["recordRange"], domain="timeline_record_range")
            if other_range["endExclusive"] == record_range["start"]:
                relationship = "previous"
            elif other_range["start"] == record_range["endExclusive"]:
                relationship = "next"
            elif other_range["start"] < record_range["endExclusive"] \
                    and record_range["start"] < other_range["endExclusive"]:
                relationship = "overlapping"
            else:
                continue
            neighbors.append({
                "timelineItemId": other["id"], "relationship": relationship,
                "recordRange": other_range,
            })
        public_targets.append({
            "projectId": value["projectId"],
            "timelineId": value["timelineId"],
            "timelineItemId": requested["id"],
            "snapshotTimelineItemId": clip.get("snapshotId", requested.get("snapshotId")),
            "name": clip.get("name", requested.get("name")),
            "track": {"type": track_type, "index": track_index},
            "recordRange": record_range,
            "sourceRange": _frame_range(
                clip.get("sourceRange") or requested.get("sourceRange"), domain="source_range",
            ),
            "linkedTimelineItemIds": list(clip.get("linkedItemIds", requested.get("linkedItemIds", ()))),
            "protectedNeighbors": neighbors[:16],
        })
    representative = primary[0]
    representative_id = representative["id"]
    before_target = {
        "recordRange": representative.get("recordRange"),
        "sourceRange": representative.get("sourceRange"),
    }
    after_target = next(row for row in public_targets if row["timelineItemId"] == representative_id)
    from .retime_curve_projection import exact_curves

    before_map = _public_time_map_state(before_target, native_before[representative_id])
    after_map = _public_time_map_state(after_target, native_after[representative_id])
    before_curves = exact_curves(declared, native_before)
    after_curve_targets = [{**target, "recordRange": observed_target["recordRange"], "sourceRange": observed_target["sourceRange"]}
                           for target in declared for observed_target in observed if target["id"] == observed_target["id"]]
    after_curves = exact_curves(after_curve_targets, native_after)
    if before_curves is not None:
        before_map["curves"] = before_curves
    if after_curves is not None:
        after_map["curves"] = after_curves
    public_result = {
        "actionId": action_id,
        "payload": {
            "status": "completed",
            "changed": True,
            "revision": {
                "relationship": "advanced",
                "before": value["timelineRevision"],
                "after": snapshot.get("revision"),
            },
            "targets": public_targets,
            "change": {
                "kind": "time_map",
                "before": before_map,
                "after": after_map,
            },
            "verification": {
                "outcome": "passed",
                "evidence": [
                    {
                        "kind": "structural_readback",
                        "summary": f"Exact native time-map readback matched {len(updates)} declared A/V target(s).",
                        "artifactId": None,
                    },
                ],
                "protectedState": "preserved",
            },
            "recovery": {
                "state": "not_needed",
                "retry": "inspect_state_first",
                "guidance": "Inspect the returned time-map state before retrying this mutation.",
            },
        },
    }
    return {
        "actionId": action_id,
        "timelineRevision": snapshot.get("revision"),
        "targets": observed,
        "before": before,
        "after": after,
        "verification": {
            "protectedStatePreserved": True,
            "structuralEvidenceCount": len(updates),
        },
        "publicResult": public_result,
    }


class ProfessionalPrimitiveCliOwner:
    """One production owner with fixed command admission and native behavior."""

    def __init__(self, action_id: str, *, handler_resolver: Callable[[str], Callable[..., Any]] | None = None):
        if action_id not in _HANDLERS:
            raise ValueError("Unknown professional primitive action.")
        self.action_id = action_id
        self._handler_resolver = handler_resolver
        self._inspector = None

    def bind_private_timeline_inspector(self, inspector):
        if not callable(inspector):
            raise TypeError("Professional private timeline inspector must be callable.")
        self._inspector = inspector

    def invoke_admitted_handler(self, *_args, **_kwargs):
        """Satisfy host authority composition without opening residual dispatch."""
        raise ValidationError("Professional actions execute only through their fixed descriptor owner.")

    def _inspect(self, value, *, phase="current"):
        if not callable(self._inspector):
            raise ValidationError("Professional action lacks fresh private inspection.")
        if phase not in {"current", "verify"}:
            raise ValidationError("Professional private inspection phase is invalid.")
        result = self._inspector({
            "phase": phase,
            "projectId": value["projectId"],
            "timelineId": value["timelineId"],
        })
        if not isinstance(result, Mapping) or not isinstance(result.get("snapshot"), Mapping):
            raise ValidationError("Professional private inspection returned no timeline snapshot.")
        snapshot = result["snapshot"]
        private_ids = result.get("privateTimelineItemNativeIds")
        if not isinstance(private_ids, Mapping):
            raise ValidationError("Professional private inspection omitted native target custody.")
        if snapshot.get("timeline", {}).get("id", snapshot.get("timelineId")) != value["timelineId"]:
            raise ValidationError("Professional private inspection changed timeline identity.")
        return result

    def _handler(self):
        command_id, name = _HANDLERS[self.action_id]
        if self._handler_resolver is not None:
            handler = self._handler_resolver(name)
        else:
            if self.action_id == _EFFECT:
                from ..commands import edit as command_module
            else:
                from ..commands import clip as command_module
            handler = getattr(command_module, name, None)
        function = inspect.unwrap(handler) if callable(handler) else None
        if not callable(function):
            raise ValidationError("Professional CutAgent CLI handler is unavailable.")
        return command_id, function

    def _private_targets(self, inspected, public_rows, *, require_declared_ranges, require_source_ranges=True):
        snapshot = inspected["snapshot"]
        private_ids = inspected["privateTimelineItemNativeIds"]
        results = []
        for public in public_rows:
            matches = [
                (track, clip) for track in snapshot.get("tracks", ()) for clip in track.get("clips", ())
                if clip.get("id") == public["id"]
            ]
            if len(matches) != 1:
                raise ValidationError("Professional exact target disappeared or became ambiguous.")
            track, clip = matches[0]
            start = clip.get("recordRange", {}).get("start", clip.get("recordStartFrame"))
            end = clip.get("recordRange", {}).get("endExclusive", clip.get("recordEndFrame"))
            source_start = (clip.get("sourceRange") or {}).get("start", clip.get("sourceStartFrame"))
            source_end = (clip.get("sourceRange") or {}).get("endExclusive", clip.get("sourceEndFrame"))
            source_origin = public.get("sourceOriginFrame")
            if source_origin is not None and require_source_ranges:
                metadata = clip.get("retimeSource")
                if self.action_id != "cutagent.action.clip.speed_ramp" or not isinstance(metadata, Mapping) \
                        or metadata.get("originFrame") != source_origin \
                        or metadata.get("availableRange") != public.get("sourceRange"):
                    raise ValidationError("Professional curve authoring source authority is stale or unavailable.")
                source_start = metadata["availableRange"]["start"]
                source_end = metadata["availableRange"]["endExclusive"]
            declared_start = public.get("recordStartFrame", public.get("recordRange", {}).get("start"))
            declared_end = public.get("recordEndFrame", public.get("recordRange", {}).get("endExclusive"))
            declared_links = set(public.get("linkedItemIds", ()))
            observed_links = set(clip.get("linkedItemIds", ()))
            declared_media = public.get("mediaPoolItemId")
            if track.get("type") != public["trackType"] or track.get("index") != public["trackIndex"] \
                    or clip.get("name") != public["name"] \
                    or observed_links != declared_links \
                    or (declared_media is not None and clip.get("mediaPoolItemId") != declared_media) \
                    or (require_declared_ranges and (start != declared_start or end != declared_end)):
                raise ValidationError("Professional exact target no longer matches its declared identity, topology or range.")
            if self.action_id in _RETIME and require_source_ranges and (
                not isinstance(source_start, int) or not isinstance(source_end, int) or source_end <= source_start
            ):
                raise ValidationError("Professional retime target omitted its exact source range.")
            native_id = private_ids.get(public["id"])
            native_links = [private_ids.get(item_id) for item_id in clip.get("linkedItemIds", ())]
            if not native_id or any(not item for item in native_links):
                raise ValidationError("Professional private inspection omitted exact native target identity.")
            results.append({
                "id": native_id, "trackType": track["type"], "trackIndex": track["index"],
                "recordStartFrame": start, "recordEndFrame": end, "name": clip["name"],
                "sourceStartFrame": source_start, "sourceEndFrame": source_end,
                **({"sourceOriginFrame": source_origin} if source_origin is not None else {}),
                "linkedItemIds": native_links,
            })
        return results

    def _matches_carrier_admission(self, action_id, command_id, admitted_handler):
        if action_id != self.action_id or _HANDLERS.get(action_id, (None,))[0] != command_id:
            return False
        try:
            _bound_command, function = self._handler()
        except Exception:
            return False
        return function is admitted_handler

    def normalize_input(self, value):
        return deepcopy(dict(value))

    def resolve_exact(self, _context, value):
        inspected = self._inspect(value, phase="current")
        snapshot = inspected["snapshot"]
        if snapshot.get("revision") != value["timelineRevision"]:
            raise ValidationError("Professional action timeline revision is stale.")
        rows = _timeline_targets(value)
        self._private_targets(inspected, rows, require_declared_ranges=True)
        target_ids = {row["id"] for row in rows}
        return {
            "targets": [{
                "kind": "clip", "stableId": row["id"],
                "revision": value["timelineRevision"], "projectId": value["projectId"],
                "timelineId": value["timelineId"],
            } for row in rows],
            "preState": {"snapshotDigest": _digest(snapshot), "input": deepcopy(value)},
            "lowering": {"boundOwner": self.action_id},
            "protectedState": {"timelineDigest": _digest(_protected_snapshot(
                snapshot, target_ids, action_id=self.action_id, value=value,
            ))},
        }

    def build_impact(self, _context, value, authority):
        if self.action_id.endswith("keyframe.get"):
            return {
                "contractVersion": 1,
                "status": "read",
                "complete": True,
                "targetDigests": _read_target_digests(authority),
                "resultMaximumBytes": 8_388_608,
            }
        modalities = ["readback", "structural", *(["rendered"] if self.action_id == _EFFECT else [])]
        public_targets = {item["id"]: item for item in _timeline_targets(value)}
        targets = []
        for item in authority["targets"]:
            public = public_targets.get(item["stableId"])
            if not isinstance(public, Mapping):
                raise ValidationError("Professional impact omitted an exact declared target.")
            target = {
                "kind": item["kind"],
                "stableId": item["stableId"],
                "revision": item["revision"],
                "trackType": public["trackType"],
                "trackIndex": public["trackIndex"],
            }
            if public.get("mediaRole") is not None:
                target["mediaRole"] = public["mediaRole"]
            targets.append(target)
        track_types = sorted({target["trackType"] for target in targets})
        return {
            "status": "mutation", "complete": True, "ambiguous": False, "broad": False,
            "effects": [{
                "operation": self.action_id.removeprefix("cutagent.action."),
                "kind": "update", "trackTypes": track_types,
                "placementIntent": "explicit", "complete": True,
                "ambiguous": False, "broad": False,
                "targets": targets,
            }],
            "closedComposition": True,
            "executableStableTargetPrecondition": True,
            "verificationPolicy": {
                "minimumEvidence": modalities,
                "requireProtectedStatePreserved": True,
                "protectedTargetEvidence": "every_declared_target",
            },
        }

    def execute(self, context, value, _prepared):
        if context.get("executionAuthority") is not self:
            raise ValidationError("Professional handler lacks carrier admission authority.")
        command_id, function = self._handler()
        target_rows = _timeline_targets(value)
        primary = target_rows[0]
        inspected = self._inspect(value, phase="current")
        private_targets = self._private_targets(inspected, target_rows, require_declared_ranges=True)
        env = {
            "CUTAGENT_SDK_EXPECTED_CLIP_MOTION_TARGET": json.dumps(
                _clip_motion_target(private_targets[0]), separators=(",", ":"),
            ),
            "CUTAGENT_SDK_EXPECTED_RETIME_TARGETS": json.dumps(private_targets, separators=(",", ":")),
        }
        if self.action_id == _EFFECT:
            env["CUTAGENT_SDK_EXPECTED_CLIP_MOTION_TARGET"] = json.dumps(
                _clip_motion_target(private_targets[0]), separators=(",", ":"),
            )
        before_independent = self._independent_protected_readback(value, private_targets)
        if self.action_id.startswith("cutagent.action.clip.keyframe."):
            from ..commands import clip

            with ExitStack() as stack:
                stack.enter_context(_temporary_environment(env))
                stack.enter_context(_prepared_action_admission_scope(
                    self.action_id, command_id, self, function, context,
                ))
                raw = execute_keyframe(
                    clip.get_connection(require_timeline=True),
                    _keyframe_request(self.action_id, value),
                )
        else:
            with ExitStack() as stack:
                captured = stack.enter_context(capture_prepared_action_output())
                stack.enter_context(_temporary_environment(env))
                stack.enter_context(_prepared_action_admission_scope(
                    self.action_id, command_id, self, function, context,
                ))
                kwargs = _materialize_handler_kwargs(function, _handler_kwargs(self.action_id, value))
                if self.action_id == _EFFECT:
                    kwargs["item_id"] = private_targets[0]["id"]
                returned = function(**kwargs)
            if len(captured) > 1:
                raise ValidationError("Professional handler emitted multiple terminal results.")
            raw = captured[0] if captured else returned
            if raw is None:
                raise ValidationError("Professional handler emitted no inspectable result.")
        after = self._inspect(value, phase="verify")
        after_private_targets = self._private_targets(
            after, target_rows, require_declared_ranges=self.action_id not in _RETIME,
            require_source_ranges=self.action_id not in _RETIME,
        )
        protected_keys = ("id", "trackType", "trackIndex", "name", "linkedItemIds") \
            if self.action_id in _RETIME else tuple(private_targets[0])
        if [
            {key: item.get(key) for key in protected_keys} for item in after_private_targets
        ] != [
            {key: item.get(key) for key in protected_keys} for item in private_targets
        ]:
            raise ValidationError("Professional private target identity or protected topology changed after execution.")
        if self.action_id in _RETIME:
            # Nonlinear native curves can invalidate linear source-offset getters.
            # Retain the source authority admitted before mutation: fresh exact
            # identities/record ranges above and decoded curve proof below
            # verify the result against that original authority, never a guessed
            # post-retime interval.
            for before_target, after_target in zip(private_targets, after_private_targets):
                after_target["sourceStartFrame"] = before_target["sourceStartFrame"]
                after_target["sourceEndFrame"] = before_target["sourceEndFrame"]
        independent = self._independent_readback(value, raw, after_private_targets)
        return {
            "raw": raw, "afterSnapshot": after["snapshot"], "primary": primary,
            "beforeIndependentReadback": before_independent,
            "independentReadback": independent,
        }

    def _independent_protected_readback(self, value, private_targets):
        if self.action_id == _EFFECT:
            return {
                "kind": "effect_before",
                "value": {"compositions": self._effect_compositions(value, phase="current")},
            }
        if self.action_id in _RETIME:
            return None
        return self._independent_readback(value, {}, private_targets)

    def _effect_compositions(self, value, *, phase):
        if phase not in {"current", "verify"}:
            raise ValidationError("Professional effect Fusion inspection phase is invalid.")
        inspected = self._inspector({
            "phase": phase, "operation": "fusion.compositions", "projectId": value["projectId"],
            "timelineId": value["timelineId"], "timelineItemId": value["target"]["id"],
        })
        rows = inspected.get("value") if isinstance(inspected, Mapping) else None
        if not isinstance(rows, list):
            raise ValidationError("Professional effect fresh Fusion readback is unavailable.")
        if any(not isinstance(row, Mapping) or not row.get("id") or not row.get("graphDigest") for row in rows):
            raise ValidationError("Professional effect proof has incomplete composition identity.")
        return rows

    def _independent_readback(self, value, raw, private_targets):
        if self.action_id == _EFFECT:
            payload = raw.get("data", raw) if isinstance(raw, Mapping) else None
            verification = payload.get("verification") if isinstance(payload, Mapping) else None
            checks = verification.get("checks") if isinstance(verification, Mapping) else None
            proof = verification.get("render_proof") if isinstance(verification, Mapping) else None
            if verification.get("status") != "verified" or not isinstance(checks, list) \
                    or not checks or any(item.get("ok") is not True for item in checks) \
                    or not isinstance(proof, Mapping):
                raise ValidationError("Professional effect omitted structural or rendered verification.")
            rows = self._effect_compositions(value, phase="verify")
            if not rows:
                raise ValidationError("Professional effect fresh Fusion readback is unavailable.")
            return {"kind": "effect", "value": {"compositions": rows}, "rendered": proof}
        from ..commands import clip
        from ..core import clip_ops, speed_ramp_db

        connection = clip.get_connection(require_timeline=True)
        primary = _timeline_targets(value)[0]
        name = primary["name"]
        env = {
            "CUTAGENT_SDK_EXPECTED_CLIP_MOTION_TARGET": json.dumps(
                _clip_motion_target(private_targets[0]), separators=(",", ":"),
            ),
            "CUTAGENT_SDK_EXPECTED_RETIME_TARGETS": json.dumps(private_targets, separators=(",", ":")),
        }
        if self.action_id.startswith("cutagent.action.clip.keyframe."):
            with _temporary_environment(env):
                return {
                    "kind": "keyframes",
                    "value": execute_keyframe(
                        connection, GetKeyframes(name, value.get("property"))
                    ),
                }
        if self.action_id.endswith(".transform"):
            with _temporary_environment(env):
                return {"kind": "transform", "value": clip_ops.get_clip_transform(connection, name)}
        payload = raw.get("data", raw) if isinstance(raw, Mapping) else None
        updates = payload.get("updated") if isinstance(payload, Mapping) else None
        if not isinstance(updates, list) or not updates:
            raise ValidationError("Professional retime omitted exact affected rows for independent proof.")
        at = primary.get("recordStartFrame", primary.get("recordRange", {}).get("start"))
        structural = speed_ramp_db.inspect_selected_retime_rows(
            connection, clip_name=name, at=f"{at}f", expected_targets=private_targets,
        )
        return {"kind": "retime", "value": structural}

    def _validate_independent_readback(self, value, independent):
        kind = independent.get("kind") if isinstance(independent, Mapping) else None
        observed = independent.get("value") if isinstance(independent, Mapping) else None
        if self.action_id == _EFFECT:
            rows = observed.get("compositions") if isinstance(observed, Mapping) else None
            if kind != "effect" or not isinstance(rows, list) or not rows:
                raise ValidationError("Professional effect proof has no fresh composition readback.")
            if any(not isinstance(row, Mapping) or not row.get("id") or not row.get("graphDigest") for row in rows):
                raise ValidationError("Professional effect proof has incomplete composition identity.")
            if not isinstance(independent.get("rendered"), Mapping):
                raise ValidationError("Professional effect proof lacks rendered evidence.")
            return
        if self.action_id.startswith("cutagent.action.clip.keyframe."):
            if kind != "keyframes" or not isinstance(observed, Mapping):
                raise ValidationError("Professional keyframe proof is unavailable.")
            rows = observed.get("keyframes")
            if not isinstance(rows, list):
                raise ValidationError("Professional keyframe proof has no exact keyframe rows.")
            frame = value.get("recordFrame")
            matches = [row for row in rows if isinstance(row, Mapping) and row.get("frame") == frame]
            if self.action_id.endswith(".get"):
                return
            if self.action_id.endswith(".delete"):
                if matches:
                    raise ValidationError("Professional keyframe delete did not remove the exact frame.")
                return
            if len(matches) != 1:
                raise ValidationError("Professional keyframe mutation did not resolve one exact frame.")
            match = matches[0]
            if self.action_id.endswith(".add") and abs(float(match.get("value")) - float(value["value"])) > 1e-6:
                raise ValidationError("Professional keyframe add read back the wrong value.")
            expected_interpolation = _INTERPOLATION_NAMES[value["interpolation"]]
            if str(match.get("interpolation", "")).lower().replace("_", "-") != expected_interpolation:
                raise ValidationError("Professional keyframe interpolation readback did not match the request.")
            return
        if self.action_id.endswith(".transform"):
            if kind != "transform" or not isinstance(observed, Mapping):
                raise ValidationError("Professional transform proof is unavailable.")
            for public_name, expected in value["transform"].items():
                actual = observed.get(_TRANSFORM_PROPERTIES[public_name])
                if isinstance(expected, (int, float)) and not isinstance(expected, bool):
                    if not isinstance(actual, (int, float)) or abs(float(actual) - float(expected)) > 1e-6:
                        raise ValidationError(f"Professional transform readback mismatched {public_name}.")
                elif actual != expected:
                    raise ValidationError(f"Professional transform readback mismatched {public_name}.")
            return
        if kind != "retime" or not isinstance(observed, Mapping) or not isinstance(observed.get("rows"), list):
            raise ValidationError("Professional retime proof is unavailable.")
        rows = observed["rows"]
        declared = _timeline_targets(value)
        semantic_by_target = {}
        exact_points_by_target = {}
        for target in declared:
            start = target.get("recordRange", {}).get("start", target.get("recordStartFrame"))
            matches = [row for row in rows if row.get("live_track_type") == target.get("trackType")
                       and row.get("live_track_index") == target.get("trackIndex")
                       and int(row.get("Start")) == int(start)]
            timemap = matches[0].get("MediaTimemapBA", {}) if len(matches) == 1 else {}
            semantic = matches[0].get("state", matches[0].get("semantic_state")) if len(matches) == 1 else None
            if len(matches) != 1 or not isinstance(timemap.get("hex"), str) or not timemap["hex"] \
                    or not isinstance(semantic, Mapping):
                raise ValidationError("Professional retime proof omitted an exact declared target row.")
            semantic_by_target[target["id"]] = semantic
            if self.action_id.endswith(".speed_ramp"):
                from ..core import speed_ramp_db
                exact_points_by_target[target["id"]] = speed_ramp_db._decoded_timemap_points(  # noqa: SLF001
                    bytes.fromhex(timemap["hex"])
                )
                if "native_record_origin_seconds" in semantic and exact_points_by_target[target["id"]] is not None:
                    record_origin = float(semantic["native_record_origin_seconds"])
                    source_origin = float(target.get("sourceOriginFrame", target["sourceRange"]["start"])) / float(semantic["source_fps"])
                    exact_points_by_target[target["id"]] = [
                        {**point, "x": float(point["x"]) - record_origin, "y": float(point["y"]) - source_origin}
                        for point in exact_points_by_target[target["id"]]
                    ]
        if self.action_id.endswith(".speed"):
            control = value["control"]
            for state in semantic_by_target.values():
                if control["kind"] == "multiplier":
                    if abs(float(state["speed_multiplier"]) - float(control["multiplier"])) > 1e-5:
                        raise ValidationError("Professional speed readback mismatched the requested multiplier.")
                elif int(state["duration_frames"]) != int(control["duration"]["value"]["value"]):
                    raise ValidationError("Professional speed readback mismatched the requested duration.")
        elif self.action_id.endswith(".freeze"):
            if any(state.get("frozen") is not True for state in semantic_by_target.values()):
                raise ValidationError("Professional freeze readback did not contain the requested hold map.")
        elif self.action_id.endswith(".reverse"):
            if any(state.get("reversed") is not True for state in semantic_by_target.values()):
                raise ValidationError("Professional reverse readback did not contain the requested reverse map.")
        elif self.action_id.endswith(".speed_ramp"):
            curve_control = value.get("curveControl")
            for role, duration_key, start_key, end_key, reversed_expected in (
                ("outgoing", "outDuration", "outStartSpeed", "outEndSpeed", False),
                ("incoming", "inDuration", "inStartSpeed", "inEndSpeed", bool(value["reverseIncoming"])),
            ):
                target = value[role]
                state = semantic_by_target[target["id"]]
                _validate_speed_ramp_state(
                    state, target, role=role,
                    ramp_frames=int(value[duration_key]["value"]["value"]),
                    start_speed=float(value[start_key]), end_speed=float(value[end_key]),
                    curve=value["curve"], reversed_expected=reversed_expected,
                    curve_control=(curve_control or {}).get(role),
                    exact_points=exact_points_by_target[target["id"]],
                )
            for target in value.get("linkedAudioTargets", ()):
                side = "outgoing" if target["recordRange"]["start"] == value["outgoing"]["recordRange"]["start"] else "incoming"
                duration_key = "outDuration" if side == "outgoing" else "inDuration"
                reversed_expected = side == "incoming" and bool(value["reverseIncoming"])
                state = semantic_by_target[target["id"]]
                start_key = "outStartSpeed" if side == "outgoing" else "inStartSpeed"
                end_key = "outEndSpeed" if side == "outgoing" else "inEndSpeed"
                _validate_speed_ramp_state(
                    state, target, role=side,
                    ramp_frames=int(value[duration_key]["value"]["value"]),
                    start_speed=float(value[start_key]), end_speed=float(value[end_key]),
                    curve=value["curve"], reversed_expected=reversed_expected,
                    curve_control=(curve_control or {}).get(side),
                    exact_points=exact_points_by_target[target["id"]],
                )

    def _validate_allowed_delta(self, value, before, after):
        if self.action_id == _EFFECT:
            before_rows = before.get("value", {}).get("compositions") if isinstance(before, Mapping) else None
            after_rows = after.get("value", {}).get("compositions") if isinstance(after, Mapping) else None
            if not isinstance(before_rows, list) or not isinstance(after_rows, list):
                raise ValidationError("Professional effect composition delta is unavailable.")
            stable = lambda row: {key: row.get(key) for key in ("id", "index", "name", "graphDigest")}
            before_by_id = {row["id"]: stable(row) for row in before_rows}
            after_by_id = {row["id"]: stable(row) for row in after_rows}
            if not set(before_by_id).issubset(after_by_id):
                raise ValidationError("Professional effect removed an existing Fusion composition.")
            changed = [identity for identity, row in before_by_id.items() if after_by_id[identity] != row]
            created = set(after_by_id) - set(before_by_id)
            if len(changed) + len(created) != 1:
                raise ValidationError("Professional effect changed more than one Fusion composition.")
            return
        if self.action_id in _RETIME:
            return
        if not isinstance(before, Mapping) or before.get("kind") != after.get("kind"):
            raise ValidationError("Professional protected action state is unavailable.")
        before_value = before.get("value")
        after_value = after.get("value")
        if self.action_id.endswith(".transform"):
            if not isinstance(before_value, Mapping) or not isinstance(after_value, Mapping):
                raise ValidationError("Professional transform protected state is unavailable.")
            requested = {_TRANSFORM_PROPERTIES[key] for key in value["transform"]}
            stable_before = {key: item for key, item in before_value.items() if key not in requested}
            stable_after = {key: item for key, item in after_value.items() if key not in requested}
            if stable_before != stable_after:
                raise ValidationError("Professional transform changed a nonrequested property.")
            return
        if not isinstance(before_value, Mapping) or not isinstance(after_value, Mapping):
            raise ValidationError("Professional keyframe protected state is unavailable.")
        before_rows = before_value.get("keyframes")
        after_rows = after_value.get("keyframes")
        if not isinstance(before_rows, list) or not isinstance(after_rows, list):
            raise ValidationError("Professional keyframe protected rows are unavailable.")
        if self.action_id.endswith(".get"):
            if before_rows != after_rows or before_value.get("curve") != after_value.get("curve"):
                raise ValidationError("Professional keyframe read changed live keyframes.")
            return
        frame = value.get("recordFrame")
        stable_before = [row for row in before_rows if not isinstance(row, Mapping) or row.get("frame") != frame]
        stable_after = [row for row in after_rows if not isinstance(row, Mapping) or row.get("frame") != frame]
        if stable_before != stable_after:
            raise ValidationError("Professional keyframe mutation changed nonrequested keyframes.")

    def read_evidence(self, _context, prepared, result):
        snapshot = result.get("afterSnapshot") if isinstance(result, Mapping) else None
        if not isinstance(snapshot, Mapping):
            raise ValidationError("Professional handler lacks fresh terminal readback.")
        value = prepared.get("lowering", {}).get("normalizedInput")
        if not isinstance(value, Mapping):
            raise ValidationError("Professional verification lost its normalized input.")
        target_ids = {row["id"] for row in _timeline_targets(value)}
        expected_protected = prepared.get("domain", {}).get("protectedState", {}).get("timelineDigest")
        observed_protected = _digest(_protected_snapshot(
            snapshot, target_ids, action_id=self.action_id,
            value=prepared["lowering"]["normalizedInput"],
        ))
        if expected_protected != observed_protected:
            raise ValidationError("Professional action changed unrelated timeline state.")
        independent = result.get("independentReadback")
        if not isinstance(independent, Mapping) or independent.get("kind") not in {"keyframes", "transform", "retime", "effect"}:
            raise ValidationError("Professional action lacks independent action-specific readback.")
        self._validate_independent_readback(prepared["lowering"]["normalizedInput"], independent)
        self._validate_allowed_delta(
            prepared["lowering"]["normalizedInput"],
            result.get("beforeIndependentReadback"), independent,
        )
        evidence = [
            {"modality": "readback", "digest": _digest(independent), "summary": "Fresh action-specific readback completed."},
            {"modality": "structural", "digest": _digest({"snapshot": snapshot, "readback": independent}), "summary": "Exact target identity and action-specific state matched."},
        ]
        if self.action_id == _EFFECT:
            rendered = independent.get("rendered")
            after = rendered.get("after") if isinstance(rendered, Mapping) else None
            digest = after.get("sha256") if isinstance(after, Mapping) else None
            if not isinstance(digest, str) or re.fullmatch(r"[a-f0-9]{64}", digest) is None:
                raise ValidationError("Professional effect rendered proof digest is malformed.")
            evidence.append({"modality": "rendered", "digest": f"sha256:{digest}", "summary": "Rendered effect proof matched."})
        return {"outcome": "passed", "evidence": evidence, "protectedStatePreserved": True}

    def recover(self, _context, _prepared, _failure):
        if self.action_id.endswith("keyframe.get"):
            return {"outcome": "not_applicable", "attempted": False, "manualActionRequired": False}
        return {"outcome": "manual_required", "attempted": True, "manualActionRequired": True}

    def project_result(self, _context, prepared, result):
        raw = result.get("raw") if isinstance(result, Mapping) else None
        snapshot = result.get("afterSnapshot") if isinstance(result, Mapping) else None
        value = prepared.get("lowering", {}).get("normalizedInput")
        if not isinstance(value, Mapping):
            raise ValidationError("Professional result projection lost its normalized input.")
        revision = snapshot.get("revision") if isinstance(snapshot, Mapping) else None
        if self.action_id == _EFFECT:
            payload = raw.get("data", raw) if isinstance(raw, Mapping) else {}
            effect = payload.get("effect", {})
            target = value["target"]
            project = snapshot.get("project", {})
            timeline = snapshot.get("timeline", {})
            start = timeline.get("startFrame", snapshot.get("start", {}).get("frame", 0))
            projected = {
                "actionId": self.action_id, "status": "completed",
                "target": {
                    "project": {"id": value["projectId"], "name": project.get("name", value["projectId"])},
                    "timeline": {"id": value["timelineId"], "name": timeline.get("name", value["timelineId"]), "startFrame": int(start)},
                },
                "revision": revision,
                "affected": {"linkedAudio": {"requested": "not_applicable", "preserved": True, "changed": False}},
                "details": {
                    "item": {
                        "id": target["id"], "name": target["name"],
                        "track": {"type": "video", "index": target["trackIndex"]},
                        "recordRange": {"startOffsetFrames": target["recordStartFrame"] - int(start), "durationFrames": target["recordEndFrame"] - target["recordStartFrame"]},
                        "sourceRange": None,
                    },
                    "effect": {"id": effect.get("id"), "name": effect.get("display_name"), "instanceId": None},
                    "parameterCount": len(payload.get("parameters", {})), "renderedProofVerified": True,
                },
                "verification": {
                    "outcome": "passed", "protectedState": "preserved",
                    "evidence": [{"kind": "structural_readback", "summary": "Fresh Fusion composition readback matched the exact target."}, {"kind": "rendered_frame", "summary": "DaVinci Resolve rendered proof confirmed the effect changed pixels."}],
                    "checks": [{"name": "exact_target", "passed": True}, {"name": "rendered_effect", "passed": True}],
                },
                "recovery": {"state": "not_needed", "retry": "same_idempotency_key_required", "manualRecoveryRequired": False, "guidance": "Retain the operation identity before retrying this mutation."},
            }
        elif self.action_id.startswith("cutagent.action.clip.keyframe."):
            data = raw.get("data", raw) if isinstance(raw, Mapping) else {}
            keyframes = data.get("keyframes", data.get("rows", []))
            projected = {
                "actionId": self.action_id, "targetId": value["target"]["id"],
                "timelineRevision": revision, "protectedStatePreserved": True,
                "property": value["property"],
                "keyframes": _project_keyframe_rows(value["property"], keyframes),
            }
            if value["property"] == "RetimeFrame":
                curve = data.get("curve")
                independent = result.get("independentReadback", {}).get("value", {}).get("curve")
                if not isinstance(curve, Mapping) or curve != independent:
                    raise ValidationError("Exact retime readback changed between independent reads.")
                projected["curve"] = {**deepcopy(curve), "timelineItemId": value["target"]["id"]}
        elif self.action_id.endswith(".transform"):
            projected = {
                "actionId": self.action_id, "targetId": value["target"]["id"],
                "timelineRevision": revision, "protectedStatePreserved": True,
                "before": {"values": _project_transform_values(result.get("beforeIndependentReadback"))},
                "after": {"values": _project_transform_values(result.get("independentReadback"))},
            }
        else:
            projected = _retime_projection(self.action_id, value, raw, snapshot)
        return projected

    def validate_result(self, value):
        return isinstance(value, Mapping) \
            and value.get("actionId") == self.action_id \
            and set(value) == _RESULT_DEFINITIONS[self.action_id].expected_result_fields(value)


def professional_primitive_production_owners():
    owners = {action_id: ProfessionalPrimitiveCliOwner(action_id) for action_id in REVIEWED_CLIP_PRIMITIVE_ACTION_IDS}
    if set(owners) != set(_HANDLERS):
        raise RuntimeError("Professional production owners must close exactly ten native-video routes.")
    return MappingProxyType(owners)
