"""Fairlight effect, ClipFX, index, and mixer helper commands."""

from __future__ import annotations

def _is_voice_isolation_effect(effect: str | None) -> bool:
    normalized = _normalize_clip_fx_lookup_key(effect)
    return normalized in {
        "voiceisolation",
        "bmdvoiceisolation",
        "bmdvoiceisolation1112364617",
    }


def _voice_isolation_effect_toggle_payload(
    *,
    conn,
    clip: str,
    enabled: bool,
) -> dict[str, Any]:
    expected_enabled = bool(enabled)
    expected_amount = 100 if expected_enabled else 0
    write_result = clip_ops.set_voice_isolation(conn, clip, enabled=expected_enabled, amount=expected_amount)
    readback = clip_ops.get_voice_isolation(conn, clip)
    actual_enabled = bool(readback.get("isEnabled"))
    actual_amount = int(readback.get("amount", -1))
    ok = actual_enabled == expected_enabled and actual_amount == expected_amount
    if not ok:
        raise APICallFailed(
            "Voice Isolation effect toggle did not match native timeline item readback.",
            details={
                "clip": clip,
                "requested": {"isEnabled": expected_enabled, "amount": expected_amount},
                "write_result": write_result,
                "readback": readback,
            },
            recoverability="manual",
        )
    set_verification_status("verified")
    set_recoverability("manual")
    return mutation_payload(
        action="fairlight.effect.add" if expected_enabled else "fairlight.effect.remove",
        target={"kind": "audio_clip", "clip": clip},
        changed=True,
        runtime_write_called=True,
        route="api_native_timeline_item_voice_isolation",
        effect={
            "key": "voice_isolation",
            "name": "Voice Isolation",
            "native_state": "TimelineItem VoiceIsolationState",
        },
        requested={"isEnabled": expected_enabled, "amount": expected_amount},
        write_result=write_result,
        readback=readback,
        native_api={
            "write": "TimelineItem.SetVoiceIsolationState(state)",
            "readback": "TimelineItem.GetVoiceIsolationState()",
        },
        verification={"status": "verified", "checks": [{"name": "timeline_item_voice_isolation_state", "ok": True}]},
        residual_scope=(
            "This native route toggles DaVinci Resolve's built-in clip Voice Isolation state. It does not provide "
            "arbitrary Fairlight track/bus plugin slot insertion or removal."
        ),
    )


@effect_app.command("add")
@handle_errors
def effect_add(
    effect: str | None = typer.Argument(None, help="Fairlight effect/plugin name"),
    track: int | None = typer.Option(None, "--track", "-t", help="Audio track index to target"),
    clip: str | None = typer.Option(None, "--clip", help="Timeline clip name to target"),
    bus: str | None = typer.Option(None, "--bus", help="Bus name to target"),
):
    """Enable a verified DB-backed built-in Fairlight effect route."""
    if not effect:
        set_capability_context("fairlight.plugin_routing", "unsupported")
        set_execution_engine("db_workaround")
        raise ValidationError(
            "Effect name is required.",
            details={
                "example": "cutagent fairlight effect add \"Dialogue Processor\" --json",
                "required": ["effect"],
                "unsupported": ["--track", "--clip", "--bus"],
                "api_note": "Fairlight FX/plugin insertion is available only for verified current timeline built-in processing.",
            },
        )
    if track is not None and int(track) < 1:
        raise ValidationError(
            "Audio track index is out of range.",
            details={"track": track, "min": 1},
            recoverability="not_applicable",
        )
    if clip and track is None and bus is None and _is_voice_isolation_effect(effect):
        enforce_mutation_policy("clip.voice_isolation", intended_engine="api_native", mutating=not is_dry_run())
        set_execution_engine("api_native")
        if is_dry_run():
            set_verification_status("not_requested")
            set_recoverability("not_applicable")
            output(
                mutation_payload(
                    action="fairlight.effect.add",
                    target={"kind": "audio_clip", "clip": clip},
                    changed=False,
                    dry_run=True,
                    runtime_write_called=False,
                    route="api_native_timeline_item_voice_isolation",
                    effect={
                        "key": "voice_isolation",
                        "name": "Voice Isolation",
                        "native_state": "TimelineItem VoiceIsolationState",
                    },
                    requested={"isEnabled": True, "amount": 100},
                    native_api={
                        "write": "TimelineItem.SetVoiceIsolationState(state)",
                        "readback": "TimelineItem.GetVoiceIsolationState()",
                    },
                    residual_scope=(
                        "This native route toggles DaVinci Resolve's built-in clip Voice Isolation state. It does not "
                        "provide arbitrary Fairlight track/bus plugin slot insertion."
                    ),
                    preflight_command=f"cutagent fairlight effect add 'Voice Isolation' --clip '{clip}' --json",
                ),
                title="Fairlight Voice Isolation Add Plan",
            )
            return
        conn = get_connection(require_timeline=True)
        output(_voice_isolation_effect_toggle_payload(conn=conn, clip=clip, enabled=True), title="Fairlight Voice Isolation Add")
        return
    clip_fx_spec = _resolve_fairlight_clip_fx_effect(effect)
    if clip and track is None and bus is None and clip_fx_spec is not None:
        from ..core import audio_clip_fx

        default_payload = audio_clip_fx.default_clip_fx_payload(clip_fx_spec["plugin_id"])
        if default_payload is not None:
            enforce_mutation_policy("fairlight.clip_effect_param_write", intended_engine="db_workaround", mutating=not is_dry_run())
            if is_dry_run():
                set_execution_engine("db_workaround")
                set_verification_status("not_requested")
                set_recoverability("not_applicable")
                output(
                    mutation_payload(
                        action="fairlight.effect.add",
                        target={"kind": "audio_clip", "clip": clip},
                        changed=False,
                        dry_run=True,
                        runtime_write_called=False,
                        route="db_workaround",
                        effect={
                            "requested": effect,
                            "key": clip_fx_spec["key"],
                            "name": clip_fx_spec["name"],
                            "plugin_id": clip_fx_spec["plugin_id"],
                        },
                        db_write={"table": "Sm2TiItem", "column": "FieldsBlob", "payload": "FL::ClipFX"},
                        fixture=_fairlight_clip_fx_fixture_info(clip_fx_spec, default_payload),
                        preconditions=[
                            "Target clip must not already contain an FL::ClipFX plugin payload.",
                            "Only packaged verified default payloads are inserted.",
                        ],
                        residual_scope=(
                            "This inserts a verified single-plugin clip-level FL::ClipFX payload while preserving sibling "
                            "clip payloads. It does not provide arbitrary track/bus plugin slots or AU/VST insertion."
                        ),
                        preflight_command=f"cutagent fairlight effect add '{effect}' --clip '{clip}' --json",
                    ),
                    title="Fairlight Clip FX Add Plan",
                )
                return

            conn = get_connection(require_timeline=True)
            target_timeline_name = _current_timeline_name(conn)

            def _writer(_db_conn, cursor, _session):
                clip_row = _resolve_fairlight_clip_fx_row(
                    cursor,
                    conn=conn,
                    clip_selector=clip,
                    timeline_name=target_timeline_name,
                    allow_live_resolution=False,
                )
                clip_id = str(clip_row.get("Sm2TiItem_id") or "")
                state = audio_clip_fx.read_clip_fx_from_db(cursor, clip_id)
                if state and state.plugins:
                    set_verification_status("not_requested")
                    raise ReadinessFailed(
                        "The target clip already contains a clip-level Fairlight FX payload.",
                        details={
                            "clip_id": clip_id,
                            "clip": clip_row.get("Name"),
                            "effect": {
                                "key": clip_fx_spec["key"],
                                "name": clip_fx_spec["name"],
                                "plugin_id": clip_fx_spec["plugin_id"],
                            },
                            "precondition": "clip_fx_payload_absent",
                            "available_clip_fx_plugins": _clip_fx_available_plugins(state),
                        },
                    )
                original_row = cursor.execute(
                    "SELECT FieldsBlob FROM Sm2TiItem WHERE Sm2TiItem_id = ?",
                    (clip_id,),
                ).fetchone()
                original_fieldsblob = original_row["FieldsBlob"] if original_row and original_row["FieldsBlob"] else b""
                new_fieldsblob = audio_clip_fx.insert_clip_fx_into_fieldsblob(original_fieldsblob, default_payload)
                cursor.execute(
                    "UPDATE Sm2TiItem SET FieldsBlob = ? WHERE Sm2TiItem_id = ?",
                    (new_fieldsblob, clip_id),
                )
                return {
                    "action": "fairlight.effect.add",
                    "route": "db_workaround",
                    "target": {
                        "kind": "audio_clip",
                        "clip": clip,
                        "clip_id": clip_id,
                        "name": clip_row.get("Name"),
                        "track_index": clip_row.get("track_index"),
                        "timeline_name": target_timeline_name,
                    },
                    "effect": {
                        "requested": effect,
                        "key": clip_fx_spec["key"],
                        "name": clip_fx_spec["name"],
                        "plugin_id": clip_fx_spec["plugin_id"],
                    },
                    "fixture": _fairlight_clip_fx_fixture_info(clip_fx_spec, default_payload),
                    "db_write": {"table": "Sm2TiItem", "column": "FieldsBlob", "inserted_payload": "FL::ClipFX"},
                }

            def _verifier(_fresh_conn, mutation_result, session):
                return _verify_clip_fx_present(
                    project_db_path=session.project_db_path,
                    clip_id=mutation_result["target"]["clip_id"],
                    plugin_id=clip_fx_spec["plugin_id"],
                    feature=clip_fx_spec["key"],
                )

            data = db_session.execute_sqlite_disk_db_mutation(
                conn,
                context="Fairlight clip FX add DB write",
                writer=_writer,
                verifier=_verifier,
                allow_project_name_inference=True,
            )
            output(data, title="Fairlight Effect Add")
            success(f"Added {clip_fx_spec['name']}.")
            return
    if track is not None or clip or bus:
        _raise_fairlight_native_unavailable(
            capability_id="fairlight.plugin_routing",
            workflow="Fairlight track/clip/bus effect insertion",
            requested={"effect": effect, "track": track, "clip": clip, "bus": bus},
            required_native_api=[
                "insert Fairlight effect/plugin on a track, clip, or bus",
                "read/write arbitrary Fairlight plugin slot assignments",
                "verify inserted plugin slot readback",
            ],
            api_note=(
                "The verified DB-backed effect route targets current timeline built-in Fairlight processing only; "
                "track, clip, bus, and arbitrary plugin slot insertion remain unmapped."
            ),
            workaround="Use `fairlight effect add EFFECT` for supported built-in timeline processing, or set arbitrary slots in DaVinci Resolve.",
            extra_details={
                "requested_effect": effect,
                "requested_track": track,
                "requested_clip": clip,
                "requested_bus": bus,
                "available_read_routes": _FAIRLIGHT_PLUGIN_SLOT_DB_BLOCKER_EVIDENCE["available_read_routes"],
                **_FAIRLIGHT_PLUGIN_SLOT_DB_BLOCKER_EVIDENCE,
            },
        )
    canonical_effect = fairlight_ops._canonical_fairlight_effect_name(effect)
    capability_id = "fairlight.eq" if canonical_effect == "eq" else "fairlight.dynamics"
    enforce_mutation_policy(capability_id, intended_engine="db_workaround", mutating=not is_dry_run())
    if is_dry_run():
        set_execution_engine("db_workaround")
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            {
                "action": "fairlight.effect.add",
                "would_add": True,
                "dry_run": True,
                "route": "db_workaround_dynamics_params",
                "effect": "EQ" if canonical_effect == "eq" else "Dialogue Processor",
                "project_close_required_for_live_run": True,
            },
            title="Fairlight Effect Add Plan",
        )
        return
    conn = get_connection(require_timeline=True)
    data = fairlight_ops.set_fairlight_effect_state_db(conn, effect_name=effect, enabled=True)
    output(data, title="Fairlight Effect Add")


