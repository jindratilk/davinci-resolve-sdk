from __future__ import annotations

@app.command("rename")
@handle_errors
def rename_timeline(
    new_name: str = typer.Argument(..., help="New timeline name"),
    source: Optional[str] = typer.Option(
        None,
        "--source",
        help="Optional source timeline name; defaults to current timeline",
    ),
):
    """Rename a timeline."""
    enforce_mutation_policy(
        "timeline.rename",
        intended_engine="api_native",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(_timeline_rename_dry_run_payload(new_name=new_name, source=source), title="Rename Timeline Dry Run")
        return

    conn = get_connection(require_project=True, require_timeline=source is None)
    result = timeline_ops.rename_timeline(conn, new_name, source_name=source, return_details=True)
    output(
        mutation_payload(
            action="timeline.rename",
            changed=bool(result.get("changed")),
            target=result.get("target"),
            source=result.get("source"),
            pre=result.get("pre"),
            final=result.get("final"),
            requested=result.get("requested"),
            api_result=result.get("api_result"),
            verified=result.get("verified"),
            message=f"Renamed timeline to: {result.get('final', {}).get('name')}",
        )
    )


@app.command("import")
@handle_errors
def import_timeline(
    path: str = typer.Argument(..., help="Path to EDL/XML/AAF/DRT/OTIO file"),
):
    """Import a timeline from file."""
    enforce_mutation_policy("timeline.import_export", intended_engine="api_native")
    conn = get_connection(require_project=True)
    timeline_ops.import_timeline(conn, path)
    success(f"Imported timeline from: {path}")


@app.command("export")
@handle_errors
def export_timeline(
    path: str = typer.Argument(..., help="Output path"),
    format: str = typer.Option("edl", help="Export format: edl, fcpxml, aaf, otio, drt"),
):
    """Export the current timeline."""
    enforce_mutation_policy("timeline.import_export", intended_engine="api_native")
    conn = get_connection(require_timeline=True)
    timeline_ops.export_timeline(conn, path, format)
    success(f"Exported timeline to: {path}")


@app.command("inspect-export")
@handle_errors
def inspect_export_timeline(
    path: str = typer.Argument(..., help="Output path for the detailed inspection document"),
    force: bool = typer.Option(False, "--force", "-f", help="Replace an existing regular file"),
):
    """Export an explicit detailed, inspection-only timeline document."""
    set_execution_engine("api_native")
    set_capability_context("timeline.inspection_export", "supported")
    conn = get_connection(require_timeline=True)
    result = timeline_inspection_export.write_timeline_inspection(conn, path, force=force)
    set_verification_status("verified")
    set_recoverability("not_applicable")
    output(result, title="Timeline Inspection Export")


@app.command("duration")
@handle_errors
def duration():
    """Show timeline duration."""
    ui_state = _probe_current_item_ui_context()
    conn = get_connection(require_timeline=True)
    data = timeline_ops.get_timeline_duration(conn)
    _attach_duration_readback_context(data, conn)
    _attach_current_item_ui_context(data, ui_state)
    output(data)


@app.command("summarize")
@handle_errors
def summarize_timeline(
    window: str = typer.Option(
        "current",
        "--window",
        help="Summary window: current (around playhead), all, or range. --from/--to imply range. Use --window all only when the full-timeline map is really needed; it can be very large.",
    ),
    radius: str = typer.Option(
        "30s",
        "--radius",
        help="Radius around the playhead for --window current, for example 30s or 720f.",
    ),
    start_ref: Optional[str] = typer.Option(
        None,
        "--from",
        help="Record-domain range start: timecode, seconds, or frames.",
    ),
    end_ref: Optional[str] = typer.Option(
        None,
        "--to",
        help="Record-domain range end: timecode, seconds, or frames.",
    ),
    track_type: str = typer.Option(
        "all",
        "--track-type",
        help="Track type to summarize: all, video, audio, or subtitle.",
    ),
    max_runs: int = typer.Option(
        24,
        "--max-runs",
        help="Maximum source runs to include per track.",
    ),
    include_items: bool = typer.Option(
        False,
        "--include-items",
        help="Include compact per-item rows for the summarized window.",
    ),
):
    """Summarize the current timeline as an editor-readable map."""
    set_execution_engine("api_native")
    conn = get_connection(require_timeline=True)
    data = timeline_ops.summarize_timeline(
        conn,
        window=window,
        radius=radius,
        start_ref=start_ref,
        end_ref=end_ref,
        track_type=track_type,
        max_runs=max_runs,
        include_items=include_items,
    )
    output(data, title="Timeline Summary")


@handle_errors
def _sdk_live_inspect_command(
    operation: str = typer.Argument(..., help="Typed SDK inspection operation."),
    deadline_at_ms: int = typer.Option(
        ...,
        "--deadline-at-ms",
        min=1,
        help="Absolute Unix epoch deadline in milliseconds.",
    ),
    offset: int = typer.Option(0, "--offset", min=0, max=1_000_000),
    page_size: int = typer.Option(32, "--page-size", min=1, max=32),
    search_json: Optional[str] = typer.Option(None, "--search-json", hidden=True),
    multicam_name: Optional[str] = typer.Option(None, "--multicam-name", hidden=True),
    managed_affected_json: Optional[str] = typer.Option(None, "--managed-affected-json", hidden=True),
    managed_retained_database_json: Optional[str] = typer.Option(None, "--managed-retained-database-json", hidden=True),
    retime_targets_json: Optional[str] = typer.Option(None, "--retime-targets-json", hidden=True),
    node_stack_layer_index: int = typer.Option(1, "--node-stack-layer", min=1, max=4096, hidden=True),
):
    """Return the private typed, bracketed SDK live-inspection contract."""
    set_execution_engine("api_native")
    timeline_ops.validate_sdk_live_inspection_deadline(deadline_at_ms)
    search = None
    if search_json is not None:
        try:
            search = json.loads(search_json)
        except json.JSONDecodeError as exc:
            raise ValidationError("SDK Media Pool search payload is malformed.") from exc
        if not isinstance(search, dict) or set(search) != {"query", "match", "fields"}:
            raise ValidationError("SDK Media Pool search payload must use the closed search contract.")
        query = search["query"]
        if not isinstance(query, str) or not query.strip():
            raise ValidationError("SDK Media Pool search query is invalid.")
        try:
            query_size = len(query.encode("utf-8"))
        except UnicodeEncodeError as exc:
            raise ValidationError("SDK Media Pool search query is invalid.") from exc
        if query_size > 1024:
            raise ValidationError("SDK Media Pool search query is invalid.")
        if search["match"] not in {"contains", "exact"}:
            raise ValidationError("SDK Media Pool search match mode is invalid.")
        fields = search["fields"]
        if not isinstance(fields, list) or not fields or len(fields) > 3 or len(set(fields)) != len(fields):
            raise ValidationError("SDK Media Pool search fields are invalid.")
        if any(field not in {"name", "metadata", "sourceFileName"} for field in fields):
            raise ValidationError("SDK Media Pool search field is unsupported.")
    conn = get_connection(require_project=False)
    managed_affected_native_ids = None
    managed_retained_database_native_ids = None
    if managed_affected_json is not None:
        try:
            managed_affected_native_ids = json.loads(managed_affected_json)
        except json.JSONDecodeError as exc:
            raise ValidationError("Managed protected-state affected identities are malformed.") from exc
        if (not isinstance(managed_affected_native_ids, list)
                or not all(isinstance(value, str) and value for value in managed_affected_native_ids)
                or len(set(managed_affected_native_ids)) != len(managed_affected_native_ids)):
            raise ValidationError("Managed protected-state affected identities are invalid.")
    if managed_retained_database_json is not None:
        try:
            managed_retained_database_native_ids = json.loads(managed_retained_database_json)
        except json.JSONDecodeError as exc:
            raise ValidationError("Managed protected-state retained database identities are malformed.") from exc
        if (not isinstance(managed_retained_database_native_ids, list)
                or not all(isinstance(value, str) and value for value in managed_retained_database_native_ids)
                or len(set(managed_retained_database_native_ids)) != len(managed_retained_database_native_ids)):
            raise ValidationError("Managed protected-state retained database identities are invalid.")
    retime_expected_targets = None
    if retime_targets_json is not None:
        try:
            retime_expected_targets = json.loads(retime_targets_json)
        except json.JSONDecodeError as exc:
            raise ValidationError("SDK retime target identities are malformed.") from exc
        if (operation != "timeline.retime"
                or not isinstance(retime_expected_targets, list)
                or not retime_expected_targets
                or len(retime_expected_targets) > 514):
            raise ValidationError("SDK retime target identities are invalid.")
    elif operation == "timeline.retime":
        raise ValidationError("SDK retime inspection requires exact native targets.")
    if operation.startswith("render."):
        from ..core.sdk_render_inspection import inspect_sdk_render_state

        output(
            inspect_sdk_render_state(conn, deadline_at_ms=deadline_at_ms),
            title="SDK Render Inspection",
        )
        return
    output(
        timeline_ops.inspect_sdk_live_state(
            conn,
            operation,
            deadline_at_ms=deadline_at_ms,
            offset=offset,
            page_size=page_size,
            search=search,
            multicam_name=multicam_name,
            inspect_multicam=_sdk_multicam_summary,
            managed_affected_native_ids=managed_affected_native_ids,
            managed_retained_database_native_ids=managed_retained_database_native_ids,
            retime_expected_targets=retime_expected_targets,
            inspect_retime=lambda current, targets: speed_ramp_db.inspect_selected_retime_rows(
                current,
                expected_targets=targets,
            ),
            node_stack_layer_index=node_stack_layer_index,
        ),
        title="SDK Live Inspection",
    )


# Private desktop transport boundary. Dynamic registration deliberately keeps
# this command out of public command/reference catalogs and normal CLI help.
app.command("sdk-live-inspect", hidden=True)(_sdk_live_inspect_command)


@app.command("settings-get")
@app.command("settings")
@handle_errors
def timeline_settings(
    key: Optional[str] = typer.Argument(None, help="Specific setting key"),
):
    """Show timeline settings."""
    conn = get_connection(require_timeline=True)
    if key:
        val = timeline_ops.get_timeline_settings(conn, key)
        output({key: val})
        return

    settings = timeline_ops.get_timeline_settings(conn)
    if isinstance(settings, dict):
        output(settings, title="Timeline Settings")
    else:
        output({"settings": str(settings)})


@app.command("settings-set")
@handle_errors
def timeline_settings_set(
    key: str = typer.Argument(...),
    value: str = typer.Argument(...),
):
    """Set a timeline setting."""
    enforce_mutation_policy("timeline.settings_write", intended_engine="api_native")
    conn = get_connection(require_timeline=True)
    result = timeline_ops.set_timeline_setting(conn, key, value, return_details=True)
    output(
        mutation_payload(
            action="timeline.settings_set",
            changed=bool(result.get("changed")),
            target={"kind": "timeline_setting", "name": result.get("key")},
            value=result.get("requested"),
            read_back=result.get("read_back"),
            api_result=result.get("api_result"),
            verified=result.get("verified"),
            message=f"Set {result.get('key')} = {result.get('read_back')}",
        )
    )


@app.command("subtitles")
@handle_errors
def subtitles():
    """Clarify whether the request should use a subtitle track or Fusion Text+."""
    output(_caption_route_prompt("subtitles"), title="Subtitle Route Choice")


@app.command("captions")
@handle_errors
def captions():
    """Clarify whether the request should use a subtitle track or Fusion Text+."""
    output(_caption_route_prompt("captions"), title="Caption Route Choice")


# --- Playhead ---

playhead_app = typer.Typer(help="Playhead control.")
app.add_typer(playhead_app, name="playhead")


@playhead_app.command("get")
@handle_errors
def playhead_get():
    """Show current playhead position."""
    conn = get_connection(require_timeline=True)
    data = timeline_ops.get_playhead(conn)
    output(data)


@playhead_app.command("set")
@handle_errors
def playhead_set(
    position: str = typer.Argument(..., help="Position: timecode (00:01:30:00), seconds (90.5s), or frames (2250f)"),
):
    """Set playhead position."""
    enforce_mutation_policy("timeline.playhead_set", intended_engine="api_native")
    conn = get_connection(require_timeline=True)
    try:
        result = timeline_ops.set_playhead(conn, position, return_details=True)
    except APICallFailed as exc:
        ui_state = _probe_current_item_ui_context()
        ui_summary = _ui_readback_summary(ui_state)
        exc.details.setdefault("ui", ui_state)
        exc.details.update(ui_summary)
        if not ui_summary["visual_readback_available"]:
            exc.recoverability = "manual"
        raise
    if is_machine_mode():
        output(
            mutation_payload(
                action="timeline.playhead_set",
                changed=bool(result.get("changed")),
                target={"kind": "playhead", "timecode": result.get("target_tc"), "frame": result.get("target_frame")},
                final={"timecode": result.get("final_tc"), "frame": result.get("final_frame")},
                pre={"timecode": result.get("pre_tc"), "frame": result.get("pre_frame")},
                api_result=result.get("api_result"),
                verified=result.get("verified"),
            )
        )
        return
    success(f"Playhead at: {result.get('final_tc')}")


# --- Markers ---

marker_app = typer.Typer(help="Timeline marker operations.")
app.add_typer(marker_app, name="marker")


def _dedupe_marker_rows(rows: list) -> list:
    """Drop duplicated frame/timecode aliases when they match the primary fields.

    ``frame``/``timeline_frame``/``record_frame`` (and the timecode triplet) are
    identical for ordinary timelines; repeating them costs tokens without adding
    information. Applied only in lean/agent output, so the JSON contract is
    unchanged by default.
    """
    deduped = []
    for row in rows:
        if not isinstance(row, dict):
            deduped.append(row)
            continue
        slim = dict(row)
        for primary, aliases in (
            ("frame", ("timeline_frame", "record_frame")),
            ("timecode", ("timeline_timecode", "record_timecode")),
        ):
            for alias in aliases:
                if alias in slim and slim.get(alias) == slim.get(primary):
                    slim.pop(alias)
        deduped.append(slim)
    return deduped


@marker_app.command("list")
@handle_errors
def marker_list():
    """List all timeline markers."""
    ui_state = _probe_current_item_ui_context()
    conn = get_connection(require_timeline=True)
    rows = timeline_ops.list_markers(conn)
    if is_agent_mode() or is_lean():
        rows = _dedupe_marker_rows(rows)
    if is_machine_mode():
        ui_summary = _ui_readback_summary(ui_state)
        if not ui_summary["visual_readback_available"]:
            set_verification_status("pending_manual")
            set_recoverability("manual")
        output(
            {
                "timeline": _current_item_context(conn).get("timeline"),
                "marker_count": len(rows),
                "markers": rows,
                **ui_summary,
            },
            title="Timeline Markers",
        )
        return
    output(rows, columns=[
        ("frame", "Frame"), ("timecode", "Timecode"), ("color", "Color"),
        ("name", "Name"), ("note", "Note"), ("duration", "Duration"),
    ], title="Timeline Markers")


@marker_app.command("add")
@handle_errors
def marker_add(
    position: str = typer.Argument(..., help="Position (timecode, seconds, frames)"),
    color: str = typer.Option("Blue", help="Marker color"),
    name: str = typer.Option("", help="Marker name"),
    note: str = typer.Option("", help="Marker note"),
    duration: int = typer.Option(1, help="Duration in frames"),
):
    """Add a marker at a position."""
    enforce_mutation_policy("timeline.marker_crud", intended_engine="api_native")
    conn = get_connection(require_timeline=True)
    timeline_ops.require_sdk_marker_mutation_guard(conn)
    result = timeline_ops.add_marker(conn, position, color, name, note, duration)
    if is_machine_mode():
        output(
            mutation_payload(
                action="timeline.marker.add",
                changed=True,
                target={
                    "kind": "timeline_marker",
                    "timeline_frame": result.get("timeline_frame"),
                    "record_frame": result.get("record_frame"),
                },
                **result,
                message=f"Added {color} marker",
            ),
            title="Timeline Marker Added",
        )
        return
    success(f"Added {color} marker")


@marker_app.command("update")
@handle_errors
def marker_update(
    frame: int = typer.Option(..., help="Exact timeline or record frame of the marker to update"),
    position: Optional[str] = typer.Option(None, help="Optional new position (timecode, seconds, frames)"),
    color: Optional[str] = typer.Option(None, help="Optional new marker color"),
    name: Optional[str] = typer.Option(None, help="Optional new marker name"),
    note: Optional[str] = typer.Option(None, help="Optional new marker note"),
    duration: Optional[int] = typer.Option(None, help="Optional new duration in frames"),
):
    """Update one exact marker with rollback on replacement failure."""
    enforce_mutation_policy("timeline.marker_crud", intended_engine="api_native")
    conn = get_connection(require_timeline=True)
    timeline_ops.require_sdk_marker_mutation_guard(conn)
    result = timeline_ops.update_marker(
        conn, frame, position=position, color=color, name=name, note=note, duration=duration
    )
    if is_machine_mode():
        payload = dict(result)
        changed = bool(payload.pop("changed", True))
        output(
            mutation_payload(
                action="timeline.marker.update",
                changed=changed,
                target={"kind": "timeline_marker", "timeline_frame": result.get("timeline_frame")},
                **payload,
            ),
            title="Timeline Marker Updated",
        )
        return
    success("Updated marker")


@marker_app.command("delete")
@handle_errors
def marker_delete(
    frame: Optional[int] = typer.Option(None, help="Delete marker at specific frame"),
    color: Optional[str] = typer.Option(None, help="Delete all markers of a color"),
    all: bool = typer.Option(False, "--all", help="Delete all markers"),
):
    """Delete markers."""
    enforce_mutation_policy("timeline.marker_crud", intended_engine="api_native")
    conn = get_connection(require_timeline=True)
    timeline_ops.require_sdk_marker_mutation_guard(conn)
    result = timeline_ops.delete_marker(conn, frame, color, all)
    if is_machine_mode():
        payload = dict(result)
        changed = bool(payload.pop("changed", True))
        target = {"kind": "timeline_marker", "mode": result.get("mode")}
        if result.get("mode") == "frame":
            target.update(
                {
                    "requested_frame": result.get("requested_frame"),
                    "timeline_frame": result.get("timeline_frame"),
                    "record_frame": result.get("record_frame"),
                }
            )
        elif result.get("mode") == "color":
            target["color"] = result.get("color")
        output(
            mutation_payload(
                action="timeline.marker.delete",
                changed=changed,
                target=target,
                **payload,
                message=(
                    "Deleted all markers."
                    if all
                    else f"Deleted all {color} markers."
                    if color
                    else f"Deleted marker at frame {frame}."
                ),
            ),
            title="Timeline Marker Deleted",
        )
        return
    if all:
        success("Deleted all markers.")
    elif color:
        success(f"Deleted all {color} markers.")
    else:
        success(f"Deleted marker at frame {frame}.")


@marker_app.command("batch")
@handle_errors
def marker_batch(
    batch: str | None = typer.Option(None, "--batch", help="Batch JSON path"),
    batch_json: str | None = typer.Option(None, "--batch-json", help="Inline batch JSON payload"),
    spec_json: str | None = typer.Option(None, "--spec-json", help="Inline batch JSON payload alias"),
    timeline_name: str | None = typer.Option(None, "--timeline-name", "--timeline", help="Target timeline name; defaults to active timeline"),
    default_color: str = typer.Option("Blue", "--default-color", help="Fallback marker color"),
    prefix: str = typer.Option("", "--prefix", help="Prefix prepended to each marker name"),
    shift_occupied: bool = typer.Option(True, "--shift-occupied/--no-shift-occupied", help="Auto-shift marker collisions by +1 frame"),
):
    """Batch add timeline markers from range or single-frame specs."""
    entries = _load_json_object_entries(
        path=batch,
        raw_json=batch_json,
        alt_raw_json=spec_json,
        wrapper_keys=("markers", "ranges"),
        label="Timeline marker batch",
    )
    set_execution_engine("api_native")
    enforce_mutation_policy("timeline.marker_crud", intended_engine="api_native", mutating=not is_dry_run())

    require_timeline = timeline_name is None
    conn = get_connection(require_project=True, require_timeline=require_timeline)
    plan = timeline_markers.plan_timeline_marker_batch(
        conn,
        entries=entries,
        timeline_name=timeline_name,
        default_color=default_color,
        prefix=prefix,
        shift_occupied=shift_occupied,
    )
    if is_dry_run():
        output(
            mutation_payload(
                action="timeline.marker.batch",
                changed=False,
                target={"kind": "timeline", "name": plan["timeline_name"] or timeline_name or "current"},
                timeline_name=plan["timeline_name"],
                requested_count=plan["preflight"]["requested_count"],
                default_color=plan["default_color"],
                prefix=plan["prefix"],
                shift_occupied=plan["shift_occupied"],
                preflight=plan["preflight"],
                markers=plan["entries"],
                ready=plan["preflight"]["ready"],
                dry_run=True,
                message=(
                    "DRY-RUN: Would add timeline markers from the requested batch."
                    if plan["preflight"]["ready"]
                    else "DRY-RUN: Marker batch preflight found collisions; a real run would fail unless auto-shift stays enabled."
                ),
            ),
            title="Timeline Marker Batch Plan",
        )
        return

    data = timeline_markers.apply_timeline_marker_batch(
        conn,
        entries=entries,
        timeline_name=timeline_name,
        default_color=default_color,
        prefix=prefix,
        shift_occupied=shift_occupied,
    )
    payload = dict(data)
    output(
        mutation_payload(
            action=str(payload.pop("action", "timeline.marker.batch")),
            target={"kind": "timeline", "name": data.get("timeline_name") or timeline_name or "current"},
            changed=bool(data.get("created_count")),
            **payload,
        ),
        title="Timeline Marker Batch",
    )


# --- Clip marker readback ---

clip_markers_app = typer.Typer(help="Timeline-wide clip marker readback.")
app.add_typer(clip_markers_app, name="clip-markers")


@clip_markers_app.command("list")
@handle_errors
def clip_markers_list(
    color: Optional[str] = typer.Option(None, "--color", help="Only include clip markers with this color"),
    track_type: str = typer.Option("video", "--track-type", help="Track type: video, audio, or all"),
    tracks: list[int] | None = typer.Option(None, "--track", help="Track index to scan; repeat for multiple tracks"),
    visible_only: bool = typer.Option(
        True,
        "--visible-only/--include-hidden-source-markers",
        help="Only include markers whose source frame is visible in each timeline item",
    ),
):
    """List clip markers attached to timeline items."""
    set_capability_context("clip.marker", "supported")
    set_execution_engine("api_native")
    enforce_mutation_policy("clip.marker", intended_engine="api_native", mutating=False)
    conn = get_connection(require_timeline=True)
    data = clip_ops.list_timeline_clip_markers(
        conn,
        track_type=track_type,
        tracks=tracks,
        color=color,
        visible_only=visible_only,
    )
    if is_machine_mode():
        output(data, title="Timeline Clip Markers")
        return
    output(
        data["markers"],
        columns=[
            ("timecode", "Timecode"),
            ("track_index", "Track"),
            ("clip_name", "Clip"),
            ("color", "Color"),
            ("name", "Name"),
            ("note", "Note"),
        ],
        title="Timeline Clip Markers",
    )


# --- Tracks ---

track_app = typer.Typer(help="Track management.")
tracks_app = typer.Typer(help="Track management.")
app.add_typer(track_app, name="track")
app.add_typer(tracks_app, name="tracks", hidden=True)

items_app = typer.Typer(help="Timeline item operations.")
app.add_typer(items_app, name="items")

clip_color_app = typer.Typer(help="Timeline clip-color operations.")
app.add_typer(clip_color_app, name="clip-color")

layout_app = typer.Typer(help="Timeline layout planning.")
app.add_typer(layout_app, name="layout")

overlay_stack_app = typer.Typer(help="Timeline overlay stack insertion.")
app.add_typer(overlay_stack_app, name="overlay-stack")

layer_app = typer.Typer(help="Timeline layer operations.")
app.add_typer(layer_app, name="layer")


def _output_track_list():
    conn = get_connection(require_timeline=True)
    rows = timeline_ops.list_tracks(conn)
    output(rows, columns=[
        ("type", "Type"), ("index", "#"), ("name", "Name"),
        ("items", "Items"), ("enabled", "On"), ("locked", "Lock"),
    ], title="Tracks")


@tracks_app.callback(invoke_without_command=True)
@handle_errors
def tracks_root(ctx: typer.Context):
    """Compatibility alias for agents that ask for timeline tracks."""
    if ctx.invoked_subcommand is None:
        _output_track_list()


@track_app.command("list")
@handle_errors
def track_list():
    """List all tracks."""
    _output_track_list()


@track_app.command("add")
@handle_errors
def track_add(
    track_type: str = typer.Argument(..., help="Track type: video, audio, subtitle"),
    subtype: Optional[str] = typer.Option(None, "--subtype", help="Optional audio subtype"),
    index: Optional[int] = typer.Option(None, "--index", help="Optional insertion index"),
):
    """Add a new track."""
    enforce_mutation_policy("timeline.track_management", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        dry_run_message(f"Would add {track_type} track (subtype={subtype}, index={index}).")
        return
    conn = get_connection(require_timeline=True)
    timeline_ops.add_track(conn, track_type, subtype=subtype, index=index)
    success(f"Added {track_type} track.")


@track_app.command("delete")
@handle_errors
def track_delete(
    track_type: str = typer.Argument(..., help="Track type: video, audio, subtitle"),
    index: int = typer.Argument(..., help="Track index"),
):
    """Delete a timeline track."""
    enforce_mutation_policy("timeline.track_management", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        dry_run_message(f"Would delete {track_type} track {index}.")
        return
    conn = get_connection(require_timeline=True)
    output(timeline_ops.delete_track(conn, track_type, index), title="Delete Track")


@track_app.command("subtype")
@handle_errors
def track_subtype(
    track_type: str = typer.Argument(..., help="Track type: video, audio, subtitle"),
    index: int = typer.Argument(..., help="Track index"),
):
    """Show a track subtype when DaVinci Resolve exposes it."""
    conn = get_connection(require_timeline=True)
    output(timeline_ops.get_track_subtype(conn, track_type, index), title="Track Subtype")


@track_app.command("rename")
@handle_errors
def track_rename(
    track_type: str = typer.Argument(..., help="video, audio, subtitle"),
    index: int = typer.Argument(..., help="Track index"),
    name: str = typer.Argument(..., help="New name"),
):
    """Rename a track."""
    enforce_mutation_policy("timeline.track_management", intended_engine="api_native")
    conn = get_connection(require_timeline=True)
    timeline_ops.rename_track(conn, track_type, index, name)
    success(f"Renamed {track_type} track {index} to: {name}")


@track_app.command("enable")
@handle_errors
def track_enable(
    track_type: str = typer.Argument(...),
    index: int = typer.Argument(...),
):
    """Enable a track."""
    set_capability_context("timeline.track_management", "supported")
    set_execution_engine("api_native")
    normalized_type = timeline_ops.normalize_timeline_track_type(track_type)
    normalized_index = timeline_ops.validate_timeline_track_index(index)
    enforce_mutation_policy("timeline.track_management", intended_engine="api_native")
    conn = get_connection(require_timeline=True)
    result = timeline_ops.set_track_enabled(conn, normalized_type, normalized_index, True, return_details=True)
    message = f"Enabled {normalized_type} track {normalized_index}."
    if is_machine_mode():
        output(
            mutation_payload(
                action="timeline.track.enable",
                changed=True,
                target={
                    "kind": "timeline_track",
                    "track_type": normalized_type,
                    "index": normalized_index,
                },
                value={"enabled": True},
                read_back={"enabled": result.get("read_back_enabled") if result else None},
                api_result=result.get("api_result") if result else None,
                verified=bool(result.get("verified")) if result else False,
                message=message,
            )
        )
    success(message)


@track_app.command("disable")
@handle_errors
def track_disable(
    track_type: str = typer.Argument(...),
    index: int = typer.Argument(...),
):
    """Disable (mute) a track."""
    set_capability_context("timeline.track_management", "supported")
    set_execution_engine("api_native")
    normalized_type = timeline_ops.normalize_timeline_track_type(track_type)
    normalized_index = timeline_ops.validate_timeline_track_index(index)
    enforce_mutation_policy("timeline.track_management", intended_engine="api_native")
    conn = get_connection(require_timeline=True)
    result = timeline_ops.set_track_enabled(conn, normalized_type, normalized_index, False, return_details=True)
    message = f"Disabled {normalized_type} track {normalized_index}."
    if is_machine_mode():
        output(
            mutation_payload(
                action="timeline.track.disable",
                changed=True,
                target={
                    "kind": "timeline_track",
                    "track_type": normalized_type,
                    "index": normalized_index,
                },
                value={"enabled": False},
                read_back={"enabled": result.get("read_back_enabled") if result else None},
                api_result=result.get("api_result") if result else None,
                verified=bool(result.get("verified")) if result else False,
                message=message,
            )
        )
    success(message)


@track_app.command("lock")
@handle_errors
def track_lock(
    track_type: str = typer.Argument(...),
    index: int = typer.Argument(...),
):
    """Lock a track."""
    set_capability_context("timeline.track_management", "supported")
    set_execution_engine("api_native")
    normalized_type = timeline_ops.normalize_timeline_track_type(track_type)
    normalized_index = timeline_ops.validate_timeline_track_index(index)
    enforce_mutation_policy("timeline.track_management", intended_engine="api_native")
    conn = get_connection(require_timeline=True)
    result = timeline_ops.set_track_locked(conn, normalized_type, normalized_index, True, return_details=True)
    message = f"Locked {normalized_type} track {normalized_index}."
    if is_machine_mode():
        output(
            mutation_payload(
                action="timeline.track.lock",
                changed=True,
                target={
                    "kind": "timeline_track",
                    "track_type": normalized_type,
                    "index": normalized_index,
                },
                value={"locked": True},
                read_back={"locked": result.get("read_back_locked") if result else None},
                api_result=result.get("api_result") if result else None,
                verified=bool(result.get("verified")) if result else False,
                message=message,
            )
        )
    success(message)


@track_app.command("unlock")
@handle_errors
def track_unlock(
    track_type: str = typer.Argument(...),
    index: int = typer.Argument(...),
):
    """Unlock a track."""
    set_capability_context("timeline.track_management", "supported")
    set_execution_engine("api_native")
    normalized_type = timeline_ops.normalize_timeline_track_type(track_type)
    normalized_index = timeline_ops.validate_timeline_track_index(index)
    enforce_mutation_policy("timeline.track_management", intended_engine="api_native")
    conn = get_connection(require_timeline=True)
    result = timeline_ops.set_track_locked(conn, normalized_type, normalized_index, False, return_details=True)
    message = f"Unlocked {normalized_type} track {normalized_index}."
    if is_machine_mode():
        output(
            mutation_payload(
                action="timeline.track.unlock",
                changed=True,
                target={
                    "kind": "timeline_track",
                    "track_type": normalized_type,
                    "index": normalized_index,
                },
                value={"locked": False},
                read_back={"locked": result.get("read_back_locked") if result else None},
                api_result=result.get("api_result") if result else None,
                verified=bool(result.get("verified")) if result else False,
                message=message,
            )
        )
    success(message)


@track_app.command("items")
@handle_errors
def track_items(
    track_type: str = typer.Argument(..., help="video, audio, subtitle"),
    index: int = typer.Argument(..., help="Track index"),
):
    """List clips on a specific track."""
    set_capability_context("timeline.track_management", "supported")
    set_execution_engine("api_native")
    normalized_type = timeline_ops.normalize_timeline_track_type(track_type)
    normalized_index = timeline_ops.validate_timeline_track_index(index)
    conn = get_connection(require_timeline=True)
    rows = timeline_ops.get_track_items(conn, normalized_type, normalized_index)
    output(rows, columns=[("name", "Name"), ("start", "Start"), ("end", "End"), ("duration", "Duration")],
           title=f"{normalized_type.title()} Track {normalized_index} Items")


for _track_alias_name, _track_alias_func in (
    ("list", track_list),
    ("add", track_add),
    ("delete", track_delete),
    ("subtype", track_subtype),
    ("rename", track_rename),
    ("enable", track_enable),
    ("disable", track_disable),
    ("lock", track_lock),
    ("unlock", track_unlock),
    ("items", track_items),
):
    tracks_app.command(_track_alias_name)(_track_alias_func)

del _track_alias_name, _track_alias_func


@items_app.command("delete")
@handle_errors
def items_delete(
    timeline_name: str | None = typer.Option(None, "--timeline", help="Target timeline name; defaults to active timeline"),
    track_type: str = typer.Option("all", "--track-type", help="video, audio, subtitle, or all"),
    track_index: int | None = typer.Option(None, "--track-index", "--track", help="Only delete items on this track index"),
    start_frame: str | None = typer.Option(None, "--start-frame", help="Record-domain range start"),
    end_frame: str | None = typer.Option(None, "--end-frame", help="Record-domain range end"),
    match: str = typer.Option("overlap", "--match", help="overlap, contained, or covering"),
    allow_empty: bool = typer.Option(False, "--allow-empty", help="Return ok when no items match"),
    force: bool = typer.Option(False, "--force", help="Required for wide deletes without a frame range"),
):
    """Delete timeline items without deleting tracks or rippling the timeline."""
    enforce_mutation_policy("timeline.items_delete", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            _timeline_items_delete_dry_run_payload(
                timeline_name=timeline_name,
                track_type=track_type,
                track_index=track_index,
                start_frame=start_frame,
                end_frame=end_frame,
                match=match,
                allow_empty=allow_empty,
                force=force,
            ),
            title="Timeline Items Delete Plan",
        )
        return

    conn = get_connection(require_project=True, require_timeline=timeline_name is None)
    data = timeline_ops.delete_timeline_items(
        conn,
        timeline_name=timeline_name,
        track_type=track_type,
        track_index=track_index,
        start_ref=start_frame,
        end_ref=end_frame,
        match=match,
        allow_empty=allow_empty,
        force=force,
    )
    output(
        mutation_payload(
            action="timeline.items.delete",
            changed=bool(data.get("changed")),
            target=data.get("target"),
            filters=data.get("filters"),
            deleted_count=data.get("deleted_count"),
            deleted_items=data.get("deleted_items"),
            readback=data.get("readback"),
            api_result=data.get("api_result"),
            used_non_ripple_argument=data.get("used_non_ripple_argument"),
            fallback_used=data.get("fallback_used"),
            message=data.get("message"),
        ),
        title="Timeline Items Delete",
    )


@items_app.command("set-duration")
@handle_errors
def items_set_duration(
    timeline_name: str | None = typer.Option(None, "--timeline", help="Target timeline name; defaults to active timeline"),
    batch_file: str | None = typer.Option(None, "--batch-file", help="JSON array/object of timeline item duration updates to apply in one DB mutation"),
    item_id: str | None = typer.Option(None, "--item-id", help="Project.db Sm2TiItem_id when known"),
    track_type: str = typer.Option("video", "--track-type", help="video, audio, or subtitle"),
    track_index: int = typer.Option(1, "--track-index", "--track", min=1, help="Track index for selector"),
    start_frame: str | None = typer.Option(None, "--start-frame", help="Current item start in record-domain frames/time"),
    current_end_frame: str | None = typer.Option(None, "--current-end-frame", help="Current item end for stricter selection"),
    name: str | None = typer.Option(None, "--name", help="Current timeline item name for stricter selection"),
    duration: str | None = typer.Option(None, "--duration", help="New item duration: frames, seconds, or timecode"),
    target_end_frame: str | None = typer.Option(None, "--end-frame", "--target-end-frame", help="New item end in record-domain frames/time"),
    allow_overlap: bool = typer.Option(False, "--allow-overlap", help="Allow the new duration to overlap the next item on the same track"),
    no_source_bounds: bool = typer.Option(False, "--no-source-bounds", help="Do not reject API-reported source/right-trim overrun before DB write"),
):
    """Set a timeline item's duration or end frame with DB-backed verification."""
    enforce_mutation_policy("timeline.item_duration_set", intended_engine="db_workaround", mutating=not is_dry_run())
    if batch_file:
        if any(value is not None for value in (item_id, start_frame, current_end_frame, name, duration, target_end_frame)):
            raise ValidationError(
                "Use --batch-file by itself for timeline items set-duration batches.",
                details={
                    "item_id": item_id,
                    "start_frame": start_frame,
                    "current_end_frame": current_end_frame,
                    "name": name,
                    "duration": duration,
                    "target_end_frame": target_end_frame,
                },
                recoverability="not_applicable",
            )
        entries = _load_timeline_item_duration_batch_entries(batch_file)
        if is_dry_run():
            set_verification_status("not_requested")
            set_recoverability("not_applicable")
            output(
                mutation_payload(
                    action="timeline.items.set_duration.batch",
                    changed=False,
                    target={"kind": "timeline", "name": timeline_name},
                    requested={
                        "entry_count": len(entries),
                        "entries": entries,
                        "allow_overlap": bool(allow_overlap),
                        "enforce_source_bounds": not bool(no_source_bounds),
                    },
                    command_intent={
                        "set_duration_or_end": True,
                        "delete_items": False,
                        "ripple_timeline": False,
                        "route": "db_workaround",
                        "batch": True,
                    },
                    message="DRY-RUN: Would set timeline item durations/ends through one Disk DB route.",
                ),
                title="Timeline Items Set Duration Batch Plan",
            )
            return

        conn = get_connection(require_project=True, require_timeline=timeline_name is None)
        data = timeline_item_duration_db.set_timeline_item_durations(
            conn,
            entries,
            timeline_name=timeline_name,
            allow_overlap=allow_overlap,
            enforce_source_bounds=not no_source_bounds,
        )
        updated_items = data.get("updated_items") if isinstance(data, dict) else None
        output(
            mutation_payload(
                action="timeline.items.set_duration.batch",
                changed=bool(updated_items),
                target={"kind": "timeline", "name": data.get("timeline_name") if isinstance(data, dict) else timeline_name},
                requested=data.get("requested") if isinstance(data, dict) else None,
                requested_count=data.get("requested_count") if isinstance(data, dict) else len(entries),
                updated_items=updated_items,
                readback=data.get("verification") if isinstance(data, dict) else None,
                project_db_path=data.get("project_db_path") if isinstance(data, dict) else None,
                backup_path=data.get("backup_path") if isinstance(data, dict) else None,
                steps=data.get("steps") if isinstance(data, dict) else None,
                route=data.get("route") if isinstance(data, dict) else "db_native",
                message="Set timeline item durations/ends.",
            ),
            title="Timeline Items Set Duration Batch",
        )
        return
    if bool(duration) == bool(target_end_frame):
        raise ValidationError(
            "Provide exactly one of --duration or --end-frame/--target-end-frame.",
            details={"duration": duration, "target_end_frame": target_end_frame},
        )
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            mutation_payload(
                action="timeline.items.set_duration",
                changed=False,
                target={"kind": "timeline", "name": timeline_name},
                selector={
                    "item_id": item_id,
                    "track_type": track_type,
                    "track_index": track_index,
                    "start_frame": start_frame,
                    "current_end_frame": current_end_frame,
                    "name": name,
                },
                requested={
                    "duration": duration,
                    "target_end_frame": target_end_frame,
                    "allow_overlap": bool(allow_overlap),
                    "enforce_source_bounds": not bool(no_source_bounds),
                },
                command_intent={
                    "set_duration_or_end": True,
                    "delete_items": False,
                    "ripple_timeline": False,
                    "route": "db_workaround",
                },
                message="DRY-RUN: Would set a timeline item duration/end through the Disk DB route.",
            ),
            title="Timeline Items Set Duration Plan",
        )
        return

    conn = get_connection(require_project=True, require_timeline=timeline_name is None)
    data = timeline_item_duration_db.set_timeline_item_duration(
        conn,
        timeline_name=timeline_name,
        item_id=item_id,
        track_type=track_type,
        track_index=track_index,
        start_frame=start_frame,
        current_end_frame=current_end_frame,
        name=name,
        duration=duration,
        target_end_frame=target_end_frame,
        allow_overlap=allow_overlap,
        enforce_source_bounds=not no_source_bounds,
    )
    updated_items = data.get("updated_items") if isinstance(data, dict) else None
    output(
        mutation_payload(
            action="timeline.items.set_duration",
            changed=bool(updated_items),
            target={"kind": "timeline", "name": data.get("timeline_name") if isinstance(data, dict) else timeline_name},
            requested=data.get("requested") if isinstance(data, dict) else None,
            updated_items=updated_items,
            readback=data.get("verification") if isinstance(data, dict) else None,
            project_db_path=data.get("project_db_path") if isinstance(data, dict) else None,
            backup_path=data.get("backup_path") if isinstance(data, dict) else None,
            steps=data.get("steps") if isinstance(data, dict) else None,
            route=data.get("route") if isinstance(data, dict) else "db_native",
            message="Set timeline item duration/end.",
        ),
        title="Timeline Items Set Duration",
    )


@items_app.command("move")
@handle_errors
def items_move(
    timeline_name: str | None = typer.Option(None, "--timeline", help="Target timeline name; defaults to active timeline"),
    track_index: int = typer.Option(1, "--track-index", "--track", min=1, help="Current video track index"),
    start_frame: str = typer.Option(..., "--start-frame", help="Current video item start in record-domain frames/time"),
    current_end_frame: str = typer.Option(..., "--current-end-frame", help="Current video item end for exact selection"),
    name: str = typer.Option(..., "--name", help="Current timeline item name for exact selection"),
    target_start_frame: str | None = typer.Option(None, "--to-start-frame", "--to", help="New item start in record-domain frames/time"),
    target_track_index: int | None = typer.Option(None, "--to-track", "--to-track-index", min=1, help="Destination video track index"),
    allow_overlap: bool = typer.Option(False, "--allow-overlap", help="Allow overlap with an existing item on the destination video track"),
    include_linked_audio: bool = typer.Option(False, "--include-linked-audio", help="Move every authoritatively linked audio item by the same record-frame delta"),
    allow_linked_video_only: bool = typer.Option(False, "--allow-linked-video-only", help="Explicitly allow a record move to leave linked audio at its current position"),
):
    """Move one exact video item with record-time and video-track changes supported independently."""
    set_execution_engine("db_workaround")
    enforce_mutation_policy("timeline.item_move", intended_engine="db_workaround", mutating=not is_dry_run())
    if target_start_frame is None and target_track_index is None:
        raise ValidationError(
            "Provide --to-track or --to-start-frame/--to for the timeline item move.",
            details={"target_start_frame": target_start_frame, "target_track_index": target_track_index},
        )
    if include_linked_audio and allow_linked_video_only:
        raise ValidationError(
            "Choose only one linked A/V policy: --include-linked-audio or --allow-linked-video-only.",
            details={"include_linked_audio": True, "allow_linked_video_only": True},
        )
    selector = {
        "track_type": "video",
        "track_index": track_index,
        "start_frame": start_frame,
        "current_end_frame": current_end_frame,
        "name": name,
    }
    requested = {
        "target_start_frame": target_start_frame,
        "target_track_index": target_track_index,
        "allow_overlap": bool(allow_overlap),
        "include_linked_audio": bool(include_linked_audio),
        "allow_linked_video_only": bool(allow_linked_video_only),
    }
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            mutation_payload(
                action="timeline.items.move",
                changed=False,
                target={"kind": "timeline", "name": timeline_name},
                selector=selector,
                requested=requested,
                command_intent={
                    "move_item": True,
                    "move_track": target_track_index is not None,
                    "move_start": target_start_frame is not None,
                    "linked_av_group": bool(include_linked_audio),
                    "route": "db_workaround",
                },
                message="DRY-RUN: Would move one exact video item through the verified Disk DB route.",
            ),
            title="Timeline Item Move Plan",
        )
        return

    conn = get_connection(require_project=True, require_timeline=timeline_name is None)
    timeline_ops.require_sdk_marker_mutation_guard(conn)
    expected_target_raw = os.environ.get("CUTAGENT_SDK_EXPECTED_TIMELINE_ITEM_TARGET")
    try:
        expected_target = json.loads(expected_target_raw) if expected_target_raw is not None else None
    except json.JSONDecodeError as exc:
        raise ValidationError("The SDK video-item target precondition is invalid JSON.") from exc
    if expected_target is not None and not isinstance(expected_target, dict):
        raise ValidationError("The SDK video-item target precondition must be an object.")
    expected_linked_audio_count_raw = os.environ.get("CUTAGENT_SDK_EXPECTED_LINKED_AUDIO_COUNT")
    try:
        expected_linked_audio_count = int(expected_linked_audio_count_raw) if expected_linked_audio_count_raw is not None else None
    except ValueError as exc:
        raise ValidationError(
            "The SDK linked-audio topology precondition is invalid.",
            details={"expected_linked_audio_count": expected_linked_audio_count_raw},
        ) from exc
    if expected_linked_audio_count is not None and expected_linked_audio_count < 0:
        raise ValidationError(
            "The SDK linked-audio topology precondition must not be negative.",
            details={"expected_linked_audio_count": expected_linked_audio_count},
        )
    expected_linked_audio_targets_raw = os.environ.get("CUTAGENT_SDK_EXPECTED_LINKED_AUDIO_TARGETS")
    try:
        expected_linked_audio_targets = json.loads(expected_linked_audio_targets_raw) if expected_linked_audio_targets_raw is not None else None
    except json.JSONDecodeError as exc:
        raise ValidationError("The SDK linked-audio target precondition is invalid JSON.") from exc
    if expected_linked_audio_targets is not None and (
        not isinstance(expected_linked_audio_targets, list)
        or any(not isinstance(target, dict) for target in expected_linked_audio_targets)
        or len(expected_linked_audio_targets) != expected_linked_audio_count
    ):
        raise ValidationError(
            "The SDK linked-audio target precondition does not match its count.",
            details={"expected_linked_audio_count": expected_linked_audio_count},
        )
    data = timeline_item_move_db.move_timeline_item(
        conn,
        timeline_name=timeline_name,
        track_type="video",
        track_index=track_index,
        start_frame=start_frame,
        current_end_frame=current_end_frame,
        name=name,
        target_start_frame=target_start_frame,
        target_track_index=target_track_index,
        allow_overlap=allow_overlap,
        include_linked_audio=include_linked_audio,
        allow_linked_video_only=allow_linked_video_only,
        expected_target=expected_target,
        expected_linked_audio_count=expected_linked_audio_count,
        expected_linked_audio_targets=expected_linked_audio_targets,
    )
    updated_items = data.get("updated_items") if isinstance(data, dict) else None
    public_updated_items = [
        {
            "role": "video" if str(item.get("track_type") or "") == "video" else "linked_audio",
            "name": str(item.get("name") or ""),
            "source_track_index": item.get("source_track_index"),
            "target_track_index": item.get("track_index"),
            "old_start": item.get("old_start"),
            "old_end": item.get("old_end"),
            "new_start": item.get("new_start"),
            "new_end": item.get("new_end"),
        }
        for item in (updated_items or [])
        if isinstance(item, dict)
    ]
    verification = data.get("verification") if isinstance(data, dict) else None
    output(
        mutation_payload(
            action="timeline.items.move",
            changed=bool(public_updated_items),
            target={"kind": "timeline", "name": data.get("timeline_name") if isinstance(data, dict) else timeline_name},
            selector=selector,
            requested=data.get("requested") if isinstance(data, dict) else requested,
            updated_items=public_updated_items,
            linked_audio_included=data.get("linked_audio_included") if isinstance(data, dict) else None,
            readback={"status": verification.get("status")} if isinstance(verification, dict) else None,
            route=data.get("route") if isinstance(data, dict) else "db_workaround",
            message="Moved timeline video item.",
        ),
        title="Timeline Item Move",
    )


@layout_app.command("free-stack")
@handle_errors
def layout_free_stack(
    timeline_name: str | None = typer.Option(None, "--timeline", help="Target timeline name; defaults to active timeline"),
    track_type: str = typer.Option("video", "--track-type", help="Track type: video, audio, or subtitle"),
    start_frame: str = typer.Option(..., "--start-frame", "--record-start", help="Timeline-relative record ref; 0f is timeline start"),
    end_frame: str | None = typer.Option(None, "--end-frame", "--record-end", help="Timeline-relative record ref; use duration for relative length"),
    duration: str | None = typer.Option(None, "--duration", help="Duration in frames, seconds, or timecode"),
    candidate_stacks: str | None = typer.Option(None, "--candidate-stacks", help="JSON array of candidate track stacks, e.g. [[4,5],[6,7]]"),
    stack_size: int | None = typer.Option(None, "--stack-size", min=1, help="Generate contiguous candidate stacks of this size"),
    min_track: int = typer.Option(1, "--min-track", min=1, help="First track for generated contiguous stacks"),
    max_track: int | None = typer.Option(None, "--max-track", min=1, help="Last track for generated contiguous stacks; defaults to current track count"),
    padding: str = typer.Option("0f", "--padding", help="Collision padding in frames, seconds, or timecode"),
    shift: bool = typer.Option(True, "--shift/--no-shift", help="Suggest and select the nearest shifted start when no stack is free"),
    ensure_tracks: bool = typer.Option(False, "--ensure-tracks/--no-ensure-tracks", help="Report whether missing tracks would need creation; does not mutate"),
    allow_missing_tracks: bool = typer.Option(False, "--allow-missing-tracks", help="Treat tracks above the current count as plannable but requiring creation"),
    all_candidates: bool = typer.Option(False, "--all-candidates", help="Include detailed candidate diagnostics"),
):
    """Plan a free stack of timeline tracks without mutating the timeline."""
    set_capability_context("timeline.layout_planning", "supported")
    set_execution_engine("api_native")
    set_verification_status("verified")
    set_recoverability("not_applicable")
    conn = get_connection(require_project=True, require_timeline=timeline_name is None)
    normalized_track_type = timeline_ops.normalize_timeline_track_type(track_type)
    track_count = 0
    if getattr(conn, "timeline", None) is not None:
        try:
            track_count = int(conn.timeline.GetTrackCount(normalized_track_type) or 0)
        except Exception:
            track_count = 0
    stacks = timeline_layout.parse_candidate_stacks(
        candidate_stacks,
        stack_size=stack_size,
        min_track=min_track,
        max_track=max_track if max_track is not None else track_count,
    )
    data = timeline_layout.plan_free_stack(
        conn,
        timeline_name=timeline_name,
        track_type=normalized_track_type,
        start_ref=start_frame,
        end_ref=end_frame,
        duration_ref=duration,
        candidate_stacks=stacks,
        padding_ref=padding,
        shift=shift,
        allow_missing_tracks=allow_missing_tracks,
    )
    payload = dict(data)
    payload["options"] = {
        "shift": bool(shift),
        "ensure_tracks": bool(ensure_tracks),
        "allow_missing_tracks": bool(allow_missing_tracks),
        "all_candidates": bool(all_candidates),
        "stack_size": stack_size,
        "min_track": min_track,
        "max_track": max_track,
    }
    output(
        mutation_payload(
            action=str(payload.pop("action", "timeline.layout.free_stack")),
            target=payload.pop("target", None),
            changed=bool(payload.pop("changed", False)),
            **payload,
        ),
        title="Timeline Layout Free Stack",
    )


@overlay_stack_app.command("insert")
@handle_errors
def overlay_stack_insert(
    spec: str | None = typer.Option(None, "--spec", help="Overlay stack JSON spec path"),
    spec_json: str | None = typer.Option(None, "--spec-json", help="Inline overlay stack JSON spec"),
):
    """Insert a multi-layer overlay stack from a JSON spec."""
    set_capability_context("timeline.overlay_stack", "supported")
    set_execution_engine("workaround_setting")
    set_recoverability("manual")
    enforce_mutation_policy("timeline.overlay_stack", intended_engine="workaround_setting", mutating=not is_dry_run())
    loaded_spec = timeline_overlay_stack.load_overlay_stack_spec(path=spec, raw_json=spec_json)
    conn = get_connection(require_project=True, require_timeline=not bool(loaded_spec.get("timeline")))
    plan = timeline_overlay_stack.plan_overlay_stack_insert(conn, loaded_spec)
    if is_dry_run():
        set_verification_status("not_requested")
        output(
            mutation_payload(
                action="timeline.overlay_stack.insert",
                target=plan["target"],
                changed=False,
                layout=plan["layout"],
                planned_items=plan["planned_items"],
                marker=plan["marker"],
                cleanup=plan["cleanup"],
                preflight=plan["preflight"],
                ready=bool(plan["preflight"]["ready"]),
                dry_run=True,
                message="DRY-RUN: Would insert timeline overlay stack from the requested spec.",
            ),
            title="Timeline Overlay Stack Insert Plan",
        )
        return

    data = timeline_overlay_stack.insert_overlay_stack(conn, loaded_spec)
    set_verification_status("verified")
    payload = dict(data)
    output(
        mutation_payload(
            action=str(payload.pop("action", "timeline.overlay_stack.insert")),
            target=payload.pop("target", None),
            changed=bool(payload.pop("changed", True)),
            **payload,
        ),
        title="Timeline Overlay Stack Insert",
    )
