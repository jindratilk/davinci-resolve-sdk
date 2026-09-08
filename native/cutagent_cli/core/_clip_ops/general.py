from __future__ import annotations

from typing import Any, Optional

from ...errors import APICallFailed, ValidationError
from ...policy import require_any_api_method, require_api_method


def _cutagent_clips_by_names(conn, names: list[str], *, ops_module) -> list[object]:
    items: list[object] = []
    for name in names:
        item = ops_module.cutagent_clip(conn, ops_module.normalize_explicit_clip_name(name, field="clip_names"))
        items.append(item)
    return items


def _clip_display_name(item, fallback: Optional[str] = None) -> Optional[str]:
    if hasattr(item, "GetName"):
        try:
            value = item.GetName()
            if value:
                return str(value)
        except Exception:
            pass
    return fallback


def normalize_explicit_clip_name(name: str, *, field: str = "clip_name") -> str:
    if name is None:
        raise ValidationError("Clip name is required.", details={"field": field}, recoverability="not_applicable")
    normalized = str(name).strip()
    if not normalized:
        raise ValidationError(
            "Clip name must not be empty.",
            details={"field": field},
            recoverability="not_applicable",
        )
    return normalized


def plan_clips_linked(conn, clip_names: list[str], linked: bool, *, ops_module) -> dict[str, Any]:
    normalized_names = [ops_module.normalize_explicit_clip_name(name, field="clip_names") for name in clip_names]
    items = ops_module._cutagent_clips_by_names(conn, normalized_names)
    resolved_names = [
        ops_module._clip_display_name(item, fallback=name) or name
        for item, name in zip(items, normalized_names)
    ]
    return {
        "operation": "link" if linked else "unlink",
        "linked": bool(linked),
        "clip_count": len(resolved_names),
        "clips": resolved_names,
    }


def _timeline_item_identity(item: Any) -> Any:
    getter = getattr(item, "GetUniqueId", None)
    if callable(getter):
        try:
            unique_id = getter()
        except Exception:
            unique_id = None
        if unique_id:
            return ("uid", str(unique_id))
    return ("object", id(item))


def _expand_unlink_items_with_current_links(items: list[Any]) -> list[Any]:
    expanded: list[Any] = []
    seen: set[Any] = set()

    def _add(item: Any) -> None:
        key = _timeline_item_identity(item)
        if key in seen:
            return
        seen.add(key)
        expanded.append(item)

    for item in items:
        _add(item)
    for item in list(items):
        getter = getattr(item, "GetLinkedItems", None)
        if not callable(getter):
            continue
        try:
            linked_items = getter() or []
        except Exception:
            continue
        for linked_item in linked_items:
            _add(linked_item)
    return expanded


def _set_clip_enabled(conn, name: Optional[str], enabled: bool, *, ops_module) -> dict[str, Any]:
    item = ops_module.cutagent_clip(conn, name)
    setter = require_api_method(
        item,
        "SetClipEnabled",
        capability_id="clip.enable_disable",
        runtime_object="timeline_item",
    )
    result = setter(enabled)
    if result is False:
        raise APICallFailed(
            "Failed to update clip enabled state.",
            details={"clip": name, "enabled": enabled},
        )

    getter = require_api_method(
        item,
        "GetClipEnabled",
        capability_id="clip.enable_disable",
        runtime_object="timeline_item",
    )
    readback = getter()
    normalized_readback = readback
    if isinstance(readback, (int, float)):
        normalized_readback = bool(readback)
    elif isinstance(readback, str):
        lowered = readback.strip().lower()
        if lowered in {"true", "1", "yes"}:
            normalized_readback = True
        elif lowered in {"false", "0", "no"}:
            normalized_readback = False
    verified = normalized_readback is enabled
    if not verified:
        raise APICallFailed(
            "Clip enabled-state readback did not match the requested value.",
            details={"clip": name, "expected": enabled, "actual": readback},
            recoverability="manual",
        )
    return {
        "clip": _clip_display_name(item, fallback=name),
        "enabled": enabled,
        "result": result is not False,
        "readback": readback,
        "verified": True,
    }