@effect_app.command("remove")
@handle_errors
def effect_remove(
    effect: str | None = typer.Argument(None, help="Fairlight effect/plugin name or slot identifier"),
    track: int | None = typer.Option(None, "--track", "-t", help="Audio track index to target"),
    clip: str | None = typer.Option(None, "--clip", help="Timeline clip name to target"),
    bus: str | None = typer.Option(None, "--bus", help="Bus name to target"),
):
    """Disable a verified DB-backed built-in Fairlight effect route."""
    if not effect:
        set_capability_context("fairlight.plugin_routing", "unsupported")
        set_execution_engine("db_workaround")
        raise ValidationError(
            "Effect name or slot is required.",
            details={
                "example": "cutagent fairlight effect remove \"Dialogue Processor\" --json",
                "required": ["effect"],
                "unsupported": ["--track", "--clip", "--bus"],
                "api_note": "Fairlight FX/plugin removal is available only for verified current timeline built-in processing.",
            },
        )
    if track is not None and int(track) < 1:
        raise ValidationError(
            "Audio track index is out of range.",
            details={"track": track, "min": 1},
            recoverability="not_applicable",
        )
    if clip and track is None and bus is None and _is_voice_isolation_effect(effect):
        enforce_mutation_policy("clip.voice_isolation", intended_engine="api_native", mutating=not is_dry_run())
        set_execution_engine("api_native")
        if is_dry_run():
            set_verification_status("not_requested")
            set_recoverability("not_applicable")
            output(
                mutation_payload(
                    action="fairlight.effect.remove",
                    target={"kind": "audio_clip", "clip": clip},
                    changed=False,
                    dry_run=True,
                    runtime_write_called=False,
                    route="api_native_timeline_item_voice_isolation",
                    effect={
                        "key": "voice_isolation",
                        "name": "Voice Isolation",
                        "native_state": "TimelineItem VoiceIsolationState",
                    },
                    requested={"isEnabled": False, "amount": 0},
                    native_api={
                        "write": "TimelineItem.SetVoiceIsolationState(state)",
                        "readback": "TimelineItem.GetVoiceIsolationState()",
                    },
                    residual_scope=(
                        "This native route toggles DaVinci Resolve's built-in clip Voice Isolation state. It does not "
                        "provide arbitrary Fairlight track/bus plugin slot removal."
                    ),
                    preflight_command=f"cutagent fairlight effect remove 'Voice Isolation' --clip '{clip}' --json",
                ),
                title="Fairlight Voice Isolation Remove Plan",
            )
            return
        conn = get_connection(require_timeline=True)
        output(_voice_isolation_effect_toggle_payload(conn=conn, clip=clip, enabled=False), title="Fairlight Voice Isolation Remove")
        return
    clip_fx_spec = _resolve_fairlight_clip_fx_effect(effect)
    if clip and track is None and bus is None and clip_fx_spec is not None:
        enforce_mutation_policy("fairlight.clip_effect_param_write", intended_engine="db_workaround", mutating=not is_dry_run())
        if is_dry_run():
            set_execution_engine("db_workaround")
            set_verification_status("not_requested")
            set_recoverability("not_applicable")
            output(
                mutation_payload(
                    action="fairlight.effect.remove",
                    target={"kind": "audio_clip", "clip": clip},
                    changed=False,
                    dry_run=True,
                    runtime_write_called=False,
                    route="db_workaround",
                    effect={
                        "requested": effect,
                        "key": clip_fx_spec["key"],
                        "name": clip_fx_spec["name"],
                        "plugin_id": clip_fx_spec["plugin_id"],
                    },
                    db_write={"table": "Sm2TiItem", "column": "FieldsBlob", "payload": "FL::ClipFX"},
                    preconditions=[
                        "Target clip must already contain exactly one FL::ClipFX plugin.",
                        "That plugin must match the requested effect.",
                    ],
                    residual_scope=(
                        "This removes a verified single-plugin clip-level FL::ClipFX payload while preserving sibling "
                        "clip payloads. It does not remove arbitrary track/bus plugin slots or one plugin from a "
                        "multi-plugin clip FX payload."
                    ),
                    preflight_command=f"cutagent fairlight effect remove '{effect}' --clip '{clip}' --json",
                ),
                title="Fairlight Clip FX Remove Plan",
            )
            return

        from ..core import audio_clip_fx

        conn = get_connection(require_timeline=True)
        target_timeline_name = _current_timeline_name(conn)

        def _writer(_db_conn, cursor, _session):
            clip_row = _resolve_fairlight_clip_fx_row(
                cursor,
                conn=conn,
                clip_selector=clip,
                timeline_name=target_timeline_name,
                allow_live_resolution=False,
            )
            clip_id = str(clip_row.get("Sm2TiItem_id") or "")
            state = audio_clip_fx.read_clip_fx_from_db(cursor, clip_id)
            plugin = _find_clip_fx_plugin(state, clip_fx_spec)
            if not state or not state.raw_payload or plugin is None:
                set_verification_status("not_requested")
                raise ReadinessFailed(
                    "The requested clip-level Fairlight FX is not present on the target clip.",
                    details={
                        "clip_id": clip_id,
                        "clip": clip_row.get("Name"),
                        "effect": {
                            "key": clip_fx_spec["key"],
                            "name": clip_fx_spec["name"],
                            "plugin_id": clip_fx_spec["plugin_id"],
                        },
                        "precondition": "clip_fx_effect_present",
                        "available_clip_fx_plugins": _clip_fx_available_plugins(state),
                    },
                )
            if len(state.plugins) != 1:
                set_verification_status("not_requested")
                raise ReadinessFailed(
                    "Removing one Fairlight FX from a multi-plugin clip payload is not yet supported.",
                    details={
                        "clip_id": clip_id,
                        "clip": clip_row.get("Name"),
                        "effect": {
                            "key": clip_fx_spec["key"],
                            "name": clip_fx_spec["name"],
                            "plugin_id": clip_fx_spec["plugin_id"],
                        },
                        "precondition": "single_plugin_clip_fx_payload",
                        "available_clip_fx_plugins": _clip_fx_available_plugins(state),
                    },
                )
            original_row = cursor.execute(
                "SELECT FieldsBlob FROM Sm2TiItem WHERE Sm2TiItem_id = ?",
                (clip_id,),
            ).fetchone()
            original_fieldsblob = original_row["FieldsBlob"] if original_row and original_row["FieldsBlob"] else b""
            new_fieldsblob = audio_clip_fx.remove_clip_fx_from_fieldsblob(original_fieldsblob)
            cursor.execute(
                "UPDATE Sm2TiItem SET FieldsBlob = ? WHERE Sm2TiItem_id = ?",
                (new_fieldsblob, clip_id),
            )
            return {
                "action": "fairlight.effect.remove",
                "route": "db_workaround",
                "target": {
                    "kind": "audio_clip",
                    "clip": clip,
                    "clip_id": clip_id,
                    "name": clip_row.get("Name"),
                    "track_index": clip_row.get("track_index"),
                    "timeline_name": target_timeline_name,
                },
                "effect": {
                    "requested": effect,
                    "key": clip_fx_spec["key"],
                    "name": clip_fx_spec["name"],
                    "plugin_id": clip_fx_spec["plugin_id"],
                },
                "db_write": {"table": "Sm2TiItem", "column": "FieldsBlob", "removed_payload": "FL::ClipFX"},
            }

        def _verifier(_fresh_conn, mutation_result, session):
            return _verify_clip_fx_removed(
                project_db_path=session.project_db_path,
                clip_id=mutation_result["target"]["clip_id"],
                plugin_id=clip_fx_spec["plugin_id"],
                feature=clip_fx_spec["key"],
            )

        data = db_session.execute_sqlite_disk_db_mutation(
            conn,
            context="Fairlight clip FX removal DB write",
            writer=_writer,
            verifier=_verifier,
            allow_project_name_inference=True,
        )
        output(data, title="Fairlight Effect Remove")
        success(f"Removed {clip_fx_spec['name']}.")
        return
    if track is not None or clip or bus:
        _raise_fairlight_native_unavailable(
            capability_id="fairlight.plugin_routing",
            workflow="Fairlight track/clip/bus effect removal",
            requested={"effect": effect, "track": track, "clip": clip, "bus": bus},
            required_native_api=[
                "remove Fairlight effect/plugin from a track, clip, or bus",
                "read/write arbitrary Fairlight plugin slot assignments",
                "verify removed plugin slot readback",
            ],
            api_note=(
                "The verified DB-backed effect route targets current timeline built-in Fairlight processing only; "
                "track, clip, bus, and arbitrary plugin slot removal remain unmapped."
            ),
            workaround="Use `fairlight effect remove EFFECT` for supported built-in timeline processing, or remove arbitrary slots in DaVinci Resolve.",
            extra_details={
                "requested_effect": effect,
                "requested_track": track,
                "requested_clip": clip,
                "requested_bus": bus,
                "available_read_routes": _FAIRLIGHT_PLUGIN_SLOT_DB_BLOCKER_EVIDENCE["available_read_routes"],
                **_FAIRLIGHT_PLUGIN_SLOT_DB_BLOCKER_EVIDENCE,
            },
        )
    canonical_effect = fairlight_ops._canonical_fairlight_effect_name(effect)
    capability_id = "fairlight.eq" if canonical_effect == "eq" else "fairlight.dynamics"
    enforce_mutation_policy(capability_id, intended_engine="db_workaround", mutating=not is_dry_run())
    if canonical_effect == "eq":
        raise ValidationError(
            "Fairlight EQ is a built-in processing module and cannot be removed with fairlight effect remove.",
            details={
                "effect": effect,
                "supported_action": "Use fairlight eq set/read for EQ parameter changes.",
            },
            recoverability="not_applicable",
        )
    if is_dry_run():
        set_execution_engine("db_workaround")
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            {
                "action": "fairlight.effect.remove",
                "would_remove": True,
                "dry_run": True,
                "route": "db_workaround_dynamics_params",
                "effect": "Dialogue Processor",
                "project_close_required_for_live_run": True,
            },
            title="Fairlight Effect Remove Plan",
        )
        return
    conn = get_connection(require_timeline=True)
    data = fairlight_ops.set_fairlight_effect_state_db(conn, effect_name=effect, enabled=False)
    output(data, title="Fairlight Effect Remove")


def _normalize_clip_fx_lookup_key(value: str | None) -> str:
    return "".join(ch.casefold() for ch in str(value or "") if ch.isalnum())


def _fairlight_clip_fx_specs() -> dict[str, dict[str, Any]]:
    from ..core.audio_clip_fx import (
        PLUGIN_CHORUS,
        PLUGIN_DELAY,
        PLUGIN_DEHUMMER,
        PLUGIN_DEESSER,
        PLUGIN_DIALOGUE_LEVELER,
        PLUGIN_DIALOGUE_PROCESSOR,
        PLUGIN_DISTORTION,
        PLUGIN_ECHO,
        PLUGIN_FAIRLIGHT_EQ,
        PLUGIN_FLANGER,
        PLUGIN_GAIN,
        PLUGIN_LIMITER,
        PLUGIN_MUSIC_REMIXER,
        PLUGIN_MODULATION,
        PLUGIN_MULTIBAND_COMPRESSOR,
        PLUGIN_NOISE_REDUCTION,
        PLUGIN_PITCH,
        PLUGIN_REVERB,
        PLUGIN_SOFT_CLIPPER,
        PLUGIN_STEREO_FIXER,
        PLUGIN_STEREO_WIDTH,
        PLUGIN_VOCAL_CHANNEL,
        PLUGIN_VOICE_ISOLATION,
        PARAM_DL_CLEANER_ON,
        PARAM_DL_LIFTER_ON,
        PARAM_DL_OUTPUT_GAIN,
        PARAM_MR_BASS_LEVEL,
        PARAM_MR_DRUMS_LEVEL,
        PARAM_MR_GUITAR_LEVEL,
        PARAM_MR_OTHER_LEVEL,
        PARAM_MR_VOICE_LEVEL,
    )

    specs = [
        {
            "key": "voice_isolation",
            "name": "Voice Isolation",
            "plugin_id": PLUGIN_VOICE_ISOLATION,
            "aliases": [
                "voice isolation",
                "voice-isolation",
                "voice_isolation",
                "bmd voice isolation",
                "BMDVoiceIsolationControl",
                PLUGIN_VOICE_ISOLATION,
            ],
        },
        {
            "key": "dialogue_leveler",
            "name": "Dialogue Leveler",
            "plugin_id": PLUGIN_DIALOGUE_LEVELER,
            "verified_writable_params": [
                PARAM_DL_LIFTER_ON,
                PARAM_DL_CLEANER_ON,
                PARAM_DL_OUTPUT_GAIN,
            ],
            "aliases": [
                "dialogue leveler",
                "dialogue-leveler",
                "dialogue_leveler",
                "dialogue leveller",
                "dialogue-leveller",
                "dialogue_leveller",
                "bmd dialogue leveler",
                "bmd dialogue leveller",
                "BMDDialogueLeveler",
                "BMDAudioIntelligence",
                PLUGIN_DIALOGUE_LEVELER,
            ],
        },
        {
            "key": "dialogue_processor",
            "name": "Dialogue Processor",
            "plugin_id": PLUGIN_DIALOGUE_PROCESSOR,
            "param_write_supported": False,
            "aliases": [
                "dialogue processor",
                "dialogue-processor",
                "dialogue_processor",
                "bmd dialogue processor",
                "BMDDialogProcessor",
                PLUGIN_DIALOGUE_PROCESSOR,
            ],
        },
        {
            "key": "music_remixer",
            "name": "Music Remixer",
            "plugin_id": PLUGIN_MUSIC_REMIXER,
            "verified_writable_params": [
                PARAM_MR_VOICE_LEVEL,
                PARAM_MR_DRUMS_LEVEL,
                PARAM_MR_BASS_LEVEL,
                PARAM_MR_OTHER_LEVEL,
                PARAM_MR_GUITAR_LEVEL,
            ],
            "aliases": [
                "music remixer",
                "music-remixer",
                "music_remixer",
                "music separator",
                "music-separator",
                "music_separator",
                "bmd music remixer",
                "bmd music separator",
                "BMDMusicSeparator",
                PLUGIN_MUSIC_REMIXER,
            ],
        },
        {
            "key": "chorus",
            "name": "Chorus",
            "plugin_id": PLUGIN_CHORUS,
            "verified_writable_params": [
                "BMDChorus::DELAY",
                "BMDChorus::VOICE_SEPARATION",
                "BMDChorus::WIDTH_EXPANSION",
                "BMDChorus::MOD_TYPE",
                "BMDChorus::MOD_FREQ",
                "BMDChorus::TIME_MOD_DEPTH",
                "BMDChorus::LEVEL_MOD_DEPTH",
                "BMDChorus::FB",
                "BMDChorus::DRY_WET",
                "BMDChorus::OUTPUT_GAIN",
            ],
            "aliases": [
                "chorus",
                "bmd chorus",
                "BMDChorus",
                PLUGIN_CHORUS,
            ],
        },
        {
            "key": "deesser",
            "name": "De-Esser",
            "plugin_id": PLUGIN_DEESSER,
            "param_write_supported": False,
            "aliases": [
                "de esser",
                "de-esser",
                "deesser",
                "bmd de esser",
                "bmd de-esser",
                "BMDDeesser",
                PLUGIN_DEESSER,
            ],
        },
        {
            "key": "reverb",
            "name": "Reverb",
            "plugin_id": PLUGIN_REVERB,
            "param_write_supported": False,
            "aliases": [
                "reverb",
                "bmd reverb",
                "BMDReverb",
                PLUGIN_REVERB,
            ],
        },
        {
            "key": "distortion",
            "name": "Distortion",
            "plugin_id": PLUGIN_DISTORTION,
            "param_write_supported": False,
            "aliases": [
                "distortion",
                "bmd distortion",
                "BMDDistortion",
                PLUGIN_DISTORTION,
            ],
        },
        {
            "key": "multiband_compressor",
            "name": "Multiband Compressor",
            "plugin_id": PLUGIN_MULTIBAND_COMPRESSOR,
            "param_write_supported": False,
            "aliases": [
                "multiband compressor",
                "multi band compressor",
                "bmd multiband compressor",
                "BMDMultiBandCompressor",
                PLUGIN_MULTIBAND_COMPRESSOR,
            ],
        },
        {
            "key": "noise_reduction",
            "name": "Noise Reduction",
            "plugin_id": PLUGIN_NOISE_REDUCTION,
            "param_write_supported": False,
            "aliases": [
                "noise reduction",
                "noise-reduction",
                "noise_reduction",
                "bmd noise reduction",
                "BMDNoiseReduction",
                PLUGIN_NOISE_REDUCTION,
            ],
        },
        {
            "key": "flanger",
            "name": "Flanger",
            "plugin_id": PLUGIN_FLANGER,
            "verified_writable_params": ["BMDFlanger::DRY_WET", "BMDFlanger::OUTPUT_GAIN"],
            "aliases": [
                "flanger",
                "bmd flanger",
                "BMDFlanger",
                PLUGIN_FLANGER,
            ],
        },
        {
            "key": "echo",
            "name": "Echo",
            "plugin_id": PLUGIN_ECHO,
            "verified_writable_params": ["BMDStereoEcho::DRY_WET", "BMDStereoEcho::OUTPUT_GAIN"],
            "aliases": [
                "echo",
                "stereo echo",
                "bmd echo",
                "bmd stereo echo",
                "BMDStereoEcho",
                PLUGIN_ECHO,
            ],
        },
        {
            "key": "delay",
            "name": "Delay",
            "plugin_id": PLUGIN_DELAY,
            "verified_writable_params": ["BMDStereoDelay::DRY_WET", "BMDStereoDelay::OUTPUT_GAIN"],
            "aliases": [
                "delay",
                "stereo delay",
                "bmd delay",
                "bmd stereo delay",
                "BMDStereoDelay",
                PLUGIN_DELAY,
            ],
        },
        {
            "key": "dehummer",
            "name": "De-Hummer",
            "plugin_id": PLUGIN_DEHUMMER,
            "verified_writable_params": [
                "BMDHumRemoval::HUM_ONLY",
                "BMDHumRemoval::FREQUENCY",
                "BMDHumRemoval::AMOUNT",
                "BMDHumRemoval::CONTOUR",
            ],
            "aliases": [
                "de hummer",
                "de-hummer",
                "dehummer",
                "hum removal",
                "bmd de hummer",
                "bmd de-hummer",
                "BMDHumRemoval",
                PLUGIN_DEHUMMER,
            ],
        },
        {
            "key": "gain",
            "name": "Gain",
            "plugin_id": PLUGIN_GAIN,
            "verified_writable_params": ["BMDGain::GAIN"],
            "aliases": [
                "gain",
                "bmd gain",
                "BMDGain",
                PLUGIN_GAIN,
            ],
        },
        {
            "key": "vocal_channel",
            "name": "Vocal Channel",
            "plugin_id": PLUGIN_VOCAL_CHANNEL,
            "verified_writable_params": [
                "BMDVocalChannel::HPF_IN",
                "BMDVocalChannel::HF_GAIN",
                "BMDVocalChannel::COMP_IN",
            ],
            "aliases": [
                "vocal channel",
                "vocal-channel",
                "vocal_channel",
                "bmd vocal channel",
                "BMDVocalChannel",
                PLUGIN_VOCAL_CHANNEL,
            ],
        },
        {
            "key": "limiter",
            "name": "Limiter",
            "plugin_id": PLUGIN_LIMITER,
            "verified_writable_params": [
                "BMDLimiter::INPUT_GAIN",
                "BMDLimiter::THRESHOLD",
            ],
            "aliases": [
                "limiter",
                "bmd limiter",
                "BMDLimiter",
                PLUGIN_LIMITER,
            ],
        },
        {
            "key": "stereo_width",
            "name": "Stereo Width",
            "plugin_id": PLUGIN_STEREO_WIDTH,
            "verified_writable_params": ["BMDStereoWidth::WIDTH", "BMDStereoWidth::SPARKLE"],
            "aliases": [
                "stereo width",
                "stereo-width",
                "stereo_width",
                "width",
                "bmd stereo width",
                "BMDStereoWidth",
                PLUGIN_STEREO_WIDTH,
            ],
        },
        {
            "key": "stereo_fixer",
            "name": "Stereo Fixer",
            "plugin_id": PLUGIN_STEREO_FIXER,
            "verified_writable_params": ["BMDStereoFixer::LEFT_GAIN", "BMDStereoFixer::RIGHT_GAIN"],
            "aliases": [
                "stereo fixer",
                "stereo-fixer",
                "stereo_fixer",
                "fix stereo",
                "bmd stereo fixer",
                "BMDStereoFixer",
                PLUGIN_STEREO_FIXER,
            ],
        },
        {
            "key": "soft_clipper",
            "name": "Soft Clipper",
            "plugin_id": PLUGIN_SOFT_CLIPPER,
            "verified_writable_params": ["BMDSoftClipper::THRESHOLD", "BMDSoftClipper::OUTPUT_GAIN"],
            "aliases": [
                "soft clipper",
                "soft-clipper",
                "soft_clipper",
                "clipper",
                "bmd soft clipper",
                "BMDSoftClipper",
                PLUGIN_SOFT_CLIPPER,
            ],
        },
        {
            "key": "pitch",
            "name": "Pitch",
            "plugin_id": PLUGIN_PITCH,
            "verified_writable_params": [
                "BMDAudioPitchShift::COARSE",
                "BMDAudioPitchShift::FINE",
                "BMDAudioPitchShift::DRY_WET",
            ],
            "aliases": [
                "pitch",
                "pitch shift",
                "pitch-shift",
                "pitch_shift",
                "bmd pitch",
                "bmd pitch shift",
                "BMDAudioPitchShift",
                PLUGIN_PITCH,
            ],
        },
        {
            "key": "modulation",
            "name": "Modulation",
            "plugin_id": PLUGIN_MODULATION,
            "verified_writable_params": [
                "BMDModulation::AM_DEPTH",
                "BMDModulation::DRY_WET",
                "BMDModulation::OUTPUT_GAIN",
            ],
            "aliases": [
                "modulation",
                "am modulation",
                "bmd modulation",
                "BMDModulation",
                PLUGIN_MODULATION,
            ],
        },
        {
            "key": "fairlight_eq",
            "name": "Fairlight EQ",
            "plugin_id": PLUGIN_FAIRLIGHT_EQ,
            "verified_writable_params": [
                "BMDEq::BAND_GAIN_3",
            ],
            "aliases": [
                "fairlight eq",
                "fairlight-eq",
                "fairlight_eq",
                "bmd fairlight eq",
                "clip eq",
                "BMDEq",
                PLUGIN_FAIRLIGHT_EQ,
            ],
        },
    ]
    lookup: dict[str, dict[str, Any]] = {}
    for spec in specs:
        for alias in (spec["key"], spec["name"], spec["plugin_id"], *spec["aliases"]):
            lookup[_normalize_clip_fx_lookup_key(alias)] = spec
    return lookup


