from __future__ import annotations

from .edit_insert_overwrite import insert_audio_clips_at, insert_clip_at, insert_clips_at, overwrite_clip_at, overwrite_clips_at

# ---------------------------------------------------------------------------
# Remove
# ---------------------------------------------------------------------------

def remove_clip_at(conn, position: str, track_type: str = "video", track_index: int = 0) -> Dict[str, Any]:
    """Remove one uniquely resolved clip without rippling adjacent items."""
    from . import timeline_precision_edit

    before = timeline_precision_edit.snapshot_timeline(conn)
    frame = parse_record_frame(position, conn.fps, before.start_frame)
    target = timeline_precision_edit.select_item_at(
        before,
        frame=frame,
        track_type=track_type,
        track_index=track_index,
    )
    result = timeline_precision_edit.delete_non_ripple(
        conn,
        before=before,
        target_ids=[target.item_id],
        action="edit.remove",
    )
    result.update(
        {
            "removed": target.name,
            "start": target.start,
            "end": target.end,
            "track_type": target.track_type,
            "track_index": target.track_index,
        }
    )
    return result


def remove_range(
    conn,
    in_pos: str,
    out_pos: str,
    track_type: str = "video",
    track_index: int = 0,
) -> Dict[str, Any]:
    """Remove every whole clip overlapping [in_pos, out_pos), without ripple."""
    from . import timeline_precision_edit

    before = timeline_precision_edit.snapshot_timeline(conn)
    sf = parse_record_frame(in_pos, conn.fps, before.start_frame)
    ef = parse_record_frame(out_pos, conn.fps, before.start_frame)
    if ef <= sf:
        raise ValidationError(
            "Range end must be greater than range start.",
            details={"in": in_pos, "out": out_pos, "start_frame": sf, "end_frame": ef},
        )
    targets = timeline_precision_edit.select_items_in_range(
        before,
        start_frame=sf,
        end_frame=ef,
        track_type=track_type,
        track_index=track_index,
    )
    result = timeline_precision_edit.delete_non_ripple(
        conn,
        before=before,
        target_ids=[target.item_id for target in targets],
        action="edit.remove_range",
    )
    result.update(
        {
            "requested_range": {"in": in_pos, "out": out_pos, "start_frame": sf, "end_frame": ef},
            "selection_semantics": "whole_items_overlapping_half_open_range",
            "removed": [target.name for target in targets],
            "count": len(targets),
        }
    )
    return result


# ---------------------------------------------------------------------------
# Silence Detection (ffmpeg)
# ---------------------------------------------------------------------------