def enable_clip(conn, name: Optional[str], *, ops_module) -> dict[str, Any]:
    return _set_clip_enabled(conn, name, True, ops_module=ops_module)


def disable_clip(conn, name: Optional[str], *, ops_module) -> dict[str, Any]:
    return _set_clip_enabled(conn, name, False, ops_module=ops_module)


def rename_clip(conn, old_name: str, new_name: str, *, ops_module) -> bool:
    item = ops_module.cutagent_clip(conn, old_name)

    renamed = False
    if hasattr(item, "SetName"):
        try:
            item.SetName(new_name)
            renamed = True
        except Exception:
            pass

    if not renamed:
        try:
            item.SetProperty("Clip Name", new_name)
            renamed = True
        except Exception:
            pass

    if renamed:
        return True
    raise APICallFailed("Failed to rename clip.")


def set_clips_linked(conn, clip_names: list[str], linked: bool, *, ops_module) -> bool:
    normalized_names = [ops_module.normalize_explicit_clip_name(name, field="clip_names") for name in clip_names]
    items = ops_module._cutagent_clips_by_names(conn, normalized_names)
    operation_items = items if linked else _expand_unlink_items_with_current_links(items)

    timeline_method = getattr(conn.timeline, "SetClipsLinked", None)
    if callable(timeline_method):
        result = timeline_method(operation_items, linked)
        if result is False:
            raise APICallFailed("SetClipsLinked failed.", details={"clips": normalized_names, "linked": linked})
        return True

    _, method = require_any_api_method(
        operation_items[0],
        ("SetClipsLinked",),
        capability_id="clip.link_unlink",
        runtime_object="timeline_item",
    )
    result = method(operation_items, linked)
    if result is False:
        raise APICallFailed("SetClipsLinked failed.", details={"clips": normalized_names, "linked": linked})
    return True


def unlink_clip(conn, clip_name: str, *, ops_module) -> bool:
    return ops_module.set_clips_linked(conn, [ops_module.normalize_explicit_clip_name(clip_name)], False)


def stabilize_clip(conn, clip_name: Optional[str] = None, *, ops_module) -> bool:
    item = ops_module.cutagent_clip(conn, clip_name)
    _, method = require_any_api_method(
        item,
        ("Stabilize",),
        capability_id="clip.stabilize",
        runtime_object="timeline_item",
    )
    result = method()
    if result is False:
        raise APICallFailed("Stabilize failed.", details={"clip": clip_name})
    return True


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
    ops_module,
) -> dict[str, Any]:
    from ..smart_reframe_operation import run_smart_reframe

    return run_smart_reframe(
        conn,
        clip_name=clip_name,
        item_id=item_id,
        track=track,
        record_frame=record_frame,
        operation_id=operation_id,
        progress_file=progress_file,
        cancel_request_file=cancel_request_file,
        proof_dir=proof_dir,
        poll_ms=poll_ms,
    )


def create_magic_mask(
    conn,
    clip_name: Optional[str] = None,
    mode: str = "BI",
    track: int | None = None,
    record_frame: str | int | None = None,
    *,
    ops_module,
) -> dict[str, Any]:
    item = ops_module.cutagent_clip_by_selector(conn, clip_name, track=track, record_frame=record_frame)
    normalized_mode = str(mode).strip().upper()
    if normalized_mode not in {"F", "B", "BI"}:
        raise ValidationError(
            "Magic mask mode must be one of F, B, or BI.",
            details={"mode": mode},
        )
    _, method = require_any_api_method(
        item,
        ("CreateMagicMask",),
        capability_id="clip.magic_mask",
        runtime_object="timeline_item",
    )
    result = method(normalized_mode)
    if result is False:
        raise APICallFailed("CreateMagicMask failed.", details={"clip": clip_name, "mode": normalized_mode})
    return {
        "clip": clip_name or (item.GetName() if hasattr(item, "GetName") else None),
        "selector": {"track": track, "record_frame": record_frame} if track is not None else None,
        "mode": normalized_mode,
        "success": bool(result),
    }


