"""Verified insert and checkpoint-backed overwrite operations.

The public time contract is half-open: source and record ranges are ``[start, end)``.
DaVinci Resolve execution remains native ``MediaPool.AppendToTimeline`` plus
``Timeline.DeleteClips``; this module owns the surrounding selection, preflight,
verification, and recovery contract.
"""

from __future__ import annotations

from collections import Counter
import hashlib
import json
import math
import re
import sqlite3
import struct
import time
from collections.abc import Mapping
from typing import Any, Iterable, Optional

import zstandard as zstd

from .audio_source_extent import audio_file_duration as _audio_file_duration

from ..connection import ResolveConnection
from ..errors import (
    AmbiguousMediaPoolItem,
    APICallFailed,
    ClipNotFound,
    EditMutationFailedBeforeChange,
    EditMutationPartiallyApplied,
    EditMutationRecoveryFailed,
    EditMutationRestored,
    InvalidTimeReference,
    ReadinessFailed,
    TimelineConflict,
    ValidationError,
)
from ..output import set_recoverability, set_verification_status
from ..utils.time_ref import parse_record_frame, parse_source_frame
from . import fairlight_channel_map_db, version_ops
from .sdk_live_inspection import documented_unique_id
from .timeline_source_range import trusted_timeline_item_source_range


_TRACK_TYPES = ("video", "audio", "subtitle")
_TRANSITION_METHODS = ("GetTransitions", "GetTransitionList", "GetTransitionItems")
_CHECKPOINT_SESSION_PREFIX = "edit-insert-overwrite"
_OVERWRITE_REQUEST_FIELDS = frozenset(
    {
        "clip_name",
        "position",
        "source_in",
        "source_out",
        "track_index",
        "media_id",
        "audio_track_index",
        "include_linked_audio",
    }
)


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {str(key): _json_value(nested) for key, nested in sorted(value.items(), key=lambda row: str(row[0]))}
    if isinstance(value, (list, tuple, set)):
        return [_json_value(nested) for nested in value]
    return str(value)