def detect_silence(
    wav_path: str,
    threshold_db: float = -40.0,
    min_duration: float = 0.5,
) -> List[Dict[str, Any]]:
    """
    Detect silent segments in a WAV file using ffmpeg silencedetect.

    Returns list of {start, end, duration} dicts (seconds).
    """
    cmd = [
        resolve_tool("ffmpeg"), "-i", wav_path,
        "-af", f"silencedetect=n={threshold_db}dB:d={min_duration}",
        "-f", "null", "-",
    ]
    logger.debug("Running: %s", " ".join(cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if proc.returncode != 0:
        raise APICallFailed(
            "ffmpeg silencedetect failed.",
            details={"stderr_tail": proc.stderr[-500:], "wav_path": wav_path},
        )
    stderr = proc.stderr

    # Parse ffmpeg silence_start / silence_end lines
    starts: List[float] = []
    ends: List[float] = []

    for line in stderr.splitlines():
        m = re.search(r"silence_start:\s*([\d.]+)", line)
        if m:
            starts.append(float(m.group(1)))
        m = re.search(r"silence_end:\s*([\d.]+)\s*\|\s*silence_duration:\s*([\d.]+)", line)
        if m:
            ends.append(float(m.group(1)))

    segments = []
    for i, s in enumerate(starts):
        e = ends[i] if i < len(ends) else None
        seg: Dict[str, Any] = {"start": round(s, 3)}
        if e is not None:
            seg["end"] = round(e, 3)
            seg["duration"] = round(e - s, 3)
        segments.append(seg)

    return segments


def detect_silence_on_timeline(
    conn,
    threshold_db: float = -40.0,
    min_duration: float = 0.5,
    wav_path: str = "/tmp/resolve_silence_detect.wav",
) -> List[Dict[str, Any]]:
    """
    Render timeline audio to WAV, then detect silence.

    Requires the render module to be available.
    """
    rendered_audio_path = render_timeline_audio_for_silence(conn, wav_path)
    return detect_silence(rendered_audio_path, threshold_db, min_duration)


def render_timeline_audio_for_silence(
    conn,
    wav_path: str = "/tmp/resolve_silence_detect.wav",
) -> str:
    """Render timeline audio once for adaptive silence analysis."""
    from ..core.render_engine import preflight_audio_render, render_audio, render_transcript_audio

    try:
        preflight_audio_render(conn, format="Wave", codec="Linear PCM")
        return str(render_audio(conn, wav_path))
    except ReadinessFailed as exc:
        if "codec" not in str(exc).lower():
            raise
        fallback_path = os.path.splitext(wav_path)[0] + ".mp3"
        preset_path = os.path.abspath(
            os.path.join(
                os.path.dirname(__file__),
                "..",
                "assets",
                "render-presets",
                "CutAgent Transcript.xml",
            )
        )
        rendered = render_transcript_audio(
            conn,
            output_path=fallback_path,
            preset_path=preset_path,
            preset_name="CutAgent Transcript",
        )
        return str(rendered.get("output_path") or fallback_path)


# ---------------------------------------------------------------------------
# Silence Cut
# ---------------------------------------------------------------------------

def _timeline_time_context(conn) -> Dict[str, Any]:
    timeline_start_tc = "00:00:00:00"
    timeline_start_seconds = 0.0
    try:
        timeline_start_tc = conn.timeline.GetStartTimecode()
        timeline_start_seconds = timecode_to_seconds(timeline_start_tc, conn.fps)
        end_tc = conn.timeline.GetEndTimecode()
        total_duration = timecode_to_seconds(end_tc, conn.fps) - timeline_start_seconds
    except Exception:
        total_duration = 0
        timeline_start_frame = int(getattr(conn, "start_frame", 0) or 0)
        if timeline_start_frame <= 0:
            try:
                timeline_start_frame = int(conn.timeline.GetStartFrame())
            except Exception:
                timeline_start_frame = 0
        for ttype in ("video", "audio"):
            count = conn.timeline.GetTrackCount(ttype) or 0
            for i in range(1, count + 1):
                items = conn.timeline.GetItemListInTrack(ttype, i) or []
                for item in items:
                    try:
                        e = int(item.GetEnd())
                        s = frames_to_seconds(e - timeline_start_frame, conn.fps)
                        if s > total_duration:
                            total_duration = s
                    except Exception:
                        pass
    return {
        "timeline_start_tc": timeline_start_tc,
        "timeline_start_seconds": timeline_start_seconds,
        "total_duration": total_duration,
    }


def _range_bounds(row: Any) -> Tuple[float, float]:
    if isinstance(row, dict):
        return (float(row["start"]), float(row["end"]))
    return (float(row[0]), float(row[1]))


def _timeline_start_frame_value(conn) -> int:
    try:
        return int(conn.timeline.GetStartFrame())
    except Exception:
        try:
            return int(getattr(conn, "start_frame", 0) or 0)
        except Exception:
            return 0


def _normalize_cut_frame_ranges(
    conn,
    cut_ranges: List[Any],
    *,
    timeline_start_frame: int,
    total_duration: float,
) -> List[Tuple[int, int]]:
    total_frames = max(0, seconds_to_frames(total_duration, conn.fps))
    timeline_end_frame = timeline_start_frame + total_frames
    frame_ranges: List[Tuple[int, int]] = []
    for cut_start, cut_end in (_range_bounds(row) for row in cut_ranges):
        start_seconds = max(0.0, min(float(total_duration), float(cut_start)))
        end_seconds = max(0.0, min(float(total_duration), float(cut_end)))
        start_frame = timeline_start_frame + seconds_to_frames(start_seconds, conn.fps)
        end_frame = timeline_start_frame + seconds_to_frames(end_seconds, conn.fps)
        start_frame = max(timeline_start_frame, min(timeline_end_frame, start_frame))
        end_frame = max(timeline_start_frame, min(timeline_end_frame, end_frame))
        if end_frame > start_frame:
            frame_ranges.append((start_frame, end_frame))

    merged: List[Tuple[int, int]] = []
    for start_frame, end_frame in sorted(frame_ranges):
        if not merged or start_frame > merged[-1][1]:
            merged.append((start_frame, end_frame))
        else:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end_frame))
    return merged


