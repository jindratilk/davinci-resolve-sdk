"""Fairlight mixer, automation, recording, and ADR commands."""

from __future__ import annotations

@mixer_app.command("read")
@handle_errors
def mixer_read(
    track: int | None = typer.Option(None, "--track", "-t", min=1, help="Audio track index"),
    bus: str | None = typer.Option(None, "--bus", help="Bus/main output name"),
):
    """Read a Fairlight audio-track or main-output mixer context from the Disk DB."""
    if bus is not None:
        if track is not None:
            raise ValidationError(
                "Fairlight mixer read accepts one target selector: use --track or --bus, not both.",
                details={"track": track, "bus": bus, "supported_targets": ["audio_track", "main_output"]},
                recoverability="not_applicable",
            )
        if not fairlight_ops.normalize_fairlight_main_output_selector(bus):
            _raise_unmapped_fairlight_bus_readback(bus)
        enforce_mutation_policy("fairlight.bus_read", intended_engine="db_workaround", mutating=False)
        set_execution_engine("db_workaround")
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        if is_dry_run():
            output(
                {
                    "action": "fairlight.mixer.read",
                    "dry_run": True,
                    "target": {"kind": "main_output_gain_context", "bus": bus},
                    "runtime_read_called": False,
                    "route": "db_workaround",
                    "db_table": "Sm2Sequence",
                    "db_field": "OutputAudioGain",
                    "reads": ["sequence_output_gain_context"],
                    "read_scope": "sequence_output_gain_context_only",
                    "sequence_output_gain_read_supported": True,
                    "verified_fader_read_supported": False,
                    "pan_read_supported": False,
                    "set_supported": False,
                    "preflight_command": "cutagent fairlight bus level Main --json",
                },
                title="Fairlight Mixer Read Plan",
            )
            return
        conn = get_connection(require_timeline=True)
        bus_level = fairlight_ops.read_fairlight_bus_level_db(conn, bus=bus)
        output(
            _fairlight_main_bus_mixer_read_payload(bus_level),
            title="Fairlight Mixer Read",
        )
        return
    enforce_mutation_policy("fairlight.mixer_read", intended_engine="db_workaround", mutating=False)
    if track is None:
        raise ValidationError(
            "Fairlight mixer read requires --track or --bus.",
            details={"track": track, "bus": bus, "supported_targets": ["audio_track", "main_output"]},
            recoverability="not_applicable",
        )
    set_execution_engine("db_workaround")
    set_verification_status("not_requested")
    set_recoverability("not_applicable")
    if is_dry_run():
        output(
            {
                "action": "fairlight.mixer.read",
                "dry_run": True,
                "track": int(track),
                "runtime_read_called": False,
                "route": "db_native",
                "db_blob": "Sm2Sequence.FieldsBlob.FLStudioModelBA",
                "reads": ["fader", "pan"],
                "preflight_command": "cutagent fairlight tracks --json",
            },
            title="Fairlight Mixer Read Plan",
        )
        return

    conn = get_connection(require_timeline=True)
    _validate_audio_track_index(conn, track)
    info = fairlight_ops.get_audio_track_info(conn, track)
    mixer = info.get("mixer")
    if not mixer:
        readback = {
            row.get("field"): row.get("db_readback")
            for row in info.get("unsupported_native_fields", [])
            if row.get("field") in {"fader_db", "pan"}
        }
        raise APICallFailed(
            "Fairlight mixer DB readback is unavailable for the selected audio track.",
            details={
                "track": int(track),
                "db_readback": readback,
                "preflight_command": "cutagent fairlight tracks --json",
            },
            recoverability="manual",
        )
    output(
        {
            "action": "fairlight.mixer.read",
            "track": {
                "index": info.get("index"),
                "name": info.get("name"),
                "format": info.get("format"),
                "enabled": (
                    info.get("enabled_bool")
                    if isinstance(info.get("enabled_bool"), bool)
                    else info.get("enabled")
                    if isinstance(info.get("enabled"), bool)
                    else info.get("enabled") == "✓"
                    if isinstance(info.get("enabled"), str)
                    else None
                ),
                "locked": (
                    info.get("locked_bool")
                    if isinstance(info.get("locked_bool"), bool)
                    else info.get("locked")
                    if isinstance(info.get("locked"), bool)
                    else info.get("locked") == "🔒"
                    if isinstance(info.get("locked"), str)
                    else None
                ),
                "clip_count": info.get("clip_count"),
            },
            "mixer": mixer,
            "route": "db_native",
            "db_blob": "Sm2Sequence.FieldsBlob.FLStudioModelBA",
        },
        title="Fairlight Mixer Read",
    )


@mixer_app.command("fader")
@handle_errors
def mixer_fader(
    track: int | None = typer.Option(None, "--track", "-t", min=1, help="Audio track index"),
    bus: str | None = typer.Option(None, "--bus", help="Bus/main output name"),
    level_db: float | None = typer.Option(None, "--level", "--level-db", help="Requested fader level in dB"),
):
    """Set or read a Fairlight audio-track fader or main-output gain context."""
    if bus is not None:
        if track is not None:
            raise ValidationError(
                "Fairlight mixer fader accepts one target selector: use --track or --bus, not both.",
                details={
                    "track": track,
                    "bus": bus,
                    "level_db": level_db,
                    "supported_targets": ["audio_track", "main_output"],
                },
                recoverability="not_applicable",
            )
        if level_db is None:
            if not fairlight_ops.normalize_fairlight_main_output_selector(bus):
                _raise_unmapped_fairlight_bus_readback(bus)
            enforce_mutation_policy("fairlight.bus_read", intended_engine="db_workaround", mutating=False)
            set_execution_engine("db_workaround")
            set_verification_status("not_requested")
            set_recoverability("not_applicable")
            if is_dry_run():
                output(
                    {
                        "action": "fairlight.mixer.fader.read",
                        "dry_run": True,
                        "target": {"kind": "main_output_gain_context", "bus": bus},
                        "runtime_read_called": False,
                        "route": "db_workaround",
                        "db_table": "Sm2Sequence",
                        "db_field": "OutputAudioGain",
                        "storage": "sequence_output_gain_context_only",
                        "sequence_output_gain_read_supported": True,
                        "verified_fader_read_supported": False,
                        "sequence_output_gain_set_supported": True,
                        "verified_fader_set_supported": False,
                        "set_supported": True,
                        "set_scope": "sequence_output_gain_context_only",
                        "preflight_command": "cutagent fairlight bus level Main --json",
                    },
                    title="Fairlight Mixer Fader Read Plan",
                )
                return
            conn = get_connection(require_timeline=True)
            bus_level = fairlight_ops.read_fairlight_bus_level_db(conn, bus=bus)
            output(
                _fairlight_main_bus_fader_read_payload(bus_level),
                title="Fairlight Mixer Fader",
            )
            return
        if not fairlight_ops.normalize_fairlight_main_output_selector(bus):
            _raise_fairlight_native_unavailable(
                capability_id="fairlight.bus_routing",
                workflow="Fairlight non-main bus mixer fader control",
                requested={"track": track, "bus": bus, "level_db": level_db},
                required_native_api=[
                    "resolve non-main buses to FlexBus graph nodes",
                    "set non-main bus fader/level",
                    "verify non-main bus mixer strip readback after a fader change",
                ],
                api_note="The discovered DaVinci Resolve 20 DB route maps only Main/Main 1 sequence output gain context, not non-main bus/FlexBus fader storage.",
                workaround="Use --bus Main for the mapped sequence output gain context, or set non-main/FlexBus faders in DaVinci Resolve until a verified bus DB route is added.",
                extra_details=_FAIRLIGHT_BUS_ROUTING_DB_BLOCKER_EVIDENCE,
            )
        enforce_mutation_policy(
            "fairlight.bus_read",
            intended_engine="db_workaround",
            mutating=not is_dry_run(),
        )
        set_execution_engine("db_workaround")
        normalized_level = fairlight_ops.validate_fairlight_sequence_output_gain_level(level_db)
        if is_dry_run():
            set_verification_status("not_requested")
            set_recoverability("not_applicable")
            output(
                mutation_payload(
                    action="fairlight.mixer.fader",
                    target={"kind": "main_output_gain_context", "bus": bus},
                    changed=False,
                    dry_run=True,
                    runtime_write_called=False,
                    level_db=normalized_level,
                    output_audio_gain=normalized_level,
                    route="db_native",
                    db_table="Sm2Sequence",
                    db_field="OutputAudioGain",
                    storage="sequence_output_gain_context_only",
                    set_scope="sequence_output_gain_context_only",
                    sequence_output_gain_set_supported=True,
                    verified_fader_set_supported=False,
                    verified_fader_read_supported=False,
                    verification_status="not_requested",
                    delegated_action="fairlight.bus.level",
                    preflight_command="cutagent fairlight bus level Main --json",
                ),
                title="Fairlight Mixer Fader Plan",
            )
            return
        conn = get_connection(require_timeline=True)
        data = fairlight_ops.set_fairlight_bus_level_db(
            conn,
            bus=bus,
            level_db=normalized_level,
        )
        output(
            _fairlight_main_bus_fader_set_payload(data),
            title="Fairlight Mixer Fader",
        )
        return
    if track is None:
        raise ValidationError(
            "Fairlight mixer fader requires --track for DB-backed track fader control.",
            details={"track": track, "bus": bus, "level_db": level_db, "supported_target": "audio_track"},
            recoverability="not_applicable",
        )
    enforce_mutation_policy(
        "fairlight.fader",
        intended_engine="db_workaround",
        mutating=level_db is not None and not is_dry_run(),
    )
    if level_db is None:
        if is_dry_run():
            set_verification_status("not_requested")
            set_recoverability("not_applicable")
            output(
                {
                    "action": "fairlight.mixer.fader.read",
                    "dry_run": True,
                    "track": int(track),
                    "runtime_read_called": False,
                    "route": "db_native",
                    "db_blob": "Sm2Sequence.FieldsBlob.FLStudioModelBA",
                    "storage": "channel_lane_int32_x10",
                    "preflight_command": "cutagent fairlight tracks --json",
                },
                title="Fairlight Mixer Fader Read Plan",
            )
            return
        conn = get_connection(require_timeline=True)
        data = fairlight_ops.read_audio_track_fader_db(conn, index=track)
        output(data, title="Fairlight Mixer Fader")
        return

    normalized_level = fairlight_ops.validate_mixer_fader_level(level_db)
    raw_value = int(round(normalized_level * 10))
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            mutation_payload(
                action="fairlight.mixer.fader",
                target={"kind": "audio_track", "track_type": "audio", "index": int(track)},
                changed=False,
                dry_run=True,
                runtime_write_called=False,
                level_db=normalized_level,
                raw_value=raw_value,
                route="db_native",
                db_blob="Sm2Sequence.FieldsBlob.FLStudioModelBA",
                storage="channel_lane_int32_x10",
                verification_status="not_requested",
                preflight_command="cutagent fairlight tracks --json",
            ),
            title="Fairlight Mixer Fader Plan",
        )
        return
    conn = get_connection(require_timeline=True)
    data = fairlight_ops.set_audio_track_fader_db(
        conn,
        index=track,
        level_db=normalized_level,
    )
    output(data, title="Fairlight Mixer Fader")


