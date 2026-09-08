"""One-command auto-edit pipeline wrapper over deterministic batch recipes."""

from __future__ import annotations

import typer

from ..connection import get_connection
from ..core import edit_ops, multicam_engine, native_multicam_db, podcast_audio_activity, podcast_multicam, recipe_ops
from ..errors import APICallFailed, ValidationError, handle_errors
from ..output import (
    dry_run_message,
    is_dry_run,
    is_machine_mode,
    output,
    mutation_payload,
    set_recoverability,
    set_verification_status,
)
from ..policy import enforce_mutation_policy
from . import batch as batch_commands

app = typer.Typer(help="Auto-edit orchestration from deterministic YAML recipes.")


def _typer_default(value: object, default: object = None) -> object:
    return default if isinstance(value, typer.models.OptionInfo) else value


def _steps_are_read_only_doctor_steps(data: dict[str, object]) -> bool:
    steps = data.get("steps")
    return isinstance(steps, list) and all(isinstance(step, dict) and step.get("op") == "doctor" for step in steps)


def _podcast_edit_missing_inputs(*, timeline: str | None, angles: str | None, transcript: str | None) -> list[str]:
    missing: list[str] = []
    if not str(timeline or "").strip():
        missing.append("timeline")
    if not str(angles or "").strip():
        missing.append("angles")
    if not str(transcript or "").strip():
        missing.append("transcript")
    return missing


def _podcast_edit_guidance(*, timeline: str | None, angles: str | None, transcript: str | None) -> dict[str, object]:
    missing = _podcast_edit_missing_inputs(timeline=timeline, angles=angles, transcript=transcript)
    return {
        "missing": missing,
        "required_transcript": {
            "option": "--transcript",
            "format": "speaker-labelled JSON with utterances, segments, speaker_turns, or words rows",
            "compatible_with": "ElevenLabs Scribe v2 style JSON",
        },
        "native_resolve_preparation": [
            "Use `cutagent render transcript-audio /tmp/podcast-transcript.mp3` to render transcript-ready audio from the active timeline.",
            "Create a speaker-labelled JSON transcript from that audio, then rerun with --transcript.",
            "DaVinci Resolve Media Pool transcription can annotate clips, but DaVinci Resolve does not expose a public API that exports the speaker-labelled JSON required for podcast camera switching.",
        ],
        "example": (
            'cutagent auto-edit podcast-edit --timeline "Podcast Edit" '
            '--angles "A=camA.mov,B=camB.mov" '
            "--transcript /path/to/scribe-v2.json "
            '--speaker-map "speaker_0=A,speaker_1=B" --json'
        ),
    }


