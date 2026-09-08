from __future__ import annotations

@app.command("solo-restore")
@handle_errors
def solo_restore(
    states_json: str = typer.Option(..., "--states-json", help="JSON previous_states array from fairlight solo"),
):
    """Restore audio track enabled states captured by fairlight solo."""
    enforce_mutation_policy("fairlight.solo", intended_engine="api_native", mutating=not is_dry_run())
    try:
        states = json.loads(states_json)
    except json.JSONDecodeError as exc:
        raise ValidationError(
            "--states-json must be a JSON array.",
            details={"states_json": states_json, "error": str(exc)},
            recoverability="not_applicable",
        ) from exc
    if not isinstance(states, list):
        raise ValidationError(
            "--states-json must decode to a JSON array.",
            details={"states_json": states_json},
            recoverability="not_applicable",
        )
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            {
                "action": "fairlight.solo_restore",
                "would_restore": True,
                "dry_run": True,
                "track_type": "audio",
                "states": states,
            },
            title="Fairlight Solo Restore Plan",
        )
        return
    conn = get_connection(require_timeline=True)
    data = fairlight_ops.restore_audio_track_states(conn, states)
    output(data, title="Fairlight Solo Restore")


@app.command("lock")
@handle_errors
def lock(index: int = typer.Argument(...)):
    """Lock an audio track."""
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
                "action": "fairlight.lock",
                "would_lock": True,
                "dry_run": True,
                "track_type": "audio",
                "index": index,
                "requires_existing_track": True,
            },
            title="Fairlight Lock Plan",
        )
        return
    conn = get_connection(require_timeline=True)
    _validate_audio_track_index(conn, index)
    fairlight_ops.lock_audio_track(conn, index)
    success(f"Locked audio track {index}.")


@app.command("unlock")
@handle_errors
def unlock(index: int = typer.Argument(...)):
    """Unlock an audio track."""
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
                "action": "fairlight.unlock",
                "would_unlock": True,
                "dry_run": True,
                "track_type": "audio",
                "index": index,
                "requires_existing_track": True,
            },
            title="Fairlight Unlock Plan",
        )
        return
    conn = get_connection(require_timeline=True)
    _validate_audio_track_index(conn, index)
    fairlight_ops.unlock_audio_track(conn, index)
    success(f"Unlocked audio track {index}.")


@app.command("items")
@handle_errors
def items(
    index: int = typer.Argument(..., help="Track index"),
):
    """List audio clips on a track."""
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            {
                "action": "fairlight.items",
                "dry_run": True,
                "runtime_read_called": False,
                "target": {"kind": "audio_track", "track_type": "audio", "index": index},
                "route": "api_native",
                "native_api": 'Timeline.GetItemListInTrack("audio", index)',
                "read_scope": "audio_track_items",
                "preflight_command": f"cutagent fairlight items {index} --json",
            },
            title=f"Audio Track {index} Plan",
        )
        return
    conn = get_connection(require_timeline=True)
    _validate_audio_track_index(conn, index)
    rows = fairlight_ops.list_audio_track_items(conn, index)
    output(rows, columns=[("name", "Name"), ("start", "Start"), ("end", "End")],
           title=f"Audio Track {index}")


@app.command("info")
@handle_errors
def track_info(
    index: int = typer.Argument(..., help="Track index"),
):
    """Show audio track details."""
    enforce_mutation_policy("fairlight.track_info", intended_engine="db_workaround", mutating=False)
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            {
                "action": "fairlight.info",
                "dry_run": True,
                "runtime_read_called": False,
                "target": {"kind": "audio_track", "track_type": "audio", "index": index},
                "route": "db_workaround",
                "native_api": (
                    'Timeline.GetTrackName("audio", index)/GetTrackSubType/'
                    "GetIsTrackEnabled/GetIsTrackLocked/GetItemListInTrack"
                ),
                "db_readbacks": ["mixer", "display", "bus_labels"],
                "read_scope": "audio_track_detail",
                "preflight_command": f"cutagent fairlight info {index} --json",
            },
            title=f"Audio Track {index} Plan",
        )
        return
    conn = get_connection(require_timeline=True)
    data = fairlight_ops.get_audio_track_info(conn, index)
    if data.get("source") == "disk_project_db":
        set_verification_status("verified")
    else:
        set_verification_status("not_requested")
    set_recoverability("not_applicable")
    if data.get("mixer") or data.get("display") or data.get("bus_readback"):
        set_execution_engine("db_workaround")
    output(data, title=f"Audio Track {index}")


preset_app = typer.Typer(help="Fairlight preset operations.")
app.add_typer(preset_app, name="preset")

_FAIRLIGHT_PRESET_APPLY_READINESS_EVIDENCE = {
    "available_native_readback": "Resolve.GetFairlightPresets() via `fairlight preset list --json`",
    "native_apply_candidates": [
        "Project.ApplyFairlightPresetToCurrentTimeline(name)",
        "Timeline.ApplyFairlightPreset(name)",
    ],
    "preset_model_evidence": {
        "catalog_read_supported": True,
        "apply_guarded_by_catalog_readback": True,
        "mutating_apply_called_without_catalog_match": False,
        "positive_apply_requires_available_preset": True,
        "local_store_recheck_2026_06_19": {
            "config_user_presets_xml": "empty <PresetList/>",
            "automix_default_dat_exposed_by_native_catalog": False,
            "native_import_or_create_api_found": False,
        },
        "gui_preset_library_recheck_2026_06_19": {
            "gui_visible_equalizer_presets": [
                "Dialog - Clean add hi end",
                "Dialog - Female lav mic fixer",
                "Dialog - Male lav finisher",
                "Dialog - Male",
                "General - Telephone effect",
                "Music Master - Top end Boost",
            ],
            "gui_visible_presets_exposed_by_resolve_get_fairlight_presets": False,
            "project_apply_gui_visible_preset_result": False,
            "timeline_apply_fairlight_preset_available": False,
            "project_db_changed_after_direct_native_apply_probe": False,
        },
        "gui_equalizer_apply_recheck_2026_06_20": {
            "gui_visible_equalizer_preset": "Dialog - Clean add hi end",
            "native_catalog_after_gui_apply": [],
            "public_apply_gui_visible_name_result": "READINESS_FAILED",
            "changed_db_tables_after_gui_apply": ["SM_Config", "SM_Project", "Sm2Sequence"],
            "changed_payload": "Sm2Sequence.FieldsBlob.FLStudioModelBA",
            "decompressed_model_diff": {
                "new_string_tokens": [],
                "diff_byte_count": 69,
                "diff_group_count": 6,
            },
            "safe_db_apply_route_found": False,
            "readback_model_found": False,
        },
    },
    "readiness_note": (
        "Fairlight preset apply is only attempted after native preset catalog readback reports the requested "
        "preset name. An empty catalog or missing name is treated as readiness failure, not as permission to "
        "guess or call the mutating apply API."
    ),
}


@preset_app.command("list")
@handle_errors
def preset_list():
    """List available Fairlight presets."""
    enforce_mutation_policy("fairlight.preset_list", intended_engine="api_native", mutating=False)
    set_execution_engine("api_native")
    set_verification_status("not_requested")
    set_recoverability("not_applicable")
    if is_dry_run():
        output(
            {
                "action": "fairlight.preset.list",
                "dry_run": True,
                "runtime_read_called": False,
                "route": "api_native",
                "native_readback": "Resolve.GetFairlightPresets()",
                "read_scope": "fairlight_preset_catalog",
                "apply_precondition": "fairlight_preset_catalog_match",
                "positive_apply_requires_available_preset": True,
                "preflight_command": "cutagent fairlight preset list --json",
            },
            title="Fairlight Preset List Plan",
        )
        return
    conn = get_connection(require_project=True)
    rows = fairlight_ops.list_fairlight_presets(conn)
    output(rows, columns=[("index", "#"), ("name", "Name")], title="Fairlight Presets")


