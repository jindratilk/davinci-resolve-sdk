from __future__ import annotations

def create_subtitles_from_audio(
    conn,
    *,
    language: Optional[str] = None,
    preset: Optional[str] = None,
    chars_per_line: Optional[int] = None,
    line_break: Optional[str] = None,
    gap: Optional[int] = None,
) -> Dict[str, Any]:
    """Create timeline subtitles from audio transcription."""
    if not conn.timeline:
        raise APICallFailed("No active timeline.")

    def _timeline_name() -> str | None:
        getter = getattr(conn.timeline, "GetName", None)
        if not callable(getter):
            return None
        try:
            value = getter()
        except Exception:
            return None
        return str(value) if value is not None else None

    def _subtitle_snapshot() -> tuple[int | None, int | None]:
        try:
            track_count = int(conn.timeline.GetTrackCount("subtitle") or 0)
        except Exception:
            return None, None
        item_count = 0
        for index in range(1, track_count + 1):
            try:
                item_count += len(conn.timeline.GetItemListInTrack("subtitle", index) or [])
            except Exception:
                pass
        return track_count, item_count

    def _audio_track_count() -> int | None:
        try:
            return int(conn.timeline.GetTrackCount("audio") or 0)
        except Exception:
            return None

    def _track_item_count(track_type: str, track_count: int | None) -> int | None:
        if track_count is None:
            return None
        item_count = 0
        for index in range(1, track_count + 1):
            try:
                item_count += len(conn.timeline.GetItemListInTrack(track_type, index) or [])
            except Exception:
                return None
        return item_count

    audio_tracks = _audio_track_count()
    audio_items = _track_item_count("audio", audio_tracks)
    if audio_tracks == 0:
        raise ValidationError(
            "Auto-caption requires at least one audio track on the active timeline.",
            details={"audio_tracks": audio_tracks, "audio_items": audio_items},
        )

    creator = require_api_method(
        conn.timeline,
        "CreateSubtitlesFromAudio",
        capability_id="timeline.subtitle_list_add_export",
        runtime_object="timeline",
    )
    settings: Dict[str, Any] = {}
    normalized_language = _normalize_auto_caption_language(language)
    normalized_preset = _normalize_auto_caption_preset(preset)
    normalized_line_break = _normalize_auto_caption_line_break(line_break)

    if normalized_language:
        settings[_resolve_api_constant(conn, "SUBTITLE_LANGUAGE")] = _resolve_api_constant(conn, normalized_language)
    if normalized_preset:
        settings[_resolve_api_constant(conn, "SUBTITLE_CAPTION_PRESET")] = _resolve_api_constant(conn, normalized_preset)
    if chars_per_line is not None:
        if not 1 <= int(chars_per_line) <= 60:
            raise ValidationError(
                "Auto-caption chars-per-line must be between 1 and 60.",
                details={"chars_per_line": chars_per_line},
            )
        settings[_resolve_api_constant(conn, "SUBTITLE_CHARS_PER_LINE")] = int(chars_per_line)
    if normalized_line_break:
        settings[_resolve_api_constant(conn, "SUBTITLE_LINE_BREAK")] = _resolve_api_constant(conn, normalized_line_break)
    if gap is not None:
        if not 0 <= int(gap) <= 10:
            raise ValidationError(
                "Auto-caption gap must be between 0 and 10.",
                details={"gap": gap},
            )
        settings[_resolve_api_constant(conn, "SUBTITLE_GAP")] = int(gap)

    before_tracks, before_items = _subtitle_snapshot()
    preflight = {
        "timeline": _timeline_name(),
        "api_method": "CreateSubtitlesFromAudio",
        "api_method_available": True,
        "audio_tracks": audio_tracks,
        "audio_items": audio_items,
        "subtitle_tracks_before": before_tracks,
        "subtitle_items_before": before_items,
        "settings": settings,
    }
    result = creator(settings)
    if not result:
        raise APICallFailed(
            "CreateSubtitlesFromAudio failed.",
            details={
                "settings": settings,
                "audio_tracks": audio_tracks,
                "audio_items": audio_items,
                "subtitle_tracks_before": before_tracks,
                "subtitle_items_before": before_items,
                "preflight": preflight,
                "diagnosis": "DaVinci Resolve exposed CreateSubtitlesFromAudio but rejected the request at runtime.",
                "possible_causes": [
                    "DaVinci Resolve auto-caption model or language support is unavailable or not initialized in this runtime.",
                    "The active timeline has audio tracks but no usable speech content, or the audio is muted, offline, disabled, or otherwise unsupported by DaVinci Resolve transcription.",
                    "DaVinci Resolve rejected one of the subtitle settings; retry with no options or --language auto.",
                    "The installed DaVinci Resolve edition/runtime exposes the method but cannot run the local auto-caption engine in the current session.",
                ],
                "next_steps": [
                    "Open DaVinci Resolve's transcription/auto-caption UI once to confirm the model is installed and licensed.",
                    "Retry with default settings before trying a specific language or caption preset.",
                    "Use timeline subtitle list before and after retrying to verify whether any subtitle track was created.",
                ],
            },
        )

    verification: Dict[str, Any] = {
        "status": "not_available",
        "subtitle_tracks_before": before_tracks,
        "subtitle_items_before": before_items,
    }
    if before_tracks is not None and before_items is not None:
        after_tracks, after_items = before_tracks, before_items
        for _ in range(20):
            refresh = getattr(conn, "refresh", None)
            if callable(refresh):
                try:
                    refresh()
                except Exception:
                    pass
            after_tracks, after_items = _subtitle_snapshot()
            if (
                after_tracks is not None
                and after_items is not None
                and (after_tracks > before_tracks or after_items > before_items)
            ):
                break
            time.sleep(0.25)
        verification.update(
            {
                "status": "verified" if (after_tracks or 0) > before_tracks or (after_items or 0) > before_items else "pending_readback",
                "subtitle_tracks_after": after_tracks,
                "subtitle_items_after": after_items,
            }
        )

    return {"success": True, "settings": settings, "audio_tracks": audio_tracks, "verification": verification}