@mixer_app.command("pan")
@handle_errors
def mixer_pan(
    track: int | None = typer.Option(None, "--track", "-t", min=1, help="Audio track index"),
    bus: str | None = typer.Option(None, "--bus", help="Bus/main output name"),
    pan: float | None = typer.Option(None, "--pan", help="Requested 2D Left / Right pan value"),
    angle: float | None = typer.Option(None, "--angle", help="Requested 3D pan angle"),
    spread: float | None = typer.Option(None, "--spread", help="Requested 3D pan spread"),
):
    """Set or read a Fairlight audio-track mixer pan in DaVinci Resolve."""
    if bus is not None:
        _raise_fairlight_native_unavailable(
            capability_id="fairlight.bus_routing",
            workflow="Fairlight bus/main mixer pan control",
            requested={"track": track, "bus": bus, "pan": pan, "angle": angle, "spread": spread},
            required_native_api=[
                "read/set Fairlight bus/main pan",
                "resolve bus/main names to FlexBus graph nodes",
                "verify bus/main mixer panner readback after a pan change",
            ],
            api_note=(
                "DaVinci Resolve 20 Free DB/native research found no safe bus/main pan route. "
                "The only mapped main-output scalar is OutputAudioGain; bus/main panner storage remains separate or absent."
            ),
            workaround=(
                "Use track pan DB control for verified mono audio tracks, or set bus/main pan in DaVinci Resolve "
                "until a native API or verified DB route is found."
            ),
            extra_details={
                "available_db_route": (
                    "Audio-track pan lanes are mapped in Sm2Sequence.FieldsBlob.FLStudioModelBA; "
                    "Main/Main 1 exposes only Sm2Sequence.OutputAudioGain as sequence output gain context."
                ),
                "db_schema_evidence": {
                    "sampled_resolve_version": "DaVinci Resolve 20 Free",
                    "sampled_project_db_count": 3,
                    "sampled_sm2sequence_audio_columns": ["NumOutputAudioChannels", "OutputAudioGain"],
                    "missing_columns": ["OutputAudioPan", "BusPan", "MainPan"],
                    "searched_column_patterns": ["%pan%", "%output%", "%bus%", "%gain%", "%audio%"],
                },
                "native_probe_evidence": _FAIRLIGHT_BUS_ROUTING_NATIVE_PROBE_EVIDENCE,
            },
        )
    if angle is not None or spread is not None:
        _raise_fairlight_native_unavailable(
            capability_id="fairlight.pan",
            workflow="Fairlight 3D panner control",
            requested={"track": track, "bus": bus, "pan": pan, "angle": angle, "spread": spread},
            required_native_api=[
                "read/set 3D panner angle/spread/divergence",
                "map 3D panner DB payloads for stereo/surround targets",
                "verify rendered channel output after a 3D panner change",
            ],
            api_note="DaVinci Resolve DB research verified mono 2D pan and stereo Left / Right control; 3D panner angle/spread storage is not yet safely mapped.",
            workaround="Use --track with --pan for verified mono 2D pan or stereo Left / Right control, or set 3D panner controls in DaVinci Resolve until a verified DB route is added.",
            extra_details=_FAIRLIGHT_3D_PANNER_DB_BLOCKER_EVIDENCE,
        )
    if track is None:
        raise ValidationError(
            "Fairlight mixer pan requires --track for DB-backed track pan control.",
            details={"track": track, "bus": bus, "pan": pan, "angle": angle, "spread": spread, "supported_target": "mono_or_stereo_audio_track"},
            recoverability="not_applicable",
        )
    enforce_mutation_policy(
        "fairlight.pan",
        intended_engine="db_workaround",
        mutating=pan is not None and not is_dry_run(),
    )
    if pan is None:
        if is_dry_run():
            set_verification_status("not_requested")
            set_recoverability("not_applicable")
            output(
                {
                    "action": "fairlight.mixer.pan.read",
                    "dry_run": True,
                    "track": int(track),
                    "runtime_read_called": False,
                    "route": "db_native",
                    "db_blob": "Sm2Sequence.FieldsBlob.FLStudioModelBA",
                    "storage": "channel_lane_pan_int32_x10",
                    "verified_set_scope": "mono_track_2d_pan_or_stereo_track_left_right_when_present",
                    "preflight_command": "cutagent fairlight tracks --json",
                },
                title="Fairlight Mixer Pan Read Plan",
            )
            return
        conn = get_connection(require_timeline=True)
        data = fairlight_ops.read_audio_track_pan_db(conn, index=track)
        output(data, title="Fairlight Mixer Pan")
        return

    normalized_pan = fairlight_ops.validate_mixer_pan_value(pan)
    raw_value = int(round(normalized_pan * 10))
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            mutation_payload(
                action="fairlight.mixer.pan",
                target={"kind": "audio_track", "track_type": "audio", "index": int(track)},
                changed=False,
                dry_run=True,
                runtime_write_called=False,
                pan=normalized_pan,
                raw_value=raw_value,
                route="db_native",
                db_blob="Sm2Sequence.FieldsBlob.FLStudioModelBA",
                storage="channel_lane_pan_int32_x10",
                verified_set_scope="mono_track_2d_pan_or_stereo_track_left_right_when_present",
                verification_status="not_requested",
                preflight_command="cutagent fairlight tracks --json",
            ),
            title="Fairlight Mixer Pan Plan",
        )
        return
    conn = get_connection(require_timeline=True)
    data = fairlight_ops.set_audio_track_pan_db(
        conn,
        index=track,
        pan=normalized_pan,
    )
    output(data, title="Fairlight Mixer Pan")


