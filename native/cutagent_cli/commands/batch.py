"""Batch/YAML deterministic recipe commands."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import typer

from ..connection import get_connection
from ..core import audio_ops, color_ops, db_session, db_timeline_selection, fx_template_ops, multicam_ops, recipe_ops, speed_ramp_db, transition_db
from ..core import media_pool as media_pool_ops
from ..errors import APICallFailed, ValidationError, handle_errors
from ..output import (
    dry_run_message,
    is_dry_run,
    is_machine_mode,
    output,
    set_recoverability,
    set_verification_status,
)
from ..policy import enforce_mutation_policy
from ..utils.time_ref import parse_record_frame
from ..utils.timecode import parse_time_input, seconds_to_frames

app = typer.Typer(help="Batch/YAML deterministic recipe execution.")


OperationHandler = Callable[[dict[str, Any]], Any]


def _steps_are_read_only_doctor_steps(data: dict[str, Any]) -> bool:
    steps = data.get("steps")
    return isinstance(steps, list) and all(isinstance(step, dict) and step.get("op") == "doctor" for step in steps)


def _doctor(_: dict[str, Any]) -> dict[str, Any]:
    return recipe_ops.doctor_snapshot()


def _edit_transition_add(args: dict[str, Any]) -> Any:
    conn = get_connection(require_timeline=True)
    transition_name = transition_db.normalize_transition_name(str(args["type"]))
    selection_scope = transition_db.resolve_transition_selection_scope(transition_name, str(args.get("scope", "auto")))
    if selection_scope == "audio":
        audio_selection = db_timeline_selection.resolve_audio_group(
            conn,
            clip_name=args.get("clip"),
            at=args.get("at"),
        )
        selected = {"video": None, "audio": audio_selection["audio"]}
    elif selection_scope == "video":
        video_selection = db_timeline_selection.resolve_video_group(
            conn,
            clip_name=args.get("clip"),
            at=args.get("at"),
        )
        selected = {"video": video_selection["video"], "audio": None}
    else:
        selected = db_timeline_selection.resolve_linked_av_group(
            conn,
            clip_name=args.get("clip"),
            at=args.get("at"),
        )
    timeline_name = conn.timeline.GetName() if getattr(conn, "timeline", None) else None
    duration_spec = args.get("duration")
    duration_omitted = duration_spec is None or (isinstance(duration_spec, str) and not duration_spec.strip())
    if duration_omitted:
        duration_frames = transition_db.default_transition_duration_frames_for_targets(
            video_item=selected["video"],
            audio_item=selected["audio"],
        )
    else:
        duration_ref = str(duration_spec).strip()
        duration_frames = seconds_to_frames(parse_time_input(duration_ref, conn.fps), conn.fps)
        if duration_frames <= 0:
            raise ValidationError("Transition duration must be greater than 0.", details={"duration": duration_ref})
    at_frame = parse_record_frame(str(args["at"]), conn.fps, conn.start_frame) if args.get("at") else None
    return db_session.execute_sqlite_disk_db_mutation(
        conn,
        context="DB-backed transition add",
        writer=lambda connection, cursor, session: transition_db.add_transition_rows(
            cursor,
            video_item=selected["video"],
            audio_item=selected["audio"],
            transition_name=transition_name,
            duration_frames=duration_frames,
            placement=str(args.get("placement", "both")),
            scope=str(args.get("scope", "auto")),
            timeline_name=timeline_name,
            at_frame=at_frame,
        ),
        verifier=lambda connection, mutation_result, session: {
            "status": "pending_manual",
            "checks": [
                {"name": "project_db_route", "ok": True},
                {
                    "name": "resolve_ui_confirmation_required",
                    "ok": False,
                    "detail": "Disk DB insertion succeeded, but DaVinci Resolve timeline/UI confirmation is still required for transitions.",
                },
            ],
        },
    )


def _parse_fx_params(args: dict[str, Any]) -> dict[str, Any]:
    params = args.get("params") or {}
    if isinstance(params, str):
        params = json.loads(params)
    if not isinstance(params, dict):
        raise ValidationError("edit.fx.add params must be an object.", details={"params": params})
    return params


def _edit_fx_add(args: dict[str, Any]) -> Any:
    conn = get_connection(require_timeline=True)
    return fx_template_ops.add_fx_via_template(
        conn,
        name=str(args["name"]),
        clip_name=args.get("clip"),
        template_path=args.get("template"),
        params=_parse_fx_params(args),
        verify=bool(args.get("verify", True)),
    )


def _color_wheels_set(args: dict[str, Any]) -> Any:
    conn = get_connection(require_timeline=True)
    return color_ops.emulate_wheels(
        conn,
        clip_name=args.get("clip"),
        node=int(args.get("node", 1)),
        lift=args.get("lift"),
        gamma=args.get("gamma"),
        gain=args.get("gain"),
        sat=args.get("sat"),
        mode=str(args.get("mode", "cdl")),
        lut_output=args.get("lut_output"),
    )


def _audio_duck(args: dict[str, Any]) -> dict[str, Any]:
    result_path = audio_ops.duck(
        str(args["input_media"]),
        speech_track=int(args["speech_track"]),
        music_track=int(args["music_track"]),
        threshold_db=float(args.get("threshold_db", -20.0)),
        ratio=float(args.get("ratio", 8.0)),
        attack_ms=float(args.get("attack_ms", 20.0)),
        release_ms=float(args.get("release_ms", 300.0)),
        output=args.get("output"),
    )
    replace_media = args.get("replace_media")
    if replace_media:
        conn = get_connection(require_project=True)
        media_pool_ops.relink_clip(conn, str(replace_media), result_path)
    return {
        "input": args["input_media"],
        "output": result_path,
        "replace_media": replace_media,
    }


def _clip_speed_ramp(args: dict[str, Any]) -> Any:
    conn = get_connection(require_timeline=True)
    plan = speed_ramp_db.prepare_speed_ramp_transition(
        conn,
        cut_at=args.get("cut_at", "current"),
        out_frames=int(args.get("out_frames", 18)),
        in_frames=int(args.get("in_frames", 18)),
        peak_speed=args.get("peak_speed", "6.5x"),
        curve=str(args.get("curve", "sharp-s")),
        reverse_incoming=bool(args.get("reverse_incoming", False)),
        track=int(args.get("track", 0)),
        out_start_speed=args.get("out_start_speed", "1x"),
        out_end_speed=args.get("out_end_speed"),
        in_start_speed=args.get("in_start_speed"),
        in_end_speed=args.get("in_end_speed", "1x"),
        out_start_handle=args.get("out_start_handle"),
        out_end_handle=args.get("out_end_handle"),
        in_start_handle=args.get("in_start_handle"),
        in_end_handle=args.get("in_end_handle"),
        out_ease=args.get("out_ease", "in-out"),
        in_ease=args.get("in_ease", "in-out"),
        out_start_interp=args.get("out_start_interp"),
        out_end_interp=args.get("out_end_interp"),
        in_start_interp=args.get("in_start_interp"),
        in_end_interp=args.get("in_end_interp"),
        out_points=args.get("out_point") or args.get("out_points"),
        in_points=args.get("in_point") or args.get("in_points"),
    )
    data = db_session.execute_sqlite_disk_db_mutation(
        conn,
        context="DB-backed clip speed-ramp",
        writer=lambda connection, cursor, session: speed_ramp_db.apply_speed_ramp_transition(cursor, plan=plan),
        verifier=speed_ramp_db.verify_speed_ramp_transition,
    )
    if bool(args.get("adjustment_blur", False)):
        from . import clip as clip_commands
        from ..connection import ResolveConnection

        blur_options = clip_commands._validate_speed_ramp_blur_options(
            enabled=True,
            frames=int(args.get("blur_frames", 8)),
            track=int(args.get("blur_track", 0)),
            angle=float(args.get("blur_angle", 0.0)),
            distance=float(args.get("blur_distance", 0.16)),
            peak_opacity=float(args.get("blur_peak_opacity", 1.0)),
            name=args.get("blur_name"),
        )
        fresh_conn = ResolveConnection.get()
        fresh_conn.connect()
        data["adjustment_blur"] = clip_commands._insert_speed_ramp_adjustment_blur(
            fresh_conn,
            plan=plan,
            blur_options=blur_options,
        )
    return data


def _edit_multicam_create(args: dict[str, Any]) -> Any:
    conn = get_connection(require_project=True)
    return multicam_ops.multicam_create(
        conn,
        timeline_name=str(args["timeline"]),
        angles=str(args["angles"]),
        sync=str(args.get("sync", "start")),
        base_track=int(args.get("base_track", 2)),
    )


def _edit_multicam_switch(args: dict[str, Any]) -> Any:
    conn = get_connection(require_timeline=True)
    return multicam_ops.multicam_switch(
        conn,
        switches=str(args["switches"]),
        program_track=int(args.get("program_track", 1)),
        angles_track_base=int(args.get("angles_track_base", 2)),
    )


_OP_HANDLERS: dict[str, OperationHandler] = {
    "doctor": _doctor,
    "edit.transition.add": _edit_transition_add,
    "edit.fx.add": _edit_fx_add,
    "color.wheels.set": _color_wheels_set,
    "audio.duck": _audio_duck,
    "clip.speed-ramp": _clip_speed_ramp,
    "edit.multicam-create": _edit_multicam_create,
    "edit.multicam-switch": _edit_multicam_switch,
}


def _run_operation(op: str, args: dict[str, Any]) -> Any:
    handler = _OP_HANDLERS.get(op)
    if handler is None:
        raise ValidationError("Unsupported recipe operation.", details={"op": op})
    return handler(args)


def run_recipe_pipeline(path: str, *, doctor: bool, fail_fast: bool) -> dict[str, Any]:
    normalized = recipe_ops.validate_recipe_file(path)
    result = recipe_ops.run_recipe_data(
        normalized,
        dispatcher=_run_operation,
        fail_fast=fail_fast,
        run_doctor=doctor,
    )
    result["recipe"] = normalized.get("path")
    return result


@app.command("validate")
@handle_errors
def validate(path: str = typer.Argument(..., help="Path to deterministic recipe YAML")):
    """Validate deterministic recipe YAML schema (version=1)."""
    data = recipe_ops.validate_recipe_file(path)
    output(data, title="Batch Validate")


@app.command("run")
@handle_errors
def run(
    path: str = typer.Argument(..., help="Path to deterministic recipe YAML"),
    doctor: bool = typer.Option(False, "--doctor", help="Run doctor preflight before steps"),
    fail_fast: bool = typer.Option(True, "--fail-fast/--continue-on-error", help="Stop on first step failure"),
):
    """Run deterministic recipe steps."""
    enforce_mutation_policy(
        "edit.batch_recipe_pipeline",
        intended_engine="workaround_setting",
        mutating=not is_dry_run(),
    )

    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        normalized = recipe_ops.validate_recipe_file(path)
        if not is_machine_mode():
            dry_run_message(f"Would run recipe '{path}' with {normalized['step_count']} step(s).")
        output({"recipe": normalized.get("path"), "steps": normalized["steps"], "doctor": doctor})
        return

    data = run_recipe_pipeline(path, doctor=doctor, fail_fast=fail_fast)
    if data.get("ok") is False:
        raise APICallFailed("Batch recipe failed.", details=data)
    if _steps_are_read_only_doctor_steps(data):
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
    output(data, title="Batch Run")