def _keep_frame_ranges_from_cuts(
    *,
    timeline_start_frame: int,
    total_duration: float,
    fps: float,
    cut_frame_ranges: List[Tuple[int, int]],
) -> List[Tuple[int, int]]:
    timeline_end_frame = timeline_start_frame + max(0, seconds_to_frames(total_duration, fps))
    keep_ranges: List[Tuple[int, int]] = []
    cursor = timeline_start_frame
    for cut_start, cut_end in cut_frame_ranges:
        if cut_start > cursor:
            keep_ranges.append((cursor, cut_start))
        cursor = max(cursor, cut_end)
    if cursor < timeline_end_frame:
        keep_ranges.append((cursor, timeline_end_frame))
    return keep_ranges


def _safe_timeline_item_name(item: Any) -> str:
    getter = getattr(item, "GetName", None)
    if callable(getter):
        try:
            return str(getter())
        except Exception:
            pass
    return "<timeline item>"


def _timeline_item_source_row(item: Any, track_type: str, track_index: int, timeline_fps: float) -> Dict[str, Any]:
    start = int(item.GetStart())
    end = int(item.GetEnd())
    if end <= start:
        raise ValidationError(
            "Timeline item has non-positive duration.",
            details={"track_type": track_type, "track_index": track_index, "name": _safe_timeline_item_name(item)},
        )

    media_pool_item = item.GetMediaPoolItem() if hasattr(item, "GetMediaPoolItem") else None
    if not media_pool_item:
        raise APICallFailed(
            "Cannot rewrite timeline natively because a timeline item has no Media Pool item.",
            details={"track_type": track_type, "track_index": track_index, "name": _safe_timeline_item_name(item)},
        )

    source_start = None
    source_start_domain = "source"
    for method_name in ("GetSourceStartFrame", "GetSourceStart"):
        getter = getattr(item, method_name, None)
        if callable(getter):
            try:
                source_start = int(getter())
                break
            except Exception:
                continue
    if source_start is None:
        try:
            source_start = int(item.GetLeftOffset())
            source_start_domain = "timeline"
        except Exception:
            source_start = 0
            source_start_domain = "timeline"

    source_fps = _media_pool_item_frame_rate(media_pool_item, fallback_fps=timeline_fps)
    if source_start_domain == "timeline":
        source_start = _timeline_to_source_frame_count(
            source_start,
            source_fps=source_fps,
            timeline_fps=timeline_fps,
        )

    return {
        "item": item,
        "name": _safe_timeline_item_name(item),
        "track_type": track_type,
        "track_index": track_index,
        "start": start,
        "end": end,
        "source_start": source_start,
        "source_start_domain": "source",
        "source_fps": source_fps,
        "timeline_fps": timeline_fps,
        "media_pool_item": media_pool_item,
    }


def _snapshot_source_timeline_items(conn) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for track_type in ("video", "audio"):
        track_count = int(conn.timeline.GetTrackCount(track_type) or 0)
        for track_index in range(1, track_count + 1):
            for item in conn.timeline.GetItemListInTrack(track_type, track_index) or []:
                rows.append(_timeline_item_source_row(item, track_type, track_index, conn.fps))
    if not rows:
        raise APICallFailed("Active timeline has no media items to rewrite.")
    return rows