def _resolve_fairlight_clip_fx_effect(effect: str | None) -> dict[str, Any] | None:
    return _fairlight_clip_fx_specs().get(_normalize_clip_fx_lookup_key(effect))


def _fairlight_clip_fx_supported_effects() -> list[dict[str, str]]:
    seen: set[str] = set()
    effects: list[dict[str, str]] = []
    for spec in _fairlight_clip_fx_specs().values():
        key = str(spec["key"])
        if key in seen:
            continue
        seen.add(key)
        effects.append({"key": key, "name": str(spec["name"]), "plugin_id": str(spec["plugin_id"])})
    return effects


def _fairlight_clip_fx_fixture_info(spec: dict[str, Any], payload: bytes) -> dict[str, Any]:
    from ..core import audio_clip_fx

    if spec["key"] == "reverb":
        payload_length = len(payload)
        if payload_length == 0:
            default_payload = audio_clip_fx.default_clip_fx_payload(audio_clip_fx.PLUGIN_REVERB)
            payload_length = len(default_payload or b"")
        return {
            "source": "BMD built-in Reverb token mapped from verified ClipFX payload shape",
            "sha256": audio_clip_fx.REVERB_DEFAULT_PAYLOAD_SHA256,
            "payload_length": payload_length,
            "verification": {
                "db_readback_artifact": "/tmp/cutagent_fairlightfx_reverb_audio_proof_20260619_214352/12_effect_list_reverb_music.json",
                "render_ab_artifact": "/tmp/cutagent_fairlightfx_reverb_audio_proof_20260619_214352/15_reverb_vs_clean_music_diff.json",
                "cleanup_artifact": "/tmp/cutagent_fairlightfx_reverb_audio_proof_20260619_214352/17_effect_list_after_remove_music.json",
            },
        }
    if spec["key"] == "deesser":
        payload_length = len(payload)
        if payload_length == 0:
            default_payload = audio_clip_fx.default_clip_fx_payload(audio_clip_fx.PLUGIN_DEESSER)
            payload_length = len(default_payload or b"")
        return {
            "source": "BMD built-in De-Esser token mapped into the verified ClipFX payload shape",
            "sha256": audio_clip_fx.DEESSER_DEFAULT_PAYLOAD_SHA256,
            "payload_length": payload_length,
            "verification": {
                "db_readback_artifact": "/tmp/cutagent_fairlightfx_deesser_payload_probe_20260619/17_public_deesser_list_after_add.json",
                "render_ab_artifact": "/tmp/cutagent_fairlightfx_deesser_payload_probe_20260619/20_public_deesser_vs_clean_diff.json",
                "cleanup_artifact": "/tmp/cutagent_fairlightfx_deesser_payload_probe_20260619/22_public_deesser_list_after_remove.json",
            },
        }
    if spec["key"] == "distortion":
        payload_length = len(payload)
        if payload_length == 0:
            default_payload = audio_clip_fx.default_clip_fx_payload(audio_clip_fx.PLUGIN_DISTORTION)
            payload_length = len(default_payload or b"")
        return {
            "source": "BMD built-in Distortion token mapped into the verified ClipFX payload shape",
            "sha256": audio_clip_fx.DISTORTION_DEFAULT_PAYLOAD_SHA256,
            "payload_length": payload_length,
            "verification": {
                "db_readback_artifact": "/tmp/cutagent_fairlightfx_distortion_probe_20260619_hwfBQm/09_effect_list_after_distortion.json",
                "render_ab_artifact": "/tmp/cutagent_fairlightfx_distortion_probe_20260619_hwfBQm/12_distortion_vs_clean_diff.json",
                "cleanup_artifact": "/tmp/cutagent_fairlightfx_distortion_probe_20260619_hwfBQm/14_effect_list_after_cleanup.json",
            },
        }
    if spec["key"] == "multiband_compressor":
        payload_length = len(payload)
        if payload_length == 0:
            default_payload = audio_clip_fx.default_clip_fx_payload(audio_clip_fx.PLUGIN_MULTIBAND_COMPRESSOR)
            payload_length = len(default_payload or b"")
        return {
            "source": "BMD built-in Multiband Compressor token mapped into the verified ClipFX payload shape",
            "sha256": audio_clip_fx.MULTIBAND_COMPRESSOR_DEFAULT_PAYLOAD_SHA256,
            "payload_length": payload_length,
            "verification": {
                "db_readback_artifact": "/tmp/cutagent_fairlightfx_multiband_probe_20260619_224202/15_public_multiband_list_after_add.json",
                "render_ab_artifact": "/tmp/cutagent_fairlightfx_multiband_probe_20260619_224202/18_public_multiband_vs_clean_diff.json",
                "cleanup_artifact": "/tmp/cutagent_fairlightfx_multiband_probe_20260619_224202/20_public_multiband_list_after_remove.json",
            },
        }
    if spec["key"] == "dialogue_leveler":
        payload_length = len(payload)
        if payload_length == 0:
            default_payload = audio_clip_fx.default_clip_fx_payload(audio_clip_fx.PLUGIN_DIALOGUE_LEVELER)
            payload_length = len(default_payload or b"")
        return {
            "source": "BMD built-in Dialogue Leveler token mapped into the verified ClipFX payload shape",
            "sha256": audio_clip_fx.DIALOGUE_LEVELER_DEFAULT_PAYLOAD_SHA256,
            "payload_length": payload_length,
            "verification": {
                "db_readback_artifact": "/tmp/cutagent_fairlight_ai_payload_probe_20260619/17_public_dialogue_leveler_list_after_ai_seed.json",
                "render_ab_artifact": "/tmp/cutagent_fairlight_ai_payload_probe_20260619/20_public_dialogue_leveler_vs_clean_diff.json",
                "cleanup_artifact": "/tmp/cutagent_fairlight_ai_payload_probe_20260619/22_public_dialogue_leveler_list_after_remove.json",
            },
        }
    if spec["key"] == "music_remixer":
        payload_length = len(payload)
        if payload_length == 0:
            default_payload = audio_clip_fx.default_clip_fx_payload(audio_clip_fx.PLUGIN_MUSIC_REMIXER)
            payload_length = len(default_payload or b"")
        return {
            "source": "BMD built-in Music Remixer token mapped into the verified ClipFX payload shape",
            "sha256": audio_clip_fx.MUSIC_REMIXER_DEFAULT_PAYLOAD_SHA256,
            "payload_length": payload_length,
            "verification": {
                "db_readback_artifact": "/tmp/cutagent_music_remixer_probe_20260619/26_effect_list_after_public_seed_after_patch.json",
                "render_ab_artifact": "/tmp/cutagent_music_remixer_probe_20260619/29_public_music_remixer_seed_vs_clean_diff.json",
                "cleanup_artifact": "/tmp/cutagent_music_remixer_probe_20260619/31_effect_list_after_seed_cleanup.json",
            },
        }
    if spec["key"] == "dialogue_processor":
        payload_length = len(payload)
        if payload_length == 0:
            default_payload = audio_clip_fx.default_clip_fx_payload(audio_clip_fx.PLUGIN_DIALOGUE_PROCESSOR)
            payload_length = len(default_payload or b"")
        return {
            "source": "BMD built-in Dialogue Processor token mapped into the verified ClipFX payload shape",
            "sha256": audio_clip_fx.DIALOGUE_PROCESSOR_DEFAULT_PAYLOAD_SHA256,
            "payload_length": payload_length,
            "verification": {
                "db_readback_artifact": "/tmp/cutagent_fairlightfx_dialogue_processor_probe_20260619_225515/15_public_dialogue_processor_list_after_add.json",
                "render_ab_artifact": "/tmp/cutagent_fairlightfx_dialogue_processor_probe_20260619_225515/18_public_dialogue_processor_vs_clean_diff.json",
                "cleanup_artifact": "/tmp/cutagent_fairlightfx_dialogue_processor_probe_20260619_225515/20_public_dialogue_processor_list_after_remove.json",
            },
        }
    if spec["key"] == "noise_reduction":
        payload_length = len(payload)
        if payload_length == 0:
            default_payload = audio_clip_fx.default_clip_fx_payload(audio_clip_fx.PLUGIN_NOISE_REDUCTION)
            payload_length = len(default_payload or b"")
        return {
            "source": "BMD built-in Noise Reduction token mapped into the verified ClipFX payload shape",
            "sha256": audio_clip_fx.NOISE_REDUCTION_DEFAULT_PAYLOAD_SHA256,
            "payload_length": payload_length,
            "verification": {
                "db_readback_artifact": "/tmp/cutagent_fairlightfx_noise_reduction_probe_20260619_230531/20_public_noise_reduction_list_after_add.json",
                "render_ab_artifact": "/tmp/cutagent_fairlightfx_noise_reduction_probe_20260619_230531/23_public_noise_reduction_vs_clean_diff.json",
                "cleanup_artifact": "/tmp/cutagent_fairlightfx_noise_reduction_probe_20260619_230531/25_public_noise_reduction_list_after_remove.json",
            },
        }
    if spec["key"] == "flanger":
        payload_length = len(payload)
        if payload_length == 0:
            default_payload = audio_clip_fx.default_clip_fx_payload(audio_clip_fx.PLUGIN_FLANGER)
            payload_length = len(default_payload or b"")
        return {
            "source": "GUI-authored BMD Flanger clip-level FL::ClipFX payload",
            "sha256": audio_clip_fx.FLANGER_DEFAULT_PAYLOAD_SHA256,
            "payload_length": payload_length,
            "verification": {
                "gui_payload_artifact": "/tmp/cutagent_flanger_gui_probe_20260619_004643/09_flanger_gui_payload.json",
                "db_readback_artifact": "/tmp/cutagent_flanger_gui_probe_20260619_004643/07_effect_list_after_drag.json",
                "render_ab_artifact": "/tmp/cutagent_flanger_gui_probe_20260619_004643/13_flanger_vs_stretched_baseline_diff.json",
            },
        }
    if spec["key"] == "echo":
        payload_length = len(payload)
        if payload_length == 0:
            default_payload = audio_clip_fx.default_clip_fx_payload(audio_clip_fx.PLUGIN_ECHO)
            payload_length = len(default_payload or b"")
        return {
            "source": "GUI-authored BMD Echo clip-level FL::ClipFX payload",
            "sha256": audio_clip_fx.ECHO_DEFAULT_PAYLOAD_SHA256,
            "payload_length": payload_length,
            "verification": {
                "gui_payload_artifact": "/tmp/cutagent_echo_gui_probe_20260619_005522/09_echo_gui_payload.json",
                "db_readback_artifact": "/tmp/cutagent_echo_gui_probe_20260619_005522/07_effect_list_after_drag.json",
                "render_ab_artifact": "/tmp/cutagent_echo_gui_probe_20260619_005522/12_echo_vs_clean_stretched_diff.json",
            },
        }
    if spec["key"] == "delay":
        payload_length = len(payload)
        if payload_length == 0:
            default_payload = audio_clip_fx.default_clip_fx_payload(audio_clip_fx.PLUGIN_DELAY)
            payload_length = len(default_payload or b"")
        return {
            "source": "GUI-authored BMD Delay clip-level FL::ClipFX payload",
            "sha256": audio_clip_fx.DELAY_DEFAULT_PAYLOAD_SHA256,
            "payload_length": payload_length,
            "verification": {
                "gui_payload_artifact": "/tmp/cutagent_delay_gui_probe_20260619_0100/07_delay_gui_payload.json",
                "db_readback_artifact": "/tmp/cutagent_delay_gui_probe_20260619_0100/05_effect_list_after_drag.json",
                "render_ab_artifact": "/tmp/cutagent_delay_gui_probe_20260619_0100/11_delay_vs_clean_stretched_diff.json",
            },
        }
    if spec["key"] == "dehummer":
        payload_length = len(payload)
        if payload_length == 0:
            default_payload = audio_clip_fx.default_clip_fx_payload(audio_clip_fx.PLUGIN_DEHUMMER)
            payload_length = len(default_payload or b"")
        return {
            "source": "GUI-authored BMD De-Hummer clip-level FL::ClipFX payload",
            "sha256": audio_clip_fx.DEHUMMER_DEFAULT_PAYLOAD_SHA256,
            "payload_length": payload_length,
            "verification": {
                "gui_payload_artifact": "/tmp/cutagent_dehummer_gui_probe_20260619_0120/17_dehummer_gui_payload.json",
                "db_readback_artifact": "/tmp/cutagent_dehummer_gui_probe_20260619_0120/16_effect_list_after_dehummer_drag.json",
                "render_ab_artifact": "/tmp/cutagent_dehummer_gui_probe_20260619_0120/20_dehummer_gui_vs_clean_diff.json",
            },
        }
    if spec["key"] == "gain":
        payload_length = len(payload)
        if payload_length == 0:
            default_payload = audio_clip_fx.default_clip_fx_payload(audio_clip_fx.PLUGIN_GAIN)
            payload_length = len(default_payload or b"")
        return {
            "source": "GUI-authored BMD Gain clip-level FL::ClipFX payload",
            "sha256": audio_clip_fx.GAIN_DEFAULT_PAYLOAD_SHA256,
            "payload_length": payload_length,
            "verification": {
                "gui_payload_artifact": "/tmp/cutagent_gain_gui_probe_20260620_1014/04_gain_gui_payload.json",
                "db_readback_artifact": "/tmp/cutagent_gain_gui_probe_20260620_1014/03_effect_list_after_gain_drag.json",
                "public_gain_artifact": "/tmp/cutagent_gain_public_proof_20260620_1014/04_set_gain_zero.json",
                "public_gain_render_artifact": "/tmp/cutagent_gain_public_proof_20260620_1014/08_gain_zero_vs_clean_diff.json",
                "cleanup_artifact": "/tmp/cutagent_gain_public_proof_20260620_1014/10_effect_list_after_cleanup.json",
                "note": "Default insert is DB-valid; BMDGain::GAIN is separately public-command render-verified.",
            },
        }
    if spec["key"] == "vocal_channel":
        payload_length = len(payload)
        if payload_length == 0:
            default_payload = audio_clip_fx.default_clip_fx_payload(audio_clip_fx.PLUGIN_VOCAL_CHANNEL)
            payload_length = len(default_payload or b"")
        return {
            "source": "GUI-authored BMD Vocal Channel clip-level FL::ClipFX payload",
            "sha256": audio_clip_fx.VOCAL_CHANNEL_DEFAULT_PAYLOAD_SHA256,
            "payload_length": payload_length,
            "verification": {
                "gui_payload_artifact": "/tmp/cutagent_vocal_channel_gui_probe_20260620_1029/04_vocal_channel_gui_payload.json",
                "db_readback_artifact": "/tmp/cutagent_vocal_channel_gui_probe_20260620_1029/03_effect_list_after_drag.json",
                "render_ab_artifact": "/tmp/cutagent_vocal_channel_gui_probe_20260620_1029/07_vocal_channel_default_vs_clean_diff.json",
                "public_param_sweep_artifact": "/tmp/cutagent_vocal_channel_public_probe_20260620_1108/24_vocal_channel_param_sweep_diff.json",
                "public_comp_individual_artifact": "/tmp/cutagent_vocal_channel_public_probe_20260620_1108/37_vocal_channel_comp_individual_diff.json",
                "cleanup_artifact": "/tmp/cutagent_vocal_channel_public_probe_20260620_1108/39_effect_list_after_cleanup.json",
                "note": "Default insert is DB-valid but subtle; HPF_IN, HF_GAIN, and COMP_IN are separately public-command render-verified. COMP_GAIN alone rendered identically to default and is not whitelisted.",
            },
        }
    if spec["key"] == "limiter":
        payload_length = len(payload)
        if payload_length == 0:
            default_payload = audio_clip_fx.default_clip_fx_payload(audio_clip_fx.PLUGIN_LIMITER)
            payload_length = len(default_payload or b"")
        return {
            "source": "GUI-authored BMD Limiter clip-level FL::ClipFX payload",
            "sha256": audio_clip_fx.LIMITER_DEFAULT_PAYLOAD_SHA256,
            "payload_length": payload_length,
            "verification": {
                "gui_payload_artifact": "/tmp/cutagent_limiter_gui_probe_20260620/10_limiter_gui_payload.json",
                "db_readback_artifact": "/tmp/cutagent_limiter_gui_probe_20260620/09_effect_list_after_double_click.json",
                "render_ab_artifact": "/tmp/cutagent_limiter_gui_probe_20260620/17_limiter_default_vs_clean_diff.json",
                "public_param_sweep_artifact": "/tmp/cutagent_limiter_public_probe_20260620/06_limiter_param_sweep_diff.json",
                "cleanup_artifact": "/tmp/cutagent_limiter_public_probe_20260620/08_list_after_cleanup.json",
                "note": "Default insert is render-visible on the stereo channel-map fixture; INPUT_GAIN and THRESHOLD are public-command render-verified. SOFT=1.0 rendered identically to default and is not whitelisted.",
            },
        }
    if spec["key"] == "stereo_width":
        payload_length = len(payload)
        if payload_length == 0:
            default_payload = audio_clip_fx.default_clip_fx_payload(audio_clip_fx.PLUGIN_STEREO_WIDTH)
            payload_length = len(default_payload or b"")
        return {
            "source": "GUI-authored BMD Stereo Width clip-level FL::ClipFX payload",
            "sha256": audio_clip_fx.STEREO_WIDTH_DEFAULT_PAYLOAD_SHA256,
            "payload_length": payload_length,
            "verification": {
                "gui_payload_artifact": "/tmp/cutagent_stereo_width_gui_probe_20260619_0130/12_stereo_width_gui_payload.json",
                "db_readback_artifact": "/tmp/cutagent_stereo_width_gui_probe_20260619_0130/11_effect_list_after_drag.json",
                "render_ab_artifact": "/tmp/cutagent_stereo_width_gui_probe_20260619_0130/15_stereo_width_gui_vs_clean_diff.json",
                "note": "Default insert is DB-valid but subtle; WIDTH parameter promotion requires a separate public-command render proof.",
            },
        }
    if spec["key"] == "stereo_fixer":
        payload_length = len(payload)
        if payload_length == 0:
            default_payload = audio_clip_fx.default_clip_fx_payload(audio_clip_fx.PLUGIN_STEREO_FIXER)
            payload_length = len(default_payload or b"")
        return {
            "source": "GUI-authored BMD Stereo Fixer clip-level FL::ClipFX payload",
            "sha256": audio_clip_fx.STEREO_FIXER_DEFAULT_PAYLOAD_SHA256,
            "payload_length": payload_length,
            "verification": {
                "gui_payload_artifact": "/tmp/cutagent_stereo_fixer_gui_probe_20260620_0953/06_stereo_fixer_gui_payload.json",
                "db_readback_artifact": "/tmp/cutagent_stereo_fixer_gui_probe_20260620_0953/05_effect_list_after_stereo_fixer_drag_precise.json",
                "render_ab_artifact": "/tmp/cutagent_stereo_fixer_gui_probe_20260620_0953/09_stereo_fixer_vs_clean_diff.json",
                "public_left_gain_artifact": "/tmp/cutagent_stereo_fixer_public_proof_20260620_100225/04_set_left_gain_zero.json",
                "public_left_gain_render_artifact": "/tmp/cutagent_stereo_fixer_public_proof_20260620_100225/08_left_zero_vs_clean_diff.json",
                "public_right_gain_artifact": "/tmp/cutagent_stereo_fixer_public_proof_20260620_100225/12_set_right_gain_zero.json",
                "public_right_gain_render_artifact": "/tmp/cutagent_stereo_fixer_public_proof_20260620_100225/16_right_zero_vs_clean_diff.json",
                "cleanup_artifact": "/tmp/cutagent_stereo_fixer_public_proof_20260620_100225/18_effect_list_after_cleanup.json",
                "note": "Default insert is DB-valid but subtle; LEFT_GAIN and RIGHT_GAIN are separately public-command render-verified.",
            },
        }
    if spec["key"] == "soft_clipper":
        payload_length = len(payload)
        if payload_length == 0:
            default_payload = audio_clip_fx.default_clip_fx_payload(audio_clip_fx.PLUGIN_SOFT_CLIPPER)
            payload_length = len(default_payload or b"")
        return {
            "source": "GUI-authored BMD Soft Clipper clip-level FL::ClipFX payload",
            "sha256": audio_clip_fx.SOFT_CLIPPER_DEFAULT_PAYLOAD_SHA256,
            "payload_length": payload_length,
            "verification": {
                "gui_payload_artifact": "/tmp/cutagent_soft_clipper_gui_probe_20260620_0200/21_soft_clipper_gui_payload.json",
                "db_readback_artifact": "/tmp/cutagent_soft_clipper_gui_probe_20260620_0200/20_effect_list_after_soft_clipper_drag.json",
                "render_ab_artifact": "/tmp/cutagent_soft_clipper_gui_probe_20260620_0200/24_soft_clipper_gui_vs_clean_diff.json",
                "note": "Default insert is DB-valid but subtle; THRESHOLD parameter promotion requires a separate public-command render proof.",
            },
        }
    if spec["key"] == "pitch":
        payload_length = len(payload)
        if payload_length == 0:
            default_payload = audio_clip_fx.default_clip_fx_payload(audio_clip_fx.PLUGIN_PITCH)
            payload_length = len(default_payload or b"")
        return {
            "source": "GUI-authored BMD Pitch clip-level FL::ClipFX payload",
            "sha256": audio_clip_fx.PITCH_DEFAULT_PAYLOAD_SHA256,
            "payload_length": payload_length,
            "verification": {
                "gui_payload_artifact": "/tmp/cutagent_pitch_gui_probe_20260620_0225/08_pitch_gui_payload.json",
                "db_readback_artifact": "/tmp/cutagent_pitch_gui_probe_20260620_0225/07_effect_list_after_pitch_drag_fairlight.json",
                "note": "Default insert is neutral; COARSE parameter promotion requires a separate public-command render proof.",
            },
        }
    if spec["key"] == "modulation":
        payload_length = len(payload)
        if payload_length == 0:
            default_payload = audio_clip_fx.default_clip_fx_payload(audio_clip_fx.PLUGIN_MODULATION)
            payload_length = len(default_payload or b"")
        return {
            "source": "GUI-authored BMD Modulation clip-level FL::ClipFX payload",
            "sha256": audio_clip_fx.MODULATION_DEFAULT_PAYLOAD_SHA256,
            "payload_length": payload_length,
            "verification": {
                "gui_payload_artifact": "/tmp/cutagent_modulation_gui_probe_20260620_0250/05_modulation_gui_payload.json",
                "db_readback_artifact": "/tmp/cutagent_modulation_gui_probe_20260620_0250/04_effect_list_after_modulation_drag.json",
                "note": "Default insert is subtle; AM_DEPTH parameter promotion requires a separate public-command render proof.",
            },
        }
    if spec["key"] == "fairlight_eq":
        payload_length = len(payload)
        if payload_length == 0:
            default_payload = audio_clip_fx.default_clip_fx_payload(audio_clip_fx.PLUGIN_FAIRLIGHT_EQ)
            payload_length = len(default_payload or b"")
        return {
            "source": "GUI-authored BMD Fairlight EQ clip-level FL::ClipFX payload",
            "sha256": audio_clip_fx.FAIRLIGHT_EQ_DEFAULT_PAYLOAD_SHA256,
            "payload_length": payload_length,
            "verification": {
                "gui_payload_artifact": "/tmp/cutagent_fx_next_gui_probe_20260620/16_fairlight_eq_payload_extract.json",
                "db_readback_artifact": "/tmp/cutagent_fx_next_gui_probe_20260620/13_list_after_fairlight_eq_mouseup.json",
                "gui_window_artifact": "/tmp/cutagent_fx_next_gui_probe_20260620/14_fairlight_eq_window_confirm.png",
                "note": "Default insert opens the native Fairlight EQ clip window; BAND_GAIN_3 requires public-command render proof before broader EQ parameter promotion.",
            },
        }
    return {
        "source": "GUI-authored Fairlight FX payload",
        "sha256": audio_clip_fx.CHORUS_DEFAULT_PAYLOAD_SHA256,
        "payload_length": len(payload),
    }


