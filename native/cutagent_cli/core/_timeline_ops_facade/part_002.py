from __future__ import annotations

def resolve_playhead_target(conn, position: str) -> Dict[str, Any]:
    """Resolve a record-domain playhead reference without mutating DaVinci Resolve."""
    from ..utils.time_ref import parse_record_frame
    from ..utils.frame_math import parse_frame_quantity, format_frame_timecode

    try:
        start_frame = int(conn.timeline.GetStartFrame())
    except Exception:
        start_frame = int(getattr(conn, "start_frame", 0) or 0)

    pos = str(position).strip()
    if ":" in pos or ";" in pos:
        label = pos + ":00" if ";" not in pos and pos.count(":") == 2 else pos
        absolute_frame = parse_frame_quantity(label, conn.fps, field="position", allow_signed=False)
        target_frame = absolute_frame if absolute_frame >= start_frame else start_frame + absolute_frame
    else:
        target_frame = parse_record_frame(pos, conn.fps, start_frame)
    get_current_timecode = getattr(conn.timeline, "GetCurrentTimecode", None)
    current_tc = get_current_timecode() if callable(get_current_timecode) else None
    if not current_tc:
        get_start_timecode = getattr(conn.timeline, "GetStartTimecode", None)
        current_tc = get_start_timecode() if callable(get_start_timecode) else None
    return {
        "position": position,
        "start_frame": start_frame,
        "target_frame": int(target_frame),
        "target_tc": format_frame_timecode(int(target_frame), conn.fps, drop_frame=";" in str(current_tc or "")),
    }


def set_playhead(
    conn,
    position: str,
    *,
    return_details: bool = False,
    frame_tolerance: int = 1,
) -> str | Dict[str, Any]:
    """
    Set playhead position.

    Args:
        conn: ResolveConnection instance
        position: Position as timecode, seconds (90.5s), or frames (2250f)

    Returns:
        Final timecode after setting
    """
    from ..utils.frame_math import parse_frame_quantity

    target = resolve_playhead_target(conn, position)
    target_frame = int(target["target_frame"])
    target_tc = str(target["target_tc"])
    tolerance = max(0, int(frame_tolerance))

    before = get_playhead(conn)
    before_frame = before.get("frame")
    before_tc = before.get("timecode")
    if before_frame is not None and abs(int(before_frame) - target_frame) <= tolerance:
        set_verification_status("verified")
        set_recoverability("not_applicable")
        details = {
            "position": position,
            "target_frame": target_frame,
            "target_tc": target_tc,
            "pre_tc": before_tc,
            "pre_frame": before_frame,
            "final_tc": before_tc,
            "final_frame": before_frame,
            "api_result": None,
            "changed": False,
            "verified": True,
        }
        return details if return_details else str(before_tc)

    result = conn.timeline.SetCurrentTimecode(target_tc)
    if result is False:
        actual = get_playhead(conn)
        actual_frame = actual.get("frame")
        actual_tc = actual.get("timecode")
        if actual_frame is not None and abs(int(actual_frame) - target_frame) <= tolerance:
            set_verification_status("verified")
            set_recoverability("not_applicable")
            details = {
                "position": position,
                "target_frame": target_frame,
                "target_tc": target_tc,
                "pre_tc": before_tc,
                "pre_frame": before_frame,
                "final_tc": actual_tc,
                "final_frame": actual_frame,
                "api_result": False,
                "changed": before_frame != actual_frame,
                "verified": True,
            }
            return details if return_details else str(actual_tc)
        set_verification_status("failed")
        raise APICallFailed(
            "DaVinci Resolve rejected the playhead move.",
            details={
                "position": position,
                "target_frame": target_frame,
                "target_tc": target_tc,
                "pre_tc": before_tc,
                "pre_frame": before_frame,
                "actual_tc": actual_tc,
                "actual_frame": actual_frame,
                "api_result": False,
                "api_call": "Timeline.SetCurrentTimecode",
            },
        )

    # Wait for playhead to settle (DaVinci Resolve is sometimes slow)
    timeout = 1.0
    start = time.time()
    current_frame = None
    while time.time() - start < timeout:
        current_tc = conn.timeline.GetCurrentTimecode()
        if current_tc:
            current_frame = parse_frame_quantity(current_tc, conn.fps, field="timecode", allow_signed=False)
            if abs(current_frame - target_frame) <= tolerance:
                break
        time.sleep(0.05)

    final_tc = conn.timeline.GetCurrentTimecode()
    if not final_tc:
        set_verification_status("failed")
        raise APICallFailed(
            "Playhead position could not be verified after setting.",
            details={
                "position": position,
                "target_frame": target_frame,
                "target_tc": target_tc,
                "pre_tc": before_tc,
                "pre_frame": before_frame,
                "api_result": result,
                "api_call": "Timeline.SetCurrentTimecode",
            },
        )
    final_frame = parse_frame_quantity(final_tc, conn.fps, field="timecode", allow_signed=False)
    if abs(final_frame - target_frame) > tolerance:
        set_verification_status("failed")
        raise APICallFailed(
            "Playhead did not move to the requested position.",
            details={
                "position": position,
                "target_frame": target_frame,
                "target_tc": target_tc,
                "pre_tc": before_tc,
                "pre_frame": before_frame,
                "actual_frame": final_frame,
                "actual_tc": final_tc,
                "api_result": result,
                "api_call": "Timeline.SetCurrentTimecode",
            },
        )
    set_verification_status("verified")
    set_recoverability("not_applicable")
    details = {
        "position": position,
        "target_frame": target_frame,
        "target_tc": target_tc,
        "pre_tc": before_tc,
        "pre_frame": before_frame,
        "final_tc": final_tc,
        "final_frame": final_frame,
        "api_result": result,
        "changed": before_frame != final_frame,
        "verified": True,
    }
    return details if return_details else final_tc


# --- Marker operations ---

def _timeline_start_frame(conn) -> int:
    timeline = getattr(conn, "timeline", None)
    if timeline is not None and hasattr(timeline, "GetStartFrame"):
        try:
            return int(timeline.GetStartFrame())
        except Exception:
            pass
    return int(getattr(conn, "start_frame", 0) or 0)


def _read_timeline_marker_map(conn) -> Dict[int, Dict[str, Any]]:
    try:
        raw_markers = conn.timeline.GetMarkers() or {}
    except Exception as exc:
        raise APICallFailed("Failed to read timeline markers.", details={"error": str(exc)}) from exc

    markers: Dict[int, Dict[str, Any]] = {}
    for frame_id, marker_data in raw_markers.items():
        try:
            marker_frame = int(frame_id)
        except (TypeError, ValueError):
            continue
        markers[marker_frame] = dict(marker_data or {})
    return markers


def _record_frame_from_marker_position(conn, position: str) -> int:
    from ..utils.timecode import parse_time_input, seconds_to_frames, timecode_to_seconds

    start_frame = _timeline_start_frame(conn)
    pos = str(position).strip()
    if ":" in pos or ";" in pos:
        absolute_frame = seconds_to_frames(timecode_to_seconds(pos, conn.fps), conn.fps)
        return int(absolute_frame) if int(absolute_frame) >= start_frame else start_frame + int(absolute_frame)
    if pos.endswith("f"):
        return parse_record_frame(pos, conn.fps, start_frame)
    return start_frame + seconds_to_frames(parse_time_input(pos, conn.fps), conn.fps)


def _marker_timecodes(timeline_frame: int, record_frame: int, fps: float) -> Dict[str, str]:
    timeline_tc = seconds_to_timecode(frames_to_seconds(int(timeline_frame), fps), fps)
    record_tc = seconds_to_timecode(frames_to_seconds(int(record_frame), fps), fps)
    return {
        "timecode": timeline_tc,
        "timeline_timecode": timeline_tc,
        "record_timecode": record_tc,
    }


def _marker_custom_data(marker_data: Dict[str, Any]) -> Any:
    return marker_data.get("customData", marker_data.get("custom_data"))


def _normalized_marker_custom_data(marker_data: Dict[str, Any]) -> str:
    custom_data = _marker_custom_data(marker_data)
    if custom_data is None:
        return ""
    if not isinstance(custom_data, str) or len(custom_data) > 65_536:
        raise APICallFailed(
            "DaVinci Resolve returned invalid marker custom data.",
            details={"api_call": "Timeline.GetMarkers"},
        )
    return custom_data


def _marker_row(frame_id: int, marker_data: Dict[str, Any], *, start_frame: int, fps: float) -> Dict[str, Any]:
    timeline_frame = int(frame_id)
    record_frame = int(start_frame) + timeline_frame
    return {
        "frame": timeline_frame,
        "timeline_frame": timeline_frame,
        "record_frame": record_frame,
        **_marker_timecodes(timeline_frame, record_frame, fps),
        "color": marker_data.get("color", ""),
        "name": marker_data.get("name", ""),
        "note": marker_data.get("note", ""),
        "duration": marker_data.get("duration", 1),
        "custom_data": _normalized_marker_custom_data(marker_data),
    }