def _ensure_timeline_track_count(timeline: Any, track_type: str, required_count: int) -> int:
    try:
        current_count = int(timeline.GetTrackCount(track_type) or 0)
    except Exception:
        current_count = 0
    if current_count >= required_count:
        return current_count

    adder = getattr(timeline, "AddTrack", None)
    if not callable(adder):
        raise APICallFailed(
            "Cannot create enough tracks on the rewritten timeline.",
            details={"track_type": track_type, "required": required_count, "current": current_count},
        )
    while current_count < required_count:
        result = adder(track_type)
        if result is False:
            raise APICallFailed(
                "DaVinci Resolve rejected track creation for the rewritten timeline.",
                details={"track_type": track_type, "required": required_count, "current": current_count},
            )
        try:
            refreshed_count = int(timeline.GetTrackCount(track_type) or 0)
        except Exception:
            refreshed_count = current_count + 1
        current_count = max(refreshed_count, current_count + 1)
    return current_count


def _set_current_timeline_for_rewrite(conn, timeline: Any, requested_name: str) -> None:
    setter = getattr(getattr(conn, "project", None), "SetCurrentTimeline", None)
    if callable(setter):
        result = setter(timeline)
        if result is False:
            raise APICallFailed(
                "Failed to switch to rewritten timeline.",
                details={"timeline": requested_name, "api_call": "Project.SetCurrentTimeline"},
            )
    if hasattr(conn, "wait_for_state"):
        conn.wait_for_state(
            lambda state: state.get("timeline") == requested_name,
            description=f"rewritten timeline '{requested_name}' to become current",
        )
    if hasattr(conn, "refresh"):
        conn.refresh()
    else:
        try:
            conn.timeline = timeline
        except Exception:
            pass


def _create_rewrite_timeline(conn, requested_name: str, timeline_start_tc: str) -> Any:
    creator = getattr(conn.media_pool, "CreateEmptyTimeline", None)
    if not callable(creator):
        raise APICallFailed(
            "Native timeline rewrite requires MediaPool.CreateEmptyTimeline.",
            details={"timeline": requested_name},
        )
    new_timeline = creator(requested_name)
    if not new_timeline:
        raise APICallFailed(f"Failed to create timeline '{requested_name}'.")

    setter = getattr(new_timeline, "SetStartTimecode", None)
    if callable(setter):
        try:
            setter(timeline_start_tc)
        except Exception:
            pass

    actual_name = new_timeline.GetName() if hasattr(new_timeline, "GetName") else requested_name
    _set_current_timeline_for_rewrite(conn, new_timeline, actual_name)
    return getattr(conn, "timeline", None) or new_timeline


def _append_rewrite_requests(conn, append_requests: List[Dict[str, Any]]) -> int:
    if not append_requests:
        return 0
    appended_count = 0
    for index, request in enumerate(append_requests):
        # DaVinci Resolve can stall on large AppendToTimeline lists; one-entry calls keep timeline rewrites responsive.
        result = conn.media_pool.AppendToTimeline([request])
        if not result:
            raise APICallFailed(
                "AppendToTimeline failed while materializing rewritten timeline.",
                details={
                    "request_count": len(append_requests),
                    "failed_index": index,
                    "append_call_size": 1,
                },
            )
        appended_count += len(result) if isinstance(result, list) else 1
    return appended_count


def _timeline_track_item_counts(timeline: Any) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for track_type in ("video", "audio"):
        total = 0
        try:
            track_count = int(timeline.GetTrackCount(track_type) or 0)
        except Exception:
            track_count = 0
        for track_index in range(1, track_count + 1):
            try:
                total += len(timeline.GetItemListInTrack(track_type, track_index) or [])
            except Exception:
                pass
        counts[track_type] = total
    return counts


def _timeline_rows_by_track(timeline: Any) -> Dict[Tuple[str, int], List[Dict[str, Any]]]:
    rows_by_track: Dict[Tuple[str, int], List[Dict[str, Any]]] = {}
    for track_type in ("video", "audio"):
        try:
            track_count = int(timeline.GetTrackCount(track_type) or 0)
        except Exception:
            track_count = 0
        for track_index in range(1, track_count + 1):
            rows: List[Dict[str, Any]] = []
            try:
                items = timeline.GetItemListInTrack(track_type, track_index) or []
            except Exception:
                items = []
            for item in items:
                row = _summarize_timeline_item(item)
                row["track_type"] = track_type
                row["track_index"] = track_index
                rows.append(row)
            rows.sort(key=lambda row: (row.get("start") if isinstance(row.get("start"), int) else -1, str(row.get("name") or "")))
            rows_by_track[(track_type, track_index)] = rows
    return rows_by_track


