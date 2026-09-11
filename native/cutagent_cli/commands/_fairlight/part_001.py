"""Fairlight (audio) commands."""

from __future__ import annotations

import json
import math
from pathlib import Path
import shlex
import shutil
import sqlite3
import time
from typing import Any, Mapping
import uuid

import typer

from ..connection import get_connection
from ..errors import APICallFailed, CapabilityNegotiationFailed, ClipNotFound, handle_errors, ReadinessFailed, ValidationError
from ..output import (
    dry_run_message,
    is_dry_run,
    mutation_payload,
    output,
    set_capability_context,
    set_execution_engine,
    set_recoverability,
    set_verification_status,
    success,
)
from ..policy import enforce_mutation_policy
from ..capabilities import get_capabilities
from ..core import (
    audio_ops,
    batch_utils,
    blade_db,
    clip_ops,
    clip_speed_db,
    clip_effects_db,
    db_timeline_selection,
    db_timeline_rows,
    db_session,
    fairlight_channel_map_db,
    fairlight_external_process_gui_route,
    fairlight_loudness_gui_route,
    fairlight_mixer_meter_gui_route,
    fairlight_ops,
    keyframe_db,
    render_engine,
    retime_db,
    speed_ramp_db,
    timeline_item_duration_db,
    timeline_item_move_db,
    timeline_ops,
    transition_db,
)
from ..utils.time_ref import parse_record_frame
from ..utils.timecode import frames_to_seconds, parse_time_input, seconds_to_frames, seconds_to_timecode

app = typer.Typer(help="Fairlight audio operations.")

SUPPORTED_AUDIO_TRACK_TYPES = {
    "mono",
    "stereo",
    "lrc",
    "lcr",
    "lrcs",
    "lcrs",
    "quad",
    "5.0",
    "5.0film",
    "5.1",
    "5.1film",
    "7.0",
    "7.0film",
    "7.1",
    "7.1film",
    *(f"adaptive{i}" for i in range(1, 37)),
}
LEGACY_AUDIO_TRACK_TYPE_ALIASES = {"adaptive": "adaptive1"}


def _fairlight_no_change_payload_fields(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict) or data.get("outcome") != "no_change":
        return {}
    return {
        "outcome": "no_change",
        "before": data.get("before"),
        "after": None,
        "affected_count": 0,
        "recovery": data.get("recovery"),
        "possible_mutation": False,
        "mutation_started": False,
        "db_session_entered": False,
        "backup_written": False,
        "project_closed": False,
        "sqlite_write_started": False,
        "no_change_reason": data.get("no_change_reason"),
    }


