"""Timeline operations — CRUD, playhead, markers, tracks, items."""

from __future__ import annotations

import time
import re
from pathlib import Path
from typing import Optional, List, Dict, Any

from ..errors import APICallFailed, CapabilityNegotiationFailed, ConfirmationRequired, MissingArgumentError, ValidationError
from ..output import set_recoverability, set_verification_status
from ..policy import require_any_api_method, require_api_method
from ..utils.time_ref import parse_record_frame
from ..utils.timecode import frames_to_seconds, seconds_to_timecode
from .sdk_live_inspection import (
    SdkLiveInspectionTimeout as _SdkLiveInspectionTimeout,
    documented_unique_id as _sdk_timeline_unique_id,
    media_pool_native_id as _sdk_media_pool_native_id,
    inspect_live_state as _inspect_sdk_live_state,
    require_color_mutation_guard as _require_sdk_color_mutation_guard,
    require_marker_mutation_guard as _require_sdk_marker_mutation_guard,
    require_mutation_guard as _require_sdk_mutation_guard,
    validate_deadline as _validate_sdk_live_inspection_deadline,
)


def _timeline_unique_id(timeline: Any) -> str | None:
    for method_name in ("GetUniqueId", "GetUniqueID", "GetId", "GetID"):
        getter = getattr(timeline, method_name, None)
        if not callable(getter):
            continue
        try:
            value = getter()
        except Exception:
            continue
        if value not in (None, ""):
            return str(value)
    return None


def list_timelines(conn, *, authoritative_ids: bool = False) -> List[Dict[str, Any]]:
    """
    List all timelines in the current project.
    
    Args:
        conn: ResolveConnection instance
    
    Returns:
        List of timeline info dicts
    """
    count = conn.project.GetTimelineCount() or 0
    current_name = conn.timeline.GetName() if conn.timeline else None
    identity_reader = _sdk_timeline_unique_id if authoritative_ids else _timeline_unique_id
    current_id = identity_reader(conn.timeline) if conn.timeline else None

    rows = []
    for i in range(1, count + 1):
        tl = conn.project.GetTimelineByIndex(i)
        if not tl and authoritative_ids:
            raise APICallFailed(
                f"DaVinci Resolve omitted Timeline index {i} from an authoritative inventory."
            )
        if tl:
            name = tl.GetName()
            settings = tl.GetSetting()
            fps = settings.get("timelineFrameRate", "?") if isinstance(settings, dict) else "?"
            timeline_id = identity_reader(tl)
            is_current = (
                timeline_id == current_id
                if timeline_id and current_id
                else (False if authoritative_ids else name == current_name)
            )
            rows.append({
                "index": i,
                "name": name,
                "timeline_id": timeline_id,
                "fps": fps,
                "current": "yes" if is_current else "",
                "is_current": is_current,
            })
    return rows


def get_timeline_info(conn) -> Dict[str, Any]:
    """
    Get detailed info about the current timeline.
    
    Args:
        conn: ResolveConnection instance
    
    Returns:
        Dictionary with timeline information
    """
    tl = conn.timeline
    data = {
        "name": tl.GetName(),
        "fps": conn.fps,
        "start_frame": conn.start_frame,
    }

    try:
        data["start_timecode"] = tl.GetStartTimecode()
    except Exception:
        pass
    try:
        data["end_timecode"] = tl.GetEndTimecode()
    except Exception:
        pass

    for track_type in ("video", "audio", "subtitle"):
        try:
            data[f"{track_type}_tracks"] = tl.GetTrackCount(track_type) or 0
        except Exception:
            pass

    try:
        settings = tl.GetSetting()
        if isinstance(settings, dict):
            for k in ["timelineResolutionWidth", "timelineResolutionHeight", "timelineFrameRate"]:
                if k in settings:
                    data[k] = settings[k]
    except Exception:
        pass

    return data