@preset_app.command("apply")
@handle_errors
def preset_apply(
    name: str = typer.Argument(..., help="Fairlight preset name"),
):
    """Apply a Fairlight preset to the current timeline."""
    enforce_mutation_policy("fairlight.preset", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            {
                "action": "fairlight.preset.apply",
                "would_apply": True,
                "dry_run": True,
                "name": name,
                "target": "current_timeline",
                "requires_available_preset": True,
                **_FAIRLIGHT_PRESET_APPLY_READINESS_EVIDENCE,
            },
            title="Fairlight Preset Apply Plan",
        )
        return
    conn = get_connection(require_timeline=True)
    presets = fairlight_ops.list_fairlight_presets(conn)
    if not presets:
        raise ReadinessFailed(
            "No Fairlight presets are available.",
            details={
                "requested_preset": name,
                "available_presets": [],
                "precondition": "fairlight_preset_available",
                **_FAIRLIGHT_PRESET_APPLY_READINESS_EVIDENCE,
            },
        )
    preset_names = {str(preset["name"]) for preset in presets}
    if name not in preset_names:
        raise ValidationError(
            "Fairlight preset not found.",
            details={
                "requested_preset": name,
                "available_presets": presets,
                "precondition": "fairlight_preset_catalog_match",
                **_FAIRLIGHT_PRESET_APPLY_READINESS_EVIDENCE,
            },
        )
    data = fairlight_ops.apply_fairlight_preset(conn, name)
    output(data, title="Fairlight Preset")


voice_isolation_app = typer.Typer(help="Timeline voice isolation operations.")
app.add_typer(voice_isolation_app, name="voice-isolation")


@voice_isolation_app.command("get")
@handle_errors
def voice_isolation_get(
    track: int = typer.Argument(..., help="Audio track index"),
):
    """Get voice isolation state for an audio track."""
    set_capability_context("fairlight.timeline_voice_isolation", "supported")
    set_execution_engine("api_native")
    set_verification_status("not_requested")
    set_recoverability("not_applicable")
    conn = get_connection(require_timeline=True)
    output(timeline_ops.get_timeline_voice_isolation(conn, track), title="Voice Isolation")


@voice_isolation_app.command("set")
@handle_errors
def voice_isolation_set(
    track: int = typer.Argument(..., help="Audio track index"),
    enable: bool = typer.Option(True, "--enable/--disable", help="Enable or disable voice isolation"),
    amount: float = typer.Option(100.0, "--amount", help="Voice isolation amount"),
):
    """Set voice isolation state for an audio track."""
    set_capability_context("fairlight.timeline_voice_isolation", "supported")
    set_execution_engine("api_native")
    set_recoverability("manual")
    enforce_mutation_policy("fairlight.timeline_voice_isolation", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        set_verification_status("not_requested")
        output(
            {
                "action": "fairlight.voice_isolation.set",
                "would_set": True,
                "dry_run": True,
                "track": int(track),
                "state": {"isEnabled": bool(enable), "amount": int(amount)},
                "native_api": {
                    "write": "Timeline.SetVoiceIsolationState(trackIndex, state)",
                    "readback": "Timeline.GetVoiceIsolationState(trackIndex)",
                },
                "verification": "post_write_readback_required",
            },
            title="Voice Isolation Plan",
        )
        return
    conn = get_connection(require_timeline=True)
    output(timeline_ops.set_timeline_voice_isolation(conn, track, enabled=enable, amount=amount), title="Voice Isolation")


@app.command("insert")
@handle_errors
def insert_audio(
    media_path: str = typer.Argument(..., help="Audio file path"),
    start_offset_in_samples: int = typer.Option(0, "--start-offset-samples", help="Sample offset within source media"),
    duration_in_samples: int = typer.Option(0, "--duration-samples", help="Duration to insert in samples (0 = full available duration)"),
):
    """Insert audio at the playhead on the current Fairlight track."""
    enforce_mutation_policy("fairlight.insert", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            {
                "action": "fairlight.insert",
                "would_insert": True,
                "dry_run": True,
                "media_path": media_path,
                "start_offset_in_samples": int(start_offset_in_samples),
                "duration_in_samples": int(duration_in_samples),
                "target": "current_fairlight_track_at_playhead",
                "requires_current_fairlight_track": True,
            },
            title="Fairlight Insert Plan",
        )
        return
    conn = get_connection(require_timeline=True)
    data = fairlight_ops.insert_audio_to_current_track(
        conn,
        media_path,
        start_offset_in_samples=start_offset_in_samples,
        duration_in_samples=duration_in_samples,
    )
    output(data, title="Fairlight Insert")


export_app = typer.Typer(help="Fairlight file export operations.")
app.add_typer(export_app, name="export")


@export_app.command("audio")
@handle_errors
def export_audio(
    output_path: str = typer.Argument(..., help="Output audio file path"),
    format: str = typer.Option("Wave", "--format", help="Render format"),
    codec: str = typer.Option("Linear PCM", "--codec", help="Audio codec"),
    bitdepth: int = typer.Option(16, "--bitdepth", help="Audio bit depth"),
    samplerate: int = typer.Option(48000, "--samplerate", help="Audio sample rate"),
):
    """Export the current timeline audio mix through DaVinci Resolve's native render API."""
    enforce_mutation_policy(
        "fairlight.audio_export",
        intended_engine="api_native",
        mutating=not is_dry_run(),
    )
    requested = {
        "output_path": str(Path(output_path).expanduser()),
        "format": format,
        "codec": codec,
        "bitdepth": int(bitdepth),
        "samplerate": int(samplerate),
        "render_route": "deliver_audio_only",
        "native_api": [
            "Project.SetCurrentRenderFormatAndCodec",
            "Project.SetRenderSettings",
            "Project.AddRenderJob",
            "Project.StartRendering",
        ],
    }
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            mutation_payload(
                action="fairlight.export.audio",
                target={"kind": "file", "path": requested["output_path"]},
                changed=False,
                dry_run=True,
                runtime_write_called=False,
                **requested,
            ),
            title="Fairlight Audio Export Plan",
        )
        return

    conn = get_connection(require_timeline=True)
    result_path = render_engine.render_audio(
        conn,
        output_path,
        format,
        codec,
        bitdepth,
        samplerate,
        None,
    )
    set_verification_status("verified")
    output(
        mutation_payload(
            action="fairlight.export.audio",
            target={"kind": "file", "path": result_path},
            changed=True,
            verification_status="verified",
            output_path=result_path,
            render_route="deliver_audio_only",
            delegated_command="render audio",
            message=f"Fairlight audio exported to: {result_path}",
        ),
        title="Fairlight Audio Export",
    )


channel_map_app = typer.Typer(help="Fairlight audio channel mapping operations.")
app.add_typer(channel_map_app, name="channel-map")


