"""Disk DB speed-ramp planning and mutation helpers."""

from __future__ import annotations

from dataclasses import asdict, replace
from datetime import datetime
import json
import math
from pathlib import Path
import re
import sqlite3
from typing import Any

from ..errors import APICallFailed, ValidationError
from ..runtime_health import resolve_current_disk_project_db
from . import clip_speed_db, db_timeline_rows, db_timeline_selection, retime_db
from .db_timeline_selection import LiveItemRef


def parse_peak_speed(value: str | float | int) -> float:
    if isinstance(value, str):
        text = value.strip().lower()
        if text.endswith("x"):
            text = text[:-1].strip()
        try:
            speed = float(text)
        except ValueError as exc:
            raise ValidationError(
                "Peak speed must be a numeric multiplier such as 6.5x.",
                details={"peak_speed": value},
                recoverability="not_applicable",
            ) from exc
    else:
        speed = float(value)
    if not math.isfinite(speed) or speed <= 1.0:
        raise ValidationError(
            "Peak speed must be greater than 1x.",
            details={"peak_speed": value},
            recoverability="not_applicable",
        )
    return speed


def parse_segment_speed(value: str | float | int | None, *, default: float | None = None, field: str = "speed") -> float:
    if value is None:
        if default is None:
            raise ValidationError(
                "Speed-ramp segment speed is required.",
                details={field: value},
                recoverability="not_applicable",
            )
        return float(default)
    if isinstance(value, str):
        text = value.strip().lower()
        if text.endswith("x"):
            text = text[:-1].strip()
        try:
            speed = float(text)
        except ValueError as exc:
            raise ValidationError(
                "Speed-ramp segment speeds must be numeric multipliers such as 1x or 6.5x.",
                details={field: value},
                recoverability="not_applicable",
            ) from exc
    else:
        speed = float(value)
    if not math.isfinite(speed) or speed <= 0.0:
        raise ValidationError(
            "Speed-ramp segment speeds must be greater than 0x.",
            details={field: value},
            recoverability="not_applicable",
        )
    return speed


def parse_interp(value: str | int | None, *, field: str) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        parsed = int(str(value).strip(), 0)
    except ValueError as exc:
        raise ValidationError(
            "Speed-ramp interpolation values must be integer DaVinci Resolve interp codes.",
            details={field: value},
            recoverability="not_applicable",
        ) from exc
    if parsed < 0:
        raise ValidationError(
            "Speed-ramp interpolation values must be zero or greater.",
            details={field: value},
            recoverability="not_applicable",
        )
    return parsed


def _parse_seconds_value(value: str | float | int, *, fps: float, field: str) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        result = float(value)
    else:
        text = str(value or "").strip().lower()
        if not text:
            raise ValidationError(f"{field} must not be empty.", details={field: value}, recoverability="not_applicable")
        if text.endswith("frames"):
            text = text[:-6].strip() + "f"
        elif text.endswith("frame"):
            text = text[:-5].strip() + "f"
        if text.endswith("f"):
            result = float(text[:-1].strip()) / float(fps or 25.0)
        elif text.endswith("s"):
            result = float(text[:-1].strip())
        else:
            result = float(text)
    if not math.isfinite(result):
        raise ValidationError(f"{field} must be finite.", details={field: value}, recoverability="not_applicable")
    return result


def parse_handle_pair(value: str | None, *, fps: float, field: str) -> tuple[float, float] | None:
    if value is None or str(value).strip() == "":
        return None
    raw = str(value).strip()
    assignments: dict[str, str] = {}
    positional: list[str] = []
    for part in raw.replace(";", ",").split(","):
        token = part.strip()
        if not token:
            continue
        if "=" in token:
            key, val = token.split("=", 1)
            assignments[key.strip().lower()] = val.strip()
        else:
            positional.append(token)
    if assignments:
        x_raw = assignments.get("x") or assignments.get("xin") or assignments.get("xout")
        y_raw = assignments.get("y") or assignments.get("yin") or assignments.get("yout")
        if x_raw is None or y_raw is None:
            raise ValidationError(
                "Bezier handle spec must include x and y values.",
                details={field: value, "format": "x=4f,y=26f or 4f,26f"},
                recoverability="not_applicable",
            )
    elif len(positional) == 2:
        x_raw, y_raw = positional
    else:
        raise ValidationError(
            "Bezier handle spec must contain exactly two values.",
            details={field: value, "format": "x=4f,y=26f or 4f,26f"},
            recoverability="not_applicable",
        )
    return (
        _parse_seconds_value(x_raw, fps=fps, field=f"{field}.x"),
        _parse_seconds_value(y_raw, fps=fps, field=f"{field}.y"),
    )


