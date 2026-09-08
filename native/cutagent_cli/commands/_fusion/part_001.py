"""Fusion commands — direct composition manipulation via Fusion API + .setting templates."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
import time
from pathlib import Path
from typing import Optional, List, Any

import typer
from typer.core import TyperGroup

from ..confirmation import require_force_for_machine_mode
from ..connection import get_connection
from ..errors import handle_errors, APICallFailed, ValidationError, ClipNotFound, CLIError
from ..output import (
    output,
    success,
    console,
    get_output_mode,
    is_dry_run,
    dry_run_message,
    set_dry_run,
    set_execution_engine,
    set_recoverability,
    set_verification_status,
    set_capability_context,
    mutation_payload,
)
from ..policy import enforce_mutation_policy, require_api_method
from ..utils.template import (
    DEFAULT_IMAGE_PLACEHOLDERS,
    DEFAULT_STYLE_PLACEHOLDERS,
    DEFAULT_TEXT_PLACEHOLDERS,
    parse_styled_text,
    render_setting_template,
)
from ..utils.timecode import parse_time_input, seconds_to_frames
from ..utils.time_ref import parse_record_frame
from ..core import clip_ops, fusion_api, fusion_image_ops, fusion_text_ops, sdk_fusion_graph, sdk_tools, text_ops, timeline_ops
from ..core.fusion_setting_inspector import (
    inspect_setting,
    is_flow_layout_tool,
    normalized_center_to_polypath,
    polypath_to_normalized_center,
    prepare_setting_for_import,
    runtime_tool_status_from_attrs,
    setting_summary,
)

class _FusionTyperGroup(TyperGroup):
    """Route batch-style aliases without changing existing single commands."""

    def invoke(self, ctx):
        if ctx._protected_args:
            args = [*ctx._protected_args, *ctx.args]
            if len(args) >= 2 and args[0] == "insert-settings" and args[1] == "batch":
                ctx._protected_args = ["insert-settings-batch"]
                ctx.args = args[2:]
        return super().invoke(ctx)


app = typer.Typer(help="Fusion operations — direct comp manipulation, templates, styled text.", cls=_FusionTyperGroup)

ROUTE_IMPORT_FUSION_COMP = "timeline_item.ImportFusionComp"
ROUTE_NATIVE_HOLDER_IMPORT_FUSION_COMP = "timeline.InsertGeneratorIntoTimeline -> timeline_item.ImportFusionComp"
ROUTE_NATIVE_TEXTPLUS_IMPORT_FUSION_COMP = "timeline.InsertFusionTitleIntoTimeline -> timeline_item.ImportFusionComp"
ROUTE_MEDIA_POOL_HOLDER_IMPORT_FUSION_COMP = "media_pool.AppendToTimeline -> timeline_item.ImportFusionComp"
ROUTE_NATIVE_TEXTPLUS_SCRATCH_DB_IMPORT_FUSION_COMP = (
    "scratch_timeline.InsertFusionTitleIntoTimeline -> timeline_item.ImportFusionComp -> project_db.transplant_timeline_item"
)
ROUTE_NATIVE_FUSION_SCRATCH_DB_IMPORT_FUSION_COMP = (
    "scratch_timeline.InsertGeneratorIntoTimeline -> timeline_item.ImportFusionComp -> project_db.transplant_timeline_item"
)
NATIVE_PRECISE_DB_MATERIALIZE_SECONDS = 2.0
NATIVE_PRECISE_DB_MATERIALIZE_TIMEOUT_SECONDS = 12.0
NATIVE_PRECISE_DB_MATERIALIZE_POLL_SECONDS = 0.5


def _prepare_setting_import(path: str) -> dict[str, Any]:
    return prepare_setting_for_import(path)


def _layout_payload(prepared: dict[str, Any] | None) -> dict[str, Any] | None:
    if not prepared:
        return None
    return {key: value for key, value in prepared.items() if key != "cleanup_path"}


def _cleanup_prepared_setting(prepared: dict[str, Any] | None) -> dict[str, Any] | None:
    if not prepared:
        return None
    cleanup = dict(prepared.get("cleanup") or {})
    cleanup["temporary_setting_deleted"] = _delete_rendered_setting(prepared.get("cleanup_path"))
    prepared["cleanup"] = cleanup
    return _layout_payload(prepared)


def _import_verification_status(*, tool_summary: dict[str, Any], verification: dict[str, Any]) -> str:
    if tool_summary.get("accessible") is False:
        return "partial"
    if tool_summary.get("tool_count") == 0:
        return "failed"
    if not all(
        verification.get(key, True)
        for key in ("track_ok", "start_ok", "duration_ok")
    ):
        return "pending_manual"
    return "partial"


def _parse_positive_duration_frames(value: str | int | float, fps: float) -> int:
    duration_frames = seconds_to_frames(parse_time_input(str(value), fps), fps)
    if duration_frames <= 0:
        raise ValidationError("duration must be greater than 0.", details={"duration": value, "fps": fps})
    return duration_frames


def _apply_timeline_item_name_and_duration(item: Any, *, name: str, duration_frames: int) -> dict[str, Any]:
    from ..core.timeline_item_mutation import apply_timeline_item_name_and_duration

    return apply_timeline_item_name_and_duration(item, name=name, duration_frames=duration_frames)


def _timeline_item_start(item: Any) -> int | None:
    from ..core.timeline_item_mutation import timeline_item_start

    return timeline_item_start(item)


def _timeline_item_end(item: Any) -> int | None:
    from ..core.timeline_item_mutation import timeline_item_end

    return timeline_item_end(item)


def _timeline_item_duration(item: Any) -> int | None:
    from ..core.timeline_item_mutation import timeline_item_duration

    return timeline_item_duration(item)


def _ensure_video_track(conn, track_index: int) -> dict[str, Any]:
    if track_index < 1:
        raise ValidationError("Track must be 1 or greater.", details={"track": track_index})
    timeline = conn.timeline
    try:
        before = int(timeline.GetTrackCount("video") or 0)
    except Exception:
        before = 0
    added = 0
    count = before
    while count < track_index:
        result = timeline.AddTrack("video")
        if result is False:
            raise APICallFailed(
                "Failed to add required video track.",
                details={"track": track_index, "current_video_tracks": count, "api_call": "Timeline.AddTrack"},
            )
        added += 1
        try:
            count = int(timeline.GetTrackCount("video") or 0)
        except Exception:
            count += 1
        if added > track_index + 5:
            raise APICallFailed(
                "Unable to verify required video track after adding tracks.",
                details={"track": track_index, "current_video_tracks": count},
            )
    return {"requested_track": track_index, "pre_video_tracks": before, "final_video_tracks": count, "added_tracks": added}


def _media_pool_item_name(item: Any) -> str:
    try:
        name = item.GetName()
        if name:
            return str(name)
    except Exception:
        pass
    return ""


_TIMELINE_TRANSITION_NAMES = {
    "cross dissolve",
    "dip to color dissolve",
    "smooth cut",
    "additive dissolve",
    "blur dissolve",
    "cross iris",
    "dip to color",
}


def _looks_like_timeline_transition_item(item: Any) -> bool:
    """DaVinci Resolve exposes transitions as short timeline items; do not target them for Fusion edits."""
    name = _media_pool_item_name(item).strip().lower()
    if not name:
        return False
    return name in _TIMELINE_TRANSITION_NAMES or name.endswith(" dissolve")


def _iter_media_pool_folder(folder: Any):
    if folder is None:
        return
    try:
        clips = folder.GetClipList() or []
    except Exception:
        clips = []
    for clip in clips:
        yield clip
    try:
        subfolders = folder.GetSubFolderList() or []
    except Exception:
        subfolders = []
    for subfolder in subfolders:
        yield from _iter_media_pool_folder(subfolder)


def _holder_name_candidates(holder: str, holder_kind: str) -> list[str]:
    kind = str(holder_kind or "fusion").strip().lower().replace("_", "-")
    if kind not in {"fusion", "textplus"}:
        raise ValidationError(
            "Unsupported holder kind.",
            details={"holder_kind": holder_kind, "allowed": ["fusion", "textplus"]},
        )
    names = [str(holder or "").strip()]
    if kind == "fusion":
        names.extend(["Fusion Composition", "Fusion Title", "Subtitle", "Title", "Default Title"])
    elif kind == "textplus":
        names.extend(["Text+", "Text Plus", "Fusion Title", "Title", "Default Title"])
    seen = set()
    ordered = []
    for name in names:
        if name and name not in seen:
            seen.add(name)
            ordered.append(name)
    return ordered


def _find_media_pool_item_by_names(conn, names: list[str]) -> tuple[Any | None, dict[str, Any]]:
    media_pool = getattr(conn, "media_pool", None)
    if media_pool is None:
        return None, {"searched_names": names, "searched": False, "reason": "missing_media_pool"}
    folders = []
    try:
        current = media_pool.GetCurrentFolder()
        if current is not None:
            folders.append(("current", current))
    except Exception:
        pass
    try:
        root = media_pool.GetRootFolder()
        if root is not None:
            folders.append(("root", root))
    except Exception:
        pass

    for scope, folder in folders:
        for item in _iter_media_pool_folder(folder):
            item_name = _media_pool_item_name(item)
            if item_name in names:
                return item, {"searched_names": names, "matched_name": item_name, "scope": scope}
    return None, {"searched_names": names, "searched": True, "scopes": [scope for scope, _folder in folders]}


def _find_timeline_item_by_track_record(conn, track_index: int, record_frame: int, name: str | None = None) -> Any | None:
    try:
        items = conn.timeline.GetItemListInTrack("video", track_index) or []
    except Exception:
        items = []
    for item in items:
        start = _timeline_item_start(item)
        if start != int(record_frame):
            continue
        if name:
            item_name = _media_pool_item_name(item)
            if item_name and item_name != name:
                continue
        return item
    return None


def _append_holder_to_timeline(conn, holder_item: Any, *, record_frame: int, duration_frames: int, track_index: int, name: str | None = None) -> tuple[Any | None, dict[str, Any]]:
    clip_info = {
        "mediaPoolItem": holder_item,
        "startFrame": 0,
        "endFrame": duration_frames,
        "trackIndex": track_index,
        "recordFrame": record_frame,
        "trackType": "video",
    }
    append_result = conn.media_pool.AppendToTimeline([clip_info])
    if not append_result:
        return None, {"clip_info": {**clip_info, "mediaPoolItem": _media_pool_item_name(holder_item)}, "append_result": append_result}
    if isinstance(append_result, list) and append_result:
        return append_result[0], {"clip_info": {**clip_info, "mediaPoolItem": _media_pool_item_name(holder_item)}, "append_result_count": len(append_result), "fallback_used": False}
    found = _find_timeline_item_by_track_record(conn, track_index, record_frame, name=name)
    return found, {"clip_info": {**clip_info, "mediaPoolItem": _media_pool_item_name(holder_item)}, "append_result_count": None, "fallback_used": True}


def _safe_delete_timeline_item(conn, item: Any) -> dict[str, Any]:
    if item is None:
        return {"attempted": False}
    items = list(item) if isinstance(item, (list, tuple, set)) else [item]
    if not items:
        return {"attempted": False, "reason": "No timeline items provided"}
    deleter = getattr(conn.timeline, "DeleteClips", None)
    if not callable(deleter):
        return {"attempted": False, "reason": "Timeline.DeleteClips unavailable"}
    try:
        result = deleter(items, False)
        return {"attempted": True, "api_result": result, "used_non_ripple_argument": True, "requested_count": len(items)}
    except TypeError:
        try:
            result = deleter(items)
            return {"attempted": True, "api_result": result, "used_non_ripple_argument": False, "fallback_used": True, "requested_count": len(items)}
        except Exception as exc:
            return {"attempted": True, "error": str(exc), "requested_count": len(items)}
    except Exception as exc:
        return {"attempted": True, "error": str(exc), "requested_count": len(items)}


def _timeline_delete_failed(result: dict[str, Any]) -> bool:
    return (
        not result.get("attempted")
        or result.get("api_result") is False
        or bool(result.get("error"))
        or bool(result.get("reason"))
    )


def _apply_timeline_item_position(item: Any, x: float | None, y: float | None) -> dict[str, Any]:
    requested = {"x": x, "y": y}
    result: dict[str, Any] = {"requested": requested, "applied": False, "x_applied": None, "y_applied": None}
    setter = getattr(item, "SetProperty", None)
    if not callable(setter):
        result["reason"] = "SetProperty unavailable"
        return result
    if x is not None:
        for key in ("Pan", "PositionX", "TransformPan", "CenterX"):
            try:
                if setter(key, float(x)):
                    result["x_applied"] = key
                    break
            except Exception:
                continue
    if y is not None:
        for key in ("Tilt", "PositionY", "TransformTilt", "CenterY"):
            try:
                if setter(key, float(y)):
                    result["y_applied"] = key
                    break
            except Exception:
                continue
    result["applied"] = (x is None or result["x_applied"] is not None) and (y is None or result["y_applied"] is not None)
    return result


def _timeline_item_readback(item: Any, *, track_index: int | None = None) -> dict[str, Any]:
    item_id = None
    for method_name in ("GetUniqueId", "GetUniqueID", "GetMediaId", "GetMediaID", "GetId", "GetID"):
        getter = getattr(item, method_name, None)
        if not callable(getter):
            continue
        try:
            value = getter()
        except Exception:
            continue
        if value not in (None, ""):
            item_id = str(value)
            break
    data = {
        "name": _media_pool_item_name(item) or None,
        "track_type": "video" if track_index is not None else None,
        "track_index": track_index,
        "start": _timeline_item_start(item),
        "end": _timeline_item_end(item),
        "duration": _timeline_item_duration(item),
        "timeline_item_id": item_id,
    }
    if hasattr(item, "GetTrackTypeAndIndex"):
        try:
            item_track_type, item_track_index = item.GetTrackTypeAndIndex()
            data["track_type"] = item_track_type
            data["track_index"] = item_track_index
        except Exception:
            pass
    return data


def _timeline_item_signature(readback: dict[str, Any]) -> tuple[Any, Any, Any, Any]:
    return (readback.get("name"), readback.get("start"), readback.get("end"), readback.get("duration"))


def _timeline_track_item_signatures(conn: Any, track: int) -> set[tuple[Any, Any, Any, Any]]:
    try:
        items = conn.timeline.GetItemListInTrack("video", int(track)) or []
    except Exception:
        return set()
    signatures = set()
    for item in items:
        signatures.add(_timeline_item_signature(_timeline_item_readback(item, track_index=int(track))))
    return signatures


def _timeline_total_video_item_count(conn: Any) -> int:
    timeline = getattr(conn, "timeline", None)
    if timeline is None:
        return 0
    try:
        track_count = int(timeline.GetTrackCount("video") or 0)
    except Exception:
        return 0
    total = 0
    for index in range(1, track_count + 1):
        try:
            total += len(timeline.GetItemListInTrack("video", index) or [])
        except Exception:
            continue
    return total


def _activate_timeline_by_name(conn: Any, timeline_name: str | None) -> bool:
    if not timeline_name:
        return False
    project = getattr(conn, "project", None)
    if project is None:
        return False
    setter = getattr(project, "SetCurrentTimeline", None)
    if not callable(setter):
        return False
    try:
        count = int(project.GetTimelineCount() or 0)
    except Exception:
        return False
    for index in range(1, count + 1):
        timeline = project.GetTimelineByIndex(index)
        if timeline and _timeline_name(timeline) == timeline_name:
            setter(timeline)
            conn.refresh()
            return True
    return False


def _settle_empty_textplus_overlay_track_context(conn: Any) -> tuple[Any, dict[str, Any]]:
    from ..connection import ResolveConnection
    from ..runtime_health import close_current_project_with_runtime_health

    project = getattr(conn, "project", None)
    project_manager = getattr(conn, "project_manager", None)
    timeline_name = _timeline_name(getattr(conn, "timeline", None))
    project_name = project.GetName() if project is not None and hasattr(project, "GetName") else None
    if not project_name or not timeline_name or project_manager is None:
        raise APICallFailed(
            "Cannot settle empty Text+ timeline context before precise insertion.",
            details={"project_name": project_name, "timeline_name": timeline_name},
            recoverability="manual",
        )

    summary: dict[str, Any] = {
        "attempted": True,
        "reason": "fresh_empty_textplus_overlay_track_context",
        "project": project_name,
        "timeline": timeline_name,
        "steps": [],
    }
    save_project = getattr(project, "SaveProject", None)
    if callable(save_project):
        try:
            summary["save_result"] = save_project()
            summary["steps"].append("save_project")
        except Exception as exc:
            summary["save_error"] = str(exc)

    close_state = close_current_project_with_runtime_health(
        conn,
        project_name=project_name,
        description=f"project '{project_name}' to settle fresh empty Text+ timeline",
    )
    summary["close_state"] = close_state
    summary["steps"].append("close_project")

    ResolveConnection.reset()
    fresh_conn = ResolveConnection.get()
    fresh_conn.connect()
    loaded = fresh_conn.project_manager.LoadProject(project_name)
    summary["loaded"] = bool(loaded)
    if not loaded:
        raise APICallFailed(
            "DaVinci Resolve could not reopen the project while settling empty Text+ timeline context.",
            details=summary,
            recoverability="manual",
        )
    summary["steps"].append("reopen_project")
    try:
        fresh_conn.wait_for_state(
            lambda state: state["project"] == project_name,
            description=f"project '{project_name}' to reopen before Text+ insertion",
        )
    except Exception as exc:
        summary["wait_error"] = str(exc)
        fresh_conn.refresh()
    activated = _activate_timeline_by_name(fresh_conn, timeline_name)
    summary["timeline_restored"] = bool(activated)
    if not activated:
        raise APICallFailed(
            "DaVinci Resolve could not restore the timeline while settling empty Text+ timeline context.",
            details=summary,
            recoverability="manual",
        )
    summary["steps"].append("restore_timeline")
    try:
        summary["post_video_tracks"] = int(fresh_conn.timeline.GetTrackCount("video") or 0)
    except Exception:
        summary["post_video_tracks"] = None
    return fresh_conn, summary


def _can_settle_empty_textplus_overlay_track_context(conn: Any) -> bool:
    project = getattr(conn, "project", None)
    project_manager = getattr(conn, "project_manager", None)
    timeline_name = _timeline_name(getattr(conn, "timeline", None))
    project_name = project.GetName() if project is not None and hasattr(project, "GetName") else None
    return bool(
        project_name
        and timeline_name
        and project_manager is not None
        and callable(getattr(project_manager, "CloseProject", None))
        and callable(getattr(project_manager, "LoadProject", None))
    )


def _timeline_name(timeline: Any) -> str | None:
    getter = getattr(timeline, "GetName", None)
    if not callable(getter):
        return None
    try:
        value = getter()
    except Exception:
        return None
    return str(value).strip() or None


def _normalize_optional_string(value: Any) -> str | None:
    if isinstance(value, typer.models.OptionInfo):
        return None
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _option_value(value: Any, default: Any = None) -> Any:
    return default if isinstance(value, typer.models.OptionInfo) else value


def _selector_payload(*, clip_name: str | None, track: int | None, record_frame: Any | None) -> dict[str, Any]:
    track = _option_value(track)
    record_frame = _option_value(record_frame)
    payload: dict[str, Any] = {}
    if clip_name:
        payload["clip"] = clip_name
    if track is not None:
        payload["track"] = int(track)
    if record_frame is not None:
        payload["record_frame"] = record_frame
    if not payload:
        payload["current"] = True
    return payload


def _record_frame_candidates(conn: Any, record_frame: int) -> set[int]:
    candidates = {int(record_frame)}
    try:
        timeline_start = int(getattr(conn, "start_frame", 0) or 0)
    except Exception:
        timeline_start = 0
    if timeline_start:
        candidates.add(int(record_frame) - timeline_start)
    timeline = getattr(conn, "timeline", None)
    if timeline is not None and hasattr(timeline, "GetStartFrame"):
        try:
            start_frame = int(timeline.GetStartFrame() or 0)
        except Exception:
            start_frame = 0
        if start_frame:
            candidates.add(int(record_frame) - start_frame)
    return candidates


def _validate_target_selector(clip_name: str | None, track: int | None, record_frame: str | int | None) -> None:
    track = _option_value(track)
    record_frame = _option_value(record_frame)
    if (track is None) != (record_frame is None):
        raise ValidationError(
            "Use --track and --record-frame together.",
            details={"clip": clip_name, "track": track, "record_frame": record_frame},
        )
    if track is not None and int(track) < 1:
        raise ValidationError("Track must be 1 or greater.", details={"track": track})
    if clip_name and track is not None:
        raise ValidationError(
            "Use either --clip or --track with --record-frame, not both.",
            details={"clip": clip_name, "track": track, "record_frame": record_frame},
        )


def _resolve_timeline_item(
    conn: Any,
    *,
    clip_name: str | None,
    track: int | None,
    record_frame: str | int | None,
) -> tuple[Any, dict[str, Any]]:
    track = _option_value(track)
    record_frame = _option_value(record_frame)
    normalized_clip = _normalize_optional_string(clip_name)
    _validate_target_selector(normalized_clip, track, record_frame)

    if normalized_clip:
        item = clip_ops.cutagent_clip(conn, normalized_clip)
        return item, {"kind": "clip", "clip": normalized_clip}

    if track is not None and record_frame is not None:
        resolved_record = parse_record_frame(str(record_frame), conn.fps, getattr(conn, "start_frame", 0))
        try:
            items = conn.timeline.GetItemListInTrack("video", int(track)) or []
        except Exception:
            items = []
        matches = []
        candidates = _record_frame_candidates(conn, resolved_record)
        for item in items:
            start = _timeline_item_start(item)
            end = _timeline_item_end(item)
            if start is None or end is None:
                continue
            if any(start <= candidate < end for candidate in candidates):
                matches.append(item)
        non_transition_matches = [item for item in matches if not _looks_like_timeline_transition_item(item)]
        if len(non_transition_matches) == 1:
            return non_transition_matches[0], {
                "kind": "track_record",
                "track": int(track),
                "record_frame": resolved_record,
                "filtered_transition_matches": len(matches) - 1,
            }
        if len(non_transition_matches) > 1:
            matches = non_transition_matches
        if not matches:
            raise ClipNotFound(
                "No video timeline item matched track and record frame.",
                details={"track": int(track), "record_frame": resolved_record, "record_frame_candidates": sorted(candidates)},
            )
        if len(matches) > 1:
            raise ValidationError(
                "Multiple video timeline items matched track and record frame.",
                details={"track": int(track), "record_frame": resolved_record, "match_count": len(matches)},
            )
        return matches[0], {"kind": "track_record", "track": int(track), "record_frame": resolved_record}

    item = clip_ops.cutagent_clip(conn, None)
    return item, {"kind": "current"}


def _load_batch_entries(path: str, *, allowed_container_keys: tuple[str, ...] = ("entries", "items", "updates", "batch")) -> list[dict[str, Any]]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValidationError("Cannot read Fusion batch JSON.", details={"path": path, "error": str(exc)}) from exc
    except json.JSONDecodeError as exc:
        raise ValidationError("Fusion batch file must be valid JSON.", details={"path": path, "error": str(exc)}) from exc

    if isinstance(payload, dict):
        for key in allowed_container_keys:
            if isinstance(payload.get(key), list):
                payload = payload[key]
                break
    if not isinstance(payload, list):
        raise ValidationError(
            "Fusion batch file must be a JSON array or an object with entries/items/updates/batch.",
            details={"path": path},
        )
    if not payload:
        raise ValidationError("Fusion batch file must contain at least one entry.", details={"path": path})
    entries: list[dict[str, Any]] = []
    for index, entry in enumerate(payload):
        if not isinstance(entry, dict):
            raise ValidationError(
                "Each Fusion batch entry must be a JSON object.",
                details={"path": path, "index": index, "entry": entry},
            )
        entries.append(dict(entry))
    return entries


def _exception_payload(exc: Exception) -> dict[str, Any]:
    if isinstance(exc, CLIError):
        return {
            "code": exc.code,
            "message": str(exc),
            "details": getattr(exc, "details", {}),
            "recoverability": getattr(exc, "recoverability", "fatal"),
        }
    return {"code": "INTERNAL_ERROR", "message": str(exc), "details": {"type": exc.__class__.__name__}, "recoverability": "fatal"}


def _normalize_nested_match_name(value: Any) -> str:
    text = str(value or "").strip().lower()
    if " (" in text:
        text = text.split(" (", 1)[0].strip()
    while text and text[-1].isdigit():
        text = text[:-1].rstrip()
    return text


def _open_nested_timeline(conn: Any, item: Any) -> dict[str, Any]:
    project = getattr(conn, "project", None)
    if project is None:
        raise APICallFailed("DaVinci Resolve project handle is unavailable for nested timeline update.")
    original_timeline = None
    if hasattr(project, "GetCurrentTimeline"):
        try:
            original_timeline = project.GetCurrentTimeline()
        except Exception:
            original_timeline = getattr(conn, "timeline", None)
    else:
        original_timeline = getattr(conn, "timeline", None)

    media_pool_item = item.GetMediaPoolItem() if hasattr(item, "GetMediaPoolItem") else None
    if media_pool_item is None:
        raise APICallFailed("Target clip has no Media Pool item; cannot open nested timeline.")

    nested_timeline = None
    opened_via = None
    getter = getattr(media_pool_item, "GetTimeline", None)
    if callable(getter):
        try:
            nested_timeline = getter()
        except Exception:
            nested_timeline = None
        if nested_timeline is not None:
            opened_via = "GetTimeline"
    if nested_timeline is None:
        opener = getattr(media_pool_item, "OpenInTimeline", None)
        if callable(opener):
            open_result = opener()
            if open_result is False:
                raise APICallFailed("OpenInTimeline failed for the nested compound clip.")
            current_getter = getattr(project, "GetCurrentTimeline", None)
            if callable(current_getter):
                nested_timeline = current_getter()
                if nested_timeline is not None:
                    opened_via = "OpenInTimeline"
    if nested_timeline is None:
        raise APICallFailed(
            "Could not resolve the nested timeline for the target clip.",
            details={"clip": _media_pool_item_name(item) or None},
        )
    if hasattr(project, "SetCurrentTimeline"):
        try:
            project.SetCurrentTimeline(nested_timeline)
        except Exception:
            pass
    return {
        "project": project,
        "original_timeline": original_timeline,
        "nested_timeline": nested_timeline,
        "opened_via": opened_via or "GetTimeline",
    }


def _restore_original_timeline(project: Any, original_timeline: Any) -> bool:
    setter = getattr(project, "SetCurrentTimeline", None)
    if not callable(setter) or original_timeline is None:
        return False
    try:
        result = setter(original_timeline)
    except Exception:
        return False
    return result is not False


def _collect_nested_text_items(nested_timeline: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        track_count = int(nested_timeline.GetTrackCount("video") or 0)
    except Exception:
        track_count = 0
    for track_index in range(1, track_count + 1):
        try:
            items = nested_timeline.GetItemListInTrack("video", track_index) or []
        except Exception:
            items = []
        for item in items:
            rows.append(
                {
                    "item": item,
                    "track_index": track_index,
                    "name": _media_pool_item_name(item) or _normalize_optional_string(getattr(item, "GetName", lambda: None)()),
                    "normalized_name": _normalize_nested_match_name(_media_pool_item_name(item) or _normalize_optional_string(getattr(item, "GetName", lambda: None)())),
                }
            )
    return rows


def _select_nested_text_targets(
    text_items: list[dict[str, Any]],
    *,
    header_clip_name: str | None,
    body_clip_name: str | None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    normalized_header = _normalize_nested_match_name(header_clip_name)
    normalized_body = _normalize_nested_match_name(body_clip_name)
    header_item = next((row for row in text_items if normalized_header and row["normalized_name"].startswith(normalized_header)), None)
    body_item = next((row for row in text_items if normalized_body and row["normalized_name"].startswith(normalized_body)), None)
    if body_item is None and text_items:
        body_item = text_items[0]
    if header_item is None and text_items:
        header_item = text_items[-1]
        if body_item is not None and header_item["item"] is body_item["item"] and len(text_items) > 1:
            header_item = text_items[-2]
    return header_item, body_item


def _runtime_tool_output_probe(tool: Any, *, time: int = 0) -> dict[str, Any]:
    finder = getattr(tool, "FindMainOutput", None)
    if not callable(finder):
        return {"attempted": False, "reason": "FindMainOutput unavailable"}
    try:
        output_socket = finder(1)
    except Exception as exc:
        return {"attempted": True, "output_found": False, "error": str(exc)}
    if not output_socket:
        return {"attempted": True, "output_found": False, "error": None}
    getter = getattr(output_socket, "GetValue", None)
    if not callable(getter):
        return {"attempted": True, "output_found": True, "value_readable": False, "reason": "GetValue unavailable"}
    try:
        value = getter(time)
    except Exception as exc:
        return {"attempted": True, "output_found": True, "value_readable": False, "error": str(exc)}
    return {
        "attempted": True,
        "output_found": True,
        "value_readable": value is not None,
        "value_type": type(value).__name__ if value is not None else None,
    }


def _summarize_imported_fusion_tools(item: Any, *, include_diagnostics: bool = False) -> dict[str, Any]:
    summary: dict[str, Any] = {"tools": [], "tool_count": None}
    try:
        if hasattr(item, "GetFusionCompCount"):
            summary["comp_count"] = int(item.GetFusionCompCount())
    except Exception:
        pass

    comp = None
    if hasattr(item, "GetFusionCompByIndex"):
        try:
            comp = item.GetFusionCompByIndex(1)
        except Exception:
            comp = None
    if comp is None and hasattr(item, "GetFusionCompByName"):
        try:
            comp = item.GetFusionCompByName("Composition 1")
        except Exception:
            comp = None
    if comp is None:
        summary["accessible"] = False
        return summary

    summary["accessible"] = True
    getter = getattr(comp, "GetToolList", None)
    if not callable(getter):
        return summary
    try:
        tool_list = getter(False) or {}
    except TypeError:
        tool_list = getter() or {}
    except Exception:
        tool_list = {}

    tools = []
    values = tool_list.values() if hasattr(tool_list, "values") else tool_list
    node_errors = []
    node_unknowns = []
    node_status_verified = True
    node_probe_verified = True
    for key, tool in enumerate(values):
        name = None
        reg_id = None
        attrs = {}
        attrs_error = None
        try:
            name = getattr(tool, "Name", None)
        except Exception:
            name = None
        try:
            attrs = tool.GetAttrs() if hasattr(tool, "GetAttrs") else {}
            reg_id = attrs.get("TOOLS_RegID") or attrs.get("REGS_ID")
            name = name or attrs.get("TOOLS_Name") or attrs.get("TOOLS_ID")
        except Exception as exc:
            attrs = {}
            attrs_error = str(exc)
        row = {"name": str(name or f"Tool{key + 1}"), "type": str(reg_id or "unknown")}
        row["is_flow_tool"] = is_flow_layout_tool(row["type"])
        if include_diagnostics:
            if attrs_error:
                status = {
                    "name": row["name"],
                    "type": row["type"],
                    "attrs_readable": False,
                    "status_detection": "attrs_error",
                    "status_attrs": {},
                    "error_indicators": [{"key": "GetAttrs", "value": attrs_error}],
                    "ok": False,
                }
            else:
                status = runtime_tool_status_from_attrs(row["name"], row["type"], attrs)
            if not row["is_flow_tool"]:
                if status.get("status_detection") == "no_status_attrs_exposed":
                    status = {**status, "status_detection": "skipped_helper_tool"}
                row["runtime_status"] = status
                row["output_probe"] = {
                    "attempted": False,
                    "skipped": True,
                    "reason": "helper_or_modifier_tool_not_part_of_flow_health",
                }
                if not status.get("attrs_readable", True) or not status.get("ok", True):
                    node_status_verified = False
                if not status.get("ok", True):
                    node_errors.append(
                        {
                            "name": row["name"],
                            "type": row["type"],
                            "source": "tool_attrs",
                            "indicators": status.get("error_indicators", []),
                        }
                    )
                tools.append(row)
                continue
            output_probe = _runtime_tool_output_probe(tool)
            row["runtime_status"] = status
            row["output_probe"] = output_probe
            if status.get("status_detection") == "no_status_attrs_exposed":
                node_status_verified = False
                node_unknowns.append(
                    {
                        "name": row["name"],
                        "type": row["type"],
                        "source": "tool_attrs",
                        "reason": "no_status_attrs_exposed",
                    }
                )
            elif not status.get("attrs_readable", True):
                node_status_verified = False
            elif not status.get("ok", True):
                node_status_verified = False
            if output_probe.get("error") or output_probe.get("value_readable") is False:
                node_probe_verified = False
            if output_probe.get("attempted") is not True:
                node_probe_verified = False
                node_unknowns.append(
                    {
                        "name": row["name"],
                        "type": row["type"],
                        "source": "main_output_probe",
                        "reason": output_probe.get("reason") or "output_probe_not_attempted",
                    }
                )
            elif output_probe.get("output_found") is False and not output_probe.get("error"):
                node_probe_verified = False
                node_unknowns.append(
                    {
                        "name": row["name"],
                        "type": row["type"],
                        "source": "main_output_probe",
                        "reason": "main_output_not_found",
                    }
                )
            elif output_probe.get("value_readable") is False and not output_probe.get("error"):
                node_unknowns.append(
                    {
                        "name": row["name"],
                        "type": row["type"],
                        "source": "main_output_probe",
                        "reason": output_probe.get("reason") or "output_value_unreadable",
                    }
                )
            if not status.get("ok", True):
                node_errors.append(
                    {
                        "name": row["name"],
                        "type": row["type"],
                        "source": "tool_attrs",
                        "indicators": status.get("error_indicators", []),
                    }
                )
            if output_probe.get("error"):
                node_errors.append(
                    {
                        "name": row["name"],
                        "type": row["type"],
                        "source": "main_output_probe",
                        "error": output_probe.get("error"),
                    }
                )
        tools.append(row)

    summary["tools"] = tools
    summary["tool_count"] = len(tools)
    if include_diagnostics:
        summary["node_status_verified"] = node_status_verified
        summary["node_probe_verified"] = node_probe_verified
        summary["node_error_count"] = len(node_errors)
        summary["node_errors"] = node_errors
        summary["node_unknown_count"] = len(node_unknowns)
        summary["node_unknowns"] = node_unknowns
    return summary
