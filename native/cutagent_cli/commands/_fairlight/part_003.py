from __future__ import annotations


def _ai_track_fx_blocker_evidence(feature: str) -> dict[str, object]:
    """Describe the currently verified AI audio boundary for missing clip payloads."""
    if feature == "music_remixer":
        return {
            "primary_feature_scope": "track_fx_plugin",
            "primary_source_evidence": "DaVinci Resolve 19 New Features Guide describes Music Remixer as a Track FX plugin.",
            "local_bmd_catalog_candidates": [
                {
                    "class_name": "BMDMusicSeparator",
                    "name": "Music Separator",
                    "param_tokens": [
                        "VOICE_LEVEL",
                        "DRUMS_LEVEL",
                        "BASS_LEVEL",
                        "GUITAR_LEVEL",
                        "OTHER_LEVEL",
                        "VOICE_MUTE",
                        "DRUMS_MUTE",
                        "BASS_MUTE",
                        "GUITAR_MUTE",
                        "OTHER_MUTE",
                    ],
                }
            ],
            "local_runtime_boundary": "Current DaVinci Resolve Free runtime exposes no Music Remixer scripting getter/setter or verified track-FX slot write route.",
            "clip_fx_route_scope": "conditional_existing_payload_only",
        }
    return {
        "primary_feature_scope": "track_or_inspector_fx",
        "primary_source_evidence": "Current scripting README exposes Voice Isolation APIs only; no Dialogue Leveler getter/setter is documented.",
        "local_bmd_catalog_candidates": [
            {
                "class_name": "BMDDialogProcessor",
                "name": "Dialogue Processor",
                "note": "catalog signal only; not a verified Dialogue Leveler clip payload or track-FX slot route",
            },
            {
                "class_name": "BMDSpeechSeparator",
                "name": "Speech Separator",
                "param_tokens": [
                    "VOICE_LEVEL",
                    "BACKGROUND_LEVEL",
                    "AMBIENCE_LEVEL",
                    "VOICE_MUTE",
                    "BACKGROUND_MUTE",
                    "AMBIENCE_MUTE",
                ],
            },
        ],
        "local_runtime_boundary": "Current DaVinci Resolve Free runtime exposes no Dialogue Leveler scripting getter/setter or verified track-FX slot write route.",
        "clip_fx_route_scope": "conditional_existing_payload_only",
    }


@ai_app.command("voice-isolation")
@handle_errors
def ai_voice_isolation(
    amount: float = typer.Argument(..., help="Amount 0-100"),
    clip: str | None = typer.Option(
        None,
        "--clip",
        help="Timeline audio clip name or id to target; defaults to the first current-timeline audio clip",
    ),
    sdk_native_clip_id: str | None = typer.Option(
        None,
        "--sdk-native-clip-id",
        hidden=True,
    ),
):
    """Set AI Voice Isolation amount (0-100)."""
    if not 0.0 <= amount <= 100.0:
        raise ValidationError(
            "amount must be between 0 and 100.",
            details={
                "argument": "amount",
                "value": amount,
                "min": 0.0,
                "max": 100.0,
            },
        )
    native_amount = int(round(amount))
    enforce_mutation_policy("clip.voice_isolation", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            {
                "action": "fairlight.ai.voice_isolation",
                "would_update": True,
                "dry_run": True,
                "route": "api_native_timeline_item_voice_isolation",
                "requested": {
                    "amount": amount,
                    "native_amount": native_amount,
                    "enable": True,
                    "clip": clip,
                },
                "native_api": {
                    "write": "TimelineItem.SetVoiceIsolationState(state)",
                    "readback": "TimelineItem.GetVoiceIsolationState()",
                },
                "preconditions": ["Current timeline must contain an audio clip or --clip must match a timeline audio item."],
            },
            title="Voice Isolation Plan",
        )
        return
    conn = get_connection(require_timeline=True)
    exact_clip = sdk_native_clip_id or clip
    write_result = clip_ops.set_voice_isolation(conn, exact_clip, enabled=True, amount=native_amount)
    readback = clip_ops.get_voice_isolation(conn, exact_clip)
    expected = {"isEnabled": True, "amount": native_amount}
    if readback.get("isEnabled") is not True or int(readback.get("amount", -1)) != native_amount:
        raise APICallFailed(
            "TimelineItem.SetVoiceIsolationState readback did not match requested state.",
            details={
                "clip": clip,
                "requested": expected,
                "readback": readback,
            },
        )
    set_verification_status("verified")
    data = {
        "action": "fairlight.ai.voice_isolation",
        "route": "api_native_timeline_item_voice_isolation",
        "clip": readback.get("clip") or write_result.get("clip") or clip,
        "requested": expected,
        "write_result": write_result,
        "readback": readback,
        "native_api": {
            "write": "TimelineItem.SetVoiceIsolationState(state)",
            "readback": "TimelineItem.GetVoiceIsolationState()",
        },
    }
    output(data, title="Voice Isolation")
    success(f"Voice Isolation amount set to {native_amount}%")