def _add_marker_with_custom_data(timeline, frame: int, marker_data: Dict[str, Any]) -> Any:
    args = (
        int(frame),
        marker_data.get("color", "Blue"),
        marker_data.get("name", ""),
        marker_data.get("note", ""),
        int(marker_data.get("duration", 1) or 1),
    )
    custom_data = _marker_custom_data(marker_data)
    if custom_data is None:
        return timeline.AddMarker(*args)
    return timeline.AddMarker(*args, _normalized_marker_custom_data(marker_data))


def _marker_values_match(readback: Dict[str, Any] | None, expected: Dict[str, Any]) -> bool:
    if not readback:
        return False
    return (
        readback.get("color", "") == expected.get("color", "Blue")
        and readback.get("name", "") == expected.get("name", "")
        and readback.get("note", "") == expected.get("note", "")
        and int(readback.get("duration", 1) or 1) == int(expected.get("duration", 1) or 1)
        and _normalized_marker_custom_data(readback) == _normalized_marker_custom_data(expected)
    )


def _marker_maps_match(readback: Dict[int, Dict[str, Any]], expected: Dict[int, Dict[str, Any]]) -> bool:
    return set(readback) == set(expected) and all(
        _marker_values_match(readback.get(frame), marker_data)
        for frame, marker_data in expected.items()
    )


def _delete_marker_frame_candidates(requested_frame: int, *, start_frame: int) -> List[int]:
    requested = int(requested_frame)
    candidates: List[int] = []
    if start_frame and requested >= int(start_frame):
        candidates.append(requested - int(start_frame))
    candidates.append(requested)

    unique: List[int] = []
    for candidate in candidates:
        if candidate < 0 or candidate in unique:
            continue
        unique.append(candidate)
    return unique


def list_markers(conn) -> List[Dict[str, Any]]:
    """
    List all timeline markers.
    
    Args:
        conn: ResolveConnection instance
    
    Returns:
        List of marker info dicts
    """
    markers = _read_timeline_marker_map(conn)
    if not markers:
        return []

    start_frame = _timeline_start_frame(conn)
    rows = []
    for frame_id, marker_data in sorted(markers.items()):
        rows.append(_marker_row(frame_id, marker_data, start_frame=start_frame, fps=conn.fps))

    return rows


def add_marker(
    conn,
    position: str,
    color: str = "Blue",
    name: str = "",
    note: str = "",
    duration: int = 1,
) -> bool:
    """
    Add a marker at a position.
    
    Args:
        conn: ResolveConnection instance
        position: Position as timecode, seconds, or frames
        color: Marker color
        name: Marker name
        note: Marker note
        duration: Duration in frames
    
    Returns:
        True if successful
    
    Raises:
        APICallFailed: If marker addition fails
    """
    if int(duration) < 1:
        raise ValidationError("Marker duration must be at least one frame.", recoverability="not_applicable")
    start_frame = _timeline_start_frame(conn)
    record_frame = _record_frame_from_marker_position(conn, position)
    timeline_frame = int(record_frame) - int(start_frame)
    if timeline_frame < 0:
        raise ValidationError(
            "Marker position is before the timeline start.",
            details={"position": position, "record_frame": record_frame, "timeline_start_frame": start_frame},
            recoverability="not_applicable",
        )

    result = conn.timeline.AddMarker(timeline_frame, color, name, note, duration)
    if not result:
        set_verification_status("failed")
        raise APICallFailed(
            "Failed to add marker. A marker may already exist at that frame.",
            details={
                "position": position,
                "timeline_frame": timeline_frame,
                "record_frame": record_frame,
                "api_call": "Timeline.AddMarker",
                "api_result": result,
            },
        )

    markers_after = _read_timeline_marker_map(conn)
    readback = markers_after.get(timeline_frame)
    verified = bool(
        readback
        and readback.get("color") == color
        and readback.get("name", "") == name
        and readback.get("note", "") == note
        and int(readback.get("duration", 1) or 1) == int(duration)
    )
    if not verified:
        set_verification_status("failed")
        raise APICallFailed(
            "Marker addition could not be verified by native readback.",
            details={
                "position": position,
                "timeline_frame": timeline_frame,
                "record_frame": record_frame,
                "expected": {"color": color, "name": name, "note": note, "duration": int(duration)},
                "readback": readback,
                "api_call": "Timeline.AddMarker",
                "api_result": result,
            },
        )

    set_verification_status("verified")
    set_recoverability("not_applicable")
    return {
        "position": position,
        "timeline_start_frame": start_frame,
        "timeline_frame": timeline_frame,
        "frame": timeline_frame,
        "record_frame": record_frame,
        **_marker_timecodes(timeline_frame, record_frame, conn.fps),
        "color": color,
        "name": name,
        "note": note,
        "duration": int(duration),
        "api_result": result,
        "verified": True,
        "readback": _marker_row(timeline_frame, readback, start_frame=start_frame, fps=conn.fps),
    }


def update_marker(
    conn,
    frame: int,
    *,
    position: Optional[str] = None,
    color: Optional[str] = None,
    name: Optional[str] = None,
    note: Optional[str] = None,
    duration: Optional[int] = None,
) -> Dict[str, Any]:
    """Replace one exact marker and restore the original if replacement fails."""
    from ..errors import EditMutationRecoveryFailed, EditMutationRestored

    start_frame = _timeline_start_frame(conn)
    markers_before = _read_timeline_marker_map(conn)
    candidates = _delete_marker_frame_candidates(int(frame), start_frame=start_frame)
    source_frame = next((candidate for candidate in candidates if candidate in markers_before), None)
    if source_frame is None:
        raise APICallFailed(
            f"No marker at frame {frame}.",
            details={"requested_frame": int(frame), "candidate_timeline_frames": candidates},
        )
    original = dict(markers_before[source_frame])
    target_record_frame = (
        _record_frame_from_marker_position(conn, position)
        if position is not None
        else start_frame + source_frame
    )
    target_frame = int(target_record_frame) - int(start_frame)
    replacement = {
        "color": original.get("color", "Blue") if color is None else color,
        "name": original.get("name", "") if name is None else name,
        "note": original.get("note", "") if note is None else note,
        "duration": int(original.get("duration", 1) or 1) if duration is None else int(duration),
        "customData": _marker_custom_data(original),
    }
    if target_frame < 0 or replacement["duration"] < 1:
        raise ValidationError("Updated marker position and duration must be valid.", recoverability="not_applicable")
    if target_frame != source_frame and target_frame in markers_before:
        raise ValidationError(
            "Another marker already exists at the requested position.",
            details={"timeline_frame": target_frame, "record_frame": target_record_frame},
            recoverability="not_applicable",
        )
    original_row = _marker_row(source_frame, original, start_frame=start_frame, fps=conn.fps)
    if target_frame == source_frame and _marker_values_match(original, replacement):
        set_verification_status("verified")
        set_recoverability("not_applicable")
        return {"changed": False, "previous": original_row, "readback": original_row, "verified": True}

    deleted = conn.timeline.DeleteMarkerAtFrame(source_frame)
    if not deleted:
        set_verification_status("failed")
        raise APICallFailed("Failed to remove the marker before updating it.", details={"timeline_frame": source_frame})
    added = _add_marker_with_custom_data(conn.timeline, target_frame, replacement)
    markers_after = _read_timeline_marker_map(conn)
    readback = markers_after.get(target_frame)
    replacement_matches = bool(added and _marker_values_match(readback, replacement))
    verified = replacement_matches and (source_frame == target_frame or source_frame not in markers_after)
    if not verified:
        if replacement_matches:
            conn.timeline.DeleteMarkerAtFrame(target_frame)
        if source_frame not in _read_timeline_marker_map(conn):
            _add_marker_with_custom_data(conn.timeline, source_frame, original)
        restored_markers = _read_timeline_marker_map(conn)
        restored_ok = _marker_maps_match(restored_markers, markers_before)
        set_verification_status("failed")
        error_details = {"source_timeline_frame": source_frame, "target_timeline_frame": target_frame, "readback": readback}
        if restored_ok:
            raise EditMutationRestored("Marker update failed and the original marker was restored.", details=error_details)
        raise EditMutationRecoveryFailed("Marker update failed and the original marker could not be restored.", details=error_details)

    set_verification_status("verified")
    set_recoverability("not_applicable")
    return {
        "changed": True,
        "previous": original_row,
        "timeline_start_frame": start_frame,
        "timeline_frame": target_frame,
        "record_frame": target_record_frame,
        **_marker_timecodes(target_frame, target_record_frame, conn.fps),
        "color": replacement["color"],
        "name": replacement["name"],
        "note": replacement["note"],
        "duration": replacement["duration"],
        "api_result": added,
        "verified": True,
        "readback": _marker_row(target_frame, readback, start_frame=start_frame, fps=conn.fps),
    }


