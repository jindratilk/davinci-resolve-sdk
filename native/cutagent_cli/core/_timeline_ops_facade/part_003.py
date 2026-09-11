from __future__ import annotations

def _timeline_items_delete_filters(
    *,
    timeline_name: str | None,
    track_type: str,
    track_index: int | None,
    start_ref: str | None,
    end_ref: str | None,
    start_frame: int | None,
    end_frame: int | None,
    match: str,
    allow_empty: bool,
    force: bool,
) -> Dict[str, Any]:
    return {
        "timeline": timeline_name,
        "track_type": track_type,
        "track_index": track_index,
        "start_frame_ref": start_ref,
        "end_frame_ref": end_ref,
        "start_frame": start_frame,
        "end_frame": end_frame,
        "match": match,
        "allow_empty": bool(allow_empty),
        "force": bool(force),
    }


def _normalize_timeline_item_delete_targets(targets: Optional[List[Dict[str, Any]]]) -> Optional[List[Dict[str, Any]]]:
    if targets is None:
        return None
    if not isinstance(targets, list) or not targets or len(targets) > 4096:
        raise ValidationError("Exact timeline item deletion requires between 1 and 4096 targets.")
    normalized: List[Dict[str, Any]] = []
    keys = set()
    for offset, target in enumerate(targets):
        if not isinstance(target, dict):
            raise ValidationError("Each exact timeline item deletion target must be an object.", details={"target_index": offset})
        track_type = normalize_timeline_item_track_type(target.get("track_type"))
        if track_type == "all":
            raise ValidationError("Exact timeline item deletion targets require video, audio, or subtitle track type.", details={"target_index": offset})
        track_index = validate_timeline_track_index(target.get("track_index"))
        start_frame = target.get("start_frame")
        end_frame = target.get("end_frame")
        name = target.get("name")
        if not isinstance(start_frame, int) or isinstance(start_frame, bool) or not isinstance(end_frame, int) or isinstance(end_frame, bool) or end_frame <= start_frame:
            raise ValidationError("Exact timeline item deletion targets require a valid half-open integer frame range.", details={"target_index": offset})
        if not isinstance(name, str) or not name or len(name) > 4096:
            raise ValidationError("Exact timeline item deletion targets require a non-empty item name.", details={"target_index": offset})
        value = {"track_type": track_type, "track_index": track_index, "start_frame": start_frame, "end_frame": end_frame, "name": name}
        key = (track_type, track_index, start_frame, end_frame, name)
        if key in keys:
            raise ValidationError("Exact timeline item deletion targets must be unique.", details={"target_index": offset})
        keys.add(key)
        normalized.append(value)
    return normalized


def _collect_exact_timeline_item_delete_targets(conn, targets: List[Dict[str, Any]]) -> List[tuple[Any, str, int]]:
    selected: List[tuple[Any, str, int]] = []
    timeline_start = _timeline_start_frame(conn)
    for offset, target in enumerate(targets):
        candidates = _collect_timeline_items_matching_filter(
            conn,
            track_type=target["track_type"],
            track_index=target["track_index"],
            start_frame=target["start_frame"],
            end_frame=target["end_frame"],
            match="contained",
        )
        expected_ranges = {(target["start_frame"], target["end_frame"])}
        if timeline_start:
            expected_ranges.add((target["start_frame"] - timeline_start, target["end_frame"] - timeline_start))
        matches = []
        for item, track_type, track_index in candidates:
            descriptor = _timeline_item_descriptor(item, track_type, track_index)
            if descriptor.get("name") == target["name"] and (descriptor.get("start"), descriptor.get("end")) in expected_ranges:
                matches.append((item, track_type, track_index))
        if len(matches) != 1:
            raise ValidationError(
                "An exact timeline item deletion target changed, disappeared, or became ambiguous.",
                details={"target_index": offset, "target": target, "match_count": len(matches)},
            )
        selected.append(matches[0])
    if len({id(item) for item, _track_type, _track_index in selected}) != len(selected):
        raise ValidationError("Exact timeline item deletion targets resolved to the same native item more than once.")
    return selected