_FAIRLIGHT_CHANNEL_MAPPING_WRITE_BLOCKER_EVIDENCE = {
    "verified_write_subset": {
        "command": "cutagent fairlight channel-map set --clip <timeline-item> --mapping-json <stereo track_mapping.1>",
        "route": "db_workaround",
        "db_table": "Sm2TiItem",
        "db_column": "VirtualAudioTrackBA",
        "storage": "verified_stereo_virtual_audio_track_marker",
        "scope": "single timeline item track_mapping.1 channel_idx [1], [2], or [1,2]; mute=false; type=stereo; embedded_audio_channels=2",
        "resolve_21_live_recheck": {
            "runtime": "DaVinci Resolve 21.0.0.48 Free",
            "timeline": "CUTAGENT_CHANNEL_MAP_FRESH_094451",
            "fixture": "/tmp/cutagent_channel_map_fresh_probe_20260620_094451/media/channel_map_lr_440_880_6s.wav",
            "set_artifact": "/tmp/cutagent_channel_map_fresh_probe_20260620_094451/07_set_right_channel.json",
            "readback_artifact": "/tmp/cutagent_channel_map_fresh_probe_20260620_094451/08_channel_map_after_right.json",
            "render_analysis": "/tmp/cutagent_channel_map_fresh_probe_20260620_094451/13_channel_map_render_analysis.json",
            "restore_artifact": "/tmp/cutagent_channel_map_fresh_probe_20260620_094451/11_restore_stereo_mapping.json",
            "restore_readback_artifact": "/tmp/cutagent_channel_map_fresh_probe_20260620_094451/12_channel_map_after_restore.json",
            "set_mapping": {"track_mapping": {"1": {"channel_idx": [2], "mute": False, "type": "stereo"}}},
            "restore_mapping": {"track_mapping": {"1": {"channel_idx": [1, 2], "mute": False, "type": "stereo"}}},
            "verification_status": "verified",
            "render_verification": {
                "clean_left_dominant_hz": 440,
                "clean_right_dominant_hz": 880,
                "right_mapping_output_dominant_hz": 880,
                "right_mapping_output_channels": 2,
                "diff_rms": 28947.701569620822,
                "identical_prefix": False,
            },
        },
    },
    "negative_four_channel_mono_probe": {
        "runtime": "DaVinci Resolve 21.0.0.48 Free",
        "timeline": "CUTAGENT_CHANNEL_MAP_4CH_PROBE_20260619",
        "fixture": "/tmp/cutagent_channel_map_multich_probe_20260619/four_channel_220_330_440_550.wav",
        "readback_artifact": "/tmp/cutagent_channel_map_multich_probe_20260619/05_channel_map_clip_4ch.json",
        "marker_probe_artifacts": [
            "/tmp/cutagent_channel_map_multich_probe_20260619/22_temp_4ch_mono_marker_patch.json",
            "/tmp/cutagent_channel_map_multich_probe_20260619/24_temp_4ch_mono_marker_set_3.json",
            "/tmp/cutagent_channel_map_multich_probe_20260619/24_temp_4ch_mono_marker_set_4.json",
            "/tmp/cutagent_channel_map_multich_probe_20260619/25_temp_4ch_mono_marker_restore_after_34.json",
        ],
        "native_readback_result": "marker edits can make TimelineItem.GetSourceAudioChannelMapping() report channel_idx [2], [3], or [4]",
        "public_route_probe": "/tmp/cutagent_channel_map_multich_probe_20260619/30_public_set_4ch_to_ch4.json",
        "render_analysis": "/tmp/cutagent_channel_map_multich_probe_20260619/34_ch1_vs_ch4_frequency_analysis.json",
        "render_result": "not_promoted_after channel 4 render was silent despite native readback reporting channel_idx [4]",
        "restore_artifact": "/tmp/cutagent_channel_map_multich_probe_20260619/35_public_restore_4ch_to_ch1.json",
        "final_readback_artifact": "/tmp/cutagent_channel_map_multich_probe_20260619/36_public_read_after_restore_ch1.json",
    },
    "available_read_routes": [
        {
            "command": "cutagent fairlight channel-map clip <clip> --json",
            "native_api": "TimelineItem.GetSourceAudioChannelMapping()",
            "source": "timeline_item",
        },
        {
            "command": "cutagent fairlight channel-map media <clip> --json",
            "native_api": "MediaPoolItem.GetAudioMapping()",
            "source": "media_pool_item",
        },
    ],
    "native_probe_evidence": {
        "runtime": "DaVinci Resolve 20.3.2.9 Free",
        "transport": "embedded_lua_http_poll",
        "official_scripting_doc_evidence": {
            "source": "DaVinci Resolve Developer/Scripting README.txt",
            "documented_read_methods": [
                "MediaPoolItem.GetAudioMapping()",
                "TimelineItem.GetSourceAudioChannelMapping()",
            ],
            "documented_write_methods": [],
            "audio_mapping_section_scope": "readback JSON format only",
        },
        "read_methods_supported": [
            "TimelineItem.GetSourceAudioChannelMapping()",
            "MediaPoolItem.GetAudioMapping()",
        ],
        "write_method_candidates_not_available": [
            "TimelineItem.SetSourceAudioChannelMapping(...)",
            "MediaPoolItem.SetAudioMapping(...)",
        ],
        "mutating_candidates_not_called": [
            "TimelineItem.SetSourceAudioChannelMapping(...)",
            "MediaPoolItem.SetAudioMapping(...)",
        ],
        "probe_result": "read methods are available; write method candidates are not available in the verified runtime",
        "write_supported": False,
        "set_supported": False,
        "readback_after_write_supported": False,
    },
    "db_schema_evidence": {
        "source": "local DaVinci Resolve 20 Free Project.db schema probes",
        "sampled_project_db_count": 5,
        "read_scope": "negative_channel_mapping_write_schema_probe",
        "native_readback_routes": [
            "TimelineItem.GetSourceAudioChannelMapping()",
            "MediaPoolItem.GetAudioMapping()",
        ],
        "candidate_audio_metadata_fields_seen": [
            "BtAudioInfo.TracksBA",
            "BtAudioTrackInfo.ChannelCount",
            "Sm2MpMedia.EmbeddedAudio",
            "Sm2MpMedia.VirtualAudioTracksBA",
            "Sm2TiItem.VirtualAudioTrackBA",
            "Sm2MpAudioRef.ChannelIdx",
            "Sm2MpAudioRef.TrackIdx",
        ],
        "candidate_audio_ref_tables_seen": [
            "BtAudioInfo",
            "BtAudioTrackInfo",
            "Sm2MpAudioRef",
            "Sm2MpAudioTrack",
            "SM_AudioSettings",
        ],
        "channel_mapping_named_table_found_in_samples": False,
        "timeline_item_source_mapping_write_schema_found_in_samples": False,
        "media_pool_item_mapping_write_schema_found_in_samples": False,
        "mute_channel_index_type_write_schema_found_in_samples": False,
        "post_write_readback_route_found_in_samples": False,
        "candidate_fields_are_metadata_not_verified_write_route": True,
    },
    "blocker_note": (
        "Timeline-item stereo VirtualAudioTrackBA writes have a verified narrow DB route through "
        "`--clip`. Four-channel mono marker probes changed native channel-map readback but rendered silence "
        "for channel 4, so they are not promoted. Media Pool item writes, multi-track mapping, mute changes, non-stereo track types, "
        "and arbitrary channel patch matrices remain blocked because no native write API or verified "
        "Project.db route has been mapped for those scopes."
    ),
}