def delete_marker(
    conn,
    frame: Optional[int] = None,
    color: Optional[str] = None,
    all_markers: bool = False,
) -> Dict[str, Any]:
    """
    Delete markers.
    
    Args:
        conn: ResolveConnection instance
        frame: Delete marker at specific frame
        color: Delete all markers of a color
        all_markers: Delete all markers
    
    Returns:
        Structured deletion result
    
    Raises:
        APICallFailed: If deletion fails
        ValueError: If no deletion criteria provided
    """
    start_frame = _timeline_start_frame(conn)
    if all_markers:
        markers_before = _read_timeline_marker_map(conn)
        result = conn.timeline.DeleteMarkersByColor("All")
        if not result:
            set_verification_status("failed")
            raise APICallFailed(
                "Failed to delete markers.",
                details={"mode": "all", "api_call": "Timeline.DeleteMarkersByColor", "api_result": result},
            )
        markers_after = _read_timeline_marker_map(conn)
        if markers_after:
            set_verification_status("failed")
            raise APICallFailed(
                "Marker deletion could not be verified by native readback.",
                details={
                    "mode": "all",
                    "marker_count_before": len(markers_before),
                    "marker_count_after": len(markers_after),
                    "remaining_frames": sorted(markers_after.keys()),
                    "api_call": "Timeline.DeleteMarkersByColor",
                    "api_result": result,
                },
            )
        set_verification_status("verified")
        set_recoverability("not_applicable")
        return {
            "mode": "all",
            "changed": bool(markers_before),
            "deleted": True,
            "deleted_count": len(markers_before),
            "marker_count_before": len(markers_before),
            "marker_count_after": len(markers_after),
            "api_result": result,
            "verified": True,
        }
    elif color:
        markers_before = _read_timeline_marker_map(conn)
        matching_before = {
            frame_id: marker
            for frame_id, marker in markers_before.items()
            if marker.get("color") == color
        }
        result = conn.timeline.DeleteMarkersByColor(color)
        if not result:
            set_verification_status("failed")
            raise APICallFailed(
                f"Failed to delete {color} markers.",
                details={"mode": "color", "color": color, "api_call": "Timeline.DeleteMarkersByColor", "api_result": result},
            )
        markers_after = _read_timeline_marker_map(conn)
        matching_after = {
            frame_id: marker
            for frame_id, marker in markers_after.items()
            if marker.get("color") == color
        }
        if matching_after:
            set_verification_status("failed")
            raise APICallFailed(
                "Marker deletion could not be verified by native readback.",
                details={
                    "mode": "color",
                    "color": color,
                    "matching_count_before": len(matching_before),
                    "matching_count_after": len(matching_after),
                    "remaining_frames": sorted(matching_after.keys()),
                    "api_call": "Timeline.DeleteMarkersByColor",
                    "api_result": result,
                },
            )
        set_verification_status("verified")
        set_recoverability("not_applicable")
        return {
            "mode": "color",
            "color": color,
            "changed": bool(matching_before),
            "deleted": True,
            "deleted_count": len(matching_before),
            "marker_count_before": len(markers_before),
            "marker_count_after": len(markers_after),
            "api_result": result,
            "verified": True,
        }
    elif frame is not None:
        requested_frame = int(frame)
        markers_before = _read_timeline_marker_map(conn)
        candidate_frames = _delete_marker_frame_candidates(requested_frame, start_frame=start_frame)
        timeline_frame = next((candidate for candidate in candidate_frames if candidate in markers_before), None)
        if timeline_frame is None:
            available_frames = sorted(markers_before.keys())
            raise APICallFailed(
                f"No marker at frame {frame}.",
                details={
                    "requested_frame": requested_frame,
                    "candidate_timeline_frames": candidate_frames,
                    "timeline_start_frame": start_frame,
                    "available_timeline_frames": available_frames,
                    "available_record_frames": [start_frame + value for value in available_frames],
                },
            )

        marker_before = dict(markers_before[timeline_frame])
        result = conn.timeline.DeleteMarkerAtFrame(timeline_frame)
        if not result:
            set_verification_status("failed")
            raise APICallFailed(
                f"No marker at frame {frame}.",
                details={
                    "requested_frame": requested_frame,
                    "timeline_frame": timeline_frame,
                    "record_frame": start_frame + timeline_frame,
                    "candidate_timeline_frames": candidate_frames,
                    "api_call": "Timeline.DeleteMarkerAtFrame",
                    "api_result": result,
                },
            )
        markers_after = _read_timeline_marker_map(conn)
        if timeline_frame in markers_after:
            set_verification_status("failed")
            raise APICallFailed(
                "Marker deletion could not be verified by native readback.",
                details={
                    "requested_frame": requested_frame,
                    "timeline_frame": timeline_frame,
                    "record_frame": start_frame + timeline_frame,
                    "candidate_timeline_frames": candidate_frames,
                    "api_call": "Timeline.DeleteMarkerAtFrame",
                    "api_result": result,
                    "readback": markers_after.get(timeline_frame),
                },
            )
        set_verification_status("verified")
        set_recoverability("not_applicable")
        return {
            "mode": "frame",
            "changed": True,
            "deleted": True,
            "requested_frame": requested_frame,
            "candidate_timeline_frames": candidate_frames,
            "timeline_start_frame": start_frame,
            "timeline_frame": timeline_frame,
            "frame": timeline_frame,
            "record_frame": start_frame + timeline_frame,
            **_marker_timecodes(timeline_frame, start_frame + timeline_frame, conn.fps),
            "marker": _marker_row(timeline_frame, marker_before, start_frame=start_frame, fps=conn.fps),
            "marker_count_before": len(markers_before),
            "marker_count_after": len(markers_after),
            "api_result": result,
            "verified": True,
        }
    else:
        raise MissingArgumentError("Provide frame, color, or all_markers=True.")


# --- Track operations ---

def list_tracks(conn, *, authoritative_state: bool = False) -> List[Dict[str, Any]]:
    """
    List all tracks.
    
    Args:
        conn: ResolveConnection instance
    
    Returns:
        List of track info dicts
    """
    rows = []
    for track_type in ("video", "audio", "subtitle"):
        count = conn.timeline.GetTrackCount(track_type) or 0
        for i in range(1, count + 1):
            name = conn.timeline.GetTrackName(track_type, i)
            items = conn.timeline.GetItemListInTrack(track_type, i) or []
            enabled = None
            try:
                enabled = conn.timeline.GetIsTrackEnabled(track_type, i)
            except Exception:
                pass
            locked = None
            try:
                locked = conn.timeline.GetIsTrackLocked(track_type, i)
            except Exception:
                pass
            rows.append({
                "type": track_type,
                "index": i,
                "name": name or "",
                "items": len(items),
                "enabled": enabled if authoritative_state else None if enabled is None else "✓" if enabled else "✗",
                "locked": locked if authoritative_state else None if locked is None else "🔒" if locked else "",
            })

    return rows


def add_track(conn, track_type: str, subtype: Optional[str] = None, index: Optional[int] = None) -> bool:
    """
    Add a new track.
    
    Args:
        conn: ResolveConnection instance
        track_type: Track type (video, audio, subtitle)
    
    Returns:
        True if successful
    
    Raises:
        APICallFailed: If track addition fails
        ValidationError: If invalid track type
    """
    valid = ("video", "audio", "subtitle")
    if track_type.lower() not in valid:
        raise ValidationError(
            f"Must be one of: {', '.join(valid)}",
            details={"track_type": track_type, "allowed_track_types": list(valid)},
        )

    normalized_type = track_type.lower()
    options: dict[str, Any] = {}
    if subtype is not None:
        if normalized_type == "audio":
            options["audioType"] = subtype
        else:
            options["subType"] = subtype
    if index is not None:
        options["index"] = int(index)
    try:
        if options:
            result = conn.timeline.AddTrack(normalized_type, options)
        else:
            result = conn.timeline.AddTrack(normalized_type)
    except TypeError:
        if subtype is not None or index is not None:
            raise CapabilityNegotiationFailed(
                "This DaVinci Resolve scripting API does not support AddTrack subtype/index options.",
                details={"track_type": track_type, "subtype": subtype, "index": index},
            )
        result = conn.timeline.AddTrack(normalized_type)
    if result:
        return True
    else:
        raise APICallFailed(f"Failed to add {track_type} track.")