def import_media(conn, path: str) -> int:
    """
    Import media into the Media Pool.
    
    Args:
        conn: ResolveConnection instance
        path: File or folder path to import
    
    Returns:
        Number of items imported
    
    Raises:
        APICallFailed: If import fails
    """
    import os
    importer = getattr(conn.media_pool, "ImportMedia", None)
    if not callable(importer):
        raise CapabilityNegotiationFailed(
            "MediaPool.ImportMedia is not available.",
            details={"capability_id": "media.import", "required_method": "MediaPool.ImportMedia"},
        )

    expanded_path = os.path.expanduser(path)
    if os.path.isdir(expanded_path):
        # Import all files from directory
        files = [os.path.join(expanded_path, f) for f in os.listdir(expanded_path)
                 if not f.startswith(".")]
        items = importer(files)
    else:
        files = [expanded_path]
        items = importer(files)

    if items:
        return len(items)
    else:
        raise APICallFailed(
            f"Failed to import from: {path}",
            details={
                "path": path,
                "expanded_path": expanded_path,
                "exists": os.path.exists(expanded_path),
                "is_file": os.path.isfile(expanded_path),
                "is_dir": os.path.isdir(expanded_path),
                "suffix": Path(expanded_path).suffix.lower(),
                "payload_count": len(files),
                "payload": files,
                "resolve_result_type": type(items).__name__,
                "resolve_result_repr": repr(items)[:500],
                "path_is_nfc": path == unicodedata.normalize("NFC", path),
                "path_is_nfd": path == unicodedata.normalize("NFD", path),
            },
        )


def delete_clip(conn, name: str) -> bool:
    """
    Delete a clip from the Media Pool.
    
    Args:
        conn: ResolveConnection instance
        name: Clip name
    
    Returns:
        True if successful
    
    Raises:
        APICallFailed: If clip not found or deletion fails
    """
    clip = find_clip(conn, name)
    if not clip:
        raise APICallFailed(f"Clip '{name}' not found.")

    result = conn.media_pool.DeleteClips([clip])
    if result:
        return True
    else:
        raise APICallFailed(f"Failed to delete clip '{name}'.")