def _load_audio_gain_batch_entries(path: str | None) -> list[dict[str, object]]:
    if path is None:
        return []
    input_path = Path(path).expanduser()
    try:
        raw = json.loads(input_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValidationError(
            "Audio-gain batch input file was not found.",
            details={"path": str(input_path)},
            recoverability="not_applicable",
        ) from exc
    except json.JSONDecodeError as exc:
        raise ValidationError(
            "Audio-gain batch input file is not valid JSON.",
            details={"path": str(input_path), "line": exc.lineno, "column": exc.colno},
            recoverability="not_applicable",
        ) from exc

    if isinstance(raw, dict) and isinstance(raw.get("entries"), list):
        raw = raw["entries"]
    if not isinstance(raw, list):
        raise ValidationError(
            "Audio-gain batch input must be a JSON array or an object with an entries array.",
            details={"path": str(input_path)},
            recoverability="not_applicable",
        )
    entries: list[dict[str, object]] = []
    for index, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise ValidationError(
                "Each audio-gain batch entry must be a JSON object.",
                details={"path": str(input_path), "index": index, "entry": entry},
                recoverability="not_applicable",
            )
        entries.append(dict(entry))
    return entries


def _load_audio_fade_batch_entries(path: str | None) -> list[dict[str, object]]:
    if path is None:
        return []
    input_path = Path(path).expanduser()
    try:
        raw = json.loads(input_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValidationError(
            "Audio fade batch input file was not found.",
            details={"path": str(input_path)},
            recoverability="not_applicable",
        ) from exc
    except json.JSONDecodeError as exc:
        raise ValidationError(
            "Audio fade batch input file is not valid JSON.",
            details={"path": str(input_path), "line": exc.lineno, "column": exc.colno},
            recoverability="not_applicable",
        ) from exc

    if isinstance(raw, dict):
        source_patch = raw.get("source_offset_patch")
        if isinstance(source_patch, dict) and isinstance(source_patch.get("patched"), list):
            raw = source_patch["patched"]
        else:
            for key in ("entries", "items", "patched"):
                if isinstance(raw.get(key), list):
                    raw = raw[key]
                    break
    if not isinstance(raw, list):
        raise ValidationError(
            "Audio fade batch input must be a JSON array or an object with entries/items/patched.",
            details={"path": str(input_path)},
            recoverability="not_applicable",
        )
    entries: list[dict[str, object]] = []
    for index, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise ValidationError(
                "Each audio fade batch entry must be a JSON object.",
                details={"path": str(input_path), "index": index, "entry": entry},
                recoverability="not_applicable",
            )
        entries.append(dict(entry))
    return entries


def _audio_gain_cli_entries(
    *,
    item_ids: list[str] | None,
    track_index: int | None,
    start_frame: str | None,
    end_frame: str | None,
    record_frame: str | None,
    record_duration: str | None,
    record_end: str | None,
) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    for item_id in item_ids or []:
        entries.append({"item_id": item_id})
    wants_track_selector = any(
        value is not None
        for value in (track_index, start_frame, end_frame, record_frame, record_duration, record_end)
    )
    if wants_track_selector:
        entry: dict[str, object] = {"track_index": track_index}
        if start_frame is not None:
            entry["start_frame"] = start_frame
        if end_frame is not None:
            entry["end_frame"] = end_frame
        if record_frame is not None:
            entry["record_frame"] = record_frame
        if record_duration is not None:
            entry["record_duration"] = record_duration
        if record_end is not None:
            entry["record_end"] = record_end
        entries.append(entry)
    return entries


def _audio_fade_cli_entries(
    *,
    item_ids: list[str] | None,
    track_index: int | None,
    start_frame: str | None,
    end_frame: str | None,
) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    for item_id in item_ids or []:
        entries.append({"item_id": item_id})
    if any(value is not None for value in (track_index, start_frame, end_frame)):
        entry: dict[str, object] = {"track_index": track_index}
        if start_frame is not None:
            entry["start_frame"] = start_frame
        if end_frame is not None:
            entry["end_frame"] = end_frame
        entries.append(entry)
    return entries


def _fairlight_batch_preflight_command(command_group: str) -> str:
    return " ".join(shlex.quote(part) for part in ("cutagent", "fairlight", command_group, "batch", "--json"))


def _fairlight_batch_dry_run_payload(
    *,
    action: str,
    command_group: str,
    timeline: str | None,
    selectors: list[dict[str, object]],
    write_payload: str,
    requested: dict[str, object],
    allow_empty: bool,
    allow_multiple: bool | None = None,
) -> dict[str, object]:
    data: dict[str, object] = {
        "action": action,
        "changed": False,
        "target": {"kind": "timeline", "name": timeline or "current"},
        "dry_run": True,
        "runtime_read_called": False,
        "runtime_write_called": False,
        "route": "db_workaround",
        "requested": requested,
        "selectors": selectors,
        "selector_count": len(selectors),
        "allow_empty": bool(allow_empty),
        "requires_runtime_preflight": True,
        "db_write": {"table": "Sm2TiItem", "column": "EffectFiltersBA", "payload": write_payload},
        "read_scope": "normalized_audio_item_selectors_only",
        "preflight_command": _fairlight_batch_preflight_command(command_group),
    }
    if allow_multiple is not None:
        data["allow_multiple"] = bool(allow_multiple)
    return data


def _validate_audio_track_type(track_type: str) -> str:
    normalized = str(track_type).strip().lower()
    normalized = LEGACY_AUDIO_TRACK_TYPE_ALIASES.get(normalized, normalized)
    if normalized not in SUPPORTED_AUDIO_TRACK_TYPES:
        allowed_preview = "mono, stereo, lrc, lcr, lrcs, lcrs, quad, 5.0, 5.0film, 5.1, 5.1film, 7.0, 7.0film, 7.1, 7.1film, adaptive1..adaptive36"
        raise ValidationError(
            f"--track-type must be one of: {allowed_preview}.",
            details={
                "option": "--track-type",
                "value": track_type,
                "allowed": sorted(SUPPORTED_AUDIO_TRACK_TYPES),
                "legacy_aliases": dict(sorted(LEGACY_AUDIO_TRACK_TYPE_ALIASES.items())),
            },
        )
    return normalized


def _validate_audio_track_index(conn, index: int) -> int:
    count = conn.timeline.GetTrackCount("audio") or 0
    if index < 1 or index > count:
        raise ValidationError(
            "Audio track index is out of range.",
            details={
                "track_type": "audio",
                "index": index,
                "min": 1,
                "max": count,
                "available_audio_tracks": count,
            },
        )
    return count


audio_gain_app = typer.Typer(help="Clip audio gain batch operations.")
app.add_typer(audio_gain_app, name="audio-gain")

audio_pan_app = typer.Typer(help="Clip audio pan batch operations.")
app.add_typer(audio_pan_app, name="audio-pan")

fade_in_app = typer.Typer(help="Clip audio fade-in batch operations.")
app.add_typer(fade_in_app, name="fade-in")

fade_out_app = typer.Typer(help="Clip audio fade-out batch operations.")
app.add_typer(fade_out_app, name="fade-out")

crossfade_app = typer.Typer(help="Clip audio crossfade batch operations.")
app.add_typer(crossfade_app, name="crossfade")

clip_app = typer.Typer(help="Fairlight audio clip edit operations.")
app.add_typer(clip_app, name="clip")
clip_linked_app = typer.Typer(help="Fairlight linked clip readback operations.")
clip_app.add_typer(clip_linked_app, name="linked")

transition_app = typer.Typer(help="Fairlight audio transition operations.")
app.add_typer(transition_app, name="transition")


@audio_gain_app.command("batch")
@handle_errors
def audio_gain_batch(
    db: float = typer.Option(..., "--db", help="Audio gain in dB"),
    timeline: str | None = typer.Option(None, "--timeline", help="Target timeline name; defaults to active timeline"),
    item_ids: list[str] | None = typer.Option(None, "--item-id", help="Repeatable Sm2TiItem_id for audio clips"),
    track_index: int | None = typer.Option(None, "--track-index", min=1, help="Audio track index for time selectors"),
    start_frame: str | None = typer.Option(None, "--start-frame", help="Record-domain range start"),
    end_frame: str | None = typer.Option(None, "--end-frame", help="Record-domain range end"),
    record_frame: str | None = typer.Option(None, "--record-frame", help="Record-domain point or range start"),
    record_duration: str | None = typer.Option(None, "--record-duration", help="Duration from --record-frame"),
    record_end: str | None = typer.Option(None, "--record-end", help="Record-domain range end from --record-frame"),
    input_path: str | None = typer.Option(None, "--input", "--batch", help="JSON batch file path"),
    allow_empty: bool = typer.Option(False, "--allow-empty", help="Do not fail when selectors match no items"),
    allow_multiple: bool = typer.Option(False, "--allow-multiple", help="Allow one selector to update multiple items"),
):
    """Apply one archive-backed audio gain payload to many audio items."""
    enforce_mutation_policy("fairlight.audio_gain_batch", intended_engine="db_workaround", mutating=not is_dry_run())
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
    clip_effects_db.validate_audio_gain_db(db)

    entries = _load_audio_gain_batch_entries(input_path)
    entries.extend(
        _audio_gain_cli_entries(
            item_ids=item_ids,
            track_index=track_index,
            start_frame=start_frame,
            end_frame=end_frame,
            record_frame=record_frame,
            record_duration=record_duration,
            record_end=record_end,
        )
    )
    if is_dry_run():
        output(
            mutation_payload(
                **_fairlight_batch_dry_run_payload(
                    action="fairlight.audio_gain.batch",
                    command_group="audio-gain",
                    timeline=timeline,
                    selectors=entries,
                    write_payload="audio_gain_effect_filter",
                    requested={"gain_db": float(db)},
                    allow_empty=allow_empty,
                    allow_multiple=allow_multiple,
                ),
            ),
            title="Fairlight Audio Gain Batch Plan",
        )
        return

    conn = get_connection(require_timeline=True)
    timeline_switch = fairlight_ops._switch_timeline_by_name(conn, timeline) if timeline else None
    if is_dry_run():
        data = fairlight_ops.preview_audio_gain_batch(
            conn,
            gain_db=db,
            selectors=entries,
            allow_empty=allow_empty,
            allow_multiple=allow_multiple,
        )
    else:
        data = fairlight_ops.apply_audio_gain_batch(
            conn,
            gain_db=db,
            selectors=entries,
            allow_empty=allow_empty,
            allow_multiple=allow_multiple,
        )

    action = str(data.pop("action", "fairlight.audio_gain.batch"))
    changed = bool(data.pop("changed", data.get("updated_count", 0)))
    output(
        mutation_payload(
            action=action,
            target={"kind": "timeline", "name": data.get("timeline_name")},
            changed=changed,
            **data,
            timeline_switch=timeline_switch,
        ),
        title="Fairlight Audio Gain Batch",
    )


@audio_pan_app.command("batch")
@handle_errors
def audio_pan_batch(
    value: float = typer.Option(..., "--value", help="Audio pan value from -100 to 100"),
    timeline: str | None = typer.Option(None, "--timeline", help="Target timeline name; defaults to active timeline"),
    item_ids: list[str] | None = typer.Option(None, "--item-id", help="Repeatable Sm2TiItem_id for audio clips"),
    track_index: int | None = typer.Option(None, "--track-index", min=1, help="Audio track index for time selectors"),
    start_frame: str | None = typer.Option(None, "--start-frame", help="Record-domain range start"),
    end_frame: str | None = typer.Option(None, "--end-frame", help="Record-domain range end"),
    record_frame: str | None = typer.Option(None, "--record-frame", help="Record-domain point or range start"),
    record_duration: str | None = typer.Option(None, "--record-duration", help="Duration from --record-frame"),
    record_end: str | None = typer.Option(None, "--record-end", help="Record-domain range end from --record-frame"),
    input_path: str | None = typer.Option(None, "--input", "--batch", help="JSON batch file path"),
    allow_empty: bool = typer.Option(False, "--allow-empty", help="Do not fail when selectors match no items"),
    allow_multiple: bool = typer.Option(False, "--allow-multiple", help="Allow one selector to update multiple items"),
):
    """Apply one archive-backed audio pan payload to many audio items."""
    set_execution_engine("db_workaround")
    enforce_mutation_policy("fairlight.audio_pan_batch", intended_engine="db_workaround", mutating=not is_dry_run())
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
    clip_effects_db.validate_audio_pan_value(value)

    entries = _load_audio_gain_batch_entries(input_path)
    entries.extend(
        _audio_gain_cli_entries(
            item_ids=item_ids,
            track_index=track_index,
            start_frame=start_frame,
            end_frame=end_frame,
            record_frame=record_frame,
            record_duration=record_duration,
            record_end=record_end,
        )
    )
    if is_dry_run():
        output(
            mutation_payload(
                **_fairlight_batch_dry_run_payload(
                    action="fairlight.audio_pan.batch",
                    command_group="audio-pan",
                    timeline=timeline,
                    selectors=entries,
                    write_payload="audio_pan_effect_filter",
                    requested={"pan_value": float(value)},
                    allow_empty=allow_empty,
                    allow_multiple=allow_multiple,
                ),
            ),
            title="Fairlight Audio Pan Batch Plan",
        )
        return

    conn = get_connection(require_timeline=True)
    timeline_switch = fairlight_ops._switch_timeline_by_name(conn, timeline) if timeline else None
    if is_dry_run():
        data = fairlight_ops.preview_audio_pan_batch(
            conn,
            pan_value=value,
            selectors=entries,
            allow_empty=allow_empty,
            allow_multiple=allow_multiple,
        )
    else:
        data = fairlight_ops.apply_audio_pan_batch(
            conn,
            pan_value=value,
            selectors=entries,
            allow_empty=allow_empty,
            allow_multiple=allow_multiple,
        )

    action = str(data.pop("action", "fairlight.audio_pan.batch"))
    changed = bool(data.pop("changed", data.get("updated_count", 0)))
    output(
        mutation_payload(
            action=action,
            target={"kind": "timeline", "name": data.get("timeline_name")},
            changed=changed,
            **data,
            timeline_switch=timeline_switch,
        ),
        title="Fairlight Audio Pan Batch",
    )


def _sdk_audio_pan_items(
    items: Mapping[str, Any] | list[Mapping[str, Any]],
) -> None:
    """Apply one signed SDK pan item or a heterogeneous item list in one native pass."""
    raw_items = [items] if isinstance(items, Mapping) else items
    if not isinstance(raw_items, list) or not 1 <= len(raw_items) <= 128:
        raise ValidationError(
            "SDK audio pan requires one to 128 items.",
            recoverability="not_applicable",
        )
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(raw_items):
        if not isinstance(item, Mapping) or set(item) != {"item_id", "value"}:
            raise ValidationError(
                "Each SDK audio pan item requires only item_id and value.",
                details={"index": index},
                recoverability="not_applicable",
            )
        item_id = str(item.get("item_id") or "").strip()
        if not item_id or item_id in seen:
            raise ValidationError(
                "SDK audio pan item identities must be non-empty and unique.",
                details={"index": index, "item_id": item_id},
                recoverability="not_applicable",
            )
        seen.add(item_id)
        try:
            value = clip_effects_db.validate_audio_pan_value(item.get("value"))
        except (TypeError, ValueError) as exc:
            raise ValidationError(
                "SDK audio pan values must be finite numbers.",
                details={"index": index},
                recoverability="not_applicable",
            ) from exc
        entries.append({"item_id": item_id, "value": value})

    set_execution_engine("db_workaround")
    enforce_mutation_policy(
        "fairlight.audio_pan_batch",
        intended_engine="db_workaround",
        mutating=not is_dry_run(),
    )
    conn = get_connection(require_timeline=True)
    data = fairlight_ops.apply_audio_pan_batch(
        conn,
        pan_value=None,
        selectors=entries,
        allow_empty=False,
        allow_multiple=False,
    )
    action = str(data.pop("action", "fairlight.audio_pan.batch"))
    changed = bool(data.pop("changed", data.get("updated_count", 0)))
    output(
        mutation_payload(
            action=action,
            target={"kind": "timeline", "name": data.get("timeline_name")},
            changed=changed,
            **data,
        ),
        title="Fairlight Audio Pan",
    )


@fade_in_app.command("batch")
@handle_errors
def fade_in_batch(
    duration: str | None = typer.Option(None, "--duration", help="Fade duration, e.g. 0.2s or 12f"),
    timeline: str | None = typer.Option(None, "--timeline", help="Target timeline name; defaults to active timeline"),
    item_ids: list[str] | None = typer.Option(None, "--item-id", help="Repeatable Sm2TiItem_id for audio clips"),
    track_index: int | None = typer.Option(None, "--track-index", min=1, help="Audio track index for range selectors"),
    start_frame: str | None = typer.Option(None, "--start-frame", help="Record-domain range start"),
    end_frame: str | None = typer.Option(None, "--end-frame", help="Record-domain range end"),
    input_path: str | None = typer.Option(None, "--input", "--batch", help="JSON batch file path"),
    skip_first_segment: bool = typer.Option(False, "--skip-first-segment/--no-skip-first-segment", help="Skip items at the earliest selected start frame"),
    skip_adjacent_same_track: bool = typer.Option(True, "--skip-adjacent-same-track/--no-skip-adjacent-same-track", help="Skip items that touch a previous selected item on the same track"),
    clamp_half_clip: bool = typer.Option(True, "--clamp-half-clip/--no-clamp-half-clip", help="Clamp fade length to at most half of each clip duration"),
    db: float | None = typer.Option(None, "--db", help="Optional audio gain in dB to merge with the fade effect chain"),
    allow_empty: bool = typer.Option(False, "--allow-empty", help="Do not fail when selectors match no items"),
):
    """Apply archive-backed audio fade-in payloads to many audio items."""
    set_execution_engine("db_workaround")
    enforce_mutation_policy("fairlight.fade_in_batch", intended_engine="db_workaround", mutating=not is_dry_run())
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")

    entries = _load_audio_fade_batch_entries(input_path)
    entries.extend(
        _audio_fade_cli_entries(
            item_ids=item_ids,
            track_index=track_index,
            start_frame=start_frame,
            end_frame=end_frame,
        )
    )
    if is_dry_run():
        output(
            mutation_payload(
                **_fairlight_batch_dry_run_payload(
                    action="fairlight.fade_in.batch",
                    command_group="fade-in",
                    timeline=timeline,
                    selectors=entries,
                    write_payload="audio_fade_in_effect_filter",
                    requested={
                        "duration": duration,
                        "skip_first_segment": bool(skip_first_segment),
                        "skip_adjacent_same_track": bool(skip_adjacent_same_track),
                        "clamp_half_clip": bool(clamp_half_clip),
                        "gain_db": None if db is None else float(db),
                    },
                    allow_empty=allow_empty,
                ),
            ),
            title="Fairlight Fade-In Batch Plan",
        )
        return

    conn = get_connection(require_timeline=True)
    timeline_switch = fairlight_ops._switch_timeline_by_name(conn, timeline) if timeline else None
    if is_dry_run():
        data = fairlight_ops.preview_audio_fade_in_batch(
            conn,
            entries=entries,
            duration=duration,
            skip_first_segment=skip_first_segment,
            skip_adjacent_same_track=skip_adjacent_same_track,
            clamp_half_clip=clamp_half_clip,
            gain_db=db,
            allow_empty=allow_empty,
        )
    else:
        data = fairlight_ops.apply_audio_fade_in_batch(
            conn,
            entries=entries,
            duration=duration,
            skip_first_segment=skip_first_segment,
            skip_adjacent_same_track=skip_adjacent_same_track,
            clamp_half_clip=clamp_half_clip,
            gain_db=db,
            allow_empty=allow_empty,
        )

    action = str(data.pop("action", "fairlight.fade_in.batch"))
    changed = bool(data.pop("changed", data.get("updated_count", 0)))
    output(
        mutation_payload(
            action=action,
            target={"kind": "timeline", "name": data.get("timeline_name")},
            changed=changed,
            **data,
            timeline_switch=timeline_switch,
        ),
        title="Fairlight Fade-In Batch",
    )


@fade_out_app.command("batch")
@handle_errors
def fade_out_batch(
    duration: str | None = typer.Option(None, "--duration", help="Fade duration, e.g. 0.2s or 12f"),
    timeline: str | None = typer.Option(None, "--timeline", help="Target timeline name; defaults to active timeline"),
    item_ids: list[str] | None = typer.Option(None, "--item-id", help="Repeatable Sm2TiItem_id for audio clips"),
    track_index: int | None = typer.Option(None, "--track-index", min=1, help="Audio track index for range selectors"),
    start_frame: str | None = typer.Option(None, "--start-frame", help="Record-domain range start"),
    end_frame: str | None = typer.Option(None, "--end-frame", help="Record-domain range end"),
    input_path: str | None = typer.Option(None, "--input", "--batch", help="JSON batch file path"),
    skip_last_segment: bool = typer.Option(False, "--skip-last-segment/--no-skip-last-segment", help="Skip items at the latest selected end frame"),
    skip_adjacent_same_track: bool = typer.Option(True, "--skip-adjacent-same-track/--no-skip-adjacent-same-track", help="Skip items that touch a following selected item on the same track"),
    clamp_half_clip: bool = typer.Option(True, "--clamp-half-clip/--no-clamp-half-clip", help="Clamp fade length to at most half of each clip duration"),
    db: float | None = typer.Option(None, "--db", help="Optional audio gain in dB to merge with the fade effect chain"),
    allow_empty: bool = typer.Option(False, "--allow-empty", help="Do not fail when selectors match no items"),
):
    """Apply archive-backed audio fade-out payloads to many audio items."""
    set_execution_engine("db_workaround")
    enforce_mutation_policy("fairlight.fade_out_batch", intended_engine="db_workaround", mutating=not is_dry_run())
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")

    entries = _load_audio_fade_batch_entries(input_path)
    entries.extend(
        _audio_fade_cli_entries(
            item_ids=item_ids,
            track_index=track_index,
            start_frame=start_frame,
            end_frame=end_frame,
        )
    )
    if is_dry_run():
        output(
            mutation_payload(
                **_fairlight_batch_dry_run_payload(
                    action="fairlight.fade_out.batch",
                    command_group="fade-out",
                    timeline=timeline,
                    selectors=entries,
                    write_payload="audio_fade_out_effect_filter",
                    requested={
                        "duration": duration,
                        "skip_last_segment": bool(skip_last_segment),
                        "skip_adjacent_same_track": bool(skip_adjacent_same_track),
                        "clamp_half_clip": bool(clamp_half_clip),
                        "gain_db": None if db is None else float(db),
                    },
                    allow_empty=allow_empty,
                ),
            ),
            title="Fairlight Fade-Out Batch Plan",
        )
        return

    conn = get_connection(require_timeline=True)
    timeline_switch = fairlight_ops._switch_timeline_by_name(conn, timeline) if timeline else None
    if is_dry_run():
        data = fairlight_ops.preview_audio_fade_out_batch(
            conn,
            entries=entries,
            duration=duration,
            skip_last_segment=skip_last_segment,
            skip_adjacent_same_track=skip_adjacent_same_track,
            clamp_half_clip=clamp_half_clip,
            gain_db=db,
            allow_empty=allow_empty,
        )
    else:
        data = fairlight_ops.apply_audio_fade_out_batch(
            conn,
            entries=entries,
            duration=duration,
            skip_last_segment=skip_last_segment,
            skip_adjacent_same_track=skip_adjacent_same_track,
            clamp_half_clip=clamp_half_clip,
            gain_db=db,
            allow_empty=allow_empty,
        )

    action = str(data.pop("action", "fairlight.fade_out.batch"))
    changed = bool(data.pop("changed", data.get("updated_count", 0)))
    output(
        mutation_payload(
            action=action,
            target={"kind": "timeline", "name": data.get("timeline_name")},
            changed=changed,
            **data,
            timeline_switch=timeline_switch,
        ),
        title="Fairlight Fade-Out Batch",
    )


@crossfade_app.command("batch")
@handle_errors
def crossfade_batch(
    duration: str | None = typer.Option(None, "--duration", help="Crossfade duration, e.g. 0.2s or 12f"),
    timeline: str | None = typer.Option(None, "--timeline", help="Target timeline name; defaults to active timeline"),
    item_ids: list[str] | None = typer.Option(None, "--item-id", help="Repeatable Sm2TiItem_id for audio clips"),
    track_index: int | None = typer.Option(None, "--track-index", min=1, help="Audio track index for range selectors"),
    start_frame: str | None = typer.Option(None, "--start-frame", help="Record-domain range start"),
    end_frame: str | None = typer.Option(None, "--end-frame", help="Record-domain range end"),
    input_path: str | None = typer.Option(None, "--input", "--batch", help="JSON batch file path"),
    clamp_half_clip: bool = typer.Option(True, "--clamp-half-clip/--no-clamp-half-clip", help="Clamp each crossfade edge to at most half of its clip duration"),
    allow_empty: bool = typer.Option(False, "--allow-empty", help="Do not fail when selectors match no adjacent edit points"),
):
    """Apply DB-backed crossfades to adjacent audio edit points."""
    set_execution_engine("db_workaround")
    enforce_mutation_policy("fairlight.crossfade_batch", intended_engine="db_workaround", mutating=not is_dry_run())
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")

    entries = _load_audio_fade_batch_entries(input_path)
    entries.extend(
        _audio_fade_cli_entries(
            item_ids=item_ids,
            track_index=track_index,
            start_frame=start_frame,
            end_frame=end_frame,
        )
    )
    if is_dry_run():
        output(
            mutation_payload(
                **_fairlight_batch_dry_run_payload(
                    action="fairlight.crossfade.batch",
                    command_group="crossfade",
                    timeline=timeline,
                    selectors=entries,
                    write_payload="audio_crossfade_effect_filter_pair",
                    requested={
                        "duration": duration,
                        "clamp_half_clip": bool(clamp_half_clip),
                    },
                    allow_empty=allow_empty,
                ),
            ),
            title="Fairlight Crossfade Batch Plan",
        )
        return

    conn = get_connection(require_timeline=True)
    timeline_switch = fairlight_ops._switch_timeline_by_name(conn, timeline) if timeline else None
    if is_dry_run():
        data = fairlight_ops.preview_audio_crossfade_batch(
            conn,
            entries=entries,
            duration=duration,
            clamp_half_clip=clamp_half_clip,
            allow_empty=allow_empty,
        )
    else:
        data = fairlight_ops.apply_audio_crossfade_batch(
            conn,
            entries=entries,
            duration=duration,
            clamp_half_clip=clamp_half_clip,
            allow_empty=allow_empty,
        )

    action = str(data.pop("action", "fairlight.crossfade.batch"))
    changed = bool(data.pop("changed", data.get("updated_count", 0)))
    output(
        mutation_payload(
            action=action,
            target={"kind": "timeline", "name": data.get("timeline_name")},
            changed=changed,
            **data,
            timeline_switch=timeline_switch,
        ),
        title="Fairlight Crossfade Batch",
    )


def _fairlight_clip_split_payload(data: dict[str, Any]) -> dict[str, Any]:
    payload = dict(data)
    if payload.get("action") == "edit.blade":
        payload["delegated_action"] = "edit.blade"
    payload["action"] = "fairlight.clip.split"
    return payload


def _fairlight_clip_split_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for index, entry in enumerate(entries):
        raw = dict(entry)
        raw_track_type = raw.get("track_type", raw.get("track-type", "audio"))
        track_type = blade_db.normalize_blade_track_type(raw_track_type)
        if track_type != "audio":
            raise ValidationError(
                "Fairlight clip split only supports audio track targets.",
                details={"index": index, "track_type": raw_track_type, "supported_track_type": "audio"},
                recoverability="not_applicable",
            )
        raw["track_type"] = "audio"
        raw.pop("track-type", None)
        normalized.append(raw)
    return normalized


@clip_app.command("split")
@handle_errors
def clip_split(
    at: str | None = typer.Option(None, "--at", help="Record-domain timecode/seconds/frames to split at; defaults to playhead"),
    track_index: int = typer.Option(0, "--track", min=0, help="Audio track index (0 = all matching audio tracks)"),
    batch: Path | None = typer.Option(None, "--batch", help="JSON batch file"),
    input_file: Path | None = typer.Option(None, "--input", help="JSON batch file alias"),
    batch_json: str | None = typer.Option(None, "--batch-json", help="Inline JSON batch payload"),
    allow_partial: bool = typer.Option(False, "--allow-partial", help="Apply valid entries even when some entries fail preflight"),
    respect_locks: bool = typer.Option(True, "--respect-locks/--ignore-locks", help="Respect timeline track locks"),
):
    """Split Fairlight audio timeline items through the DB-backed blade route."""
    set_execution_engine("db_workaround")
    enforce_mutation_policy("fairlight.clip_split", intended_engine="db_workaround", mutating=not is_dry_run())
    normalized_track_index = blade_db.normalize_blade_track_index(track_index)
    batch_sources = [batch is not None, input_file is not None, batch_json is not None]
    if sum(batch_sources) > 1:
        raise ValidationError(
            "Provide only one Fairlight clip split batch input source.",
            details={
                "batch": str(batch) if batch else None,
                "input": str(input_file) if input_file else None,
                "batch_json": bool(batch_json),
            },
            recoverability="not_applicable",
        )
    if any(batch_sources):
        entries = batch_utils.load_batch_entries(
            batch_path=batch,
            input_path=input_file,
            batch_json=batch_json,
            wrapper_keys=("cuts", "entries", "items", "batch"),
        )
        entries = _fairlight_clip_split_entries(entries)
    else:
        entries = [{"index": 0, "at": at, "track_type": "audio", "track": normalized_track_index}]

    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            _fairlight_clip_split_payload(
                {
                    "action": "edit.blade",
                    "changed": False,
                    "dry_run": True,
                    "runtime_read_called": False,
                    "route": "db_workaround",
                    "target": {"kind": "timeline", "track_type": "audio"},
                    "requested_count": len(entries),
                    "entries": entries,
                    "default_at": at,
                    "default_track_type": "audio",
                    "default_track_index": normalized_track_index,
                    "respect_locks": respect_locks,
                    "allow_partial": allow_partial,
                    "requires_runtime_preflight": True,
                    "preflight_command": "cutagent fairlight clip split --json",
                }
            ),
            title="Fairlight Clip Split Plan",
        )
        return

    conn = get_connection(require_timeline=True)
    timeline_name = conn.timeline.GetName() if getattr(conn, "timeline", None) else None
    pre_track_counts = blade_db._pre_track_counts(conn, ["audio"])
    plans, preflight_results = blade_db.preflight_blade_entries(
        conn,
        entries,
        default_at=at,
        default_track_type="audio",
        default_track_index=normalized_track_index,
        respect_locks=respect_locks,
        allow_partial=allow_partial,
    )
    if not plans:
        output(
            _fairlight_clip_split_payload(
                blade_db.no_op_payload(
                    preflight_results=preflight_results,
                    timeline_name=timeline_name,
                    allow_partial=allow_partial,
                )
            ),
            title="Fairlight Clip Split",
        )
        return

    result = db_session.execute_sqlite_disk_db_mutation(
        conn,
        context="Fairlight DB-backed audio clip split",
        writer=lambda _connection, cursor, _session: blade_db.write_blade_batch(
            cursor,
            plans=plans,
            preflight_results=preflight_results,
            timeline_name=timeline_name,
            allow_partial=allow_partial,
            pre_track_counts=pre_track_counts,
        ),
        verifier=blade_db.verify_blade_batch,
        allow_project_name_inference=True,
        require_verified=True,
    )
    output(_fairlight_clip_split_payload(result), title="Fairlight Clip Split")


@clip_app.command("trim")
@handle_errors
def clip_trim(
    timeline_name: str | None = typer.Option(None, "--timeline", help="Target timeline name; defaults to active timeline"),
    item_id: str | None = typer.Option(None, "--item-id", help="Project.db Sm2TiItem_id when known"),
    track_index: int = typer.Option(1, "--track", "--track-index", min=1, help="Audio track index for selector"),
    start_frame: str | None = typer.Option(None, "--start-frame", help="Current audio item start in record-domain frames/time"),
    current_end_frame: str | None = typer.Option(None, "--current-end-frame", help="Current audio item end for stricter selection"),
    name: str | None = typer.Option(None, "--name", help="Current timeline item name for stricter selection"),
    duration: str | None = typer.Option(None, "--duration", help="New audio item duration: frames, seconds, or timecode"),
    target_end_frame: str | None = typer.Option(None, "--end-frame", "--target-end-frame", help="New audio item end in record-domain frames/time"),
    target_start_frame: str | None = typer.Option(None, "--target-start-frame", "--new-start-frame", help="New audio item head/start in record-domain frames/time"),
    head_delta: str | None = typer.Option(None, "--head-delta", "--trim-start-by", help="Signed left-edge trim amount, e.g. 12f or -0.5s"),
    allow_overlap: bool = typer.Option(False, "--allow-overlap", help="Allow the new duration to overlap the next item on the same audio track"),
    no_source_bounds: bool = typer.Option(False, "--no-source-bounds", help="Do not reject API-reported source/right-trim overrun before DB write"),
    allow_linked_audio_only: bool = typer.Option(
        False,
        "--allow-linked-audio-only",
        help="Allow trimming only the Fairlight audio item when native-linked video companions are present",
    ),
    include_linked_video: bool = typer.Option(
        False,
        "--include-linked-video",
        help="Trim native-linked video companions by the same edge/source delta",
    ),
):
    """Trim a Fairlight audio item's right or left edge through verified Disk DB routes."""
    set_execution_engine("db_workaround")
    enforce_mutation_policy("fairlight.clip_trim", intended_engine="db_workaround", mutating=not is_dry_run())
    requested_modes = [value for value in (duration, target_end_frame, target_start_frame, head_delta) if value is not None]
    if len(requested_modes) != 1:
        raise ValidationError(
            "Provide exactly one trim target: --duration, --end-frame/--target-end-frame, --target-start-frame/--new-start-frame, or --head-delta.",
            details={
                "duration": duration,
                "target_end_frame": target_end_frame,
                "target_start_frame": target_start_frame,
                "head_delta": head_delta,
            },
        )
    if allow_linked_audio_only and include_linked_video:
        raise ValidationError(
            "Choose only one linked A/V mode: --include-linked-video or --allow-linked-audio-only.",
            details={"allow_linked_audio_only": True, "include_linked_video": True},
        )
    trim_edge = "head" if target_start_frame is not None or head_delta is not None else "tail"
    selector = {
        "item_id": item_id,
        "track_type": "audio",
        "track_index": track_index,
        "start_frame": start_frame,
        "current_end_frame": current_end_frame,
        "name": name,
    }
    requested = {
        "duration": duration,
        "target_end_frame": target_end_frame,
        "target_start_frame": target_start_frame,
        "head_delta": head_delta,
        "trim_edge": trim_edge,
        "allow_overlap": bool(allow_overlap),
        "enforce_source_bounds": not bool(no_source_bounds),
        "allow_linked_audio_only": bool(allow_linked_audio_only),
        "include_linked_video": bool(include_linked_video),
    }
    delegated_action = "timeline.items.trim_head" if trim_edge == "head" else "timeline.items.set_duration"
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            mutation_payload(
                action="fairlight.clip.trim",
                changed=False,
                target={"kind": "timeline", "name": timeline_name},
                selector=selector,
                requested=requested,
                delegated_action=delegated_action,
                command_intent={
                    "set_duration_or_end": trim_edge == "tail",
                    "set_head_or_source_in": trim_edge == "head",
                    "delete_items": False,
                    "ripple_timeline": False,
                    "route": "db_workaround",
                    "audio_only": not bool(include_linked_video),
                    "linked_av_group": bool(include_linked_video),
                    "include_linked_video": bool(include_linked_video),
                },
                message="DRY-RUN: Would trim a Fairlight audio clip through the Disk DB route.",
            ),
            title="Fairlight Clip Trim Plan",
        )
        return

    conn = get_connection(require_project=True, require_timeline=timeline_name is None)
    if trim_edge == "head":
        data = timeline_item_duration_db.trim_timeline_item_head(
            conn,
            timeline_name=timeline_name,
            item_id=item_id,
            track_type="audio",
            track_index=track_index,
            start_frame=start_frame,
            current_end_frame=current_end_frame,
            name=name,
            target_start_frame=target_start_frame,
            head_delta=head_delta,
            allow_overlap=allow_overlap,
            allow_linked_audio_only=allow_linked_audio_only,
            include_linked_video=include_linked_video,
            require_fairlight_edit_contract=True,
        )
    else:
        data = timeline_item_duration_db.set_timeline_item_duration(
            conn,
            timeline_name=timeline_name,
            item_id=item_id,
            track_type="audio",
            track_index=track_index,
            start_frame=start_frame,
            current_end_frame=current_end_frame,
            name=name,
            duration=duration,
            target_end_frame=target_end_frame,
            allow_overlap=allow_overlap,
            enforce_source_bounds=not no_source_bounds,
            allow_linked_audio_only=allow_linked_audio_only,
            include_linked_video=include_linked_video,
            require_fairlight_edit_contract=True,
        )
    updated_items = data.get("updated_items") if isinstance(data, dict) else None
    output(
        mutation_payload(
            action="fairlight.clip.trim",
            changed=bool(updated_items),
            target={"kind": "timeline", "name": data.get("timeline_name") if isinstance(data, dict) else timeline_name},
            selector=selector,
            requested=data.get("requested") if isinstance(data, dict) else requested,
            updated_items=updated_items,
            readback=data.get("verification") if isinstance(data, dict) else None,
            linked_video_included=data.get("linked_video_included") if isinstance(data, dict) else None,
            project_db_path=data.get("project_db_path") if isinstance(data, dict) else None,
            backup_path=data.get("backup_path") if isinstance(data, dict) else None,
            steps=data.get("steps") if isinstance(data, dict) else None,
            route=data.get("route") if isinstance(data, dict) else "db_native",
            delegated_action=delegated_action,
            **_fairlight_no_change_payload_fields(data),
            message="Trimmed Fairlight audio clip.",
        ),
        title="Fairlight Clip Trim",
    )