@ai_app.command("dialogue-leveler")
@handle_errors
def ai_dialogue_leveler(
    lifter: bool = typer.Option(None, "--lifter/--no-lifter", help="Lift soft dialogue"),
    cleaner: bool = typer.Option(None, "--cleaner/--no-cleaner", help="Background reduction"),
    gain: float = typer.Option(None, "--gain", help="Output gain (0.0-1.0)"),
    clip: str | None = typer.Option(
        None,
        "--clip",
        help="Timeline audio clip name or id to target; defaults to the first current-timeline audio clip",
    ),
):
    """Set AI Dialogue Leveler parameters."""
    if gain is not None and not 0.0 <= gain <= 1.0:
        raise ValidationError(
            "--gain must be between 0.0 and 1.0.",
            details={
                "option": "--gain",
                "value": gain,
                "min": 0.0,
                "max": 1.0,
            },
        )
    enforce_mutation_policy("fairlight.dialogue_leveler", intended_engine="db_workaround", mutating=not is_dry_run())
    requested = {
        "lifter": lifter,
        "cleaner": cleaner,
        "gain": gain,
        "clip": clip,
    }
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            {
                "action": "fairlight.ai.dialogue_leveler",
                "would_update": True,
                "conditional_db_write": True,
                "dry_run": True,
                "route": "db_workaround",
                "db_table": "Sm2TiItem",
                "db_field": "FieldsBlob",
                "db_payload": "FL::ClipFX",
                "requested": requested,
                "preconditions": [
                    "Current timeline must contain an audio clip.",
                    "Target clip must not already contain an unrelated FL::ClipFX payload unless it already contains Dialogue Leveler params.",
                ],
                "readiness_guard": "dialogue_leveler_default_or_existing_payload_available",
            },
            title="Dialogue Leveler Plan",
        )
        return
    from ..core.audio_clip_fx import (
        PLUGIN_DIALOGUE_LEVELER,
        PARAM_DL_CLEANER_ON,
        PARAM_DL_LIFTER_ON,
        PARAM_DL_OUTPUT_GAIN,
        default_clip_fx_payload,
        insert_clip_fx_into_fieldsblob,
        read_clip_fx_from_db,
        set_param_in_payload,
        write_clip_fx_to_fieldsblob,
    )
    conn = get_connection(require_timeline=True)
    target_timeline_name = _current_timeline_name(conn)
    expected_params: dict[str, float] = {}
    if lifter is not None:
        expected_params[PARAM_DL_LIFTER_ON] = 1.0 if lifter else 0.0
    if cleaner is not None:
        expected_params[PARAM_DL_CLEANER_ON] = 1.0 if cleaner else 0.0
    if gain is not None:
        expected_params[PARAM_DL_OUTPUT_GAIN] = float(gain)

    def _writer(_db_conn, cursor, _session):
        clip_row = _resolve_fairlight_clip_fx_row(
            cursor,
            conn=conn,
            clip_selector=clip,
            timeline_name=target_timeline_name,
            allow_live_resolution=False,
        )
        clip_id = str(clip_row.get("Sm2TiItem_id") or "")
        state = read_clip_fx_from_db(cursor, clip_id)
        original_row = cursor.execute(
            "SELECT FieldsBlob FROM Sm2TiItem WHERE Sm2TiItem_id = ?",
            (clip_id,),
        ).fetchone()
        original_fieldsblob = original_row["FieldsBlob"] if original_row and original_row["FieldsBlob"] else b""
        seeded_default_payload = False
        if not state or not state.raw_payload:
            default_payload = default_clip_fx_payload(PLUGIN_DIALOGUE_LEVELER)
            if default_payload is None:
                raise ReadinessFailed(
                    "Dialogue Leveler default payload is unavailable.",
                    details={
                        "clip_id": clip_id,
                        "clip": clip,
                        "name": clip_row.get("Name"),
                        "timeline_name": target_timeline_name,
                        "track_index": clip_row.get("track_index"),
                        "feature": "dialogue_leveler",
                        "precondition": "dialogue_leveler_default_payload_available",
                    },
                )
            payload = default_payload
            seeded_default_payload = True
        else:
            payload = state.raw_payload
        try:
            for param_name, value in expected_params.items():
                payload = set_param_in_payload(payload, param_name, value)
        except ValueError as exc:
            set_verification_status("not_requested")
            raise ReadinessFailed(
                "Dialogue Leveler parameters are not present on clip. Enable Dialogue Leveler in DaVinci Resolve first.",
                details={
                    "clip_id": clip_id,
                    "clip": clip,
                    "name": clip_row.get("Name"),
                    "timeline_name": target_timeline_name,
                    "track_index": clip_row.get("track_index"),
                    "feature": "dialogue_leveler",
                    "precondition": "dialogue_leveler_enabled_on_clip",
                    "missing_parameter": str(exc),
                    "track_fx_blocker_evidence": _ai_track_fx_blocker_evidence("dialogue_leveler"),
                },
            ) from exc
        if seeded_default_payload:
            new_fb = insert_clip_fx_into_fieldsblob(original_fieldsblob, payload)
        else:
            new_fb = write_clip_fx_to_fieldsblob(original_fieldsblob, payload)
        cursor.execute(
            "UPDATE Sm2TiItem SET FieldsBlob = ? WHERE Sm2TiItem_id = ?",
            (new_fb, clip_id),
        )
        return {
            "action": "fairlight.ai.dialogue_leveler",
            "clip_id": clip_id,
            "requested": requested,
            "updated_params": sorted(expected_params),
            "seeded_default_payload": seeded_default_payload,
        }

    def _verifier(_fresh_conn, mutation_result, session):
        return _verify_clip_fx_params(
            project_db_path=session.project_db_path,
            clip_id=mutation_result["clip_id"],
            plugin_id=PLUGIN_DIALOGUE_LEVELER,
            expected_params=expected_params,
            feature="dialogue_leveler",
        )

    data = db_session.execute_sqlite_disk_db_mutation(
        conn,
        context="Fairlight Dialogue Leveler DB write",
        writer=_writer,
        verifier=_verifier,
        allow_project_name_inference=True,
    )
    output(data, title="Dialogue Leveler")
    success("Dialogue Leveler settings updated.")