def delete_track(conn, track_type: str, index: int) -> Dict[str, Any]:
    """Delete a timeline track."""
    deleter = getattr(conn.timeline, "DeleteTrack", None)
    if not callable(deleter):
        raise APICallFailed("DeleteTrack not available.")
    result = deleter(track_type.lower(), int(index))
    if result is False:
        raise APICallFailed("Failed to delete track.", details={"track_type": track_type, "index": index})
    return {"track_type": track_type.lower(), "index": int(index), "deleted": bool(result)}


def get_track_subtype(conn, track_type: str, index: int) -> Dict[str, Any]:
    """Return a track subtype when DaVinci Resolve exposes it."""
    getter = getattr(conn.timeline, "GetTrackSubType", None) or getattr(conn.timeline, "GetTrackSubtype", None)
    if not callable(getter):
        raise APICallFailed("GetTrackSubType not available.")
    subtype = getter(track_type.lower(), int(index))
    return {"track_type": track_type.lower(), "index": int(index), "subtype": subtype}


def rename_track(conn, track_type: str, index: int, name: str) -> bool:
    """
    Rename a track.
    
    Args:
        conn: ResolveConnection instance
        track_type: Track type
        index: Track index
        name: New name
    
    Returns:
        True if successful
    
    Raises:
        APICallFailed: If rename fails
    """
    result = conn.timeline.SetTrackName(track_type.lower(), index, name)
    if result:
        return True
    else:
        raise APICallFailed("Failed to rename track.")


VALID_TIMELINE_TRACK_TYPES = ("video", "audio", "subtitle")
VALID_TIMELINE_ITEM_TRACK_TYPES = ("video", "audio", "subtitle", "all")
VALID_TIMELINE_ITEM_DELETE_MATCHES = ("overlap", "contained", "covering")


def normalize_timeline_track_type(track_type: str) -> str:
    normalized = str(track_type or "").strip().lower()
    if normalized not in VALID_TIMELINE_TRACK_TYPES:
        raise ValidationError(
            "Track type must be one of: video, audio, subtitle.",
            details={
                "track_type": track_type,
                "allowed_track_types": list(VALID_TIMELINE_TRACK_TYPES),
            },
            recoverability="not_applicable",
        )
    return normalized


def normalize_timeline_item_track_type(track_type: str) -> str:
    normalized = str(track_type or "").strip().lower()
    if normalized not in VALID_TIMELINE_ITEM_TRACK_TYPES:
        raise ValidationError(
            "Track type must be one of: video, audio, subtitle, all.",
            details={
                "track_type": track_type,
                "allowed_track_types": list(VALID_TIMELINE_ITEM_TRACK_TYPES),
            },
            recoverability="not_applicable",
        )
    return normalized


def normalize_timeline_item_delete_match(match: str) -> str:
    normalized = str(match or "").strip().lower()
    if normalized not in VALID_TIMELINE_ITEM_DELETE_MATCHES:
        raise ValidationError(
            "Timeline item delete match must be one of: overlap, contained, covering.",
            details={
                "match": match,
                "allowed_matches": list(VALID_TIMELINE_ITEM_DELETE_MATCHES),
            },
            recoverability="not_applicable",
        )
    return normalized


def validate_timeline_track_index(index: int) -> int:
    try:
        normalized_index = int(index)
    except (TypeError, ValueError):
        raise ValidationError(
            "Track index must be an integer.",
            details={"index": index},
            recoverability="not_applicable",
        )
    if normalized_index < 1:
        raise ValidationError(
            "Track index must be 1 or greater.",
            details={"index": index},
            recoverability="not_applicable",
        )
    return normalized_index


def _ensure_edit_page_for_video_track_state(conn, track_type: str) -> Dict[str, Any]:
    if track_type != "video":
        return {"available": False, "reason": "not_required"}

    resolve = getattr(conn, "resolve", None)
    if resolve is None:
        return {"available": False, "reason": "resolve_unavailable"}

    get_current_page = getattr(resolve, "GetCurrentPage", None)
    open_page = getattr(resolve, "OpenPage", None)
    current_page = None
    if callable(get_current_page):
        try:
            current_page = get_current_page()
        except Exception:
            current_page = None

    if str(current_page or "").lower() == "edit":
        return {"available": True, "changed": False, "current_page": current_page}

    if not callable(open_page):
        return {
            "available": False,
            "reason": "open_page_unavailable",
            "current_page": current_page,
        }

    opened = open_page("edit")
    if opened is False:
        return {
            "available": True,
            "changed": False,
            "current_page": current_page,
            "open_result": opened,
            "error": "open_page_failed",
        }
    time.sleep(0.15)
    updated_page = None
    if callable(get_current_page):
        try:
            updated_page = get_current_page()
        except Exception:
            updated_page = None
    return {
        "available": True,
        "changed": str(updated_page or current_page or "").lower() == "edit",
        "previous_page": current_page,
        "current_page": updated_page,
        "open_result": opened,
        "native_api": "Resolve.OpenPage('edit')",
    }


def set_track_enabled(conn, track_type: str, index: int, enabled: bool, *, return_details: bool = False) -> Optional[Dict[str, Any]]:
    """
    Enable or disable (mute) a track.
    
    Args:
        conn: ResolveConnection instance
        track_type: Track type
        index: Track index
        enabled: True to enable, False to disable
    """
    normalized_type = normalize_timeline_track_type(track_type)
    normalized_index = validate_timeline_track_index(index)

    count_getter = getattr(conn.timeline, "GetTrackCount", None)
    if callable(count_getter):
        try:
            track_count = int(count_getter(normalized_type) or 0)
        except Exception:
            track_count = None
        else:
            if normalized_index > track_count:
                raise ValidationError(
                    "Track index not found.",
                    details={
                        "track_type": normalized_type,
                        "index": normalized_index,
                        "track_count": track_count,
                    },
                    recoverability="not_applicable",
                )

    page_switch = _ensure_edit_page_for_video_track_state(conn, normalized_type)
    result = conn.timeline.SetTrackEnable(normalized_type, normalized_index, enabled)
    getter = getattr(conn.timeline, "GetIsTrackEnabled", None)
    if callable(getter):
        actual = None
        deadline = time.monotonic() + (1.0 if normalized_type == "video" else 0.0)
        while True:
            try:
                actual = bool(getter(normalized_type, normalized_index))
            except Exception:
                actual = None
            else:
                if actual == bool(enabled):
                    set_verification_status("verified")
                    set_recoverability("not_applicable")
                    if return_details:
                        return {
                            "track_type": normalized_type,
                            "index": normalized_index,
                            "requested_enabled": bool(enabled),
                            "read_back_enabled": actual,
                            "api_result": result,
                            "verified": True,
                            "page_switch": page_switch,
                        }
                    return None
            if time.monotonic() >= deadline:
                break
            time.sleep(0.05)
        raise APICallFailed(
            "Failed to update track enabled state.",
            details={
                "track_type": normalized_type,
                "index": normalized_index,
                "enabled": bool(enabled),
                "actual": actual,
                "api_result": result,
                "page_switch": page_switch,
            },
        )
    if result is False:
        raise APICallFailed(
            "Failed to update track enabled state.",
            details={
                "track_type": normalized_type,
                "index": normalized_index,
                "enabled": bool(enabled),
                "api_result": result,
            },
        )
    set_verification_status("pending_manual")
    set_recoverability("manual")
    if return_details:
        return {
            "track_type": normalized_type,
            "index": normalized_index,
            "requested_enabled": bool(enabled),
            "read_back_enabled": None,
            "api_result": result,
            "verified": False,
        }
    return None


def set_track_locked(conn, track_type: str, index: int, locked: bool, *, return_details: bool = False) -> Optional[Dict[str, Any]]:
    """
    Lock or unlock a track.
    
    Args:
        conn: ResolveConnection instance
        track_type: Track type
        index: Track index
        locked: True to lock, False to unlock
    """
    normalized_type = normalize_timeline_track_type(track_type)
    normalized_index = validate_timeline_track_index(index)

    count_getter = getattr(conn.timeline, "GetTrackCount", None)
    if callable(count_getter):
        try:
            track_count = int(count_getter(normalized_type) or 0)
        except Exception:
            track_count = None
        else:
            if normalized_index > track_count:
                raise ValidationError(
                    "Track index not found.",
                    details={
                        "track_type": normalized_type,
                        "index": normalized_index,
                        "track_count": track_count,
                    },
                    recoverability="not_applicable",
                )

    result = conn.timeline.SetTrackLock(normalized_type, normalized_index, locked)
    getter = getattr(conn.timeline, "GetIsTrackLocked", None)
    if callable(getter):
        try:
            actual = bool(getter(normalized_type, normalized_index))
        except Exception:
            actual = None
        else:
            if actual == bool(locked):
                set_verification_status("verified")
                set_recoverability("not_applicable")
                if return_details:
                    return {
                        "track_type": normalized_type,
                        "index": normalized_index,
                        "requested_locked": bool(locked),
                        "read_back_locked": actual,
                        "api_result": result,
                        "verified": True,
                    }
                return None
        raise APICallFailed(
            "Failed to update track lock state.",
            details={
                "track_type": normalized_type,
                "index": normalized_index,
                "locked": bool(locked),
                "actual": actual,
                "api_result": result,
            },
        )
    if result is False:
        raise APICallFailed(
            "Failed to update track lock state.",
            details={
                "track_type": normalized_type,
                "index": normalized_index,
                "locked": bool(locked),
                "api_result": result,
            },
        )
    set_verification_status("pending_manual")
    set_recoverability("manual")
    if return_details:
        return {
            "track_type": normalized_type,
            "index": normalized_index,
            "requested_locked": bool(locked),
            "read_back_locked": None,
            "api_result": result,
            "verified": False,
        }
    return None