def create_timeline(
    conn,
    name: str,
    width: Optional[int] = None,
    height: Optional[int] = None,
    fps: Optional[float] = None,
) -> object:
    """
    Create a new empty timeline.
    
    Args:
        conn: ResolveConnection instance
        name: Timeline name
        width: Optional resolution width
        height: Optional resolution height
        fps: Optional frame rate
    
    Returns:
        Timeline object
    
    Raises:
        APICallFailed: If timeline creation fails
    """
    def _matches(key: str, expected: str, actual: object) -> bool:
        if actual in (None, ""):
            return False
        try:
            if key == "timelineFrameRate":
                return abs(float(actual) - float(expected)) < 0.001
            return int(float(actual)) == int(float(expected))
        except (TypeError, ValueError):
            return str(actual).strip() == expected.strip()

    def _setting_token(key: str, value: object) -> str:
        if key == "timelineFrameRate":
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                pass
            else:
                if numeric.is_integer():
                    return str(int(numeric))
        return str(value)

    requested_settings = {
        key: _setting_token(key, value)
        for key, value in (
            ("timelineResolutionWidth", width),
            ("timelineResolutionHeight", height),
            ("timelineFrameRate", fps),
        )
        if value is not None
    }

    def _restore_project_settings(previous: Dict[str, object]) -> Dict[str, Any]:
        setter_results: Dict[str, Any] = {}
        for key in reversed(list(previous)):
            try:
                setter_results[key] = conn.project.SetSetting(key, previous[key])
            except Exception as exc:
                setter_results[key] = {"error": str(exc)}
        actual_settings = {
            key: conn.project.GetSetting(key)
            for key in previous
        }
        return {
            "setter_results": setter_results,
            "actual_settings": actual_settings,
            "restored": all(
                (
                    actual_settings.get(key) == expected
                    or str(actual_settings.get(key, "")).strip() == str(expected or "").strip()
                )
                for key, expected in previous.items()
            ),
        }

    def _delete_created_timeline(timeline: object) -> Dict[str, Any]:
        delete_timelines = getattr(conn.media_pool, "DeleteTimelines", None)
        if not callable(delete_timelines):
            return {"deleted": False, "error": "DeleteTimelines is unavailable."}
        try:
            return {"deleted": bool(delete_timelines([timeline]))}
        except Exception as exc:
            return {"deleted": False, "error": str(exc)}

    # DaVinci Resolve establishes project-level timeline resolution and frame
    # rate when the first timeline is created. Set and verify those values at
    # project scope first so Timeline.SetSetting cannot silently ignore them.
    project_timeline_count = conn.project.GetTimelineCount() or 0
    project_previous_settings: Dict[str, object] = {}
    if requested_settings and project_timeline_count == 0:
        project_previous_settings = {
            key: conn.project.GetSetting(key)
            for key in requested_settings
        }
        project_setter_results: Dict[str, Any] = {}
        for key, value in requested_settings.items():
            try:
                project_setter_results[key] = conn.project.SetSetting(key, value)
            except Exception as exc:
                project_setter_results[key] = {"error": str(exc)}
        project_actual_settings = {
            key: conn.project.GetSetting(key)
            for key in requested_settings
        }
        project_mismatches = {
            key: {"expected": expected, "actual": project_actual_settings.get(key)}
            for key, expected in requested_settings.items()
            if not _matches(key, expected, project_actual_settings.get(key))
        }
        if project_mismatches:
            rollback = _restore_project_settings(project_previous_settings)
            set_verification_status("failed")
            raise APICallFailed(
                "Failed to configure project timeline settings before creating its first timeline.",
                details={
                    "timeline": name,
                    "mismatches": project_mismatches,
                    "setter_results": project_setter_results,
                    "actual_settings": project_actual_settings,
                    "rollback": rollback,
                },
            )

    tl = conn.media_pool.CreateEmptyTimeline(name)
    if not tl:
        rollback = _restore_project_settings(project_previous_settings) if project_previous_settings else None
        raise APICallFailed(
            f"Failed to create timeline '{name}'.",
            details={"timeline": name, "rollback": rollback},
        )

    # Existing projects create timelines with inherited project settings. Read
    # those values before writing: DaVinci Resolve can reject a redundant
    # Timeline.SetSetting call even though the inherited value is already exact.
    inherited_settings = {
        key: tl.GetSetting(key)
        for key in requested_settings
    }
    settings_to_apply = {
        key: value
        for key, value in requested_settings.items()
        if not _matches(key, value, inherited_settings.get(key))
    }

    setter_results: Dict[str, Any] = {}
    if project_timeline_count > 0 and settings_to_apply:
        custom_setting = tl.GetSetting("useCustomSettings")
        if custom_setting not in (True, 1, "1") and str(custom_setting).strip().lower() != "true":
            try:
                setter_results["useCustomSettings"] = tl.SetSetting("useCustomSettings", "1")
            except Exception as exc:
                setter_results["useCustomSettings"] = {"error": str(exc)}
    for key, value in settings_to_apply.items():
        try:
            setter_results[key] = tl.SetSetting(key, value)
        except Exception as exc:
            setter_results[key] = {"error": str(exc)}

    actual_settings = {
        key: tl.GetSetting(key)
        for key in requested_settings
    }

    mismatches = {
        key: {"expected": expected, "actual": actual_settings.get(key)}
        for key, expected in requested_settings.items()
        if not _matches(key, expected, actual_settings.get(key))
    }
    if mismatches:
        timeline_cleanup = _delete_created_timeline(tl)
        project_rollback = _restore_project_settings(project_previous_settings) if project_previous_settings else None
        set_verification_status("failed")
        raise APICallFailed(
            f"Timeline '{name}' was created, but its requested settings did not verify.",
            details={
                "timeline": name,
                "mismatches": mismatches,
                "setter_results": setter_results,
                "actual_settings": actual_settings,
                "timeline_cleanup": timeline_cleanup,
                "project_rollback": project_rollback,
            },
        )

    conn.wait_for_state(
        lambda state: state["timeline"] == name,
        description=f"timeline '{name}' to become current after creation",
    )
    set_verification_status("verified")
    return tl


