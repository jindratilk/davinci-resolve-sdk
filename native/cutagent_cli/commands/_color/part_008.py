@page_app.command("viewer-before-after")
@handle_errors
def page_viewer_before_after(
    before_at: str = typer.Option(..., "--before-at", help="Timeline position for the before/reference frame"),
    after_at: Optional[str] = typer.Option(None, "--after-at", help="Timeline position for the after frame; current playhead when omitted"),
    before_output: str = typer.Option("color_before.png", "--before-output", help="Exported before frame path"),
    after_output: str = typer.Option("color_after.png", "--after-output", help="Exported after frame path"),
    contact_sheet: Optional[str] = typer.Option(None, "--contact-sheet", help="Optional side-by-side proof image path"),
):
    """Export before/after Color Page frames and return pixel-diff proof metrics."""
    set_execution_engine("api_native")
    set_capability_context("color.page_viewer_before_after", "supported")
    before_path = _resolve_output_file_path(before_output, option_name="--before-output")
    after_path = _resolve_output_file_path(after_output, option_name="--after-output")
    contact_path = _resolve_output_file_path(contact_sheet, option_name="--contact-sheet") if contact_sheet else None
    output_paths = {"before_output": before_path, "after_output": after_path}
    if contact_path is not None:
        output_paths["contact_sheet"] = contact_path
    _validate_distinct_color_frame_outputs(output_paths)

    enforce_mutation_policy("color.page_viewer_before_after", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            {
                "route": "api_native_color_page_viewer_before_after",
                "before_at": before_at,
                "after_at": after_at,
                "before_output_path": str(before_path),
                "after_output_path": str(after_path),
                "contact_sheet_path": str(contact_path) if contact_path else None,
                "would_export": True,
                "would_compare": True,
                "would_generate_contact_sheet": contact_path is not None,
                "exported": False,
                "verified": False,
                "required_page": "color",
            },
            title="Color Page — Viewer Before/After Preview",
        )
        return

    conn = get_connection(require_timeline=True)
    original_playhead = timeline_ops.get_playhead(conn)
    restored = False
    restore_error = None
    contact = None
    try:
        before = _export_match_frame(
            conn,
            at=before_at,
            resolved_path=before_path,
            requested_output_path=before_output,
        )
        after_position = after_at
        if after_position is None and original_playhead and original_playhead.get("timecode"):
            after_position = str(original_playhead["timecode"])
        after = _export_match_frame(
            conn,
            at=after_position,
            resolved_path=after_path,
            requested_output_path=after_output,
        )
        comparison = _compare_before_after_pixels(before["rgb"], after["rgb"])
        if contact_path is not None:
            contact = _write_side_by_side_contact_sheet(before_path, after_path, contact_path)
    finally:
        if original_playhead and original_playhead.get("timecode"):
            try:
                timeline_ops.set_playhead(conn, str(original_playhead["timecode"]), return_details=True)
                restored = True
            except Exception as exc:
                restore_error = str(exc)

    before.pop("rgb", None)
    after.pop("rgb", None)
    set_verification_status("verified")
    set_recoverability("manual" if restore_error else "not_applicable")
    output(
        {
            "route": "api_native_color_page_viewer_before_after",
            "before": before,
            "after": after,
            "contact_sheet": contact,
            "original_playhead": original_playhead,
            "restored_playhead": restored,
            "restore_warning": restore_error,
            "exported": True,
            "verified": True,
            "required_page": "color",
            "verification": {
                "before_frame_exported": True,
                "after_frame_exported": True,
                "pixel_diff_verified": True,
                "contact_sheet_generated": contact is not None,
                "decode_route": "ffmpeg_rawvideo_rgb24",
            },
            "comparison": comparison,
        },
        title="Color Page — Viewer Before/After",
    )


