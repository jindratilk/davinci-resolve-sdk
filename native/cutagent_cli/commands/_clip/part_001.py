"""Clip / Timeline Item commands."""

from __future__ import annotations

import math
import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Optional

import typer

from ..capabilities import get_capabilities
from ..connection import get_connection
from ..errors import APICallFailed, CapabilityNegotiationFailed, MissingArgumentError, ValidationError, handle_errors
from ..output import (
    output,
    success,
    is_dry_run,
    dry_run_message,
    is_machine_mode,
    set_capability_context,
    set_execution_engine,
    set_recoverability,
    set_verification_status,
)
from ..policy import enforce_mutation_policy
from ..runtime_health import get_current_database_details, resolve_current_disk_project_db
from ..utils.timecode import parse_time_input, seconds_to_frames
from ..core.fusion_setting_inspector import prepare_setting_for_import
from ..core import native_clip_audio, native_clip_speed, project_ops, resolve_api_version
from ..core import audio_eq_db, audio_normalize, clip_effects_db, clip_ops, clip_speed_db, db_session, db_timeline_rows, db_timeline_selection, keyframe_ops, mutation_target, retime_db, speed_ramp_db, timeline_ops

app = typer.Typer(help="Clip / timeline item operations.")


def _persist_sdk_clip_motion_state(conn) -> None:
    """Synchronously publish native Inspector writes before SDK verification starts."""

    if os.environ.get("CUTAGENT_SDK_TIMELINE_GUARD") is None:
        return
    if not project_ops.save_current_project_if_available(conn):
        raise APICallFailed(
            "DaVinci Resolve could not persist the SDK clip transform before verification.",
            details={"method": "ProjectManager.SaveProject"},
            recoverability="manual",
        )


def _exact_sdk_retime_targets(conn):
    raw = os.environ.get("CUTAGENT_SDK_EXPECTED_RETIME_TARGETS")
    if raw is None:
        return None
    timeline_ops.require_sdk_marker_mutation_guard(conn)
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValidationError("The exact SDK retime target precondition is invalid JSON.") from exc
    return db_timeline_selection.require_exact_sdk_retime_targets(conn, value)


def _validate_exact_sdk_retime_targets_at_pre_close(locked_conn, _session):
    _exact_sdk_retime_targets(locked_conn)


def _require_sdk_retime_selection_matches(selection, exact_targets):
    if exact_targets is None:
        return
    selected = set()
    for value in selection.values():
        items = value if isinstance(value, (list, tuple)) else (value,)
        selected.update(
            str(item.item_id)
            for item in items
            if isinstance(item, db_timeline_selection.LiveItemRef)
        )
    expected = {str(item.item_id) for item in exact_targets}
    if selected != expected:
        from ..errors import SdkMutationStaleRevision

        raise SdkMutationStaleRevision(
            "The SDK retime selector did not resolve the complete exact target set.",
            details={"selected_count": len(selected), "expected_count": len(expected)},
        )


def _layout_payload(prepared: dict | None) -> dict | None:
    if not prepared:
        return None
    return {key: value for key, value in prepared.items() if key != "cleanup_path"}


def _unsupported_clip_preview(capability_id: str, route: str, payload: dict, title: str) -> None:
    feature = get_capabilities().get("feature_graph", {}).get(capability_id, {})
    caveats = feature.get("caveats") if isinstance(feature.get("caveats"), dict) else {}
    status = str(feature.get("status") or "unsupported")
    diagnostic = {
        "route": route,
        "available": False,
        "would_mutate": False,
        "capability_id": capability_id,
        "capability_status": status,
        **payload,
        "verification": {
            "status": "not_available",
            "source": "capability_graph",
        },
        "caveats": caveats,
    }

    set_execution_engine("not_available", 0.0)
    set_capability_context(capability_id, status)
    enforce_mutation_policy(capability_id, intended_engine="not_available", mutating=False)
    set_verification_status("not_available")
    set_recoverability("manual")
    if is_dry_run():
        output(diagnostic, title=title)
        return

    raise CapabilityNegotiationFailed(
        "Clip command is not production-verified.",
        details=diagnostic,
    )


def _cleanup_prepared_setting(prepared: dict | None) -> dict | None:
    if not prepared:
        return None
    cleanup = dict(prepared.get("cleanup") or {})
    cleanup_path = prepared.get("cleanup_path")
    deleted = False
    if cleanup_path:
        try:
            if os.path.exists(str(cleanup_path)):
                os.unlink(str(cleanup_path))
                deleted = True
        except Exception:
            deleted = False
    cleanup["temporary_setting_deleted"] = deleted
    prepared["cleanup"] = cleanup
    return _layout_payload(prepared)


def _parse_optional_duration_frames(conn, value: Optional[str]) -> Optional[int]:
    if value is None:
        return None
    try:
        frames = seconds_to_frames(parse_time_input(str(value), conn.fps), conn.fps)
    except Exception as exc:
        details = getattr(exc, "details", {"duration": value, "fps": conn.fps})
        raise ValidationError(
            f"Cannot parse fade duration: {value}",
            details=details,
            recoverability="not_applicable",
        ) from exc
    if frames <= 0:
        raise ValidationError(
            "Duration must be greater than 0.",
            details={"duration": value},
            recoverability="not_applicable",
        )
    return int(frames)


def _timeline_name(conn) -> Optional[str]:
    timeline = getattr(conn, "timeline", None)
    return timeline.GetName() if timeline and hasattr(timeline, "GetName") else None