def _sqlite_row_to_dict(cursor: sqlite3.Cursor, row: Any) -> dict[str, Any]:
    if hasattr(row, "keys"):
        return {key: row[key] for key in row.keys()}
    return {cursor.description[index][0]: value for index, value in enumerate(row)}


def _table_exists(cursor: sqlite3.Cursor, table_name: str) -> bool:
    row = cursor.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def _current_timeline_name(conn) -> str | None:
    timeline = getattr(conn, "timeline", None)
    if timeline and hasattr(timeline, "GetName"):
        try:
            return str(timeline.GetName() or "").strip() or None
        except Exception:
            return None
    return None


def _fetch_current_timeline_audio_clip_rows(cursor: sqlite3.Cursor, timeline_name: str | None) -> list[dict[str, Any]]:
    if timeline_name:
        rows = cursor.execute(
            """
            SELECT
                item.rowid AS db_rowid,
                item.Sm2TiItem_id,
                item.Name,
                item.Sm2TiTrack_id,
                item.Start,
                item.Duration,
                COALESCE(track_rel.DbIndex, track.rowid - 1) + 1 AS track_index
            FROM Sm2Timeline timeline
            JOIN Sm2TiTrack track
              ON track.Sequence = timeline.Sequence
             AND track.Type = 1
            LEFT JOIN Sm2SequenceContainer container
              ON container.Sm2Sequence_id = timeline.Sequence
            LEFT JOIN Sm2SequenceContainer_Sm2TiTrack track_rel
              ON track_rel.DbOwner = container.Sm2SequenceContainer_id
             AND track_rel.DbAssociate = track.Sm2TiTrack_id
             AND track_rel.DbPropertyName = 'AudioTrackVec'
            JOIN Sm2TiItem item
              ON item.Sm2TiTrack_id = track.Sm2TiTrack_id
             AND item.DbType = 'Sm2TiAudioClip'
            WHERE timeline.Name = ?
            ORDER BY COALESCE(track_rel.DbIndex, track.rowid), item.Start, item.rowid
            """,
            (timeline_name,),
        ).fetchall()
        if rows:
            return [_sqlite_row_to_dict(cursor, row) for row in rows]

        if _table_exists(cursor, "Sm2TiItem_Sm2TiTrack"):
            rel_rows = cursor.execute(
                """
                SELECT
                    item.rowid AS db_rowid,
                    item.Sm2TiItem_id,
                    item.Name,
                    item_rel.DbOwner AS Sm2TiTrack_id,
                    item.Start,
                    item.Duration,
                    COALESCE(track_rel.DbIndex, track.rowid - 1) + 1 AS track_index
                FROM Sm2Timeline timeline
                JOIN Sm2TiTrack track
                  ON track.Sequence = timeline.Sequence
                 AND track.Type = 1
                JOIN Sm2TiItem_Sm2TiTrack item_rel
                  ON item_rel.DbOwner = track.Sm2TiTrack_id
                 AND item_rel.DbPropertyName = 'Items'
                JOIN Sm2TiItem item
                  ON item.Sm2TiItem_id = item_rel.DbAssociate
                 AND item.DbType = 'Sm2TiAudioClip'
                LEFT JOIN Sm2SequenceContainer container
                  ON container.Sm2Sequence_id = timeline.Sequence
                LEFT JOIN Sm2SequenceContainer_Sm2TiTrack track_rel
                  ON track_rel.DbOwner = container.Sm2SequenceContainer_id
                 AND track_rel.DbAssociate = track.Sm2TiTrack_id
                 AND track_rel.DbPropertyName = 'AudioTrackVec'
                WHERE timeline.Name = ?
                ORDER BY COALESCE(track_rel.DbIndex, track.rowid), item_rel.DbIndex, item.rowid
                """,
                (timeline_name,),
            ).fetchall()
            if rel_rows:
                return [_sqlite_row_to_dict(cursor, row) for row in rel_rows]

        return []

    rows = cursor.execute(
        """
        SELECT
            rowid AS db_rowid,
            Sm2TiItem_id,
            Name,
            Sm2TiTrack_id,
            Start,
            Duration,
            NULL AS track_index
        FROM Sm2TiItem
        WHERE DbType = 'Sm2TiAudioClip'
        ORDER BY rowid
        """
    ).fetchall()
    return [_sqlite_row_to_dict(cursor, row) for row in rows]