def delete_timeline_items(
    conn,
    *,
    timeline_name: Optional[str] = None,
    track_type: str = "all",
    track_index: Optional[int] = None,
    start_ref: Optional[str] = None,
    end_ref: Optional[str] = None,
    match: str = "overlap",
    allow_empty: bool = False,
    force: bool = False,
    exact_targets: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Delete timeline items without deleting tracks or rippling the timeline."""
    normalized_targets = _normalize_timeline_item_delete_targets(exact_targets)
    normalized_track_type = normalize_timeline_item_track_type(track_type)
    normalized_match = normalize_timeline_item_delete_match(match)
    normalized_track_index = validate_timeline_track_index(track_index) if track_index is not None else None

    if normalized_targets is None and start_ref is None and end_ref is None and not force:
        raise ConfirmationRequired(
            "Deleting timeline items without a frame range requires --force.",
            details={
                "action": "timeline.items.delete",
                "track_type": normalized_track_type,
                "track_index": normalized_track_index,
            },
        )

    if timeline_name:
        switch_timeline(conn, name=timeline_name)

    target_timeline = _timeline_name(conn)
    start_frame = _parse_optional_record_frame(conn, start_ref)
    end_frame = _parse_optional_record_frame(conn, end_ref)
    if start_frame is not None and end_frame is not None and end_frame <= start_frame:
        raise ValidationError(
            "Timeline item delete end frame must be after start frame.",
            details={"start_frame": start_ref, "end_frame": end_ref, "resolved_start_frame": start_frame, "resolved_end_frame": end_frame},
            recoverability="not_applicable",
        )

    filters = _timeline_items_delete_filters(
        timeline_name=target_timeline,
        track_type=normalized_track_type,
        track_index=normalized_track_index,
        start_ref=start_ref,
        end_ref=end_ref,
        start_frame=start_frame,
        end_frame=end_frame,
        match=normalized_match,
        allow_empty=allow_empty,
        force=force,
    )
    if normalized_targets is not None:
        filters = {"timeline": target_timeline, "exact_targets": normalized_targets}

    selected_items = _collect_exact_timeline_item_delete_targets(conn, normalized_targets) if normalized_targets is not None else _collect_timeline_items_matching_filter(
        conn, track_type=normalized_track_type, track_index=normalized_track_index,
        start_frame=start_frame, end_frame=end_frame, match=normalized_match,
    )
    deleted_items = [
        _timeline_item_descriptor(item, current_track_type, current_track_index)
        for item, current_track_type, current_track_index in selected_items
    ]

    if not selected_items:
        if allow_empty:
            set_verification_status("verified")
            set_recoverability("not_applicable")
            return {
                "action": "timeline.items.delete",
                "changed": False,
                "target": {"kind": "timeline", "name": target_timeline},
                "filters": filters,
                "deleted_count": 0,
                "deleted_items": [],
                "readback": {"remaining_count": 0, "remaining_items": [], "verified": True},
                "api_result": None,
                "message": "No timeline items matched the delete filters.",
            }
        raise ValidationError(
            "No timeline items matched the delete filters.",
            details={"filters": filters},
        )

    delete_result = _delete_clips_no_ripple(conn.timeline, [item for item, _track_type, _track_index in selected_items])
    save_project = getattr(getattr(conn, "project_manager", None), "SaveProject", None)
    if not callable(save_project):
        raise APICallFailed(
            "DaVinci Resolve cannot durably save the timeline item deletion.",
            details={"required_api": "ProjectManager.SaveProject", "mutation_may_have_occurred": True},
        )
    try:
        save_result = save_project()
    except Exception as exc:
        raise APICallFailed(
            "DaVinci Resolve failed to save the timeline item deletion.",
            details={"required_api": "ProjectManager.SaveProject", "mutation_may_have_occurred": True, "error": str(exc)},
        ) from exc
    if save_result is not True:
        raise APICallFailed(
            "DaVinci Resolve did not confirm the timeline item deletion save.",
            details={"required_api": "ProjectManager.SaveProject", "mutation_may_have_occurred": True, "save_result": save_result},
        )
    if normalized_targets is not None:
        remaining_items = []
        for target in normalized_targets:
            try:
                remaining_items.extend(_collect_exact_timeline_item_delete_targets(conn, [target]))
            except ValidationError as error:
                if error.details.get("match_count") not in {0, None}:
                    raise
    else:
        remaining_items = _collect_timeline_items_matching_filter(
            conn, track_type=normalized_track_type, track_index=normalized_track_index,
            start_frame=start_frame, end_frame=end_frame, match=normalized_match,
        )
    remaining_descriptors = [
        _timeline_item_descriptor(item, current_track_type, current_track_index)
        for item, current_track_type, current_track_index in remaining_items
    ]
    verified = len(remaining_items) == 0
    if delete_result.get("api_result") is False and not verified:
        set_verification_status("failed")
        raise APICallFailed(
            "DaVinci Resolve rejected timeline item deletion.",
            details={
                "filters": filters,
                "deleted_items": deleted_items,
                "readback": {"remaining_count": len(remaining_items), "remaining_items": remaining_descriptors, "verified": False},
                **delete_result,
            },
        )
    if not verified:
        set_verification_status("failed")
        raise APICallFailed(
            "Timeline item deletion could not be verified after readback.",
            details={
                "filters": filters,
                "deleted_items": deleted_items,
                "readback": {"remaining_count": len(remaining_items), "remaining_items": remaining_descriptors, "verified": False},
                **delete_result,
            },
        )

    set_verification_status("verified")
    set_recoverability("not_applicable")
    return {
        "action": "timeline.items.delete",
        "changed": True,
        "target": {"kind": "timeline", "name": target_timeline},
        "filters": filters,
        "deleted_count": len(deleted_items),
        "deleted_items": deleted_items,
        "readback": {"remaining_count": 0, "remaining_items": [], "verified": True},
        **delete_result,
        "message": f"Deleted {len(deleted_items)} timeline item(s).",
    }


def _collect_timeline_items_in_range(
    conn,
    *,
    start_frame: int,
    end_frame: int,
    track_type: str = "all",
    track_index: int = 0,
) -> List[tuple[Any, str, int]]:
    """Collect timeline items overlapping the given record-domain range."""
    normalized_track_type = str(track_type).strip().lower()
    if normalized_track_type not in {"video", "audio", "subtitle", "all"}:
        raise ValidationError(
            "Track type must be one of: video, audio, subtitle, all.",
            details={"track_type": track_type},
        )
    types_to_search = ["video", "audio", "subtitle"] if normalized_track_type == "all" else [normalized_track_type]
    candidate_ranges = {(int(start_frame), int(end_frame))}
    try:
        timeline_start = int(getattr(conn, "start_frame", 0) or 0)
    except Exception:
        timeline_start = 0
    if timeline_start == 0 and hasattr(conn.timeline, "GetStartFrame"):
        try:
            timeline_start = int(conn.timeline.GetStartFrame())
        except Exception:
            timeline_start = 0
    if timeline_start:
        candidate_ranges.add((int(start_frame) - timeline_start, int(end_frame) - timeline_start))

    rows: List[tuple[Any, str, int]] = []
    for current_type in types_to_search:
        count = conn.timeline.GetTrackCount(current_type) or 0
        start_idx = track_index if track_index else 1
        end_idx = (track_index + 1) if track_index else (count + 1)
        for idx in range(start_idx, end_idx):
            items = conn.timeline.GetItemListInTrack(current_type, idx) or []
            for item in items:
                try:
                    item_start = int(item.GetStart())
                    item_end = int(item.GetEnd())
                except Exception:
                    continue
                if any(item_start < candidate_end and item_end > candidate_start for candidate_start, candidate_end in candidate_ranges):
                    rows.append((item, current_type, idx))
    return rows


def _timeline_item_descriptor(item: Any, track_type: str, track_index: int) -> Dict[str, Any]:
    """Serialize a timeline item for command output."""
    data: Dict[str, Any] = {
        "track_type": track_type,
        "track_index": track_index,
    }
    if hasattr(item, "GetName"):
        try:
            data["name"] = item.GetName()
        except Exception:
            pass
    if hasattr(item, "GetStart"):
        try:
            data["start"] = int(item.GetStart())
        except Exception:
            pass
    if hasattr(item, "GetEnd"):
        try:
            data["end"] = int(item.GetEnd())
        except Exception:
            pass
    if hasattr(item, "GetDuration"):
        try:
            data["duration"] = int(item.GetDuration())
        except Exception:
            pass
    return data


def duplicate_timeline(conn, new_name: str, source_name: Optional[str] = None) -> Dict[str, Any]:
    """Duplicate a timeline with native API and verified DRT fallback routes."""
    from .timeline_duplicate import duplicate_timeline as duplicate_timeline_verified

    return duplicate_timeline_verified(conn, new_name=new_name, source_name=source_name)


def create_compound_clip(
    conn,
    *,
    in_ref: str,
    out_ref: str,
    track_type: str = "all",
    track_index: int = 0,
    name: Optional[str] = None,
    start_tc: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a compound clip from timeline items overlapping a record-domain range."""
    start_frame = parse_record_frame(in_ref, conn.fps, conn.start_frame)
    end_frame = parse_record_frame(out_ref, conn.fps, conn.start_frame)
    if end_frame <= start_frame:
        raise ValidationError(
            "Compound clip out must be after in.",
            details={"in": in_ref, "out": out_ref},
        )

    selected_items = _collect_timeline_items_in_range(
        conn,
        start_frame=start_frame,
        end_frame=end_frame,
        track_type=track_type,
        track_index=track_index,
    )
    if not selected_items:
        raise ValidationError(
            "No timeline items overlap the requested range.",
            details={"in": in_ref, "out": out_ref, "track_type": track_type, "track_index": track_index},
        )

    clip_info: Dict[str, Any] = {}
    if name:
        clip_info["name"] = name
    if start_tc:
        clip_info["startTimecode"] = start_tc

    creator = require_api_method(
        conn.timeline,
        "CreateCompoundClip",
        capability_id="timeline.compound_clip",
        runtime_object="timeline",
    )
    input_items = [item for item, _track_type, _track_index in selected_items]
    result = creator(input_items, clip_info) if clip_info else creator(input_items)
    if not result:
        raise APICallFailed(
            "Failed to create compound clip.",
            details={
                "in": in_ref,
                "out": out_ref,
                "track_type": track_type,
                "track_index": track_index,
                "clip_info": clip_info,
            },
        )

    created_track_type = None
    created_track_index = None
    if hasattr(result, "GetTrackTypeAndIndex"):
        try:
            created_track_type, created_track_index = result.GetTrackTypeAndIndex()
        except Exception:
            created_track_type, created_track_index = None, None

    return {
        "created": _timeline_item_descriptor(result, created_track_type or "video", created_track_index or 0),
        "input_count": len(selected_items),
        "input_items": [
            _timeline_item_descriptor(item, current_track_type, current_track_index)
            for item, current_track_type, current_track_index in selected_items
        ],
        "range": {
            "in": in_ref,
            "out": out_ref,
            "start_frame": start_frame,
            "end_frame": end_frame,
        },
        "clip_info": clip_info,
    }


def grab_still(conn, output_path: Optional[str] = None) -> dict[str, Any]:
    """Grab still via timeline API or export current frame if output path is provided."""
    if output_path:
        ok = conn.project.ExportCurrentFrameAsStill(output_path)
        if not ok:
            raise APICallFailed(
                "Failed to export current frame as still.",
                details={"output_path": output_path},
            )
        return {"output_path": output_path, "mode": "export_current_frame"}

    grab = require_api_method(
        conn.timeline,
        "GrabStill",
        capability_id="timeline.grab_still",
        runtime_object="timeline",
    )
    result = grab()
    if result is False:
        raise APICallFailed("GrabStill returned False.")
    return {"mode": "grab_still", "result": bool(result)}


def _validate_timeline_timecode(value: str, fps: float) -> str:
    raw = str(value or "").strip()
    parts = raw.replace(";", ":").split(":")
    if len(parts) != 4 or any(not part.isdigit() for part in parts):
        raise ValidationError(
            "Timeline start timecode must use HH:MM:SS:FF.",
            details={"timecode": value, "expected_format": "HH:MM:SS:FF"},
            recoverability="not_applicable",
        )
    hours, minutes, seconds, frames = (int(part) for part in parts)
    nominal_fps = max(1, round(float(fps)))
    if minutes > 59 or seconds > 59 or frames >= nominal_fps:
        raise ValidationError(
            "Timeline start timecode contains out-of-range fields.",
            details={
                "timecode": value,
                "hours": hours,
                "minutes": minutes,
                "seconds": seconds,
                "frames": frames,
                "frame_max_exclusive": nominal_fps,
            },
            recoverability="not_applicable",
        )
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}:{frames:02d}"


