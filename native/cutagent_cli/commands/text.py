"""Agent-facing text/title commands."""

from __future__ import annotations

import json
import os
import re
import time
import uuid
from typing import Any, Optional

import typer

from ..connection import get_connection
from ..errors import APICallFailed, ValidationError, handle_errors
from ..output import output, is_dry_run, set_execution_engine, set_recoverability, set_verification_status
from ..policy import enforce_mutation_policy
from ..utils.time_ref import parse_record_frame
from ..utils.timecode import parse_time_input, seconds_to_frames
from ..core import caption_segmentation, retime_db, text_ops, text_track_locks

app = typer.Typer(help="Agent-facing text and title insertion/update.")


def _timing_start() -> float:
    return time.perf_counter()


def _timing_add(timings: dict[str, float] | None, key: str, started_at: float) -> None:
    if timings is None:
        return
    timings[key] = timings.get(key, 0.0) + (time.perf_counter() - started_at)


def _normalize_kind(value: str, allowed: set[str], *, field: str) -> str:
    normalized = str(value or "").strip().lower().replace("_", "-")
    if normalized not in allowed:
        raise ValidationError(f"Unsupported {field}.", details={field: value, "allowed": sorted(allowed)})
    return normalized


def _list_option(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value if str(item or "").strip()]
    return [str(value)] if str(value or "").strip() else []


def _dry_run_insert_plan(
    *,
    action: str,
    intent: str,
    text_kind: str,
    route: str,
    request: dict[str, Any],
) -> dict[str, Any]:
    at = str(request.get("at") or "0s")
    duration = str(request.get("duration") or "5s")
    try:
        at_seconds = parse_time_input(at, 24.0)
    except ValidationError as exc:
        raise ValidationError("Invalid text start position.", details={"at": at}) from exc
    try:
        duration_seconds = parse_time_input(duration, 24.0)
    except ValidationError as exc:
        raise ValidationError("Invalid text duration.", details={"duration": duration}) from exc
    duration_frames = seconds_to_frames(duration_seconds, 24.0)
    if duration_frames <= 0:
        raise ValidationError("Text duration must be greater than 0.", details={"duration": duration})
    try:
        track = int(request.get("track", 1))
    except (TypeError, ValueError) as exc:
        raise ValidationError("Text track must be a positive integer.", details={"track": request.get("track")}) from exc
    if track < 1:
        raise ValidationError("Text track must be 1 or greater.", details={"track": track})
    return text_ops.agent_text_payload(
        intent=intent,
        text_kind=text_kind,
        route=route,
        request={
            **request,
            "at_seconds_at_24fps": at_seconds,
            "duration_seconds_at_24fps": duration_seconds,
            "duration_frames_at_24fps": duration_frames,
        },
        verification={"status": "not_requested"},
        fallback_used=False,
        warnings=[],
        action=action,
        dry_run=True,
        would_insert=action.startswith("text.insert"),
    )


def _load_template_batch_spec(spec_path: str | None, spec_json: str | None) -> dict[str, Any]:
    if bool(spec_path) == bool(spec_json):
        raise ValidationError(
            "Provide exactly one of --spec or --spec-json.",
            details={"spec": spec_path, "spec_json": bool(spec_json)},
        )
    if spec_path:
        path = os.path.abspath(os.path.expanduser(str(spec_path)))
        if not os.path.isfile(path):
            raise APICallFailed("Text template batch spec file not found.", details={"spec": path})
        with open(path, "r", encoding="utf-8") as handle:
            raw = handle.read()
    else:
        raw = str(spec_json or "")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValidationError("Text template batch spec must be valid JSON.", details={"error": str(exc)}) from exc
    if not isinstance(payload, dict):
        raise ValidationError("Text template batch spec must be a JSON object.")
    return payload