def parse_timemap_point_specs(values: list[str] | tuple[str, ...] | None, *, fps: float, field: str) -> tuple[retime_db.TimeMapPoint, ...] | None:
    if not values:
        return None
    points: list[retime_db.TimeMapPoint] = []
    aliases = {
        "x": "x",
        "y": "y",
        "xin": "x_in",
        "x-in": "x_in",
        "x_in": "x_in",
        "yin": "y_in",
        "y-in": "y_in",
        "y_in": "y_in",
        "xout": "x_out",
        "x-out": "x_out",
        "x_out": "x_out",
        "yout": "y_out",
        "y-out": "y_out",
        "y_out": "y_out",
        "interp": "interp",
    }
    for index, raw in enumerate(values):
        assignments: dict[str, str] = {}
        for part in str(raw or "").replace(";", ",").split(","):
            token = part.strip()
            if not token:
                continue
            if "=" not in token:
                raise ValidationError(
                    "Explicit speed-ramp point specs must use key=value pairs.",
                    details={field: raw, "format": "x=102f,y=102f,xOut=4f,yOut=26f"},
                    recoverability="not_applicable",
                )
            key, value = token.split("=", 1)
            normalized = aliases.get(key.strip().lower().replace("_", "-"))
            if normalized is None:
                raise ValidationError(
                    "Unknown explicit speed-ramp point field.",
                    details={field: raw, "key": key.strip(), "supported": sorted(set(aliases.values()))},
                    recoverability="not_applicable",
                )
            assignments[normalized] = value.strip()
        if "x" not in assignments or "y" not in assignments:
            raise ValidationError(
                "Explicit speed-ramp point specs require x and y.",
                details={field: raw, "format": "x=102f,y=102f"},
                recoverability="not_applicable",
            )
        points.append(
            retime_db.TimeMapPoint(
                index=index,
                x=_parse_seconds_value(assignments["x"], fps=fps, field=f"{field}[{index}].x"),
                y=_parse_seconds_value(assignments["y"], fps=fps, field=f"{field}[{index}].y"),
                interp=int(assignments.get("interp") or 0),
                x_in=_parse_seconds_value(assignments.get("x_in", 0.0), fps=fps, field=f"{field}[{index}].xIn"),
                y_in=_parse_seconds_value(assignments.get("y_in", 0.0), fps=fps, field=f"{field}[{index}].yIn"),
                x_out=_parse_seconds_value(assignments.get("x_out", 0.0), fps=fps, field=f"{field}[{index}].xOut"),
                y_out=_parse_seconds_value(assignments.get("y_out", 0.0), fps=fps, field=f"{field}[{index}].yOut"),
            )
        )
    return tuple(points)