def set_start_timecode(conn, timecode: str, *, return_details: bool = False) -> str | Dict[str, Any]:
    """Set timeline start timecode."""
    requested_tc = _validate_timeline_timecode(timecode, conn.fps)
    setter = require_api_method(
        conn.timeline,
        "SetStartTimecode",
        capability_id="timeline.set_start_tc",
        runtime_object="timeline",
    )
    getter = getattr(conn.timeline, "GetStartTimecode", None)
    before_tc = getter() if callable(getter) else None
    if before_tc == requested_tc:
        set_verification_status("verified")
        set_recoverability("not_applicable")
        details = {
            "requested_tc": requested_tc,
            "pre_tc": before_tc,
            "final_tc": before_tc,
            "api_result": None,
            "changed": False,
            "verified": True,
        }
        return details if return_details else before_tc

    ok = setter(requested_tc)
    final_tc = getter() if callable(getter) else requested_tc
    if ok is False:
        if final_tc == requested_tc:
            set_verification_status("verified")
            set_recoverability("not_applicable")
            details = {
                "requested_tc": requested_tc,
                "pre_tc": before_tc,
                "final_tc": final_tc,
                "api_result": False,
                "changed": before_tc != final_tc,
                "verified": True,
            }
            return details if return_details else final_tc
        set_verification_status("failed")
        raise APICallFailed(
            "DaVinci Resolve rejected timeline start timecode.",
            details={
                "timecode": timecode,
                "requested_tc": requested_tc,
                "pre_tc": before_tc,
                "actual_tc": final_tc,
                "api_result": False,
                "api_call": "Timeline.SetStartTimecode",
            },
        )
    if final_tc != requested_tc:
        set_verification_status("failed")
        raise APICallFailed(
            "Timeline start timecode did not verify after setting.",
            details={
                "timecode": timecode,
                "requested_tc": requested_tc,
                "pre_tc": before_tc,
                "actual_tc": final_tc,
                "api_result": ok,
                "api_call": "Timeline.SetStartTimecode",
            },
        )
    set_verification_status("verified")
    set_recoverability("not_applicable")
    details = {
        "requested_tc": requested_tc,
        "pre_tc": before_tc,
        "final_tc": final_tc,
        "api_result": ok,
        "changed": before_tc != final_tc,
        "verified": True,
    }
    return details if return_details else final_tc