@ai_app.command("music-remixer")
@handle_errors
def ai_music_remixer(
    voice: float = typer.Option(None, "--voice", help="Voice stem level (0.0-1.0)"),
    drums: float = typer.Option(None, "--drums", help="Drums stem level (0.0-1.0)"),
    bass: float = typer.Option(None, "--bass", help="Bass stem level (0.0-1.0)"),
    other: float = typer.Option(None, "--other", help="Other stem level (0.0-1.0)"),
    guitar: float = typer.Option(None, "--guitar", help="Guitar stem level (0.0-1.0)"),
    clip: str | None = typer.Option(
        None,
        "--clip",
        help="Timeline audio clip name or id to target; defaults to the first current-timeline audio clip",
    ),
):
    """Set AI Music Remixer stem levels."""
    requested = {
        "voice": voice,
        "drums": drums,
        "bass": bass,
        "other": other,
        "guitar": guitar,
        "clip": clip,
    }
    for option, value in {
        "voice": voice,
        "drums": drums,
        "bass": bass,
        "other": other,
        "guitar": guitar,
    }.items():
        if value is not None and not 0.0 <= value <= 1.0:
            raise ValidationError(
                f"--{option} must be between 0.0 and 1.0.",
                details={
                    "option": f"--{option}",
                    "value": value,
                    "min": 0.0,
                    "max": 1.0,
                },
            )
    enforce_mutation_policy("fairlight.music_remixer", intended_engine="db_workaround", mutating=not is_dry_run())
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            {
                "action": "fairlight.ai.music_remixer",
                "would_update": True,
                "conditional_db_write": True,
                "dry_run": True,
                "route": "db_workaround",
                "db_table": "Sm2TiItem",
                "db_field": "FieldsBlob",
                "db_payload": "FL::ClipFX",
                "requested": requested,
                "preconditions": [
                    "Current timeline must contain an audio clip.",
                    "Target clip must not already contain an unrelated FL::ClipFX payload unless it already contains Music Remixer params.",
                ],
                "readiness_guard": "music_remixer_default_or_existing_payload_available",
            },
            title="Music Remixer Plan",
        )
        return
    from ..core.audio_clip_fx import (
        PLUGIN_MUSIC_REMIXER,
        PARAM_MR_BASS_LEVEL,
        PARAM_MR_DRUMS_LEVEL,
        PARAM_MR_GUITAR_LEVEL,
        PARAM_MR_OTHER_LEVEL,
        PARAM_MR_VOICE_LEVEL,
        default_clip_fx_payload,
        insert_clip_fx_into_fieldsblob,
        read_clip_fx_from_db,
        set_param_in_payload,
        write_clip_fx_to_fieldsblob,
    )
    conn = get_connection(require_timeline=True)
    target_timeline_name = _current_timeline_name(conn)
    param_map = {
        "voice": (voice, PARAM_MR_VOICE_LEVEL),
        "drums": (drums, PARAM_MR_DRUMS_LEVEL),
        "bass": (bass, PARAM_MR_BASS_LEVEL),
        "other": (other, PARAM_MR_OTHER_LEVEL),
        "guitar": (guitar, PARAM_MR_GUITAR_LEVEL),
    }
    expected_params = {param: float(val) for _name, (val, param) in param_map.items() if val is not None}

    def _writer(_db_conn, cursor, _session):
        clip_row = _resolve_fairlight_clip_fx_row(
            cursor,
            conn=conn,
            clip_selector=clip,
            timeline_name=target_timeline_name,
            allow_live_resolution=False,
        )
        clip_id = str(clip_row.get("Sm2TiItem_id") or "")
        state = read_clip_fx_from_db(cursor, clip_id)
        original_row = cursor.execute(
            "SELECT FieldsBlob FROM Sm2TiItem WHERE Sm2TiItem_id = ?",
            (clip_id,),
        ).fetchone()
        original_fieldsblob = original_row["FieldsBlob"] if original_row and original_row["FieldsBlob"] else b""
        seeded_default_payload = False
        if not state or not state.raw_payload:
            default_payload = default_clip_fx_payload(PLUGIN_MUSIC_REMIXER)
            if default_payload is None:
                raise ReadinessFailed(
                    "Music Remixer default payload is unavailable.",
                    details={
                        "clip_id": clip_id,
                        "clip": clip,
                        "name": clip_row.get("Name"),
                        "timeline_name": target_timeline_name,
                        "track_index": clip_row.get("track_index"),
                        "feature": "music_remixer",
                        "precondition": "music_remixer_default_payload_available",
                    },
                )
            payload = default_payload
            seeded_default_payload = True
        else:
            payload = state.raw_payload
        try:
            for param, value in expected_params.items():
                payload = set_param_in_payload(payload, param, value)
        except ValueError as exc:
            set_verification_status("not_requested")
            raise ReadinessFailed(
                "Music Remixer parameters are not present on clip. Enable Music Remixer in DaVinci Resolve first.",
                details={
                    "clip_id": clip_id,
                    "clip": clip,
                    "name": clip_row.get("Name"),
                    "timeline_name": target_timeline_name,
                    "track_index": clip_row.get("track_index"),
                    "feature": "music_remixer",
                    "precondition": "music_remixer_enabled_on_clip",
                    "missing_parameter": str(exc),
                    "track_fx_blocker_evidence": _ai_track_fx_blocker_evidence("music_remixer"),
                },
            ) from exc
        if seeded_default_payload:
            new_fb = insert_clip_fx_into_fieldsblob(original_fieldsblob, payload)
        else:
            new_fb = write_clip_fx_to_fieldsblob(original_fieldsblob, payload)
        cursor.execute(
            "UPDATE Sm2TiItem SET FieldsBlob = ? WHERE Sm2TiItem_id = ?",
            (new_fb, clip_id),
        )
        return {
            "action": "fairlight.ai.music_remixer",
            "clip_id": clip_id,
            "requested": requested,
            "updated_params": sorted(expected_params),
            "seeded_default_payload": seeded_default_payload,
        }

    def _verifier(_fresh_conn, mutation_result, session):
        return _verify_clip_fx_params(
            project_db_path=session.project_db_path,
            clip_id=mutation_result["clip_id"],
            plugin_id=PLUGIN_MUSIC_REMIXER,
            expected_params=expected_params,
            feature="music_remixer",
        )

    data = db_session.execute_sqlite_disk_db_mutation(
        conn,
        context="Fairlight Music Remixer DB write",
        writer=_writer,
        verifier=_verifier,
        allow_project_name_inference=True,
    )
    output(data, title="Music Remixer")
    success("Music Remixer settings updated.")