def _resolve_fairlight_clip_fx_row(
    cursor: sqlite3.Cursor,
    *,
    conn,
    clip_selector: str | None,
    timeline_name: str | None = None,
    allow_live_resolution: bool = True,
) -> dict[str, Any]:
    target_timeline_name = timeline_name if timeline_name is not None else _current_timeline_name(conn)
    if clip_selector and allow_live_resolution:
        try:
            audio_ref = db_timeline_selection.resolve_audio_group(conn, clip_name=clip_selector).get("audio")
            if audio_ref is not None:
                row = db_timeline_rows.find_ti_item_row(
                    cursor,
                    item=audio_ref,
                    db_type="Sm2TiAudioClip",
                    timeline_name=target_timeline_name,
                )
                return {
                    "db_rowid": row.get("db_rowid"),
                    "Sm2TiItem_id": row.get("Sm2TiItem_id"),
                    "Name": row.get("Name"),
                    "Sm2TiTrack_id": row.get("Sm2TiTrack_id"),
                    "Start": row.get("Start"),
                    "Duration": row.get("Duration"),
                    "track_index": row.get("track_index"),
                }
        except Exception:
            pass

    rows = _fetch_current_timeline_audio_clip_rows(cursor, target_timeline_name)
    if not rows:
        raise ReadinessFailed(
            "No audio clip found for Fairlight clip effect parameter readback.",
            details={"timeline_name": target_timeline_name, "clip": clip_selector},
        )
    if not clip_selector:
        return rows[0]

    selector = str(clip_selector).strip()
    selector_key = selector.casefold()
    matches = [
        row
        for row in rows
        if str(row.get("Sm2TiItem_id") or "") == selector
        or str(row.get("Name") or "").strip().casefold() == selector_key
    ]
    if not matches:
        raise ValidationError(
            "Audio clip was not found in the current timeline DB rows.",
            details={
                "clip": clip_selector,
                "timeline_name": target_timeline_name,
                "available_audio_clips": [
                    {"clip_id": row.get("Sm2TiItem_id"), "name": row.get("Name"), "track_index": row.get("track_index")}
                    for row in rows[:20]
                ],
            },
            recoverability="not_applicable",
        )
    if len(matches) > 1:
        raise ValidationError(
            "Audio clip selector is ambiguous in the current timeline DB rows.",
            details={
                "clip": clip_selector,
                "timeline_name": target_timeline_name,
                "matches": [
                    {"clip_id": row.get("Sm2TiItem_id"), "name": row.get("Name"), "track_index": row.get("track_index")}
                    for row in matches
                ],
            },
            recoverability="not_applicable",
        )
    return matches[0]


def _clip_fx_available_plugins(state: Any | None) -> list[dict[str, Any]]:
    if not state:
        return []
    plugins = []
    for plugin in getattr(state, "plugins", []) or []:
        plugins.append(
            {
                "plugin_id": getattr(plugin, "plugin_id", None),
                "name": getattr(plugin, "name", None),
                "param_count": len(getattr(plugin, "params", []) or []),
            }
        )
    return plugins


def _find_clip_fx_plugin(state: Any | None, spec: dict[str, Any]) -> Any | None:
    if not state:
        return None
    wanted_id = str(spec["plugin_id"])
    wanted_key = _normalize_clip_fx_lookup_key(spec["name"])
    for plugin in getattr(state, "plugins", []) or []:
        if str(getattr(plugin, "plugin_id", "") or "") == wanted_id:
            return plugin
        if _normalize_clip_fx_lookup_key(getattr(plugin, "name", None)) == wanted_key:
            return plugin
    return None


def _clip_fx_param_payload(plugin: Any | None, param: str | None) -> tuple[dict[str, Any], str | None]:
    if plugin is None:
        return {}, "effect_not_present"
    params = {
        str(getattr(entry, "name", "") or ""): getattr(entry, "value", None)
        for entry in getattr(plugin, "params", []) or []
        if str(getattr(entry, "name", "") or "")
    }
    if not param:
        return params, None
    requested_key = _normalize_clip_fx_lookup_key(param)
    selected = {
        name: value
        for name, value in params.items()
        if _normalize_clip_fx_lookup_key(name) == requested_key
        or _normalize_clip_fx_lookup_key(name.rsplit("::", 1)[-1]) == requested_key
    }
    return selected, None if selected else "parameter_not_present"


def _cutagent_clip_fx_param_name(plugin: Any | None, param: str | None) -> str:
    if plugin is None:
        raise ReadinessFailed(
            "The requested clip-level Fairlight FX is not present on the target clip.",
            details={
                "precondition": "clip_fx_effect_present",
                "param": param,
            },
        )
    if not param or not str(param).strip():
        raise ValidationError(
            "Parameter name is required.",
            details={
                "required": ["--param"],
                "example": "cutagent fairlight effect set-param \"Voice Isolation\" --clip \"Dialogue A\" --param DRY_MIX --value 0.65 --json",
            },
            recoverability="not_applicable",
        )
    requested_key = _normalize_clip_fx_lookup_key(param)
    available = [
        str(getattr(entry, "name", "") or "")
        for entry in getattr(plugin, "params", []) or []
        if str(getattr(entry, "name", "") or "")
    ]
    matches = [
        name
        for name in available
        if _normalize_clip_fx_lookup_key(name) == requested_key
        or _normalize_clip_fx_lookup_key(name.rsplit("::", 1)[-1]) == requested_key
    ]
    if not matches:
        raise ReadinessFailed(
            "The requested clip-level Fairlight FX parameter is not present on the target clip.",
            details={
                "precondition": "clip_fx_parameter_present",
                "requested_param": param,
                "available_params": sorted(available),
            },
        )
    if len(matches) > 1:
        raise ValidationError(
            "Clip-level Fairlight FX parameter selector is ambiguous.",
            details={
                "requested_param": param,
                "matches": sorted(matches),
            },
            recoverability="not_applicable",
        )
    return matches[0]


def _clip_fx_verified_writable_params(spec: dict[str, Any]) -> list[str]:
    return [str(param) for param in spec.get("verified_writable_params") or []]


def _is_clip_fx_param_verified_writable(spec: dict[str, Any], resolved_param: str) -> bool:
    verified = _clip_fx_verified_writable_params(spec)
    if not verified:
        return True
    resolved_key = _normalize_clip_fx_lookup_key(resolved_param)
    return any(_normalize_clip_fx_lookup_key(param) == resolved_key for param in verified)


def _requested_clip_fx_param_matches_verified_writable(spec: dict[str, Any], requested_param: str | None) -> bool:
    verified = _clip_fx_verified_writable_params(spec)
    if not verified:
        return True
    requested_key = _normalize_clip_fx_lookup_key(requested_param)
    return any(
        _normalize_clip_fx_lookup_key(param) == requested_key
        or _normalize_clip_fx_lookup_key(param.rsplit("::", 1)[-1]) == requested_key
        for param in verified
    )


def _is_voice_isolation_dry_mix_param(param: str | None) -> bool:
    if not param:
        return False
    requested_key = _normalize_clip_fx_lookup_key(param)
    known = [
        "DRY_MIX",
        "BMDVoiceIsolationControl::DRY_MIX",
    ]
    return any(
        _normalize_clip_fx_lookup_key(name) == requested_key
        or _normalize_clip_fx_lookup_key(name.rsplit("::", 1)[-1]) == requested_key
        for name in known
    )


def _voice_isolation_dry_mix_to_amount(value: float) -> int:
    if not 0.0 <= value <= 1.0:
        raise ValidationError(
            "Voice Isolation DRY_MIX value must be between 0.0 and 1.0.",
            details={
                "param": "DRY_MIX",
                "value": value,
                "min": 0.0,
                "max": 1.0,
                "native_mapping": "TimelineItem.SetVoiceIsolationState({isEnabled: true, amount: round(value * 100)})",
            },
            recoverability="not_applicable",
        )
    return int(round(value * 100))


index_app = typer.Typer(help="Fairlight Index panel readback.")
app.add_typer(index_app, name="index")


def _validate_fairlight_index_limit(limit: int) -> int:
    if limit < 1 or limit > 1000:
        raise ValidationError(
            "Fairlight Index limit must be between 1 and 1000.",
            details={"limit": limit, "min": 1, "max": 1000},
            recoverability="not_applicable",
        )
    return limit


def _fairlight_index_clip_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "clip_id": row.get("Sm2TiItem_id"),
        "name": row.get("Name"),
        "track_index": row.get("track_index"),
        "start": row.get("Start"),
        "duration": row.get("Duration"),
        "track_id": row.get("Sm2TiTrack_id"),
        "db_rowid": row.get("db_rowid"),
    }


def _filter_fairlight_index_clip_rows(
    rows: list[dict[str, Any]],
    *,
    track: int | None,
    query: str | None,
    limit: int,
) -> tuple[list[dict[str, Any]], bool]:
    filtered = rows
    if track is not None:
        filtered = [row for row in filtered if row.get("track_index") in {track, str(track)}]
    normalized_query = str(query or "").strip().casefold()
    if normalized_query:
        filtered = [
            row
            for row in filtered
            if normalized_query in str(row.get("Name") or "").casefold()
            or normalized_query in str(row.get("Sm2TiItem_id") or "").casefold()
        ]
    truncated = len(filtered) > limit
    return [_fairlight_index_clip_row(row) for row in filtered[:limit]], truncated


def _fairlight_index_base_payload(*, action: str, timeline_name: str | None) -> dict[str, Any]:
    return {
        "action": action,
        "route": "db_workaround",
        "timeline": timeline_name,
        "source": "Fairlight Index readback",
        "db_readback": {
            "tracks_table": "Sm2TiTrack",
            "clips_table": "Sm2TiItem",
            "track_order_table": "Sm2SequenceContainer_Sm2TiTrack",
        },
    }


@index_app.command("tracks")
@handle_errors
def index_tracks():
    """List Fairlight Index audio tracks for the current timeline."""
    enforce_mutation_policy("fairlight.index_read", intended_engine="db_workaround", mutating=False)
    set_execution_engine("db_workaround")
    set_verification_status("not_requested")
    set_recoverability("not_applicable")
    if is_dry_run():
        output(
            {
                **_fairlight_index_base_payload(action="fairlight.index.tracks", timeline_name=None),
                "dry_run": True,
                "would_read": True,
                "target": "current_timeline_audio_tracks",
            },
            title="Fairlight Index Tracks Plan",
        )
        return

    conn = get_connection(require_timeline=True)
    timeline_name = _current_timeline_name(conn)
    tracks = fairlight_ops.list_audio_tracks(conn)
    cursor = conn.disk_db_cursor(allow_project_name_inference=True)
    clip_rows = _fetch_current_timeline_audio_clip_rows(cursor, timeline_name)
    clip_counts: dict[int, int] = {}
    for row in clip_rows:
        try:
            track_index = int(row.get("track_index") or 0)
        except (TypeError, ValueError):
            continue
        if track_index > 0:
            clip_counts[track_index] = clip_counts.get(track_index, 0) + 1
    indexed_tracks = [
        {
            **track,
            "clip_count": clip_counts.get(int(track.get("index") or 0), 0),
        }
        for track in tracks
    ]
    output(
        {
            **_fairlight_index_base_payload(action="fairlight.index.tracks", timeline_name=timeline_name),
            "count": len(indexed_tracks),
            "tracks": indexed_tracks,
        },
        title="Fairlight Index Tracks",
    )


@index_app.command("clips")
@handle_errors
def index_clips(
    track: int | None = typer.Option(None, "--track", "-t", min=1, help="Filter by audio track index"),
    query: str | None = typer.Option(None, "--query", "-q", help="Filter by clip name or DB id"),
    limit: int = typer.Option(200, "--limit", help="Maximum clips to return, 1-1000"),
):
    """List Fairlight Index audio clips for the current timeline."""
    limit = _validate_fairlight_index_limit(limit)
    enforce_mutation_policy("fairlight.index_read", intended_engine="db_workaround", mutating=False)
    set_execution_engine("db_workaround")
    set_verification_status("not_requested")
    set_recoverability("not_applicable")
    if is_dry_run():
        output(
            {
                **_fairlight_index_base_payload(action="fairlight.index.clips", timeline_name=None),
                "dry_run": True,
                "would_read": True,
                "target": "current_timeline_audio_clips",
                "filters": {"track": track, "query": query, "limit": limit},
            },
            title="Fairlight Index Clips Plan",
        )
        return

    conn = get_connection(require_timeline=True)
    timeline_name = _current_timeline_name(conn)
    cursor = conn.disk_db_cursor(allow_project_name_inference=True)
    rows = _fetch_current_timeline_audio_clip_rows(cursor, timeline_name)
    clips, truncated = _filter_fairlight_index_clip_rows(rows, track=track, query=query, limit=limit)
    output(
        {
            **_fairlight_index_base_payload(action="fairlight.index.clips", timeline_name=timeline_name),
            "filters": {"track": track, "query": query, "limit": limit},
            "count": len(clips),
            "truncated": truncated,
            "clips": clips,
        },
        title="Fairlight Index Clips",
    )


@index_app.command("markers")
@handle_errors
def index_markers():
    """List Fairlight Index timeline markers."""
    enforce_mutation_policy("fairlight.index_read", intended_engine="db_workaround", mutating=False)
    set_execution_engine("db_workaround")
    set_verification_status("not_requested")
    set_recoverability("not_applicable")
    if is_dry_run():
        output(
            {
                **_fairlight_index_base_payload(action="fairlight.index.markers", timeline_name=None),
                "dry_run": True,
                "would_read": True,
                "target": "current_timeline_markers",
            },
            title="Fairlight Index Markers Plan",
        )
        return

    conn = get_connection(require_timeline=True)
    timeline_name = _current_timeline_name(conn)
    markers = timeline_ops.list_markers(conn)
    output(
        {
            **_fairlight_index_base_payload(action="fairlight.index.markers", timeline_name=timeline_name),
            "route": "api_native",
            "count": len(markers),
            "markers": markers,
        },
        title="Fairlight Index Markers",
    )