def _timeline_item_summary(item, asset_name: str, asset_type: str, method_name: str) -> Dict[str, Any]:
    data: Dict[str, Any] = {
        "asset_name": asset_name,
        "asset_type": asset_type,
        "method": method_name,
    }
    if not item:
        data["inserted"] = False
        return data
    data["inserted"] = True
    if hasattr(item, "GetName"):
        try:
            data["clip_name"] = item.GetName()
        except Exception:
            pass
    if hasattr(item, "GetTrackTypeAndIndex"):
        try:
            track_type, track_index = item.GetTrackTypeAndIndex()
            data["track_type"] = track_type
            data["track_index"] = track_index
        except Exception:
            pass
    if hasattr(item, "GetStart"):
        try:
            data["start"] = int(item.GetStart())
        except Exception:
            pass
    if hasattr(item, "GetEnd"):
        try:
            data["end"] = int(item.GetEnd())
        except Exception:
            pass
    if hasattr(item, "GetDuration"):
        try:
            data["duration"] = int(item.GetDuration())
        except Exception:
            pass
    return data


def _timeline_item_matches_summary(item: Any, summary: Dict[str, Any]) -> bool:
    """Return True when a timeline readback item matches the inserted API item."""
    checks = []
    if "clip_name" in summary and hasattr(item, "GetName"):
        try:
            checks.append(item.GetName() == summary["clip_name"])
        except Exception:
            checks.append(False)
    if "start" in summary and hasattr(item, "GetStart"):
        try:
            checks.append(int(item.GetStart()) == summary["start"])
        except Exception:
            checks.append(False)
    if "end" in summary and hasattr(item, "GetEnd"):
        try:
            checks.append(int(item.GetEnd()) == summary["end"])
        except Exception:
            checks.append(False)
    if "duration" in summary and hasattr(item, "GetDuration"):
        try:
            checks.append(int(item.GetDuration()) == summary["duration"])
        except Exception:
            checks.append(False)

    return bool(checks) and all(checks)


