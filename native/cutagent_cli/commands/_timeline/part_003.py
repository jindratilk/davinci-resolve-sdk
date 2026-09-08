from __future__ import annotations

@layer_app.command("ensure-media")
@handle_errors
def layer_ensure_media(
    media: str = typer.Option(..., "--media", help="Media Pool item name, id, or source path"),
    timeline_name: str | None = typer.Option(None, "--timeline", help="Target timeline name; defaults to active timeline"),
    track: int = typer.Option(..., "--track", min=1, help="Target video track index"),
    start_frame: int = typer.Option(..., "--start-frame", min=0, help="DaVinci Resolve recordFrame where the layer must start"),
    duration: int = typer.Option(..., "--duration", min=1, help="Required target duration in frames"),
    extend_gap: str = typer.Option("0f", "--extend-gap", help="Maximum gap to bridge, e.g. 1s, 25f, or a bare frame count"),
    match_name: str = typer.Option("exact", "--match-name", help="Media name matching mode: exact or contains"),
    allow_insert: bool = typer.Option(True, "--allow-insert/--no-insert", help="Insert the media when no suitable existing item is found"),
    allow_extend: bool = typer.Option(True, "--allow-extend/--no-extend", help="Extend a nearby matching item when possible"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Plan the operation without mutating DaVinci Resolve"),
):
    """Ensure a video-track media layer covers a target record-frame range."""
    set_capability_context("timeline.layer.ensure_media", "supported")
    set_execution_engine("api_native")
    set_recoverability("manual")
    set_verification_status("not_requested" if dry_run or is_dry_run() else "verified")
    effective_dry_run = bool(dry_run or is_dry_run())
    enforce_mutation_policy("timeline.layer.ensure_media", intended_engine="api_native", mutating=not effective_dry_run)
    conn = get_connection(require_project=True, require_timeline=timeline_name is None)
    extend_gap_frames = parse_source_frame(str(extend_gap), conn.fps)
    data = timeline_layer_ops.ensure_media_layer(
        conn,
        media=media,
        track=track,
        start_frame=start_frame,
        duration_frames=duration,
        extend_gap_frames=extend_gap_frames,
        timeline=timeline_name,
        match_name=match_name,
        allow_insert=allow_insert,
        allow_extend=allow_extend,
        dry_run=effective_dry_run,
    )
    if effective_dry_run:
        set_verification_status("not_requested")
    else:
        set_verification_status("verified" if data.get("verification", {}).get("covers_target_range") else "failed")
    payload = dict(data)
    output(
        mutation_payload(
            action=str(payload.pop("action", "timeline.layer.ensure_media")),
            target=payload.pop("target", None),
            changed=bool(payload.pop("changed", False)),
            **payload,
        ),
        title="Timeline Layer Ensure Media",
    )


@clip_color_app.command("batch")
@handle_errors
def clip_color_batch(
    batch: str = typer.Option(..., "--batch", help="Batch JSON path"),
    timeline_name: str | None = typer.Option(None, "--timeline-name", "--timeline", help="Target timeline name; defaults to active timeline"),
    track_type: str = typer.Option("video", "--track-type", help="Track type: video, audio, or all"),
    track_index: int = typer.Option(1, "--track", "--track-index", min=1, help="Track index when not using --all-tracks"),
    all_tracks: bool = typer.Option(False, "--all-tracks", help="Scan all tracks for the selected track type"),
    require_count_match: bool = typer.Option(True, "--require-count-match/--no-require-count-match", help="Require expected and actual item counts to match before mutation"),
    allow_partial: bool = typer.Option(False, "--allow-partial/--no-allow-partial", help="Apply only matched bounds when preflight has non-duplicate mismatches"),
):
    """Batch set or clear timeline clip colors by exact frame bounds."""
    entries = _load_clip_color_batch_entries(batch)
    timeline_clip_color.validate_batch_entry_colors(entries)
    set_execution_engine("api_native")
    enforce_mutation_policy("timeline.clip_color_batch", intended_engine="api_native", mutating=not is_dry_run())

    require_timeline = timeline_name is None
    conn = get_connection(require_project=True, require_timeline=require_timeline)
    plan = timeline_clip_color.plan_timeline_clip_color_batch(
        conn,
        entries=entries,
        timeline_name=timeline_name,
        track_type=track_type,
        track_index=track_index,
        all_tracks=all_tracks,
        require_count_match=require_count_match,
    )

    if is_dry_run():
        output(
            mutation_payload(
                action="timeline.clip_color.batch",
                target={"kind": "timeline", "name": plan["timeline_name"] or timeline_name or "current"},
                changed=False,
                timeline_name=plan["timeline_name"],
                track_type=plan["track_type"],
                track_index=plan["track_index"],
                all_tracks=plan["all_tracks"],
                require_count_match=plan["require_count_match"],
                allow_partial=bool(allow_partial),
                dry_run=True,
                preflight=plan["preflight"],
                entries=plan["preflight"]["expected"],
                ready=bool(plan["preflight"]["ready"] or allow_partial),
                runtime_validation="performed",
                message=(
                    "DRY-RUN: Would apply timeline clip colors to matched timeline items."
                    if plan["preflight"]["ready"] or allow_partial
                    else "DRY-RUN: Preflight found mismatches; a real run would fail unless --allow-partial is used."
                ),
            ),
            title="Timeline Clip Color Batch Plan",
        )
        return

    data = timeline_clip_color.apply_timeline_clip_color_batch(
        conn,
        entries=entries,
        timeline_name=timeline_name,
        track_type=track_type,
        track_index=track_index,
        all_tracks=all_tracks,
        require_count_match=require_count_match,
        allow_partial=allow_partial,
    )
    payload = dict(data)
    output(
        mutation_payload(
            action=str(payload.pop("action", "timeline.clip_color.batch")),
            target={"kind": "timeline", "name": data.get("timeline_name") or timeline_name or "current"},
            changed=bool(data.get("applied_count") or data.get("cleared_count")),
            **payload,
        ),
        title="Timeline Clip Color Batch",
    )


# --- Setting (singular - alternative API) ---

setting_app = typer.Typer(help="Deprecated timeline setting aliases.")
app.add_typer(setting_app, name="setting", hidden=True)


@setting_app.command("set", hidden=True)
@handle_errors
def setting_set(
    key: str = typer.Argument(..., help="Setting key"),
    value: str = typer.Argument(..., help="Setting value"),
):
    """Set a timeline setting (using SetSetting API)."""
    enforce_mutation_policy("timeline.settings_write", intended_engine="api_native")
    conn = get_connection(require_timeline=True)
    result = timeline_ops.set_timeline_setting(conn, key, value, return_details=True)
    if is_machine_mode():
        output(
            mutation_payload(
                action="timeline.settings_set",
                changed=bool(result.get("changed")),
                target={"kind": "timeline_setting", "name": result.get("key")},
                value=result.get("requested"),
                read_back=result.get("read_back"),
                api_result=result.get("api_result"),
                verified=result.get("verified"),
                deprecated_alias=True,
                replacement="timeline settings-set",
                message=f"Set {result.get('key')} = {result.get('read_back')}",
            )
        )
        return
    success(f"Set {result.get('key')} = {result.get('read_back')}")


# --- Subtitle ---

subtitle_app = typer.Typer(help="Subtitle operations.")
app.add_typer(subtitle_app, name="subtitle")


@subtitle_app.command("list")
@handle_errors
def subtitle_list(
    track: Optional[int] = typer.Option(None, "--track", help="Subtitle track index"),
):
    """List subtitle clips."""
    conn = get_connection(require_timeline=True)
    rows = timeline_ops.list_subtitles(conn, track)
    output(
        rows,
        columns=[
            ("track", "Track"),
            ("start_tc", "Start"),
            ("end_tc", "End"),
            ("text", "Text"),
        ],
        title="Subtitles",
    )


@subtitle_app.command("insert")
@handle_errors
def subtitle_insert(
    path: str = typer.Argument(..., help="SRT subtitle file to import and append as native subtitle clips"),
    ensure_track: bool = typer.Option(True, "--ensure-track/--no-ensure-track", help="Create a subtitle track when none exists"),
):
    """Insert SRT subtitles as native DaVinci Resolve subtitle-track items."""
    set_execution_engine("api_native")
    set_capability_context("timeline.subtitle_arbitrary_insert", "supported")
    enforce_mutation_policy(
        "timeline.subtitle_arbitrary_insert",
        intended_engine="api_native",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            {
                "action": "timeline.subtitle.insert",
                "path": path,
                "format": "srt",
                "would_import_media": True,
                "would_append_to_timeline": True,
                "ensure_track": bool(ensure_track),
                "native_api": ["MediaPool.ImportMedia([path])", "MediaPool.AppendToTimeline([mediaPoolItem])"],
            },
            title="Subtitle Insert Plan",
        )
        return

    conn = get_connection(require_timeline=True)
    data = timeline_ops.insert_subtitles_from_srt(conn, path, ensure_track=ensure_track)
    payload = dict(data)
    output(
        mutation_payload(
            action=str(payload.pop("action", "timeline.subtitle.insert")),
            target={"kind": "subtitle_file", "path": payload.get("path")},
            changed=bool(payload.get("matched_entries")),
            **payload,
        ),
        title="Subtitle Insert",
    )
    success(f"Inserted {data.get('matched_entries')} subtitle entries.")


@subtitle_app.command("export")
@handle_errors
def subtitle_export(
    path: str = typer.Argument(..., help="Output subtitle file"),
    format: str = typer.Option("srt", "--format", help="srt, vtt, or ttml"),
    track: Optional[int] = typer.Option(None, "--track", help="Subtitle track index"),
    all_tracks: bool = typer.Option(False, "--all-tracks", help="Export all subtitle tracks"),
):
    """Export subtitles to SRT, VTT, or TTML."""
    normalized_format = format.lower()
    if normalized_format not in {"srt", "vtt", "ttml"}:
        raise ValidationError("Subtitle export format must be srt, vtt, or ttml.", details={"format": format})
    if track is not None and all_tracks:
        raise ValidationError(
            "Use either --track or --all-tracks, not both.",
            details={"track": track, "all_tracks": all_tracks},
            recoverability="not_applicable",
        )
    enforce_mutation_policy(
        "timeline.subtitle_list_add_export",
        intended_engine="api_native",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        dry_run_message(f"Would export subtitles to '{path}' ({format})")
        return
    conn = get_connection(require_timeline=True)
    result_path = timeline_ops.export_subtitles_srt_vtt(
        conn,
        output_path=path,
        fmt=normalized_format,
        track=track,
        all_tracks=all_tracks,
        return_details=True,
    )
    if is_machine_mode():
        output(result_path)
        return
    success(
        f"Exported {result_path.get('exported_entries')} subtitle entries to: {result_path.get('path')}"
    )


@app.command("auto-caption")
@handle_errors
def auto_caption(
    language: Optional[str] = typer.Option(None, "--language", help="auto|english|german|..."),
    preset: Optional[str] = typer.Option(None, "--preset", help="default|teletext|netflix"),
    chars_per_line: Optional[int] = typer.Option(None, "--chars-per-line", min=1, max=60),
    line_break: Optional[str] = typer.Option(None, "--line-break", help="single|double"),
    gap: Optional[int] = typer.Option(None, "--gap", min=0, max=10, help="Gap between captions in frames/seconds per DaVinci Resolve setting"),
):
    """Create subtitles from timeline audio using DaVinci Resolve auto-caption."""
    enforce_mutation_policy(
        "timeline.subtitle_list_add_export",
        intended_engine="api_native",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        dry_run_message("Would create subtitles from timeline audio.")
        return
    conn = get_connection(require_timeline=True)
    from ..core.media_pool import create_subtitles_from_audio

    data = create_subtitles_from_audio(
        conn,
        language=language,
        preset=preset,
        chars_per_line=chars_per_line,
        line_break=line_break,
        gap=gap,
    )
    output(data, title="Auto Caption")


# --- Extended Timeline Ops ---

@app.command("duplicate")
@handle_errors
def duplicate(
    new_name: str = typer.Argument(..., help="New timeline name"),
    source: Optional[str] = typer.Option(None, "--source", help="Optional source timeline name"),
):
    """Duplicate a timeline with native API or a verified DRT fallback."""
    enforce_mutation_policy(
        "timeline.duplicate",
        intended_engine="api_native",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(_timeline_duplicate_dry_run_payload(new_name=new_name, source=source), title="Duplicate Timeline Dry Run")
        return

    conn = get_connection(require_project=True)
    data = timeline_ops.duplicate_timeline(conn, new_name=new_name, source_name=source)
    output(data, title="Duplicate Timeline")


@app.command("compound-create")
@handle_errors
def compound_create(
    in_ref: str = typer.Option(..., "--in", help="Record-domain in reference"),
    out_ref: str = typer.Option(..., "--out", help="Record-domain out reference"),
    track_type: str = typer.Option("all", "--track-type", help="video, audio, subtitle, all"),
    track: int = typer.Option(0, "--track", min=0, help="Track index (0 = all tracks for selected type)"),
    name: Optional[str] = typer.Option(None, "--name", help="Optional compound clip name"),
    start_tc: Optional[str] = typer.Option(None, "--start-tc", help="Optional compound clip start timecode"),
):
    """Create a compound clip from a record-domain range."""
    enforce_mutation_policy(
        "timeline.compound_clip",
        intended_engine="api_native",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        set_recoverability("not_applicable")
        output(
            _compound_create_dry_run_payload(
                in_ref=in_ref,
                out_ref=out_ref,
                track_type=track_type,
                track=track,
                name=name,
                start_tc=start_tc,
            ),
            title="Compound Clip Dry Run",
        )
        return

    conn = get_connection(require_timeline=True)
    data = timeline_ops.create_compound_clip(
        conn,
        in_ref=in_ref,
        out_ref=out_ref,
        track_type=track_type,
        track_index=track,
        name=name,
        start_tc=start_tc,
    )
    output(data, title="Compound Clip")


@app.command("insert-generator")
@handle_errors
def insert_generator(
    name: str = typer.Argument(..., help="Generator name"),
    fusion: bool = typer.Option(False, "--fusion", help="Insert a Fusion generator"),
    ofx: bool = typer.Option(False, "--ofx", help="Insert an OFX generator"),
):
    """Insert a generator into the timeline at the playhead."""
    enforce_mutation_policy(
        "timeline.insert_generator",
        intended_engine="api_native",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        mode = "Fusion generator" if fusion else "OFX generator" if ofx else "generator"
        dry_run_message(f"Would insert {mode} '{name}' at the playhead.")
        return
    conn = get_connection(require_timeline=True)
    data = timeline_ops.insert_generator(conn, name, fusion=fusion, ofx=ofx)
    output(data, title="Insert Generator")


@app.command("insert-title")
@handle_errors
def insert_title(
    name: str = typer.Argument(..., help="Title name"),
    fusion: bool = typer.Option(False, "--fusion", help="Insert a Fusion title"),
):
    """Insert a title into the timeline at the playhead."""
    enforce_mutation_policy(
        "timeline.insert_title",
        intended_engine="api_native",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        mode = "Fusion title" if fusion else "title"
        dry_run_message(f"Would insert {mode} '{name}' at the playhead.")
        return
    conn = get_connection(require_timeline=True)
    data = timeline_ops.insert_title(conn, name, fusion=fusion)
    output(data, title="Insert Title")


@app.command("grab-still")
@handle_errors
def grab_still(
    output_path: Optional[str] = typer.Option(None, "--output", "-o", help="Optional output image path"),
):
    """Grab still from current frame."""
    enforce_mutation_policy("timeline.grab_still", intended_engine="api_native")
    conn = get_connection(require_timeline=True)
    data = timeline_ops.grab_still(conn, output_path=output_path)
    output(data, title="Grab Still")


@app.command("frame-export")
@handle_errors
def frame_export(
    at: str = typer.Option(..., "--at", help="Timeline position to sample: timecode, seconds, or frames"),
    output_path: str = typer.Option(..., "--output", "-o", help="Output image path"),
):
    """Export a still image from a specific timeline position and restore the playhead."""
    set_execution_engine("api_native")
    set_capability_context("timeline.frame_export", "supported")
    resolved_path = _resolve_thumbnail_output_file_path(output_path)
    enforce_mutation_policy("timeline.frame_export", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            {
                "requested_at": at,
                "output_path": str(resolved_path),
                "visual_check_path": _workspace_relative_path(resolved_path),
                "requested_output_path": output_path,
                "would_set_playhead": True,
                "would_export": True,
                "would_restore_playhead": True,
                "exported": False,
                "verified": False,
                "page_switch_required": True,
            },
            title="Timeline Frame Export Preview",
        )
        return

    with exclusive_resolve_state_operation(operation="timeline.frame_export"):
        conn = get_connection(require_timeline=True)
        export_result = _export_single_timeline_frame(
            conn,
            frame_ref=at,
            resolved_path=resolved_path,
            requested_output_path=output_path,
        )

    set_verification_status("verified")
    set_recoverability("manual" if export_result["restore_warning"] else "not_applicable")
    data = {
        "requested_at": at,
        "output_path": str(resolved_path),
        "visual_check_path": _workspace_relative_path(resolved_path),
        "requested_output_path": output_path,
        "original_playhead": export_result["original_playhead"],
        "target": export_result["target"],
        "restored_playhead": export_result["restored_playhead"],
        "restore_warning": export_result["restore_warning"],
        "exported": True,
        "verified": True,
        "page_switch_required": True,
        **{key: value for key, value in export_result.items() if key not in {"original_playhead", "target", "restored_playhead", "restore_warning"}},
    }
    # Visual truth: the export can succeed while rendering the "Media Offline"
    # placeholder; flag it so callers never reason over garbage pixels.
    from ..core.visual_truth import attach_media_offline_verdict

    attach_media_offline_verdict(data, resolved_path)
    if data.get("media_offline"):
        set_verification_status("failed")
        data["verified"] = False
    output(data, title="Timeline Frame Export")


@app.command("frame-export-batch", hidden=True)
@handle_errors
def frame_export_batch(
    frames: str = typer.Option(..., "--frames", help="Comma-separated timeline positions to sample"),
    out_dir: str = typer.Option(..., "--out-dir", help="Directory for exported stills"),
    prefix: str = typer.Option("frame", "--prefix", help="Output filename prefix"),
    extension: str = typer.Option("png", "--extension", help="Output extension: png|jpg|jpeg"),
    contact_sheet: Optional[str] = typer.Option(None, "--contact-sheet", help="Optional contact sheet image path"),
    contact_columns: int = typer.Option(3, "--contact-columns", help="Contact sheet columns"),
    contact_tile_width: int = typer.Option(480, "--contact-tile-width", help="Contact sheet tile width"),
):
    """Export multiple timeline frames sequentially and restore the playhead once."""
    set_execution_engine("api_native")
    set_capability_context("timeline.frame_export_batch", "supported")
    frame_refs = _parse_frame_refs(frames)
    # Resolve the destination without creating it. Live timeline bounds for the
    # complete batch are validated before the first filesystem or playhead
    # mutation in _export_frame_sequence.
    resolved_out_dir = _resolve_output_directory(out_dir, create=False)
    if contact_sheet:
        contact_path = _resolve_thumbnail_output_file_path(contact_sheet, require_parent=not is_dry_run())
    else:
        contact_path = None
    enforce_mutation_policy("timeline.frame_export_batch", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        planned_frames = [
            {
                "index": index,
                "requested_at": frame_ref,
                "output_path": str(_frame_output_path(resolved_out_dir, prefix=prefix, index=index, frame_ref=frame_ref, extension=extension)),
                "visual_check_path": _workspace_relative_path(_frame_output_path(resolved_out_dir, prefix=prefix, index=index, frame_ref=frame_ref, extension=extension)),
                "would_export": True,
            }
            for index, frame_ref in enumerate(frame_refs)
        ]
        output(
            {
                "requested_frames": frame_refs,
                "out_dir": str(resolved_out_dir),
                "frames": planned_frames,
                "would_restore_playhead_once": True,
                "contact_sheet": str(contact_path) if contact_path else None,
                "exported": False,
                "verified": False,
            },
            title="Timeline Frame Export Batch Preview",
        )
        return

    conn = get_connection(require_timeline=True)
    sequence = _export_frame_sequence(conn, frame_refs=frame_refs, out_dir=resolved_out_dir, prefix=prefix, extension=extension)
    exported_paths = [Path(str(frame["output_path"])) for frame in sequence["frames"]]
    contact = _write_contact_sheet(
        exported_paths,
        contact_path,
        columns=contact_columns,
        tile_width=contact_tile_width,
    ) if contact_path else None
    set_verification_status("verified")
    set_recoverability("manual" if sequence.get("restore_warning") else "not_applicable")
    output(
        {
            "requested_frames": frame_refs,
            "out_dir": str(resolved_out_dir),
            "frames": sequence["frames"],
            "frame_count": len(sequence["frames"]),
            "visual_check_paths": [frame["visual_check_path"] for frame in sequence["frames"]],
            "contact_sheet": contact,
            "original_playhead": sequence["original_playhead"],
            "restored_playhead": sequence["restored_playhead"],
            "restore_warning": sequence["restore_warning"],
            "exported": True,
            "verified": True,
            "page_switch_required": True,
        },
        title="Timeline Frame Export Batch",
    )


@app.command("preview-export")
@handle_errors
def preview_export(
    frames: Optional[str] = typer.Option(None, "--frames", help="Comma-separated frame refs; overrides --start-frame/--end-frame"),
    start_frame: int = typer.Option(0, "--start-frame", help="First timeline-relative frame when --frames is omitted"),
    end_frame: int = typer.Option(120, "--end-frame", help="Last timeline-relative frame when --frames is omitted"),
    step: int = typer.Option(4, "--step", help="Frame step when --frames is omitted"),
    out_dir: str = typer.Option(..., "--out-dir", help="Directory for intermediate stills"),
    output_path: str = typer.Option(..., "--output", "-o", help="Preview video/GIF path"),
    fps: float = typer.Option(12.0, "--fps", help="Preview playback FPS"),
    contact_sheet: Optional[str] = typer.Option(None, "--contact-sheet", help="Optional contact sheet image path"),
):
    """Export a short visual preview from sampled timeline frames."""
    set_execution_engine("api_native")
    set_capability_context("timeline.preview_export", "supported")
    if frames:
        frame_refs = _parse_frame_refs(frames)
    else:
        if step <= 0:
            raise ValidationError("--step must be greater than 0.", details={"step": step})
        if end_frame < start_frame:
            raise ValidationError("--end-frame must be >= --start-frame.", details={"start_frame": start_frame, "end_frame": end_frame})
        frame_refs = [f"{frame}f" for frame in range(start_frame, end_frame + 1, step)]
        if frame_refs[-1] != f"{end_frame}f":
            frame_refs.append(f"{end_frame}f")
    # _export_frame_sequence creates this only after its complete live range
    # preflight. Invalid preview targets must not leave an empty directory.
    resolved_out_dir = _resolve_output_directory(out_dir, create=False)
    resolved_output = _resolve_thumbnail_output_file_path(output_path, require_parent=not is_dry_run())
    contact_path = _resolve_thumbnail_output_file_path(contact_sheet, require_parent=not is_dry_run()) if contact_sheet else None
    enforce_mutation_policy("timeline.preview_export", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        output(
            {
                "requested_frames": frame_refs,
                "out_dir": str(resolved_out_dir),
                "output_path": str(resolved_output),
                "visual_check_path": _workspace_relative_path(resolved_output),
                "fps": fps,
                "contact_sheet": str(contact_path) if contact_path else None,
                "would_export_frames": True,
                "would_encode_preview": True,
            },
            title="Timeline Preview Export Preview",
        )
        return

    conn = get_connection(require_timeline=True)
    sequence = _export_frame_sequence(conn, frame_refs=frame_refs, out_dir=resolved_out_dir, prefix="preview", extension="png")
    exported_paths = [Path(str(frame["output_path"])) for frame in sequence["frames"]]
    preview = _write_preview_video(exported_paths, resolved_output, fps=fps)
    contact = _write_contact_sheet(exported_paths, contact_path) if contact_path else None
    set_verification_status("verified")
    set_recoverability("manual" if sequence.get("restore_warning") else "not_applicable")
    data = {
        "requested_frames": frame_refs,
        "frames": sequence["frames"],
        "frame_count": len(sequence["frames"]),
        "preview": preview,
        "contact_sheet": contact,
        "original_playhead": sequence["original_playhead"],
        "restored_playhead": sequence["restored_playhead"],
        "restore_warning": sequence["restore_warning"],
        "exported": True,
        "verified": True,
        "page_switch_required": True,
    }
    _attach_preview_media_offline_verdict(data, exported_paths)
    output(data, title="Timeline Preview Export")


def _attach_preview_media_offline_verdict(data: dict, exported_paths: list) -> None:
    """Sample exported preview frames for the 'Media Offline' placeholder.

    Checks up to five evenly spread frames — enough to catch offline media in
    a sampled window without paying one decode per frame on long previews.
    """
    from ..core.visual_truth import detect_media_offline

    if not exported_paths:
        return
    if len(exported_paths) <= 5:
        sample = list(exported_paths)
    else:
        last = len(exported_paths) - 1
        indexes = sorted({0, last // 4, last // 2, (3 * last) // 4, last})
        sample = [exported_paths[i] for i in indexes]
    checked = 0
    offline = 0
    for path in sample:
        verdict = detect_media_offline(str(path))
        if verdict is None:
            continue
        checked += 1
        if verdict["media_offline"]:
            offline += 1
    if checked == 0:
        return
    data["media_offline_checked_frames"] = checked
    data["media_offline_frames"] = offline
    data["media_offline"] = offline > 0
    if offline > 0:
        data["media_offline_warning"] = (
            f"{offline} of {checked} sampled frames are the DaVinci Resolve 'Media Offline' "
            "placeholder — the source media is unlinked or unavailable in this range. Do not "
            "treat this preview/contact sheet as the real cut; relink the media first."
        )
        data["verified"] = False
        set_verification_status("failed")


@app.command("set-start-tc")
@handle_errors
def set_start_tc(
    timecode: str = typer.Argument(..., help="Start timecode (HH:MM:SS:FF)"),
):
    """Set timeline start timecode."""
    enforce_mutation_policy("timeline.set_start_tc", intended_engine="api_native")
    conn = get_connection(require_timeline=True)
    result = timeline_ops.set_start_timecode(conn, timecode, return_details=True)
    if is_machine_mode():
        output(
            mutation_payload(
                action="timeline.set_start_tc",
                changed=bool(result.get("changed")),
                target={"kind": "timeline_start_timecode", "timecode": result.get("requested_tc")},
                pre={"timecode": result.get("pre_tc")},
                final={"timecode": result.get("final_tc")},
                api_result=result.get("api_result"),
                verified=result.get("verified"),
            )
        )
        return
    success(f"Timeline start timecode: {result.get('final_tc')}")


@app.command("start-tc")
@handle_errors
def start_tc(
    value: Optional[str] = typer.Argument(None, help="Optional new start timecode"),
):
    """Get or set timeline start timecode (compatibility alias)."""
    conn = get_connection(require_timeline=True)
    if value is None:
        current = conn.timeline.GetStartTimecode() if hasattr(conn.timeline, "GetStartTimecode") else None
        output({"start_timecode": current})
        return
    enforce_mutation_policy("timeline.set_start_tc", intended_engine="api_native")
    result = timeline_ops.set_start_timecode(conn, value, return_details=True)
    if is_machine_mode():
        output(
            mutation_payload(
                action="timeline.set_start_tc",
                changed=bool(result.get("changed")),
                target={"kind": "timeline_start_timecode", "timecode": result.get("requested_tc")},
                pre={"timecode": result.get("pre_tc")},
                final={"timecode": result.get("final_tc")},
                api_result=result.get("api_result"),
                verified=result.get("verified"),
            )
        )
        return
    success(f"Timeline start timecode: {result.get('final_tc')}")


@app.command("item-at")
@handle_errors
def item_at(
    position: str = typer.Argument(..., help="Record-domain position"),
    track_type: str = typer.Option("all", "--track-type", help="video, audio, subtitle, or all"),
    track: Optional[int] = typer.Option(None, "--track", help="Track index"),
):
    """Find timeline item(s) at a position."""
    normalized_track_type = timeline_ops.normalize_item_at_track_type(track_type)
    conn = get_connection(require_timeline=True)
    rows = timeline_ops.get_item_at(conn, position=position, track_type=normalized_track_type, track_index=track)
    output(
        rows,
        columns=[
            ("track_type", "Type"),
            ("track_index", "Track"),
            ("name", "Name"),
            ("start", "Start"),
            ("end", "End"),
            ("duration", "Duration"),
        ],
        title=f"Items at {position}",
    )


@app.command("import-into")
@handle_errors
def import_into(
    file_path: str = typer.Argument(..., help="Timeline import file"),
    offset_tc: Optional[str] = typer.Option(None, "--offset-tc", help="Insert with timeline offset timecode"),
    source_clips_path: Optional[str] = typer.Option(None, "--source-clips-path", help="Source clips path"),
    options_json: Optional[str] = typer.Option(None, "--options-json", help="Additional import options as JSON"),
):
    """Import timeline content into the active timeline."""
    enforce_mutation_policy("timeline.import_export", intended_engine="api_native", mutating=not is_dry_run())
    options = json.loads(options_json) if options_json else None
    if options is not None and not isinstance(options, dict):
        raise ValidationError("--options-json must decode to a JSON object.")
    if is_dry_run():
        dry_run_message(f"Would import timeline content into current timeline from: {file_path}")
        return
    conn = get_connection(require_timeline=True)
    output(timeline_ops.import_into_timeline(conn, file_path, offset_tc=offset_tc, source_clips_path=source_clips_path, options=options), title="Timeline Import")


fusion_composition_app = typer.Typer(help="Timeline Fusion composition operations.")
app.add_typer(fusion_composition_app, name="fusion-composition")


@fusion_composition_app.command("insert")
@handle_errors
def fusion_composition_insert():
    """Insert a Fusion composition into the active timeline."""
    enforce_mutation_policy("fusion.comp_add_delete_import_export", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        dry_run_message("Would insert a Fusion composition into the active timeline.")
        return
    conn = get_connection(require_timeline=True)
    output(timeline_ops.insert_fusion_composition(conn), title="Fusion Composition")


fusion_clip_app = typer.Typer(help="Timeline Fusion clip operations.")
app.add_typer(fusion_clip_app, name="fusion-clip")


@fusion_clip_app.command("create")
@handle_errors
def fusion_clip_create(
    clips: list[str] = typer.Argument(..., help="Timeline clip names"),
):
    """Create a Fusion clip from timeline items."""
    enforce_mutation_policy("fusion.comp_add_delete_import_export", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        dry_run_message(f"Would create a Fusion clip from {len(clips)} item(s).")
        return
    conn = get_connection(require_timeline=True)
    output(timeline_ops.create_fusion_clip(conn, clips), title="Fusion Clip")


still_app = typer.Typer(help="Timeline still operations.")
app.add_typer(still_app, name="still")


@still_app.command("grab-all")
@handle_errors
def still_grab_all(
    source: str = typer.Option("first", "--source", help="Still source: first or middle"),
):
    """Grab stills for all clips on the current timeline."""
    enforce_mutation_policy("timeline.grab_still", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        dry_run_message(f"Would grab all stills from {source} frame.")
        return
    conn = get_connection(require_timeline=True)
    output(timeline_ops.grab_all_stills(conn, source), title="Grab All Stills")


dolby_app = typer.Typer(help="Dolby Vision timeline analysis.")
app.add_typer(dolby_app, name="dolby")


@dolby_app.command("analyze")
@handle_errors
def dolby_analyze(
    items: Optional[list[str]] = typer.Option(None, "--items", help="Timeline item names"),
    blend_shots: bool = typer.Option(False, "--blend-shots", help="Blend shots during analysis"),
    enable_project_controls: bool = typer.Option(True, "--enable-project-controls/--no-enable-project-controls", help="Enable required Dolby Vision/HDR project controls via native Project.SetSetting before analysis"),
):
    """Run Dolby Vision analysis through DaVinci Resolve's native timeline API."""
    enforce_mutation_policy("timeline.dolby_vision", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        dry_run_message("Would run Dolby Vision timeline analysis.")
        return
    conn = get_connection(require_timeline=True)
    output(timeline_ops.analyze_dolby_vision(conn, items, blend_shots=blend_shots, enable_project_controls=enable_project_controls), title="Dolby Vision Analysis")


mark_app = typer.Typer(help="Timeline mark in/out operations.")
app.add_typer(mark_app, name="mark")


@mark_app.command("get")
@handle_errors
def mark_get():
    """Show timeline mark in/out points."""
    conn = get_connection(require_timeline=True)
    output(timeline_ops.get_mark_in_out(conn), title="Timeline Mark")


@mark_app.command("set")
@handle_errors
def mark_set(
    mark_in: int = typer.Option(..., "--in", help="Mark-in frame"),
    mark_out: int = typer.Option(..., "--out", help="Mark-out frame"),
    mark_type: str = typer.Option("all", "--type", help="all|video|audio"),
):
    """Set timeline mark in/out points."""
    enforce_mutation_policy("timeline.marker_crud", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        dry_run_message(f"Would set timeline {mark_type} mark range to {mark_in}-{mark_out}.")
        return
    conn = get_connection(require_timeline=True)
    output(timeline_ops.set_mark_in_out(conn, mark_in, mark_out, mark_type), title="Timeline Mark")


@mark_app.command("clear")
@handle_errors
def mark_clear(
    mark_type: str = typer.Option("all", "--type", help="all|video|audio"),
):
    """Clear timeline mark in/out points."""
    enforce_mutation_policy("timeline.marker_crud", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        dry_run_message(f"Would clear timeline {mark_type} mark range.")
        return
    conn = get_connection(require_timeline=True)
    output(timeline_ops.clear_mark_in_out(conn, mark_type), title="Timeline Mark")


voice_isolation_app = typer.Typer(help="Timeline voice isolation operations.")
app.add_typer(voice_isolation_app, name="voice-isolation")