@clip_app.command("delete")
@handle_errors
def clip_delete(
    timeline_name: str | None = typer.Option(None, "--timeline", help="Target timeline name; defaults to active timeline"),
    track_index: int | None = typer.Option(None, "--track", "--track-index", min=1, help="Only delete audio items on this track index"),
    start_frame: str | None = typer.Option(None, "--start-frame", help="Record-domain range start"),
    end_frame: str | None = typer.Option(None, "--end-frame", help="Record-domain range end"),
    match: str = typer.Option("overlap", "--match", help="overlap, contained, or covering"),
    allow_empty: bool = typer.Option(False, "--allow-empty", help="Return ok when no audio items match"),
    force: bool = typer.Option(False, "--force", help="Required for wide deletes without a frame range"),
):
    """Delete Fairlight audio clips without deleting tracks or rippling the timeline."""
    set_execution_engine("api_native")
    enforce_mutation_policy("fairlight.clip_delete", intended_engine="api_native", mutating=not is_dry_run())
    normalized_track_index = timeline_ops.validate_timeline_track_index(track_index) if track_index is not None else None
    normalized_match = timeline_ops.normalize_timeline_item_delete_match(match)
    filters = {
        "timeline": timeline_name,
        "track_type": "audio",
        "track_index": normalized_track_index,
        "start_frame": start_frame,
        "end_frame": end_frame,
        "match": normalized_match,
        "allow_empty": bool(allow_empty),
        "force": bool(force),
    }
    command_intent = {
        "delete_items": True,
        "delete_tracks": False,
        "ripple_timeline": False,
        "audio_only": True,
        "requires_force_for_wide_delete": start_frame is None and end_frame is None,
        "route": "api_native",
    }
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            mutation_payload(
                action="fairlight.clip.delete",
                changed=False,
                target={"kind": "timeline", "name": timeline_name},
                filters=filters,
                delegated_action="timeline.items.delete",
                command_intent=command_intent,
                message="DRY-RUN: Would delete Fairlight audio clips through the native timeline item delete route.",
            ),
            title="Fairlight Clip Delete Plan",
        )
        return

    conn = get_connection(require_project=True, require_timeline=timeline_name is None)
    data = timeline_ops.delete_timeline_items(
        conn,
        timeline_name=timeline_name,
        track_type="audio",
        track_index=normalized_track_index,
        start_ref=start_frame,
        end_ref=end_frame,
        match=normalized_match,
        allow_empty=allow_empty,
        force=force,
    )
    output(
        mutation_payload(
            action="fairlight.clip.delete",
            changed=bool(data.get("changed")) if isinstance(data, dict) else False,
            target=data.get("target") if isinstance(data, dict) else {"kind": "timeline", "name": timeline_name},
            filters=data.get("filters") if isinstance(data, dict) else filters,
            deleted_count=data.get("deleted_count") if isinstance(data, dict) else None,
            deleted_items=data.get("deleted_items") if isinstance(data, dict) else None,
            readback=data.get("readback") if isinstance(data, dict) else None,
            api_result=data.get("api_result") if isinstance(data, dict) else None,
            used_non_ripple_argument=data.get("used_non_ripple_argument") if isinstance(data, dict) else None,
            fallback_used=data.get("fallback_used") if isinstance(data, dict) else None,
            delegated_action="timeline.items.delete",
            command_intent=command_intent,
            message=data.get("message") if isinstance(data, dict) else "Deleted Fairlight audio clips.",
        ),
        title="Fairlight Clip Delete",
    )


