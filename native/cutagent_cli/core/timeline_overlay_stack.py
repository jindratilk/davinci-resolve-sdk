"""High-level timeline overlay stack insertion."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..errors import APICallFailed, ValidationError
from . import fusion_image_ops, fusion_text_ops, media_pool, timeline_item_duration_db, timeline_layout, timeline_markers, timeline_ops


SUPPORTED_LAYER_KINDS = {"media", "text_setting", "image_setting"}


def load_overlay_stack_spec(*, path: str | None = None, raw_json: str | None = None) -> dict[str, Any]:
    provided = [value for value in (path, raw_json) if value is not None]
    if len(provided) != 1:
        raise ValidationError(
            "Overlay stack insert requires exactly one of --spec or --spec-json.",
            details={"spec": path, "spec_json": raw_json},
            recoverability="not_applicable",
        )
    try:
        if path is not None:
            raw = Path(path).expanduser().read_text(encoding="utf-8")
        else:
            raw = str(raw_json)
        data = json.loads(raw)
    except FileNotFoundError as exc:
        raise ValidationError(
            "Overlay stack spec file was not found.",
            details={"path": str(Path(path).expanduser()) if path else None},
            recoverability="not_applicable",
        ) from exc
    except json.JSONDecodeError as exc:
        raise ValidationError(
            "Overlay stack spec is not valid JSON.",
            details={"path": str(Path(path).expanduser()) if path else None, "line": exc.lineno, "column": exc.colno},
            recoverability="not_applicable",
        ) from exc
    if not isinstance(data, dict):
        raise ValidationError(
            "Overlay stack spec must be a JSON object.",
            details={"spec_type": type(data).__name__},
            recoverability="not_applicable",
        )
    return data


def _coerce_positive_int(value: Any, *, field: str) -> int:
    if isinstance(value, bool):
        raise ValidationError(f"{field} must be a positive integer.", details={field: value}, recoverability="not_applicable")
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{field} must be a positive integer.", details={field: value}, recoverability="not_applicable") from exc
    if result <= 0:
        raise ValidationError(f"{field} must be greater than zero.", details={field: value}, recoverability="not_applicable")
    return result


def _coerce_non_negative_int(value: Any, *, field: str) -> int:
    if isinstance(value, bool):
        raise ValidationError(f"{field} must be a non-negative integer.", details={field: value}, recoverability="not_applicable")
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{field} must be a non-negative integer.", details={field: value}, recoverability="not_applicable") from exc
    if result < 0:
        raise ValidationError(f"{field} must not be negative.", details={field: value}, recoverability="not_applicable")
    return result


def _optional_str(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _normalize_position(raw: Any) -> dict[str, float | None]:
    if raw is None:
        return {"x": None, "y": None}
    if not isinstance(raw, dict):
        raise ValidationError("Layer position must be an object.", details={"position": raw}, recoverability="not_applicable")
    result: dict[str, float | None] = {"x": None, "y": None}
    for key in ("x", "y"):
        value = raw.get(key)
        if value is None:
            continue
        try:
            result[key] = float(value)
        except (TypeError, ValueError) as exc:
            raise ValidationError("Layer position values must be numeric.", details={"position": raw, "field": key}, recoverability="not_applicable") from exc
    return result


def _normalize_layout(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValidationError("Overlay stack spec requires layout object.", details={"layout": raw}, recoverability="not_applicable")
    stacks = raw.get("candidate_stacks")
    if not isinstance(stacks, list) or not stacks:
        raise ValidationError("layout.candidate_stacks must be a non-empty array.", details={"candidate_stacks": stacks}, recoverability="not_applicable")
    normalized_stacks: list[list[int]] = []
    for index, stack in enumerate(stacks):
        if not isinstance(stack, list) or not stack:
            raise ValidationError("Each candidate stack must be a non-empty array.", details={"candidate_index": index, "stack": stack}, recoverability="not_applicable")
        tracks = [timeline_ops.validate_timeline_track_index(track) for track in stack]
        if len(set(tracks)) != len(tracks):
            raise ValidationError("Candidate stack track indexes must be unique.", details={"candidate_index": index, "tracks": tracks}, recoverability="not_applicable")
        normalized_stacks.append(tracks)
    padding_frames = _coerce_non_negative_int(raw.get("padding_frames", 0), field="layout.padding_frames")
    return {
        "candidate_stacks": normalized_stacks,
        "padding_frames": padding_frames,
        "shift_if_blocked": bool(raw.get("shift_if_blocked", True)),
        "allow_missing_tracks": bool(raw.get("allow_missing_tracks", True)),
    }


def _normalize_background(raw: Any) -> dict[str, Any] | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValidationError("background must be an object.", details={"background": raw}, recoverability="not_applicable")
    media_name = _optional_str(raw.get("media_name") or raw.get("name"))
    if not media_name:
        raise ValidationError("background.media_name is required.", details={"background": raw}, recoverability="not_applicable")
    return {
        "media_name": media_name,
        "folder": _optional_str(raw.get("folder")),
        "track": timeline_ops.validate_timeline_track_index(raw.get("track", 1)),
        "shared": bool(raw.get("shared", False)),
        "extend_if_overlapping": bool(raw.get("extend_if_overlapping", False)),
        "optional": bool(raw.get("optional", False)),
    }


def _normalize_layer(raw: Any, *, index: int) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValidationError("Each overlay stack layer must be an object.", details={"index": index, "layer": raw}, recoverability="not_applicable")
    kind = str(raw.get("kind") or "").strip()
    if kind not in SUPPORTED_LAYER_KINDS:
        raise ValidationError("Unsupported overlay stack layer kind.", details={"index": index, "kind": kind, "allowed": sorted(SUPPORTED_LAYER_KINDS)}, recoverability="not_applicable")
    track_from_stack = raw.get("track_from_stack")
    if track_from_stack is None:
        raise ValidationError("Layer track_from_stack is required.", details={"index": index, "layer": raw}, recoverability="not_applicable")
    track_offset = _coerce_non_negative_int(track_from_stack, field="track_from_stack")
    name = _optional_str(raw.get("name"))
    role = _optional_str(raw.get("role")) or f"layer_{index}"
    position = _normalize_position(raw.get("position"))
    layer = {
        "index": index,
        "role": role,
        "kind": kind,
        "track_from_stack": track_offset,
        "name": name,
        "position": position,
        "raw": dict(raw),
    }
    if kind == "media":
        media_name = _optional_str(raw.get("media_name") or raw.get("name"))
        if not media_name:
            raise ValidationError("Media layer requires media_name or name.", details={"index": index, "layer": raw}, recoverability="not_applicable")
        layer.update({"media_name": media_name, "folder": _optional_str(raw.get("folder"))})
    else:
        template = _optional_str(raw.get("template") or raw.get("path"))
        if not template:
            raise ValidationError("Setting layer requires template path.", details={"index": index, "layer": raw}, recoverability="not_applicable")
        holder_kind = str(raw.get("holder_kind") or "fusion").strip().lower().replace("_", "-")
        holder_default = "Text+" if holder_kind == "textplus" else "Fusion Composition"
        layer.update(
            {
                "template": str(Path(template).expanduser()),
                "text": str(raw.get("text") or ""),
                "uppercase": bool(raw.get("uppercase", False)),
                "double_spaces": bool(raw.get("double_spaces", False)),
                "styled": raw.get("styled"),
                "bold_style": str(raw.get("bold_style") or "ExtraBold"),
                "holder": str(raw.get("holder") or holder_default),
                "holder_kind": holder_kind,
                "tool": _optional_str(raw.get("tool")),
                "tool_candidates": list(raw.get("tool_candidates") or []),
                "inputs": list(raw.get("inputs") or raw.get("input") or []),
                "cls_tool_candidates": list(raw.get("cls_tool_candidates") or []),
            }
        )
        if kind == "image_setting":
            image_path = _optional_str(raw.get("image_path") or raw.get("image"))
            if not image_path:
                raise ValidationError("image_setting layer requires image_path.", details={"index": index, "layer": raw}, recoverability="not_applicable")
            layer.update(
                {
                    "image_path": image_path,
                    "group_tool": _optional_str(raw.get("group_tool")),
                    "group_input": _optional_str(raw.get("group_input")),
                    "import_media": bool(raw.get("import_media", True)),
                    "image_transform": {
                        "zoom_x": raw.get("zoom_x"),
                        "zoom_y": raw.get("zoom_y"),
                        "pan": raw.get("pan"),
                        "tilt": raw.get("tilt"),
                        "position_x": raw.get("position_x", position["x"]),
                        "position_y": raw.get("position_y", position["y"]),
                    },
                }
            )
    return layer


def normalize_overlay_stack_spec(spec: dict[str, Any]) -> dict[str, Any]:
    timeline = _optional_str(spec.get("timeline"))
    record_frame = _coerce_non_negative_int(spec.get("record_frame"), field="record_frame")
    duration_frames = _coerce_positive_int(spec.get("duration_frames"), field="duration_frames")
    layout = _normalize_layout(spec.get("layout"))
    layers_raw = spec.get("layers")
    if not isinstance(layers_raw, list) or not layers_raw:
        raise ValidationError("Overlay stack spec requires at least one layer.", details={"layers": layers_raw}, recoverability="not_applicable")
    layers = [_normalize_layer(layer, index=index) for index, layer in enumerate(layers_raw)]
    for layer in layers:
        for stack in layout["candidate_stacks"]:
            if int(layer["track_from_stack"]) >= len(stack):
                raise ValidationError(
                    "Layer track_from_stack is outside at least one candidate stack.",
                    details={"layer_index": layer["index"], "track_from_stack": layer["track_from_stack"], "candidate_stack": stack},
                    recoverability="not_applicable",
                )
    marker = spec.get("marker")
    if marker is not None and not isinstance(marker, dict):
        raise ValidationError("marker must be an object.", details={"marker": marker}, recoverability="not_applicable")
    return {
        "timeline": timeline,
        "record_frame": record_frame,
        "duration_frames": duration_frames,
        "layout": layout,
        "background": _normalize_background(spec.get("background")),
        "layers": layers,
        "marker": dict(marker) if marker else None,
        "cleanup_on_failure": bool(spec.get("cleanup_on_failure", True)),
    }


def _timeline_name(timeline: Any) -> str | None:
    getter = getattr(timeline, "GetName", None)
    if callable(getter):
        try:
            return str(getter())
        except Exception:
            return None
    return None


def _item_summary(item: Any, *, role: str, track_index: int, name: str | None = None) -> dict[str, Any]:
    data: dict[str, Any] = {"role": role, "track_index": track_index, "name": name}
    for key, method in (("name", "GetName"), ("start_frame", "GetStart"), ("end_frame", "GetEnd"), ("duration_frames", "GetDuration")):
        getter = getattr(item, method, None)
        if not callable(getter):
            continue
        try:
            value = getter()
            if key in {"start_frame", "end_frame", "duration_frames"}:
                value = int(value)
            if value is not None:
                data[key] = value
        except Exception:
            pass
    return data


def _ensure_video_track(conn: Any, track: int) -> dict[str, Any]:
    from ..commands import fusion as fusion_commands

    return fusion_commands._ensure_video_track(conn, track)


def _duration_readback_matches(duration_apply: dict[str, Any] | None, duration_frames: int) -> bool:
    if not isinstance(duration_apply, dict):
        return True
    readback = duration_apply.get("duration_readback_frames")
    return readback in (None, int(duration_frames))


def _fresh_connection_after_db_mutation(conn: Any, *, timeline_name: str | None) -> Any:
    try:
        from ..connection import ResolveConnection

        fresh_conn = ResolveConnection.get()
        fresh_conn.connect()
    except Exception:
        fresh_conn = conn
    if timeline_name:
        try:
            timeline_ops.switch_timeline(fresh_conn, name=timeline_name)
        except Exception:
            pass
    return fresh_conn


def _apply_media_duration_db_fallback(
    conn: Any,
    item: Any,
    *,
    role: str,
    name: str,
    track: int,
    start_frame: int,
    duration_frames: int,
) -> tuple[Any, dict[str, Any], Any]:
    before = _item_summary(item, role=role, track_index=track, name=name)
    timeline_name = _timeline_name(getattr(conn, "timeline", None))
    fallback: dict[str, Any] = {
        "attempted": True,
        "route": "timeline.items.set_duration",
        "selector": {
            "timeline": timeline_name,
            "track_type": "video",
            "track_index": int(track),
            "start_frame": int(start_frame),
            "current_end_frame": before.get("end_frame"),
            "name": name,
        },
    }
    try:
        mutation = timeline_item_duration_db.set_timeline_item_duration(
            conn,
            timeline_name=timeline_name,
            track_type="video",
            track_index=int(track),
            start_frame=f"{int(start_frame)}f",
            current_end_frame=f"{int(before['end_frame'])}f" if before.get("end_frame") is not None else None,
            name=name,
            duration=f"{int(duration_frames)}f",
            allow_overlap=True,
            enforce_source_bounds=False,
        )
        fresh_conn = _fresh_connection_after_db_mutation(conn, timeline_name=timeline_name)
        refreshed_item = _find_named_overlap(
            fresh_conn.timeline,
            track=int(track),
            name=name,
            start_frame=int(start_frame),
            end_frame=int(start_frame) + int(duration_frames),
            padding_frames=0,
        )
        item_after = refreshed_item or item
        after = _item_summary(item_after, role=role, track_index=track, name=name)
        fallback.update(
            {
                "ok": after.get("duration_frames") == int(duration_frames),
                "mutation": mutation,
                "before": before,
                "after": after,
                "connection_reloaded": fresh_conn is not conn,
            }
        )
        return item_after, fallback, fresh_conn
    except Exception as exc:
        details = getattr(exc, "details", None)
        fallback.update(
            {
                "ok": False,
                "error": str(exc),
                "error_type": type(exc).__name__,
                "before": before,
            }
        )
        if isinstance(details, dict):
            fallback["error_details"] = details
        return item, fallback, conn


def _append_media_item(conn: Any, *, role: str, media_name: str, folder: str | None, track: int, start_frame: int, duration_frames: int, name_after_append: str | None = None) -> tuple[Any, dict[str, Any], Any]:
    entry = {"name": media_name}
    if folder:
        entry["folder"] = folder
    resolved = media_pool.resolve_append_media_entry(conn, entry)
    clip_info = {
        "mediaPoolItem": resolved["clip"],
        "startFrame": 0,
        "endFrame": duration_frames,
        "trackIndex": track,
        "recordFrame": start_frame,
        "trackType": "video",
    }
    result = conn.media_pool.AppendToTimeline([clip_info])
    if not result:
        raise APICallFailed("Failed to append overlay stack media layer.", details={"role": role, "media_name": media_name, "track": track, "record_frame": start_frame})
    item = result[0] if isinstance(result, list) else result
    if name_after_append:
        setter = getattr(item, "SetName", None)
        if callable(setter):
            try:
                setter(str(name_after_append))
            except Exception:
                pass
    duration_apply = None
    effective_conn = conn
    try:
        from ..commands import fusion as fusion_commands

        duration_apply = fusion_commands._apply_timeline_item_name_and_duration(
            item,
            name=str(name_after_append or media_name),
            duration_frames=int(duration_frames),
        )
    except Exception as exc:
        duration_apply = {"attempted": True, "error": str(exc)}
    if not _duration_readback_matches(duration_apply, duration_frames):
        item, db_fallback, effective_conn = _apply_media_duration_db_fallback(
            conn,
            item,
            role=role,
            name=str(name_after_append or media_name),
            track=int(track),
            start_frame=int(start_frame),
            duration_frames=int(duration_frames),
        )
        duration_apply = {
            **(duration_apply if isinstance(duration_apply, dict) else {}),
            "db_fallback": db_fallback,
            "duration_readback_frames": _item_summary(item, role=role, track_index=int(track), name=str(name_after_append or media_name)).get("duration_frames"),
            "duration_applied": bool(db_fallback.get("ok")),
        }
    return item, {
        "resolved": {key: value for key, value in resolved.items() if key != "clip"},
        "clip_info": {**clip_info, "mediaPoolItem": resolved.get("name") or media_name},
        "duration_apply": duration_apply,
    }, effective_conn


def _find_named_overlap(timeline: Any, *, track: int, name: str, start_frame: int, end_frame: int, padding_frames: int) -> Any | None:
    try:
        items = timeline.GetItemListInTrack("video", track) or []
    except Exception:
        return None
    requested_start = int(start_frame) - int(padding_frames)
    requested_end = int(end_frame) + int(padding_frames)
    for item in items:
        try:
            item_name = item.GetName() if hasattr(item, "GetName") else ""
            item_start = int(item.GetStart())
            item_end = int(item.GetEnd())
        except Exception:
            continue
        if item_name == name and item_start < requested_end and item_end > requested_start:
            return item
    return None


def _extend_item_to_cover(item: Any, *, start_frame: int, end_frame: int) -> dict[str, Any]:
    current_start = None
    current_end = None
    try:
        current_start = int(item.GetStart())
        current_end = int(item.GetEnd())
    except Exception:
        pass
    if current_start is None or current_end is None:
        return {"attempted": False, "reason": "readback_unavailable"}
    requested_duration = max(current_end, int(end_frame)) - min(current_start, int(start_frame))
    if requested_duration <= current_end - current_start:
        return {"attempted": False, "reason": "already_covers_range", "duration_frames": current_end - current_start}
    from ..commands import fusion as fusion_commands

    return fusion_commands._apply_timeline_item_name_and_duration(
        item,
        name=item.GetName() if hasattr(item, "GetName") else "background",
        duration_frames=requested_duration,
    )


def _insert_setting_layer(conn: Any, *, layer: dict[str, Any], track: int, start_frame: int, duration_frames: int) -> tuple[Any, dict[str, Any], Any]:
    from ..commands import fusion as fusion_commands

    name = layer["name"] or Path(str(layer["template"])).stem
    inserted = fusion_commands._insert_setting_precise(
        conn,
        path=str(layer["template"]),
        clip_name=str(name),
        at=f"{start_frame}f",
        record_frame=int(start_frame),
        duration=f"{duration_frames}f",
        track=track,
        holder=str(layer["holder"]),
        holder_kind=str(layer["holder_kind"]),
        position_x=layer["position"]["x"],
        position_y=layer["position"]["y"],
    )
    readback_conn = conn
    if inserted.get("connection_reloaded"):
        try:
            from ..connection import ResolveConnection

            readback_conn = ResolveConnection.get()
            readback_conn.connect()
        except Exception:
            readback_conn = conn
    item = fusion_commands._find_timeline_item_by_track_record(readback_conn, track, int(start_frame), name=str(name))
    if item is None:
        raise APICallFailed("Inserted setting layer could not be read back for follow-up updates.", details={"layer": layer["role"], "track": track, "record_frame": start_frame, "inserted": inserted})
    return item, inserted, readback_conn


def _delete_created_items(conn: Any, items: list[Any]) -> dict[str, Any]:
    if not items:
        return {"attempted": False, "deleted_count": 0}
    deleter = getattr(getattr(conn, "timeline", None), "DeleteClips", None)
    if not callable(deleter):
        return {"attempted": False, "deleted_count": 0, "errors": ["Timeline.DeleteClips unavailable"]}
    try:
        result = deleter(list(items), False)
        return {"attempted": True, "deleted_count": len(items) if result is not False else 0, "api_result": result, "used_non_ripple_argument": True}
    except TypeError:
        try:
            result = deleter(list(items))
            return {"attempted": True, "deleted_count": len(items) if result is not False else 0, "api_result": result, "used_non_ripple_argument": False, "fallback_used": True}
        except Exception as exc:
            return {"attempted": True, "deleted_count": 0, "errors": [str(exc)]}
    except Exception as exc:
        return {"attempted": True, "deleted_count": 0, "errors": [str(exc)]}


def plan_overlay_stack_insert(conn: Any, spec: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_overlay_stack_spec(spec)
    if normalized["timeline"]:
        timeline_ops.switch_timeline(conn, name=normalized["timeline"])
    timeline_start = timeline_markers._timeline_start_frame(conn, timeline=getattr(conn, "timeline", None))
    relative_start_ref = f"{int(normalized['record_frame']) - int(timeline_start)}f"
    layout_plan = timeline_layout.plan_free_stack(
        conn,
        timeline_name=None,
        track_type="video",
        start_ref=relative_start_ref,
        end_ref=None,
        duration_ref=f"{normalized['duration_frames']}f",
        candidate_stacks=normalized["layout"]["candidate_stacks"],
        padding_ref=f"{normalized['layout']['padding_frames']}f",
        shift=normalized["layout"]["shift_if_blocked"],
        allow_missing_tracks=normalized["layout"]["allow_missing_tracks"],
    )
    selected = layout_plan.get("selected")
    if not selected:
        raise ValidationError("No free overlay stack candidate was found.", details={"layout": layout_plan}, recoverability="manual")
    tracks = list(selected["tracks"])
    start_frame = int(selected["start_frame"])
    end_frame = int(selected["end_frame"])
    planned_items: list[dict[str, Any]] = []
    if normalized["background"]:
        bg = normalized["background"]
        planned_items.append({"role": "background", "kind": "media", "track_index": bg["track"], "name": bg["media_name"], "optional": bg["optional"]})
    for layer in normalized["layers"]:
        planned_items.append(
            {
                "role": layer["role"],
                "kind": layer["kind"],
                "track_index": tracks[int(layer["track_from_stack"])],
                "name": layer["name"] or layer.get("media_name") or Path(str(layer.get("template", "layer"))).stem,
            }
        )
    return {
        "action": "timeline.overlay_stack.insert",
        "changed": False,
        "target": {"kind": "timeline", "name": _timeline_name(getattr(conn, "timeline", None)) or normalized["timeline"] or "current"},
        "layout": {
            "selected_tracks": tracks,
            "candidate_index": selected.get("candidate_index"),
            "start_frame": start_frame,
            "end_frame": end_frame,
            "duration_frames": normalized["duration_frames"],
            "shifted": bool(selected.get("shifted", False)),
        },
        "planned_items": planned_items,
        "marker": {"planned": bool(normalized["marker"]), "created": False},
        "cleanup": {"needed": False},
        "preflight": {"ready": True, "layout": layout_plan},
        "normalized_spec": normalized,
    }


def insert_overlay_stack(conn: Any, spec: dict[str, Any]) -> dict[str, Any]:
    plan = plan_overlay_stack_insert(conn, spec)
    normalized = plan.pop("normalized_spec")
    layout = plan["layout"]
    start_frame = int(layout["start_frame"])
    end_frame = int(layout["end_frame"])
    duration_frames = int(layout["duration_frames"])
    selected_tracks = list(layout["selected_tracks"])
    created_items: list[dict[str, Any]] = []
    created_objects: list[Any] = []
    background_result: dict[str, Any] | None = None
    marker_result: dict[str, Any] = {"created": False}
    cleanup = {"needed": False}

    try:
        bg = normalized["background"]
        if bg:
            try:
                _ensure_video_track(conn, int(bg["track"]))
                existing = _find_named_overlap(
                    conn.timeline,
                    track=int(bg["track"]),
                    name=str(bg["media_name"]),
                    start_frame=start_frame,
                    end_frame=end_frame,
                    padding_frames=int(normalized["layout"]["padding_frames"]),
                ) if bg["shared"] else None
                if existing is not None:
                    extend = _extend_item_to_cover(existing, start_frame=start_frame, end_frame=end_frame) if bg["extend_if_overlapping"] else {"attempted": False}
                    background_result = {"reused": True, "extended": extend, "item": _item_summary(existing, role="background", track_index=int(bg["track"]), name=str(bg["media_name"]))}
                    created_items.append({"role": "background", "track_index": int(bg["track"]), "name": str(bg["media_name"]), "reused": True})
                else:
                    item, append, conn = _append_media_item(
                        conn,
                        role="background",
                        media_name=str(bg["media_name"]),
                        folder=bg["folder"],
                        track=int(bg["track"]),
                        start_frame=start_frame,
                        duration_frames=duration_frames,
                    )
                    created_objects.append(item)
                    summary = _item_summary(item, role="background", track_index=int(bg["track"]), name=str(bg["media_name"]))
                    created_items.append(summary)
                    background_result = {"reused": False, "append": append, "item": summary}
                    duration_apply = append.get("duration_apply") if isinstance(append, dict) else None
                    if not _duration_readback_matches(duration_apply, duration_frames):
                        raise APICallFailed(
                            "Overlay stack background duration did not match requested duration.",
                            details={
                                "role": "background",
                                "media_name": bg["media_name"],
                                "track": bg["track"],
                                "requested_duration_frames": duration_frames,
                                "duration_apply": duration_apply,
                            },
                            recoverability="manual",
                        )
            except Exception as exc:
                if not bg["optional"]:
                    raise
                background_result = {"optional": True, "failed": True, "error": str(exc)}

        for layer in normalized["layers"]:
            track = int(selected_tracks[int(layer["track_from_stack"])])
            _ensure_video_track(conn, track)
            if layer["kind"] == "media":
                item, append, conn = _append_media_item(
                    conn,
                    role=str(layer["role"]),
                    media_name=str(layer["media_name"]),
                    folder=layer["folder"],
                    track=track,
                    start_frame=start_frame,
                    duration_frames=duration_frames,
                    name_after_append=layer["name"],
                )
                layer_result = {"append": append}
                created_objects.append(item)
                duration_apply = append.get("duration_apply") if isinstance(append, dict) else None
                if not _duration_readback_matches(duration_apply, duration_frames):
                    raise APICallFailed(
                        "Overlay stack media layer duration did not match requested duration.",
                        details={
                            "role": layer["role"],
                            "media_name": layer["media_name"],
                            "track": track,
                            "requested_duration_frames": duration_frames,
                            "duration_apply": duration_apply,
                        },
                        recoverability="manual",
                    )
            else:
                inserted_layer = _insert_setting_layer(conn, layer=layer, track=track, start_frame=start_frame, duration_frames=duration_frames)
                if len(inserted_layer) == 3:
                    item, insert_result, conn = inserted_layer
                else:
                    item, insert_result = inserted_layer
                layer_result = {"insert": insert_result}
                if item not in created_objects:
                    created_objects.append(item)
                if layer["kind"] == "text_setting":
                    layer_result["text"] = fusion_text_ops.set_text_on_item(
                        item,
                        text=str(layer["text"]),
                        role=str(layer["role"]),
                        explicit_tool=layer["tool"],
                        tool_candidates=list(layer["tool_candidates"]),
                        input_names=list(layer["inputs"]),
                        uppercase=bool(layer["uppercase"]),
                        double_spaces=bool(layer["double_spaces"]),
                        styled=layer["styled"],
                        bold_style=str(layer["bold_style"]),
                        cls_tool_candidates=list(layer["cls_tool_candidates"]),
                    )
                elif layer["kind"] == "image_setting":
                    layer_result["image"] = fusion_image_ops.set_image_on_item(
                        conn,
                        item,
                        str(layer["image_path"]),
                        group_tool_name=layer["group_tool"],
                        group_input_name=layer["group_input"],
                        import_media=bool(layer["import_media"]),
                        transform=dict(layer["image_transform"]),
                    )
            if item not in created_objects:
                created_objects.append(item)
            summary = _item_summary(item, role=str(layer["role"]), track_index=track, name=layer["name"] or layer.get("media_name"))
            summary["kind"] = layer["kind"]
            summary["result"] = layer_result
            created_items.append(summary)

        if normalized["marker"]:
            marker = normalized["marker"]
            timeline_start = timeline_markers._timeline_start_frame(conn, timeline=conn.timeline)
            marker_frame = start_frame - timeline_start
            api_result = conn.timeline.AddMarker(
                marker_frame,
                timeline_markers.normalize_timeline_marker_color(marker.get("color", "Blue")),
                str(marker.get("title") or marker.get("name") or "Overlay"),
                str(marker.get("note") or marker.get("title") or "Overlay"),
                _coerce_positive_int(marker.get("duration_frames", 1), field="marker.duration_frames"),
            )
            marker_result = {"created": api_result not in (False, None), "frame": start_frame, "timeline_frame": marker_frame, "api_result": api_result}
            if not marker_result["created"]:
                raise APICallFailed("Failed to create overlay stack marker.", details={"marker": marker_result})
    except Exception as exc:
        cleanup = {"needed": bool(created_objects)}
        if normalized["cleanup_on_failure"]:
            cleanup.update(_delete_created_items(conn, created_objects))
        else:
            cleanup["attempted"] = False
            cleanup["deleted_count"] = 0
        raise APICallFailed(
            "Overlay stack insert failed.",
            details={
                "cleanup": cleanup,
                "created_items": created_items,
                "marker": marker_result,
                "cause": str(exc),
                "cause_type": type(exc).__name__,
            },
            recoverability="manual",
        ) from exc

    return {
        **plan,
        "changed": True,
        "created_items": created_items,
        "background": background_result,
        "marker": marker_result,
        "cleanup": cleanup,
    }