def _build_podcast_preset_job(
    *,
    timeline: str,
    angles: str,
    transcript: str | None,
    speaker_map: str | None,
    multicam_name: str | None,
    sync: str,
    min_shot_ms: int,
    merge_gap_ms: int,
    switch_by: str = "transcript",
    audio_source_specs: list[str] | None = None,
    audio_angle_map: str | None = None,
    audio_target_specs: list[str] | None = None,
    audio_sync: str | None = None,
    sync_reference_audio: str | None = None,
    sync_reference_angle: str | None = None,
    audio_offsets_json: str | None = None,
    overlap_policy: str | None = None,
    overlap_angle: str | None = None,
    analysis_window_ms: int | None = None,
    activity_floor_db: float | None = None,
    activity_margin_db: float | None = None,
    dominance_margin_db: float | None = None,
    min_switch_ms: int | None = None,
    switch_delay_ms: int | None = None,
    max_silence_hold_ms: int | None = None,
    allow_unresolved_targets: bool = False,
    program_audio_source_specs: list[str] | None = None,
    replace_program_audio: bool = False,
    program_audio_unmapped: str = "remove",
) -> dict[str, object]:
    angle_map = podcast_multicam._parse_angle_spec(angles)
    resolved_switch_by = str(switch_by or "transcript").strip()
    if resolved_switch_by not in {"transcript", "audio-activity"}:
        raise ValidationError(
            "Unsupported podcast multicam switch mode.",
            details={"switch_by": resolved_switch_by, "supported": ["transcript", "audio-activity"]},
        )
    job: dict[str, object] = {
        "sources": [
            {"angle": angle, "clip_name": clip_name}
            for angle, clip_name in angle_map.items()
        ],
        "selection_policy_result": {
            "strategy": "explicit_podcast_preset",
            "source": "auto-edit podcast-multicam",
        },
        "timeline_settings": {
            "timeline_name": timeline,
            "replace_active_timeline": False,
        },
        "switch_by": resolved_switch_by,
        "multicam_settings": {
            "multicam_name": multicam_name or f"{timeline} Multicam",
            "timeline_name": timeline,
            "sync_mode": sync,
            "min_shot_ms": min_shot_ms,
            "merge_gap_ms": merge_gap_ms,
            "default_video_angle": next(iter(angle_map.keys())),
            "default_audio_angle": next(iter(angle_map.keys())),
            "hold_short_utterances": False,
            "reaction_hold_ms": 0,
            "switch_on": ["speaker_active"],
            "switch_exceptions": [],
        },
        "verification_requirements": {
            "require_native_multicam": True,
            "require_native_multicam_segments": True,
            "require_switch_menu": True,
        },
    }
    if resolved_switch_by == "transcript":
        program_audio_sources = podcast_audio_activity.parse_audio_sources(program_audio_source_specs)
        if replace_program_audio and not program_audio_sources:
            raise ValidationError(
                "Transcript podcast multicam program audio replacement requires --program-audio-source.",
                details={"required_option": "--program-audio-source"},
            )
        if program_audio_sources:
            program_audio_angle_map = podcast_audio_activity.parse_audio_angle_map(audio_angle_map)
            if not program_audio_angle_map:
                raise ValidationError(
                    "Transcript podcast multicam program audio replacement requires --audio-angle-map.",
                    details={"required_option": "--audio-angle-map"},
                )
            job["program_audio"] = {
                "mode": "multicam_internal_tracks",
                "sources": program_audio_sources,
                "audio_angle_map": program_audio_angle_map,
                "angle_order": list(angle_map.keys()),
                "unmapped_audio": program_audio_unmapped,
            }
        if not str(transcript or "").strip():
            raise ValidationError(
                "Transcript podcast multicam mode requires --transcript.",
                details={"switch_by": resolved_switch_by, "required_option": "--transcript"},
            )
        job["rule_program"] = {
            "kind": "speaker_transcript_v1",
            "transcript_path": str(transcript or "").strip(),
            "speaker_map": podcast_multicam.parse_speaker_mapping(speaker_map),
            "filler_tokens": [],
        }
        return job

    if not str(audio_sync or "").strip():
        raise ValidationError(
            "Audio-activity podcast multicam mode requires --audio-sync.",
            details={"switch_by": resolved_switch_by, "required_option": "--audio-sync"},
        )
    sync_payload: dict[str, object] = {"mode": str(audio_sync or "").strip()}
    if sync_reference_audio:
        sync_payload["reference_audio_path"] = str(sync_reference_audio).strip()
    if sync_reference_angle:
        sync_payload["reference_angle"] = str(sync_reference_angle).strip()
    loaded_offsets = podcast_audio_activity.load_audio_offsets_json(audio_offsets_json)
    if loaded_offsets:
        sync_payload["offsets"] = loaded_offsets
    overlap_payload: dict[str, object] = {}
    if overlap_policy:
        overlap_payload["policy"] = str(overlap_policy).strip()
    if overlap_angle:
        overlap_payload["angle"] = str(overlap_angle).strip()
        overlap_payload.setdefault("policy", "angle")
    parsed_audio_angle_map = podcast_audio_activity.parse_audio_angle_map(audio_angle_map)
    parsed_audio_targets = podcast_audio_activity.parse_audio_targets(audio_target_specs)
    job["rule_program"] = {
        "kind": "audio_activity_v1",
        "audio_sources": podcast_audio_activity.parse_audio_sources(audio_source_specs),
        "audio_angle_map": parsed_audio_angle_map,
        "audio_targets": parsed_audio_targets,
        "audio_sync": sync_payload,
        "switching": {
            "analysis_window_ms": analysis_window_ms,
            "activity_floor_db": activity_floor_db,
            "activity_margin_db": activity_margin_db,
            "dominance_margin_db": dominance_margin_db,
            "min_switch_ms": min_switch_ms,
            "switch_delay_ms": switch_delay_ms,
            "max_silence_hold_ms": 0 if max_silence_hold_ms is None else max_silence_hold_ms,
        },
        "overlap": overlap_payload,
        "allow_unresolved_targets": bool(allow_unresolved_targets),
    }
    program_audio_sources = podcast_audio_activity.parse_audio_sources(program_audio_source_specs)
    if replace_program_audio and not program_audio_sources:
        program_audio_sources = list(job["rule_program"]["audio_sources"])
    if program_audio_sources:
        replacement_angle_map = dict(parsed_audio_angle_map)
        if not replacement_angle_map:
            for source_id, target in parsed_audio_targets.items():
                angles = [str(item).strip() for item in list(target.get("angles") or []) if str(item).strip()]
                if len(angles) == 1:
                    replacement_angle_map[str(source_id)] = angles[0]
        if not replacement_angle_map:
            raise ValidationError(
                "Program audio replacement requires --audio-angle-map or single-angle --audio-target values.",
                details={"required_option": "--audio-angle-map"},
            )
        job["program_audio"] = {
            "mode": "multicam_internal_tracks",
            "sources": program_audio_sources,
            "audio_angle_map": replacement_angle_map,
            "angle_order": list(angle_map.keys()),
            "offsets": loaded_offsets,
            "unmapped_audio": program_audio_unmapped,
        }
    return job