@effect_app.command("catalog")
@handle_errors
def effect_catalog():
    """Read Fairlight Track FX, Macro FX, AutoMix, bus-processing, and BMD catalog tokens from the mixer model."""
    enforce_mutation_policy("fairlight.track_effect_catalog", intended_engine="db_workaround", mutating=False)
    set_execution_engine("db_workaround")
    set_verification_status("not_requested")
    set_recoverability("not_applicable")
    if is_dry_run():
        output(
            {
                "action": "fairlight.effect.catalog",
                "dry_run": True,
                "would_read": True,
                "route": "db_workaround",
                "target": "current_timeline_fairlight_mixer_model",
                "db_readback": {
                    "table": "Sm2Sequence",
                    "column": "FieldsBlob",
                    "payload": "FLStudioModelBA",
                    "storage": "length_prefixed_ascii_effect_catalog_tokens",
                },
                "read_scope": "track_fx_macro_automix_bus_bmd_catalog_only",
                "slot_readback_supported": False,
                "set_supported": False,
            },
            title="Fairlight Effect Catalog Plan",
        )
        return

    conn = get_connection(require_timeline=True)
    data = fairlight_ops.read_fairlight_effect_catalog_db(conn)
    output(data, title="Fairlight Effect Catalog")


@effect_app.command("plugin-catalog")
@handle_errors
def effect_plugin_catalog(
    limit: int = typer.Option(100, "--limit", min=1, help="Maximum plugin entries per provider to read"),
):
    """List available Fairlight AU/VST3 XML entries and built-in BMD Fairlight FX symbols."""
    enforce_mutation_policy("fairlight.plugin_catalog_read", intended_engine="workaround_setting", mutating=False)
    set_execution_engine("workaround_setting")
    set_verification_status("not_requested")
    set_recoverability("not_applicable")
    if is_dry_run():
        output(
            {
                "action": "fairlight.effect.plugin_catalog",
                "dry_run": True,
                "limit": int(limit),
                "runtime_read_called": False,
                "config_read_called": False,
                "route": "workaround_setting",
                "read_scope": "fairlight_effect_plugin_configuration_xml_and_bmd_builtin_audio_symbols",
                "related_resolvefx_route": _FAIRLIGHT_PLUGIN_SLOT_DB_BLOCKER_EVIDENCE["resolvefx_route_scope_evidence"],
                "slot_readback_supported": False,
                "slot_insert_supported": False,
                "slot_remove_supported": False,
                "param_routing_supported": False,
                "set_supported": False,
                "bmd_builtin_catalog_source": "libBMDAudioPlugins.dylib",
                "preflight_command": "cutagent fairlight effect plugin-catalog --json",
            },
            title="Fairlight Effect Plugin Catalog Plan",
        )
        return
    data = fairlight_ops.read_fairlight_effect_plugin_catalog_config(limit=limit)
    output(data, title="Fairlight Effect Plugin Catalog")


@effect_app.command("slot-scan")
@handle_errors
def effect_slot_scan(
    limit: int = typer.Option(100, "--limit", min=1, help="Maximum candidates per source bucket to return"),
):
    """Scan Project.db for Fairlight plugin slot candidate tokens and clip FX payloads."""
    enforce_mutation_policy("fairlight.plugin_slot_probe", intended_engine="db_workaround", mutating=False)
    set_execution_engine("db_workaround")
    set_verification_status("not_requested")
    set_recoverability("not_applicable")
    if is_dry_run():
        output(
            {
                "action": "fairlight.effect.slot_scan",
                "dry_run": True,
                "would_read": True,
                "runtime_read_called": False,
                "route": "db_workaround",
                "limit": int(limit),
                "read_scope": "mixer_model_bmd_tokens_and_clip_fx_payloads",
                "candidate_probe_supported": True,
                "track_bus_slot_state_supported": False,
                "slot_insert_supported": False,
                "slot_remove_supported": False,
                "slot_bypass_supported": False,
                "param_routing_supported": False,
                "set_supported": False,
                "preflight_command": "cutagent fairlight effect slot-scan --json",
            },
            title="Fairlight Effect Slot Scan Plan",
        )
        return

    conn = get_connection(require_timeline=True)
    data = fairlight_ops.read_fairlight_plugin_slot_probe_db(conn, limit=limit)
    output(data, title="Fairlight Effect Slot Scan")


def _fairlight_effect_preflight_command(
    command: str,
    *args: str,
    clip: str | None = None,
    param: str | None = None,
    value: float | None = None,
) -> str:
    parts: list[str] = ["cutagent", "fairlight", "effect", command, *[str(arg) for arg in args]]
    if clip is not None:
        parts.extend(["--clip", str(clip)])
    if param is not None:
        parts.extend(["--param", str(param)])
    if value is not None:
        parts.extend(["--value", str(value)])
    parts.append("--json")
    return " ".join(shlex.quote(part) for part in parts)


@effect_app.command("list")
@handle_errors
def effect_list(
    track: int | None = typer.Option(None, "--track", "-t", help="Audio track index to target"),
    clip: str | None = typer.Option(None, "--clip", help="Timeline clip name to target"),
    bus: str | None = typer.Option(None, "--bus", help="Bus name to target"),
):
    """List known clip-level Fairlight FX stored in Project.db."""
    if track is not None or bus is not None:
        set_capability_context("fairlight.plugin_routing", "unsupported")
        set_execution_engine("not_available")
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        raise CapabilityNegotiationFailed(
            "General Fairlight effect/plugin slot listing is not available through the DaVinci Resolve scripting API.",
            details={
                "capability_id": "fairlight.plugin_routing",
                "requested_track": track,
                "requested_clip": clip,
                "requested_bus": bus,
                "supported_db_readback": "clip-level FL::ClipFX entries through --clip or the first current-timeline audio clip",
                "required_native_api": [
                    "list Fairlight effects/plugins on a track or bus",
                    "enumerate arbitrary Fairlight plugin slots",
                    "inspect arbitrary Fairlight plugin chains",
                ],
                "available_db_route": "Known clip-level FL::ClipFX plugins in Sm2TiItem.FieldsBlob.",
                **_FAIRLIGHT_PLUGIN_SLOT_DB_BLOCKER_EVIDENCE,
                "workaround": (
                    "Use --clip to list known clip-level FL::ClipFX entries, or inspect arbitrary track/bus plugin "
                    "slots in DaVinci Resolve until a verified native or DB route exists."
                ),
            },
            recoverability="not_applicable",
        )

    enforce_mutation_policy("fairlight.clip_effect_list", intended_engine="db_workaround", mutating=False)
    set_execution_engine("db_workaround")
    set_verification_status("not_requested")
    set_recoverability("not_applicable")
    requested = {
        "clip": clip,
        "track": track,
        "bus": bus,
    }
    if is_dry_run():
        output(
            {
                "action": "fairlight.effect.list",
                "dry_run": True,
                "would_read": True,
                "runtime_read_called": False,
                "route": "db_workaround",
                "requested": requested,
                "target": {"kind": "audio_clip", "clip": clip, "default": "first_current_timeline_audio_clip" if not clip else None},
                "supported_effects": _fairlight_clip_fx_supported_effects(),
                "db_readback": {"table": "Sm2TiItem", "column": "FieldsBlob", "payload": "FL::ClipFX"},
                "read_scope": "known_clip_level_fl_clipfx_payload",
                "preflight_command": _fairlight_effect_preflight_command("list", clip=clip),
            },
            title="Fairlight Effect List Plan",
        )
        return

    from ..core.audio_clip_fx import read_clip_fx_from_db

    conn = get_connection(require_timeline=True)
    cursor = conn.disk_db_cursor()
    clip_row = _resolve_fairlight_clip_fx_row(cursor, conn=conn, clip_selector=clip)
    clip_id = str(clip_row.get("Sm2TiItem_id") or "")
    state = read_clip_fx_from_db(cursor, clip_id)
    plugins = _clip_fx_available_plugins(state)
    data = {
        "action": "fairlight.effect.list",
        "route": "db_workaround",
        "target": {
            "kind": "audio_clip",
            "clip": clip,
            "clip_id": clip_id,
            "name": clip_row.get("Name"),
            "track_index": clip_row.get("track_index"),
        },
        "found": bool(plugins),
        "plugins": plugins,
        "supported_effects": _fairlight_clip_fx_supported_effects(),
        "summary": state.to_dict() if state else {"plugins": []},
        "db_readback": {"table": "Sm2TiItem", "column": "FieldsBlob", "payload": "FL::ClipFX"},
    }
    output(data, title="Fairlight Effect List")


@effect_app.command("params")
@handle_errors
def effect_params(
    effect: str | None = typer.Argument(None, help="Fairlight effect/plugin name or slot identifier"),
    track: int | None = typer.Option(None, "--track", "-t", help="Audio track index to target"),
    clip: str | None = typer.Option(None, "--clip", help="Timeline clip name to target"),
    bus: str | None = typer.Option(None, "--bus", help="Bus name to target"),
    param: str | None = typer.Option(None, "--param", help="Specific parameter name to inspect"),
):
    """Inspect verified DB-backed Fairlight effect parameters."""
    if not effect:
        enforce_mutation_policy("fairlight.clip_effect_params", intended_engine="db_workaround", mutating=False)
        raise ValidationError(
            "Effect name or slot is required.",
            details={
                "example": "cutagent fairlight effect params \"Voice Isolation\" --clip \"Dialogue A\" --json",
                "required": ["effect"],
                "optional": ["--clip", "--param", "--track", "--bus"],
                "supported_clip_effects": _fairlight_clip_fx_supported_effects(),
                "supported_timeline_effects": ["Dialogue Processor", "Dynamics", "EQ"],
            },
        )

    spec = _resolve_fairlight_clip_fx_effect(effect)
    if clip or spec is not None:
        if track is not None or bus is not None or spec is None:
            set_capability_context("fairlight.plugin_routing", "unsupported")
            set_execution_engine("not_available")
            set_verification_status("not_requested")
            set_recoverability("not_applicable")
            raise CapabilityNegotiationFailed(
                "General Fairlight effect/plugin parameter routing is not available through the DaVinci Resolve scripting API.",
                details={
                    "capability_id": "fairlight.plugin_routing",
                    "requested_effect": effect,
                    "requested_param": param,
                    "requested_track": track,
                    "requested_clip": clip,
                    "requested_bus": bus,
                    "supported_db_readback": _fairlight_clip_fx_supported_effects(),
                    "required_native_api": [
                        "list Fairlight effects/plugins on a track, clip, or bus",
                        "inspect arbitrary Fairlight effect/plugin parameters",
                        "set arbitrary Fairlight effect/plugin parameters",
                    ],
                    "available_db_route": "Known clip-level FL::ClipFX parameters in Sm2TiItem.FieldsBlob.",
                    **_FAIRLIGHT_PLUGIN_SLOT_DB_BLOCKER_EVIDENCE,
                    "workaround": (
                        "Use a known clip-level effect such as Voice Isolation, Dialogue Leveler, or Music Remixer with --clip, "
                        "or inspect arbitrary Fairlight plugin slots in DaVinci Resolve until a verified native or DB route exists."
                    ),
                },
                recoverability="not_applicable",
            )

        enforce_mutation_policy("fairlight.clip_effect_params", intended_engine="db_workaround", mutating=False)
        set_execution_engine("db_workaround")
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        requested = {
            "effect": effect,
            "clip": clip,
            "param": param,
            "track": track,
            "bus": bus,
        }
        if is_dry_run():
            output(
                {
                    "action": "fairlight.effect.params",
                    "dry_run": True,
                    "would_read": True,
                    "runtime_read_called": False,
                    "route": "db_workaround",
                    "requested": requested,
                    "target": {"kind": "audio_clip", "clip": clip, "default": "first_current_timeline_audio_clip" if not clip else None},
                    "effect": {"key": spec["key"], "name": spec["name"], "plugin_id": spec["plugin_id"]},
                    "db_readback": {"table": "Sm2TiItem", "column": "FieldsBlob", "payload": "FL::ClipFX"},
                    "read_scope": "known_clip_level_fl_clipfx_params",
                    "preflight_command": _fairlight_effect_preflight_command("params", effect, clip=clip, param=param),
                },
                title="Fairlight Effect Params Plan",
            )
            return

        from ..core.audio_clip_fx import read_clip_fx_from_db

        conn = get_connection(require_timeline=True)
        cursor = conn.disk_db_cursor()
        clip_row = _resolve_fairlight_clip_fx_row(cursor, conn=conn, clip_selector=clip)
        clip_id = str(clip_row.get("Sm2TiItem_id") or "")
        state = read_clip_fx_from_db(cursor, clip_id)
        plugin = _find_clip_fx_plugin(state, spec)
        params, reason = _clip_fx_param_payload(plugin, param)
        found = bool(params) if param else plugin is not None
        data = {
            "action": "fairlight.effect.params",
            "route": "db_workaround",
            "target": {
                "kind": "audio_clip",
                "clip": clip,
                "clip_id": clip_id,
                "name": clip_row.get("Name"),
                "track_index": clip_row.get("track_index"),
            },
            "effect": {
                "requested": effect,
                "key": spec["key"],
                "name": spec["name"],
                "plugin_id": spec["plugin_id"],
            },
            "param": param,
            "found": found,
            "reason": reason,
            "params": params,
            "available_params": sorted(
                str(getattr(entry, "name", "") or "")
                for entry in getattr(plugin, "params", []) or []
                if str(getattr(entry, "name", "") or "")
            )
            if plugin is not None
            else [],
            "available_clip_fx_plugins": _clip_fx_available_plugins(state),
            "summary": state.to_dict() if state else {"plugins": []},
            "db_readback": {"table": "Sm2TiItem", "column": "FieldsBlob", "payload": "FL::ClipFX"},
        }
        output(data, title="Fairlight Effect Params")
        return

    canonical_effect = fairlight_ops._canonical_fairlight_effect_name(effect)
    capability_id = "fairlight.eq" if canonical_effect == "eq" else "fairlight.dynamics"
    enforce_mutation_policy(capability_id, intended_engine="db_workaround", mutating=False)
    if track is not None and int(track) < 1:
        raise ValidationError(
            "Audio track index is out of range.",
            details={"track": track, "min": 1},
            recoverability="not_applicable",
        )
    if track is not None or bus:
        set_capability_context("fairlight.plugin_routing", "unsupported")
        set_execution_engine("not_available")
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        raise CapabilityNegotiationFailed(
            "General Fairlight effect/plugin parameter routing is not available through the DaVinci Resolve scripting API.",
            details={
                "capability_id": "fairlight.plugin_routing",
                "requested_effect": effect,
                "requested_param": param,
                "requested_track": track,
                "requested_clip": clip,
                "requested_bus": bus,
                "supported_db_readback": ["current timeline built-in Fairlight processing", *_fairlight_clip_fx_supported_effects()],
                "required_native_api": [
                    "list Fairlight effects/plugins on a track, clip, or bus",
                    "inspect arbitrary Fairlight effect/plugin parameters",
                    "set arbitrary Fairlight effect/plugin parameters",
                ],
                "available_db_route": "Current timeline built-in Fairlight processing plus known clip-level FL::ClipFX parameters.",
                **_FAIRLIGHT_PLUGIN_SLOT_DB_BLOCKER_EVIDENCE,
                "workaround": (
                    "Use the current timeline built-in effect route without --track/--bus, or use a known clip-level "
                    "effect with --clip until arbitrary Fairlight plugin slot routing is mapped."
                ),
            },
            recoverability="not_applicable",
        )
    conn = get_connection(require_timeline=True)
    set_execution_engine("db_workaround")
    data = fairlight_ops.read_fairlight_effect_params_db(conn, effect_name=effect, param=param)
    output(data, title="Fairlight Effect Params")


