"""Archive-backed DB transition insertion helpers."""

from __future__ import annotations

from dataclasses import asdict
import re
import sqlite3
import struct
import time
import uuid

from ..errors import ValidationError
from ..fixtures.db_workaround_payloads import TRANSITION_REGISTRY, TransitionRegistryEntry
from ..utils.time_ref import parse_record_frame
from .db_session import next_db_index, rebuild_track_item_indices
from .db_timeline_rows import find_ti_item_row, insert_row, update_row
from . import db_timeline_selection
from .db_timeline_selection import LiveItemRef

_FUSION_COMP_FIELDS_PREFIX = bytes.fromhex(
    "000000010000000200000016004C006100730074004D006F006400540069006D00650000000400000000"
)
_FUSION_COMP_FIELDS_SUFFIX = bytes.fromhex(
    "0000002C0046007500730069006F006E00530074006100720074004600720061006D0065004F00660066007300650074000000020000000000"
)
DEFAULT_TRANSITION_DURATION_FRAMES = 24


def _default_transition_duration_frames(item: LiveItemRef) -> int:
    item_duration = int(item.duration)
    if item_duration <= 0:
        raise ValidationError(
            "Transition default duration requires a positive target clip duration.",
            details={"clip": asdict(item), "default_duration_frames": DEFAULT_TRANSITION_DURATION_FRAMES},
        )
    return min(DEFAULT_TRANSITION_DURATION_FRAMES, item_duration)


def default_transition_duration_frames_for_targets(
    *,
    video_item: LiveItemRef | None,
    audio_item: LiveItemRef | None,
) -> int:
    targets = [item for item in (video_item, audio_item) if item is not None]
    if not targets:
        raise ValidationError(
            "Transition default duration requires a deterministic target clip.",
            details={"default_duration_frames": DEFAULT_TRANSITION_DURATION_FRAMES},
        )
    return min(_default_transition_duration_frames(item) for item in targets)


def normalize_transition_name(name: str) -> str:
    normalized = str(name or "").strip().lower().replace("_", "-").replace(" ", "-")
    aliases = {
        "cross-dissolve": "cross-dissolve",
        "crossfade": "cross-dissolve",
        "cross-fade": "cross-dissolve",
        "smooth-cut": "smooth-cut",
        "cross-fade-0db": "cross-fade-0db",
        "cross-fade-3db": "cross-fade-3db",
        "cross-fade+3db": "cross-fade+3db",
        "rotate-90": "rotate-90",
        "zoom-in": "zoom-in",
    }
    resolved = aliases.get(normalized)
    if resolved is None or resolved not in TRANSITION_REGISTRY:
        raise ValidationError(
            "Unsupported archive-backed transition type.",
            details={"transition_type": name, "supported": sorted(TRANSITION_REGISTRY)},
        )
    return resolved


def build_fusion_composition_fields_blob(last_mod_time: int) -> bytes:
    return _FUSION_COMP_FIELDS_PREFIX + struct.pack(">I", int(last_mod_time) & 0xFFFFFFFF) + _FUSION_COMP_FIELDS_SUFFIX


def _normalize_scope(scope: str | None) -> str:
    normalized = str(scope or "auto").strip().lower()
    if normalized not in {"auto", "linked", "video", "audio"}:
        raise ValidationError("Transition scope must be auto, linked, video, or audio.", details={"scope": scope})
    return normalized


def resolve_transition_selection_scope(transition_name: str, scope: str | None = None) -> str:
    key = normalize_transition_name(transition_name)
    normalized_scope = _normalize_scope(scope)
    if normalized_scope != "auto":
        return normalized_scope
    if key == "cross-dissolve":
        return "linked"
    if key == "smooth-cut":
        return "linked"
    if TRANSITION_REGISTRY[key].category == "audio_builtin":
        return "audio"
    return "video"