def _clip_row_name_matches(row: Dict[str, Any], expected: Dict[str, Any]) -> bool:
    expected_names = {
        str(value).strip()
        for value in (expected.get("name"), expected.get("media_pool_item"))
        if value is not None and str(value).strip()
    }
    if not expected_names:
        return True
    for key in ("name", "media_pool_item"):
        value = row.get(key)
        if isinstance(value, str) and value.strip() in expected_names:
            return True
    return False


def _verify_rewrite_timeline_segments(
    timeline: Any,
    expected_segments: List[Dict[str, Any]],
) -> Dict[str, Any]:
    rows_by_track = _timeline_rows_by_track(timeline)
    used: Dict[Tuple[str, int], set[int]] = {}
    missing: List[Dict[str, Any]] = []
    duration_mismatches: List[Dict[str, Any]] = []
    matched: List[Dict[str, Any]] = []

    for expected in expected_segments:
        track_key = (str(expected["track_type"]), int(expected["track_index"]))
        rows = rows_by_track.get(track_key, [])
        used_indexes = used.setdefault(track_key, set())
        start = int(expected["start"])
        duration = int(expected["duration"])
        name_matches = [
            (idx, row)
            for idx, row in enumerate(rows)
            if idx not in used_indexes
            and row.get("start") == start
            and _clip_row_name_matches(row, expected)
        ]
        exact_match = next(
            ((idx, row) for idx, row in name_matches if row.get("duration") == duration),
            None,
        )
        if exact_match:
            idx, row = exact_match
            used_indexes.add(idx)
            matched.append({"expected": expected, "actual": row})
            continue
        if name_matches:
            idx, row = name_matches[0]
            used_indexes.add(idx)
            duration_mismatches.append(
                {
                    "track_type": expected["track_type"],
                    "track_index": expected["track_index"],
                    "name": expected.get("name"),
                    "start": start,
                    "expected_duration": duration,
                    "actual_duration": row.get("duration"),
                    "actual_end": row.get("end"),
                }
            )
            matched.append({"expected": expected, "actual": row})
            continue
        missing.append(expected)

    continuity_mismatches: List[Dict[str, Any]] = []
    for track_key in sorted({(str(row["track_type"]), int(row["track_index"])) for row in expected_segments}):
        track_matches = [
            pair for pair in matched
            if (str(pair["expected"]["track_type"]), int(pair["expected"]["track_index"])) == track_key
        ]
        track_matches.sort(key=lambda pair: int(pair["expected"]["start"]))
        previous = None
        for pair in track_matches:
            if previous is not None:
                prev_expected_end = int(previous["expected"]["end"])
                current_expected_start = int(pair["expected"]["start"])
                if current_expected_start == prev_expected_end:
                    prev_actual_end = previous["actual"].get("end")
                    current_actual_start = pair["actual"].get("start")
                    if prev_actual_end != current_actual_start:
                        continuity_mismatches.append(
                            {
                                "track_type": track_key[0],
                                "track_index": track_key[1],
                                "previous_expected_end": prev_expected_end,
                                "previous_actual_end": prev_actual_end,
                                "current_expected_start": current_expected_start,
                                "current_actual_start": current_actual_start,
                            }
                        )
            previous = pair

    ok = not missing and not duration_mismatches and not continuity_mismatches
    return {
        "ok": ok,
        "segments_expected": len(expected_segments),
        "segments_verified": len(matched) - len(duration_mismatches),
        "missing_count": len(missing),
        "duration_mismatch_count": len(duration_mismatches),
        "continuity_mismatch_count": len(continuity_mismatches),
        "missing_segments": missing[:20],
        "duration_mismatches": duration_mismatches[:20],
        "continuity_mismatches": continuity_mismatches[:20],
    }