def _fairlight_clip_readback_dry_run_payload(
    *,
    action: str,
    clip: str | None,
    native_api: str,
    delegated_action: str,
    command: str,
    read_scope: str,
) -> dict[str, Any]:
    command_clip = clip or "<current>"
    return {
        "action": action,
        "dry_run": True,
        "runtime_read_called": False,
        "target": {"kind": "timeline_item", "clip": clip, "audio_focus": True},
        "route": "api_native",
        "native_api": native_api,
        "delegated_action": delegated_action,
        "read_scope": read_scope,
        "preflight_command": f"cutagent fairlight clip {command} {command_clip} --json",
    }


@clip_app.command("info")
@handle_errors
def clip_info(
    clip: str | None = typer.Argument(None, help="Clip name (current clip when omitted)"),
):
    """Show detailed TimelineItem metadata for a Fairlight timeline clip."""
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            _fairlight_clip_readback_dry_run_payload(
                action="fairlight.clip.info",
                clip=clip,
                native_api="TimelineItem.GetName/GetStart/GetEnd/GetDuration/GetProperty",
                delegated_action="clip.info",
                command="info",
                read_scope="timeline_item_metadata",
            ),
            title="Fairlight Clip Info Plan",
        )
        return
    conn = get_connection(require_timeline=True)
    data = clip_ops.get_clip_info(conn, clip)
    output(
        {
            "action": "fairlight.clip.info",
            "target": {"kind": "timeline_item", "clip": data.get("name") or clip, "audio_focus": True},
            "route": "api_native",
            "native_api": "TimelineItem.GetName/GetStart/GetEnd/GetDuration/GetProperty",
            "delegated_action": "clip.info",
            **data,
        },
        title=f"Fairlight Clip: {data.get('name', '?')}",
    )


@clip_app.command("source-range")
@handle_errors
def clip_source_range(
    clip: str | None = typer.Argument(None, help="Clip name (current clip when omitted)"),
):
    """Show source-domain range information for a Fairlight timeline clip."""
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            _fairlight_clip_readback_dry_run_payload(
                action="fairlight.clip.source_range",
                clip=clip,
                native_api="TimelineItem.GetStart/GetEnd/GetDuration/GetLeftOffset/GetRightOffset",
                delegated_action="clip.source_range",
                command="source-range",
                read_scope="timeline_item_source_range",
            ),
            title="Fairlight Clip Source Range Plan",
        )
        return
    conn = get_connection(require_timeline=True)
    data = clip_ops.get_source_range(conn, clip)
    output(
        {
            "action": "fairlight.clip.source_range",
            "target": {"kind": "timeline_item", "clip": data.get("clip"), "audio_focus": True},
            "route": "api_native",
            "native_api": "TimelineItem.GetStart/GetEnd/GetDuration/GetLeftOffset/GetRightOffset",
            "delegated_action": "clip.source_range",
            **data,
        },
        title="Fairlight Clip Source Range",
    )


@clip_app.command("track-info")
@handle_errors
def clip_track_info(
    clip: str | None = typer.Argument(None, help="Clip name (current clip when omitted)"),
):
    """Show track type and index for a Fairlight timeline clip."""
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            _fairlight_clip_readback_dry_run_payload(
                action="fairlight.clip.track_info",
                clip=clip,
                native_api="TimelineItem.GetTrackTypeAndIndex()",
                delegated_action="clip.track_info",
                command="track-info",
                read_scope="timeline_item_track_binding",
            ),
            title="Fairlight Clip Track Info Plan",
        )
        return
    conn = get_connection(require_timeline=True)
    data = clip_ops.get_track_info(conn, clip)
    output(
        {
            "action": "fairlight.clip.track_info",
            "target": {"kind": "timeline_item", "clip": data.get("clip"), "audio_focus": True},
            "route": "api_native",
            "native_api": "TimelineItem.GetTrackTypeAndIndex()",
            "delegated_action": "clip.track_info",
            **data,
        },
        title="Fairlight Clip Track Info",
    )


@clip_app.command("link")
@handle_errors
def clip_link(
    clips: list[str] = typer.Argument(..., help="Audio clip names to link"),
):
    """Link two or more Fairlight timeline clips through the native DaVinci Resolve API."""
    if len(clips) < 2:
        raise ValidationError(
            "Provide at least two audio clip names to link.",
            details={"clips": clips, "minimum": 2},
            recoverability="not_applicable",
        )
    enforce_mutation_policy("clip.link_unlink", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            mutation_payload(
                action="fairlight.clip.link",
                target={"kind": "timeline", "track_type": "audio"},
                changed=False,
                dry_run=True,
                route="api_native",
                native_api="Timeline.SetClipsLinked([timelineItems], True)",
                delegated_capability="clip.link_unlink",
                runtime_read_called=False,
                operation="link",
                linked=True,
                clip_count=len(clips),
                clips=clips,
                message=f"DRY-RUN: Would link {len(clips)} Fairlight clips.",
            ),
            title="Fairlight Clip Link Plan",
        )
        return
    conn = get_connection(require_timeline=True)
    plan = clip_ops.plan_clips_linked(conn, clips, True)
    result = clip_ops.set_clips_linked(conn, clips, True)
    readback = clip_ops.list_linked_items(conn, clips[0])
    set_verification_status("verified")
    set_recoverability("not_applicable")
    output(
        mutation_payload(
            action="fairlight.clip.link",
            target={"kind": "timeline", "track_type": "audio"},
            changed=bool(result),
            route="api_native",
            native_api="Timeline.SetClipsLinked([timelineItems], True)",
            delegated_capability="clip.link_unlink",
            **plan,
            result=bool(result),
            readback=readback,
            message=f"Linked {plan['clip_count']} Fairlight clips.",
        ),
        title="Fairlight Clip Link",
    )


@clip_linked_app.command("list")
@handle_errors
def clip_linked_list(
    clip: str | None = typer.Argument(None, help="Clip name (current clip when omitted)"),
):
    """List timeline items linked to a Fairlight timeline clip through the native DaVinci Resolve API."""
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            _fairlight_clip_readback_dry_run_payload(
                action="fairlight.clip.linked.list",
                clip=clip,
                native_api="TimelineItem.GetLinkedItems()",
                delegated_action="clip.linked.list",
                command="linked list",
                read_scope="timeline_item_linked_items",
            ),
            title="Fairlight Linked Clips Plan",
        )
        return
    conn = get_connection(require_timeline=True)
    data = clip_ops.list_linked_items(conn, clip)
    output(
        {
            "action": "fairlight.clip.linked.list",
            "target": {"kind": "timeline_item", "clip": data.get("clip"), "audio_focus": True},
            "route": "api_native",
            "native_api": "TimelineItem.GetLinkedItems()",
            "delegated_action": "clip.linked.list",
            **data,
        },
        title="Fairlight Linked Clips",
    )


@clip_app.command("unlink")
@handle_errors
def clip_unlink(
    clip_name: str = typer.Argument(..., help="Audio clip name to unlink"),
):
    """Unlink a Fairlight timeline clip through the native DaVinci Resolve API."""
    normalized_clip_name = clip_ops.normalize_explicit_clip_name(clip_name)
    enforce_mutation_policy("clip.link_unlink", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            mutation_payload(
                action="fairlight.clip.unlink",
                target={"kind": "timeline", "track_type": "audio"},
                changed=False,
                dry_run=True,
                route="api_native",
                native_api="Timeline.SetClipsLinked([timelineItems], False)",
                delegated_capability="clip.link_unlink",
                runtime_read_called=False,
                operation="unlink",
                linked=False,
                clip_count=1,
                clips=[normalized_clip_name],
                message=f"DRY-RUN: Would unlink Fairlight clip: {normalized_clip_name}",
            ),
            title="Fairlight Clip Unlink Plan",
        )
        return
    conn = get_connection(require_timeline=True)
    plan = clip_ops.plan_clips_linked(conn, [normalized_clip_name], False)
    result = clip_ops.set_clips_linked(conn, [normalized_clip_name], False)
    readback = clip_ops.list_linked_items(conn, normalized_clip_name)
    set_verification_status("verified")
    set_recoverability("not_applicable")
    output(
        mutation_payload(
            action="fairlight.clip.unlink",
            target={"kind": "timeline", "track_type": "audio"},
            changed=bool(result),
            route="api_native",
            native_api="Timeline.SetClipsLinked([timelineItems], False)",
            delegated_capability="clip.link_unlink",
            **plan,
            result=bool(result),
            readback=readback,
            message=f"Unlinked Fairlight clip: {plan['clips'][0]}",
        ),
        title="Fairlight Clip Unlink",
    )