def switch_timeline(
    conn,
    name: Optional[str] = None,
    index: Optional[int] = None,
    *,
    return_details: bool = False,
) -> object | Dict[str, Any]:
    """
    Switch to a different timeline by name or index.
    
    Args:
        conn: ResolveConnection instance
        name: Timeline name
        index: Timeline index (1-based)
    
    Returns:
        Timeline object
    
    Raises:
        APICallFailed: If timeline not found or switch fails
    """
    if name and index is not None:
        raise ValidationError(
            "Provide either a timeline name or --index, not both.",
            details={"name": name, "index": index},
            recoverability="not_applicable",
        )

    target_index = index
    if index is not None:
        tl = conn.project.GetTimelineByIndex(index)
        if not tl:
            raise APICallFailed(f"No timeline at index {index}.")
    elif name:
        count = conn.project.GetTimelineCount() or 0
        tl = None
        for i in range(1, count + 1):
            t = conn.project.GetTimelineByIndex(i)
            if t and t.GetName() == name:
                tl = t
                target_index = i
                break
        if not tl:
            raise APICallFailed(f"Timeline '{name}' not found.")
    else:
        raise MissingArgumentError("Provide a timeline name or index.")

    current_timeline = getattr(conn, "timeline", None)
    current_name = current_timeline.GetName() if current_timeline and hasattr(current_timeline, "GetName") else None
    target_name = tl.GetName() if hasattr(tl, "GetName") else name
    if current_name and target_name and current_name == target_name:
        conn.wait_for_state(
            lambda state: state["timeline"] == target_name,
            description=f"timeline '{target_name}' to remain current",
        )
        set_verification_status("verified")
        set_recoverability("not_applicable")
        details = {
            "timeline": tl,
            "requested": {"name": name, "index": index},
            "target": {"kind": "timeline", "name": target_name, "index": target_index},
            "pre": {"name": current_name},
            "final": {"name": target_name},
            "api_result": None,
            "changed": False,
            "verified": True,
        }
        return details if return_details else tl

    result = conn.project.SetCurrentTimeline(tl)
    if not result:
        if current_name and target_name and current_name == target_name:
            conn.wait_for_state(
                lambda state: state["timeline"] == target_name,
                description=f"timeline '{target_name}' to remain current",
            )
            set_verification_status("verified")
            set_recoverability("not_applicable")
            details = {
                "timeline": tl,
                "requested": {"name": name, "index": index},
                "target": {"kind": "timeline", "name": target_name, "index": target_index},
                "pre": {"name": current_name},
                "final": {"name": target_name},
                "api_result": False,
                "changed": False,
                "verified": True,
            }
            return details if return_details else tl
        raise APICallFailed("Failed to switch timeline.")

    conn.wait_for_state(
        lambda state: state["timeline"] == target_name,
        description=f"timeline '{target_name}' to become current",
    )
    set_verification_status("verified")
    set_recoverability("not_applicable")
    details = {
        "timeline": tl,
        "requested": {"name": name, "index": index},
        "target": {"kind": "timeline", "name": target_name, "index": target_index},
        "pre": {"name": current_name},
        "final": {"name": target_name},
        "api_result": result,
        "changed": current_name != target_name,
        "verified": True,
    }
    return details if return_details else tl