def _track_item_call_optional(obj: Any, method_name: str, *args: Any) -> Any:
    getter = getattr(obj, method_name, None)
    if not callable(getter):
        return None
    try:
        return getter(*args)
    except Exception:
        return None


def _track_item_int_optional(value: Any) -> int | None:
    try:
        return int(value)
    except Exception:
        return None


def _track_item_clip_properties(clip: Any) -> Dict[str, Any]:
    props = _track_item_call_optional(clip, "GetClipProperty")
    return props if isinstance(props, dict) else {}


def _track_item_clip_property(clip: Any, key: str) -> Any:
    value = _track_item_call_optional(clip, "GetClipProperty", key)
    if value not in (None, ""):
        return value
    return _track_item_clip_properties(clip).get(key)


def _track_item_first_property(clip: Any, keys: tuple[str, ...]) -> str | None:
    props = _track_item_clip_properties(clip)
    for key in keys:
        value = props.get(key)
        if value in (None, ""):
            value = _track_item_clip_property(clip, key)
        if value not in (None, ""):
            return str(value)
    return None


def _track_item_identifier(obj: Any, props: Dict[str, Any] | None = None) -> str | None:
    for method_name in ("GetUniqueId", "GetUniqueID", "GetMediaId", "GetMediaID", "GetId", "GetID"):
        value = _track_item_call_optional(obj, method_name)
        if value not in (None, ""):
            return str(value)
    for key in ("MediaId", "Media ID", "media_id", "Id", "ID"):
        value = (props or {}).get(key)
        if value not in (None, ""):
            return str(value)
    return None


def _track_item_media_pool_identifier(obj: Any, props: Dict[str, Any] | None = None) -> str | None:
    for method_name in ("GetMediaId", "GetMediaID", "GetUniqueId", "GetUniqueID", "GetId", "GetID"):
        value = _track_item_call_optional(obj, method_name)
        if value not in (None, ""):
            return str(value)
    for key in ("MediaId", "Media ID", "media_id", "Id", "ID"):
        value = (props or {}).get(key)
        if value not in (None, ""):
            return str(value)
    return None


def _track_item_unique_identifier(obj: Any) -> str | None:
    """Return only the native unique identifier; never widen durable identity to media/name/index truth."""
    return _sdk_timeline_unique_id(obj)


def _track_item_media_pool_details(item: Any, *, include_unique_id: bool = False) -> Dict[str, Any]:
    media_pool_item = _track_item_call_optional(item, "GetMediaPoolItem")
    if media_pool_item is None:
        details = {
            "source_path": None,
            "media_pool_item_name": None,
            "media_pool_item_id": None,
        }
        if include_unique_id:
            details["media_pool_item_unique_id"] = None
            details["source_frame_rate"] = None
        return details

    props = _track_item_clip_properties(media_pool_item)
    source_path = _track_item_first_property(
        media_pool_item,
        ("File Path", "Source File", "SourcePath", "FilePath", "Path"),
    )
    name = _track_item_call_optional(media_pool_item, "GetName")
    if name in (None, ""):
        name = _track_item_first_property(media_pool_item, ("Clip Name", "File Name", "FileName", "Name"))

    details = {
        "source_path": source_path,
        "media_pool_item_name": str(name) if name not in (None, "") else None,
        "media_pool_item_id": _track_item_media_pool_identifier(media_pool_item, props),
    }
    if include_unique_id:
        details["media_pool_item_unique_id"] = _track_item_unique_identifier(media_pool_item)
        details["source_frame_rate"] = _track_item_first_property(
            media_pool_item,
            ("FPS", "Frame Rate", "FrameRate", "Shot Frame Rate"),
        )
    return details


def get_track_items(
    conn,
    track_type: str,
    index: int,
    *,
    include_unique_ids: bool = False,
) -> List[Dict[str, Any]]:
    """
    List clips on a specific track.
    
    Args:
        conn: ResolveConnection instance
        track_type: Track type
        index: Track index
    
    Returns:
        List of clip info dicts
    """
    normalized_type = normalize_timeline_track_type(track_type)
    normalized_index = validate_timeline_track_index(index)

    count_getter = getattr(conn.timeline, "GetTrackCount", None)
    if callable(count_getter):
        try:
            track_count = int(count_getter(normalized_type) or 0)
        except Exception:
            track_count = None
        else:
            if normalized_index > track_count:
                raise ValidationError(
                    "Track index not found.",
                    details={
                        "track_type": normalized_type,
                        "index": normalized_index,
                        "track_count": track_count,
                    },
                    recoverability="not_applicable",
                )

    items = conn.timeline.GetItemListInTrack(normalized_type, normalized_index)
    if not items:
        return []

    rows = []
    for item in items:
        name = _track_item_call_optional(item, "GetName")
        if include_unique_ids:
            from .timeline_record_geometry import timeline_record_geometry

            geometry = timeline_record_geometry(item)
            start, end, dur = geometry["start"], geometry["end"], geometry["duration"]
        else:
            start = _track_item_call_optional(item, "GetStart")
            end = _track_item_call_optional(item, "GetEnd")
            dur = _track_item_call_optional(item, "GetDuration")
        media_pool_details = _track_item_media_pool_details(item, include_unique_id=include_unique_ids)
        row = {
            "name": name if name not in (None, "") else "?",
            "start": start if start is not None else "",
            "end": end if end is not None else "",
            "duration": dur if dur is not None else "",
            "left_offset": _track_item_int_optional(_track_item_call_optional(item, "GetLeftOffset")),
            "right_offset": _track_item_int_optional(_track_item_call_optional(item, "GetRightOffset")),
            "timeline_item_id": _track_item_identifier(item),
            **media_pool_details,
        }
        if include_unique_ids:
            row["record_subframes"] = geometry["record_subframes"]
            from .timeline_source_range import (
                ordinary_source_mapping_proven,
                trusted_timeline_item_source_range,
            )

            source_range = trusted_timeline_item_source_range(
                item, float(conn.fps), audio_only=normalized_type == "audio", connection=conn,
            )
            if (source_range["conflict"] or (normalized_type == "audio" and not source_range["authoritative"])) and ordinary_source_mapping_proven(conn, item):
                source_range = trusted_timeline_item_source_range(
                    item,
                    float(conn.fps),
                    ordinary_mapping_proven=True,
                    audio_only=normalized_type == "audio",
                    connection=conn,
                )
            if source_range["conflict"] or not source_range["authoritative"]:
                row["source_start_frame"] = None
                row["source_end_frame_exclusive"] = None
            else:
                row["source_start_frame"] = source_range["start"]
                row["source_end_frame_exclusive"] = source_range["end_exclusive"]
            row["timeline_item_unique_id"] = _track_item_unique_identifier(item)
            linked_getter = getattr(item, "GetLinkedItems", None)
            if not callable(linked_getter):
                row["linked_timeline_item_unique_ids"] = None
            else:
                try:
                    linked_items = linked_getter()
                except Exception:
                    linked_items = None
                if not isinstance(linked_items, (list, tuple)):
                    row["linked_timeline_item_unique_ids"] = None
                else:
                    linked_ids = []
                    unreadable_link = False
                    for linked_item in linked_items:
                        linked_id = _track_item_unique_identifier(linked_item)
                        if not linked_id:
                            unreadable_link = True
                            break
                        linked_ids.append(linked_id)
                    row["linked_timeline_item_unique_ids"] = None if unreadable_link else sorted(set(linked_ids))
        rows.append(row)

    if include_unique_ids:
        from .retime_source_metadata import enrich_track_source_metadata
        enrich_track_source_metadata(conn, rows, items, track_type=normalized_type, track_index=normalized_index)
    return rows