@effect_app.command("set-param")
@handle_errors
def effect_set_param(
    effect: str | None = typer.Argument(None, help="Known clip-level Fairlight effect/plugin name"),
    track: int | None = typer.Option(None, "--track", "-t", help="Audio track index to target"),
    clip: str | None = typer.Option(None, "--clip", help="Timeline clip name to target"),
    bus: str | None = typer.Option(None, "--bus", help="Bus name to target"),
    param: str | None = typer.Option(None, "--param", help="Specific parameter name to set"),
    value: float | None = typer.Option(None, "--value", help="New parameter value"),
    create_if_missing: bool = typer.Option(
        False,
        "--create-if-missing/--no-create-if-missing",
        help="Insert the verified default clip FX payload before setting the parameter when the target clip has no FL::ClipFX payload",
    ),
):
    """Set a known clip-level Fairlight FX parameter through a verified native or DB route."""
    if not effect:
        enforce_mutation_policy("fairlight.clip_effect_param_write", intended_engine="db_workaround", mutating=False)
        raise ValidationError(
            "Effect name or slot is required.",
            details={
                "example": "cutagent fairlight effect set-param \"Voice Isolation\" --clip \"Dialogue A\" --param DRY_MIX --value 0.65 --json",
                "required": ["effect", "--param", "--value"],
                "optional": ["--clip"],
                "supported_effects": _fairlight_clip_fx_supported_effects(),
                "api_note": (
                    "Voice Isolation DRY_MIX maps to the native TimelineItem voice-isolation API. Other known "
                    "clip-level FL::ClipFX parameter writes require an existing DaVinci Resolve Disk DB payload; general "
                    "Fairlight plugin slots remain unsupported."
                ),
            },
            recoverability="not_applicable",
        )
    if not param or not str(param).strip():
        enforce_mutation_policy("fairlight.clip_effect_param_write", intended_engine="db_workaround", mutating=False)
        raise ValidationError(
            "Parameter name is required.",
            details={
                "example": "cutagent fairlight effect set-param \"Voice Isolation\" --clip \"Dialogue A\" --param DRY_MIX --value 0.65 --json",
                "required": ["--param"],
                "supported_effects": _fairlight_clip_fx_supported_effects(),
            },
            recoverability="not_applicable",
        )
    if value is None or not math.isfinite(float(value)):
        enforce_mutation_policy("fairlight.clip_effect_param_write", intended_engine="db_workaround", mutating=False)
        raise ValidationError(
            "Parameter value must be a finite number.",
            details={
                "example": "cutagent fairlight effect set-param \"Voice Isolation\" --clip \"Dialogue A\" --param DRY_MIX --value 0.65 --json",
                "required": ["--value"],
                "value": value,
            },
            recoverability="not_applicable",
        )

    spec = _resolve_fairlight_clip_fx_effect(effect)
    if track is not None or bus is not None or spec is None:
        set_capability_context("fairlight.plugin_routing", "unsupported")
        set_execution_engine("not_available")
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        raise CapabilityNegotiationFailed(
            "General Fairlight effect/plugin parameter routing is not available through the DaVinci Resolve scripting API.",
            details={
                "capability_id": "fairlight.plugin_routing",
                "requested_effect": effect,
                "requested_param": param,
                "requested_value": value,
                "requested_track": track,
                "requested_clip": clip,
                "requested_bus": bus,
                "supported_db_write": _fairlight_clip_fx_supported_effects(),
                "required_native_api": [
                    "list Fairlight effects/plugins on a track, clip, or bus",
                    "inspect arbitrary Fairlight effect/plugin parameters",
                    "set arbitrary Fairlight effect/plugin parameters",
                ],
                "available_db_route": "Known clip-level FL::ClipFX parameters in Sm2TiItem.FieldsBlob.",
                **_FAIRLIGHT_PLUGIN_SLOT_DB_BLOCKER_EVIDENCE,
                "workaround": (
                    "Use a known clip-level effect such as Voice Isolation, Dialogue Leveler, or Music Remixer with --clip, "
                    "or set arbitrary Fairlight plugin parameters in DaVinci Resolve until a verified native or DB route exists."
                ),
            },
            recoverability="not_applicable",
        )

    requested_value = float(value)
    if spec["key"] == "voice_isolation" and _is_voice_isolation_dry_mix_param(param):
        native_amount = _voice_isolation_dry_mix_to_amount(requested_value)
        enforce_mutation_policy("clip.voice_isolation", intended_engine="api_native", mutating=not is_dry_run())
        requested = {
            "effect": effect,
            "clip": clip,
            "param": param,
            "value": requested_value,
            "native_amount": native_amount,
            "track": track,
            "bus": bus,
        }
        native_api = {
            "write": "TimelineItem.SetVoiceIsolationState(state)",
            "readback": "TimelineItem.GetVoiceIsolationState()",
        }
        if is_dry_run():
            set_verification_status("not_requested")
            set_recoverability("not_applicable")
            output(
                mutation_payload(
                    action="fairlight.effect.set_param",
                    target={
                        "kind": "audio_clip",
                        "clip": clip,
                        "default": "first_current_timeline_audio_clip" if not clip else None,
                    },
                    changed=False,
                    dry_run=True,
                    runtime_read_called=False,
                    runtime_write_called=False,
                    route="api_native_timeline_item_voice_isolation",
                    requested=requested,
                    effect={"key": spec["key"], "name": spec["name"], "plugin_id": spec["plugin_id"]},
                    param={
                        "requested": param,
                        "resolved": "BMDVoiceIsolationControl::DRY_MIX",
                        "native_state_field": "amount",
                    },
                    native_api=native_api,
                    value_mapping={
                        "input_range": "0.0-1.0",
                        "native_range": "0-100",
                        "native_amount": native_amount,
                    },
                    read_scope="timeline_item_voice_isolation_state",
                    preflight_command=_fairlight_effect_preflight_command(
                        "set-param",
                        effect,
                        clip=clip,
                        param=param,
                        value=requested_value,
                    ),
                    verification_status="not_requested",
                    preconditions=[
                        "Current timeline must contain an audio clip or --clip must match a timeline audio item.",
                        "DaVinci Resolve runtime must expose TimelineItem.SetVoiceIsolationState and GetVoiceIsolationState.",
                    ],
                ),
                title="Fairlight Effect Set Param Plan",
            )
            return

        conn = get_connection(require_timeline=True)
        write_result = clip_ops.set_voice_isolation(conn, clip, enabled=True, amount=native_amount)
        readback = clip_ops.get_voice_isolation(conn, clip)
        expected = {"isEnabled": True, "amount": native_amount}
        if readback.get("isEnabled") is not True or int(readback.get("amount", -1)) != native_amount:
            raise APICallFailed(
                "TimelineItem.SetVoiceIsolationState readback did not match requested Fairlight effect parameter state.",
                details={
                    "clip": clip,
                    "effect": {"key": spec["key"], "name": spec["name"], "plugin_id": spec["plugin_id"]},
                    "param": {"requested": param, "resolved": "BMDVoiceIsolationControl::DRY_MIX"},
                    "requested": expected,
                    "readback": readback,
                },
            )
        set_verification_status("verified")
        data = {
            "action": "fairlight.effect.set_param",
            "route": "api_native_timeline_item_voice_isolation",
            "target": {"kind": "audio_clip", "clip": readback.get("clip") or write_result.get("clip") or clip},
            "effect": {"requested": effect, "key": spec["key"], "name": spec["name"], "plugin_id": spec["plugin_id"]},
            "param": {
                "requested": param,
                "resolved": "BMDVoiceIsolationControl::DRY_MIX",
                "native_state_field": "amount",
            },
            "value": requested_value,
            "value_mapping": {
                "input_range": "0.0-1.0",
                "native_range": "0-100",
                "native_amount": native_amount,
            },
            "requested": expected,
            "write_result": write_result,
            "readback": readback,
            "native_api": native_api,
        }
        output(data, title="Fairlight Effect Set Param")
        success(f"Set {spec['name']} {param} to {requested_value}.")
        return

    if spec.get("param_write_supported") is False:
        set_capability_context("fairlight.clip_effect_param_write", "partial")
        set_execution_engine("db_workaround")
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        raise CapabilityNegotiationFailed(
            "Fairlight clip FX parameter write is not verified for this effect.",
            details={
                "capability_id": "fairlight.clip_effect_param_write",
                "requested_effect": effect,
                "requested_param": param,
                "requested_value": requested_value,
                "requested_clip": clip,
                "effect": {
                    "key": spec["key"],
                    "name": spec["name"],
                    "plugin_id": spec["plugin_id"],
                },
                "supported_write_scope": [
                    "Voice Isolation DRY_MIX through TimelineItem.SetVoiceIsolationState",
                    "Known pre-existing FL::ClipFX payload parameters for verified writable payloads such as Chorus",
                ],
                "supported_readback": (
                    "This effect can be inserted/removed as a verified default clip-level FL::ClipFX payload and "
                    "listed/read with `fairlight effect list/params --clip`, but its individual parameter controls "
                    "have not yet been mapped to render-verified native behavior."
                ),
                "evidence": _fairlight_clip_fx_fixture_info(spec, b""),
                "workaround": "Apply the default effect with `fairlight effect add`, or adjust effect parameters in DaVinci Resolve.",
            },
            recoverability="not_applicable",
        )

    enforce_mutation_policy("fairlight.clip_effect_param_write", intended_engine="db_workaround", mutating=not is_dry_run())
    requested = {
        "effect": effect,
        "clip": clip,
        "param": param,
        "value": requested_value,
        "track": track,
        "bus": bus,
        "create_if_missing": bool(create_if_missing),
    }
    preflight_command = _fairlight_effect_preflight_command(
        "set-param",
        effect,
        clip=clip,
        param=param,
        value=requested_value,
    )
    if create_if_missing:
        preflight_command = preflight_command.replace(" --json", " --create-if-missing --json")
    if not _requested_clip_fx_param_matches_verified_writable(spec, param):
        set_capability_context("fairlight.clip_effect_param_write", "partial")
        set_execution_engine("db_workaround")
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        raise CapabilityNegotiationFailed(
            "Fairlight clip FX parameter write is not render-verified for this parameter.",
            details={
                "capability_id": "fairlight.clip_effect_param_write",
                "requested_effect": effect,
                "requested_param": param,
                "requested_value": requested_value,
                "requested_clip": clip,
                "effect": {"key": spec["key"], "name": spec["name"], "plugin_id": spec["plugin_id"]},
                "verified_writable_params": _clip_fx_verified_writable_params(spec),
                "workaround": "Use a render-verified parameter for this effect, or adjust the parameter in DaVinci Resolve.",
            },
            recoverability="not_applicable",
        )
    if is_dry_run():
        set_execution_engine("db_workaround")
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            mutation_payload(
                action="fairlight.effect.set_param",
                target={"kind": "audio_clip", "clip": clip, "default": "first_current_timeline_audio_clip" if not clip else None},
                changed=False,
                dry_run=True,
                runtime_read_called=False,
                runtime_write_called=False,
                route="db_workaround",
                requested=requested,
                effect={"key": spec["key"], "name": spec["name"], "plugin_id": spec["plugin_id"]},
                db_write={"table": "Sm2TiItem", "column": "FieldsBlob", "payload": "FL::ClipFX"},
                read_scope="known_clip_level_fl_clipfx_param_write",
                preflight_command=preflight_command,
                create_if_missing=bool(create_if_missing),
                verification_status="not_requested",
                preconditions=[
                    (
                        "Target clip may be missing FL::ClipFX; a verified default payload will be inserted first."
                        if create_if_missing
                        else "Target clip must already contain the requested FL::ClipFX payload."
                    ),
                    (
                        "If the target already contains FL::ClipFX, it must be the requested effect payload."
                        if create_if_missing
                        else "Parameter must be present in that clip-level effect payload."
                    ),
                    "Parameter must be present in that clip-level effect payload.",
                ],
            ),
            title="Fairlight Effect Set Param Plan",
        )
        return

    from ..core import audio_clip_fx

    conn = get_connection(require_timeline=True)
    target_timeline_name = _current_timeline_name(conn)

    def _writer(_db_conn, cursor, _session):
        clip_row = _resolve_fairlight_clip_fx_row(
            cursor,
            conn=conn,
            clip_selector=clip,
            timeline_name=target_timeline_name,
            allow_live_resolution=False,
        )
        clip_id = str(clip_row.get("Sm2TiItem_id") or "")
        state = audio_clip_fx.read_clip_fx_from_db(cursor, clip_id)
        plugin = _find_clip_fx_plugin(state, spec)
        created_clip_fx = False
        if not state or not state.raw_payload or plugin is None:
            if create_if_missing:
                if state and state.raw_payload:
                    set_verification_status("not_requested")
                    raise ReadinessFailed(
                        "The target clip already contains a different or unrecognized clip-level Fairlight FX payload.",
                        details={
                            "clip_id": clip_id,
                            "clip": clip_row.get("Name"),
                            "effect": {"key": spec["key"], "name": spec["name"], "plugin_id": spec["plugin_id"]},
                            "precondition": "clip_fx_payload_absent_or_matching",
                            "available_clip_fx_plugins": _clip_fx_available_plugins(state),
                            "raw_clip_fx_payload_present": True,
                            "workaround": "Remove the existing clip FX payload first, or set parameters on the existing effect.",
                        },
                    )
                default_payload = audio_clip_fx.default_clip_fx_payload(spec["plugin_id"])
                if not default_payload:
                    set_verification_status("not_requested")
                    raise ReadinessFailed(
                        "The requested Fairlight FX does not have a verified default payload for create-if-missing.",
                        details={
                            "clip_id": clip_id,
                            "clip": clip_row.get("Name"),
                            "effect": {"key": spec["key"], "name": spec["name"], "plugin_id": spec["plugin_id"]},
                            "precondition": "verified_default_clip_fx_payload",
                        },
                    )
                state = audio_clip_fx.parse_clip_fx(default_payload)
                plugin = _find_clip_fx_plugin(state, spec)
                created_clip_fx = True
                if plugin is None:
                    raise APICallFailed(
                        "The verified default Fairlight FX payload did not parse as the requested effect.",
                        details={
                            "clip_id": clip_id,
                            "effect": {"key": spec["key"], "name": spec["name"], "plugin_id": spec["plugin_id"]},
                        },
                    )
            else:
                set_verification_status("not_requested")
                raise ReadinessFailed(
                    "The requested clip-level Fairlight FX is not present on the target clip.",
                    details={
                        "clip_id": clip_id,
                        "clip": clip_row.get("Name"),
                        "effect": {"key": spec["key"], "name": spec["name"], "plugin_id": spec["plugin_id"]},
                        "precondition": "clip_fx_effect_present",
                        "available_clip_fx_plugins": _clip_fx_available_plugins(state),
                        "supported_create_if_missing_command": _fairlight_effect_preflight_command(
                            "set-param",
                            effect,
                            clip=clip,
                            param=param,
                            value=requested_value,
                        ).replace(" --json", " --create-if-missing --json"),
                    },
                )
        resolved_param = _cutagent_clip_fx_param_name(plugin, param)
        if not _is_clip_fx_param_verified_writable(spec, resolved_param):
            set_verification_status("not_requested")
            raise ReadinessFailed(
                "The requested clip-level Fairlight FX parameter is not yet render-verified for DB writes.",
                details={
                    "clip_id": clip_id,
                    "clip": clip_row.get("Name"),
                    "effect": {"key": spec["key"], "name": spec["name"], "plugin_id": spec["plugin_id"]},
                    "requested_param": param,
                    "resolved_param": resolved_param,
                    "precondition": "clip_fx_parameter_render_verified",
                    "verified_writable_params": _clip_fx_verified_writable_params(spec),
                    "workaround": "Use a render-verified parameter for this effect, or adjust the parameter in DaVinci Resolve.",
                },
            )
        try:
            modified = audio_clip_fx.set_param_in_payload(state.raw_payload, resolved_param, requested_value)
        except ValueError as exc:
            set_verification_status("not_requested")
            raise ReadinessFailed(
                "The requested clip-level Fairlight FX parameter could not be written in the target payload.",
                details={
                    "clip_id": clip_id,
                    "clip": clip_row.get("Name"),
                    "effect": {"key": spec["key"], "name": spec["name"], "plugin_id": spec["plugin_id"]},
                    "requested_param": param,
                    "resolved_param": resolved_param,
                    "precondition": "clip_fx_parameter_writable",
                    "missing_parameter": str(exc),
                },
            ) from exc
        original_row = cursor.execute(
            "SELECT FieldsBlob FROM Sm2TiItem WHERE Sm2TiItem_id = ?",
            (clip_id,),
        ).fetchone()
        original_fieldsblob = original_row["FieldsBlob"] if original_row and original_row["FieldsBlob"] else b""
        if created_clip_fx:
            new_fieldsblob = audio_clip_fx.insert_clip_fx_into_fieldsblob(original_fieldsblob, modified)
        else:
            new_fieldsblob = audio_clip_fx.write_clip_fx_to_fieldsblob(original_fieldsblob, modified)
        cursor.execute(
            "UPDATE Sm2TiItem SET FieldsBlob = ? WHERE Sm2TiItem_id = ?",
            (new_fieldsblob, clip_id),
        )
        return {
            "action": "fairlight.effect.set_param",
            "route": "db_workaround",
            "target": {
                "kind": "audio_clip",
                "clip": clip,
                "clip_id": clip_id,
                "name": clip_row.get("Name"),
                "track_index": clip_row.get("track_index"),
                "timeline_name": target_timeline_name,
            },
            "effect": {
                "requested": effect,
                "key": spec["key"],
                "name": spec["name"],
                "plugin_id": spec["plugin_id"],
            },
            "param": {"requested": param, "resolved": resolved_param},
            "value": requested_value,
            "created_clip_fx": created_clip_fx,
            "create_if_missing": bool(create_if_missing),
            "db_write": {"table": "Sm2TiItem", "column": "FieldsBlob", "payload": "FL::ClipFX"},
        }

    def _verifier(_fresh_conn, mutation_result, session):
        return _verify_clip_fx_params(
            project_db_path=session.project_db_path,
            clip_id=mutation_result["target"]["clip_id"],
            plugin_id=spec["plugin_id"],
            expected_params={mutation_result["param"]["resolved"]: requested_value},
            feature=spec["key"],
        )

    data = db_session.execute_sqlite_disk_db_mutation(
        conn,
        context="Fairlight clip FX parameter DB write",
        writer=_writer,
        verifier=_verifier,
        allow_project_name_inference=True,
    )
    output(data, title="Fairlight Effect Set Param")
    success(f"Set {spec['name']} {param} to {requested_value}.")