_FAIRLIGHT_RESIDUAL_NATIVE_PROBE_CONTEXT = {
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
}


_FAIRLIGHT_RESOLVE21_NATIVE_PROBE_CONTEXT = {
    "runtime": "DaVinci Resolve 21.0.0.48 Free",
    "transport": "embedded_free_lua_bridge",
    "checked_at": "2026-06-12",
    "probe_project": "CUTAGENT_FAIRLIGHT_PARITY_20260605_175239",
    "probe_timeline": "FL_PARITY_24FPS",
    "audio_track_count": 4,
    "audio_track_1_item_count": 1,
    "baseline_verified_methods": [
        "Resolve.GetVersionString()",
        "Project.GetName()",
        "Timeline.GetName()",
        "Timeline.GetTrackCount('audio')",
        "Timeline.GetItemListInTrack('audio', 1)",
    ],
}


_FAIRLIGHT_ADR_NATIVE_PROBE_EVIDENCE = {
    **_FAIRLIGHT_RESIDUAL_NATIVE_PROBE_CONTEXT,
    "candidate_methods_not_available": [
        "Resolve.GetADRCueList()",
        "Resolve.GetADRCues()",
        "Resolve.GetADRSettings()",
        "Project.GetADRCueList()",
        "Project.GetADRCues()",
        "Project.GetADRTakes()",
        "Project.GetADRSettings()",
        "Timeline.GetADRCueList()",
        "Timeline.GetADRCues()",
        "Timeline.GetADRTakes()",
    ],
    "mutating_candidates_not_called": [
        "Project.StartADRRecording(...)",
        "Project.StopADRRecording(...)",
        "Project.CreateADRCue(...)",
        "Timeline.CreateADRCue(...)",
    ],
    "resolve_21_embedded_recheck": {
        "runtime": "DaVinci Resolve 21.0.0.48 Free",
        "transport": "embedded_lua_http_poll",
        "artifact": "/tmp/cutagent_adr_record_io_cp_20260619/11_direct_adr_record_io_probe_after_allowlist.json",
        "candidate_methods_not_available": [
            "Resolve.GetADRCueList()",
            "Resolve.GetADRCues()",
            "Resolve.GetADRSettings()",
            "Resolve.GetADRTakes()",
            "Project.GetADRCueList()",
            "Project.GetADRCues()",
            "Project.GetADRSettings()",
            "Project.GetADRTakes()",
            "Timeline.GetADRCueList()",
            "Timeline.GetADRCues()",
            "Timeline.GetADRSettings()",
            "Timeline.GetADRTakes()",
        ],
        "unsupported_bridge_count": 0,
        "probe_result": "ADR cue/take getter candidates reached DaVinci Resolve and returned method_not_available",
    },
    "probe_result": "ADR cue/take getters returned method_not_available; mutating ADR candidates were not called",
    "adr_native_read_supported": False,
    "adr_native_record_supported": False,
    "adr_native_mutation_supported": False,
}


_FAIRLIGHT_LOUDNESS_NATIVE_PROBE_EVIDENCE = {
    **_FAIRLIGHT_RESIDUAL_NATIVE_PROBE_CONTEXT,
    "candidate_methods_not_available": [
        "Project.GetLoudnessInfo()",
        "Project.GetLoudnessAnalysis()",
        "Project.GetLoudnessReport()",
        "Timeline.GetLoudnessInfo()",
        "Timeline.GetLoudnessAnalysis()",
        "Timeline.GetIntegratedLoudness()",
        "Timeline.GetTruePeak()",
    ],
    "mutating_candidates_not_called": [
        "Project.AnalyzeLoudness(...)",
        "Timeline.AnalyzeLoudness(...)",
        "Timeline.NormalizeLoudness(...)",
    ],
    "resolve_21_embedded_recheck": {
        "runtime": "DaVinci Resolve 21.0.0.48 Free",
        "transport": "embedded_lua_http_poll",
        "artifact": "/tmp/cutagent_loudness_meter_cr_20260619/01_direct_loudness_meter_probe.json",
        "candidate_methods_not_available": [
            "Project.GetLoudnessInfo()",
            "Project.GetLoudnessAnalysis()",
            "Project.GetLoudnessReport()",
            "Timeline.GetLoudnessInfo()",
            "Timeline.GetLoudnessAnalysis()",
            "Timeline.GetIntegratedLoudness()",
            "Timeline.GetTruePeak()",
        ],
        "unsupported_bridge_count": 0,
        "probe_result": "loudness getter candidates reached DaVinci Resolve and returned method_not_available",
    },
    "probe_result": "loudness getters returned method_not_available; analysis/normalization candidates were not called",
    "loudness_native_read_supported": False,
    "loudness_native_analysis_supported": False,
    "loudness_native_normalization_supported": False,
}


_FAIRLIGHT_METERING_NATIVE_PROBE_EVIDENCE = {
    **_FAIRLIGHT_RESIDUAL_NATIVE_PROBE_CONTEXT,
    "candidate_methods_not_available": [
        "Resolve.GetAudioMeters()",
        "Project.GetAudioMeters()",
        "Timeline.GetAudioMeterData()",
        "Timeline.GetTrackMeter('audio', 1)",
        "Timeline.GetTrackMeters('audio', 1)",
        "Timeline.GetFairlightMeter()",
        "Timeline.GetMixerMeters()",
    ],
    "resolve_21_embedded_recheck": {
        "runtime": "DaVinci Resolve 21.0.0.48 Free",
        "transport": "embedded_lua_http_poll",
        "artifact": "/tmp/cutagent_loudness_meter_cr_20260619/01_direct_loudness_meter_probe.json",
        "candidate_methods_not_available": [
            "Resolve.GetAudioMeters()",
            "Project.GetAudioMeters()",
            "Timeline.GetAudioMeterData()",
            "Timeline.GetTrackMeter('audio', 1)",
            "Timeline.GetTrackMeters('audio', 1)",
            "Timeline.GetFairlightMeter()",
            "Timeline.GetMixerMeters()",
        ],
        "unsupported_bridge_count": 0,
        "probe_result": "live meter getter candidates reached DaVinci Resolve and returned method_not_available",
    },
    "probe_result": "live meter getter candidates returned method_not_available",
    "live_meter_native_read_supported": False,
    "track_meter_native_read_supported": False,
    "bus_meter_native_read_supported": False,
}


_FAIRLIGHT_AUTOMATION_NATIVE_PROBE_EVIDENCE = {
    **_FAIRLIGHT_RESIDUAL_NATIVE_PROBE_CONTEXT,
    "candidate_methods_not_available": [
        "Timeline.GetAutomationItems('audio', 1)",
        "Timeline.GetAutomationLanes('audio', 1)",
        "Timeline.GetTrackAutomation('audio', 1)",
        "Timeline.GetAutomationData('audio', 1)",
        "TimelineItem.GetAutomationItems()",
        "TimelineItem.GetKeyframes()",
    ],
    "mutating_candidates_not_called": [
        "Timeline.SetAutomation(...)",
        "Timeline.WriteAutomationKeyframe(...)",
    ],
    "probe_result": "automation getters returned method_not_available; automation write candidates were not called",
    "automation_native_read_supported": False,
    "automation_native_write_supported": False,
}


