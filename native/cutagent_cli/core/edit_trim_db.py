"""Verified non-ripple video head/tail trim through a Disk Project.db mutation."""

from __future__ import annotations

import math
import sqlite3
import unicodedata
from typing import Any

from ..errors import APICallFailed, ValidationError
from ..output import set_recoverability, set_verification_status
from ..utils.timecode import seconds_to_frames
from . import db_session, edit_ops, timeline_item_duration_db, timeline_ops


# Fail closed until the linked-preserving path has fresh real-DaVinci-Resolve
# mutation, reopen, topology, recovery, and protected-state proof.
_LINKED_AUDIO_PRESERVATION_RELEASE_ACTIVE = False


def _authoritative_uid(value: Any) -> str | None:
    if not isinstance(value, str) or not value or value != value.strip():
        return None
    if any(unicodedata.category(character) == "Cc" for character in value):
        return None
    return value


def _item_uid(item: Any) -> str | None:
    getter = getattr(item, "GetUniqueId", None)
    if not callable(getter):
        return None
    try:
        value = getter()
    except Exception:
        return None
    return _authoritative_uid(value)


def _media_uid(item: Any) -> str | None:
    getter = getattr(item, "GetMediaPoolItem", None)
    if not callable(getter):
        return None
    try:
        media_item = getter()
    except Exception:
        return None
    if media_item is None:
        return None
    method = getattr(media_item, "GetMediaId", None)
    if not callable(method):
        return None
    try:
        value = method()
    except Exception:
        return None
    return _authoritative_uid(value)


def _optional_int(item: Any, method_name: str) -> int | None:
    method = getattr(item, method_name, None)
    if not callable(method):
        return None
    try:
        return int(method())
    except Exception:
        return None


def _direct_link_state(item: Any) -> dict[str, Any]:
    """Read direct links from the exact TimelineItem proxy being verified."""
    getter = getattr(item, "GetLinkedItems", None)
    if not callable(getter):
        return {"readable": False, "items": [], "error": "GetLinkedItems unavailable"}
    try:
        linked_items = list(getter() or [])
        snapshots = [
            {
                "timeline_item_id": _item_uid(linked_item),
                "media_pool_id": _media_uid(linked_item),
                "name": str(linked_item.GetName() or ""),
                "start": int(linked_item.GetStart()),
                "end": int(linked_item.GetEnd()),
            }
            for linked_item in linked_items
        ]
    except Exception as exc:
        return {
            "readable": False,
            "items": [],
            "error": f"{exc.__class__.__name__}: {exc}",
        }
    return {
        "readable": True,
        "items": snapshots,
        "error": None,
    }


def _live_row(
    item: Any,
    *,
    track_type: str,
    track_index: int,
    include_direct_link_state: bool = False,
) -> dict[str, Any]:
    media_item = None
    try:
        media_item = item.GetMediaPoolItem()
    except Exception:
        pass
    source_frame_rate = edit_ops._media_pool_item_frame_rate(media_item, fallback_fps=None)
    native_source_end = _optional_int(item, "GetSourceEndFrame")
    row = {
        "track_type": str(track_type),
        "track_index": int(track_index),
        "name": str(item.GetName() or ""),
        "start": int(item.GetStart()),
        "end": int(item.GetEnd()),
        "duration": int(item.GetEnd()) - int(item.GetStart()),
        "timeline_item_id": _item_uid(item),
        "media_pool_id": _media_uid(item),
        "source_in": _optional_int(item, "GetLeftOffset"),
        "source_right_offset": _optional_int(item, "GetRightOffset"),
        "source_start_frame": _optional_int(item, "GetSourceStartFrame"),
        # DaVinci Resolve returns the last rendered source frame here. Plans use
        # half-open source ranges, matching the authoritative timeline snapshot.
        "source_end_frame_exclusive": (
            None if native_source_end is None else native_source_end + 1
        ),
        "source_frame_rate": source_frame_rate,
    }
    if include_direct_link_state:
        row["_direct_link_state"] = _direct_link_state(item)
    return row


def _all_live_rows(conn: Any, *, include_direct_link_state: bool = False) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for track_type in ("video", "audio", "subtitle"):
        track_count = int(conn.timeline.GetTrackCount(track_type) or 0)
        for track_index in range(1, track_count + 1):
            for item in conn.timeline.GetItemListInTrack(track_type, track_index) or []:
                try:
                    rows.append(
                        _live_row(
                            item,
                            track_type=track_type,
                            track_index=track_index,
                            include_direct_link_state=include_direct_link_state,
                        )
                    )
                except Exception as exc:
                    raise APICallFailed(
                        "Timeline state could not be snapshotted completely for verified trim.",
                        details={
                            "track_type": track_type,
                            "track_index": track_index,
                            "error_type": exc.__class__.__name__,
                        },
                    ) from exc
    return sorted(rows, key=lambda row: (row["track_type"], row["track_index"], row["start"], row["end"], row["name"]))