def _timeline_summary_frame_to_timecode(frame: int | None, fps: float) -> str | None:
    if frame is None:
        return None
    return seconds_to_timecode(frames_to_seconds(max(0, int(frame)), fps), fps)


def _timeline_summary_parse_duration_frames(value: str, fps: float) -> int:
    from ..utils.timecode import parse_time_input, seconds_to_frames

    raw = str(value or "").strip()
    if not raw:
        raise ValidationError(
            "Radius must be a duration such as 30s or 720f.",
            details={"radius": value},
            recoverability="not_applicable",
        )
    try:
        frames = seconds_to_frames(parse_time_input(raw, fps), fps)
    except Exception as exc:
        raise ValidationError(
            "Radius must be a duration such as 30s or 720f.",
            details={"radius": value},
            recoverability="not_applicable",
        ) from exc
    if frames < 0:
        raise ValidationError(
            "Radius must be zero or greater.",
            details={"radius": value, "frames": frames},
            recoverability="not_applicable",
        )
    return int(frames)


def _timeline_summary_parse_record_frame(conn, value: str) -> int:
    from ..utils.timecode import seconds_to_frames, timecode_to_seconds

    start_frame = _timeline_start_frame(conn)
    pos = str(value).strip()
    if ":" in pos or ";" in pos:
        absolute_frame = seconds_to_frames(timecode_to_seconds(pos, conn.fps), conn.fps)
        return int(absolute_frame) if int(absolute_frame) >= start_frame else start_frame + int(absolute_frame)
    return parse_record_frame(pos, conn.fps, start_frame)


def _timeline_summary_window(
    conn,
    *,
    window: str,
    radius: str,
    start_ref: str | None,
    end_ref: str | None,
) -> Dict[str, Any]:
    mode = str(window or "all").strip().lower()
    if start_ref is not None or end_ref is not None:
        mode = "range"
    if mode not in {"all", "current", "range"}:
        raise ValidationError(
            "Timeline summary window must be one of: all, current, range.",
            details={"window": window, "allowed_windows": ["all", "current", "range"]},
            recoverability="not_applicable",
        )

    fps = float(getattr(conn, "fps", 24.0) or 24.0)
    start_frame = _timeline_start_frame(conn)
    playhead = get_playhead(conn)

    range_start: int | None = None
    range_end: int | None = None
    radius_frames: int | None = None
    if mode == "current":
        radius_frames = _timeline_summary_parse_duration_frames(radius, fps)
        playhead_frame = int(playhead.get("frame") or start_frame)
        range_start = max(start_frame, playhead_frame - radius_frames)
        range_end = playhead_frame + radius_frames + 1
    elif mode == "range":
        if start_ref is None or end_ref is None:
            raise ValidationError(
                "Timeline summary range requires both --from and --to.",
                details={"from": start_ref, "to": end_ref},
                recoverability="not_applicable",
            )
        range_start = _timeline_summary_parse_record_frame(conn, start_ref)
        range_end = _timeline_summary_parse_record_frame(conn, end_ref)
        if range_start is None or range_end is None or range_end <= range_start:
            raise ValidationError(
                "Timeline summary range must end after it starts.",
                details={"from": start_ref, "to": end_ref, "start_frame": range_start, "end_frame": range_end},
                recoverability="not_applicable",
            )

    return {
        "mode": mode,
        "start_frame": range_start,
        "end_frame": range_end,
        "start_timecode": _timeline_summary_frame_to_timecode(range_start, fps),
        "end_timecode": _timeline_summary_frame_to_timecode(range_end, fps),
        "radius": radius,
        "radius_frames": radius_frames,
        "playhead": playhead,
    }


def _timeline_summary_item_int(item: Dict[str, Any], key: str) -> int | None:
    try:
        return int(item.get(key))
    except Exception:
        return None


def _timeline_summary_item_overlaps(item: Dict[str, Any], start_frame: int | None, end_frame: int | None) -> bool:
    if start_frame is None and end_frame is None:
        return True
    start = _timeline_summary_item_int(item, "start")
    end = _timeline_summary_item_int(item, "end")
    if start is None or end is None:
        return False
    if start_frame is not None and end <= start_frame:
        return False
    if end_frame is not None and start >= end_frame:
        return False
    return True


def _timeline_summary_source(item: Dict[str, Any]) -> str:
    for key in ("media_pool_item_name", "source_path", "name"):
        value = item.get(key)
        if value not in (None, ""):
            return str(value)
    return "Unknown source"


def _timeline_summary_angle(item: Dict[str, Any]) -> str | None:
    text = " ".join(str(item.get(key) or "") for key in ("name", "media_pool_item_name"))
    match = re.search(r"\bangle\s*([0-9A-Za-z_-]+)\b", text, flags=re.IGNORECASE)
    if match:
        return match.group(1)
    return None


def _timeline_summary_run_label(item: Dict[str, Any]) -> str:
    source = _timeline_summary_source(item)
    angle = _timeline_summary_angle(item)
    return f"{source} / Angle {angle}" if angle else source


def _timeline_summary_item_brief(
    item: Dict[str, Any],
    fps: float,
    *,
    include_unique_ids: bool = False,
) -> Dict[str, Any]:
    start = _timeline_summary_item_int(item, "start")
    end = _timeline_summary_item_int(item, "end")
    brief = {
        "name": item.get("name"),
        "start": start,
        "end": end,
        "start_timecode": _timeline_summary_frame_to_timecode(start, fps),
        "end_timecode": _timeline_summary_frame_to_timecode(end, fps),
        "duration_frames": max(0, int(end) - int(start)) if start is not None and end is not None else None,
        "source": _timeline_summary_source(item),
        "source_path": item.get("source_path"),
        "media_pool_item_name": item.get("media_pool_item_name"),
        "media_pool_item_id": item.get("media_pool_item_id"),
        "timeline_item_id": item.get("timeline_item_id"),
    }
    if include_unique_ids:
        if "record_subframes" in item:
            brief["record_subframes"] = item["record_subframes"]
        brief["media_pool_item_unique_id"] = item.get("media_pool_item_unique_id")
        brief["timeline_item_unique_id"] = item.get("timeline_item_unique_id")
        brief["linked_timeline_item_unique_ids"] = item.get("linked_timeline_item_unique_ids")
        brief["source_start_frame"] = _timeline_summary_item_int(item, "source_start_frame")
        brief["source_end_frame_exclusive"] = _timeline_summary_item_int(item, "source_end_frame_exclusive")
        brief["source_frame_rate"] = item.get("source_frame_rate")
        brief["retime_source"] = item.get("retime_source")
        brief["retime_time_map_digest"] = item.get("retime_time_map_digest")
        brief["inspector_state_digest"] = item.get("inspector_state_digest")
    return brief


def _timeline_summary_runs(items: List[Dict[str, Any]], *, fps: float, max_runs: int) -> Dict[str, Any]:
    sorted_items = sorted(
        items,
        key=lambda item: (
            _timeline_summary_item_int(item, "start") if _timeline_summary_item_int(item, "start") is not None else 10**18,
            _timeline_summary_item_int(item, "end") if _timeline_summary_item_int(item, "end") is not None else 10**18,
        ),
    )
    runs: List[Dict[str, Any]] = []
    for item in sorted_items:
        start = _timeline_summary_item_int(item, "start")
        end = _timeline_summary_item_int(item, "end")
        if start is None or end is None:
            continue
        label = _timeline_summary_run_label(item)
        source = _timeline_summary_source(item)
        angle = _timeline_summary_angle(item)
        if runs and runs[-1]["label"] == label and start <= int(runs[-1]["end"]) + 1:
            run = runs[-1]
            run["end"] = max(int(run["end"]), end)
            run["end_timecode"] = _timeline_summary_frame_to_timecode(run["end"], fps)
            run["duration_frames"] = max(0, int(run["end"]) - int(run["start"]))
            run["item_count"] += 1
            continue
        runs.append(
            {
                "label": label,
                "source": source,
                "angle": angle,
                "start": start,
                "end": end,
                "start_timecode": _timeline_summary_frame_to_timecode(start, fps),
                "end_timecode": _timeline_summary_frame_to_timecode(end, fps),
                "duration_frames": max(0, end - start),
                "item_count": 1,
            }
        )

    truncated = len(runs) > max_runs
    return {
        "runs": runs[:max_runs],
        "run_count": len(runs),
        "runs_truncated": truncated,
        "max_runs": max_runs,
    }


def _timeline_summary_track_pattern(track_type: str, items: List[Dict[str, Any]]) -> str:
    if not items:
        return "empty"
    angle_values = {_timeline_summary_angle(item) for item in items if _timeline_summary_angle(item)}
    source_values = {_timeline_summary_source(item) for item in items}
    if track_type in {"video", "audio"} and angle_values:
        return "multicam_angle_switches" if len(angle_values) > 1 else "single_multicam_angle"
    if len(source_values) == 1 and len(items) > 1:
        return "repeated_source_segments"
    if len(items) > 1:
        return "mixed_segments"
    return "single_item"