_FAIRLIGHT_MONITOR_NATIVE_PROBE_EVIDENCE = {
    **_FAIRLIGHT_RESIDUAL_NATIVE_PROBE_CONTEXT,
    "candidate_methods_not_available": [
        "Resolve.GetMonitorSettings()",
        "Resolve.GetMonitorLevel()",
        "Resolve.GetMonitorMute()",
        "Project.GetMonitorSettings()",
        "Project.GetFairlightMonitorSettings()",
        "Timeline.GetMonitorSettings()",
    ],
    "mutating_candidates_not_called": [
        "Resolve.SetMonitorLevel(...)",
        "Resolve.SetMonitorMute(...)",
    ],
    "resolve_21_embedded_recheck": {
        "runtime": "DaVinci Resolve 21.0.0.48 Free",
        "transport": "embedded_lua_http_poll",
        "artifact": "/tmp/cutagent_fairlight_display_control_cm_20260619/13_direct_runtime_read_probe_after_allowlist.json",
        "candidate_methods_not_available": [
            "Resolve.GetMonitorSettings()",
            "Resolve.GetMonitorLevel()",
            "Resolve.GetMonitorMute()",
            "Project.GetMonitorSettings()",
            "Project.GetFairlightMonitorSettings()",
            "Timeline.GetMonitorSettings()",
            "Resolve.GetControlRoomLevel()",
            "Resolve.GetControlRoomMute()",
        ],
        "unsupported_bridge_count": 0,
        "probe_result": "monitor/control-room getter candidates reached DaVinci Resolve and returned method_not_available",
    },
    "probe_result": "monitor/control-room getters returned method_not_available; monitor mutation candidates were not called",
    "monitor_native_read_supported": False,
    "monitor_native_write_supported": False,
}


_FAIRLIGHT_ELASTIC_NATIVE_PROBE_EVIDENCE = {
    **_FAIRLIGHT_RESIDUAL_NATIVE_PROBE_CONTEXT,
    "candidate_methods_not_available": [
        "Timeline.GetElasticWaveItems()",
        "TimelineItem.GetElasticWaveState()",
        "TimelineItem.GetElasticWaveKeyframes()",
        "TimelineItem.GetElasticAudio()",
        "TimelineItem.GetRetimeProcess()",
    ],
    "mutating_candidates_not_called": [
        "TimelineItem.SetElasticWaveState(...)",
        "TimelineItem.AddElasticWaveKeyframe(...)",
    ],
    "probe_result": "Elastic Wave getters returned method_not_available; Elastic Wave mutation candidates were not called",
    "elastic_native_read_supported": False,
    "elastic_native_write_supported": False,
    "resolve_21_probe_evidence": {
        **_FAIRLIGHT_RESOLVE21_NATIVE_PROBE_CONTEXT,
        "candidate_methods_not_available": [
            "Timeline.GetElasticWaveItems()",
            "TimelineItem.GetElasticWaveState()",
            "TimelineItem.GetElasticWaveKeyframes()",
            "TimelineItem.GetElasticAudio()",
            "TimelineItem.GetRetimeProcess()",
        ],
        "mutating_candidates_not_called": [
            "TimelineItem.SetElasticWaveState(...)",
            "TimelineItem.AddElasticWaveKeyframe(...)",
        ],
        "probe_result": (
            "DaVinci Resolve 21 embedded Lua bridge returned method_not_available for Elastic Wave getters; "
            "Elastic Wave mutation candidates were not called."
        ),
        "elastic_native_read_supported": False,
        "elastic_native_write_supported": False,
    },
}


_FAIRLIGHT_EXTERNAL_PROCESS_NATIVE_PROBE_EVIDENCE = {
    **_FAIRLIGHT_RESIDUAL_NATIVE_PROBE_CONTEXT,
    "candidate_methods_not_available": [
        "Resolve.GetExternalAudioProcesses()",
        "Resolve.GetFairlightExternalProcesses()",
        "Project.GetExternalAudioProcesses()",
        "Project.GetFairlightExternalProcesses()",
        "Timeline.GetExternalAudioProcesses()",
    ],
    "mutating_candidates_not_called": [
        "Project.RunExternalAudioProcess(...)",
    ],
    "resolve_21_embedded_recheck": {
        "runtime": "DaVinci Resolve 21.0.0.48 Free",
        "transport": "embedded_lua_http_poll",
        "artifact": "/tmp/cutagent_sound_external_cn_20260619/07_direct_sound_external_probe_after_allowlist.json",
        "candidate_methods_not_available": [
            "Resolve.GetExternalAudioProcesses()",
            "Resolve.GetFairlightExternalProcesses()",
            "Project.GetExternalAudioProcesses()",
            "Project.GetFairlightExternalProcesses()",
            "Timeline.GetExternalAudioProcesses()",
        ],
        "unsupported_bridge_count": 0,
        "probe_result": "external-process getter candidates reached DaVinci Resolve and returned method_not_available",
    },
    "probe_result": "external-process getters returned method_not_available; launch candidate was not called",
    "external_process_native_list_supported": False,
    "external_process_native_run_supported": False,
}


_FAIRLIGHT_WAVEFORM_NATIVE_PROBE_EVIDENCE = {
    **_FAIRLIGHT_RESIDUAL_NATIVE_PROBE_CONTEXT,
    "candidate_methods_not_available": [
        "Timeline.GetWaveformData('audio', 1)",
        "Timeline.GetAudioWaveform('audio', 1)",
        "TimelineItem.GetWaveform()",
        "TimelineItem.GetAudioWaveform()",
        "TimelineItem.GetWaveformData()",
        "TimelineItem.GetAudioSamples()",
        "TimelineItem.GetSampleRepairState()",
    ],
    "mutating_candidates_not_called": [
        "TimelineItem.RepairClick(...)",
        "TimelineItem.RepairPop(...)",
    ],
    "resolve_21_embedded_recheck": {
        "runtime": "DaVinci Resolve 21.0.0.48 Free",
        "transport": "embedded_lua_http_poll",
        "artifact": "/tmp/cutagent_waveform_probe_cq_20260619/01_direct_waveform_probe_after_allowlist.json",
        "candidate_methods_not_available": [
            "Timeline.GetWaveformData('audio', 1)",
            "Timeline.GetAudioWaveform('audio', 1)",
            "Timeline.GetAudioSamples('audio', 1)",
            "TimelineItem.GetWaveform()",
            "TimelineItem.GetAudioWaveform()",
            "TimelineItem.GetWaveformData()",
            "TimelineItem.GetAudioSamples()",
            "TimelineItem.GetSampleRepairState()",
        ],
        "unsupported_bridge_count": 0,
        "probe_result": "waveform/sample getter candidates reached DaVinci Resolve and returned method_not_available",
    },
    "probe_result": "waveform/sample getters returned method_not_available; repair candidates were not called",
    "waveform_native_read_supported": False,
    "sample_repair_native_supported": False,
}