def regenerate_magic_mask(
    conn,
    clip_name: Optional[str] = None,
    *,
    track: int | None = None,
    record_frame: str | int | None = None,
    ops_module,
) -> dict[str, Any]:
    item = ops_module.cutagent_clip_by_selector(conn, clip_name, track=track, record_frame=record_frame)
    _, method = require_any_api_method(
        item,
        ("RegenerateMagicMask",),
        capability_id="clip.magic_mask",
        runtime_object="timeline_item",
    )
    result = method()
    if result is False:
        raise APICallFailed("RegenerateMagicMask failed.", details={"clip": clip_name})
    return {
        "clip": clip_name or (item.GetName() if hasattr(item, "GetName") else None),
        "selector": {"track": track, "record_frame": record_frame} if track is not None else None,
        "regenerated": bool(result),
    }


def get_voice_isolation(conn, clip_name: Optional[str] = None, *, ops_module) -> dict[str, Any]:
    item = ops_module.cutagent_clip(conn, clip_name)
    getter = require_api_method(
        item,
        "GetVoiceIsolationState",
        capability_id="clip.voice_isolation",
        runtime_object="timeline_item",
    )
    state = getter()
    result = state if isinstance(state, dict) else {"state": state}
    result["clip"] = clip_name or (item.GetName() if hasattr(item, "GetName") else None)
    return result


def set_voice_isolation(
    conn,
    clip_name: Optional[str] = None,
    *,
    enabled: Optional[bool] = None,
    amount: Optional[int] = None,
    ops_module,
) -> dict[str, Any]:
    item = ops_module.cutagent_clip(conn, clip_name)
    current: dict[str, Any] = {}
    getter = getattr(item, "GetVoiceIsolationState", None)
    if callable(getter):
        try:
            state = getter()
            if isinstance(state, dict):
                current = state
        except APICallFailed:
            if enabled is None:
                raise

    state = {
        "isEnabled": bool(current.get("isEnabled", False) if enabled is None else enabled),
        "amount": int(current.get("amount", 100 if enabled else 0) if amount is None else amount),
    }
    if not 0 <= state["amount"] <= 100:
        raise ValidationError(
            "Voice isolation amount must be between 0 and 100.",
            details={"amount": state["amount"]},
        )

    setter = require_api_method(
        item,
        "SetVoiceIsolationState",
        capability_id="clip.voice_isolation",
        runtime_object="timeline_item",
    )
    result = setter(state)
    if result is False:
        raise APICallFailed("SetVoiceIsolationState failed.", details={"clip": clip_name, "state": state})
    state["clip"] = clip_name or (item.GetName() if hasattr(item, "GetName") else None)
    return state


def get_keyframe_mode(conn) -> dict[str, Any]:
    getter = getattr(conn.resolve, "GetKeyframeMode", None)
    if not getter:
        raise APICallFailed("GetKeyframeMode not available.")
    return {"keyframe_mode": getter()}


def set_keyframe_mode(conn, mode: int) -> dict[str, Any]:
    setter = getattr(conn.resolve, "SetKeyframeMode", None)
    if not setter:
        raise APICallFailed("SetKeyframeMode not available.")
    result = setter(mode)
    return {"keyframe_mode": mode, "success": bool(result)}


def export_current_frame_as_still(conn, path: str) -> dict[str, Any]:
    if not conn.project:
        raise APICallFailed("No active project.")
    exporter = getattr(conn.project, "ExportCurrentFrameAsStill", None)
    if not exporter:
        raise APICallFailed("ExportCurrentFrameAsStill not available.")
    result = exporter(path)
    return {"exported": bool(result), "path": path}


def insert_audio_to_current_track(conn, media_path: str, start_offset: int = 0) -> dict[str, Any]:
    if not conn.project:
        raise APICallFailed("No active project.")
    inserter = getattr(conn.project, "InsertAudioToCurrentTrackAtPlayhead", None)
    if not inserter:
        raise APICallFailed("InsertAudioToCurrentTrackAtPlayhead not available.")
    result = inserter(media_path, start_offset)
    return {"inserted": bool(result), "path": media_path}