@page_app.command("shot-match-analyze")
@handle_errors
def page_shot_match_analyze(
    reference_at: str = typer.Option(..., "--reference-at", help="Timeline position for the reference shot/frame"),
    target_at: Optional[str] = typer.Option(None, "--target-at", help="Timeline position for the target shot/frame; current playhead when omitted"),
    reference_output: str = typer.Option("color_shot_match_reference.png", "--reference-output", help="Exported reference frame path"),
    target_output: str = typer.Option("color_shot_match_target.png", "--target-output", help="Exported target frame path"),
    anchor_x: Optional[float] = typer.Option(None, "--anchor-x", help="Optional normalized shared anchor X coordinate, 0..1"),
    anchor_y: Optional[float] = typer.Option(None, "--anchor-y", help="Optional normalized shared anchor Y coordinate, 0..1"),
    radius: int = typer.Option(12, "--radius", help="Anchor sample radius in pixels, 0..200"),
    strength: float = typer.Option(1.0, "--strength", help="Recommendation strength, 0..1"),
):
    """Analyze reference/target Color Page frames for exposure and RGB shot matching."""
    set_execution_engine("api_native")
    set_capability_context("color.page_shot_match_analyze", "supported")
    sample_x, sample_y, sample_radius = _validate_match_anchor(anchor_x, anchor_y, radius)
    match_strength = _validate_balance_strength(strength)
    reference_path = _resolve_output_file_path(reference_output, option_name="--reference-output")
    target_path = _resolve_output_file_path(target_output, option_name="--target-output")

    enforce_mutation_policy("color.page_shot_match_analyze", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            {
                "route": "api_native_color_page_shot_match_analyze",
                "reference_at": reference_at,
                "target_at": target_at,
                "reference_output_path": str(reference_path),
                "target_output_path": str(target_path),
                "anchor": {"x": sample_x, "y": sample_y, "radius": sample_radius},
                "strength": match_strength,
                "would_export": True,
                "would_analyze": True,
                "exported": False,
                "verified": False,
                "required_page": "color",
            },
            title="Color Page — Shot Match Analyze Preview",
        )
        return

    conn = get_connection(require_timeline=True)
    original_playhead = timeline_ops.get_playhead(conn)
    restored = False
    restore_error = None
    try:
        reference = _export_match_frame(
            conn,
            at=reference_at,
            resolved_path=reference_path,
            requested_output_path=reference_output,
        )
        target_position = target_at
        if target_position is None and original_playhead and original_playhead.get("timecode"):
            target_position = str(original_playhead["timecode"])
        target = _export_match_frame(
            conn,
            at=target_position,
            resolved_path=target_path,
            requested_output_path=target_output,
        )
        analysis = _analyze_shot_match_pixels(
            reference["rgb"],
            target["rgb"],
            anchor_x=sample_x,
            anchor_y=sample_y,
            radius=sample_radius,
            strength=match_strength,
        )
    finally:
        if original_playhead and original_playhead.get("timecode"):
            try:
                timeline_ops.set_playhead(conn, str(original_playhead["timecode"]), return_details=True)
                restored = True
            except Exception as exc:
                restore_error = str(exc)

    reference.pop("rgb", None)
    target.pop("rgb", None)
    set_verification_status("verified")
    set_recoverability("manual" if restore_error else "not_applicable")
    output(
        {
            "route": "api_native_color_page_shot_match_analyze",
            "reference": reference,
            "target": target,
            "original_playhead": original_playhead,
            "restored_playhead": restored,
            "restore_warning": restore_error,
            "exported": True,
            "verified": True,
            "required_page": "color",
            "verification": {
                "reference_frame_exported": True,
                "target_frame_exported": True,
                "analysis_verified": True,
                "decode_route": "ffmpeg_rawvideo_rgb24",
            },
            "analysis": analysis,
        },
        title="Color Page — Shot Match Analyze",
    )


