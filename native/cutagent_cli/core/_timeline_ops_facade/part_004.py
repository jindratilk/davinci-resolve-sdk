from __future__ import annotations

from collections import Counter


def _read_srt_entries(path: Path) -> List[Dict[str, Any]]:
    """Return simple SRT entries for preflight/readback matching."""
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        raise ValidationError(
            "Subtitle SRT file must be UTF-8 text.",
            details={"path": str(path), "encoding": "utf-8"},
            recoverability="not_applicable",
        ) from exc

    entries: List[Dict[str, Any]] = []
    for block in text.replace("\r\n", "\n").replace("\r", "\n").split("\n\n"):
        lines = [line.strip("\ufeff") for line in block.split("\n") if line.strip()]
        if not lines:
            continue
        if lines[0].strip().isdigit():
            lines = lines[1:]
        if not lines or "-->" not in lines[0]:
            continue
        body = "\n".join(line.strip() for line in lines[1:]).strip()
        if body:
            entries.append({"text": body, "timing": lines[0].strip()})

    if not entries:
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        raise ValidationError(
            "Subtitle SRT file does not contain any timed subtitle entries.",
            details={"path": str(path), "format": "srt"},
            recoverability="not_applicable",
        )
    return entries


def _subtitle_text_counter(rows: List[Dict[str, Any]]) -> Counter:
    return Counter(str(row.get("text") or "") for row in rows)


def insert_subtitles_from_srt(conn, path: str, *, ensure_track: bool = True) -> Dict[str, Any]:
    """Insert an SRT file as native DaVinci Resolve subtitle-track items."""
    if not conn.timeline:
        raise APICallFailed("No active timeline.")
    media_pool = getattr(conn, "media_pool", None)
    if media_pool is None:
        raise APICallFailed("No media pool available.")

    subtitle_path = Path(path).expanduser()
    if subtitle_path.suffix.lower() != ".srt":
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        raise ValidationError(
            "Only SRT subtitle insertion is live-verified for this native route.",
            details={"path": str(subtitle_path), "suffix": subtitle_path.suffix, "supported": [".srt"]},
            recoverability="not_applicable",
        )
    if not subtitle_path.is_file():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        raise ValidationError(
            "Subtitle SRT file was not found.",
            details={"path": str(subtitle_path)},
            recoverability="not_applicable",
        )

    expected_entries = _read_srt_entries(subtitle_path)
    before_tracks = int(conn.timeline.GetTrackCount("subtitle") or 0)
    if before_tracks < 1:
        if not ensure_track:
            set_verification_status("not_requested")
            set_recoverability("manual")
            raise ValidationError(
                "No subtitle track exists.",
                details={"subtitle_tracks_found": before_tracks, "ensure_track": False},
                recoverability="manual",
            )
        adder = getattr(conn.timeline, "AddTrack", None)
        if not callable(adder):
            raise APICallFailed(
                "Timeline.AddTrack is not available for subtitle insertion.",
                details={"required_method": 'Timeline.AddTrack("subtitle")'},
            )
        if not adder("subtitle"):
            raise APICallFailed("Failed to create a subtitle track.")

    before_rows = list_subtitles(conn)
    importer = getattr(media_pool, "ImportMedia", None)
    appender = getattr(media_pool, "AppendToTimeline", None)
    if not callable(importer) or not callable(appender):
        raise APICallFailed(
            "MediaPool subtitle import/append APIs are not available.",
            details={
                "required_methods": ["MediaPool.ImportMedia([path])", "MediaPool.AppendToTimeline([mediaPoolItem])"],
            },
        )

    imported = importer([str(subtitle_path)])
    if not imported:
        raise APICallFailed(
            "DaVinci Resolve did not import the subtitle file.",
            details={"path": str(subtitle_path), "api": "MediaPool.ImportMedia"},
        )
    subtitle_item = imported[0]
    properties: Dict[str, Any] = {}
    getter = getattr(subtitle_item, "GetClipProperty", None)
    if callable(getter):
        try:
            raw_properties = getter()
            if isinstance(raw_properties, dict):
                properties = raw_properties
        except Exception:
            properties = {}
    media_type = str(properties.get("Type") or "").strip()
    if media_type and media_type.lower() != "subtitle":
        raise APICallFailed(
            "Imported media is not a DaVinci Resolve subtitle item.",
            details={"path": str(subtitle_path), "media_type": media_type},
        )

    appended = appender([subtitle_item])
    if not appended:
        raise APICallFailed(
            "DaVinci Resolve failed to append the subtitle item to the timeline.",
            details={"path": str(subtitle_path), "api": "MediaPool.AppendToTimeline"},
        )

    if hasattr(conn, "refresh"):
        conn.refresh()
    after_tracks = int(conn.timeline.GetTrackCount("subtitle") or 0)
    after_rows = list_subtitles(conn)
    before_counter = _subtitle_text_counter(before_rows)
    after_counter = _subtitle_text_counter(after_rows)
    expected_counter = Counter(entry["text"] for entry in expected_entries)
    matched_count = 0
    missing: List[Dict[str, Any]] = []
    for text, count in expected_counter.items():
        delta = max(0, after_counter[text] - before_counter[text])
        matched_count += min(delta, count)
        if delta < count:
            missing.append({"text": text, "expected": count, "matched": delta})
    verified = not missing and matched_count >= len(expected_entries)
    set_verification_status("verified" if verified else "failed")
    set_recoverability("manual")
    if not verified:
        raise APICallFailed(
            "Subtitle insert did not match DaVinci Resolve readback.",
            details={
                "path": str(subtitle_path),
                "expected_entries": expected_entries,
                "missing": missing,
                "subtitle_tracks_before": before_tracks,
                "subtitle_tracks_after": after_tracks,
                "readback_entries": len(after_rows),
            },
        )

    inserted_rows = after_rows[len(before_rows):] if len(after_rows) >= len(before_rows) else after_rows
    return {
        "action": "timeline.subtitle.insert",
        "path": str(subtitle_path),
        "format": "srt",
        "imported_media_type": media_type or None,
        "expected_entries": len(expected_entries),
        "matched_entries": matched_count,
        "subtitle_tracks_before": before_tracks,
        "subtitle_tracks_after": after_tracks,
        "created_subtitle_track": before_tracks < 1 and after_tracks > before_tracks,
        "inserted_items": inserted_rows,
        "verified": True,
        "native_api": ["MediaPool.ImportMedia([path])", "MediaPool.AppendToTimeline([mediaPoolItem])"],
    }