def _fairlight_channel_mapping_payload(*, source: str, native_api: str, data: dict[str, Any]) -> dict[str, Any]:
    raw_mapping = data.get("mapping")
    mapping = raw_mapping
    parse_error = None
    if isinstance(raw_mapping, str):
        try:
            mapping = json.loads(raw_mapping)
        except json.JSONDecodeError as exc:
            parse_error = {"line": exc.lineno, "column": exc.colno, "message": exc.msg}
    payload: dict[str, Any] = {
        "action": "fairlight.channel_map.read",
        "source": source,
        "clip": data.get("clip"),
        "mapping": mapping,
        "native_api": native_api,
    }
    if isinstance(raw_mapping, str):
        payload["raw_mapping"] = raw_mapping
    if parse_error:
        payload["parse_error"] = parse_error
    return payload


def _fairlight_channel_mapping_dry_run_payload(*, source: str, native_api: str, clip: str | None) -> dict[str, Any]:
    command_clip = clip or "<current>"
    command_name = "clip" if source == "timeline_item" else "media"
    return {
        "action": "fairlight.channel_map.read",
        "dry_run": True,
        "runtime_read_called": False,
        "route": "api_native",
        "source": source,
        "clip": clip,
        "native_api": native_api,
        "read_scope": "audio_channel_mapping",
        "write_supported": False,
        "preflight_command": f"cutagent fairlight channel-map {command_name} {command_clip} --json",
    }


@channel_map_app.command("clip")
@handle_errors
def channel_map_clip(
    clip_arg: str | None = typer.Argument(None, help="Timeline clip name; current clip when omitted"),
    clip_option: str | None = typer.Option(None, "--clip", help="Timeline clip name; current clip when omitted"),
):
    """Read source audio channel mapping for a timeline item."""
    from ..core import clip_ops

    if clip_arg and clip_option and clip_arg != clip_option:
        raise ValidationError(
            "Timeline clip selector was provided twice with different values.",
            details={"clip_arg": clip_arg, "clip_option": clip_option},
            recoverability="not_applicable",
        )
    clip = clip_option or clip_arg
    enforce_mutation_policy("fairlight.channel_mapping_read", intended_engine="api_native", mutating=False)
    set_execution_engine("api_native")
    set_verification_status("not_requested")
    set_recoverability("not_applicable")
    native_api = "TimelineItem.GetSourceAudioChannelMapping()"
    if is_dry_run():
        output(
            _fairlight_channel_mapping_dry_run_payload(
                source="timeline_item",
                native_api=native_api,
                clip=clip,
            ),
            title="Fairlight Channel Map Plan",
        )
        return
    conn = get_connection(require_timeline=True)
    data = clip_ops.get_source_audio_mapping(conn, clip)
    output(
        _fairlight_channel_mapping_payload(
            source="timeline_item",
            native_api=native_api,
            data=data,
        ),
        title="Fairlight Channel Map",
    )


@channel_map_app.command("media")
@handle_errors
def channel_map_media(
    clip: str = typer.Argument(..., help="Media Pool clip name"),
):
    """Read audio channel mapping for a Media Pool item."""
    from ..core import media_pool

    enforce_mutation_policy("fairlight.channel_mapping_read", intended_engine="api_native", mutating=False)
    set_execution_engine("api_native")
    set_verification_status("not_requested")
    set_recoverability("not_applicable")
    native_api = "MediaPoolItem.GetAudioMapping()"
    if is_dry_run():
        output(
            _fairlight_channel_mapping_dry_run_payload(
                source="media_pool_item",
                native_api=native_api,
                clip=clip,
            ),
            title="Fairlight Channel Map Plan",
        )
        return
    conn = get_connection(require_project=True)
    data = media_pool.get_audio_mapping(conn, clip)
    output(
        _fairlight_channel_mapping_payload(
            source="media_pool_item",
            native_api=native_api,
            data=data,
        ),
        title="Fairlight Channel Map",
    )


@channel_map_app.command("set")
@handle_errors
def channel_map_set(
    clip: str | None = typer.Option(None, "--clip", help="Timeline clip name or item id"),
    media: str | None = typer.Option(None, "--media", help="Media Pool clip name"),
    mapping_json: str | None = typer.Option(None, "--mapping-json", help="Requested channel mapping JSON"),
):
    """Set the verified Fairlight timeline-item audio channel mapping subset."""
    if media is None and clip is not None and mapping_json is not None:
        enforce_mutation_policy(
            "fairlight.channel_mapping_write",
            intended_engine="db_workaround",
            mutating=not is_dry_run(),
        )
        try:
            mapping = json.loads(mapping_json)
        except json.JSONDecodeError as exc:
            raise ValidationError(
                "--mapping-json must be valid JSON.",
                details={"mapping_json": mapping_json, "line": exc.lineno, "column": exc.colno, "message": exc.msg},
                recoverability="not_applicable",
            ) from exc
        normalized_mapping = fairlight_ops._normalize_timeline_channel_mapping_request(mapping)
        if is_dry_run():
            set_verification_status("not_requested")
            set_recoverability("not_applicable")
            output(
                mutation_payload(
                    action="fairlight.channel_map.set",
                    target={"kind": "timeline_item", "clip": clip},
                    changed=False,
                    dry_run=True,
                    runtime_write_called=False,
                    mapping=normalized_mapping,
                    route="db_native",
                    db_table="Sm2TiItem",
                    db_column="VirtualAudioTrackBA",
                    storage="verified_stereo_virtual_audio_track_marker",
                    verified_set_scope="single_timeline_item_stereo_channel_idx_1_2_or_single_source_duplicate",
                    verification_status="not_requested",
                    preflight_command=f"cutagent fairlight channel-map clip {shlex.quote(str(clip))} --json",
                ),
                title="Fairlight Channel Map Set Plan",
            )
            return
        conn = get_connection(require_timeline=True)
        data = fairlight_ops.set_timeline_item_channel_mapping_db(
            conn,
            clip=str(clip),
            mapping=normalized_mapping,
        )
        output(data, title="Fairlight Channel Map Set")
        return

    enforce_mutation_policy("fairlight.channel_mapping_write", intended_engine="db_workaround", mutating=False)
    _raise_fairlight_native_unavailable(
        capability_id="fairlight.channel_mapping_write",
        workflow="Fairlight channel mapping writes",
        requested={"clip": clip, "media": media, "mapping_json": mapping_json},
        required_native_api=[
            "write Media Pool item audio channel mapping",
            "write timeline item source audio channel mapping",
            "set mute/channel index/type for individual mapped tracks",
        ],
        api_note=(
            "DaVinci Resolve exposes audio channel mapping read APIs "
            "MediaPoolItem.GetAudioMapping() and TimelineItem.GetSourceAudioChannelMapping(), "
            "but not channel mapping write APIs."
        ),
        workaround="Set channel mapping in Clip Attributes inside DaVinci Resolve, then verify with `cutagent fairlight channel-map clip` or `media`.",
        extra_details=_FAIRLIGHT_CHANNEL_MAPPING_WRITE_BLOCKER_EVIDENCE,
    )


bus_app = typer.Typer(help="Fairlight bus routing operations.")
app.add_typer(bus_app, name="bus")