def _count_option_occurrences(option_name: str, argv: list[str] | None = None) -> int:
    tokens = sys.argv[1:] if argv is None else argv
    prefix = f"{option_name}="
    return sum(1 for token in tokens if token == option_name or token.startswith(prefix))


def _reject_duplicate_audio_gain_db(argv: list[str] | None = None) -> None:
    count = _count_option_occurrences("--db", argv=argv)
    if count > 1:
        raise ValidationError(
            "Duplicate --db options are not allowed for clip audio-gain.",
            details={"option": "--db", "count": count},
            recoverability="not_applicable",
        )


def _reject_duplicate_audio_normalize_target(argv: list[str] | None = None) -> None:
    count = _count_option_occurrences("--target-dbfs", argv=argv)
    if count > 1:
        raise ValidationError(
            "Duplicate --target-dbfs options are not allowed for clip audio-normalize.",
            details={"option": "--target-dbfs", "count": count},
            recoverability="not_applicable",
        )


def _reject_duplicate_audio_pan_value(argv: list[str] | None = None) -> None:
    count = _count_option_occurrences("--value", argv=argv)
    if count > 1:
        raise ValidationError(
            "Duplicate --value options are not allowed for clip audio-pan.",
            details={"option": "--value", "count": count},
            recoverability="not_applicable",
        )


def _reject_duplicate_audio_pitch_options(argv: list[str] | None = None) -> None:
    for option_name in ("--semitones", "--cents"):
        count = _count_option_occurrences(option_name, argv=argv)
        if count > 1:
            raise ValidationError(
                f"Duplicate {option_name} options are not allowed for clip audio-pitch.",
                details={"option": option_name, "count": count},
                recoverability="not_applicable",
            )


def _reject_conflicting_clip_cache_toggle(argv: list[str] | None = None) -> None:
    tokens = sys.argv[1:] if argv is None else argv
    has_enable = "--enable" in tokens
    has_disable = "--disable" in tokens
    if has_enable and has_disable:
        raise ValidationError(
            "Use only one of --enable or --disable for clip cache.",
            details={"options": ["--enable", "--disable"]},
            recoverability="not_applicable",
        )


def _reject_conflicting_clip_color_options(set_color: str | None, clear: bool) -> None:
    if set_color is not None and clear:
        raise ValidationError(
            "Use only one of --set or --clear for clip color.",
            details={"options": ["--set", "--clear"]},
            recoverability="not_applicable",
        )