def _verify_timeline_item_inserted(conn, summary: Dict[str, Any]) -> Dict[str, Any]:
    """Verify an inserted generator/title is visible in the timeline item list."""
    track_type = str(summary.get("track_type") or "video").lower()
    track_index = int(summary.get("track_index") or 1)
    readback_error = None

    for attempt in range(1, 7):
        try:
            items = conn.timeline.GetItemListInTrack(track_type, track_index) or []
        except Exception as exc:
            readback_error = str(exc)
            items = []

        for item in items:
            if _timeline_item_matches_summary(item, summary):
                summary["verification_status"] = "verified"
                set_verification_status("verified")
                return summary

        if attempt < 6:
            refresh = getattr(conn, "refresh", None)
            if callable(refresh):
                try:
                    refresh()
                except Exception:
                    pass
            time.sleep(0.1)

    details = {
        "asset_name": summary.get("asset_name"),
        "asset_type": summary.get("asset_type"),
        "method": summary.get("method"),
        "track_type": track_type,
        "track_index": track_index,
        "expected": {
            key: summary[key]
            for key in ("clip_name", "start", "end", "duration")
            if key in summary
        },
    }
    if readback_error:
        details["readback_error"] = readback_error
    raise APICallFailed(
        "Inserted timeline item was not visible in timeline readback.",
        details=details,
    )


