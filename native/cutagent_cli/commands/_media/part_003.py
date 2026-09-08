from __future__ import annotations

@app.command("stereo-create")
@handle_errors
def stereo_create(
    left: str = typer.Argument(..., help="Left-eye Media Pool clip"),
    right: str = typer.Argument(..., help="Right-eye Media Pool clip"),
):
    """Create a stereo clip from left/right Media Pool items."""
    enforce_mutation_policy("media.stereo_clip", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        dry_run_message(f"Would create stereo clip from left='{left}' and right='{right}'.")
        return
    conn = get_connection(require_project=True)
    output(media_pool.create_stereo_clip(conn, left, right), title="Stereo Clip")


@app.command("rename")
@handle_errors
def rename(
    old: str = typer.Argument(..., help="Current Media Pool clip name"),
    new: str = typer.Argument(..., help="New Media Pool clip name"),
):
    """Rename a Media Pool item."""
    enforce_mutation_policy("media.clip_management", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        dry_run_message(f"Would rename Media Pool item '{old}' to '{new}'.")
        return
    conn = get_connection(require_project=True)
    output(media_pool.rename_media_pool_item(conn, old, new), title="Media Rename")


selected_app = typer.Typer(help="Media Pool selected clips.")
app.add_typer(selected_app, name="selected")


@selected_app.command("list")
@handle_errors
def selected_list():
    """List selected Media Pool clips."""
    conn = get_connection(require_project=True)
    output(media_pool.get_selected_clips(conn), title="Selected Clips")


@selected_app.command("set")
@handle_errors
def selected_set(
    clip: str = typer.Argument(..., help="Media Pool clip name"),
):
    """Select a Media Pool clip."""
    enforce_mutation_policy("media.clip_management", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        dry_run_message(f"Would select Media Pool clip: {clip}")
        return
    conn = get_connection(require_project=True)
    output(media_pool.set_selected_clip(conn, clip), title="Selected Clip")


third_party_app = typer.Typer(help="Third-party Media Pool metadata.")
app.add_typer(third_party_app, name="third-party-metadata")


@third_party_app.command("get")
@handle_errors
def third_party_get(
    clip: str = typer.Argument(..., help="Media Pool clip name"),
    key: Optional[str] = typer.Argument(None, help="Optional metadata key"),
):
    """Read third-party metadata from a Media Pool item."""
    conn = get_connection(require_project=True)
    output(media_pool.get_third_party_metadata(conn, clip, key), title="Third-Party Metadata")


@third_party_app.command("set")
@handle_errors
def third_party_set(
    clip: str = typer.Argument(..., help="Media Pool clip name"),
    key: str = typer.Argument(..., help="Metadata key"),
    value: str = typer.Argument(..., help="Metadata value"),
):
    """Set one third-party metadata key on a Media Pool item."""
    enforce_mutation_policy("media.metadata_write", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        dry_run_message(f"Would set third-party metadata '{key}' on '{clip}'.")
        return
    conn = get_connection(require_project=True)
    output(media_pool.set_third_party_metadata(conn, clip, key, value), title="Third-Party Metadata")


@third_party_app.command("set-json")
@handle_errors
def third_party_set_json(
    clip: str = typer.Argument(..., help="Media Pool clip name"),
    json_payload: str = typer.Argument(..., help="JSON object or path to JSON file"),
):
    """Set third-party metadata from a JSON object or file."""
    enforce_mutation_policy("media.metadata_write", intended_engine="api_native", mutating=not is_dry_run())
    payload_text = json_payload
    candidate = Path(json_payload).expanduser()
    if candidate.is_file():
        payload_text = candidate.read_text(encoding="utf-8")
    data = json.loads(payload_text)
    if not isinstance(data, dict):
        raise ValidationError("Third-party metadata JSON must be an object.")
    if is_dry_run():
        dry_run_message(f"Would set {len(data)} third-party metadata key(s) on '{clip}'.")
        return
    conn = get_connection(require_project=True)
    output(media_pool.set_third_party_metadata(conn, clip, data), title="Third-Party Metadata")


@proxy_app.command("link-fullres")
@handle_errors
def proxy_link_fullres(
    ctx: typer.Context,
    clip: str = typer.Argument(..., help="Media Pool clip name"),
    path: str = typer.Argument(..., help="Full-resolution media path"),
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Show what would happen without making changes"),
    json_output: bool = typer.Option(False, "--json", "-j", help="JSON output"),
):
    """Link full-resolution media for a clip."""
    _apply_proxy_local_flags(ctx, dry_run=dry_run, json_output=json_output)
    enforce_mutation_policy("media.proxy_transcode", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        dry_run_message(f"Would link full-resolution media '{path}' for '{clip}'.")
        return
    conn = get_connection(require_project=True)
    output(media_pool.link_full_resolution_media(conn, clip, path), title="Full-Resolution Media")


@app.command("replace")
@handle_errors
def replace(
    clip: str = typer.Argument(..., help="Media Pool clip name"),
    path: str = typer.Argument(..., help="Replacement media path"),
):
    """Replace a Media Pool clip's source media."""
    replace_path, _ = _validate_existing_media_path(path, label="Replacement media")
    enforce_mutation_policy("media.unlink_relink", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        dry_run_message(f"Would replace Media Pool clip '{clip}' with '{replace_path}'.")
        return
    conn = get_connection(require_project=True)
    output(media_pool.replace_media_pool_clip(conn, clip, replace_path), title="Replace Clip")


@app.command("replace-preserve-subclip")
@handle_errors
def replace_preserve_subclip(
    clip: str = typer.Argument(..., help="Media Pool clip name"),
    path: str = typer.Argument(..., help="Replacement media path"),
):
    """Replace a clip while preserving subclip metadata."""
    replace_path, _ = _validate_existing_media_path(path, label="Replacement media")
    enforce_mutation_policy("media.unlink_relink", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        dry_run_message(f"Would replace Media Pool clip '{clip}' with '{replace_path}' while preserving subclip metadata.")
        return
    conn = get_connection(require_project=True)
    output(media_pool.replace_media_pool_clip(conn, clip, replace_path, preserve_subclip=True), title="Replace Clip")


growing_file_app = typer.Typer(help="Growing-file operations.")
app.add_typer(growing_file_app, name="growing-file")


@growing_file_app.command("monitor")
@handle_errors
def growing_file_monitor(
    clip: str = typer.Argument(..., help="Media Pool clip name"),
):
    """Enable growing-file monitoring for a clip."""
    enforce_mutation_policy("media.proxy_transcode", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        dry_run_message(f"Would enable growing-file monitoring for '{clip}'.")
        return
    conn = get_connection(require_project=True)
    output(media_pool.monitor_growing_file(conn, clip), title="Growing File")


matte_app = typer.Typer(help="Media Pool matte operations.")
app.add_typer(matte_app, name="matte")


@matte_app.command("list")
@handle_errors
def matte_list(
    clip: str = typer.Argument(..., help="Media Pool clip name"),
):
    """List mattes attached to a Media Pool clip."""
    conn = get_connection(require_project=True)
    output(media_pool.list_clip_mattes(conn, clip), title="Clip Mattes")


@matte_app.command("delete")
@handle_errors
def matte_delete(
    clip: str = typer.Argument(..., help="Media Pool clip name"),
    paths: list[str] = typer.Argument(..., help="Matte paths to delete"),
):
    """Delete mattes from a Media Pool clip."""
    enforce_mutation_policy("media.clip_management", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        dry_run_message(f"Would delete {len(paths)} matte path(s) from '{clip}'.")
        return
    conn = get_connection(require_project=True)
    output(media_pool.delete_clip_mattes(conn, clip, paths), title="Clip Mattes")


timeline_matte_app = typer.Typer(help="Timeline matte operations.")
app.add_typer(timeline_matte_app, name="timeline-matte")


@timeline_matte_app.command("list")
@handle_errors
def timeline_matte_list(
    folder: str = typer.Argument(..., help="Media Pool folder path"),
):
    """List timeline mattes in a Media Pool folder."""
    conn = get_connection(require_project=True)
    output(media_pool.list_timeline_mattes(conn, folder), title="Timeline Mattes")


folder_app = typer.Typer(help="Media Pool folder DRB import/export operations.")
app.add_typer(folder_app, name="folder")


@folder_app.command("import-drb")
@handle_errors
def folder_import_drb(
    file: str = typer.Argument(..., help="DRB/folder file"),
    source_clips_path: Optional[str] = typer.Option(None, "--source-clips-path", help="Source clips path"),
):
    """Import a Media Pool folder file."""
    enforce_mutation_policy("media.folder_management", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        dry_run_message(f"Would import Media Pool folder file: {file}")
        return
    conn = get_connection(require_project=True)
    output(media_pool.import_folder_from_drb(conn, file, source_clips_path), title="Folder Import")


@folder_app.command("export-drb")
@handle_errors
def folder_export_drb(
    folder: str = typer.Argument(..., help="Media Pool folder path to export"),
    file: str = typer.Argument(..., help="Output .drb file"),
):
    """Export a Media Pool folder file."""
    if is_dry_run():
        dry_run_message(f"Would export Media Pool folder '{folder}' to: {file}")
        return
    conn = get_connection(require_project=True)
    output(media_pool.export_folder_to_drb(conn, folder, file), title="Folder Export")