def _load_clip_transform_batch_entries(path: str) -> list[dict[str, object]]:
    input_path = Path(path).expanduser()
    try:
        raw = json.loads(input_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValidationError(
            "Clip transform batch input file was not found.",
            details={"path": str(input_path)},
            recoverability="not_applicable",
        ) from exc
    except json.JSONDecodeError as exc:
        raise ValidationError(
            "Clip transform batch input file is not valid JSON.",
            details={"path": str(input_path), "line": exc.lineno, "column": exc.colno},
            recoverability="not_applicable",
        ) from exc

    if isinstance(raw, dict):
        for key in ("items", "entries", "transforms", "updates"):
            if isinstance(raw.get(key), list):
                raw = raw[key]
                break
    if not isinstance(raw, list):
        raise ValidationError(
            "Clip transform batch input must be a JSON array or an object with an items/entries/transforms/updates array.",
            details={"path": str(input_path)},
            recoverability="not_applicable",
        )
    entries: list[dict[str, object]] = []
    for index, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise ValidationError(
                "Clip transform batch entries must be JSON objects.",
                details={"path": str(input_path), "index": index},
                recoverability="not_applicable",
            )
        entries.append(entry)
    return entries


def _reject_conflicting_clip_flag_options(add: str | None, clear: bool) -> None:
    if add is not None and clear:
        raise ValidationError(
            "Use only one of --add or --clear for clip flag.",
            details={"options": ["--add", "--clear"]},
            recoverability="not_applicable",
        )


def _validate_clip_properties_options(
    key: str | None,
    set_key: str | None,
    set_value: str | None,
) -> None:
    wants_get = key is not None
    wants_set = set_key is not None or set_value is not None
    if wants_get and wants_set:
        raise ValidationError(
            "Use --get by itself, or use --set with --value.",
            details={"options": ["--get", "--set", "--value"]},
            recoverability="not_applicable",
        )
    if set_key is None and set_value is not None:
        raise ValidationError(
            "--value requires --set.",
            details={"missing": "--set", "provided": "--value"},
            recoverability="not_applicable",
        )
    if set_key is not None and set_value is None:
        raise ValidationError(
            "--set requires --value.",
            details={"missing": "--value", "provided": "--set"},
            recoverability="not_applicable",
        )
    if set_key is not None and not set_key.strip():
        raise ValidationError(
            "--set property key must not be empty.",
            details={"option": "--set"},
            recoverability="not_applicable",
        )


def _option_value(value, default=None):
    return default if isinstance(value, typer.models.OptionInfo) else value


def _validate_clip_speed_options(
    *,
    set_speed: float | None,
    speed_percent: float | None,
    frames_per_second: float | None,
    duration: str | None,
    ripple_timeline: bool,
    at: str | None,
    reverse_speed: bool,
    freeze_frame: bool,
    pitch_correction: bool | None,
    keyframes: str,
) -> dict[str, object]:
    options = clip_speed_db.validate_speed_controls(
        multiplier=set_speed,
        speed_percent=speed_percent,
        frames_per_second=frames_per_second,
        duration=duration,
        reverse_speed=reverse_speed,
        freeze_frame=freeze_frame,
        pitch_correction=pitch_correction,
        keyframes=keyframes,
    )
    if ripple_timeline and not options["retime_requested"]:
        raise ValidationError(
            "--ripple-timeline can only be used with a clip speed mutation.",
            details={"option": "--ripple-timeline", "requires": "clip speed mutation"},
            recoverability="not_applicable",
        )
    if not options["retime_requested"] and at is not None:
        raise ValidationError(
            "--at can only be used with --set or another clip speed mutation.",
            details={"option": "--at", "requires": "clip speed mutation"},
            recoverability="not_applicable",
        )
    return options


def _reject_dynamic_zoom_trailing_name(name: str | None, argv: list[str] | None = None) -> None:
    if name is None:
        return
    tokens = sys.argv[1:] if argv is None else argv
    try:
        command_index = tokens.index("dynamic-zoom")
    except ValueError:
        return
    after_command = tokens[command_index + 1 :]
    first_option_index = next((index for index, token in enumerate(after_command) if token.startswith("-")), None)
    if first_option_index == 0:
        raise ValidationError(
            "Clip name for clip dynamic-zoom must appear before options.",
            details={"name": name},
            recoverability="not_applicable",
        )


@app.command("list")
@handle_errors
def list_clips(
    track_type: str = typer.Option("video", help="Track type: video, audio, subtitle"),
    index: int = typer.Option(1, "--track", min=1, help="Track index"),
):
    """List clips on a track."""
    enforce_mutation_policy("clip.list_read", intended_engine="api_native", mutating=False)
    track_type = clip_ops.normalize_clip_list_track_type(track_type)
    index = clip_ops.validate_clip_list_track_index(index)
    conn = get_connection(require_timeline=True)
    track_type, index = clip_ops.validate_clip_list_request(conn, track_type, index)
    rows = clip_ops.list_clips(conn, track_type, index)
    output(rows, columns=[("name", "Name"), ("start", "Start"), ("end", "End"), ("duration", "Duration")],
           title=f"{track_type.title()} Track {index}", quiet_key="name")


@app.command("current")
@handle_errors
def current_clip():
    """Show the clip under the playhead."""
    conn = get_connection(require_timeline=True)
    item = clip_ops.get_current_item(conn)
    if not item:
        from ..output import warning
        warning("No clip under playhead.")
        return

    data = clip_ops.get_clip_info(conn, None)
    output(data, title="Current Clip")


@app.command("info")
@handle_errors
def clip_info(
    name: Optional[str] = typer.Argument(None, help="Clip name (or current if omitted)"),
):
    """Show detailed clip info."""
    conn = get_connection(require_timeline=True)
    data = clip_ops.get_clip_info(conn, name)
    output(data, title=f"Clip: {data.get('name', '?')}")


@app.command("properties")
@handle_errors
def clip_properties(
    name: Optional[str] = typer.Argument(None, help="Clip name"),
    key: Optional[str] = typer.Option(None, "--get", help="Get specific property"),
    set_key: Optional[str] = typer.Option(None, "--set", help="Set property key"),
    set_value: Optional[str] = typer.Option(None, "--value", help="Set property value"),
):
    """Get or set clip properties."""
    enforce_mutation_policy("clip.properties_write", intended_engine="api_native", mutating=False)
    _validate_clip_properties_options(key, set_key, set_value)

    if set_key is not None:
        enforce_mutation_policy("clip.properties_write", intended_engine="api_native", mutating=not is_dry_run())
        if is_dry_run():
            set_verification_status("not_requested")
            set_recoverability("not_applicable")
            dry_run_message(f"Would set clip property {set_key} = {set_value} on '{name or 'current'}'")
            return
        conn = get_connection(require_timeline=True)
        clip_ops.set_clip_property(conn, name, set_key, set_value)
        success(f"Set {set_key} = {set_value}")
    elif key is not None:
        conn = get_connection(require_timeline=True)
        val = clip_ops.get_clip_property(conn, name, key)
        output({key: val})
    else:
        conn = get_connection(require_timeline=True)
        props = clip_ops.get_clip_property(conn, name)
        output(props, title="Clip Properties")


# --- Color ---

@app.command("color")
@handle_errors
def clip_color(
    name: Optional[str] = typer.Argument(None, help="Clip name"),
    set: Optional[str] = typer.Option(None, "--set", help="Set color (Orange, Teal, Blue, Green, Pink, etc.)"),
    clear: bool = typer.Option(False, "--clear", help="Clear color"),
):
    """Get or set clip color."""
    _reject_conflicting_clip_color_options(set, clear)
    normalized_color = clip_ops.normalize_clip_color(set) if set is not None else None
    is_mutation = clear or normalized_color is not None

    if is_dry_run() and is_mutation:
        enforce_mutation_policy("clip.color_flag", intended_engine="api_native", mutating=False)
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        if clear:
            dry_run_message(f"Would clear clip color on '{name or 'current'}'")
        else:
            dry_run_message(f"Would set clip color on '{name or 'current'}' to {normalized_color}")
        return

    if clear:
        conn = get_connection(require_timeline=True)
        clip_ops.get_clip_color(conn, name)
        enforce_mutation_policy("clip.color_flag", intended_engine="api_native")
        clip_ops.clear_clip_color(conn, name)
        success("Cleared clip color.")
    elif normalized_color is not None:
        conn = get_connection(require_timeline=True)
        clip_ops.get_clip_color(conn, name)
        enforce_mutation_policy("clip.color_flag", intended_engine="api_native")
        clip_ops.set_clip_color(conn, name, normalized_color)
        success(f"Set clip color: {normalized_color}")
    else:
        enforce_mutation_policy("clip.color_flag", intended_engine="api_native", mutating=False)
        conn = get_connection(require_timeline=True)
        color = clip_ops.get_clip_color(conn, name)
        output({"color": color})


# --- Flags ---

@app.command("flag")
@handle_errors
def clip_flag(
    name: Optional[str] = typer.Argument(None, help="Clip name"),
    add: Optional[str] = typer.Option(None, "--add", help="Add flag color"),
    clear: bool = typer.Option(False, "--clear", help="Clear all flags"),
):
    """Manage clip flags."""
    _reject_conflicting_clip_flag_options(add, clear)
    normalized_flag_color = clip_ops.normalize_clip_flag_color(add) if add is not None else None
    is_mutation = clear or normalized_flag_color is not None

    if is_dry_run() and is_mutation:
        enforce_mutation_policy("clip.flag", intended_engine="api_native", mutating=False)
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        if clear:
            dry_run_message(f"Would clear all flags on '{name or 'current'}'")
        else:
            dry_run_message(f"Would add {normalized_flag_color} flag to '{name or 'current'}'")
        return

    if clear:
        enforce_mutation_policy("clip.flag", intended_engine="api_native")
        conn = get_connection(require_timeline=True)
        clip_ops.clear_clip_flags(conn, name)
        success("Cleared all flags.")
    elif normalized_flag_color is not None:
        enforce_mutation_policy("clip.flag", intended_engine="api_native")
        conn = get_connection(require_timeline=True)
        clip_ops.add_clip_flag(conn, name, normalized_flag_color)
        success(f"Added {normalized_flag_color} flag.")
    else:
        enforce_mutation_policy("clip.flag", intended_engine="api_native", mutating=False)
        conn = get_connection(require_timeline=True)
        flags = clip_ops.get_clip_flags(conn, name)
        output({"flags": flags if flags else []})


# --- Transform ---

@app.command("transform")
@handle_errors
def clip_transform(
    name: Optional[str] = typer.Argument(None, help="Clip name"),
    batch_file: Optional[str] = typer.Option(None, "--batch-file", help="JSON array/object of clip transform entries to apply in one DaVinci Resolve session"),
    zoom_x: Optional[float] = typer.Option(None, "--zoom-x"),
    zoom_y: Optional[float] = typer.Option(None, "--zoom-y"),
    zoom: Optional[float] = typer.Option(None, "--zoom", help="Set both zoom X and Y"),
    position_x: Optional[float] = typer.Option(None, "--position-x", "--pan"),
    position_y: Optional[float] = typer.Option(None, "--position-y", "--tilt"),
    rotation: Optional[float] = typer.Option(None, "--rotation"),
    anchor_x: Optional[float] = typer.Option(None, "--anchor-x"),
    anchor_y: Optional[float] = typer.Option(None, "--anchor-y"),
    pitch: Optional[float] = typer.Option(None, "--pitch"),
    yaw: Optional[float] = typer.Option(None, "--yaw"),
    flip_x: Optional[bool] = typer.Option(None, "--flip-x/--no-flip-x"),
    flip_y: Optional[bool] = typer.Option(None, "--flip-y/--no-flip-y"),
    opacity: Optional[float] = typer.Option(None, "--opacity", help="0.0 to 100.0"),
    crop_left: Optional[float] = typer.Option(None, "--crop-left"),
    crop_right: Optional[float] = typer.Option(None, "--crop-right"),
    crop_top: Optional[float] = typer.Option(None, "--crop-top"),
    crop_bottom: Optional[float] = typer.Option(None, "--crop-bottom"),
    distortion: Optional[float] = typer.Option(None, "--distortion"),
    dynamic_zoom_ease: Optional[str] = typer.Option(None, "--dynamic-zoom-ease", help="linear|in|out|inout"),
    reset: bool = typer.Option(False, "--reset", help="Reset all transforms"),
):
    """Get or set clip transform properties."""
    setting_any = any(v is not None for v in [
        zoom_x, zoom_y, zoom, position_x, position_y,
        rotation, anchor_x, anchor_y, pitch, yaw, flip_x, flip_y,
        opacity, crop_left, crop_right, crop_top, crop_bottom, distortion, dynamic_zoom_ease,
    ]) or reset

    if batch_file:
        if name or setting_any:
            raise ValidationError(
                "Use --batch-file by itself for clip transform batches.",
                details={"clip": name, "has_single_transform_options": bool(setting_any)},
                recoverability="not_applicable",
            )
        enforce_mutation_policy("clip.transform", intended_engine="api_native", mutating=not is_dry_run())
        entries = _load_clip_transform_batch_entries(batch_file)
        if is_dry_run():
            set_verification_status("not_requested")
            set_recoverability("not_applicable")
            output(
                {
                    "action": "clip.transform.batch",
                    "changed": False,
                    "requested_count": len(entries),
                    "entries": entries,
                    "message": "DRY-RUN: Would apply clip transforms in one DaVinci Resolve session.",
                },
                title="Clip Transform Batch Plan",
            )
            return
        conn = get_connection(require_timeline=True)
        data = clip_ops.set_clip_transform_batch(conn, entries)
        _persist_sdk_clip_motion_state(conn)
        set_verification_status("partial")
        set_recoverability("not_applicable")
        output(data, title="Clip Transform Batch")
        return

    conn = get_connection(require_timeline=True)

    if not setting_any and os.environ.get("CUTAGENT_SDK_CLIP_MOTION_STATE") == "1":
        from ..core.keyframe_service import GetKeyframes, execute_keyframe
        from ..core.sdk_clip_motion import SDK_CLIP_MOTION_TARGET_ENV, expected_state_targets

        state_targets = expected_state_targets()
        if state_targets is not None:
            if name:
                raise ValidationError("SDK plural clip motion state reads do not accept a positional clip selector.")
            previous_target = os.environ.get(SDK_CLIP_MOTION_TARGET_ENV)
            states = []
            try:
                for target in state_targets:
                    os.environ[SDK_CLIP_MOTION_TARGET_ENV] = json.dumps(target)
                    transform_data = clip_ops.get_clip_transform(conn, target["name"])
                    keyframe_data = execute_keyframe(conn, GetKeyframes(target["name"]))
                    states.append({
                        "transform": transform_data,
                        "keyframes": keyframe_data.get("keyframes", {}),
                    })
            finally:
                if previous_target is None:
                    os.environ.pop(SDK_CLIP_MOTION_TARGET_ENV, None)
                else:
                    os.environ[SDK_CLIP_MOTION_TARGET_ENV] = previous_target
            output({"states": states}, title="Transform States")
            return

    if reset:
        enforce_mutation_policy("clip.transform", intended_engine="api_native")
        clip_ops.reset_clip_transform(conn, name)
        success("Reset all transforms.")
    elif setting_any:
        enforce_mutation_policy("clip.transform", intended_engine="api_native")
        clip_ops.set_clip_transform(
            conn, name, zoom_x, zoom_y, zoom, position_x, position_y,
            rotation, anchor_x, anchor_y, pitch, yaw, flip_x, flip_y,
            opacity, crop_left, crop_right, crop_top, crop_bottom, distortion, dynamic_zoom_ease,
        )
        _persist_sdk_clip_motion_state(conn)
        success("Set transform properties.")
    else:
        data = clip_ops.get_clip_transform(conn, name)
        if os.environ.get("CUTAGENT_SDK_CLIP_MOTION_STATE") == "1":
            from ..core.keyframe_service import GetKeyframes, execute_keyframe

            keyframe_data = execute_keyframe(conn, GetKeyframes(name))
            data = {
                "transform": data,
                "keyframes": keyframe_data.get("keyframes", {}),
            }
        output(data, title="Transform")


@app.command("cache")
@handle_errors
def clip_cache(
    name: Optional[str] = typer.Argument(None, help="Clip name (or current if omitted)"),
    cache_type: str = typer.Option("color", "--type", help="Cache type: color or fusion"),
    enable: Optional[bool] = typer.Option(None, "--enable/--disable", help="Enable or disable output cache"),
):
    """Get or set clip output cache state."""
    normalized_type = clip_ops.normalize_cache_type(cache_type)
    _reject_conflicting_clip_cache_toggle()
    enforce_mutation_policy("clip.cache_control", intended_engine="api_native", mutating=enable is not None and not is_dry_run())
    if is_dry_run() and enable is not None:
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        dry_run_message(
            f"Would {'enable' if enable else 'disable'} {normalized_type} output cache on '{name or 'current'}'"
        )
        return

    conn = get_connection(require_timeline=True)
    if enable is None:
        data = clip_ops.get_clip_cache_state(conn, name, cache_type=normalized_type)
        output(data, title="Clip Cache")
        return

    data = clip_ops.set_clip_cache_state(conn, name, cache_type=normalized_type, enabled=enable)
    set_verification_status("verified")
    set_recoverability("not_applicable")
    output(data, title="Clip Cache")


@app.command("source-range")
@handle_errors
def source_range(
    clip: Optional[str] = typer.Argument(None, help="Clip name (current clip when omitted)"),
):
    """Show source-domain range information for a timeline item."""
    conn = get_connection(require_timeline=True)
    output(clip_ops.get_source_range(conn, clip), title="Source Range")


linked_app = typer.Typer(help="Linked timeline item operations.")
app.add_typer(linked_app, name="linked")


@linked_app.command("list")
@handle_errors
def linked_list(
    clip: Optional[str] = typer.Argument(None, help="Clip name (current clip when omitted)"),
):
    """List items linked to a timeline item."""
    conn = get_connection(require_timeline=True)
    output(clip_ops.list_linked_items(conn, clip), title="Linked Items")


@app.command("track-info")
@handle_errors
def track_info(
    clip: Optional[str] = typer.Argument(None, help="Clip name (current clip when omitted)"),
):
    """Show the track type/index for a timeline item."""
    conn = get_connection(require_timeline=True)
    output(clip_ops.get_track_info(conn, clip), title="Track Info")


@app.command("source-audio-mapping")
@handle_errors
def source_audio_mapping(
    clip: Optional[str] = typer.Argument(None, help="Clip name (current clip when omitted)"),
):
    """Show source audio channel mapping for a timeline item."""
    conn = get_connection(require_timeline=True)
    output(clip_ops.get_source_audio_mapping(conn, clip), title="Source Audio Mapping")


@app.command("cache-state")
@handle_errors
def cache_state(
    clip: Optional[str] = typer.Argument(None, help="Clip name (current clip when omitted)"),
    cache_type: str = typer.Option("color", "--type", help="Cache type: color or fusion"),
):
    """Show color/fusion cache state using newer DaVinci Resolve APIs where available."""
    conn = get_connection(require_timeline=True)
    output(clip_ops.get_clip_cache_state(conn, clip, cache_type=cache_type), title="Clip Cache")


@app.command("cache-set")
@handle_errors
def cache_set(
    clip: Optional[str] = typer.Argument(None, help="Clip name (current clip when omitted)"),
    cache_type: str = typer.Option("color", "--type", help="Cache type: color or fusion"),
    mode: str = typer.Option(..., "--mode", help="enable|disable|auto"),
):
    """Set color/fusion cache state using newer DaVinci Resolve APIs where available."""
    normalized_type = clip_ops.normalize_cache_type(cache_type)
    normalized_mode = clip_ops.normalize_cache_mode(normalized_type, mode)
    enforce_mutation_policy("clip.cache_control", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        dry_run_message(f"Would set {normalized_type} cache mode to {normalized_mode} on '{clip or 'current'}'.")
        return
    conn = get_connection(require_timeline=True)
    data = clip_ops.set_clip_cache_state(conn, clip, cache_type=normalized_type, mode=normalized_mode)
    set_verification_status("verified")
    set_recoverability("not_applicable")
    output(data, title="Clip Cache")


# --- Composite ---

@app.command("composite")
@handle_errors
def clip_composite(
    name: Optional[str] = typer.Argument(None, help="Clip name"),
    mode: Optional[str] = typer.Option(None, "--mode", help="Composite mode"),
    opacity_val: Optional[float] = typer.Option(None, "--opacity", help="Opacity 0-100"),
):
    """Get or set composite mode and opacity."""
    normalized_mode = clip_ops.normalize_composite_mode(mode) if mode is not None else None
    normalized_opacity = clip_ops.validate_clip_opacity(opacity_val) if opacity_val is not None else None
    is_mutation = normalized_mode is not None or normalized_opacity is not None

    if is_dry_run() and is_mutation:
        enforce_mutation_policy("clip.composite", intended_engine="api_native", mutating=False)
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        changes = []
        if normalized_mode is not None:
            changes.append(f"composite mode to {normalized_mode}")
        if normalized_opacity is not None:
            changes.append(f"opacity to {normalized_opacity}")
        dry_run_message(f"Would set {' and '.join(changes)} on '{name or 'current'}'")
        return

    conn = get_connection(require_timeline=True)
    if is_mutation:
        clip_ops.get_clip_composite(conn, name)
        enforce_mutation_policy("clip.composite", intended_engine="api_native")
        clip_ops.set_clip_composite(conn, name, normalized_mode, normalized_opacity)
        changes = []
        if normalized_mode is not None:
            changes.append(f"composite mode: {normalized_mode}")
        if normalized_opacity is not None:
            changes.append(f"opacity: {normalized_opacity}")
        success(f"Set {'; '.join(changes)}")
        return

    enforce_mutation_policy("clip.composite", intended_engine="api_native", mutating=False)
    data = clip_ops.get_clip_composite(conn, name)
    output(data)


# --- Speed ---

@app.command("speed")
@handle_errors
def clip_speed(
    name: Optional[str] = typer.Argument(None, help="Clip name"),
    set_speed: Optional[float] = typer.Option(None, "--set", "--multiplier", help="Speed multiplier (e.g., 2.0 for 2x)"),
    speed_percent: Optional[float] = typer.Option(None, "--speed-percent", "--percent", help="GUI Speed value in percent (e.g., 200 for 2x)"),
    frames_per_second: Optional[float] = typer.Option(None, "--fps", "--frames-per-second", help="GUI Frames per Second value"),
    duration: Optional[str] = typer.Option(None, "--duration", help="GUI Duration value, e.g. 00:01:23:00 or 120f"),
    ripple_timeline: bool = typer.Option(False, "--ripple-timeline/--no-ripple-timeline", help="Ripple downstream timeline items after the speed change"),
    reverse_speed: bool = typer.Option(False, "--reverse-speed", help="Apply the GUI Reverse Speed option"),
    freeze_frame: bool = typer.Option(False, "--freeze-frame", help="Apply the GUI Freeze Frame option"),
    pitch_correction: Optional[bool] = typer.Option(None, "--pitch-correction/--no-pitch-correction", help="Set the GUI Pitch Correction option when the Disk DB stores clip speed state"),
    keyframes: str = typer.Option("maintain-timing", "--keyframes", help="GUI keyframe timing mode: maintain-timing or stretch-to-fit"),
    at: Optional[str] = typer.Option(None, "--at", help="Record-domain position for deterministic clip selection"),
):
    """Get or set clip speed."""
    set_speed_value = _option_value(set_speed)
    speed_percent_value = _option_value(speed_percent)
    frames_per_second_value = _option_value(frames_per_second)
    duration_value = _option_value(duration)
    ripple_timeline_value = bool(_option_value(ripple_timeline, False))
    reverse_speed_value = bool(_option_value(reverse_speed, False))
    freeze_frame_value = bool(_option_value(freeze_frame, False))
    pitch_correction_value = _option_value(pitch_correction)
    keyframes_value = str(_option_value(keyframes, "maintain-timing"))
    at_value = _option_value(at)
    options = _validate_clip_speed_options(
        set_speed=set_speed_value,
        speed_percent=speed_percent_value,
        frames_per_second=frames_per_second_value,
        duration=duration_value,
        ripple_timeline=ripple_timeline_value,
        at=at_value,
        reverse_speed=reverse_speed_value,
        freeze_frame=freeze_frame_value,
        pitch_correction=pitch_correction_value,
        keyframes=keyframes_value,
    )
    if options["retime_requested"] or at_value is not None:
        enforce_mutation_policy(
            "clip.speed",
            intended_engine="db_workaround" if options["retime_requested"] else "api_native",
            mutating=False,
        )
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
    conn = get_connection(require_timeline=True)
    exact_sdk_targets = _exact_sdk_retime_targets(conn)

    if options["retime_requested"]:
        current_database = get_current_database_details(conn)
        if str(current_database.get("DbType") or "").strip() == "Disk":
            enforce_mutation_policy("clip.speed", intended_engine="db_workaround", mutating=not is_dry_run())
            if is_dry_run():
                set_verification_status("not_requested")
                set_recoverability("not_applicable")
            timeline_name = _timeline_name(conn)
            timeline_fps = clip_speed_db.resolve_timeline_fps(conn)
            if duration_value is not None:
                clip_speed_db.validate_duration_frames(str(duration_value), timeline_fps)
            sdk_track_index = db_timeline_selection.sdk_guard_track_index("video")
            selection = db_timeline_selection.resolve_linked_av_group(
                conn, clip_name=name, at=at_value,
                **({"track": sdk_track_index} if sdk_track_index is not None else {}),
            )
            _require_sdk_retime_selection_matches(selection, exact_sdk_targets)
            if is_dry_run():
                target = selection["video"].name if selection.get("video") else (name or "current")
                requested = options.get("multiplier")
                if requested is not None:
                    requested = f"{requested}x"
                elif options.get("speed_percent") is not None:
                    requested = f"{options['speed_percent']}%"
                elif options.get("frames_per_second") is not None:
                    requested = f"{options['frames_per_second']} fps"
                elif options.get("duration") is not None:
                    requested = f"duration {options['duration']}"
                elif options.get("freeze_frame"):
                    requested = "freeze frame"
                elif options.get("reverse_speed"):
                    requested = "reverse speed"
                else:
                    requested = "requested speed"
                dry_run_message(
                    f"Would set clip speed on '{target}' to {requested} at '{at_value or 'current item'}' via Disk DB"
                )
                return

            db_options = dict(options)
            db_options["ripple_timeline"] = ripple_timeline_value

            def _writer(connection, cursor, session):
                return clip_speed_db.apply_clip_speed(
                    cursor,
                    conn=conn,
                    selection=selection,
                    timeline_name=timeline_name,
                    options=db_options,
                    fps=timeline_fps,
                )

            data = db_session.execute_sqlite_disk_db_mutation(
                conn,
                context="DB-backed clip speed",
                writer=_writer,
                verifier=lambda fresh, result, session: clip_speed_db.verify_clip_speed_mutation(
                    fresh, result, session
                ),
                pre_close_validator=(_validate_exact_sdk_retime_targets_at_pre_close if exact_sdk_targets is not None else None),
                allow_project_name_inference=True,
            )
            output(data, title="Clip Speed")
            return

        if any(
            (
                speed_percent_value is not None,
                frames_per_second_value is not None,
                duration_value is not None,
                ripple_timeline_value,
                reverse_speed_value,
                freeze_frame_value,
                pitch_correction_value is not None,
                options["keyframes"] != "maintain-timing",
            )
        ):
            raise ValidationError(
                "GUI-style clip speed controls require a DaVinci Resolve Disk project database.",
                details={"current_database": current_database},
                recoverability="manual",
            )

        enforce_mutation_policy("clip.speed", intended_engine="api_native", mutating=not is_dry_run())
        if is_dry_run():
            set_verification_status("not_requested")
            set_recoverability("not_applicable")
            clip_ops.get_clip_speed(conn, name)
            dry_run_message(f"Would set clip speed on '{name or 'current'}' to {set_speed_value}x")
            return
        clip_ops.set_clip_speed(conn, name, float(set_speed_value))
        success(f"Set speed: {set_speed_value}x")
    else:
        if resolve_api_version.at_least(conn, 21, 1):
            state = native_clip_speed.read(clip_ops.cutagent_clip(conn, name))
            set_execution_engine("api_native")
            set_verification_status("verified")
            output({"speed": state["Percentage"], "multiplier": state["Percentage"] / 100, "native_options": state}, title="Clip Speed")
            return
        current_database = get_current_database_details(conn)
        if str(current_database.get("DbType") or "").strip() == "Disk":
            enforce_mutation_policy("clip.speed", intended_engine="db_workaround", mutating=False)
            data = clip_speed_db.inspect_clip_speed(conn, clip_name=name, at=at_value)
        else:
            data = clip_ops.get_clip_speed(conn, name)
        output(data)


@app.command("freeze")
@handle_errors
def clip_freeze(
    name: Optional[str] = typer.Argument(None, help="Clip name"),
    at: Optional[str] = typer.Option(None, "--at", help="Record-domain position for deterministic clip selection"),
):
    """Freeze linked video/audio items through the Disk DB route."""
    enforce_mutation_policy("clip.freeze", intended_engine="db_workaround", mutating=not is_dry_run())
    at_value = None if isinstance(at, typer.models.OptionInfo) else at
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
    conn = get_connection(require_timeline=True)
    exact_sdk_targets = _exact_sdk_retime_targets(conn)
    selection = db_timeline_selection.resolve_linked_av_group(conn, clip_name=name, at=at_value)
    _require_sdk_retime_selection_matches(selection, exact_sdk_targets)
    if is_dry_run():
        target = selection["video"].name if selection.get("video") else (name or "current")
        dry_run_message(f"Would freeze '{target}' at '{at_value or 'current item'}' via Disk DB")
        return

    timeline_name = _timeline_name(conn)
    options = clip_speed_db.validate_speed_controls(freeze_frame=True)
    timeline_fps = clip_speed_db.resolve_timeline_fps(conn)
    db_options = {**options, "ripple_timeline": False}
    data = db_session.execute_sqlite_disk_db_mutation(
        conn,
        context="DB-backed clip freeze",
        writer=lambda connection, cursor, session: clip_speed_db.apply_clip_speed(
            cursor, conn=conn, selection=selection, timeline_name=timeline_name, options=db_options, fps=timeline_fps,
        ),
        verifier=lambda fresh, result, session: clip_speed_db.verify_clip_speed_mutation(
            fresh, result, session
        ),
        pre_close_validator=(_validate_exact_sdk_retime_targets_at_pre_close if exact_sdk_targets is not None else None),
        allow_project_name_inference=True,
    )
    output(data, title="Clip Freeze")


@app.command("reverse")
@handle_errors
def clip_reverse(
    name: Optional[str] = typer.Argument(None, help="Clip name"),
    at: Optional[str] = typer.Option(None, "--at", help="Record-domain position for deterministic clip selection"),
):
    """Reverse linked video/audio items through the Disk DB route."""
    enforce_mutation_policy("clip.reverse", intended_engine="db_workaround", mutating=not is_dry_run())
    at_value = None if isinstance(at, typer.models.OptionInfo) else at
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
    conn = get_connection(require_timeline=True)
    exact_sdk_targets = _exact_sdk_retime_targets(conn)
    selection = db_timeline_selection.resolve_linked_av_group(conn, clip_name=name, at=at_value)
    _require_sdk_retime_selection_matches(selection, exact_sdk_targets)
    if is_dry_run():
        target = selection["video"].name if selection.get("video") else (name or "current")
        dry_run_message(f"Would reverse '{target}' at '{at_value or 'current item'}' via Disk DB")
        return

    timeline_name = _timeline_name(conn)
    options = clip_speed_db.validate_speed_controls(reverse_speed=True)
    timeline_fps = clip_speed_db.resolve_timeline_fps(conn)
    db_options = {**options, "ripple_timeline": False}
    data = db_session.execute_sqlite_disk_db_mutation(
        conn,
        context="DB-backed clip reverse",
        writer=lambda connection, cursor, session: clip_speed_db.apply_clip_speed(
            cursor, conn=conn, selection=selection, timeline_name=timeline_name, options=db_options, fps=timeline_fps,
        ),
        verifier=lambda fresh, result, session: clip_speed_db.verify_clip_speed_mutation(
            fresh, result, session
        ),
        pre_close_validator=(_validate_exact_sdk_retime_targets_at_pre_close if exact_sdk_targets is not None else None),
        allow_project_name_inference=True,
    )
    output(data, title="Clip Reverse")


@app.command("audio-gain")
@handle_errors
def clip_audio_gain(
    name: Optional[str] = typer.Argument(None, help="Clip name"),
    db: float = typer.Option(..., "--db", help="Clip gain in dB"),
    at: Optional[str] = typer.Option(None, "--at", help="Record-domain position for deterministic clip selection"),
):
    """Set clip audio gain natively on 21.1; retain the Disk DB route for older runtimes and gain above +30 dB."""
    enforce_mutation_policy("clip.audio_gain", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
    _reject_duplicate_audio_gain_db()
    validated_db = clip_effects_db.validate_audio_gain_db(db)
    at_value = None if isinstance(at, typer.models.OptionInfo) else at
    if is_dry_run():
        target_name = name or "current"
        if at_value is not None:
            conn = get_connection(require_timeline=True)
            selection = db_timeline_selection.resolve_audio_group(conn, clip_name=name, at=at_value)
            target_name = selection["audio"].name
        dry_run_message(f"Would set audio gain on '{target_name}' to {validated_db} dB")
        return

    conn = get_connection(require_timeline=True)
    selection = db_timeline_selection.resolve_audio_group(conn, clip_name=name, at=at_value)
    if native_clip_audio.available(conn, gain_db=validated_db):
        output(native_clip_audio.set_audio(conn, selection["audio"], kind="audio-gain", values={"AudioVolume": validated_db}), title="Clip Audio Gain")
        return
    enforce_mutation_policy("clip.audio_gain", intended_engine="db_workaround")
    timeline_name = _timeline_name(conn)
    def _write_gain(_connection, cursor, _session):
        existing_gain_db = clip_effects_db.read_current_audio_gain(
            cursor,
            audio_item=selection["audio"],
            timeline_name=timeline_name,
        )
        result = clip_effects_db.apply_audio_effect(
            cursor,
            audio_item=selection["audio"],
            write=clip_effects_db.build_audio_gain_payload(validated_db),
            effect_name="audio-gain",
            timeline_name=timeline_name,
        )
        return {
            **result,
            "existing_gain_db": float(existing_gain_db),
            "resulting_gain_db": float(validated_db),
        }

    def _verify_gain(_connection, mutation_result, session):
        with sqlite3.connect(
            Path(session.project_db_path).resolve().as_uri() + "?mode=ro",
            uri=True,
            timeout=5.0,
        ) as database:
            database.row_factory = sqlite3.Row
            actual_gain_db = clip_effects_db.read_current_audio_gain(
                database.cursor(),
                audio_item=selection["audio"],
                timeline_name=timeline_name,
            )
        matches = math.isclose(
            float(actual_gain_db), float(mutation_result["resulting_gain_db"]),
            rel_tol=0.0, abs_tol=1e-9,
        )
        return {
            "status": "verified" if matches else "failed",
            "checks": [{"name": "exact_audio_gain_db", "ok": matches}],
            "actual_gain_db": float(actual_gain_db),
        }

    data = db_session.execute_sqlite_disk_db_mutation(
        conn,
        context="DB-backed audio gain",
        writer=_write_gain,
        verifier=_verify_gain,
        require_verified=True,
    )
    output(data, title="Clip Audio Gain")