_FAIRLIGHT_METERING_DB_BLOCKER_EVIDENCE = {
    "available_db_route": "cutagent fairlight mixer meter-settings --json",
    "db_readback_command": "fairlight.mixer.meter_settings",
    "api_setting_snapshot_evidence": {
        "source": "Project.GetSetting()/Timeline.GetSetting() snapshot via embedded DaVinci Resolve 20.3.2 Free",
        "project": "CUTAGENT_FAIRLIGHT_PARITY_20260605_175239",
        "timeline": "FL_PARITY_24FPS",
        "queryable_audio_meter_keys": [
            "limitAudioMeterAlignLevel",
            "limitAudioMeterDisplayMode",
            "limitAudioMeterHighLevel",
            "limitAudioMeterLUFS",
            "limitAudioMeterLoudnessScale",
            "limitAudioMeterLowLevel",
        ],
        "read_scope": "project/timeline audio meter preferences only",
        "live_meter_values_supported": False,
        "peak_hold_supported": False,
        "clip_indicator_supported": False,
        "targeted_track_bus_metering_supported": False,
    },
    "db_schema_evidence": {
        "source": "local DaVinci Resolve 20 Free Project.db schema probes",
        "sampled_project_db_count": 5,
        "read_scope": "negative_live_meter_schema_probe",
        "setup_tables_read_by_command": [
            "SM_UserSetup",
            "SM_Setup",
        ],
        "stored_meter_setup_columns_seen": [
            "SM_UserSetup.AudioMeterDBUEnable",
            "SM_UserSetup.AudioMeterAlignmentLevel",
        ],
        "non_meter_candidates_seen": [
            "SM_Effect.ParametersBody",
            "SmSpeedProfile.SpeedCurveParameterBody",
        ],
        "live_meter_named_table_found_in_samples": False,
        "lufs_peak_meter_table_found_in_samples": False,
        "per_track_meter_value_column_found_in_samples": False,
        "bus_meter_value_column_found_in_samples": False,
        "peak_hold_clip_indicator_schema_found_in_samples": False,
        "playback_meter_readback_route_found_in_samples": False,
        "setup_columns_are_preferences_not_live_meter_values": True,
    },
    "meter_model_evidence": {
        "db_tables": ["SM_UserSetup", "SM_Setup"],
        "read_scope": "stored_audio_meter_setup_only",
        "setup_signal_supported": True,
        "live_meter_values_supported": False,
        "peak_hold_supported": False,
        "clip_indicator_supported": False,
        "targeted_track_bus_metering_supported": False,
        "loudness_analysis_supported": False,
    },
    "native_probe_evidence": _FAIRLIGHT_METERING_NATIVE_PROBE_EVIDENCE,
    "db_blocker_note": (
        "`fairlight mixer meter-settings` can read stored audio-meter setup rows, but it is read-only evidence. "
        "It is not a verified live meter-value, peak/hold, clip-indicator, track/bus target, or playback-meter route."
    ),
}


@mixer_app.command("meter")
@handle_errors
def mixer_meter(
    track: int | None = typer.Option(None, "--track", "-t", min=1, help="Audio track index"),
    bus: str | None = typer.Option(None, "--bus", help="Bus/main output name"),
    include_peak_hold: bool = typer.Option(True, "--include-peak-hold/--no-peak-hold", help="Request peak-hold values when available"),
):
    """Report Fairlight mixer metering API availability."""
    enforce_mutation_policy("fairlight.metering", intended_engine="not_available", mutating=False)
    _raise_fairlight_native_unavailable(
        capability_id="fairlight.metering",
        workflow="Fairlight mixer metering",
        requested={"track": track, "bus": bus, "include_peak_hold": bool(include_peak_hold)},
        required_native_api=[
            "read Fairlight mixer meter values",
            "read peak/hold/clip indicators during playback",
            "select track, bus, and main-output meter targets",
        ],
        api_note="Fairlight live mixer meters are not exposed by the DaVinci Resolve scripting API.",
        workaround="Use DaVinci Resolve's Fairlight meters or render/export audio and analyze the resulting file with an external metering tool.",
        extra_details=_FAIRLIGHT_METERING_DB_BLOCKER_EVIDENCE,
    )


@mixer_app.command("meter-settings")
@handle_errors
def mixer_meter_settings(
    limit: int = typer.Option(20, "--limit", min=1, help="Maximum stored meter setup rows per table to read"),
):
    """Read stored Fairlight audio-meter setup rows from the DaVinci Resolve project database."""
    enforce_mutation_policy("fairlight.metering_read", intended_engine="db_workaround", mutating=False)
    set_execution_engine("db_workaround")
    set_verification_status("not_requested")
    set_recoverability("not_applicable")
    db_tables = ["SM_UserSetup", "SM_Setup"]
    if is_dry_run():
        output(
            {
                "action": "fairlight.mixer.meter_settings",
                "dry_run": True,
                "limit": int(limit),
                "runtime_read_called": False,
                "route": "db_workaround",
                "db_tables": db_tables,
                "read_scope": "stored_audio_meter_setup_only",
                "live_meter_values_supported": False,
                "peak_hold_supported": False,
                "loudness_analysis_supported": False,
                "monitor_control_supported": False,
                "set_supported": False,
                "preflight_command": "cutagent fairlight mixer meter-settings --json",
            },
            title="Fairlight Meter Settings Plan",
        )
        return
    conn = get_connection(require_project=True, require_timeline=False)
    data = fairlight_ops.read_fairlight_meter_settings_db(conn, limit=limit)
    output(data, title="Fairlight Meter Settings")


@automation_app.command("list")
@handle_errors
def automation_list(
    limit: int = typer.Option(50, "--limit", min=1, help="Maximum AutoMix/MixLevel token rows per group to return"),
    include_context: bool = typer.Option(False, "--include-context", help="Include bounded hex/ASCII DB context around each token"),
    context_bytes: int = typer.Option(32, "--context-bytes", min=0, max=256, help="Bytes before/after each token when --include-context is set"),
):
    """List verified audio-clip volume envelopes and diagnostic mixer-model tokens."""
    enforce_mutation_policy("fairlight.automation_read", intended_engine="db_workaround", mutating=False)
    set_execution_engine("db_workaround")
    set_verification_status("not_requested")
    set_recoverability("not_applicable")
    if is_dry_run():
        output(
            {
                "action": "fairlight.automation.list",
                "dry_run": True,
                "would_read": True,
                "route": "db_workaround",
                "target": "current_timeline_fairlight_automation_tokens",
                "limit": int(limit),
                "include_context": bool(include_context),
                "context_bytes": int(context_bytes) if include_context else 0,
                "db_blob": "Sm2Sequence.FieldsBlob.FLStudioModelBA",
                "read_scope": "audio_clip_volume_envelopes_plus_automix_and_mix_level_tokens",
                "token_probe_supported": True,
                "context_supported": True,
                "clip_volume_envelope_keyframes_supported": True,
                "track_or_bus_lane_keyframes_supported": False,
                "write_supported": True,
                "set_supported": False,
            },
            title="Fairlight Automation Plan",
        )
        return
    conn = get_connection(require_timeline=True)
    data = fairlight_ops.read_fairlight_automation_list_db(
        conn,
        limit=limit,
        include_context=include_context,
        context_bytes=context_bytes,
    )
    envelopes = keyframe_db.list_audio_volume_envelopes(conn, limit=limit)
    data["clip_volume_envelopes"] = envelopes["envelopes"]
    data["clip_volume_envelope_count"] = envelopes["count"]
    data["clip_volume_envelope_total_count"] = envelopes["total_count"]
    data["clip_volume_envelopes_truncated"] = envelopes["truncated"]
    data["read_scope"] = "audio_clip_volume_envelopes_plus_automix_and_mix_level_tokens"
    data["lane_keyframes_supported"] = False
    data["clip_volume_envelope_keyframes_supported"] = True
    data["track_or_bus_lane_keyframes_supported"] = False
    data["write_supported"] = True
    data["set_supported"] = True
    data["set_blocker"] = (
        "Audio-clip volume envelope points are supported through the exact keyframe DB route. "
        "Track mixer and bus automation lanes remain unmapped."
    )
    data["note"] = (
        "Clip volume envelopes are decoded from Sm2TiItem.EffectFiltersBA and are distinct from track or bus mixer automation. "
        "AutoMix and MixLevel tokens are diagnostic mixer-model evidence only."
    )
    output(data, title="Fairlight Automation")


