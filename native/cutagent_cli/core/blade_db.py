"""DB-backed timeline blade helpers."""

from __future__ import annotations

from dataclasses import asdict
import re
import sqlite3
import uuid
from typing import Any

from ..errors import ClipNotFound, SdkMutationStaleRevision, ValidationError
from ..utils.time_ref import parse_record_frame
from ..utils.timecode import frames_to_timecode
from . import clip_effects_db, db_timeline_selection
from .db_session import next_db_index, rebuild_track_item_indices
from .db_timeline_rows import find_ti_item_row, insert_row, update_row
from .db_timeline_selection import LiveItemRef


BLADE_ACTION = "edit.blade"
_BLADE_TRACK_TYPES = {"all", "video", "audio"}
_DB_TYPE_BY_TRACK_TYPE = {
    "video": "Sm2TiVideoClip",
    "audio": "Sm2TiAudioClip",
}


def normalize_blade_track_type(track_type: str | None) -> str:
    normalized = str(track_type or "all").strip().lower()
    if normalized not in _BLADE_TRACK_TYPES:
        raise ValidationError(
            "Track type must be one of: all, video, audio.",
            details={
                "option": "--track-type",
                "value": track_type,
                "supported_track_types": sorted(_BLADE_TRACK_TYPES),
            },
            recoverability="not_applicable",
        )
    return normalized


def normalize_blade_track_index(track_index: object | None) -> int:
    try:
        value = int(track_index or 0)
    except Exception as exc:
        raise ValidationError(
            "Track index must be an integer.",
            details={"option": "--track", "value": track_index},
            recoverability="not_applicable",
        ) from exc
    if value < 0:
        raise ValidationError(
            "Track index must be 0 or greater.",
            details={"option": "--track", "value": track_index},
            recoverability="not_applicable",
        )
    return value


def playhead_at_reference(conn: Any) -> str:
    tc = conn.timeline.GetCurrentTimecode()
    if not tc:
        raise ClipNotFound("Cannot read playhead position.")
    from ..utils.timecode import seconds_to_frames, timecode_to_seconds

    absolute_frame = seconds_to_frames(timecode_to_seconds(tc, conn.fps), conn.fps)
    try:
        start_frame = int(conn.timeline.GetStartFrame())
    except Exception:
        start_frame = int(getattr(conn, "start_frame", 0) or 0)
    return f"{max(0, int(absolute_frame) - int(start_frame))}f"


def _track_types(track_type: str) -> list[str]:
    return ["video", "audio"] if track_type == "all" else [track_type]


def _track_count(conn: Any, track_type: str) -> int:
    try:
        return int(conn.timeline.GetTrackCount(track_type) or 0)
    except Exception:
        return 0


def _track_indices(conn: Any, *, track_type: str, track_index: int) -> list[int]:
    count = _track_count(conn, track_type)
    if track_index:
        if track_index > count:
            raise ValidationError(
                "Track index is out of range.",
                details={"track_type": track_type, "track_index": track_index, "track_count": count},
            )
        return [track_index]
    return list(range(1, count + 1))


def _track_locked(conn: Any, *, track_type: str, track_index: int, respect_locks: bool) -> bool:
    if not respect_locks:
        return False
    getter = getattr(conn.timeline, "GetIsTrackLocked", None)
    if not callable(getter):
        raise ValidationError(
            "Track lock readback is unavailable; use --ignore-locks to blade without lock protection.",
            details={"track_type": track_type, "track_index": track_index},
        )
    try:
        return bool(getter(track_type, track_index))
    except Exception as exc:
        raise ValidationError(
            "Track lock readback failed; use --ignore-locks to blade without lock protection.",
            details={"track_type": track_type, "track_index": track_index, "error": str(exc)},
        ) from exc


def _candidate_timeline_frames(conn: Any, record_frame: int) -> set[int]:
    frames = {int(record_frame)}
    try:
        start_frame = int(conn.timeline.GetStartFrame())
    except Exception:
        start_frame = int(getattr(conn, "start_frame", 0) or 0)
    if start_frame:
        frames.add(int(record_frame) - start_frame)
    return frames


