from __future__ import annotations

@folders_app.command("list")
@handle_errors
def folders_list():
    """List subfolders in the current folder."""
    conn = get_connection(require_project=True)
    rows = media_pool.list_folders(conn)
    folder = conn.media_pool.GetCurrentFolder()
    folder_name = folder.GetName() if folder else "?"
    output(rows, columns=[("name", "Name")],
           title=f"Subfolders in: {folder_name}", quiet_key="name")


@folders_app.command("tree")
@handle_errors
def folders_tree():
    """Show the complete folder tree."""
    conn = get_connection(require_project=True)
    root = media_pool.get_folder_tree(conn)
    if is_machine_mode():
        output(media_pool.serialize_folder_tree(root), title="Folder Tree")
        return

    from ..output import console

    media_pool.print_folder_tree(root, console, "")


@folders_app.command("create")
@handle_errors
def folders_create(
    path: str = typer.Argument(..., help="Folder path (e.g., 'A/B/C')"),
):
    """Create a folder (including nested)."""
    path = path.strip()
    if not path:
        raise ValidationError("Folder path is required.")

    enforce_mutation_policy(
        "media.folder_management",
        intended_engine="api_native",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        output(
            mutation_payload(
                action="media.folders.create",
                changed=False,
                target={"kind": "folder", "path": path},
                message=f"Would create folder: {path}",
            )
        )
        return

    conn = get_connection(require_project=True)
    media_pool.create_folder(conn, path)
    output(
        mutation_payload(
            action="media.folders.create",
            target={"kind": "folder", "path": path},
            message=f"Created folder: {path}",
        )
    )


@folders_app.command("open")
@handle_errors
def folders_open(
    path: str = typer.Argument(..., help="Folder path to navigate to"),
):
    """Navigate to a folder."""
    conn = get_connection(require_project=True)
    media_pool.open_folder(conn, path)
    success(f"Opened folder: {path}")


@folders_app.command("root")
@handle_errors
def folders_root():
    """Go to root folder."""
    conn = get_connection(require_project=True)
    media_pool.go_to_root(conn)
    success("Switched to root folder.")


@folders_app.command("delete")
@handle_errors
def folders_delete(
    path: str = typer.Argument(..., help="Folder path to delete"),
    force: bool = typer.Option(False, "--force", "-f"),
):
    """Delete a Media Pool folder."""
    path = path.strip()
    if not path:
        raise ValidationError("Folder path is required.")

    enforce_mutation_policy(
        "media.folder_move_delete",
        intended_engine="api_native",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        output(
            mutation_payload(
                action="media.folders.delete",
                changed=False,
                target={"kind": "folder", "path": path},
                message=f"Would delete folder: {path}",
            )
        )
        return

    require_force_for_machine_mode(
        force=force,
        action="media.folders.delete",
        target_kind="folder",
        target_name=path,
        prompt=f"Delete folder '{path}'?",
    )
    conn = get_connection(require_project=True)
    media_pool.delete_folder(conn, path)
    output(
        mutation_payload(
            action="media.folders.delete",
            target={"kind": "folder", "path": path},
            message=f"Deleted folder: {path}",
        )
    )


@folders_app.command("move")
@handle_errors
def folders_move(
    path: str = typer.Argument(..., help="Folder path to move"),
    target_path: str = typer.Argument(..., help="Target folder path"),
):
    """Move a Media Pool folder."""
    path = path.strip()
    target_path = target_path.strip()
    if not path:
        raise ValidationError("Source folder path is required.")
    if not target_path:
        raise ValidationError("Target folder path is required.")

    enforce_mutation_policy(
        "media.folder_move_delete",
        intended_engine="api_native",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        output(
            mutation_payload(
                action="media.folders.move",
                changed=False,
                target={"kind": "folder", "path": path},
                destination={"kind": "folder", "path": target_path},
                message=f"Would move folder '{path}' to '{target_path}'.",
            )
        )
        return

    conn = get_connection(require_project=True)
    media_pool.move_folder(conn, path, target_path)
    output(
        mutation_payload(
            action="media.folders.move",
            target={"kind": "folder", "path": path},
            destination={"kind": "folder", "path": target_path},
            message=f"Moved folder '{path}' to '{target_path}'",
        )
    )


# --- Color ---

color_app = typer.Typer(help="Clip color management.")
app.add_typer(color_app, name="color")


@color_app.command("set")
@handle_errors
def color_set(
    name: str = typer.Argument(..., help="Clip name"),
    color: str = typer.Argument(..., help="Color name (e.g., Blue, Green, Pink)"),
):
    """Set clip color."""
    normalized_color = media_pool.normalize_clip_color(color)
    enforce_mutation_policy(
        "media.flag_color",
        intended_engine="api_native",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        output(
            mutation_payload(
                action="media.color.set",
                target={"kind": "clip", "name": name},
                changed=False,
                color=normalized_color,
                message=f"DRY-RUN: would set color of '{name}' to {normalized_color}.",
            )
        )
        return

    conn = get_connection(require_project=True)
    match = media_pool.find_clip_match(conn, name)
    if not match:
        raise APICallFailed(f"Clip '{name}' not found.")

    clip = match["clip"]
    result = clip.SetClipColor(normalized_color)
    if result is False:
        raise APICallFailed(
            "Failed to set clip color.",
            details={"clip": name, "color": normalized_color},
        )

    output(
        mutation_payload(
            action="media.color.set",
            target={"kind": "clip", "name": name, "folder": match.get("folder")},
            color=normalized_color,
            message=f"Set color of '{name}' to {normalized_color}",
        )
    )


@color_app.command("clear")
@handle_errors
def color_clear(
    name: str = typer.Argument(..., help="Clip name"),
):
    """Clear clip color."""
    enforce_mutation_policy(
        "media.flag_color",
        intended_engine="api_native",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        output(
            mutation_payload(
                action="media.color.clear",
                target={"kind": "clip", "name": name},
                changed=False,
                message=f"DRY-RUN: would clear color of '{name}'.",
            )
        )
        return

    conn = get_connection(require_project=True)
    match = media_pool.find_clip_match(conn, name)
    if not match:
        raise APICallFailed(f"Clip '{name}' not found.")

    clip = match["clip"]
    result = clip.ClearClipColor()
    if result is False:
        raise APICallFailed("Failed to clear clip color.", details={"clip": name})

    output(
        mutation_payload(
            action="media.color.clear",
            target={"kind": "clip", "name": name, "folder": match.get("folder")},
            message=f"Cleared color of '{name}'",
        )
    )


# --- Flags ---

flag_app = typer.Typer(help="Clip flag management.")
app.add_typer(flag_app, name="flag")


@flag_app.command("add")
@handle_errors
def flag_add(
    name: str = typer.Argument(..., help="Clip name"),
    color: str = typer.Argument(..., help="Flag color (e.g., Blue, Red, Green)"),
):
    """Add a flag to a clip."""
    normalized_color = media_pool.normalize_flag_color(color)
    enforce_mutation_policy(
        "media.flag_color",
        intended_engine="api_native",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        output(
            mutation_payload(
                action="media.flag.add",
                target={"kind": "clip", "name": name},
                changed=False,
                color=normalized_color,
                message=f"DRY-RUN: would add {normalized_color} flag to '{name}'.",
            )
        )
        return

    conn = get_connection(require_project=True)
    match = media_pool.find_clip_match(conn, name)
    if not match:
        raise APICallFailed(f"Clip '{name}' not found.")

    clip = match["clip"]
    result = clip.AddFlag(normalized_color)
    if result is False:
        raise APICallFailed("Failed to add clip flag.", details={"clip": name, "color": normalized_color})

    flags = []
    getter = getattr(clip, "GetFlagList", None)
    if callable(getter):
        try:
            flags = list(getter() or [])
        except Exception:
            flags = []
        if normalized_color not in {str(flag) for flag in flags}:
            raise APICallFailed(
                "Failed to verify clip flag.",
                details={"clip": name, "color": normalized_color, "flags": flags},
            )
        set_verification_status("verified")

    output(
        mutation_payload(
            action="media.flag.add",
            target={"kind": "clip", "name": name, "folder": match.get("folder")},
            color=normalized_color,
            flags=flags,
            verification_status="verified" if flags else "not_available",
            message=f"Added {normalized_color} flag to '{name}'",
        )
    )


@flag_app.command("clear")
@handle_errors
def flag_clear(
    name: str = typer.Argument(..., help="Clip name"),
    color: Optional[str] = typer.Argument(None, help="Flag color to clear (all if not specified)"),
):
    """Clear flags from a clip."""
    normalized_color = media_pool.normalize_flag_color(color) if color else None
    enforce_mutation_policy(
        "media.flag_color",
        intended_engine="api_native",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        output(
            mutation_payload(
                action="media.flag.clear",
                target={"kind": "clip", "name": name},
                changed=False,
                color=normalized_color,
                message=(
                    f"DRY-RUN: would clear {normalized_color} flag from '{name}'."
                    if normalized_color
                    else f"DRY-RUN: would clear all flags from '{name}'."
                ),
            )
        )
        return

    conn = get_connection(require_project=True)
    match = media_pool.find_clip_match(conn, name)
    if not match:
        raise APICallFailed(f"Clip '{name}' not found.")

    clip = match["clip"]
    flags = []
    getter = getattr(clip, "GetFlagList", None)
    if callable(getter):
        try:
            flags = list(getter() or [])
        except Exception:
            flags = []
    clear_attempts = []
    if normalized_color:
        result = clip.ClearFlags(normalized_color)
        clear_attempts.append({"color": normalized_color, "api_result": result})
        if result is False:
            raise APICallFailed(
                "Failed to clear clip flag.",
                details={"clip": name, "color": normalized_color, "api_result": result, "flags_before": flags},
            )
    else:
        if flags:
            for flag in list(flags):
                flag_color = str(flag)
                result = clip.ClearFlags(flag_color)
                clear_attempts.append({"color": flag_color, "api_result": result})
        else:
            result = clip.ClearFlags()
            clear_attempts.append({"color": None, "api_result": result})

    flags = []
    if callable(getter):
        try:
            flags = list(getter() or [])
        except Exception:
            flags = []
    if normalized_color:
        cleared = normalized_color not in {str(flag) for flag in flags}
    else:
        cleared = not flags
        if not cleared:
            try:
                cleared = _coerce_property_value(clip.GetClipProperty("Flags")) == ""
            except Exception:
                cleared = False

    if not cleared:
        raise APICallFailed(
            "Failed to clear clip flags.",
            details={"clip": name, "color": normalized_color, "remaining_flags": flags, "clear_attempts": clear_attempts},
        )

    set_verification_status("verified")
    output(
        mutation_payload(
            action="media.flag.clear",
            target={"kind": "clip", "name": name, "folder": match.get("folder")},
            verification_status="verified",
            flags=flags,
            clear_attempts=clear_attempts,
            message=f"Cleared {normalized_color} flag from '{name}'" if normalized_color else f"Cleared all flags from '{name}'",
        )
    )


# --- Markers ---

marker_app = typer.Typer(help="Clip marker management.")
app.add_typer(marker_app, name="marker")


@marker_app.command("add")
@handle_errors
def marker_add(
    name: str = typer.Argument(..., help="Clip name"),
    frame: int = typer.Argument(..., help="Frame number"),
    color: str = typer.Option("Blue", "--color", help="Marker color"),
    marker_name: str = typer.Option("", "--name", help="Marker name"),
    note: str = typer.Option("", "--note", help="Marker note"),
    duration: int = typer.Option(1, "--duration", help="Marker duration in frames"),
):
    """Add a marker to a clip."""
    enforce_mutation_policy(
        "media.marker_crud",
        intended_engine="api_native",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        output(
            mutation_payload(
                action="media.marker.add",
                changed=False,
                target={"kind": "clip", "name": name},
                frame=frame,
                color=color,
                marker_name=marker_name,
                note=note,
                duration=duration,
                message=f"Would add marker to '{name}' at frame {frame}",
            )
        )
        return

    conn = get_connection(require_project=True)
    match = media_pool.find_clip_match(conn, name)
    if not match:
        raise APICallFailed(f"Clip '{name}' not found.")
    
    clip = match["clip"]
    clip.AddMarker(frame, color, marker_name, note, duration)
    output(
        mutation_payload(
            action="media.marker.add",
            target={"kind": "clip", "name": name, "folder": match.get("folder")},
            frame=frame,
            color=color,
            marker_name=marker_name,
            note=note,
            duration=duration,
            message=f"Added marker to '{name}' at frame {frame}",
        )
    )


@marker_app.command("list")
@handle_errors
def marker_list(
    name: str = typer.Argument(..., help="Clip name"),
):
    """List markers on a clip."""
    conn = get_connection(require_project=True)
    clip = media_pool.find_clip(conn, name)
    if not clip:
        from ..errors import APICallFailed
        raise APICallFailed(f"Clip '{name}' not found in current folder.")
    
    markers = clip.GetMarkers()
    if not markers:
        output([])
        return
    
    rows = []
    for frame, info in markers.items():
        rows.append({
            "frame": frame,
            "color": info.get("color", ""),
            "name": info.get("name", ""),
            "note": info.get("note", ""),
            "duration": info.get("duration", ""),
        })
    output(rows, columns=[("frame", "Frame"), ("color", "Color"), ("name", "Name"), 
                          ("note", "Note"), ("duration", "Duration")],
           title=f"Markers: {name}", quiet_key="frame")


@marker_app.command("delete")
@handle_errors
def marker_delete(
    name: str = typer.Argument(..., help="Clip name"),
    frame: Optional[int] = typer.Option(None, "--frame", help="Frame number"),
    color: Optional[str] = typer.Option(None, "--color", help="Marker color"),
):
    """Delete marker(s) from a clip."""
    if frame is None and not color:
        raise MissingArgumentError("Must specify either --frame or --color.")

    selector = {"frame": frame} if frame is not None else {"color": color}
    enforce_mutation_policy(
        "media.marker_crud",
        intended_engine="api_native",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        output(
            mutation_payload(
                action="media.marker.delete",
                changed=False,
                target={"kind": "clip", "name": name},
                selector=selector,
                message=(
                    f"Would delete marker at frame {frame} from '{name}'"
                    if frame is not None
                    else f"Would delete {color} markers from '{name}'"
                ),
            )
        )
        return

    conn = get_connection(require_project=True)
    match = media_pool.find_clip_match(conn, name)
    if not match:
        raise APICallFailed(f"Clip '{name}' not found.")
    
    clip = match["clip"]
    if frame is not None:
        clip.DeleteMarkerAtFrame(frame)
        message = f"Deleted marker at frame {frame}"
    else:
        clip.DeleteMarkersByColor(color)
        message = f"Deleted {color} markers"
    output(
        mutation_payload(
            action="media.marker.delete",
            target={"kind": "clip", "name": name, "folder": match.get("folder")},
            selector=selector,
            message=message,
        )
    )


# --- Properties ---

@app.command("property-set")
@handle_errors
def property_set(
    name: str = typer.Argument(..., help="Clip name"),
    key: str = typer.Argument(..., help="Property key"),
    value: str = typer.Argument(..., help="Property value"),
):
    """Set a clip property."""
    enforce_mutation_policy(
        "media.metadata_write",
        intended_engine="api_native",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        output(
            mutation_payload(
                action="media.property_set",
                changed=False,
                target={"kind": "clip", "name": name},
                key=key,
                value=value,
                message=f"Would set {key} = {value}",
            )
        )
        return

    conn = get_connection(require_project=True)
    match = media_pool.find_clip_match(conn, name)
    if not match:
        raise APICallFailed(f"Clip '{name}' not found.")
    clip = match["clip"]
    
    result = clip.SetClipProperty(key, value)
    actual_value = None
    try:
        actual_value = clip.GetClipProperty(key)
    except Exception:
        actual_value = None
    if not _property_values_match(actual_value, value):
        raise APICallFailed(
            f"Failed to set property {key}.",
            details={"clip": name, "key": key, "expected": value, "actual": actual_value, "setter_result": result},
        )
    set_verification_status("verified")
    output(
        mutation_payload(
            action="media.property_set",
            target={"kind": "clip", "name": name, "folder": match.get("folder")},
            verification_status="verified",
            key=key,
            value=actual_value,
            message=f"Set {key} = {actual_value}",
        )
    )


# --- Create Timeline ---

@app.command("create-timeline")
@handle_errors
def create_timeline(
    timeline_name: str = typer.Argument(..., help="Timeline name"),
    clips: list[str] = typer.Argument(..., help="Clip names"),
):
    """Create a timeline from clips."""
    enforce_mutation_policy(
        "media.create_timeline",
        intended_engine="api_native",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        output(
            mutation_payload(
                action="media.create_timeline",
                target={"kind": "timeline", "name": timeline_name},
                changed=False,
                clips=list(clips),
                clip_count=len(clips),
                message=f"DRY-RUN: would create timeline '{timeline_name}' from {len(clips)} clip(s).",
            )
        )
        return

    conn = get_connection(require_project=True)

    # Find all clips
    clip_items = []
    resolved_clips = []
    for clip_name in clips:
        match = media_pool.find_clip_match(conn, clip_name)
        if not match:
            raise APICallFailed(f"Clip '{clip_name}' not found.")
        clip = match["clip"]
        clip_items.append(clip)
        resolved_clips.append({"name": clip_name, "folder": match.get("folder")})

    # Create timeline
    try:
        timeline = conn.media_pool.CreateTimelineFromClips(timeline_name, clip_items)
    except Exception as failure:
        try:
            failure.prepared_action_substage = "media.create_timeline.native_call"
        except Exception:
            pass
        raise
    if timeline:
        conn.refresh()
        output(
            mutation_payload(
                action="media.create_timeline",
                target={"kind": "timeline", "name": timeline_name},
                clips=resolved_clips,
                clip_count=len(clip_items),
                message=f"Created timeline '{timeline_name}' with {len(clip_items)} clip(s)",
            )
        )
    else:
        raise APICallFailed("Failed to create timeline.")


@app.command("sync-audio")
@handle_errors
def sync_audio_cmd(
    clips: list[str] = typer.Argument(..., help="Clip names to pass to DaVinci Resolve audio sync"),
    mode: Optional[str] = typer.Option(None, "--mode", help="timecode|waveform"),
    channel: Optional[int] = typer.Option(None, "--channel", help="Waveform sync channel number, -1=automatic, -2=mix"),
    retain_embedded_audio: Optional[bool] = typer.Option(None, "--retain-embedded-audio/--no-retain-embedded-audio"),
    retain_video_metadata: Optional[bool] = typer.Option(None, "--retain-video-metadata/--no-retain-video-metadata"),
):
    """Auto-sync selected media pool clips."""
    preview_settings = _audio_sync_preview_settings(
        mode,
        channel,
        retain_embedded_audio,
        retain_video_metadata,
    )
    enforce_mutation_policy(
        "media.audio_sync",
        intended_engine="api_native",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        output(
            mutation_payload(
                action="media.sync_audio",
                changed=False,
                target={"kind": "media_pool_clips", "names": list(clips)},
                clip_count=len(clips),
                settings=preview_settings,
                runtime_validation="not_performed",
                message=f"Would auto-sync {len(clips)} media pool clip(s).",
            )
        )
        return

    settings = {
        "mode": mode,
        "channel": channel,
        "retain_embedded_audio": retain_embedded_audio,
        "retain_video_metadata": retain_video_metadata,
    }
    conn = get_connection(require_project=True)
    data = media_pool.auto_sync_audio(conn, clips, settings=settings)
    output(data, title="Audio Sync")


@app.command("transcribe")
@handle_errors
def transcribe_cmd(
    clip: Optional[str] = typer.Option(None, "--clip", "-c", help="Clip name to transcribe."),
    folder: Optional[str] = typer.Option(None, "--folder", "-f", help="Folder path to transcribe."),
    language: Optional[str] = typer.Option(None, "--language", "-l", help="Language code."),
):
    """Transcribe audio for a clip or folder."""
    if clip and folder:
        raise ValidationError("Choose either clip transcription or folder transcription, not both.")
    if not clip and not folder:
        raise MissingArgumentError(
            "Choose a transcription target with --clip or --folder.",
            details={"required_one_of": ["--clip", "--folder"]},
        )
    enforce_mutation_policy("media.transcription", mutating=not is_dry_run())
    if is_dry_run():
        target_kind = "clip" if clip else "folder"
        target_name = clip or folder
        output(
            mutation_payload(
                action="media.transcribe",
                target={"kind": target_kind, "name": target_name},
                changed=False,
                clip=clip,
                folder=folder,
                language=language,
                runtime_validation="not_performed",
                message=f"DRY-RUN: would transcribe {target_kind} '{target_name}'.",
            )
        )
        return
    conn = get_connection()
    from ..core.media_pool import transcribe_audio
    result = transcribe_audio(conn, clip_name=clip, folder_path=folder, language=language)
    output(result)


@app.command("clear-transcription")
@handle_errors
def clear_transcription_cmd(
    clip: Optional[str] = typer.Option(None, "--clip", "-c", help="Clip name."),
    folder: Optional[str] = typer.Option(None, "--folder", "-f", help="Folder path."),
):
    """Clear transcription for a clip or folder."""
    if clip and folder:
        raise ValidationError("Choose either clip or folder clear operation, not both.")
    enforce_mutation_policy("media.transcription", mutating=not is_dry_run())
    if is_dry_run():
        target_kind = "clip" if clip else "folder"
        target_name = clip or folder or "current"
        output(mutation_payload(
            action="media.clear_transcription",
            target={"kind": target_kind, "name": target_name},
            changed=False,
            clip=clip,
            folder=folder,
            message=f"DRY-RUN: would clear transcription for {target_kind} '{target_name}'.",
        ))
        return

    conn = get_connection()
    from ..core.media_pool import clear_transcription
    result = clear_transcription(conn, clip_name=clip, folder_path=folder)
    output(result)


@app.command("audio-mapping")
@handle_errors
def audio_mapping(
    clip: str = typer.Argument(..., help="Media Pool clip name"),
):
    """Show source audio mapping for a Media Pool item."""
    conn = get_connection(require_project=True)
    output(media_pool.get_audio_mapping(conn, clip), title="Audio Mapping")


mark_app = typer.Typer(help="Media Pool mark in/out operations.")
app.add_typer(mark_app, name="mark")


@mark_app.command("get")
@handle_errors
def mark_get(
    clip: str = typer.Argument(..., help="Media Pool clip name"),
):
    """Show mark in/out points for a Media Pool item."""
    conn = get_connection(require_project=True)
    output(media_pool.get_mark_in_out(conn, clip), title="Media Mark")


@mark_app.command("set")
@handle_errors
def mark_set(
    clip: str = typer.Argument(..., help="Media Pool clip name"),
    mark_in: int = typer.Option(..., "--in", help="Mark-in frame"),
    mark_out: int = typer.Option(..., "--out", help="Mark-out frame"),
    mark_type: str = typer.Option("all", "--type", help="all|video|audio"),
):
    """Set mark in/out points for a Media Pool item."""
    enforce_mutation_policy("media.mark_in_out", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        dry_run_message(f"Would set {mark_type} mark range on '{clip}' to {mark_in}-{mark_out}.")
        return
    conn = get_connection(require_project=True)
    output(media_pool.set_mark_in_out(conn, clip, mark_in, mark_out, mark_type), title="Media Mark")


@mark_app.command("clear")
@handle_errors
def mark_clear(
    clip: str = typer.Argument(..., help="Media Pool clip name"),
    mark_type: str = typer.Option("all", "--type", help="all|video|audio"),
):
    """Clear mark in/out points for a Media Pool item."""
    enforce_mutation_policy("media.mark_in_out", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        dry_run_message(f"Would clear {mark_type} mark range on '{clip}'.")
        return
    conn = get_connection(require_project=True)
    output(media_pool.clear_mark_in_out(conn, clip, mark_type), title="Media Mark")