_FAIRLIGHT_AUTOMATION_DB_BLOCKER_EVIDENCE = {
    "available_db_route": "cutagent fairlight automation list --include-context --json",
    "db_readback_command": "fairlight.automation.list",
    "automation_model_evidence": {
        "db_blob": "Sm2Sequence.FieldsBlob.FLStudioModelBA",
        "read_scope": "automix_and_mix_level_tokens_only",
        "token_probe_supported": True,
        "context_supported": True,
        "track_or_bus_lane_keyframes_supported": False,
        "clip_volume_envelope_keyframes_supported": True,
        "write_supported": True,
        "set_supported": True,
    },
    "db_schema_evidence": {
        "source": "local DaVinci Resolve 20 Free Project.db schema probes",
        "sampled_project_db_count": 5,
        "read_scope": "negative_automation_lane_keyframe_schema_probe",
        "searched_table_or_column_fragments": [
            "automation",
            "automix",
            "mixlevel",
            "keyframe",
            "envelope",
            "latch",
            "touch",
            "write_state",
        ],
        "mixer_model_blob_read_by_command": "Sm2Sequence.FieldsBlob.FLStudioModelBA",
        "token_families_read_by_command": [
            "AutoMix*",
            "MixLevel:*",
        ],
        "setup_columns_seen": [
            "SM_Setup.UseTimelineKeyframes",
        ],
        "sampled_tables_matching_automation_lanes": [],
        "automation_lane_schema_found_in_samples": False,
        "automation_keyframe_schema_found_in_samples": False,
        "automation_envelope_schema_found_in_samples": False,
        "touch_latch_write_state_schema_found_in_samples": False,
        "track_or_bus_automation_write_readback_route_found_in_samples": False,
        "clip_volume_envelope_write_readback_route": "Sm2TiItem.EffectFiltersBA group 124 parameter 95",
    },
    "native_probe_evidence": _FAIRLIGHT_AUTOMATION_NATIVE_PROBE_EVIDENCE,
    "db_blocker_note": (
        "`fairlight automation list` can expose AutoMix/MixLevel token candidates in the Fairlight mixer model, "
        "and does not map track or bus automation lanes. Audio-clip volume envelopes use the separate verified "
        "Sm2TiItem.EffectFiltersBA keyframe route."
    ),
}


@automation_app.command("write", context_settings={"ignore_unknown_options": True, "allow_extra_args": True})
@handle_errors
def automation_write(
    ctx: typer.Context,
    lane: str | None = typer.Argument(None, help="Audio-clip automation lane; volume/level/gain are accepted"),
    value: str | None = typer.Option(None, "--value", "-v", help="Automation value to write"),
    track: int | None = typer.Option(None, "--track", "-t", help="Audio track index to target"),
    clip: str | None = typer.Option(None, "--clip", help="Unsupported; use --track with --at"),
    bus: str | None = typer.Option(None, "--bus", help="Unsupported for time-varying automation"),
    at: str | None = typer.Option(None, "--at", help="Timeline timecode/frame/seconds for the automation write"),
):
    """Write one verified audio-clip volume-envelope point at a timeline position."""
    extra_args = list(ctx.args)
    if value is None and extra_args:
        candidate = extra_args[0]
        try:
            float(candidate)
        except ValueError:
            pass
        else:
            if candidate.startswith("-"):
                value = candidate
                extra_args.pop(0)
    if extra_args:
        raise ValidationError(
            "Unexpected automation write argument.",
            details={
                "unexpected": extra_args,
                "hint": "Use --value or -v for signed values, e.g. `--value -6` or `-v -6`.",
            },
        )
    if isinstance(value, str) and value.startswith("="):
        value = value[1:]
    enforce_mutation_policy("fairlight.automation", intended_engine="db_workaround", mutating=not is_dry_run())
    missing = []
    if not lane:
        missing.append("lane")
    if value is None:
        missing.append("value")
    if missing:
        raise ValidationError(
            "Automation lane and value are required.",
            details={
                "example": "cutagent fairlight automation write volume --value -6 --track 1 --at 01:00:00:00 --json",
                "missing": missing,
                "optional": ["--track", "--clip", "--bus", "--at"],
                "api_note": "Fairlight automation writing is limited to a verified audio-clip volume-envelope point.",
            },
        )
    import math

    lane_key = str(lane or "").strip().casefold().replace("_", "-")
    if lane_key not in {"volume", "level", "gain"}:
        raise ValidationError(
            "Only audio-clip volume-envelope automation is supported by the verified DB-backed route.",
            details={"lane": lane, "supported": ["volume"]},
            recoverability="not_applicable",
        )
    try:
        gain_db = float(value)
    except Exception as exc:
        raise ValidationError(
            "Automation value must be a finite number.",
            details={"value": value},
            recoverability="not_applicable",
        ) from exc
    if not math.isfinite(gain_db):
        raise ValidationError(
            "Automation value must be a finite number.",
            details={"value": value},
            recoverability="not_applicable",
        )
    if clip:
        raise ValidationError(
            "Clip-name automation selectors are not supported; select one exact audio clip by track and timeline position.",
            details={"clip": clip, "supported_selectors": ["--track with --at"]},
            recoverability="not_applicable",
        )
    if bus:
        _raise_fairlight_native_unavailable(
            capability_id="fairlight.automation",
            workflow="Fairlight bus automation lane write",
            requested={"lane": lane, "value": gain_db, "bus": bus, "at": at},
            required_native_api=[
                "write and read back a time-varying Fairlight bus automation lane",
                "write a bus automation keyframe at an exact timeline frame",
            ],
            api_note="Main-output gain is mapped, but a time-varying bus automation lane is not.",
            workaround="Use `fairlight bus level` for non-automated main-output gain.",
            extra_details=_FAIRLIGHT_AUTOMATION_DB_BLOCKER_EVIDENCE,
        )
    if track is None:
        raise ValidationError(
            "Track volume automation requires --track.",
            details={"required": ["--track"], "example": "cutagent fairlight automation write volume --value -6 --track 1 --at 01:00:00:00 --json"},
            recoverability="not_applicable",
        )
    if not at:
        raise ValidationError(
            "Audio-clip volume-envelope automation requires --at to select the containing clip and keyframe position.",
            details={"required": ["--at"], "example": "cutagent fairlight automation write volume --value -6 --track 1 --at 01:00:00:00 --json"},
            recoverability="not_applicable",
        )
    selector = {"track_index": int(track), "record_frame": at}
    if is_dry_run():
        set_execution_engine("db_workaround")
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            {
                "action": "fairlight.automation.write",
                "would_write": True,
                "dry_run": True,
                "route": "keyframe_db_audio_clip_volume_envelope",
                "automation_owner": "audio_clip",
                "lane": "volume",
                "track": int(track),
                "at": at,
                "value_db": gain_db,
                "selector": selector,
                "project_close_required_for_live_run": True,
            },
            title="Fairlight Automation Write Plan",
        )
        return
    conn = get_connection(require_timeline=True)
    data = keyframe_db.add_audio_volume_keyframe(
        conn,
        track=int(track),
        at=str(at),
        value_db=gain_db,
    )
    output(data, title="Fairlight Automation Write")


record_app = typer.Typer(help="Fairlight recording operations.")
app.add_typer(record_app, name="record")


