from __future__ import annotations

@marker_app.command("list")
@handle_errors
def marker_list(name: Optional[str] = typer.Argument(None)):
    """List markers on a clip."""
    enforce_mutation_policy("clip.marker", intended_engine="api_native", mutating=False)
    conn = get_connection(require_timeline=True)
    rows = clip_ops.list_clip_markers(conn, name)
    output(rows, columns=[("frame", "Frame"), ("color", "Color"), ("name", "Name"), ("note", "Note")])


@marker_app.command("add")
@handle_errors
def marker_add(
    frame: int = typer.Argument(..., help="Marker frame value"),
    color: str = typer.Option("Blue"),
    marker_name: str = typer.Option("", "--name"),
    note: str = typer.Option(""),
    duration: int = typer.Option(1),
    frame_domain: str = typer.Option("auto", "--frame-domain", help="Frame domain: auto, offset, source, or raw"),
    clip_name: Optional[str] = typer.Option(None, "--clip"),
):
    """Add a marker to a clip."""
    enforce_mutation_policy("clip.marker", intended_engine="api_native")
    conn = get_connection(require_timeline=True)
    clip_ops.add_clip_marker(conn, clip_name, frame, color, marker_name, note, duration, frame_domain=frame_domain)
    success(f"Added marker at frame {frame}.")


@marker_app.command("delete")
@handle_errors
def marker_delete(
    frame: int = typer.Argument(..., help="Marker frame value"),
    frame_domain: str = typer.Option("auto", "--frame-domain", help="Frame domain: auto, offset, source, or raw"),
    clip_name: Optional[str] = typer.Option(None, "--clip"),
):
    """Delete a marker from a clip by frame."""
    enforce_mutation_policy("clip.marker", intended_engine="api_native")
    conn = get_connection(require_timeline=True)
    data = clip_ops.delete_clip_marker(conn, clip_name, frame, frame_domain=frame_domain)
    if is_machine_mode():
        output(data)
    else:
        success(f"Deleted marker at frame {data['frame']}.")


@marker_app.command("get-custom")
@handle_errors
def marker_get_custom(
    clip_or_data: str = typer.Argument(..., help="Clip name or custom marker data"),
    maybe_data: Optional[str] = typer.Argument(None, help="Custom marker data when clip is positional"),
    clip: Optional[str] = typer.Option(None, "--clip", help="Clip name (current clip when omitted)"),
):
    """Read a marker by custom data."""
    data = maybe_data or clip_or_data
    if maybe_data is not None:
        clip = clip_or_data
    conn = get_connection(require_timeline=True)
    output(clip_ops.get_marker_by_custom_data(conn, clip, data), title="Clip Marker")