def _timeline_summary_track(
    conn,
    track: Dict[str, Any],
    *,
    window_info: Dict[str, Any],
    max_runs: int,
    include_items: bool,
    include_unique_ids: bool,
) -> Dict[str, Any]:
    fps = float(getattr(conn, "fps", 24.0) or 24.0)
    track_type = str(track.get("type") or "")
    track_index = int(track.get("index") or 0)
    all_items = get_track_items(conn, track_type, track_index, include_unique_ids=include_unique_ids)
    window_items = [
        item
        for item in all_items
        if _timeline_summary_item_overlaps(item, window_info.get("start_frame"), window_info.get("end_frame"))
    ]
    source_counts: Dict[str, int] = {}
    for item in window_items:
        source = _timeline_summary_source(item)
        source_counts[source] = source_counts.get(source, 0) + 1
    ordered_sources = sorted(source_counts.items(), key=lambda pair: (-pair[1], pair[0]))
    run_info = _timeline_summary_runs(window_items, fps=fps, max_runs=max_runs)
    playhead_frame = window_info.get("playhead", {}).get("frame")
    items_at_playhead = []
    if playhead_frame is not None:
        for item in window_items:
            start = _timeline_summary_item_int(item, "start")
            end = _timeline_summary_item_int(item, "end")
            if start is not None and end is not None and start <= int(playhead_frame) < end:
                items_at_playhead.append(_timeline_summary_item_brief(item, fps, include_unique_ids=include_unique_ids))
    rows = {
        "type": track_type,
        "index": track_index,
        "name": track.get("name") or "",
        "enabled": track.get("enabled"),
        "locked": track.get("locked"),
        "total_item_count": len(all_items),
        "window_item_count": len(window_items),
        "dominant_source": ordered_sources[0][0] if ordered_sources else None,
        "source_counts": [{"source": source, "items": count} for source, count in ordered_sources[:8]],
        "pattern": _timeline_summary_track_pattern(track_type, window_items),
        "items_at_playhead": items_at_playhead,
        **run_info,
    }
    if include_items and window_items:
        rows["first_item"] = _timeline_summary_item_brief(window_items[0], fps, include_unique_ids=include_unique_ids)
        rows["last_item"] = _timeline_summary_item_brief(window_items[-1], fps, include_unique_ids=include_unique_ids)
    if include_items:
        rows["items"] = [
            _timeline_summary_item_brief(item, fps, include_unique_ids=include_unique_ids)
            for item in window_items
        ]
    return rows


def _timeline_summary_current_items(tracks: List[Dict[str, Any]], playhead_frame: int | None) -> List[Dict[str, Any]]:
    if playhead_frame is None:
        return []
    rows = []
    for track in tracks:
        for item in track.get("items_at_playhead", []) if isinstance(track.get("items_at_playhead"), list) else []:
            rows.append(
                {
                    "track_type": track.get("type"),
                    "track_index": track.get("index"),
                    **item,
                }
            )
    return rows


def _timeline_summary_readiness(track_summaries: List[Dict[str, Any]], info: Dict[str, Any]) -> Dict[str, Any]:
    video_tracks = [track for track in track_summaries if track.get("type") == "video" and track.get("window_item_count", 0) > 0]
    audio_tracks = [track for track in track_summaries if track.get("type") == "audio" and track.get("window_item_count", 0) > 0]
    subtitle_tracks = [track for track in track_summaries if track.get("type") == "subtitle"]
    audio_embedded_or_unknown = bool(audio_tracks) and all(
        not track.get("source_counts")
        or all(("multicam" in str(row.get("source") or "").lower()) or not row.get("source") for row in track.get("source_counts", []))
        for track in audio_tracks
    )

    reasons: List[str] = []
    if not audio_tracks:
        reasons.append("No audio items were found in the summarized window.")
    elif audio_embedded_or_unknown and len(audio_tracks) <= 1:
        reasons.append("Only one audio track with multicam/unknown sources is visible in the summarized window.")
    if not subtitle_tracks and int(info.get("subtitle_tracks") or 0) == 0:
        reasons.append("No subtitle tracks are present.")
    if video_tracks and any(track.get("pattern") == "multicam_angle_switches" for track in video_tracks):
        reasons.append("Video appears to contain multicam angle switches; timeline changes can invalidate downstream captions, graphics, or color timing.")

    return {
        "transcription_scope": "current_open_timeline_audio",
        "transcription_safe": "unknown" if audio_tracks else "no_timeline_audio",
        "caption_safe": "unknown",
        "picture_lock_safe": "not_proven",
        "notes": reasons,
    }


def _timeline_summary_insights(track_summaries: List[Dict[str, Any]], info: Dict[str, Any]) -> List[str]:
    insights: List[str] = []
    total_items = sum(int(track.get("window_item_count") or 0) for track in track_summaries)
    total_runs = sum(int(track.get("run_count") or 0) for track in track_summaries)
    if total_items and total_runs and total_runs < total_items:
        insights.append(f"Compressed {total_items} window items into {total_runs} source runs for editor-readable scanning.")
    if any(track.get("pattern") == "multicam_angle_switches" for track in track_summaries):
        insights.append("At least one summarized track looks like a multicam angle-switch edit.")
    if int(info.get("subtitle_tracks") or 0) == 0:
        insights.append("The timeline currently has no subtitle tracks.")
    if any(track.get("runs_truncated") for track in track_summaries):
        insights.append("Some run lists were truncated; increase --max-runs or narrow the window for full detail.")
    return insights


def summarize_timeline(
    conn,
    *,
    window: str = "all",
    radius: str = "30s",
    start_ref: str | None = None,
    end_ref: str | None = None,
    track_type: str = "all",
    max_runs: int = 24,
    include_items: bool = False,
    authoritative_track_state: bool = False,
) -> Dict[str, Any]:
    """Return a compact, editor-readable map of the current timeline state."""
    normalized_track_type = normalize_timeline_item_track_type(track_type)
    try:
        normalized_max_runs = int(max_runs)
    except Exception:
        raise ValidationError(
            "Max runs must be an integer.",
            details={"max_runs": max_runs},
            recoverability="not_applicable",
        )
    if normalized_max_runs < 1:
        raise ValidationError(
            "Max runs must be 1 or greater.",
            details={"max_runs": max_runs},
            recoverability="not_applicable",
        )

    info = get_timeline_info(conn)
    duration = get_timeline_duration(conn)
    window_info = _timeline_summary_window(conn, window=window, radius=radius, start_ref=start_ref, end_ref=end_ref)
    tracks = [
        track
        for track in list_tracks(conn, authoritative_state=authoritative_track_state)
        if normalized_track_type == "all" or track.get("type") == normalized_track_type
    ]
    track_summaries = [
        _timeline_summary_track(
            conn,
            track,
            window_info=window_info,
            max_runs=normalized_max_runs,
            include_items=include_items,
            include_unique_ids=authoritative_track_state,
        )
        for track in tracks
    ]

    playhead_frame = window_info.get("playhead", {}).get("frame")
    current_items = _timeline_summary_current_items(track_summaries, playhead_frame)

    set_verification_status("verified")
    set_recoverability("not_applicable")
    return {
        "timeline": {
            "name": info.get("name"),
            "timeline_id": (
                _sdk_timeline_unique_id(conn.timeline)
                if authoritative_track_state
                else _timeline_unique_id(conn.timeline)
            ),
            "fps": info.get("fps"),
            "start_frame": info.get("start_frame"),
            "start_timecode": info.get("start_timecode"),
            "end_timecode": info.get("end_timecode"),
            "duration": duration.get("duration"),
            "duration_seconds": duration.get("duration_seconds"),
            "video_tracks": info.get("video_tracks"),
            "audio_tracks": info.get("audio_tracks"),
            "subtitle_tracks": info.get("subtitle_tracks"),
            "resolution": {
                "width": info.get("timelineResolutionWidth"),
                "height": info.get("timelineResolutionHeight"),
            },
        },
        "window": window_info,
        "tracks": track_summaries,
        "current_items": current_items,
        "readiness": _timeline_summary_readiness(track_summaries, info),
        "insights": _timeline_summary_insights(track_summaries, info),
    }


def validate_sdk_live_inspection_deadline(deadline_at_ms: int | None) -> None:
    _validate_sdk_live_inspection_deadline(deadline_at_ms)


def documented_sdk_unique_id(native_object):
    return _sdk_timeline_unique_id(native_object)


def documented_sdk_media_pool_id(native_object):
    return _sdk_media_pool_native_id(native_object)


