"""Media Pool commands."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Optional

import typer
import click
from typer.core import TyperGroup

from ..connection import get_connection
from ..confirmation import require_force_for_machine_mode
from ..errors import APICallFailed, CLIError, CapabilityNegotiationFailed, MissingArgumentError, ValidationError, handle_errors
from ..output import (
    dry_run_message,
    is_dry_run,
    is_machine_mode,
    mutation_payload,
    output,
    set_dry_run,
    set_output_mode,
    set_verification_status,
    success,
)
from ..policy import enforce_mutation_policy
from ..core import batch_utils, media_pool, media_template_extract, timeline_ops
from ..core.sdk_live_inspection import require_media_pool_mutation_guard


class _MediaTyperGroup(TyperGroup):
    """Route `media append batch` to the command-local batch implementation."""

    def invoke(self, ctx):
        if ctx._protected_args:
            args = [*ctx._protected_args, *ctx.args]
            if len(args) >= 2 and args[0] == "append" and args[1] == "batch":
                ctx._protected_args = ["append-batch"]
                ctx.args = args[2:]
        return super().invoke(ctx)


app = typer.Typer(help="Media Pool operations.", cls=_MediaTyperGroup)


class _ProxyTyperGroup(TyperGroup):
    """Allow legacy `media proxy CLIP --generate` while keeping proxy subcommands."""

    def invoke(self, ctx):
        if ctx._protected_args:
            args = [*ctx._protected_args, *ctx.args]
            commands = getattr(self, "commands", {})
            proxy_flags = {"--generate", "--unlink", "--dry-run", "-n", "--json", "-j"}
            has_legacy_flag = any(token in proxy_flags or token.startswith("--link") for token in args[1:])
            if args[0] not in commands and has_legacy_flag:
                ctx.args = args
                ctx._protected_args = []
                ctx.invoked_subcommand = None
                with ctx:
                    return click.Command.invoke(self, ctx)
        return super().invoke(ctx)


def _apply_proxy_local_flags(ctx: Optional[typer.Context], *, dry_run: bool = False, json_output: bool = False) -> None:
    current = ctx
    while current is not None:
        params = getattr(current, "params", {}) or {}
        dry_run = dry_run or bool(params.get("dry_run"))
        json_output = json_output or bool(params.get("json_output")) or params.get("output_mode") == "json"
        current = getattr(current, "parent", None)
    args = list(getattr(ctx, "args", []) or []) if ctx is not None else []
    dry_run = dry_run or "--dry-run" in args or "-n" in args
    json_output = json_output or "--json" in args or "-j" in args
    if dry_run:
        set_dry_run(True)
    if json_output:
        set_output_mode("json")


def _append_clip_info_from_plan(plan: dict[str, object]) -> dict[str, object]:
    clip_info: dict[str, object] = {
        "mediaPoolItem": plan["clip"],
        "trackIndex": int(plan["track_index"]),
        "trackType": str(plan["track_type"]),
    }
    if plan.get("source_start_frame") is not None:
        clip_info["startFrame"] = int(plan["source_start_frame"])
    if plan.get("source_end_frame") is not None:
        clip_info["endFrame"] = int(plan["source_end_frame"])
    if plan.get("resolved_record_frame") is not None:
        clip_info["recordFrame"] = int(plan["resolved_record_frame"])
    return clip_info


def _compact_append_details(plan: dict[str, object], *, timeline_name: str | None, append_result_count: int) -> dict[str, object]:
    clip_info: dict[str, object] = {
        "mediaPoolItem": plan.get("name"),
        "trackIndex": int(plan["track_index"]),
        "trackType": str(plan["track_type"]),
    }
    if plan.get("source_start_frame") is not None:
        clip_info["startFrame"] = int(plan["source_start_frame"])
    if plan.get("source_end_frame") is not None:
        clip_info["endFrame"] = int(plan["source_end_frame"])
    if plan.get("resolved_record_frame") is not None:
        clip_info["recordFrame"] = int(plan["resolved_record_frame"])
    return {
        "clip": plan.get("name"),
        "folder": plan.get("folder"),
        "timeline_name": timeline_name,
        "track_type": str(plan["track_type"]),
        "track_index": int(plan["track_index"]),
        "record_frame": plan.get("resolved_record_frame"),
        "record_frame_mode": plan.get("record_frame_mode"),
        "source_start_frame": plan.get("source_start_frame"),
        "source_end_frame": plan.get("source_end_frame"),
        "clip_info": clip_info,
        "append_result_count": append_result_count,
        "timeline_items": [],
        "name_after_append": plan.get("name_after_append"),
    }


def _append_readback_identity_matches(row: dict[str, object], plan: dict[str, object]) -> bool:
    expected_media_id = str(plan.get("media_id") or "").strip()
    actual_media_id = str(row.get("media_pool_item_id") or "").strip()
    if expected_media_id:
        return bool(actual_media_id and actual_media_id == expected_media_id)
    expected_path = str(plan.get("source_path") or "").strip()
    actual_path = str(row.get("source_path") or "").strip()
    if expected_path:
        return bool(actual_path and media_pool._source_path_matches(actual_path, expected_path))
    expected_name = str(plan.get("name") or "").strip()
    actual_names = {
        str(row.get("name") or "").strip(),
        str(row.get("media_pool_item_name") or "").strip(),
    }
    return bool(expected_name and expected_name in actual_names)


def _append_verification_expected(plan: dict[str, object]) -> dict[str, object]:
    track_type = str(plan["track_type"])
    track_index = int(plan["track_index"])
    expected_start = plan.get("resolved_record_frame")
    source_end = plan.get("source_end_frame")
    expected_duration = None
    if source_end is not None:
        expected_duration = int(source_end) - int(plan.get("source_start_frame") or 0)
    return {
        "name": plan.get("name"),
        "media_id": plan.get("media_id"),
        "source_path": plan.get("source_path"),
        "track_type": track_type,
        "track_index": track_index,
        "start": expected_start,
        "duration": expected_duration,
    }


def _verify_append_candidates(plan: dict[str, object], candidates: list[dict[str, object]]) -> dict[str, object]:
    expected = _append_verification_expected(plan)
    matching = [row for row in candidates if _append_readback_identity_matches(row, plan)]
    if expected["start"] is not None:
        matching = [row for row in matching if row.get("start") == int(expected["start"])]
    exact = matching
    if expected["duration"] is not None:
        exact = [row for row in matching if row.get("duration") == expected["duration"]]
    if exact:
        return {"status": "verified", "expected": expected, "readback": exact[0]}
    return {"status": "failed", "expected": expected, "candidates": matching}


def _call_timeline_item(item, method_name: str):
    method = getattr(item, method_name, None)
    if not callable(method):
        return None
    try:
        return method()
    except APICallFailed as exc:
        embedded_code = exc.details.get("embedded_error_code")
        unavailable_before_dispatch = (
            embedded_code == "VALIDATION_ERROR"
            and exc.details.get("method") == method_name
        )
        unavailable_on_lua_object = (
            embedded_code == "API_CALL_FAILED"
            and exc.details.get("source") == "CutAgent.lua"
            and str(exc).endswith(f"method not available: {method_name}")
        )
        if unavailable_before_dispatch or unavailable_on_lua_object:
            return None
        raise
    except CLIError:
        raise
    except Exception:
        return None


def _timeline_item_track(item: object) -> tuple[str | None, int | None]:
    track = _call_timeline_item(item, "GetTrackTypeAndIndex")
    if not isinstance(track, (list, tuple)) or len(track) < 2:
        return None, None
    try:
        return str(track[0]).strip().lower(), int(track[1])
    except (TypeError, ValueError):
        return None, None


def _media_pool_item_readback(media_pool_item: object | None) -> dict[str, object]:
    if media_pool_item is None:
        return {
            "media_pool_item_id": None,
            "media_pool_item_name": None,
            "source_path": None,
        }
    properties = _call_timeline_item(media_pool_item, "GetClipProperty")
    if not isinstance(properties, dict):
        properties = {}
    media_pool_item_id = None
    for method_name in ("GetMediaId", "GetUniqueId", "GetUniqueID", "GetMediaID", "GetId", "GetID"):
        media_pool_item_id = _call_timeline_item(media_pool_item, method_name)
        if media_pool_item_id not in (None, ""):
            break
    if media_pool_item_id in (None, ""):
        for key in ("MediaId", "Media ID", "media_id", "Id", "ID"):
            media_pool_item_id = properties.get(key)
            if media_pool_item_id not in (None, ""):
                break
    source_path = None
    for key in ("File Path", "Source File", "SourcePath", "FilePath", "Path"):
        source_path = properties.get(key)
        if source_path not in (None, ""):
            break
    name = _call_timeline_item(media_pool_item, "GetName")
    if name in (None, ""):
        for key in ("Clip Name", "File Name", "FileName", "Name"):
            name = properties.get(key)
            if name not in (None, ""):
                break
    return {
        "media_pool_item_id": str(media_pool_item_id) if media_pool_item_id not in (None, "") else None,
        "media_pool_item_name": str(name) if name not in (None, "") else None,
        "source_path": str(source_path) if source_path not in (None, "") else None,
    }


def _direct_append_identity(
    item: object,
    plan: dict[str, object],
) -> tuple[bool, str, dict[str, object]]:
    media_pool_item = _call_timeline_item(item, "GetMediaPoolItem")
    if media_pool_item is plan.get("clip"):
        return True, "media_pool_object_identity", {
            "media_pool_item_id": plan.get("media_id"),
            "media_pool_item_name": plan.get("name"),
            "source_path": plan.get("source_path"),
        }
    readback = _media_pool_item_readback(media_pool_item)

    expected_media_id = str(plan.get("media_id") or "").strip()
    actual_media_id = str(readback.get("media_pool_item_id") or "").strip()
    if expected_media_id:
        return bool(actual_media_id and actual_media_id == expected_media_id), "media_pool_item_id", readback

    expected_path = str(plan.get("source_path") or "").strip()
    actual_path = str(readback.get("source_path") or "").strip()
    if expected_path:
        return bool(actual_path and media_pool._source_path_matches(actual_path, expected_path)), "source_path", readback

    expected_media_name = str(plan.get("name") or "").strip()
    actual_media_name = str(readback.get("media_pool_item_name") or "").strip()
    if actual_media_name:
        return bool(expected_media_name and actual_media_name == expected_media_name), "media_pool_item_name", readback
    expected_timeline_name = str(plan.get("name_after_append") or plan.get("name") or "").strip()
    actual_timeline_name = str(_call_timeline_item(item, "GetName") or "").strip()
    return bool(expected_timeline_name and actual_timeline_name == expected_timeline_name), "timeline_item_name", readback


def _verify_append_items_direct(
    plan: dict[str, object],
    items: list[object],
    target_item_object_ids: set[int],
    target_item_ids: set[str],
) -> dict[str, object]:
    expected = _append_verification_expected(plan)
    readbacks: list[dict[str, object]] = []
    for item in items:
        start = _call_timeline_item(item, "GetStart")
        end = _call_timeline_item(item, "GetEnd")
        duration = _call_timeline_item(item, "GetDuration")
        item_id = _call_timeline_item(item, "GetUniqueId")
        track_type, track_index = _timeline_item_track(item)
        identity_matches, identity_verification, media_readback = _direct_append_identity(item, plan)
        target_track_membership = id(item) in target_item_object_ids or (
            item_id not in (None, "") and str(item_id) in target_item_ids
        )
        if track_type is not None and track_index is not None:
            track_matches = (
                track_type == str(expected["track_type"]).strip().lower()
                and track_index == int(expected["track_index"])
            )
            track_verification = "GetTrackTypeAndIndex"
        else:
            track_matches = target_track_membership
            track_verification = "target_track_membership"
        readback = {
            "name": _call_timeline_item(item, "GetName"),
            "timeline_item_id": item_id,
            "start": start,
            "end": end,
            "duration": duration,
            "track_type": track_type,
            "track_index": track_index,
            "target_track_membership": target_track_membership,
            "track_verification": track_verification,
            "identity_matches": identity_matches,
            "identity_verification": identity_verification,
            **media_readback,
        }
        readbacks.append(readback)
        start_matches = expected["start"] is None or start == int(expected["start"])
        duration_matches = expected["duration"] is None or duration == expected["duration"]
        if identity_matches and track_matches and start_matches and duration_matches:
            return {"status": "verified", "expected": expected, "readback": readback}
    return {"status": "failed", "expected": expected, "candidates": readbacks}


def _append_verification_error(verification: dict[str, object]) -> dict[str, object]:
    return {
        "code": "VERIFICATION_FAILED",
        "message": "Media append batch entry did not match independent timeline readback.",
        "details": verification,
        "recoverability": "manual",
    }


def _apply_append_verification(row: dict[str, object], verification: dict[str, object]) -> None:
    row["verification"] = verification
    row["ok"] = verification["status"] == "verified"
    if verification["status"] != "verified":
        row["error"] = _append_verification_error(verification)


def _append_track_snapshot(conn, track_type: str, track_index: int) -> dict[str, object]:
    items = conn.timeline.GetItemListInTrack(track_type, track_index) or []
    ids = {
        str(item_id)
        for item in items
        if (item_id := _call_timeline_item(item, "GetUniqueId")) not in (None, "")
    }
    return {
        "count": len(items),
        "ids": ids,
        "complete_ids": len(ids) == len(items),
    }


def _new_append_readback_rows(
    before: dict[str, object],
    after_rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    if int(before["count"]) == 0:
        return after_rows
    if not before["complete_ids"]:
        return []
    before_ids = before["ids"]
    return [
        row for row in after_rows
        if row.get("timeline_item_id") not in (None, "")
        and str(row.get("timeline_item_id")) not in before_ids
    ]


def _append_readbacks_same_item(left: dict[str, object], right: dict[str, object]) -> bool:
    same_range = all(left.get(key) == right.get(key) for key in ("start", "end", "duration"))
    left_timeline_item_id = str(left.get("timeline_item_id") or "").strip()
    right_timeline_item_id = str(right.get("timeline_item_id") or "").strip()
    if left_timeline_item_id and right_timeline_item_id:
        return left_timeline_item_id == right_timeline_item_id
    left_media_pool_item_id = str(left.get("media_pool_item_id") or "").strip()
    right_media_pool_item_id = str(right.get("media_pool_item_id") or "").strip()
    if left_media_pool_item_id and right_media_pool_item_id:
        return same_range and left_media_pool_item_id == right_media_pool_item_id
    left_path = str(left.get("source_path") or "").strip()
    right_path = str(right.get("source_path") or "").strip()
    if left_path and right_path:
        return same_range and media_pool._source_path_matches(left_path, right_path)
    left_names = {
        str(left.get("name") or "").strip(),
        str(left.get("media_pool_item_name") or "").strip(),
    } - {""}
    right_names = {
        str(right.get("name") or "").strip(),
        str(right.get("media_pool_item_name") or "").strip(),
    } - {""}
    return same_range and bool(left_names.intersection(right_names))


def _exclude_direct_readbacks(
    available: list[dict[str, object]],
    direct_readbacks: list[dict[str, object]],
) -> None:
    for direct_readback in direct_readbacks:
        matching_index = next(
            (index for index, row in enumerate(available) if _append_readbacks_same_item(row, direct_readback)),
            None,
        )
        if matching_index is not None:
            available.pop(matching_index)


def _append_plan_serial(conn, plan: dict[str, object], *, timeline_name: str | None) -> dict[str, object]:
    clip_info = _append_clip_info_from_plan(plan)
    append_result = conn.media_pool.AppendToTimeline([clip_info])
    if not append_result:
        raise APICallFailed(
            "Media append batch entry failed.",
            details={"index": int(plan["index"]), "timeline": timeline_name},
        )
    appended_items = append_result if isinstance(append_result, list) else []
    if appended_items:
        name_after_append = plan.get("name_after_append")
        if name_after_append:
            for item in appended_items:
                setter = getattr(item, "SetName", None)
                if callable(setter):
                    try:
                        setter(str(name_after_append))
                    except Exception:
                        pass
    row: dict[str, object] = {
        "index": int(plan["index"]),
        "ok": True,
        "skipped": False,
        "changed": True,
        "target": {"kind": "media", "name": plan.get("name"), "folder": plan.get("folder")},
        "preflight": plan.get("preflight"),
        "append": _compact_append_details(plan, timeline_name=timeline_name, append_result_count=len(appended_items) or 1),
        "timeline_switch": None,
        "_appended_items": appended_items,
    }
    del append_result
    del clip_info
    return row


def _append_plans_serial(conn, plans: list[dict[str, object]], *, timeline_name: str | None) -> list[dict[str, object]]:
    # DaVinci Resolve can spend tens of minutes on one huge AppendToTimeline list; one-entry calls stay responsive.
    track_keys = {(str(plan["track_type"]), int(plan["track_index"])) for plan in plans}
    before_by_track = {key: _append_track_snapshot(conn, key[0], key[1]) for key in track_keys}
    rows = [_append_plan_serial(conn, plan, timeline_name=timeline_name) for plan in plans]
    direct_by_track: dict[
        tuple[str, int],
        list[tuple[dict[str, object], dict[str, object], list[object]]],
    ] = {}
    fallback_by_track: dict[tuple[str, int], list[tuple[dict[str, object], dict[str, object]]]] = {}
    direct_readbacks_by_track: dict[tuple[str, int], list[dict[str, object]]] = {}
    for plan, row in zip(plans, rows, strict=True):
        appended_items = row.pop("_appended_items", [])
        key = (str(plan["track_type"]), int(plan["track_index"]))
        if appended_items:
            direct_by_track.setdefault(key, []).append((plan, row, appended_items))
            continue
        fallback_by_track.setdefault(key, []).append((plan, row))

    for key, pending in direct_by_track.items():
        target_track_items = conn.timeline.GetItemListInTrack(key[0], key[1]) or []
        target_item_object_ids = {id(item) for item in target_track_items}
        target_item_ids = {
            str(item_id)
            for item in target_track_items
            if (item_id := _call_timeline_item(item, "GetUniqueId")) not in (None, "")
        }
        for plan, row, appended_items in pending:
            verification = _verify_append_items_direct(
                plan,
                appended_items,
                target_item_object_ids,
                target_item_ids,
            )
            _apply_append_verification(row, verification)
            direct_readbacks_by_track.setdefault(key, []).extend(
                [verification["readback"]] if verification.get("readback") else verification.get("candidates", [])
            )

    for key, pending in fallback_by_track.items():
        after_rows = timeline_ops.get_track_items(conn, key[0], key[1])
        available = _new_append_readback_rows(before_by_track[key], after_rows)
        _exclude_direct_readbacks(available, direct_readbacks_by_track.get(key, []))
        for plan, row in pending:
            verification = _verify_append_candidates(plan, available)
            _apply_append_verification(row, verification)
            verified_row = verification.get("readback")
            if verified_row in available:
                available.remove(verified_row)
    return rows


def _timeline_name(timeline) -> str | None:
    if timeline is not None and hasattr(timeline, "GetName"):
        try:
            return str(timeline.GetName())
        except Exception:
            return None
    return None


def _timeline_start_frame(timeline) -> int | None:
    if timeline is not None and hasattr(timeline, "GetStartFrame"):
        try:
            return int(timeline.GetStartFrame())
        except Exception:
            return None
    return None


def _append_batch_timeline_start_frames(conn) -> tuple[str | None, dict[str, int]]:
    current_timeline = getattr(conn, "timeline", None)
    current_name = _timeline_name(current_timeline)
    start_frames: dict[str, int] = {}
    current_start_frame = _timeline_start_frame(current_timeline)
    if current_start_frame is None:
        current_start = getattr(conn, "start_frame", None)
        if current_start is not None:
            try:
                current_start_frame = int(current_start)
            except Exception:
                current_start_frame = None
    if current_name and current_start_frame is not None:
        start_frames[current_name] = current_start_frame

    project = getattr(conn, "project", None)
    count_getter = getattr(project, "GetTimelineCount", None) if project is not None else None
    timeline_getter = getattr(project, "GetTimelineByIndex", None) if project is not None else None
    if callable(count_getter) and callable(timeline_getter):
        try:
            count = int(count_getter() or 0)
        except Exception:
            count = 0
        for index in range(1, count + 1):
            try:
                timeline = timeline_getter(index)
            except Exception:
                continue
            name = _timeline_name(timeline)
            start_frame = _timeline_start_frame(timeline)
            if name and start_frame is not None and name not in start_frames:
                start_frames[name] = start_frame
    return current_name, start_frames


def _append_entry_timeline_start_frame(
    entry: dict[str, object],
    *,
    current_timeline: str | None,
    start_frames: dict[str, int],
) -> int | None:
    target_timeline = entry.get("timeline")
    if target_timeline is None:
        return start_frames.get(str(current_timeline)) if current_timeline is not None else None

    target_name = str(target_timeline)
    if target_name in start_frames:
        return start_frames[target_name]
    raise APICallFailed(
        f"Timeline '{target_name}' not found.",
        details={"timeline": target_name},
    )


def _coerce_property_value(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _property_values_match(actual: object, expected: object) -> bool:
    actual_str = _coerce_property_value(actual)
    expected_str = _coerce_property_value(expected)
    if actual_str == expected_str:
        return True
    try:
        return float(actual_str) == float(expected_str)
    except (TypeError, ValueError):
        return False


def _validate_import_path(path: str) -> tuple[str, str]:
    candidate = Path(path).expanduser()
    if not candidate.exists():
        raise ValidationError(
            "Media import path does not exist.",
            details={"path": str(candidate)},
        )
    if candidate.is_file():
        return str(candidate), "file"
    if candidate.is_dir():
        return str(candidate), "folder"
    raise ValidationError(
        "Media import path must be a file or folder.",
        details={"path": str(candidate)},
    )


def _require_sdk_exact_import_file(path: str, expected_identity: str | None = None) -> str:
    absolute_path = os.path.abspath(os.path.expanduser(path))
    canonical_path = os.path.realpath(absolute_path)
    try:
        file_info = os.lstat(absolute_path)
    except OSError:
        file_info = None
    if canonical_path != absolute_path or file_info is None or not stat.S_ISREG(file_info.st_mode):
        raise CapabilityNegotiationFailed(
            "SDK Media Pool import requires one exact regular file and rejects directories or symbolic-link traversal.",
            details={"capability_id": "media.import", "reason": "sdk_media_import_exact_file_required"},
        )
    if expected_identity is not None:
        try:
            expected = json.loads(expected_identity)
        except (TypeError, ValueError, json.JSONDecodeError):
            expected = None
        actual = {
            "device": str(file_info.st_dev),
            "inode": str(file_info.st_ino),
            "size": str(file_info.st_size),
            "modifiedNanoseconds": str(file_info.st_mtime_ns),
        }
        if not isinstance(expected, dict) or set(expected) != set(actual) or expected != actual:
            raise CapabilityNegotiationFailed(
                "SDK Media Pool import file identity changed after inspection.",
                details={"capability_id": "media.import", "reason": "sdk_media_import_file_identity_changed"},
            )
    return canonical_path


def _validate_existing_media_path(path: str, *, label: str) -> tuple[str, str]:
    candidate = Path(path).expanduser()
    if not candidate.exists():
        raise ValidationError(
            f"{label} path does not exist.",
            details={"path": str(candidate)},
        )
    if candidate.is_file():
        return str(candidate), "file"
    if candidate.is_dir():
        return str(candidate), "folder"
    raise ValidationError(
        f"{label} path must be a file or folder.",
        details={"path": str(candidate)},
    )


def _validate_output_file_parent(path: str, *, label: str) -> str:
    candidate = Path(path).expanduser()
    parent = candidate.parent if str(candidate.parent) else Path(".")
    if not parent.exists():
        raise ValidationError(
            f"{label} parent directory does not exist.",
            details={"path": str(candidate), "parent": str(parent)},
        )
    if not parent.is_dir():
        raise ValidationError(
            f"{label} parent path is not a directory.",
            details={"path": str(candidate), "parent": str(parent)},
        )
    return str(candidate)


def _validate_proxy_action(generate: bool, link_path: Optional[str], unlink: bool) -> tuple[str, Optional[str]]:
    action_count = sum(1 for flag in (generate, bool(link_path), unlink) if flag)
    if action_count == 0:
        raise MissingArgumentError("Choose one proxy action: --generate, --link, or --unlink.")
    if action_count > 1:
        raise ValidationError("Choose exactly one proxy action: --generate, --link, or --unlink.")
    if generate:
        return "generate", None
    if link_path:
        return "link", link_path
    return "unlink", None


def _audio_sync_preview_settings(
    mode: Optional[str],
    channel: Optional[int],
    retain_embedded_audio: Optional[bool],
    retain_video_metadata: Optional[bool],
) -> dict[str, object]:
    settings: dict[str, object] = {}
    if mode is not None:
        normalized_mode = str(mode).strip().lower()
        if normalized_mode not in {"timecode", "waveform"}:
            raise ValidationError(
                f"Unsupported audio sync mode '{mode}'.",
                details={"mode": mode, "allowed": ["timecode", "waveform"]},
            )
        settings["mode"] = normalized_mode
    if channel is not None:
        settings["channel"] = int(channel)
    if retain_embedded_audio is not None:
        settings["retain_embedded_audio"] = bool(retain_embedded_audio)
    if retain_video_metadata is not None:
        settings["retain_video_metadata"] = bool(retain_video_metadata)
    return settings


@app.command("list")
@handle_errors
def list_clips(
    recursive: bool = typer.Option(False, "--recursive", "-r", help="Include subfolders"),
    kind: Optional[str] = typer.Option(None, "--kind", help="Filter by kind: media, timeline, subtitle"),
    include_generated: bool = typer.Option(True, "--include-generated/--exclude-generated", help="Include generated/internal assets"),
):
    """List clips in the current Media Pool folder."""
    conn = get_connection(require_project=True)
    rows = media_pool.list_clips(
        conn,
        recursive,
        kind=kind,
        include_generated=include_generated,
    )
    output(rows, columns=[("name", "Name"), ("type", "Type"), ("duration", "Duration"), ("resolution", "Resolution")],
           title="Media Pool Clips", quiet_key="name")


@app.command("info")
@handle_errors
def clip_info(name: str = typer.Argument(..., help="Clip name")):
    """Show detailed clip information."""
    conn = get_connection(require_project=True)
    props = media_pool.get_clip_info(conn, name)
    output(props, title=f"Clip: {name}")


@app.command("extract-template")
@handle_errors
def extract_template(
    clip: str = typer.Argument(..., help="Media Pool clip name, id, or source path"),
    fields: str = typer.Option("text,image", "--fields", help="Comma-separated fields: text,image"),
    exact: bool = typer.Option(False, "--exact", help="Require an exact name/id/path match"),
    folder: Optional[str] = typer.Option(None, "--folder", help="Disambiguate by Media Pool folder path"),
    allow_temp_append: bool = typer.Option(False, "--allow-temp-append/--no-temp-append", help="Allow a reversible temporary timeline append"),
    temp_track: Optional[int] = typer.Option(None, "--temp-track", min=1, help="Video track for the temporary append"),
    temp_duration: str = typer.Option("1s", "--temp-duration", help="Temporary append duration"),
    temp_gap: str = typer.Option("1s", "--temp-gap", help="Gap after current timeline end for temporary append"),
    include_nested: bool = typer.Option(True, "--include-nested/--no-include-nested", help="Inspect nested/compound timeline contents when available"),
    cleanup: bool = typer.Option(True, "--cleanup/--keep-temp", help="Delete the temporary item created by this command"),
    json_output: bool = typer.Option(False, "--json", "-j", help="JSON output"),
):
    """Extract text/image metadata from a Media Pool template clip."""
    if json_output:
        set_output_mode("json")
    enforce_mutation_policy(
        "media.extract_template",
        intended_engine="api_native",
        mutating=bool(allow_temp_append),
    )
    conn = get_connection(require_project=True, require_timeline=allow_temp_append)
    fps = float(getattr(conn, "fps", 25.0) or 25.0)
    data = media_template_extract.extract_media_template(
        conn,
        clip,
        media_template_extract.parse_fields(fields),
        exact=exact,
        folder=folder,
        allow_temp_append=allow_temp_append,
        temp_track=temp_track,
        temp_duration_frames=media_template_extract.parse_duration_frames(temp_duration, fps),
        include_nested=include_nested,
        cleanup=cleanup,
        temp_gap_frames=media_template_extract.parse_duration_frames(temp_gap, fps),
    )
    if any(warning.get("code") == "TEMP_CLEANUP_FAILED" for warning in data.get("warnings", [])):
        set_verification_status("partial")
    output(data, title="Media Template Extraction")


@app.command("import")
@handle_errors
def import_media(
    path: str = typer.Argument(..., help="File or folder path to import"),
):
    """Import media into the Media Pool."""
    import_path, path_kind = _validate_import_path(path)
    enforce_mutation_policy(
        "media.import",
        intended_engine="api_native",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        output(
            mutation_payload(
                action="media.import",
                changed=False,
                target={"kind": path_kind, "path": import_path},
                message=f"Would import media from: {import_path}",
            )
        )
        return
    conn = get_connection(require_project=True)
    # SDK semantic placement carries the same coherent timeline snapshot guard
    # used by marker mutations. Normal CLI imports have no guard environment
    # and return immediately from this fail-closed precondition.
    timeline_ops.require_sdk_marker_mutation_guard(conn)
    require_media_pool_mutation_guard(conn)
    if os.environ.get("CUTAGENT_SDK_MEDIA_IMPORT_ROOT") == "1":
        expected_file_identity = os.environ.get("CUTAGENT_SDK_MEDIA_IMPORT_FILE_IDENTITY")
        if not expected_file_identity:
            raise CapabilityNegotiationFailed(
                "SDK Media Pool import requires an inspected exact-file identity.",
                details={"capability_id": "media.import", "reason": "sdk_media_import_file_identity_required"},
            )
        import_path = _require_sdk_exact_import_file(
            import_path,
            expected_file_identity,
        )
        root = conn.media_pool.GetRootFolder()
        current = conn.media_pool.GetCurrentFolder()
        root_id = getattr(root, "GetUniqueId", lambda: None)() if root else None
        current_id = getattr(current, "GetUniqueId", lambda: None)() if current else None
        if not root or not current or (root is not current and (not root_id or root_id != current_id)):
            raise CapabilityNegotiationFailed(
                "SDK root import requires the Media Pool root to be the current folder; CutAgent will not change UI selection implicitly.",
                details={"capability_id": "media.import", "reason": "sdk_media_pool_root_not_current"},
            )
    count = media_pool.import_media(conn, import_path)
    output(
        mutation_payload(
            action="media.import",
            target={"kind": path_kind, "path": import_path},
            imported_count=count,
            message=f"Imported {count} item(s).",
        )
    )


@app.command("delete")
@handle_errors
def delete_clip(
    name: str = typer.Argument(..., help="Clip name"),
    force: bool = typer.Option(False, "--force", "-f"),
):
    """Delete a clip from the Media Pool."""
    enforce_mutation_policy(
        "media.clip_management",
        intended_engine="api_native",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        dry_run_message(f"Would delete clip: {name}")
        return
    require_force_for_machine_mode(
        force=force,
        action="media.delete",
        target_kind="clip",
        target_name=name,
        prompt=f"Delete clip '{name}'?",
    )

    conn = get_connection(require_project=True)
    media_pool.delete_clip(conn, name)
    output(
        mutation_payload(
            action="media.delete",
            target={"kind": "clip", "name": name},
            message=f"Deleted clip: {name}",
        )
    )


@app.command("move")
@handle_errors
def move_clip(
    name: str = typer.Argument(..., help="Clip name"),
    target: str = typer.Argument(..., help="Target folder path"),
):
    """Move a clip to a different folder."""
    target = target.strip()
    if not target:
        raise ValidationError("Target folder path is required.")

    enforce_mutation_policy(
        "media.clip_management",
        intended_engine="api_native",
        mutating=not is_dry_run(),
    )
    conn = get_connection(require_project=True)
    move_context = media_pool.validate_clip_move(conn, name, target)
    if is_dry_run():
        output(
            mutation_payload(
                action="media.move",
                changed=False,
                target={"kind": "clip", "name": name, "folder": move_context.get("source_folder")},
                destination={"kind": "folder", "path": move_context.get("destination_folder")},
                message=f"Would move '{name}' to '{move_context.get('destination_folder')}'.",
            )
        )
        return
    media_pool.move_clip(conn, name, target)
    output(
        mutation_payload(
            action="media.move",
            target={"kind": "clip", "name": name, "folder": move_context.get("source_folder")},
            destination={"kind": "folder", "path": move_context.get("destination_folder")},
            message=f"Moved '{name}' to '{move_context.get('destination_folder')}'.",
        )
    )


@app.command("duplicate")
@handle_errors
def duplicate_clip(
    name: str = typer.Argument(..., help="Clip name"),
    new_name: Optional[str] = typer.Option(None, "--new-name", help="Optional new clip name"),
):
    """Duplicate a media pool clip."""
    enforce_mutation_policy(
        "media.duplicate",
        intended_engine="api_native",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        output(mutation_payload(
            action="media.duplicate",
            target={"kind": "clip", "name": name},
            changed=False,
            new_name=new_name,
            message=(
                f"DRY-RUN: would duplicate clip '{name}' as '{new_name}'."
                if new_name
                else f"DRY-RUN: would duplicate clip '{name}'."
            ),
        ))
        return
    conn = get_connection(require_project=True)
    data = media_pool.duplicate_clip(conn, name, new_name)
    output(data, title="Duplicate Clip")


@app.command("unlink")
@handle_errors
def unlink_clip(
    name: str = typer.Argument(..., help="Clip name"),
):
    """Unlink clip from source media."""
    enforce_mutation_policy(
        "media.unlink_relink",
        intended_engine="api_native",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        output(
            mutation_payload(
                action="media.unlink",
                changed=False,
                target={"kind": "clip", "name": name},
                runtime_validation="not_performed",
                message=f"Would unlink clip '{name}' from source media.",
            )
        )
        return

    conn = get_connection(require_project=True)
    media_pool.unlink_clip(conn, name)
    success(f"Unlinked clip: {name}")


@app.command("relink")
@handle_errors
def relink_clip(
    name: str = typer.Argument(..., help="Clip name"),
    path: str = typer.Argument(..., help="New media path"),
):
    """Relink clip to a media path."""
    relink_path, path_kind = _validate_existing_media_path(path, label="Relink media")
    enforce_mutation_policy(
        "media.unlink_relink",
        intended_engine="api_native",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        output(
            mutation_payload(
                action="media.relink",
                changed=False,
                target={"kind": "clip", "name": name},
                destination={"kind": path_kind, "path": relink_path},
                runtime_validation="not_performed",
                message=f"Would relink clip '{name}' to: {relink_path}",
            )
        )
        return

    conn = get_connection(require_project=True)
    media_pool.relink_clip(conn, name, relink_path)
    success(f"Relinked clip '{name}' to: {relink_path}")


proxy_app = typer.Typer(
    help="Media Pool proxy/full-resolution media.",
    cls=_ProxyTyperGroup,
    invoke_without_command=True,
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
app.add_typer(proxy_app, name="proxy")


@proxy_app.callback(invoke_without_command=True)
@handle_errors
def proxy_clip(
    ctx: typer.Context = None,
    name: Optional[str] = typer.Option(None, "--name", hidden=True),
    generate: bool = typer.Option(False, "--generate", help="Generate proxy/optimized media"),
    link: Optional[str] = typer.Option(None, "--link", help="Link proxy media path"),
    unlink: bool = typer.Option(False, "--unlink", help="Unlink proxy media"),
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Show what would happen without making changes"),
    json_output: bool = typer.Option(False, "--json", "-j", help="JSON output"),
):
    """Manage clip proxy media."""
    if hasattr(ctx, "invoked_subcommand") and ctx.invoked_subcommand is not None:
        return
    _apply_proxy_local_flags(ctx, dry_run=dry_run, json_output=json_output)
    legacy_args = list(getattr(ctx, "args", []) or [])
    generate = generate or "--generate" in legacy_args
    unlink = unlink or "--unlink" in legacy_args
    if link is None:
        for index, token in enumerate(legacy_args):
            if token == "--link" and index + 1 < len(legacy_args):
                link = legacy_args[index + 1]
                break
            if token.startswith("--link="):
                link = token.split("=", 1)[1]
                break
    name = name or (legacy_args[0] if legacy_args else None)
    if not name:
        raise MissingArgumentError("Clip name is required for proxy management.")
    proxy_action, proxy_path = _validate_proxy_action(generate, link, unlink)
    enforce_mutation_policy(
        "media.proxy_transcode",
        intended_engine="api_native",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        message = f"Would {proxy_action} proxy media for '{name}'."
        if proxy_action == "link":
            message = f"Would link proxy media for '{name}' to '{proxy_path}'."
        output(
            mutation_payload(
                action=f"media.proxy.{proxy_action}",
                changed=False,
                target={"kind": "clip", "name": name},
                proxy_action=proxy_action,
                path=proxy_path,
                runtime_validation="not_performed",
                message=message,
            )
        )
        return

    conn = get_connection(require_project=True)
    data = media_pool.proxy_clip(conn, name, generate=generate, link_path=link, unlink=unlink)
    output(data, title="Proxy")


@app.command("transcode")
@handle_errors
def transcode_clip(
    name: str = typer.Argument(..., help="Clip name"),
    output_path: str = typer.Option(..., "--output", help="Output path"),
    format: Optional[str] = typer.Option(None, "--format", help="Optional transcode format"),
    codec: Optional[str] = typer.Option(None, "--codec", help="Optional transcode codec"),
):
    """Transcode media pool clip."""
    output_path = _validate_output_file_parent(output_path, label="Transcode output")
    enforce_mutation_policy(
        "media.proxy_transcode",
        intended_engine="api_native",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        output(
            mutation_payload(
                action="media.transcode",
                changed=False,
                target={"kind": "clip", "name": name},
                destination={"kind": "file", "path": output_path},
                format=format,
                codec=codec,
                runtime_validation="not_performed",
                message=f"Would transcode '{name}' to: {output_path}",
            )
        )
        return

    conn = get_connection(require_project=True)
    data = media_pool.transcode_clip(conn, name, output_path=output_path, format_name=format, codec=codec)
    output(data, title="Transcode")


@app.command("metadata")
@handle_errors
def metadata(
    args: Optional[list[str]] = typer.Argument(None, help="CLIP [KEY [VALUE]] or export FILE [CLIP...]"),
    name: Optional[str] = typer.Option(None, "--name", hidden=True),
    key: Optional[str] = typer.Option(None, "--key", hidden=True),
    value: Optional[str] = typer.Option(None, "--value", hidden=True),
):
    """Get/set clip metadata; also accepts `media metadata export FILE [CLIP...]`."""
    if not isinstance(args, list):
        args = None
    if args is None and name is not None:
        args = [name]
        if key is not None:
            args.append(key)
        if value is not None:
            args.append(value)
    if not args:
        raise MissingArgumentError("Metadata command requires arguments.")
    if args[0] == "export":
        if len(args) < 2:
            raise MissingArgumentError("Metadata export requires an output file.")
        export_path = _validate_output_file_parent(args[1], label="Metadata export")
        enforce_mutation_policy(
            "media.metadata_write",
            intended_engine="api_native",
            mutating=not is_dry_run(),
        )
        if is_dry_run():
            dry_run_message(f"Would export Media Pool metadata to: {export_path}")
            return
        conn = get_connection(require_project=True)
        output(media_pool.export_metadata(conn, export_path, args[2:] or None), title="Metadata Export")
        return

    name = args[0]
    key = args[1] if len(args) >= 2 else None
    value = args[2] if len(args) >= 3 else None
    if len(args) > 3:
        raise ValidationError("Too many metadata arguments. Use CLIP [KEY [VALUE]] or export FILE [CLIP...].")

    if key is not None and value is not None:
        enforce_mutation_policy(
            "media.metadata_write",
            intended_engine="api_native",
            mutating=not is_dry_run(),
        )
        if is_dry_run():
            output(
                mutation_payload(
                    action="media.metadata.set",
                    changed=False,
                    target={"kind": "clip", "name": name},
                    key=key,
                    value=value,
                    message=f"Would set {key} = {value}",
                )
            )
            return
        conn = get_connection(require_project=True)
        media_pool.set_clip_metadata(conn, name, key, value)
        output(
            mutation_payload(
                action="media.metadata.set",
                target={"kind": "clip", "name": name},
                key=key,
                value=value,
                message=f"Set {key} = {value}",
            )
        )
    elif key is not None:
        conn = get_connection(require_project=True)
        val = media_pool.get_clip_metadata(conn, name, key)
        output({key: val})
    else:
        conn = get_connection(require_project=True)
        all_meta = media_pool.get_clip_metadata(conn, name)
        output(all_meta, title=f"Metadata: {name}")


@app.command("search")
@handle_errors
def search(
    query: str = typer.Argument(..., help="Search query"),
    exact: bool = typer.Option(False, "--exact", help="Exact name match"),
    kind: Optional[str] = typer.Option(None, "--kind", help="Filter by kind: media, timeline, subtitle"),
    include_generated: bool = typer.Option(True, "--include-generated/--exclude-generated", help="Include generated/internal assets"),
):
    """Search for clips in the entire Media Pool."""
    conn = get_connection(require_project=True)
    results = media_pool.search_clips(
        conn,
        query,
        exact,
        kind=kind,
        include_generated=include_generated,
    )
    output(results, columns=[("name", "Name"), ("folder", "Folder")],
           title=f"Search: {query}", quiet_key="name")


@app.command("append")
@handle_errors
def append_clip(
    name: str = typer.Argument(..., help="Clip name"),
    at: Optional[str] = typer.Option(None, "--at", help="Record-domain position; legacy alias for --record-frame"),
    timeline_name: Optional[str] = typer.Option(None, "--timeline", help="Target timeline name; defaults to active timeline"),
    track_type: str = typer.Option("video", "--track-type", help="Track type: video or audio"),
    track_index: int = typer.Option(1, "--track", "--track-index", help="Timeline track index"),
    source_start: Optional[str] = typer.Option(None, "--source-start", "--start-frame", help="Source-domain startFrame"),
    source_end: Optional[str] = typer.Option(None, "--source-end", "--end-frame", help="Source-domain endFrame"),
    record_frame: Optional[str] = typer.Option(None, "--record-frame", help="Record-domain recordFrame"),
    absolute_record_frame: Optional[int] = typer.Option(None, "--absolute-record-frame", help="Exact DaVinci Resolve API recordFrame; no timeline-start offset is applied"),
):
    """Append a clip to the timeline with optional precise source/record frames."""
    normalized_track_type = media_pool.normalize_append_track_type(track_type)
    validated_track_index = media_pool.validate_append_track_index(track_index)
    if sum(value is not None for value in (at, record_frame, absolute_record_frame)) > 1:
        raise ValidationError(
            "Use only one of --at, --record-frame, or --absolute-record-frame.",
            details={"at": at, "record_frame": record_frame, "absolute_record_frame": absolute_record_frame},
        )
    enforce_mutation_policy("media.append", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        output(mutation_payload(
            action="media.append",
            target={"kind": "media", "name": name, "timeline": timeline_name or "current"},
            changed=False,
            timeline=timeline_name,
            at=at,
            source_start=source_start,
            source_end=source_end,
            record_frame=record_frame,
            absolute_record_frame=absolute_record_frame,
            track_type=normalized_track_type,
            track_index=validated_track_index,
            message=(
                f"DRY-RUN: would append '{name}' to {normalized_track_type} track {validated_track_index} "
                "using precise AppendToTimeline clip info."
            ),
        ))
        return

    conn = get_connection(require_timeline=True)
    timeline_ops.require_sdk_marker_mutation_guard(conn)
    original_timeline = None
    timeline_switch = None
    restored_original_timeline = False
    if timeline_name:
        original_timeline = conn.project.GetCurrentTimeline() if getattr(conn, "project", None) and hasattr(conn.project, "GetCurrentTimeline") else getattr(conn, "timeline", None)
        timeline_switch = timeline_ops.switch_timeline(conn, name=timeline_name, return_details=True)
    result = media_pool.append_clip_to_timeline(
        conn,
        name,
        at,
        normalized_track_type,
        validated_track_index,
        source_start=source_start,
        source_end=source_end,
        record_frame=record_frame,
        absolute_record_frame=absolute_record_frame,
        return_details=True,
    )
    if original_timeline is not None and getattr(conn, "project", None) and hasattr(conn.project, "SetCurrentTimeline"):
        try:
            restored_original_timeline = bool(conn.project.SetCurrentTimeline(original_timeline))
            conn.refresh()
        except Exception:
            restored_original_timeline = False
    output(
        mutation_payload(
            action="media.append",
            target={"kind": "media", "name": name, "folder": result.get("folder")},
            timeline=result.get("timeline_name") or timeline_name,
            timeline_switch={key: value for key, value in (timeline_switch or {}).items() if key != "timeline"} if timeline_switch else None,
            restored_original_timeline=restored_original_timeline,
            track_type=result.get("track_type"),
            track_index=result.get("track_index"),
            record_frame=result.get("record_frame"),
            record_frame_mode=result.get("record_frame_mode"),
            source_start_frame=result.get("source_start_frame"),
            source_end_frame=result.get("source_end_frame"),
            clip_info=result.get("clip_info"),
            append_result_count=result.get("append_result_count"),
            message=f"Appended '{name}' to timeline.",
        )
    )


@app.command("append-batch", hidden=True)
@handle_errors
def append_batch(
    batch: Optional[Path] = typer.Option(None, "--batch", help="JSON batch file"),
    input_file: Optional[Path] = typer.Option(None, "--input", help="JSON batch file alias"),
    batch_json: Optional[str] = typer.Option(None, "--batch-json", help="Inline JSON batch payload"),
    allow_partial: bool = typer.Option(False, "--allow-partial", help="Apply valid entries even when some entries fail preflight"),
):
    """Append multiple Media Pool items with all-entry preflight."""
    enforce_mutation_policy("media.append", intended_engine="api_native", mutating=not is_dry_run())
    conn = get_connection(require_timeline=True)
    entries = batch_utils.load_batch_entries(batch_path=batch, input_path=input_file, batch_json=batch_json)
    media_matches = media_pool.collect_append_media_matches(conn, entries=entries)
    media_lookup = media_pool.build_append_media_lookup_index(media_matches)
    current_timeline, timeline_start_frames = _append_batch_timeline_start_frames(conn)
    plans, preflight_results = batch_utils.preflight_entries(
        entries,
        lambda entry: media_pool.plan_append_entry(
            conn,
            entry,
            media_matches=media_lookup,
            timeline_start_frame=_append_entry_timeline_start_frame(
                entry,
                current_timeline=current_timeline,
                start_frames=timeline_start_frames,
            ),
        ),
        allow_partial=allow_partial,
    )
    preflight = {
        "status": "passed" if all(row.get("ok") for row in preflight_results) else "partial",
        "timeline": current_timeline,
        "requested_count": len(entries),
        "planned_count": len(plans),
    }
    if is_dry_run():
        output(
            batch_utils.batch_payload(
                action="media.append.batch",
                target={"kind": "timeline", "name": current_timeline},
                changed=False,
                dry_run=True,
                allow_partial=allow_partial,
                preflight=preflight,
                results=[{**row, "changed": False} for row in preflight_results],
            ),
            title="Media Append Batch",
        )
        return

    original_timeline = conn.project.GetCurrentTimeline() if getattr(conn, "project", None) and hasattr(conn.project, "GetCurrentTimeline") else getattr(conn, "timeline", None)
    results: list[dict[str, object]] = []
    timeline_switches: list[dict[str, object]] = []
    active_batch_timeline = current_timeline
    try:
        index = 0
        while index < len(plans):
            plan = plans[index]
            timeline_switch = None
            target_timeline = plan.get("timeline")
            timeline_name = str(target_timeline) if target_timeline else active_batch_timeline
            if target_timeline and str(target_timeline) != str(active_batch_timeline or ""):
                timeline_switch = timeline_ops.switch_timeline(conn, name=str(target_timeline), return_details=True)
                timeline_switches.append({key: value for key, value in timeline_switch.items() if key != "timeline"})
                active_batch_timeline = str(target_timeline)
                timeline_name = active_batch_timeline
            group = [plan]
            index += 1
            while index < len(plans):
                next_plan = plans[index]
                next_timeline = str(next_plan.get("timeline")) if next_plan.get("timeline") else active_batch_timeline
                if next_timeline != timeline_name:
                    break
                group.append(next_plan)
                index += 1
            group_rows = _append_plans_serial(conn, group, timeline_name=timeline_name)
            if timeline_switch and group_rows:
                switch_summary = {key: value for key, value in timeline_switch.items() if key != "timeline"}
                group_rows[0]["timeline_switch"] = switch_summary
            results.extend(group_rows)
    finally:
        if original_timeline is not None and getattr(conn, "project", None) and hasattr(conn.project, "SetCurrentTimeline"):
            try:
                conn.project.SetCurrentTimeline(original_timeline)
                conn.refresh()
            except Exception:
                pass

    if allow_partial:
        results.extend(row for row in preflight_results if row.get("error"))
    verification_status = "verified" if results and all(row.get("ok") for row in results) else "failed"
    set_verification_status(verification_status)
    output(
        batch_utils.batch_payload(
            action="media.append.batch",
            target={"kind": "timeline", "name": current_timeline},
            changed=any(row.get("changed") for row in results),
            dry_run=False,
            allow_partial=allow_partial,
            preflight=preflight,
            results=results,
            verification={"status": verification_status},
            timeline_switches=timeline_switches,
            append_strategy={"mode": "serial_append_to_timeline", "grouping": "target_timeline", "append_call_size": 1},
        ),
        title="Media Append Batch",
    )


# --- Folders ---

folders_app = typer.Typer(help="Media Pool folder management.")
app.add_typer(folders_app, name="folders")