_FAIRLIGHT_SLOT_BUS_NATIVE_PROBE_CONTEXT = {
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


_FAIRLIGHT_BUS_ROUTING_NATIVE_PROBE_EVIDENCE = {
    **_FAIRLIGHT_SLOT_BUS_NATIVE_PROBE_CONTEXT,
    "candidate_methods_not_available": [
        "Resolve.GetFairlightBuses()",
        "Resolve.GetAudioBuses()",
        "Project.GetFairlightBuses()",
        "Project.GetAudioBuses()",
        "Timeline.GetBusList()",
        "Timeline.GetFairlightBusList()",
        "Timeline.GetAudioBusList()",
        "Timeline.GetBusLevel('Bus 1')",
        "Timeline.GetBusFader('Bus 1')",
        "Timeline.GetBusPan('Bus 1')",
        "Timeline.GetBusRouting('Bus 1')",
        "Timeline.GetFlexBusGraph()",
        "Timeline.GetTrackOutputBus('audio', 1)",
        "Timeline.GetTrackRouting('audio', 1)",
        "Timeline.GetTrackBus('audio', 1)",
        "Timeline.GetTrackOutput('audio', 1)",
        "Timeline.GetMainBus()",
    ],
    "mutating_candidates_not_called": [
        "Timeline.SetTrackOutputBus('audio', 1, ...)",
        "Timeline.AssignTrackToBus('audio', 1, ...)",
        "Timeline.SetBusLevel('Bus 1', ...)",
        "Timeline.SetBusPan('Bus 1', ...)",
        "Timeline.CreateBus(...)",
        "Timeline.SetFlexBusRouting(...)",
        "Timeline.SetTrackRouting('audio', 1, ...)",
    ],
    "probe_result": "bus/FlexBus routing getters returned method_not_available; bus routing and fader/pan mutation candidates were not called",
    "bus_native_read_supported": False,
    "bus_native_assignment_supported": False,
    "non_main_bus_native_fader_supported": False,
    "flexbus_native_graph_supported": False,
}


_FAIRLIGHT_PANNER_NATIVE_PROBE_EVIDENCE = {
    **_FAIRLIGHT_SLOT_BUS_NATIVE_PROBE_CONTEXT,
    "candidate_methods_not_available": [
        "Timeline.GetTrackPan('audio', 1)",
        "Timeline.GetTrackPanner('audio', 1)",
        "Timeline.GetTrackPan3D('audio', 1)",
        "Timeline.GetTrackPanner3D('audio', 1)",
        "Timeline.GetTrackSurroundPan('audio', 1)",
        "Timeline.GetTrackPannerProperties('audio', 1)",
        "Timeline.GetTrackPanAngle('audio', 1)",
        "Timeline.GetTrackPanSpread('audio', 1)",
        "Timeline.GetTrackPanDivergence('audio', 1)",
        "TimelineItem.GetAudioPan()",
        "TimelineItem.GetPanner()",
        "TimelineItem.GetPan3D()",
        "TimelineItem.GetPanner3D()",
        "TimelineItem.GetSurroundPan()",
        "TimelineItem.GetPannerProperties()",
    ],
    "mutating_candidates_not_called": [
        "Timeline.SetTrackPan('audio', 1, ...)",
        "Timeline.SetTrackPan3D('audio', 1, ...)",
        "Timeline.SetTrackPanner3D('audio', 1, ...)",
        "Timeline.SetTrackSurroundPan('audio', 1, ...)",
        "Timeline.SetTrackPanAngle('audio', 1, ...)",
        "Timeline.SetTrackPanSpread('audio', 1, ...)",
        "Timeline.SetTrackPanDivergence('audio', 1, ...)",
        "TimelineItem.SetAudioPan(...)",
        "TimelineItem.SetPan3D(...)",
        "TimelineItem.SetPanner3D(...)",
        "TimelineItem.SetSurroundPan(...)",
    ],
    "probe_result": "track and timeline-item panner getters returned method_not_available; panner mutation candidates were not called",
    "track_panner_native_read_supported": False,
    "clip_panner_native_read_supported": False,
    "panner_3d_native_read_supported": False,
    "panner_native_write_supported": False,
}


_FAIRLIGHT_PLUGIN_SLOT_NATIVE_PROBE_EVIDENCE = {
    **_FAIRLIGHT_SLOT_BUS_NATIVE_PROBE_CONTEXT,
    "resolve_21_embedded_recheck": {
        "runtime": "DaVinci Resolve 21.0.0.48 Free",
        "transport": "embedded_lua_http_poll",
        "probe_project": "CUTAGENT_FAIRLIGHT_AUDIT_MEDIA_20260613_003908",
        "probe_timeline": "AUDIT_MEDIA_FAIRLIGHT_24FPS",
        "evidence_file": "/tmp/cutagent_fairlightfx_live_method_probe_connection_20260618.json",
        "baseline_verified_methods": [
            "Project.GetName()",
            "Timeline.GetName()",
            "Timeline.GetItemListInTrack('audio', 1)",
        ],
        "candidate_methods_not_available": [
            "Resolve.GetFairlightEffectList()",
            "Resolve.GetFairlightEffects()",
            "Resolve.GetFairlightPlugInList()",
            "Resolve.GetFairlightPluginList()",
            "Project.GetFairlightEffectList()",
            "Project.GetFairlightEffects()",
            "Project.GetFairlightPlugInList()",
            "Project.GetFairlightPluginList()",
            "Timeline.GetFairlightEffectList()",
            "Timeline.GetFairlightEffects()",
            "Timeline.GetFairlightPlugInList()",
            "Timeline.GetFairlightPluginList()",
            "Timeline.GetTrackEffects('audio', 1)",
            "Timeline.GetTrackPluginList('audio', 1)",
            "Timeline.GetTrackPluginParameters('audio', 1, 1)",
            "Timeline.GetBusEffects('Main')",
            "Timeline.GetBusPluginList('Main')",
            "TimelineItem.GetClipEffects()",
            "TimelineItem.GetFairlightEffects()",
            "TimelineItem.GetTrackEffects()",
            "TimelineItem.GetTrackPluginList()",
            "TimelineItem.GetTrackPluginParameters()",
        ],
        "probe_result": "DaVinci Resolve 21 embedded runtime returned method_not_available for plugin/effect slot getters on DaVinci Resolve, Project, Timeline, and TimelineItem objects.",
        "track_bus_plugin_native_read_supported": False,
        "clip_plugin_native_read_supported": False,
    },
    "candidate_methods_not_available": [
        "Resolve.GetAudioPlugins()",
        "Resolve.GetFairlightEffects()",
        "Resolve.GetFairlightEffectList()",
        "Resolve.GetInstalledAudioPlugins()",
        "Resolve.GetPluginList()",
        "Project.GetAudioPlugins()",
        "Project.GetFairlightEffects()",
        "Project.GetFairlightEffectList()",
        "Timeline.GetTrackEffects('audio', 1)",
        "Timeline.GetTrackEffectList('audio', 1)",
        "Timeline.GetTrackFXList('audio', 1)",
        "Timeline.GetTrackPlugins('audio', 1)",
        "Timeline.GetTrackPluginList('audio', 1)",
        "Timeline.GetTrackPluginParameters('audio', 1, 1)",
        "Timeline.GetBusEffects('Main')",
        "Timeline.GetBusPlugins('Main')",
        "Timeline.GetBusPluginList('Main')",
        "TimelineItem.GetAudioEffects()",
        "TimelineItem.GetClipEffects()",
        "TimelineItem.GetPlugins()",
    ],
    "mutating_candidates_not_called": [
        "Timeline.AddTrackEffect('audio', 1, ...)",
        "Timeline.InsertTrackEffect('audio', 1, ...)",
        "Timeline.RemoveTrackEffect('audio', 1, ...)",
        "Timeline.SetTrackPluginParameter('audio', 1, ...)",
        "Timeline.AddBusEffect('Main', ...)",
        "Timeline.RemoveBusEffect('Main', ...)",
        "Timeline.SetBusPluginParameter('Main', ...)",
    ],
    "probe_result": "track/bus plugin slot getters returned method_not_available; plugin insertion/removal/parameter mutation candidates were not called",
    "track_bus_plugin_native_read_supported": False,
    "track_bus_plugin_native_insert_supported": False,
    "track_bus_plugin_native_param_supported": False,
}


_FAIRLIGHT_TRACK_DUPLICATE_NATIVE_PROBE_EVIDENCE = {
    **_FAIRLIGHT_SLOT_BUS_NATIVE_PROBE_CONTEXT,
    "candidate_methods_not_available": [
        "Timeline.GetTrackProcessing('audio', 1)",
        "Timeline.GetTrackProperties('audio', 1)",
        "Timeline.GetTrackFormat('audio', 1)",
        "Timeline.GetTrackSends('audio', 1)",
        "Timeline.GetTrackEffects('audio', 1)",
        "Timeline.GetTrackAutomation('audio', 1)",
        "Timeline.GetTrackRouting('audio', 1)",
    ],
    "mutating_candidates_not_called": [
        "Timeline.DuplicateTrack('audio', 1, ...)",
        "Timeline.CopyTrack('audio', 1, ...)",
        "Timeline.CloneTrack('audio', 1, ...)",
        "Timeline.ApplyTrackPreset('audio', 1, ...)",
    ],
    "resolve_21_embedded_recheck": {
        "runtime": "DaVinci Resolve 21.0.0.48 Free",
        "transport": "embedded_lua_http_poll",
        "artifact": "/tmp/cutagent_track_duplicate_cw_20260619/01_direct_track_duplicate_full_probe_after_allowlist.json",
        "candidate_methods_not_available": [
            "Timeline.GetTrackProcessing('audio', 1)",
            "Timeline.GetTrackProperties('audio', 1)",
            "Timeline.GetTrackFormat('audio', 1)",
            "Timeline.GetTrackSends('audio', 1)",
            "Timeline.GetTrackEffects('audio', 1)",
            "Timeline.GetTrackAutomation('audio', 1)",
            "Timeline.GetTrackRouting('audio', 1)",
        ],
        "unsupported_bridge_count": 0,
        "probe_result": "full-processing duplicate readback candidates reached DaVinci Resolve and returned method_not_available",
    },
    "probe_result": "full-processing duplicate readback candidates returned method_not_available; duplicate/copy/clone candidates were not called",
    "full_duplicate_native_readback_supported": False,
    "full_duplicate_native_copy_supported": False,
    "processing_copy_native_supported": False,
    "routing_send_plugin_automation_copy_native_supported": False,
}


_FAIRLIGHT_BUS_ROUTING_DB_BLOCKER_EVIDENCE = {
    "available_db_routes": [
        {
            "command": "cutagent fairlight bus list --include-context --json",
            "scope": "stored main/bus label tokens only",
            "db_blob": "Sm2Sequence.FieldsBlob.FLStudioModelBA",
            "read_scope": "labels_only",
        },
        {
            "command": "cutagent fairlight bus level Main --json",
            "scope": "Main/Main 1 sequence output gain context only",
            "db_table": "Sm2Sequence",
            "db_field": "OutputAudioGain",
            "read_scope": "sequence_output_gain_context_only",
        },
    ],
    "bus_model_evidence": {
        "label_read_supported": True,
        "main_output_gain_context_supported": True,
        "bus_assignment_supported": False,
        "non_main_bus_fader_read_supported": False,
        "non_main_bus_fader_write_supported": False,
        "flexbus_graph_edit_supported": False,
        "verified_bus_strip_readback_supported": False,
        "bus_pan_supported": False,
    },
    "native_probe_evidence": _FAIRLIGHT_BUS_ROUTING_NATIVE_PROBE_EVIDENCE,
    "db_schema_evidence": {
        "source": "local DaVinci Resolve 20 Free Project.db schema probes",
        "sampled_project_db_count": 5,
        "read_scope": "negative_bus_flexbus_routing_schema_probe",
        "verified_label_storage": [
            "Sm2Sequence.FieldsBlob.FLStudioModelBA length-prefixed main/bus label tokens",
        ],
        "verified_main_output_gain_context": [
            "Sm2Sequence.OutputAudioGain",
            "Sm2Sequence.NumOutputAudioChannels",
        ],
        "candidate_blob_fields_seen": [
            "Sm2Sequence.FieldsBlob",
            "Sm2TiTrack.AudioMixerBA",
            "Sm2TiTrack.FieldsBlob",
        ],
        "aux_like_fields_seen_but_not_bus_routes": [
            "Sm2Sequence.AuxRenderCacheBA",
            "Sm2Sequence.pAuxLmVerTable",
            "Sm2TiItem.pAuxLmVerTable",
        ],
        "unrelated_output_setup_tables_seen": [
            "SM_VTROutputSettings",
        ],
        "bus_or_flexbus_named_table_found_in_samples": False,
        "track_output_bus_column_found_in_samples": False,
        "non_main_bus_fader_column_found_in_samples": False,
        "bus_pan_column_found_in_samples": False,
        "flexbus_graph_schema_found_in_samples": False,
        "bounce_source_selector_schema_found_in_samples": False,
        "active_bus_assignment_readback_found_in_samples": False,
    },
    "db_blocker_note": (
        "`fairlight bus list` reads label tokens only, and `fairlight bus level Main` reads/writes "
        "Sm2Sequence.OutputAudioGain as a Main-output sequence gain context only. Neither route verifies "
        "non-main bus assignment, FlexBus graph edits, non-main bus faders, bus strip readback, or bus pan."
    ),
}


_FAIRLIGHT_NON_MAIN_BUS_BOUNCE_DB_BLOCKER_EVIDENCE = {
    **_FAIRLIGHT_BUS_ROUTING_DB_BLOCKER_EVIDENCE,
    "bounce_source_selection_evidence": {
        "main_mix_bounce_supported": True,
        "non_main_bus_bounce_supported": False,
        "flexbus_bounce_source_supported": False,
        "render_settings_bus_selector_supported": False,
        "verified_db_bounce_source_selector_supported": False,
    },
    "db_blocker_note": (
        "`fairlight bounce mix-to-track` can render/import/append the main timeline mix through native "
        "Deliver and MediaPool APIs. The available DB routes expose labels-only bus tokens and Main output "
        "gain context, but not a verified bus/FlexBus render-source selector or source-routing mutation."
    ),
}


@bus_app.command("list")
@handle_errors
def bus_list(
    include_context: bool = typer.Option(False, "--include-context", help="Include bounded hex/ASCII DB context around bus label tokens"),
    context_bytes: int = typer.Option(32, "--context-bytes", min=0, max=256, help="Bytes before/after each token when --include-context is set"),
):
    """List Fairlight main/bus labels from the Disk DB mixer model."""
    enforce_mutation_policy("fairlight.bus_read", intended_engine="db_workaround", mutating=False)
    set_execution_engine("db_workaround")
    set_verification_status("not_requested")
    set_recoverability("not_applicable")
    if is_dry_run():
        output(
            {
                "action": "fairlight.bus.list",
                "dry_run": True,
                "would_read": True,
                "route": "db_workaround",
                "target": "current_timeline_fairlight_bus_labels",
                "include_context": bool(include_context),
                "context_bytes": int(context_bytes) if include_context else 0,
                "db_blob": "Sm2Sequence.FieldsBlob.FLStudioModelBA",
                "read_scope": "labels_only",
                "context_supported": True,
                "set_supported": False,
            },
            title="Fairlight Buses Plan",
        )
        return
    conn = get_connection(require_timeline=True)
    data = fairlight_ops.read_fairlight_bus_list_db(
        conn,
        include_context=include_context,
        context_bytes=context_bytes,
    )
    output(data, title="Fairlight Buses")


@bus_app.command("assign")
@handle_errors
def bus_assign(
    bus: str | None = typer.Argument(None, help="Destination bus name, e.g. 'Bus 1' or 'Main 1'"),
    track: int | None = typer.Option(None, "--track", "-t", help="Audio track index to route"),
    track_name: str | None = typer.Option(None, "--track-name", help="Audio track name to route"),
):
    """Verify Fairlight bus assignment through the DB-backed output route."""
    enforce_mutation_policy("fairlight.bus_routing", intended_engine="db_workaround", mutating=not is_dry_run())
    if not bus:
        raise ValidationError(
            "Destination bus name is required.",
            details={
                "example": "cutagent fairlight bus assign \"Bus 1\" --track 1 --json",
                "required": ["bus"],
                "optional": ["--track", "--track-name"],
                "api_note": "Fairlight bus routing is limited to the verified default output bus route.",
            },
        )
    if track is None and not track_name:
        raise ValidationError(
            "Audio track selector is required for Fairlight bus assignment.",
            details={"required": ["--track or --track-name"], "example": "cutagent fairlight bus assign \"Bus 1\" --track 1 --json"},
        )
    canonical_bus = fairlight_ops._canonical_fairlight_bus_name(bus)
    if is_dry_run():
        set_execution_engine("db_workaround")
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            {
                "action": "fairlight.bus.assign",
                "would_assign": True,
                "dry_run": True,
                "route": "db_workaround_verified_default_output",
                "bus": canonical_bus,
                "track": track,
                "track_name": track_name,
                "project_close_required_for_live_run": False,
            },
            title="Fairlight Bus Assign Plan",
        )
        return
    conn = get_connection(require_timeline=True)
    set_execution_engine("db_workaround")
    data = fairlight_ops.assign_audio_track_bus_db(conn, bus_name=bus, track_index=track, track_name=track_name)
    output(data, title="Fairlight Bus Assign")