def _rewrite_timeline_from_cut_ranges(
    conn,
    cut_ranges: List[Any],
    *,
    requested_name: str,
    temp_prefix: str,
) -> Dict[str, Any]:
    normalized_ranges = [
        (start, end)
        for start, end in (_range_bounds(row) for row in cut_ranges)
        if end > start
    ]
    if not normalized_ranges:
        raise ValidationError("At least one positive cut range is required.")

    context = _timeline_time_context(conn)
    total_duration = float(context["total_duration"])
    timeline_start_frame = _timeline_start_frame_value(conn)
    timeline_start_tc = str(context.get("timeline_start_tc") or "00:00:00:00")
    cut_frame_ranges = _normalize_cut_frame_ranges(
        conn,
        normalized_ranges,
        timeline_start_frame=timeline_start_frame,
        total_duration=total_duration,
    )
    keep_ranges = _keep_frame_ranges_from_cuts(
        timeline_start_frame=timeline_start_frame,
        total_duration=total_duration,
        fps=conn.fps,
        cut_frame_ranges=cut_frame_ranges,
    )
    if not keep_ranges:
        return {"message": "Everything is removed.", "cut_ranges": normalized_ranges}

    source_rows = _snapshot_source_timeline_items(conn)
    max_tracks = {
        "video": max((row["track_index"] for row in source_rows if row["track_type"] == "video"), default=0),
        "audio": max((row["track_index"] for row in source_rows if row["track_type"] == "audio"), default=0),
    }

    new_timeline = _create_rewrite_timeline(conn, requested_name, timeline_start_tc)
    for track_type, required_count in max_tracks.items():
        if required_count:
            _ensure_timeline_track_count(new_timeline, track_type, required_count)

    planned_entries: List[Dict[str, Dict[str, Any]]] = []
    output_keep_start = timeline_start_frame
    media_type_map = {"video": 1, "audio": 2}
    for keep_start, keep_end in keep_ranges:
        for row in source_rows:
            overlap_start = max(int(row["start"]), keep_start)
            overlap_end = min(int(row["end"]), keep_end)
            if overlap_end <= overlap_start:
                continue
            timeline_offset = overlap_start - int(row["start"])
            timeline_duration = overlap_end - overlap_start
            source_fps = row.get("source_fps") if isinstance(row.get("source_fps"), (int, float)) else conn.fps
            source_in = int(row["source_start"]) + _timeline_to_source_frame_count(
                timeline_offset,
                source_fps=float(source_fps),
                timeline_fps=conn.fps,
            )
            source_duration = _timeline_to_source_frame_count(
                timeline_duration,
                source_fps=float(source_fps),
                timeline_fps=conn.fps,
            )
            source_out = source_in + source_duration
            record_frame = output_keep_start + (overlap_start - keep_start)
            request = {
                "mediaPoolItem": row["media_pool_item"],
                "startFrame": source_in,
                "endFrame": source_out,
                "recordFrame": record_frame,
                "trackIndex": int(row["track_index"]),
                "trackType": row["track_type"],
                "mediaType": media_type_map[row["track_type"]],
            }
            expected = {
                "track_type": row["track_type"],
                "track_index": int(row["track_index"]),
                "name": row["name"],
                "media_pool_item": row["media_pool_item"].GetName() if hasattr(row["media_pool_item"], "GetName") else None,
                "start": record_frame,
                "end": record_frame + timeline_duration,
                "duration": timeline_duration,
                "source_start": source_in,
                "source_end": source_out,
                "source_duration": source_duration,
                "source_fps": float(source_fps),
                "timeline_fps": float(conn.fps),
            }
            planned_entries.append(
                {
                    "request": request,
                    "expected": expected,
                }
            )
        output_keep_start += keep_end - keep_start

    planned_entries.sort(
        key=lambda entry: (
            int(entry["request"]["recordFrame"]),
            str(entry["request"]["trackType"]),
            int(entry["request"]["trackIndex"]),
        )
    )
    append_requests = [entry["request"] for entry in planned_entries]
    expected_segments = [entry["expected"] for entry in planned_entries]
    expected_item_counts = {
        "video": sum(1 for entry in append_requests if entry["trackType"] == "video"),
        "audio": sum(1 for entry in append_requests if entry["trackType"] == "audio"),
    }
    appended_count = _append_rewrite_requests(conn, append_requests)

    if hasattr(conn, "refresh"):
        conn.refresh()
    current_timeline = getattr(conn, "timeline", None) or new_timeline
    item_counts = _timeline_track_item_counts(current_timeline)
    segment_verification = _verify_rewrite_timeline_segments(current_timeline, expected_segments)
    count_verified = all(item_counts.get(track_type, 0) == expected for track_type, expected in expected_item_counts.items())
    verified = count_verified and bool(segment_verification.get("ok"))
    verification_status = "verified" if verified else "pending_manual"
    set_verification_status(verification_status)
    set_recoverability("not_applicable" if verified else "manual")

    try:
        project_timeline_count = conn.project.GetTimelineCount()
    except Exception:
        project_timeline_count = None

    return {
        "new_timeline": current_timeline.GetName() if hasattr(current_timeline, "GetName") else requested_name,
        "ranges_removed": len(cut_frame_ranges),
        "clips_assembled": appended_count,
        "kept_ranges": len(keep_ranges),
        "edl_path": None,
        "rewrite_engine": "native_append",
        "verification": {
            "status": verification_status,
            "current_timeline": current_timeline.GetName() if hasattr(current_timeline, "GetName") else requested_name,
            "track_counts": {
                "video": max_tracks["video"],
                "audio": max_tracks["audio"],
            },
            "item_counts": item_counts,
            "expected_item_counts": expected_item_counts,
            "item_count_check": count_verified,
            "segment_checks": segment_verification,
            "project_timeline_visible": project_timeline_count is None or project_timeline_count > 0,
            "project_timeline_count": project_timeline_count,
        },
    }