# ---------------------------------------------------------------------------
# Dynamics commands (DB-backed, exact timeline and audio track)
# ---------------------------------------------------------------------------

dyn_app = typer.Typer(help="Dynamics (Compressor/Limiter/Gate) for an audio track.")
app.add_typer(dyn_app, name="dynamics")


def _get_db_path(conn):
    """Get project DB path from connection."""
    return conn.disk_db_path()


@dyn_app.command("read")
@handle_errors
def dynamics_read(
    track: int = typer.Option(1, "--track", min=1, help="Audio track index (1-based)"),
):
    """Read current dynamics parameters."""
    from ..core.dynamics_operations import read_active_dynamics
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            {
                "action": "fairlight.dynamics.read",
                "dry_run": True,
                "runtime_read_called": False,
                "route": "db_workaround",
                "db_readback": {
                    "table": "Sm2Sequence",
                    "column": "FieldsBlob",
                    "payload": "FLStudioModelBA",
                    "storage": "zlib_fairlight_studio_model_dynamics_params",
                },
                "read_scope": "track_dynamics_parameters",
                "track": track,
                "preflight_command": "cutagent fairlight dynamics read --json",
            },
            title="Dynamics Plan",
        )
        return
    conn = get_connection(require_timeline=True)
    result = read_active_dynamics(conn, track=track)
    output(result, title="Dynamics")