def _transition_positions(
    item: LiveItemRef,
    *,
    duration_frames: int,
    placement: str,
    at_frame: int | None = None,
) -> list[tuple[int, int]]:
    normalized = str(placement or "both").strip().lower()
    if normalized not in {"start", "end", "both"}:
        raise ValidationError("Transition placement must be start, end, or both.", details={"placement": placement})
    if duration_frames <= 0:
        raise ValidationError("Transition duration must be greater than 0.", details={"duration_frames": duration_frames})
    positions: list[tuple[int, int]] = []
    if normalized == "both" and at_frame is not None:
        seam_frame = int(at_frame)
        if not (item.start <= seam_frame <= item.end):
            raise ValidationError(
                "Transition --at must be inside or on the boundary of the selected clip.",
                details={"clip": asdict(item), "at_frame": seam_frame},
            )
        return [(seam_frame - (int(duration_frames) // 2), 2)]
    if normalized in {"start", "both"}:
        positions.append((int(item.start), 1))
    if normalized in {"end", "both"}:
        positions.append((int(item.end) - int(duration_frames), 3))
    return positions


def _duration_from_spec(item: LiveItemRef, spec: object | None, formula: object | None = None) -> int:
    if formula is not None:
        normalized = str(formula or "").strip().lower().replace("_", "-")
        if normalized == "quarter-clamped":
            return max(4, min(12, int(item.duration) // 4))
        raise ValidationError(
            "Unsupported transition duration formula.",
            details={"duration_formula": formula, "supported": ["quarter-clamped"]},
        )
    if spec is None:
        return _default_transition_duration_frames(item)
    try:
        text = str(spec).strip().lower()
        value = int(text[:-1] if text.endswith("f") else text)
    except Exception as exc:
        raise ValidationError("Transition batch duration must be an integer frame count.", details={"duration": spec}) from exc
    if value <= 0:
        raise ValidationError("Transition duration must be greater than 0.", details={"duration_frames": value})
    return value


def _read_items_for_scope(conn, *, scope: str, track_type: str | None = None) -> list[LiveItemRef]:
    if track_type is not None:
        return db_timeline_selection._read_live_items(conn, track_type=track_type)
    if scope == "audio":
        return db_timeline_selection._read_live_items(conn, track_type="audio")
    return db_timeline_selection._read_live_items(conn, track_type="video")


def _target_from_exact_entry(
    entry: dict[str, object],
    *,
    scope: str,
    items: list[LiveItemRef],
) -> dict[str, LiveItemRef | None] | None:
    """Build a deterministic target from exact timing after validating the live item still exists."""
    if scope not in {"video", "audio"}:
        return None
    if entry.get("item_id") is not None or entry.get("name_regex") is not None or entry.get("select_name_regex") is not None:
        return None
    if entry.get("record_frame") is not None or entry.get("at") is not None:
        return None
    if entry.get("track_index") is None or entry.get("start_frame") is None or entry.get("end_frame") is None:
        return None

    track_type = str(entry.get("track_type") or ("audio" if scope == "audio" else "video")).strip().lower()
    if track_type != scope:
        return None

    clip_name = str(entry.get("clip") or entry.get("name") or "").strip()
    if not clip_name:
        return None

    try:
        start = int(entry["start_frame"])
        duration = int(entry["end_frame"]) - start
        track_index = int(entry["track_index"])
    except Exception:
        return None
    if duration <= 0 or track_index <= 0:
        return None

    expected = LiveItemRef(
        track_type=track_type,
        track_index=track_index,
        name=clip_name,
        start=start,
        duration=duration,
        aliases=(clip_name,),
    )
    matches = [
        item
        for item in items
        if item.track_type == track_type
        and item.track_index == track_index
        and item.start == start
        and item.end == expected.end
        and db_timeline_selection._item_matches_name(item, clip_name)
    ]
    if not matches:
        raise ValidationError(
            "Transition batch target did not match any timeline item.",
            details={"entry": entry, "expected": asdict(expected)},
        )
    if len(matches) != 1:
        raise ValidationError(
            "Transition batch target is ambiguous.",
            details={"entry": entry, "matches": [asdict(item) for item in matches]},
        )

    item = matches[0]
    return {"video": item, "audio": None} if track_type == "video" else {"video": None, "audio": item}


def _target_from_entry(
    conn,
    entry: dict[str, object],
    *,
    scope: str,
    item_cache: dict[tuple[str, str | None], list[LiveItemRef]] | None = None,
) -> dict[str, LiveItemRef | None]:
    track_type = str(entry.get("track_type") or ("audio" if scope == "audio" else "video")).strip().lower()
    if track_type not in {"video", "audio"}:
        raise ValidationError("Transition batch track_type must be video or audio.", details={"track_type": track_type})

    cache_key = (scope, track_type)
    if item_cache is not None:
        if cache_key not in item_cache:
            item_cache[cache_key] = _read_items_for_scope(conn, scope=scope, track_type=track_type)
        items = list(item_cache[cache_key])
    else:
        items = _read_items_for_scope(conn, scope=scope, track_type=track_type)

    exact_target = _target_from_exact_entry(entry, scope=scope, items=items)
    if exact_target is not None:
        return exact_target
    if entry.get("item_id") is not None:
        # The DaVinci Resolve scripting timeline item API does not expose stable item ids in every runtime.
        # Keep this selector explicit instead of pretending a lossy match is deterministic.
        raise ValidationError("item_id transition batch selection is not available in the live API preflight.")

    clip_name = entry.get("clip") or entry.get("name")
    if clip_name is not None:
        items = [item for item in items if db_timeline_selection._item_matches_name(item, str(clip_name))]

    name_regex = entry.get("name_regex") or entry.get("select_name_regex")
    if name_regex is not None:
        try:
            pattern = re.compile(str(name_regex))
        except re.error as exc:
            raise ValidationError("Invalid transition batch name_regex.", details={"name_regex": name_regex, "error": str(exc)}) from exc
        items = [item for item in items if pattern.search(item.name) or any(pattern.search(alias) for alias in item.aliases)]

    if entry.get("track_index") is not None:
        track_index = int(entry["track_index"])
        items = [item for item in items if item.track_index == track_index]

    start_frame = entry.get("start_frame")
    end_frame = entry.get("end_frame")
    if start_frame is not None:
        items = [item for item in items if item.start == int(start_frame)]
    if end_frame is not None:
        items = [item for item in items if item.end == int(end_frame)]

    record_frame = entry.get("record_frame") or entry.get("at")
    if record_frame is not None:
        parsed = parse_record_frame(str(record_frame), conn.fps, conn.start_frame)
        items = [item for item in items if item.start <= parsed < item.end]

    if not items:
        raise ValidationError("Transition batch target did not match any timeline item.", details={"entry": entry})
    if len(items) != 1:
        raise ValidationError(
            "Transition batch target is ambiguous.",
            details={"entry": entry, "matches": [asdict(item) for item in items]},
        )

    item = items[0]
    if scope == "audio" or item.track_type == "audio":
        return {"video": None, "audio": item}
    if scope == "linked":
        audio_item = db_timeline_selection._match_linked_audio(conn, video_item=item, clip_name=str(clip_name) if clip_name else None, record_frame=item.start)
        return {"video": item, "audio": audio_item}
    return {"video": item, "audio": None}


def _plan_from_items(
    entry: dict[str, object],
    *,
    video_item: LiveItemRef | None,
    audio_item: LiveItemRef | None,
    transition_name: str,
    scope: str,
    placement: str,
) -> dict[str, object]:
    target_item = video_item or audio_item
    if target_item is None:
        raise ValidationError("Transition batch target could not be resolved.", details={"entry": entry})
    duration_spec = entry.get("duration_frames", entry.get("duration"))
    duration_formula = entry.get("duration_formula")
    duration_frames = (
        default_transition_duration_frames_for_targets(video_item=video_item, audio_item=audio_item)
        if duration_spec is None and duration_formula is None
        else _duration_from_spec(target_item, duration_spec, duration_formula)
    )
    at_frame = int(entry["at_frame"]) if entry.get("at_frame") is not None else None
    positions = []
    if video_item is not None:
        positions.extend({"track_type": video_item.track_type, "track_index": video_item.track_index, "start": start, "duration": duration_frames} for start, _alignment in _transition_positions(video_item, duration_frames=duration_frames, placement=placement, at_frame=at_frame))
    if audio_item is not None:
        positions.extend({"track_type": audio_item.track_type, "track_index": audio_item.track_index, "start": start, "duration": duration_frames} for start, _alignment in _transition_positions(audio_item, duration_frames=duration_frames, placement=placement, at_frame=at_frame))
    return {
        "index": int(entry.get("index", 0)),
        "entry": entry,
        "video_item": video_item,
        "audio_item": audio_item,
        "transition_name": transition_name,
        "duration_frames": duration_frames,
        "placement": placement,
        "scope": scope,
        "at_frame": at_frame,
        "target": asdict(target_item),
        "preflight": {
            "target": asdict(target_item),
            "transition_type": transition_name,
            "duration_frames": duration_frames,
            "placement": placement,
            "scope": scope,
            "positions": positions,
        },
    }


def plan_transition_batch(
    conn,
    entries: list[dict[str, object]],
    *,
    transition_name: str,
    placement: str = "both",
    scope: str = "video",
) -> list[dict[str, object]]:
    """Resolve all transition batch targets before a DB mutation starts."""
    key = normalize_transition_name(transition_name)
    normalized_scope = resolve_transition_selection_scope(key, scope)
    plans: list[dict[str, object]] = []
    item_cache: dict[tuple[str, str | None], list[LiveItemRef]] = {}
    for entry in entries:
        entry_transition = normalize_transition_name(str(entry.get("transition_type") or entry.get("type") or key))
        entry_scope = resolve_transition_selection_scope(entry_transition, str(entry.get("scope") or normalized_scope))
        entry_placement = str(entry.get("placement") or placement or "both").strip().lower()
        targets = _target_from_entry(conn, entry, scope=entry_scope, item_cache=item_cache)
        plans.append(
            _plan_from_items(
                entry,
                video_item=targets.get("video"),
                audio_item=targets.get("audio"),
                transition_name=entry_transition,
                scope=entry_scope,
                placement=entry_placement,
            )
        )
    return plans


def select_transition_batch_by_regex(
    conn,
    *,
    name_regex: str,
    transition_name: str,
    duration_formula: str | None = None,
    duration_frames: int | None = None,
    track_type: str = "video",
    track_index: int | None = None,
    placement: str = "both",
    scope: str = "video",
) -> list[dict[str, object]]:
    """Build batch entries from a regex selector over live timeline items."""
    pattern = re.compile(str(name_regex))
    entries: list[dict[str, object]] = []
    for item in _read_items_for_scope(conn, scope=scope, track_type=track_type):
        if track_index is not None and item.track_index != int(track_index):
            continue
        if not (pattern.search(item.name) or any(pattern.search(alias) for alias in item.aliases)):
            continue
        entry: dict[str, object] = {
            "index": len(entries),
            "track_type": item.track_type,
            "track_index": item.track_index,
            "start_frame": item.start,
            "end_frame": item.end,
            "transition_type": transition_name,
            "placement": placement,
            "scope": scope,
        }
        if duration_formula:
            entry["duration_formula"] = duration_formula
        elif duration_frames is not None:
            entry["duration_frames"] = int(duration_frames)
        entries.append(entry)
    return entries


def plan_transition_batch_by_regex(
    conn,
    *,
    name_regex: str,
    transition_name: str,
    duration_formula: str | None = None,
    duration_frames: int | None = None,
    track_type: str = "video",
    track_index: int | None = None,
    placement: str = "both",
    scope: str = "video",
) -> list[dict[str, object]]:
    """Build fully resolved transition plans from a regex selector.

    Selector mode already reads live timeline items to discover matching clips.
    Resolve those same item references directly instead of re-reading the whole
    timeline once per generated entry during generic batch preflight.
    """
    pattern = re.compile(str(name_regex))
    entry_transition = normalize_transition_name(transition_name)
    entry_scope = resolve_transition_selection_scope(entry_transition, scope)
    plans: list[dict[str, object]] = []
    for item in _read_items_for_scope(conn, scope=entry_scope, track_type=track_type):
        if track_index is not None and item.track_index != int(track_index):
            continue
        if not (pattern.search(item.name) or any(pattern.search(alias) for alias in item.aliases)):
            continue
        entry: dict[str, object] = {
            "index": len(plans),
            "track_type": item.track_type,
            "track_index": item.track_index,
            "start_frame": item.start,
            "end_frame": item.end,
            "transition_type": entry_transition,
            "placement": placement,
            "scope": entry_scope,
        }
        if duration_formula:
            entry["duration_formula"] = duration_formula
        elif duration_frames is not None:
            entry["duration_frames"] = int(duration_frames)

        if entry_scope == "audio" or item.track_type == "audio":
            video_item = None
            audio_item = item
        elif entry_scope == "linked":
            video_item = item
            audio_item = db_timeline_selection._match_linked_audio(
                conn,
                video_item=item,
                clip_name=None,
                record_frame=item.start,
            )
        else:
            video_item = item
            audio_item = None
        plans.append(
            _plan_from_items(
                entry,
                video_item=video_item,
                audio_item=audio_item,
                transition_name=entry_transition,
                scope=entry_scope,
                placement=placement,
            )
        )
    return plans


def _transition_row_exists(
    cursor: sqlite3.Cursor,
    *,
    track_id: str,
    start_frame: int,
    duration_frames: int,
    entry: TransitionRegistryEntry,
) -> dict[str, object] | None:
    cursor.execute(
        """
        SELECT Sm2TiItem_id, PrettyType, Name, Start, Duration, Sm2TiTrack_id
        FROM Sm2TiItem
        WHERE DbType = 'Sm2TiTransition'
          AND Sm2TiTrack_id = ?
          AND Start = ?
          AND Duration = ?
          AND PrettyType = ?
        """,
        (str(track_id), str(int(start_frame)), str(int(duration_frames)), entry.pretty_type),
    )
    row = cursor.fetchone()
    return dict(row) if row is not None else None


def _smooth_cut_position(item: LiveItemRef, *, duration_frames: int, at_frame: int) -> tuple[int, int]:
    if not (item.start < int(at_frame) < item.end):
        raise ValidationError(
            "Smooth Cut requires --at inside the selected clip span.",
            details={"clip": asdict(item), "at_frame": at_frame},
        )
    return int(at_frame) - (int(duration_frames) // 2), 2


def _split_in_value(current_in: object, offset_frames: int) -> str | None:
    if current_in in (None, ""):
        return str(int(offset_frames))
    value = str(current_in)
    if value.isdigit():
        return str(int(value) + int(offset_frames))
    return value


def _split_clip_row(
    cursor: sqlite3.Cursor,
    *,
    row: dict[str, object],
    item: LiveItemRef,
    at_frame: int,
) -> dict[str, object]:
    lead_duration = int(at_frame) - int(item.start)
    tail_duration = int(item.end) - int(at_frame)
    if lead_duration <= 0 or tail_duration <= 0:
        raise ValidationError(
            "Smooth Cut requires a cut point strictly inside the target clip.",
            details={"clip": asdict(item), "at_frame": at_frame},
        )

    tail_id = str(uuid.uuid4())
    tail_row = dict(row)
    tail_row["Sm2TiItem_id"] = tail_id
    tail_row["Start"] = str(at_frame)
    tail_row["Duration"] = str(tail_duration)
    tail_row["In"] = _split_in_value(row.get("In"), lead_duration)
    insert_row(cursor, "Sm2TiItem", tail_row)
    insert_row(
        cursor,
        "Sm2TiItem_Sm2TiTrack",
        {
            "DbOwner": str(row["Sm2TiTrack_id"]),
            "DbAssociate": tail_id,
            "DbPropertyName": "Items",
            "DbIndex": next_db_index(
                cursor,
                table_name="Sm2TiItem_Sm2TiTrack",
                owner_value=str(row["Sm2TiTrack_id"]),
                property_name="Items",
            ),
        },
    )
    update_row(cursor, "Sm2TiItem", "Sm2TiItem_id", row["Sm2TiItem_id"], {"Duration": str(lead_duration)})
    return {
        "original_item_id": row["Sm2TiItem_id"],
        "tail_item_id": tail_id,
        "lead_duration": lead_duration,
        "tail_duration": tail_duration,
        "tail_start": at_frame,
    }


def _insert_composition_table(
    cursor: sqlite3.Cursor,
    *,
    item_id: str,
    db_saved_time: int,
) -> str:
    comp_id = str(uuid.uuid4())
    insert_row(
        cursor,
        "Sm2TiCompositionTable",
        {
            "Sm2TiCompositionTable_id": comp_id,
            "DbType": "Sm2TiCompositionTable",
            "FieldsBlob": build_fusion_composition_fields_blob(db_saved_time),
            "DbSavedTime": int(db_saved_time),
            "CompositionBA": None,
            "ActiveCompositionIdx": 0,
            "Sm2TiItem_id": item_id,
        },
    )
    return comp_id


def _insert_transition_row(
    cursor: sqlite3.Cursor,
    *,
    track_id: str,
    start_frame: int,
    duration_frames: int,
    alignment: int,
    entry: TransitionRegistryEntry,
) -> dict[str, object]:
    item_id = str(uuid.uuid4())
    db_saved_time = int(time.time())
    composition_table = None
    if entry.category == "fusion_transition":
        composition_table = _insert_composition_table(cursor, item_id=item_id, db_saved_time=db_saved_time)
    insert_row(
        cursor,
        "Sm2TiItem",
        {
            "Sm2TiItem_id": item_id,
            "DbType": "Sm2TiTransition",
            "Name": entry.name,
            "PrettyType": entry.pretty_type,
            "Start": str(int(start_frame)),
            "Duration": str(int(duration_frames)),
            "AlignmentType": int(alignment),
            "Position": int(alignment),
            "FieldsBlob": bytes.fromhex(entry.fields_hex),
            "EffectFiltersBA": bytes.fromhex(entry.effect_hex) if entry.effect_hex else None,
            "CompositionTable": composition_table,
            "Sm2TiTrack_id": track_id,
        },
    )
    insert_row(
        cursor,
        "Sm2TiItem_Sm2TiTrack",
        {
            "DbOwner": track_id,
            "DbAssociate": item_id,
            "DbPropertyName": "Items",
            "DbIndex": next_db_index(
                cursor,
                table_name="Sm2TiItem_Sm2TiTrack",
                owner_value=track_id,
                property_name="Items",
            ),
        },
    )
    return {
        "item_id": item_id,
        "track_id": track_id,
        "start": int(start_frame),
        "duration": int(duration_frames),
        "alignment": int(alignment),
        "pretty_type": entry.pretty_type,
        "composition_table": composition_table,
    }


def add_transition_rows(
    cursor: sqlite3.Cursor,
    *,
    video_item: LiveItemRef | None,
    audio_item: LiveItemRef | None,
    transition_name: str,
    duration_frames: int,
    placement: str,
    scope: str = "auto",
    timeline_name: str | None = None,
    at_frame: int | None = None,
    skip_existing: bool = False,
) -> dict[str, object]:
    key = normalize_transition_name(transition_name)
    entry = TRANSITION_REGISTRY[key]
    normalized_scope = _normalize_scope(scope)
    if key == "smooth-cut" and placement != "both":
        raise ValidationError(
            "Smooth Cut is centered-only in the DB route. Use --placement both with an explicit --at cut point.",
            details={"placement": placement},
        )

    applied_scope = normalized_scope
    video_entry: TransitionRegistryEntry | None = None
    audio_entry: TransitionRegistryEntry | None = None

    if key == "cross-dissolve":
        if normalized_scope == "auto":
            applied_scope = "linked"
            want_video = True
            want_audio = audio_item is not None
        else:
            want_video = normalized_scope in {"linked", "video"}
            want_audio = normalized_scope in {"linked", "audio"}
            applied_scope = normalized_scope
        video_entry = entry if want_video else None
        audio_entry = TRANSITION_REGISTRY["cross-fade-0db"] if want_audio else None
    elif entry.category == "audio_builtin":
        if normalized_scope == "video":
            raise ValidationError(
                "Audio crossfades cannot target the video scope.",
                details={"transition_type": key, "scope": scope},
            )
        if audio_item is None:
            raise ValidationError(
                "Audio crossfades require a linked audio item.",
                details={"transition_type": key, "scope": scope},
            )
        applied_scope = "audio" if normalized_scope == "auto" else normalized_scope
        video_entry = None
        audio_entry = entry
    else:
        if normalized_scope == "audio":
            raise ValidationError(
                "Video transitions cannot target the audio-only scope.",
                details={"transition_type": key, "scope": scope},
            )
        applied_scope = "linked" if normalized_scope == "auto" and key == "smooth-cut" and audio_item is not None else (
            "video" if normalized_scope == "auto" else normalized_scope
        )
        video_entry = entry
        audio_entry = None

    if video_entry is not None and video_item is None:
        raise ValidationError(
            "Transition requires a deterministic video target.",
            details={"transition_type": key, "scope": scope},
        )
    if audio_entry is not None and audio_item is None:
        raise ValidationError(
            "Transition requires a deterministic audio target.",
            details={"transition_type": key, "scope": scope},
        )

    video_row = (
        find_ti_item_row(cursor, item=video_item, db_type="Sm2TiVideoClip", timeline_name=timeline_name)
        if video_item is not None
        else None
    )
    audio_row = (
        find_ti_item_row(cursor, item=audio_item, db_type="Sm2TiAudioClip", timeline_name=timeline_name)
        if audio_item is not None
        else None
    )

    if key == "smooth-cut":
        if normalized_scope == "audio":
            raise ValidationError("Smooth Cut cannot target audio-only scope.", details={"scope": scope})
        if at_frame is None:
            raise ValidationError("Smooth Cut requires --at so the cut point is deterministic.")
        if video_row is None or video_item is None:
            raise ValidationError("Smooth Cut requires a video clip target.", details={"transition_type": key, "scope": scope})
        split_video = _split_clip_row(cursor, row=video_row, item=video_item, at_frame=at_frame)
        split_audio = (
            _split_clip_row(cursor, row=audio_row, item=audio_item, at_frame=at_frame)
            if normalized_scope in {"auto", "linked"} and audio_row and audio_item
            else None
        )
        video_positions = [_smooth_cut_position(video_item, duration_frames=duration_frames, at_frame=at_frame)]
        audio_positions: list[tuple[int, int]] = []
    else:
        split_video = None
        split_audio = None
        video_positions = (
            _transition_positions(video_item, duration_frames=duration_frames, placement=placement, at_frame=at_frame)
            if video_item is not None
            else []
        )
        audio_positions = (
            _transition_positions(audio_item, duration_frames=duration_frames, placement=placement, at_frame=at_frame)
            if audio_item is not None
            else []
        )

    inserted_video = []
    skipped_existing: list[dict[str, object]] = []
    if video_entry is not None and video_row is not None:
        for start_frame, alignment in video_positions:
            existing = _transition_row_exists(
                cursor,
                track_id=str(video_row["Sm2TiTrack_id"]),
                start_frame=start_frame,
                duration_frames=duration_frames,
                entry=video_entry,
            )
            if existing and skip_existing:
                skipped_existing.append(
                    {
                        "reason": "already_exists",
                        "track_type": video_item.track_type if video_item is not None else "video",
                        "track_index": video_item.track_index if video_item is not None else None,
                        "start": int(start_frame),
                        "duration": int(duration_frames),
                        "existing": existing,
                    }
                )
                continue
            inserted_video.append(
                _insert_transition_row(
                    cursor,
                    track_id=str(video_row["Sm2TiTrack_id"]),
                    start_frame=start_frame,
                    duration_frames=duration_frames,
                    alignment=alignment,
                    entry=video_entry,
                )
            )
    for row in inserted_video:
        if video_item is not None:
            row["track_type"] = video_item.track_type
            row["track_index"] = video_item.track_index

    inserted_audio = []
    if audio_entry is not None and audio_row is not None:
        for start_frame, alignment in audio_positions:
            existing = _transition_row_exists(
                cursor,
                track_id=str(audio_row["Sm2TiTrack_id"]),
                start_frame=start_frame,
                duration_frames=duration_frames,
                entry=audio_entry,
            )
            if existing and skip_existing:
                skipped_existing.append(
                    {
                        "reason": "already_exists",
                        "track_type": audio_item.track_type if audio_item is not None else "audio",
                        "track_index": audio_item.track_index if audio_item is not None else None,
                        "start": int(start_frame),
                        "duration": int(duration_frames),
                        "existing": existing,
                    }
                )
                continue
            inserted_audio.append(
                _insert_transition_row(
                    cursor,
                    track_id=str(audio_row["Sm2TiTrack_id"]),
                    start_frame=start_frame,
                    duration_frames=duration_frames,
                    alignment=alignment,
                    entry=audio_entry,
                )
            )
    for row in inserted_audio:
        if audio_item is not None:
            row["track_type"] = audio_item.track_type
            row["track_index"] = audio_item.track_index

    if (inserted_video or split_video) and video_row is not None:
        rebuild_track_item_indices(cursor, track_id=str(video_row["Sm2TiTrack_id"]))
    if (inserted_audio or split_audio) and audio_row is not None:
        rebuild_track_item_indices(cursor, track_id=str(audio_row["Sm2TiTrack_id"]))

    inserted = inserted_video + inserted_audio
    return {
        "transition_type": key,
        "duration_frames": duration_frames,
        "placement": placement,
        "requested_scope": normalized_scope,
        "applied_scope": applied_scope,
        "inserted": inserted,
        "inserted_video": inserted_video,
        "inserted_audio": inserted_audio,
        "skipped_existing": skipped_existing,
        "audio_companions": inserted_audio if key == "cross-dissolve" else [],
        "split_video": split_video,
        "split_audio": split_audio,
    }


def write_transition_batch(
    cursor: sqlite3.Cursor,
    *,
    plans: list[dict[str, object]],
    timeline_name: str | None = None,
) -> dict[str, object]:
    results: list[dict[str, object]] = []
    inserted: list[dict[str, object]] = []
    skipped: list[dict[str, object]] = []
    for plan in plans:
        index = int(plan.get("index", len(results)))
        result = add_transition_rows(
            cursor,
            video_item=plan.get("video_item"),
            audio_item=plan.get("audio_item"),
            transition_name=str(plan["transition_name"]),
            duration_frames=int(plan["duration_frames"]),
            placement=str(plan["placement"]),
            scope=str(plan["scope"]),
            timeline_name=timeline_name,
            at_frame=plan.get("at_frame"),
            skip_existing=True,
        )
        inserted_rows = list(result.get("inserted") or [])
        skipped_rows = list(result.get("skipped_existing") or [])
        inserted.extend(inserted_rows)
        skipped.extend(skipped_rows)
        results.append(
            {
                "index": index,
                "ok": True,
                "skipped": bool(skipped_rows) and not bool(inserted_rows),
                "changed": bool(inserted_rows),
                "target": plan.get("target"),
                "preflight": plan.get("preflight"),
                "inserted": inserted_rows,
                "skipped_existing": skipped_rows,
            }
        )
    return {
        "transition_type": plans[0]["transition_name"] if plans else None,
        "inserted": inserted,
        "skipped_existing": skipped,
        "results": results,
    }