def silence_cut(
    conn,
    threshold_db: float = -40.0,
    min_silence: float = 0.5,
    padding: float = 0.1,
    new_timeline_name: Optional[str] = None,
    wav_path: str = "/tmp/resolve_silence_cut.wav",
    auto_threshold: bool = False,
) -> Dict[str, Any]:
    """
    Create a new timeline with silent segments removed.

    Workflow:
    1. Detect silence on the active timeline audio
    2. Build keep ranges in timeline time
    3. Materialize a new timeline with native video/audio AppendToTimeline calls
    4. Verify the rewritten timeline by track/item readback
    """
    previous_page = None
    resolve = getattr(conn, "resolve", None)
    get_current_page = getattr(resolve, "GetCurrentPage", None)
    open_page = getattr(resolve, "OpenPage", None)
    if callable(get_current_page):
        try:
            previous_page = get_current_page()
        except Exception:
            previous_page = None

    try:
        calibration = None
        effective_threshold_db = threshold_db
        if auto_threshold:
            from ..core.silence_calibration import calibrate_rendered_audio

            rendered_audio_path = render_timeline_audio_for_silence(conn, wav_path)
            calibration_result = calibrate_rendered_audio(
                rendered_audio_path,
                fallback_gate_db=threshold_db,
            )
            calibration = calibration_result.as_dict()
            if not calibration_result.usable:
                return {
                    "message": "Adaptive silence threshold could not be established; timeline was left unchanged.",
                    "segments": [],
                    "calibration": calibration,
                }
            effective_threshold_db = calibration_result.gate_db
            segments = detect_silence(rendered_audio_path, effective_threshold_db, min_silence)
        else:
            segments = detect_silence_on_timeline(conn, threshold_db, min_silence, wav_path)
        if not segments:
            return {
                "message": "No silence detected.",
                "segments": [],
                "threshold_db": effective_threshold_db,
                "calibration": calibration,
            }

        context = _timeline_time_context(conn)
        total_duration = float(context["total_duration"])

        cut_ranges: List[Tuple[float, float]] = []
        for seg in segments:
            seg_start = seg["start"]
            seg_end = seg.get("end", total_duration)
            cut_start = seg_start if seg_start <= 0 else seg_start + padding
            cut_end = seg_end if seg_end >= total_duration else seg_end - padding
            cut_start = max(0.0, cut_start)
            cut_end = min(total_duration, cut_end)
            if cut_end > cut_start:
                cut_ranges.append((cut_start, cut_end))

        if not cut_ranges:
            return {"message": "No silence remained after padding.", "segments": segments}

        requested_name = new_timeline_name or f"{conn.timeline.GetName()} silence-cut"
        data = _rewrite_timeline_from_cut_ranges(
            conn,
            cut_ranges,
            requested_name=requested_name,
            temp_prefix="resolve_silence_cut_",
        )
        if data.get("message") == "Everything is removed.":
            return {"message": "Everything is silent.", "segments": segments}

        return {
            "new_timeline": data["new_timeline"],
            "segments_removed": data["ranges_removed"],
            "clips_assembled": data["clips_assembled"],
            "non_silent_ranges": data["kept_ranges"],
            "edl_path": data["edl_path"],
            "verification": data["verification"],
            "threshold_db": effective_threshold_db,
            "calibration": calibration,
        }
    except Exception:
        if previous_page and callable(open_page):
            try:
                current_page = get_current_page() if callable(get_current_page) else None
            except Exception:
                current_page = None
            if current_page and current_page != previous_page:
                try:
                    open_page(previous_page)
                except Exception:
                    pass
        raise