def validate_clip_move(conn, name: str, target: str) -> dict[str, Any]:
    """Validate a clip move and return source/target context without mutating."""
    match = find_clip_match(conn, name)
    if not match:
        raise APICallFailed(f"Clip '{name}' not found.")

    try:
        target_folder = navigate_folder(conn, target, create=False)
    except FolderNotFound as exc:
        raise ValidationError(
            str(exc),
            details=getattr(exc, "details", {"target": target}),
            recoverability="not_applicable",
        ) from exc
    destination_path = _get_folder_path(conn.media_pool.GetRootFolder(), target_folder) or target
    return {
        "clip": match["clip"],
        "source_folder": match.get("folder"),
        "target_folder": target_folder,
        "destination_folder": destination_path,
    }


def move_clip(conn, name: str, target: str) -> bool:
    """
    Move a clip to a different folder.
    
    Args:
        conn: ResolveConnection instance
        name: Clip name
        target: Target folder path
    
    Returns:
        True if successful
    
    Raises:
        APICallFailed: If clip not found or move fails
    """
    move_context = validate_clip_move(conn, name, target)
    result = conn.media_pool.MoveClips([move_context["clip"]], move_context["target_folder"])
    if result:
        return True
    else:
        raise APICallFailed("Failed to move clip.")


def duplicate_clip(conn, name: str, new_name: Optional[str] = None) -> Dict[str, Any]:
    """
    Duplicate a media pool clip.

    Falls back to re-importing the source file when no direct duplicate API is available.
    """
    match = find_clip_match(conn, name)
    if not match:
        raise APICallFailed(f"Clip '{name}' not found.")
    clip = match["clip"]

    duplicate = None
    for method_name in ("Duplicate", "DuplicateClip"):
        method = getattr(clip, method_name, None)
        if callable(method):
            try:
                duplicate = method()
                if duplicate:
                    break
            except Exception:
                continue

    imported = None
    if not duplicate:
        source_path = _canonical_source_path(_clip_properties(clip), clip)
        if not source_path:
            raise APICallFailed(
                "Could not resolve source path for duplicate fallback.",
                details={"clip": name},
            )
        root = conn.media_pool.GetRootFolder()
        before_source_count = _count_source_path_matches(root, source_path) if root else 0
        imported = conn.media_pool.ImportMedia([source_path])
        if not imported:
            raise APICallFailed("Failed to duplicate clip via re-import.", details={"source_path": source_path})
        duplicate = imported[0]
        if duplicate is clip:
            raise APICallFailed(
                "DaVinci Resolve returned the source clip instead of a duplicate.",
                details={
                    "clip": name,
                    "source_path": source_path,
                    "fallback": "import_media",
                },
            )
        after_source_count = _count_source_path_matches(root, source_path) if root else before_source_count + 1
        if after_source_count <= before_source_count:
            raise APICallFailed(
                "Duplicate fallback did not create a new Media Pool item.",
                details={
                    "clip": name,
                    "source_path": source_path,
                    "before_count": before_source_count,
                    "after_count": after_source_count,
                    "fallback": "import_media",
                },
            )

    final_name = new_name
    if final_name and hasattr(duplicate, "SetClipProperty"):
        try:
            duplicate.SetClipProperty("Clip Name", final_name)
        except Exception:
            pass
        actual_name = None
        if hasattr(duplicate, "GetName"):
            try:
                actual_name = duplicate.GetName()
            except Exception:
                actual_name = None
        if actual_name and actual_name != final_name:
            raise APICallFailed(
                "Failed to rename duplicated clip.",
                details={"source": name, "requested_name": final_name, "actual_name": actual_name},
            )
        if find_clip_match(conn, name) is None:
            raise APICallFailed(
                "Duplicate fallback did not preserve the source clip.",
                details={"source": name, "requested_name": final_name},
            )
    elif hasattr(duplicate, "GetName"):
        try:
            final_name = duplicate.GetName()
        except Exception:
            pass

    return {"source": name, "duplicate": final_name or new_name or name, "fallback_import": bool(imported)}