@clip_app.command("move")
@handle_errors
def clip_move(
    timeline_name: str | None = typer.Option(None, "--timeline", help="Target timeline name; defaults to active timeline"),
    item_id: str | None = typer.Option(None, "--item-id", help="Project.db Sm2TiItem_id when known"),
    track_index: int = typer.Option(1, "--track", "--track-index", min=1, help="Audio track index for selector"),
    start_frame: str | None = typer.Option(None, "--start-frame", help="Current audio item start in record-domain frames/time"),
    current_end_frame: str | None = typer.Option(None, "--current-end-frame", help="Current audio item end for stricter selection"),
    name: str | None = typer.Option(None, "--name", help="Current timeline item name for stricter selection"),
    target_start_frame: str | None = typer.Option(None, "--to-start-frame", "--to", help="New audio item start in record-domain frames/time"),
    delta: str | None = typer.Option(None, "--delta", "--nudge", help="Signed move amount, e.g. 12f or -0.5s"),
    target_track_index: int | None = typer.Option(None, "--to-track", "--to-track-index", min=1, help="Destination audio track index; may be combined with --to-start-frame or --delta"),
    allow_overlap: bool = typer.Option(False, "--allow-overlap", help="Allow the moved audio item to overlap another item on the same track"),
    allow_linked_audio_only: bool = typer.Option(
        False,
        "--allow-linked-audio-only",
        help="Allow moving only the Fairlight audio item when native-linked video companions are present",
    ),
    include_linked_video: bool = typer.Option(
        False,
        "--include-linked-video",
        help="Move native-linked video companions by the same record-frame delta",
    ),
):
    """Move or nudge a Fairlight audio item through the Disk DB route."""
    set_execution_engine("db_workaround")
    enforce_mutation_policy("fairlight.clip_move", intended_engine="db_workaround", mutating=not is_dry_run())
    if target_start_frame and delta:
        raise ValidationError(
            "Provide exactly one of --to-start-frame/--to or --delta/--nudge.",
            details={"target_start_frame": target_start_frame, "delta": delta},
        )
    if not target_start_frame and not delta and target_track_index is None:
        raise ValidationError(
            "Provide --to-track, or exactly one of --to-start-frame/--to or --delta/--nudge.",
            details={"target_start_frame": target_start_frame, "delta": delta, "target_track_index": target_track_index},
        )
    if allow_linked_audio_only and include_linked_video:
        raise ValidationError(
            "Choose only one linked A/V mode: --include-linked-video or --allow-linked-audio-only.",
            details={"allow_linked_audio_only": True, "include_linked_video": True},
        )
    selector = {
        "item_id": item_id,
        "track_type": "audio",
        "track_index": track_index,
        "start_frame": start_frame,
        "current_end_frame": current_end_frame,
        "name": name,
    }
    requested = {
        "target_start_frame": target_start_frame,
        "delta": delta,
        "target_track_index": target_track_index,
        "allow_overlap": bool(allow_overlap),
        "allow_linked_audio_only": bool(allow_linked_audio_only),
        "include_linked_video": bool(include_linked_video),
    }
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            mutation_payload(
                action="fairlight.clip.move",
                changed=False,
                target={"kind": "timeline", "name": timeline_name},
                selector=selector,
                requested=requested,
                delegated_action="timeline.items.move",
                command_intent={
                    "move_item": True,
                    "move_track": target_track_index is not None,
                    "move_start": bool(target_start_frame or delta),
                    "delete_items": False,
                    "ripple_timeline": False,
                    "audio_only": not bool(include_linked_video),
                    "linked_av_group": bool(include_linked_video),
                    "include_linked_video": bool(include_linked_video),
                    "route": "db_workaround",
                },
                message="DRY-RUN: Would move a Fairlight audio clip through the Disk DB route.",
            ),
            title="Fairlight Clip Move Plan",
        )
        return

    conn = get_connection(require_project=True, require_timeline=timeline_name is None)
    data = timeline_item_move_db.move_timeline_item(
        conn,
        timeline_name=timeline_name,
        item_id=item_id,
        track_type="audio",
        track_index=track_index,
        start_frame=start_frame,
        current_end_frame=current_end_frame,
        name=name,
        target_start_frame=target_start_frame,
        delta=delta,
        target_track_index=target_track_index,
        allow_overlap=allow_overlap,
        allow_linked_audio_only=allow_linked_audio_only,
        include_linked_video=include_linked_video,
        require_fairlight_edit_contract=True,
    )
    updated_items = data.get("updated_items") if isinstance(data, dict) else None
    output(
        mutation_payload(
            action="fairlight.clip.move",
            changed=bool(updated_items),
            target={"kind": "timeline", "name": data.get("timeline_name") if isinstance(data, dict) else timeline_name},
            selector=selector,
            requested=data.get("requested") if isinstance(data, dict) else requested,
            updated_items=updated_items,
            readback=data.get("verification") if isinstance(data, dict) else None,
            linked_video_included=data.get("linked_video_included") if isinstance(data, dict) else None,
            project_db_path=data.get("project_db_path") if isinstance(data, dict) else None,
            backup_path=data.get("backup_path") if isinstance(data, dict) else None,
            steps=data.get("steps") if isinstance(data, dict) else None,
            route=data.get("route") if isinstance(data, dict) else "db_native",
            delegated_action="timeline.items.move",
            **_fairlight_no_change_payload_fields(data),
            message="Moved Fairlight audio clip.",
        ),
        title="Fairlight Clip Move",
    )


@clip_app.command("nudge")
@handle_errors
def clip_nudge(
    timeline_name: str | None = typer.Option(None, "--timeline", help="Target timeline name; defaults to active timeline"),
    item_id: str | None = typer.Option(None, "--item-id", help="Project.db Sm2TiItem_id when known"),
    track_index: int = typer.Option(1, "--track", "--track-index", min=1, help="Audio track index for selector"),
    start_frame: str | None = typer.Option(None, "--start-frame", help="Current audio item start in record-domain frames/time"),
    current_end_frame: str | None = typer.Option(None, "--current-end-frame", help="Current audio item end for stricter selection"),
    name: str | None = typer.Option(None, "--name", help="Current timeline item name for stricter selection"),
    delta: str | None = typer.Option(None, "--delta", "--nudge", "--by", help="Signed nudge amount, e.g. 12f or -0.5s"),
    allow_overlap: bool = typer.Option(False, "--allow-overlap", help="Allow the nudged audio item to overlap another item on the same track"),
    allow_linked_audio_only: bool = typer.Option(
        False,
        "--allow-linked-audio-only",
        help="Allow nudging only the Fairlight audio item when native-linked video companions are present",
    ),
    include_linked_video: bool = typer.Option(
        False,
        "--include-linked-video",
        help="Nudge native-linked video companions by the same record-frame delta",
    ),
):
    """Nudge a Fairlight audio item earlier/later through the verified Disk DB move route."""
    set_execution_engine("db_workaround")
    enforce_mutation_policy("fairlight.clip_move", intended_engine="db_workaround", mutating=not is_dry_run())
    if not delta:
        raise ValidationError(
            "Provide --delta/--nudge/--by for the Fairlight clip nudge amount.",
            details={
                "delta": delta,
                "example": "cutagent fairlight clip nudge --track 1 --start-frame 36f --delta 12f --json",
            },
        )
    if allow_linked_audio_only and include_linked_video:
        raise ValidationError(
            "Choose only one linked A/V mode: --include-linked-video or --allow-linked-audio-only.",
            details={"allow_linked_audio_only": True, "include_linked_video": True},
        )
    selector = {
        "item_id": item_id,
        "track_type": "audio",
        "track_index": track_index,
        "start_frame": start_frame,
        "current_end_frame": current_end_frame,
        "name": name,
    }
    requested = {
        "delta": delta,
        "allow_overlap": bool(allow_overlap),
        "allow_linked_audio_only": bool(allow_linked_audio_only),
        "include_linked_video": bool(include_linked_video),
    }
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            mutation_payload(
                action="fairlight.clip.nudge",
                changed=False,
                target={"kind": "timeline", "name": timeline_name},
                selector=selector,
                requested=requested,
                delegated_action="timeline.items.move",
                command_intent={
                    "move_item": True,
                    "move_track": False,
                    "move_start": True,
                    "delete_items": False,
                    "ripple_timeline": False,
                    "audio_only": not bool(include_linked_video),
                    "linked_av_group": bool(include_linked_video),
                    "include_linked_video": bool(include_linked_video),
                    "route": "db_workaround",
                },
                message="DRY-RUN: Would nudge a Fairlight audio clip through the Disk DB route.",
            ),
            title="Fairlight Clip Nudge Plan",
        )
        return

    conn = get_connection(require_project=True, require_timeline=timeline_name is None)
    data = timeline_item_move_db.move_timeline_item(
        conn,
        timeline_name=timeline_name,
        item_id=item_id,
        track_type="audio",
        track_index=track_index,
        start_frame=start_frame,
        current_end_frame=current_end_frame,
        name=name,
        target_start_frame=None,
        delta=delta,
        target_track_index=None,
        allow_overlap=allow_overlap,
        allow_linked_audio_only=allow_linked_audio_only,
        include_linked_video=include_linked_video,
        require_fairlight_edit_contract=True,
    )
    updated_items = data.get("updated_items") if isinstance(data, dict) else None
    output(
        mutation_payload(
            action="fairlight.clip.nudge",
            changed=bool(updated_items),
            target={"kind": "timeline", "name": data.get("timeline_name") if isinstance(data, dict) else timeline_name},
            selector=selector,
            requested=data.get("requested") if isinstance(data, dict) else requested,
            updated_items=updated_items,
            readback=data.get("verification") if isinstance(data, dict) else None,
            project_db_path=data.get("project_db_path") if isinstance(data, dict) else None,
            backup_path=data.get("backup_path") if isinstance(data, dict) else None,
            steps=data.get("steps") if isinstance(data, dict) else None,
            route=data.get("route") if isinstance(data, dict) else "db_native",
            delegated_action="timeline.items.move",
            **_fairlight_no_change_payload_fields(data),
            message="Nudged Fairlight audio clip.",
        ),
        title="Fairlight Clip Nudge",
    )