@bus_app.command("level")
@handle_errors
def bus_level(
    bus: str | None = typer.Argument(None, help="Bus name, e.g. 'Bus 1' or 'Main 1'"),
    level_db: float | None = typer.Option(None, "--level", "--level-db", help="Target bus level in dB, e.g. -6.0"),
):
    """Read or set main-output sequence gain DB context.

    DaVinci Resolve's public scripting API currently exposes basic Fairlight track
    operations, but not bus fader/level control. The mapped write route updates
    Sm2Sequence.OutputAudioGain for the default output only; it is not verified
    Fairlight mixer fader parity.
    """
    if not bus:
        set_capability_context("fairlight.bus_routing", "supported")
        set_execution_engine("db_workaround")
        raise ValidationError(
            "Bus name is required.",
            details={
                "example": "cutagent fairlight bus level \"Bus 1\" --level -6 --json",
                "required": ["bus"],
                "optional": ["--level"],
                "api_note": "Fairlight bus level/fader control is limited to the verified default output bus route.",
            },
        )
    if not fairlight_ops.normalize_fairlight_main_output_selector(bus):
        if level_db is None:
            _raise_unmapped_fairlight_bus_readback(bus)
        _raise_fairlight_native_unavailable(
            capability_id="fairlight.bus_routing",
            workflow="Fairlight non-default bus level control",
            requested={"bus": bus, "level_db": level_db},
            required_native_api=[
                "resolve non-default buses to FlexBus graph nodes",
                "set non-default bus fader/level",
                "verify non-default bus mixer strip readback after a fader change",
            ],
            api_note=(
                "The discovered DB route maps only the default output bus sequence gain context, "
                "not arbitrary Fairlight bus/FlexBus fader storage."
            ),
            workaround="Use Bus 1/Main/Main 1 for the mapped default output gain context, or set non-default bus faders in DaVinci Resolve.",
            extra_details={
                "requested_bus": bus,
                "requested_level_db": level_db,
                "supported_write_bus_selectors": ["Bus 1", "Main", "Main 1"],
                "unsupported_scope": "non_main_bus_fader_write",
                "available_db_routes": _FAIRLIGHT_BUS_ROUTING_DB_BLOCKER_EVIDENCE["available_db_routes"],
                **_FAIRLIGHT_BUS_ROUTING_DB_BLOCKER_EVIDENCE,
            },
        )
    if level_db is None:
        enforce_mutation_policy("fairlight.bus_read", intended_engine="db_workaround", mutating=False)
        set_execution_engine("db_workaround")
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        if is_dry_run():
            output(
                {
                    "action": "fairlight.bus.level",
                    "dry_run": True,
                    "would_read": True,
                    "route": "db_workaround",
                    "target": {"kind": "main_output_gain_context", "bus": bus},
                    "db_table": "Sm2Sequence",
                    "db_field": "OutputAudioGain",
                    "read_scope": "sequence_output_gain_context_only",
                    "sequence_output_gain_read_supported": True,
                    "verified_fader_read_supported": False,
                    "sequence_output_gain_set_supported": True,
                    "verified_fader_set_supported": False,
                    "set_supported": True,
                    "set_scope": "sequence_output_gain_context_only",
                },
                title="Fairlight Bus Level Plan",
            )
            return
        conn = get_connection(require_timeline=True)
        data = fairlight_ops.read_fairlight_bus_level_db(conn, bus=bus)
        output(data, title="Fairlight Bus Level")
        return

    enforce_mutation_policy(
        "fairlight.bus_routing",
        intended_engine="db_workaround",
        mutating=not is_dry_run(),
    )
    set_execution_engine("db_workaround")
    normalized_level = fairlight_ops.validate_fairlight_sequence_output_gain_level(level_db)
    canonical_bus = fairlight_ops._canonical_fairlight_bus_name(bus)
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            mutation_payload(
                action="fairlight.bus.level",
                target={"kind": "main_output_gain_context", "bus": bus},
                changed=False,
                dry_run=True,
                runtime_write_called=False,
                level_db=normalized_level,
                output_audio_gain=normalized_level,
                route="db_workaround_sequence_output_gain",
                bus=canonical_bus,
                db_table="Sm2Sequence",
                db_field="OutputAudioGain",
                storage="sequence_output_gain_context_only",
                set_scope="sequence_output_gain_context_only",
                verification_status="not_requested",
                sequence_output_gain_set_supported=True,
                verified_fader_set_supported=False,
                verified_fader_read_supported=False,
                preflight_command="cutagent fairlight bus level Main --json",
            ),
            title="Fairlight Bus Level Plan",
        )
        return
    conn = get_connection(require_timeline=True)
    data = fairlight_ops.set_fairlight_bus_level_db(
        conn,
        bus_name=bus,
        level_db=normalized_level,
    )
    output(data, title="Fairlight Bus Level")


