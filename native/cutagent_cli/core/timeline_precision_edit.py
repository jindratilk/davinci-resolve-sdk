"""Stable timeline snapshots and verified precision-delete mutations."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable

from ..errors import APICallFailed, ClipNotFound, ValidationError


@dataclass(frozen=True)
class TimelineItemState:
    item_id: str
    track_type: str
    track_index: int
    name: str
    start: int
    end: int
    duration: int
    source_start: int | None
    source_end: int | None
    linked_item_ids: tuple[str, ...]

    def payload(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TimelineSnapshot:
    timeline_id: str
    timeline_name: str
    start_frame: int
    items: tuple[TimelineItemState, ...]
    native_items: dict[str, Any]

    @property
    def by_id(self) -> dict[str, TimelineItemState]:
        return {item.item_id: item for item in self.items}


def _required_unique_id(native_object: Any, *, object_kind: str) -> str:
    getter = getattr(native_object, "GetUniqueId", None)
    if not callable(getter):
        raise ValidationError(
            f"{object_kind} does not expose the stable identity required for a precision edit.",
            details={"object_kind": object_kind, "required_method": "GetUniqueId"},
            recoverability="manual",
        )
    try:
        value = str(getter() or "").strip()
    except Exception as exc:
        raise ValidationError(
            f"Could not read the stable {object_kind} identity required for a precision edit.",
            details={"object_kind": object_kind, "required_method": "GetUniqueId", "error": str(exc)},
            recoverability="manual",
        ) from exc
    if not value:
        raise ValidationError(
            f"{object_kind} returned an empty stable identity for a precision edit.",
            details={"object_kind": object_kind, "required_method": "GetUniqueId"},
            recoverability="manual",
        )
    return value


def _required_frame(item: Any, *, item_id: str, field: str, method_names: tuple[str, ...]) -> int:
    for method_name in method_names:
        getter = getattr(item, method_name, None)
        if not callable(getter):
            continue
        try:
            value = getter()
            if value is not None and not isinstance(value, bool):
                return int(value)
        except Exception as exc:
            raise ValidationError(
                "Could not read source-range state required for precision-edit protection.",
                details={"item_id": item_id, "field": field, "method": method_name, "error": str(exc)},
                recoverability="manual",
            ) from exc
    raise ValidationError(
        "Timeline item does not expose source-range state required for precision-edit protection.",
        details={"item_id": item_id, "field": field, "required_methods": list(method_names)},
        recoverability="manual",
    )


def _timeline_identity(conn: Any) -> tuple[str, str, int]:
    timeline = getattr(conn, "timeline", None)
    if timeline is None:
        raise ValidationError("No active DaVinci Resolve timeline for precision edit.")
    timeline_id = _required_unique_id(timeline, object_kind="Timeline")
    try:
        name = str(timeline.GetName() or "")
    except Exception:
        name = ""
    getter = getattr(timeline, "GetStartFrame", None)
    if not callable(getter):
        raise ValidationError(
            "Timeline does not expose the absolute start frame required for precision editing.",
            details={"required_method": "Timeline.GetStartFrame"},
            recoverability="manual",
        )
    try:
        raw_start_frame = getter()
        if raw_start_frame is None or isinstance(raw_start_frame, bool):
            raise TypeError(f"invalid start-frame value: {raw_start_frame!r}")
        start_frame = int(raw_start_frame)
    except Exception as exc:
        raise ValidationError(
            "Could not read the absolute timeline start required for precision editing.",
            details={"required_method": "Timeline.GetStartFrame", "error": str(exc)},
            recoverability="manual",
        ) from exc
    return timeline_id, name, start_frame


def snapshot_timeline(conn: Any) -> TimelineSnapshot:
    """Capture stable A/V timeline item identity, record/source ranges, and links."""
    timeline_id, timeline_name, start_frame = _timeline_identity(conn)
    native_items: dict[str, Any] = {}
    provisional: list[dict[str, Any]] = []
    for track_type in ("video", "audio"):
        try:
            raw_track_count = conn.timeline.GetTrackCount(track_type)
            if raw_track_count is None or isinstance(raw_track_count, bool):
                raise TypeError(f"invalid track-count value: {raw_track_count!r}")
            track_count = int(raw_track_count)
        except Exception as exc:
            raise ValidationError(
                "Could not enumerate all A/V tracks required for precision-edit protection.",
                details={"track_type": track_type, "required_method": "GetTrackCount", "error": str(exc)},
                recoverability="manual",
            ) from exc
        for track_index in range(1, track_count + 1):
            try:
                track_items = conn.timeline.GetItemListInTrack(track_type, track_index)
            except Exception as exc:
                raise ValidationError(
                    "Could not enumerate a track required for precision-edit protection.",
                    details={"track_type": track_type, "track_index": track_index, "error": str(exc)},
                    recoverability="manual",
                ) from exc
            if not isinstance(track_items, (list, tuple)):
                raise ValidationError(
                    "Timeline track item readback did not return a complete collection.",
                    details={
                        "track_type": track_type,
                        "track_index": track_index,
                        "required_method": "GetItemListInTrack",
                        "actual_type": type(track_items).__name__,
                    },
                    recoverability="manual",
                )
            for item in track_items:
                item_id = _required_unique_id(item, object_kind="TimelineItem")
                if item_id in native_items:
                    raise ValidationError(
                        "Timeline item stable identity is not unique in the active timeline.",
                        details={"item_id": item_id, "timeline_id": timeline_id},
                        recoverability="manual",
                    )
                try:
                    name = str(item.GetName() or "")
                    start = int(item.GetStart())
                    end = int(item.GetEnd())
                except Exception as exc:
                    raise ValidationError(
                        "Could not read a timeline item required for precision-edit preflight.",
                        details={"item_id": item_id, "track_type": track_type, "track_index": track_index, "error": str(exc)},
                        recoverability="manual",
                    ) from exc
                native_items[item_id] = item
                provisional.append(
                    {
                        "item_id": item_id,
                        "track_type": track_type,
                        "track_index": track_index,
                        "name": name,
                        "start": start,
                        "end": end,
                        "duration": end - start,
                        "source_start": _required_frame(
                            item,
                            item_id=item_id,
                            field="source_start",
                            method_names=("GetSourceStartFrame", "GetSourceStart"),
                        ),
                        "source_end": _required_frame(
                            item,
                            item_id=item_id,
                            field="source_end",
                            method_names=("GetSourceEndFrame", "GetSourceEnd"),
                        ),
                    }
                )

    states: list[TimelineItemState] = []
    for row in provisional:
        item = native_items[row["item_id"]]
        linked_ids: list[str] = []
        getter = getattr(item, "GetLinkedItems", None)
        if not callable(getter):
            raise ValidationError(
                "Timeline item does not expose linked-item state required for precision-edit protection.",
                details={"item_id": row["item_id"], "required_method": "GetLinkedItems"},
                recoverability="manual",
            )
        try:
            linked_items = getter()
            if not isinstance(linked_items, (list, tuple)):
                raise ValidationError(
                    "Linked-item readback did not return a complete collection.",
                    details={
                        "item_id": row["item_id"],
                        "required_method": "GetLinkedItems",
                        "actual_type": type(linked_items).__name__,
                    },
                    recoverability="manual",
                )
            for linked in linked_items:
                linked_id = _required_unique_id(linked, object_kind="Linked TimelineItem")
                if linked_id not in native_items:
                    raise ValidationError(
                        "A linked timeline item is outside the readable A/V timeline snapshot.",
                        details={"item_id": row["item_id"], "linked_item_id": linked_id},
                        recoverability="manual",
                    )
                linked_ids.append(linked_id)
        except ValidationError:
            raise
        except Exception as exc:
            raise ValidationError(
                "Could not read linked timeline items required for precision-edit preflight.",
                details={"item_id": row["item_id"], "error": str(exc)},
                recoverability="manual",
            ) from exc
        states.append(TimelineItemState(**row, linked_item_ids=tuple(sorted(set(linked_ids)))))

    links_by_id = {state.item_id: set(state.linked_item_ids) for state in states}
    asymmetric = [
        {"item_id": item_id, "linked_item_id": linked_id}
        for item_id, linked_ids in links_by_id.items()
        for linked_id in linked_ids
        if item_id not in links_by_id.get(linked_id, set())
    ]
    if asymmetric:
        raise ValidationError(
            "Timeline linked-item state is asymmetric and cannot safely define a precision-edit group.",
            details={"asymmetric_links": asymmetric},
            recoverability="manual",
        )

    return TimelineSnapshot(
        timeline_id=timeline_id,
        timeline_name=timeline_name,
        start_frame=start_frame,
        items=tuple(sorted(states, key=lambda item: (item.track_type, item.track_index, item.start, item.end, item.item_id))),
        native_items=native_items,
    )


def select_item_at(
    snapshot: TimelineSnapshot,
    *,
    frame: int,
    track_type: str,
    track_index: int,
) -> TimelineItemState:
    matches = [
        item
        for item in snapshot.items
        if item.track_type == track_type
        and (not track_index or item.track_index == int(track_index))
        and item.start <= int(frame) < item.end
    ]
    if not matches:
        raise ClipNotFound(
            f"No {track_type} clip at frame {frame}.",
            details={"record_frame": int(frame), "track_type": track_type, "track_index": int(track_index)},
        )
    if len(matches) != 1:
        raise ValidationError(
            "Timeline item selection is ambiguous at the requested position.",
            details={
                "record_frame": int(frame),
                "track_type": track_type,
                "track_index": int(track_index),
                "matches": [item.payload() for item in matches],
            },
            recoverability="manual",
        )
    return matches[0]


def select_items_in_range(
    snapshot: TimelineSnapshot,
    *,
    start_frame: int,
    end_frame: int,
    track_type: str,
    track_index: int,
) -> list[TimelineItemState]:
    if int(end_frame) <= int(start_frame):
        raise ValidationError(
            "Range end must be greater than range start.",
            details={"start_frame": int(start_frame), "end_frame": int(end_frame)},
        )
    matches = [
        item
        for item in snapshot.items
        if item.track_type == track_type
        and (not track_index or item.track_index == int(track_index))
        and item.start < int(end_frame)
        and item.end > int(start_frame)
    ]
    if not matches:
        raise ClipNotFound(
            f"No clips in range on the requested {track_type} track scope.",
            details={
                "start_frame": int(start_frame),
                "end_frame": int(end_frame),
                "track_type": track_type,
                "track_index": int(track_index),
            },
        )
    return matches


def match_ref(snapshot: TimelineSnapshot, ref: Any) -> TimelineItemState:
    matches = [
        item
        for item in snapshot.items
        if item.track_type == str(ref.track_type)
        and item.track_index == int(ref.track_index)
        and item.start == int(ref.start)
        and item.end == int(ref.end)
        and item.name == str(ref.name)
    ]
    if len(matches) != 1:
        raise ValidationError(
            "Resolved timeline item is not uniquely addressable by stable identity.",
            details={"selection": asdict(ref), "match_count": len(matches)},
            recoverability="manual",
        )
    return matches[0]


def linked_group(snapshot: TimelineSnapshot, primary_id: str) -> list[TimelineItemState]:
    by_id = snapshot.by_id
    if primary_id not in by_id:
        raise ValidationError("Primary timeline item is missing from the precision-edit snapshot.", details={"item_id": primary_id})
    selected: set[str] = set()
    pending = [primary_id]
    while pending:
        item_id = pending.pop()
        if item_id in selected:
            continue
        selected.add(item_id)
        pending.extend(linked_id for linked_id in by_id[item_id].linked_item_ids if linked_id not in selected)
    return [by_id[item_id] for item_id in sorted(selected)]


def _assert_same_timeline(before: TimelineSnapshot, after: TimelineSnapshot) -> None:
    if before.timeline_id != after.timeline_id or before.start_frame != after.start_frame:
        raise ValidationError(
            "The active timeline identity or absolute start changed after precision-edit preflight.",
            details={
                "expected_timeline_id": before.timeline_id,
                "actual_timeline_id": after.timeline_id,
                "expected_start_frame": before.start_frame,
                "actual_start_frame": after.start_frame,
            },
            recoverability="manual",
        )


def _state_equal(left: TimelineItemState, right: TimelineItemState, *, ignored_link_ids: set[str] | None = None) -> bool:
    ignored = ignored_link_ids or set()
    return (
        left.item_id == right.item_id
        and left.track_type == right.track_type
        and left.track_index == right.track_index
        and left.name == right.name
        and left.start == right.start
        and left.end == right.end
        and left.duration == right.duration
        and left.source_start == right.source_start
        and left.source_end == right.source_end
        and tuple(item_id for item_id in left.linked_item_ids if item_id not in ignored)
        == tuple(item_id for item_id in right.linked_item_ids if item_id not in ignored)
    )


def revalidate_targets(conn: Any, before: TimelineSnapshot, target_ids: Iterable[str]) -> TimelineSnapshot:
    target_set = set(target_ids)
    try:
        conn.refresh()
    except Exception as exc:
        raise ValidationError(
            "Could not refresh live DaVinci Resolve state before precision-edit mutation revalidation.",
            details={"failure_step": "pre_mutation_refresh", "error": str(exc)},
            recoverability="manual",
        ) from exc
    current = snapshot_timeline(conn)
    _assert_same_timeline(before, current)
    before_by_id = before.by_id
    current_by_id = current.by_id
    stale: list[dict[str, Any]] = []
    protected_changes: list[dict[str, Any]] = []
    for item_id in sorted(set(before_by_id) | set(current_by_id)):
        expected = before_by_id.get(item_id)
        actual = current_by_id.get(item_id)
        if expected is None or actual is None or not _state_equal(expected, actual):
            change = {
                "item_id": item_id,
                "expected": expected.payload() if expected else None,
                "actual": actual.payload() if actual else None,
            }
            (stale if item_id in target_set else protected_changes).append(
                {
                    **change,
                }
            )
    if stale or protected_changes:
        raise ValidationError(
            "Precision-edit timeline changed after selection; refusing mutation before any write.",
            details={"stale_targets": stale, "protected_state_changes": protected_changes},
            recoverability="manual",
        )
    return current


def _post_write_snapshot(conn: Any, before: TimelineSnapshot, *, action: str) -> TimelineSnapshot:
    try:
        conn.refresh()
        after = snapshot_timeline(conn)
        _assert_same_timeline(before, after)
        return after
    except Exception as exc:
        raise APICallFailed(
            "Precision-edit mutation completed but post-write timeline readback failed.",
            details={
                "action": action,
                "failure_step": "post_write_readback",
                "mutation_may_have_occurred": True,
                "mutation_state": "unknown",
                "compensation": {"available": False, "attempted": False, "status": "not_available"},
                "rollback_hint": "Restore the pre-edit project/timeline checkpoint, then inspect the active timeline before retrying.",
                "cause_code": getattr(exc, "code", None),
                "cause_details": getattr(exc, "details", None),
                "error": str(exc),
            },
            recoverability="manual",
        ) from exc


def _non_ripple_verification(
    before: TimelineSnapshot,
    after: TimelineSnapshot,
    target_ids: set[str],
) -> dict[str, Any]:
    before_by_id = before.by_id
    after_by_id = after.by_id
    removed = [item_id for item_id in sorted(target_ids) if item_id not in after_by_id]
    protected_changes: list[dict[str, Any]] = []
    for item_id, expected in before_by_id.items():
        if item_id in target_ids:
            continue
        actual = after_by_id.get(item_id)
        if actual is None or not _state_equal(expected, actual, ignored_link_ids=target_ids):
            protected_changes.append(
                {
                    "item_id": item_id,
                    "expected": expected.payload(),
                    "actual": actual.payload() if actual else None,
                }
            )
    unexpected = sorted(set(after_by_id) - set(before_by_id))
    ok = len(removed) == len(target_ids) and not protected_changes and not unexpected
    return {
        "status": "verified" if ok else "failed",
        "removed_item_ids": removed,
        "expected_removed_item_ids": sorted(target_ids),
        "protected_changes": protected_changes,
        "unexpected_item_ids": unexpected,
    }


def delete_non_ripple(
    conn: Any,
    *,
    before: TimelineSnapshot,
    target_ids: Iterable[str],
    action: str,
) -> dict[str, Any]:
    target_set = set(target_ids)
    if not target_set:
        raise ValidationError("Precision delete requires at least one target.")
    current = revalidate_targets(conn, before, target_set)
    native_targets = [current.native_items[item_id] for item_id in sorted(target_set)]
    try:
        delete_result = conn.timeline.DeleteClips(native_targets, False)
    except Exception as exc:
        raise APICallFailed(
            "DaVinci Resolve failed the explicit non-ripple Timeline.DeleteClips call.",
            details={
                "action": action,
                "required_api": "Timeline.DeleteClips(items, False)",
                "mutation_may_have_occurred": True,
                "mutation_state": "unknown",
                "compensation": {"available": False, "attempted": False, "status": "not_available"},
                "rollback_hint": "Restore the pre-edit project/timeline checkpoint, then inspect the active timeline before retrying.",
                "error": str(exc),
            },
            recoverability="manual",
        ) from exc
    after = _post_write_snapshot(conn, before, action=action)
    verification = _non_ripple_verification(before, after, target_set)
    if delete_result is False or verification["status"] != "verified":
        raise APICallFailed(
            "Failed to delete timeline item(s) or verify protected timeline state.",
            details={
                "action": action,
                "delete_result": delete_result,
                "mutation_may_have_occurred": True,
                "mutation_state": "partial_or_unverified",
                "compensation": {"available": False, "attempted": False, "status": "not_available"},
                "rollback_hint": "Restore the pre-edit project/timeline checkpoint before retrying.",
                "verification": verification,
            },
            recoverability="manual",
        )
    return {
        "action": action,
        "changed": True,
        "route": "api_native_timeline_delete_clips_non_ripple",
        "native_api": "Timeline.DeleteClips([timelineItems], False)",
        "timeline": before.timeline_name,
        "targets": [before.by_id[item_id].payload() for item_id in sorted(target_set)],
        "delete_result": delete_result,
        "verification": verification,
    }


def _ripple_expected_states(before: TimelineSnapshot, target_ids: set[str]) -> tuple[dict[str, TimelineItemState], dict[str, int]]:
    missing_target_ids = sorted(target_ids - set(before.by_id))
    if missing_target_ids:
        raise ValidationError(
            "Native ripple-delete targets are missing from the precision-edit snapshot.",
            details={"missing_target_ids": missing_target_ids},
            recoverability="manual",
        )
    targets = [before.by_id[item_id] for item_id in sorted(target_ids)]
    by_track: dict[tuple[str, int], list[TimelineItemState]] = {}
    for target in targets:
        by_track.setdefault((target.track_type, target.track_index), []).append(target)
    invalid_tracks = {
        f"{track_type}:{track_index}": [target.payload() for target in rows]
        for (track_type, track_index), rows in by_track.items()
        if len(rows) != 1
    }
    if invalid_tracks:
        raise ValidationError(
            "Native ripple delete requires exactly one selected item per affected track.",
            details={"affected_tracks": invalid_tracks},
            recoverability="manual",
        )
    spans = {(target.start, target.end, target.duration) for target in targets}
    if len(spans) != 1:
        raise ValidationError(
            "Linked ripple-delete targets must share one record span and duration.",
            details={"targets": [target.payload() for target in targets]},
            recoverability="manual",
        )

    expected: dict[str, TimelineItemState] = {}
    deltas: dict[str, int] = {}
    for item in before.items:
        if item.item_id in target_ids:
            continue
        target = by_track.get((item.track_type, item.track_index), [None])[0]
        if target is None:
            expected[item.item_id] = item
            continue
        if item.end <= target.start:
            expected[item.item_id] = item
        elif item.start >= target.end:
            expected[item.item_id] = TimelineItemState(
                **{
                    **item.payload(),
                    "start": item.start - target.duration,
                    "end": item.end - target.duration,
                    "linked_item_ids": tuple(item_id for item_id in item.linked_item_ids if item_id not in target_ids),
                }
            )
        else:
            raise ValidationError(
                "Ripple delete found an overlapping protected item on an affected track.",
                details={"target": target.payload(), "protected_item": item.payload()},
                recoverability="manual",
            )
        deltas[f"{target.track_type}:{target.track_index}"] = target.duration
    return expected, deltas


def _ripple_verification(
    before: TimelineSnapshot,
    after: TimelineSnapshot,
    target_ids: set[str],
    expected: dict[str, TimelineItemState],
    deltas: dict[str, int],
) -> dict[str, Any]:
    after_by_id = after.by_id
    removed = [item_id for item_id in sorted(target_ids) if item_id not in after_by_id]
    mismatches: list[dict[str, Any]] = []
    for item_id, expected_state in expected.items():
        actual = after_by_id.get(item_id)
        if actual is None or not _state_equal(expected_state, actual, ignored_link_ids=target_ids):
            mismatches.append(
                {
                    "item_id": item_id,
                    "expected": expected_state.payload(),
                    "actual": actual.payload() if actual else None,
                }
            )
    unexpected = sorted(set(after_by_id) - set(expected))
    ok = len(removed) == len(target_ids) and not mismatches and not unexpected
    return {
        "status": "verified" if ok else "failed",
        "removed_item_ids": removed,
        "expected_removed_item_ids": sorted(target_ids),
        "ripple_delta_frames_by_track": deltas,
        "protected_or_ripple_mismatches": mismatches,
        "unexpected_item_ids": unexpected,
    }


def delete_ripple(
    conn: Any,
    *,
    before: TimelineSnapshot,
    target_ids: Iterable[str],
) -> dict[str, Any]:
    target_set = set(target_ids)
    if not target_set:
        raise ValidationError("Native ripple delete requires at least one target.")
    expected, deltas = _ripple_expected_states(before, target_set)
    current = revalidate_targets(conn, before, target_set)
    native_targets = [current.native_items[item_id] for item_id in sorted(target_set)]
    try:
        delete_result = conn.timeline.DeleteClips(native_targets, True)
    except Exception as exc:
        raise APICallFailed(
            "DaVinci Resolve failed the native ripple Timeline.DeleteClips call.",
            details={
                "required_api": "Timeline.DeleteClips(items, True)",
                "mutation_may_have_occurred": True,
                "mutation_state": "unknown",
                "compensation": {"available": False, "attempted": False, "status": "not_available"},
                "rollback_hint": "Restore the pre-edit project/timeline checkpoint, then inspect the active timeline before retrying.",
                "error": str(exc),
            },
            recoverability="manual",
        ) from exc
    after = _post_write_snapshot(conn, before, action="edit.ripple_delete_selected")
    verification = _ripple_verification(before, after, target_set, expected, deltas)
    if delete_result is False or verification["status"] != "verified":
        raise APICallFailed(
            "Native ripple delete did not verify gap closure and protected timeline state.",
            details={
                "delete_result": delete_result,
                "mutation_may_have_occurred": True,
                "mutation_state": "partial_or_unverified",
                "compensation": {"available": False, "attempted": False, "status": "not_available"},
                "rollback_hint": "Restore the pre-edit project/timeline checkpoint before retrying.",
                "verification": verification,
            },
            recoverability="manual",
        )
    return {
        "action": "edit.ripple_delete_selected",
        "changed": True,
        "route": "api_native_timeline_delete_clips_ripple",
        "native_api": "Timeline.DeleteClips([timelineItems], True)",
        "timeline": before.timeline_name,
        "targets": [before.by_id[item_id].payload() for item_id in sorted(target_set)],
        "delete_result": delete_result,
        "verification": verification,
    }