def delete_timeline(conn, name: str) -> bool:
    """
    Delete a timeline by name.
    
    Args:
        conn: ResolveConnection instance
        name: Timeline name
    
    Returns:
        True if successful
    
    Raises:
        APICallFailed: If timeline not found or deletion fails
    """
    count = conn.project.GetTimelineCount() or 0
    tl = None
    for i in range(1, count + 1):
        t = conn.project.GetTimelineByIndex(i)
        if t and t.GetName() == name:
            tl = t
            break

    if not tl:
        raise APICallFailed(f"Timeline '{name}' not found.")

    result = conn.media_pool.DeleteTimelines([tl])
    if result:
        conn.refresh()
        return True
    else:
        raise APICallFailed(f"Failed to delete timeline '{name}'.")


def _normalize_timeline_name(name: str, *, field: str) -> str:
    normalized = str(name or "").strip()
    if not normalized:
        raise ValidationError(
            "Timeline name is required.",
            details={field: name},
            recoverability="not_applicable",
        )
    return normalized


def _find_timeline_by_name(conn, name: str) -> tuple[object | None, int | None]:
    count = conn.project.GetTimelineCount() or 0
    for index in range(1, count + 1):
        timeline = conn.project.GetTimelineByIndex(index)
        if timeline and hasattr(timeline, "GetName") and timeline.GetName() == name:
            return timeline, index
    return None, None


def rename_timeline(
    conn,
    new_name: str,
    source_name: Optional[str] = None,
    *,
    return_details: bool = False,
) -> bool | Dict[str, Any]:
    """Rename the current timeline or a named source timeline."""
    normalized_new_name = _normalize_timeline_name(new_name, field="new_name")
    normalized_source_name = None
    if source_name is not None:
        normalized_source_name = _normalize_timeline_name(source_name, field="source_name")

    target_index = None
    if normalized_source_name:
        timeline, target_index = _find_timeline_by_name(conn, normalized_source_name)
        if timeline is None:
            raise APICallFailed(
                f"Timeline '{normalized_source_name}' not found.",
                details={"source_name": normalized_source_name},
            )
    else:
        timeline = conn.timeline
        if timeline is None:
            raise APICallFailed(
                "No current timeline to rename.",
                details={"source_name": None},
            )

    current_name = timeline.GetName() if hasattr(timeline, "GetName") else None
    existing_names = _timeline_names(conn)
    if current_name != normalized_new_name and normalized_new_name in existing_names:
        raise ValidationError(
            "Timeline name already exists.",
            details={
                "new_name": normalized_new_name,
                "source_name": normalized_source_name,
            },
            recoverability="not_applicable",
        )

    requested = {
        "new_name": normalized_new_name,
        "source_name": normalized_source_name,
    }
    source = {"kind": "timeline", "name": current_name, "index": target_index}
    target = {"kind": "timeline", "name": normalized_new_name, "index": target_index}
    pre = {"name": current_name}

    if current_name == normalized_new_name:
        set_verification_status("verified")
        set_recoverability("not_applicable")
        details = {
            "requested": requested,
            "source": source,
            "target": target,
            "pre": pre,
            "final": {"name": current_name},
            "api_result": None,
            "changed": False,
            "verified": True,
        }
        return details if return_details else True

    setter = require_api_method(
        timeline,
        "SetName",
        capability_id="timeline.rename",
        runtime_object="timeline",
    )
    try:
        result = setter(normalized_new_name)
    except Exception as exc:
        set_verification_status("failed")
        raise APICallFailed(
            "Failed to rename timeline.",
            details={
                "new_name": normalized_new_name,
                "source_name": normalized_source_name,
                "pre": current_name,
                "api_call": "Timeline.SetName",
                "error": str(exc),
            },
        ) from exc

    try:
        final_name = timeline.GetName()
    except Exception:
        final_name = None

    if final_name != normalized_new_name:
        set_verification_status("failed")
        raise APICallFailed(
            "Timeline rename could not be verified.",
            details={
                "new_name": normalized_new_name,
                "source_name": normalized_source_name,
                "pre": current_name,
                "actual_name": final_name,
                "api_result": result,
                "api_call": "Timeline.SetName",
            },
        )

    if hasattr(conn, "refresh"):
        conn.refresh()
    set_verification_status("verified")
    set_recoverability("not_applicable")
    details = {
        "requested": requested,
        "source": source,
        "target": target,
        "pre": pre,
        "final": {"name": final_name},
        "api_result": result,
        "changed": current_name != final_name,
        "verified": True,
    }
    return details if return_details else True