@marker_app.command("custom-data")
@handle_errors
def marker_custom_data(
    clip_or_frame: str = typer.Argument(..., help="Clip name or marker frame"),
    frame_or_data: str = typer.Argument(..., help="Marker frame or custom data"),
    maybe_data: Optional[str] = typer.Argument(None, help="Custom marker data when clip is positional"),
    clip: Optional[str] = typer.Option(None, "--clip", help="Clip name (current clip when omitted)"),
):
    """Set custom data on a clip marker."""
    if maybe_data is None:
        frame = int(clip_or_frame)
        data = frame_or_data
    else:
        clip = clip_or_frame
        frame = int(frame_or_data)
        data = maybe_data
    enforce_mutation_policy("clip.marker", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        dry_run_message(f"Would set custom marker data at frame {frame} on '{clip or 'current clip'}'.")
        return
    conn = get_connection(require_timeline=True)
    output(clip_ops.update_marker_custom_data(conn, clip, frame, data), title="Clip Marker")


@marker_app.command("delete-custom")
@handle_errors
def marker_delete_custom(
    clip_or_data: str = typer.Argument(..., help="Clip name or custom marker data"),
    maybe_data: Optional[str] = typer.Argument(None, help="Custom marker data when clip is positional"),
    clip: Optional[str] = typer.Option(None, "--clip", help="Clip name (current clip when omitted)"),
):
    """Delete a marker by custom data."""
    data = maybe_data or clip_or_data
    if maybe_data is not None:
        clip = clip_or_data
    enforce_mutation_policy("clip.marker", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        dry_run_message(f"Would delete marker with custom data on '{clip or 'current clip'}'.")
        return
    conn = get_connection(require_timeline=True)
    output(clip_ops.delete_marker_by_custom_data(conn, clip, data), title="Clip Marker")


# --- Takes ---

take_app = typer.Typer(help="Clip takes management.")
app.add_typer(take_app, name="take")


@take_app.command("list")
@handle_errors
def take_list(name: Optional[str] = typer.Argument(None)):
    """List takes on a clip."""
    enforce_mutation_policy("clip.take", intended_engine="api_native", mutating=False)
    set_verification_status("not_requested")
    set_recoverability("not_applicable")
    conn = get_connection(require_timeline=True)
    data = clip_ops.list_takes_summary(conn, name)
    if is_machine_mode():
        output(data)
    else:
        output(data["takes"], columns=[("index", "#"), ("selected", "Selected"), ("info", "Info")])


@take_app.command("add")
@handle_errors
def take_add(
    media_name: str = typer.Argument(..., help="Media Pool clip to add as a take"),
    clip_name: Optional[str] = typer.Option(None, "--clip", help="Timeline clip name (current clip when omitted)"),
    start_frame: Optional[int] = typer.Option(None, "--start-frame", help="Source start frame for the take"),
    end_frame: Optional[int] = typer.Option(None, "--end-frame", help="Source end frame for the take"),
):
    """Add a Media Pool clip as a take on a timeline clip."""
    enforce_mutation_policy("clip.take", intended_engine="api_native")
    conn = get_connection(require_timeline=True)
    clip_ops.add_take(conn, clip_name, media_name, start_frame=start_frame, end_frame=end_frame)
    success(f"Added take from media: {media_name}")


@take_app.command("select")
@handle_errors
def take_select(
    index: int = typer.Argument(..., help="Take index"),
    clip_name: Optional[str] = typer.Option(None, "--clip"),
):
    """Select a take by index."""
    enforce_mutation_policy("clip.take", intended_engine="api_native")
    conn = get_connection(require_timeline=True)
    clip_ops.select_take(conn, clip_name, index)
    success(f"Selected take {index}.")


@take_app.command("finalize")
@handle_errors
def take_finalize(clip_name: Optional[str] = typer.Argument(None)):
    """Finalize takes on a clip."""
    enforce_mutation_policy("clip.take", intended_engine="api_native")
    conn = get_connection(require_timeline=True)
    clip_ops.finalize_take(conn, clip_name)
    success("Finalized takes.")


@take_app.command("delete")
@handle_errors
def take_delete(
    clip: str = typer.Argument(..., help="Clip name"),
    index: int = typer.Argument(..., help="Take index"),
):
    """Delete a take from a timeline clip."""
    enforce_mutation_policy("clip.take", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        dry_run_message(f"Would delete take {index} from '{clip}'.")
        return
    conn = get_connection(require_timeline=True)
    output(clip_ops.delete_take(conn, clip, index), title="Delete Take")


@app.command("reset-node-colors")
@handle_errors
def reset_node_colors(
    clip: Optional[str] = typer.Argument(None, help="Clip name (current clip when omitted)"),
):
    """Reset all node colors on a timeline item."""
    enforce_mutation_policy("color.node_graph_ops", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        dry_run_message(f"Would reset all node colors on '{clip or 'current clip'}'.")
        return
    conn = get_connection(require_timeline=True)
    output(clip_ops.reset_all_node_colors(conn, clip), title="Node Colors")


@app.command("update-sidecar")
@handle_errors
def update_sidecar(
    clip: Optional[str] = typer.Argument(None, help="Clip name (current clip when omitted)"),
):
    """Update sidecar files for a timeline item."""
    enforce_mutation_policy("clip.properties_write", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        dry_run_message(f"Would update sidecar for '{clip or 'current clip'}'.")
        return
    conn = get_connection(require_timeline=True)
    output(clip_ops.update_sidecar(conn, clip), title="Sidecar")


@app.command("stereo-values")
@handle_errors
def stereo_values(
    clip: Optional[str] = typer.Argument(None, help="Clip name (current clip when omitted)"),
):
    """Read stereo 3D values from a timeline item."""
    conn = get_connection(require_timeline=True)
    output(clip_ops.get_stereo_values(conn, clip), title="Stereo Values")


burnin_app = typer.Typer(help="Clip burn-in preset operations.")
app.add_typer(burnin_app, name="burnin")


@burnin_app.command("load")
@handle_errors
def burnin_load(
    clip_or_name: str = typer.Argument(..., help="Clip name or burn-in preset name"),
    maybe_name: Optional[str] = typer.Argument(None, help="Burn-in preset name when clip is positional"),
    clip: Optional[str] = typer.Option(None, "--clip", help="Clip name (current clip when omitted)"),
):
    """Load a burn-in preset on a timeline item."""
    name = maybe_name or clip_or_name
    if maybe_name is not None:
        clip = clip_or_name
    enforce_mutation_policy("render.burnin_preset_import_export", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        dry_run_message(f"Would load burn-in preset '{name}' on '{clip or 'current clip'}'.")
        return
    conn = get_connection(require_timeline=True)
    output(clip_ops.load_burnin_preset(conn, clip, name), title="Burn-In")


# --- Offset ---

@app.command("offset")
@handle_errors
def clip_offset(
    name: Optional[str] = typer.Argument(None, help="Clip name (or current if omitted)"),
):
    """Show left and right offset of a clip."""
    conn = get_connection(require_timeline=True)
    data = clip_ops.get_clip_offsets(conn, name)
    output(data, title="Clip Offset")
