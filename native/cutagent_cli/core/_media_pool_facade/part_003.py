from __future__ import annotations

def append_resolved_clip_to_timeline(
    conn,
    clip,
    *,
    name: str,
    folder: str | None = None,
    at: Optional[str] = None,
    track_type: str = "video",
    track_index: int = 1,
    source_start: Optional[str] = None,
    source_end: Optional[str] = None,
    record_frame: Optional[str] = None,
    absolute_record_frame: Optional[float] = None,
    name_after_append: str | None = None,
    return_details: bool = False,
) -> bool | Dict[str, Any]:
    normalized_track_type = normalize_append_track_type(track_type)
    validated_track_index = validate_append_track_index(track_index)
    record_ref_count = sum(value is not None for value in (at, record_frame, absolute_record_frame))
    if record_ref_count > 1:
        raise ValidationError(
            "Use only one of --at, --record-frame, or --absolute-record-frame.",
            details={"at": at, "record_frame": record_frame, "absolute_record_frame": absolute_record_frame},
        )

    resolved_record_frame = None
    record_frame_mode = None
    if absolute_record_frame is not None:
        # Fractional recordFrame is honored by DaVinci Resolve 19.0.2+ for audio-only
        # appends (sub-frame placement); keep integers as int so existing
        # callers and JSON output are byte-identical.
        resolved_record_frame = float(absolute_record_frame)
        if float(resolved_record_frame).is_integer():
            resolved_record_frame = int(resolved_record_frame)
        if resolved_record_frame < 0:
            raise ValidationError(
                "--absolute-record-frame must be a non-negative DaVinci Resolve recordFrame.",
                details={"absolute_record_frame": absolute_record_frame},
            )
        record_frame_mode = "absolute"
    record_ref = record_frame if record_frame is not None else at
    if record_ref is not None:
        resolved_record_frame = parse_record_frame(str(record_ref), conn.fps, _timeline_start_frame(conn))
        record_frame_mode = "record_ref"

    start_frame = parse_source_frame(str(source_start), conn.fps) if source_start is not None else None
    end_frame = parse_source_frame(str(source_end), conn.fps) if source_end is not None else None
    if end_frame is not None and end_frame <= int(start_frame or 0):
        raise InvalidTimeReference(
            "source end must be greater than source start.",
            details={
                "clip": name,
                "source_start": source_start,
                "source_end": source_end,
                "startFrame": int(start_frame or 0),
                "endFrame": int(end_frame),
            },
        )

    clip_info = {"mediaPoolItem": clip}
    if start_frame is not None:
        clip_info["startFrame"] = start_frame
    if end_frame is not None:
        clip_info["endFrame"] = end_frame
    if resolved_record_frame is not None:
        clip_info["recordFrame"] = resolved_record_frame
    clip_info["trackIndex"] = validated_track_index
    clip_info["trackType"] = normalized_track_type
    if normalized_track_type == "audio":
        # Audio-only append. Without this, DaVinci Resolve quantizes fractional
        # recordFrame values to whole frames for clips that carry video
        # (verified live on DaVinci Resolve Studio 21.0.0.47).
        clip_info["mediaType"] = 2

    _validate_append_source_bounds(
        clip_name=name,
        start_frame=start_frame,
        end_frame=end_frame,
        source_total_frames=_source_total_frames(clip, conn.fps),
    )

    result = conn.media_pool.AppendToTimeline([clip_info])
    if not result:
        raise APICallFailed("Failed to append clip.")
    appended_items = result if isinstance(result, list) else [result]
    if name_after_append:
        for item in appended_items:
            setter = getattr(item, "SetName", None)
            if callable(setter):
                try:
                    setter(str(name_after_append))
                except Exception:
                    pass
    if not return_details:
        return True

    append_count = len(appended_items)
    return {
        "clip": name,
        "folder": folder,
        "timeline_name": getattr(conn, "timeline", None).GetName() if hasattr(getattr(conn, "timeline", None), "GetName") else None,
        "track_type": normalized_track_type,
        "track_index": validated_track_index,
        "record_frame": resolved_record_frame,
        "record_frame_mode": record_frame_mode,
        "source_start_frame": start_frame,
        "source_end_frame": end_frame,
        "clip_info": {
            "mediaPoolItem": name,
            **({"startFrame": start_frame} if start_frame is not None else {}),
            **({"endFrame": end_frame} if end_frame is not None else {}),
            **({"recordFrame": resolved_record_frame} if resolved_record_frame is not None else {}),
            "trackIndex": validated_track_index,
            "trackType": normalized_track_type,
        },
        "append_result_count": append_count,
        "timeline_items": [_timeline_item_summary(item) for item in appended_items],
        "name_after_append": name_after_append,
    }