def _timeline_names(conn) -> set[str]:
    count = conn.project.GetTimelineCount() or 0
    names: set[str] = set()
    for i in range(1, count + 1):
        tl = conn.project.GetTimelineByIndex(i)
        if tl and hasattr(tl, "GetName"):
            name = tl.GetName()
            if name:
                names.add(name)
    return names


def _unique_timeline_import_name(conn, path: str) -> str:
    stem = Path(path).stem.strip() or "Imported Timeline"
    existing = _timeline_names(conn)
    if stem not in existing:
        return stem

    suffix = 2
    while True:
        candidate = f"{stem} {suffix}"
        if candidate not in existing:
            return candidate
        suffix += 1


def import_timeline(conn, path: str) -> object:
    """
    Import a timeline from file (EDL/XML/AAF/DRT/OTIO).
    
    Args:
        conn: ResolveConnection instance
        path: Path to timeline file
    
    Returns:
        Timeline object
    
    Raises:
        APICallFailed: If import fails
    """
    if Path(path).suffix.lower() == ".drt":
        tl = conn.media_pool.ImportTimelineFromFile(path)
    else:
        import_options = {
            "timelineName": _unique_timeline_import_name(conn, path),
        }
        tl = conn.media_pool.ImportTimelineFromFile(path, import_options)
    if tl:
        timeline_name = tl.GetName() if hasattr(tl, "GetName") else None
        if timeline_name:
            setter = getattr(conn.project, "SetCurrentTimeline", None) if getattr(conn, "project", None) else None
            if callable(setter):
                try:
                    setter(tl)
                except Exception:
                    pass
            conn.wait_for_state(
                lambda state: state["timeline"] == timeline_name,
                description=f"imported timeline '{timeline_name}' to become current",
            )
            set_verification_status("verified")
        else:
            conn.refresh()
        return tl
    else:
        raise APICallFailed(f"Failed to import timeline from: {path}")