def _digest(value: Any) -> str:
    encoded = json.dumps(_json_value(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _call(target: Any, method_name: str, *args: Any, default: Any = None) -> Any:
    method = getattr(target, method_name, None)
    if not callable(method):
        return default
    try:
        return method(*args)
    except Exception:
        return default


def _required_text(value: Any, *, label: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValidationError(f"{label} must not be empty.", details={"field": label})
    return normalized


def _positive_track(value: Any, *, label: str) -> int:
    try:
        normalized = int(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{label} must be a one-based track index.", details={"field": label, "value": value}) from exc
    if normalized < 1:
        raise ValidationError(f"{label} must be a one-based track index.", details={"field": label, "value": value})
    return normalized


def _native_id(value: Any, methods: Iterable[str]) -> str | None:
    for method_name in methods:
        candidate = _call(value, method_name)
        if isinstance(candidate, str) and candidate and candidate == candidate.strip() and not any(
            ord(character) < 32 or ord(character) == 127 for character in candidate
        ):
            return candidate
    return None


def _media_id(item: Any) -> str | None:
    return _native_id(item, ("GetMediaId", "GetUniqueId"))


def _timeline_item_id(item: Any) -> str | None:
    return _native_id(item, ("GetUniqueId",))


def _current_identity(conn: Any) -> dict[str, str]:
    project = getattr(conn, "project", None)
    timeline = getattr(conn, "timeline", None)
    if project is None or timeline is None:
        raise ReadinessFailed("A current DaVinci Resolve project and timeline are required.")
    project_id = documented_unique_id(project)
    timeline_id = documented_unique_id(timeline)
    project_name = _call(project, "GetName")
    timeline_name = _call(timeline, "GetName")
    if not project_id or not timeline_id or not isinstance(project_name, str) or not isinstance(timeline_name, str):
        raise ReadinessFailed(
            "DaVinci Resolve did not expose authoritative project and timeline identity for this mutation.",
            details={"reason": "authoritative_identity_unavailable"},
        )
    current_timeline = _call(project, "GetCurrentTimeline")
    if current_timeline is None:
        raise ReadinessFailed(
            "DaVinci Resolve did not expose the active timeline required for this mutation.",
            details={"reason": "active_timeline_identity_unavailable"},
        )
    if documented_unique_id(current_timeline) != timeline_id:
        raise TimelineConflict(
            "The active DaVinci Resolve timeline changed during mutation preflight.",
            details={"reason": "active_timeline_changed"},
        )
    return {
        "project_id": project_id,
        "project_name": project_name,
        "timeline_id": timeline_id,
        "timeline_name": timeline_name,
    }


def _assert_expected_identity(
    identity: dict[str, str],
    *,
    expected_project_id: str | None,
    expected_timeline_id: str | None,
) -> None:
    expected = {
        "project_id": str(expected_project_id).strip() if expected_project_id else None,
        "timeline_id": str(expected_timeline_id).strip() if expected_timeline_id else None,
    }
    conflicts = {
        field: {"expected": value, "actual": identity[field]}
        for field, value in expected.items()
        if value is not None and value != identity[field]
    }
    if conflicts:
        raise TimelineConflict(
            "The requested DaVinci Resolve project or timeline identity is stale.",
            details={"reason": "identity_precondition_failed", "conflicts": conflicts},
        )


def _walk_media_pool(folder: Any, path: tuple[str, ...] = ()) -> list[tuple[Any, tuple[str, ...]]]:
    folder_name = _call(folder, "GetName")
    current_path = (*path, folder_name) if isinstance(folder_name, str) and folder_name.strip() else path
    rows = [(item, current_path) for item in (_call(folder, "GetClipList", default=[]) or [])]
    for child in _call(folder, "GetSubFolderList", default=[]) or []:
        rows.extend(_walk_media_pool(child, current_path))
    return rows


def _resolve_media_pool_item(
    conn: Any,
    *,
    clip_name: str,
    requested_media_id: str | None,
    all_items: list[tuple[Any, tuple[str, ...]]] | None = None,
) -> dict[str, Any]:
    root = _call(getattr(conn, "media_pool", None), "GetRootFolder")
    if root is None:
        raise ReadinessFailed("DaVinci Resolve Media Pool is unavailable.")
    normalized_name = _required_text(clip_name, label="clip name")
    normalized_media_id = str(requested_media_id or "").strip() or None
    all_items = all_items if all_items is not None else _walk_media_pool(root)
    if normalized_media_id:
        matches = [(item, path) for item, path in all_items if _media_id(item) == normalized_media_id]
        if len(matches) == 1 and str(_call(matches[0][0], "GetName") or "") != normalized_name:
            raise TimelineConflict(
                "The requested Media Pool identity no longer has the expected name.",
                details={
                    "reason": "media_identity_name_changed",
                    "expected_name": normalized_name,
                    "actual_name": str(_call(matches[0][0], "GetName") or ""),
                    "media_id": normalized_media_id,
                },
            )
    else:
        matches = [(item, path) for item, path in all_items if str(_call(item, "GetName") or "") == normalized_name]
    if not matches:
        raise ClipNotFound(
            f"Media Pool item '{normalized_name}' not found.",
            details={"clip_name": normalized_name, "media_id": normalized_media_id},
        )
    if len(matches) != 1:
        raise AmbiguousMediaPoolItem(
            "Media Pool item selector matched multiple candidates.",
            details={
                "clip_name": normalized_name,
                "media_id": normalized_media_id,
                "match_count": len(matches),
                "candidates": [
                    {
                        "name": str(_call(item, "GetName") or ""),
                        "media_id": _media_id(item),
                        "bin": "/".join(path) or "/",
                    }
                    for item, path in matches
                ],
            },
        )
    item, path = matches[0]
    actual_media_id = _media_id(item)
    if actual_media_id is None:
        raise ReadinessFailed(
            "DaVinci Resolve did not expose an authoritative identity for the selected Media Pool item.",
            details={"reason": "media_identity_unavailable", "clip_name": normalized_name},
        )
    return {
        "item": item,
        "name": normalized_name,
        "media_id": actual_media_id,
        "bin": "/".join(path) or "/",
        "selector": "media_id" if normalized_media_id else "unique_name",
    }


def _clip_properties(item: Any) -> dict[str, Any]:
    value = _call(item, "GetClipProperty", default={})
    return value if isinstance(value, dict) else {}


def _parse_number(value: Any) -> float | None:
    if value is None:
        return None
    match = re.search(r"-?\d+(?:[.,]\d+)?", str(value))
    if not match:
        return None
    try:
        return float(match.group(0).replace(",", "."))
    except ValueError:
        return None


def _source_fps(item: Any, fallback: float) -> float:
    props = _clip_properties(item)
    for key in ("FPS", "Frame Rate", "Video Frame Rate", "Clip Frame Rate", "MediaFrameRate"):
        parsed = _parse_number(props.get(key))
        if parsed and parsed > 0:
            return parsed
    return float(fallback)


def _audio_file_total_frames(audio_file_duration: tuple[int, int], source_fps: float) -> int:
    sample_count, sample_rate = audio_file_duration
    return int(sample_count * float(source_fps) / sample_rate)


def _source_total_frames(
    item: Any,
    source_fps: float,
    *,
    audio_file_duration: tuple[int, int] | None = None,
) -> int:
    props = _clip_properties(item)
    if audio_file_duration is not None:
        return _audio_file_total_frames(audio_file_duration, source_fps)
    for key in ("Frames", "DurationFrames", "SourceFrames"):
        parsed = _parse_number(props.get(key))
        if parsed is not None and parsed >= 0:
            return int(parsed)
    duration = props.get("Duration")
    if isinstance(duration, str) and duration.strip():
        return int(_parse_exact_source_frame(duration.strip(), source_fps))
    raise InvalidTimeReference(
        "Source duration is unavailable; an exact half-open source range cannot be planned.",
        details={"reason": "source_duration_unavailable"},
    )


def _fractional_fps(fps: float) -> bool:
    return abs(float(fps) - round(float(fps))) > 0.000001


def _reject_ambiguous_fractional_timecode(raw: str, fps: float, *, domain: str) -> None:
    value = str(raw or "").strip()
    if _fractional_fps(fps) and (":" in value or ";" in value):
        raise InvalidTimeReference(
            "Fractional-rate timecodes require an explicit frame reference for exact placement.",
            details={
                "reason": "fractional_timecode_requires_frames",
                "domain": domain,
                "raw": value,
                "fps": float(fps),
                "accepted_examples": ["18000f", "18000"],
            },
        )


def _parse_exact_source_frame(raw: str, fps: float) -> int:
    _reject_ambiguous_fractional_timecode(raw, fps, domain="source")
    return int(parse_source_frame(raw, fps))


def _parse_exact_record_frame(raw: str, fps: float, start_frame: int) -> int:
    _reject_ambiguous_fractional_timecode(raw, fps, domain="record")
    return int(parse_record_frame(raw, fps, start_frame))


def _audio_mapping_payload(item: Any) -> tuple[bool, dict[str, Any] | list[Any] | None]:
    method = getattr(item, "GetAudioMapping", None)
    if not callable(method):
        return False, None
    try:
        raw = method()
    except Exception:
        return True, None
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (TypeError, ValueError):
            return True, None
    return True, raw if isinstance(raw, (dict, list)) else None


def _mapping_source_tracks(value: Any) -> set[int]:
    tracks: set[int] = set()
    if isinstance(value, dict):
        for key, candidate in value.items():
            if str(key).casefold() in {"track_mapping", "trackmapping"} and isinstance(candidate, dict):
                for track_key in candidate:
                    parsed_track = _parse_number(track_key)
                    if parsed_track is not None:
                        tracks.add(int(parsed_track))
            if str(key).casefold() in {"source_track", "source_track_index", "sourcetrack", "sourcetrackindex"}:
                parsed = _parse_number(candidate)
                if parsed is not None:
                    tracks.add(int(parsed))
            tracks.update(_mapping_source_tracks(candidate))
    elif isinstance(value, list):
        for candidate in value:
            tracks.update(_mapping_source_tracks(candidate))
    return tracks


def _mapping_has_muted_track(value: Any) -> bool:
    if isinstance(value, dict):
        for key, candidate in value.items():
            if str(key).casefold() in {"mute", "muted"} and candidate in (True, 1, "1", "true", "True"):
                return True
            if _mapping_has_muted_track(candidate):
                return True
    elif isinstance(value, list):
        return any(_mapping_has_muted_track(candidate) for candidate in value)
    return False


def _source_streams(item: Any) -> tuple[bool, bool | None]:
    props = _clip_properties(item)
    type_text = " ".join(str(props.get(key) or "") for key in ("Type", "Clip Type", "Video Codec", "Resolution")).casefold()
    has_video = bool(props.get("Resolution") or props.get("Video Codec") or "video" in type_text)
    mapping_available, mapping = _audio_mapping_payload(item)
    if mapping is not None:
        source_tracks = _mapping_source_tracks(mapping)
        if len(source_tracks) > 1 or any(track > 1 for track in source_tracks) or _mapping_has_muted_track(mapping):
            raise ValidationError(
                "Selected media exposes a source-audio layout that this placement route cannot address exactly.",
                details={
                    "reason": "source_audio_layout_unsupported",
                    "source_tracks": sorted(source_tracks),
                    "muted_track": _mapping_has_muted_track(mapping),
                },
            )
        if isinstance(mapping, list):
            has_audio = bool(mapping)
        else:
            channel_count = max(
                int(_parse_number(mapping.get(key)) or 0)
                for key in ("embedded_audio_channels", "audio_channels", "channels")
            )
            mapped = mapping.get("audio_mapping") or mapping.get("audioMapping") or mapping.get("mapping")
            linked = mapping.get("linked_audio") or mapping.get("linkedAudio")
            has_audio = bool(channel_count > 0 or mapped or linked)
    elif mapping_available:
        has_audio = None
    else:
        audio_text = " ".join(
            str(props.get(key) or "")
            for key in ("Audio Ch", "Audio Channels", "Audio Codec", "Audio Sample Rate", "Type", "Clip Type")
        ).casefold()
        if any(token in audio_text for token in ("audio", "mono", "stereo", "channel")) or any(
            (_parse_number(props.get(key)) or 0) > 0 for key in ("Audio Ch", "Audio Channels")
        ):
            has_audio = True
        elif any(props.get(key) not in (None, "") for key in ("Audio Ch", "Audio Channels", "Audio Codec")):
            has_audio = False
        else:
            has_audio = None
    return has_video, has_audio


def _convert_frame_count(frames: int, *, from_fps: float, to_fps: float) -> int:
    if frames <= 0:
        return 0
    if abs(from_fps - to_fps) < 0.000001:
        return int(frames)
    return max(1, int((frames * to_fps / from_fps) + 0.5))


def _native_record_duration_frames(
    source_duration: int,
    *,
    source_fps: float,
    timeline_fps: float,
    has_video: bool,
) -> int:
    """Project the record span produced by the native append boundary."""

    if (
        has_video
        and timeline_fps > source_fps
    ):
        # DaVinci Resolve truncates video source spans when it expands them
        # onto a higher-rate Timeline. GetStart(True), GetEnd(True), and
        # GetDuration(True) all report the same integral floor, so preview must
        # model that native boundary instead of promising a rounded frame that
        # execution cannot author. Some fractional media also reports its
        # nominal integer rate through GetClipProperty, so this cannot key only
        # on whether the exposed source rate contains a decimal fraction.
        return max(1, math.floor(source_duration * timeline_fps / source_fps + 1e-9))
    return _convert_frame_count(
        source_duration,
        from_fps=source_fps,
        to_fps=timeline_fps,
    )


def _native_end_extension_for_nearest_record_duration(
    source_duration: int,
    *,
    source_fps: float,
    timeline_fps: float,
) -> int | None:
    if timeline_fps >= source_fps:
        # DaVinci Resolve retains the expanded record subframe duration for
        # equal-rate and up-converted placements; normal record-grid
        # projection already yields the requested nearest frame.
        return 0
    expected = _convert_frame_count(
        source_duration,
        from_fps=source_fps,
        to_fps=timeline_fps,
    )
    native_floor = math.floor(source_duration * timeline_fps / source_fps + 1e-9)
    if native_floor >= expected:
        return 0
    extended_floor = math.floor((source_duration + 1) * timeline_fps / source_fps + 1e-9)
    return 1 if extended_floor == expected else None


def _native_source_frame_exact(frame: int, *, source_fps: float, timeline_fps: float) -> int | float:
    """Return the source boundary expected by ``AppendToTimeline``."""

    requested = int(frame)
    nominal = round(source_fps)
    if nominal > 0 and not math.isclose(source_fps, nominal, abs_tol=1e-6):
        # Media Pool source boundaries are already expressed in the source
        # item's frame domain. Scaling them into a nominal integer timebase
        # makes AppendToTimeline reject otherwise valid fractional-rate ranges.
        return requested
    # Integer-rate source boundaries are already expressed in the source
    # timebase accepted by AppendToTimeline. DaVinci Resolve may quantize
    # GetSourceStartFrame() by one frame after placing that source on a
    # different-rate timeline; compensating the write for that readback moves
    # the rendered source frame and is therefore incorrect.
    return requested


def _source_range(
    item: Any,
    *,
    source_in: str | None,
    source_out: str | None,
    timeline_fps: float,
    audio_only: bool = False,
) -> dict[str, Any]:
    source_fps = _source_fps(item, timeline_fps)
    audio_file_duration = _audio_file_duration(item) if audio_only else None
    total_frames = _source_total_frames(item, source_fps, audio_file_duration=audio_file_duration)
    start = _parse_exact_source_frame(source_in, source_fps) if source_in else 0
    end = _parse_exact_source_frame(source_out, source_fps) if source_out else total_frames
    if start < 0 or end <= start or end > total_frames:
        raise InvalidTimeReference(
            "Source range must be a non-empty half-open range inside the selected media item.",
            details={
                "source_in": source_in,
                "source_out": source_out,
                "start_frame": start,
                "end_frame_exclusive": end,
                "source_total_frames": total_frames,
            },
        )
    _native_source_frame_exact(start, source_fps=source_fps, timeline_fps=timeline_fps)
    _native_source_frame_exact(end, source_fps=source_fps, timeline_fps=timeline_fps)
    duration_source = end - start
    has_video, _has_audio = _source_streams(item)
    duration_record = _native_record_duration_frames(
        duration_source,
        source_fps=source_fps,
        timeline_fps=timeline_fps,
        has_video=has_video,
    )
    native_end_extension = _native_end_extension_for_nearest_record_duration(
        duration_source,
        source_fps=source_fps,
        timeline_fps=timeline_fps,
    )
    if has_video and (
        native_end_extension is None
        or (native_end_extension == 1 and end >= total_frames)
    ):
        raise InvalidTimeReference(
            "The exact source range cannot produce the requested nearest-frame record duration through the native placement API.",
            details={
                "reason": "nearest_record_duration_unrepresentable",
                "source_start_frame": start,
                "source_end_frame_exclusive": end,
                "source_total_frames": total_frames,
                "source_fps": source_fps,
                "timeline_fps": timeline_fps,
                "record_duration_frames": duration_record,
            },
        )
    return {
        "start_frame": start,
        "end_frame_exclusive": end,
        "duration_frames": duration_source,
        "record_duration_frames": duration_record,
        "source_fps": source_fps,
        "timeline_fps": timeline_fps,
        "conversion": "nearest_record_frame",
    }


def _track_state(timeline: Any, track_type: str, track_index: int) -> dict[str, Any]:
    return {
        "track_type": track_type,
        "track_index": track_index,
        "name": _call(timeline, "GetTrackName", track_type, track_index),
        "enabled": _call(timeline, "GetIsTrackEnabled", track_type, track_index),
        "locked": _call(timeline, "GetIsTrackLocked", track_type, track_index),
    }


def _validate_target_track(timeline: Any, track_type: str, track_index: int) -> dict[str, Any]:
    count = int(_call(timeline, "GetTrackCount", track_type, default=0) or 0)
    if track_index > count:
        raise ValidationError(
            "Target track does not exist.",
            details={"track_type": track_type, "track_index": track_index, "track_count": count},
        )
    state = _track_state(timeline, track_type, track_index)
    if state["locked"] is not False or state["enabled"] is not True:
        raise TimelineConflict(
            "Target track must be enabled and unlocked before mutation.",
            details={"reason": "target_track_not_writable", "track": state},
        )
    return state


def _linked_item_ids(item: Any) -> list[str] | None:
    method = getattr(item, "GetLinkedItems", None)
    if not callable(method):
        return None
    try:
        raw = method()
    except Exception:
        return None
    if raw is False or raw is None:
        return None
    values = list(raw.values()) if isinstance(raw, dict) else list(raw) if isinstance(raw, (list, tuple)) else []
    return sorted(filter(None, (_timeline_item_id(candidate) for candidate in values)))


def _first_int_call(item: Any, method_names: tuple[str, ...]) -> int | None:
    for method_name in method_names:
        method = getattr(item, method_name, None)
        if not callable(method):
            continue
        try:
            value = method()
        except Exception:
            continue
        if isinstance(value, (int, float)):
            return int(value)
    return None


_EDGE_PROPERTY_DEFAULTS: dict[str, tuple[Any, ...]] = {
    "ZoomX": (1, 1.0, "1", "1.0"),
    "ZoomY": (1, 1.0, "1", "1.0"),
    "ZoomGang": (True, 1, "1", "true", "True"),
    "Pan": (0, 0.0, "0", "0.0"),
    "Tilt": (0, 0.0, "0", "0.0"),
    "RotationAngle": (0, 0.0, "0", "0.0"),
    "AnchorPointX": (0, 0.0, "0", "0.0"),
    "AnchorPointY": (0, 0.0, "0", "0.0"),
    "Pitch": (0, 0.0, "0", "0.0"),
    "Yaw": (0, 0.0, "0", "0.0"),
    "FlipX": (False, 0, "0", "false", "False"),
    "FlipY": (False, 0, "0", "false", "False"),
    "CropLeft": (0, 0.0, "0", "0.0"),
    "CropRight": (0, 0.0, "0", "0.0"),
    "CropTop": (0, 0.0, "0", "0.0"),
    "CropBottom": (0, 0.0, "0", "0.0"),
    "CropSoftness": (0, 0.0, "0", "0.0"),
    "CropRetain": (False, 0, "0", "false", "False"),
    "Opacity": (100, 100.0, "100", "100.0"),
    "CompositeMode": (0, "0", "Normal", "normal"),
    "Distortion": (0, 0.0, "0", "0.0"),
    "DynamicZoomEase": (0, "0", "Linear", "linear"),
    "RetimeProcess": (0, "0"),
    "MotionEstimation": (0, "0"),
    "Scaling": (0, "0"),
    "ResizeFilter": (0, "0"),
}


def _edge_property_state(item: Any, properties: dict[str, Any], *, track_type: str) -> dict[str, Any]:
    if track_type != "video":
        return {}
    values: dict[str, Any] = {}
    for key in _EDGE_PROPERTY_DEFAULTS:
        value = properties.get(key)
        if value is None:
            value = _call(item, "GetProperty", key)
        values[key] = value
    return values


def _item_row(
    item: Any,
    *,
    track_type: str,
    track_index: int,
    timeline_fps: float,
    ordinary_mapping_proven: bool = False,
    connection: Any | None = None,
) -> dict[str, Any]:
    from .timeline_record_geometry import timeline_record_geometry

    geometry = timeline_record_geometry(item)
    start, end = geometry["start"], geometry["end"]
    mpi = _call(item, "GetMediaPoolItem")
    source_range = trusted_timeline_item_source_range(
        item,
        timeline_fps,
        ordinary_mapping_proven=ordinary_mapping_proven,
        audio_only=track_type == "audio",
        connection=connection,
    )
    properties = _call(item, "GetProperty", default={})
    properties = properties if isinstance(properties, dict) else {}
    source_range_conflict = source_range["conflict"]
    source_start = source_range["start"]
    source_end = source_range["end_exclusive"]
    markers = _call(item, "GetMarkers", default={})
    flags = _call(item, "GetFlagList", default=[])
    state = {
        "record_subframes": geometry["record_subframes"],
        "properties": properties,
        "edge_properties": _edge_property_state(item, properties, track_type=track_type),
        "authoritative_source_range": source_range["authoritative"],
        "source_range_readback_conflict": source_range_conflict,
    }
    source_range_readback = {
        "selected": source_range["selected"],
        "native_source_start_frame": source_range["native_start"],
        "native_source_end_frame_exclusive": source_range["native_end_exclusive"],
        "offset_source_start_frame": source_range["offset_start"],
        "offset_source_end_frame_exclusive": source_range["offset_end_exclusive"],
        "conflict": source_range_conflict,
    }
    state.update(
        {
            "markers": markers if isinstance(markers, dict) else {},
            "flags": flags if isinstance(flags, (list, tuple)) else [],
            "enabled": _call(item, "GetClipEnabled"),
            "color": _call(item, "GetClipColor"),
            "fusion_comp_count": _call(item, "GetFusionCompCount"),
            "take_count": _call(item, "GetTakesCount"),
        }
    )
    row = {
        "item_id": _timeline_item_id(item),
        "media_id": _media_id(mpi) if mpi is not None else None,
        "name": str(_call(item, "GetName") or ""),
        "track_type": track_type,
        "track_index": track_index,
        "record_start_frame": start,
        "record_end_frame_exclusive": end,
        "duration_frames": max(0, end - start),
        "source_start_frame": source_start,
        "source_end_frame_exclusive": source_end,
        "linked_item_ids": _linked_item_ids(item),
        "state_digest": _digest({key: value for key, value in state.items() if key != "record_subframes"}),
        "record_geometry_digest": _digest(geometry["record_subframes"]),
        "_state": state,
        "_source_range_readback": source_range_readback,
        "_item": item,
        "_media_item": mpi,
    }
    row["_key"] = row["item_id"] or _digest({key: value for key, value in row.items() if not key.startswith("_")})
    return row


def _api_transition_snapshot(timeline: Any) -> list[dict[str, Any]] | None:
    for method_name in _TRANSITION_METHODS:
        method = getattr(timeline, method_name, None)
        if not callable(method):
            continue
        try:
            raw = method()
        except Exception:
            continue
        if raw is False or raw is None:
            continue
        values = list(raw.values()) if isinstance(raw, dict) else list(raw) if isinstance(raw, (list, tuple)) else []
        return [
            {
                "transition_id": _timeline_item_id(item),
                "name": str(_call(item, "GetName") or ""),
                "record_start_frame": int(_call(item, "GetStart", default=0) or 0),
                "record_end_frame_exclusive": int(_call(item, "GetEnd", default=0) or 0),
                "track_type": str(_call(item, "GetTrackType") or "unknown"),
                "track_index": int(_call(item, "GetTrackIndex", default=0) or 0),
            }
            for item in values
        ]
    return None


def _db_track_ids(cursor: sqlite3.Cursor, *, timeline_name: str, track_type: str, track_index: int) -> list[str]:
    property_name = {"video": "VideoTrackVec", "audio": "AudioTrackVec"}[track_type]
    rows = cursor.execute(
        """
        SELECT tr.Sm2TiTrack_id
        FROM Sm2Timeline tl
        JOIN Sm2SequenceContainer sc ON sc.Sm2Sequence_id = tl.Sequence
        JOIN Sm2SequenceContainer_Sm2TiTrack rel
          ON rel.DbOwner = sc.Sm2SequenceContainer_id
         AND rel.DbPropertyName = ? AND rel.DbIndex = ?
        JOIN Sm2TiTrack tr ON tr.Sm2TiTrack_id = rel.DbAssociate
        WHERE tl.Name = ?
        """,
        (property_name, track_index - 1, timeline_name),
    ).fetchall()
    return [str(row[0]) for row in rows]


def _db_transition_snapshot(conn: Any, identity: dict[str, str]) -> list[dict[str, Any]]:
    try:
        # The official scripting API does not expose Project.db. Resolve the
        # current local Disk project through the established exact-name
        # inference path used by the other read-only DB validators.
        db_path = conn.disk_db_path(allow_project_name_inference=True)
        database = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        database.row_factory = sqlite3.Row
        try:
            rows: list[dict[str, Any]] = []
            cursor = database.cursor()
            for track_type in ("video", "audio"):
                count = int(_call(conn.timeline, "GetTrackCount", track_type, default=0) or 0)
                for track_index in range(1, count + 1):
                    track_ids = _db_track_ids(
                        cursor,
                        timeline_name=identity["timeline_name"],
                        track_type=track_type,
                        track_index=track_index,
                    )
                    if len(track_ids) != 1:
                        raise RuntimeError("timeline track identity is not unique")
                    db_rows = cursor.execute(
                        """
                        SELECT item.Sm2TiItem_id, item.Name, item.Start, item.Duration
                        FROM Sm2TiItem item
                        JOIN Sm2TiItem_Sm2TiTrack rel ON rel.DbAssociate = item.Sm2TiItem_id
                        WHERE rel.DbOwner = ? AND rel.DbPropertyName = 'Items'
                          AND item.DbType = 'Sm2TiTransition'
                        ORDER BY CAST(COALESCE(item.Start, '0') AS INTEGER), item.Sm2TiItem_id
                        """,
                        (track_ids[0],),
                    ).fetchall()
                    for row in db_rows:
                        start = int(str(row["Start"] or "0").split("|", 1)[0])
                        duration = int(str(row["Duration"] or "0").split("|", 1)[0])
                        rows.append(
                            {
                                "transition_id": str(row["Sm2TiItem_id"] or ""),
                                "name": str(row["Name"] or ""),
                                "record_start_frame": start,
                                "record_end_frame_exclusive": start + max(0, duration),
                                "track_type": track_type,
                                "track_index": track_index,
                            }
                        )
            return rows
        finally:
            database.close()
    except Exception as exc:
        raise ReadinessFailed(
            "CutAgent could not inspect transition state for verified insert or overwrite.",
            details={"reason": "transition_state_unavailable", "error_type": exc.__class__.__name__},
        ) from exc


def _snapshot(conn: Any) -> dict[str, Any]:
    identity = _current_identity(conn)
    timeline = conn.timeline
    tracks: list[dict[str, Any]] = []
    items: list[dict[str, Any]] = []
    for track_type in _TRACK_TYPES:
        count = int(_call(timeline, "GetTrackCount", track_type, default=0) or 0)
        for track_index in range(1, count + 1):
            state = _track_state(timeline, track_type, track_index)
            if not isinstance(state["enabled"], bool) or not isinstance(state["locked"], bool):
                raise ReadinessFailed(
                    "DaVinci Resolve did not expose authoritative enabled and locked state for every timeline track.",
                    details={
                        "reason": "track_state_unavailable",
                        "track_type": track_type,
                        "track_index": track_index,
                    },
                )
            tracks.append(state)
            for item in _call(timeline, "GetItemListInTrack", track_type, track_index, default=[]) or []:
                row = _item_row(
                    item,
                    track_type=track_type,
                    track_index=track_index,
                    timeline_fps=float(conn.fps),
                    connection=conn,
                )
                if row["_source_range_readback"]["conflict"] or (
                    track_type == "audio" and not row["_state"]["authoritative_source_range"]
                ):
                    from .timeline_source_range import ordinary_source_mapping_proven

                    if ordinary_source_mapping_proven(conn, item):
                        row = _item_row(
                            item,
                            track_type=track_type,
                            track_index=track_index,
                            timeline_fps=float(conn.fps),
                            ordinary_mapping_proven=True,
                            connection=conn,
                        )
                if row["item_id"] is None:
                    raise ReadinessFailed(
                        "DaVinci Resolve did not expose an authoritative identity for every timeline item.",
                        details={
                            "reason": "timeline_item_identity_unavailable",
                            "track_type": track_type,
                            "track_index": track_index,
                        },
                    )
                if row["linked_item_ids"] is None:
                    raise ReadinessFailed(
                        "DaVinci Resolve did not expose linked-item state for every timeline item.",
                        details={
                            "reason": "linked_state_unavailable",
                            "item_id": row["item_id"],
                            "track_type": track_type,
                            "track_index": track_index,
                        },
                    )
                items.append(row)
    transitions = _api_transition_snapshot(timeline)
    if transitions is None:
        # An empty timeline cannot contain a transition. This gives newly
        # created timelines a fully authoritative API-only preflight while
        # retaining the stricter database readback once timeline items exist.
        transitions = [] if not items else _db_transition_snapshot(conn, identity)
    serial_items = [{key: value for key, value in row.items() if not key.startswith("_")} for row in items]
    revision = _digest(
        {
            "identity": identity,
            "fps": float(conn.fps),
            "start_frame": int(_call(timeline, "GetStartFrame", default=0) or 0),
            "tracks": tracks,
            "items": serial_items,
            "transitions": transitions,
        }
    )
    return {
        "identity": identity,
        "fps": float(conn.fps),
        "tracks": tracks,
        "items": items,
        "transitions": transitions,
        "transition_fingerprint": _digest(transitions),
        "revision": revision,
    }


def _public_item(row: dict[str, Any]) -> dict[str, Any]:
    return {
        key: row.get(key)
        for key in (
            "item_id",
            "media_id",
            "name",
            "track_type",
            "track_index",
            "record_start_frame",
            "record_end_frame_exclusive",
            "duration_frames",
            "source_start_frame",
            "source_end_frame_exclusive",
        )
    }


def _overlaps(row: dict[str, Any], start: int, end: int) -> bool:
    return int(row["record_start_frame"]) < end and int(row["record_end_frame_exclusive"]) > start


def _transition_conflicts(snapshot: dict[str, Any], *, target_tracks: set[tuple[str, int]], start: int, end: int) -> list[dict[str, Any]]:
    return [
        {
            "name": row.get("name"),
            "track_type": row.get("track_type"),
            "track_index": row.get("track_index"),
            "record_start_frame": row.get("record_start_frame"),
            "record_end_frame_exclusive": row.get("record_end_frame_exclusive"),
        }
        for row in snapshot["transitions"]
        if (row.get("track_type"), int(row.get("track_index") or 0)) in target_tracks
        and int(row.get("record_start_frame") or 0) < end
        and int(row.get("record_end_frame_exclusive") or 0) > start
    ]


def _non_default_edge_properties(state: dict[str, Any]) -> list[str]:
    values = state.get("edge_properties")
    if not isinstance(values, dict):
        return ["property_state_unavailable"]
    unsupported: list[str] = []
    for key, defaults in _EDGE_PROPERTY_DEFAULTS.items():
        value = values.get(key)
        if value is None:
            unsupported.append(f"{key}_unavailable")
        elif value not in defaults:
            unsupported.append(key)
    return unsupported


def _fields_blob_names(blob: bytes | None) -> set[str]:
    if not blob:
        return set()
    payload = bytes(blob)
    try:
        if len(payload) < 9:
            raise ValueError("FieldsBlob is shorter than its packed header")
        version, body_size = struct.unpack(">II", payload[:8])
        body = payload[8:]
        if version != 2 or body_size != len(body):
            raise ValueError("FieldsBlob has an unsupported packed envelope")
        if body.startswith(b"\x80"):
            proto = body[1:]
        elif body.startswith(b"\x81") and len(body) > 1:
            proto = zstd.ZstdDecompressor().decompress(
                body[1:], max_output_size=16 * 1024 * 1024
            )
        else:
            raise ValueError("FieldsBlob has an unsupported payload encoding")
    except Exception as exc:
        raise ReadinessFailed(
            "CutAgent could not decode clip-local Project.db state for a partial overwrite edge.",
            details={"reason": "edge_db_state_undecodable", "error_type": exc.__class__.__name__},
        ) from exc
    return {
        name
        for name in ("FL::ClipFX", "FL::Retimer")
        if name.encode("utf-8") in proto
    }


def _is_default_edge_timemap(value: bytes | None) -> bool:
    if value in (None, b""):
        return True
    blob = bytes(value)
    if len(blob) == 9 and blob[:1] == b"\x02":
        return True
    # DaVinci Resolve 21 also writes an ordinary linear map as five doubles:
    # extent, zero, last-valid extent, zero, extent. Speed ramps and constant
    # retimes use other shapes or unequal outer extents. Keep this recognizer
    # deliberately narrow so unknown encodings fail closed.
    if (
        len(blob) == 41
        and blob[:1] == b"\x02"
        and blob[9:17] == b"\x00" * 8
        and blob[25:33] == b"\x00" * 8
        and blob[1:9] == blob[33:41]
    ):
        extent = struct.unpack(">d", blob[1:9])[0]
        last_valid = struct.unpack(">d", blob[17:25])[0]
        return (
            math.isfinite(extent)
            and math.isfinite(last_valid)
            and extent >= 0.0
            and 0.0 <= last_valid <= extent
            and extent - last_valid <= 1.0
        )
    return False


def _hydrate_edge_db_state(conn: Any, rows: list[dict[str, Any]]) -> None:
    """Attach fail-closed DB evidence for clip state omitted by TimelineItem."""

    if not rows:
        return
    injected = getattr(conn, "_edge_db_state", None)
    if isinstance(injected, dict):
        states = injected
    else:
        try:
            db_path = conn.disk_db_path(allow_project_name_inference=True)
            database = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            database.row_factory = sqlite3.Row
            try:
                columns = {str(column[1]) for column in database.execute("PRAGMA table_info(Sm2TiItem)")}
                required = {
                    "Sm2TiItem_id",
                    "EffectFiltersBA",
                    "FieldsBlob",
                    "MediaTimemapBA",
                    "pLmVerTable",
                    "VirtualAudioTrackBA",
                }
                if not required <= columns:
                    raise RuntimeError("required Sm2TiItem edge-state columns are unavailable")
                states = {}
                for row in rows:
                    db_row = database.execute(
                        "SELECT EffectFiltersBA, FieldsBlob, MediaTimemapBA, pLmVerTable, VirtualAudioTrackBA "
                        "FROM Sm2TiItem WHERE Sm2TiItem_id = ?",
                        (row["item_id"],),
                    ).fetchone()
                    if db_row is None:
                        raise RuntimeError("timeline item is absent from Project.db")
                    audio_channel_mapping_default = True
                    if row["track_type"] == "audio":
                        _mapping_available, mapping = _audio_mapping_payload(row.get("_media_item"))
                        track_mapping = mapping.get("track_mapping") if isinstance(mapping, dict) else None
                        try:
                            expected_virtual_track = fairlight_channel_map_db.canonical_timeline_track_mapping_blob(
                                track_mapping
                            )
                        except Exception:
                            expected_virtual_track = None
                        actual_virtual_track = bytes(db_row["VirtualAudioTrackBA"] or b"")
                        audio_channel_mapping_default = bool(
                            expected_virtual_track is not None
                            and actual_virtual_track == expected_virtual_track
                        )
                    states[row["item_id"]] = {
                        "effect_filters_present": db_row["EffectFiltersBA"] is not None,
                        "fields_blob_names": sorted(_fields_blob_names(db_row["FieldsBlob"])),
                        "non_default_timemap": not _is_default_edge_timemap(db_row["MediaTimemapBA"]),
                        "grade_version_present": bool(db_row["pLmVerTable"]),
                        "audio_channel_mapping_default": audio_channel_mapping_default,
                    }
            finally:
                database.close()
        except ReadinessFailed:
            raise
        except Exception as exc:
            raise ReadinessFailed(
                "CutAgent could not inspect clip-local Project.db state for a partial overwrite edge.",
                details={"reason": "edge_db_state_unavailable", "error_type": exc.__class__.__name__},
            ) from exc
    for row in rows:
        state = states.get(row["item_id"], states.get("*"))
        if not isinstance(state, dict):
            raise ReadinessFailed(
                "CutAgent could not resolve clip-local Project.db state for a partial overwrite edge.",
                details={"reason": "edge_db_item_state_unavailable", "item_id": row["item_id"]},
            )
        unsupported: list[str] = []
        if state.get("effect_filters_present"):
            unsupported.append("clip_effect_filters")
        if state.get("non_default_timemap"):
            unsupported.append("non_default_timemap")
        if state.get("grade_version_present"):
            unsupported.append("local_color_grade")
        if row["track_type"] == "audio" and state.get("audio_channel_mapping_default") is not True:
            unsupported.append("audio_channel_mapping_non_default")
        unsupported.extend(str(name) for name in state.get("fields_blob_names") or [])
        row["_state"]["db_edge_unsupported"] = sorted(set(unsupported))


def _segment_for_record_range(
    row: dict[str, Any],
    *,
    record_start: int,
    record_end: int,
    timeline_fps: float,
) -> dict[str, Any]:
    mpi = row.get("_media_item")
    source_start = row.get("source_start_frame")
    source_end = row.get("source_end_frame_exclusive")
    if mpi is None or source_start is None or source_end is None:
        raise TimelineConflict(
            "Overwrite cannot preserve a partially covered timeline item with unknown source identity or range.",
            details={"reason": "edge_preservation_unsupported", "item": _public_item(row)},
        )
    state = row.get("_state") or {}
    source_span = int(source_end) - int(source_start)
    expected_record_span = _convert_frame_count(
        source_span,
        from_fps=_source_fps(mpi, timeline_fps),
        to_fps=timeline_fps,
    )
    linear_playback_proven = (
        state.get("authoritative_source_range") is True
        and source_span > 0
        and expected_record_span == int(row["duration_frames"])
    )
    unsupported_state = {
        "markers": bool(state.get("markers")),
        "flags": bool(state.get("flags")),
        "disabled": state.get("enabled") is False,
        "clip_color": bool(str(state.get("color") or "").strip()),
        "retimed_or_unproven": not linear_playback_proven,
        "fusion_comp": (_parse_number(state.get("fusion_comp_count")) or 0) > 0,
        "multiple_takes": (_parse_number(state.get("take_count")) or 0) > 1,
    }
    active_unsupported_state = sorted(key for key, active in unsupported_state.items() if active)
    if row["track_type"] == "video":
        active_unsupported_state.extend(_non_default_edge_properties(state))
    active_unsupported_state.extend(state.get("db_edge_unsupported") or [])
    active_unsupported_state = sorted(set(active_unsupported_state))
    if active_unsupported_state:
        raise TimelineConflict(
            "Overwrite cannot reconstruct a partially covered timeline item with unsupported clip-local state.",
            details={
                "reason": "edge_state_preservation_unsupported",
                "item": _public_item(row),
                "unsupported_state": active_unsupported_state,
            },
        )
    media_fps = _source_fps(mpi, timeline_fps)
    item_record_start = int(row["record_start_frame"])
    item_record_end = int(row["record_end_frame_exclusive"])
    if record_start == item_record_start:
        source_segment_start = int(source_start)
        source_segment_end = source_segment_start + _convert_frame_count(
            record_end - record_start, from_fps=timeline_fps, to_fps=media_fps
        )
    elif record_end == item_record_end:
        source_segment_end = int(source_end)
        source_segment_start = source_segment_end - _convert_frame_count(
            record_end - record_start, from_fps=timeline_fps, to_fps=media_fps
        )
    else:
        source_segment_start = int(source_start) + _convert_frame_count(
            record_start - item_record_start,
            from_fps=timeline_fps,
            to_fps=media_fps,
        )
        source_segment_end = int(source_start) + _convert_frame_count(
            record_end - item_record_start,
            from_fps=timeline_fps,
            to_fps=media_fps,
        )
    return {
        "side": "head" if record_start == item_record_start else "tail",
        "original_key": row["_key"],
        "linked_item_ids": row.get("linked_item_ids"),
        "media_item": mpi,
        "media_id": row.get("media_id"),
        "name": row.get("name"),
        "track_type": row["track_type"],
        "track_index": row["track_index"],
        "record_start_frame": record_start,
        "record_end_frame_exclusive": record_end,
        "source_start_frame": source_segment_start,
        "source_end_frame_exclusive": source_segment_end,
        "state_digest": row.get("state_digest"),
    }


def _segment_for_edge(row: dict[str, Any], *, side: str, boundary: int, timeline_fps: float) -> dict[str, Any]:
    return _segment_for_record_range(
        row,
        record_start=(
            int(row["record_start_frame"]) if side == "head" else boundary
        ),
        record_end=(
            boundary if side == "head" else int(row["record_end_frame_exclusive"])
        ),
        timeline_fps=timeline_fps,
    )


def _build_plan(
    conn: Any,
    *,
    mode: str,
    clip_name: str,
    position: str,
    source_in: str | None,
    source_out: str | None,
    track_index: int,
    audio_only: bool,
    media_id: str | None,
    audio_track_index: int | None,
    include_linked_audio: bool,
    expected_project_id: str | None,
    expected_timeline_id: str | None,
    expected_revision: str | None,
    snapshot: dict[str, Any] | None = None,
    prepare_segments: bool = True,
    shared_media_items: list[tuple[Any, tuple[str, ...]]] | None = None,
) -> dict[str, Any]:
    if mode not in {"insert", "overwrite"}:
        raise ValidationError("Unsupported edit placement mode.", details={"mode": mode})
    if audio_only and mode != "insert":
        raise ValidationError("Audio-only placement supports insert only.")
    target_track_index = _positive_track(track_index, label="audio track" if audio_only else "video track")
    video_track_index = None if audio_only else target_track_index
    media = _resolve_media_pool_item(
        conn,
        clip_name=clip_name,
        requested_media_id=media_id,
        all_items=shared_media_items,
    )
    has_video, has_audio = _source_streams(media["item"])
    if audio_only and has_audio is not True:
        raise ValidationError("Selected Media Pool item does not expose a readable audio stream.", details={"media_id": media["media_id"]})
    if not audio_only and not has_video:
        raise ValidationError("Selected Media Pool item does not expose a video stream.", details={"media_id": media["media_id"]})
    if include_linked_audio and has_audio is None:
        raise ValidationError(
            "Selected Media Pool item audio-stream state is unknown; use --video-only or choose media with readable audio metadata.",
            details={"reason": "source_audio_state_unknown", "media_id": media["media_id"]},
        )
    include_audio = False if audio_only else bool(include_linked_audio and has_audio)
    resolved_audio_track = target_track_index if audio_only else (_positive_track(audio_track_index or video_track_index, label="audio track") if include_audio else None)
    snapshot = snapshot if snapshot is not None else _snapshot(conn)
    _assert_expected_identity(
        snapshot["identity"],
        expected_project_id=expected_project_id,
        expected_timeline_id=expected_timeline_id,
    )
    if expected_revision and str(expected_revision).strip() != snapshot["revision"]:
        raise TimelineConflict(
            "Timeline revision precondition failed.",
            details={
                "reason": "revision_precondition_failed",
                "expected_revision": str(expected_revision).strip(),
                "actual_revision": snapshot["revision"],
            },
        )
    if video_track_index is not None:
        _validate_target_track(conn.timeline, "video", video_track_index)
    if resolved_audio_track is not None:
        _validate_target_track(conn.timeline, "audio", resolved_audio_track)
    source = _source_range(
        media["item"],
        source_in=source_in,
        source_out=source_out,
        timeline_fps=float(conn.fps),
        audio_only=audio_only,
    )
    record_start = _parse_exact_record_frame(
        position,
        float(conn.fps),
        int(_call(conn.timeline, "GetStartFrame", default=0) or 0),
    )
    record_end = record_start + int(source["record_duration_frames"])
    target_tracks = set()
    if video_track_index is not None:
        target_tracks.add(("video", video_track_index))
    if resolved_audio_track is not None:
        target_tracks.add(("audio", resolved_audio_track))
    overlaps = [
        row
        for row in snapshot["items"]
        if (row["track_type"], row["track_index"]) in target_tracks and _overlaps(row, record_start, record_end)
    ]
    transitions = _transition_conflicts(snapshot, target_tracks=target_tracks, start=record_start, end=record_end)
    if transitions:
        raise TimelineConflict(
            "Insert or overwrite would intersect transition state that this native route cannot preserve.",
            details={"reason": "transition_preservation_unsupported", "transitions": transitions},
        )
    if mode == "insert" and overlaps:
        raise TimelineConflict(
            "Insert is a non-ripple placement and requires an empty target range.",
            details={"reason": "insert_target_not_empty", "conflicts": [_public_item(row) for row in overlaps]},
        )
    overlap_keys = {row["_key"] for row in overlaps}
    item_ids = {row["item_id"]: row for row in snapshot["items"] if row.get("item_id")}
    if mode == "overwrite":
        for row in overlaps:
            linked_ids = row.get("linked_item_ids")
            if linked_ids is None:
                raise TimelineConflict(
                    "Overwrite cannot prove linked-item preservation for an affected timeline item.",
                    details={"reason": "linked_state_unavailable", "item": _public_item(row)},
                )
            linked_rows = [item_ids[item_id] for item_id in linked_ids if item_id in item_ids]
            unselected = [linked for linked in linked_rows if linked["_key"] not in overlap_keys]
            if unselected:
                raise TimelineConflict(
                    "Overwrite would separate or mutate a linked item outside the explicit target tracks.",
                    details={
                        "reason": "linked_protected_item_conflict",
                        "item": _public_item(row),
                        "protected_linked_items": [_public_item(linked) for linked in unselected],
                    },
                )
    segments: list[dict[str, Any]] = []
    if mode == "overwrite" and prepare_segments:
        partial_rows = [
            row
            for row in overlaps
            if int(row["record_start_frame"]) < record_start
            or int(row["record_end_frame_exclusive"]) > record_end
        ]
        _hydrate_edge_db_state(conn, partial_rows)
        for row in overlaps:
            if int(row["record_start_frame"]) < record_start:
                segments.append(_segment_for_edge(row, side="head", boundary=record_start, timeline_fps=float(conn.fps)))
            if int(row["record_end_frame_exclusive"]) > record_end:
                segments.append(_segment_for_edge(row, side="tail", boundary=record_end, timeline_fps=float(conn.fps)))
        for segment in segments:
            segment_source_fps = _source_fps(segment["media_item"], float(conn.fps))
            _native_source_frame_exact(
                segment["source_start_frame"],
                source_fps=segment_source_fps,
                timeline_fps=float(conn.fps),
            )
            _native_source_frame_exact(
                segment["source_end_frame_exclusive"],
                source_fps=segment_source_fps,
                timeline_fps=float(conn.fps),
            )
    subtitles = [
        _public_item(row)
        for row in snapshot["items"]
        if row["track_type"] == "subtitle" and _overlaps(row, record_start, record_end)
    ]
    return {
        "mode": mode,
        "media": media,
        "source": source,
        "snapshot": snapshot,
        "record_start_frame": record_start,
        "record_end_frame_exclusive": record_end,
        "video_track_index": video_track_index,
        "audio_track_index": resolved_audio_track,
        "include_audio": include_audio,
        "audio_only": audio_only,
        "overlaps": overlaps,
        "segments": segments,
        "protected_subtitles": subtitles,
        "target_tracks": target_tracks,
    }


def _clip_info(
    *,
    media_item: Any,
    source_start: int,
    source_end: int,
    record_start: int,
    track_type: str,
    track_index: int,
    timeline_fps: float,
) -> dict[str, Any]:
    source_fps = _source_fps(media_item, 24.0)
    native_start = _native_source_frame_exact(
        source_start,
        source_fps=source_fps,
        timeline_fps=timeline_fps,
    )
    native_end = _native_source_frame_exact(
        source_end,
        source_fps=source_fps,
        timeline_fps=timeline_fps,
    )
    source_duration = source_end - source_start
    has_video, has_audio = _source_streams(media_item)
    native_end_extension = _native_end_extension_for_nearest_record_duration(
        source_duration,
        source_fps=source_fps,
        timeline_fps=timeline_fps,
    )
    source_total_frames = _source_total_frames(media_item, source_fps)
    if (
        has_video
        and native_end_extension == 1
        and source_end < source_total_frames
    ):
        # DaVinci Resolve floors the record duration produced by an explicit
        # source range. Extend the native endpoint by one source-timebase frame
        # only when that produces the exact public nearest-frame duration;
        # this also covers fractional sources such as 59.94 fps on 29.97 fps.
        native_end += native_end_extension

    clip_info = {
        "mediaPoolItem": media_item,
        "startFrame": native_start,
        "endFrame": native_end,
        "recordFrame": int(record_start),
        "trackIndex": int(track_index),
        "trackType": track_type,
    }
    # Omitting the stream selector for a physically video-only item matches the
    # native media-append contract and avoids format-specific rejection. Keep
    # an explicit selector whenever audio may exist so video-only author intent
    # cannot append an undeclared audio stream.
    if track_type == "audio":
        clip_info["mediaType"] = 2
    elif has_audio is not False:
        clip_info["mediaType"] = 1
    return clip_info


def _append_specs(conn: Any, specs: list[dict[str, Any]], link_groups: list[list[int]]) -> list[Any]:
    raw_specs = [spec["clip_info"] for spec in specs]
    result = conn.media_pool.AppendToTimeline(raw_specs)
    if result is False or result is None:
        raise APICallFailed("DaVinci Resolve rejected timeline placement.")
    created = list(result) if isinstance(result, (list, tuple)) else []
    if created and len(created) != len(specs):
        raise APICallFailed(
            "DaVinci Resolve returned an incomplete placement result.",
            details={"requested_count": len(specs), "returned_count": len(created)},
        )
    if link_groups:
        if not created:
            raise APICallFailed("DaVinci Resolve did not return items required for linked-audio verification.")
        linker = getattr(conn.timeline, "SetClipsLinked", None)
        if not callable(linker):
            raise APICallFailed("DaVinci Resolve cannot link the inserted video and audio items.")
        for group in link_groups:
            if len(group) > 1:
                # DaVinci Resolve may return False when the append already
                # created the requested A/V linkage.  The complete fresh
                # timeline readback below is the authority for linkage, so a
                # false no-op result must not turn a correct placement into a
                # destructive overwrite recovery.
                linker([created[index] for index in group], True)
    return created


def _delete_no_ripple(conn: Any, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    deleter = getattr(conn.timeline, "DeleteClips", None)
    if not callable(deleter):
        raise APICallFailed("DaVinci Resolve cannot delete overwrite targets.")
    items = [row["_item"] for row in rows]
    try:
        result = deleter(items, False)
    except TypeError:
        result = deleter(items)
    if result is not True:
        raise APICallFailed("DaVinci Resolve failed to delete overwrite targets without ripple.")


def _specs_for_plan(plan: dict[str, Any]) -> tuple[list[dict[str, Any]], list[list[int]]]:
    specs: list[dict[str, Any]] = []
    groups: list[list[int]] = []
    for segment in plan["segments"]:
        expected = dict(segment)
        expected["source_end_tolerance_frames"] = max(
            1,
            int(math.ceil(_source_fps(segment["media_item"], plan["snapshot"]["fps"]) / plan["snapshot"]["fps"])),
        )
        specs.append(
            {
                "kind": "preserved_edge",
                "expected": expected,
                "clip_info": _clip_info(
                    media_item=segment["media_item"],
                    source_start=segment["source_start_frame"],
                    source_end=segment["source_end_frame_exclusive"],
                    record_start=segment["record_start_frame"],
                    track_type=segment["track_type"],
                    track_index=segment["track_index"],
                    timeline_fps=plan["snapshot"]["fps"],
                ),
            }
        )
    replacement_indices: list[int] = []
    for track_type, track_index in (
        ("video", plan["video_track_index"]),
        ("audio", plan["audio_track_index"]),
    ):
        if track_index is None:
            continue
        replacement_indices.append(len(specs))
        specs.append(
            {
                "kind": "replacement",
                "expected": {
                    "media_id": plan["media"]["media_id"],
                    "name": plan["media"]["name"],
                    "track_type": track_type,
                    "track_index": track_index,
                    "record_start_frame": plan["record_start_frame"],
                    "record_end_frame_exclusive": plan["record_end_frame_exclusive"],
                    "source_start_frame": plan["source"]["start_frame"],
                    "source_end_frame_exclusive": plan["source"]["end_frame_exclusive"],
                    "source_end_tolerance_frames": max(
                        1,
                        int(math.ceil(plan["source"]["source_fps"] / plan["snapshot"]["fps"])),
                    ),
                },
                "clip_info": _clip_info(
                    media_item=plan["media"]["item"],
                    source_start=plan["source"]["start_frame"],
                    source_end=plan["source"]["end_frame_exclusive"],
                    record_start=plan["record_start_frame"],
                    track_type=track_type,
                    track_index=track_index,
                    timeline_fps=plan["snapshot"]["fps"],
                ),
            }
        )
    if len(replacement_indices) > 1:
        groups.append(replacement_indices)
    for side in ("head", "tail"):
        side_indices = [
            index
            for index, spec in enumerate(specs)
            if spec["kind"] == "preserved_edge" and spec["expected"]["side"] == side
        ]
        for index in side_indices:
            expected = specs[index]["expected"]
            linked = set(expected.get("linked_item_ids") or [])
            linked_group = [
                candidate
                for candidate in side_indices
                if candidate == index
                or (
                    specs[candidate]["expected"].get("original_key") in linked
                    and specs[candidate]["expected"].get("record_start_frame")
                    == expected.get("record_start_frame")
                    and specs[candidate]["expected"].get("record_end_frame_exclusive")
                    == expected.get("record_end_frame_exclusive")
                )
                or specs[candidate]["expected"].get("media_id") == expected.get("media_id")
                and specs[candidate]["expected"].get("record_start_frame") == expected.get("record_start_frame")
                and specs[candidate]["expected"].get("track_type") != expected.get("track_type")
            ]
            if len(linked_group) > 1 and linked_group not in groups:
                groups.append(linked_group)
    return specs, groups


def _source_range_is_verifiable(
    row: dict[str, Any], expected: dict[str, Any]
) -> bool:
    readback = row.get("_source_range_readback", {})
    if readback.get("conflict") is not True:
        return True
    expected_start = expected.get("source_start_frame")
    expected_end = expected.get("source_end_frame_exclusive")
    if expected_start is None or expected_end is None:
        return False
    tolerance = int(expected.get("source_end_tolerance_frames", 1))
    native_start = readback.get("native_source_start_frame")
    native_end = readback.get("native_source_end_frame_exclusive")
    offset_start = readback.get("offset_source_start_frame")
    offset_end = readback.get("offset_source_end_frame_exclusive")
    return (
        native_start == expected_start
        and offset_start == expected_start
        and isinstance(native_end, int)
        and isinstance(offset_end, int)
        and abs(native_end - int(expected_end)) <= tolerance
        and abs(offset_end - int(expected_end)) <= tolerance
    )


def _match_expected(
    rows: list[dict[str, Any]], expected: dict[str, Any]
) -> list[dict[str, Any]]:
    return [
        row
        for row in rows
        if row["track_type"] == expected["track_type"]
        and _source_range_is_verifiable(row, expected)
        and row["track_index"] == expected["track_index"]
        and row["record_start_frame"] == expected["record_start_frame"]
        and row["record_end_frame_exclusive"] == expected["record_end_frame_exclusive"]
        and (expected.get("media_id") is None or row.get("media_id") == expected.get("media_id"))
        and (expected.get("name") is None or row.get("name") == expected.get("name"))
        and (
            expected.get("source_start_frame") is None
            or row.get("source_start_frame") == expected.get("source_start_frame")
        )
        and (
            expected.get("source_end_frame_exclusive") is None
            # DaVinci Resolve exposes timeline-item offsets in the record-rate
            # domain. Converting the right offset back to a fractional source
            # rate can differ by one source frame; record range, duration,
            # source start, media identity, and track remain exact.
            or (
                row.get("source_end_frame_exclusive") is not None
                and abs(
                    int(row["source_end_frame_exclusive"])
                    - int(expected["source_end_frame_exclusive"])
                ) <= int(expected.get("source_end_tolerance_frames", 1))
            )
        )
        and (expected.get("state_digest") is None or row.get("state_digest") == expected.get("state_digest"))
    ]


def _verify(
    plan: dict[str, Any],
    after: dict[str, Any],
    specs: list[dict[str, Any]],
    link_groups: list[list[int]],
) -> dict[str, Any]:
    before = plan["snapshot"]
    removed_keys = {row["_key"] for row in plan["overlaps"]}
    protected = [row for row in before["items"] if row["_key"] not in removed_keys]
    after_public = [{key: value for key, value in row.items() if not key.startswith("_")} for row in after["items"]]
    protected_signatures = Counter(_digest({key: value for key, value in row.items() if not key.startswith("_")}) for row in protected)
    after_signatures = Counter(_digest(row) for row in after_public)
    protected_ok = all(after_signatures[signature] >= count for signature, count in protected_signatures.items())
    after_item_ids = {row.get("item_id") for row in after["items"] if row.get("item_id")}
    removed_ok = all(row.get("item_id") not in after_item_ids for row in plan["overlaps"])
    expected_matches: list[dict[str, Any]] = []
    expected_ok = True
    for spec in specs:
        matches = _match_expected(after["items"], spec["expected"])
        expected_matches.append({"kind": spec["kind"], "matches": [_public_item(row) for row in matches]})
        expected_ok = expected_ok and len(matches) == 1
    after_by_id = {row.get("item_id"): row for row in after["items"] if row.get("item_id")}
    link_ok = True
    for group in link_groups:
        resolved = [
            expected_matches[index]["matches"][0]
            for index in group
            if index < len(expected_matches) and len(expected_matches[index]["matches"]) == 1
        ]
        actual = [after_by_id.get(row.get("item_id")) for row in resolved]
        if len(actual) != len(group) or any(row is None for row in actual):
            link_ok = False
            continue
        ids = {row["item_id"] for row in actual if row is not None}
        link_ok = link_ok and all(
            ids - {row["item_id"]} <= set(row.get("linked_item_ids") or [])
            for row in actual
            if row is not None
        )
    checks = [
        {"name": "active_identity_unchanged", "ok": after["identity"] == before["identity"]},
        {"name": "track_state_unchanged", "ok": after["tracks"] == before["tracks"]},
        {"name": "transitions_unchanged", "ok": after["transition_fingerprint"] == before["transition_fingerprint"]},
        {"name": "protected_items_unchanged", "ok": protected_ok},
        {"name": "removed_items_absent", "ok": removed_ok, "required": bool(plan["overlaps"])},
        {"name": "expected_items_resolved_once", "ok": expected_ok},
        {"name": "linked_groups_verified", "ok": link_ok, "required": bool(link_groups)},
    ]
    passed = all(check["ok"] for check in checks)
    return {
        "status": "passed" if passed else "failed",
        "checks": checks,
        "revision_before": before["revision"],
        "revision_after": after["revision"],
        "evidence": ["fresh_structural_readback"],
        "resolved_items": expected_matches,
    }


def _public_plan(plan: dict[str, Any], *, dry_run: bool, verification: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "action": f"edit.{plan['mode']}",
        "mode": plan["mode"],
        "dry_run": dry_run,
        "semantics": "non_ripple_empty_range_placement" if plan["mode"] == "insert" else "checkpoint_backed_overwrite",
        "target": {
            "project": {
                "id": plan["snapshot"]["identity"]["project_id"],
                "name": plan["snapshot"]["identity"]["project_name"],
            },
            "timeline": {
                "id": plan["snapshot"]["identity"]["timeline_id"],
                "name": plan["snapshot"]["identity"]["timeline_name"],
            },
            "video_track_index": plan["video_track_index"],
            "audio_track_index": plan["audio_track_index"],
        },
        "source": {
            "name": plan["media"]["name"],
            "media_id": plan["media"]["media_id"],
            "selector": plan["media"]["selector"],
            "range": {
                **{key: value for key, value in plan["source"].items()},
                "source_end_tolerance_frames": max(
                    1,
                    int(math.ceil(plan["source"]["source_fps"] / plan["snapshot"]["fps"])),
                ),
            },
        },
        "placement": {
            "record_start_frame": plan["record_start_frame"],
            "record_end_frame_exclusive": plan["record_end_frame_exclusive"],
            "duration_frames": plan["record_end_frame_exclusive"] - plan["record_start_frame"],
            "ripple": False,
        },
        "effects": {
            "removed_items": [_public_item(row) for row in plan["overlaps"]],
            "preserved_edge_segments": [
                {
                    **{key: value for key, value in segment.items() if key not in {"media_item", "linked_item_ids", "original_key"}},
                    "source_end_tolerance_frames": max(
                        1,
                        int(math.ceil(_source_fps(segment["media_item"], plan["snapshot"]["fps"]) / plan["snapshot"]["fps"])),
                    ),
                }
                for segment in plan["segments"]
            ],
            "protected_subtitles": plan["protected_subtitles"],
            "transition_count": len(plan["snapshot"]["transitions"]),
            "linked_audio": plan["include_audio"],
        },
        "precondition": {"revision": plan["snapshot"]["revision"], "validated": True},
        "verification": verification
        or {
            "status": "planned",
            "checks": [
                {"name": "identity_and_revision_validated", "ok": True},
                {"name": "source_and_tracks_validated", "ok": True},
                {"name": "protected_state_validated", "ok": True},
            ],
            "revision_before": plan["snapshot"]["revision"],
            "revision_after": None,
            "evidence": ["non_mutating_preflight"],
            "resolved_items": [],
        },
        "recovery": {
            "checkpoint_created": False,
            "state": "not_created_for_dry_run" if dry_run and plan["mode"] == "overwrite" else "not_needed",
            "manual_recovery_required": False,
        },
    }


def _refresh(conn: Any) -> Any:
    refresher = getattr(conn, "refresh", None)
    if callable(refresher):
        refresher()
    return conn


def _save_project(conn: Any) -> None:
    save_target = getattr(conn, "project_manager", None) or getattr(conn, "project", None)
    saver = getattr(save_target, "SaveProject", None)
    if not callable(saver) or not bool(saver()):
        raise APICallFailed("DaVinci Resolve failed to save the verified timeline placement.")


def _create_overwrite_checkpoint(conn: Any) -> tuple[str, str]:
    checkpoint_session_id = f"{_CHECKPOINT_SESSION_PREFIX}-{time.time_ns()}"
    try:
        checkpoint = version_ops.create_checkpoint(
            conn,
            label="Before verified overwrite",
            kind="before_prompt",
            session_id=checkpoint_session_id,
        )
        return str(checkpoint["id"]), checkpoint_session_id
    except Exception as exc:
        raise EditMutationFailedBeforeChange(
            "Overwrite checkpoint creation failed before timeline mutation.",
            details={
                "outcome": "failed_before_mutation",
                "mutation_state": "not_started",
                "error_code": getattr(exc, "code", exc.__class__.__name__),
            },
        ) from exc


def _restore_after_failure(
    conn: Any,
    *,
    checkpoint_id: str,
    checkpoint_session_id: str,
    plan: dict[str, Any],
    original_error: BaseException,
) -> None:
    try:
        restored = version_ops.restore_checkpoint(conn, checkpoint_id, session_id=checkpoint_session_id)
        if restored.get("verified") is not True:
            raise RuntimeError("checkpoint restore did not verify")
        fresh_conn = ResolveConnection.get()
        if not getattr(fresh_conn, "timeline", None):
            fresh_conn.connect()
        restored_snapshot = _snapshot(fresh_conn)
        restored_ok = (
            restored_snapshot["identity"] == plan["snapshot"]["identity"]
            and restored_snapshot["revision"] == plan["snapshot"]["revision"]
        )
        if not restored_ok:
            raise RuntimeError("restored timeline does not match the pre-mutation revision")
    except Exception as recovery_error:
        set_verification_status("failed")
        set_recoverability("manual")
        raise EditMutationRecoveryFailed(
            "Overwrite failed and CutAgent could not verify checkpoint recovery.",
            details={
                "outcome": "recovery_failed",
                "mutation_state": "manual_recovery_required",
                "checkpoint_id": checkpoint_id,
                "original_error_code": getattr(original_error, "code", original_error.__class__.__name__),
                "recovery_error_code": getattr(recovery_error, "code", recovery_error.__class__.__name__),
            },
        ) from original_error
    set_verification_status("failed")
    set_recoverability("manual")
    if not isinstance(original_error, Exception):
        raise original_error
    raise EditMutationRestored(
        "Overwrite failed after mutation and the pre-mutation checkpoint was restored and verified.",
        details={
            "outcome": "restored_checkpoint",
            "mutation_state": "restored",
            "checkpoint_id": checkpoint_id,
            "original_error_code": getattr(original_error, "code", original_error.__class__.__name__),
            "revision": plan["snapshot"]["revision"],
        },
    ) from original_error


def place_clip(
    conn: Any,
    *,
    mode: str,
    clip_name: str,
    position: str,
    source_in: str | None = None,
    source_out: str | None = None,
    track_index: int = 1,
    audio_only: bool = False,
    media_id: str | None = None,
    audio_track_index: int | None = None,
    include_linked_audio: bool = True,
    expected_project_id: str | None = None,
    expected_timeline_id: str | None = None,
    expected_revision: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Plan and execute verified insert or checkpoint-backed overwrite."""

    plan = _build_plan(
        conn,
        mode=mode,
        clip_name=clip_name,
        position=position,
        source_in=source_in,
        source_out=source_out,
        track_index=track_index,
        audio_only=audio_only,
        media_id=media_id,
        audio_track_index=audio_track_index,
        include_linked_audio=include_linked_audio,
        expected_project_id=expected_project_id,
        expected_timeline_id=expected_timeline_id,
        expected_revision=expected_revision,
    )
    if dry_run:
        set_verification_status("planned")
        set_recoverability("not_applicable")
        return _public_plan(plan, dry_run=True)

    checkpoint_id: str | None = None
    checkpoint_session_id: str | None = None
    mutation_started = False
    if mode == "overwrite":
        checkpoint_id, checkpoint_session_id = _create_overwrite_checkpoint(conn)

    try:
        _refresh(conn)
        revalidated = _build_plan(
            conn,
            mode=mode,
            clip_name=clip_name,
            position=position,
            source_in=source_in,
            source_out=source_out,
            track_index=track_index,
            audio_only=audio_only,
            media_id=media_id,
            audio_track_index=audio_track_index,
            include_linked_audio=include_linked_audio,
            expected_project_id=plan["snapshot"]["identity"]["project_id"],
            expected_timeline_id=plan["snapshot"]["identity"]["timeline_id"],
            expected_revision=plan["snapshot"]["revision"],
        )
        plan = revalidated
        specs, link_groups = _specs_for_plan(plan)
        if mode == "overwrite":
            mutation_started = bool(plan["overlaps"])
            _delete_no_ripple(conn, plan["overlaps"])
        # Treat the native append invocation as a possible mutation boundary.
        # DaVinci Resolve can return a false or incomplete result after
        # accepting only part of a multi-component placement, so the outcome
        # must be decided by fresh readback (or overwrite checkpoint restore),
        # never by the return value alone.
        mutation_started = mutation_started or bool(specs)
        created = _append_specs(conn, specs, link_groups)
        mutation_started = mutation_started or bool(created)
        _save_project(conn)
        _refresh(conn)
        after = _snapshot(conn)
        verification = _verify(plan, after, specs, link_groups)
        if verification["status"] != "passed":
            raise APICallFailed(
                "Fresh DaVinci Resolve readback did not verify the requested timeline placement.",
                details={"verification": verification},
            )
    except (EditMutationFailedBeforeChange, EditMutationPartiallyApplied, EditMutationRecoveryFailed, EditMutationRestored):
        raise
    except Exception as exc:
        if mode == "overwrite" and checkpoint_id and checkpoint_session_id and mutation_started:
            try:
                _refresh(conn)
                unchanged_before_recovery = (
                    _snapshot(conn)["revision"] == plan["snapshot"]["revision"]
                )
            except Exception:
                unchanged_before_recovery = False
            if unchanged_before_recovery:
                raise EditMutationFailedBeforeChange(
                    "Overwrite failed and fresh readback confirms the timeline remained unchanged.",
                    details={
                        "outcome": "failed_before_mutation",
                        "mutation_state": "not_started",
                        "checkpoint_id": checkpoint_id,
                        "error_code": getattr(exc, "code", exc.__class__.__name__),
                    },
                ) from exc
            _restore_after_failure(
                conn,
                checkpoint_id=checkpoint_id,
                checkpoint_session_id=checkpoint_session_id,
                plan=plan,
                original_error=exc,
            )
        if not mutation_started:
            raise EditMutationFailedBeforeChange(
                "Timeline placement failed before any mutation was observed.",
                details={
                    "outcome": "failed_before_mutation",
                    "mutation_state": "not_started",
                    "error_code": getattr(exc, "code", exc.__class__.__name__),
                },
            ) from exc
        try:
            _refresh(conn)
            unchanged = _snapshot(conn)["revision"] == plan["snapshot"]["revision"]
        except Exception:
            unchanged = False
        if unchanged:
            raise EditMutationFailedBeforeChange(
                "Timeline placement failed and readback confirms the timeline remained unchanged.",
                details={
                    "outcome": "failed_before_mutation",
                    "mutation_state": "not_started",
                    "error_code": getattr(exc, "code", exc.__class__.__name__),
                },
            ) from exc
        raise EditMutationPartiallyApplied(
            "Timeline placement failed after a mutation and no verified automatic recovery is available.",
            details={
                "outcome": "partially_applied",
                "mutation_state": "manual_recovery_required",
                "error_code": getattr(exc, "code", exc.__class__.__name__),
                "verification": getattr(exc, "details", {}).get("verification"),
            },
        ) from exc

    set_verification_status("verified")
    set_recoverability("manual")
    result = _public_plan(plan, dry_run=False, verification=verification)
    result["inserted"] = [
        match["matches"][0]
        for match in verification["resolved_items"]
        if match["kind"] == "replacement" and len(match["matches"]) == 1
    ]
    if checkpoint_id:
        result["recovery"] = {
            "checkpoint_created": True,
            "state": "available",
            "manual_recovery_required": False,
            "checkpoint_id": checkpoint_id,
        }
    return result


def insert_audio_clips_at(
    conn: Any,
    placements: list[dict[str, Any]],
    *,
    expected_project_id: str | None = None,
    expected_timeline_id: str | None = None,
    expected_revision: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Plan and insert several independent audio clips through one native append."""

    if not isinstance(placements, list) or not 1 <= len(placements) <= 256:
        raise ValidationError("Audio placement list must contain between 1 and 256 items.")

    def build(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
        plans = [
            _build_plan(
                conn,
                mode="insert",
                clip_name=str(item.get("clip_name") or ""),
                position=str(item.get("position") or ""),
                source_in=item.get("source_in"),
                source_out=item.get("source_out"),
                track_index=item.get("track_index"),
                audio_only=True,
                media_id=item.get("media_id"),
                audio_track_index=None,
                include_linked_audio=False,
                expected_project_id=expected_project_id,
                expected_timeline_id=expected_timeline_id,
                expected_revision=expected_revision,
                snapshot=snapshot,
            )
            for item in placements
        ]
        occupied: list[tuple[int, int, int]] = []
        for plan in plans:
            coordinate = (
                int(plan["audio_track_index"]),
                int(plan["record_start_frame"]),
                int(plan["record_end_frame_exclusive"]),
            )
            if any(
                track == coordinate[0]
                and start < coordinate[2]
                and coordinate[1] < end
                for track, start, end in occupied
            ):
                raise TimelineConflict(
                    "Audio placement items overlap each other on the same target track.",
                    details={"reason": "insert_items_overlap"},
                )
            occupied.append(coordinate)
        return plans

    snapshot = _snapshot(conn)
    _assert_expected_identity(
        snapshot["identity"],
        expected_project_id=expected_project_id,
        expected_timeline_id=expected_timeline_id,
    )
    if expected_revision and str(expected_revision).strip() != snapshot["revision"]:
        raise TimelineConflict(
            "Timeline revision precondition failed.",
            details={
                "reason": "revision_precondition_failed",
                "expected_revision": str(expected_revision).strip(),
                "actual_revision": snapshot["revision"],
            },
        )
    plans = build(snapshot)
    if dry_run:
        set_verification_status("planned")
        set_recoverability("not_applicable")
        return {
            "action": "edit.insert",
            "mode": "insert",
            "semantics": "non_ripple_empty_range_audio_placement",
            "dry_run": True,
            "items": [_public_plan(plan, dry_run=True) for plan in plans],
            "precondition": {"revision": snapshot["revision"], "validated": True},
        }

    mutation_started = False
    try:
        _refresh(conn)
        current = _snapshot(conn)
        if current["revision"] != snapshot["revision"]:
            raise TimelineConflict(
                "Timeline revision precondition failed.",
                details={
                    "reason": "revision_precondition_failed",
                    "expected_revision": snapshot["revision"],
                    "actual_revision": current["revision"],
                },
            )
        plans = build(current)
        all_specs: list[dict[str, Any]] = []
        for plan in plans:
            specs, link_groups = _specs_for_plan(plan)
            if link_groups or len(specs) != 1 or specs[0]["expected"]["track_type"] != "audio":
                raise ValidationError("Plural audio insertion resolved an unexpected native placement topology.")
            all_specs.extend(specs)
        mutation_started = bool(all_specs)
        created = _append_specs(conn, all_specs, [])
        mutation_started = mutation_started or bool(created)
        save_target = getattr(conn, "project_manager", None) or getattr(conn, "project", None)
        saver = getattr(save_target, "SaveProject", None)
        if not callable(saver) or not bool(saver()):
            raise APICallFailed("DaVinci Resolve failed to save the verified audio placements.")
        _refresh(conn)
        after = _snapshot(conn)
        verifications = []
        for plan in plans:
            specs, _ = _specs_for_plan(plan)
            verification = _verify(plan, after, specs, [])
            if verification["status"] != "passed":
                raise APICallFailed(
                    "Fresh DaVinci Resolve readback did not verify every requested audio placement.",
                    details={"verification": verification},
                )
            verifications.append(verification)
    except Exception as exc:
        try:
            _refresh(conn)
            unchanged = _snapshot(conn)["revision"] == snapshot["revision"]
        except Exception:
            unchanged = False
        if not mutation_started or unchanged:
            raise EditMutationFailedBeforeChange(
                "Audio placement failed and readback confirms that no requested mutation persisted.",
                details={
                    "outcome": "failed_before_mutation",
                    "mutation_state": "not_started",
                    "error_code": getattr(exc, "code", exc.__class__.__name__),
                },
            ) from exc
        raise EditMutationPartiallyApplied(
            "Audio placement failed after a possible partial native append.",
            details={
                "outcome": "partially_applied",
                "mutation_state": "manual_recovery_required",
                "error_code": getattr(exc, "code", exc.__class__.__name__),
            },
        ) from exc

    set_verification_status("verified")
    set_recoverability("manual")
    items = []
    for plan, verification in zip(plans, verifications):
        item = _public_plan(plan, dry_run=False, verification=verification)
        item["inserted"] = [
            match["matches"][0]
            for match in verification["resolved_items"]
            if match["kind"] == "replacement" and len(match["matches"]) == 1
        ]
        items.append(item)
    return {
        "action": "edit.insert",
        "mode": "insert",
        "semantics": "non_ripple_empty_range_audio_placement",
        "dry_run": False,
        "items": items,
        "revision_before": snapshot["revision"],
        "revision_after": after["revision"],
    }


def insert_clip_at(
    conn: Any,
    clip_name: str,
    position: str,
    source_in: Optional[str] = None,
    source_out: Optional[str] = None,
    track_index: int = 1,
    *,
    audio_only: bool = False,
    media_id: str | None = None,
    audio_track_index: int | None = None,
    include_linked_audio: bool = True,
    expected_project_id: str | None = None,
    expected_timeline_id: str | None = None,
    expected_revision: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    return place_clip(
        conn,
        mode="insert",
        clip_name=clip_name,
        position=position,
        source_in=source_in,
        source_out=source_out,
        track_index=track_index,
        audio_only=audio_only,
        media_id=media_id,
        audio_track_index=audio_track_index,
        include_linked_audio=include_linked_audio,
        expected_project_id=expected_project_id,
        expected_timeline_id=expected_timeline_id,
        expected_revision=expected_revision,
        dry_run=dry_run,
    )


_INSERT_REQUEST_FIELDS = {
    "clip_name",
    "position",
    "source_in",
    "source_out",
    "track_index",
    "media_id",
    "audio_track_index",
    "include_linked_audio",
}


def _normalize_insert_requests(
    requests: Mapping[str, Any] | Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    candidates = [requests] if isinstance(requests, Mapping) else list(requests)
    if not candidates:
        raise ValidationError("Insert requires at least one placement request.")
    if len(candidates) > 256:
        raise ValidationError("Insert accepts at most 256 placement requests.")
    normalized: list[dict[str, Any]] = []
    for index, request in enumerate(candidates):
        if not isinstance(request, Mapping):
            raise ValidationError(
                "Each insert placement request must be an object.",
                details={"index": index},
            )
        unknown = sorted(set(request) - _INSERT_REQUEST_FIELDS)
        missing = sorted({"clip_name", "position"} - set(request))
        if unknown or missing:
            raise ValidationError(
                "Insert placement request fields are invalid.",
                details={"index": index, "unknown_fields": unknown, "missing_fields": missing},
            )
        normalized.append(dict(request))
    return normalized


def _normalize_overwrite_requests(
    requests: Mapping[str, Any] | Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    candidates = [requests] if isinstance(requests, Mapping) else list(requests)
    if not candidates:
        raise ValidationError("Overwrite requires at least one placement request.")
    normalized: list[dict[str, Any]] = []
    for index, request in enumerate(candidates):
        if not isinstance(request, Mapping):
            raise ValidationError(
                "Each overwrite placement request must be an object.",
                details={"index": index},
            )
        unknown = sorted(set(request) - _OVERWRITE_REQUEST_FIELDS)
        missing = sorted({"clip_name", "position"} - set(request))
        if unknown or missing:
            raise ValidationError(
                "Overwrite placement request fields are invalid.",
                details={"index": index, "unknown_fields": unknown, "missing_fields": missing},
            )
        normalized.append(dict(request))
    return normalized


def _aggregate_preserved_segments(
    conn: Any, plans: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    affected = {
        row["_key"]: row for plan in plans for row in plan["overlaps"]
    }
    remaining: list[tuple[dict[str, Any], int, int]] = []
    for key, row in affected.items():
        cuts = sorted(
            (
                max(int(row["record_start_frame"]), int(plan["record_start_frame"])),
                min(
                    int(row["record_end_frame_exclusive"]),
                    int(plan["record_end_frame_exclusive"]),
                ),
            )
            for plan in plans
            if any(candidate["_key"] == key for candidate in plan["overlaps"])
        )
        cursor = int(row["record_start_frame"])
        for cut_start, cut_end in cuts:
            if cursor < cut_start:
                remaining.append((row, cursor, cut_start))
            cursor = max(cursor, cut_end)
        if cursor < int(row["record_end_frame_exclusive"]):
            remaining.append((row, cursor, int(row["record_end_frame_exclusive"])))
    _hydrate_edge_db_state(
        conn,
        list({row["_key"]: row for row, _start, _end in remaining}.values()),
    )
    timeline_fps = float(plans[0]["snapshot"]["fps"])
    segments = [
        _segment_for_record_range(
            row,
            record_start=record_start,
            record_end=record_end,
            timeline_fps=timeline_fps,
        )
        for row, record_start, record_end in remaining
    ]
    for segment in segments:
        segment_source_fps = _source_fps(segment["media_item"], timeline_fps)
        _native_source_frame_exact(
            segment["source_start_frame"],
            source_fps=segment_source_fps,
            timeline_fps=timeline_fps,
        )
        _native_source_frame_exact(
            segment["source_end_frame_exclusive"],
            source_fps=segment_source_fps,
            timeline_fps=timeline_fps,
        )
    return segments


def overwrite_clips_at(
    conn: Any,
    requests: Mapping[str, Any] | Iterable[Mapping[str, Any]],
    *,
    expected_project_id: str | None = None,
    expected_timeline_id: str | None = None,
    expected_revision: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Overwrite one or more disjoint ranges with one checkpoint and one save."""

    normalized = _normalize_overwrite_requests(requests)
    initial_snapshot = _snapshot(conn)
    plans = [
        _build_plan(
            conn,
            mode="overwrite",
            clip_name=request["clip_name"],
            position=request["position"],
            source_in=request.get("source_in"),
            source_out=request.get("source_out"),
            track_index=request.get("track_index", 1),
            audio_only=False,
            media_id=request.get("media_id"),
            audio_track_index=request.get("audio_track_index"),
            include_linked_audio=request.get("include_linked_audio", True),
            expected_project_id=expected_project_id,
            expected_timeline_id=expected_timeline_id,
            expected_revision=expected_revision,
            snapshot=initial_snapshot,
            prepare_segments=False,
        )
        for request in normalized
    ]
    for left_index, left in enumerate(plans):
        for right_index, right in enumerate(plans[left_index + 1 :], start=left_index + 1):
            overlaps_in_time = (
                left["record_start_frame"] < right["record_end_frame_exclusive"]
                and right["record_start_frame"] < left["record_end_frame_exclusive"]
            )
            if overlaps_in_time and left["target_tracks"] & right["target_tracks"]:
                raise TimelineConflict(
                    "Overwrite group contains overlapping target ranges on the same track.",
                    details={
                        "reason": "overlapping_batch_targets",
                        "request_indices": [left_index, right_index],
                    },
                )

    aggregate_segments = _aggregate_preserved_segments(conn, plans)
    if dry_run:
        set_verification_status("planned")
        set_recoverability("not_applicable")
        return {
            "action": "edit.overwrite",
            "dry_run": True,
            "items": [
                _public_plan(
                    {
                        **plan,
                        "segments": [
                            segment
                            for segment in aggregate_segments
                            if segment["original_key"]
                            in {row["_key"] for row in plan["overlaps"]}
                        ],
                    },
                    dry_run=True,
                )
                for plan in plans
            ],
            "precondition": {
                "revision": initial_snapshot["revision"],
                "validated": True,
            },
            "batch": {"requested_count": len(plans), "completed_count": 0},
            "recovery": {
                "checkpoint_created": False,
                "state": "not_created_for_dry_run",
                "manual_recovery_required": False,
            },
            "verification": {
                "status": "planned",
                "request_count": len(plans),
                "evidence": ["shared_non_mutating_preflight"],
            },
        }

    edge_plan = {
        **plans[0],
        "segments": aggregate_segments,
        "video_track_index": None,
        "audio_track_index": None,
    }
    specs, link_groups = _specs_for_plan(edge_plan)
    plan_spec_indices: list[list[int]] = []
    plan_output_segments: list[list[dict[str, Any]]] = []
    for plan in plans:
        replacement_plan = {**plan, "segments": []}
        plan_specs, plan_link_groups = _specs_for_plan(replacement_plan)
        offset = len(specs)
        specs.extend(plan_specs)
        link_groups.extend(
            [[offset + index for index in group] for group in plan_link_groups]
        )
        affected_keys = {row["_key"] for row in plan["overlaps"]}
        relevant_edge_indices = [
            index
            for index, spec in enumerate(specs[:offset])
            if spec["expected"].get("original_key") in affected_keys
        ]
        plan_spec_indices.append(
            [*relevant_edge_indices, *range(offset, len(specs))]
        )
        plan_output_segments.append(
            [
                segment
                for segment in aggregate_segments
                if segment["original_key"] in affected_keys
            ]
        )
    overlaps_by_key = {
        row["_key"]: row for plan in plans for row in plan["overlaps"]
    }
    overlaps = list(overlaps_by_key.values())
    aggregate_plan = {"snapshot": initial_snapshot, "overlaps": overlaps}

    checkpoint_id, checkpoint_session_id = _create_overwrite_checkpoint(conn)
    mutation_started = False
    try:
        _refresh(conn)
        revalidated = _snapshot(conn)
        if (
            revalidated["identity"] != initial_snapshot["identity"]
            or revalidated["revision"] != initial_snapshot["revision"]
        ):
            raise EditMutationFailedBeforeChange(
                "Overwrite group changed during final pre-mutation revalidation.",
                details={
                    "outcome": "failed_before_mutation",
                    "mutation_state": "not_started",
                    "checkpoint_id": checkpoint_id,
                },
            )
        mutation_started = bool(overlaps)
        _delete_no_ripple(conn, overlaps)
        # AppendToTimeline may partially mutate before returning a failure.
        mutation_started = mutation_started or bool(specs)
        _append_specs(conn, specs, link_groups)
        _save_project(conn)
        _refresh(conn)
        after = _snapshot(conn)
        verification = _verify(aggregate_plan, after, specs, link_groups)
        if verification["status"] != "passed":
            raise APICallFailed(
                "Fresh DaVinci Resolve readback did not verify the saved overwrite group.",
                details={"verification": verification},
            )
    except BaseException as exc:
        if mutation_started:
            _restore_after_failure(
                conn,
                checkpoint_id=checkpoint_id,
                checkpoint_session_id=checkpoint_session_id,
                plan={"snapshot": initial_snapshot},
                original_error=exc,
            )
        raise

    completed: list[dict[str, Any]] = []
    for plan, spec_indices, output_segments in zip(
        plans, plan_spec_indices, plan_output_segments
    ):
        item_verification = {
            **verification,
            "resolved_items": [
                verification["resolved_items"][index] for index in spec_indices
            ],
        }
        item = _public_plan(
            {**plan, "segments": output_segments},
            dry_run=False,
            verification=item_verification,
        )
        item["inserted"] = [
            match["matches"][0]
            for match in item_verification["resolved_items"]
            if match["kind"] == "replacement" and len(match["matches"]) == 1
        ]
        item["recovery"] = {
            "checkpoint_created": True,
            "state": "available",
            "manual_recovery_required": False,
            "checkpoint_id": checkpoint_id,
        }
        completed.append(item)

    set_verification_status("verified")
    set_recoverability("manual")
    return {
        "action": "edit.overwrite",
        "dry_run": False,
        "items": completed,
        "precondition": {
            "revision": initial_snapshot["revision"],
            "validated": True,
        },
        "batch": {
            "requested_count": len(normalized),
            "completed_count": len(completed),
        },
        "recovery": {
            "checkpoint_created": True,
            "state": "available",
            "manual_recovery_required": False,
            "checkpoint_id": checkpoint_id,
            "scope": "all_items",
        },
        "verification": {
            "status": "passed",
            "request_count": len(completed),
            "revision_before": initial_snapshot["revision"],
            "revision_after": after["revision"],
            "evidence": ["shared_structural_readback", "shared_post_save_readback"],
        },
    }


def insert_clips_at(
    conn: Any,
    requests: Mapping[str, Any] | Iterable[Mapping[str, Any]],
    *,
    expected_project_id: str | None = None,
    expected_timeline_id: str | None = None,
    expected_revision: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Insert one or more disjoint placements with one native append and readback."""

    normalized = _normalize_insert_requests(requests)
    snapshot = _snapshot(conn)
    root = _call(getattr(conn, "media_pool", None), "GetRootFolder")
    if root is None:
        raise ReadinessFailed("DaVinci Resolve Media Pool is unavailable.")
    media_items = _walk_media_pool(root)
    plans = [
        _build_plan(
            conn,
            mode="insert",
            clip_name=request["clip_name"],
            position=request["position"],
            source_in=request.get("source_in"),
            source_out=request.get("source_out"),
            track_index=request.get("track_index", 1),
            audio_only=False,
            media_id=request.get("media_id"),
            audio_track_index=request.get("audio_track_index"),
            include_linked_audio=request.get("include_linked_audio", True),
            expected_project_id=expected_project_id,
            expected_timeline_id=expected_timeline_id,
            expected_revision=expected_revision,
            snapshot=snapshot,
            shared_media_items=media_items,
        )
        for request in normalized
    ]
    for left_index, left in enumerate(plans):
        for right_index, right in enumerate(plans[left_index + 1 :], start=left_index + 1):
            overlaps_in_time = (
                left["record_start_frame"] < right["record_end_frame_exclusive"]
                and right["record_start_frame"] < left["record_end_frame_exclusive"]
            )
            if overlaps_in_time and left["target_tracks"] & right["target_tracks"]:
                raise TimelineConflict(
                    "Insert group contains overlapping target ranges on the same track.",
                    details={"reason": "overlapping_batch_targets", "request_indices": [left_index, right_index]},
                )

    if dry_run:
        set_verification_status("planned")
        set_recoverability("not_applicable")
        return {
            "action": "edit.insert",
            "dry_run": True,
            "items": [_public_plan(plan, dry_run=True) for plan in plans],
            "precondition": {"revision": snapshot["revision"], "validated": True},
            "batch": {"requested_count": len(plans), "completed_count": 0},
            "verification": {"status": "planned", "request_count": len(plans), "evidence": ["shared_non_mutating_preflight"]},
        }

    _refresh(conn)
    revalidated = _snapshot(conn)
    if revalidated["identity"] != snapshot["identity"] or revalidated["revision"] != snapshot["revision"]:
        raise EditMutationFailedBeforeChange(
            "Timeline changed after insert group preflight.",
            details={"outcome": "failed_before_mutation", "mutation_state": "not_started"},
        )
    all_specs: list[dict[str, Any]] = []
    all_link_groups: list[list[int]] = []
    per_plan_specs: list[tuple[list[dict[str, Any]], list[list[int]]]] = []
    for plan in plans:
        specs, link_groups = _specs_for_plan(plan)
        offset = len(all_specs)
        all_specs.extend(specs)
        all_link_groups.extend([[offset + index for index in group] for group in link_groups])
        per_plan_specs.append((specs, link_groups))
    mutation_started = bool(all_specs)
    try:
        _append_specs(conn, all_specs, all_link_groups)
        save_target = getattr(conn, "project_manager", None) or getattr(conn, "project", None)
        saver = getattr(save_target, "SaveProject", None)
        if not callable(saver) or not bool(saver()):
            raise APICallFailed("DaVinci Resolve failed to save the verified timeline placements.")
        _refresh(conn)
        after = _snapshot(conn)
        verifications = [
            _verify(plan, after, specs, link_groups)
            for plan, (specs, link_groups) in zip(plans, per_plan_specs)
        ]
        if any(verification["status"] != "passed" for verification in verifications):
            raise APICallFailed(
                "Fresh DaVinci Resolve readback did not verify every requested timeline placement.",
                details={"verifications": verifications},
            )
    except (EditMutationFailedBeforeChange, EditMutationPartiallyApplied):
        raise
    except Exception as exc:
        try:
            unchanged = _snapshot(conn)["revision"] == snapshot["revision"]
        except Exception:
            unchanged = False
        if not mutation_started or unchanged:
            raise EditMutationFailedBeforeChange(
                "Timeline insert group failed and readback confirms no mutation.",
                details={"outcome": "failed_before_mutation", "mutation_state": "not_started", "error_code": getattr(exc, "code", exc.__class__.__name__)},
            ) from exc
        raise EditMutationPartiallyApplied(
            "Timeline insert group failed after a mutation and requires manual recovery.",
            details={"outcome": "partially_applied", "mutation_state": "manual_recovery_required", "error_code": getattr(exc, "code", exc.__class__.__name__)},
        ) from exc

    set_verification_status("verified")
    set_recoverability("manual")
    completed = []
    for plan, verification in zip(plans, verifications):
        result = _public_plan(plan, dry_run=False, verification=verification)
        result["inserted"] = [
            match["matches"][0]
            for match in verification["resolved_items"]
            if match["kind"] == "replacement" and len(match["matches"]) == 1
        ]
        completed.append(result)
    return {
        "action": "edit.insert",
        "dry_run": False,
        "items": completed,
        "precondition": {"revision": snapshot["revision"], "validated": True},
        "batch": {"requested_count": len(plans), "completed_count": len(completed)},
        "verification": {
            "status": "passed",
            "request_count": len(completed),
            "revision_before": snapshot["revision"],
            "revision_after": after["revision"],
            "evidence": ["one_native_plural_append", "shared_post_save_readback"],
        },
    }


def overwrite_clip_at(
    conn: Any,
    clip_name: str,
    position: str,
    source_in: Optional[str] = None,
    source_out: Optional[str] = None,
    track_index: int = 1,
    *,
    media_id: str | None = None,
    audio_track_index: int | None = None,
    include_linked_audio: bool = True,
    expected_project_id: str | None = None,
    expected_timeline_id: str | None = None,
    expected_revision: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    return place_clip(
        conn,
        mode="overwrite",
        clip_name=clip_name,
        position=position,
        source_in=source_in,
        source_out=source_out,
        track_index=track_index,
        audio_only=False,
        media_id=media_id,
        audio_track_index=audio_track_index,
        include_linked_audio=include_linked_audio,
        expected_project_id=expected_project_id,
        expected_timeline_id=expected_timeline_id,
        expected_revision=expected_revision,
        dry_run=dry_run,
    )