def plan_append_entry(
    conn,
    entry: dict[str, Any],
    media_matches: list[dict[str, Any]] | None = None,
    *,
    timeline_start_frame: int | None = None,
) -> dict[str, Any]:
    """Resolve and validate a media append batch entry without mutating DaVinci Resolve."""
    resolved = resolve_append_media_entry(conn, entry, media_matches=media_matches)
    track_type = normalize_append_track_type(str(entry.get("track_type") or entry.get("trackType") or "video"))
    track_index = validate_append_track_index(int(entry.get("track_index") or entry.get("trackIndex") or entry.get("track") or 1))
    at = entry.get("at")
    record_frame = entry.get("record_frame")
    absolute_record_frame = entry.get("absolute_record_frame")
    if sum(value is not None for value in (at, record_frame, absolute_record_frame)) > 1:
        raise ValidationError(
            "Use only one of at, record_frame, or absolute_record_frame.",
            details={"entry": entry},
        )
    source_start = entry.get("source_start")
    source_end = entry.get("source_end")
    start_frame = parse_source_frame(str(source_start), conn.fps) if source_start is not None else None
    end_frame = parse_source_frame(str(source_end), conn.fps) if source_end is not None else None
    if end_frame is None and entry.get("duration_frames") is not None:
        if start_frame is None:
            start_frame = 0
        end_frame = int(start_frame) + int(entry["duration_frames"])
    _validate_append_source_bounds(
        clip_name=str(resolved.get("name") or entry.get("name") or entry.get("path") or entry.get("media_id")),
        start_frame=start_frame,
        end_frame=end_frame,
        source_total_frames=resolved.get("source_total_frames") if resolved.get("source_total_frames") is not None else _source_total_frames(resolved["clip"], conn.fps),
    )
    resolved_record_frame = None
    record_frame_mode = None
    if absolute_record_frame is not None:
        resolved_record_frame = int(absolute_record_frame)
        if resolved_record_frame < 0:
            raise ValidationError(
                "absolute_record_frame must be non-negative.",
                details={"absolute_record_frame": absolute_record_frame},
            )
        record_frame_mode = "absolute"
    record_ref = record_frame if record_frame is not None else at
    if record_ref is not None:
        start_frame_for_record = _timeline_start_frame(conn) if timeline_start_frame is None else int(timeline_start_frame)
        resolved_record_frame = parse_record_frame(str(record_ref), conn.fps, start_frame_for_record)
        record_frame_mode = "record_ref"
    return {
        "index": int(entry.get("index", 0)),
        "entry": entry,
        "clip": resolved["clip"],
        "name": resolved.get("name"),
        "folder": resolved.get("folder"),
        "media_id": resolved.get("media_id"),
        "source_path": resolved.get("source_path"),
        "timeline": entry.get("timeline"),
        "track_type": track_type,
        "track_index": track_index,
        "source_start": source_start,
        "source_end": str(end_frame) if entry.get("duration_frames") is not None and source_end is None else source_end,
        "source_start_frame": start_frame,
        "source_end_frame": end_frame,
        "record_frame": record_frame,
        "at": at,
        "absolute_record_frame": absolute_record_frame,
        "resolved_record_frame": resolved_record_frame,
        "record_frame_mode": record_frame_mode,
        "name_after_append": entry.get("name_after_append"),
        "preflight": {
            "target": {"kind": "media", "name": resolved.get("name"), "folder": resolved.get("folder"), "source_path": resolved.get("source_path")},
            "timeline": entry.get("timeline") or "current",
            "track_type": track_type,
            "track_index": track_index,
            "source_start_frame": start_frame,
            "source_end_frame": end_frame,
            "record_frame": resolved_record_frame,
            "record_frame_mode": record_frame_mode,
        },
    }


# --- Folder operations ---