# ---------------------------------------------------------------------------
# From-markers
# ---------------------------------------------------------------------------

def split_by_markers(conn, new_timeline_name: Optional[str] = None) -> Dict[str, Any]:
    """Split timeline at every marker, creating sub-clips in a new timeline."""
    markers = conn.timeline.GetMarkers()
    if not markers:
        raise APICallFailed("No markers on the current timeline.")

    marker_frames = sorted(int(f) for f in markers.keys())

    items = conn.timeline.GetItemListInTrack("video", 1) or []
    if not items:
        raise APICallFailed("No video clips on track 1.")

    # Build ranges: [timeline_start … marker1, marker1 … marker2, …, markerN … end]
    try:
        start_frame = int(conn.timeline.GetStartFrame()) if hasattr(conn.timeline, "GetStartFrame") else int(items[0].GetStart())
    except Exception:
        start_frame = int(items[0].GetStart())

    last_item = items[-1]
    end_frame = int(last_item.GetEnd())

    boundaries = [start_frame] + marker_frames + [end_frame]

    clip_infos = []
    for i in range(len(boundaries) - 1):
        seg_start = boundaries[i]
        seg_end = boundaries[i + 1]
        if seg_end <= seg_start:
            continue

        for item in items:
            cs = int(item.GetStart())
            ce = int(item.GetEnd())
            if cs >= seg_end or ce <= seg_start:
                continue

            mpi = item.GetMediaPoolItem() if hasattr(item, "GetMediaPoolItem") else None
            if not mpi:
                continue

            left_offset = 0
            try:
                left_offset = int(item.GetLeftOffset())
            except Exception:
                pass

            actual_start = max(cs, seg_start)
            actual_end = min(ce, seg_end)
            source_in = left_offset + (actual_start - cs)
            source_out = left_offset + (actual_end - cs)

            clip_infos.append({
                "mediaPoolItem": mpi,
                "startFrame": source_in,
                "endFrame": source_out,
            })

    tl_name = new_timeline_name or f"{conn.timeline.GetName()}_markers"
    new_tl = conn.media_pool.CreateTimelineFromClips(tl_name, clip_infos)
    if not new_tl:
        raise APICallFailed("CreateTimelineFromClips failed.")

    return {
        "new_timeline": tl_name,
        "markers": len(marker_frames),
        "segments": len(boundaries) - 1,
        "clips": len(clip_infos),
    }


def _project_timeline_names(conn) -> tuple[list[str] | None, int | None]:
    project = getattr(conn, "project", None)
    if not project:
        return None, None
    count_getter = getattr(project, "GetTimelineCount", None)
    timeline_getter = getattr(project, "GetTimelineByIndex", None)
    if not callable(count_getter) or not callable(timeline_getter):
        return None, None
    try:
        count = int(count_getter() or 0)
    except Exception:
        return None, None
    names: list[str] = []
    for index in range(1, count + 1):
        try:
            timeline = timeline_getter(index)
            name = timeline.GetName() if timeline and hasattr(timeline, "GetName") else None
        except Exception:
            name = None
        if name:
            names.append(str(name))
    return names, count