_FAIRLIGHT_RECORD_INPUT_DB_BLOCKER_EVIDENCE = {
    "available_db_route": (
        "`fairlight record info` reads stored SyRecordInfo setup/status rows and `fairlight io info` "
        "reads stored SM_AudioSettings/VTR setup rows, but those routes are read-only project setup "
        "readbacks and do not verify per-track record-arm, patch, or input-monitor writes."
    ),
    "db_readback_commands": [
        "cutagent fairlight record info --json",
        "cutagent fairlight io info --json",
    ],
    "api_setting_snapshot_evidence": {
        "source": "Project.GetSetting()/Timeline.GetSetting() snapshot via embedded DaVinci Resolve 20.3.2 Free",
        "project": "CUTAGENT_FAIRLIGHT_PARITY_20260605_175239",
        "timeline": "FL_PARITY_24FPS",
        "queryable_record_patch_keys": [
            "audioCaptureNumChannels",
            "audioOutputHasTimecode",
            "audioPlayoutNumChannels",
            "videoCaptureMode",
            "videoDeckOutputSyncSource",
            "videoPlayoutMode",
        ],
        "read_scope": "project/timeline capture and playout preferences only",
        "per_track_record_arm_supported": False,
        "per_track_input_monitor_supported": False,
        "patch_write_supported": False,
        "record_transport_supported": False,
    },
    "db_schema_evidence": {
        "sampled_resolve_edition": "DaVinci Resolve 20 Free",
        "sampled_project_db_count": 3,
        "read_scope": "stored_record_and_patch_setup_only",
        "sampled_track_table": "Sm2TiTrack",
        "sampled_sm2titrack_columns": [
            "Sm2TiTrack_id",
            "DbType",
            "Type",
            "SubType",
            "Flags",
            "Sequence",
            "AudioMixerBA",
            "Sm2Sequence_id",
            "UserDefinedName",
            "FieldsBlob",
            "Sm2SequenceContainer_id",
            "BaseTrack",
            "Sm2TiTrack_Owner_id",
        ],
        "sampled_record_setup_columns": [
            "SM_Setup.RecordAudioEnabled",
            "SM_Setup.RecordAudioNumChannels",
            "SM_Setup.IsRecording",
            "SM_Session.RecordStartFrame",
            "SyRecordInfo.RecordAudioEnabled",
            "SyRecordInfo.RecordAudioNumChannels",
        ],
        "sampled_patch_setup_columns": [
            "SM_AudioSettings.EnableAudio",
            "SM_AudioSettings.SM_VTRInputSettings_id",
            "SM_VTRConfiguration.InputSettings",
            "SM_VTRInputSettings.InputFolder",
            "SM_VTRInputSettings.AudioSettings",
            "SM_VTROutputSettings.AudioSettings",
        ],
        "missing_per_track_columns": [
            "Sm2TiTrack.RecordArm",
            "Sm2TiTrack.InputMonitor",
            "Sm2TiTrack.InputPatch",
            "Sm2TiTrack.AudioInput",
        ],
        "unverified_write_scope": [
            "per-track record arm",
            "per-track input monitor",
            "hardware input patch mutation",
            "record transport start/stop",
        ],
    },
    "native_probe_evidence": {
        "runtime": "DaVinci Resolve 20.3.2.9 Free",
        "transport": "embedded_lua_http_poll",
        "probe_project": "CUTAGENT_FAIRLIGHT_PARITY_20260605_175239",
        "verified_available_methods": [
            "Resolve.GetFairlightPresets()",
            "Project.GetCurrentTimeline()",
            "Timeline.GetTrackCount('audio')",
            "Timeline.GetTrackName('audio', 1)",
            "Timeline.GetIsTrackEnabled('audio', 1)",
            "Timeline.GetIsTrackLocked('audio', 1)",
            "Timeline.GetTrackSubType('audio', 1)",
        ],
        "candidate_methods_not_available": [
            "Resolve.GetFairlightRecordSettings()",
            "Project.GetFairlightRecordSettings()",
            "Project.StartFairlightRecording()",
            "Project.StopFairlightRecording()",
            "Project.ArmForRecording()",
            "Project.GetTrackRecordEnable()",
            "Project.GetTrackInputMonitor()",
            "Project.PatchInput()",
            "Timeline.GetTrackRecordEnable('audio', 1)",
            "Timeline.GetTrackInputMonitor('audio', 1)",
            "Timeline.ArmTrack('audio', 1)",
            "Timeline.RecordArmTrack('audio', 1)",
            "Timeline.GetTrackArmForRecord('audio', 1)",
            "Timeline.StartRecording('audio', 1)",
            "Timeline.StopRecording('audio', 1)",
            "Timeline.StartFairlightRecording('audio', 1)",
            "Timeline.StopFairlightRecording('audio', 1)",
        ],
        "probe_result": "read-only candidate getters returned method_not_available; mutating candidates were not called",
        "resolve_21_embedded_recheck": {
            "runtime": "DaVinci Resolve 21.0.0.48 Free",
            "transport": "embedded_lua_http_poll",
            "artifact": "/tmp/cutagent_adr_record_io_cp_20260619/11_direct_adr_record_io_probe_after_allowlist.json",
            "candidate_methods_not_available": [
                "Resolve.GetFairlightRecordSettings()",
                "Project.GetFairlightRecordSettings()",
                "Project.GetTrackRecordEnable()",
                "Project.GetTrackInputMonitor()",
                "Project.GetPatchInput()",
                "Project.GetPatchIO()",
                "Project.GetIOPatch()",
                "Timeline.GetTrackRecordEnable('audio', 1)",
                "Timeline.GetTrackInputMonitor('audio', 1)",
                "Timeline.GetTrackArmForRecord('audio', 1)",
                "Timeline.GetPatchInput('audio', 1)",
                "Timeline.GetPatchIO('audio', 1)",
                "Timeline.GetIOPatch('audio', 1)",
            ],
            "unsupported_bridge_count": 0,
            "probe_result": "record/input/Patch I/O getter candidates reached DaVinci Resolve and returned method_not_available",
        },
        "record_arm_native_read_supported": False,
        "record_transport_native_read_supported": False,
        "input_monitor_native_read_supported": False,
        "patch_io_native_read_supported": False,
    },
}


@record_app.command("info")
@handle_errors
def record_info(
    limit: int = typer.Option(20, "--limit", min=1, help="Maximum stored record setup/status rows to read"),
):
    """Read stored Fairlight recording setup/status rows from Project.db."""
    enforce_mutation_policy("fairlight.recording_read", intended_engine="db_workaround", mutating=False)
    set_execution_engine("db_workaround")
    set_verification_status("not_requested")
    set_recoverability("not_applicable")
    if is_dry_run():
        output(
            {
                "action": "fairlight.record.info",
                "dry_run": True,
                "limit": int(limit),
                "runtime_read_called": False,
                "route": "db_workaround",
                "db_tables": ["SyRecordInfo", "Sm2Timeline"],
                "read_scope": "stored_record_setup_only",
                "record_arm_supported": False,
                "record_transport_supported": False,
                "preflight_command": "cutagent fairlight record info --json",
            },
            title="Fairlight Record Info Plan",
        )
        return
    conn = get_connection(require_project=True, require_timeline=False)
    data = fairlight_ops.read_fairlight_record_info_db(conn, limit=limit)
    output(data, title="Fairlight Record Info")


@record_app.command("arm")
@handle_errors
def record_arm(
    track: int | None = typer.Option(None, "--track", "-t", min=1, help="Audio track index to arm"),
    enable: bool = typer.Option(True, "--enable/--disable", help="Requested record-arm state"),
):
    """Report Fairlight record-arm API availability."""
    enforce_mutation_policy("fairlight.recording", intended_engine="not_available", mutating=False)
    if track is None:
        raise ValidationError(
            "Audio track is required for record arm.",
            details={
                "example": "cutagent fairlight record arm --track 1 --enable --json",
                "required": ["--track"],
                "api_note": "Fairlight record-arm state is not exposed by the DaVinci Resolve scripting API.",
            },
        )
    _raise_fairlight_native_unavailable(
        capability_id="fairlight.recording",
        workflow="Fairlight record arm",
        requested={"track": int(track), "enable": bool(enable)},
        required_native_api=[
            "arm/disarm an audio track for recording",
            "read audio track record-arm state",
            "select/patch an audio input for recording",
        ],
        api_note=(
            "DaVinci Resolve exposes media import and Fairlight insert APIs, but not record-arm or input monitoring APIs. "
            "Stored record setup/status and patch rows are readable for diagnostics only and are not a verified "
            "per-track arm/input-monitor mutation route."
        ),
        workaround="Arm and patch the track in DaVinci Resolve, then use cutagent for supported post-recording timeline operations.",
        extra_details=_FAIRLIGHT_RECORD_INPUT_DB_BLOCKER_EVIDENCE,
    )


@record_app.command("start")
@handle_errors
def record_start(
    track: int | None = typer.Option(None, "--track", "-t", min=1, help="Optional audio track index expected to be armed"),
):
    """Report Fairlight audio recording start API availability."""
    enforce_mutation_policy("fairlight.recording", intended_engine="not_available", mutating=False)
    _raise_fairlight_native_unavailable(
        capability_id="fairlight.recording",
        workflow="Fairlight audio recording",
        requested={"track": int(track) if track else None, "action": "start"},
        required_native_api=[
            "start Fairlight audio recording",
            "stop Fairlight audio recording",
            "read recording/take status",
        ],
        api_note=(
            "Fairlight transport recording and take creation are not exposed by the DaVinci Resolve scripting API. "
            "Stored SyRecordInfo rows are post/setup readback only and do not provide a verified transport-control route."
        ),
        workaround="Record in DaVinci Resolve, then use cutagent to inspect, rename, move, gain-stage, or process resulting clips.",
        extra_details=_FAIRLIGHT_RECORD_INPUT_DB_BLOCKER_EVIDENCE,
    )


