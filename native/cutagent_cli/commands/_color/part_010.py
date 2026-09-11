from __future__ import annotations

from ..core import render_engine


def _mark_color_render_unverified(data, *, readback_source: str = "readback") -> dict:
    if not isinstance(data, dict):
        return data
    previous = data.get("verification") if isinstance(data.get("verification"), dict) else {}
    readback_status = str(previous.get("status") or "verified")
    data["verification"] = {
        **previous,
        "status": "render_unverified",
        "readback_status": readback_status,
        "readback_source": readback_source,
        "readback_verified": readback_status in {"verified", "db_readback_verified", "matched"},
        "render_proof_status": "not_performed",
        "render_proof_required": True,
        "note": (
            "Command readback matched the requested state, but no rendered-frame proof was performed. "
            "Do not treat this as visually verified until a rendered frame changes as expected."
        ),
    }
    set_verification_status("render_unverified")
    set_recoverability("manual")
    return data


def _color_timeline_start_frame(conn) -> int:
    try:
        return int(conn.timeline.GetStartFrame()) if hasattr(conn.timeline, "GetStartFrame") else int(getattr(conn, "start_frame", 0) or 0)
    except Exception:
        return int(getattr(conn, "start_frame", 0) or 0)


def _absolute_timeline_frame(conn, frame: object, *, timeline_start: int) -> int:
    value = int(frame)
    return value if value >= int(timeline_start) else int(timeline_start) + value


def _timeline_item_bounds(conn, item: object) -> tuple[int, int] | None:
    timeline_start = _color_timeline_start_frame(conn)

    try:
        raw_start = item.GetStart() if hasattr(item, "GetStart") else getattr(item, "start")
        raw_end = item.GetEnd() if hasattr(item, "GetEnd") else getattr(item, "end")
    except Exception:
        return None

    try:
        start = _absolute_timeline_frame(conn, raw_start, timeline_start=timeline_start)
        end = _absolute_timeline_frame(conn, raw_end, timeline_start=timeline_start)
    except Exception:
        return None
    if end <= start:
        return None
    return start, end