def insert_generator(conn, name: str, *, fusion: bool = False, ofx: bool = False) -> Dict[str, Any]:
    """Insert a generator at the current playhead position."""
    if fusion and ofx:
        raise ValidationError(
            "Choose either fusion or ofx generator mode, not both.",
            details={"fusion": fusion, "ofx": ofx},
        )
    method_name = "InsertGeneratorIntoTimeline"
    asset_type = "generator"
    if fusion:
        method_name = "InsertFusionGeneratorIntoTimeline"
        asset_type = "fusion_generator"
    elif ofx:
        method_name = "InsertOFXGeneratorIntoTimeline"
        asset_type = "ofx_generator"

    inserter = require_api_method(
        conn.timeline,
        method_name,
        capability_id="timeline.insert_generator",
        runtime_object="timeline",
    )
    item = inserter(name)
    if not item:
        raise APICallFailed(
            "Failed to insert generator into timeline.",
            details={"name": name, "method": method_name},
        )
    summary = _timeline_item_summary(item, name, asset_type, method_name)
    return _verify_timeline_item_inserted(conn, summary)


def insert_title(conn, name: str, *, fusion: bool = False) -> Dict[str, Any]:
    """Insert a title at the current playhead position."""
    method_name = "InsertFusionTitleIntoTimeline" if fusion else "InsertTitleIntoTimeline"
    asset_type = "fusion_title" if fusion else "title"
    inserter = require_api_method(
        conn.timeline,
        method_name,
        capability_id="timeline.insert_title",
        runtime_object="timeline",
    )
    item = inserter(name)
    if not item:
        raise APICallFailed(
            "Failed to insert title into timeline.",
            details={"name": name, "method": method_name},
        )
    summary = _timeline_item_summary(item, name, asset_type, method_name)
    return _verify_timeline_item_inserted(conn, summary)