def _validate_dynamics_params(params: dict[str, object]) -> dict[str, object]:
    if not params:
        raise ValidationError(
            "At least one dynamics parameter required.",
            details={
                "example": "cutagent fairlight dynamics set --comp-threshold -20 --comp-ratio 4 --comp-enable --json",
                "supported": [
                    "comp_threshold",
                    "comp_ratio",
                    "comp_knee",
                    "comp_mix",
                    "comp_enable",
                    "gate_threshold",
                    "gate_enable",
                    "limiter_threshold",
                    "limiter_enable",
                ],
            },
        )

    bounded = {"comp_knee": (0, 100), "comp_mix": (0, 100), "comp_ratio": (0, 100)}
    for name, value in params.items():
        if name in bounded:
            low, high = bounded[name]
            numeric = float(value)
            if not low <= numeric <= high:
                raise ValidationError(
                    f"{name} must be between {low} and {high}.",
                    details={"parameter": name, "value": value, "min": low, "max": high},
                )
        if name.endswith("_enable") and not isinstance(value, bool):
            raise ValidationError(
                f"{name} must be a boolean enable/disable flag.",
                details={"parameter": name, "value": value},
            )
    return params


@dyn_app.command("set")
@handle_errors
def dynamics_set(
    track: int = typer.Option(1, "--track", min=1, help="Audio track index (1-based)"),
    comp_threshold: float | None = typer.Option(None, "--comp-threshold", help="Compressor threshold (dB, e.g. -20.0)"),
    comp_ratio: float | None = typer.Option(None, "--comp-ratio", help="Compressor ratio control (normalized native scale 0-100)"),
    comp_knee: int | None = typer.Option(None, "--comp-knee", help="Compressor knee (0-100)"),
    comp_mix: int | None = typer.Option(None, "--comp-mix", help="Compressor mix (0-100)"),
    comp_enable: bool | None = typer.Option(None, "--comp-enable/--comp-disable", help="Enable/disable compressor"),
    gate_threshold: float | None = typer.Option(None, "--gate-threshold", help="Gate threshold (dB)"),
    gate_enable: bool | None = typer.Option(None, "--gate-enable/--gate-disable", help="Enable/disable gate"),
    limiter_threshold: float | None = typer.Option(None, "--lim-threshold", help="Limiter threshold (dB)"),
    limiter_enable: bool | None = typer.Option(None, "--lim-enable/--lim-disable", help="Enable/disable limiter"),
):
    """Set individual dynamics parameters.

    Project must be closed before patching. Will close, patch, and reopen.
    """
    enforce_mutation_policy("fairlight.dynamics", intended_engine="db_workaround", mutating=not is_dry_run())
    params = {
        "comp_threshold": comp_threshold,
        "comp_ratio": comp_ratio,
        "comp_knee": comp_knee,
        "comp_mix": comp_mix,
        "comp_enable": comp_enable,
        "gate_threshold": gate_threshold,
        "gate_enable": gate_enable,
        "limiter_threshold": limiter_threshold,
        "limiter_enable": limiter_enable,
    }
    params = _validate_dynamics_params({k: v for k, v in params.items() if v is not None})
    if is_dry_run():
        dry_run_message(
            "Would set Fairlight dynamics via DB-backed route: "
            + ", ".join(f"{name}={value}" for name, value in params.items())
        )
        return

    from ..core.dynamics_operations import set_active_dynamics
    conn = get_connection(require_timeline=True)
    data = set_active_dynamics(conn, params=params, track=track, action="fairlight.dynamics.set")
    output(data, title="Dynamics Set")
    success("Dynamics parameters updated.")