@record_app.command("stop")
@handle_errors
def record_stop():
    """Report Fairlight audio recording stop API availability."""
    enforce_mutation_policy("fairlight.recording", intended_engine="not_available", mutating=False)
    _raise_fairlight_native_unavailable(
        capability_id="fairlight.recording",
        workflow="Fairlight audio recording stop",
        requested={"action": "stop"},
        required_native_api=[
            "stop Fairlight audio recording",
            "read active recording/take status",
        ],
        api_note=(
            "Fairlight transport recording control is not exposed by the DaVinci Resolve scripting API. "
            "Stored SyRecordInfo rows are post/setup readback only and do not provide a verified transport-control route."
        ),
        workaround="Stop recording in DaVinci Resolve, then use cutagent for supported clip and track operations.",
        extra_details=_FAIRLIGHT_RECORD_INPUT_DB_BLOCKER_EVIDENCE,
    )


adr_app = typer.Typer(help="Fairlight ADR operations.")
app.add_typer(adr_app, name="adr")

_FAIRLIGHT_ADR_DB_BLOCKER_EVIDENCE = {
    "available_db_route": "cutagent fairlight adr info --json",
    "db_readback_command": "fairlight.adr.info",
    "db_schema_evidence": {
        "source": "local Project.db schema probe",
        "sampled_project_db_count": 1,
        "read_scope": "negative_adr_cue_take_schema_probe",
        "searched_table_name_fragments": ["adr", "cue", "take"],
        "sampled_tables_matching_adr_cue_take": [],
        "record_setup_tables_seen": [
            "SyRecordInfo",
            "SyRecordInfo_SyRenderFormatInfo",
        ],
        "cue_schema_found_in_sample": False,
        "cue_rows_found_in_sample": False,
        "take_schema_found_in_sample": False,
        "adr_record_route_found_in_sample": False,
    },
    "adr_model_evidence": {
        "read_scope": "adr_schema_probe_and_setup_signals",
        "read_consistency": "disk_project_db",
        "storage_probe": "tables/views matching ADR, cue, take, or setup-signal columns",
        "cue_schema_probe_supported": True,
        "cue_rows_may_be_reported": True,
        "cue_mutation_supported": False,
        "record_supported": False,
        "take_management_supported": False,
        "panel_control_supported": False,
    },
    "native_probe_evidence": _FAIRLIGHT_ADR_NATIVE_PROBE_EVIDENCE,
    "db_blocker_note": (
        "`fairlight adr info` can report stored ADR cue/take schema candidates and setup signals, but it is "
        "read-only evidence. It is not a verified ADR panel control, cue mutation, recorder, beep/streamer, "
        "prompt, or take-management route."
    ),
}


@adr_app.command("info")
@handle_errors
def adr_info(
    limit: int = typer.Option(20, "--limit", min=1, help="Maximum ADR-related schema/setup rows per candidate table to read"),
):
    """Read stored Fairlight ADR cue/take schema and setup signals from Project.db."""
    enforce_mutation_policy("fairlight.adr_read", intended_engine="db_workaround", mutating=False)
    set_execution_engine("db_workaround")
    set_verification_status("not_requested")
    set_recoverability("not_applicable")
    if is_dry_run():
        output(
            {
                "action": "fairlight.adr.info",
                "dry_run": True,
                "limit": int(limit),
                "runtime_read_called": False,
                "route": "db_workaround",
                "target": "current_project_adr_schema_probe",
                "read_scope": "adr_schema_probe_and_setup_signals",
                "cue_list_supported": False,
                "cue_mutation_supported": False,
                "record_supported": False,
                "take_management_supported": False,
                "preflight_command": "cutagent fairlight adr info --json",
            },
            title="Fairlight ADR Info Plan",
        )
        return
    conn = get_connection(require_project=True, require_timeline=False)
    data = fairlight_ops.read_fairlight_adr_info_db(conn, limit=limit)
    output(data, title="Fairlight ADR Info")


@adr_app.command("cue-list")
@handle_errors
def adr_cue_list():
    """Report Fairlight ADR cue list API availability."""
    enforce_mutation_policy("fairlight.adr", intended_engine="not_available", mutating=False)
    _raise_fairlight_native_unavailable(
        capability_id="fairlight.adr",
        workflow="Fairlight ADR cue list",
        requested={"action": "cue-list"},
        required_native_api=[
            "list ADR cues",
            "create/edit/delete ADR cues",
            "read ADR take metadata",
        ],
        api_note="The Fairlight ADR panel and cue/take database are not exposed by the DaVinci Resolve scripting API.",
        workaround="Manage ADR cues in DaVinci Resolve. Export cue sheets manually if downstream processing is required.",
        extra_details=_FAIRLIGHT_ADR_DB_BLOCKER_EVIDENCE,
    )


@adr_app.command("record")
@handle_errors
def adr_record(
    cue: str | None = typer.Option(None, "--cue", help="ADR cue identifier/name to record"),
):
    """Report Fairlight ADR recording API availability."""
    enforce_mutation_policy("fairlight.adr", intended_engine="not_available", mutating=False)
    _raise_fairlight_native_unavailable(
        capability_id="fairlight.adr",
        workflow="Fairlight ADR recording",
        requested={"cue": cue},
        required_native_api=[
            "start ADR recording for a cue",
            "configure beeps/streamers/prompts",
            "read and select ADR takes",
        ],
        api_note="ADR recording workflows are not exposed by the DaVinci Resolve scripting API.",
        workaround="Record ADR in DaVinci Resolve and use cutagent for supported post-recording clip operations.",
        extra_details=_FAIRLIGHT_ADR_DB_BLOCKER_EVIDENCE,
    )


sound_library_app = typer.Typer(help="Fairlight Sound Library operations.")
app.add_typer(sound_library_app, name="sound-library")

_SOUND_LIBRARY_REQUIRED_TABLES = (
    "FLAssetBaseClip",
    "FLAssetBaseFile",
    "FLAssetBaseContainer",
)
_SOUND_LIBRARY_SEARCH_COLUMNS = (
    "clip.name",
    "clip.filename",
    "clip.category",
    "clip.description",
    "clip.user1",
    "clip.user2",
    "clip.user3",
    "clip.user4",
    "library_file.filename",
    "library_file.path",
    "library_file.file_comment",
    "container.description",
    "container.path",
)
_SOUND_LIBRARY_EDIT_COLUMNS = (
    "ed_mark",
    "ed_wave",
    "ed_wave2",
    "ed_start",
    "ed_stop",
    "ed_hook",
    "ed_sync",
    "ed_fadein",
    "ed_fadeout",
    "ed_pan0",
    "ed_pan1",
    "ed_panin",
    "ed_eqin",
    "ed_level_db",
    "ed_fin",
    "ed_fout",
    "ed_fia",
    "ed_fis",
    "ed_foa",
    "ed_fos",
    "eq_band0_freq",
    "eq_band0_gain",
    "eq_band0_qshelf",
    "eq_band1_freq",
    "eq_band1_gain",
    "eq_band1_qshelf",
    "eq_band2_freq",
    "eq_band2_gain",
    "eq_band2_qshelf",
    "eq_band3_freq",
    "eq_band3_gain",
    "eq_band3_qshelf",
    "ed_text",
)
_SOUND_LIBRARY_AUDIO_EXTENSIONS = frozenset(
    {
        ".aac",
        ".aif",
        ".aiff",
        ".flac",
        ".m4a",
        ".mp3",
        ".mp4",
        ".mov",
        ".ogg",
        ".wav",
    }
)
_SOUND_LIBRARY_DATABASE_ALIASES = {
    "project": "project",
    "current": "project",
    "current_project": "project",
    "current-project": "project",
    "project_db": "project",
    "project-db": "project",
    "user": "user",
    "user_db": "user",
    "user-db": "user",
    "local": "user",
    "local_database": "user",
    "local-database": "user",
}