def get_item_at(
    conn,
    position: str,
    track_type: str = "video",
    track_index: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Find timeline item(s) that cover the specified record-domain position."""
    normalized_track_type = normalize_item_at_track_type(track_type)
    frame = parse_record_frame(position, conn.fps, conn.start_frame)
    types = [normalized_track_type] if normalized_track_type != "all" else ["video", "audio", "subtitle"]
    rows: List[Dict[str, Any]] = []

    for ttype in types:
        indices = [track_index] if track_index is not None else list(range(1, (conn.timeline.GetTrackCount(ttype) or 0) + 1))
        for idx in indices:
            if idx is None:
                continue
            items = conn.timeline.GetItemListInTrack(ttype, idx) or []
            for item in items:
                try:
                    start = int(item.GetStart())
                    end = int(item.GetEnd())
                except Exception:
                    continue
                if start <= frame < end:
                    rows.append(
                        {
                            "track_type": ttype,
                            "track_index": idx,
                            "name": item.GetName() if hasattr(item, "GetName") else "",
                            "start": start,
                            "end": end,
                            "duration": max(0, end - start),
                            "position": frame,
                        }
                    )
    return rows


def normalize_item_at_track_type(track_type: str) -> str:
    normalized = str(track_type or "").strip().lower()
    allowed = {"video", "audio", "subtitle", "all"}
    if normalized not in allowed:
        raise ValidationError(
            "Track type must be one of: video, audio, subtitle, all.",
            details={"track_type": track_type, "allowed_track_types": sorted(allowed)},
            recoverability="not_applicable",
        )
    return normalized


def _extract_subtitle_text(item: Any) -> str:
    """Best-effort subtitle text extraction from timeline item."""
    for key in ("Text", "StyledText", "SubTitle", "Subtitle"):
        try:
            val = item.GetProperty(key)
            if val:
                try:
                    coerced = str(val)
                except Exception:
                    coerced = ""
                if isinstance(coerced, str) and coerced:
                    return coerced
        except Exception:
            continue
    if hasattr(item, "GetName"):
        try:
            name = item.GetName()
            if not name:
                return ""
            coerced = str(name)
            return coerced if isinstance(coerced, str) else ""
        except Exception:
            pass
    return ""


def _subtitle_frame(item: Any, getter_name: str, *, default: int = 0) -> int:
    """Best-effort integer frame extraction from subtitle items."""
    getter = getattr(item, getter_name, None)
    if getter is None:
        return default
    try:
        value = getter()
    except Exception:
        return default
    try:
        return int(value)
    except Exception:
        return default


def list_subtitles(conn, track: Optional[int] = None) -> List[Dict[str, Any]]:
    """List subtitle clips from subtitle tracks."""
    tracks = [track] if track is not None else list(range(1, (conn.timeline.GetTrackCount("subtitle") or 0) + 1))
    rows: List[Dict[str, Any]] = []
    for idx in tracks:
        if idx is None:
            continue
        items = conn.timeline.GetItemListInTrack("subtitle", idx) or []
        for item in items:
            start = _subtitle_frame(item, "GetStart", default=0)
            end = _subtitle_frame(item, "GetEnd", default=start)
            rows.append(
                {
                    "track": idx,
                    "start_frame": start,
                    "end_frame": end,
                    "start_tc": seconds_to_timecode(frames_to_seconds(max(0, start - conn.start_frame), conn.fps), conn.fps),
                    "end_tc": seconds_to_timecode(frames_to_seconds(max(0, end - conn.start_frame), conn.fps), conn.fps),
                    "text": _extract_subtitle_text(item),
                }
            )
    rows.sort(key=lambda r: (r["track"], r["start_frame"]))
    return rows


def _frame_to_srt_timestamp(frame: int, fps: float) -> str:
    seconds = max(0.0, frames_to_seconds(frame, fps))
    hh = int(seconds // 3600)
    mm = int((seconds % 3600) // 60)
    ss = int(seconds % 60)
    ms = int(round((seconds - int(seconds)) * 1000))
    return f"{hh:02d}:{mm:02d}:{ss:02d},{ms:03d}"


def _frame_to_vtt_timestamp(frame: int, fps: float) -> str:
    return _frame_to_srt_timestamp(frame, fps).replace(",", ".")