effect_app = typer.Typer(help="Fairlight effect/plugin operations.")
app.add_typer(effect_app, name="effect")


_FAIRLIGHT_PLUGIN_SLOT_DB_BLOCKER_EVIDENCE = {
    "available_read_routes": [
        {
            "command": "cutagent fairlight effect catalog --json",
            "scope": "timeline mixer model catalog tokens only",
            "db_blob": "Sm2Sequence.FieldsBlob.FLStudioModelBA",
            "read_scope": "track_fx_macro_automix_bus_bmd_catalog_only",
        },
        {
            "command": "cutagent fairlight effect plugin-catalog --json",
            "scope": "installed AU/VST XML configuration plus built-in BMD Fairlight FX symbol catalog",
            "route": "Fairlight Effects XML configuration and libBMDAudioPlugins.dylib symbol scan",
        },
        {
            "command": "cutagent fairlight effect slot-scan --json",
            "scope": "mixer BMD token candidates plus clip-level FL::ClipFX payloads",
            "db_blobs": [
                "Sm2Sequence.FieldsBlob.FLStudioModelBA",
                "Sm2TiItem.FieldsBlob.FL::ClipFX",
            ],
        },
        {
            "command": "cutagent color page resolvefx-list --json",
            "scope": "related Color Page ResolveFX image OFX registry only, not Fairlight audio slots",
            "route": "resolve.Fusion().GetRegList(2)",
        },
    ],
    "supported_clip_fx_db_route": (
        "Known clip-level FL::ClipFX entries and parameters are readable through `fairlight effect list/params --clip` "
        "and writable for the supported built-in clip effects through `fairlight effect set-param --clip`."
    ),
    "resolvefx_route_scope_evidence": {
        "color_page_resolvefx_route_available": True,
        "registry_command": "cutagent color page resolvefx-list --json",
        "write_commands": [
            "cutagent color page resolvefx-add CLIP --fx EFFECT --json",
            "cutagent color page resolvefx-remove CLIP --json",
        ],
        "registry_source": "resolve.Fusion().GetRegList(2)",
        "write_route": "db_workaround_color_page_resolvefx_add",
        "write_storage_scope": "Color Page primary grade container tool params",
        "ofx_context": "OfxImageEffectContextFilter",
        "fairlight_audio_slot_route": False,
        "workflow_integration_scope": (
            "Workflow Integration plugins host Electron/JavaScript integrations and access the same DaVinci Resolve scripting APIs; "
            "the installed SDK README does not add a separate Fairlight plugin-slot API."
        ),
        "local_fairlight_config_probe_2026_06_14": {
            "config_dir": "~/Library/Preferences/Blackmagic Design/DaVinci Resolve/Fairlight/Effects",
            "files_seen": [
                "AUConfiguration.xml",
                "VST3Configuration.xml",
                "FXConfiguration.xml",
                "FXScan.xml",
                "ExternalFXConfiguration.xml",
            ],
            "audio_unit_total_count": 28,
            "vst3_total_count": 0,
            "fairlight_fx_total_count": 0,
            "fx_scan_paths": [
                "/Library/Audio/Plug-Ins/VST",
                "/Library/Audio/Plug-Ins/VST3",
            ],
            "xml_contains_slot_assignment_state": False,
            "bmd_builtin_audio_plugin_library": (
                "/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/Libraries/libBMDAudioPlugins.dylib"
            ),
            "bmd_builtin_audio_fx_total_count": 35,
            "bmd_builtin_audio_fx_examples": [
                "BMDChorus",
                "BMDDistortion",
                "BMDDialogProcessor",
                "BMDReverb",
                "BMDStereoEcho",
                "BMDVoiceIsolationControl",
            ],
            "bmd_builtin_library_contains_slot_assignment_state": False,
        },
        "fairlight_route_boundary": (
            "Color Page ResolveFX entries are image OFX filters stored in the grade body. "
            "They do not describe Fairlight track, bus, or audio clip plugin slot assignment."
        ),
    },
    "db_schema_evidence": {
        "source": (
            "local DaVinci Resolve 20 Free Project.db schema probes, Fairlight Effects XML config probe, "
            "Color Page ResolveFX route boundary check, and DaVinci Resolve 21.0.0.48 Free catalog/slot DB token probe"
        ),
        "sampled_project_db_count": 5,
        "resolve_21_probe_project": "CUTAGENT_RESOLVE21_FOLDER_PROBE_20260612_173908",
        "resolve_21_probe_timeline": "FOLDER_PROBE_24FPS",
        "read_scope": "negative_track_bus_plugin_slot_schema_probe",
        "catalog_candidate_storage_seen": [
            "Sm2Sequence.FieldsBlob.FLStudioModelBA",
            "Sm2TiTrack.AudioMixerBA",
            "Sm2TiTrack.FieldsBlob",
        ],
        "clip_level_fx_storage_seen": [
            "Sm2TiItem.FieldsBlob.FL::ClipFX",
            "Sm2TiItem.EffectFiltersBA",
        ],
        "legacy_clip_effect_tables_seen_but_not_track_bus_slot_model": [
            "SM_Effect",
            "SM_Clip_FilterEffects",
        ],
        "fairlight_effect_config_files_seen": [
            "AUConfiguration.xml: Effects/Effect availability catalog entries",
            "FXConfiguration.xml: Effects availability catalog",
            "VST3Configuration.xml: Effects availability catalog",
            "FXScan.xml: plugin scan paths",
            "libBMDAudioPlugins.dylib: built-in BMD Fairlight FX class and parameter symbol catalog",
        ],
        "track_bus_plugin_slot_table_found_in_samples": False,
        "slot_indexed_assignment_schema_found_in_samples": False,
        "track_bus_plugin_bypass_schema_found_in_samples": False,
        "track_bus_plugin_param_schema_found_in_samples": False,
        "track_bus_plugin_write_readback_route_found_in_samples": False,
        "xml_catalog_is_slot_assignment_state": False,
        "bmd_builtin_symbol_catalog_is_slot_assignment_state": False,
        "mixer_bmd_tokens_are_active_slots": False,
        "clip_fx_payload_is_track_bus_slot_state": False,
        "resolve_21_new_feature_probe": {
            "public_features_checked": ["Chain FX", "EQ Match", "Level Matcher"],
            "commands_run": [
                "cutagent fairlight effect catalog --json",
                "cutagent fairlight effect plugin-catalog --json",
                "cutagent fairlight effect slot-scan --limit 200 --json",
            ],
            "evidence_files": [
                "/tmp/cutagent_resolve21_effect_catalog.json",
                "/tmp/cutagent_resolve21_plugin_catalog.json",
                "/tmp/cutagent_resolve21_slot_scan.json",
                "/tmp/cutagent_resolve21_chain_matcher_db_scan.json",
            ],
            "chain_fx_token_found": False,
            "eq_match_token_found": False,
            "level_matcher_token_found": False,
            "generic_level_tokens_are_level_matcher": False,
            "generic_match_schema_hits_are_matcher_payload": False,
            "active_slot_or_matcher_readback_route_found": False,
            "write_readback_route_found": False,
        },
    },
    "slot_model_evidence": {
        "candidate_probe_supported": True,
        "clip_fx_payload_read_supported": True,
        "mixer_model_bmd_tokens_active_slot_verified": False,
        "track_bus_slot_state_supported": False,
        "slot_insert_supported": False,
        "slot_remove_supported": False,
        "slot_bypass_supported": False,
        "param_routing_supported": False,
        "set_supported": False,
        "unverified_write_scope": [
            "track/bus plugin slot assignment",
            "track/bus plugin insertion",
            "track/bus plugin removal",
            "track/bus plugin bypass",
            "arbitrary track/bus plugin parameter routing",
            "arbitrary plugin preset routing",
            "DaVinci Resolve 21 Chain FX creation/application",
            "DaVinci Resolve 21 EQ Match processing",
            "DaVinci Resolve 21 Level Matcher processing",
        ],
    },
    "native_probe_evidence": _FAIRLIGHT_PLUGIN_SLOT_NATIVE_PROBE_EVIDENCE,
    "db_blocker_note": (
        "Mixer-model BMD tokens are catalog/candidate signals only. They are not treated as active track/bus slot "
        "state without separate native, GUI-readback, or verified DB mutation/readback evidence."
    ),
}