def export_subtitles_srt_vtt(
    conn,
    output_path: str,
    fmt: str = "srt",
    track: Optional[int] = None,
    all_tracks: bool = False,
    *,
    return_details: bool = False,
) -> str | Dict[str, Any]:
    """Export subtitles to SRT, VTT, or TTML from timeline subtitle clips."""
    normalized_fmt = fmt.lower()
    if normalized_fmt not in {"srt", "vtt", "ttml"}:
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        raise ValidationError("Subtitle export format must be srt, vtt, or ttml.", details={"format": fmt})
    if all_tracks and track is not None:
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        raise ValidationError(
            "Use either --track or --all-tracks, not both.",
            details={"track": track, "all_tracks": all_tracks},
            recoverability="not_applicable",
        )
    if track is not None and track < 1:
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        raise ValidationError(
            "Subtitle track index must be 1 or greater.",
            details={"track": track},
            recoverability="not_applicable",
        )

    subtitle_track_count = int(conn.timeline.GetTrackCount("subtitle") or 0)
    if subtitle_track_count < 1:
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        raise ValidationError(
            "No subtitle tracks available to export.",
            details={
                "subtitle_tracks_found": subtitle_track_count,
                "format": normalized_fmt,
                "track": track,
                "all_tracks": all_tracks,
                "output_path": output_path,
            },
            recoverability="not_applicable",
        )
    if track is not None and track > subtitle_track_count:
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        raise ValidationError(
            "Subtitle track not found.",
            details={"track": track, "subtitle_tracks_found": subtitle_track_count},
            recoverability="not_applicable",
        )

    if all_tracks:
        tracks = None
    else:
        tracks = track
    rows = list_subtitles(conn, tracks)
    lines: List[str] = []
    if normalized_fmt == "ttml":
        lines.extend(['<?xml version="1.0" encoding="UTF-8"?>', '<tt xmlns="http://www.w3.org/ns/ttml">', "  <body>", "    <div>"])
    if normalized_fmt == "vtt":
        lines.append("WEBVTT")
        lines.append("")

    for idx, row in enumerate(rows, 1):
        start_rel = max(0, int(row["start_frame"]) - conn.start_frame)
        end_rel = max(0, int(row["end_frame"]) - conn.start_frame)
        if normalized_fmt == "srt":
            lines.append(str(idx))
            lines.append(
                f"{_frame_to_srt_timestamp(start_rel, conn.fps)} --> {_frame_to_srt_timestamp(end_rel, conn.fps)}"
            )
            lines.append(row.get("text", ""))
            lines.append("")
        elif normalized_fmt == "vtt":
            lines.append(
                f"{_frame_to_vtt_timestamp(start_rel, conn.fps)} --> {_frame_to_vtt_timestamp(end_rel, conn.fps)}"
            )
            lines.append(row.get("text", ""))
            lines.append("")
        else:
            escaped = str(row.get("text", "")).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;").replace("'", "&apos;")
            lines.append(f'      <p begin="{_frame_to_vtt_timestamp(start_rel, conn.fps)}" end="{_frame_to_vtt_timestamp(end_rel, conn.fps)}">{escaped}</p>')

    if normalized_fmt == "ttml":
        lines.extend(["    </div>", "  </body>", "</tt>"])

    file_text = "\n".join(lines).rstrip() + "\n"
    Path(output_path).write_text(file_text, encoding="utf-8")
    set_verification_status("verified")
    set_recoverability("not_applicable")
    details = {
        "path": output_path,
        "format": normalized_fmt,
        "track": track,
        "all_tracks": all_tracks,
        "subtitle_tracks_found": subtitle_track_count,
        "tracks_exported": sorted({int(row["track"]) for row in rows}),
        "exported_entries": len(rows),
        "empty_export": len(rows) == 0,
        "bytes_written": len(file_text.encode("utf-8")),
    }
    return details if return_details else output_path