def _resolve_color_render_proof_target(
    conn,
    clip_name: Optional[str],
    *,
    track: int | None = None,
    at: str | None = None,
    frame_offset: int = 0,
) -> dict[str, object]:
    original_playhead = timeline_ops.get_playhead(conn)
    target: dict[str, object] = {
        "clip": clip_name,
        "track": track,
        "at": at,
        "original_playhead": original_playhead,
        "position": None,
        "target_frame": None,
        "target_timecode": None,
        "target_source": "current_playhead",
        "frame_offset": int(frame_offset),
    }
    if not clip_name and track is None and at is None:
        if original_playhead and original_playhead.get("timecode"):
            target_frame = original_playhead.get("frame")
            if target_frame is not None:
                from ..utils.timecode import seconds_to_timecode

                try:
                    current_item = clip_ops.get_current_item(conn)
                    bounds = _timeline_item_bounds(conn, current_item) if current_item is not None else None
                    original_frame = int(target_frame)
                    if bounds and bounds[0] <= original_frame < bounds[1]:
                        target["target_clip_bounds"] = {"start": bounds[0], "end": bounds[1]}
                except Exception as exc:
                    target["target_clip_bounds_warning"] = str(exc)
                target_frame = max(0, int(target_frame) + int(frame_offset))
                bounds_payload = target.get("target_clip_bounds")
                if isinstance(bounds_payload, dict):
                    target_frame = max(int(bounds_payload["start"]), min(target_frame, int(bounds_payload["end"]) - 1))
                target_tc = seconds_to_timecode(target_frame / conn.fps, conn.fps)
                target["position"] = target_tc
                target["target_timecode"] = target_tc
                target["target_frame"] = target_frame
                if frame_offset:
                    target["target_source"] = "current_playhead_offset"
            else:
                target["position"] = str(original_playhead["timecode"])
                target["target_timecode"] = str(original_playhead["timecode"])
                target["target_frame"] = target_frame
        return target

    try:
        from ..core.db_timeline_selection import resolve_video_group
        from ..utils.timecode import seconds_to_timecode

        item = resolve_video_group(conn, clip_name=clip_name, track=track, at=at)["video"]
        timeline_start = _color_timeline_start_frame(conn)
        if at is not None:
            from ..utils.time_ref import parse_record_frame

            target_frame = parse_record_frame(str(at), conn.fps, timeline_start) + int(frame_offset)
        else:
            local_mid = int(item.start) + max(0, min(int(item.duration) // 2, max(int(item.duration) - 1, 0)))
            target_frame = _absolute_timeline_frame(conn, local_mid, timeline_start=timeline_start) + int(frame_offset)
        bounds = _timeline_item_bounds(conn, item)
        if bounds:
            target_frame = max(bounds[0], min(target_frame, bounds[1] - 1))
        target_tc = seconds_to_timecode(target_frame / conn.fps, conn.fps)
        target.update(
            {
                "clip": clip_name or item.name,
                "position": target_tc,
                "target_frame": target_frame,
                "target_timecode": target_tc,
                "target_source": (
                    "target_clip_selector_position" if at is not None else "target_clip_midpoint"
                ),
                "target_clip": {
                    "id": item.item_id,
                    "name": item.name,
                    "track_type": item.track_type,
                    "track_index": item.track_index,
                    "start": item.start,
                    "duration": item.duration,
                    "end": item.end,
                },
            }
        )
    except Exception as exc:
        if clip_name or track is not None or at is not None:
            raise
        if original_playhead and original_playhead.get("timecode"):
            target["position"] = str(original_playhead["timecode"])
            target["target_timecode"] = str(original_playhead["timecode"])
            target["target_frame"] = original_playhead.get("frame")
        target["target_source"] = "current_playhead_fallback"
        target["target_warning"] = {
            "message": "Could not resolve named clip midpoint for render proof; using current playhead.",
            "error": str(exc),
        }
    return target


def _capture_color_render_proof_frame(conn, *, target: dict[str, object], path: Path) -> dict[str, object]:
    position = target.get("position")
    playhead = None
    if position:
        playhead = timeline_ops.set_playhead(conn, str(position), return_details=True)
    metadata = _export_color_page_frame_as_still(
        conn,
        resolved_path=path,
        requested_output_path=str(path),
    )
    rgb = _load_frame_rgb_array(path)
    return {
        "path": str(path),
        "visual_check_path": _workspace_relative_path(path),
        "metadata": metadata,
        "playhead": playhead or timeline_ops.get_playhead(conn),
        "rgb": rgb,
    }


def _exact_color_render_target_signature(target: dict[str, object]) -> dict[str, object]:
    target_clip = target.get("target_clip") if isinstance(target.get("target_clip"), dict) else {}
    return {
        "clip": target.get("clip"),
        "track": target.get("track"),
        "at": target.get("at"),
        "target_frame": target.get("target_frame"),
        "name": target_clip.get("name"),
        "id": target_clip.get("id"),
        "track_type": target_clip.get("track_type"),
        "track_index": target_clip.get("track_index"),
        "start": target_clip.get("start"),
        "duration": target_clip.get("duration"),
        "end": target_clip.get("end"),
    }


def _capture_color_proof_with_target_isolation(
    conn,
    *,
    target: dict[str, object],
    capture,
) -> dict[str, object]:
    clip_name = target.get("clip")
    track = target.get("track")
    at = target.get("at")
    if clip_name in (None, "") and track is None and at in (None, ""):
        return capture()

    from ..core import color_page_gui_route

    expected = _exact_color_render_target_signature(target)
    with color_page_gui_route._isolated_primary_gui_target(
        conn,
        clip_name=None if clip_name in (None, "") else str(clip_name),
        track=None if track is None else int(track),
        at=None if at in (None, "") else str(at),
    ) as isolation_context:
        verified_target = _resolve_color_render_proof_target(
            conn,
            None if clip_name in (None, "") else str(clip_name),
            track=None if track is None else int(track),
            at=None if at in (None, "") else str(at),
            frame_offset=int(target.get("frame_offset") or 0),
        )
        verified = _exact_color_render_target_signature(verified_target)
        if verified != expected:
            raise ColorRenderProofFailed(
                "Color render proof target changed before frame capture.",
                details={
                    "reason": "render_proof_target_changed",
                    "expected_target": expected,
                    "verified_target": verified,
                },
            )
        active_target_check = color_page_gui_route._verify_active_primary_gui_target(
            conn,
            isolation_context,
            phase="before_render_proof_capture",
        )
        captured = capture()

    captured["verified_target"] = verified
    captured["active_target_check"] = active_target_check
    captured["target_isolation"] = isolation_context.get("track_isolation")
    return captured


def _seek_color_render_proof_playhead(conn, proof: dict[str, object], *, frame_offset: int = 0) -> dict[str, object] | None:
    target = proof.get("target") if isinstance(proof.get("target"), dict) else {}
    original_playhead = target.get("original_playhead") if isinstance(target, dict) else None
    if isinstance(original_playhead, dict) and original_playhead.get("timecode"):
        if frame_offset:
            from ..utils.timecode import seconds_to_timecode

            anchor_frame = target.get("target_frame")
            if anchor_frame is None:
                anchor_frame = original_playhead.get("frame")
            if anchor_frame is None:
                return None
            target_frame = max(0, int(anchor_frame) + int(frame_offset))
            bounds_payload = target.get("target_clip_bounds") if isinstance(target, dict) else None
            if isinstance(bounds_payload, dict):
                target_frame = max(int(bounds_payload["start"]), min(target_frame, int(bounds_payload["end"]) - 1))
            target_tc = seconds_to_timecode(target_frame / conn.fps, conn.fps)
            return timeline_ops.set_playhead(conn, target_tc, return_details=True)
        return timeline_ops.set_playhead(conn, str(original_playhead["timecode"]), return_details=True)
    return None


def _restore_color_render_proof_playhead(conn, proof: dict[str, object]) -> dict[str, object] | None:
    return _seek_color_render_proof_playhead(conn, proof, frame_offset=0)


_COLOR_DELIVER_REQUIRED_SETTING_KEYS = (
    "TargetDir",
    "CustomName",
    "ExportVideo",
    "ExportAudio",
    "MarkIn",
    "MarkOut",
)


def _color_deliver_snapshot_gaps(snapshot: object) -> list[str]:
    if not isinstance(snapshot, dict):
        return ["snapshot"]
    gaps = [key for key in ("format", "codec", "render_mode") if snapshot.get(key) is None]
    settings = snapshot.get("settings")
    if not isinstance(settings, dict) or settings.get("settings_api_available") is not True:
        gaps.append("settings_api_available")
        settings = settings if isinstance(settings, dict) else {}
    gaps.extend(f"settings.{key}" for key in _COLOR_DELIVER_REQUIRED_SETTING_KEYS if key not in settings)
    return gaps


def _snapshot_color_deliver_render_context(conn) -> dict[str, object]:
    snapshotter = getattr(render_engine, "_snapshot_render_context", None)
    if not callable(snapshotter):
        raise ColorRenderProofFailed(
            "Deliver render proof cannot snapshot the current render context.",
            details={"reason": "deliver_render_context_snapshot_unavailable"},
        )
    try:
        snapshot = snapshotter(conn)
    except Exception as exc:
        raise ColorRenderProofFailed(
            "Deliver render proof could not read the current render context.",
            details={"reason": "deliver_render_context_snapshot_failed", "error": str(exc)},
        ) from exc
    gaps = _color_deliver_snapshot_gaps(snapshot)
    if gaps:
        raise ColorRenderProofFailed(
            "Deliver render proof requires a complete render-context baseline before mutation.",
            details={"reason": "deliver_render_context_snapshot_incomplete", "missing": gaps},
        )
    return dict(snapshot)


def _restore_color_deliver_render_context(conn, snapshot: dict[str, object]) -> dict[str, object]:
    restorer = getattr(render_engine, "_restore_render_context", None)
    snapshotter = getattr(render_engine, "_snapshot_render_context", None)
    status = {
        "attempted": callable(restorer),
        "ok": None,
        "snapshot_available": bool(snapshot),
        "readback_attempted": callable(snapshotter),
    }
    if not callable(restorer):
        status["ok"] = False
        status["error"] = "Render context restore helper is unavailable."
        return status
    try:
        restorer(conn, snapshot)
    except Exception as exc:
        status["ok"] = False
        status["error"] = str(exc)
        return status
    if not callable(snapshotter):
        status["ok"] = False
        status["error"] = "Render context readback helper is unavailable."
        return status
    try:
        readback = snapshotter(conn)
    except Exception as exc:
        status["ok"] = False
        status["readback_error"] = str(exc)
        return status
    readback_gaps = _color_deliver_snapshot_gaps(readback)
    if readback_gaps:
        status["ok"] = False
        status["readback_missing"] = readback_gaps
        return status

    ignored_setting_keys = {
        "source",
        "settings_api_available",
        "render_queue_count",
        "format",
        "Format",
        "format_name",
        "FormatName",
        "format_label",
        "codec",
        "Codec",
        "codec_name",
        "CodecName",
        "codec_label",
        "render_mode",
        "render_mode_description",
    }
    mismatches: list[dict[str, object]] = []
    for key in ("format", "codec", "render_mode"):
        expected = snapshot.get(key)
        actual = readback.get(key) if isinstance(readback, dict) else None
        if expected is not None and actual != expected:
            mismatches.append({"field": key, "expected": expected, "actual": actual})
    expected_settings = snapshot.get("settings") if isinstance(snapshot.get("settings"), dict) else {}
    actual_settings = readback.get("settings") if isinstance(readback, dict) and isinstance(readback.get("settings"), dict) else {}
    for key, expected in expected_settings.items():
        if key in ignored_setting_keys and key not in _COLOR_DELIVER_REQUIRED_SETTING_KEYS:
            continue
        actual = actual_settings.get(key)
        if actual != expected:
            mismatches.append({"field": f"settings.{key}", "expected": expected, "actual": actual})
    status["mismatches"] = mismatches
    status["ok"] = not mismatches
    return status


def _delete_color_deliver_render_job(conn, job_id: object) -> dict[str, object]:
    status = {"attempted": False, "ok": None, "job_id": None if job_id is None else str(job_id)}
    if job_id in (None, ""):
        return status
    deleter = getattr(getattr(conn, "project", None), "DeleteRenderJob", None)
    if not callable(deleter):
        status["attempted"] = False
        return status
    status["attempted"] = True
    try:
        result = deleter(str(job_id))
        status["api_ok"] = result is True
        status["api_result"] = result
    except Exception as exc:
        status["ok"] = False
        status["error"] = str(exc)
        return status
    list_jobs = getattr(getattr(conn, "project", None), "GetRenderJobList", None)
    if not callable(list_jobs):
        status["ok"] = False
        status["error"] = "Render job cleanup readback is unavailable."
        return status
    try:
        remaining = list_jobs()
        if not isinstance(remaining, list) or any(not isinstance(row, dict) for row in remaining):
            status["ok"] = False
            status["readback_error"] = "Render job list readback was not a valid list of jobs."
            return status
        remaining_ids = {
            str(row.get("JobId") or row.get("JobID") or row.get("jobId") or row.get("job_id"))
            for row in remaining
        }
        status["verified_absent"] = str(job_id) not in remaining_ids
        status["ok"] = bool(status["api_ok"] and status["verified_absent"])
    except Exception as exc:
        status["ok"] = False
        status["readback_error"] = str(exc)
    return status


def _assert_color_deliver_cleanup_verified(
    *,
    restore_status: dict[str, object],
    cleanup_status: dict[str, object],
    job_id: object,
    original_error: BaseException | None,
) -> None:
    cleanup_required = job_id not in (None, "")
    if restore_status.get("ok") is True and (not cleanup_required or cleanup_status.get("ok") is True):
        return
    raise ColorRenderProofFailed(
        "Color Deliver render proof could not restore and verify the user's render context.",
        details={
            "reason": "deliver_render_context_restore_unverified",
            "render_context_restore": restore_status,
            "render_job_cleanup": cleanup_status,
            "job_cleanup_required": cleanup_required,
            "original_error": str(original_error) if original_error is not None else None,
        },
    ) from original_error


def _find_color_deliver_render_output(conn, *, target_dir: Path, base_name: str, job_id: object) -> Path:
    candidates: list[Path] = []
    list_jobs = getattr(getattr(conn, "project", None), "GetRenderJobList", None)
    if callable(list_jobs):
        try:
            for job in list_jobs() or []:
                if not isinstance(job, dict):
                    continue
                current_id = job.get("JobId") or job.get("JobID") or job.get("jobId") or job.get("job_id")
                if job_id not in (None, "") and str(current_id) != str(job_id):
                    continue
                output_name = job.get("OutputFilename") or job.get("OutputFileName") or job.get("Filename")
                if output_name:
                    output_path = Path(str(output_name))
                    candidates.append(output_path if output_path.is_absolute() else target_dir / output_path)
        except Exception:
            pass

    candidates.extend(
        [
            target_dir / f"{base_name}.png",
            target_dir / f"{base_name}.mov",
            target_dir / f"{base_name}.mp4",
        ]
    )
    candidates.extend(sorted(target_dir.glob(f"{base_name}*")))
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise APICallFailed(
        "Deliver render proof completed but no output file was found.",
        details={
            "target_dir": str(target_dir),
            "base_name": base_name,
            "job_id": None if job_id is None else str(job_id),
            "directory_listing": sorted(path.name for path in target_dir.iterdir()) if target_dir.is_dir() else [],
        },
    )


def _capture_color_deliver_proof_frame(conn, *, target: dict[str, object], proof_dir: Path, stem: str) -> dict[str, object]:
    raw_target_frame = target.get("target_frame")
    if raw_target_frame is None:
        raise APICallFailed(
            "Deliver render proof requires a resolved target frame.",
            details={"target": target, "stem": stem},
        )
    try:
        target_frame = int(raw_target_frame)
    except (TypeError, ValueError) as exc:
        raise APICallFailed(
            "Deliver render proof target frame is invalid.",
            details={"target_frame": raw_target_frame, "target": target, "stem": stem},
        ) from exc

    target_dir = proof_dir / "deliver" / stem
    target_dir.mkdir(parents=True, exist_ok=True)
    base_name = f"{stem}_{target_frame}"
    snapshot = _snapshot_color_deliver_render_context(conn)
    job_id = None
    capture: dict[str, object] | None = None
    primary_error: BaseException | None = None
    try:
        render_engine.set_render_settings(
            conn,
            target=str(target_dir),
            format="PNG",
            codec="RGB8",
            name=base_name,
            video=True,
            audio=False,
        )
        render_job = render_engine.render_custom_range(
            conn,
            mark_in=f"{target_frame}f",
            mark_out=f"{target_frame}f",
            start=True,
            wait=True,
            range_domain="absolute",
        )
        job_id = render_job.get("job_id") if isinstance(render_job, dict) else None
        output_path = _find_color_deliver_render_output(
            conn,
            target_dir=target_dir,
            base_name=base_name,
            job_id=job_id,
        )
        rgb = _load_frame_rgb_array(output_path)
        capture = {
            "path": str(output_path),
            "visual_check_path": _workspace_relative_path(output_path),
            "metadata": _image_file_metadata(output_path),
            "render_job": render_job,
            "range": {
                "domain": "absolute",
                "mark_in": f"{target_frame}f",
                "mark_out": f"{target_frame}f",
                "target_frame": target_frame,
            },
            "rgb": rgb,
        }
        return capture
    except BaseException as exc:
        primary_error = exc
        raise
    finally:
        restore_status = _restore_color_deliver_render_context(conn, snapshot)
        cleanup_status = _delete_color_deliver_render_job(conn, job_id)
        if capture is not None:
            capture["render_context_restore"] = restore_status
            capture["render_job_cleanup"] = cleanup_status
        _assert_color_deliver_cleanup_verified(
            restore_status=restore_status,
            cleanup_status=cleanup_status,
            job_id=job_id,
            original_error=primary_error,
        )


def _begin_color_render_proof(
    conn,
    *,
    clip_name: Optional[str],
    track: int | None = None,
    at: str | None = None,
    route: str,
    frame_offset: int = 0,
    restore_after_capture: bool = False,
    restore_after_capture_frame_offset: int = 0,
    force_seek_target: bool = False,
    deliver_proof: bool = False,
) -> dict[str, object]:
    proof_dir = Path(tempfile.mkdtemp(prefix="cutagent_color_render_proof_"))
    target = _resolve_color_render_proof_target(
        conn,
        clip_name,
        track=track,
        at=at,
        frame_offset=int(frame_offset),
    )
    if force_seek_target and target.get("position") and target.get("target_source") == "current_playhead":
        target["target_source"] = "current_playhead_forced"
    before = _capture_color_proof_with_target_isolation(
        conn,
        target=target,
        capture=lambda: _capture_color_render_proof_frame(
            conn,
            target=target,
            path=proof_dir / "before.png",
        ),
    )
    proof = {
        "route": route,
        "proof_dir": str(proof_dir),
        "target": target,
        "before": before,
    }
    if deliver_proof:
        proof["deliver_before"] = _capture_color_proof_with_target_isolation(
            conn,
            target=target,
            capture=lambda: _capture_color_deliver_proof_frame(
                conn,
                target=target,
                proof_dir=proof_dir,
                stem="before",
            ),
        )
    if restore_after_capture:
        try:
            proof["restored_after_before"] = _seek_color_render_proof_playhead(
                conn,
                proof,
                frame_offset=int(restore_after_capture_frame_offset),
            )
        except Exception as exc:
            proof["restore_after_before_warning"] = str(exc)
    return proof


def _complete_color_render_proof(
    conn,
    proof: dict[str, object],
    *,
    partial_result: Optional[dict[str, object]] = None,
    min_changed_pixel_percent: float = 0.0,
    min_mean_abs_diff: float = 0.0,
    min_max_channel_abs_diff: int = 1,
) -> dict[str, object]:
    proof_dir = Path(str(proof["proof_dir"]))
    target = proof["target"] if isinstance(proof.get("target"), dict) else {}
    after = _capture_color_proof_with_target_isolation(
        conn,
        target=target,
        capture=lambda: _capture_color_render_proof_frame(
            conn,
            target=target,
            path=proof_dir / "after.png",
        ),
    )
    final_composite = _capture_color_render_proof_frame(
        conn,
        target=target,
        path=proof_dir / "after-final-composite.png",
    )
    before = proof["before"] if isinstance(proof.get("before"), dict) else {}
    comparison = _compare_before_after_pixels(before["rgb"], after["rgb"])
    changed_pixel_count = int(comparison.get("changed_pixel_count") or 0)
    changed_pixel_percent = float(comparison.get("changed_pixel_percent") or 0.0)
    mean_abs_diff = float(comparison.get("mean_abs_diff") or 0.0)
    max_channel_abs_diff = int(comparison.get("max_channel_abs_diff") or 0)
    minimums = {
        "min_changed_pixel_percent": float(min_changed_pixel_percent),
        "min_mean_abs_diff": float(min_mean_abs_diff),
        "min_max_channel_abs_diff": int(min_max_channel_abs_diff),
    }
    meets_minimums = (
        changed_pixel_count > 0
        and changed_pixel_percent >= float(min_changed_pixel_percent)
        and mean_abs_diff >= float(min_mean_abs_diff)
        and max_channel_abs_diff >= int(min_max_channel_abs_diff)
    )
    color_page_status = "verified" if meets_minimums else "failed"
    render_proof = {
        "status": color_page_status,
        "proof_kind": (
            "color_page_still_deliver_and_final_composite"
            if isinstance(proof.get("deliver_before"), dict)
            else "color_page_still_and_final_composite"
        ),
        "route": proof.get("route"),
        "target": target,
        "proof_dir": str(proof_dir),
        "before": {
            "path": before.get("path"),
            "visual_check_path": before.get("visual_check_path"),
            "metadata": before.get("metadata"),
            "playhead": before.get("playhead"),
            "verified_target": before.get("verified_target"),
            "active_target_check": before.get("active_target_check"),
            "target_isolation": before.get("target_isolation"),
        },
        "after": {
            "path": after.get("path"),
            "visual_check_path": after.get("visual_check_path"),
            "metadata": after.get("metadata"),
            "playhead": after.get("playhead"),
            "verified_target": after.get("verified_target"),
            "active_target_check": after.get("active_target_check"),
            "target_isolation": after.get("target_isolation"),
        },
        "final_composite": {
            "path": final_composite.get("path"),
            "visual_check_path": final_composite.get("visual_check_path"),
            "metadata": final_composite.get("metadata"),
            "playhead": final_composite.get("playhead"),
            "overlay_tracks_restored_before_capture": True,
        },
        "comparison": comparison,
        "minimums": minimums,
        "color_page": {
            "status": color_page_status,
            "comparison": comparison,
            "minimums": minimums,
        },
    }
    for passthrough_key in ("tracking_proof_strategy",):
        if passthrough_key in proof:
            render_proof[passthrough_key] = proof[passthrough_key]
    deliver_before = proof.get("deliver_before") if isinstance(proof.get("deliver_before"), dict) else None
    if deliver_before is not None:
        render_proof["deliver"] = {
            "status": "not_performed",
            "before": {
                "path": deliver_before.get("path"),
                "visual_check_path": deliver_before.get("visual_check_path"),
                "metadata": deliver_before.get("metadata"),
                "render_job": deliver_before.get("render_job"),
                "range": deliver_before.get("range"),
                "render_context_restore": deliver_before.get("render_context_restore"),
                "render_job_cleanup": deliver_before.get("render_job_cleanup"),
                "verified_target": deliver_before.get("verified_target"),
                "active_target_check": deliver_before.get("active_target_check"),
                "target_isolation": deliver_before.get("target_isolation"),
            },
        }
    original_playhead = target.get("original_playhead") if isinstance(target, dict) else None
    if render_proof["status"] != "verified":
        if changed_pixel_count <= 0:
            reason = "render_proof_no_pixel_change"
            message = "Color command completed, but exported before/after frames were pixel-identical."
        else:
            reason = "render_proof_below_visual_threshold"
            message = (
                "Color command completed, but exported before/after frames did not meet the "
                "minimum visual-difference proof threshold."
            )
        if isinstance(original_playhead, dict) and original_playhead.get("timecode"):
            try:
                render_proof["restored_playhead"] = _restore_color_render_proof_playhead(conn, proof)
            except Exception as exc:
                render_proof["restore_warning"] = str(exc)
        set_verification_status("failed")
        set_recoverability("manual")
        raise ColorRenderProofFailed(
            message,
            details={
                "reason": reason,
                "render_proof": render_proof,
                "partial_result": partial_result,
            },
        )

    if deliver_before is not None:
        deliver_after = _capture_color_proof_with_target_isolation(
            conn,
            target=target,
            capture=lambda: _capture_color_deliver_proof_frame(
                conn,
                target=target,
                proof_dir=proof_dir,
                stem="after",
            ),
        )
        deliver_comparison = _compare_before_after_pixels(deliver_before["rgb"], deliver_after["rgb"])
        deliver_status = "verified" if int(deliver_comparison.get("changed_pixel_count") or 0) > 0 else "failed"
        render_proof["deliver"] = {
            "status": deliver_status,
            "before": {
                "path": deliver_before.get("path"),
                "visual_check_path": deliver_before.get("visual_check_path"),
                "metadata": deliver_before.get("metadata"),
                "render_job": deliver_before.get("render_job"),
                "range": deliver_before.get("range"),
                "render_context_restore": deliver_before.get("render_context_restore"),
                "render_job_cleanup": deliver_before.get("render_job_cleanup"),
                "verified_target": deliver_before.get("verified_target"),
                "active_target_check": deliver_before.get("active_target_check"),
                "target_isolation": deliver_before.get("target_isolation"),
            },
            "after": {
                "path": deliver_after.get("path"),
                "visual_check_path": deliver_after.get("visual_check_path"),
                "metadata": deliver_after.get("metadata"),
                "render_job": deliver_after.get("render_job"),
                "range": deliver_after.get("range"),
                "render_context_restore": deliver_after.get("render_context_restore"),
                "render_job_cleanup": deliver_after.get("render_job_cleanup"),
                "verified_target": deliver_after.get("verified_target"),
                "active_target_check": deliver_after.get("active_target_check"),
                "target_isolation": deliver_after.get("target_isolation"),
            },
            "comparison": deliver_comparison,
            "decode_route": "ffmpeg_rawvideo_rgb24",
        }
        if deliver_status != "verified":
            render_proof["status"] = "failed"
            if isinstance(original_playhead, dict) and original_playhead.get("timecode"):
                try:
                    render_proof["restored_playhead"] = timeline_ops.set_playhead(
                        conn,
                        str(original_playhead["timecode"]),
                        return_details=True,
                    )
                except Exception as exc:
                    render_proof["restore_warning"] = str(exc)
            set_verification_status("failed")
            set_recoverability("manual")
            raise ColorRenderProofFailed(
                "Color command completed, but Deliver before/after render frames were pixel-identical.",
                details={
                    "reason": "deliver_render_proof_no_pixel_change",
                    "render_proof": render_proof,
                    "partial_result": partial_result,
                },
            )

    if isinstance(original_playhead, dict) and original_playhead.get("timecode"):
        try:
            render_proof["restored_playhead"] = timeline_ops.set_playhead(
                conn,
                str(original_playhead["timecode"]),
                return_details=True,
            )
        except Exception as exc:
            render_proof["restore_warning"] = str(exc)
    return render_proof