def unlink_clip(conn, name: str) -> bool:
    """Unlink clip from source media."""
    clip = find_clip(conn, name)
    if not clip:
        raise APICallFailed(f"Clip '{name}' not found.")
    unlink = require_api_method(
        conn.media_pool,
        "UnlinkClips",
        capability_id="media.unlink_relink",
        runtime_object="media_pool",
    )
    result = unlink([clip])
    if result:
        return True
    raise APICallFailed("Failed to unlink clip.", details={"clip": name})


def relink_clip(conn, name: str, path: str) -> bool:
    """Relink clip to a media path."""
    clip = find_clip(conn, name)
    if not clip:
        raise APICallFailed(f"Clip '{name}' not found.")
    relink = require_api_method(
        conn.media_pool,
        "RelinkClips",
        capability_id="media.unlink_relink",
        runtime_object="media_pool",
    )
    requested_path = os.path.abspath(path)
    api_path = os.path.dirname(requested_path) if os.path.isfile(requested_path) else requested_path
    result = relink([clip], api_path)
    if result:
        try:
            props = clip.GetClipProperty() or {}
        except Exception:
            props = {}
        readback_path = props.get("File Path") or props.get("Source File") or props.get("SourcePath")
        if os.path.isfile(requested_path) and readback_path and os.path.abspath(str(readback_path)) != requested_path:
            raise APICallFailed(
                "Relink returned success but DaVinci Resolve did not bind the requested file.",
                details={"clip": name, "path": requested_path, "api_path": api_path, "readback_path": readback_path},
            )
        return True
    raise APICallFailed("Failed to relink clip.", details={"clip": name, "path": requested_path, "api_path": api_path})


def proxy_clip(
    conn,
    name: str,
    *,
    generate: bool = False,
    link_path: Optional[str] = None,
    unlink: bool = False,
) -> Dict[str, Any]:
    """Generate/link/unlink proxy media for a clip."""
    clip = find_clip(conn, name)
    if not clip:
        raise APICallFailed(f"Clip '{name}' not found.")

    action_count = sum(1 for flag in (generate, bool(link_path), unlink) if flag)
    if action_count == 0:
        raise MissingArgumentError("Choose one proxy action: --generate, --link, or --unlink.")
    if action_count > 1:
        raise ValidationError("Choose exactly one proxy action: --generate, --link, or --unlink.")

    if generate:
        method_name, method = require_any_api_method(
            clip,
            ("GenerateProxyMedia", "GenerateOptimizedMedia"),
            capability_id="media.proxy_transcode",
            runtime_object="media_pool_item",
        )
        try:
            result = method()
        except APICallFailed as exc:
            if "method not available" in str(exc):
                raise CapabilityNegotiationFailed(
                    "Required runtime API method not available.",
                    details={
                        "capability_id": "media.proxy_transcode",
                        "required_method": method_name,
                        "runtime_object": "media_pool_item",
                    },
                ) from exc
            raise
        if result is False:
            raise APICallFailed("Proxy generation failed.", details={"clip": name, "method": method_name})
        return {"clip": name, "action": "generate", "method": method_name}

    if link_path:
        _, method = require_any_api_method(
            clip,
            ("LinkProxyMedia",),
            capability_id="media.proxy_transcode",
            runtime_object="media_pool_item",
        )
        try:
            result = method(link_path)
        except APICallFailed as exc:
            if "method not available" in str(exc):
                raise CapabilityNegotiationFailed(
                    "Required runtime API method not available.",
                    details={
                        "capability_id": "media.proxy_transcode",
                        "required_method": "LinkProxyMedia",
                        "runtime_object": "media_pool_item",
                    },
                ) from exc
            raise
        if result is False:
            raise APICallFailed("Proxy link failed.", details={"clip": name, "path": link_path})
        return {"clip": name, "action": "link", "path": link_path}

    _, method = require_any_api_method(
        clip,
        ("UnlinkProxyMedia",),
        capability_id="media.proxy_transcode",
        runtime_object="media_pool_item",
    )
    try:
        result = method()
    except APICallFailed as exc:
        if "method not available" in str(exc):
            raise CapabilityNegotiationFailed(
                "Required runtime API method not available.",
                details={
                    "capability_id": "media.proxy_transcode",
                    "required_method": "UnlinkProxyMedia",
                    "runtime_object": "media_pool_item",
                },
            ) from exc
        raise
    if result is False:
        raise APICallFailed("Proxy unlink failed.", details={"clip": name})
    return {"clip": name, "action": "unlink"}