def _set_dynamics_enabled(*, enabled: bool, track: int):
    enforce_mutation_policy("fairlight.dynamics", intended_engine="db_workaround", mutating=not is_dry_run())
    action = "fairlight.dynamics.enable" if enabled else "fairlight.dynamics.disable"
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output({
            "action": action, "track": track, "enabled": enabled,
            "dry_run": True, "route": "db_workaround",
            "project_close_required_for_live_run": True,
            "would_close_project": False, "would_patch_project_db": False,
            "would_reload_project": False,
        }, title="Dynamics Plan")
        return
    from ..core.dynamics_operations import set_active_dynamics
    conn = get_connection(require_timeline=True)
    params = {name: enabled for name in ("comp_enable", "gate_enable", "limiter_enable")}
    result = set_active_dynamics(conn, params=params, track=track, action=action)
    output(result, title="Dynamics")
    success("Dynamics enabled." if enabled else "Dynamics disabled.")


@dyn_app.command("enable")
@handle_errors
def dynamics_enable(
    track: int = typer.Option(1, "--track", min=1, help="Audio track index (1-based)"),
):
    """Enable compressor, gate, and limiter while preserving their settings."""
    _set_dynamics_enabled(enabled=True, track=track)


@dyn_app.command("disable")
@handle_errors
def dynamics_disable(
    track: int = typer.Option(1, "--track", min=1, help="Audio track index (1-based)"),
):
    """Disable compressor, gate, and limiter while preserving their settings."""
    _set_dynamics_enabled(enabled=False, track=track)