def _item_cut_frame(conn: Any, item: LiveItemRef, *, record_frame: int) -> int | None:
    for frame in sorted(_candidate_timeline_frames(conn, int(record_frame)), reverse=True):
        if int(item.start) < int(frame) < int(item.end):
            return int(frame)
    return None


def _pre_track_counts(conn: Any, track_types: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for track_type in track_types:
        for index in range(1, _track_count(conn, track_type) + 1):
            try:
                counts[f"{track_type}:{index}"] = len(conn.timeline.GetItemListInTrack(track_type, index) or [])
            except Exception:
                counts[f"{track_type}:{index}"] = 0
    return counts


def require_exact_sdk_blade_targets(conn: Any, expected_targets: object) -> list[dict[str, Any]]:
    """Revalidate every private blade target against the live timeline before DB preflight."""
    if not isinstance(expected_targets, list) or not expected_targets:
        raise ValidationError("The exact SDK blade target precondition must be a non-empty array.")
    normalized: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for raw in expected_targets:
        try:
            item_id = str(raw["id"] or "")
            track_type = str(raw["trackType"])
            track_index = int(raw["trackIndex"])
            record_start = int(raw["recordStartFrame"])
            record_end = int(raw["recordEndFrame"])
            name = str(raw["name"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValidationError("The exact SDK blade target precondition is malformed.") from exc
        if (
            not item_id
            or item_id in seen_ids
            or track_type not in {"video", "audio"}
            or track_index < 1
            or record_end <= record_start
        ):
            raise ValidationError("The exact SDK blade target precondition is malformed.")
        seen_ids.add(item_id)
        items = conn.timeline.GetItemListInTrack(track_type, track_index) or []
        matches = []
        for item in items:
            try:
                live_id = item.GetUniqueId()
                live_start = int(item.GetStart())
                live_end = int(item.GetEnd())
                live_name = str(item.GetName() or "")
            except Exception:
                continue
            if not isinstance(live_id, str) or live_id != item_id:
                continue
            start_candidates = _candidate_timeline_frames(conn, record_start)
            end_candidates = _candidate_timeline_frames(conn, record_end)
            if live_start in start_candidates and live_end in end_candidates and live_name == name:
                matches.append(item)
        if len(matches) != 1:
            raise SdkMutationStaleRevision(
                "An exact SDK blade target changed before CutAgent CLI preflight.",
                details={
                    "track_type": track_type,
                    "track_index": track_index,
                    "record_start_frame": record_start,
                    "record_end_frame": record_end,
                    "name": name,
                },
            )
        normalized.append({
            "id": item_id,
            "track_type": track_type,
            "track_index": track_index,
            "record_start_frame": record_start,
            "record_end_frame": record_end,
            "name": name,
        })
    return normalized


def require_blade_plans_match_exact_targets(
    conn: Any,
    plans: list[dict[str, Any]],
    expected_targets: list[dict[str, Any]],
) -> None:
    expected = {
        (
            target["track_type"],
            target["track_index"],
            target["name"],
            frozenset(_candidate_timeline_frames(conn, target["record_start_frame"])),
            frozenset(_candidate_timeline_frames(conn, target["record_end_frame"])),
        )
        for target in expected_targets
    }
    actual = {
        (
            str(target["track_type"]),
            int(target["track_index"]),
            str(target.get("name") or ""),
            frozenset({int(target["start"])}),
            frozenset({int(target["start"]) + int(target["duration"])}),
        )
        for plan in plans
        for target in (plan.get("targets") or [])
    }
    matched = all(any(
        expected_type == actual_type
        and expected_index == actual_index
        and expected_name == actual_name
        and bool(expected_starts.intersection(actual_starts))
        and bool(expected_ends.intersection(actual_ends))
        for actual_type, actual_index, actual_name, actual_starts, actual_ends in actual
    ) for expected_type, expected_index, expected_name, expected_starts, expected_ends in expected)
    if not matched or len(actual) != len(expected):
        raise SdkMutationStaleRevision("The exact SDK blade target set changed during CutAgent CLI preflight.")


def _entry_value(entry: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in entry and entry[key] is not None:
            return entry[key]
    return default


def plan_blade_entry(
    conn: Any,
    entry: dict[str, Any],
    *,
    default_at: str | None,
    default_track_type: str = "all",
    default_track_index: int = 0,
    respect_locks: bool = True,
) -> dict[str, Any]:
    track_type = normalize_blade_track_type(_entry_value(entry, "track_type", "track-type", default=default_track_type))
    track_index = normalize_blade_track_index(_entry_value(entry, "track", "track_index", "track-index", default=default_track_index))
    at_value = _entry_value(entry, "at", default=default_at)
    if at_value in (None, ""):
        at_value = playhead_at_reference(conn)
    at_ref = str(at_value)
    record_frame = parse_record_frame(at_ref, conn.fps, conn.start_frame)
    wanted_track_types = _track_types(track_type)
    all_live_items = {
        current_type: db_timeline_selection._read_live_items(conn, track_type=current_type)
        for current_type in wanted_track_types
    }

    targets: list[dict[str, Any]] = []
    skipped_locked: list[dict[str, Any]] = []
    scanned_tracks: list[dict[str, Any]] = []
    for current_type in wanted_track_types:
        for current_index in _track_indices(conn, track_type=current_type, track_index=track_index):
            locked = _track_locked(
                conn,
                track_type=current_type,
                track_index=current_index,
                respect_locks=respect_locks,
            )
            scanned_tracks.append({"track_type": current_type, "track_index": current_index, "locked": locked})
            if locked:
                skipped_locked.append({"track_type": current_type, "track_index": current_index, "reason": "track_locked"})
                continue
            for item in all_live_items[current_type]:
                if int(item.track_index) != current_index:
                    continue
                cut_frame = _item_cut_frame(conn, item, record_frame=record_frame)
                if cut_frame is None:
                    continue
                targets.append(
                    {
                        **asdict(item),
                        "cut_frame": cut_frame,
                        "record_frame": int(record_frame),
                        "db_type": _DB_TYPE_BY_TRACK_TYPE[current_type],
                    }
                )

    if not targets:
        raise ClipNotFound(
            "No blade targets found at the requested timeline position.",
            details={
                "at": at_ref,
                "record_frame": int(record_frame),
                "track_type": track_type,
                "track_index": track_index,
                "scanned_tracks": scanned_tracks,
                "skipped_locked": skipped_locked,
            },
        )

    return {
        "index": int(entry.get("index", 0)),
        "at": at_ref,
        "record_frame": int(record_frame),
        "record_tc": frames_to_timecode(int(record_frame), conn.fps),
        "track_type": track_type,
        "track_index": track_index,
        "targets": targets,
        "target_count": len(targets),
        "skipped_locked": skipped_locked,
        "preflight": {
            "at": at_ref,
            "record_frame": int(record_frame),
            "track_type": track_type,
            "track_index": track_index,
            "target_count": len(targets),
            "targets": targets,
            "skipped_locked": skipped_locked,
        },
    }


def preflight_blade_entries(
    conn: Any,
    entries: list[dict[str, Any]],
    *,
    default_at: str | None,
    default_track_type: str,
    default_track_index: int,
    respect_locks: bool,
    allow_partial: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    plans: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for entry in entries:
        index = int(entry.get("index", len(results)))
        try:
            plan = plan_blade_entry(
                conn,
                entry,
                default_at=default_at,
                default_track_type=default_track_type,
                default_track_index=default_track_index,
                respect_locks=respect_locks,
            )
            plans.append(plan)
            results.append({"index": index, "ok": True, "changed": True, "preflight": plan["preflight"]})
        except Exception as exc:
            from . import batch_utils

            row = {"index": index, "ok": False, "changed": False, "error": batch_utils.cli_error_payload(exc)}
            results.append(row)
            failures.append(row)
    if failures and not allow_partial:
        raise ValidationError(
            "Blade batch preflight failed; no mutations were applied.",
            details={"failure_count": len(failures), "failures": failures},
        )
    return plans, results


def _live_item_from_target(target: dict[str, Any]) -> LiveItemRef:
    return LiveItemRef(
        track_type=str(target["track_type"]),
        track_index=int(target["track_index"]),
        name=str(target.get("name") or ""),
        start=int(target["start"]),
        duration=int(target["duration"]),
        aliases=tuple(str(alias) for alias in (target.get("aliases") or ())),
    )


def _int_cell(value: object, *, default: int = 0) -> int:
    if value in (None, ""):
        return default
    return int(value)


def _split_in_value(current_in: object, offset_frames: int) -> str | None:
    if current_in in (None, ""):
        return str(int(offset_frames))
    value = str(current_in).strip()
    match = re.fullmatch(r"([+-]?\d+)(\|[0-9a-fA-F]{16})?", value)
    if match is not None:
        return f"{int(match[1]) + int(offset_frames)}{match[2] or ''}"
    return value


def _has_non_empty_markers(row: dict[str, Any]) -> bool:
    value = row.get("MarkersBA")
    if value in (None, "", b""):
        return False
    if isinstance(value, memoryview):
        return len(value.tobytes()) > 0
    if isinstance(value, bytes):
        return len(value) > 0
    return True


def _empty_blob(value: object) -> bool:
    if value in (None, "", b""):
        return True
    if isinstance(value, memoryview):
        return len(value.tobytes()) == 0
    if isinstance(value, bytes):
        return len(value) == 0
    return False


def _resolve_target_row(
    cursor: sqlite3.Cursor,
    *,
    target: dict[str, Any],
    timeline_name: str | None,
) -> dict[str, Any]:
    item = _live_item_from_target(target)
    row = find_ti_item_row(cursor, item=item, db_type=str(target["db_type"]), timeline_name=timeline_name)
    if row.get("DbType") not in {"Sm2TiVideoClip", "Sm2TiAudioClip"}:
        raise ValidationError(
            "Blade supports only video and audio timeline clips in v1.",
            details={"item_id": row.get("Sm2TiItem_id"), "db_type": row.get("DbType")},
        )
    if _has_non_empty_markers(row):
        raise ValidationError(
            "Blade refuses clips with non-empty clip marker payloads until marker splitting is supported.",
            details={"item_id": row.get("Sm2TiItem_id"), "name": row.get("Name")},
        )
    cut_frame = int(target["cut_frame"])
    start = _int_cell(row.get("Start"))
    duration = _int_cell(row.get("Duration"))
    if not (start < cut_frame < start + duration):
        raise ValidationError(
            "Blade cut point is not strictly inside the resolved Project.db item.",
            details={
                "item_id": row.get("Sm2TiItem_id"),
                "start": start,
                "duration": duration,
                "cut_frame": cut_frame,
            },
        )
    return row


def _right_effect_filters(row: dict[str, Any]) -> tuple[bytes | None, str]:
    if row.get("DbType") != "Sm2TiAudioClip":
        return row.get("EffectFiltersBA"), "preserved"
    return clip_effects_db.blade_right_audio_effect_filters(row.get("EffectFiltersBA"))


def _segment_link_groups(
    target_groups: dict[str, dict[str, Any]],
    segments: list[dict[str, Any]],
) -> list[list[str]]:
    """Build exact post-split link groups for every originally linked interval."""
    closed_groups: set[tuple[str, ...]] = set()
    target_ids = set(target_groups)
    for original_id, group in target_groups.items():
        linked_ids = group["target"].get("linked_item_ids")
        if linked_ids:
            members = tuple(sorted({original_id, *(str(item_id) for item_id in linked_ids)}))
            if set(members) != set(members).intersection(target_ids):
                raise ValidationError(
                    "Blade cannot preserve an incomplete linked-item group.",
                    details={"original_item_id": original_id, "linked_item_ids": list(linked_ids)},
                )
            closed_groups.add(members)

    segments_by_original: dict[str, dict[tuple[int, int], str]] = {}
    for segment in segments:
        original_id = str(segment["original_item_id"])
        interval = (int(segment["start"]), int(segment["duration"]))
        segments_by_original.setdefault(original_id, {})[interval] = str(segment["item_id"])

    result: list[list[str]] = []
    for members in sorted(closed_groups):
        intervals = {frozenset(segments_by_original.get(member, {})) for member in members}
        if len(intervals) != 1 or not intervals or not next(iter(intervals)):
            raise ValidationError(
                "Blade produced mismatched segment intervals for a linked-item group.",
                details={"original_item_ids": list(members)},
            )
        for interval in sorted(next(iter(intervals))):
            result.append([segments_by_original[member][interval] for member in members])
    return result


def _item_unique_id(item: Any) -> str | None:
    getter = getattr(item, "GetUniqueId", None)
    if not callable(getter):
        return None
    try:
        return str(getter() or "").strip() or None
    except Exception:
        return None


def _repair_and_verify_segment_links(conn: Any, link_groups: list[list[str]]) -> list[dict[str, Any]]:
    if not link_groups:
        return []
    items_by_id: dict[str, Any] = {}
    for track_type in ("video", "audio"):
        for track_index in range(1, _track_count(conn, track_type) + 1):
            for item in conn.timeline.GetItemListInTrack(track_type, track_index) or []:
                item_id = _item_unique_id(item)
                if item_id:
                    items_by_id[item_id] = item
    affected_ids = {item_id for group in link_groups for item_id in group}
    if affected_ids - set(items_by_id):
        return [{
            "group": sorted(affected_ids),
            "ok": False,
            "reason": "split_item_unavailable",
            "missing_item_ids": sorted(affected_ids - set(items_by_id)),
        }]
    linker = getattr(conn.timeline, "SetClipsLinked", None)
    if not callable(linker):
        return [{"group": sorted(affected_ids), "ok": False, "reason": "link_api_unavailable"}]
    affected_items = [items_by_id[item_id] for item_id in sorted(affected_ids)]
    if linker(affected_items, False) is not True:
        return [{"group": sorted(affected_ids), "ok": False, "reason": "unlink_failed"}]
    for group in link_groups:
        if linker([items_by_id[item_id] for item_id in group], True) is not True:
            return [{"group": list(group), "ok": False, "reason": "relink_failed"}]

    checks: list[dict[str, Any]] = []
    for group in link_groups:
        group_ids = set(group)
        for item_id in group:
            getter = getattr(items_by_id[item_id], "GetLinkedItems", None)
            try:
                linked_items = getter() if callable(getter) else None
            except Exception:
                linked_items = None
            actual_ids = None
            if isinstance(linked_items, (list, tuple)):
                resolved_ids = [_item_unique_id(linked) for linked in linked_items]
                actual_ids = sorted(linked_id for linked_id in resolved_ids if linked_id)
            expected_ids = sorted(group_ids - {item_id})
            checks.append({
                "item_id": item_id,
                "expected_linked_item_ids": expected_ids,
                "actual_linked_item_ids": actual_ids,
                "ok": actual_ids == expected_ids,
            })
    return checks


def write_blade_batch(
    cursor: sqlite3.Cursor,
    *,
    plans: list[dict[str, Any]],
    preflight_results: list[dict[str, Any]],
    timeline_name: str | None,
    allow_partial: bool,
    pre_track_counts: dict[str, int],
) -> dict[str, Any]:
    target_groups: dict[str, dict[str, Any]] = {}
    for plan in plans:
        for target in plan.get("targets") or []:
            row = _resolve_target_row(cursor, target=target, timeline_name=timeline_name)
            item_id = str(row["Sm2TiItem_id"])
            group = target_groups.setdefault(
                item_id,
                {
                    "row": row,
                    "target": target,
                    "cuts": [],
                },
            )
            if int(target["cut_frame"]) in {int(cut["cut_frame"]) for cut in group["cuts"]}:
                raise ValidationError(
                    "Duplicate blade cut for the same timeline item.",
                    details={"item_id": item_id, "cut_frame": int(target["cut_frame"])},
                )
            group["cuts"].append(target)

    segments: list[dict[str, Any]] = []
    property_checks: list[dict[str, Any]] = []
    touched_tracks: set[tuple[str, int, str]] = set()
    for group in target_groups.values():
        row = dict(group["row"])
        target = dict(group["target"])
        cuts = sorted((int(cut["cut_frame"]) for cut in group["cuts"]), key=int)
        start = _int_cell(row.get("Start"))
        duration = _int_cell(row.get("Duration"))
        end = start + duration
        if any(cut <= start or cut >= end for cut in cuts):
            raise ValidationError(
                "Blade cut point is not strictly inside the resolved Project.db item.",
                details={"item_id": row.get("Sm2TiItem_id"), "start": start, "duration": duration, "cuts": cuts},
            )

        original_id = str(row["Sm2TiItem_id"])
        track_id = str(row["Sm2TiTrack_id"])
        track_type = str(target["track_type"])
        track_index = int(target["track_index"])
        touched_tracks.add((track_type, track_index, track_id))

        boundaries = [start, *cuts, end]
        first_duration = boundaries[1] - boundaries[0]
        update_row(cursor, "Sm2TiItem", "Sm2TiItem_id", original_id, {"Duration": str(first_duration)})
        segments.append(
            {
                "track_type": track_type,
                "track_index": track_index,
                "original_item_id": original_id,
                "right_item_id": None,
                "item_id": original_id,
                "start": start,
                "duration": first_duration,
                "in": row.get("In"),
                "side": "left",
            }
        )

        for segment_index in range(1, len(boundaries) - 1):
            segment_start = boundaries[segment_index]
            segment_end = boundaries[segment_index + 1]
            right_id = str(uuid.uuid4())
            effect_filters, transform = _right_effect_filters(row)
            right_row = dict(row)
            right_row["Sm2TiItem_id"] = right_id
            right_row["Start"] = str(segment_start)
            right_row["Duration"] = str(segment_end - segment_start)
            right_row["In"] = _split_in_value(row.get("In"), segment_start - start)
            right_row["EffectFiltersBA"] = sqlite3.Binary(effect_filters) if effect_filters is not None else None
            if "MarkersBA" in right_row and _empty_blob(right_row.get("MarkersBA")):
                right_row["MarkersBA"] = None
            insert_row(cursor, "Sm2TiItem", right_row)
            insert_row(
                cursor,
                "Sm2TiItem_Sm2TiTrack",
                {
                    "DbOwner": track_id,
                    "DbAssociate": right_id,
                    "DbPropertyName": "Items",
                    "DbIndex": next_db_index(
                        cursor,
                        table_name="Sm2TiItem_Sm2TiTrack",
                        owner_value=track_id,
                        property_name="Items",
                    ),
                },
            )
            right_segment = {
                "track_type": track_type,
                "track_index": track_index,
                "original_item_id": original_id,
                "right_item_id": right_id,
                "item_id": right_id,
                "start": segment_start,
                "duration": segment_end - segment_start,
                "in": right_row.get("In"),
                "side": "right",
                "effect_transform": transform,
            }
            segments.append(right_segment)
            property_checks.append(
                {
                    "item_id": right_id,
                    "original_item_id": original_id,
                    "track_type": track_type,
                    "track_index": track_index,
                    "effect_transform": transform,
                    "fields_blob_preserved": right_row.get("FieldsBlob") == row.get("FieldsBlob"),
                    "media_timemap_preserved": right_row.get("MediaTimemapBA") == row.get("MediaTimemapBA"),
                    "current_selector_preserved": right_row.get("CurrentSelectorIdx") == row.get("CurrentSelectorIdx"),
                }
            )

    for _track_type, _track_index, track_id in touched_tracks:
        rebuild_track_item_indices(cursor, track_id=track_id)

    cut_count = sum(max(0, len(group["cuts"])) for group in target_groups.values())
    expected_track_counts = []
    additions_by_track: dict[str, int] = {}
    for segment in segments:
        if segment["side"] != "right":
            continue
        key = f"{segment['track_type']}:{segment['track_index']}"
        additions_by_track[key] = additions_by_track.get(key, 0) + 1
    for key, additions in sorted(additions_by_track.items()):
        expected_track_counts.append(
            {
                "track": key,
                "pre_count": int(pre_track_counts.get(key, 0)),
                "expected_post_count": int(pre_track_counts.get(key, 0)) + int(additions),
                "added_count": int(additions),
            }
        )

    link_groups = _segment_link_groups(target_groups, segments)

    return {
        "action": BLADE_ACTION,
        "changed": bool(cut_count),
        "dry_run": False,
        "allow_partial": bool(allow_partial),
        "timeline": timeline_name,
        "requested_count": len(preflight_results),
        "planned_count": len(plans),
        "cut_count": cut_count,
        "results": preflight_results,
        "segments": segments,
        "property_checks": property_checks,
        "expected_track_counts": expected_track_counts,
        "link_groups": link_groups,
    }


def verify_blade_batch(conn: Any, mutation_result: Any, _session: Any) -> dict[str, Any]:
    result = mutation_result if isinstance(mutation_result, dict) else {}
    checks: list[dict[str, Any]] = []
    for expected in result.get("expected_track_counts") or []:
        track_type, _, track_index_text = str(expected.get("track") or "").partition(":")
        try:
            post_count = len(conn.timeline.GetItemListInTrack(track_type, int(track_index_text)) or [])
            ok = post_count >= int(expected.get("expected_post_count") or 0)
            checks.append({**expected, "post_count": post_count, "ok": ok})
        except Exception as exc:
            checks.append({**expected, "ok": False, "error": str(exc)})
    property_checks = list(result.get("property_checks") or [])
    property_ok = all(
        bool(check.get("fields_blob_preserved"))
        and bool(check.get("media_timemap_preserved"))
        and bool(check.get("current_selector_preserved"))
        for check in property_checks
    )
    link_checks = _repair_and_verify_segment_links(conn, list(result.get("link_groups") or []))
    links_ok = all(bool(check.get("ok")) for check in link_checks)
    count_ok = all(bool(check.get("ok")) for check in checks) if checks else True
    return {
        "status": "verified" if count_ok and property_ok and links_ok else "failed",
        "track_count_checks": checks,
        "property_checks": property_checks,
        "link_checks": link_checks,
    }


def dry_run_payload(
    *,
    plans: list[dict[str, Any]],
    preflight_results: list[dict[str, Any]],
    timeline_name: str | None,
    allow_partial: bool,
) -> dict[str, Any]:
    cut_count = sum(len(plan.get("targets") or []) for plan in plans)
    return {
        "action": BLADE_ACTION,
        "changed": False,
        "dry_run": True,
        "allow_partial": bool(allow_partial),
        "timeline": timeline_name,
        "requested_count": len(preflight_results),
        "planned_count": len(plans),
        "cut_count": cut_count,
        "results": preflight_results,
        "verification": {},
    }


def no_op_payload(
    *,
    preflight_results: list[dict[str, Any]],
    timeline_name: str | None,
    allow_partial: bool,
) -> dict[str, Any]:
    return {
        "action": BLADE_ACTION,
        "changed": False,
        "dry_run": False,
        "allow_partial": bool(allow_partial),
        "timeline": timeline_name,
        "requested_count": len(preflight_results),
        "planned_count": 0,
        "cut_count": 0,
        "results": preflight_results,
        "verification": {"status": "not_requested"},
    }