def transcode_clip(
    conn,
    name: str,
    output_path: str,
    format_name: Optional[str] = None,
    codec: Optional[str] = None,
) -> Dict[str, Any]:
    """Transcode media pool clip using runtime API when available."""
    clip = find_clip(conn, name)
    if not clip:
        raise APICallFailed(f"Clip '{name}' not found.")

    method_name, method = require_any_api_method(
        clip,
        ("TranscodeMediaPoolItem", "Transcode"),
        capability_id="media.proxy_transcode",
        runtime_object="media_pool_item",
    )
    kwargs = {}
    if format_name:
        kwargs["format"] = format_name
    if codec:
        kwargs["codec"] = codec

    try:
        result = method(output_path, **kwargs)
    except TypeError as exc:
        if kwargs:
            raise APICallFailed(
                "DaVinci Resolve does not accept the requested transcode format or codec.",
                details={"clip": name, "format": format_name, "codec": codec, "method": method_name},
            ) from exc
        try:
            result = method(output_path)
        except APICallFailed as exc:
            if "method not available" in str(exc):
                raise CapabilityNegotiationFailed(
                    "Required runtime API method not available.",
                    details={
                        "capability_id": "media.proxy_transcode",
                        "required_method": method_name,
                        "runtime_object": "media_pool_item",
                    },
                ) from exc
            raise
    except APICallFailed as exc:
        if "method not available" in str(exc):
            raise CapabilityNegotiationFailed(
                "Required runtime API method not available.",
                details={
                    "capability_id": "media.proxy_transcode",
                    "required_method": method_name,
                    "runtime_object": "media_pool_item",
                },
            ) from exc
        raise
    if result is False:
        raise APICallFailed(
            "Transcode failed.",
            details={"clip": name, "output_path": output_path, "method": method_name},
        )
    return {
        "clip": name,
        "output_path": output_path,
        "format": format_name,
        "codec": codec,
        "method": method_name,
    }


def get_clip_metadata(conn, name: str, key: Optional[str] = None) -> Any:
    """
    Get clip metadata.
    
    Args:
        conn: ResolveConnection instance
        name: Clip name
        key: Optional specific metadata key
    
    Returns:
        Metadata value or dict of all metadata
    
    Raises:
        APICallFailed: If clip not found
    """
    clip = find_clip(conn, name)
    if not clip:
        raise APICallFailed(f"Clip '{name}' not found.")

    if key:
        return clip.GetMetadata(key)
    else:
        all_meta = clip.GetMetadata()
        if isinstance(all_meta, dict):
            return all_meta
        else:
            return {"metadata": str(all_meta)}


def set_clip_metadata(conn, name: str, key: str, value: str) -> bool:
    """
    Set clip metadata.
    
    Args:
        conn: ResolveConnection instance
        name: Clip name
        key: Metadata key
        value: Metadata value
    
    Returns:
        True if successful
    
    Raises:
        APICallFailed: If clip not found or setting fails
    """
    clip = find_clip(conn, name)
    if not clip:
        raise APICallFailed(f"Clip '{name}' not found.")

    result = clip.SetMetadata(key, value)
    if result:
        return True
    else:
        raise APICallFailed("Failed to set metadata.")