def list_folders(conn) -> List[Dict[str, str]]:
    """
    List subfolders in the current folder.
    
    Args:
        conn: ResolveConnection instance
    
    Returns:
        List of folder info dicts
    
    Raises:
        APICallFailed: If cannot get current folder
    """
    folder = conn.media_pool.GetCurrentFolder()
    if not folder:
        raise APICallFailed("Cannot get current folder.")

    subfolders = folder.GetSubFolderList() or []
    return [{"name": sf.GetName()} for sf in subfolders]


def get_folder_tree(conn):
    """
    Get the complete folder tree structure.
    
    Args:
        conn: ResolveConnection instance
    
    Returns:
        Root folder object
    """
    return conn.media_pool.GetRootFolder()


def serialize_folder_tree(folder, *, parent_path: str = "") -> dict[str, object]:
    """Convert a live Media Pool folder tree into a JSON-safe structure."""
    name = folder.GetName() if hasattr(folder, "GetName") else "?"
    path = f"{parent_path}/{name}".strip("/")
    clips = folder.GetClipList() or []
    subfolders = folder.GetSubFolderList() or []
    return {
        "name": name,
        "path": path,
        "clip_count": len(clips),
        "subfolder_count": len(subfolders),
        "subfolders": [
            serialize_folder_tree(subfolder, parent_path=path)
            for subfolder in subfolders
        ],
    }


def create_folder(conn, path: str):
    """
    Create a folder (including nested).
    
    Args:
        conn: ResolveConnection instance
        path: Folder path (e.g., 'A/B/C')
    
    Returns:
        Folder object
    """
    return navigate_folder(conn, path, create=True)


def open_folder(conn, path: str):
    """
    Navigate to a folder.
    
    Args:
        conn: ResolveConnection instance
        path: Folder path
    
    Returns:
        Folder object
    """
    folder = navigate_folder(conn, path, create=False)
    conn.media_pool.SetCurrentFolder(folder)
    return folder


def go_to_root(conn):
    """
    Go to root folder.
    
    Args:
        conn: ResolveConnection instance
    
    Returns:
        Root folder object
    """
    root = conn.media_pool.GetRootFolder()
    conn.media_pool.SetCurrentFolder(root)
    return root


def delete_folder(conn, path: str) -> bool:
    """Delete media pool folder by path."""
    folder = navigate_folder(conn, path, create=False)
    root = conn.media_pool.GetRootFolder()
    if folder == root:
        raise APICallFailed("Cannot delete root Media Pool folder.")
    deleter = require_api_method(
        conn.media_pool,
        "DeleteFolders",
        capability_id="media.folder_move_delete",
        runtime_object="media_pool",
    )
    result = deleter([folder])
    if result:
        return True
    raise APICallFailed("Failed to delete folder.", details={"path": path})


def move_folder(conn, path: str, target_path: str) -> bool:
    """Move media pool folder to target folder."""
    folder = navigate_folder(conn, path, create=False)
    target = navigate_folder(conn, target_path, create=False)
    mover = require_api_method(
        conn.media_pool,
        "MoveFolders",
        capability_id="media.folder_move_delete",
        runtime_object="media_pool",
    )
    result = mover([folder], target)
    if result:
        return True
    raise APICallFailed("Failed to move folder.", details={"path": path, "target_path": target_path})


def print_folder_tree(folder, console, prefix: str = ""):
    """
    Print folder tree recursively (for display).
    
    Args:
        folder: Folder object
        console: Rich console object
        prefix: Current prefix string for tree display
    """
    name = folder.GetName() if hasattr(folder, "GetName") else "?"
    clips = folder.GetClipList() or []
    console.print(f"{prefix}📁 {name} ({len(clips)} clips)")

    subfolders = folder.GetSubFolderList() or []
    for i, sf in enumerate(subfolders):
        is_last = i == len(subfolders) - 1
        child_prefix = prefix + ("    " if is_last else "│   ")
        connector = "└── " if is_last else "├── "
        console.print(f"{prefix}{connector}", end="")
        print_folder_tree(sf, console, child_prefix)


# ---------------------------------------------------------------------------
# Additional MediaPool / MediaPoolItem Operations (API parity)
# ---------------------------------------------------------------------------