@clip_app.command("slip")
@handle_errors
def clip_slip(
    timeline_name: str | None = typer.Option(None, "--timeline", help="Target timeline name; defaults to active timeline"),
    item_id: str | None = typer.Option(None, "--item-id", help="Project.db Sm2TiItem_id when known"),
    track_index: int = typer.Option(1, "--track", "--track-index", min=1, help="Audio track index for selector"),
    start_frame: str | None = typer.Option(None, "--start-frame", help="Current audio item start in record-domain frames/time"),
    current_end_frame: str | None = typer.Option(None, "--current-end-frame", help="Current audio item end for stricter selection"),
    name: str | None = typer.Option(None, "--name", help="Current timeline item name for stricter selection"),
    source_start_frame: str | None = typer.Option(None, "--source-start-frame", "--source-in-frame", "--source-in", help="New source In frame/time for the selected audio item"),
    delta: str | None = typer.Option(None, "--delta", "--slip", help="Signed source slip amount, e.g. 12f or -0.5s"),
    allow_linked_audio_only: bool = typer.Option(
        False,
        "--allow-linked-audio-only",
        help="Allow slipping only the Fairlight audio item when native-linked video companions are present",
    ),
    include_linked_video: bool = typer.Option(
        False,
        "--include-linked-video",
        help="Slip native-linked video companions by the same source-frame delta",
    ),
):
    """Slip a Fairlight audio item's source In frame while preserving its timeline range."""
    set_execution_engine("db_workaround")
    enforce_mutation_policy("fairlight.clip_slip", intended_engine="db_workaround", mutating=not is_dry_run())
    if bool(source_start_frame) == bool(delta):
        raise ValidationError(
            "Provide exactly one of --source-start-frame/--source-in-frame or --delta/--slip.",
            details={"source_start_frame": source_start_frame, "delta": delta},
        )
    if allow_linked_audio_only and include_linked_video:
        raise ValidationError(
            "Choose only one linked A/V mode: --include-linked-video or --allow-linked-audio-only.",
            details={"allow_linked_audio_only": True, "include_linked_video": True},
        )
    selector = {
        "item_id": item_id,
        "track_type": "audio",
        "track_index": track_index,
        "start_frame": start_frame,
        "current_end_frame": current_end_frame,
        "name": name,
    }
    requested = {
        "source_start_frame": source_start_frame,
        "delta": delta,
        "allow_linked_audio_only": bool(allow_linked_audio_only),
        "include_linked_video": bool(include_linked_video),
    }
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            mutation_payload(
                action="fairlight.clip.slip",
                changed=False,
                target={"kind": "timeline", "name": timeline_name},
                selector=selector,
                requested=requested,
                delegated_action="timeline.items.slip_source",
                command_intent={
                    "slip_source": True,
                    "preserve_timeline_range": True,
                    "audio_only": not bool(include_linked_video),
                    "linked_av_group": bool(include_linked_video),
                    "include_linked_video": bool(include_linked_video),
                    "route": "db_workaround",
                },
                message="DRY-RUN: Would slip a Fairlight audio clip source In frame through the Disk DB route.",
            ),
            title="Fairlight Clip Slip Plan",
        )
        return

    conn = get_connection(require_project=True, require_timeline=timeline_name is None)
    data = timeline_item_duration_db.slip_timeline_item_source(
        conn,
        timeline_name=timeline_name,
        item_id=item_id,
        track_type="audio",
        track_index=track_index,
        start_frame=start_frame,
        current_end_frame=current_end_frame,
        name=name,
        source_start_frame=source_start_frame,
        delta=delta,
        allow_linked_audio_only=allow_linked_audio_only,
        include_linked_video=include_linked_video,
        require_fairlight_edit_contract=True,
    )
    updated_items = data.get("updated_items") if isinstance(data, dict) else None
    output(
        mutation_payload(
            action="fairlight.clip.slip",
            changed=bool(updated_items),
            target={"kind": "timeline", "name": data.get("timeline_name") if isinstance(data, dict) else timeline_name},
            selector=selector,
            requested=data.get("requested") if isinstance(data, dict) else requested,
            updated_items=updated_items,
            readback=data.get("verification") if isinstance(data, dict) else None,
            linked_video_included=data.get("linked_video_included") if isinstance(data, dict) else None,
            project_db_path=data.get("project_db_path") if isinstance(data, dict) else None,
            backup_path=data.get("backup_path") if isinstance(data, dict) else None,
            steps=data.get("steps") if isinstance(data, dict) else None,
            route=data.get("route") if isinstance(data, dict) else "db_native",
            delegated_action="timeline.items.slip_source",
            **_fairlight_no_change_payload_fields(data),
            message="Slipped Fairlight audio clip source.",
        ),
        title="Fairlight Clip Slip",
    )


def _fairlight_transition_item_summary(item: Any) -> dict[str, Any]:
    row: dict[str, Any] = {}
    for key, attr in (("name", "GetName"), ("start", "GetStart"), ("end", "GetEnd"), ("duration", "GetDuration")):
        getter = getattr(item, attr, None)
        if not callable(getter):
            continue
        try:
            value = getter()
            if key in {"start", "end", "duration"}:
                value = int(value)
            row[key] = value
        except Exception:
            pass
    return row


def _verify_fairlight_transition_readback(conn: Any, mutation_result: Any, _session: Any) -> dict[str, Any]:
    inserted = list((mutation_result or {}).get("inserted") or []) if isinstance(mutation_result, dict) else []
    skipped_existing = list((mutation_result or {}).get("skipped_existing") or []) if isinstance(mutation_result, dict) else []
    if not inserted and skipped_existing:
        return {
            "status": "verified",
            "inserted_count": 0,
            "skipped_existing_count": len(skipped_existing),
            "checks": [],
        }
    checks: list[dict[str, Any]] = []
    db_rows_by_id: dict[str, dict[str, Any]] = {}
    project_db_path = getattr(_session, "project_db_path", None)
    if project_db_path:
        try:
            connection = sqlite3.connect(str(project_db_path))
            connection.row_factory = sqlite3.Row
            try:
                ids = [str(row.get("item_id")) for row in inserted if row.get("item_id")]
                if ids:
                    placeholders = ",".join("?" for _ in ids)
                    for db_row in connection.execute(
                        f"""
                        SELECT Sm2TiItem_id, DbType, PrettyType, Start, Duration, Sm2TiTrack_id
                        FROM Sm2TiItem
                        WHERE Sm2TiItem_id IN ({placeholders})
                        """,
                        ids,
                    ).fetchall():
                        db_rows_by_id[str(db_row["Sm2TiItem_id"])] = dict(db_row)
            finally:
                connection.close()
        except Exception:
            db_rows_by_id = {}
    items_by_track: dict[tuple[str, int], list[dict[str, Any]]] = {}
    for row in inserted:
        track_type = str(row.get("track_type") or "audio").lower()
        track_index = int(row.get("track_index") or 1)
        expected_start = int(row.get("start") or 0)
        expected_duration = int(row.get("duration") or 0)
        expected_name = str(row.get("pretty_type") or "").lower()
        item_id = str(row.get("item_id") or "")
        db_row = db_rows_by_id.get(item_id)
        db_ok = bool(
            db_row
            and str(db_row.get("PrettyType") or "").lower() == expected_name
            and int(db_row.get("Start") or -1) == expected_start
            and int(db_row.get("Duration") or -1) == expected_duration
            and str(db_row.get("DbType") or "") == "Sm2TiTransition"
        )
        track_key = (track_type, track_index)
        try:
            if track_key not in items_by_track:
                items_by_track[track_key] = [
                    _fairlight_transition_item_summary(item)
                    for item in (conn.timeline.GetItemListInTrack(track_type, track_index) or [])
                ]
            items = items_by_track[track_key]
        except Exception as exc:
            checks.append(
                {
                    "ok": db_ok,
                    "track_type": track_type,
                    "track_index": track_index,
                    "expected": row,
                    "db_match": db_row,
                    "matches": [],
                    "live_api_error": str(exc),
                }
            )
            continue

        matches = []
        for summary in items:
            if int(summary.get("start", -1)) != expected_start:
                continue
            if expected_duration and int(summary.get("duration", -1)) != expected_duration:
                continue
            if expected_name and expected_name not in str(summary.get("name") or "").lower():
                continue
            matches.append(summary)
        checks.append(
            {
                "ok": db_ok or bool(matches),
                "track_type": track_type,
                "track_index": track_index,
                "expected": row,
                "db_match": db_row,
                "matches": matches,
            }
        )

    return {
        "status": "verified" if inserted and all(check["ok"] for check in checks) else "failed",
        "inserted_count": len(inserted),
        "checks": checks,
    }


_FAIRLIGHT_AUDIO_TRANSITION_TYPES = {
    "cross-dissolve",
    "cross-fade-0db",
    "cross-fade-3db",
    "cross-fade+3db",
}


_FAIRLIGHT_TRANSITION_NATIVE_PROBE_EVIDENCE = {
    "runtime": "DaVinci Resolve 20.3.2.9 Free",
    "transport": "direct_utility_lua_script",
    "probe_project": "CUTAGENT_FAIRLIGHT_PARITY_20260605_175239",
    "probe_timeline": "FL_PARITY_24FPS",
    "baseline_verified_methods": [
        "Project.GetName()",
        "Timeline.GetName()",
        "Timeline.GetTrackCount('audio')",
        "Timeline.GetItemListInTrack('audio', 1)",
    ],
    "candidate_methods_not_available": [
        "Timeline.GetTransitions()",
        "Timeline.GetTransitionList()",
        "Timeline.GetTransitionItems()",
        "Timeline.GetTransitionItemsInTrack('audio', 1)",
        "Timeline.GetAudioTransitions()",
        "Timeline.GetAudioTransitionList()",
        "TimelineItem.GetTransitions()",
        "TimelineItem.GetLeftTransition()",
        "TimelineItem.GetRightTransition()",
        "TimelineItem.GetTransitionProperties()",
    ],
    "mutating_candidates_not_called": [
        "Timeline.AddTransition(...)",
        "Timeline.AddAudioTransition(...)",
        "Timeline.ApplyTransition(...)",
        "Timeline.SetTransitionProperty(...)",
        "TimelineItem.SetLeftTransition(...)",
        "TimelineItem.SetRightTransition(...)",
    ],
    "probe_result": "transition getter candidates returned method_not_available; transition add/apply/property mutation candidates were not called",
    "transition_native_readback_supported": False,
    "transition_native_custom_curve_supported": False,
    "transition_native_mutation_supported": False,
}


_FAIRLIGHT_AUDIO_TRANSITION_RESIDUAL_EVIDENCE = {
    "available_db_route": (
        "Verified Fairlight audio transition insertion writes Sm2TiTransition Cross Fade rows through the "
        "DB-backed edit transition route with audio scope and reopened Project.db readback."
    ),
    "transition_model_evidence": {
        "supported_transition_table": "Sm2TiItem",
        "supported_transition_db_type": "Sm2TiTransition",
        "supported_pretty_types": ["Cross Fade 0DB", "Cross Fade -3DB", "Cross Fade +3DB"],
        "audio_scope_supported": True,
        "custom_fade_curve_supported": False,
        "video_transition_family_supported_in_fairlight_namespace": False,
        "unverified_transition_semantics": [
            "custom Fairlight fade curve or shape selection",
            "non-crossfade audio transition families",
            "video transition families in the Fairlight audio namespace",
            "live timeline API transition-object readback",
        ],
    },
    "db_schema_evidence": {
        "source": "local DaVinci Resolve 20 Free Project.db schema probes",
        "sampled_project_db_count": 5,
        "read_scope": "transition_family_schema_probe",
        "verified_audio_transition_route": "Sm2TiItem rows with DbType=Sm2TiTransition and audio track scope",
        "sampled_transition_storage": [
            "Sm2TiItem.DbType",
            "Sm2TiItem.PrettyType",
            "Sm2TiItem.Start",
            "Sm2TiItem.Duration",
            "Sm2TiItem.Sm2TiTrack_id",
            "Sm2TiItem.FieldsBlob",
            "SM_TransitionItem.Name",
            "SM_TransitionItem.Effect",
        ],
        "sampled_pretty_types_seen": [
            "Cross Dissolve",
            "Cross Fade +3DB",
            "Cross Fade -3DB",
            "Cross Fade 0DB",
            "Fusion Transition",
            "Smooth Cut",
        ],
        "supported_audio_pretty_types_verified": [
            "Cross Fade 0DB",
            "Cross Fade -3DB",
            "Cross Fade +3DB",
        ],
        "sm_transition_item_rows_seen_in_samples": 0,
        "custom_fade_curve_column_found_in_samples": False,
        "custom_fade_shape_column_found_in_samples": False,
        "fairlight_audio_family_discriminator_found_in_samples": False,
        "live_transition_object_readback_found_in_samples": False,
        "generic_transition_pretty_types_are_not_fairlight_namespace_support": True,
    },
    "native_probe_evidence": _FAIRLIGHT_TRANSITION_NATIVE_PROBE_EVIDENCE,
    "db_blocker_note": (
        "The Fairlight namespace only claims verified audio crossfade DB insertion. Other transition families "
        "remain blocked until their DB payloads and readback semantics are mapped for Fairlight audio."
    ),
}


def _normalize_fairlight_audio_transition(transition_type: str) -> str:
    try:
        normalized_transition = transition_db.normalize_transition_name(transition_type)
    except ValidationError as exc:
        details = dict(getattr(exc, "details", None) or {})
        details.update(_FAIRLIGHT_AUDIO_TRANSITION_RESIDUAL_EVIDENCE)
        details["supported_audio_transitions"] = sorted(_FAIRLIGHT_AUDIO_TRANSITION_TYPES)
        raise ValidationError(
            "Unsupported Fairlight audio transition type.",
            details=details,
        ) from exc
    if normalized_transition not in _FAIRLIGHT_AUDIO_TRANSITION_TYPES:
        raise ValidationError(
            "Unsupported Fairlight audio transition type.",
            details={
                "transition_type": transition_type,
                "normalized_transition": normalized_transition,
                "supported_audio_transitions": sorted(_FAIRLIGHT_AUDIO_TRANSITION_TYPES),
                "unsupported_transition_scope": "video_or_custom_transition_family",
                **_FAIRLIGHT_AUDIO_TRANSITION_RESIDUAL_EVIDENCE,
            },
        )
    return normalized_transition