def _sdk_fairlight_numeric_readback(value: Any, *, minimum: float, maximum: float) -> Dict[str, Any]:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        normalized = float(value)
        if minimum <= normalized <= maximum:
            return {"status": "available", "value": normalized}
    return {"status": "unavailable", "reason": "readback_unavailable"}


def _inspect_sdk_fairlight_state(conn) -> Dict[str, Any]:
    """Return a bounded, public-safe Fairlight read model for SDK snapshot bracketing."""
    from . import fairlight_ops

    tracks = []
    for row in fairlight_ops.list_audio_tracks(conn):
        index = row.get("index")
        if not isinstance(index, int) or isinstance(index, bool) or not 1 <= index <= 4096:
            raise APICallFailed("Fairlight track inspection returned an invalid one-based track index.")
        mixer = row.get("mixer") if isinstance(row.get("mixer"), dict) else {}
        pan_state = mixer.get("pan") if isinstance(mixer.get("pan"), dict) else {}
        pan_percent = row.get("pan")
        normalized_pan = (
            float(pan_percent) / 100.0
            if isinstance(pan_percent, (int, float)) and not isinstance(pan_percent, bool)
            else None
        )
        tracks.append({
            "track_index": index,
            "level_db": _sdk_fairlight_numeric_readback(row.get("fader_db"), minimum=-160, maximum=60),
            "pan": _sdk_fairlight_numeric_readback(normalized_pan, minimum=-1, maximum=1),
            "pan_channel_values": row.get("pan_channel_values"),
            "pan_set_supported": pan_state.get("set_supported"),
        })

    # The current DB reader proves only that label tokens occur in an opaque
    # mixer blob. It does not prove active FlexBus topology, so those labels
    # must never become routable SDK identities.
    try:
        plan_readback = fairlight_ops.inspect_sdk_fairlight_plan_clip_state(conn)
    except Exception:
        # Public timeline snapshots remain available when private Disk DB
        # readback is unsupported. Aggregate plans fail closed on this status.
        plan_readback = {"status": "unavailable", "clips": []}
    return {
        "tracks": tracks,
        "buses": {"status": "unavailable", "reason": "readback_unavailable", "buses": []},
        "plan_readback": plan_readback,
    }


def inspect_sdk_live_state(
    conn,
    operation: str,
    *,
    deadline_at_ms: int | None = None,
    offset: int = 0,
    page_size: int = 100,
    search: dict[str, Any] | None = None,
    multicam_name: str | None = None,
    inspect_multicam=None,
    managed_affected_native_ids: list[str] | None = None,
    managed_retained_database_native_ids: list[str] | None = None,
    retime_expected_targets: list[dict[str, Any]] | None = None,
    inspect_retime=None,
    node_stack_layer_index: int = 1,
) -> Dict[str, Any]:
    return _inspect_sdk_live_state(
        conn,
        operation,
        deadline_at_ms=deadline_at_ms,
        list_timelines=list_timelines,
        summarize_timeline=summarize_timeline,
        offset=offset,
        page_size=page_size,
        search=search,
        list_markers=list_markers,
        multicam_name=multicam_name,
        inspect_multicam=inspect_multicam,
        managed_affected_native_ids=managed_affected_native_ids,
        managed_retained_database_native_ids=managed_retained_database_native_ids,
        retime_expected_targets=retime_expected_targets,
        inspect_retime=inspect_retime,
        inspect_fairlight=_inspect_sdk_fairlight_state,
        node_stack_layer_index=node_stack_layer_index,
    )


def require_sdk_marker_mutation_guard(conn) -> None:
    _require_sdk_marker_mutation_guard(
        conn,
        list_timelines=list_timelines,
        summarize_timeline=summarize_timeline,
        list_markers=list_markers,
        inspect_fairlight=_inspect_sdk_fairlight_state,
    )


def require_sdk_color_mutation_guard(conn) -> None:
    _require_sdk_color_mutation_guard(
        conn,
        list_timelines=list_timelines,
        summarize_timeline=summarize_timeline,
        list_markers=list_markers,
        inspect_fairlight=_inspect_sdk_fairlight_state,
    )


def require_sdk_mutation_guard(conn) -> None:
    _require_sdk_mutation_guard(
        conn,
        list_timelines=list_timelines,
        summarize_timeline=summarize_timeline,
        list_markers=list_markers,
        inspect_fairlight=_inspect_sdk_fairlight_state,
    )


def _timeline_start_frame(conn) -> int:
    try:
        value = int(getattr(conn, "start_frame", 0) or 0)
    except Exception:
        value = 0
    if value == 0 and hasattr(conn.timeline, "GetStartFrame"):
        try:
            value = int(conn.timeline.GetStartFrame())
        except Exception:
            value = 0
    return value


def _timeline_name(conn) -> str | None:
    try:
        return conn.timeline.GetName()
    except Exception:
        return None


def _parse_optional_record_frame(conn, value: str | None) -> int | None:
    if value is None:
        return None
    return parse_record_frame(str(value), conn.fps, _timeline_start_frame(conn))


def _timeline_item_bounds_match(
    *,
    item_start: int,
    item_end: int,
    start_frame: int | None,
    end_frame: int | None,
    match: str,
) -> bool:
    if start_frame is None and end_frame is None:
        return True

    if match == "overlap":
        return (end_frame is None or item_start < end_frame) and (start_frame is None or item_end > start_frame)

    if match == "contained":
        return (start_frame is None or item_start >= start_frame) and (end_frame is None or item_end <= end_frame)

    if match == "covering":
        if start_frame is not None and end_frame is not None:
            return item_start <= start_frame and item_end >= end_frame
        if start_frame is not None:
            return item_start <= start_frame < item_end
        if end_frame is not None:
            return item_start < end_frame <= item_end

    return False


def _timeline_item_filter_candidates(
    *,
    start_frame: int | None,
    end_frame: int | None,
    timeline_start: int,
) -> set[tuple[int | None, int | None]]:
    ranges: set[tuple[int | None, int | None]] = {(start_frame, end_frame)}
    if timeline_start:
        ranges.add(
            (
                None if start_frame is None else int(start_frame) - timeline_start,
                None if end_frame is None else int(end_frame) - timeline_start,
            )
        )
    return ranges


def _collect_timeline_items_matching_filter(
    conn,
    *,
    track_type: str,
    track_index: int | None,
    start_frame: int | None,
    end_frame: int | None,
    match: str,
) -> List[tuple[Any, str, int]]:
    normalized_track_type = normalize_timeline_item_track_type(track_type)
    normalized_track_index = validate_timeline_track_index(track_index) if track_index is not None else None
    normalized_match = normalize_timeline_item_delete_match(match)

    types_to_search = ["video", "audio", "subtitle"] if normalized_track_type == "all" else [normalized_track_type]
    candidate_ranges = _timeline_item_filter_candidates(
        start_frame=start_frame,
        end_frame=end_frame,
        timeline_start=_timeline_start_frame(conn),
    )

    rows: List[tuple[Any, str, int]] = []
    for current_type in types_to_search:
        count_getter = getattr(conn.timeline, "GetTrackCount", None)
        try:
            track_count = int(count_getter(current_type) or 0) if callable(count_getter) else 0
        except Exception:
            track_count = 0

        if normalized_track_index is not None:
            if track_count and normalized_track_index > track_count:
                if normalized_track_type == "all":
                    continue
                raise ValidationError(
                    "Track index not found.",
                    details={
                        "track_type": current_type,
                        "index": normalized_track_index,
                        "track_count": track_count,
                    },
                    recoverability="not_applicable",
                )
            track_indices = [normalized_track_index]
        else:
            track_indices = range(1, track_count + 1)

        for idx in track_indices:
            items = conn.timeline.GetItemListInTrack(current_type, idx) or []
            for item in items:
                try:
                    item_start = int(item.GetStart())
                    item_end = int(item.GetEnd())
                except Exception:
                    continue
                if any(
                    _timeline_item_bounds_match(
                        item_start=item_start,
                        item_end=item_end,
                        start_frame=candidate_start,
                        end_frame=candidate_end,
                        match=normalized_match,
                    )
                    for candidate_start, candidate_end in candidate_ranges
                ):
                    rows.append((item, current_type, idx))
    return rows


def _delete_clips_no_ripple(timeline, items: list[Any]) -> dict[str, Any]:
    deleter = require_api_method(
        timeline,
        "DeleteClips",
        capability_id="timeline.items_delete",
        runtime_object="timeline",
    )
    try:
        result = deleter(items, False)
        return {"api_result": result, "used_non_ripple_argument": True, "fallback_used": False}
    except TypeError as exc:
        result = deleter(items)
        return {
            "api_result": result,
            "used_non_ripple_argument": False,
            "fallback_used": True,
            "fallback_reason": str(exc),
        }