def _all_track_state(conn: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    timeline = conn.timeline
    methods = {
        "name": getattr(timeline, "GetTrackName", None),
        "enabled": getattr(timeline, "GetIsTrackEnabled", None),
        "locked": getattr(timeline, "GetIsTrackLocked", None),
    }
    for track_type in ("video", "audio", "subtitle"):
        track_count = int(timeline.GetTrackCount(track_type) or 0)
        for track_index in range(1, track_count + 1):
            row: dict[str, Any] = {"track_type": track_type, "track_index": track_index}
            for field, method in methods.items():
                if not callable(method):
                    row[field] = None
                    continue
                try:
                    value = method(track_type, track_index)
                except Exception as exc:
                    raise APICallFailed(
                        "Timeline track structure could not be snapshotted completely for verified trim.",
                        details={
                            "track_type": track_type,
                            "track_index": track_index,
                            "field": field,
                            "error_type": exc.__class__.__name__,
                        },
                    ) from exc
                row[field] = str(value or "") if field == "name" else (None if value is None else bool(value))
            rows.append(row)
    return rows


def _row_matches_target(row: dict[str, Any], target: dict[str, Any], *, expected: bool) -> bool:
    if row["track_type"] != target["track_type"] or int(row["track_index"]) != int(target["track_index"]):
        return False
    if target.get("timeline_item_id"):
        if not row.get("timeline_item_id") or str(row["timeline_item_id"]) != str(target["timeline_item_id"]):
            return False
    if row["name"] not in set(target.get("name_candidates") or [target["name"]]):
        return False
    prefix = "new" if expected else "old"
    return int(row["start"]) == int(target[f"{prefix}_start"]) and int(row["end"]) == int(target[f"{prefix}_end"])


def _without_targets(rows: list[dict[str, Any]], targets: list[dict[str, Any]], *, expected: bool) -> list[dict[str, Any]]:
    remaining = list(rows)
    for target in targets:
        matches = [index for index, row in enumerate(remaining) if _row_matches_target(row, target, expected=expected)]
        if len(matches) != 1:
            raise ValidationError(
                "Trim target could not be separated uniquely from protected timeline state.",
                details={"target": target, "expected": expected, "match_count": len(matches)},
            )
        remaining.pop(matches[0])
    return remaining


def _timeline_name(conn: Any) -> str:
    try:
        return str(conn.timeline.GetName() or "")
    except Exception:
        return ""


def _project_name(conn: Any) -> str:
    project = getattr(conn, "project", None)
    getter = getattr(project, "GetName", None) if project is not None else None
    if not callable(getter):
        return ""
    try:
        return str(getter() or "").strip()
    except Exception:
        return ""


def _native_uid(owner: Any) -> str | None:
    getter = getattr(owner, "GetUniqueId", None) if owner is not None else None
    if not callable(getter):
        return None
    try:
        value = getter()
    except Exception:
        return None
    return _authoritative_uid(value)


def _context_identity(conn: Any) -> tuple[str, str]:
    project_uid = _native_uid(getattr(conn, "project", None))
    timeline_uid = _native_uid(getattr(conn, "timeline", None))
    missing = []
    if not project_uid:
        missing.append("project_unique_id")
    if not timeline_uid:
        missing.append("timeline_unique_id")
    if missing:
        raise ValidationError(
            "Verified trim requires authoritative project and timeline identity.",
            details={
                "reason": "edit_trim_context_identity_unavailable",
                "missing": missing,
                "mutation_started": False,
                "retry": "Reconnect to DaVinci Resolve and submit a fresh bounded selector.",
            },
            recoverability="retry_possible",
        )
    return project_uid, timeline_uid


def _select_video_item(
    conn: Any,
    *,
    timeline_name: str | None,
    track_index: int,
    start_frame: str | None,
    current_end_frame: str | None,
    name: str | None,
) -> tuple[Any, Any]:
    if timeline_name:
        timeline_ops.switch_timeline(conn, name=timeline_name)
    if start_frame is None and not name:
        raise ValidationError(
            "Trim selection requires an unambiguous CLIP_NAME/--name and/or --start-frame selector.",
            details={"track_type": "video", "track_index": int(track_index)},
        )
    return timeline_item_duration_db._select_live_item(
        conn,
        track_type="video",
        track_index=track_index,
        start_ref=start_frame,
        current_end_ref=current_end_frame,
        name=name,
    )


def _resolve_linked_audio_items(
    conn: Any,
    video_item: Any,
    direct_link_state: dict[str, Any],
) -> list[tuple[Any, Any, list[str]]]:
    """Resolve every direct link to one exact reciprocal audio occurrence."""
    video_uid = _item_uid(video_item)
    if not video_uid:
        raise ValidationError(
            "Linked trim requires an authoritative video timeline-item identity.",
            details={"reason": "edit_trim_linked_video_identity_unavailable", "mutation_started": False},
        )
    resolved: list[tuple[Any, Any, list[str]]] = []
    seen: set[str] = set()
    for link in direct_link_state["items"]:
        linked_uid = link.get("timeline_item_id")
        if not linked_uid or linked_uid in seen:
            raise ValidationError(
                "Linked trim requires unique authoritative identities for every linked audio item.",
                details={"reason": "edit_trim_linked_audio_identity_unavailable", "linked_item": link, "mutation_started": False},
            )
        matches: list[tuple[Any, Any]] = []
        for track_index in range(1, int(conn.timeline.GetTrackCount("audio") or 0) + 1):
            for item in conn.timeline.GetItemListInTrack("audio", track_index) or []:
                if _item_uid(item) == linked_uid:
                    live_target = timeline_item_duration_db.TimelineItemDurationTarget(
                        item_id=None,
                        track_type="audio",
                        track_index=track_index,
                        name=str(item.GetName() or ""),
                        start=int(item.GetStart()),
                        duration=int(item.GetEnd()) - int(item.GetStart()),
                        end=int(item.GetEnd()),
                    )
                    matches.append((live_target, item))
        if len(matches) != 1:
            raise ValidationError(
                "A directly linked timeline item did not resolve to exactly one audio occurrence.",
                details={"reason": "edit_trim_linked_audio_target_ambiguous", "timeline_item_id": linked_uid, "match_count": len(matches), "mutation_started": False},
            )
        audio_target, audio_item = matches[0]
        reciprocal = _direct_link_state(audio_item)
        reciprocal_ids = {entry.get("timeline_item_id") for entry in reciprocal.get("items", [])}
        if not reciprocal.get("readable") or reciprocal_ids != {video_uid}:
            raise ValidationError(
                "Linked trim requires exact reciprocal video/audio topology.",
                details={"reason": "edit_trim_link_topology_not_reciprocal", "video_timeline_item_id": video_uid, "audio_timeline_item_id": linked_uid, "reciprocal": reciprocal, "mutation_started": False},
            )
        resolved.append((audio_target, audio_item, sorted(value for value in reciprocal_ids if value)))
        seen.add(linked_uid)
    return resolved


def _preflight(
    conn: Any,
    *,
    timeline_name: str | None,
    track_index: int,
    start_frame: str | None,
    current_end_frame: str | None,
    name: str | None,
    head_frames: int,
    tail_frames: int,
    linked_audio_mode: str,
) -> dict[str, Any]:
    target, video_item = _select_video_item(
        conn,
        timeline_name=timeline_name,
        track_index=track_index,
        start_frame=start_frame,
        current_end_frame=current_end_frame,
        name=name,
    )
    project_uid, timeline_uid = _context_identity(conn)
    media_type = timeline_item_duration_db.media_pool_item_type(video_item)
    if media_type and media_type.casefold() == "multicam":
        raise ValidationError(
            "Verified trim does not support a multicam timeline item.",
            details={
                "reason": "edit_trim_multicam_unsupported",
                "media_type": media_type,
                "track_type": "video",
                "track_index": int(track_index),
                "name": str(target.name),
                "start": int(target.start),
                "end": int(target.end),
                "mutation_started": False,
                "retry": "Flatten or replace the multicam occurrence with an ordinary video item, then submit a fresh bounded selector.",
            },
            recoverability="retry_possible",
        )
    if head_frames + tail_frames >= int(target.duration):
        raise ValidationError(
            "Trim must leave at least one frame of the selected video item.",
            details={"duration_frames": target.duration, "head_frames": head_frames, "tail_frames": tail_frames},
        )
    direct_link_state = _direct_link_state(video_item) if linked_audio_mode == "preserve" else None
    if direct_link_state is not None and not direct_link_state["readable"]:
        raise APICallFailed(
            "Direct link state could not be read before verified trim.",
            details={
                "reason": "edit_trim_direct_link_state_unreadable",
                "track_type": "video",
                "track_index": int(track_index),
                "name": str(target.name),
                "start": int(target.start),
                "end": int(target.end),
                "error": direct_link_state.get("error"),
                "mutation_started": False,
            },
        )
    if direct_link_state is not None and direct_link_state["items"] and not _LINKED_AUDIO_PRESERVATION_RELEASE_ACTIVE:
        raise ValidationError(
            "Linked-audio-preserving trim is release-gated pending real DaVinci Resolve proof.",
            details={
                "reason": "edit_trim_linked_audio_preservation_release_gated",
                "required_proof": [
                    "real_mutation",
                    "project_reopen",
                    "exact_link_topology",
                    "protected_state",
                    "checkpoint_recovery",
                ],
                "mutation_started": False,
            },
        )
    targets: list[dict[str, Any]] = []
    video_link_ids = sorted(
        entry["timeline_item_id"]
        for entry in (direct_link_state or {}).get("items", [])
        if entry.get("timeline_item_id")
    )
    live_targets = [(target, video_item, video_link_ids)]
    if direct_link_state is not None and direct_link_state["items"]:
        live_targets.extend(_resolve_linked_audio_items(conn, video_item, direct_link_state))
        if any(
            int(linked_target.start) != int(target.start) or int(linked_target.end) != int(target.end)
            for linked_target, _, _ in live_targets[1:]
        ):
            raise ValidationError(
                "Linked trim requires video and audio occurrences with identical record ranges.",
                details={"reason": "edit_trim_linked_record_ranges_diverged", "mutation_started": False},
            )
    for live_target, item, expected_link_item_ids in live_targets:
        row = _live_row(item, track_type=live_target.track_type, track_index=live_target.track_index)
        old_source_in = row.get("source_in")
        old_source_start = row.get("source_start_frame")
        old_source_end = row.get("source_end_frame_exclusive")
        source_frame_rate = row.get("source_frame_rate")
        if old_source_start is None or old_source_end is None or source_frame_rate is None:
            raise APICallFailed(
                "Exact source-domain trim planning is unavailable for the selected timeline item.",
                details={
                    "reason": "edit_trim_source_plan_unavailable",
                    "track_type": live_target.track_type,
                    "track_index": live_target.track_index,
                    "name": live_target.name,
                    "source_start_frame": old_source_start,
                    "source_end_frame_exclusive": old_source_end,
                    "source_frame_rate": source_frame_rate,
                    "mutation_started": False,
                },
            )
        head_source_frames = edit_ops._timeline_to_source_frame_count(
            head_frames,
            source_fps=float(source_frame_rate),
            timeline_fps=float(conn.fps),
        )
        tail_source_frames = edit_ops._timeline_to_source_frame_count(
            tail_frames,
            source_fps=float(source_frame_rate),
            timeline_fps=float(conn.fps),
        )
        new_source_start = int(old_source_start) + int(head_source_frames)
        new_source_end = int(old_source_end) - int(tail_source_frames)
        if new_source_end <= new_source_start:
            raise ValidationError(
                "Trim must leave a non-empty source range.",
                details={
                    "reason": "edit_trim_source_range_empty",
                    "old_source_start_frame": old_source_start,
                    "old_source_end_frame_exclusive": old_source_end,
                    "head_source_frames": head_source_frames,
                    "tail_source_frames": tail_source_frames,
                    "mutation_started": False,
                },
            )
        targets.append(
            {
                "track_type": live_target.track_type,
                "track_index": live_target.track_index,
                "name": live_target.name,
                "name_candidates": sorted({live_target.name, *live_target.aliases} - {""}),
                "timeline_item_id": row.get("timeline_item_id"),
                "media_pool_id": row.get("media_pool_id"),
                "old_start": live_target.start,
                "old_end": live_target.end,
                "old_duration": live_target.duration,
                "old_source_in": old_source_in,
                "old_source_right_offset": row.get("source_right_offset"),
                "new_start": live_target.start + head_frames,
                "new_end": live_target.end - tail_frames,
                "new_duration": live_target.duration - head_frames - tail_frames,
                "new_source_in": None if old_source_in is None else int(old_source_in) + head_frames,
                "new_source_right_offset": (
                    None
                    if row.get("source_right_offset") is None
                    else int(row["source_right_offset"]) + tail_frames
                ),
                "source_frame_rate": float(source_frame_rate),
                "old_source_start_frame": int(old_source_start),
                "old_source_end_frame_exclusive": int(old_source_end),
                "new_source_start_frame": new_source_start,
                "new_source_end_frame_exclusive": new_source_end,
                "expected_link_item_ids": expected_link_item_ids,
            }
        )
    targets.sort(
        key=lambda item: (
            0 if item["track_type"] == "video" else 1,
            int(item["track_index"]),
            int(item["old_start"]),
            str(item["name"]),
            str(item.get("timeline_item_id") or ""),
        )
    )
    all_rows = _all_live_rows(conn)
    protected_rows = _without_targets(all_rows, targets, expected=False)
    return {
        "project_name": _project_name(conn),
        "project_uid": project_uid,
        "timeline_name": _timeline_name(conn),
        "timeline_uid": timeline_uid,
        "fps": float(conn.fps),
        "head_frames": int(head_frames),
        "tail_frames": int(tail_frames),
        "linked_audio_mode": linked_audio_mode,
        "targets": targets,
        "protected_rows": protected_rows,
        "track_counts": {
            "video": int(conn.timeline.GetTrackCount("video") or 0),
            "audio": int(conn.timeline.GetTrackCount("audio") or 0),
            "subtitle": int(conn.timeline.GetTrackCount("subtitle") or 0),
        },
        "track_state": _all_track_state(conn),
    }


def _validate_plan_still_current(conn: Any, plan: dict[str, Any]) -> None:
    refresh = getattr(conn, "refresh", None)
    if not callable(refresh):
        raise ValidationError(
            "Live DaVinci Resolve state cannot be refreshed before verified trim.",
            details={
                "reason": "edit_trim_refresh_unavailable_before_close",
                "mutation_started": False,
                "retry": "Reconnect to DaVinci Resolve and submit a fresh bounded selector.",
            },
            recoverability="retry_possible",
        )
    try:
        refresh()
    except Exception as exc:
        raise ValidationError(
            "Live DaVinci Resolve state could not be refreshed before verified trim.",
            details={
                "reason": "edit_trim_refresh_failed_before_close",
                "error_type": exc.__class__.__name__,
                "mutation_started": False,
                "retry": "Reconnect to DaVinci Resolve and submit a fresh bounded selector.",
            },
            recoverability="retry_possible",
        ) from exc

    try:
        actual_project_uid, actual_timeline_uid = _context_identity(conn)
    except ValidationError as exc:
        raise ValidationError(
            "Authoritative project or timeline identity could not be re-established before verified trim.",
            details={
                "reason": "edit_trim_context_identity_unavailable_before_close",
                "missing": exc.details.get("missing", []),
                "mutation_started": False,
                "retry": "Reconnect to DaVinci Resolve and submit a fresh bounded selector.",
            },
            recoverability="retry_possible",
        ) from exc
    changed_identities = []
    if actual_project_uid != str(plan["project_uid"]):
        changed_identities.append("project_unique_id")
    if actual_timeline_uid != str(plan["timeline_uid"]):
        changed_identities.append("timeline_unique_id")
    if changed_identities:
        raise ValidationError(
            "The active project or timeline identity changed before verified trim.",
            details={
                "reason": "edit_trim_context_identity_changed_before_close",
                "changed_identities": changed_identities,
                "expected_project_name": str(plan.get("project_name") or "") or None,
                "actual_project_name": _project_name(conn) or None,
                "expected_timeline_name": str(plan.get("timeline_name") or "") or None,
                "actual_timeline_name": _timeline_name(conn) or None,
                "mutation_started": False,
                "retry": "Open the intended project and timeline, then submit a fresh bounded selector.",
            },
            recoverability="retry_possible",
        )

    actual_project_name = _project_name(conn)
    expected_project_name = str(plan.get("project_name") or "").strip()
    if not actual_project_name or not expected_project_name or actual_project_name != expected_project_name:
        raise ValidationError(
            "The active project changed or could not be re-established before verified trim.",
            details={
                "reason": "edit_trim_project_changed_before_close",
                "expected_project_name": expected_project_name or None,
                "actual_project_name": actual_project_name or None,
                "mutation_started": False,
                "retry": "Open the intended saved project and submit a fresh bounded selector.",
            },
            recoverability="retry_possible",
        )

    selector = plan["selector"]
    if _timeline_name(conn) != str(plan["timeline_name"]):
        raise ValidationError(
            "The active timeline changed while waiting for the project mutation lock.",
            details={
                "reason": "edit_trim_timeline_changed_before_close",
                "mutation_started": False,
                "retry": "Re-select the intended timeline and submit a fresh bounded selector.",
            },
            recoverability="retry_possible",
        )
    current = _preflight(
        conn,
        timeline_name=None,
        track_index=int(selector["track_index"]),
        start_frame=selector.get("start_frame"),
        current_end_frame=selector.get("current_end_frame"),
        name=selector.get("name"),
        head_frames=int(plan["head_frames"]),
        tail_frames=int(plan["tail_frames"]),
        linked_audio_mode=str(plan["linked_audio_mode"]),
    )
    compared_fields = ("timeline_name", "targets", "protected_rows", "track_counts", "track_state")
    changed = [field for field in compared_fields if current.get(field) != plan.get(field)]
    try:
        actual_fps = float(conn.fps)
    except (TypeError, ValueError, AttributeError):
        actual_fps = math.nan
    if "fps" in plan and (not math.isfinite(actual_fps) or actual_fps <= 0 or actual_fps != float(plan["fps"])):
        changed.append("timeline_frame_rate")
    if changed:
        raise ValidationError(
            "Trim target or protected timeline state changed while waiting for the project mutation lock.",
            details={
                "reason": "edit_trim_state_changed_before_close",
                "changed_sections": changed,
                "mutation_started": False,
                "retry": "Re-read the intended timeline item and submit a fresh bounded selector.",
            },
            recoverability="retry_possible",
        )


def _pre_close_validator_for_plan(plan: dict[str, Any]):
    def _validator(conn: Any, _session: db_session.DiskDbMutationSession) -> None:
        _validate_plan_still_current(conn, plan)

    return _validator


def _target_ref(target: dict[str, Any]) -> timeline_item_duration_db.TimelineItemDurationTarget:
    return timeline_item_duration_db.TimelineItemDurationTarget(
        item_id=None,
        track_type=str(target["track_type"]),
        track_index=int(target["track_index"]),
        name=str(target["name"]),
        start=int(target["old_start"]),
        duration=int(target["old_duration"]),
        end=int(target["old_end"]),
        aliases=tuple(target.get("name_candidates") or ()),
    )


def _decorate_update(update: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
    return {
        **update,
        "old_start": int(target["old_start"]),
        "old_end": int(target["old_end"]),
        "old_duration": int(target["old_duration"]),
        "old_in": target.get("old_source_in"),
        "new_start": int(target["new_start"]),
        "new_end": int(target["new_end"]),
        "new_duration": int(target["new_duration"]),
        "new_in": target.get("new_source_in"),
        "new_source_right_offset": target.get("new_source_right_offset"),
        "source_frame_rate": target.get("source_frame_rate"),
        "old_source_start_frame": target.get("old_source_start_frame"),
        "old_source_end_frame_exclusive": target.get("old_source_end_frame_exclusive"),
        "new_source_start_frame": target.get("new_source_start_frame"),
        "new_source_end_frame_exclusive": target.get("new_source_end_frame_exclusive"),
        "timeline_item_id": target.get("timeline_item_id"),
        "media_pool_id": target.get("media_pool_id"),
        "expected_link_item_ids": list(target.get("expected_link_item_ids") or []),
        "track_type": target["track_type"],
        "track_index": int(target["track_index"]),
        "selector": {
            "track_type": target["track_type"],
            "track_index": int(target["track_index"]),
            "name": target["name"],
            "start": int(target["old_start"]),
            "end": int(target["old_end"]),
        },
        "readback_name_candidates": list(target.get("name_candidates") or []),
    }


def _writer_for_plan(plan: dict[str, Any]):
    def _writer(_connection: sqlite3.Connection, cursor: sqlite3.Cursor, _session: db_session.DiskDbMutationSession) -> dict[str, Any]:
        updated_items: list[dict[str, Any]] = []
        for target in plan["targets"]:
            ref = _target_ref(target)
            row = timeline_item_duration_db._fetch_db_row_for_live_target(
                cursor,
                target=ref,
                timeline_name=str(plan["timeline_name"]),
            )
            transition_conflicts = timeline_item_duration_db._transition_conflicts_for_item_range(
                cursor,
                target_row=row,
                start=int(target["old_start"]),
                end=int(target["old_end"]),
            )
            if transition_conflicts:
                raise ValidationError(
                    "Linked video/audio trim does not support a target with an overlapping transition row.",
                    details={
                        "target": target,
                        "transition_conflicts": transition_conflicts,
                        "precondition": "transition_adjacent_video_trim_blocked",
                        "recovery": "Remove or recreate the transition around the trim, then retry the bounded trim.",
                    },
                )
            if int(plan["head_frames"]):
                update = timeline_item_duration_db._apply_head_trim_update(
                    cursor,
                    target_row=row,
                    new_start=int(target["new_start"]),
                    allow_overlap=False,
                    fps=float(plan["fps"]),
                    allow_linked_audio_only=True,
                    include_linked_video=False,
                    preserve_source_timemap=True,
                    timeline_name=str(plan["timeline_name"]),
                )
                row = timeline_item_duration_db._fetch_db_row_by_item_id(
                    cursor,
                    item_id=str(update["item_id"]),
                    timeline_name=str(plan["timeline_name"]),
                    track_type=str(target["track_type"]),
                    track_index=int(target["track_index"]),
                )
            if int(plan["tail_frames"]):
                update = timeline_item_duration_db._apply_duration_update(
                    cursor,
                    target_row=row,
                    new_duration=int(target["new_duration"]),
                    new_end=int(target["new_end"]),
                    allow_overlap=False,
                    fps=float(plan["fps"]),
                    allow_linked_audio_only=True,
                    include_linked_video=False,
                    preserve_source_timemap=True,
                    timeline_name=str(plan["timeline_name"]),
                )
            updated_items.append(_decorate_update(update, target))
        return {
            "action": "edit.trim",
            "timeline_name": plan["timeline_name"],
            "fps": float(plan["fps"]),
            "head_trimmed_frames": int(plan["head_frames"]),
            "tail_trimmed_frames": int(plan["tail_frames"]),
            "linked_audio_mode": plan["linked_audio_mode"],
            "updated_items": updated_items,
            "protected_rows": plan["protected_rows"],
            "track_counts": plan["track_counts"],
            "track_state": plan.get("track_state", []),
        }
    return _writer


def _verify_db_fields(session: Any, updated_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    connection = sqlite3.connect(session.project_db_path, timeout=5.0)
    try:
        cursor = connection.cursor()
        for item in updated_items:
            row = cursor.execute(
                'SELECT Start, Duration, "In" FROM Sm2TiItem WHERE Sm2TiItem_id = ?',
                (item.get("item_id"),),
            ).fetchone()
            actual = None if row is None else {"start": int(str(row[0]).split("|", 1)[0]), "duration": int(str(row[1]).split("|", 1)[0]), "in": int(str(row[2] or 0).split("|", 1)[0])}
            expected = {"start": int(item["new_start"]), "duration": int(item["new_duration"]), "in": int(item.get("new_in") or 0)}
            checks.append({"name": "db_target_fields", "ok": actual == expected, "item_id": item.get("item_id"), "expected": expected, "actual": actual})
    finally:
        connection.close()
    return checks


def _verify_trim(fresh_conn: Any, mutation_result: dict[str, Any], session: Any) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    expected_project_name = str(getattr(session, "project_name", "") or "")
    project = getattr(fresh_conn, "project", None)
    actual_project_name = ""
    if project is not None:
        getter = getattr(project, "GetName", None)
        if callable(getter):
            try:
                actual_project_name = str(getter() or "")
            except Exception:
                actual_project_name = ""
    if expected_project_name:
        checks.append(
            {
                "name": "intended_project_restored",
                "ok": actual_project_name == expected_project_name,
                "expected": expected_project_name,
                "actual": actual_project_name,
            }
        )
    actual_timeline_name = _timeline_name(fresh_conn)
    checks.append(
        {
            "name": "intended_timeline_restored",
            "ok": actual_timeline_name == str(mutation_result["timeline_name"]),
            "expected": mutation_result["timeline_name"],
            "actual": actual_timeline_name,
        }
    )
    actual_counts = {
        "video": int(fresh_conn.timeline.GetTrackCount("video") or 0),
        "audio": int(fresh_conn.timeline.GetTrackCount("audio") or 0),
        "subtitle": int(fresh_conn.timeline.GetTrackCount("subtitle") or 0),
    }
    checks.append({"name": "track_counts_unchanged", "ok": actual_counts == mutation_result["track_counts"], "expected": mutation_result["track_counts"], "actual": actual_counts})
    actual_track_state = _all_track_state(fresh_conn)
    checks.append(
        {
            "name": "track_structure_unchanged",
            "ok": actual_track_state == mutation_result["track_state"],
            "expected": mutation_result["track_state"],
            "actual": actual_track_state,
        }
    )
    verify_topology = mutation_result["linked_audio_mode"] == "preserve"
    all_rows = _all_live_rows(fresh_conn, include_direct_link_state=verify_topology)
    try:
        protected_after = _without_targets(all_rows, mutation_result["updated_items"], expected=True)
        protected_after = [
            {key: value for key, value in row.items() if key != "_direct_link_state"}
            for row in protected_after
        ]
    except ValidationError as exc:
        protected_after = []
        checks.append({"name": "target_unique_after_reopen", "ok": False, "error": str(exc), "details": exc.details})
    else:
        checks.append({"name": "target_unique_after_reopen", "ok": True})
    checks.append(
        {
            "name": "protected_timeline_state_unchanged",
            "ok": protected_after == mutation_result["protected_rows"],
            "expected": mutation_result["protected_rows"],
            "actual": protected_after,
        }
    )
    for expected in mutation_result["updated_items"]:
        matches = [row for row in all_rows if _row_matches_target(row, expected, expected=True)]
        ok = len(matches) == 1
        actual = matches[0] if ok else None
        if ok and expected.get("timeline_item_id"):
            ok = bool(actual.get("timeline_item_id")) and actual["timeline_item_id"] == expected["timeline_item_id"]
        if ok and expected.get("media_pool_id"):
            ok = bool(actual.get("media_pool_id")) and actual["media_pool_id"] == expected["media_pool_id"]
        if ok and expected.get("new_in") is not None:
            ok = actual.get("source_in") is not None and int(actual["source_in"]) == int(expected["new_in"])
        if ok and expected.get("new_source_right_offset") is not None:
            ok = (
                actual.get("source_right_offset") is not None
                and int(actual["source_right_offset"]) == int(expected["new_source_right_offset"])
            )
        if ok:
            source_rate = float(expected["source_frame_rate"])
            timeline_rate = float(mutation_result["fps"])
            source_end_tolerance = (
                0
                if math.isclose(source_rate, timeline_rate, rel_tol=0.0, abs_tol=0.000001)
                else max(1, int(math.ceil(source_rate / timeline_rate)))
            )
            ok = (
                actual.get("source_start_frame") is not None
                and int(actual["source_start_frame"]) == int(expected["new_source_start_frame"])
                and actual.get("source_end_frame_exclusive") is not None
                and abs(
                    int(actual["source_end_frame_exclusive"])
                    - int(expected["new_source_end_frame_exclusive"])
                ) <= source_end_tolerance
                and actual.get("source_frame_rate") is not None
                and math.isclose(
                    float(actual["source_frame_rate"]),
                    float(expected["source_frame_rate"]),
                    rel_tol=0.0,
                    abs_tol=0.000001,
                )
            )
        if ok and verify_topology:
            link_state = actual.get("_direct_link_state") or {}
            link_items = link_state.get("items", [])
            actual_link_ids = sorted(entry.get("timeline_item_id") for entry in link_items if entry.get("timeline_item_id"))
            expected_link_ids = sorted(expected.get("expected_link_item_ids") or [])
            topology_ok = bool(link_state.get("readable")) and len(actual_link_ids) == len(link_items) and actual_link_ids == expected_link_ids
            checks.append({"name": "reciprocal_link_topology_preserved", "ok": topology_ok, "expected_item_ids": expected_link_ids, "actual_item_ids": actual_link_ids})
        public_actual = (
            {key: value for key, value in actual.items() if key != "_direct_link_state"}
            if actual is not None
            else None
        )
        checks.append({"name": "live_target_readback", "ok": ok, "expected": expected, "actual": public_actual, "match_count": len(matches)})
    checks.extend(_verify_db_fields(session, mutation_result["updated_items"]))
    verification = {"status": "verified" if checks and all(check.get("ok") for check in checks) else "failed", "checks": checks}
    if verification["status"] != "verified":
        raise APICallFailed(
            "Video trim readback failed after DaVinci Resolve reopened the project.",
            details={"reason": "edit_trim_post_reopen_verification_failed", "verification": verification},
            recoverability="automatic",
        )
    return verification


def _semantic_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            key: item[key]
            for key in (
                "track_type",
                "track_index",
                "name",
                "old_start",
                "old_end",
                "old_duration",
                "new_start",
                "new_end",
                "new_duration",
                "source_frame_rate",
                "old_source_start_frame",
                "old_source_end_frame_exclusive",
                "new_source_start_frame",
                "new_source_end_frame_exclusive",
            )
            if key in item
        }
        for item in items
    ]


def _semantic_result(result: dict[str, Any]) -> dict[str, Any]:
    """Project the internal mutation receipt onto the public trim contract."""
    updated_items = _semantic_items(result.get("updated_items", []))
    verification = result.get("verification") or {}
    public_checks: list[dict[str, Any]] = []
    for check in verification.get("checks", []):
        name = "durable_target_state" if check.get("name") == "db_target_fields" else check.get("name")
        projected = {"name": name, "ok": bool(check.get("ok"))}
        if name in {"intended_project_restored", "intended_timeline_restored", "track_counts_unchanged"}:
            projected.update({"expected": check.get("expected"), "actual": check.get("actual")})
        if "match_count" in check:
            projected["match_count"] = check["match_count"]
        if "mode" in check:
            projected["mode"] = check["mode"]
        public_checks.append(projected)
    lifecycle_steps = [
        step
        for step in result.get("steps", [])
        if step in {"save_project", "close_project", "reopen_project", "restore_timeline", "verify"}
    ]
    return {
        "action": "edit.trim",
        "changed": True,
        "dry_run": False,
        "timeline_name": result.get("timeline_name"),
        "head_trimmed_frames": int(result.get("head_trimmed_frames") or 0),
        "tail_trimmed_frames": int(result.get("tail_trimmed_frames") or 0),
        "linked_audio_mode": result.get("linked_audio_mode"),
        "updated_items": updated_items,
        "protected_item_count": len(result.get("protected_rows") or []),
        "lifecycle_steps": lifecycle_steps,
        "verification": {"status": verification.get("status"), "checks": public_checks},
        "recovery": {
            "status": "checkpoint_created",
            "manual_recovery_required": False,
        },
    }


def trim_video_item(
    conn: Any,
    *,
    timeline_name: str | None = None,
    track_index: int = 1,
    start_frame: str | None = None,
    current_end_frame: str | None = None,
    name: str | None = None,
    head_seconds: float = 0.0,
    tail_seconds: float = 0.0,
    linked_audio_mode: str = "preserve",
    dry_run: bool = False,
) -> dict[str, Any]:
    if linked_audio_mode not in {"preserve", "exclude"}:
        raise ValidationError(
            "Linked audio mode must be 'preserve' or 'exclude'.",
            details={"linked_audio_mode": linked_audio_mode, "allowed": ["preserve", "exclude"]},
        )
    if head_seconds < 0 or tail_seconds < 0:
        raise ValidationError("Trim head and tail must be non-negative.", details={"head": head_seconds, "tail": tail_seconds})
    if head_seconds == 0.0 and tail_seconds == 0.0:
        raise ValidationError("Specify --head and/or --tail.", details={"head": head_seconds, "tail": tail_seconds})
    head_frames = int(seconds_to_frames(head_seconds, conn.fps))
    tail_frames = int(seconds_to_frames(tail_seconds, conn.fps))
    if head_seconds > 0 and head_frames <= 0 or tail_seconds > 0 and tail_frames <= 0:
        raise ValidationError(
            "Each non-zero trim duration must resolve to at least one frame at the timeline frame rate.",
            details={"fps": conn.fps, "head_seconds": head_seconds, "tail_seconds": tail_seconds, "head_frames": head_frames, "tail_frames": tail_frames},
        )
    plan = _preflight(
        conn,
        timeline_name=timeline_name,
        track_index=track_index,
        start_frame=start_frame,
        current_end_frame=current_end_frame,
        name=name,
        head_frames=head_frames,
        tail_frames=tail_frames,
        linked_audio_mode=linked_audio_mode,
    )
    plan["fps"] = float(conn.fps)
    plan["selector"] = {
        "track_index": int(track_index),
        "start_frame": start_frame,
        "current_end_frame": current_end_frame,
        "name": name,
    }
    if linked_audio_mode == "exclude":
        # Linked audio is protected state in this mode and must remain byte-for-byte equivalent in API readback.
        plan["targets"] = [target for target in plan["targets"] if target["track_type"] == "video"]
        all_rows = _all_live_rows(conn)
        plan["protected_rows"] = _without_targets(all_rows, plan["targets"], expected=False)
    if dry_run:
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        return {
            "action": "edit.trim",
            "changed": False,
            "dry_run": True,
            "timeline_name": plan["timeline_name"],
            "head_trimmed_frames": head_frames,
            "tail_trimmed_frames": tail_frames,
            "linked_audio_mode": linked_audio_mode,
            "targets": _semantic_items(plan["targets"]),
            "protected_item_count": len(plan["protected_rows"]),
            "verification": {"status": "not_requested"},
            "recovery": {"status": "not_applicable", "mutation_possible": False},
        }
    result = db_session.execute_sqlite_disk_db_mutation(
        conn,
        context="DB-backed video timeline item trim",
        writer=_writer_for_plan(plan),
        verifier=_verify_trim,
        pre_close_validator=_pre_close_validator_for_plan(plan),
        allow_project_name_inference=True,
    )
    verification = result.get("verification") if isinstance(result, dict) else None
    if not isinstance(verification, dict) or verification.get("status") != "verified":
        raise APICallFailed(
            "Video trim did not verify after DaVinci Resolve reopened the project.",
            details={"mutation": result, "verification": verification},
            recoverability="manual",
        )
    return _semantic_result(result)