@transition_app.command("add")
@handle_errors
def transition_add(
    transition_type: str = typer.Argument(..., help="Audio transition type: cross-fade-0db, cross-fade-3db, cross-fade+3db, or cross-dissolve"),
    duration: str | None = typer.Argument(None, help="Transition duration (default: 24f, e.g. 12f, 0.5s, 00:00:00:12)"),
    at: str | None = typer.Option(None, "--at", help="Record-domain position where the audio transition is applied"),
    clip_name: str | None = typer.Option(None, "--clip", help="Target audio clip name for deterministic selection"),
    placement: str = typer.Option("both", "--placement", help="Placement: start|end|both"),
):
    """Add a Fairlight audio transition object through the Disk DB route."""
    set_execution_engine("db_workaround")
    enforce_mutation_policy("fairlight.transition", intended_engine="db_workaround", mutating=not is_dry_run())
    normalized_transition = _normalize_fairlight_audio_transition(transition_type)
    requested = {
        "transition_type": normalized_transition,
        "duration": duration,
        "at": at,
        "clip": clip_name,
        "placement": placement,
        "scope": "audio",
    }
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            mutation_payload(
                action="fairlight.transition.add",
                changed=False,
                target={"kind": "timeline", "name": None},
                requested=requested,
                delegated_action="edit.transition.add",
                command_intent={
                    "add_transition_object": True,
                    "scope": "audio",
                    "route": "db_workaround",
                },
                message="DRY-RUN: Would add a Fairlight audio transition object through the Disk DB route.",
            ),
            title="Fairlight Transition Add Plan",
        )
        return

    conn = get_connection(require_timeline=True)
    audio_selection = db_timeline_selection.resolve_audio_group(conn, clip_name=clip_name, at=at)
    audio_item = audio_selection["audio"]
    timeline_name = conn.timeline.GetName() if getattr(conn, "timeline", None) else None
    duration_ref = duration.strip() if isinstance(duration, str) and duration.strip() else None
    if duration_ref is None:
        duration_frames = transition_db.default_transition_duration_frames_for_targets(video_item=None, audio_item=audio_item)
    else:
        duration_frames = seconds_to_frames(parse_time_input(duration_ref, conn.fps), conn.fps)
        if duration_frames <= 0:
            raise ValidationError("Transition duration must be greater than 0.", details={"duration": duration_ref})
    at_frame = parse_record_frame(str(at), conn.fps, conn.start_frame) if at else None

    data = db_session.execute_sqlite_disk_db_mutation(
        conn,
        context="DB-backed Fairlight audio transition add",
        writer=lambda _connection, cursor, _session: transition_db.add_transition_rows(
            cursor,
            video_item=None,
            audio_item=audio_item,
            transition_name=normalized_transition,
            duration_frames=duration_frames,
            placement=placement,
            scope="audio",
            timeline_name=timeline_name,
            at_frame=at_frame,
        ),
        verifier=_verify_fairlight_transition_readback,
        allow_project_name_inference=True,
    )
    output(
        mutation_payload(
            action="fairlight.transition.add",
            changed=bool(data.get("inserted")) if isinstance(data, dict) else False,
            target={"kind": "timeline", "name": timeline_name},
            requested={**requested, "duration_frames": duration_frames},
            selected_audio={
                "track_type": audio_item.track_type,
                "track_index": audio_item.track_index,
                "name": audio_item.name,
                "start": audio_item.start,
                "duration": audio_item.duration,
            },
            inserted=data.get("inserted") if isinstance(data, dict) else None,
            skipped_existing=data.get("skipped_existing") if isinstance(data, dict) else None,
            readback=data.get("verification") if isinstance(data, dict) else None,
            route=data.get("route") if isinstance(data, dict) else "db_native",
            project_db_path=data.get("project_db_path") if isinstance(data, dict) else None,
            backup_path=data.get("backup_path") if isinstance(data, dict) else None,
            steps=data.get("steps") if isinstance(data, dict) else None,
            delegated_action="edit.transition.add",
            message="Added Fairlight audio transition object.",
        ),
        title="Fairlight Transition Add",
    )


@app.command("tracks")
@handle_errors
def tracks():
    """List audio tracks."""
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            {
                "action": "fairlight.tracks",
                "dry_run": True,
                "runtime_read_called": False,
                "route": "api_native",
                "native_api": (
                    'Timeline.GetTrackCount("audio")/GetTrackName/GetTrackSubType/'
                    "GetIsTrackEnabled/GetIsTrackLocked/GetItemListInTrack"
                ),
                "read_scope": "audio_track_list",
                "optional_db_readbacks": ["mixer", "display"],
                "preflight_command": "cutagent fairlight tracks --json",
            },
            title="Audio Tracks Plan",
        )
        return
    conn = get_connection(require_timeline=True)
    rows = fairlight_ops.list_audio_tracks(conn)
    if any(row.get("mixer") or row.get("display") or row.get("source") == "disk_project_db" for row in rows):
        set_execution_engine("db_workaround")
    output(rows, columns=[
        ("index", "#"), ("name", "Name"), ("clips", "Clips"),
        ("format", "Format"), ("fader_db", "Fader"), ("pan", "Pan"),
        ("enabled", "On"), ("locked", "Lock"), ("color", "Color"),
    ], title="Audio Tracks")


@app.command("add")
@handle_errors
def add_track(
    track_type: str = typer.Option(
        "mono",
        "--track-type",
        help="Audio format: mono, stereo, lcr, 5.1film, 7.1film, adaptive1..adaptive36",
    ),
    index: int | None = typer.Option(None, "--index", min=1, help="Optional 1-based insertion index"),
):
    """Add an audio track through the native DaVinci Resolve API."""
    normalized_type = _validate_audio_track_type(track_type)
    requested_type = str(track_type).strip().lower()
    enforce_mutation_policy("fairlight.track_management", intended_engine="api_native", mutating=not is_dry_run())

    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            mutation_payload(
                action="fairlight.add",
                target={"kind": "audio_track", "track_type": "audio", "index": int(index) if index else None},
                changed=False,
                track_type=normalized_type,
                requested_track_type=requested_type,
                legacy_alias_applied=requested_type != normalized_type,
                insertion_index=int(index) if index else None,
                would_add=True,
                dry_run=True,
                native_api=(
                    'Timeline.AddTrack("audio", {"audioType": track_type, "index": index})'
                    if index
                    else 'Timeline.AddTrack("audio", track_type)'
                ),
            ),
            title="Fairlight Add Track",
        )
        return

    conn = get_connection(require_timeline=True)
    before_count = conn.timeline.GetTrackCount("audio") or 0
    max_insert_index = int(before_count) + 1
    if index is not None and index > max_insert_index:
        raise ValidationError(
            "Audio track insertion index is out of range.",
            details={
                "track_type": "audio",
                "index": int(index),
                "min": 1,
                "max_insert_index": max_insert_index,
                "audio_tracks_before": int(before_count),
                "append_command": f"cutagent fairlight add --track-type {normalized_type} --json",
            },
        )

    fairlight_ops.add_audio_track(conn, normalized_type, index=index)
    after_count = conn.timeline.GetTrackCount("audio") or 0
    deadline = time.monotonic() + 2.0
    while after_count <= before_count and time.monotonic() < deadline:
        time.sleep(0.1)
        after_count = conn.timeline.GetTrackCount("audio") or 0
    if after_count <= before_count:
        raise APICallFailed(
            "Audio track add did not appear in timeline readback.",
            details={
                "track_type": normalized_type,
                "audio_tracks_before": before_count,
                "audio_tracks_after": after_count,
            },
        )
    created_index = int(index) if index is not None else int(after_count)
    readback_format = fairlight_ops._read_audio_track_subtype(conn, created_index)
    if readback_format is not None and readback_format != normalized_type:
        set_verification_status("failed")
        raise APICallFailed(
            "Audio track format readback did not match requested format.",
            details={
                "requested_track_type": normalized_type,
                "readback_track_type": readback_format,
                "created_track_index": created_index,
                "audio_tracks_before": before_count,
                "audio_tracks_after": after_count,
            },
        )
    set_verification_status("verified" if readback_format is not None else "pending_manual")
    output(
        {
            "message": f"Added {normalized_type} audio track.",
            "track_type": normalized_type,
            "requested_track_type": requested_type,
            "legacy_alias_applied": requested_type != normalized_type,
            "created_track_index": created_index,
            "readback_track_type": readback_format,
            "format_verified": readback_format is not None,
            "audio_tracks_before": before_count,
            "audio_tracks_after": after_count,
            "created": True,
        },
        title="Fairlight Add Track",
    )


@app.command("delete")
@handle_errors
def delete_track(
    index: int = typer.Argument(..., help="Audio track index"),
    force: bool = typer.Option(False, "--force", help="Required for live audio track deletion"),
):
    """Delete an audio track through the native DaVinci Resolve API."""
    enforce_mutation_policy("fairlight.track_management", intended_engine="api_native", mutating=not is_dry_run())
    if index < 1:
        raise ValidationError(
            "Audio track index is out of range.",
            details={"track_type": "audio", "index": index, "min": 1},
        )
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            mutation_payload(
                action="fairlight.delete",
                target={"kind": "audio_track", "track_type": "audio", "index": int(index)},
                changed=False,
                would_delete=True,
                dry_run=True,
                requires_existing_track=True,
                native_api='Timeline.DeleteTrack("audio", index)',
            ),
            title="Fairlight Delete Track Plan",
        )
        return
    if not force:
        raise ValidationError(
            "Live audio track deletion requires --force.",
            details={
                "track_type": "audio",
                "index": int(index),
                "required_option": "--force",
                "dry_run_command": f"cutagent fairlight delete {index} --dry-run --json",
            },
            recoverability="retry_possible",
        )

    conn = get_connection(require_timeline=True)
    data = fairlight_ops.delete_audio_track(conn, index)
    output(
        mutation_payload(
            action=data.pop("action", "fairlight.delete"),
            target={"kind": "audio_track", "track_type": "audio", "index": int(index)},
            changed=True,
            **data,
        ),
        title="Fairlight Delete Track",
    )


@app.command("ensure-tracks")
@handle_errors
def ensure_tracks(
    count: int = typer.Option(..., "--count", min=1, help="Minimum number of matching audio tracks to ensure"),
    track_type: str = typer.Option(
        "stereo",
        "--track-type",
        help="Audio format: mono, stereo, lcr, 5.1film, 7.1film, adaptive1..adaptive36",
    ),
    timeline: str | None = typer.Option(None, "--timeline", help="Optional target timeline name"),
    allow_existing: bool = typer.Option(
        True,
        "--allow-existing/--no-allow-existing",
        help="Count existing tracks with matching format when format readback is available",
    ),
):
    """Ensure the target timeline has at least N native audio tracks of a requested format."""
    normalized_type = _validate_audio_track_type(track_type)
    requested_type = str(track_type).strip().lower()
    enforce_mutation_policy("fairlight.track_management", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            mutation_payload(
                action="fairlight.ensure_tracks",
                target={"kind": "timeline", "name": timeline or "current"},
                changed=False,
                requested_count=int(count),
                track_type=normalized_type,
                requested_track_type=requested_type,
                legacy_alias_applied=requested_type != normalized_type,
                timeline=timeline,
                allow_existing=bool(allow_existing),
                native_plan='Timeline.AddTrack("audio", track_type) until matching track count reaches --count',
                dry_run=True,
            ),
            title="Fairlight Ensure Tracks Plan",
        )
        return

    conn = get_connection(require_timeline=True)
    data = fairlight_ops.ensure_audio_tracks(
        conn,
        count=count,
        track_type=normalized_type,
        timeline_name=timeline,
        allow_existing=allow_existing,
    )
    target = dict(data.pop("target"))
    changed = bool(data.get("created_count"))
    output(
        mutation_payload(
            action="fairlight.ensure_tracks",
            target=target,
            changed=changed,
            **data,
        ),
        title="Fairlight Ensure Tracks",
    )


@app.command("ensure-stereo-tracks")
@handle_errors
def ensure_stereo_tracks(
    count: int = typer.Option(..., "--count", min=1, help="Minimum number of audio tracks to ensure"),
    timeline: str | None = typer.Option(None, "--timeline", help="Optional target timeline name"),
    db_subtype: int = typer.Option(0, "--db-subtype", min=0, help="Sm2TiTrack.SubType value for stereo tracks"),
    patch_db_subtype: bool = typer.Option(
        True,
        "--patch-db-subtype/--no-patch-db-subtype",
        help="Patch Sm2TiTrack.SubType for all target timeline audio tracks through Disk DB",
    ),
    allow_existing: bool = typer.Option(
        True,
        "--allow-existing/--no-allow-existing",
        help="If the target already has at least --count audio tracks, do not add more",
    ),
):
    """Ensure the target timeline has at least N stereo audio tracks."""
    engine = "db_workaround" if patch_db_subtype else "api_native"
    set_execution_engine(engine)
    enforce_mutation_policy("fairlight.stereo_track_management", intended_engine=engine, mutating=not is_dry_run())
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            mutation_payload(
                action="fairlight.ensure_stereo_tracks",
                target={"kind": "timeline", "name": timeline or "current"},
                changed=False,
                requested_count=int(count),
                timeline=timeline,
                patch_db_subtype=bool(patch_db_subtype),
                db_subtype=int(db_subtype),
                allow_existing=bool(allow_existing),
                native_plan='Timeline.AddTrack("audio", "stereo") until audio track count reaches --count',
                fallback_plan='Timeline.AddTrack("audio") if subtype add is unsupported or returns false',
                dry_run=True,
            ),
            title="Fairlight Ensure Stereo Tracks Plan",
        )
        return

    conn = get_connection(require_timeline=True)
    data = fairlight_ops.ensure_stereo_audio_tracks(
        conn,
        count=count,
        timeline_name=timeline,
        patch_db_subtype=patch_db_subtype,
        db_subtype=db_subtype,
        allow_existing=allow_existing,
    )
    target = dict(data.pop("target"))
    changed = bool(data.get("created_count")) or bool(data.get("db_subtype_patch", {}).get("requested"))
    output(
        mutation_payload(
            action="fairlight.ensure_stereo_tracks",
            target=target,
            changed=changed,
            **data,
        ),
        title="Fairlight Ensure Stereo Tracks",
    )