automation_app = typer.Typer(help="Fairlight automation operations.")
app.add_typer(automation_app, name="automation")

_AVAILABLE_NATIVE_FAIRLIGHT_API = [
    "Resolve.GetFairlightPresets()",
    "Timeline.GetTrackCount('audio')",
    "Timeline.GetTrackName('audio', index)",
    "Timeline.GetTrackSubType('audio', index)",
    "Timeline.AddTrack('audio', ...)",
    "Timeline.DeleteTrack('audio', index)",
    "Timeline.SetTrackName('audio', index, name)",
    "Timeline.SetTrackEnable('audio', index, enabled)",
    "Timeline.SetTrackLock('audio', index, locked)",
    "Timeline.GetVoiceIsolationState(trackIndex)",
    "Timeline.SetVoiceIsolationState(trackIndex, state)",
    "TimelineItem.GetVoiceIsolationState()",
    "TimelineItem.SetVoiceIsolationState(state)",
    "TimelineItem.GetSourceAudioChannelMapping()",
    "MediaPoolItem.GetAudioMapping()",
    "Project.InsertAudioToCurrentTrackAtPlayhead(path, startOffsetInSamples, durationInSamples)",
    "Project.ApplyFairlightPresetToCurrentTimeline(name)",
]


def _raise_fairlight_native_unavailable(
    *,
    capability_id: str,
    workflow: str,
    requested: dict[str, Any] | None = None,
    required_native_api: list[str],
    workaround: str,
    api_note: str,
    extra_details: dict[str, Any] | None = None,
):
    # Residual unsupported scopes can live under a broader supported capability
    # family; return the scoped blocker evidence instead of failing early on the
    # family's registered engine.
    feature_graph = get_capabilities().get("feature_graph", {})
    capability_meta = feature_graph.get(capability_id, {}) if capability_id else {}
    set_capability_context(capability_id, capability_meta.get("status", "unknown"))
    set_execution_engine("not_available")
    set_recoverability("not_applicable")
    set_verification_status("not_requested")
    raise CapabilityNegotiationFailed(
        f"{workflow} is not available through the DaVinci Resolve scripting API.",
        details={
            "capability_id": capability_id,
            "requested": requested or {},
            "required_native_api": required_native_api,
            "available_native_fairlight_api": _AVAILABLE_NATIVE_FAIRLIGHT_API,
            "api_note": api_note,
            "workaround": workaround,
            **(extra_details or {}),
        },
        recoverability="not_applicable",
    )


mixer_app = typer.Typer(help="Fairlight mixer fader, pan, and metering operations.")
app.add_typer(mixer_app, name="mixer")


def _raise_unmapped_fairlight_bus_readback(bus: str | None) -> None:
    set_capability_context("fairlight.bus_routing", "unsupported")
    set_execution_engine("not_available")
    set_verification_status("not_requested")
    set_recoverability("manual")
    raise CapabilityNegotiationFailed(
        "Only main-output sequence gain context is currently mapped for Fairlight bus/main mixer readback.",
        details={
            "capability_id": "fairlight.bus_routing",
            "requested_bus": bus,
            "supported_read_bus_selectors": ["Main", "Main 1"],
            "unsupported_scope": "non_main_bus_fader_readback",
            "reason": (
                "Non-main bus/FlexBus fader storage is not safely mapped in the "
                "DaVinci Resolve Disk DB route."
            ),
            **_FAIRLIGHT_BUS_ROUTING_DB_BLOCKER_EVIDENCE,
        },
    )


def _fairlight_main_bus_mixer_read_payload(bus_level: dict[str, Any]) -> dict[str, Any]:
    context = dict(bus_level.get("sequence_output_gain_context") or {})
    sequence_output_gain_set_supported = bool(bus_level.get("sequence_output_gain_set_supported"))
    verified_fader_set_supported = bool(bus_level.get("verified_fader_set_supported"))
    return {
        "action": "fairlight.mixer.read",
        "timeline_name": bus_level.get("timeline_name"),
        "timeline_sequence": bus_level.get("timeline_sequence"),
        "target": {"kind": "main_output", "bus": bus_level.get("bus")},
        "mixer": {
            "fader": {
                "output_audio_gain": context.get("output_audio_gain"),
                "num_output_audio_channels": context.get("num_output_audio_channels"),
                "sequence_output_gain_context": context,
                "route": "db_workaround",
                "db_table": "Sm2Sequence",
                "db_field": "OutputAudioGain",
                "read_scope": "sequence_output_gain_context_only",
                "verified_fader_read_supported": False,
                "sequence_output_gain_set_supported": sequence_output_gain_set_supported,
                "verified_fader_set_supported": verified_fader_set_supported,
                "set_supported": sequence_output_gain_set_supported,
                "set_scope": bus_level.get("set_scope"),
                "set_blocker": bus_level.get("set_blocker"),
            },
            "pan": {
                "read_supported": False,
                "set_supported": False,
                "unsupported_scope": "main_output_pan_unmapped",
            },
        },
        "bus_readback": bus_level.get("bus_readback") or {},
        "route": "db_workaround",
        "db_table": "Sm2Sequence",
        "db_field": "OutputAudioGain",
        "read_scope": "sequence_output_gain_context_only",
        "read_consistency": bus_level.get("read_consistency"),
        "project_db_path": bus_level.get("project_db_path"),
        "sequence_output_gain_read_supported": True,
        "verified_fader_read_supported": False,
        "sequence_output_gain_set_supported": sequence_output_gain_set_supported,
        "verified_fader_set_supported": verified_fader_set_supported,
        "set_supported": sequence_output_gain_set_supported,
        "set_scope": bus_level.get("set_scope"),
    }


def _fairlight_main_bus_fader_read_payload(bus_level: dict[str, Any]) -> dict[str, Any]:
    context = dict(bus_level.get("sequence_output_gain_context") or {})
    sequence_output_gain_set_supported = bool(bus_level.get("sequence_output_gain_set_supported"))
    verified_fader_set_supported = bool(bus_level.get("verified_fader_set_supported"))
    return {
        "action": "fairlight.mixer.fader.read",
        "timeline_name": bus_level.get("timeline_name"),
        "timeline_sequence": bus_level.get("timeline_sequence"),
        "bus": bus_level.get("bus"),
        "sequence_output_gain_context": context,
        "output_audio_gain": context.get("output_audio_gain"),
        "num_output_audio_channels": context.get("num_output_audio_channels"),
        "route": "db_workaround",
        "db_table": "Sm2Sequence",
        "db_field": "OutputAudioGain",
        "read_scope": "sequence_output_gain_context_only",
        "read_consistency": bus_level.get("read_consistency"),
        "project_db_path": bus_level.get("project_db_path"),
        "sequence_output_gain_read_supported": True,
        "verified_fader_read_supported": False,
        "sequence_output_gain_set_supported": sequence_output_gain_set_supported,
        "verified_fader_set_supported": verified_fader_set_supported,
        "set_supported": sequence_output_gain_set_supported,
        "set_scope": bus_level.get("set_scope"),
        "set_blocker": bus_level.get("set_blocker"),
    }


def _fairlight_main_bus_fader_set_payload(data: dict[str, Any]) -> dict[str, Any]:
    return mutation_payload(
        action="fairlight.mixer.fader",
        target={"kind": "main_output_gain_context", "bus": data.get("bus")},
        changed=bool(data.get("changed")),
        runtime_write_called=True,
        level_db=data.get("level_db"),
        output_audio_gain=data.get("output_audio_gain"),
        previous_output_audio_gain=data.get("previous_output_audio_gain"),
        timeline_name=data.get("timeline_name"),
        timeline_sequence=data.get("timeline_sequence"),
        route=data.get("route"),
        db_table=data.get("db_table"),
        db_field=data.get("db_field"),
        storage=data.get("storage"),
        set_scope=data.get("set_scope"),
        sequence_output_gain_set_supported=bool(data.get("sequence_output_gain_set_supported")),
        verified_fader_set_supported=bool(data.get("verified_fader_set_supported")),
        verified_fader_read_supported=False,
        verification=data.get("verification"),
        verification_status=(data.get("verification") or {}).get("status"),
        project_db_path=data.get("project_db_path"),
        backup_path=data.get("backup_path"),
        steps=data.get("steps"),
        delegated_action="fairlight.bus.level",
        message="Updated Fairlight main-output sequence gain context.",
    )


_FAIRLIGHT_3D_PANNER_DB_BLOCKER_EVIDENCE = {
    "available_db_routes": [
        {
            "command": "cutagent fairlight mixer pan --track <track> --json",
            "scope": "mapped audio-track pan lane readback",
            "db_blob": "Sm2Sequence.FieldsBlob.FLStudioModelBA",
            "storage": "channel_lane_pan_int32_x10",
        },
        {
            "command": "cutagent fairlight mixer pan --track <mono-track> --pan <value> --json",
            "scope": "verified mono audio-track 2D pan write only",
            "verified_set_scope": "mono_track_2d_pan",
            "db_blob": "Sm2Sequence.FieldsBlob.FLStudioModelBA",
        },
        {
            "command": "cutagent fairlight mixer pan --track <stereo-track> --pan <value> --json",
            "scope": "verified stereo audio-track Left / Right write",
            "verified_set_scope": "stereo_track_left_right",
            "db_blob": "Sm2Sequence.FieldsBlob.FLStudioModelBA",
            "storage": "second_consecutive_parameter_4_record_int32_x10",
        },
    ],
    "panner_model_evidence": {
        "mono_track_2d_pan_set_supported": True,
        "stereo_track_pan_set_supported": True,
        "surround_track_pan_set_supported": False,
        "adaptive_track_pan_set_supported": False,
        "panner_3d_angle_supported": False,
        "panner_3d_spread_supported": False,
        "render_channel_mapping_verified": True,
        "stereo_render_negative_evidence": {
            "runtime": "DaVinci Resolve 21.0.0.48 Free",
            "timeline": "CUTAGENT_STEREO_PAN_RENDER_PROBE_184651",
            "render_analysis_artifact": "/tmp/cutagent_mixer_stereo_pan_render_ch/09_render_channel_analysis.json",
            "experimental_read_artifact": "/tmp/cutagent_mixer_stereo_pan_render_ch/07_pan_read_after_experimental_left.json",
            "experimental_raw_values": [-1000, -1000],
            "db_lane_readback_verified": True,
            "render_visible": False,
            "result": "Historical negative changed the input-channel anchor record, not the subsequently decoded track-level Left / Right record.",
        },
        "stereo_left_right_positive_evidence": fairlight_ops.FAIRLIGHT_MIXER_STEREO_PAN_WRITE_BLOCKER_EVIDENCE[
            "resolve_21_stereo_left_right_evidence"
        ],
    },
    "native_probe_evidence": _FAIRLIGHT_PANNER_NATIVE_PROBE_EVIDENCE,
    "db_schema_evidence": {
        "source": "local DaVinci Resolve 20 Free Project.db schema probes",
        "sampled_project_db_count": 5,
        "read_scope": "negative_stereo_surround_3d_panner_schema_probe",
        "verified_mono_2d_storage": [
            "Sm2Sequence.FieldsBlob.FLStudioModelBA channel_lane_pan_int32_x10",
        ],
        "candidate_blob_fields_seen": [
            "Sm2Sequence.FieldsBlob",
            "Sm2TiTrack.AudioMixerBA",
            "Sm2TiTrack.FieldsBlob",
            "Sm2TiItem.FieldsBlob",
        ],
        "clip_asset_pan_columns_seen_but_not_track_panner_state": [
            "FLAssetBaseClip.ed_pan0",
            "FLAssetBaseClip.ed_pan1",
            "FLAssetBaseClip.ed_panin",
        ],
        "unrelated_setup_panel_columns_seen": [
            "SM_Setup.RefPan",
            "SM_PanelSetup.FieldsBlob",
            "SM_PanelSensitivity.FieldsBlob",
        ],
        "panner_3d_named_table_found_in_samples": False,
        "pan_angle_spread_divergence_columns_found_in_samples": False,
        "stereo_surround_adaptive_write_schema_found_in_samples": False,
        "rendered_channel_mapping_readback_found_in_samples": False,
        "audio_mixer_blob_panner_model_verified": False,
        "track_fields_blob_panner_model_verified": False,
    },
    "db_blocker_note": (
        "The DB route maps channel-lane 2D pan values and verifies writes only for mono audio tracks. "
        "Stereo Left / Right uses the verified second consecutive parameter-4 record. Surround, adaptive, "
        "and 3D panner angle/spread semantics require separate native, DB, GUI-readback, or rendered-channel "
        "mapping before they can be marked supported."
    ),
}