def export_timeline(conn, path: str, format: str = "edl") -> bool:
    """
    Export the current timeline.
    
    Args:
        conn: ResolveConnection instance
        path: Output file path
        format: Export format (edl, fcpxml, aaf, otio, drt)
    
    Returns:
        True if successful
    
    Raises:
        APICallFailed: If export fails
    """
    def _export_const(attr: str, fallback: int) -> int:
        value = getattr(conn.resolve, attr, None)
        return fallback if value is None else value

    fcpxml_const = (
        getattr(conn.resolve, "EXPORT_FCPXML_1_10", None)
        or getattr(conn.resolve, "EXPORT_FCPXML_1_9", None)
        or getattr(conn.resolve, "EXPORT_FCPXML_1_8", None)
        or getattr(conn.resolve, "EXPORT_FCPXML", None)
    )

    format_map = {
        "edl": _export_const("EXPORT_EDL", 0),
        "fcpxml": 1 if fcpxml_const is None else fcpxml_const,
        "aaf": _export_const("EXPORT_AAF", 2),
        "drt": _export_const("EXPORT_DRT", 3),
        "otio": _export_const("EXPORT_OTIO", 4),
    }

    format_norm = (format or "").strip().lower()
    format_aliases = {
        "xml": "fcpxml",
    }
    format_key = format_aliases.get(format_norm, format_norm)

    fmt = format_map.get(format_key)
    if fmt is None:
        raise ValidationError(
            "Unknown timeline export format.",
            details={
                "provided_format": format,
                "normalized_format": format_norm,
                "allowed_formats": sorted(format_map.keys()),
            },
        )

    result = conn.timeline.Export(path, fmt)
    if result:
        return True
    else:
        raise APICallFailed("Failed to export timeline.")


def get_timeline_duration(conn) -> Dict[str, Any]:
    """
    Get timeline duration information.
    
    Args:
        conn: ResolveConnection instance
    
    Returns:
        Dictionary with duration info
    """
    from ..utils.timecode import timecode_to_seconds, format_duration, frames_to_seconds
    
    data = {}
    try:
        start_tc = None
        end_tc = None
        
        try:
            start_tc = conn.timeline.GetStartTimecode()
        except Exception:
            pass
        
        try:
            end_tc = conn.timeline.GetEndTimecode()
        except Exception:
            pass
        
        if start_tc:
            data["start"] = start_tc
        if end_tc:
            data["end"] = end_tc
        
        if start_tc and end_tc:
            start_s = timecode_to_seconds(start_tc, conn.fps)
            end_s = timecode_to_seconds(end_tc, conn.fps)
            dur = end_s - start_s
            data["duration_seconds"] = round(dur, 3)
            data["duration"] = format_duration(dur)
        else:
            # Fallback: calculate from last clip on any track
            max_end = 0
            for track_type in ("video", "audio"):
                count = conn.timeline.GetTrackCount(track_type) or 0
                for i in range(1, count + 1):
                    items = conn.timeline.GetItemListInTrack(track_type, i) or []
                    for item in items:
                        try:
                            end = item.GetEnd()
                            if end and int(end) > max_end:
                                max_end = int(end)
                        except Exception:
                            pass
            
            if max_end > 0:
                start_frame = conn.start_frame
                dur_frames = max_end - start_frame
                dur_s = frames_to_seconds(dur_frames, conn.fps)
                data["duration_seconds"] = round(dur_s, 3)
                data["duration"] = format_duration(dur_s)
                data["end_frame"] = max_end
            else:
                data["note"] = "Timeline appears empty."
        
        return data
    except Exception as e:
        raise APICallFailed(f"Could not get duration: {e}")


def get_timeline_settings(conn, key: Optional[str] = None) -> Any:
    """
    Get timeline settings.
    
    Args:
        conn: ResolveConnection instance
        key: Optional specific setting key
    
    Returns:
        Setting value or dict of all settings
    """
    if key:
        normalized_key = _validate_timeline_setting_key(conn, key)
        return conn.timeline.GetSetting(normalized_key)
    return conn.timeline.GetSetting()


def _setting_values_match(actual: Any, expected: str) -> bool:
    """Best-effort value comparison for DaVinci Resolve setting read-back."""
    if actual is None:
        return False

    actual_str = str(actual).strip()
    expected_str = str(expected).strip()
    if actual_str == expected_str:
        return True

    try:
        return float(actual_str) == float(expected_str)
    except (TypeError, ValueError):
        return False


_KNOWN_TIMELINE_SETTING_KEYS = {
    "timelineFrameRate",
    "timelinePlaybackFrameRate",
    "timelineResolutionWidth",
    "timelineResolutionHeight",
    "perfRenderCacheMode",
    "useCustomSettings",
}