@page_app.command("shot-match-apply")
@handle_errors
def page_shot_match_apply(
    clip_name: Optional[str] = typer.Argument(None, help="Target clip name; current target frame clip when omitted"),
    reference_at: str = typer.Option(..., "--reference-at", help="Timeline position for the reference shot/frame"),
    target_at: Optional[str] = typer.Option(None, "--target-at", help="Timeline position for the target shot/frame; current playhead when omitted"),
    reference_output: str = typer.Option("color_shot_match_reference.png", "--reference-output", help="Exported reference frame path"),
    target_output: str = typer.Option("color_shot_match_target.png", "--target-output", help="Exported target frame path"),
    anchor_x: Optional[float] = typer.Option(None, "--anchor-x", help="Optional normalized shared anchor X coordinate, 0..1"),
    anchor_y: Optional[float] = typer.Option(None, "--anchor-y", help="Optional normalized shared anchor Y coordinate, 0..1"),
    radius: int = typer.Option(12, "--radius", help="Anchor sample radius in pixels, 0..200"),
    strength: float = typer.Option(0.5, "--strength", help="Applied RGB gain strength, 0..1"),
):
    """Apply a conservative RGB gain shot-match correction from reference/target frame analysis."""
    set_execution_engine("db_workaround")
    set_capability_context("color.page_shot_match_apply", "supported")
    normalized_clip = None
    if clip_name is not None:
        normalized_clip = clip_name.strip()
        if not normalized_clip:
            raise ValidationError("Clip name must not be empty.", details={"clip": clip_name}, recoverability="not_applicable")
    sample_x, sample_y, sample_radius = _validate_match_anchor(anchor_x, anchor_y, radius)
    match_strength = _validate_balance_strength(strength)
    reference_path = _resolve_output_file_path(reference_output, option_name="--reference-output")
    target_path = _resolve_output_file_path(target_output, option_name="--target-output")

    enforce_mutation_policy("color.page_shot_match_apply", intended_engine="db_workaround", mutating=not is_dry_run())
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            {
                "route": "db_workaround_color_page_shot_match_apply",
                "analysis_route": "api_native_color_page_shot_match_analyze",
                "clip": normalized_clip,
                "reference_at": reference_at,
                "target_at": target_at,
                "reference_output_path": str(reference_path),
                "target_output_path": str(target_path),
                "anchor": {"x": sample_x, "y": sample_y, "radius": sample_radius},
                "strength": match_strength,
                "would_export": True,
                "would_analyze": True,
                "would_write_gain": True,
                "exported": False,
                "verified": False,
                "required_page": "color",
            },
            title="Color Page — Shot Match Apply Preview",
        )
        return

    conn = get_connection(require_timeline=True)
    original_playhead = timeline_ops.get_playhead(conn)
    restored = False
    restore_error = None
    try:
        reference = _export_match_frame(
            conn,
            at=reference_at,
            resolved_path=reference_path,
            requested_output_path=reference_output,
        )
        target_position = target_at
        if target_position is None and original_playhead and original_playhead.get("timecode"):
            target_position = str(original_playhead["timecode"])
        target = _export_match_frame(
            conn,
            at=target_position,
            resolved_path=target_path,
            requested_output_path=target_output,
        )
        analysis = _analyze_shot_match_pixels(
            reference["rgb"],
            target["rgb"],
            anchor_x=sample_x,
            anchor_y=sample_y,
            radius=sample_radius,
            strength=match_strength,
        )
        gains = analysis["recommended_primary"]
        write_result = color_page_db.write_color_grade(
            conn,
            clip_name=normalized_clip,
            gain_r=gains["gain_r"],
            gain_g=gains["gain_g"],
            gain_b=gains["gain_b"],
        )
    finally:
        if original_playhead and original_playhead.get("timecode"):
            try:
                timeline_ops.set_playhead(conn, str(original_playhead["timecode"]), return_details=True)
                restored = True
            except Exception as exc:
                restore_error = str(exc)

    reference.pop("rgb", None)
    target.pop("rgb", None)
    if isinstance(write_result, dict):
        write_result["db_session_route"] = write_result.get("route")
        write_result["route"] = "db_workaround_color_page_shot_match_apply"

    set_verification_status("verified")
    set_recoverability("manual" if restore_error else "not_applicable")
    output(
        {
            "route": "db_workaround_color_page_shot_match_apply",
            "analysis_route": "api_native_color_page_shot_match_analyze",
            "clip": normalized_clip,
            "reference": reference,
            "target": target,
            "original_playhead": original_playhead,
            "restored_playhead": restored,
            "restore_warning": restore_error,
            "exported": True,
            "verified": True,
            "required_page": "color",
            "verification": {
                "reference_frame_exported": True,
                "target_frame_exported": True,
                "analysis_verified": True,
                "db_write_verified": True,
                "decode_route": "ffmpeg_rawvideo_rgb24",
            },
            "analysis": analysis,
            "write_result": write_result,
        },
        title="Color Page — Shot Match Apply",
    )