def _coerce_bool(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    raise ValidationError("Expected a boolean value.", details={"value": value})


def _coerce_optional_positive_int(value: Any, *, field: str) -> int | None:
    if value is None or value == "":
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{field} must be a positive integer.", details={field: value}) from exc
    if parsed < 1:
        raise ValidationError(f"{field} must be 1 or greater.", details={field: value})
    return parsed


def _normalize_template_params(value: Any, *, field: str) -> list[str]:
    if value is None:
        return []
    if isinstance(value, dict):
        return [f"{key}={val}" for key, val in value.items()]
    if isinstance(value, list):
        params = []
        for index, item in enumerate(value):
            if not isinstance(item, str) or "=" not in item:
                raise ValidationError(
                    f"{field} list values must be KEY=VALUE strings.",
                    details={field: value, "index": index},
                )
            params.append(item)
        return params
    raise ValidationError(f"{field} must be a JSON object or KEY=VALUE string list.", details={field: value})


def _parse_positive_duration_frames(value: str, fps: float) -> int:
    try:
        frames = seconds_to_frames(parse_time_input(str(value), fps), fps)
    except Exception as exc:
        raise ValidationError("Caption duration is invalid.", details={"duration": value}) from exc
    if frames <= 0:
        raise ValidationError("Caption duration must be greater than 0.", details={"duration": value})
    return frames


def _timeline_start_frame(conn: Any) -> int:
    for attr in ("start_frame", "timeline_start_frame"):
        value = getattr(conn, attr, None)
        if isinstance(value, int):
            return value
    return 0


def _video_track_items(conn: Any, track: int) -> list[Any]:
    try:
        return list(conn.timeline.GetItemListInTrack("video", track) or [])
    except Exception as exc:
        raise APICallFailed(
            "Unable to inspect video track occupancy.",
            details={"track": track},
            recoverability="manual",
        ) from exc


def _video_track_occupancy(conn: Any) -> dict[str, Any]:
    try:
        track_count = int(conn.timeline.GetTrackCount("video") or 0)
    except Exception as exc:
        raise APICallFailed(
            "Unable to inspect video track count.",
            details={"track_type": "video"},
            recoverability="manual",
        ) from exc
    tracks = []
    highest_occupied = 0
    for index in range(1, track_count + 1):
        item_count = len(_video_track_items(conn, index))
        occupied = item_count > 0
        if occupied:
            highest_occupied = index
        tracks.append({"track": index, "item_count": item_count, "occupied": occupied})
    return {
        "track_count": track_count,
        "tracks": tracks,
        "highest_occupied_track": highest_occupied,
    }


def _select_template_batch_track(
    conn: Any,
    *,
    requested_track: int | None,
    allow_create_track: bool,
    allow_non_empty_track: bool,
    require_above_occupied: bool,
) -> dict[str, Any]:
    occupancy = _video_track_occupancy(conn)
    track_count = int(occupancy["track_count"])
    highest_occupied = int(occupancy["highest_occupied_track"])
    occupied_by_track = {int(row["track"]): bool(row["occupied"]) for row in occupancy["tracks"]}

    if requested_track is not None:
        if requested_track <= track_count and occupied_by_track.get(requested_track) and not allow_non_empty_track:
            raise ValidationError(
                "Requested Text+ template track is not empty.",
                details={
                    "track": requested_track,
                    "track_policy": "explicit-empty",
                    "occupancy": occupancy,
                    "allow_non_empty_track": allow_non_empty_track,
                },
            )
        if require_above_occupied and highest_occupied and requested_track <= highest_occupied:
            raise ValidationError(
                "Requested Text+ template track must be above all existing occupied video tracks.",
                details={
                    "track": requested_track,
                    "highest_occupied_track": highest_occupied,
                    "occupancy": occupancy,
                    "require_above_occupied": require_above_occupied,
                },
            )
        if requested_track > track_count and not allow_create_track:
            raise ValidationError(
                "Requested Text+ template track does not exist and track creation is disabled.",
                details={"track": requested_track, "track_count": track_count, "allow_create_track": allow_create_track},
            )
        return {
            "selected_track": requested_track,
            "track_policy": "explicit-empty",
            "would_create_tracks": requested_track > track_count,
            "tracks_to_create": max(0, requested_track - track_count),
            "occupancy": occupancy,
        }

    first_allowed = highest_occupied + 1 if highest_occupied else 1
    selected = None
    for candidate in range(first_allowed, track_count + 1):
        if not occupied_by_track.get(candidate, False):
            selected = candidate
            break
    if selected is None:
        selected = max(track_count + 1, first_allowed)
    if selected > track_count and not allow_create_track:
        raise ValidationError(
            "No empty video track exists above occupied tracks and track creation is disabled.",
            details={
                "track_policy": "empty-above-occupied",
                "track_count": track_count,
                "highest_occupied_track": highest_occupied,
                "allow_create_track": allow_create_track,
                "occupancy": occupancy,
            },
        )
    return {
        "selected_track": selected,
        "track_policy": "empty-above-occupied",
        "would_create_tracks": selected > track_count,
        "tracks_to_create": max(0, selected - track_count),
        "occupancy": occupancy,
    }


def _normalize_template_batch_spec(raw: dict[str, Any], *, fps: float, start_frame: int) -> dict[str, Any]:
    template = str(raw.get("template") or "").strip()
    if not template:
        raise ValidationError("Text template batch spec requires template.", details={"field": "template"})
    if not os.path.isfile(os.path.abspath(os.path.expanduser(template))):
        raise APICallFailed("Text template batch template file not found.", details={"template": template})
    items = raw.get("items")
    if not isinstance(items, list) or not items:
        raise ValidationError("Text template batch spec requires a non-empty items array.", details={"field": "items"})

    track_policy = str(raw.get("track_policy") or "empty-above-occupied").strip().lower().replace("_", "-")
    if track_policy not in {"empty-above-occupied", "requested"}:
        raise ValidationError(
            "Unsupported Text+ template batch track policy.",
            details={"track_policy": raw.get("track_policy"), "allowed": ["empty-above-occupied", "requested"]},
        )
    requested_track = _coerce_optional_positive_int(raw.get("track"), field="track")
    if track_policy == "requested" and requested_track is None:
        raise ValidationError(
            "Text+ template batch requested track policy requires track.",
            details={"track_policy": track_policy, "field": "track"},
            recoverability="not_applicable",
        )
    holder_kind = _normalize_kind(str(raw.get("holder_kind") or "textplus"), {"fusion", "textplus"}, field="holder_kind")
    root_params = _normalize_template_params(raw.get("params"), field="params")
    root_duration = str(raw.get("duration") or "2s")
    normalized_items: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValidationError("Each Text+ template batch item must be a JSON object.", details={"index": index})
        text = item.get("text")
        if not isinstance(text, str) or not text.strip():
            raise ValidationError("Each Text+ template batch item requires non-empty text.", details={"index": index})
        at = str(item.get("at") or raw.get("at") or "0s")
        duration = str(item.get("duration") or root_duration)
        absolute_record_frame_value = item.get("absolute_record_frame")
        record_frame_value = item.get("record_frame")
        if absolute_record_frame_value is not None and record_frame_value is not None:
            raise ValidationError(
                "Text+ template batch item cannot specify both record_frame and absolute_record_frame.",
                details={"index": index, "record_frame": record_frame_value, "absolute_record_frame": absolute_record_frame_value},
            )
        if absolute_record_frame_value is not None:
            try:
                record_frame = int(absolute_record_frame_value)
            except (TypeError, ValueError) as exc:
                raise ValidationError(
                    "Text+ template batch absolute_record_frame must be an integer.",
                    details={"index": index, "absolute_record_frame": absolute_record_frame_value},
                ) from exc
            if record_frame < 0:
                raise ValidationError(
                    "Text+ template batch absolute_record_frame must be non-negative.",
                    details={"index": index, "absolute_record_frame": absolute_record_frame_value},
                )
        elif record_frame_value is not None:
            try:
                record_frame = parse_record_frame(str(record_frame_value), fps, start_frame)
            except Exception as exc:
                raise ValidationError(
                    "Text+ template batch record_frame must be a valid record-domain time reference.",
                    details={"index": index, "record_frame": record_frame_value},
                ) from exc
            if record_frame < 0:
                raise ValidationError(
                    "Text+ template batch record_frame must be non-negative.",
                    details={"index": index, "record_frame": record_frame_value},
                )
        else:
            record_frame = parse_record_frame(at, fps, start_frame)
        duration_frames = _parse_positive_duration_frames(duration, fps)
        item_params = _normalize_template_params(item.get("params"), field=f"items[{index}].params")
        normalized_items.append(
            {
                "index": index,
                "name": str(item.get("name") or f"Caption {index + 1:03d}"),
                "text": text,
                "at": at,
                "record_frame": record_frame,
                "duration": duration,
                "duration_frames": duration_frames,
                "end_frame": record_frame + duration_frames,
                "image": item.get("image") or raw.get("image"),
                "params": [*root_params, *item_params],
            }
        )

    sorted_items = sorted(normalized_items, key=lambda row: (row["record_frame"], row["end_frame"], row["index"]))
    overlaps = []
    for previous, current in zip(sorted_items, sorted_items[1:]):
        if int(current["record_frame"]) < int(previous["end_frame"]):
            overlaps.append(
                {
                    "left_index": previous["index"],
                    "right_index": current["index"],
                    "left_range": [previous["record_frame"], previous["end_frame"]],
                    "right_range": [current["record_frame"], current["end_frame"]],
                }
            )
    if overlaps:
        raise ValidationError(
            "Text+ template batch items overlap on the selected target track.",
            details={"overlaps": overlaps},
            recoverability="not_applicable",
        )

    return {
        "template": os.path.abspath(os.path.expanduser(template)),
        "track_policy": track_policy,
        "track": requested_track,
        "allow_create_track": _coerce_bool(raw.get("allow_create_track"), default=True),
        "allow_non_empty_track": _coerce_bool(raw.get("allow_non_empty_track"), default=False),
        "require_above_occupied": _coerce_bool(raw.get("require_above_occupied"), default=True),
        "cleanup_on_failure": _coerce_bool(raw.get("cleanup_on_failure"), default=True),
        "holder_kind": holder_kind,
        "holder": str(raw.get("holder") or ("Text+" if holder_kind == "textplus" else "Fusion Composition")),
        "style_markdown": _coerce_bool(raw.get("style_markdown"), default=True),
        "bold_style": str(raw.get("bold_style") or "ExtraBold"),
        "require_text": _coerce_bool(raw.get("require_text"), default=True),
        "require_image": _coerce_bool(raw.get("require_image"), default=False),
        "require_styling": _coerce_bool(raw.get("require_styling"), default=False),
        "items": normalized_items,
    }


def _render_template_batch_item(spec: dict[str, Any], item: dict[str, Any], *, keep_rendered: bool = False) -> dict[str, Any]:
    from ..commands import fusion as fusion_commands

    return fusion_commands._resolve_insert_setting_source(
        path=None,
        render_template=spec["template"],
        text=str(item["text"]),
        image=item.get("image"),
        style_markdown=bool(spec["style_markdown"]),
        bold_style=str(spec["bold_style"]),
        params=list(item.get("params") or []),
        require_text=bool(spec["require_text"]),
        require_image=bool(spec["require_image"]),
        require_styling=bool(spec["require_styling"]),
        keep_rendered=keep_rendered,
        rendered_output=None,
    )


def _cleanup_created_text_batch_items(conn: Any, items: list[Any]) -> dict[str, Any]:
    if not items:
        return {"attempted": False, "requested_count": 0, "deleted": False, "deleted_count": 0, "error": None}
    deleter = getattr(getattr(conn, "timeline", None), "DeleteClips", None)
    if not callable(deleter):
        return {
            "attempted": True,
            "requested_count": len(items),
            "deleted": False,
            "deleted_count": 0,
            "error": "Timeline.DeleteClips is unavailable.",
        }
    try:
        try:
            result = deleter(items, False)
        except TypeError:
            result = deleter(items)
    except Exception as exc:
        return {
            "attempted": True,
            "requested_count": len(items),
            "deleted": False,
            "deleted_count": 0,
            "error": str(exc),
        }
    return {
        "attempted": True,
        "requested_count": len(items),
        "deleted": result is not False,
        "deleted_count": len(items) if result is not False else 0,
        "error": None,
    }


_FAST_TEXTPLUS_CUT_PREFIX = "__CUTAGENT_TEXTPLUS_CUT__"


def _set_video_track_locks_for_fast_textplus(conn: Any, selected_track: int) -> dict[str, Any]:
    return text_track_locks.set_timeline_track_locks_for_textplus_batch(conn, selected_track)


def _restore_video_track_locks(conn: Any, snapshot: dict[str, Any]) -> dict[str, Any]:
    return text_track_locks.restore_video_track_locks(conn, snapshot)


def _fast_textplus_lock_setup_errors(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    return text_track_locks.track_lock_setup_errors(snapshot)


def _apply_timeline_item_name_only(item: Any, *, name: str) -> dict[str, Any]:
    attempts: list[dict[str, Any]] = []
    applied = False
    setter = getattr(item, "SetName", None)
    if callable(setter):
        try:
            result = setter(name)
            attempts.append({"method": "SetName", "result": result})
            applied = applied or result is not False
        except Exception as exc:
            attempts.append({"method": "SetName", "error": str(exc)})
    prop_setter = getattr(item, "SetProperty", None)
    if callable(prop_setter):
        for key in ("Name", "Clip Name", "ClipName"):
            try:
                result = prop_setter(key, name)
                attempts.append({"method": "SetProperty", "key": key, "result": result})
                applied = applied or result is not False
                if result is not False:
                    break
            except Exception as exc:
                attempts.append({"method": "SetProperty", "key": key, "error": str(exc)})
    return {"name_requested": name, "name_applied": applied, "name_attempts": attempts}


def _duration_batch_entry_for_textplus_item(
    *,
    event: dict[str, Any],
    selected_track: int,
) -> dict[str, Any]:
    item_info = dict(event.get("item") or {})
    duration_frames = int(event["duration_frames"])
    entry: dict[str, Any] = {
        "track_type": "video",
        "track_index": int(selected_track),
        "duration": f"{duration_frames}f",
        "target_start_frame": f"{int(event['frame'])}f",
        "allow_overlap": False,
        "no_source_bounds": True,
    }
    item_id = str(item_info.get("timeline_item_id") or "").strip()
    if item_id:
        entry["item_id"] = item_id
        return entry

    start = item_info.get("start")
    if start is None:
        raise APICallFailed(
            "Direct Text+ batch cannot build duration update selector for inserted item.",
            details={"event": {key: value for key, value in event.items() if key != "native_item"}},
            recoverability="manual",
        )
    entry.update(
        {
            "start_frame": f"{int(start)}f",
            "name": str(event["name"]),
        }
    )
    return entry


def _timeline_item_id_from_row(row: dict[str, Any] | None) -> str | None:
    if not isinstance(row, dict):
        return None
    value = row.get("timeline_item_id")
    if value in (None, ""):
        return None
    return str(value)


def _timeline_item_guard_row(item: Any) -> dict[str, Any]:
    row: dict[str, Any] = {}
    for key, method_name in (
        ("name", "GetName"),
        ("start", "GetStart"),
        ("end", "GetEnd"),
        ("duration", "GetDuration"),
    ):
        getter = getattr(item, method_name, None)
        if not callable(getter):
            continue
        try:
            value = getter()
        except Exception as exc:
            value = f"<read-error:{exc}>"
        row[key] = value
    return row


def _snapshot_fast_textplus_non_target_tracks(conn: Any, *, selected_track: int) -> dict[str, Any]:
    timeline = getattr(conn, "timeline", None)
    rows: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    if timeline is None:
        return {"checked": False, "reason": "timeline unavailable", "tracks": rows, "errors": errors}
    for track_type in ("video", "audio", "subtitle"):
        try:
            track_count = int(timeline.GetTrackCount(track_type) or 0)
        except Exception as exc:
            errors.append({"track_type": track_type, "reason": "track_count_unreadable", "error": str(exc)})
            continue
        for index in range(1, track_count + 1):
            if track_type == "video" and int(index) == int(selected_track):
                continue
            try:
                items = list(timeline.GetItemListInTrack(track_type, index) or [])
            except Exception as exc:
                errors.append({"track_type": track_type, "track": index, "reason": "track_items_unreadable", "error": str(exc)})
                continue
            item_rows = [_timeline_item_guard_row(item) for item in items]
            rows.append(
                {
                    "track_type": track_type,
                    "track": index,
                    "item_count": len(item_rows),
                    "items": item_rows,
                }
            )
    return {"checked": True, "selected_track": int(selected_track), "tracks": rows, "errors": errors}


def _compare_fast_textplus_non_target_snapshots(before: dict[str, Any], after: dict[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for label, snapshot in (("before", before), ("after", after)):
        if not snapshot.get("checked"):
            issues.append({"phase": label, "reason": snapshot.get("reason") or "snapshot_not_checked"})
        for error in snapshot.get("errors") or []:
            issues.append({"phase": label, **dict(error)})
    before_tracks = {
        (str(row.get("track_type")), int(row.get("track") or 0)): row
        for row in before.get("tracks") or []
    }
    after_tracks = {
        (str(row.get("track_type")), int(row.get("track") or 0)): row
        for row in after.get("tracks") or []
    }
    for key in sorted(set(before_tracks) | set(after_tracks)):
        before_row = before_tracks.get(key)
        after_row = after_tracks.get(key)
        if before_row is None or after_row is None:
            issues.append(
                {
                    "track_type": key[0],
                    "track": key[1],
                    "reason": "non_target_track_set_changed",
                    "before_present": before_row is not None,
                    "after_present": after_row is not None,
                }
            )
            continue
        if int(before_row.get("item_count") or 0) != int(after_row.get("item_count") or 0):
            issues.append(
                {
                    "track_type": key[0],
                    "track": key[1],
                    "reason": "non_target_item_count_changed",
                    "before_count": before_row.get("item_count"),
                    "after_count": after_row.get("item_count"),
                    "before_items": before_row.get("items"),
                    "after_items": after_row.get("items"),
                }
            )
            continue
        if list(before_row.get("items") or []) != list(after_row.get("items") or []):
            issues.append(
                {
                    "track_type": key[0],
                    "track": key[1],
                    "reason": "non_target_items_changed",
                    "before_items": before_row.get("items"),
                    "after_items": after_row.get("items"),
                }
            )
    return issues


def _compact_fast_textplus_non_target_snapshot(snapshot: dict[str, Any] | None) -> dict[str, Any] | None:
    if snapshot is None:
        return None
    tracks = [
        {
            "track_type": row.get("track_type"),
            "track": row.get("track"),
            "item_count": row.get("item_count"),
        }
        for row in snapshot.get("tracks") or []
    ]
    return {
        "checked": bool(snapshot.get("checked")),
        "selected_track": snapshot.get("selected_track"),
        "track_count": len(tracks),
        "tracks": tracks,
        "errors": list(snapshot.get("errors") or []),
    }


def _read_video_track_rows(conn: Any, track: int) -> list[dict[str, Any]]:
    from ..commands import fusion as fusion_commands

    try:
        items = conn.timeline.GetItemListInTrack("video", int(track)) or []
    except Exception as exc:
        raise APICallFailed(
            "Unable to read Text+ template target track after insertion.",
            details={"track": track, "error": str(exc)},
            recoverability="manual",
        ) from exc
    rows = []
    for item in items:
        readback = fusion_commands._timeline_item_readback(item, track_index=int(track))
        rows.append({"item": item, **readback})
    return rows


def _delete_fast_textplus_extra_items(
    conn: Any,
    *,
    selected_track: int,
    expected_items: list[dict[str, Any]],
) -> dict[str, Any]:
    try:
        track_count = int(conn.timeline.GetTrackCount("video") or 0)
    except Exception:
        track_count = int(selected_track)

    expected_counts: dict[tuple[str, int, int], int] = {}
    expected_names = set()
    for item in expected_items:
        name = str(item["name"])
        expected_names.add(name)
        key = (name, int(item["record_frame"]), int(item["duration_frames"]))
        expected_counts[key] = expected_counts.get(key, 0) + 1

    keep_counts: dict[tuple[str, int, int], int] = {}
    delete_items: list[Any] = []
    scanned_rows: list[dict[str, Any]] = []
    for track in range(1, track_count + 1):
        for row in _read_video_track_rows(conn, track):
            name = str(row.get("name") or "")
            start = row.get("start")
            duration = row.get("duration")
            scanned_rows.append({key: value for key, value in row.items() if key != "item"})
            should_delete = False
            if name.startswith(_FAST_TEXTPLUS_CUT_PREFIX):
                should_delete = True
            elif track == int(selected_track) and name in expected_names:
                key = (name, int(start) if start is not None else -1, int(duration) if duration is not None else -1)
                if keep_counts.get(key, 0) < expected_counts.get(key, 0):
                    keep_counts[key] = keep_counts.get(key, 0) + 1
                else:
                    should_delete = True
            if should_delete:
                delete_items.append(row["item"])

    cleanup = _cleanup_created_text_batch_items(conn, delete_items)
    cleanup["scanned_count"] = len(scanned_rows)
    cleanup["extra_count"] = len(delete_items)
    cleanup["scanned"] = scanned_rows
    return cleanup


def _ensure_edit_page_for_textplus_holder(conn: Any) -> dict[str, Any]:
    resolve = getattr(conn, "resolve", None)
    if resolve is None:
        return {"attempted": False, "reason": "resolve_handle_unavailable"}
    get_current_page = getattr(resolve, "GetCurrentPage", None)
    open_page = getattr(resolve, "OpenPage", None)
    if not callable(get_current_page) or not callable(open_page):
        return {"attempted": False, "reason": "page_api_unavailable"}
    try:
        previous_page = str(get_current_page() or "").lower()
    except Exception as exc:
        return {"attempted": False, "reason": "current_page_read_failed", "error": str(exc)}
    if previous_page == "edit":
        return {"attempted": True, "changed": False, "previous_page": previous_page, "current_page": previous_page}
    try:
        result = bool(open_page("edit"))
        current_page = str(get_current_page() or "").lower()
    except Exception as exc:
        raise APICallFailed(
            "Text+ template insertion could not switch DaVinci Resolve to the Edit page.",
            details={"previous_page": previous_page, "error": str(exc)},
            recoverability="retryable",
        ) from exc
    if not result or current_page != "edit":
        raise APICallFailed(
            "Text+ template insertion requires the Edit page before native holder insertion.",
            details={"previous_page": previous_page, "current_page": current_page, "api_result": result},
            recoverability="retryable",
        )
    return {"attempted": True, "changed": True, "previous_page": previous_page, "current_page": current_page}


def _insert_direct_textplus_template_item(
    conn: Any,
    *,
    fusion_commands: Any,
    source_payload: dict[str, Any],
    item: dict[str, Any],
    selected_track: int,
    holder: str,
    pre_track_signatures: set[tuple[Any, Any, Any, Any]],
    defer_duration_db_batch: bool = False,
    timings: dict[str, float] | None = None,
) -> tuple[Any, dict[str, Any]]:
    frame = int(item["record_frame"])
    duration_frames = int(item["duration_frames"])
    clip_name = str(item["name"])
    native_item = None
    layout_prepared = None
    layout = None
    page_switch: dict[str, Any] = {"attempted": False}

    try:
        phase_started = _timing_start()
        page_switch = _ensure_edit_page_for_textplus_holder(conn)
        _timing_add(timings, "09_ensure_edit_page", phase_started)
        phase_started = _timing_start()
        native_item, native_insert = fusion_commands._insert_native_holder_at_frame(
            conn,
            holder=holder,
            holder_kind="textplus",
            record_frame=frame,
        )
        _timing_add(timings, "10_insert_native_textplus_holder", phase_started)
        phase_started = _timing_start()
        initial_readback = fusion_commands._timeline_item_readback(native_item, track_index=int(selected_track))
        _timing_add(timings, "10a_initial_insert_readback", phase_started)
        if initial_readback.get("track_index") not in (int(selected_track), None) or initial_readback.get("start") not in (frame, None):
            cleanup = fusion_commands._safe_delete_timeline_item(conn, native_item)
            raise APICallFailed(
                "Direct Text+ batch insertion missed the requested target track/start.",
                details={
                    "name": clip_name,
                    "requested": {"track": int(selected_track), "record_frame": frame},
                    "readback": initial_readback,
                    "cleanup": cleanup,
                },
                recoverability="manual",
            )

        importer = getattr(native_item, "ImportFusionComp", None)
        if not callable(importer):
            cleanup = fusion_commands._safe_delete_timeline_item(conn, native_item)
            raise APICallFailed(
                "Inserted Text+ holder clip does not support ImportFusionComp.",
                details={"name": clip_name, "holder": holder, "holder_kind": "textplus", "cleanup": cleanup},
                recoverability="manual",
            )

        phase_started = _timing_start()
        layout_prepared = fusion_commands._prepare_setting_import(str(source_payload["path"]))
        import_path = str(layout_prepared.get("import_path") or source_payload["path"])
        _timing_add(timings, "11a_prepare_setting_import", phase_started)
        try:
            phase_started = _timing_start()
            imported = importer(import_path)
            _timing_add(timings, "11_import_fusion_comp", phase_started)
        except Exception as exc:
            layout = fusion_commands._cleanup_prepared_setting(layout_prepared)
            cleanup = fusion_commands._safe_delete_timeline_item(conn, native_item)
            raise APICallFailed(
                "ImportFusionComp failed during direct Text+ batch insertion.",
                details={
                    "name": clip_name,
                    "path": source_payload.get("path"),
                    "import_path": import_path,
                    "holder": holder,
                    "holder_kind": "textplus",
                    "layout": layout,
                    "cleanup": cleanup,
                    "error": str(exc),
                },
                recoverability="manual",
            ) from exc
        if imported is False:
            layout = fusion_commands._cleanup_prepared_setting(layout_prepared)
            cleanup = fusion_commands._safe_delete_timeline_item(conn, native_item)
            raise APICallFailed(
                "ImportFusionComp failed during direct Text+ batch insertion.",
                details={
                    "name": clip_name,
                    "path": source_payload.get("path"),
                    "import_path": import_path,
                    "holder": holder,
                    "holder_kind": "textplus",
                    "layout": layout,
                    "cleanup": cleanup,
                },
                recoverability="manual",
            )
        phase_started = _timing_start()
        layout = fusion_commands._cleanup_prepared_setting(layout_prepared)
        _timing_add(timings, "13a_cleanup_prepared_setting_layout", phase_started)

        if defer_duration_db_batch:
            phase_started = _timing_start()
            item_props = _apply_timeline_item_name_only(native_item, name=clip_name)
            _timing_add(timings, "12_apply_clip_name", phase_started)
            phase_started = _timing_start()
            readback = fusion_commands._timeline_item_readback(native_item, track_index=int(selected_track))
            _timing_add(timings, "12a_post_import_readback", phase_started)
            duration_verify_attempts: list[dict[str, Any]] = [{"attempt": 0, "readback": readback, "deferred_to_db_batch": True}]
        else:
            phase_started = _timing_start()
            item_props = fusion_commands._apply_timeline_item_name_and_duration(
                native_item,
                name=clip_name,
                duration_frames=duration_frames,
            )
            _timing_add(timings, "12_apply_clip_name_and_duration", phase_started)
            phase_started = _timing_start()
            readback = fusion_commands._timeline_item_readback(native_item, track_index=int(selected_track))
            _timing_add(timings, "12a_post_import_readback", phase_started)
            duration_verify_attempts = [{"attempt": 0, "readback": readback}]
            if readback.get("duration") != duration_frames:
                phase_started = _timing_start()
                for attempt in range(1, 13):
                    time.sleep(0.05)
                    retry_props = fusion_commands._apply_timeline_item_name_and_duration(
                        native_item,
                        name=clip_name,
                        duration_frames=duration_frames,
                    )
                    readback = fusion_commands._timeline_item_readback(native_item, track_index=int(selected_track))
                    duration_verify_attempts.append({"attempt": attempt, "props": retry_props, "readback": readback})
                    if readback.get("duration") == duration_frames:
                        break
                _timing_add(timings, "12c_verify_native_duration", phase_started)
            if readback.get("duration") != duration_frames:
                cleanup = fusion_commands._safe_delete_timeline_item(conn, native_item)
                raise APICallFailed(
                    "Direct Text+ batch could not verify native holder duration.",
                    details={
                        "name": clip_name,
                        "requested": {"track": int(selected_track), "record_frame": frame, "duration_frames": duration_frames},
                        "duration_verify_attempts": duration_verify_attempts,
                        "cleanup": cleanup,
                    },
                    recoverability="manual",
                )
        phase_started = _timing_start()
        tool_summary = fusion_commands._summarize_imported_fusion_tools(native_item)
        _timing_add(timings, "12b_summarize_imported_fusion_tools", phase_started)
        if tool_summary.get("accessible") is not False and tool_summary.get("tool_count") == 0:
            cleanup = fusion_commands._safe_delete_timeline_item(conn, native_item)
            raise APICallFailed(
                "Inserted .setting, but the Fusion composition has no readable tools.",
                details={"path": source_payload.get("path"), "item": readback, "cleanup": cleanup},
                recoverability="manual",
            )

        verification = {
            "imported": bool(imported),
            "track_requested": int(selected_track),
            "track_readback": readback.get("track_index"),
            "record_frame_requested": frame,
            "start_readback": readback.get("start"),
            "duration_requested_frames": duration_frames,
            "duration_readback_frames": readback.get("duration"),
            "duration_deferred_to_db_batch": bool(defer_duration_db_batch),
            "fusion_comp_accessible": bool(tool_summary.get("accessible")),
            "tool_count": tool_summary.get("tool_count"),
            "track_ok": readback.get("track_index") in (int(selected_track), None),
            "start_ok": readback.get("start") in (frame, None),
            "duration_ok": bool(defer_duration_db_batch) or readback.get("duration") == duration_frames,
            "node_status_verified": False,
            "node_probe_verified": False,
            "visual_output_verified": False,
        }
        return native_item, {
            "path": str(source_payload["path"]),
            "import_path": import_path,
            "name": clip_name,
            "holder": holder,
            "holder_kind": "textplus",
            "route": (
                "timeline.SetTrackLock(batch) -> timeline.InsertFusionTitleIntoTimeline(reverse) -> "
                "timeline_item.ImportFusionComp -> project_db.set_duration(batch)"
                if defer_duration_db_batch
                else "timeline.SetTrackLock(batch) -> timeline.InsertFusionTitleIntoTimeline -> timeline_item.ImportFusionComp -> timeline_item.SetProperty(Duration)"
            ),
            "page_switch": page_switch,
            "native_insert": native_insert,
            "native_direct_batch": True,
            "db_move": None,
            "duration_db_update": (
                "deferred_batch" if defer_duration_db_batch else None
            ),
            "duration_verify_attempts": duration_verify_attempts,
            "item": {**item_props, **readback},
            "fusion": tool_summary,
            "layout": layout,
            "verification": verification,
        }
    except Exception:
        if layout_prepared is not None and layout is None:
            try:
                fusion_commands._cleanup_prepared_setting(layout_prepared)
            except Exception:
                pass
        raise


def _lua_quote(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _replace_textplus_styled_text(inner: bytes, text: str, *, old_text: str | None = None) -> bytes:
    source = inner.decode("utf-8", errors="strict")
    quoted = _lua_quote(text)

    updated, count = re.subn(
        r'(StyledText\s*=\s*Input\s*\{\s*Value\s*=\s*").*?(",\s*\})',
        lambda match: f"{match.group(1)}{quoted}{match.group(2)}",
        source,
        count=1,
        flags=re.DOTALL,
    )
    if count:
        return updated.encode("utf-8")

    updated, count = re.subn(
        r'(Text\s*=\s*Input\s*\{\s*Value\s*=\s*").*?(",\s*\})',
        lambda match: f"{match.group(1)}{quoted}{match.group(2)}",
        source,
        count=1,
        flags=re.DOTALL,
    )
    if count:
        return updated.encode("utf-8")

    if old_text:
        updated = source.replace(_lua_quote(str(old_text)), quoted)
        if updated != source:
            return updated.encode("utf-8")

    if count < 1:
        raise APICallFailed(
            "Text+ template seed does not contain a replaceable StyledText input.",
            details={"reason": "styled_text_input_missing", "supported_patterns": ["StyledText.Value", "Text.Value", "old_text_literal"]},
            recoverability="manual",
        )
    return source.encode("utf-8")


def _strip_lua_line_comments(source: str) -> str:
    result: list[str] = []
    index = 0
    in_string = False
    escape = False
    length = len(source)
    while index < length:
        char = source[index]
        if in_string:
            result.append(char)
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            index += 1
            continue
        if char == '"':
            in_string = True
            result.append(char)
            index += 1
            continue
        if char == "-" and index + 1 < length and source[index + 1] == "-":
            while index < length and source[index] not in "\r\n":
                index += 1
            continue
        result.append(char)
        index += 1
    return "".join(result)


def _matching_lua_brace(source: str, open_index: int) -> int:
    depth = 0
    index = open_index
    in_string = False
    escape = False
    length = len(source)
    while index < length:
        char = source[index]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            index += 1
            continue
        if char == '"':
            in_string = True
            index += 1
            continue
        if char == "-" and index + 1 < length and source[index + 1] == "-":
            while index < length and source[index] not in "\r\n":
                index += 1
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index
        index += 1
    return -1


def _rendered_textplus_setting_to_db_inner_payload(rendered_setting: bytes) -> bytes:
    source = rendered_setting.decode("utf-8", errors="strict")
    match = re.search(r"\bTools\s*=\s*ordered\s*\(\s*\)\s*\{", source)
    if match:
        open_index = source.find("{", match.start())
        close_index = _matching_lua_brace(source, open_index)
        if close_index < 0:
            raise APICallFailed(
                "Rendered Text+ template payload has an unterminated Tools block.",
                details={"reason": "rendered_setting_tools_block_unterminated"},
                recoverability="manual",
            )
        tools_body = _strip_lua_line_comments(source[open_index + 1 : close_index]).strip()
        if not tools_body:
            raise APICallFailed(
                "Rendered Text+ template payload has an empty Tools block.",
                details={"reason": "rendered_setting_tools_block_empty"},
                recoverability="manual",
            )
        inner = f"{{ {tools_body} }}\0".encode("utf-8")
    else:
        stripped = _strip_lua_line_comments(source).strip()
        if not stripped.startswith("{"):
            raise APICallFailed(
                "Rendered Text+ template payload is not a supported Fusion setting format.",
                details={"reason": "rendered_setting_tools_block_missing"},
                recoverability="manual",
            )
        inner = stripped.encode("utf-8")
        if not inner.endswith(b"\0"):
            inner += b"\0"

    if b"TextPlus" not in inner or b"MediaOut" not in inner:
        raise APICallFailed(
            "Rendered Text+ template payload does not contain the expected Text+ tool graph.",
            details={"reason": "rendered_setting_missing_textplus_graph"},
            recoverability="manual",
        )
    if b"Tools = ordered()" in inner:
        raise APICallFailed(
            "Rendered Text+ template payload was not converted to the DaVinci Resolve DB inner format.",
            details={"reason": "rendered_setting_wrapper_not_removed"},
            recoverability="manual",
        )
    return inner


def _build_textplus_composition_blob(
    seed_blob: bytes,
    *,
    old_item_id: str,
    new_item_id: str,
    text: str,
    old_text: str | None = None,
    rendered_inner: bytes | None = None,
) -> bytes:
    from ..core import fusion_composition_db

    def transform(inner: bytes) -> bytes:
        if rendered_inner is None:
            return _replace_textplus_styled_text(inner, text, old_text=old_text)
        replacement = bytes(rendered_inner)
        old_id_bytes = old_item_id.encode("utf-8")
        return replacement.replace(old_id_bytes, new_item_id.encode("utf-8"))

    return fusion_composition_db.rebuild_composition_blob(
        seed_blob,
        old_item_id=old_item_id,
        new_item_id=new_item_id,
        transform_inner=transform,
    )


def _read_rendered_textplus_inner_payload(source_payload: dict[str, Any]) -> bytes:
    path = os.path.abspath(os.path.expanduser(str(source_payload.get("path") or "")))
    if not path or not os.path.isfile(path):
        raise APICallFailed(
            "Rendered Text+ template payload is not available for DB batch insertion.",
            details={"path": path or None, "reason": "rendered_setting_missing"},
            recoverability="manual",
        )
    try:
        rendered = open(path, "rb").read()
    except OSError as exc:
        raise APICallFailed(
            "Rendered Text+ template payload could not be read for DB batch insertion.",
            details={"path": path, "error": str(exc)},
            recoverability="manual",
        ) from exc
    if b"TextPlus" not in rendered and b"StyledText" not in rendered and b"Text = Input" not in rendered:
        raise APICallFailed(
            "Rendered Text+ template payload does not look like a Text+ Fusion setting.",
            details={"path": path, "reason": "rendered_setting_not_textplus"},
            recoverability="manual",
        )
    return _rendered_textplus_setting_to_db_inner_payload(rendered)


def _textplus_db_item_payload(
    seed_item: dict[str, Any],
    *,
    item_id: str,
    comp_id: str,
    track_id: str,
    name: str,
    start: int,
    duration: int,
    fps: float,
) -> dict[str, Any]:
    payload = dict(seed_item)
    payload.update(
        {
            "Sm2TiItem_id": item_id,
            "Name": name,
            "Start": str(int(start)),
            "Duration": str(int(duration)),
            "MediaTimemapBA": retime_db.default_timemap(int(duration), float(fps or 24.0)),
            "Sm2TiTrack_id": track_id,
            "CompositionTable": comp_id,
        }
    )
    return payload


def _textplus_db_comp_payload(
    seed_comp: dict[str, Any],
    *,
    comp_id: str,
    item_id: str,
    composition_blob: bytes,
) -> dict[str, Any]:
    payload = dict(seed_comp)
    payload.update(
        {
            "Sm2TiCompositionTable_id": comp_id,
            "Sm2TiItem_id": item_id,
            "CompositionBA": composition_blob,
        }
    )
    return payload


def _summarize_textplus_db_item_graph(item: Any) -> dict[str, Any]:
    summary: dict[str, Any] = {"accessible": False, "tool_count": 0, "tools": []}
    comp = None
    try:
        if hasattr(item, "GetFusionCompByIndex"):
            comp = item.GetFusionCompByIndex(1)
    except Exception as exc:
        return {**summary, "error": str(exc)}
    if comp is None:
        return summary

    summary["accessible"] = True
    try:
        getter = getattr(comp, "GetToolList", None)
        if not callable(getter):
            return {**summary, "error": "GetToolList unavailable"}
        try:
            tool_list = getter(False) or {}
        except TypeError:
            tool_list = getter() or {}
    except Exception as exc:
        return {**summary, "error": str(exc)}

    values = tool_list.values() if hasattr(tool_list, "values") else tool_list
    tools = []
    for key, tool in enumerate(values or []):
        attrs = {}
        try:
            attrs = tool.GetAttrs() if hasattr(tool, "GetAttrs") else {}
        except Exception:
            attrs = {}
        name = None
        try:
            name = attrs.get("TOOLS_Name") or getattr(tool, "Name", None)
        except Exception:
            name = None
        tools.append({"index": key, "name": str(name or key), "type": str(attrs.get("TOOLS_RegID") or "")})
    summary["tools"] = tools
    summary["tool_count"] = len(tools)
    summary["has_textplus"] = any(str(row.get("type") or "").lower() == "textplus" for row in tools)
    summary["has_mediaout"] = any(str(row.get("type") or "").lower() == "mediaout" for row in tools)
    return summary


def _textplus_db_graph_sample_indices(count: int) -> list[int]:
    if count <= 0:
        return []
    if count <= 10:
        return list(range(count))
    indices = {0, 1, 2, count // 2 - 1, count // 2, count // 2 + 1, count - 3, count - 2, count - 1}
    return sorted(index for index in indices if 0 <= index < count)


def _verify_textplus_db_batch_track(fresh_conn: Any, mutation_result: dict[str, Any], _session: Any) -> dict[str, Any]:
    selected_track = int(mutation_result["selected_track"])
    expected = list(mutation_result.get("expected") or [])
    rows = _read_video_track_rows(fresh_conn, selected_track)
    compact_rows = [{key: value for key, value in row.items() if key != "item"} for row in rows]
    expected_counts: dict[tuple[str, int, int], int] = {}
    expected_rows: dict[tuple[str, int, int], list[dict[str, Any]]] = {}
    for row in expected:
        key = (str(row["name"]), int(row["record_frame"]), int(row["duration_frames"]))
        expected_counts[key] = expected_counts.get(key, 0) + 1
        expected_rows.setdefault(key, []).append(row)
    checks = []
    matched_rows: list[dict[str, Any]] = []
    for source_row, row in zip(rows, compact_rows):
        key = (
            str(row.get("name") or ""),
            int(row.get("start") if row.get("start") is not None else -1),
            int(row.get("duration") if row.get("duration") is not None else -1),
        )
        expected_row = expected_rows.get(key, [None])[0]
        ok = expected_counts.get(key, 0) > 0
        if ok:
            expected_counts[key] = expected_counts.get(key, 0) - 1
            matched_rows.append(source_row)
        checks.append(
            {
                "name": row.get("name"),
                "ok": ok,
                "readback": row,
                "expected": expected_row,
            }
        )
    missing = []
    for key, remaining in expected_counts.items():
        if remaining <= 0:
            continue
        missing.extend(expected_rows.get(key, [])[:remaining])
    graph_checks: list[dict[str, Any]] = []
    graph_status = "skipped_no_item_objects"
    item_rows = [row for row in matched_rows if row.get("item") is not None]
    if item_rows:
        graph_status = "verified"
        for index in _textplus_db_graph_sample_indices(len(item_rows)):
            row = item_rows[index]
            graph = _summarize_textplus_db_item_graph(row["item"])
            ok = bool(graph.get("accessible")) and bool(graph.get("has_textplus")) and bool(graph.get("has_mediaout"))
            graph_checks.append(
                {
                    "sample_index": index,
                    "name": row.get("name"),
                    "start": row.get("start"),
                    "duration": row.get("duration"),
                    "ok": ok,
                    "graph": graph,
                }
            )
            if not ok:
                graph_status = "failed"

    placement_status = len(compact_rows) == len(expected) and not missing and all(row["ok"] for row in checks)
    status = "verified" if placement_status and graph_status != "failed" else "failed"
    if status != "verified":
        raise APICallFailed(
            "Text+ DB batch verification failed after reopening DaVinci Resolve project.",
            details={
                "selected_track": selected_track,
                "expected_count": len(expected),
                "readback_count": len(compact_rows),
                "missing": missing[:10],
                "failed_checks": [row for row in checks if not row["ok"]][:10],
                "fusion_graph_status": graph_status,
                "failed_fusion_graph_checks": [row for row in graph_checks if not row["ok"]][:10],
                "readback_sample": compact_rows[:5] + compact_rows[-5:],
            },
            recoverability="manual",
        )
    return {
        "status": "verified",
        "selected_track": selected_track,
        "created_count": len(compact_rows),
        "planned_count": len(expected),
        "max_count_possible_during_db_route": len(expected),
        "sample": compact_rows[:3] + compact_rows[-3:],
        "fusion_graph_status": graph_status,
        "fusion_graph_checks": graph_checks,
        "failed_checks": [],
    }


def _cleanup_textplus_db_seed_clip(conn: Any, *, selected_track: int, seed_name: str) -> dict[str, Any]:
    cleanup_conn = conn
    refresh = getattr(cleanup_conn, "refresh", None)
    if callable(refresh):
        try:
            refresh()
        except Exception:
            pass

    def scan_and_delete(candidate_conn: Any) -> dict[str, Any]:
        try:
            track_count = int(candidate_conn.timeline.GetTrackCount("video") or 0)
        except Exception:
            track_count = int(selected_track)
        seed_items: list[Any] = []
        scanned: list[dict[str, Any]] = []
        for track in range(1, track_count + 1):
            for row in _read_video_track_rows(candidate_conn, track):
                compact = {key: value for key, value in row.items() if key != "item"}
                scanned.append(compact)
                if str(row.get("name") or "") == seed_name:
                    seed_items.append(row["item"])
        cleanup = _cleanup_created_text_batch_items(candidate_conn, seed_items)
        cleanup.update({"seed_name": seed_name, "seed_count": len(seed_items), "scanned_count": len(scanned), "scanned": scanned[:10]})
        return cleanup

    try:
        return scan_and_delete(cleanup_conn)
    except Exception as first_exc:
        try:
            fresh_conn = get_connection(require_timeline=True)
            return scan_and_delete(fresh_conn)
        except Exception as second_exc:
            return {
                "attempted": True,
                "deleted": False,
                "deleted_count": 0,
                "seed_name": seed_name,
                "error": str(second_exc),
                "first_error": str(first_exc),
            }


def _insert_textplus_template_batch_db(
    conn: Any,
    *,
    normalized: dict[str, Any],
    selected_track: int,
    track_plan: dict[str, Any],
    track_summary: dict[str, Any],
) -> dict[str, Any]:
    from ..commands import fusion as fusion_commands
    from ..core import db_session, db_timeline_rows, project_ops, retime_db, timeline_item_duration_db

    ordered_items = sorted(normalized["items"], key=lambda row: (int(row["record_frame"]), int(row["index"])))
    first_item = ordered_items[0]
    rendered_payloads: list[dict[str, Any]] = []
    try:
        for item in ordered_items:
            source_payload = _render_template_batch_item(normalized, item)
            rendered_payloads.append(
                {
                    "item_index": int(item["index"]),
                    "source": source_payload,
                    "inner": _read_rendered_textplus_inner_payload(source_payload),
                }
            )
    except Exception:
        for rendered in rendered_payloads:
            fusion_commands._delete_rendered_setting((rendered.get("source") or {}).get("cleanup_path"))
        raise
    source_payload = rendered_payloads[0]["source"]
    rendered_inner_by_index = {int(row["item_index"]): bytes(row["inner"]) for row in rendered_payloads}
    rendered_cleanup_done = False

    def cleanup_rendered_payloads() -> None:
        nonlocal rendered_cleanup_done
        if rendered_cleanup_done:
            return
        rendered_cleanup_done = True
        for rendered in rendered_payloads:
            fusion_commands._delete_rendered_setting((rendered.get("source") or {}).get("cleanup_path"))

    seed_item_obj = None
    lock_snapshot: dict[str, Any] = {"attempted": False, "tracks": []}
    lock_restore: dict[str, Any] = {"attempted": False, "tracks": []}
    pre_batch_save = project_ops.save_current_project_if_available(conn)
    non_target_before = _snapshot_fast_textplus_non_target_tracks(conn, selected_track=selected_track)
    seed_name = f"__CUTAGENT_TEXTPLUS_DB_SEED__{uuid.uuid4()}"

    try:
        lock_snapshot = _set_video_track_locks_for_fast_textplus(conn, selected_track)
        lock_errors = _fast_textplus_lock_setup_errors(lock_snapshot)
        if lock_errors:
            raise APICallFailed(
                "Text+ DB batch requires verified seed track isolation.",
                details={"selected_track": selected_track, "lock_errors": lock_errors, "track_locks": {"applied": lock_snapshot}},
                recoverability="manual",
            )

        seed_item_obj, seed_insert = _insert_direct_textplus_template_item(
            conn,
            fusion_commands=fusion_commands,
            source_payload=source_payload,
            item={**first_item, "name": seed_name},
            selected_track=int(selected_track),
            holder=str(normalized["holder"]),
            pre_track_signatures=fusion_commands._timeline_track_item_signatures(conn, int(selected_track)),
            defer_duration_db_batch=True,
        )
    except Exception as exc:
        if seed_item_obj is not None:
            try:
                fusion_commands._safe_delete_timeline_item(conn, seed_item_obj)
            except Exception:
                pass
        cleanup_rendered_payloads()
        raise APICallFailed(
            "Text+ DB batch could not create the reusable seed Text+ clip.",
            details={"selected_track": selected_track, "seed_name": seed_name, "error": str(exc), "track_locks": {"applied": lock_snapshot}},
            recoverability="manual",
        ) from exc
    finally:
        try:
            lock_restore = _restore_video_track_locks(conn, lock_snapshot)
        finally:
            pass

    if lock_restore.get("attempted") and not lock_restore.get("restored"):
        try:
            fusion_commands._safe_delete_timeline_item(conn, seed_item_obj)
        except Exception:
            pass
        cleanup_rendered_payloads()
        raise APICallFailed(
            "Text+ DB batch could not restore track locks after seed creation.",
            details={"selected_track": selected_track, "seed_name": seed_name, "track_locks": {"applied": lock_snapshot, "restored": lock_restore}},
            recoverability="manual",
        )

    seed_readback = fusion_commands._timeline_item_readback(seed_item_obj, track_index=int(selected_track))
    seed_start = int(seed_readback.get("start") if seed_readback.get("start") is not None else first_item["record_frame"])
    timeline_name = str(conn.timeline.GetName())
    fps = float(getattr(conn, "fps", 24.0) or 24.0)
    expected = [
        {
            "index": int(item["index"]),
            "name": str(item["name"]),
            "record_frame": int(item["record_frame"]),
            "duration_frames": int(item["duration_frames"]),
            "text": str(item["text"]),
        }
        for item in ordered_items
    ]

    def writer(_connection: Any, cursor: Any, _session: Any) -> dict[str, Any]:
        track_rows = timeline_item_duration_db._timeline_track_ids(
            cursor,
            timeline_name=timeline_name,
            track_type="video",
            track_index=int(selected_track),
        )
        if len(track_rows) != 1:
            raise ValidationError(
                "Text+ DB batch could not resolve a unique target video track in Project.db.",
                details={"timeline_name": timeline_name, "selected_track": selected_track, "track_rows": track_rows},
                recoverability="manual",
            )
        track_id = str(track_rows[0]["track_id"])
        seed_rows = cursor.execute(
            """
            SELECT item.*
            FROM Sm2TiItem item
            JOIN Sm2TiItem_Sm2TiTrack rel
              ON rel.DbAssociate = item.Sm2TiItem_id
             AND rel.DbPropertyName = 'Items'
             AND rel.DbOwner = ?
            WHERE item.Name = ? AND item.Start = ?
            """,
            (track_id, seed_name, str(seed_start)),
        ).fetchall()
        if len(seed_rows) != 1:
            raise ValidationError(
                "Text+ DB batch could not resolve the seed Text+ item in Project.db.",
                details={"seed_name": seed_name, "seed_start": seed_start, "selected_track": selected_track, "match_count": len(seed_rows)},
                recoverability="manual",
            )
        seed_item = db_timeline_rows._row_to_dict(cursor, seed_rows[0])
        seed_item_id = str(seed_item["Sm2TiItem_id"])
        comp_rows = cursor.execute(
            "SELECT * FROM Sm2TiCompositionTable WHERE Sm2TiItem_id = ?",
            (seed_item_id,),
        ).fetchall()
        if len(comp_rows) != 1:
            raise ValidationError(
                "Text+ DB batch could not resolve the seed Text+ composition row.",
                details={"seed_item_id": seed_item_id, "match_count": len(comp_rows)},
                recoverability="manual",
            )
        seed_comp = db_timeline_rows._row_to_dict(cursor, comp_rows[0])
        seed_comp_id = str(seed_comp["Sm2TiCompositionTable_id"])
        seed_blob = bytes(seed_comp["CompositionBA"])

        target_count = cursor.execute(
            """
            SELECT COUNT(*)
            FROM Sm2TiItem item
            JOIN Sm2TiItem_Sm2TiTrack rel
              ON rel.DbAssociate = item.Sm2TiItem_id
             AND rel.DbPropertyName = 'Items'
             AND rel.DbOwner = ?
            """,
            (track_id,),
        ).fetchone()[0]
        if int(target_count) != 1:
            raise ValidationError(
                "Text+ DB batch target track must contain only the seed Text+ item during mutation.",
                details={"selected_track": selected_track, "target_track_item_count": int(target_count)},
                recoverability="manual",
            )

        cursor.execute(
            "DELETE FROM Sm2TiItem_Sm2TiTrack WHERE DbOwner = ? AND DbPropertyName = 'Items'",
            (track_id,),
        )
        inserted: list[dict[str, Any]] = []
        for db_index, item in enumerate(expected):
            if db_index == 0:
                item_id = seed_item_id
                comp_id = seed_comp_id
                db_timeline_rows.update_row(
                    cursor,
                    "Sm2TiItem",
                    "Sm2TiItem_id",
                    item_id,
                    {
                        "Name": item["name"],
                        "Start": str(item["record_frame"]),
                        "Duration": str(item["duration_frames"]),
                        "MediaTimemapBA": retime_db.default_timemap(int(item["duration_frames"]), fps),
                        "Sm2TiTrack_id": track_id,
                        "CompositionTable": comp_id,
                    },
                )
                db_timeline_rows.update_row(
                    cursor,
                    "Sm2TiCompositionTable",
                    "Sm2TiCompositionTable_id",
                    comp_id,
                    {
                        "Sm2TiItem_id": item_id,
                        "CompositionBA": _build_textplus_composition_blob(
                            seed_blob,
                            old_item_id=seed_item_id,
                            new_item_id=item_id,
                            text=item["text"],
                            old_text=expected[0]["text"],
                            rendered_inner=rendered_inner_by_index[int(item["index"])],
                        ),
                    },
                )
            else:
                item_id = str(uuid.uuid4())
                comp_id = str(uuid.uuid4())
                db_timeline_rows.insert_row(
                    cursor,
                    "Sm2TiItem",
                    _textplus_db_item_payload(
                        seed_item,
                        item_id=item_id,
                        comp_id=comp_id,
                        track_id=track_id,
                        name=item["name"],
                        start=int(item["record_frame"]),
                        duration=int(item["duration_frames"]),
                        fps=fps,
                    ),
                )
                db_timeline_rows.insert_row(
                    cursor,
                    "Sm2TiCompositionTable",
                    _textplus_db_comp_payload(
                        seed_comp,
                        comp_id=comp_id,
                        item_id=item_id,
                        composition_blob=_build_textplus_composition_blob(
                            seed_blob,
                            old_item_id=seed_item_id,
                            new_item_id=item_id,
                            text=item["text"],
                            old_text=expected[0]["text"],
                            rendered_inner=rendered_inner_by_index[int(item["index"])],
                        ),
                    ),
                )
            db_timeline_rows.insert_row(
                cursor,
                "Sm2TiItem_Sm2TiTrack",
                {"DbOwner": track_id, "DbAssociate": item_id, "DbPropertyName": "Items", "DbIndex": db_index},
            )
            inserted.append({"item_id": item_id, "composition_id": comp_id, **item})

        return {
            "action": "textplus.template_batch.direct_db_insert",
            "timeline_name": timeline_name,
            "selected_track": int(selected_track),
            "inserted_count": len(inserted),
            "expected": expected,
            "inserted": inserted,
            "seed": {"name": seed_name, "item_id": seed_item_id, "composition_id": seed_comp_id, "start": seed_start},
        }

    try:
        mutation = db_session.execute_sqlite_disk_db_mutation(
            conn,
            context="textplus template batch direct db insert",
            writer=writer,
            verifier=_verify_textplus_db_batch_track,
            save_project=True,
            allow_project_name_inference=True,
        )
    except Exception as exc:
        cleanup = _cleanup_textplus_db_seed_clip(conn, selected_track=int(selected_track), seed_name=seed_name)
        if isinstance(exc, APICallFailed):
            details = dict(getattr(exc, "details", {}) or {})
            details["seed_cleanup"] = cleanup
            raise APICallFailed(str(exc), details=details, recoverability=exc.recoverability) from exc
        raise APICallFailed(
            "Text+ DB batch failed after seed creation.",
            details={"selected_track": int(selected_track), "seed_name": seed_name, "seed_cleanup": cleanup, "error": str(exc)},
            recoverability="manual",
        ) from exc
    finally:
        cleanup_rendered_payloads()
    verification = dict(mutation.get("verification") or {})
    created = [
        {
            "index": item["index"],
            "name": item["name"],
            "track": int(selected_track),
            "record_frame": item["record_frame"],
            "duration_frames": item["duration_frames"],
            "timeline_item_id": item.get("item_id"),
            "composition_id": item.get("composition_id"),
            "verification": {
                "track_ok": True,
                "start_ok": True,
                "duration_ok": True,
                "imported": True,
            },
        }
        for item in mutation.get("inserted", [])
    ]
    verification_status = str(verification.get("status") or "verified")
    set_verification_status(verification_status)
    set_recoverability("not_applicable" if verification_status == "verified" else "manual")
    return text_ops.agent_text_payload(
        intent="visible_text_template_batch",
        text_kind="setting_template_batch",
        route="timeline.InsertFusionTitleIntoTimeline(seed) -> project_db.clone_textplus_batch -> reopen_verify",
        request={
            "template": normalized["template"],
            "selected_track": selected_track,
            "track_policy": normalized["track_policy"],
            "track_plan": track_plan,
            "track_summary": track_summary,
            "pre_batch_save": pre_batch_save,
            "non_target_before": _compact_fast_textplus_non_target_snapshot(non_target_before),
            "holder": normalized["holder"],
            "holder_kind": normalized["holder_kind"],
            "style_markdown": normalized["style_markdown"],
            "bold_style": normalized["bold_style"],
            "require_text": normalized["require_text"],
            "require_image": normalized["require_image"],
            "require_styling": normalized["require_styling"],
            "cleanup_on_failure": normalized["cleanup_on_failure"],
            "planned_count": len(normalized["items"]),
        },
        result={
            "created": created,
            "created_count": len(created),
            "mutation": {key: value for key, value in mutation.items() if key not in {"inserted", "expected"}},
            "track_locks": {"applied": lock_snapshot, "restored": lock_restore},
            "seed_insert": seed_insert,
            "failure_count": 0,
            "failures": [],
        },
        verification={
            **verification,
            "status": verification_status,
            "selected_track": selected_track,
            "created_count": len(created),
            "planned_count": len(normalized["items"]),
            "failure_count": 0,
            "verification_failure_count": 0,
        },
        fallback_used=False,
        warnings=[],
    )


def _insert_textplus_template_batch_fast_api(
    conn: Any,
    *,
    normalized: dict[str, Any],
    selected_track: int,
    track_plan: dict[str, Any],
    track_summary: dict[str, Any],
) -> dict[str, Any]:
    from ..commands import fusion as fusion_commands
    from ..core import project_ops, timeline_item_duration_db

    source_payloads: dict[int, dict[str, Any]] = {}
    inserted_objects: list[Any] = []
    inserted_events: list[dict[str, Any]] = []
    created: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    cleanup = {"attempted": False, "requested_count": 0, "deleted": False, "deleted_count": 0, "error": None}
    duration_db_update: dict[str, Any] | None = None
    duration_entries: list[dict[str, Any]] = []
    lock_snapshot: dict[str, Any] = {"attempted": False, "tracks": []}
    lock_restore: dict[str, Any] = {"attempted": False, "tracks": []}
    timings: dict[str, float] = dict(normalized.get("_timings") or {})
    phase_started = _timing_start()
    pre_batch_save = project_ops.save_current_project_if_available(conn)
    _timing_add(timings, "08a_save_project_before_batch", phase_started)
    phase_started = _timing_start()
    non_target_before = _snapshot_fast_textplus_non_target_tracks(conn, selected_track=selected_track)
    _timing_add(timings, "08b_snapshot_non_target_before", phase_started)
    non_target_after: dict[str, Any] | None = None

    def cleanup_inserted_on_failure() -> dict[str, Any]:
        nonlocal cleanup
        if normalized.get("cleanup_on_failure"):
            cleanup = _cleanup_created_text_batch_items(conn, inserted_objects)
        return cleanup

    events: list[dict[str, Any]] = []
    for item in normalized["items"]:
        events.append({"kind": "textplus_template", "frame": int(item["record_frame"]), "item": item})
    events.sort(key=lambda row: (int(row["frame"]), int(row["item"]["index"])), reverse=True)

    try:
        phase_started = _timing_start()
        for item in normalized["items"]:
            source_payloads[int(item["index"])] = _render_template_batch_item(normalized, item)
        _timing_add(timings, "07_render_item_settings", phase_started)

        phase_started = _timing_start()
        lock_snapshot = _set_video_track_locks_for_fast_textplus(conn, selected_track)
        _timing_add(timings, "09_lock_non_target_tracks", phase_started)
        lock_errors = _fast_textplus_lock_setup_errors(lock_snapshot)
        if lock_errors:
            lock_restore = _restore_video_track_locks(conn, lock_snapshot)
            raise APICallFailed(
                "Direct Text+ template batch requires verified video track lock isolation.",
                details={
                    "selected_track": selected_track,
                    "lock_errors": lock_errors,
                    "track_locks": {"applied": lock_snapshot, "restored": lock_restore},
                    "non_target_before": non_target_before,
                },
                recoverability="manual",
            )

        phase_started = _timing_start()
        for event in events:
            frame = int(event["frame"])
            clip_name = str(event["item"]["name"])
            source_payload = source_payloads[int(event["item"]["index"])]
            item_phase_started = _timing_start()
            pre_track_signatures = fusion_commands._timeline_track_item_signatures(conn, int(selected_track))
            _timing_add(timings, "10b_pre_track_signatures", item_phase_started)
            native_item, precise_insert = _insert_direct_textplus_template_item(
                conn,
                fusion_commands=fusion_commands,
                source_payload=source_payload,
                item=event["item"],
                selected_track=int(selected_track),
                holder=str(normalized["holder"]),
                pre_track_signatures=pre_track_signatures,
                defer_duration_db_batch=True,
                timings=timings,
            )
            source_payload["layout"] = precise_insert.get("layout")
            inserted_objects.append(native_item)
            inserted_events.append(
                {
                    "kind": event["kind"],
                    "index": event["item"]["index"],
                    "name": clip_name,
                    "frame": frame,
                    "duration_frames": int(event["item"]["duration_frames"]),
                    "native_insert": precise_insert.get("native_insert"),
                    "db_move": precise_insert.get("db_move"),
                    "duration_db_update": precise_insert.get("duration_db_update"),
                    "imported": bool((precise_insert.get("verification") or {}).get("imported")),
                    "layout": precise_insert.get("layout"),
                    "item": precise_insert.get("item"),
                }
            )
        _timing_add(timings, "10_12_insert_import_name_loop_total", phase_started)
    except Exception as exc:
        failures.append({"error": str(exc)})
        lock_restore = _restore_video_track_locks(conn, lock_snapshot)
        if normalized.get("cleanup_on_failure"):
            cleanup = _cleanup_created_text_batch_items(conn, inserted_objects)
        raise APICallFailed(
            "Direct Text+ template batch insertion failed.",
            details={
                "created_event_count": len(inserted_events),
                "failures": failures,
                "cleanup": cleanup,
                "selected_track": selected_track,
                "track_locks": {"applied": lock_snapshot, "restored": lock_restore},
                "non_target_before": non_target_before,
            },
            recoverability="manual",
        ) from exc
    finally:
        phase_started = _timing_start()
        for source_payload in source_payloads.values():
            fusion_commands._delete_rendered_setting(source_payload.get("cleanup_path"))
        _timing_add(timings, "13_cleanup_temporary_settings", phase_started)

    phase_started = _timing_start()
    lock_restore = _restore_video_track_locks(conn, lock_snapshot)
    _timing_add(timings, "14_restore_track_locks", phase_started)
    if lock_restore.get("attempted") and not lock_restore.get("restored"):
        cleanup_inserted_on_failure()
        raise APICallFailed(
            "Direct Text+ template batch could not verify track lock restoration.",
            details={
                "created_event_count": len(inserted_events),
                "cleanup": cleanup,
                "selected_track": selected_track,
                "track_locks": {"applied": lock_snapshot, "restored": lock_restore},
                "non_target_before": non_target_before,
                "non_target_after": non_target_after,
            },
            recoverability="manual",
        )

    phase_started = _timing_start()
    non_target_after_insert = _snapshot_fast_textplus_non_target_tracks(conn, selected_track=selected_track)
    _timing_add(timings, "15a_snapshot_non_target_after_insert", phase_started)
    phase_started = _timing_start()
    side_effect_issues = _compare_fast_textplus_non_target_snapshots(non_target_before, non_target_after_insert or {})
    _timing_add(timings, "15b_compare_non_target_after_insert", phase_started)
    if side_effect_issues:
        cleanup_inserted_on_failure()
        raise APICallFailed(
            "Direct Text+ template batch changed timeline items outside the target video track.",
            details={
                "created_event_count": len(inserted_events),
                "selected_track": selected_track,
                "side_effect_issues": side_effect_issues,
                "cleanup": cleanup,
                "track_locks": {"applied": lock_snapshot, "restored": lock_restore},
                "non_target_before": non_target_before,
                "non_target_after": non_target_after_insert,
            },
            recoverability="manual",
        )

    phase_started = _timing_start()
    duration_entries = []
    try:
        current_target_rows = _read_video_track_rows(conn, selected_track)
    except Exception:
        current_target_rows = []
    used_current_row_indexes: set[int] = set()
    current_rows_by_id: dict[str, tuple[int, dict[str, Any]]] = {}
    for row_index, row in enumerate(current_target_rows):
        row_id = _timeline_item_id_from_row(row)
        if row_id and row_id not in current_rows_by_id:
            current_rows_by_id[row_id] = (row_index, row)
    for event in sorted(inserted_events, key=lambda row: (int(row["frame"]), int(row["index"]))):
        target_start = int(event["frame"])
        target_duration = int(event["duration_frames"])
        current_row_index = None
        current_row = None
        event_item_id = _timeline_item_id_from_row(event.get("item") if isinstance(event.get("item"), dict) else None)
        if event_item_id:
            row_match = current_rows_by_id.get(event_item_id)
            if row_match is not None and row_match[0] not in used_current_row_indexes:
                current_row_index, current_row = row_match
        if current_row is None:
            for row_index, row in enumerate(current_target_rows):
                if row_index in used_current_row_indexes:
                    continue
                if str(row.get("name") or "") != str(event["name"]):
                    continue
                current_row_index = row_index
                current_row = row
                break
        if current_row_index is not None:
            used_current_row_indexes.add(current_row_index)
        if current_row is not None:
            event["item"] = {**dict(event.get("item") or {}), **{key: value for key, value in current_row.items() if key != "item"}}
        item_info = event.get("item") or {}
        if item_info.get("start") == target_start and item_info.get("duration") == target_duration:
            continue
        duration_entries.append(_duration_batch_entry_for_textplus_item(event=event, selected_track=selected_track))
    _timing_add(timings, "16a_build_duration_entries", phase_started)
    if duration_entries:
        try:
            phase_started = _timing_start()
            duration_db_update = timeline_item_duration_db.set_timeline_item_durations(
                conn,
                duration_entries,
                allow_overlap=False,
                enforce_source_bounds=False,
            )
            _timing_add(timings, "16_duration_db_batch", phase_started)
        except Exception as exc:
            cleanup_inserted_on_failure()
            raise APICallFailed(
                "Direct Text+ template batch inserted clips but failed to apply batch durations.",
                details={
                    "created_event_count": len(inserted_events),
                    "duration_entries": duration_entries,
                    "selected_track": selected_track,
                    "cleanup": cleanup,
                    "track_locks": {"applied": lock_snapshot, "restored": lock_restore},
                    "non_target_before": non_target_before,
                    "non_target_after_insert": non_target_after_insert,
                    "error": str(exc),
                },
                recoverability="manual",
            ) from exc
    else:
        duration_db_update = {
            "route": "api_native",
            "skipped": True,
            "requested_count": 0,
            "reason": "native_duration_verified",
        }

    refresh = getattr(conn, "refresh", None)
    if duration_entries and callable(refresh):
        try:
            phase_started = _timing_start()
            refresh()
            _timing_add(timings, "16b_connection_refresh_after_duration_db", phase_started)
        except Exception:
            pass

    cleanup_error: Exception | None = None
    try:
        phase_started = _timing_start()
        cleanup = _delete_fast_textplus_extra_items(
            conn,
            selected_track=selected_track,
            expected_items=normalized["items"],
        )
        _timing_add(timings, "17_cleanup_extra_tail_items", phase_started)
    except Exception as exc:
        cleanup_error = exc
        cleanup = {
            "attempted": True,
            "requested_count": None,
            "deleted": False,
            "deleted_count": 0,
            "error": str(exc),
        }
    phase_started = _timing_start()
    non_target_after = _snapshot_fast_textplus_non_target_tracks(conn, selected_track=selected_track)
    _timing_add(timings, "15c_snapshot_non_target_after_cleanup", phase_started)

    if cleanup_error is not None:
        cleanup_inserted_on_failure()
        raise APICallFailed(
            "Direct Text+ template batch cleanup failed.",
            details={
                "created_event_count": len(inserted_events),
                "cleanup": cleanup,
                "selected_track": selected_track,
                "duration_db_update": duration_db_update,
                "track_locks": {"applied": lock_snapshot, "restored": lock_restore},
                "non_target_before": non_target_before,
                "non_target_after": non_target_after,
            },
            recoverability="manual",
        ) from cleanup_error

    phase_started = _timing_start()
    side_effect_issues = _compare_fast_textplus_non_target_snapshots(non_target_before, non_target_after or {})
    _timing_add(timings, "15d_compare_non_target_after_cleanup", phase_started)
    if side_effect_issues:
        cleanup_inserted_on_failure()
        raise APICallFailed(
            "Direct Text+ template batch changed timeline items outside the target video track.",
            details={
                "created_event_count": len(inserted_events),
                "selected_track": selected_track,
                "side_effect_issues": side_effect_issues,
                "cleanup": cleanup,
                "duration_db_update": duration_db_update,
                "track_locks": {"applied": lock_snapshot, "restored": lock_restore},
                "non_target_before": non_target_before,
                "non_target_after": non_target_after,
            },
            recoverability="manual",
        )

    phase_started = _timing_start()
    final_rows = _read_video_track_rows(conn, selected_track)
    _timing_add(timings, "18a_read_target_track_final_rows", phase_started)
    phase_started = _timing_start()
    for item in normalized["items"]:
        matches = [
            row
            for row in final_rows
            if str(row.get("name") or "") == str(item["name"])
            and row.get("start") == int(item["record_frame"])
            and row.get("duration") == int(item["duration_frames"])
        ]
        readback = {key: value for key, value in matches[0].items() if key != "item"} if matches else None
        verification = {
            "imported": True,
            "track_requested": selected_track,
            "track_readback": readback.get("track_index") if readback else None,
            "record_frame_requested": int(item["record_frame"]),
            "start_readback": readback.get("start") if readback else None,
            "duration_requested_frames": int(item["duration_frames"]),
            "duration_readback_frames": readback.get("duration") if readback else None,
            "track_ok": bool(readback and readback.get("track_index") in (selected_track, None)),
            "start_ok": bool(readback and readback.get("start") == int(item["record_frame"])),
            "duration_ok": bool(readback and readback.get("duration") == int(item["duration_frames"])),
        }
        created.append(
            {
                "index": item["index"],
                "name": item["name"],
                "track": selected_track,
                "record_frame": item["record_frame"],
                "duration_frames": item["duration_frames"],
                "render": source_payloads.get(int(item["index"]), {}).get("render"),
                "layout": source_payloads.get(int(item["index"]), {}).get("layout"),
                "duration_db_update": "batch" if duration_entries else None,
                "verification": verification,
                "readback": readback,
            }
        )
    _timing_add(timings, "18b_build_final_verification", phase_started)

    phase_started = _timing_start()
    verification_failures = [
        row
        for row in created
        if not (
            row["verification"].get("track_ok")
            and row["verification"].get("start_ok")
            and row["verification"].get("duration_ok")
        )
    ]
    _timing_add(timings, "18c_check_verification_failures", phase_started)
    if verification_failures:
        cleanup_inserted_on_failure()
        raise APICallFailed(
            "Direct Text+ template batch did not verify created item placement and duration.",
            details={
                "created_event_count": len(inserted_events),
                "selected_track": selected_track,
                "verification_failures": verification_failures,
                "cleanup": cleanup,
                "track_locks": {"applied": lock_snapshot, "restored": lock_restore},
                "non_target_before": non_target_before,
                "non_target_after": non_target_after,
            },
            recoverability="manual",
        )
    all_verified = len(created) == len(normalized["items"]) and not failures and not verification_failures
    verification_status = "verified" if all_verified else "pending_manual"
    set_verification_status(verification_status)
    set_recoverability("not_applicable" if all_verified else "manual")
    return text_ops.agent_text_payload(
        intent="visible_text_template_batch",
        text_kind="setting_template_batch",
        route=(
            "timeline.SetTrackLock(all_non_target_tracks) -> "
            "timeline.InsertFusionTitleIntoTimeline(reverse batch) -> "
            "timeline_item.ImportFusionComp(batch) -> "
            "project_db.set_duration(batch)"
        ),
        request={
            "template": normalized["template"],
            "selected_track": selected_track,
            "track_policy": normalized["track_policy"],
            "track_plan": track_plan,
            "track_summary": track_summary,
            "pre_batch_save": pre_batch_save,
            "non_target_before": _compact_fast_textplus_non_target_snapshot(non_target_before),
            "non_target_after": _compact_fast_textplus_non_target_snapshot(non_target_after),
            "holder": normalized["holder"],
            "holder_kind": normalized["holder_kind"],
            "style_markdown": normalized["style_markdown"],
            "bold_style": normalized["bold_style"],
            "require_text": normalized["require_text"],
            "require_image": normalized["require_image"],
            "require_styling": normalized["require_styling"],
            "cleanup_on_failure": normalized["cleanup_on_failure"],
            "planned_count": len(normalized["items"]),
            "event_count": len(events),
            "cut_event_count": 0,
        },
        result={
            "created": created,
            "created_count": len(created),
            "events": inserted_events,
            "event_count": len(inserted_events),
            "failures": failures,
            "failure_count": len(failures),
            "cleanup": cleanup,
            "duration_db_update": duration_db_update,
            "duration_entries": duration_entries,
            "track_locks": {"applied": lock_snapshot, "restored": lock_restore},
            "non_target_before": _compact_fast_textplus_non_target_snapshot(non_target_before),
            "non_target_after": _compact_fast_textplus_non_target_snapshot(non_target_after),
            "timings": timings,
        },
        verification={
            "status": verification_status,
            "selected_track": selected_track,
            "created_count": len(created),
            "planned_count": len(normalized["items"]),
            "failure_count": len(failures),
            "verification_failure_count": len(verification_failures),
        },
        fallback_used=False,
        warnings=(
            ["Text+ templates imported and placement checks passed; node GUI health still requires runtime/visual verification."]
            if all_verified
            else ["Direct Text+ batch insertion completed, but one or more template ranges need manual review."]
        ),
    )


@app.command("insert")
@handle_errors
def insert(
    text_arg: Optional[str] = typer.Argument(None, help="Visible text to insert"),
    text_option: Optional[str] = typer.Option(None, "--text", help="Visible text to insert"),
    at: str = typer.Option("0s", "--at", help="Position (timecode/seconds/frames)"),
    duration: str = typer.Option("5s", "--duration", "-d", help="Duration (e.g. 5s, 120f, 00:00:05:00)"),
    track: int = typer.Option(2, "--track", help="Video track index"),
    name: str = typer.Option("Text Overlay", "--name", help="Timeline clip name"),
    template_path: Optional[str] = typer.Option(None, "--template", "-t", help="Optional Text+ .setting template"),
    bold_style: str = typer.Option("ExtraBold", "--bold-style", help="Font style for **bold** ranges"),
    route: str = typer.Option("auto", "--route", help="auto|setting|native-title"),
):
    """Insert a visible Text+/styled text overlay."""
    enforce_mutation_policy("text.insert", intended_engine="workaround_setting", mutating=not is_dry_run())
    text, _fields, source = text_ops.resolve_text_and_fields(
        text_arg=text_arg,
        text_option=text_option,
        require_text_or_fields=True,
    )
    route_key = str(route or "auto").strip().lower().replace("_", "-")
    if route_key not in {"auto", "setting", "native-title"}:
        raise ValidationError(
            "Unsupported text insert route.",
            details={"route": route, "allowed": ["auto", "setting", "native-title"]},
        )
    if template_path and not os.path.isfile(template_path):
        raise APICallFailed("Text insert template file not found.", details={"template": template_path})
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        payload = _dry_run_insert_plan(
            action="text.insert",
            intent="visible_text_overlay",
            text_kind="text_plus",
            route=route_key,
            request={
                "text": text,
                "text_source": source,
                "name": name,
                "at": at,
                "duration": duration,
                "track": track,
                "template": template_path or text_ops.default_text_overlay_template_path(),
                "template_source": "custom" if template_path else "bundled",
                "bold_style": bold_style,
                "route": route_key,
            },
        )
        output(payload, title="Text Insert Plan")
        return

    conn = get_connection(require_timeline=True)
    payload = text_ops.insert_visible_text(
        conn,
        text=str(text or ""),
        template_path=template_path,
        name=name,
        at=at,
        duration=duration,
        track=track,
        bold_style=bold_style,
        route=route,
    )
    payload["request"]["text_source"] = source
    output(payload, title="Text Insert")


@app.command("insert-preset")
@handle_errors
def insert_preset(
    name: str = typer.Argument(..., help='DaVinci Resolve title preset name, e.g. "Text+", "MultiText"'),
    kind: str = typer.Option("auto", "--kind", help="auto|title|fusion-title"),
    text_option: Optional[str] = typer.Option(None, "--text", help="Single text value to apply"),
    fields_json: Optional[str] = typer.Option(None, "--fields-json", help="JSON object of field/tool names to text values"),
    at: str = typer.Option("0s", "--at", help="Position (timecode/seconds/frames)"),
    duration: str = typer.Option("5s", "--duration", "-d", help="Duration"),
    track: int = typer.Option(1, "--track", help="Video track index"),
    clip_name: Optional[str] = typer.Option(None, "--name", help="Timeline clip name after insertion"),
    allow_partial_fields: bool = typer.Option(False, "--allow-partial-fields", help="Allow field update partial success"),
    bold_style: str = typer.Option("ExtraBold", "--bold-style", help="Font style for **bold** ranges"),
):
    """Insert a DaVinci Resolve/Fusion title preset by name and optionally fill text fields."""
    enforce_mutation_policy("text.insert_preset", intended_engine="api_native", mutating=not is_dry_run())
    text, fields, source = text_ops.resolve_text_and_fields(text_option=text_option, fields_json=fields_json)
    resolved_kind, _fusion = text_ops._resolve_preset_kind(name, kind)
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        payload = _dry_run_insert_plan(
            action="text.insert_preset",
            intent="visible_text_preset",
            text_kind=text_ops._text_kind_for_preset(name, resolved_kind),
            route=f"timeline.{'InsertFusionTitleIntoTimeline' if resolved_kind == 'fusion-title' else 'InsertTitleIntoTimeline'}",
            request={
                "preset": name,
                "kind": resolved_kind,
                "text": text,
                "fields": fields,
                "text_source": source,
                "name": clip_name or name,
                "at": at,
                "duration": duration,
                "track": track,
                "allow_partial_fields": allow_partial_fields,
            },
        )
        output(payload, title="Text Preset Insert Plan")
        return

    conn = get_connection(require_timeline=True)
    payload = text_ops.insert_text_preset(
        conn,
        preset_name=name,
        kind=resolved_kind,
        text=text,
        fields=fields,
        allow_partial_fields=allow_partial_fields,
        name=clip_name,
        at=at,
        duration=duration,
        track=track,
        bold_style=bold_style,
    )
    payload["request"]["text_source"] = source
    output(payload, title="Text Preset Insert")


@app.command("insert-template")
@handle_errors
def insert_template(
    template: str = typer.Argument(..., help=".setting template path"),
    text_option: Optional[str] = typer.Option(None, "--text", help="Text replacement for template text placeholders"),
    fields_json: Optional[str] = typer.Option(None, "--fields-json", help="JSON object converted to template params"),
    image: Optional[str] = typer.Option(None, "--image", help="Image path replacement for image placeholders"),
    params: list[str] = typer.Option([], "--param", help="Raw template replacement as KEY=VALUE; repeatable"),
    name: Optional[str] = typer.Option(None, "--name", help="Timeline clip name after insertion"),
    at: str = typer.Option("0s", "--at", help="Position (timecode/seconds/frames)"),
    duration: str = typer.Option("5s", "--duration", "-d", help="Duration"),
    track: int = typer.Option(2, "--track", help="Video track index"),
    holder_kind: str = typer.Option("textplus", "--holder-kind", help="fusion|textplus"),
    holder: Optional[str] = typer.Option(None, "--holder", help="Holder preset name"),
    style_markdown: bool = typer.Option(True, "--style-markdown/--plain-text", help="Parse **bold** markdown into CharacterLevelStyling"),
    bold_style: str = typer.Option("ExtraBold", "--bold-style", help="Fusion font style for markdown bold ranges"),
    require_text: bool = typer.Option(False, "--require-text", help="Require a recognized text placeholder to be replaced"),
    require_image: bool = typer.Option(False, "--require-image", help="Require a recognized image placeholder to be replaced"),
    require_styling: bool = typer.Option(False, "--require-styling", help="Require a recognized styling placeholder to be replaced"),
    keep_rendered: bool = typer.Option(False, "--keep-rendered", help="Keep rendered temporary .setting file"),
    rendered_output: Optional[str] = typer.Option(None, "--rendered-output", help="Write rendered .setting to this path"),
):
    """Insert a custom/rendered Fusion .setting title template."""
    set_execution_engine("workaround_setting")
    enforce_mutation_policy("text.insert_template", intended_engine="workaround_setting", mutating=not is_dry_run())
    fields = text_ops.parse_fields_json(fields_json)
    text = str(text_option) if text_option is not None else None
    source = "fields_json" if fields and text is None else "option" if text is not None else None
    holder_kind = _normalize_kind(holder_kind, {"fusion", "textplus"}, field="holder_kind")
    field_params = [f"{key}={value}" for key, value in fields.items()]
    effective_params = [*params, *field_params]
    should_render = bool(text or image or effective_params or require_text or require_image or require_styling or rendered_output)
    from ..commands import fusion as fusion_commands

    source_payload = fusion_commands._resolve_insert_setting_source(
        path=None if should_render else template,
        render_template=template if should_render else None,
        text=text,
        image=image,
        style_markdown=style_markdown,
        bold_style=bold_style,
        params=effective_params,
        require_text=require_text,
        require_image=require_image,
        require_styling=require_styling,
        keep_rendered=keep_rendered,
        rendered_output=rendered_output,
    )
    effective_path = str(source_payload["path"])
    clip_name = str(name or os.path.splitext(os.path.basename(effective_path))[0] or "Text Template").strip()
    if is_dry_run():
        cleanup = dict(source_payload.get("cleanup") or {})
        cleanup["temporary_setting_deleted"] = fusion_commands._delete_rendered_setting(source_payload.get("cleanup_path"))
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        payload = _dry_run_insert_plan(
            action="text.insert_template",
            intent="visible_text_template",
            text_kind="setting_template",
            route="fusion.insert_setting",
            request={
                "template": template,
                "path": effective_path,
                "render": source_payload.get("render"),
                "text": text,
                "fields": fields,
                "text_source": source,
                "image": image,
                "params": effective_params,
                "name": clip_name,
                "at": at,
                "duration": duration,
                "track": track,
                "holder_kind": holder_kind,
                "holder": holder,
            },
        )
        payload["cleanup"] = cleanup
        output(payload, title="Text Template Insert Plan")
        return

    conn = get_connection(require_timeline=True)
    try:
        inserted = fusion_commands._insert_setting_precise(
            conn,
            path=effective_path,
            clip_name=clip_name,
            at=at,
            record_frame=None,
            duration=duration,
            track=track,
            holder=holder or ("Text+" if holder_kind == "textplus" else "Fusion Composition"),
            holder_kind=holder_kind,
            position_x=None,
            position_y=None,
        )
    finally:
        fusion_commands._delete_rendered_setting(source_payload.get("cleanup_path"))

    verification = inserted.get("verification") if isinstance(inserted.get("verification"), dict) else {}
    payload = text_ops.agent_text_payload(
        intent="visible_text_template",
        text_kind="setting_template",
        route=str(inserted.get("route") or "fusion.insert_setting"),
        request={
            "template": template,
            "path": effective_path,
            "render": source_payload.get("render"),
            "text": text,
            "fields": fields,
            "text_source": source,
            "image": image,
            "params": effective_params,
            "name": clip_name,
            "at": at,
            "duration": duration,
            "track": track,
            "holder_kind": holder_kind,
            "holder": holder,
        },
        result=inserted,
        verification=verification,
        fallback_used=text_ops.insertion_fallback_used(inserted),
        warnings=[],
    )
    output(payload, title="Text Template Insert")


def _augment_batch_payload(payload: dict[str, Any], request_extra: dict[str, Any] | None) -> dict[str, Any]:
    if not request_extra:
        return payload
    request = payload.get("request")
    if isinstance(request, dict):
        request.update(request_extra)
    return payload


def _execute_template_batch(
    raw_spec: dict[str, Any],
    *,
    command_id: str,
    conn: Any | None = None,
    timings: dict[str, float] | None = None,
    request_extra: dict[str, Any] | None = None,
    dry_run_title: str = "Text Template Batch Insert Plan",
    output_title: str = "Text Template Batch Insert",
) -> None:
    timings = timings if timings is not None else {}
    if conn is None:
        phase_started = _timing_start()
        conn = get_connection(require_timeline=True)
        _timing_add(timings, "01a_get_resolve_connection", phase_started)
    fps = float(getattr(conn, "fps", 24.0) or 24.0)
    phase_started = _timing_start()
    normalized = _normalize_template_batch_spec(raw_spec, fps=fps, start_frame=_timeline_start_frame(conn))
    _timing_add(timings, "02_03_normalize_validate_times_and_overlaps", phase_started)
    normalized["_timings"] = timings
    phase_started = _timing_start()
    track_plan = _select_template_batch_track(
        conn,
        requested_track=normalized["track"],
        allow_create_track=bool(normalized["allow_create_track"]),
        allow_non_empty_track=bool(normalized["allow_non_empty_track"]),
        require_above_occupied=bool(normalized["require_above_occupied"]),
    )
    _timing_add(timings, "04_select_target_track", phase_started)
    selected_track = int(track_plan["selected_track"])

    render_checks: list[dict[str, Any]] = []
    if is_dry_run():
        from ..commands import fusion as fusion_commands

        non_target_snapshot = None
        if normalized["holder_kind"] == "textplus":
            non_target_snapshot = _compact_fast_textplus_non_target_snapshot(
                _snapshot_fast_textplus_non_target_tracks(conn, selected_track=selected_track)
            )
        for item in normalized["items"]:
            source_payload = _render_template_batch_item(normalized, item)
            cleanup = dict(source_payload.get("cleanup") or {})
            cleanup["temporary_setting_deleted"] = fusion_commands._delete_rendered_setting(source_payload.get("cleanup_path"))
            render_checks.append(
                {
                    "index": item["index"],
                    "name": item["name"],
                    "render": source_payload.get("render"),
                    "cleanup": cleanup,
                }
            )
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            text_ops.agent_text_payload(
                intent="visible_text_template_batch",
                text_kind="setting_template_batch",
                route=command_id,
                request={
                    "template": normalized["template"],
                    "selected_track": selected_track,
                    "track_policy": normalized["track_policy"],
                    "track_plan": track_plan,
                    "non_target_snapshot": non_target_snapshot,
                    "holder": normalized["holder"],
                    "holder_kind": normalized["holder_kind"],
                    "style_markdown": normalized["style_markdown"],
                    "bold_style": normalized["bold_style"],
                    "require_text": normalized["require_text"],
                    "require_image": normalized["require_image"],
                    "require_styling": normalized["require_styling"],
                    "cleanup_on_failure": normalized["cleanup_on_failure"],
                    "items": normalized["items"],
                    "planned_count": len(normalized["items"]),
                    **(request_extra or {}),
                },
                result={"render_checks": render_checks},
                verification={"status": "not_requested"},
                action=command_id,
                dry_run=True,
                would_insert=True,
            ),
            title=dry_run_title,
        )
        return

    from ..commands import fusion as fusion_commands

    phase_started = _timing_start()
    track_summary = fusion_commands._ensure_video_track(conn, selected_track)
    _timing_add(timings, "06_ensure_video_track", phase_started)
    if normalized["holder_kind"] == "textplus":
        output(
            _augment_batch_payload(
                _insert_textplus_template_batch_db(
                    conn,
                    normalized=normalized,
                    selected_track=selected_track,
                    track_plan=track_plan,
                    track_summary=track_summary,
                ),
                request_extra,
            ),
            title=output_title,
        )
        return

    created: list[dict[str, Any]] = []
    created_objects: list[Any] = []
    failures: list[dict[str, Any]] = []
    cleanup = {"attempted": False, "requested_count": 0, "deleted": False, "deleted_count": 0, "error": None}

    for item in normalized["items"]:
        source_payload = None
        try:
            source_payload = _render_template_batch_item(normalized, item)
            inserted = fusion_commands._insert_setting_precise(
                conn,
                path=str(source_payload["path"]),
                clip_name=str(item["name"]),
                at=str(item["at"]),
                record_frame=int(item["record_frame"]),
                duration=str(item["duration"]),
                track=selected_track,
                holder=str(normalized["holder"]),
                holder_kind=str(normalized["holder_kind"]),
                position_x=None,
                position_y=None,
            )
            if inserted.get("connection_reloaded"):
                try:
                    from ..connection import ResolveConnection

                    fresh_conn = ResolveConnection.get()
                    fresh_conn.connect()
                    conn = fresh_conn
                except Exception:
                    pass
            else:
                refresh = getattr(conn, "refresh", None)
                if callable(refresh):
                    try:
                        refresh()
                    except Exception:
                        pass
            try:
                maybe_item = fusion_commands._find_timeline_item_by_track_record(
                    conn,
                    selected_track,
                    int(item["record_frame"]),
                    name=str(item["name"]),
                )
                if maybe_item is not None:
                    created_objects.append(maybe_item)
            except Exception:
                pass
            created.append(
                {
                    "index": item["index"],
                    "name": item["name"],
                    "track": selected_track,
                    "record_frame": item["record_frame"],
                    "duration_frames": item["duration_frames"],
                    "render": source_payload.get("render"),
                    "verification": inserted.get("verification"),
                    "result": inserted,
                }
            )
        except Exception as exc:
            failures.append({"index": item.get("index"), "name": item.get("name"), "error": str(exc)})
            if normalized["cleanup_on_failure"]:
                cleanup = _cleanup_created_text_batch_items(conn, created_objects)
            raise APICallFailed(
                "Text template batch insertion failed.",
                details={
                    "failed_item": item,
                    "created_count": len(created),
                    "failures": failures,
                    "cleanup": cleanup,
                    "selected_track": selected_track,
                },
                recoverability="manual",
            ) from exc
        finally:
            if source_payload is not None:
                fusion_commands._delete_rendered_setting(source_payload.get("cleanup_path"))

    verification_failures = [
        row
        for row in created
        if not (
            isinstance(row.get("verification"), dict)
            and row["verification"].get("track_ok") is not False
            and row["verification"].get("start_ok") is not False
            and row["verification"].get("duration_ok") is not False
        )
    ]
    all_verified = len(created) == len(normalized["items"]) and not failures and not verification_failures
    verification_status = "partial" if all_verified else "pending_manual"
    set_verification_status(verification_status)
    set_recoverability("not_applicable" if all_verified else "manual")
    output(
        text_ops.agent_text_payload(
            intent="visible_text_template_batch",
            text_kind="setting_template_batch",
            route=command_id,
            request={
                "template": normalized["template"],
                "selected_track": selected_track,
                "track_policy": normalized["track_policy"],
                "track_plan": track_plan,
                "track_summary": track_summary,
                "holder": normalized["holder"],
                "holder_kind": normalized["holder_kind"],
                "style_markdown": normalized["style_markdown"],
                "bold_style": normalized["bold_style"],
                "require_text": normalized["require_text"],
                "require_image": normalized["require_image"],
                "require_styling": normalized["require_styling"],
                "cleanup_on_failure": normalized["cleanup_on_failure"],
                "planned_count": len(normalized["items"]),
                **(request_extra or {}),
            },
            result={
                "created": created,
                "created_count": len(created),
                "failures": failures,
                "failure_count": len(failures),
                "cleanup": cleanup,
            },
            verification={
                "status": verification_status,
                "selected_track": selected_track,
                "created_count": len(created),
                "planned_count": len(normalized["items"]),
                "failure_count": len(failures),
                "verification_failure_count": len(verification_failures),
            },
            fallback_used=any(bool((row.get("result") or {}).get("holder_lookup", {}).get("fallback_used")) for row in created),
            warnings=(
                ["Text+ templates imported and placement checks passed; node GUI health still requires runtime/visual verification."]
                if all_verified
                else []
            ),
        ),
        title=output_title,
    )


def _load_caption_transcript(path_value: Any) -> tuple[str, dict[str, Any]]:
    path = os.path.abspath(os.path.expanduser(str(path_value or "").strip()))
    if not str(path_value or "").strip():
        raise ValidationError("Caption insert spec requires transcript.", details={"field": "transcript"})
    if not os.path.isfile(path):
        raise APICallFailed("Caption transcript file not found.", details={"transcript": path})
    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(
            "Caption transcript must be a readable JSON file.",
            details={"transcript": path, "error": str(exc)},
        ) from exc
    if not isinstance(payload, dict):
        raise ValidationError("Caption transcript must contain a JSON object.", details={"transcript": path})
    return path, payload


def _build_caption_batch_spec(raw_spec: dict[str, Any], *, fps: float) -> tuple[dict[str, Any], dict[str, Any]]:
    if raw_spec.get("preset") is not None:
        raise ValidationError(
            "Caption presets are not supported; provide an explicit segmentation configuration.",
            details={"field": "preset"},
        )
    transcript_path, transcript_payload = _load_caption_transcript(raw_spec.get("transcript"))
    plan = caption_segmentation.segment_caption_payload(transcript_payload, raw_spec.get("segmentation"))
    items, frame_warnings = caption_segmentation.caption_plan_to_batch_items(plan, fps)
    if not items:
        raise ValidationError("Caption transcript produced no caption items.", details={"transcript": transcript_path})

    batch_fields = {
        "template",
        "track_policy",
        "track",
        "allow_create_track",
        "allow_non_empty_track",
        "require_above_occupied",
        "cleanup_on_failure",
        "holder_kind",
        "holder",
        "style_markdown",
        "bold_style",
        "require_text",
        "require_image",
        "require_styling",
        "image",
        "params",
    }
    batch_spec = {key: raw_spec[key] for key in batch_fields if key in raw_spec}
    batch_spec["items"] = items
    batch_spec.setdefault("holder_kind", "textplus")
    batch_spec.setdefault("track_policy", "empty-above-occupied")
    batch_spec.setdefault("cleanup_on_failure", True)
    batch_spec.setdefault("allow_non_empty_track", False)
    batch_spec.setdefault("require_above_occupied", True)

    review = {
        "transcript_file": os.path.basename(transcript_path),
        "version": plan["version"],
        "config": plan["config"],
        "token_count": plan["token_count"],
        "cue_count": plan["cue_count"],
        "warning_count": plan["warning_count"] + len(frame_warnings),
        "frame_warnings": frame_warnings,
        "cues": plan["cues"],
    }
    return batch_spec, review


@app.command("insert-template-batch")
@handle_errors
def insert_template_batch(
    spec_path: Optional[str] = typer.Option(None, "--spec", help="Path to Text+ template batch JSON spec"),
    spec_json: Optional[str] = typer.Option(None, "--spec-json", help="Inline Text+ template batch JSON spec"),
):
    """Insert multiple Text+ template clips from one .setting template."""
    timings: dict[str, float] = {}
    set_execution_engine("workaround_setting")
    enforce_mutation_policy("text.insert_template_batch", intended_engine="workaround_setting", mutating=not is_dry_run())
    phase_started = _timing_start()
    raw_spec = _load_template_batch_spec(spec_path, spec_json)
    _timing_add(timings, "01_load_batch_spec", phase_started)
    _execute_template_batch(
        raw_spec,
        command_id="text.insert_template_batch",
        timings=timings,
    )


@app.command("insert-captions")
@handle_errors
def insert_captions(
    spec_path: Optional[str] = typer.Option(None, "--spec", help="Path to transcript caption insertion JSON spec"),
    spec_json: Optional[str] = typer.Option(None, "--spec-json", help="Inline transcript caption insertion JSON spec"),
):
    """Segment a transcript with explicit rules and insert designed Text+ captions."""
    timings: dict[str, float] = {}
    set_execution_engine("workaround_setting")
    enforce_mutation_policy("text.insert_captions", intended_engine="workaround_setting", mutating=not is_dry_run())
    phase_started = _timing_start()
    raw_spec = _load_template_batch_spec(spec_path, spec_json)
    _timing_add(timings, "01_load_caption_spec", phase_started)
    phase_started = _timing_start()
    conn = get_connection(require_timeline=True)
    _timing_add(timings, "01a_get_resolve_connection", phase_started)
    phase_started = _timing_start()
    batch_spec, review = _build_caption_batch_spec(raw_spec, fps=float(getattr(conn, "fps", 24.0) or 24.0))
    _timing_add(timings, "01b_segment_caption_transcript", phase_started)
    _execute_template_batch(
        batch_spec,
        command_id="text.insert_captions",
        conn=conn,
        timings=timings,
        request_extra={"segmentation": review},
        dry_run_title="Transcript Caption Insert Plan",
        output_title="Transcript Caption Insert",
    )


@app.command("update")
@handle_errors
def update(
    text_option: Optional[str] = typer.Option(None, "--text", help="Single text value to apply"),
    fields_json: Optional[str] = typer.Option(None, "--fields-json", help="JSON object of field/tool names to text values"),
    clip_name: Optional[str] = typer.Option(None, "--clip", help="Clip name selector"),
    track: Optional[int] = typer.Option(None, "--track", min=1, help="Video track index selector"),
    record_frame: Optional[str] = typer.Option(None, "--record-frame", help="Record-domain point selector"),
    role: Optional[str] = typer.Option(None, "--role", help="Optional role hint: body/header"),
    tool: Optional[str] = typer.Option(None, "--tool", help="Explicit tool name"),
    tool_candidate: list[str] = typer.Option([], "--tool-candidate", help="Additional preferred tool names"),
    input_name: list[str] = typer.Option([], "--input", help="Preferred input name fallback order"),
    uppercase: bool = typer.Option(False, "--uppercase", help="Uppercase final text"),
    double_spaces: bool = typer.Option(False, "--double-spaces", help="Replace spaces with double spaces"),
    styled: bool = typer.Option(False, "--styled/--plain", help="Force CharacterLevelStyling parsing"),
    bold_style: str = typer.Option("ExtraBold", "--bold-style", help="Bold style for markdown ranges"),
    cls_tool: list[str] = typer.Option([], "--cls-tool", help="Preferred CLS tool candidates"),
    allow_partial_fields: bool = typer.Option(False, "--allow-partial-fields", help="Allow field update partial success"),
):
    """Update text in an existing Fusion/Text+ timeline item."""
    enforce_mutation_policy("text.update", intended_engine="api_native", mutating=not is_dry_run())
    text, fields, source = text_ops.resolve_text_and_fields(
        text_option=text_option,
        fields_json=fields_json,
        require_text_or_fields=True,
    )
    selector = {"clip": clip_name, "track": track, "record_frame": record_frame}
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            text_ops.agent_text_payload(
                intent="update_visible_text",
                text_kind="existing_text_item",
                route="fusion_text_update",
                request={
                    "selector": selector,
                    "text": text,
                    "fields": fields,
                    "text_source": source,
                    "role": role,
                    "tool": tool,
                    "tool_candidates": list(tool_candidate or []),
                    "inputs": list(input_name or []),
                    "allow_partial_fields": allow_partial_fields,
                },
                verification={"status": "not_requested"},
                action="text.update",
                dry_run=True,
            ),
            title="Text Update Plan",
        )
        return

    from ..commands import fusion as fusion_commands

    conn = get_connection(require_timeline=True)
    item, resolved_selector = fusion_commands._resolve_timeline_item(conn, clip_name=clip_name, track=track, record_frame=record_frame)
    field_result = text_ops.apply_text_fields_to_item(
        item,
        text=text,
        fields=fields,
        allow_partial=allow_partial_fields,
        role=role,
        explicit_tool=tool,
        tool_candidates=_list_option(tool_candidate),
        input_names=_list_option(input_name),
        uppercase=uppercase,
        double_spaces=double_spaces,
        bold_style=bold_style,
        styled=styled,
        cls_tool_candidates=_list_option(cls_tool),
    )
    set_verification_status("verified" if field_result.get("ok") else "partial")
    payload = text_ops.agent_text_payload(
        intent="update_visible_text",
        text_kind="existing_text_item",
        route="fusion_text_update",
        request={
            "selector": resolved_selector,
            "text": text,
            "fields": fields,
            "text_source": source,
            "role": role,
            "tool": tool,
            "tool_candidates": list(tool_candidate or []),
            "inputs": list(input_name or []),
            "allow_partial_fields": allow_partial_fields,
        },
        result=field_result,
        verification={"status": "verified" if field_result.get("ok") else "partial"},
        warnings=list(field_result.get("warnings") or []),
    )
    output(payload, title="Text Update")


@app.command("inspect")
@handle_errors
def inspect(
    target: str = typer.Argument(..., help="Clip/preset/template target"),
    kind: str = typer.Option("auto", "--kind", help="auto|clip|preset|template"),
):
    """Inspect a text clip, preset, or .setting template."""
    resolved_kind = _normalize_kind(kind, {"auto", "clip", "preset", "template"}, field="kind")
    target_path = os.path.abspath(os.path.expanduser(target))
    if resolved_kind == "auto":
        resolved_kind = "template" if os.path.isfile(target_path) or target.endswith(".setting") else "preset"
    if resolved_kind == "template":
        from ..core.fusion_setting_inspector import inspect_setting

        if not os.path.isfile(target_path):
            raise APICallFailed("Text template path does not exist.", details={"path": target_path})
        inspected = inspect_setting(target_path)
        output(
            text_ops.agent_text_payload(
                intent="inspect_text_template",
                text_kind="setting_template",
                route="local_setting_inspect",
                request={"target": target, "kind": resolved_kind},
                result=inspected,
                verification={"status": "read_only"},
            ),
            title="Text Inspect",
        )
        return
    if resolved_kind == "clip":
        from ..commands import fusion as fusion_commands

        conn = get_connection(require_timeline=True)
        item, selector = fusion_commands._resolve_timeline_item(conn, clip_name=target, track=None, record_frame=None)
        inspected = text_ops.inspect_text_item(item)
        inspected["selector"] = selector
        output(
            text_ops.agent_text_payload(
                intent="inspect_text_clip",
                text_kind="existing_text_item",
                route="timeline_item_fusion_readback",
                request={"target": target, "kind": resolved_kind},
                result=inspected,
                verification={"status": "read_only"},
            ),
            title="Text Inspect",
        )
        return
    preset = next((row for row in text_ops.KNOWN_TEXT_PRESETS if row["name"].casefold() == target.casefold()), None)
    output(
        text_ops.agent_text_payload(
            intent="inspect_text_preset",
            text_kind=str(preset.get("text_kind") if preset else "fusion_title_preset"),
            route="static_preset_catalog",
            request={"target": target, "kind": "preset"},
            result=preset
            or {
                "name": target,
                "kind": "fusion-title",
                "editable": "unknown",
                "fields": [],
                "exhaustive": False,
            },
            verification={"status": "read_only"},
        ),
        title="Text Inspect",
    )


@app.command("list-presets")
@handle_errors
def list_presets():
    """List known text presets and visible .setting title templates."""
    templates = []
    try:
        from ..commands import fusion as fusion_commands

        for directory in fusion_commands._template_directories():
            if not os.path.isdir(directory):
                continue
            for entry in sorted(os.listdir(directory)):
                if entry.endswith(".setting"):
                    templates.append({"name": entry, "path": os.path.join(directory, entry), "source": "bundled" if "assets/fusion-templates" in directory else "user"})
    except Exception as exc:
        templates.append({"warning": str(exc)})
    output(
        text_ops.agent_text_payload(
            intent="text_preset_discovery",
            text_kind="preset_catalog",
            route="static_preset_catalog + template_directory_scan",
            request={},
            result={
                "exhaustive": False,
                "builtin_presets": list(text_ops.KNOWN_TEXT_PRESETS),
                "templates": templates,
            },
            verification={"status": "read_only"},
            fallback_used=False,
            warnings=[],
            exhaustive=False,
            builtin_presets=list(text_ops.KNOWN_TEXT_PRESETS),
            templates=templates,
            recommended_default="text insert",
            notes=[
                "DaVinci Resolve does not expose an exhaustive scriptable list of GUI Fusion Titles.",
                "Use text insert for normal visible text and text insert-preset for known DaVinci Resolve preset names.",
            ],
        ),
        title="Text Presets",
    )
