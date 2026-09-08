"""Deterministic live timeline item selection for Disk DB mutations."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
import math

from ..errors import ClipNotFound, SdkMutationStaleRevision, ValidationError
from ..utils.time_ref import parse_record_frame
from . import clip_ops


@dataclass(frozen=True)
class LiveItemRef:
    track_type: str
    track_index: int
    name: str
    start: int
    duration: int
    aliases: tuple[str, ...] = ()
    item_id: str | None = None
    linked_item_ids: tuple[str, ...] | None = None
    source_start_frame: int | None = None
    source_end_frame: int | None = None
    source_origin_frame: float | None = None

    @property
    def end(self) -> int:
        return int(self.start) + int(self.duration)


def sdk_guard_track_index(expected_track_type: str) -> int | None:
    """Return the exact private SDK selector track, or no selector outside SDK dispatch."""
    if not os.getenv("CUTAGENT_SDK_TIMELINE_GUARD"):
        return None
    track_type = str(os.getenv("CUTAGENT_CLI_SDK_TIMELINE_TRACK_TYPE") or "").strip().lower()
    raw_index = str(os.getenv("CUTAGENT_CLI_SDK_TIMELINE_TRACK_INDEX") or "").strip()
    try:
        track_index = int(raw_index)
    except (TypeError, ValueError) as exc:
        raise ValidationError("SDK timeline selector omitted an exact track index.") from exc
    if track_type != expected_track_type or track_index < 1:
        raise ValidationError(
            "SDK timeline selector does not match the native command's required track type.",
            details={"expected_track_type": expected_track_type, "track_type": track_type, "track_index": track_index},
        )
    return track_index


def _read_live_items(conn, *, track_type: str) -> list[LiveItemRef]:
    rows: list[LiveItemRef] = []
    count = int(conn.timeline.GetTrackCount(track_type) or 0)
    for index in range(1, count + 1):
        for item in conn.timeline.GetItemListInTrack(track_type, index) or []:
            try:
                start = int(item.GetStart())
                end = int(item.GetEnd())
                name = str(item.GetName() or "")
            except Exception:
                continue
            aliases = tuple(sorted(clip_ops._item_name_candidates(item)))
            item_id = None
            unique_id_getter = getattr(item, "GetUniqueId", None)
            if callable(unique_id_getter):
                try:
                    item_id = str(unique_id_getter() or "").strip() or None
                except Exception:
                    item_id = None
            linked_item_ids = None
            linked_items_getter = getattr(item, "GetLinkedItems", None)
            if callable(linked_items_getter):
                try:
                    linked_items = linked_items_getter()
                    if linked_items is not None:
                        linked_ids: list[str] = []
                        for linked_item in linked_items:
                            linked_id_getter = getattr(linked_item, "GetUniqueId", None)
                            linked_id = str(linked_id_getter() or "").strip() if callable(linked_id_getter) else ""
                            if not linked_id:
                                linked_ids = []
                                break
                            linked_ids.append(linked_id)
                        else:
                            linked_item_ids = tuple(sorted(set(linked_ids)))
                except Exception:
                    linked_item_ids = None
            rows.append(
                LiveItemRef(
                    track_type=track_type,
                    track_index=index,
                    name=name,
                    start=start,
                    duration=max(0, end - start),
                    aliases=aliases,
                    item_id=item_id,
                    linked_item_ids=linked_item_ids,
                )
            )
    return rows


def require_exact_sdk_retime_targets(conn, expected_targets: object) -> list[LiveItemRef]:
    """Revalidate the complete private retime target/link set against live state."""

    if not isinstance(expected_targets, list) or not expected_targets:
        raise ValidationError("The exact SDK retime target precondition must be a non-empty array.")
    live_by_type = {
        track_type: _read_live_items(conn, track_type=track_type)
        for track_type in ("video", "audio")
    }
    normalized: list[LiveItemRef] = []
    expected_ids: set[str] = set()
    expected_links: dict[str, set[str]] = {}
    for raw in expected_targets:
        try:
            item_id = str(raw["id"] or "")
            track_type = str(raw["trackType"])
            track_index = int(raw["trackIndex"])
            record_start = int(raw["recordStartFrame"])
            record_end = int(raw["recordEndFrame"])
            name = str(raw["name"])
            linked_ids = {str(value) for value in raw["linkedItemIds"]}
            source_start = int(raw["sourceStartFrame"])
            source_end = int(raw["sourceEndFrame"])
            source_origin = float(raw["sourceOriginFrame"]) if "sourceOriginFrame" in raw else None
        except (KeyError, TypeError, ValueError) as exc:
            raise ValidationError("The exact SDK retime target precondition is malformed.") from exc
        if (
            not item_id
            or item_id in expected_ids
            or track_type not in {"video", "audio"}
            or track_index < 1
            or record_end <= record_start
            or source_start < 0
            or source_end <= source_start
            or (source_origin is not None and (not math.isfinite(source_origin) or not source_start <= source_origin < source_end))
            or not name
            or "" in linked_ids
        ):
            raise ValidationError("The exact SDK retime target precondition is malformed.")
        expected_ids.add(item_id)
        expected_links[item_id] = linked_ids
        matches = [
            item
            for item in live_by_type[track_type]
            if item.item_id == item_id
            and item.track_index == track_index
            and item.name == name
            and item.start in _candidate_timeline_frames(conn, record_start)
            and item.end in _candidate_timeline_frames(conn, record_end)
        ]
        if len(matches) != 1:
            raise SdkMutationStaleRevision(
                "An exact SDK retime target changed before CutAgent CLI preflight.",
                details={
                    "track_type": track_type,
                    "track_index": track_index,
                    "record_start_frame": record_start,
                    "record_end_frame": record_end,
                    "name": name,
                },
            )
        matched = matches[0]
        normalized.append(
            LiveItemRef(
                track_type=matched.track_type,
                track_index=matched.track_index,
                name=matched.name,
                start=matched.start,
                duration=matched.duration,
                aliases=matched.aliases,
                item_id=matched.item_id,
                linked_item_ids=matched.linked_item_ids,
                source_start_frame=source_start,
                source_end_frame=source_end,
                source_origin_frame=source_origin,
            )
        )

    if any(item.linked_item_ids is None for item in normalized):
        raise SdkMutationStaleRevision("SDK retime linkage became unavailable before mutation.")
    actual_by_id = {str(item.item_id): set(item.linked_item_ids or ()) for item in normalized}
    if any(
        expected_links[item_id] != actual_by_id.get(item_id)
        or not expected_links[item_id].issubset(expected_ids)
        or any(item_id not in actual_by_id.get(linked_id, set()) for linked_id in expected_links[item_id])
        for item_id in expected_ids
    ):
        raise SdkMutationStaleRevision(
            "The exact SDK retime linked-media topology changed before mutation."
        )
    return normalized


def require_exact_sdk_transition_selection(
    conn,
    *,
    selected: dict[str, object],
    expected: object | None = None,
) -> dict[str, LiveItemRef | None]:
    """Revalidate one signed transition seam and its selected native items."""

    if expected is None:
        raw = os.getenv("CUTAGENT_CLI_SDK_TRANSITION_TARGETS")
        if not raw:
            if os.getenv("CUTAGENT_SDK_TIMELINE_GUARD"):
                raise ValidationError("SDK transition execution omitted exact native target custody.")
            return {
                "video": selected.get("video") if isinstance(selected.get("video"), LiveItemRef) else None,
                "audio": selected.get("audio") if isinstance(selected.get("audio"), LiveItemRef) else None,
            }
        try:
            expected = json.loads(raw)
        except (TypeError, ValueError) as exc:
            raise ValidationError("SDK transition target custody is malformed.") from exc
    if not isinstance(expected, dict) or set(expected) != {
        "outgoing", "incoming", "linkedAudioTargets", "editFrame", "placement", "scope"
    }:
        raise ValidationError("SDK transition target custody is malformed.")

    placement = expected.get("placement")
    scope = expected.get("scope")
    edit_frame = expected.get("editFrame")
    if placement not in {"start", "end", "both"} or scope not in {"linked", "video", "audio"} \
            or not isinstance(edit_frame, int) or isinstance(edit_frame, bool) or edit_frame < 0:
        raise ValidationError("SDK transition target custody is malformed.")
    linked_audio_targets = expected.get("linkedAudioTargets")
    if not isinstance(linked_audio_targets, list):
        raise ValidationError("SDK transition target custody is malformed.")
    raw_targets = [expected.get("outgoing"), expected.get("incoming"), *linked_audio_targets]
    if any(not isinstance(item, dict) for item in raw_targets):
        raise ValidationError("SDK transition target custody is malformed.")

    live_by_type = {
        track_type: _read_live_items(conn, track_type=track_type)
        for track_type in ("video", "audio")
    }
    normalized: list[LiveItemRef] = []
    expected_ids: set[str] = set()
    expected_links: dict[str, set[str]] = {}
    required_keys = {
        "id", "trackType", "trackIndex", "recordStartFrame", "recordEndFrame", "name", "linkedItemIds"
    }
    for raw_target in raw_targets:
        if set(raw_target) != required_keys \
                or any(isinstance(raw_target.get(key), bool) or not isinstance(raw_target.get(key), int)
                       for key in ("trackIndex", "recordStartFrame", "recordEndFrame")) \
                or not isinstance(raw_target.get("linkedItemIds"), list):
            raise ValidationError("SDK transition target custody is malformed.")
        try:
            item_id = str(raw_target["id"] or "")
            track_type = str(raw_target["trackType"])
            track_index = int(raw_target["trackIndex"])
            record_start = int(raw_target["recordStartFrame"])
            record_end = int(raw_target["recordEndFrame"])
            name = str(raw_target["name"])
            linked_ids = {str(value) for value in raw_target["linkedItemIds"]}
        except (TypeError, ValueError) as exc:
            raise ValidationError("SDK transition target custody is malformed.") from exc
        if not item_id or item_id in expected_ids or track_type not in {"video", "audio"} \
                or track_index < 1 or record_start < 0 or record_end <= record_start or not name \
                or "" in linked_ids or len(linked_ids) != len(raw_target["linkedItemIds"]):
            raise ValidationError("SDK transition target custody is malformed.")
        expected_ids.add(item_id)
        expected_links[item_id] = linked_ids
        matches = [
            item for item in live_by_type[track_type]
            if item.item_id == item_id
            and item.track_index == track_index
            and item.name == name
            and item.start in _candidate_timeline_frames(conn, record_start)
            and item.end in _candidate_timeline_frames(conn, record_end)
        ]
        if len(matches) != 1:
            raise SdkMutationStaleRevision(
                "An exact SDK transition target changed before CutAgent CLI preflight.",
                details={
                    "track_type": track_type, "track_index": track_index,
                    "record_start_frame": record_start, "record_end_frame": record_end,
                    "name": name,
                },
            )
        normalized.append(matches[0])

    if any(item.linked_item_ids is None for item in normalized):
        raise SdkMutationStaleRevision("SDK transition linkage became unavailable before mutation.")
    actual_by_id = {str(item.item_id): set(item.linked_item_ids or ()) for item in normalized}
    if any(
        expected_links[item_id] != actual_by_id.get(item_id)
        or any(
            linked_id in expected_ids and item_id not in actual_by_id.get(linked_id, set())
            for linked_id in expected_links[item_id]
        )
        for item_id in expected_ids
    ):
        raise SdkMutationStaleRevision("The exact SDK transition linked-media topology changed before mutation.")

    outgoing, incoming = normalized[:2]
    expected_type = "audio" if scope == "audio" else "video"
    if outgoing.track_type != expected_type or incoming.track_type != expected_type \
            or outgoing.track_index != incoming.track_index or outgoing.end != incoming.start \
            or incoming.start not in _candidate_timeline_frames(conn, edit_frame):
        raise SdkMutationStaleRevision("The exact SDK transition edit seam changed before mutation.")

    primary = outgoing if placement == "end" else incoming
    selected_video = selected.get("video")
    selected_audio = selected.get("audio")
    if isinstance(selected_audio, list):
        if len(selected_audio) > 1:
            raise ValidationError("SDK transition execution supports one exact linked audio track at a time.")
        selected_audio = selected_audio[0] if selected_audio else None
    selected_primary = selected_audio if expected_type == "audio" else selected_video
    if not isinstance(selected_primary, LiveItemRef) or selected_primary.item_id != primary.item_id:
        raise SdkMutationStaleRevision("SDK transition private selection drifted from its exact target.")

    linked_audio = normalized[2:]
    declared_audio_ids = {str(item.item_id) for item in linked_audio}
    primary_linked_audio_ids = set(outgoing.linked_item_ids or ()) | set(incoming.linked_item_ids or ())
    live_audio_ids = {str(item.item_id) for item in live_by_type["audio"]}
    if declared_audio_ids != primary_linked_audio_ids & live_audio_ids:
        raise SdkMutationStaleRevision("SDK transition linked-audio custody is incomplete.")
    if scope == "linked" and linked_audio:
        outgoing_audio = [item for item in linked_audio if item.item_id in set(outgoing.linked_item_ids or ())]
        incoming_audio = [item for item in linked_audio if item.item_id in set(incoming.linked_item_ids or ())]
        if len(outgoing_audio) != 1 or len(incoming_audio) != 1 \
                or outgoing_audio[0].track_index != incoming_audio[0].track_index \
                or outgoing_audio[0].end != incoming_audio[0].start \
                or incoming_audio[0].start not in _candidate_timeline_frames(conn, edit_frame) \
                or not isinstance(selected_audio, LiveItemRef) or selected_audio.item_id != (outgoing_audio[0] if placement == "end" else incoming_audio[0]).item_id:
            raise ValidationError("SDK linked transition requires one exact adjacent audio companion track.")
    elif scope == "linked" and selected_audio is not None:
        raise SdkMutationStaleRevision("SDK transition selected undeclared linked audio.")
    elif scope == "video" and selected_audio is not None:
        raise SdkMutationStaleRevision("SDK video-only transition selected an audio target.")
    elif scope == "audio" and selected_video is not None:
        raise SdkMutationStaleRevision("SDK audio-only transition selected a video target.")

    return {
        "video": selected_video if isinstance(selected_video, LiveItemRef) else None,
        "audio": selected_audio if isinstance(selected_audio, LiveItemRef) else None,
    }


def _ensure_unique(items: list[LiveItemRef], *, reason: str, details: dict[str, object]) -> LiveItemRef:
    if not items:
        clip_name = details.get("clip_name")
        if clip_name:
            track_type = str(details.get("track_type") or "clip")
            raise ClipNotFound(
                f"{track_type.capitalize()} clip '{clip_name}' not found on timeline.",
                details=details,
            )
        raise ClipNotFound(reason)
    if len(items) != 1:
        raise ValidationError(reason, details={**details, "matches": [asdict(item) for item in items]})
    return items[0]


def _find_by_name(conn, *, track_type: str, clip_name: str) -> list[LiveItemRef]:
    return [item for item in _read_live_items(conn, track_type=track_type) if _item_matches_name(item, clip_name)]


def _normalized_names(values: list[str] | tuple[str, ...] | set[str]) -> set[str]:
    normalized: set[str] = set()
    for value in values:
        try:
            text = str(value).strip()
        except Exception:
            continue
        if text:
            normalized.add(text.lower())
    return normalized


def _item_name_set(item: LiveItemRef) -> set[str]:
    return _normalized_names((item.name, *item.aliases))


def _item_matches_name(item: LiveItemRef, clip_name: str) -> bool:
    query = str(clip_name or "").strip()
    if not query:
        return False
    query_names = clip_ops._item_name_candidates(type("_Query", (), {"GetName": lambda self: query})())
    return bool(_item_name_set(item).intersection(_normalized_names(tuple(query_names) + (query,))))


def _items_share_name(left: LiveItemRef, right: LiveItemRef) -> bool:
    return bool(_item_name_set(left).intersection(_item_name_set(right)))


def _find_covering_frame(conn, *, track_type: str, record_frame: int) -> list[LiveItemRef]:
    matches: list[LiveItemRef] = []
    candidate_frames = _candidate_timeline_frames(conn, int(record_frame))
    for item in _read_live_items(conn, track_type=track_type):
        if any(item.start <= frame < item.end for frame in candidate_frames):
            matches.append(item)
    return matches


def _candidate_timeline_frames(conn, record_frame: int) -> set[int]:
    candidate_frames = {int(record_frame)}
    try:
        start_frame = int(conn.timeline.GetStartFrame())
    except Exception:
        start_frame = int(getattr(conn, "start_frame", 0) or 0)
    if start_frame:
        candidate_frames.add(int(record_frame) - start_frame)
    return candidate_frames


def _filter_items_covering_frame(conn, *, items: list[LiveItemRef], record_frame: int) -> list[LiveItemRef]:
    candidate_frames = _candidate_timeline_frames(conn, int(record_frame))
    return [item for item in items if any(item.start <= frame < item.end for frame in candidate_frames)]


def _sdk_link_identity_guard_active() -> bool:
    return bool(
        os.getenv("CUTAGENT_SDK_TIMELINE_GUARD")
        or os.getenv("CUTAGENT_SDK_EXPECTED_RETIME_TARGETS")
    )


def _match_linked_audio(
    conn, *, video_item: LiveItemRef | None, clip_name: str | None, record_frame: int | None
) -> LiveItemRef | list[LiveItemRef] | None:
    audio_items = _read_live_items(conn, track_type="audio")
    if video_item is not None:
        if _sdk_link_identity_guard_active():
            if not video_item.item_id or video_item.linked_item_ids is None:
                raise ValidationError(
                    "SDK linked timeline selection requires authoritative native item identity and linkage.",
                    details={"video": asdict(video_item)},
                )
            linked_ids = set(video_item.linked_item_ids)
            if not linked_ids:
                return []
            authoritative = [item for item in audio_items if item.item_id in linked_ids]
            if len(authoritative) != len(linked_ids) or {str(item.item_id) for item in authoritative} != linked_ids:
                raise ValidationError(
                    "SDK linked audio selection must resolve every authoritative native linked item.",
                    details={"video": asdict(video_item), "matches": [asdict(item) for item in authoritative]},
                )
            return sorted(authoritative, key=lambda item: (item.track_index, item.start, str(item.item_id)))
        exact = [
            item
            for item in audio_items
            if _items_share_name(item, video_item) and item.start == video_item.start and item.duration == video_item.duration
        ]
        if len(exact) == 1:
            return exact[0]
        if len(exact) > 1:
            raise ValidationError(
                "Linked audio selection is ambiguous for the selected video clip.",
                details={"video": asdict(video_item), "matches": [asdict(item) for item in exact]},
            )

    if clip_name:
        matches = [item for item in audio_items if _item_matches_name(item, clip_name)]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise ValidationError(
                "Audio clip selection is ambiguous.",
                details={"clip_name": clip_name, "matches": [asdict(item) for item in matches]},
            )

    if record_frame is not None:
        matches = _find_covering_frame(conn, track_type="audio", record_frame=record_frame)
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise ValidationError(
                "Audio clip selection is ambiguous at the requested timeline position.",
                details={"record_frame": record_frame, "matches": [asdict(item) for item in matches]},
            )

    return None


def _current_video_item(conn) -> LiveItemRef:
    current = clip_ops.get_current_item(conn)
    if current is None:
        raise ClipNotFound("Could not resolve the current timeline item.")

    try:
        current_name = str(current.GetName() or "")
        current_start = int(current.GetStart())
        current_duration = int(current.GetEnd()) - int(current.GetStart())
    except Exception as exc:
        raise ValidationError("Could not resolve the current timeline item.", details={"error": str(exc)}) from exc

    matches = [
        item
        for item in _read_live_items(conn, track_type="video")
        if item.name == current_name and item.start == current_start and item.duration == current_duration
    ]
    if matches:
        return _ensure_unique(
            matches,
            reason="Current timeline item selection is ambiguous.",
            details={"track_type": "video", "name": current_name, "start": current_start, "duration": current_duration},
        )

    return LiveItemRef(
        track_type="video",
        track_index=1,
        name=current_name,
        start=current_start,
        duration=current_duration,
    )


def resolve_video_group(
    conn,
    *,
    clip_name: str | None = None,
    track: int | None = None,
    at: str | None = None,
) -> dict[str, LiveItemRef]:
    record_frame = parse_record_frame(str(at), conn.fps, conn.start_frame) if at else None

    normalized_track = None
    if track is not None:
        try:
            normalized_track = int(track)
        except (TypeError, ValueError) as exc:
            raise ValidationError(
                "Video track must be a positive integer.",
                details={"track": track, "minimum": 1},
            ) from exc
        track_count = int(conn.timeline.GetTrackCount("video") or 0)
        if normalized_track < 1 or normalized_track > track_count:
            raise ValidationError(
                "Video track is out of range.",
                details={"track": normalized_track, "minimum": 1, "track_count": track_count},
            )

    if clip_name or record_frame is not None or normalized_track is not None:
        matches = _read_live_items(conn, track_type="video")
        if clip_name:
            matches = [item for item in matches if _item_matches_name(item, clip_name)]
        if normalized_track is not None:
            matches = [item for item in matches if item.track_index == normalized_track]
        if record_frame is not None:
            matches = _filter_items_covering_frame(conn, items=matches, record_frame=record_frame)

        selector_details: dict[str, object] = {"track_type": "video"}
        if clip_name:
            selector_details["clip_name"] = clip_name
        if normalized_track is not None:
            selector_details["track"] = normalized_track
        if record_frame is not None:
            selector_details["at"] = at
            selector_details["record_frame"] = record_frame
        return {
            "video": _ensure_unique(
                matches,
                reason="Video clip selection is ambiguous for the requested selector.",
                details=selector_details,
            )
        }

    return {"video": _current_video_item(conn)}


def resolve_linked_av_group(
    conn, *, clip_name: str | None = None, at: str | None = None, track: int | None = None
) -> dict[str, LiveItemRef | list[LiveItemRef] | None]:
    record_frame = parse_record_frame(str(at), conn.fps, conn.start_frame) if at else None

    if clip_name or record_frame is not None or track is not None:
        video_item = resolve_video_group(conn, clip_name=clip_name, track=track, at=at)["video"]
        audio_item = _match_linked_audio(conn, video_item=video_item, clip_name=clip_name, record_frame=record_frame)
        return {"video": video_item, "audio": audio_item}

    video_item = _current_video_item(conn)
    audio_item = _match_linked_audio(conn, video_item=video_item, clip_name=None, record_frame=video_item.start)
    return {"video": video_item, "audio": audio_item}


def resolve_audio_group(conn, *, clip_name: str | None = None, at: str | None = None, track: int | None = None) -> dict[str, LiveItemRef]:
    record_frame = parse_record_frame(str(at), conn.fps, conn.start_frame) if at else None

    if clip_name:
        audio_matches = _find_by_name(conn, track_type="audio", clip_name=clip_name)
        if track is not None:
            audio_matches = [item for item in audio_matches if item.track_index == int(track)]
        if record_frame is not None:
            audio_matches = _filter_items_covering_frame(conn, items=audio_matches, record_frame=record_frame)
        reason = (
            "Audio clip selection is ambiguous at the requested timeline position."
            if record_frame is not None
            else "Audio clip selection is ambiguous."
        )
        details: dict[str, object] = {"clip_name": clip_name, "track_type": "audio"}
        if track is not None:
            details["track"] = int(track)
        if record_frame is not None:
            details["at"] = at
            details["record_frame"] = record_frame
        return {"audio": _ensure_unique(audio_matches, reason=reason, details=details)}

    if record_frame is not None:
        audio_matches = _find_covering_frame(conn, track_type="audio", record_frame=record_frame)
        if track is not None:
            audio_matches = [item for item in audio_matches if item.track_index == int(track)]
        if audio_matches:
            return {
                "audio": _ensure_unique(
                    audio_matches,
                    reason="Audio clip selection is ambiguous at the requested timeline position.",
                    details={"at": at, "record_frame": record_frame, "track_type": "audio", **({"track": int(track)} if track is not None else {})},
                )
            }

    selection = resolve_linked_av_group(conn, clip_name=clip_name, at=at)
    audio_item = selection.get("audio")
    if audio_item is None:
        raise ClipNotFound("Could not resolve a linked audio timeline item for the selected clip.")
    return {"audio": audio_item}


def _current_record_frame(conn) -> int:
    from . import timeline_ops

    playhead = timeline_ops.get_playhead(conn)
    return int(playhead.get("frame") or 0)


def resolve_record_frame(conn, *, at: str | None = None) -> int:
    if at is None or str(at).strip().lower() == "current":
        return _current_record_frame(conn)
    return parse_record_frame(str(at), conn.fps, conn.start_frame)


def resolve_adjacent_av_cut(conn, *, cut_at: str | None = None, track: int = 0) -> dict[str, object]:
    record_frame = resolve_record_frame(conn, at=cut_at)
    requested_track = int(track or 0)
    if requested_track < 0:
        raise ValidationError(
            "--track must be 0 for auto-detect or a positive video track index.",
            details={"track": track},
            recoverability="not_applicable",
        )

    candidate_frames = _candidate_timeline_frames(conn, record_frame)
    video_items = _read_live_items(conn, track_type="video")
    if requested_track:
        video_items = [item for item in video_items if item.track_index == requested_track]

    pairs: list[tuple[int, LiveItemRef, LiveItemRef]] = []
    for frame in sorted(candidate_frames):
        outgoing = [item for item in video_items if item.end == frame]
        incoming = [item for item in video_items if item.start == frame]
        for left in outgoing:
            for right in incoming:
                if left.track_index == right.track_index:
                    pairs.append((frame, left, right))

    if not pairs:
        raise ClipNotFound(
            "No adjacent video cut was found at the requested timeline position.",
            details={
                "cut_at": cut_at or "current",
                "record_frame": record_frame,
                "candidate_frames": sorted(candidate_frames),
                "track": requested_track,
            },
        )
    if len(pairs) != 1:
        raise ValidationError(
            "Adjacent cut selection is ambiguous.",
            details={
                "cut_at": cut_at or "current",
                "record_frame": record_frame,
                "candidate_frames": sorted(candidate_frames),
                "track": requested_track,
                "matches": [
                    {
                        "timeline_frame": frame,
                        "track_index": outgoing.track_index,
                        "outgoing": asdict(outgoing),
                        "incoming": asdict(incoming),
                    }
                    for frame, outgoing, incoming in pairs
                ],
            },
        )

    timeline_frame, outgoing_video, incoming_video = pairs[0]
    return {
        "cut_at": cut_at or "current",
        "record_frame": record_frame,
        "timeline_frame": timeline_frame,
        "track_index": outgoing_video.track_index,
        "outgoing": {
            "video": outgoing_video,
            "audio": _match_linked_audio(conn, video_item=outgoing_video, clip_name=None, record_frame=record_frame),
        },
        "incoming": {
            "video": incoming_video,
            "audio": _match_linked_audio(conn, video_item=incoming_video, clip_name=None, record_frame=record_frame),
        },
    }
