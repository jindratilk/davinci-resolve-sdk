from __future__ import annotations

@voice_isolation_app.command("get")
@handle_errors
def voice_isolation_get(
    track: int = typer.Argument(..., help="Audio track index"),
):
    """Read timeline voice isolation state."""
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
    enable: Optional[bool] = typer.Option(None, "--enable/--disable", help="Enable or disable voice isolation"),
    amount: Optional[int] = typer.Option(None, "--amount", help="Isolation amount 0-100"),
):
    """Set timeline voice isolation state."""
    set_capability_context("fairlight.timeline_voice_isolation", "supported")
    set_execution_engine("api_native")
    set_recoverability("manual")
    enforce_mutation_policy("fairlight.timeline_voice_isolation", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        set_verification_status("not_requested")
        output(
            {
                "action": "timeline.voice_isolation.set",
                "would_set": True,
                "dry_run": True,
                "track": int(track),
                "state": {
                    "isEnabled": None if enable is None else bool(enable),
                    "amount": None if amount is None else int(amount),
                },
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


@app.command("stereo-convert")
@handle_errors
def stereo_convert():
    """Convert current timeline to stereo 3D."""
    enforce_mutation_policy("timeline.stereo_convert", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        dry_run_message("Would convert the current timeline to stereo 3D.")
        return
    conn = get_connection(require_timeline=True)
    output(timeline_ops.convert_timeline_to_stereo(conn), title="Timeline Stereo")


@app.command("media-pool-item")
@handle_errors
def media_pool_item():
    """Show the MediaPoolItem backing the current timeline."""
    conn = get_connection(require_timeline=True)
    output(timeline_ops.current_timeline_media_pool_item(conn), title="Timeline MediaPoolItem")


@app.command("sync-clips")
@handle_errors
def sync_clips(
    source: list[str] = typer.Option([], "--source", help="Sync source as LABEL=clip, LABEL=name:clip, LABEL=path:/file.mov, LABEL=media_id:ID, or compound LABEL=path:/file.mov|folder:Bin; repeat for each clip"),
    timeline_name: Optional[str] = typer.Option(None, "--timeline", help="Target timeline name; defaults to active timeline"),
    create_timeline: bool = typer.Option(False, "--create-timeline", help="Create --timeline before placing synced clips"),
    sync: str = typer.Option("waveform", "--sync", help="Sync mode: waveform or manual"),
    reference: Optional[str] = typer.Option(None, "--reference", help="Source label used as waveform reference; defaults to the first --source"),
    offset: list[str] = typer.Option([], "--offset", help="Manual frame offset as LABEL=FRAMES; repeat when --sync manual"),
    video_track: list[str] = typer.Option([], "--video-track", help="Video track mapping as LABEL=TRACK; defaults to source order V1..VN"),
    audio_mode: str = typer.Option("reference", "--audio-mode", help="Audio placement mode: none, reference, or all"),
    audio_track: list[str] = typer.Option([], "--audio-track", help="Audio track mapping as LABEL=TRACK; defaults to A1 for reference or source order for all"),
    record_frame: Optional[str] = typer.Option(None, "--record-frame", "--at", help="Record-domain placement for the earliest synced source; defaults to timeline start"),
    plan_only: bool = typer.Option(False, "--plan-only", help="Resolve clips and offsets but do not append to the timeline"),
    subframe: str = typer.Option(
        "auto",
        "--subframe",
        help="Sub-frame accuracy for audio placements: auto (fractional when verified, conform fallback), fractional, round (legacy), or conform",
    ),
    use_timecode_prior: bool = typer.Option(
        False,
        "--use-timecode-prior",
        help="Use container/BWF timecode metadata as a waveform search prior; default ignores timecode metadata.",
    ),
    derived_media_dir: Optional[str] = typer.Option(
        None, "--derived-media-dir", help="Directory for conform-derived WAVs; defaults to a .cutagent-derived folder beside the source"
    ),
    max_derived_media_gb: float = typer.Option(
        20.0, "--max-derived-media-gb", help="Cumulative size budget for conform-derived media in this run"
    ),
    write_multicam_job: Optional[str] = typer.Option(
        None, "--write-multicam-job", help="Write a structured multicam job derived from the sync plan"
    ),
    write_audio_offsets_json: Optional[str] = typer.Option(
        None, "--write-audio-offsets-json", help="Write audio-activity offsets JSON derived from the sync plan"
    ),
    multicam_name: Optional[str] = typer.Option(
        None, "--multicam-name", help="Native multicam clip name for the generated multicam job"
    ),
    multicam_timeline_name: Optional[str] = typer.Option(
        None, "--multicam-timeline-name", help="Target timeline name for the generated multicam job; defaults to the synced timeline"
    ),
    multicam_angle: list[str] = typer.Option(
        [], "--multicam-angle", help="Video source label to use as a multicam angle: LABEL or LABEL=ANGLE; defaults to all video sources"
    ),
    multicam_audio_angle_map: list[str] = typer.Option(
        [], "--multicam-audio-angle-map", help="Audio source to multicam angle mapping as SOURCE=ANGLE; repeat for each mic source"
    ),
    multicam_audio_target: list[str] = typer.Option(
        [], "--multicam-audio-target", help="Optional audio target mapping as SOURCE=ANGLE[,ANGLE]"
    ),
    multicam_overlap_angle: Optional[str] = typer.Option(
        None, "--multicam-overlap-angle", "--multicam-wide-angle", help="Angle to use for overlap/wide moments in generated audio-activity job"
    ),
    multicam_default_video_angle: Optional[str] = typer.Option(
        None, "--multicam-default-video-angle", help="Default video angle in generated multicam settings"
    ),
    multicam_default_audio_angle: Optional[str] = typer.Option(
        None, "--multicam-default-audio-angle", help="Default audio angle in generated multicam settings"
    ),
    multicam_sync_anchor: Optional[str] = typer.Option(
        None, "--multicam-sync-anchor", help="Program sync anchor as a generated multicam angle or sync source label"
    ),
    multicam_switch_plan: Optional[str] = typer.Option(
        None, "--multicam-switch-plan", help="Path to include in the generated multicam switch --write-plan command"
    ),
):
    """Place synced ordinary clips on timeline tracks without creating a native multicam clip."""
    set_execution_engine("api_native")
    set_capability_context("timeline.sync_clips", "supported")
    apply_changes = not (is_dry_run() or plan_only)
    enforce_mutation_policy("timeline.sync_clips", intended_engine="api_native", mutating=apply_changes)
    conn = get_connection(require_project=True, require_timeline=False)
    data = timeline_sync.execute_sync(
        conn,
        source_specs=source,
        timeline_name=timeline_name,
        create_timeline=create_timeline,
        sync_mode=sync,
        reference_label=reference,
        offset_specs=offset,
        video_track_specs=video_track,
        audio_track_specs=audio_track,
        audio_mode=audio_mode,
        record_frame=record_frame,
        apply=apply_changes,
        subframe_mode=subframe,
        use_timecode_prior=use_timecode_prior,
        derived_media_dir=derived_media_dir,
        max_derived_media_gb=max_derived_media_gb,
        write_multicam_job=write_multicam_job,
        write_audio_offsets_json=write_audio_offsets_json,
        multicam_name=multicam_name,
        multicam_timeline_name=multicam_timeline_name,
        multicam_angle_specs=multicam_angle,
        multicam_audio_angle_map_specs=multicam_audio_angle_map,
        multicam_audio_target_specs=multicam_audio_target,
        multicam_overlap_angle=multicam_overlap_angle,
        multicam_default_video_angle=multicam_default_video_angle,
        multicam_default_audio_angle=multicam_default_audio_angle,
        multicam_sync_anchor=multicam_sync_anchor,
        multicam_switch_plan=multicam_switch_plan,
    )
    if data.get("verification", {}).get("status") == "verified":
        set_verification_status("verified")
    elif apply_changes:
        set_verification_status("partial")
    else:
        set_verification_status("not_requested")
    output(data, title="Timeline Sync Clips")


node_graph_app = typer.Typer(help="Timeline node graph operations.")
app.add_typer(node_graph_app, name="node-graph")


@node_graph_app.command("inspect")
@handle_errors
def node_graph_inspect():
    """Inspect the current timeline node graph when available."""
    conn = get_connection(require_timeline=True)
    output(timeline_ops.inspect_timeline_node_graph(conn), title="Timeline Node Graph")


fairlight_preset_app = typer.Typer(help="Timeline Fairlight preset operations.")
app.add_typer(fairlight_preset_app, name="fairlight-preset")


@fairlight_preset_app.command("apply")
@handle_errors
def fairlight_preset_apply(
    name: str = typer.Argument(..., help="Fairlight preset name"),
):
    """Apply a Fairlight preset to the current timeline."""
    from ..core import fairlight_ops

    enforce_mutation_policy("fairlight.preset", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        dry_run_message(f"Would apply Fairlight preset: {name}")
        return
    conn = get_connection(require_timeline=True)
    output(fairlight_ops.apply_fairlight_preset(conn, name), title="Fairlight Preset")


# --- Current Item ---

@app.command("current-item")
@handle_errors
def current_item():
    """Show info about the current video item under playhead."""
    ui_state = _probe_current_item_ui_context()
    conn = get_connection(require_timeline=True)
    context = _current_item_context(conn)
    item = conn.timeline.GetCurrentVideoItem()
    if not item:
        data = {**context, "current_item": None, "warning": "No video item at current playhead position."}
        _attach_current_item_ui_context(data, ui_state)
        output(data, title="Current Video Item")
        return
    
    # Get item properties
    data = dict(context)
    try:
        data["name"] = item.GetName() if hasattr(item, "GetName") else "Unknown"
    except Exception:
        data["name"] = "Unknown"
    
    try:
        data["start"] = item.GetStart() if hasattr(item, "GetStart") else None
    except Exception:
        pass
    
    try:
        data["end"] = item.GetEnd() if hasattr(item, "GetEnd") else None
    except Exception:
        pass
    
    try:
        data["duration"] = item.GetDuration() if hasattr(item, "GetDuration") else None
    except Exception:
        pass

    if hasattr(item, "GetTrackTypeAndIndex"):
        try:
            track_type, track_index = item.GetTrackTypeAndIndex()
            data["track_type"] = track_type
            data["track_index"] = track_index
        except Exception:
            pass
    
    _attach_current_item_ui_context(data, ui_state)
    output(data, title="Current Video Item")


# --- Thumbnail ---

@app.command("thumbnail")
@handle_errors
def thumbnail(
    output_path: str = typer.Option("thumbnail.png", "--output", "-o", help="Output file path"),
):
    """Export thumbnail of current clip under playhead."""
    set_execution_engine("workaround_setting")
    set_capability_context("timeline.thumbnail", "supported")
    resolved_path = _resolve_thumbnail_output_file_path(output_path)
    enforce_mutation_policy("timeline.thumbnail", intended_engine="workaround_setting", mutating=not is_dry_run())
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            {
                "output_path": str(resolved_path),
                "requested_output_path": output_path,
                "would_export": True,
                "exported": False,
                "verified": False,
                "page_switch_required": True,
            },
            title="Timeline Thumbnail Preview",
        )
        return
    conn = get_connection(require_timeline=True)
    metadata = _export_current_frame_as_still(
        conn,
        resolved_path=resolved_path,
        requested_output_path=output_path,
        error_message="Failed to export current frame thumbnail.",
    )
    set_verification_status("verified")
    set_recoverability("not_applicable")
    output(
        {
            "output_path": str(resolved_path),
            "requested_output_path": output_path,
            "exported": True,
            "verified": True,
            "page_switch_required": True,
            **metadata,
        },
        title="Timeline Thumbnail",
    )