# ---------------------------------------------------------------------------
# EQ commands (DB-backed, clip-level)
# ---------------------------------------------------------------------------

eq_app = typer.Typer(help="Clip EQ operations (multi-band, DB-backed).")
app.add_typer(eq_app, name="eq")


@eq_app.command("read")
@handle_errors
def eq_read():
    """Read current EQ settings from audio clip."""
    from ..core.audio_eq_db import read_eq_state
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            {
                "action": "fairlight.eq.read",
                "dry_run": True,
                "runtime_read_called": False,
                "route": "db_workaround",
                "db_readback": {
                    "table": "Sm2TiItem",
                    "column": "EffectFiltersBA",
                    "db_type": "Sm2TiAudioClip",
                    "storage": "clip_eq_effect_filters_payload",
                },
                "read_scope": "clip_eq_parameters",
                "preflight_command": "cutagent fairlight eq read --json",
            },
            title="EQ Settings Plan",
        )
        return
    conn = get_connection(require_timeline=True)
    state = read_eq_state(conn.disk_db_cursor())
    output(state, title="EQ Settings")


@eq_app.command("set")
@handle_errors
def eq_set(
    bands: str | None = typer.Argument(
        None,
        help="Band spec: 'B1:high-pass@80 B2:bell@1k+6dB/Q2 B6:low-pass@12k'",
    ),
    sdk_audio_item_id: str | None = typer.Option(
        None,
        "--sdk-audio-item-id",
        hidden=True,
    ),
):
    """Set multi-band EQ from scratch."""
    enforce_mutation_policy("fairlight.eq", intended_engine="db_workaround", mutating=not is_dry_run())
    from ..core.audio_eq_composer import compose_eq_payload, parse_eq_spec, write_eq_payload_with_cursor

    parsed_bands = parse_eq_spec(str(bands or ""))
    eq_payload = compose_eq_payload(parsed_bands)
    if is_dry_run():
        dry_run_message(
            "Would set Fairlight EQ via DB-backed route: "
            + ", ".join(
                f"B{band.band}:{band.shape_name}@{band.freq_hz}Hz"
                + (f"{band.gain_db:+g}dB" if band.gain_db else "")
                + (f"/Q{band.q:g}" if band.q != 1.0 else "")
                for band in parsed_bands
            )
        )
        return

    conn = get_connection(require_timeline=True)

    def _writer(_db_conn, cursor, _session):
        data = write_eq_payload_with_cursor(
            cursor,
            payload=eq_payload,
            bands=parsed_bands,
            spec_str=str(bands or ""),
            audio_item_id=sdk_audio_item_id,
        )
        return {"action": "fairlight.eq.set", **data}

    def _verifier(_fresh_conn, mutation_result, session):
        return _verify_eq_payload(
            project_db_path=session.project_db_path,
            audio_item_id=mutation_result["audio_item_id"],
            expected_payload=eq_payload,
        )

    try:
        data = db_session.execute_sqlite_disk_db_mutation(
            conn,
            context="Fairlight EQ DB write",
            writer=_writer,
            verifier=_verifier,
            allow_project_name_inference=True,
        )
    except ValidationError:
        raise
    except APICallFailed:
        raise
    except Exception as exc:
        raise APICallFailed(
            "Failed to set Fairlight EQ via DB-backed route.",
            details={
                "bands": bands,
                "engine": "db_workaround",
                "hint": "Use `cutagent fairlight eq read --json` to verify the current clip and `--dry-run` to validate the band spec before writing.",
                "error_type": exc.__class__.__name__,
            },
        ) from exc
    output(data, title="EQ Set")
    success(f"EQ set: {bands}")