# ---------------------------------------------------------------------------
# Additional Timeline Operations (API parity)
# ---------------------------------------------------------------------------

def get_current_clip_thumbnail(conn) -> Dict[str, Any]:
    """Get thumbnail image data for the current clip at playhead."""
    if not conn.timeline:
        raise APICallFailed("No active timeline.")
    getter = getattr(conn.timeline, "GetCurrentClipThumbnailImage", None)
    if not getter:
        raise APICallFailed("GetCurrentClipThumbnailImage not available.")
    result = getter()
    if result:
        return {"has_thumbnail": True, "data": result}
    return {"has_thumbnail": False}


def convert_timeline_to_stereo(conn) -> Dict[str, Any]:
    """Convert current timeline to stereo 3D."""
    if not conn.timeline:
        raise APICallFailed("No active timeline.")
    converter = getattr(conn.timeline, "ConvertTimelineToStereo", None)
    if not converter:
        raise APICallFailed("ConvertTimelineToStereo not available.")
    result = converter()
    return {"converted": bool(result)}


def import_into_timeline(
    conn,
    file_path: str,
    *,
    offset_tc: Optional[str] = None,
    source_clips_path: Optional[str] = None,
    options: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Import timeline content into the active timeline."""
    if not conn.timeline:
        raise APICallFailed("No active timeline.")
    importer = getattr(conn.timeline, "ImportIntoTimeline", None)
    if not callable(importer):
        raise APICallFailed("ImportIntoTimeline not available.")
    import_options = dict(options or {})
    if offset_tc:
        if import_options.get("insertAdditionalTracks") not in {None, False}:
            raise ValidationError(
                "Import offset requires insertAdditionalTracks=False.",
                details={"insertAdditionalTracks": import_options.get("insertAdditionalTracks"), "offset": offset_tc},
            )
        import_options["insertAdditionalTracks"] = False
        import_options["insertWithOffset"] = offset_tc
    if source_clips_path:
        import_options["sourceClipsPath"] = source_clips_path
    try:
        result = importer(file_path, import_options) if import_options else importer(file_path)
    except TypeError as exc:
        if import_options:
            raise CapabilityNegotiationFailed(
                "This DaVinci Resolve scripting API does not accept Timeline.ImportIntoTimeline import options.",
                details={
                    "capability_id": "timeline.import_into",
                    "required_method": "Timeline.ImportIntoTimeline(filePath, importOptions)",
                    "file": file_path,
                    "options": import_options,
                },
            ) from exc
        result = importer(file_path)
    if result is False:
        raise APICallFailed("Failed to import into timeline.", details={"file": file_path, "options": import_options})
    return {"file": file_path, "options": import_options, "imported": bool(result)}


def insert_fusion_composition(conn) -> Dict[str, Any]:
    """Insert a Fusion composition into the active timeline."""
    if not conn.timeline:
        raise APICallFailed("No active timeline.")
    inserter = getattr(conn.timeline, "InsertFusionCompositionIntoTimeline", None)
    if not callable(inserter):
        raise APICallFailed("InsertFusionCompositionIntoTimeline not available.")
    item = inserter()
    if not item:
        raise APICallFailed("Failed to insert Fusion composition.")
    return {"inserted": True, "item": _timeline_item_descriptor(item, "video", 0)}


def create_fusion_clip(conn, clip_names: list[str]) -> Dict[str, Any]:
    """Create a Fusion clip from timeline items."""
    from . import clip_ops

    if not conn.timeline:
        raise APICallFailed("No active timeline.")
    if not clip_names:
        raise ValidationError("At least one clip name is required.", details={"clips": clip_names})
    creator = getattr(conn.timeline, "CreateFusionClip", None)
    if not callable(creator):
        raise APICallFailed("CreateFusionClip not available.")
    items = [clip_ops.cutagent_clip(conn, name) for name in clip_names]
    result = creator(items)
    if not result:
        raise APICallFailed("Failed to create Fusion clip.", details={"clips": clip_names})
    return {"clips": clip_names, "created": _timeline_item_descriptor(result, "video", 0)}


def grab_all_stills(conn, source: str = "first") -> Dict[str, Any]:
    """Grab stills for all clips on the current timeline."""
    if not conn.timeline:
        raise APICallFailed("No active timeline.")
    grabber = getattr(conn.timeline, "GrabAllStills", None)
    if not callable(grabber):
        raise APICallFailed("GrabAllStills not available.")
    normalized = str(source or "first").strip().lower()
    if normalized not in {"first", "middle"}:
        raise ValidationError("Still source must be first or middle.", details={"source": source})
    source_value = 1 if normalized == "first" else 2
    result = grabber(source_value)
    if result is False or result is None:
        raise APICallFailed("GrabAllStills failed.", details={"source": normalized})
    return {
        "source": normalized,
        "source_value": source_value,
        "grabbed": True,
        "still_count": len(result) if isinstance(result, list) else None,
        "stills": result if isinstance(result, list) else [],
    }


_DOLBY_PROJECT_CONTROL_SETTINGS = {
    "hdrDolbyControlsOn": "1",
    "hdrMasteringOn": "1",
}


_DOLBY_DIAGNOSTIC_SETTINGS = (
    "hdrDolbyControlsOn",
    "hdrMasteringOn",
    "hdrDolbyVersion",
    "hdrDolbyAnalysisTuning",
    "colorScienceMode",
    "timelineWorkingLuminance",
    "timelineWorkingLuminanceMode",
    "colorSpaceTimeline",
    "colorSpaceOutput",
)


def _read_project_settings(project: Any, keys: tuple[str, ...]) -> Dict[str, Any]:
    settings: Dict[str, Any] = {}
    if not project:
        return settings
    getter = getattr(project, "GetSetting", None)
    if not callable(getter):
        return settings
    for key in keys:
        try:
            settings[key] = getter(key)
        except Exception as exc:
            settings[key] = f"<unreadable: {exc}>"
    return settings


def _ensure_dolby_project_controls(conn, *, enable: bool) -> Dict[str, Any]:
    project = getattr(conn, "project", None)
    before = _read_project_settings(project, _DOLBY_DIAGNOSTIC_SETTINGS)
    result: Dict[str, Any] = {"enabled": False, "requested": enable, "changed": {}, "before": before, "after": before}
    if not enable:
        return result
    setter = getattr(project, "SetSetting", None) if project else None
    if not callable(setter):
        result["warning"] = "Project.SetSetting is not available; Dolby Vision controls could not be enabled automatically."
        return result
    for key, value in _DOLBY_PROJECT_CONTROL_SETTINGS.items():
        if str(before.get(key, "")).strip() == value:
            continue
        try:
            ok = setter(key, value)
        except Exception as exc:
            result["changed"][key] = {"requested": value, "ok": False, "error": str(exc)}
            continue
        result["changed"][key] = {"from": before.get(key), "to": value, "ok": bool(ok)}
    after = _read_project_settings(project, _DOLBY_DIAGNOSTIC_SETTINGS)
    result["after"] = after
    result["enabled"] = all(str(after.get(key, "")).strip() == value for key, value in _DOLBY_PROJECT_CONTROL_SETTINGS.items())
    if enable and not result["enabled"]:
        result["warning"] = "Dolby Vision project controls are still not enabled after Project.SetSetting."
    return result


def _dolby_analysis_type(conn, *, blend_shots: bool) -> Any:
    if not blend_shots:
        return None
    resolve = getattr(conn, "resolve", None)
    return getattr(resolve, "DLB_BLEND_SHOTS", 1)


def _dolby_timeline_items(conn, item_names: Optional[list[str]]) -> tuple[list[Any], list[Dict[str, Any]]]:
    if not item_names:
        return [], []
    from . import clip_ops

    items: list[Any] = []
    descriptors: list[Dict[str, Any]] = []
    for name in item_names:
        item = clip_ops.cutagent_clip(conn, name)
        items.append(item)
        descriptors.append(_timeline_item_descriptor(item, "timeline", 0))
    return items, descriptors


def _dolby_timeline_summary(conn) -> Dict[str, Any]:
    timeline = getattr(conn, "timeline", None)
    summary: Dict[str, Any] = {"name": None, "track_counts": {}, "item_count": 0}
    if not timeline:
        return summary
    try:
        summary["name"] = timeline.GetName()
    except Exception:
        pass
    for track_type in ("video", "audio"):
        try:
            count = timeline.GetTrackCount(track_type) or 0
        except Exception:
            count = 0
        summary["track_counts"][track_type] = count
        for index in range(1, count + 1):
            try:
                summary["item_count"] += len(timeline.GetItemListInTrack(track_type, index) or [])
            except Exception:
                pass
    return summary


def analyze_dolby_vision(
    conn,
    item_names: Optional[list[str]] = None,
    *,
    blend_shots: bool = False,
    enable_project_controls: bool = True,
) -> Dict[str, Any]:
    """Run Dolby Vision analysis through the native DaVinci Resolve timeline API."""
    if not conn.timeline:
        raise APICallFailed("No active timeline.")
    analyzer = getattr(conn.timeline, "AnalyzeDolbyVision", None)
    if not callable(analyzer):
        raise APICallFailed("AnalyzeDolbyVision not available.")
    controls = _ensure_dolby_project_controls(conn, enable=enable_project_controls)
    items, item_descriptors = _dolby_timeline_items(conn, item_names)
    analysis_type = _dolby_analysis_type(conn, blend_shots=blend_shots)
    args: list[Any] = [items]
    if analysis_type is not None:
        args.append(analysis_type)
    try:
        result = analyzer(*args)
    except TypeError as exc:
        raise CapabilityNegotiationFailed(
            "Timeline.AnalyzeDolbyVision signature is not compatible with requested options.",
            details={
                "required_method": "Timeline.AnalyzeDolbyVision([timelineItems]=[], analysisType=NONE)",
                "items": item_names or [],
                "blend_shots": blend_shots,
                "analysis_type": analysis_type,
                "error": str(exc),
            },
        ) from exc
    if result is False:
        raise APICallFailed(
            "AnalyzeDolbyVision failed.",
            details={
                "items": item_names or [],
                "blend_shots": blend_shots,
                "analysis_type": analysis_type,
                "project_controls": controls,
                "timeline": _dolby_timeline_summary(conn),
                "required_manual_step": "Enable and configure Dolby Vision/HDR project settings in DaVinci Resolve, then run analysis on analyzable timeline clips.",
            },
        )
    return {
        "items": item_names or [],
        "item_count": len(items) if item_names else None,
        "item_descriptors": item_descriptors,
        "blend_shots": blend_shots,
        "analysis_type": analysis_type,
        "project_controls": controls,
        "timeline": _dolby_timeline_summary(conn),
        "analyzed": bool(result),
    }


def _normalize_mark_type(mark_type: str) -> str:
    normalized = str(mark_type or "all").strip().lower()
    if normalized not in {"all", "video", "audio"}:
        raise ValidationError("Mark type must be one of: all, video, audio.", details={"mark_type": mark_type})
    return normalized


def get_mark_in_out(conn) -> Dict[str, Any]:
    """Read active timeline mark in/out points."""
    getter = getattr(conn.timeline, "GetMarkInOut", None)
    if not callable(getter):
        raise APICallFailed("GetMarkInOut not available.")
    return {"marks": getter()}


def set_mark_in_out(conn, mark_in: int, mark_out: int, mark_type: str = "all") -> Dict[str, Any]:
    """Set active timeline mark in/out points."""
    if mark_out <= mark_in:
        raise ValidationError("Mark out must be greater than mark in.", details={"in": mark_in, "out": mark_out})
    setter = getattr(conn.timeline, "SetMarkInOut", None)
    if not callable(setter):
        raise APICallFailed("SetMarkInOut not available.")
    normalized_type = _normalize_mark_type(mark_type)
    result = setter(int(mark_in), int(mark_out), normalized_type)
    if result is False:
        raise APICallFailed("Failed to set timeline mark in/out.", details={"in": mark_in, "out": mark_out, "type": normalized_type})
    return {"in": int(mark_in), "out": int(mark_out), "type": normalized_type, "set": bool(result)}


def clear_mark_in_out(conn, mark_type: str = "all") -> Dict[str, Any]:
    """Clear active timeline mark in/out points."""
    clearer = getattr(conn.timeline, "ClearMarkInOut", None)
    if not callable(clearer):
        raise APICallFailed("ClearMarkInOut not available.")
    normalized_type = _normalize_mark_type(mark_type)
    result = clearer(normalized_type)
    if result is False:
        raise APICallFailed("Failed to clear timeline mark in/out.", details={"type": normalized_type})
    return {"type": normalized_type, "cleared": bool(result)}


def _is_unavailable_voice_isolation_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return "method" in text and ("not available" in text or "unsupported" in text)


def get_timeline_voice_isolation(conn, track_index: int) -> Dict[str, Any]:
    """Read timeline/track voice isolation state."""
    getter = getattr(conn.timeline, "GetVoiceIsolationState", None)
    if not callable(getter):
        set_verification_status("not_requested")
        raise CapabilityNegotiationFailed(
            "Timeline voice isolation is not available through this DaVinci Resolve scripting runtime.",
            details={
                "capability_id": "fairlight.timeline_voice_isolation",
                "track": int(track_index),
                "required_native_api": "Timeline.GetVoiceIsolationState(track)",
                "workaround": "Use `fairlight ai read` for clip-level DB readback, or enable/read track Voice Isolation manually in DaVinci Resolve.",
            },
        )
    try:
        state = getter(int(track_index))
    except TypeError:
        try:
            state = getter()
        except APICallFailed as exc:
            if _is_unavailable_voice_isolation_error(exc):
                set_verification_status("not_requested")
                raise CapabilityNegotiationFailed(
                    "Timeline voice isolation is not available through this DaVinci Resolve scripting runtime.",
                    details={
                        "capability_id": "fairlight.timeline_voice_isolation",
                        "track": int(track_index),
                        "required_native_api": "Timeline.GetVoiceIsolationState(track)",
                        "runtime_error": str(exc),
                        "native_probe_evidence": {
                            "probe_result": "method not available",
                            "runtime_method": "Timeline.GetVoiceIsolationState",
                            "mutating_write_confirmed": False,
                        },
                    },
                ) from exc
            raise
    except APICallFailed as exc:
        if _is_unavailable_voice_isolation_error(exc):
            set_verification_status("not_requested")
            raise CapabilityNegotiationFailed(
                "Timeline voice isolation is not available through this DaVinci Resolve scripting runtime.",
                details={
                    "capability_id": "fairlight.timeline_voice_isolation",
                    "track": int(track_index),
                    "required_native_api": "Timeline.GetVoiceIsolationState(track)",
                    "runtime_error": str(exc),
                    "native_probe_evidence": {
                        "probe_result": "method not available",
                        "runtime_method": "Timeline.GetVoiceIsolationState",
                        "mutating_write_confirmed": False,
                    },
                },
            ) from exc
        raise
    data = state if isinstance(state, dict) else {"state": state}
    data["track"] = int(track_index)
    return data


def set_timeline_voice_isolation(conn, track_index: int, *, enabled: Optional[bool], amount: Optional[int]) -> Dict[str, Any]:
    """Set timeline/track voice isolation state."""
    setter = getattr(conn.timeline, "SetVoiceIsolationState", None)
    if not callable(setter):
        set_verification_status("not_requested")
        raise CapabilityNegotiationFailed(
            "Timeline voice isolation writes are not available through this DaVinci Resolve scripting runtime.",
            details={
                "capability_id": "fairlight.timeline_voice_isolation",
                "track": int(track_index),
                "required_native_api": "Timeline.SetVoiceIsolationState(track, state)",
                "workaround": "Use clip-level `fairlight ai ...` DB routes only when the target clip already has the corresponding Fairlight AI payload.",
            },
        )
    getter = getattr(conn.timeline, "GetVoiceIsolationState", None)
    if not callable(getter):
        set_verification_status("not_requested")
        raise CapabilityNegotiationFailed(
            "Timeline voice isolation readback is not available through this DaVinci Resolve scripting runtime.",
            details={
                "capability_id": "fairlight.timeline_voice_isolation",
                "track": int(track_index),
                "required_native_api": "Timeline.GetVoiceIsolationState(track)",
                "workaround": "Use DaVinci Resolve manually; CutAgent CLI requires readback before writing track Voice Isolation.",
            },
        )

    def _read_state() -> dict[str, Any]:
        try:
            raw_state = getter(int(track_index))
        except TypeError:
            raw_state = getter()
        if isinstance(raw_state, dict):
            return raw_state
        return {"state": raw_state}

    try:
        current = _read_state()
    except APICallFailed as exc:
        if _is_unavailable_voice_isolation_error(exc):
            set_verification_status("not_requested")
            raise CapabilityNegotiationFailed(
                "Timeline voice isolation readback is not available through this DaVinci Resolve scripting runtime.",
                details={
                    "capability_id": "fairlight.timeline_voice_isolation",
                    "track": int(track_index),
                    "required_native_api": "Timeline.GetVoiceIsolationState(track)",
                    "runtime_error": str(exc),
                    "native_probe_evidence": {
                        "probe_result": "method not available",
                        "runtime_method": "Timeline.GetVoiceIsolationState",
                        "mutating_write_confirmed": False,
                    },
                },
            ) from exc
        raise
    state = {
        "isEnabled": bool(current.get("isEnabled", False) if enabled is None else enabled),
        "amount": int(current.get("amount", 100 if enabled else 0) if amount is None else amount),
    }
    if not 0 <= state["amount"] <= 100:
        raise ValidationError("Voice isolation amount must be between 0 and 100.", details={"amount": state["amount"]})
    try:
        result = setter(int(track_index), dict(state))
    except TypeError:
        try:
            result = setter(dict(state))
        except APICallFailed as exc:
            if _is_unavailable_voice_isolation_error(exc):
                set_verification_status("not_requested")
                raise CapabilityNegotiationFailed(
                    "Timeline voice isolation writes are not available through this DaVinci Resolve scripting runtime.",
                    details={
                        "capability_id": "fairlight.timeline_voice_isolation",
                        "track": int(track_index),
                        "state": state,
                        "required_native_api": "Timeline.SetVoiceIsolationState(track, state)",
                        "runtime_error": str(exc),
                        "native_probe_evidence": {
                            "probe_result": "method not available",
                            "runtime_method": "Timeline.SetVoiceIsolationState",
                            "mutating_write_confirmed": False,
                        },
                    },
                ) from exc
            raise
    except APICallFailed as exc:
        if _is_unavailable_voice_isolation_error(exc):
            set_verification_status("not_requested")
            raise CapabilityNegotiationFailed(
                "Timeline voice isolation writes are not available through this DaVinci Resolve scripting runtime.",
                details={
                    "capability_id": "fairlight.timeline_voice_isolation",
                    "track": int(track_index),
                    "state": state,
                    "required_native_api": "Timeline.SetVoiceIsolationState(track, state)",
                    "runtime_error": str(exc),
                    "native_probe_evidence": {
                        "probe_result": "method not available",
                        "runtime_method": "Timeline.SetVoiceIsolationState",
                        "mutating_write_confirmed": False,
                    },
                },
            ) from exc
        raise
    if result is False:
        raise APICallFailed("SetVoiceIsolationState failed.", details={"track": track_index, "state": state})
    try:
        readback = _read_state()
    except APICallFailed as exc:
        if _is_unavailable_voice_isolation_error(exc):
            set_verification_status("pending_manual")
            raise CapabilityNegotiationFailed(
                "Timeline voice isolation write completed but readback is not available.",
                details={
                    "capability_id": "fairlight.timeline_voice_isolation",
                    "track": int(track_index),
                    "state": state,
                    "required_native_api": "Timeline.GetVoiceIsolationState(track)",
                    "runtime_error": str(exc),
                    "native_probe_evidence": {
                        "probe_result": "method not available",
                        "runtime_method": "Timeline.GetVoiceIsolationState",
                        "mutating_write_confirmed": True,
                    },
                },
            ) from exc
        raise
    read_enabled = bool(readback.get("isEnabled")) if "isEnabled" in readback else None
    read_amount = int(readback.get("amount")) if "amount" in readback and readback.get("amount") is not None else None
    if read_enabled != state["isEnabled"] or read_amount != state["amount"]:
        set_verification_status("failed")
        raise APICallFailed(
            "SetVoiceIsolationState readback did not match requested state.",
            details={"track": track_index, "expected": state, "actual": readback},
        )
    set_verification_status("verified")
    state["track"] = int(track_index)
    state["readback"] = readback
    return state


def current_timeline_media_pool_item(conn) -> Dict[str, Any]:
    """Return the MediaPoolItem for the current timeline when exposed."""
    getter = getattr(conn.timeline, "GetMediaPoolItem", None)
    if not callable(getter):
        raise APICallFailed("Timeline.GetMediaPoolItem not available.")
    item = getter()
    if not item:
        raise APICallFailed("Current timeline did not return a MediaPoolItem.")
    return {"name": item.GetName() if hasattr(item, "GetName") else None, "item": item}


def inspect_timeline_node_graph(conn) -> Dict[str, Any]:
    """Best-effort timeline node graph inspection."""
    graph_getter = getattr(conn.timeline, "GetNodeGraph", None)
    if not callable(graph_getter):
        raise APICallFailed("Timeline.GetNodeGraph not available.")
    graph = graph_getter()
    return {"available": bool(graph), "graph": graph}


def export_current_frame(conn, output_path: str, position: Optional[str] = None) -> Dict[str, Any]:
    """Export the current frame, optionally moving the playhead first."""
    if position:
        set_playhead(conn, position)
    exporter = getattr(conn.project, "ExportCurrentFrameAsStill", None)
    if not callable(exporter):
        raise APICallFailed("ExportCurrentFrameAsStill not available.")
    result = exporter(output_path)
    if result is False:
        raise APICallFailed("Failed to export current frame.", details={"output_path": output_path, "position": position})
    return {"output_path": output_path, "position": position, "exported": bool(result)}


def detect_scene_cuts_native(conn) -> Dict[str, Any]:
    """Detect scene cuts using DaVinci Resolve.s built-in detection."""
    if not conn.timeline:
        raise APICallFailed("No active timeline.")
    detector = getattr(conn.timeline, "DetectSceneCuts", None)
    if not detector:
        raise APICallFailed("DetectSceneCuts not available.")
    before = _scene_detection_snapshot(conn)
    result = detector()
    timeline_name = conn.timeline.GetName() if hasattr(conn.timeline, "GetName") else None
    after = _wait_for_scene_detection_change(conn, before)
    cuts_created = max(0, after["video_items"] - before["video_items"])
    verification = {
        "status": "verified" if cuts_created > 0 else "failed",
        "pre": before,
        "post": after,
        "cuts_created": cuts_created,
    }
    if not result:
        set_verification_status("failed")
        raise APICallFailed(
            "DetectSceneCuts failed.",
            details={
                "timeline": timeline_name,
                "route": "resolve_native",
                "verification": verification,
            },
        )
    if cuts_created <= 0:
        set_verification_status("failed")
        raise APICallFailed(
            "Scene detection completed without creating timeline cuts.",
            details={
                "timeline": timeline_name,
                "route": "resolve_native",
                "verification": verification,
                "possible_causes": [
                    "DaVinci Resolve did not detect scene boundaries in the current timeline.",
                    "The active timeline or selected clip is not eligible for native scene detection.",
                    "DaVinci Resolve returned success before applying any observable timeline split.",
                ],
            },
        )
    set_verification_status("verified")
    return {
        "timeline": timeline_name,
        "route": "resolve_native",
        "success": bool(result),
        "verification": verification,
        "cuts_created": cuts_created,
    }


def _scene_detection_snapshot(conn) -> Dict[str, Any]:
    timeline = conn.timeline
    video_tracks = timeline.GetTrackCount("video") or 0
    audio_tracks = timeline.GetTrackCount("audio") or 0
    video_items = 0
    audio_items = 0
    tracks: list[dict[str, Any]] = []
    for track_type, track_count in (("video", video_tracks), ("audio", audio_tracks)):
        for index in range(1, track_count + 1):
            items = timeline.GetItemListInTrack(track_type, index) or []
            item_count = len(items)
            if track_type == "video":
                video_items += item_count
            else:
                audio_items += item_count
            tracks.append({"type": track_type, "index": index, "items": item_count})
    return {
        "video_tracks": video_tracks,
        "audio_tracks": audio_tracks,
        "video_items": video_items,
        "audio_items": audio_items,
        "tracks": tracks,
    }


def _wait_for_scene_detection_change(conn, before: Dict[str, Any], timeout_s: float = 3.0) -> Dict[str, Any]:
    deadline = time.monotonic() + timeout_s
    latest = _scene_detection_snapshot(conn)
    while time.monotonic() < deadline:
        if latest["video_items"] > before["video_items"]:
            return latest
        time.sleep(0.1)
        latest = _scene_detection_snapshot(conn)
    return latest