item_source_app = typer.Typer(help="Audio timeline item source-offset operations.")
app.add_typer(item_source_app, name="item-source")


def _load_item_source_batch(path: str) -> list[dict[str, object]]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValidationError(
            "Cannot read audio source patch batch JSON.",
            details={"path": path, "error": str(exc)},
            recoverability="not_applicable",
        ) from exc
    except json.JSONDecodeError as exc:
        raise ValidationError(
            "Audio source patch batch must be valid JSON.",
            details={"path": path, "error": str(exc)},
            recoverability="not_applicable",
        ) from exc

    if isinstance(payload, dict):
        for key in ("entries", "patches", "items"):
            if isinstance(payload.get(key), list):
                payload = payload[key]
                break
    if not isinstance(payload, list):
        raise ValidationError(
            "Audio source patch batch must be a JSON array or an object with entries/patches/items.",
            details={"path": path},
            recoverability="not_applicable",
        )
    if not payload:
        raise ValidationError(
            "Audio source patch batch must contain at least one entry.",
            details={"path": path},
            recoverability="not_applicable",
        )
    entries: list[dict[str, object]] = []
    for index, entry in enumerate(payload):
        if not isinstance(entry, dict):
            raise ValidationError(
                "Each audio source patch batch entry must be a JSON object.",
                details={"path": path, "index": index, "entry": entry},
                recoverability="not_applicable",
            )
        entries.append(dict(entry))
    return entries


def _single_item_source_patch_entry(
    *,
    item_id: str | None,
    track_index: int | None,
    record_frame: str | None,
    record_duration: str | None,
    record_end: str | None,
    source_start_frame: str | None,
    duration_frames: str | None,
    source_end_frame: str | None,
) -> dict[str, object]:
    entry: dict[str, object] = {}
    if item_id is not None:
        entry["item_id"] = item_id
    if track_index is not None:
        entry["track_index"] = int(track_index)
    if record_frame is not None:
        entry["record_frame"] = record_frame
    if record_duration is not None:
        entry["record_duration"] = record_duration
    if record_end is not None:
        entry["record_end"] = record_end
    if source_start_frame is not None:
        entry["source_start_frame"] = source_start_frame
    if duration_frames is not None:
        entry["duration_frames"] = duration_frames
    if source_end_frame is not None:
        entry["source_end_frame"] = source_end_frame
    return entry


@item_source_app.command("patch")
@handle_errors
def item_source_patch(
    timeline: str | None = typer.Option(None, "--timeline", help="Target timeline name; defaults to current timeline"),
    item_id: str | None = typer.Option(None, "--item-id", help="Direct Sm2TiItem_id selector"),
    track_index: int | None = typer.Option(None, "--track-index", min=1, help="Audio track index selector"),
    record_frame: str | None = typer.Option(None, "--record-frame", help="Record-domain item start reference"),
    record_duration: str | None = typer.Option(None, "--record-duration", help="Optional record-domain item duration check"),
    record_end: str | None = typer.Option(None, "--record-end", help="Optional record-domain item end check"),
    source_start_frame: str | None = typer.Option(None, "--source-start-frame", "--source-start", help="Source-domain start frame to write to Sm2TiItem.In"),
    duration_frames: str | None = typer.Option(None, "--duration-frames", "--duration", help="Duration to write; defaults to current Duration - source_start"),
    source_end_frame: str | None = typer.Option(None, "--source-end-frame", "--source-end", help="Source-domain end frame; writes end-start as Duration"),
    batch: str | None = typer.Option(None, "--batch", "--input", help="Batch JSON path"),
    allow_multiple: bool = typer.Option(False, "--allow-multiple/--no-allow-multiple", help="Patch all matches when track/start selector is ambiguous"),
):
    """Patch audio timeline item source In/Duration in DaVinci Resolve Disk DB."""
    set_execution_engine("db_workaround")
    enforce_mutation_policy("fairlight.item_source_patch", intended_engine="db_workaround", mutating=not is_dry_run())

    if batch:
        if any(
            value is not None
            for value in (
                item_id,
                track_index,
                record_frame,
                record_duration,
                record_end,
                source_start_frame,
                duration_frames,
                source_end_frame,
            )
        ):
            raise ValidationError(
                "--batch/--input cannot be combined with single-patch selector or source options.",
                details={"batch": batch},
                recoverability="not_applicable",
            )
        entries = _load_item_source_batch(batch)
    else:
        entries = [
            _single_item_source_patch_entry(
                item_id=item_id,
                track_index=track_index,
                record_frame=record_frame,
                record_duration=record_duration,
                record_end=record_end,
                source_start_frame=source_start_frame,
                duration_frames=duration_frames,
                source_end_frame=source_end_frame,
            )
        ]

    if is_dry_run():
        normalized = fairlight_ops.normalize_audio_source_patch_entries(
            entries,
            fps=24.0,
            timeline_start_frame=0,
            parse_record_refs=False,
        )
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            mutation_payload(
                action="fairlight.item_source.patch",
                target={"kind": "timeline", "name": timeline or "current"},
                changed=False,
                timeline=timeline,
                requested_patches=[
                    {key: value for key, value in patch.items() if key != "raw"}
                    for patch in normalized
                ],
                patch_count=len(normalized),
                allow_multiple=bool(allow_multiple),
                dry_run=True,
                record_refs_require_live_resolution=True,
            ),
            title="Fairlight Item Source Patch Plan",
        )
        return

    conn = get_connection(require_timeline=True)
    data = fairlight_ops.patch_audio_item_source_offsets(
        conn,
        timeline_name=timeline,
        patches=entries,
        allow_multiple=allow_multiple,
    )
    output(
        mutation_payload(
            action="fairlight.item_source.patch",
            target={"kind": "timeline", "name": data.get("timeline") or timeline or "current"},
            changed=bool(data.get("patched_count")),
            **data,
        ),
        title="Fairlight Item Source Patch",
    )


@app.command("rename")
@handle_errors
def rename(
    index: int = typer.Argument(..., help="Track index"),
    name: str = typer.Argument(..., help="New name"),
):
    """Rename an audio track."""
    enforce_mutation_policy("fairlight.track_management", intended_engine="api_native", mutating=not is_dry_run())
    if index < 1:
        raise ValidationError(
            "Audio track index is out of range.",
            details={
                "track_type": "audio",
                "index": index,
                "min": 1,
            },
        )
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            {
                "action": "fairlight.rename",
                "would_rename": True,
                "dry_run": True,
                "runtime_write_called": False,
                "track_type": "audio",
                "index": index,
                "name": name,
                "requires_existing_track": True,
            },
            title="Fairlight Rename Plan",
        )
        return
    conn = get_connection(require_timeline=True)
    _validate_audio_track_index(conn, index)
    fairlight_ops.rename_audio_track(conn, index, name)
    success(f"Renamed audio track {index} to: {name}")


@app.command("track-color")
@handle_errors
def track_color(
    index: int = typer.Argument(..., help="Track index"),
    color: str = typer.Argument(..., help="DaVinci Resolve Fairlight track color name, e.g. Apricot, Blue, Green, or Clear"),
):
    """Set an audio track color through the verified Fairlight Disk DB route."""
    enforce_mutation_policy("fairlight.track_color", intended_engine="db_workaround", mutating=not is_dry_run())
    if index < 1:
        raise ValidationError(
            "Audio track index is out of range.",
            details={"track_type": "audio", "index": index, "min": 1},
        )
    if is_dry_run():
        set_execution_engine("db_workaround")
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            {
                "action": "fairlight.track_color",
                "would_set": True,
                "conditional_native_write": False,
                "dry_run": True,
                "track_type": "audio",
                "index": index,
                "color": color,
                "requires_native_track_color_api": False,
                "route": "db_workaround",
                "native_api": {
                    "write": "Timeline.SetTrackColor('audio', index, color)",
                    "readback": "Timeline.GetTrackColor('audio', index) when exposed by the runtime",
                    "used_when_available": True,
                },
                "db_write": {"table": "Sm2TiTrack", "column": "FieldsBlob", "payload": "Color"},
                "db_readback": "Sm2TiTrack.FieldsBlob.Color after project reopen",
                "supported_track_colors": sorted(fairlight_ops._FAIRLIGHT_TRACK_COLOR_VALUES.keys()) + ["Clear"],
                "verified_gui_evidence": {
                    "artifact_dir": "/tmp/cutagent_track_color_gui_research_20260620",
                    "db_value_map_artifact": "/tmp/cutagent_track_color_gui_research_20260620/26_color_value_map_click_row.jsonl",
                    "screenshots": [
                        "/tmp/cutagent_track_color_gui_research_20260620/06_after_choose_blue.png",
                        "/tmp/cutagent_track_color_gui_research_20260620/13_after_choose_purple_retry.png",
                    ],
                },
            },
            title="Fairlight Track Color Plan",
        )
        return
    conn = get_connection(require_timeline=True)
    data = fairlight_ops.set_audio_track_color(conn, index, color)
    output(data, title="Fairlight Track Color")


@app.command("mute")
@handle_errors
def mute(index: int = typer.Argument(...)):
    """Mute an audio track."""
    enforce_mutation_policy("fairlight.track_state", intended_engine="api_native", mutating=not is_dry_run())
    if index < 1:
        raise ValidationError(
            "Audio track index is out of range.",
            details={
                "track_type": "audio",
                "index": index,
                "min": 1,
            },
        )
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            {
                "action": "fairlight.mute",
                "would_mute": True,
                "dry_run": True,
                "track_type": "audio",
                "index": index,
                "requires_existing_track": True,
            },
            title="Fairlight Mute Plan",
        )
        return
    conn = get_connection(require_timeline=True)
    _validate_audio_track_index(conn, index)
    fairlight_ops.mute_audio_track(conn, index)
    success(f"Muted audio track {index}.")


@app.command("unmute")
@handle_errors
def unmute(index: int = typer.Argument(...)):
    """Unmute an audio track."""
    enforce_mutation_policy("fairlight.track_state", intended_engine="api_native", mutating=not is_dry_run())
    if index < 1:
        raise ValidationError(
            "Audio track index is out of range.",
            details={
                "track_type": "audio",
                "index": index,
                "min": 1,
            },
        )
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            {
                "action": "fairlight.unmute",
                "would_unmute": True,
                "dry_run": True,
                "track_type": "audio",
                "index": index,
                "requires_existing_track": True,
            },
            title="Fairlight Unmute Plan",
        )
        return
    conn = get_connection(require_timeline=True)
    _validate_audio_track_index(conn, index)
    fairlight_ops.unmute_audio_track(conn, index)
    success(f"Unmuted audio track {index}.")


@app.command("solo")
@handle_errors
def solo(index: int = typer.Argument(..., help="Audio track index to solo")):
    """Solo an audio track by disabling all other audio tracks."""
    enforce_mutation_policy("fairlight.solo", intended_engine="api_native", mutating=not is_dry_run())
    if index < 1:
        raise ValidationError(
            "Audio track index is out of range.",
            details={"track_type": "audio", "index": index, "min": 1},
        )
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            {
                "action": "fairlight.solo",
                "would_solo": True,
                "dry_run": True,
                "track_type": "audio",
                "index": index,
                "emulation": "enable target track and disable every other audio track",
                "restore": "Use fairlight solo-restore with previous_states from a live solo response.",
            },
            title="Fairlight Solo Plan",
        )
        return
    conn = get_connection(require_timeline=True)
    data = fairlight_ops.solo_audio_track(conn, index)
    output(data, title="Fairlight Solo")


@app.command("fade-curve")
@handle_errors
def fade_curve(
    item_id: str = typer.Option(..., "--item-id", help="Exact audio timeline item ID"),
    direction: str = typer.Option(..., "--direction", help="in or out"),
    x: float | None = typer.Option(None, "--x", help="Native curve control-point X"),
    y: float | None = typer.Option(None, "--y", help="Native curve control-point Y"),
    linear: bool = typer.Option(False, "--linear", help="Reset this fade to a linear envelope"),
):
    """Read or edit an audio fade curve without changing either fade duration."""
    from ..core import audio_fade_curve
    audio_fade_curve._parameter(direction)
    if (x is None) != (y is None) or (linear and x is not None):
        raise ValidationError("Use both --x and --y, or --linear, or neither to read.")
    conn = get_connection(require_project=True, require_timeline=True)
    if not linear and x is None:
        output(audio_fade_curve.read(conn, item_id, direction))
        return
    point = None if linear else {"x": x, "y": y}
    audio_fade_curve.validate_point(point)
    enforce_mutation_policy("fairlight.fade_in_batch" if direction == "in" else "fairlight.fade_out_batch", intended_engine="db_workaround", mutating=not is_dry_run())
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output({"item_id": item_id, "direction": direction, "control_point": point, "dry_run": True}, title="Audio Fade Curve Plan")
        return
    output(audio_fade_curve.set_curve(conn, item_id, direction, point))