@app.command("run")
@handle_errors
def run(
    path: str = typer.Argument(..., help="Path to deterministic recipe YAML"),
    doctor: bool = typer.Option(False, "--doctor", help="Run doctor preflight before steps"),
    fail_fast: bool = typer.Option(True, "--fail-fast/--continue-on-error", help="Stop on first step failure"),
):
    """Run one-command auto-edit pipeline."""
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
            dry_run_message(f"Would run auto-edit recipe '{path}' with {normalized['step_count']} step(s).")
        output(
            {
                "recipe": normalized.get("path"),
                "steps": normalized["steps"],
                "doctor": doctor,
                "fail_fast": fail_fast,
            }
        )
        return

    data = batch_commands.run_recipe_pipeline(path, doctor=doctor, fail_fast=fail_fast)
    if data.get("ok") is False:
        raise APICallFailed("Auto-edit recipe failed.", details=data)
    if _steps_are_read_only_doctor_steps(data):
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
    output(data, title="Auto Edit Run")


@app.command("silence-cut")
@handle_errors
def silence_cut_cmd(
    threshold_db: float = typer.Option(-40.0, "--threshold-db", help="Silence threshold in dB"),
    auto_threshold: bool = typer.Option(
        False,
        "--auto-threshold/--fixed-threshold",
        help="Calibrate the silence threshold from rendered timeline dynamics",
    ),
    min_silence: float = typer.Option(0.5, "--min-silence", help="Minimum silence duration in seconds"),
    padding: float = typer.Option(0.1, "--padding", help="Keep this much time around speech in seconds"),
    timeline_name: str | None = typer.Option(None, "--name", help="Name for the new timeline"),
    wav_path: str = typer.Option("/tmp/resolve_silence_cut.wav", "--wav-path", help="Temporary WAV render path"),
):
    """Create a new timeline with silent segments removed."""
    enforce_mutation_policy(
        "auto_edit.silence_cut",
        intended_engine="workaround_setting",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        dry_run_message(
            f"Would remove silence longer than {min_silence}s "
            f"with {'an adaptive threshold' if auto_threshold else f'a {threshold_db}dB threshold'} "
            f"with {padding}s padding into timeline '{timeline_name or 'auto'}'"
        )
        return

    conn = get_connection(require_timeline=True)
    data = edit_ops.silence_cut(
        conn,
        threshold_db=threshold_db,
        auto_threshold=auto_threshold,
        min_silence=min_silence,
        padding=padding,
        new_timeline_name=timeline_name,
        wav_path=wav_path,
    )
    output(data, title="Silence Cut Auto Edit")


@app.command("podcast-edit")
@handle_errors
def podcast_edit_cmd(
    timeline: str | None = typer.Option("Podcast Auto Edit", "--timeline", help="Target timeline name"),
    angles: str | None = typer.Option(None, "--angles", help="Angle spec: A=clipA,B=clipB,..."),
    transcript: str | None = typer.Option(None, "--transcript", help="Path to speaker-labelled JSON transcript"),
    speaker_map: str | None = typer.Option(None, "--speaker-map", help="Optional explicit speaker mapping: speaker_0=A,speaker_1=B"),
    multicam_name: str | None = typer.Option(None, "--multicam-name", help="Optional native multicam clip name"),
    sync: str = typer.Option(
        native_multicam_db.DEFAULT_NATIVE_ANGLE_SYNC_MODE,
        "--sync",
        help="Native multicam Angle Sync: in, out, timecode, sound, marker",
    ),
    provider: str = typer.Option("ax_native", "--provider", help="Retained for CLI compatibility; ignored by the native DB/API multicam flow"),
    verify: bool = typer.Option(True, "--verify/--no-verify", help="Retained for CLI compatibility; no GUI verification is used"),
    checkpoint: bool = typer.Option(False, "--checkpoint", help="Retained for CLI compatibility; ignored"),
    retries: int = typer.Option(1, "--retries", min=1, help="Retained for CLI compatibility; ignored"),
    min_shot_ms: int = typer.Option(1200, "--min-shot-ms", min=1, help="Minimum shot length after transcript normalization"),
    merge_gap_ms: int = typer.Option(250, "--merge-gap-ms", min=0, help="Merge same-speaker gaps shorter than this"),
):
    """Create a podcast multicam edit from a speaker-labelled transcript."""
    enforce_mutation_policy(
        "edit.multicam_podcast_auto",
        intended_engine="db_workaround",
        mutating=not is_dry_run(),
    )
    guidance = _podcast_edit_guidance(timeline=timeline, angles=angles, transcript=transcript)
    missing = list(guidance["missing"])
    if is_dry_run():
        output(
            {
                "message": "DRY-RUN: Would create a podcast multicam edit from transcript-driven active-speaker switches.",
                **guidance,
                "timeline": timeline,
                "angles": angles,
                "transcript": transcript,
                "speaker_map": speaker_map,
                "multicam_name": multicam_name,
                "sync": sync,
                "provider": provider,
                "verify": verify,
                "checkpoint": checkpoint,
                "retries": retries,
                "min_shot_ms": min_shot_ms,
                "merge_gap_ms": merge_gap_ms,
            },
            title="Podcast Edit Auto Edit",
        )
        return
    if missing:
        raise ValidationError(
            "Podcast edit requires a timeline, angle map, and speaker-labelled transcript before running.",
            details=guidance,
        )

    conn = get_connection(require_project=True)
    payload = _build_podcast_preset_job(
        timeline=str(timeline),
        angles=str(angles),
        transcript=str(transcript),
        speaker_map=speaker_map,
        multicam_name=multicam_name,
        sync=sync,
        min_shot_ms=min_shot_ms,
        merge_gap_ms=merge_gap_ms,
    )
    data = multicam_engine.auto_edit_multicam(conn, job=payload)
    data["preset"] = {
        "name": "podcast_edit",
        "source": "auto-edit podcast-edit",
        "provider": provider,
        "verify": verify,
        "checkpoint": checkpoint,
        "retries": retries,
    }
    output(data, title="Podcast Edit Auto Edit")


@app.command("podcast-multicam")
@handle_errors
def podcast_multicam_cmd(
    timeline: str = typer.Option(..., "--timeline", help="Target timeline name"),
    angles: str = typer.Option(..., "--angles", help="Angle spec: A=clipA,B=clipB,..."),
    switch_by: str = typer.Option("transcript", "--switch-by", help="Switch planner: transcript or audio-activity"),
    transcript: str | None = typer.Option(None, "--transcript", help="Path to ElevenLabs Scribe v2 JSON transcript"),
    speaker_map: str = typer.Option(None, "--speaker-map", help="Optional explicit speaker mapping: speaker_0=A,speaker_1=B"),
    audio_source: list[str] | None = typer.Option(None, "--audio-source", help="Repeatable audio activity source spec: id=/path/audio.wav"),
    audio_angle_map: str | None = typer.Option(None, "--audio-angle-map", help="Audio activity mapping: source_id=ANGLE,source_id=ANGLE"),
    audio_target: list[str] | None = typer.Option(None, "--audio-target", help="Repeatable flexible target spec: source_id=ANGLE or source_id=ANGLE_A,ANGLE_B"),
    audio_sync: str | None = typer.Option(None, "--audio-sync", help="Audio sync mode for audio-activity: prealigned, waveform, offsets-json"),
    sync_reference_audio: str | None = typer.Option(None, "--sync-reference-audio", help="Reference camera/audio file for waveform audio sync"),
    sync_reference_angle: str | None = typer.Option(None, "--sync-reference-angle", help="Reference angle for waveform audio sync when the angle has a source path"),
    audio_offsets_json: str | None = typer.Option(None, "--audio-offsets-json", help="Path to JSON offsets object for audio-activity sync"),
    overlap_policy: str | None = typer.Option(None, "--overlap-policy", help="Overlap handling: angle/wide, dominant, hold, mark"),
    overlap_angle: str | None = typer.Option(None, "--overlap-angle", "--wide-angle", help="Multicam angle to use for overlap/wide moments"),
    analysis_window_ms: int | None = typer.Option(None, "--analysis-window-ms", min=1, help="Audio activity analysis window in milliseconds"),
    activity_floor_db: float | None = typer.Option(None, "--activity-floor-db", help="Absolute dBFS floor required for activity"),
    activity_margin_db: float | None = typer.Option(None, "--activity-margin-db", help="dB above per-source noise floor required for activity"),
    dominance_margin_db: float | None = typer.Option(None, "--dominance-margin-db", help="Leader margin in dB required before avoiding overlap handling"),
    min_switch_ms: int | None = typer.Option(None, "--min-switch-ms", min=0, help="Minimum planned video switch duration in milliseconds"),
    switch_delay_ms: int | None = typer.Option(None, "--switch-delay-ms", min=0, help="New audio target must persist this long before switching"),
    max_silence_hold_ms: int | None = typer.Option(None, "--max-silence-hold-ms", min=0, help="Hold previous angle through silence up to this duration"),
    program_audio_source: list[str] | None = typer.Option(None, "--program-audio-source", help="Repeatable internal multicam program-audio source spec: id=/path/audio.wav"),
    replace_program_audio: bool = typer.Option(False, "--replace-program-audio", help="Replace internal native multicam audio angle items with isolated mic WAVs"),
    program_audio_unmapped: str = typer.Option("remove", "--program-audio-unmapped", help="Internal audio policy for angles without replacement sources: keep or remove"),
    plan_only: bool = typer.Option(False, "--plan-only", help="Build and return the switch plan without creating/applying the edit"),
    write_plan: str | None = typer.Option(None, "--write-plan", help="Optional JSON path to write the generated switch plan"),
    multicam_name: str = typer.Option(None, "--multicam-name", help="Optional native multicam clip name"),
    sync: str = typer.Option(
        native_multicam_db.DEFAULT_NATIVE_ANGLE_SYNC_MODE,
        "--sync",
        help="Native multicam Angle Sync: in, out, timecode, sound, marker",
    ),
    provider: str = typer.Option("ax_native", "--provider", help="Retained for CLI compatibility; ignored by the native DB/API multicam flow"),
    verify: bool = typer.Option(True, "--verify/--no-verify", help="Retained for CLI compatibility; no GUI verification is used"),
    checkpoint: bool = typer.Option(False, "--checkpoint", help="Retained for CLI compatibility; ignored"),
    retries: int = typer.Option(1, "--retries", min=1, help="Retained for CLI compatibility; ignored"),
    min_shot_ms: int = typer.Option(1200, "--min-shot-ms", min=1, help="Minimum shot length after transcript normalization"),
    merge_gap_ms: int = typer.Option(250, "--merge-gap-ms", min=0, help="Merge same-speaker gaps shorter than this"),
):
    """Create a native podcast multicam cut from transcript or audio activity."""
    switch_by = str(_typer_default(switch_by, "transcript") or "transcript")
    transcript = _typer_default(transcript)
    speaker_map = _typer_default(speaker_map)
    audio_source = _typer_default(audio_source)
    audio_angle_map = _typer_default(audio_angle_map)
    audio_target = _typer_default(audio_target)
    audio_sync = _typer_default(audio_sync)
    sync_reference_audio = _typer_default(sync_reference_audio)
    sync_reference_angle = _typer_default(sync_reference_angle)
    audio_offsets_json = _typer_default(audio_offsets_json)
    overlap_policy = _typer_default(overlap_policy)
    overlap_angle = _typer_default(overlap_angle)
    analysis_window_ms = _typer_default(analysis_window_ms)
    activity_floor_db = _typer_default(activity_floor_db)
    activity_margin_db = _typer_default(activity_margin_db)
    dominance_margin_db = _typer_default(dominance_margin_db)
    min_switch_ms = _typer_default(min_switch_ms)
    switch_delay_ms = _typer_default(switch_delay_ms)
    max_silence_hold_ms = _typer_default(max_silence_hold_ms)
    program_audio_source = _typer_default(program_audio_source)
    replace_program_audio = bool(_typer_default(replace_program_audio, False))
    program_audio_unmapped = str(_typer_default(program_audio_unmapped, "remove") or "remove")
    plan_only = bool(_typer_default(plan_only, False))
    write_plan = _typer_default(write_plan)
    enforce_mutation_policy(
        "edit.multicam_podcast_auto",
        intended_engine="db_workaround",
        mutating=not is_dry_run() and not plan_only,
    )
    payload = _build_podcast_preset_job(
        timeline=timeline,
        angles=angles,
        transcript=transcript,
        speaker_map=speaker_map,
        multicam_name=multicam_name,
        sync=sync,
        min_shot_ms=min_shot_ms,
        merge_gap_ms=merge_gap_ms,
        switch_by=switch_by,
        audio_source_specs=audio_source,
        audio_angle_map=audio_angle_map,
        audio_target_specs=audio_target,
        audio_sync=audio_sync,
        sync_reference_audio=sync_reference_audio,
        sync_reference_angle=sync_reference_angle,
        audio_offsets_json=audio_offsets_json,
        overlap_policy=overlap_policy,
        overlap_angle=overlap_angle,
        analysis_window_ms=analysis_window_ms,
        activity_floor_db=activity_floor_db,
        activity_margin_db=activity_margin_db,
        dominance_margin_db=dominance_margin_db,
        min_switch_ms=min_switch_ms,
        switch_delay_ms=switch_delay_ms,
        max_silence_hold_ms=max_silence_hold_ms,
        allow_unresolved_targets=plan_only,
        program_audio_source_specs=program_audio_source,
        replace_program_audio=replace_program_audio,
        program_audio_unmapped=program_audio_unmapped,
    )
    if is_dry_run():
        dry_run_message(
            f"Would auto-edit podcast multicam timeline '{timeline}' with angles '{angles}', "
            f"switch mode '{switch_by}', provider '{provider}'"
        )
        return

    if plan_only:
        plan_conn = type("DryRunPodcastMulticamContext", (), {"fps": 24.0, "start_frame": 0})()
        runtime_validation = "not_performed"
        runtime_validation_error = None
        rule_kind = str((payload.get("rule_program") or {}).get("kind") or "").strip() if isinstance(payload.get("rule_program"), dict) else ""
        if rule_kind == "audio_activity_v1":
            try:
                plan_conn = get_connection(require_project=True)
                runtime_validation = "live_project_context"
            except Exception as exc:
                runtime_validation = "dry_context_fallback"
                runtime_validation_error = str(exc)
        plan = multicam_engine.build_multicam_job_plan(plan_conn, payload)
        if str(write_plan or "").strip():
            from pathlib import Path
            import json

            out_path = Path(str(write_plan)).expanduser()
            if out_path.parent and not out_path.parent.exists():
                raise ValidationError(
                    "Switch plan output directory does not exist.",
                    details={"write_plan": str(out_path), "parent": str(out_path.parent)},
                )
            out_path.write_text(json.dumps(plan, indent=2), encoding="utf-8")
        output(
            mutation_payload(
                action="auto_edit.podcast_multicam.plan",
                changed=False,
                target={"kind": "timeline", "name": timeline},
                timeline_name=timeline,
                multicam_name=payload["multicam_settings"]["multicam_name"],
                segment_count=plan.get("segment_count", len(plan.get("segments") or [])),
                unresolved_segment_count=len((plan.get("audio_activity") or {}).get("unresolved_segments") or []),
                plan=plan,
                write_plan=write_plan,
                runtime_validation=runtime_validation,
                runtime_validation_error=runtime_validation_error,
                message=f"Built podcast multicam plan for '{timeline}'.",
            )
        )
        return

    conn = get_connection(require_project=True)
    data = multicam_engine.auto_edit_multicam(conn, job=payload)
    data["preset"] = {
        "name": "podcast_multicam",
        "provider": provider,
        "verify": verify,
        "checkpoint": checkpoint,
        "retries": retries,
    }
    output(data, title="Podcast Multicam Auto Edit")


@app.command("multicam")
@handle_errors
def multicam_cmd(
    job: str | None = typer.Option(None, "--job", help="Path to a structured multicam job JSON file"),
    job_json: str | None = typer.Option(None, "--job-json", help="Inline structured multicam job JSON"),
):
    """Create and switch a native multicam edit from a structured multicam job."""
    enforce_mutation_policy(
        "multicam.job_execute",
        intended_engine="db_workaround",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        dry_run_message("Would execute a structured native multicam auto-edit job.")
        return

    payload = multicam_engine.load_multicam_job(job_path=job, job_json=job_json)
    conn = get_connection(require_project=True)
    data = multicam_engine.auto_edit_multicam(conn, job=payload)
    output(data, title="Multicam Auto Edit")