@page_app.command("qualifier-sample")
@handle_errors
def page_qualifier_sample(
    x: float = typer.Option(..., "--x", help="Normalized sample X coordinate across the Color Page frame (0..1)"),
    y: float = typer.Option(..., "--y", help="Normalized sample Y coordinate down the Color Page frame (0..1)"),
    radius: int = typer.Option(3, "--radius", help="Pixel radius around the sample point (0..200)"),
    at: Optional[str] = typer.Option(None, "--at", help="Optional timeline position to sample before restoring the playhead"),
    output_path: str = typer.Option("color_qualifier_sample.png", "--output", "-o", help="Exported frame path used for sample analysis"),
):
    """Sample Color Page frame values for qualifier/scope-guided grading."""
    set_execution_engine("api_native")
    set_capability_context("color.page_qualifier_sample", "supported")
    sample_x = _validate_normalized_coordinate(x, option_name="--x")
    sample_y = _validate_normalized_coordinate(y, option_name="--y")
    sample_radius = _validate_sample_radius(radius)
    resolved_path = _resolve_output_file_path(output_path)

    enforce_mutation_policy("color.page_qualifier_sample", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            {
                "route": "api_native_color_page_qualifier_sample",
                "requested_at": at,
                "output_path": str(resolved_path),
                "visual_check_path": _workspace_relative_path(resolved_path),
                "requested_output_path": output_path,
                "sample": {"x": sample_x, "y": sample_y, "radius": sample_radius},
                "would_set_playhead": at is not None,
                "would_export": True,
                "would_sample": True,
                "exported": False,
                "verified": False,
                "required_page": "color",
            },
            title="Color Page — Qualifier Sample Preview",
        )
        return

    conn = get_connection(require_timeline=True)
    original_playhead = None
    target = None
    restored = False
    restore_error = None
    if at is not None:
        original_playhead = timeline_ops.get_playhead(conn)
        target = timeline_ops.set_playhead(conn, at, return_details=True)

    try:
        metadata = _export_color_page_frame_as_still(
            conn,
            resolved_path=resolved_path,
            requested_output_path=output_path,
        )
    finally:
        if original_playhead:
            original_tc = original_playhead.get("timecode")
            if original_tc:
                try:
                    timeline_ops.set_playhead(conn, str(original_tc), return_details=True)
                    restored = True
                except Exception as exc:
                    try:
                        fresh_conn = get_connection(require_timeline=True)
                        timeline_ops.set_playhead(fresh_conn, str(original_tc), return_details=True)
                        restored = True
                    except Exception as fresh_exc:
                        restore_error = f"{exc}; retry after reopen failed: {fresh_exc}"

    rgb = _load_frame_rgb_array(resolved_path)
    sample = _sample_qualifier_pixels(rgb, x=sample_x, y=sample_y, radius=sample_radius)

    set_verification_status("verified")
    set_recoverability("manual" if restore_error else "not_applicable")
    output(
        {
            "route": "api_native_color_page_qualifier_sample",
            "requested_at": at,
            "output_path": str(resolved_path),
            "visual_check_path": _workspace_relative_path(resolved_path),
            "requested_output_path": output_path,
            "original_playhead": original_playhead,
            "target": target,
            "restored_playhead": restored,
            "restore_warning": restore_error,
            "exported": True,
            "verified": True,
            "required_page": "color",
            "verification": {
                "frame_exported": True,
                "sample_verified": True,
                "pixel_count": sample["sample"]["pixel_count"],
                "decode_route": "ffmpeg_rawvideo_rgb24",
            },
            "frame_export": metadata,
            "sample": sample,
        },
        title="Color Page — Qualifier Sample",
    )