def create_stereo_clip(conn, left_clip_name: str, right_clip_name: str) -> Dict[str, Any]:
    """Create a stereo clip pair from two media pool items."""
    left = find_clip(conn, left_clip_name)
    right = find_clip(conn, right_clip_name)
    if not left:
        raise APICallFailed(f"Left clip '{left_clip_name}' not found.")
    if not right:
        raise APICallFailed(f"Right clip '{right_clip_name}' not found.")
    creator = getattr(conn.media_pool, "CreateStereoClip", None)
    if not creator:
        raise APICallFailed("CreateStereoClip not available.")
    result = creator(left, right)
    return {"created": bool(result), "left": left_clip_name, "right": right_clip_name}


def auto_sync_audio(conn, clip_names: list, settings: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Auto-sync audio for given clips."""
    clips = []
    for name in clip_names:
        clip = find_clip(conn, name)
        if clip:
            clips.append(clip)
    if not clips:
        raise APICallFailed("No valid clips found for audio sync.")
    syncer = getattr(conn.media_pool, "AutoSyncAudio", None)
    if not syncer:
        raise APICallFailed("AutoSyncAudio not available.")

    normalized_settings: Dict[Any, Any] = {}
    if settings:
        mode = _normalize_audio_sync_mode(settings.get("mode"))
        channel = settings.get("channel")
        retain_embedded_audio = settings.get("retain_embedded_audio")
        retain_video_metadata = settings.get("retain_video_metadata")

        if mode:
            normalized_settings[_resolve_api_constant(conn, "AUDIO_SYNC_MODE")] = _resolve_api_constant(conn, mode)
        if channel is not None:
            normalized_settings[_resolve_api_constant(conn, "AUDIO_SYNC_CHANNEL_NUMBER")] = int(channel)
        if retain_embedded_audio is not None:
            normalized_settings[_resolve_api_constant(conn, "AUDIO_SYNC_RETAIN_EMBEDDED_AUDIO")] = bool(retain_embedded_audio)
        if retain_video_metadata is not None:
            normalized_settings[_resolve_api_constant(conn, "AUDIO_SYNC_RETAIN_VIDEO_METADATA")] = bool(retain_video_metadata)

    result = syncer(clips, normalized_settings)
    return {"synced": bool(result), "clip_count": len(clips), "settings": normalized_settings}


def get_audio_mapping(conn, clip_name: str) -> Dict[str, Any]:
    """Get audio mapping for a media pool item."""
    clip = find_clip(conn, clip_name)
    if not clip:
        raise APICallFailed(f"Clip '{clip_name}' not found.")
    getter = getattr(clip, "GetAudioMapping", None)
    if not getter:
        raise APICallFailed("GetAudioMapping not available.")
    return {"clip": clip_name, "mapping": getter()}


def get_mark_in_out(conn, clip_name: str) -> Dict[str, Any]:
    """Get mark in/out points for a media pool item."""
    clip = find_clip(conn, clip_name)
    if not clip:
        raise APICallFailed(f"Clip '{clip_name}' not found.")
    getter = getattr(clip, "GetMarkInOut", None)
    if not getter:
        raise APICallFailed("GetMarkInOut not available.")
    return {"clip": clip_name, "marks": getter()}


def set_mark_in_out(conn, clip_name: str, mark_in: float, mark_out: float, mark_type: str = "uncategorized") -> Dict[str, Any]:
    """Set mark in/out points for a media pool item."""
    clip = find_clip(conn, clip_name)
    if not clip:
        raise APICallFailed(f"Clip '{clip_name}' not found.")
    setter = getattr(clip, "SetMarkInOut", None)
    if not setter:
        raise APICallFailed("SetMarkInOut not available.")
    result = setter(mark_in, mark_out, mark_type)
    return {"clip": clip_name, "mark_in": mark_in, "mark_out": mark_out, "type": mark_type, "success": bool(result)}


def clear_mark_in_out(conn, clip_name: str, mark_type: str = "uncategorized") -> Dict[str, Any]:
    """Clear mark in/out points for a media pool item."""
    clip = find_clip(conn, clip_name)
    if not clip:
        raise APICallFailed(f"Clip '{clip_name}' not found.")
    clearer = getattr(clip, "ClearMarkInOut", None)
    if not clearer:
        raise APICallFailed("ClearMarkInOut not available.")
    result = clearer(mark_type)
    return {"clip": clip_name, "type": mark_type, "cleared": bool(result)}


def _clip_label(clip, fallback: str = "") -> str:
    if hasattr(clip, "GetName"):
        try:
            value = clip.GetName()
            if value:
                return str(value)
        except Exception:
            pass
    return fallback


def get_selected_clips(conn) -> List[Dict[str, Any]]:
    """Return selected Media Pool clips when DaVinci Resolve exposes the selected-clip API."""
    getter = getattr(conn.media_pool, "GetSelectedClips", None)
    if not callable(getter):
        raise APICallFailed("GetSelectedClips not available.")
    clips = getter() or []
    if isinstance(clips, dict):
        clips = list(clips.values())
    rows = []
    for index, clip in enumerate(clips, start=1):
        props = _clip_properties(clip)
        rows.append(
            {
                "index": index,
                "name": _clip_label(clip, f"Clip {index}"),
                "source_path": _canonical_source_path(props, clip),
                "type": props.get("Type", ""),
            }
        )
    return rows


def set_selected_clip(conn, clip_name: str) -> Dict[str, Any]:
    """Select a Media Pool clip by name."""
    clip = find_clip(conn, clip_name)
    if not clip:
        raise APICallFailed(f"Clip '{clip_name}' not found.")
    for method_name, args in (
        ("SetSelectedClip", (clip,)),
        ("SetSelectedClips", ([clip],)),
    ):
        method = getattr(conn.media_pool, method_name, None)
        if not callable(method):
            continue
        result = method(*args)
        if result is not False:
            return {"clip": clip_name, "selected": True, "method": method_name}
    raise APICallFailed(
        "Media Pool selected-clip API is not available.",
        details={"clip": clip_name, "required_method": ["MediaPool.SetSelectedClip", "MediaPool.SetSelectedClips"]},
    )


def rename_media_pool_item(conn, old_name: str, new_name: str) -> Dict[str, Any]:
    """Rename a Media Pool item."""
    clip = find_clip(conn, old_name)
    if not clip:
        raise APICallFailed(f"Clip '{old_name}' not found.")
    setter = getattr(clip, "SetName", None)
    if callable(setter):
        result = setter(new_name)
        if result is not False:
            return {"old_name": old_name, "new_name": new_name, "renamed": True, "method": "SetName"}
    prop_setter = getattr(clip, "SetClipProperty", None)
    if callable(prop_setter):
        for key in ("Clip Name", "Name"):
            result = prop_setter(key, new_name)
            if result is not False:
                return {"old_name": old_name, "new_name": new_name, "renamed": True, "method": "SetClipProperty", "key": key}
    raise APICallFailed("Failed to rename Media Pool clip.", details={"old_name": old_name, "new_name": new_name})


def export_metadata(conn, output_file: str, clip_names: Optional[list[str]] = None) -> Dict[str, Any]:
    """Export metadata for selected or named Media Pool clips."""
    exporter = getattr(conn.media_pool, "ExportMetadata", None)
    if not callable(exporter):
        raise APICallFailed("ExportMetadata not available.")
    clips = None
    if clip_names:
        clips = []
        for name in clip_names:
            clip = find_clip(conn, name)
            if not clip:
                raise APICallFailed(f"Clip '{name}' not found.")
            clips.append(clip)
    if clips is None:
        result = exporter(output_file)
    else:
        result = exporter(output_file, clips)
    if result is False:
        raise APICallFailed("Metadata export failed.", details={"output_file": output_file, "clips": clip_names or []})
    return {"output_file": output_file, "clips": clip_names or [], "exported": bool(result)}


def _folder_names(folder) -> list[str]:
    try:
        subfolders = folder.GetSubFolderList() or []
    except Exception:
        return []
    names: list[str] = []
    for subfolder in subfolders:
        try:
            names.append(str(subfolder.GetName()))
        except Exception:
            continue
    return names


def _validate_drb_path(path: str, *, must_exist: bool) -> Path:
    file_path = Path(path).expanduser()
    if file_path.suffix.lower() != ".drb":
        raise ValidationError("Media Pool folder files must use the .drb extension.", details={"file": str(file_path)})
    if must_exist and not file_path.is_file():
        raise ValidationError("Media Pool folder file was not found.", details={"file": str(file_path)})
    if not must_exist:
        parent = file_path.parent
        if parent and not parent.exists():
            raise ValidationError("Output directory does not exist.", details={"file": str(file_path), "directory": str(parent)})
        if file_path.exists():
            raise ValidationError("Output DRB file already exists.", details={"file": str(file_path)})
    return file_path


def export_folder_to_drb(conn, folder_path: str, output_file: str) -> Dict[str, Any]:
    """Export a Media Pool folder to a DaVinci Resolve .drb fixture."""
    file_path = _validate_drb_path(output_file, must_exist=False)
    folder = navigate_folder(conn, folder_path, create=False)
    exporter = getattr(folder, "Export", None)
    if not callable(exporter):
        raise APICallFailed("Folder.Export not available.", details={"folder": folder_path, "file": str(file_path)})
    result = exporter(str(file_path))
    if result is False or not file_path.is_file():
        raise APICallFailed(
            "Failed to export Media Pool folder file.",
            details={"folder": folder_path, "file": str(file_path), "native_result": bool(result), "file_exists": file_path.exists()},
        )
    return {"folder": folder_path, "file": str(file_path), "exported": True, "size_bytes": file_path.stat().st_size}


def import_folder_from_drb(conn, file_path: str, source_clips_path: Optional[str] = None) -> Dict[str, Any]:
    """Import a Media Pool folder from a .drb/.drt style folder file."""
    drb_path = _validate_drb_path(file_path, must_exist=True)
    if source_clips_path and not Path(source_clips_path).expanduser().exists():
        raise ValidationError("Source clips path was not found.", details={"file": str(drb_path), "source_clips_path": source_clips_path})
    importer = getattr(conn.media_pool, "ImportFolderFromFile", None)
    if not callable(importer):
        raise APICallFailed("ImportFolderFromFile not available.")
    current_folder = conn.media_pool.GetCurrentFolder()
    before_subfolders = _folder_names(current_folder) if current_folder else []
    result = importer(str(drb_path), source_clips_path) if source_clips_path else importer(str(drb_path))
    after_subfolders = _folder_names(current_folder) if current_folder else []
    if result is False:
        raise APICallFailed(
            "Failed to import Media Pool folder file.",
            details={
                "file": str(drb_path),
                "source_clips_path": source_clips_path,
                "before_subfolders": before_subfolders,
                "after_subfolders": after_subfolders,
            },
        )
    return {
        "file": str(drb_path),
        "source_clips_path": source_clips_path,
        "imported": bool(result),
        "before_subfolders": before_subfolders,
        "after_subfolders": after_subfolders,
        "created_subfolders": [name for name in after_subfolders if name not in before_subfolders],
    }


def get_third_party_metadata(conn, clip_name: str, key: Optional[str] = None) -> Dict[str, Any]:
    """Read third-party metadata from a Media Pool item."""
    clip = find_clip(conn, clip_name)
    if not clip:
        raise APICallFailed(f"Clip '{clip_name}' not found.")
    getter = getattr(clip, "GetThirdPartyMetadata", None)
    if not callable(getter):
        raise APICallFailed("GetThirdPartyMetadata not available.")
    if key:
        try:
            value = getter(key)
        except TypeError:
            data = getter() or {}
            value = data.get(key) if isinstance(data, dict) else None
        return {"clip": clip_name, "key": key, "value": value}
    data = getter()
    return {"clip": clip_name, "metadata": data if isinstance(data, dict) else data}


def set_third_party_metadata(conn, clip_name: str, key_or_data: Any, value: Optional[str] = None) -> Dict[str, Any]:
    """Set third-party metadata on a Media Pool item."""
    clip = find_clip(conn, clip_name)
    if not clip:
        raise APICallFailed(f"Clip '{clip_name}' not found.")
    setter = getattr(clip, "SetThirdPartyMetadata", None)
    if not callable(setter):
        raise APICallFailed("SetThirdPartyMetadata not available.")
    if isinstance(key_or_data, dict):
        result = setter(key_or_data)
        payload = dict(key_or_data)
    else:
        result = setter(str(key_or_data), value)
        payload = {str(key_or_data): value}
    if result is False:
        raise APICallFailed("Failed to set third-party metadata.", details={"clip": clip_name, "metadata": payload})
    return {"clip": clip_name, "metadata": payload, "updated": bool(result)}


def link_full_resolution_media(conn, clip_name: str, path: str) -> Dict[str, Any]:
    """Link full-resolution media for a Media Pool item."""
    clip = find_clip(conn, clip_name)
    if not clip:
        raise APICallFailed(f"Clip '{clip_name}' not found.")
    linker = getattr(clip, "LinkFullResolutionMedia", None)
    if not callable(linker):
        raise APICallFailed("LinkFullResolutionMedia not available.")
    result = linker(path)
    if result is False:
        raise APICallFailed("Failed to link full-resolution media.", details={"clip": clip_name, "path": path})
    return {"clip": clip_name, "path": path, "linked": bool(result)}


def replace_media_pool_clip(conn, clip_name: str, path: str, *, preserve_subclip: bool = False) -> Dict[str, Any]:
    """Replace a Media Pool clip's source media."""
    clip = find_clip(conn, clip_name)
    if not clip:
        raise APICallFailed(f"Clip '{clip_name}' not found.")
    method_name = "ReplaceClipPreserveSubClip" if preserve_subclip else "ReplaceClip"
    replacer = getattr(clip, method_name, None)
    if not callable(replacer):
        raise APICallFailed(f"{method_name} not available.")
    result = replacer(path)
    if result is False:
        raise APICallFailed("Failed to replace clip media.", details={"clip": clip_name, "path": path, "method": method_name})
    return {"clip": clip_name, "path": path, "preserve_subclip": preserve_subclip, "replaced": bool(result), "method": method_name}


def monitor_growing_file(conn, clip_name: str) -> Dict[str, Any]:
    """Enable growing-file monitoring for a Media Pool item."""
    clip = find_clip(conn, clip_name)
    if not clip:
        raise APICallFailed(f"Clip '{clip_name}' not found.")
    monitor = getattr(clip, "MonitorGrowingFile", None)
    if not callable(monitor):
        raise APICallFailed("MonitorGrowingFile not available.")
    result = monitor()
    if result is False:
        raise APICallFailed("Failed to monitor growing file.", details={"clip": clip_name})
    return {"clip": clip_name, "monitoring": bool(result)}


def list_clip_mattes(conn, clip_name: str) -> Dict[str, Any]:
    """List matte paths attached to a Media Pool item."""
    clip = find_clip(conn, clip_name)
    if not clip:
        raise APICallFailed(f"Clip '{clip_name}' not found.")
    getter = getattr(conn.media_pool, "GetClipMatteList", None)
    if not callable(getter):
        raise APICallFailed("GetClipMatteList not available.")
    mattes = getter(clip) or []
    return {"clip": clip_name, "mattes": mattes if isinstance(mattes, list) else [mattes] if mattes else []}


def delete_clip_mattes(conn, clip_name: str, paths: list[str]) -> Dict[str, Any]:
    """Delete matte paths from a Media Pool item."""
    clip = find_clip(conn, clip_name)
    if not clip:
        raise APICallFailed(f"Clip '{clip_name}' not found.")
    deleter = getattr(conn.media_pool, "DeleteClipMattes", None)
    if not callable(deleter):
        raise APICallFailed("DeleteClipMattes not available.")
    result = deleter(clip, paths)
    if result is False:
        raise APICallFailed("Failed to delete clip matte(s).", details={"clip": clip_name, "paths": paths})
    return {"clip": clip_name, "paths": paths, "deleted": bool(result)}


def list_timeline_mattes(conn, folder_name: str) -> Dict[str, Any]:
    """List timeline mattes from a Media Pool folder."""
    folder = navigate_folder(conn, folder_name, create=False)
    getter = getattr(conn.media_pool, "GetTimelineMatteList", None)
    if not callable(getter):
        raise APICallFailed("GetTimelineMatteList not available.")
    mattes = getter(folder) or []
    result = {"folder": folder_name, "mattes": mattes}
    if os.environ.get("CUTAGENT_SDK_TIMELINE_MATTE_IDENTITY") == "1":
        from .sdk_live_inspection import media_pool_native_id

        native_id = media_pool_native_id(folder, folder=True)
        if not native_id:
            raise APICallFailed("DaVinci Resolve timeline matte folder identity is unavailable.")
        result["folder_native_id"] = native_id
    return result