def validate_speed_ramp_transition_options(
    *,
    out_frames: int,
    in_frames: int,
    peak_speed: str | float | int,
    curve: str,
    track: int = 0,
    out_start_speed: str | float | int | None = "1x",
    out_end_speed: str | float | int | None = None,
    in_start_speed: str | float | int | None = None,
    in_end_speed: str | float | int | None = "1x",
    out_start_handle: str | None = None,
    out_end_handle: str | None = None,
    in_start_handle: str | None = None,
    in_end_handle: str | None = None,
    out_ease: str = "in-out",
    in_ease: str = "in-out",
    out_start_interp: str | int | None = None,
    out_end_interp: str | int | None = None,
    in_start_interp: str | int | None = None,
    in_end_interp: str | int | None = None,
    out_points: list[str] | tuple[str, ...] | None = None,
    in_points: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    safe_out_frames = int(out_frames)
    safe_in_frames = int(in_frames)
    safe_track = int(track or 0)
    if safe_out_frames <= 0:
        raise ValidationError(
            "--out-frames must be greater than 0.",
            details={"out_frames": out_frames},
            recoverability="not_applicable",
        )
    if safe_in_frames <= 0:
        raise ValidationError(
            "--in-frames must be greater than 0.",
            details={"in_frames": in_frames},
            recoverability="not_applicable",
        )
    if safe_track < 0:
        raise ValidationError(
            "--track must be 0 for auto-detect or a positive video track index.",
            details={"track": track},
            recoverability="not_applicable",
        )
    normalized_curve = retime_db.normalize_curve(curve)
    safe_peak = parse_peak_speed(peak_speed)
    return {
        "out_frames": safe_out_frames,
        "in_frames": safe_in_frames,
        "peak_speed": safe_peak,
        "curve": normalized_curve,
        "track": safe_track,
        "out_start_speed": parse_segment_speed(out_start_speed, default=1.0, field="out_start_speed"),
        "out_end_speed": parse_segment_speed(out_end_speed, default=safe_peak, field="out_end_speed"),
        "in_start_speed": parse_segment_speed(in_start_speed, default=safe_peak, field="in_start_speed"),
        "in_end_speed": parse_segment_speed(in_end_speed, default=1.0, field="in_end_speed"),
        "out_start_handle": out_start_handle,
        "out_end_handle": out_end_handle,
        "in_start_handle": in_start_handle,
        "in_end_handle": in_end_handle,
        "out_ease": retime_db.normalize_ease_mode(out_ease),
        "in_ease": retime_db.normalize_ease_mode(in_ease),
        "out_start_interp": parse_interp(out_start_interp, field="out_start_interp"),
        "out_end_interp": parse_interp(out_end_interp, field="out_end_interp"),
        "in_start_interp": parse_interp(in_start_interp, field="in_start_interp"),
        "in_end_interp": parse_interp(in_end_interp, field="in_end_interp"),
        "out_points": list(out_points or []),
        "in_points": list(in_points or []),
    }


def _timeline_name(conn: Any) -> str | None:
    timeline = getattr(conn, "timeline", None)
    return timeline.GetName() if timeline and hasattr(timeline, "GetName") else None


def _item_payload(item: LiveItemRef | None) -> dict[str, Any] | None:
    return asdict(item) if item is not None else None


def _db_type_for_item(item: LiveItemRef) -> str:
    return "Sm2TiAudioClip" if item.track_type == "audio" else "Sm2TiVideoClip"


def _build_target(
    *,
    side: str,
    media_kind: str,
    item: LiveItemRef,
    fps: float,
    ramp_frames: int,
    peak_speed: float,
    curve: str,
    reverse: bool,
    start_speed: float | None = None,
    end_speed: float | None = None,
    start_handle: tuple[float, float] | None = None,
    end_handle: tuple[float, float] | None = None,
    ease: str = "in-out",
    start_interp: int | None = None,
    end_interp: int | None = None,
    points: tuple[retime_db.TimeMapPoint, ...] | None = None,
) -> dict[str, Any]:
    if points:
        timemap = retime_db.build_explicit_speed_ramp_timemap(
            item.duration,
            fps,
            points=points,
            direction=side,
            reverse=reverse,
        )
    else:
        timemap = retime_db.build_speed_ramp_timemap(
            item.duration,
            fps,
            ramp_frames=ramp_frames,
            peak_speed=peak_speed,
            curve=curve,
            direction=side,
            reverse=reverse,
            start_speed=start_speed,
            end_speed=end_speed,
            start_handle=start_handle,
            end_handle=end_handle,
            ease=ease,
            start_interp=start_interp,
            end_interp=end_interp,
        )
    return {
        "side": side,
        "media_kind": media_kind,
        "db_type": _db_type_for_item(item),
        "item": item,
        "timemap": timemap,
    }


def prepare_speed_ramp_transition(
    conn: Any,
    *,
    cut_at: str | None,
    out_frames: int,
    in_frames: int,
    peak_speed: str | float | int,
    curve: str,
    reverse_incoming: bool,
    track: int = 0,
    out_start_speed: str | float | int | None = "1x",
    out_end_speed: str | float | int | None = None,
    in_start_speed: str | float | int | None = None,
    in_end_speed: str | float | int | None = "1x",
    out_start_handle: str | None = None,
    out_end_handle: str | None = None,
    in_start_handle: str | None = None,
    in_end_handle: str | None = None,
    out_ease: str = "in-out",
    in_ease: str = "in-out",
    out_start_interp: str | int | None = None,
    out_end_interp: str | int | None = None,
    in_start_interp: str | int | None = None,
    in_end_interp: str | int | None = None,
    out_points: list[str] | tuple[str, ...] | None = None,
    in_points: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    options = validate_speed_ramp_transition_options(
        out_frames=out_frames,
        in_frames=in_frames,
        peak_speed=peak_speed,
        curve=curve,
        track=track,
        out_start_speed=out_start_speed,
        out_end_speed=out_end_speed,
        in_start_speed=in_start_speed,
        in_end_speed=in_end_speed,
        out_start_handle=out_start_handle,
        out_end_handle=out_end_handle,
        in_start_handle=in_start_handle,
        in_end_handle=in_end_handle,
        out_ease=out_ease,
        in_ease=in_ease,
        out_start_interp=out_start_interp,
        out_end_interp=out_end_interp,
        in_start_interp=in_start_interp,
        in_end_interp=in_end_interp,
        out_points=out_points,
        in_points=in_points,
    )
    selection = db_timeline_selection.resolve_adjacent_av_cut(conn, cut_at=cut_at, track=options["track"])
    outgoing = selection["outgoing"]
    incoming = selection["incoming"]
    if not isinstance(outgoing, dict) or not isinstance(incoming, dict):
        raise APICallFailed("Adjacent cut selection returned an invalid shape.")

    outgoing_video = outgoing.get("video")
    incoming_video = incoming.get("video")
    if not isinstance(outgoing_video, LiveItemRef) or not isinstance(incoming_video, LiveItemRef):
        raise APICallFailed("Adjacent cut selection did not resolve both video clips.")

    fps = clip_speed_db.resolve_timeline_fps(conn)
    parsed_handles = {
        "out_start_handle": parse_handle_pair(options["out_start_handle"], fps=fps, field="out_start_handle"),
        "out_end_handle": parse_handle_pair(options["out_end_handle"], fps=fps, field="out_end_handle"),
        "in_start_handle": parse_handle_pair(options["in_start_handle"], fps=fps, field="in_start_handle"),
        "in_end_handle": parse_handle_pair(options["in_end_handle"], fps=fps, field="in_end_handle"),
    }
    parsed_out_points = parse_timemap_point_specs(options["out_points"], fps=fps, field="out_point")
    parsed_in_points = parse_timemap_point_specs(options["in_points"], fps=fps, field="in_point")

    # Build the pair explicitly so callers can inspect the public builder output for the two video clips.
    video_timemaps = retime_db.build_speed_ramp_transition_timemaps(
        outgoing_duration_frames=outgoing_video.duration,
        incoming_duration_frames=incoming_video.duration,
        fps=fps,
        out_frames=options["out_frames"],
        in_frames=options["in_frames"],
        peak_speed=options["peak_speed"],
        curve=options["curve"],
        reverse_incoming=reverse_incoming,
        outgoing_start_speed=options["out_start_speed"],
        outgoing_end_speed=options["out_end_speed"],
        incoming_start_speed=options["in_start_speed"],
        incoming_end_speed=options["in_end_speed"],
        outgoing_start_handle=parsed_handles["out_start_handle"],
        outgoing_end_handle=parsed_handles["out_end_handle"],
        incoming_start_handle=parsed_handles["in_start_handle"],
        incoming_end_handle=parsed_handles["in_end_handle"],
        outgoing_ease=options["out_ease"],
        incoming_ease=options["in_ease"],
        outgoing_start_interp=options["out_start_interp"],
        outgoing_end_interp=options["out_end_interp"],
        incoming_start_interp=options["in_start_interp"],
        incoming_end_interp=options["in_end_interp"],
        outgoing_points=parsed_out_points,
        incoming_points=parsed_in_points,
    )

    targets: list[dict[str, Any]] = [
        {
            "side": "outgoing",
            "media_kind": "video",
            "db_type": "Sm2TiVideoClip",
            "item": outgoing_video,
            "timemap": video_timemaps["outgoing"],
        },
        {
            "side": "incoming",
            "media_kind": "video",
            "db_type": "Sm2TiVideoClip",
            "item": incoming_video,
            "timemap": video_timemaps["incoming"],
        },
    ]

    outgoing_audio = outgoing.get("audio")
    outgoing_audio_items = outgoing_audio if isinstance(outgoing_audio, list) else [outgoing_audio]
    for audio_item in outgoing_audio_items:
        if not isinstance(audio_item, LiveItemRef):
            continue
        targets.append(
            _build_target(
                side="outgoing",
                media_kind="audio",
                item=audio_item,
                fps=clip_speed_db.resolve_timeline_fps(conn),
                ramp_frames=options["out_frames"],
                peak_speed=options["peak_speed"],
                curve=options["curve"],
                reverse=False,
                start_speed=options["out_start_speed"],
                end_speed=options["out_end_speed"],
                start_handle=parsed_handles["out_start_handle"],
                end_handle=parsed_handles["out_end_handle"],
                ease=options["out_ease"],
                start_interp=options["out_start_interp"],
                end_interp=options["out_end_interp"],
                points=parsed_out_points,
            )
        )
    incoming_audio = incoming.get("audio")
    incoming_audio_items = incoming_audio if isinstance(incoming_audio, list) else [incoming_audio]
    for audio_item in incoming_audio_items:
        if not isinstance(audio_item, LiveItemRef):
            continue
        targets.append(
            _build_target(
                side="incoming",
                media_kind="audio",
                item=audio_item,
                fps=clip_speed_db.resolve_timeline_fps(conn),
                ramp_frames=options["in_frames"],
                peak_speed=options["peak_speed"],
                curve=options["curve"],
                reverse=reverse_incoming,
                start_speed=options["in_start_speed"],
                end_speed=options["in_end_speed"],
                start_handle=parsed_handles["in_start_handle"],
                end_handle=parsed_handles["in_end_handle"],
                ease=options["in_ease"],
                start_interp=options["in_start_interp"],
                end_interp=options["in_end_interp"],
                points=parsed_in_points,
            )
        )

    return {
        "operation": "speed-ramp-transition",
        "engine": "db_workaround",
        "timeline_name": _timeline_name(conn),
        "cut": {
            "cut_at": selection["cut_at"],
            "record_frame": selection["record_frame"],
            "timeline_frame": selection["timeline_frame"],
            "track_index": selection["track_index"],
        },
        "options": {
            **options,
            "reverse_incoming": bool(reverse_incoming),
            "handles_seconds": parsed_handles,
            "explicit_points": {
                "outgoing": [point.to_dict() for point in parsed_out_points or ()],
                "incoming": [point.to_dict() for point in parsed_in_points or ()],
            },
        },
        "selection": {
            "outgoing": {
                "video": _item_payload(outgoing_video),
                "audio": (
                    [_item_payload(item) for item in outgoing_audio_items if isinstance(item, LiveItemRef)]
                    if isinstance(outgoing_audio, list)
                    else _item_payload(outgoing_audio if isinstance(outgoing_audio, LiveItemRef) else None)
                ),
            },
            "incoming": {
                "video": _item_payload(incoming_video),
                "audio": (
                    [_item_payload(item) for item in incoming_audio_items if isinstance(item, LiveItemRef)]
                    if isinstance(incoming_audio, list)
                    else _item_payload(incoming_audio if isinstance(incoming_audio, LiveItemRef) else None)
                ),
            },
        },
        "targets": targets,
    }


def speed_ramp_plan_payload(plan: dict[str, Any], *, include_hex: bool = False) -> dict[str, Any]:
    targets = []
    for target in plan.get("targets") or []:
        item = target.get("item")
        timemap = target.get("timemap")
        targets.append(
            {
                "side": target.get("side"),
                "media_kind": target.get("media_kind"),
                "db_type": target.get("db_type"),
                "item": _item_payload(item if isinstance(item, LiveItemRef) else None),
                "timemap": timemap.to_plan(include_hex=include_hex) if isinstance(timemap, retime_db.SpeedRampTimeMap) else None,
                "db_row": target.get("db_row"),
            }
        )
    return {
        "operation": plan.get("operation"),
        "engine": plan.get("engine"),
        "timeline_name": plan.get("timeline_name"),
        "cut": plan.get("cut"),
        "options": plan.get("options"),
        "selection": plan.get("selection"),
        "targets": targets,
    }


def _native_ramp_timemap(timemap: retime_db.SpeedRampTimeMap, row: dict[str, Any], *, source_start_frame: float | None = None) -> retime_db.SpeedRampTimeMap:
    """Place clip-relative authoring points on the native media-time axes."""
    try:
        record_origin = clip_speed_db._record_in_frames(row) / timemap.fps
    except (TypeError, ValueError, ValidationError) as exc:
        raise ValidationError("Speed-ramp planning found an invalid DB source origin.") from exc
    if not math.isfinite(record_origin) or record_origin < 0:
        raise ValidationError("Speed-ramp planning found an invalid DB source origin.")
    source_origin = record_origin if source_start_frame is None else source_start_frame / clip_speed_db._source_fps(row, fallback_fps=timemap.fps)
    points = tuple(replace(point, x=point.x + record_origin, y=point.y + source_origin) for point in timemap.keyframes)
    x_max, y_max = timemap.x_max + record_origin, timemap.y_max + source_origin
    decoded = retime_db.decode_timemap_blob(row.get("MediaTimemapBA")).get("decoded") or {}
    source_limit = (decoded.get("last_valid_seconds") if decoded.get("type") == "simple_default"
                    else decoded.get("entries", {}).get("LastValidYOffset"))
    if not isinstance(source_limit, (int, float)) or not math.isfinite(source_limit) or source_limit < 0:
        raise ValidationError("Speed-ramp planning cannot establish the available media source range.")
    source_min, source_max = retime_db.timemap_source_bounds(points)
    if not math.isfinite(source_min) or not math.isfinite(source_max) or source_min < -1e-9 or source_max > source_limit + 1e-9:
        raise ValidationError("The requested speed ramp exceeds the available media source range.")
    if timemap.timemap_encoding == "compressed-proto":
        blob = retime_db._encode_sm2_time_map_compressed_proto(
            x_max=x_max, y_max=y_max, keyframes=points, last_valid_y_offset=source_limit,
        )
    else:
        blob = retime_db._encode_sm2_time_map(x_max=x_max, y_max=y_max, last_valid_y_offset=source_limit, keyframes=points)
    return replace(timemap, media_timemap_ba=blob, keyframes=points, x_max=x_max, y_max=y_max)


def attach_db_row_plan(plan: dict[str, Any], *, project_db_path: str, timeline_name: str | None = None, exact_targets: list[LiveItemRef] | None = None) -> dict[str, Any]:
    exact_by_id = {item.item_id: item for item in exact_targets or []}
    connection = sqlite3.connect(project_db_path, timeout=2.0)
    connection.row_factory = sqlite3.Row
    try:
        cursor = connection.cursor()
        for target in plan.get("targets") or []:
            item = target.get("item")
            if not isinstance(item, LiveItemRef):
                continue
            row = db_timeline_rows.find_ti_item_row(
                cursor,
                item=item,
                db_type=str(target["db_type"]),
                timeline_name=timeline_name or plan.get("timeline_name"),
            )
            target["db_row"] = _row_summary(row)
            target["_proof_row"] = dict(row)
            local_timemap = target.setdefault("_local_timemap", target["timemap"])
            exact = exact_by_id.get(item.item_id)
            target["timemap"] = _native_ramp_timemap(
                local_timemap, dict(row), source_start_frame=(exact.source_origin_frame if exact.source_origin_frame is not None else exact.source_start_frame) if exact else None,
            )
    finally:
        connection.close()
    return plan


def preview_speed_ramp_render_updates(plan: dict[str, Any]) -> list[dict[str, Any]]:
    """Derive exact video before/after maps from the attached pre-close DB rows."""

    updates: list[dict[str, Any]] = []
    for target in plan.get("targets") or []:
        item = target.get("item")
        timemap = target.get("timemap")
        row = target.get("_proof_row")
        if target.get("media_kind") != "video" or not isinstance(item, LiveItemRef) or not isinstance(timemap, retime_db.SpeedRampTimeMap) or not isinstance(row, dict):
            continue
        updates.append({
            "media_kind": "video",
            "item_id": row.get("Sm2TiItem_id"),
            "name": row.get("Name"),
            "track_type": item.track_type,
            "track_index": item.track_index,
            "start": item.start,
            "old_duration": item.duration,
            "new_duration": timemap.output_duration_frames,
            "reference_authoring": {
                "points": timemap.keyframes,
                "record_in": clip_speed_db._record_in_frames(row),
                "record_fps": timemap.fps,
                "source_fps": clip_speed_db._source_fps(row, fallback_fps=math.nan),
            },
            "before_state": clip_speed_db.normalized_time_map_state(
                row, fps=timemap.fps, record_start_frame=item.start, fallback_duration_frames=item.duration
            ),
            "after_state": clip_speed_db.normalized_time_map_state(
                {**row, "Duration": str(timemap.output_duration_frames), "MediaTimemapBA": timemap.media_timemap_ba},
                fps=timemap.fps,
                record_start_frame=item.start,
                fallback_duration_frames=timemap.output_duration_frames,
            ),
        })
    if not updates:
        raise ValidationError("Speed-ramp rendered proof requires exact video targets with attached DB rows.")
    return updates


def require_sdk_speed_ramp_source_ranges(
    plan: dict[str, Any], exact_targets: list[LiveItemRef]
) -> None:
    """Reject an SDK ramp before mutation when its decoded map needs undeclared source frames."""

    exact_by_id = {str(item.item_id): item for item in exact_targets}
    for target in plan.get("targets") or []:
        item = target.get("item")
        timemap = target.get("timemap")
        row = target.get("_proof_row")
        if not isinstance(item, LiveItemRef) or not isinstance(timemap, retime_db.SpeedRampTimeMap) or not isinstance(row, dict):
            raise ValidationError("SDK speed-ramp source preflight requires every exact attached DB target.")
        expected = exact_by_id.get(str(item.item_id))
        if (
            expected is None
            or expected.source_start_frame is None
            or expected.source_end_frame is None
        ):
            raise ValidationError("SDK speed-ramp source preflight omitted an authoritative source range.")
        try:
            db_source_origin = clip_speed_db._record_in_frames(row)
        except (TypeError, ValueError, ValidationError) as exc:
            raise ValidationError("SDK speed-ramp source preflight found an invalid DB source origin.") from exc
        if not math.isfinite(db_source_origin):
            raise ValidationError("SDK speed-ramp source preflight found an invalid DB source origin.")
        source_fps = clip_speed_db._source_fps(row, fallback_fps=timemap.fps)
        if expected.source_origin_frame is not None:
            decoded = retime_db.decode_timemap_blob(row.get("MediaTimemapBA")).get("decoded") or {}
            limit = (decoded.get("last_valid_seconds") if decoded.get("type") == "simple_default"
                     else decoded.get("entries", {}).get("LastValidYOffset"))
            if row.get("Sm2TiItem_id") != expected.item_id or expected.source_start_frame != 0 \
                    or not isinstance(limit, (int, float)) or not math.isfinite(limit) \
                    or abs(limit * source_fps + 1 - expected.source_end_frame) > 1e-6 \
                    or abs(db_source_origin * source_fps / timemap.fps - expected.source_origin_frame) > 1e-7:
                raise ValidationError("SDK speed-ramp persisted source authority changed before mutation.")
        source_values = [value * source_fps for value in retime_db.timemap_source_bounds(timemap.keyframes)]
        if not source_values or any(
            not math.isfinite(value)
            or value < expected.source_start_frame - 1e-6
            or value >= expected.source_end_frame
            for value in source_values
        ):
            raise ValidationError(
                "The requested SDK speed ramp requires undeclared source handles.",
                details={
                    "item_id": item.item_id,
                    "source_start_frame": expected.source_start_frame,
                    "source_end_frame": expected.source_end_frame,
                },
                recoverability="not_applicable",
            )


def _row_summary(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "Sm2TiItem_id": row.get("Sm2TiItem_id"),
        "DbType": row.get("DbType"),
        "Name": row.get("Name"),
        "Start": row.get("Start"),
        "Duration": row.get("Duration"),
        "In": row.get("In"),
        "Sm2TiTrack_id": row.get("Sm2TiTrack_id"),
        "MediaTimemapBA": retime_db.timemap_blob_summary(row.get("MediaTimemapBA")),
    }


def _row_dump(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "Sm2TiItem_id": row.get("Sm2TiItem_id"),
        "DbType": row.get("DbType"),
        "Name": row.get("Name"),
        "Start": row.get("Start"),
        "Duration": row.get("Duration"),
        "In": row.get("In"),
        "Sm2TiTrack_id": row.get("Sm2TiTrack_id"),
        "MediaTimemapBA": retime_db.decode_timemap_blob(row.get("MediaTimemapBA")),
    }


def _safe_capture_label(label: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(label).strip()).strip(".-")
    return safe or "retime-reference"


def _default_capture_dir(label: str) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return Path.cwd() / "tmp" / "retime-reference" / f"{stamp}-{_safe_capture_label(label)}"


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _item_entries_for_clip_selection(selection: dict[str, Any]) -> list[tuple[str, str, LiveItemRef]]:
    entries: list[tuple[str, str, LiveItemRef]] = []
    for media_kind, db_type in (("video", "Sm2TiVideoClip"), ("audio", "Sm2TiAudioClip")):
        item = selection.get(media_kind)
        if isinstance(item, LiveItemRef):
            entries.append(("selected", db_type, item))
    return entries


def _item_entries_for_cut_selection(selection: dict[str, Any]) -> list[tuple[str, str, LiveItemRef]]:
    entries: list[tuple[str, str, LiveItemRef]] = []
    for side in ("outgoing", "incoming"):
        side_payload = selection.get(side)
        if not isinstance(side_payload, dict):
            continue
        for media_kind, db_type in (("video", "Sm2TiVideoClip"), ("audio", "Sm2TiAudioClip")):
            item = side_payload.get(media_kind)
            if isinstance(item, LiveItemRef):
                entries.append((f"{side}-{media_kind}", db_type, item))
    return entries


def _write_row_artifacts(out_dir: Path, label: str, row_payload: dict[str, Any], raw_blob: bytes) -> dict[str, str]:
    row_label = _safe_capture_label(
        "__".join(
            [
                label,
                str(row_payload.get("role") or "row"),
                str(row_payload.get("DbType") or "unknown"),
                str(row_payload.get("Start") or "start"),
                str(row_payload.get("Sm2TiItem_id") or "item")[:8],
            ]
        )
    )
    bin_path = out_dir / f"{row_label}.MediaTimemapBA.bin"
    hex_path = out_dir / f"{row_label}.MediaTimemapBA.hex.txt"
    decoded_path = out_dir / f"{row_label}.MediaTimemapBA.decoded.json"
    bin_path.write_bytes(raw_blob)
    hex_path.write_text(raw_blob.hex().upper() + "\n", encoding="utf-8")
    _write_json(decoded_path, row_payload["MediaTimemapBA"])
    return {
        "media_timemap_ba_bin": str(bin_path),
        "media_timemap_ba_hex": str(hex_path),
        "media_timemap_ba_decoded": str(decoded_path),
    }


def capture_retime_reference(
    conn: Any,
    *,
    label: str,
    clip_name: str | None = None,
    at: str | None = None,
    cut_at: str | None = None,
    track: int = 0,
    out_dir: str | None = None,
    save_project: bool = True,
    project_db_path: str | None = None,
) -> dict[str, Any]:
    """Capture raw DaVinci Resolve retime DB rows for GUI reverse-engineering."""
    safe_label = _safe_capture_label(label)
    if cut_at and (clip_name or at):
        raise ValidationError(
            "--cut-at cannot be combined with a clip name or --at for retime reference capture.",
            details={"cut_at": cut_at, "clip_name": clip_name, "at": at},
            recoverability="not_applicable",
        )
    if save_project:
        project_manager = getattr(conn, "project_manager", None)
        save_fn = getattr(project_manager, "SaveProject", None) if project_manager is not None else None
        if callable(save_fn):
            save_fn()

    timeline_name = _timeline_name(conn)
    if project_db_path is None:
        current_db = resolve_current_disk_project_db(conn)
        project_db_path = str(current_db["project_db_path"])
    else:
        current_db = {"project_db_path": project_db_path}

    if cut_at:
        selection_mode = "adjacent_cut"
        selection = db_timeline_selection.resolve_adjacent_av_cut(conn, cut_at=cut_at, track=int(track or 0))
        item_entries = _item_entries_for_cut_selection(selection)
        selection_payload: Any = {
            "cut": {
                "cut_at": selection.get("cut_at"),
                "record_frame": selection.get("record_frame"),
                "timeline_frame": selection.get("timeline_frame"),
                "track_index": selection.get("track_index"),
            },
            "outgoing": {
                "video": _item_payload(selection.get("outgoing", {}).get("video") if isinstance(selection.get("outgoing"), dict) else None),
                "audio": _item_payload(selection.get("outgoing", {}).get("audio") if isinstance(selection.get("outgoing"), dict) else None),
            },
            "incoming": {
                "video": _item_payload(selection.get("incoming", {}).get("video") if isinstance(selection.get("incoming"), dict) else None),
                "audio": _item_payload(selection.get("incoming", {}).get("audio") if isinstance(selection.get("incoming"), dict) else None),
            },
        }
    else:
        selection_mode = "linked_clip"
        selection = db_timeline_selection.resolve_linked_av_group(conn, clip_name=clip_name, at=at)
        item_entries = _item_entries_for_clip_selection(selection)
        selection_payload = {
            "video": _item_payload(selection.get("video") if isinstance(selection.get("video"), LiveItemRef) else None),
            "audio": _item_payload(selection.get("audio") if isinstance(selection.get("audio"), LiveItemRef) else None),
        }

    resolved_out_dir = Path(out_dir).expanduser() if out_dir else _default_capture_dir(safe_label)
    resolved_out_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    connection = sqlite3.connect(project_db_path, timeout=2.0)
    connection.row_factory = sqlite3.Row
    try:
        cursor = connection.cursor()
        for role, db_type, item_ref in item_entries:
            row = db_timeline_rows.find_ti_item_row(cursor, item=item_ref, db_type=db_type, timeline_name=timeline_name)
            raw_blob = bytes(row["MediaTimemapBA"] or b"")
            row_payload = {
                **_row_dump(row),
                "role": role,
                "live_track_type": item_ref.track_type,
                "live_track_index": item_ref.track_index,
                "timeline_name": timeline_name,
            }
            row_payload["artifacts"] = _write_row_artifacts(resolved_out_dir, safe_label, row_payload, raw_blob)
            rows.append(row_payload)
    finally:
        connection.close()

    payload = {
        "operation": "retime-reference-capture",
        "label": safe_label,
        "selection_mode": selection_mode,
        "timeline_name": timeline_name,
        "clip_name": clip_name,
        "at": at,
        "cut_at": cut_at,
        "track": int(track or 0),
        "current_database": current_db,
        "out_dir": str(resolved_out_dir),
        "selection": selection_payload,
        "rows": rows,
    }
    manifest_path = resolved_out_dir / f"{safe_label}.manifest.json"
    _write_json(manifest_path, payload)
    payload["manifest_path"] = str(manifest_path)
    return payload


def apply_speed_ramp_transition(cursor: sqlite3.Cursor, *, plan: dict[str, Any]) -> dict[str, Any]:
    updated: list[dict[str, Any]] = []
    timeline_name = str(plan.get("timeline_name") or "")
    for target in plan.get("targets") or []:
        item = target.get("item")
        timemap = target.get("timemap")
        if not isinstance(item, LiveItemRef) or not isinstance(timemap, retime_db.SpeedRampTimeMap):
            continue
        row = db_timeline_rows.find_ti_item_row(
            cursor,
            item=item,
            db_type=str(target["db_type"]),
            timeline_name=timeline_name or None,
        )
        db_timeline_rows.update_row(
            cursor,
            "Sm2TiItem",
            "Sm2TiItem_id",
            row["Sm2TiItem_id"],
            {
                "MediaTimemapBA": sqlite3.Binary(timemap.media_timemap_ba),
                "Duration": str(timemap.output_duration_frames),
            },
        )
        updated.append(
            {
                "side": target["side"],
                "media_kind": target["media_kind"],
                "item_id": row["Sm2TiItem_id"],
                "db_type": row["DbType"],
                "name": row["Name"],
                "track_type": item.track_type,
                "track_index": item.track_index,
                "start": item.start,
                "old_duration": item.duration,
                "new_duration": timemap.output_duration_frames,
                "source_duration_frames": timemap.source_duration_frames,
                "old_timemap": retime_db.timemap_blob_summary(row.get("MediaTimemapBA")),
                "new_timemap": timemap.to_plan(include_hex=False),
                "before_state": clip_speed_db.normalized_time_map_state(
                    dict(row), fps=timemap.fps, record_start_frame=item.start, fallback_duration_frames=item.duration
                ),
                "after_state": clip_speed_db.normalized_time_map_state(
                    {**dict(row), "Duration": str(timemap.output_duration_frames), "MediaTimemapBA": timemap.media_timemap_ba},
                    fps=timemap.fps,
                    record_start_frame=item.start,
                    fallback_duration_frames=timemap.output_duration_frames,
                ),
            }
        )
    if not updated:
        raise ValidationError("Speed-ramp DB plan did not contain any patchable targets.")
    return {
        "operation": "speed-ramp-transition",
        "timeline_name": plan.get("timeline_name"),
        "cut": plan.get("cut"),
        "options": plan.get("options"),
        "updated": updated,
    }


def _live_item_still_present(conn: Any, update: dict[str, Any]) -> bool | None:
    timeline = getattr(conn, "timeline", None)
    if timeline is None:
        return None
    try:
        items = timeline.GetItemListInTrack(str(update["track_type"]), int(update["track_index"])) or []
    except Exception:
        return None
    for item in items:
        try:
            if (
                str(item.GetName() or "") == str(update["name"] or "")
                and int(item.GetStart()) == int(update["start"])
                and int(item.GetEnd()) - int(item.GetStart()) == int(update["new_duration"])
            ):
                return True
        except Exception:
            continue
    return False


def _decoded_timemap_points(blob: bytes) -> list[dict[str, float | int]] | None:
    decoded = retime_db.decode_timemap_blob(blob)
    try:
        keyframes_ba = decoded["decoded"]["entries"]["KeyframesBA"]["decoded"]
    except (KeyError, TypeError):
        return None
    if isinstance(keyframes_ba, dict) and keyframes_ba.get("type") in {
        "RetimeKeyframeListProto", "Sm2TimeMapLegacyKeyframes",
    }:
        points = []
        for point in keyframes_ba.get("keyframes") or []:
            points.append(
                {
                    "x": float(point["x"]),
                    "y": float(point["y"]),
                    "x_in": float(point.get("x_in", 0.0)),
                    "y_in": float(point.get("y_in", 0.0)),
                    "x_out": float(point.get("x_out", 0.0)),
                    "y_out": float(point.get("y_out", 0.0)),
                    "interp": int(point.get("interp", 0)),
                }
            )
        return points
    entries = keyframes_ba.get("entries") if isinstance(keyframes_ba, dict) else None
    if not isinstance(entries, dict):
        return None
    points: list[dict[str, float | int]] = []
    for key in sorted(entries, key=lambda value: int(value)):
        point_entries = entries[key]["decoded"]["entries"]
        points.append(
            {
                "x": float(point_entries["X"]),
                "y": float(point_entries["Y"]),
                "x_in": float(point_entries["XIn"]),
                "y_in": float(point_entries["YIn"]),
                "x_out": float(point_entries["XOut"]),
                "y_out": float(point_entries["YOut"]),
                "interp": int(point_entries["interp"]),
            }
        )
    return points


def _timemap_points_match(actual: list[dict[str, float | int]] | None, expected: list[dict[str, Any]] | None) -> bool:
    if actual is None or expected is None or len(actual) != len(expected):
        return False
    float_fields = ("x", "y", "x_in", "y_in", "x_out", "y_out")
    for actual_point, expected_point in zip(actual, expected):
        for field in float_fields:
            if abs(float(actual_point[field]) - float(expected_point[field])) > 1e-7:
                return False
        if int(actual_point["interp"]) != int(expected_point.get("interp", 0)):
            return False
    return True


def verify_speed_ramp_transition(
    fresh_conn: Any,
    mutation_result: dict[str, Any],
    session: Any,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = [{"name": "project_db_route", "ok": True}]
    connection = sqlite3.connect(session.project_db_path, timeout=2.0)
    connection.row_factory = sqlite3.Row
    try:
        for update in mutation_result.get("updated") or []:
            row = connection.execute(
                'SELECT Sm2TiItem_id, Name, Start, Duration, MediaTimemapBA FROM Sm2TiItem WHERE Sm2TiItem_id = ?',
                (update["item_id"],),
            ).fetchone()
            row_ok = row is not None
            timemap = bytes(row["MediaTimemapBA"] or b"") if row_ok else b""
            duration_ok = row_ok and str(row["Duration"]) == str(update["new_duration"])
            timemap_ok = bool(timemap) and not (len(timemap) == 9 and timemap[:1] == b"\x02")
            decoded_points = _decoded_timemap_points(timemap) if timemap_ok else None
            expected_points = (update.get("new_timemap") or {}).get("keyframes")
            timemap_points_match = _timemap_points_match(decoded_points, expected_points)
            live_present = _live_item_still_present(fresh_conn, update)
            check = {
                "name": f"{update['side']}_{update['media_kind']}_{update['item_id']}",
                "ok": bool(row_ok and duration_ok and timemap_ok and timemap_points_match and live_present is not False),
                "row_present": bool(row_ok),
                "duration_ok": bool(duration_ok),
                "timemap_non_default": bool(timemap_ok),
                "timemap_points_match": bool(timemap_points_match),
                "decoded_point_count": len(decoded_points or []),
                "live_item_present_after_reopen": live_present,
            }
            checks.append(check)
    finally:
        connection.close()

    failed = [check for check in checks if not check.get("ok")]
    if failed:
        raise APICallFailed(
            "Speed-ramp DB verification failed after project reopen.",
            details={"checks": checks, "updated": mutation_result.get("updated")},
            recoverability="manual",
        )
    return {"status": "verified", "checks": checks}


def inspect_selected_retime_rows(
    conn: Any,
    *,
    clip_name: str | None = None,
    at: str | None = None,
    project_db_path: str | None = None,
    expected_targets: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if expected_targets is None:
        selection = db_timeline_selection.resolve_linked_av_group(conn, clip_name=clip_name, at=at)
        selected_items = [
            item for item in (selection.get("video"), selection.get("audio"))
            if isinstance(item, LiveItemRef)
        ]
    else:
        selected_items = db_timeline_selection.require_exact_sdk_retime_targets(
            conn, expected_targets,
        )
    timeline_name = _timeline_name(conn)
    if project_db_path is None:
        current_db = resolve_current_disk_project_db(conn)
        project_db_path = str(current_db["project_db_path"])
    else:
        current_db = {"project_db_path": project_db_path}

    rows: list[dict[str, Any]] = []
    connection = sqlite3.connect(project_db_path, timeout=2.0)
    connection.row_factory = sqlite3.Row
    try:
        cursor = connection.cursor()
        for item_ref in selected_items:
            db_type = _db_type_for_item(item_ref)
            row = db_timeline_rows.find_ti_item_row(cursor, item=item_ref, db_type=db_type, timeline_name=timeline_name)
            rows.append(
                {
                    **_row_summary(row),
                    "live_track_type": item_ref.track_type,
                    "live_track_index": item_ref.track_index,
                    "timeline_name": timeline_name,
                    "state": clip_speed_db.normalized_time_map_state(
                        dict(row),
                        fps=clip_speed_db.resolve_timeline_fps(conn),
                        record_start_frame=item_ref.start,
                        fallback_duration_frames=item_ref.duration,
                    ),
                }
            )
    finally:
        connection.close()

    return {
        "operation": "retime-db-inspect",
        "timeline_name": timeline_name,
        "clip_name": clip_name,
        "at": at,
        "current_database": current_db,
        "rows": rows,
    }