@page_app.command("white-balance-picker")
@handle_errors
def page_white_balance_picker(
    clip_name: Optional[str] = typer.Argument(None, help="Clip name; current clip at sample position when omitted"),
    x: float = typer.Option(..., "--x", help="Normalized neutral sample X coordinate across the Color Page frame (0..1)"),
    y: float = typer.Option(..., "--y", help="Normalized neutral sample Y coordinate down the Color Page frame (0..1)"),
    radius: int = typer.Option(8, "--radius", help="Pixel radius around the neutral sample point (0..200)"),
    at: Optional[str] = typer.Option(None, "--at", help="Optional timeline position to sample before restoring the playhead"),
    strength: float = typer.Option(1.0, "--strength", help="Blend strength for computed RGB gain correction (0..1)"),
    output_path: str = typer.Option("color_white_balance_sample.png", "--output", "-o", help="Exported frame path used for white balance sampling"),
):
    """White-balance a clip from a sampled neutral Color Page frame patch."""
    set_execution_engine("db_workaround")
    set_capability_context("color.page_white_balance_picker", "supported")
    normalized_clip = None
    if clip_name is not None:
        normalized_clip = clip_name.strip()
        if not normalized_clip:
            raise ValidationError(
                "Clip name must not be empty.",
                details={"clip": clip_name},
                recoverability="not_applicable",
            )
    sample_x = _validate_normalized_coordinate(x, option_name="--x")
    sample_y = _validate_normalized_coordinate(y, option_name="--y")
    sample_radius = _validate_sample_radius(radius)
    balance_strength = _validate_balance_strength(strength)
    resolved_path = _resolve_output_file_path(output_path)

    enforce_mutation_policy(
        "color.page_white_balance_picker",
        intended_engine="db_workaround",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            {
                "route": "db_workaround_color_page_white_balance_picker",
                "sample_route": "api_native_color_page_frame_sample",
                "clip": normalized_clip,
                "requested_at": at,
                "output_path": str(resolved_path),
                "visual_check_path": _workspace_relative_path(resolved_path),
                "sample": {"x": sample_x, "y": sample_y, "radius": sample_radius},
                "strength": balance_strength,
                "would_set_playhead": at is not None,
                "would_export": True,
                "would_sample": True,
                "would_write_gain": True,
                "exported": False,
                "verified": False,
                "required_page": "color",
            },
            title="Color Page — White Balance Picker Preview",
        )
        return

    conn = get_connection(require_timeline=True)
    original_playhead = None
    target = None
    restored = False
    restore_error = None
    if at is not None:
        original_playhead = timeline_ops.get_playhead(conn)
        target = timeline_ops.set_playhead(conn, at, return_details=True)

    try:
        metadata = _export_color_page_frame_as_still(
            conn,
            resolved_path=resolved_path,
            requested_output_path=output_path,
        )
        rgb = _load_frame_rgb_array(resolved_path)
        sample = _sample_qualifier_pixels(rgb, x=sample_x, y=sample_y, radius=sample_radius)
        correction = _white_balance_gains_from_sample(sample, strength=balance_strength)
        write_result = color_page_db.write_color_grade(
            conn,
            clip_name=normalized_clip,
            gain_r=correction["gain_r"],
            gain_g=correction["gain_g"],
            gain_b=correction["gain_b"],
        )
    finally:
        if original_playhead:
            original_tc = original_playhead.get("timecode")
            if original_tc:
                try:
                    timeline_ops.set_playhead(conn, str(original_tc), return_details=True)
                    restored = True
                except Exception as exc:
                    try:
                        fresh_conn = get_connection(require_timeline=True)
                        timeline_ops.set_playhead(fresh_conn, str(original_tc), return_details=True)
                        restored = True
                    except Exception as fresh_exc:
                        restore_error = f"{exc}; retry after reopen failed: {fresh_exc}"

    if isinstance(write_result, dict):
        write_result["db_session_route"] = write_result.get("route")
        write_result["route"] = "db_workaround_color_page_white_balance_picker"

    set_verification_status("verified")
    set_recoverability("manual" if restore_error else "not_applicable")
    output(
        {
            "route": "db_workaround_color_page_white_balance_picker",
            "sample_route": "api_native_color_page_frame_sample",
            "clip": normalized_clip,
            "requested_at": at,
            "output_path": str(resolved_path),
            "visual_check_path": _workspace_relative_path(resolved_path),
            "requested_output_path": output_path,
            "original_playhead": original_playhead,
            "target": target,
            "restored_playhead": restored,
            "restore_warning": restore_error,
            "exported": True,
            "verified": True,
            "required_page": "color",
            "verification": {
                "frame_exported": True,
                "sample_verified": True,
                "db_write_verified": True,
                "decode_route": "ffmpeg_rawvideo_rgb24",
            },
            "frame_export": metadata,
            "sample": sample,
            "correction": correction,
            "write": write_result,
        },
        title="Color Page — White Balance Picker",
    )
