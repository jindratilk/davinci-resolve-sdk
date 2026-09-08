def _camera_pip_property_correction(
    *,
    screen_error: dict[str, float],
    measurement: dict[str, Any],
    zoom: float,
) -> dict[str, Any]:
    image_size = measurement.get("image_size") or {}
    bbox = measurement.get("bbox") or {}
    estimated_width = max(1.0, float(image_size.get("width") or 0) * float(zoom))
    estimated_height = max(1.0, float(image_size.get("height") or 0) * float(zoom))
    sensitivity_x = max(0.001, float(bbox.get("width") or 0) / estimated_width)
    sensitivity_y = max(0.001, float(bbox.get("height") or 0) / estimated_height)
    return {
        "screen_error_px": {
            "x": _round_layout_value(screen_error["x"]),
            "y": _round_layout_value(screen_error["y"]),
        },
        "pan": _round_layout_value(screen_error["x"] / sensitivity_x),
        "tilt": _round_layout_value(screen_error["y"] / sensitivity_y),
        "sensitivity": {
            "x": _round_layout_value(sensitivity_x),
            "y": _round_layout_value(sensitivity_y),
        },
    }


def _camera_pip_frame_ref_for_item(conn: Any, item: Any, verify_frame: str | None) -> str:
    if verify_frame:
        return str(verify_frame)
    try:
        start = int(item.GetStart())
        end = int(item.GetEnd())
        sample = start + max(0, (end - start) // 2)
    except Exception:
        playhead = timeline_ops.get_playhead(conn)
        tc = playhead.get("timecode")
        if tc:
            return str(tc)
        sample = int(getattr(conn, "start_frame", 0) or 0)
    return seconds_to_timecode(sample / float(conn.fps), conn.fps)


def _camera_pip_render_verify_output_dir(output_dir: str | None) -> Path:
    if output_dir:
        path = Path(output_dir).expanduser()
        if not path.is_absolute():
            path = Path.cwd() / path
        path = path.resolve(strict=False)
        path.mkdir(parents=True, exist_ok=True)
        return path
    return Path(tempfile.mkdtemp(prefix="camera-pip-render-verify-"))


def _export_camera_pip_verification_frame(
    conn: Any,
    *,
    frame_ref: str,
    output_path: Path,
    error_message: str,
) -> dict[str, Any]:
    from . import timeline as timeline_commands

    original_playhead = timeline_ops.get_playhead(conn)
    target = timeline_ops.set_playhead(conn, frame_ref, return_details=True)
    restored = False
    restore_error: str | None = None
    metadata: dict[str, Any] = {}
    try:
        metadata = timeline_commands._export_current_frame_as_still(
            conn,
            resolved_path=output_path,
            requested_output_path=str(output_path),
            error_message=error_message,
        )
    finally:
        original_tc = original_playhead.get("timecode")
        if original_tc:
            try:
                timeline_ops.set_playhead(conn, str(original_tc), return_details=True)
                restored = True
            except Exception as exc:
                restore_error = str(exc)
    return {
        "requested_at": frame_ref,
        "output_path": str(output_path),
        "visual_check_path": timeline_commands._workspace_relative_path(output_path),
        "target": target,
        "restored_playhead": restored,
        "restore_warning": restore_error,
        "exported": True,
        "verified": True,
        **metadata,
    }


def _apply_camera_pip_transform_to_items(
    items: list[Any],
    *,
    zoom: float,
    pan: float,
    tilt: float,
    opacity: float,
) -> list[dict[str, object]]:
    return [
        _set_camera_pip_transform(item, zoom=zoom, pan=pan, tilt=tilt, opacity=opacity)
        for item in items
    ]


def _camera_pip_track_enabled(conn: Any, track_index: int) -> bool:
    getter = getattr(getattr(conn, "timeline", None), "GetIsTrackEnabled", None)
    if not callable(getter):
        raise APICallFailed(
            "Rendered camera PiP placement verification requires video track enabled-state readback.",
            details={"track_type": "video", "track_index": track_index},
        )
    try:
        state = getter("video", track_index)
    except Exception as exc:
        raise APICallFailed(
            "Cannot read camera PiP video track enabled state.",
            details={"track_type": "video", "track_index": track_index},
        ) from exc
    # Fail closed on indeterminate readback: DaVinci Resolve returns None on API
    # failure, and coercing that to False would record "disabled" as the
    # original state and leave an enabled camera track switched off after the
    # finally-restore.
    if isinstance(state, bool):
        return state
    if state in (0, 1):
        return bool(state)
    raise APICallFailed(
        "Camera PiP video track enabled-state readback returned an indeterminate value.",
        details={
            "track_type": "video",
            "track_index": track_index,
            "value": repr(state),
        },
    )


def _render_verify_and_tune_camera_pip(
    conn: Any,
    *,
    items: list[Any],
    camera_track: int,
    transform: dict[str, object],
    anchor: str,
    margin_px: float,
    verify_frame: str | None,
    output_dir: str | None,
    tolerance_px: float,
    iterations: int,
    diff_threshold: int,
) -> dict[str, Any]:
    if not items:
        raise ValidationError("Rendered PiP placement verification requires at least one camera item.")
    if anchor not in _CAMERA_PIP_ANCHORS:
        raise ValidationError("--verify-rendered-placement requires --anchor.", details={"anchor": anchor})

    output_base = _camera_pip_render_verify_output_dir(output_dir)
    sample_item = items[0]
    frame_ref = _camera_pip_frame_ref_for_item(conn, sample_item, verify_frame)
    max_iterations = max(1, min(5, int(iterations)))
    tolerance = max(0.0, float(tolerance_px))
    pan = float(transform["Pan"])
    tilt = float(transform["Tilt"])
    zoom = float(transform["ZoomX"])
    opacity = float(transform["Opacity"])
    steps: list[dict[str, Any]] = []
    background_path = output_base / "camera_pip_background.png"
    original_track_enabled = _camera_pip_track_enabled(conn, camera_track)
    track_state_changes: list[dict[str, Any]] = []

    try:
        track_state_changes.append(
            timeline_ops.set_track_enabled(
                conn,
                "video",
                camera_track,
                False,
                return_details=True,
            )
            or {}
        )
        background_export = _export_camera_pip_verification_frame(
            conn,
            frame_ref=frame_ref,
            output_path=background_path,
            error_message="Failed to export camera PiP background-only verification frame.",
        )
        track_state_changes.append(
            timeline_ops.set_track_enabled(
                conn,
                "video",
                camera_track,
                True,
                return_details=True,
            )
            or {}
        )

        final_measurement: dict[str, Any] | None = None
        final_check: dict[str, Any] | None = None
        for iteration in range(max_iterations):
            foreground_path = output_base / f"camera_pip_foreground_{iteration:02d}.png"
            foreground_export = _export_camera_pip_verification_frame(
                conn,
                frame_ref=frame_ref,
                output_path=foreground_path,
                error_message="Failed to export camera PiP foreground verification frame.",
            )
            measurement = _measure_changed_png_bbox(
                foreground_path,
                background_path,
                diff_threshold=diff_threshold,
            )
            margins = dict(measurement["edge_margins"])
            margins["_image_size"] = measurement["image_size"]
            margins["_bbox"] = measurement["bbox"]
            check = _camera_pip_margin_check(anchor, margins, target_margin=margin_px, tolerance_px=tolerance)
            error = _camera_pip_margin_error(anchor, margins, target_margin=margin_px)
            correction = _camera_pip_property_correction(
                screen_error=error,
                measurement=measurement,
                zoom=zoom,
            )
            step = {
                "iteration": iteration,
                "pan": _round_layout_value(pan),
                "tilt": _round_layout_value(tilt),
                "foreground_export": foreground_export,
                "measurement": measurement,
                "check": check,
                "correction": correction,
            }
            steps.append(step)
            final_measurement = measurement
            final_check = check
            if check["ok"]:
                break
            if iteration >= max_iterations - 1:
                break
            pan += float(correction["pan"])
            tilt += float(correction["tilt"])
            _apply_camera_pip_transform_to_items(items, zoom=zoom, pan=pan, tilt=tilt, opacity=opacity)

        final_transform = {"ZoomX": zoom, "ZoomY": zoom, "Pan": pan, "Tilt": tilt, "Opacity": opacity}
        return {
            "status": "verified" if final_check and final_check.get("ok") else "failed",
            "anchor": anchor,
            "target_margin_px": _round_layout_value(margin_px),
            "tolerance_px": _round_layout_value(tolerance),
            "frame_ref": frame_ref,
            "output_dir": str(output_base),
            "background_capture": {
                "method": "camera_track_disable",
                "track_type": "video",
                "track_index": camera_track,
                "original_track_enabled": original_track_enabled,
                "state_changes": track_state_changes,
            },
            "background_export": background_export,
            "steps": steps,
            "final_measurement": final_measurement,
            "final_check": final_check,
            "final_transform": {key: _round_layout_value(float(value)) for key, value in final_transform.items()},
            "iterations_used": len(steps),
        }
    finally:
        try:
            timeline_ops.set_track_enabled(
                conn,
                "video",
                camera_track,
                original_track_enabled,
                return_details=True,
            )
        except Exception as exc:
            raise APICallFailed(
                "Failed to restore camera PiP video track enabled state after rendered verification.",
                details={
                    "track_type": "video",
                    "track_index": camera_track,
                    "restore_enabled": original_track_enabled,
                },
            ) from exc


def _require_render_verified_camera_pip(
    conn: Any,
    *,
    items: list[Any],
    camera_track: int,
    transform: dict[str, object],
    anchor: str,
    margin_px: float,
    verify_frame: str | None,
    output_dir: str | None,
    tolerance_px: float,
    iterations: int,
    diff_threshold: int,
) -> dict[str, Any]:
    verification = _render_verify_and_tune_camera_pip(
        conn,
        items=items,
        camera_track=camera_track,
        transform=transform,
        anchor=anchor,
        margin_px=margin_px,
        verify_frame=verify_frame,
        output_dir=output_dir,
        tolerance_px=tolerance_px,
        iterations=iterations,
        diff_threshold=diff_threshold,
    )
    if verification.get("status") != "verified":
        raise APICallFailed(
            "Rendered camera PiP placement verification failed.",
            details={"rendered_placement_verification": verification},
        )
    return verification


def _ensure_camera_pip_video_tracks(conn: Any, *, required_track: int) -> dict[str, Any]:
    timeline = getattr(conn, "timeline", None)
    getter = getattr(timeline, "GetTrackCount", None)
    if not callable(getter):
        return {"status": "unavailable", "required_track": required_track, "added": 0}
    try:
        current = int(getter("video") or 0)
    except Exception as exc:
        raise APICallFailed("Cannot inspect video track count for camera PiP.", details={"track_type": "video"}) from exc
    initial = current
    added = 0
    stale_readbacks = 0
    while current < required_track:
        timeline_ops.add_track(conn, "video")
        added += 1
        try:
            refreshed = int(getter("video") or 0)
        except Exception:
            refreshed = current + 1
        if refreshed <= current:
            stale_readbacks += 1
        current = max(refreshed, current + 1)
    return {
        "status": "verified",
        "required_track": required_track,
        "initial_count": initial,
        "final_count": current,
        "added": added,
        "readback_stale_count": stale_readbacks,
    }


@app.command("social-crop")
@handle_errors
def social_crop(
    clip_name: Optional[str] = typer.Argument(None, help="Clip name (defaults to current timeline item)"),
    format_name: str = typer.Option("9:16", "--format", help="Social format: 9:16|1:1|4:5|16:9|vertical|square|portrait"),
    source_aspect: str = typer.Option("16:9", "--source-aspect", help="Source aspect ratio, e.g. 16:9 or 4:3"),
    pan: float = typer.Option(0.0, "--pan", "--position-x", help="DaVinci Resolve Pan value for horizontal reframing"),
    tilt: float = typer.Option(0.0, "--tilt", "--position-y", help="DaVinci Resolve Tilt value for vertical reframing"),
    zoom: Optional[float] = typer.Option(None, "--zoom", help="Override computed fill zoom"),
    all_clips: bool = typer.Option(False, "--all-clips", help="Apply to all video timeline items"),
    set_timeline: bool = typer.Option(True, "--set-timeline/--no-set-timeline", help="Set active timeline resolution to the selected social format"),
):
    """Apply a social-format crop/reframe using native timeline item transforms."""
    enforce_mutation_policy(
        "clip.transform",
        intended_engine="api_native",
        mutating=not is_dry_run(),
    )
    width, height, canonical_format = _resolve_social_crop_preset(format_name)
    target_aspect = width / height
    source_aspect_value = _parse_social_aspect(source_aspect)
    resolved_zoom = _social_crop_zoom(target_aspect=target_aspect, source_aspect=source_aspect_value, zoom=zoom)
    plan = {
        "format": canonical_format,
        "timeline_resolution": {"width": width, "height": height},
        "source_aspect": source_aspect,
        "target_aspect": round(target_aspect, 6),
        "zoom": resolved_zoom,
        "pan": pan,
        "tilt": tilt,
        "scope": "all_video_items" if all_clips else "current_or_named_clip",
        "clip": clip_name,
        "set_timeline": set_timeline,
        "route": "resolve_native_timeline_settings_and_item_transform",
    }
    if is_dry_run():
        output({"message": "DRY-RUN: Would apply social crop using native DaVinci Resolve timeline settings and clip transforms.", **plan})
        return

    conn = get_connection(require_timeline=True)
    timeline_update: dict[str, object] = {
        "requested": {"timelineResolutionWidth": str(width), "timelineResolutionHeight": str(height)},
        "status": "skipped",
        "verified": False,
        "readback": {},
        "attempts": [],
        "failed": [],
    }
    if set_timeline:
        timeline_update = _apply_social_timeline_resolution(conn, width=width, height=height)

    if all_clips:
        items = _timeline_video_items(conn)
        if not items:
            raise ValidationError("No video timeline items found for social crop.", details={"track_type": "video"})
    else:
        items = [clip_ops.cutagent_clip(conn, clip_name)]

    applied = []
    for index, item in enumerate(items, 1):
        props = _set_social_crop_transform(item, zoom=resolved_zoom, pan=pan, tilt=tilt)
        applied.append({"clip": _item_display_name(item, f"video_item_{index}"), "properties": props})

    if set_timeline and not timeline_update["verified"]:
        set_verification_status("pending_manual")
    else:
        set_verification_status("verified")

    output(
        {
            **plan,
            "timeline_update": timeline_update,
            "timeline_updates": timeline_update["requested"] if timeline_update["verified"] else {},
            "partial_success": bool(set_timeline and not timeline_update["verified"]),
            "affected_count": len(applied),
            "applied": applied,
        },
        title="Social Crop",
    )


@app.command("camera-pip")
@handle_errors
def camera_pip(
    camera_clip: str = typer.Argument(..., help="Camera clip to place as picture-in-picture"),
    background_clip: Optional[str] = typer.Option(None, "--background", help="Optional background/screen clip to append on track 1"),
    at: Optional[str] = typer.Option(None, "--at", help="Record-domain start position"),
    duration: Optional[str] = typer.Option(None, "--duration", help="Optional source duration for appended clips"),
    camera_track: int = typer.Option(2, "--camera-track", "--track", min=1, help="Video track for the PiP camera clip"),
    background_track: int = typer.Option(1, "--background-track", min=1, help="Video track for the optional background clip"),
    zoom: float = typer.Option(0.32, "--zoom", help="PiP zoom applied through native TimelineItem.SetProperty"),
    pan: float = typer.Option(0.62, "--pan", "--position-x", help="PiP horizontal position"),
    tilt: float = typer.Option(-0.56, "--tilt", "--position-y", help="PiP vertical position"),
    anchor: Optional[str] = typer.Option(None, "--anchor", help="Compute PiP Pan/Tilt from an anchor: top-left|top-right|bottom-left|bottom-right|center"),
    margin: Optional[float] = typer.Option(None, "--margin", help="Anchor edge margin in timeline pixels; default scales from 24 px at 1920x1080"),
    verify_placement: bool = typer.Option(False, "--verify-placement", help="Read back applied transform properties and include placement verification notes"),
    verify_rendered_placement: bool = typer.Option(
        False,
        "--verify-rendered-placement",
        help="Temporarily disable/restore the camera track, export background/foreground frames, measure the rendered PiP bbox, and tune Pan/Tilt",
    ),
    verify_frame: Optional[str] = typer.Option(None, "--verify-frame", help="Timeline position for rendered placement verification; default samples the camera item midpoint"),
    verify_output_dir: Optional[str] = typer.Option(None, "--verify-output-dir", help="Directory for rendered placement verification frames"),
    render_tolerance: float = typer.Option(4.0, "--render-tolerance", help="Rendered placement tolerance in pixels"),
    render_iterations: int = typer.Option(3, "--render-iterations", min=1, max=5, help="Maximum rendered placement measurement/tuning passes"),
    render_diff_threshold: int = typer.Option(8, "--render-diff-threshold", min=1, max=255, help="RGB diff threshold for detecting the PiP overlay against background"),
    corner_radius: float = typer.Option(0.12, "--corner-radius", help="Fusion RectangleMask CornerRadius; 0 disables rounded crop"),
    softness: float = typer.Option(0.002, "--softness", help="Fusion RectangleMask SoftEdge"),
    opacity: float = typer.Option(100.0, "--opacity", help="PiP opacity; no border is added by this command"),
    apply_existing: bool = typer.Option(
        False,
        "--apply-existing",
        help="Apply PiP transform to existing items on the camera track instead of appending new clips.",
    ),
):
    """Create a camera PiP using native DaVinci Resolve timeline and Fusion APIs only."""
    apply_existing_enabled = apply_existing is True
    anchor = anchor if isinstance(anchor, str) else None
    margin = margin if isinstance(margin, (int, float)) else None
    verify_placement_enabled = verify_placement is True
    verify_rendered_placement_enabled = verify_rendered_placement is True
    verify_frame = verify_frame if isinstance(verify_frame, str) else None
    verify_output_dir = verify_output_dir if isinstance(verify_output_dir, str) else None
    render_tolerance = float(render_tolerance) if isinstance(render_tolerance, (int, float)) else 4.0
    render_iterations = int(render_iterations) if isinstance(render_iterations, int) else 3
    render_diff_threshold = int(render_diff_threshold) if isinstance(render_diff_threshold, int) else 8
    normalized_anchor = _normalize_camera_pip_anchor(anchor)
    if camera_track < 1 or background_track < 1:
        raise ValidationError("Camera PiP track indexes must be 1 or greater.")
    if zoom <= 0:
        raise ValidationError("Camera PiP zoom must be greater than 0.", details={"zoom": zoom})
    if margin is not None and margin < 0:
        raise ValidationError("Camera PiP margin cannot be negative.", details={"margin": margin})
    if margin is not None and normalized_anchor is None:
        raise ValidationError("--margin requires --anchor.", details={"margin": margin})
    if verify_rendered_placement_enabled and normalized_anchor is None:
        raise ValidationError("--verify-rendered-placement requires --anchor.", details={"anchor": anchor})
    if render_tolerance < 0:
        raise ValidationError("Camera PiP render tolerance cannot be negative.", details={"render_tolerance": render_tolerance})
    if corner_radius < 0:
        raise ValidationError("Camera PiP corner radius cannot be negative.", details={"corner_radius": corner_radius})
    if softness < 0:
        raise ValidationError("Camera PiP softness cannot be negative.", details={"softness": softness})
    if opacity < 0 or opacity > 100:
        raise ValidationError("Camera PiP opacity must be between 0 and 100.", details={"opacity": opacity})

    source_end = duration if duration else None
    plan = {
        "action": "edit.camera_pip",
        "route": "resolve_native_existing_transform_fusion_mask"
        if apply_existing_enabled
        else "resolve_native_append_transform_fusion_mask",
        "engine_route": "api_native",
        "camera_clip": camera_clip,
        "background_clip": background_clip,
        "record_frame": at,
        "duration": duration,
        "camera_track": camera_track,
        "background_track": background_track,
        "transform": {"ZoomX": zoom, "ZoomY": zoom, "Pan": pan, "Tilt": tilt, "Opacity": opacity},
        "placement": {
            "mode": "anchor" if normalized_anchor else "manual",
            "anchor": normalized_anchor,
            "requested_margin_px": margin,
            "computed": False,
            "note": "Anchor placement is computed from live timeline resolution during execution."
            if normalized_anchor
            else "Manual Pan/Tilt values were requested.",
        },
        "verify_placement": verify_placement_enabled,
        "verify_rendered_placement": verify_rendered_placement_enabled,
        "rendered_placement_options": {
            "verify_frame": verify_frame,
            "verify_output_dir": verify_output_dir,
            "tolerance_px": render_tolerance,
            "iterations": render_iterations,
            "diff_threshold": render_diff_threshold,
        },
        "rounded_crop": {
            "tool": "RectangleMask",
            "corner_radius": corner_radius,
            "softness": softness,
            "preserve_rounded_crop": corner_radius > 0,
        },
        "border": {"enabled": False, "width": 0, "color": None},
        "forbidden_routes": ["ffmpeg_overlay", "generated_overlay_asset", "rendered_workaround"],
    }
    enforce_mutation_policy("clip.transform", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        output({"message": "DRY-RUN: Would create camera PiP through native DaVinci Resolve append/transform/Fusion mask only.", **plan})
        return

    conn = get_connection(require_timeline=True)
    if normalized_anchor:
        timeline_width, timeline_height = _timeline_resolution_for_camera_pip(conn)
        placement = _camera_pip_anchor_placement(
            anchor=normalized_anchor,
            width=timeline_width,
            height=timeline_height,
            zoom=zoom,
            margin=margin,
            strict_fit=not verify_rendered_placement_enabled,
        )
        pan = float(placement["transform"]["Pan"])
        tilt = float(placement["transform"]["Tilt"])
        plan["transform"] = {"ZoomX": zoom, "ZoomY": zoom, "Pan": pan, "Tilt": tilt, "Opacity": opacity}
        plan["placement"] = {**placement, "computed": True}
    placement_margin_px = float((plan.get("placement") or {}).get("margin_px") or 0.0)
    if apply_existing_enabled:
        try:
            existing_items = list(conn.timeline.GetItemListInTrack("video", camera_track) or [])
        except Exception as exc:
            raise APICallFailed(
                "Cannot inspect camera PiP track items.",
                details={"track_type": "video", "track_index": camera_track},
            ) from exc
        matched_items = [item for item in existing_items if _camera_pip_item_matches(item, camera_clip)]
        if not matched_items:
            raise ValidationError(
                "No existing camera PiP items matched on the requested track.",
                details={
                    "camera_clip": camera_clip,
                    "track_type": "video",
                    "track_index": camera_track,
                    "items_seen": len(existing_items),
                },
            )
        applied_items: list[dict[str, object]] = []
        rounded_results: list[dict[str, object]] = []
        transform = {"ZoomX": zoom, "ZoomY": zoom, "Pan": pan, "Tilt": tilt, "Opacity": opacity}
        for item in matched_items:
            item_transform = _set_camera_pip_transform(item, zoom=zoom, pan=pan, tilt=tilt, opacity=opacity)
            if corner_radius > 0:
                rounded_results.append(
                    _apply_camera_pip_rounded_crop(
                        item,
                        clip_name=str(getattr(item, "GetName", lambda: camera_clip)() or camera_clip),
                        radius=corner_radius,
                        softness=softness,
                    )
                )
            try:
                name = item.GetName()
            except Exception:
                name = None
            try:
                start = int(item.GetStart())
                end = int(item.GetEnd())
            except Exception:
                start = None
                end = None
            applied_item = {"name": name, "start": start, "end": end, "transform": item_transform}
            applied_items.append(applied_item)
        rendered_verification: dict[str, Any] | None = None
        if verify_rendered_placement_enabled and normalized_anchor:
            rendered_verification = _require_render_verified_camera_pip(
                conn,
                items=matched_items,
                camera_track=camera_track,
                transform=transform,
                anchor=normalized_anchor,
                margin_px=placement_margin_px,
                verify_frame=verify_frame,
                output_dir=verify_output_dir,
                tolerance_px=render_tolerance,
                iterations=render_iterations,
                diff_threshold=render_diff_threshold,
            )
            final_transform = rendered_verification["final_transform"]
            pan = float(final_transform["Pan"])
            tilt = float(final_transform["Tilt"])
            transform = {"ZoomX": zoom, "ZoomY": zoom, "Pan": pan, "Tilt": tilt, "Opacity": opacity}
            plan["transform"] = {key: _round_layout_value(float(value)) for key, value in transform.items()}
            for applied_item in applied_items:
                applied_item["transform"] = dict(plan["transform"])
        placement_verifications: list[dict[str, Any]] = []
        if verify_placement_enabled:
            for item, applied_item in zip(matched_items, applied_items):
                placement_verification = _verify_camera_pip_transform_properties(item, transform)
                placement_verifications.append(placement_verification)
                applied_item["placement_verification"] = placement_verification
        set_verification_status("verified" if rendered_verification else _camera_pip_verification_status(placement_verifications))
        output(
            {
                **plan,
                "mode": "apply_existing",
                "matched_count": len(matched_items),
                "applied_items": applied_items,
                **({"rendered_placement_verification": rendered_verification} if rendered_verification is not None else {}),
                "applied_rounded_crop": rounded_results
                if rounded_results
                else {"applied": False, "reason": "radius_disabled_or_preserve_existing"},
            },
            title="Camera PiP",
        )
        return

    appended: dict[str, object] = {}
    required_video_track = max(camera_track, background_track if background_clip else 0)
    track_setup = _ensure_camera_pip_video_tracks(conn, required_track=required_video_track)
    if background_clip:
        appended["background"] = media_pool.append_clip_to_timeline(
            conn,
            background_clip,
            at=at,
            track_type="video",
            track_index=background_track,
            source_end=source_end,
            return_details=True,
        )
    camera_item_name = f"{camera_clip} PiP"
    camera_append = media_pool.append_clip_to_timeline(
        conn,
        camera_clip,
        at=at,
        track_type="video",
        track_index=camera_track,
        source_end=source_end,
        name_after_append=camera_item_name,
        return_details=True,
    )
    appended["camera"] = camera_append
    camera_item = clip_ops.cutagent_clip(conn, camera_item_name)
    transform = _set_camera_pip_transform(camera_item, zoom=zoom, pan=pan, tilt=tilt, opacity=opacity)
    rounded_crop = _apply_camera_pip_rounded_crop(
        camera_item,
        clip_name=camera_clip,
        radius=corner_radius,
        softness=softness,
    )
    rendered_verification: dict[str, Any] | None = None
    if verify_rendered_placement_enabled and normalized_anchor:
        rendered_verification = _require_render_verified_camera_pip(
            conn,
            items=[camera_item],
            camera_track=camera_track,
            transform=transform,
            anchor=normalized_anchor,
            margin_px=placement_margin_px,
            verify_frame=verify_frame,
            output_dir=verify_output_dir,
            tolerance_px=render_tolerance,
            iterations=render_iterations,
            diff_threshold=render_diff_threshold,
        )
        transform = {
            key: _round_layout_value(float(value))
            for key, value in rendered_verification["final_transform"].items()
        }
        plan["transform"] = dict(transform)
    placement_verification = _verify_camera_pip_transform_properties(camera_item, transform) if verify_placement_enabled else None
    set_verification_status(
        "verified" if rendered_verification else _camera_pip_verification_status([placement_verification] if placement_verification else [])
    )
    output(
        {
            **plan,
            "track_setup": track_setup,
            "appended": appended,
            "applied_transform": transform,
            **({"placement_verification": placement_verification} if placement_verification is not None else {}),
            **({"rendered_placement_verification": rendered_verification} if rendered_verification is not None else {}),
            "applied_rounded_crop": rounded_crop,
        },
        title="Camera PiP",
    )


@app.command("from-edl")
@handle_errors
def from_edl(
    path: str = typer.Argument(..., help="Path to EDL file"),
):
    """Import and assemble a timeline from an EDL file."""
    set_execution_engine("api_native")
    set_capability_context("timeline.import_export", "supported")
    from ..core import edit_ops

    preflight = edit_ops.validate_edl_import_file(path)
    enforce_mutation_policy(
        "timeline.import_export",
        intended_engine="api_native",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        output(
            {
                **preflight,
                "would_import": True,
                "imported": False,
            },
            title="Import EDL Preview",
        )
        return
    conn = get_connection(require_timeline=False)

    import os

    result = edit_ops.import_edl(
        conn,
        preflight["path"],
        expected_timeline_name=os.getenv("CUTAGENT_SDK_EXPECTED_EDL_TIMELINE_NAME"),
    )
    output(result, title="Import EDL")



# ---------------------------------------------------------------------------
# Ripple Delete (EDL-based workaround)
# ---------------------------------------------------------------------------

@app.command("ripple-delete")
@handle_errors
def ripple_delete(
    at: str = typer.Option(..., "--at", help="Start timecode of segment to remove (HH:MM:SS:FF)"),
    duration: str = typer.Option(..., "--duration", help="Duration to remove (e.g., '5s', '00:00:05:00', '125f')"),
    fps: float = typer.Option(25.0, "--fps", help="Timeline frame rate"),
    edl_path: Optional[str] = typer.Option(None, "--edl", help="Use existing EDL instead of exporting"),
    timeline_name: Optional[str] = typer.Option(None, "--name", help="Name for the new timeline"),
):
    """Ripple-delete a segment: remove time range and close the gap.

    Workaround: exports timeline as EDL, removes the segment, closes the gap,
    and reimports as a new timeline.
    """
    set_execution_engine("workaround_setting")
    set_capability_context("timeline.import_export", "supported")
    enforce_mutation_policy(
        "timeline.import_export",
        intended_engine="workaround_setting",
        mutating=not is_dry_run(),
    )
    set_execution_engine("workaround_setting")
    from ..core import edl_ops
    from ..utils.timecode import parse_time_input
    import tempfile
    import os
    import re

    try:
        dur_seconds = parse_time_input(duration, fps)
    except ValidationError:
        raise
    except Exception as exc:
        raise ValidationError(
            "Cannot parse duration.",
            details={"duration": duration, "fps": fps},
            recoverability="not_applicable",
        ) from exc
    if dur_seconds <= 0:
        raise ValidationError(
            "Ripple-delete duration must be greater than zero.",
            details={"duration": duration, "duration_seconds": dur_seconds, "fps": fps},
            recoverability="not_applicable",
        )

    if edl_path:
        edl_path = os.path.abspath(os.path.expanduser(edl_path))
        if not os.path.exists(edl_path):
            raise ValidationError(
                "EDL file does not exist.",
                details={"path": edl_path},
                recoverability="not_applicable",
            )
        if not os.path.isfile(edl_path):
            raise ValidationError(
                "EDL path must be a file.",
                details={"path": edl_path},
                recoverability="not_applicable",
            )
        # Use provided EDL
        events = edl_ops.parse_edl(edl_path, fps)
    else:
        if is_dry_run():
            dry_run_message(f"Would ripple-delete {duration} at {at}")
            return
        # Export current timeline as EDL
        conn = get_connection(require_timeline=True)
        tl_name = conn.timeline.GetName()
        export_dir = tempfile.mkdtemp(prefix="resolve_ripple_")
        edl_path = os.path.join(export_dir, f"{tl_name}.edl")

        ok = conn.timeline.Export(edl_path, conn.resolve.EXPORT_EDL
            if hasattr(conn.resolve, "EXPORT_EDL") else "EDL")
        if not ok:
            # Fallback: try ExportToFile
            try:
                ok = conn.timeline.ExportToFile(edl_path, "EDL")
            except Exception:
                pass
        if not ok:
            from ..errors import APICallFailed
            raise APICallFailed(
                "Failed to export timeline as EDL. "
                "Export manually and pass with --edl."
            )
        events = edl_ops.parse_edl(edl_path, fps)

    if not events:
        from ..errors import APICallFailed
        raise APICallFailed("EDL contains no events.")

    # Remove segment and close gap
    modified = edl_ops.remove_segment(events, at, dur_seconds, fps)

    # Write modified EDL
    import tempfile
    import os
    new_title = timeline_name or "rippled"
    safe_stem = re.sub(r"[\\/:\n\r\t]+", "_", str(new_title)).strip() or "rippled"
    if safe_stem != new_title:
        raise ValidationError(
            "Ripple-delete timeline name must already be a canonical file-safe name.",
            details={"requested_name": new_title, "canonical_name": safe_stem},
            recoverability="not_applicable",
        )
    out_edl = os.path.join(
        tempfile.mkdtemp(prefix="resolve_ripple_"),
        f"{safe_stem}.edl",
    )
    edl_ops.write_edl(modified, out_edl, title=new_title)

    if is_dry_run():
        dry_run_message(f"Would import rippled EDL from: {out_edl}")
        output({
            "edl_output": out_edl,
            "expected_timeline": safe_stem,
            "requested_timeline": new_title,
            "original_events": len(events),
            "modified_events": len(modified),
            "removed_duration": f"{dur_seconds:.2f}s",
        })
        return

    # Import the modified EDL as a new timeline
    from ..core import edit_ops
    conn = get_connection(require_timeline=False)
    result = edit_ops.import_edl(
        conn, out_edl, expected_timeline_name=new_title
    )
    result["original_events"] = len(events)
    result["modified_events"] = len(modified)
    result["removed_at"] = at
    result["removed_duration"] = f"{dur_seconds:.2f}s"
    output(result, title="Ripple Delete")


# ---------------------------------------------------------------------------
# Scene Cut Detection (DaVinci Resolve native)
# ---------------------------------------------------------------------------

@app.command("scene-detect")
@handle_errors
def scene_detect():
    """Run DaVinci Resolve native scene detection on the current timeline."""
    enforce_mutation_policy(
        "timeline.scene_cuts_native",
        intended_engine="api_native",
        mutating=not is_dry_run(),
    )

    if is_dry_run():
        dry_run_message("Would run DaVinci Resolve native scene detection on the current timeline")
        return

    conn = get_connection(require_timeline=True)
    output(timeline_ops.detect_scene_cuts_native(conn), title="Scene Detection")


# ---------------------------------------------------------------------------
# Multicam orchestration
# ---------------------------------------------------------------------------


@handle_errors
def multicam_create(
    timeline: str = typer.Option(..., "--timeline", help="Target timeline name"),
    angles: str = typer.Option(..., "--angles", help="Angle spec: A=clipA,B=clipB,..."),
    sync: str = typer.Option("start", "--sync", help="Legacy timeline scaffold sync strategy (supported: start)"),
    base_track: int = typer.Option(2, "--base-track", min=1, help="First angle video track"),
):
    """Create deterministic multicam timeline scaffold via timeline operations."""
    enforce_mutation_policy(
        "edit.multicam_orchestration",
        intended_engine="workaround_setting",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        dry_run_message(
            f"Would create multicam timeline '{timeline}' with angles '{angles}', sync='{sync}', base_track={base_track}"
        )
        return
    conn = get_connection(require_project=True)
    data = multicam_ops.multicam_create(
        conn,
        timeline_name=timeline,
        angles=angles,
        sync=sync,
        base_track=base_track,
    )
    output(data, title="Multicam Create")


@handle_errors
def multicam_switch(
    switches: str = typer.Option(..., "--switches", help="Switch script: 0:A,120:B,240:C"),
    program_track: int = typer.Option(1, "--program-track", min=1, help="Output program track index"),
    angles_track_base: int = typer.Option(2, "--angles-track-base", min=1, help="Base index for angle tracks"),
):
    """Create multicam switch edits on program track via deterministic orchestration."""
    enforce_mutation_policy(
        "edit.multicam_orchestration",
        intended_engine="workaround_setting",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        dry_run_message(
            f"Would apply multicam switches '{switches}' on program_track={program_track}, "
            f"angles_track_base={angles_track_base}"
        )
        return
    conn = get_connection(require_timeline=True)
    data = multicam_ops.multicam_switch(
        conn,
        switches=switches,
        program_track=program_track,
        angles_track_base=angles_track_base,
    )
    output(data, title="Multicam Switch")


# Note: from-markers remains intentionally omitted from the public CLI surface.