def _validate_timeline_setting_key(conn, key: str) -> str:
    normalized = str(key or "").strip()
    if not normalized:
        raise ValidationError(
            "Timeline setting key is required.",
            details={"key": key},
            recoverability="not_applicable",
        )
    allowed = set(_KNOWN_TIMELINE_SETTING_KEYS)
    try:
        settings = conn.timeline.GetSetting()
        if isinstance(settings, dict):
            allowed.update(str(item) for item in settings.keys())
    except Exception:
        pass
    if normalized not in allowed:
        raise ValidationError(
            "Unsupported timeline setting key.",
            details={"key": key, "supported_keys": sorted(allowed)},
            recoverability="not_applicable",
        )
    return normalized


def set_timeline_setting(conn, key: str, value: str, *, return_details: bool = False) -> bool | Dict[str, Any]:
    """
    Set a timeline setting.
    
    Args:
        conn: ResolveConnection instance
        key: Setting key
        value: Setting value
    
    Returns:
        True if successful
    
    Raises:
        APICallFailed: If setting fails
    """
    normalized_key = _validate_timeline_setting_key(conn, key)
    requested = str(value)
    getter = getattr(conn.timeline, "GetSetting", None)
    try:
        before = getter(normalized_key) if callable(getter) else None
    except Exception:
        before = None

    result = conn.timeline.SetSetting(normalized_key, requested)
    if result:
        conn._update_fps()
        try:
            read_back = getter(normalized_key) if callable(getter) else requested
        except Exception:
            read_back = None
        if not _setting_values_match(read_back, requested):
            set_verification_status("failed")
            raise APICallFailed(
                f"Timeline setting {normalized_key} did not verify after setting.",
                details={
                    "key": normalized_key,
                    "requested": requested,
                    "pre": before,
                    "read_back": read_back,
                    "api_result": result,
                    "api_call": "Timeline.SetSetting",
                },
            )
        set_verification_status("verified")
        set_recoverability("not_applicable")
        details = {
            "key": normalized_key,
            "requested": requested,
            "pre": before,
            "read_back": read_back,
            "api_result": result,
            "changed": not _setting_values_match(before, read_back),
            "verified": _setting_values_match(read_back, requested),
        }
        return details if return_details else True

    read_back = None
    try:
        read_back = conn.timeline.GetSetting(normalized_key)
    except Exception:
        read_back = None

    if _setting_values_match(read_back, requested):
        conn._update_fps()
        set_verification_status("verified")
        set_recoverability("not_applicable")
        details = {
            "key": normalized_key,
            "requested": requested,
            "pre": before,
            "read_back": read_back,
            "api_result": result,
            "changed": not _setting_values_match(before, read_back),
            "verified": True,
        }
        return details if return_details else True

    set_verification_status("failed")
    raise APICallFailed(
        f"Failed to set {normalized_key}.",
        details={
            "key": normalized_key,
            "requested": requested,
            "pre": before,
            "read_back": read_back,
            "api_result": result,
            "api_call": "Timeline.SetSetting",
        },
    )


# --- Playhead operations ---

def get_playhead(conn) -> Dict[str, Any]:
    """
    Get current playhead position.
    
    Args:
        conn: ResolveConnection instance
    
    Returns:
        Dictionary with timecode, seconds, and frame
    """
    from ..utils.frame_math import parse_frame_quantity, format_frame_timecode

    tc = conn.timeline.GetCurrentTimecode()
    if not tc and hasattr(conn.timeline, "GetStartTimecode"):
        try:
            tc = conn.timeline.GetStartTimecode()
        except Exception:
            tc = None
    if not tc:
        start_frame = getattr(conn, "start_frame", None)
        if start_frame is None and hasattr(conn.timeline, "GetStartFrame"):
            try:
                start_frame = conn.timeline.GetStartFrame()
            except Exception:
                start_frame = None
        if start_frame is not None:
            tc = format_frame_timecode(int(start_frame), conn.fps)
    frame = parse_frame_quantity(tc, conn.fps, field="timecode", allow_signed=False) if tc else 0
    seconds = frame / conn.fps
    return {
        "timecode": tc,
        "seconds": round(seconds, 3),
        "frame": frame,
    }