def search_clips(
    conn,
    query: str,
    exact: bool = False,
    *,
    kind: Optional[str] = None,
    include_generated: bool = True,
) -> List[Dict[str, Any]]:
    """
    Search for clips in the entire Media Pool.
    
    Args:
        conn: ResolveConnection instance
        query: Search query
        exact: Exact name match
    
    Returns:
        List of matching clips with folder paths
    """
    root = conn.media_pool.GetRootFolder()
    results = []
    _search_recursive(
        root,
        query,
        exact,
        results,
        "",
        kind=normalize_media_kind(kind),
        include_generated=include_generated,
    )
    return results


def _search_recursive(
    folder,
    query: str,
    exact: bool,
    results: list,
    path: str,
    *,
    kind: Optional[str],
    include_generated: bool,
):
    """Recursively search for clips."""
    folder_name = folder.GetName() if hasattr(folder, "GetName") else ""
    current_path = f"{path}/{folder_name}" if path else folder_name

    clips = folder.GetClipList() or []
    for clip in clips:
        row = _serialize_clip_row(clip, current_path)
        clip_name = row["name"]
        if not _matches_clip_filters(row, kind, include_generated):
            continue
        if exact:
            if clip_name == query:
                results.append(row)
        else:
            if query.lower() in clip_name.lower():
                results.append(row)

    subfolders = folder.GetSubFolderList() or []
    for sf in subfolders:
        _search_recursive(
            sf,
            query,
            exact,
            results,
            current_path,
            kind=kind,
            include_generated=include_generated,
        )


def append_clip_to_timeline(
    conn,
    name: str,
    at: Optional[str] = None,
    track_type: str = "video",
    track_index: int = 1,
    source_start: Optional[str] = None,
    source_end: Optional[str] = None,
    record_frame: Optional[str] = None,
    absolute_record_frame: Optional[int] = None,
    *,
    name_after_append: str | None = None,
    return_details: bool = False,
) -> bool | Dict[str, Any]:
    """
    Append a clip to the timeline.
    
    Args:
        conn: ResolveConnection instance
        name: Clip name
        at: Optional record-domain position (legacy alias for record_frame)
        track_type: Track type
        track_index: Track index
        source_start: Optional source-domain startFrame reference
        source_end: Optional source-domain endFrame reference
        record_frame: Optional record-domain recordFrame reference
        name_after_append: Optional timeline item name to apply after append
        return_details: Return structured append metadata instead of True
    
    Returns:
        True if successful, or append metadata when return_details=True
    
    Raises:
        APICallFailed: If clip not found or append fails
    """
    normalize_append_track_type(track_type)
    validate_append_track_index(track_index)
    if sum(value is not None for value in (at, record_frame, absolute_record_frame)) > 1:
        raise ValidationError(
            "Use only one of --at, --record-frame, or --absolute-record-frame.",
            details={"at": at, "record_frame": record_frame, "absolute_record_frame": absolute_record_frame},
        )
    if absolute_record_frame is not None and int(absolute_record_frame) < 0:
        raise ValidationError(
            "--absolute-record-frame must be a non-negative DaVinci Resolve recordFrame.",
            details={"absolute_record_frame": absolute_record_frame},
        )
    record_ref = record_frame if record_frame is not None else at
    if record_ref is not None:
        parse_record_frame(str(record_ref), conn.fps, _timeline_start_frame(conn))
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
    match = find_clip_match(conn, name)
    if not match:
        raise APICallFailed(f"Clip '{name}' not found.")
    return append_resolved_clip_to_timeline(
        conn,
        match["clip"],
        name=str(match.get("name") or name),
        folder=match.get("folder"),
        at=at,
        track_type=track_type,
        track_index=track_index,
        source_start=source_start,
        source_end=source_end,
        record_frame=record_frame,
        absolute_record_frame=absolute_record_frame,
        name_after_append=name_after_append,
        return_details=return_details,
    )


def _timeline_item_summary(item) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for key, method in (("name", "GetName"), ("start", "GetStart"), ("end", "GetEnd"), ("duration", "GetDuration")):
        getter = getattr(item, method, None)
        if callable(getter):
            try:
                value = getter()
                if key in {"start", "end", "duration"}:
                    value = int(value)
                summary[key] = value
            except Exception:
                pass
    return summary
