def _complete_curve_render_proof_if_requested(
    *,
    conn,
    clip_name,
    route: str,
    require_render_proof: bool,
    write,
    readback_source: str | None = None,
):
    render_proof = None
    if require_render_proof:
        render_proof = _begin_color_render_proof(
            conn,
            clip_name=clip_name,
            route=route,
        )
    data = write()
    _tag_db_workaround_route(data, route)
    if render_proof is not None:
        conn_after = get_connection(require_timeline=True)
        try:
            data["render_proof"] = _complete_color_render_proof(conn_after, render_proof, partial_result=data)
        except Exception as exc:
            from ..core.db_session import restore_project_db_backup_from_mutation_result

            rollback = restore_project_db_backup_from_mutation_result(conn_after, data)
            data["rollback_after_failed_render_proof"] = rollback
            error_details = getattr(exc, "details", None)
            if isinstance(error_details, dict):
                error_details["rollback_after_failed_render_proof"] = rollback
                partial = error_details.get("partial_result")
                if isinstance(partial, dict):
                    partial["rollback_after_failed_render_proof"] = rollback
            raise
        data.setdefault("verification", {})
        data["verification"]["status"] = "verified"
        data["verification"]["render_proof_status"] = data["render_proof"]["status"]
        data["verification"]["render_proof_route"] = data["render_proof"]["route"]
        data["verification"]["render_proof_required"] = True
        data["verification"]["note"] = "Project.db readback and rendered-frame proof both verified after project reload."
        set_verification_status("verified")
        set_recoverability("not_applicable")
    else:
        _mark_color_render_unverified(
            data,
            readback_source=readback_source or f"project_db_{route.replace('db_workaround_color_page_', '')}",
        )
        data.setdefault("render_proof", {
            "status": "not_requested",
            "reason": "setup_only_curve_may_not_change_pixels",
            "required_next_proof": "Run with --require-render-proof before claiming a visible curve grade.",
        })
    return data


@page_app.command("wheel-set")
@handle_errors
def page_wheel_set(
    clip_name: Optional[str] = typer.Argument(None, help="Clip name"),
    node_index: int = typer.Option(1, "--node-index", "--node", help="1-based Color Page node index"),
    lift_r: Optional[float] = typer.Option(None, "--lift-r", help="Lift Red"),
    lift_g: Optional[float] = typer.Option(None, "--lift-g", help="Lift Green"),
    lift_b: Optional[float] = typer.Option(None, "--lift-b", help="Lift Blue"),
    gamma_r: Optional[float] = typer.Option(None, "--gamma-r", help="Gamma Red"),
    gamma_g: Optional[float] = typer.Option(None, "--gamma-g", help="Gamma Green"),
    gamma_b: Optional[float] = typer.Option(None, "--gamma-b", help="Gamma Blue"),
    gain_r: Optional[float] = typer.Option(None, "--gain-r", help="Gain Red"),
    gain_g: Optional[float] = typer.Option(None, "--gain-g", help="Gain Green"),
    gain_b: Optional[float] = typer.Option(None, "--gain-b", help="Gain Blue"),
    saturation: Optional[float] = typer.Option(None, "--sat", help="Saturation"),
    require_render_proof: bool = typer.Option(False, "--require-render-proof", help="Export before/after Color Page frames and fail unless the rendered image changes"),
):
    """Set color wheel values via DB readback (Disk projects only).

    Writes directly to the LmVersion.Body protobuf in the project database.
    Requires a Disk-type project. The project is closed or switched away,
    patched, reopened, and verified with a post-reload DB readback.
    """
    from ..core import color_page_db

    node_index = int(_option_value(node_index) or 1)
    if node_index < 1:
        raise ValidationError(
            "Color Page wheel-set --node must be a positive integer.",
            details={"node_index": node_index, "minimum": 1},
            recoverability="not_applicable",
        )

    enforce_mutation_policy(
        "color.page_wheel_set",
        intended_engine="db_workaround",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        dry_run_message("Would set color wheel values via DB")
        return

    conn = get_connection(require_timeline=True)
    render_proof = None
    if bool(_option_value(require_render_proof, False)):
        render_proof = _begin_color_render_proof(
            conn,
            clip_name=clip_name,
            route="db_workaround_color_page_wheel_set",
        )
    data = color_page_db.write_color_grade(
        conn,
        clip_name=clip_name,
        node_index=node_index,
        lift_r=lift_r, lift_g=lift_g, lift_b=lift_b,
        gamma_r=gamma_r, gamma_g=gamma_g, gamma_b=gamma_b,
        gain_r=gain_r, gain_g=gain_g, gain_b=gain_b,
        saturation=saturation,
    )
    _tag_db_workaround_route(data, "db_workaround_color_page_wheel_set")
    if render_proof is not None:
        conn_after = get_connection(require_timeline=True)
        data["render_proof"] = _complete_color_render_proof(conn_after, render_proof, partial_result=data)
        data["verification"]["status"] = "verified"
        data["verification"]["render_proof_status"] = data["render_proof"]["status"]
        data["verification"]["render_proof_route"] = data["render_proof"]["route"]
        data["verification"]["render_proof_required"] = True
        set_verification_status("verified")
        set_recoverability("not_applicable")
    else:
        _mark_color_render_unverified(data, readback_source="project_db_color_page_params")
    output(data, title="Color Page — Wheel Set")
    success("Color wheel values written to DB.")


@page_app.command("primary-set")
@handle_errors
def page_primary_set(
    clip_name: Optional[str] = typer.Argument(None, help="Clip name"),
    track: Optional[int] = typer.Option(None, "--track", help="Exact 1-based video track selector"),
    at: Optional[str] = typer.Option(None, "--at", help="Exact timeline position selector"),
    node_index: int = typer.Option(1, "--node-index", "--node", help="1-based Color Page node index"),
    contrast: Optional[float] = typer.Option(None, "--contrast", help="Primary contrast value"),
    pivot: Optional[float] = typer.Option(None, "--pivot", help="Primary pivot value"),
    temperature: Optional[float] = typer.Option(None, "--temperature", help="Primary temperature value"),
    tint: Optional[float] = typer.Option(None, "--tint", help="Primary tint value"),
    hue: Optional[float] = typer.Option(None, "--hue", help="Primary hue value"),
    lum_mix: Optional[float] = typer.Option(None, "--lum-mix", help="Luminance mix value"),
    highlights: Optional[float] = typer.Option(None, "--highlights", help="Primary highlights value"),
    shadows: Optional[float] = typer.Option(None, "--shadows", help="Primary shadows value"),
    color_boost: Optional[float] = typer.Option(None, "--color-boost", help="Primary color boost value"),
    mid_detail: Optional[float] = typer.Option(None, "--mid-detail", help="Primary midtone detail value"),
    offset_r: Optional[float] = typer.Option(None, "--offset-r", help="Offset Red"),
    offset_g: Optional[float] = typer.Option(None, "--offset-g", help="Offset Green"),
    offset_b: Optional[float] = typer.Option(None, "--offset-b", help="Offset Blue"),
    require_render_proof: bool = typer.Option(False, "--require-render-proof", help="Export before/after Color Page frames and fail unless the rendered image changes"),
):
    """Set native Color Page primary controls via DB readback (Disk projects only)."""
    from ..core import color_page_db

    node_index = int(_option_value(node_index) or 1)
    track = _option_value(track)
    at = _option_value(at)
    if node_index < 1:
        raise ValidationError(
            "Color Page primary-set --node must be a positive integer.",
            details={"node_index": node_index, "minimum": 1},
            recoverability="not_applicable",
        )

    enforce_mutation_policy(
        "color.page_primary_set",
        intended_engine="db_workaround",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        dry_run_message("Would set Color Page primary controls via DB")
        return

    conn = get_connection(require_timeline=True)
    timeline_ops.require_sdk_color_mutation_guard(conn)
    proof_required = bool(_option_value(require_render_proof, False))
    render_proof = None
    if proof_required:
        render_proof = _begin_color_render_proof(
            conn,
            clip_name=clip_name,
            track=track,
            at=at,
            route="db_workaround_color_page_primary_set",
        )
    data = color_page_db.write_color_grade(
        conn,
        clip_name=clip_name,
        track=track,
        at=at,
        node_index=node_index,
        contrast=contrast,
        pivot=pivot,
        temperature=temperature,
        tint=tint,
        hue=hue,
        lum_mix=lum_mix,
        highlights=highlights,
        shadows=shadows,
        color_boost=color_boost,
        mid_detail=mid_detail,
        offset_r=offset_r,
        offset_g=offset_g,
        offset_b=offset_b,
    )
    _tag_db_workaround_route(data, "db_workaround_color_page_primary_set")
    if render_proof is not None:
        conn_after = get_connection(require_timeline=True)
        try:
            data["render_proof"] = _complete_color_render_proof(conn_after, render_proof, partial_result=data)
        except Exception as exc:
            from ..core.db_session import restore_project_db_backup_from_mutation_result

            rollback = restore_project_db_backup_from_mutation_result(conn_after, data)
            data["rollback_after_failed_render_proof"] = rollback
            error_details = getattr(exc, "details", None)
            if isinstance(error_details, dict):
                error_details["rollback_after_failed_render_proof"] = rollback
                partial = error_details.get("partial_result")
                if isinstance(partial, dict):
                    partial["rollback_after_failed_render_proof"] = rollback
            raise
        data["verification"]["status"] = "verified"
        data["verification"]["render_proof_status"] = data["render_proof"]["status"]
        data["verification"]["render_proof_route"] = data["render_proof"]["route"]
        data["verification"]["render_proof_required"] = True
        set_verification_status("verified")
        set_recoverability("not_applicable")
    else:
        _mark_color_render_unverified(data, readback_source="project_db_color_page_params")
    output(data, title="Color Page — Primary Set")
    success("Color Page primary values written to DB.")


@page_app.command("curve-set")
@handle_errors
def page_curve_set(
    clip_name: Optional[str] = typer.Argument(None, help="Clip name"),
    all_channels: Optional[float] = typer.Option(None, "--all", help="Set Custom Curves Edit Y/R/G/B endpoint value (0-100)"),
    y: Optional[float] = typer.Option(None, "--y", help="Set Custom Curves Edit Y endpoint value (0-100)"),
    red: Optional[float] = typer.Option(None, "--red", help="Set Custom Curves Edit Red endpoint value (0-100)"),
    green: Optional[float] = typer.Option(None, "--green", help="Set Custom Curves Edit Green endpoint value (0-100)"),
    blue: Optional[float] = typer.Option(None, "--blue", help="Set Custom Curves Edit Blue endpoint value (0-100)"),
    require_render_proof: bool = typer.Option(True, "--require-render-proof/--setup-only", help="Export before/after Color Page frames and fail unless rendered pixels change"),
):
    """Set native Color Page Custom Curves endpoint values via DB and rendered-frame proof."""
    from ..core import color_page_db

    clip_name = _option_value(clip_name)
    all_channels = _option_value(all_channels)
    y = _option_value(y)
    red = _option_value(red)
    green = _option_value(green)
    blue = _option_value(blue)
    require_render_proof = bool(_option_value(require_render_proof, True))

    set_execution_engine("db_workaround", 0.75)
    set_capability_context("color.page_curve_set", "supported")

    requested = {
        "y": y if y is not None else all_channels,
        "red": red if red is not None else all_channels,
        "green": green if green is not None else all_channels,
        "blue": blue if blue is not None else all_channels,
    }
    if all(value is None for value in requested.values()):
        raise ValidationError(
            "Color Page curve-set requires at least one endpoint option: --all/--y/--red/--green/--blue.",
            recoverability="not_applicable",
        )

    internal = {
        name: color_page_db.curve_endpoint_ui_to_internal(value)
        for name, value in requested.items()
        if value is not None
    }

    enforce_mutation_policy(
        "color.page_curve_set",
        intended_engine="db_workaround",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        proof_note = "with render proof" if require_render_proof else "as setup-only DB readback"
        dry_run_message(f"Would set Color Page Custom Curves endpoint values via DB {proof_note}")
        return

    conn = get_connection(require_timeline=True)
    data = _complete_curve_render_proof_if_requested(
        conn=conn,
        clip_name=clip_name,
        route="db_workaround_color_page_custom_curves_endpoint",
        require_render_proof=require_render_proof,
        readback_source="project_db_custom_curve_endpoint",
        write=lambda: color_page_db.write_color_grade(
            conn,
            clip_name=clip_name,
            curve_high_y=internal.get("y"),
            curve_high_r=internal.get("red"),
            curve_high_g=internal.get("green"),
            curve_high_b=internal.get("blue"),
        ),
    )
    data["curve_endpoint_ui"] = {name: value for name, value in requested.items() if value is not None}
    data["curve_endpoint_internal"] = internal
    output(data, title="Color Page — Curve Set")
    success("Color Page Custom Curves endpoint values written to DB.")


@page_app.command("curve-points-set")
@handle_errors
def page_curve_points_set(
    clip_name: Optional[str] = typer.Argument(None, help="Clip name"),
    all_points: Optional[str] = typer.Option(None, "--all-points", help="Set linked Y/R/G/B Custom Curves points as 'x,y;x,y' normalized pairs"),
    y: Optional[str] = typer.Option(None, "--y", help="Set Y Custom Curves points as 'x,y;x,y' normalized pairs"),
    red: Optional[str] = typer.Option(None, "--red", help="Set Red Custom Curves points as 'x,y;x,y' normalized pairs"),
    green: Optional[str] = typer.Option(None, "--green", help="Set Green Custom Curves points as 'x,y;x,y' normalized pairs"),
    blue: Optional[str] = typer.Option(None, "--blue", help="Set Blue Custom Curves points as 'x,y;x,y' normalized pairs"),
    require_render_proof: bool = typer.Option(True, "--require-render-proof/--setup-only", help="Export before/after Color Page frames and fail unless rendered pixels change"),
):
    """Set native Color Page Custom Curves control points via DB and rendered-frame proof."""
    from ..core import color_page_db

    clip_name = _option_value(clip_name)
    all_points = _option_value(all_points)
    y = _option_value(y)
    red = _option_value(red)
    green = _option_value(green)
    blue = _option_value(blue)
    require_render_proof = bool(_option_value(require_render_proof, True))

    set_execution_engine("db_workaround", 0.75)
    set_capability_context("color.page_curve_points_set", "supported")

    requested = {
        "y": y if y is not None else all_points,
        "red": red if red is not None else all_points,
        "green": green if green is not None else all_points,
        "blue": blue if blue is not None else all_points,
    }
    if all(value is None for value in requested.values()):
        raise ValidationError(
            "Color Page curve-points-set requires --all-points or at least one channel option.",
            recoverability="not_applicable",
        )

    parsed = {
        channel: color_page_db.parse_curve_points_spec(value)
        for channel, value in requested.items()
        if value is not None
    }

    enforce_mutation_policy(
        "color.page_curve_points_set",
        intended_engine="db_workaround",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        proof_note = "with render proof" if require_render_proof else "as setup-only DB readback"
        dry_run_message(f"Would set Color Page Custom Curves control points via DB {proof_note}")
        return

    conn = get_connection(require_timeline=True)
    data = _complete_curve_render_proof_if_requested(
        conn=conn,
        clip_name=clip_name,
        route="db_workaround_color_page_custom_curves_points",
        require_render_proof=require_render_proof,
        readback_source="project_db_custom_curve_points",
        write=lambda: color_page_db.write_custom_curve_points(
            conn,
            clip_name=clip_name,
            y=parsed.get("y"),
            red=parsed.get("red"),
            green=parsed.get("green"),
            blue=parsed.get("blue"),
        ),
    )
    output(data, title="Color Page — Curve Points Set")
    success("Color Page Custom Curves control points written to DB.")


@page_app.command("split-tone-set")
@handle_errors
def page_split_tone_set(
    clip_name: Optional[str] = typer.Argument(None, help="Clip name"),
    strength: float = typer.Option(1.0, "--strength", help="Overall split-tone strength, 0..2"),
    shadow_cool: float = typer.Option(0.06, "--shadow-cool", help="Cool shadow color curve amount, -0.5..0.5"),
    highlight_warm: float = typer.Option(0.06, "--highlight-warm", help="Warm highlight color curve amount, -0.5..0.5"),
    shadow_lift: float = typer.Option(0.0, "--shadow-lift", help="Optional neutral shadow curve lift, -0.5..0.5"),
    highlight_lift: float = typer.Option(0.0, "--highlight-lift", help="Optional neutral highlight curve lift, -0.5..0.5"),
    pivot: float = typer.Option(0.5, "--pivot", help="Split-tone tonal pivot, 0.05..0.95"),
    rolloff: float = typer.Option(1.0, "--rolloff", help="Shadow/highlight curve rolloff exponent, 0.25..4"),
    shadow_r: Optional[float] = typer.Option(None, "--shadow-r", help="Explicit red shadow curve offset, -0.5..0.5"),
    shadow_g: Optional[float] = typer.Option(None, "--shadow-g", help="Explicit green shadow curve offset, -0.5..0.5"),
    shadow_b: Optional[float] = typer.Option(None, "--shadow-b", help="Explicit blue shadow curve offset, -0.5..0.5"),
    highlight_r: Optional[float] = typer.Option(None, "--highlight-r", help="Explicit red highlight curve offset, -0.5..0.5"),
    highlight_g: Optional[float] = typer.Option(None, "--highlight-g", help="Explicit green highlight curve offset, -0.5..0.5"),
    highlight_b: Optional[float] = typer.Option(None, "--highlight-b", help="Explicit blue highlight curve offset, -0.5..0.5"),
    y_mood: float = typer.Option(0.0, "--y-mood", help="Optional neutral Y contrast mood curve amount, -0.5..0.5"),
    key_output_gain: Optional[float] = typer.Option(None, "--key-output-gain", "--gain", help="Optional Key Output Gain applied after split tone, 0..1"),
):
    """Apply a verified split tone via native Custom Curves, optionally with Key Output."""
    from ..core import color_page_db

    clip_name = _option_value(clip_name)
    strength = _option_value(strength, 1.0)
    shadow_cool = _option_value(shadow_cool, 0.06)
    highlight_warm = _option_value(highlight_warm, 0.06)
    shadow_lift = _option_value(shadow_lift, 0.0)
    highlight_lift = _option_value(highlight_lift, 0.0)
    pivot = _option_value(pivot, 0.5)
    rolloff = _option_value(rolloff, 1.0)
    shadow_r = _option_value(shadow_r)
    shadow_g = _option_value(shadow_g)
    shadow_b = _option_value(shadow_b)
    highlight_r = _option_value(highlight_r)
    highlight_g = _option_value(highlight_g)
    highlight_b = _option_value(highlight_b)
    y_mood = _option_value(y_mood, 0.0)
    key_output_gain = _option_value(key_output_gain)

    set_execution_engine("db_workaround", 0.75)
    set_capability_context("color.page_split_tone_set", "supported")
    color_page_db.build_split_tone_curve_points(
        strength=float(strength),
        shadow_cool=float(shadow_cool),
        highlight_warm=float(highlight_warm),
        shadow_lift=float(shadow_lift),
        highlight_lift=float(highlight_lift),
        pivot=float(pivot),
        rolloff=float(rolloff),
        shadow_r=None if shadow_r is None else float(shadow_r),
        shadow_g=None if shadow_g is None else float(shadow_g),
        shadow_b=None if shadow_b is None else float(shadow_b),
        highlight_r=None if highlight_r is None else float(highlight_r),
        highlight_g=None if highlight_g is None else float(highlight_g),
        highlight_b=None if highlight_b is None else float(highlight_b),
        y_mood=float(y_mood),
    )
    if key_output_gain is not None:
        color_page_db.validate_key_output_gain(float(key_output_gain))

    enforce_mutation_policy(
        "color.page_split_tone_set",
        intended_engine="db_workaround",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        if key_output_gain is None:
            dry_run_message("Would set Color Page split tone through verified Custom Curves DB payloads")
        else:
            dry_run_message("Would set Color Page split tone and Key Output Gain through verified DB payloads")
        return

    conn = get_connection(require_timeline=True)
    split_tone_kwargs = {
        "strength": float(strength),
        "shadow_cool": float(shadow_cool),
        "highlight_warm": float(highlight_warm),
        "shadow_lift": float(shadow_lift),
        "highlight_lift": float(highlight_lift),
        "pivot": float(pivot),
        "rolloff": float(rolloff),
        "shadow_r": None if shadow_r is None else float(shadow_r),
        "shadow_g": None if shadow_g is None else float(shadow_g),
        "shadow_b": None if shadow_b is None else float(shadow_b),
        "highlight_r": None if highlight_r is None else float(highlight_r),
        "highlight_g": None if highlight_g is None else float(highlight_g),
        "highlight_b": None if highlight_b is None else float(highlight_b),
        "y_mood": float(y_mood),
    }
    if key_output_gain is None:
        data = color_page_db.write_split_tone_curves(
            conn,
            clip_name=clip_name,
            **split_tone_kwargs,
        )
    else:
        data = color_page_db.write_split_tone_curves_with_key_output(
            conn,
            clip_name=clip_name,
            key_output_gain=float(key_output_gain),
            connection_factory=lambda: get_connection(require_timeline=True),
            **split_tone_kwargs,
        )
        if isinstance(data.get("verification"), dict) and data["verification"].get("status") == "verified":
            set_verification_status("verified")
            set_recoverability("not_applicable")
    output(data, title="Color Page — Split Tone Set")
    success("Color Page split tone written to DB.")


@page_app.command("hsv-node-set")
@handle_errors
def page_hsv_node_set(
    clip_name: Optional[str] = typer.Argument(None, help="Clip name"),
    node_index: int = typer.Option(1, "--node-index", "--node", help="Verified HSV node target. Only node 1 is currently fixture-backed"),
    gamma_r: Optional[float] = typer.Option(None, "--gamma-r", help="HSV node Gamma Red internal value"),
    gamma_g: Optional[float] = typer.Option(None, "--gamma-g", help="HSV node Gamma Green internal value"),
    gamma_b: Optional[float] = typer.Option(None, "--gamma-b", help="HSV node Gamma Blue internal value"),
    gamma_master: Optional[float] = typer.Option(None, "--gamma-master", help="HSV node Gamma master/internal fourth value"),
    gain_r: Optional[float] = typer.Option(None, "--gain-r", help="HSV node Gain Red internal value"),
    gain_g: Optional[float] = typer.Option(None, "--gain-g", help="HSV node Gain Green internal value"),
    gain_b: Optional[float] = typer.Option(None, "--gain-b", help="HSV node Gain Blue internal value"),
    gain_master: Optional[float] = typer.Option(None, "--gain-master", help="HSV node Gain master/internal fourth value"),
    key_output_gain: Optional[float] = typer.Option(None, "--key-output-gain", "--strength", help="Optional Key Output Gain/strength applied after HSV node, 0..1"),
):
    """Apply the verified tutorial HSV saturation node workflow, optionally with strength."""
    from ..core import color_page_db

    clip_name = _option_value(clip_name)
    node_index = int(_option_value(node_index) or 1)
    gamma_r = _option_value(gamma_r)
    gamma_g = _option_value(gamma_g)
    gamma_b = _option_value(gamma_b)
    gamma_master = _option_value(gamma_master)
    gain_r = _option_value(gain_r)
    gain_g = _option_value(gain_g)
    gain_b = _option_value(gain_b)
    gain_master = _option_value(gain_master)
    key_output_gain = _option_value(key_output_gain)

    set_execution_engine("db_workaround", 0.75)
    set_capability_context("color.page_hsv_node_set", "supported")
    if node_index < 1:
        raise ValidationError(
            "HSV node index must be a positive integer.",
            details={"node_index": node_index, "minimum": 1},
            recoverability="not_applicable",
        )
    if node_index != 1:
        _unsupported_color_page_preview(
            "color.page_hsv_node_target",
            "not_available_color_page_hsv_node_target",
            {
                "clip": clip_name,
                "requested_node_index": node_index,
                "verified_node_index": 1,
                "verified_slices": ["color.page_hsv_node_set"],
            },
            "Color Page — HSV Node Target",
        )
        return
    color_page_db._hsv_node_expected_params(
        gamma_r=gamma_r,
        gamma_g=gamma_g,
        gamma_b=gamma_b,
        gamma_master=gamma_master,
        gain_r=gain_r,
        gain_g=gain_g,
        gain_b=gain_b,
        gain_master=gain_master,
    )
    if key_output_gain is not None:
        color_page_db.validate_key_output_gain(float(key_output_gain))

    enforce_mutation_policy(
        "color.page_hsv_node_set",
        intended_engine="db_workaround",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        if key_output_gain is None:
            dry_run_message("Would set verified Color Page HSV saturation node payload via DB")
        else:
            dry_run_message("Would set verified Color Page HSV saturation node payload and Key Output Gain via DB")
        return

    conn = get_connection(require_timeline=True)
    hsv_kwargs = {
        "gamma_r": gamma_r,
        "gamma_g": gamma_g,
        "gamma_b": gamma_b,
        "gamma_master": gamma_master,
        "gain_r": gain_r,
        "gain_g": gain_g,
        "gain_b": gain_b,
        "gain_master": gain_master,
    }
    if key_output_gain is None:
        data = color_page_db.write_hsv_node_saturation(
            conn,
            clip_name=clip_name,
            **hsv_kwargs,
        )
    else:
        data = color_page_db.write_hsv_node_saturation_with_key_output(
            conn,
            clip_name=clip_name,
            key_output_gain=float(key_output_gain),
            connection_factory=lambda: get_connection(require_timeline=True),
            **hsv_kwargs,
        )
        if isinstance(data.get("verification"), dict) and data["verification"].get("status") == "verified":
            set_verification_status("verified")
            set_recoverability("not_applicable")
    output(data, title="Color Page — HSV Node Set")
    success("Color Page HSV saturation node written to DB.")


@page_app.command("hue-curve-set")
@handle_errors
def page_hue_curve_set(
    clip_name: Optional[str] = typer.Argument(None, help="Clip name"),
    input_hue: Optional[float] = typer.Option(None, "--input-hue", help="Hue curve GUI Input Hue value (0..720)"),
    mode: str = typer.Option("hue-vs-hue", "--mode", help="Hue curve mode: hue-vs-hue, hue-vs-sat, or hue-vs-lum"),
    hue_rotate: Optional[float] = typer.Option(None, "--hue-rotate", help="Hue vs Hue GUI Hue Rotate value (-180..180)"),
    saturation: Optional[float] = typer.Option(None, "--saturation", help="Hue vs Sat GUI Saturation value (0..2)"),
    lum_gain: Optional[float] = typer.Option(None, "--lum-gain", help="Hue vs Lum GUI Lum Gain value (0..2)"),
    points: Optional[str] = typer.Option(None, "--points", help='Multi-point Hue curve pairs as "input_hue,value;input_hue,value"'),
    require_render_proof: bool = typer.Option(True, "--require-render-proof/--setup-only", help="Export before/after Color Page frames and fail unless rendered pixels change"),
):
    """Set native Color Page hue curve point(s) via DB and rendered-frame proof."""
    from ..core import color_page_db

    clip_name = _option_value(clip_name)
    normalized_mode = mode.strip().lower().replace("_", "-")
    points = _option_value(points)
    require_render_proof = bool(_option_value(require_render_proof, True))

    set_execution_engine("db_workaround", 0.75)
    set_capability_context("color.page_hue_curve_set", "supported")

    parsed_points = None
    if points is not None:
        if input_hue is not None or hue_rotate is not None or saturation is not None or lum_gain is not None:
            raise ValidationError(
                "Color Page hue-curve-set --points cannot be combined with single-point hue curve options.",
                details={
                    "points": points,
                    "input_hue": input_hue,
                    "hue_rotate": hue_rotate,
                    "saturation": saturation,
                    "lum_gain": lum_gain,
                },
                recoverability="not_applicable",
            )
        parsed_points = color_page_db.parse_hue_curve_points_spec(points, mode=normalized_mode)
    elif normalized_mode == "hue-vs-hue":
        if input_hue is None:
            raise ValidationError(
                "--input-hue is required when --points is not used.",
                details={"mode": normalized_mode},
                recoverability="not_applicable",
            )
        color_page_db.hue_curve_input_hue_to_internal(float(input_hue))
        if hue_rotate is None:
            raise ValidationError(
                "--hue-rotate is required when --mode hue-vs-hue.",
                details={"mode": normalized_mode},
                recoverability="not_applicable",
            )
        color_page_db.hue_curve_rotate_to_internal(float(hue_rotate))
    elif normalized_mode == "hue-vs-sat":
        if input_hue is None:
            raise ValidationError(
                "--input-hue is required when --points is not used.",
                details={"mode": normalized_mode},
                recoverability="not_applicable",
            )
        color_page_db.hue_curve_input_hue_to_internal(float(input_hue))
        if saturation is None:
            raise ValidationError(
                "--saturation is required when --mode hue-vs-sat.",
                details={"mode": normalized_mode},
                recoverability="not_applicable",
            )
        color_page_db.hue_curve_saturation_to_internal(float(saturation))
    elif normalized_mode == "hue-vs-lum":
        if input_hue is None:
            raise ValidationError(
                "--input-hue is required when --points is not used.",
                details={"mode": normalized_mode},
                recoverability="not_applicable",
            )
        color_page_db.hue_curve_input_hue_to_internal(float(input_hue))
        if lum_gain is None:
            raise ValidationError(
                "--lum-gain is required when --mode hue-vs-lum.",
                details={"mode": normalized_mode},
                recoverability="not_applicable",
            )
        color_page_db.hue_curve_lum_gain_to_internal(float(lum_gain))
    else:
        raise ValidationError(
            "--mode must be hue-vs-hue, hue-vs-sat, or hue-vs-lum.",
            details={"mode": mode, "supported_modes": ["hue-vs-hue", "hue-vs-sat", "hue-vs-lum"]},
            recoverability="not_applicable",
        )

    enforce_mutation_policy(
        "color.page_hue_curve_set",
        intended_engine="db_workaround",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        detail = " points" if parsed_points is not None else ""
        proof_note = "with render proof" if require_render_proof else "as setup-only DB readback"
        dry_run_message(f"Would set Color Page {normalized_mode} curve{detail} via DB {proof_note}")
        return

    conn = get_connection(require_timeline=True)
    route = f"db_workaround_color_page_{normalized_mode.replace('-', '_')}"
    if parsed_points is not None:
        route = f"{route}_points"

    def _write_hue_curve():
        if parsed_points is not None:
            return color_page_db.write_hue_curve_points(
                conn,
                clip_name=clip_name,
                mode=normalized_mode,
                points=parsed_points,
            )
        if normalized_mode == "hue-vs-hue":
            return color_page_db.write_hue_vs_hue_curve(
                conn,
                clip_name=clip_name,
                input_hue=float(input_hue),
                hue_rotate=float(hue_rotate),
            )
        if normalized_mode == "hue-vs-sat":
            return color_page_db.write_hue_vs_sat_curve(
                conn,
                clip_name=clip_name,
                input_hue=float(input_hue),
                saturation=float(saturation),
            )
        return color_page_db.write_hue_vs_lum_curve(
            conn,
            clip_name=clip_name,
            input_hue=float(input_hue),
            lum_gain=float(lum_gain),
        )

    data = _complete_curve_render_proof_if_requested(
        conn=conn,
        clip_name=clip_name,
        route=route,
        require_render_proof=require_render_proof,
        write=_write_hue_curve,
    )
    output(data, title="Color Page — Hue Curve Set")
    success(f"Color Page {normalized_mode} curve written to DB.")


@page_app.command("sat-curve-set")
@handle_errors
def page_sat_curve_set(
    clip_name: Optional[str] = typer.Argument(None, help="Clip name"),
    input_sat: Optional[float] = typer.Option(None, "--input-sat", help="Saturation curve GUI Input Sat value (0..1)"),
    input_lum: Optional[float] = typer.Option(None, "--input-lum", help="Lum vs Sat GUI Input Lum value (0..1)"),
    output_sat: Optional[float] = typer.Option(None, "--output-sat", help="Sat vs Sat GUI Output Sat value (0..2)"),
    saturation: Optional[float] = typer.Option(None, "--saturation", help="Lum vs Sat GUI Saturation value (0..2)"),
    lum: Optional[float] = typer.Option(None, "--lum", help="Sat vs Lum GUI Lum value (0..2)"),
    mode: str = typer.Option("sat-vs-sat", "--mode", help="Saturation curve mode: sat-vs-sat, sat-vs-lum, or lum-vs-sat"),
    points: Optional[str] = typer.Option(None, "--points", help='Multi-point saturation curve pairs as "input,value;input,value"'),
    require_render_proof: bool = typer.Option(True, "--require-render-proof/--setup-only", help="Export before/after Color Page frames and fail unless rendered pixels change"),
):
    """Set a native Color Page saturation curve point via DB and rendered-frame proof."""
    from ..core import color_page_db

    clip_name = _option_value(clip_name)
    points = _option_value(points)
    normalized_mode = mode.strip().lower().replace("_", "-")
    require_render_proof = bool(_option_value(require_render_proof, True))
    parsed_points = None

    set_execution_engine("db_workaround", 0.75)
    set_capability_context("color.page_sat_curve_set", "supported")

    if points is not None:
        if any(value is not None for value in (input_sat, input_lum, output_sat, saturation, lum)):
            raise ValidationError(
                "Use either --points or a single saturation curve input/value pair, not both.",
                details={
                    "points": points,
                    "input_sat": input_sat,
                    "input_lum": input_lum,
                    "output_sat": output_sat,
                    "saturation": saturation,
                    "lum": lum,
                },
                recoverability="not_applicable",
            )
        parsed_points = color_page_db.parse_sat_curve_points_spec(points, mode=normalized_mode)
    elif normalized_mode == "sat-vs-sat":
        if input_sat is None:
            raise ValidationError(
                "--input-sat is required when --mode sat-vs-sat.",
                details={"mode": normalized_mode},
                recoverability="not_applicable",
            )
        if output_sat is None:
            raise ValidationError(
                "--output-sat is required when --mode sat-vs-sat.",
                details={"mode": normalized_mode},
                recoverability="not_applicable",
            )
        color_page_db.sat_curve_output_sat_to_internal(float(output_sat))
    elif normalized_mode == "sat-vs-lum":
        if input_sat is None:
            raise ValidationError(
                "--input-sat is required when --mode sat-vs-lum.",
                details={"mode": normalized_mode},
                recoverability="not_applicable",
            )
        if lum is None:
            raise ValidationError(
                "--lum is required when --mode sat-vs-lum.",
                details={"mode": normalized_mode},
                recoverability="not_applicable",
            )
        color_page_db.sat_curve_lum_to_internal(float(lum))
    elif normalized_mode == "lum-vs-sat":
        if input_lum is None:
            raise ValidationError(
                "--input-lum is required when --mode lum-vs-sat.",
                details={"mode": normalized_mode},
                recoverability="not_applicable",
            )
        if saturation is None:
            raise ValidationError(
                "--saturation is required when --mode lum-vs-sat.",
                details={"mode": normalized_mode},
                recoverability="not_applicable",
            )
        color_page_db.lum_curve_input_lum_to_internal(float(input_lum))
        color_page_db.sat_curve_output_sat_to_internal(float(saturation))
    else:
        raise ValidationError(
            "--mode must be sat-vs-sat, sat-vs-lum, or lum-vs-sat.",
            details={"mode": mode, "supported_modes": ["sat-vs-sat", "sat-vs-lum", "lum-vs-sat"]},
            recoverability="not_applicable",
        )
    if input_sat is not None:
        color_page_db.sat_curve_input_sat_to_internal(float(input_sat))

    enforce_mutation_policy(
        "color.page_sat_curve_set",
        intended_engine="db_workaround",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        proof_note = "with render proof" if require_render_proof else "as setup-only DB readback"
        dry_run_message(f"Would set Color Page {normalized_mode} curve{' points' if parsed_points is not None else ''} via DB {proof_note}")
        return

    conn = get_connection(require_timeline=True)
    route = f"db_workaround_color_page_{normalized_mode.replace('-', '_')}"
    if parsed_points is not None:
        route = f"{route}_points"

    def _write_sat_curve():
        if parsed_points is not None:
            return color_page_db.write_sat_curve_points(
                conn,
                clip_name=clip_name,
                mode=normalized_mode,
                points=parsed_points,
            )
        if normalized_mode == "sat-vs-sat":
            return color_page_db.write_sat_vs_sat_curve(
                conn,
                clip_name=clip_name,
                input_sat=float(input_sat),
                output_sat=float(output_sat),
            )
        if normalized_mode == "sat-vs-lum":
            return color_page_db.write_sat_vs_lum_curve(
                conn,
                clip_name=clip_name,
                input_sat=float(input_sat),
                lum=float(lum),
            )
        return color_page_db.write_lum_vs_sat_curve(
            conn,
            clip_name=clip_name,
            input_lum=float(input_lum),
            saturation=float(saturation),
        )

    data = _complete_curve_render_proof_if_requested(
        conn=conn,
        clip_name=clip_name,
        route=route,
        require_render_proof=require_render_proof,
        write=_write_sat_curve,
    )
    output(data, title="Color Page — Saturation Curve Set")
    success(f"Color Page {normalized_mode} curve written to DB.")


@page_app.command("hdr-global-set")
@handle_errors
def page_hdr_global_set(
    clip_name: Optional[str] = typer.Argument(None, help="Clip name"),
    exposure: Optional[float] = typer.Option(None, "--exposure", "--exp", help="HDR Global Exposure value"),
    saturation: Optional[float] = typer.Option(None, "--saturation", "--sat", help="HDR Global Saturation value"),
    require_render_proof: bool = typer.Option(
        True,
        "--require-render-proof/--setup-only",
        help="Export before/after Color Page frames and fail unless the rendered image changes.",
    ),
):
    """Set native Color Page HDR Global exposure/saturation via DB and rendered-frame proof."""
    from ..core import color_page_db

    clip_name = _option_value(clip_name)
    exposure = _option_value(exposure)
    saturation = _option_value(saturation)
    require_render_proof = bool(_option_value(require_render_proof, True))

    set_execution_engine("db_workaround", 0.75)
    set_capability_context("color.page_hdr_global_set", "supported")

    if exposure is None and saturation is None:
        raise ValidationError(
            "Color Page hdr-global-set requires --exposure/--exp or --saturation/--sat.",
            recoverability="not_applicable",
        )
    if exposure is not None:
        color_page_db._validate_hdr_global_value("exposure", float(exposure), minimum=-4.0, maximum=4.0)
    if saturation is not None:
        color_page_db._validate_hdr_global_value("saturation", float(saturation), minimum=0.0, maximum=4.0)

    enforce_mutation_policy(
        "color.page_hdr_global_set",
        intended_engine="db_workaround",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        output(
            {
                "message": "DRY-RUN: Would set Color Page HDR Global controls via DB.",
                "route": "db_workaround_color_page_hdr_global",
                "clip": clip_name,
                "requested": {
                    "exposure": exposure,
                    "saturation": saturation,
                },
                "render_proof_required": require_render_proof,
                "render_proof": {
                    "status": "would_run" if require_render_proof else "not_requested",
                    "required": require_render_proof,
                },
            },
            title="Color Page — HDR Global Set Preview",
        )
        return

    conn = get_connection(require_timeline=True)
    render_proof = None
    if require_render_proof:
        render_proof = _begin_color_render_proof(
            conn,
            clip_name=clip_name,
            route="db_workaround_color_page_hdr_global",
        )
    data = color_page_db.write_hdr_global(
        conn,
        clip_name=clip_name,
        exposure=exposure,
        saturation=saturation,
    )
    data.setdefault("verification", {})
    if render_proof is not None:
        conn_after = get_connection(require_timeline=True)
        try:
            data["render_proof"] = _complete_color_render_proof(conn_after, render_proof, partial_result=data)
        except ColorRenderProofFailed as exc:
            from ..core.db_session import restore_project_db_backup_from_mutation_result

            rollback = restore_project_db_backup_from_mutation_result(conn_after, data)
            data["rollback_after_failed_render_proof"] = rollback
            if isinstance(exc.details, dict):
                exc.details["rollback_after_failed_render_proof"] = rollback
                partial = exc.details.get("partial_result")
                if isinstance(partial, dict):
                    partial["rollback_after_failed_render_proof"] = rollback
            raise
        data["verification"]["status"] = "verified"
        data["verification"]["render_proof_status"] = data["render_proof"]["status"]
        data["verification"]["render_proof_route"] = data["render_proof"]["route"]
        data["verification"]["render_proof_required"] = True
        set_verification_status("verified")
        set_recoverability("not_applicable")
    else:
        data["verification"]["render_proof_status"] = "not_requested"
        data["verification"]["render_proof_required"] = False
    output(data, title="Color Page — HDR Global Set")
    success("Color Page HDR Global values written and verified.")


@page_app.command("key-output-set")
@handle_errors
def page_key_output_set(
    clip_name: Optional[str] = typer.Argument(None, help="Clip name"),
    gain: float = typer.Option(..., "--gain", "--output-gain", help="Key Output Gain value, 0..1"),
):
    """Set native Color Page Key Output Gain via DB."""
    from ..core import color_page_db

    clip_name = _option_value(clip_name)
    gain = _option_value(gain)

    set_execution_engine("db_workaround", 0.75)
    set_capability_context("color.page_key_output_set", "supported")
    color_page_db.validate_key_output_gain(float(gain))

    enforce_mutation_policy(
        "color.page_key_output_set",
        intended_engine="db_workaround",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        dry_run_message("Would set Color Page Key Output Gain via DB")
        return

    conn = get_connection(require_timeline=True)
    data = color_page_db.write_key_output(conn, clip_name=clip_name, gain=float(gain))
    output(data, title="Color Page — Key Output Set")
    success("Color Page Key Output Gain written to DB.")


@page_app.command("rgb-mixer-set")
@handle_errors
def page_rgb_mixer_set(
    clip_name: Optional[str] = typer.Argument(None, help="Clip name"),
    node_index: int = typer.Option(1, "--node-index", "--node", help="1-based Color Page node index"),
    monochrome: bool = typer.Option(True, "--monochrome/--no-monochrome", help="Enable RGB Mixer Monochrome mode"),
    preserve_luminance: bool = typer.Option(True, "--preserve-luminance/--no-preserve-luminance", help="Preserve luminance while monochrome is enabled"),
    red: Optional[float] = typer.Option(None, "--red", help="Requested RGB Mixer red coefficient; currently returns an explicit unsupported diagnostic"),
    green: Optional[float] = typer.Option(None, "--green", help="Requested RGB Mixer green coefficient; currently returns an explicit unsupported diagnostic"),
    blue: Optional[float] = typer.Option(None, "--blue", help="Requested RGB Mixer blue coefficient; currently returns an explicit unsupported diagnostic"),
):
    """Set verified Color Page RGB Mixer Monochrome controls via DB."""
    from ..core import color_page_db

    clip_name = _option_value(clip_name)
    node_index = int(_option_value(node_index) or 1)
    monochrome = bool(_option_value(monochrome))
    preserve_luminance = bool(_option_value(preserve_luminance))
    red = _option_value(red)
    green = _option_value(green)
    blue = _option_value(blue)
    has_coefficients = any(value is not None for value in (red, green, blue))

    set_execution_engine("db_workaround", 0.75)
    set_capability_context("color.page_rgb_mixer_monochrome", "supported")
    if node_index < 1:
        raise ValidationError(
            "Node index must be a positive integer.",
            details={"node_index": node_index, "minimum": 1},
            recoverability="not_applicable",
        )
    if has_coefficients:
        _unsupported_color_page_preview(
            "color.page_rgb_mixer_coefficients",
            "not_available_color_page_rgb_mixer_coefficients",
            {
                "clip": clip_name,
                "node_index": node_index,
                "requested_coefficients": {
                    "red": red,
                    "green": green,
                    "blue": blue,
                },
                "verified_slices": ["color.page_rgb_mixer_monochrome"],
            },
            "Color Page — RGB Mixer Coefficients",
        )
        return
    elif monochrome and not preserve_luminance:
        raise ValidationError(
            "RGB Mixer Monochrome without Preserve Luminance is not yet verified.",
            details={"monochrome": monochrome, "preserve_luminance": preserve_luminance},
            recoverability="not_applicable",
        )

    enforce_mutation_policy(
        "color.page_rgb_mixer_monochrome",
        intended_engine="db_workaround",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        dry_run_message("Would set Color Page RGB Mixer Monochrome")
        return

    conn = get_connection(require_timeline=True)
    data = color_page_db.write_rgb_mixer_monochrome(
        conn,
        clip_name=clip_name,
        node_index=node_index,
        monochrome=monochrome,
        preserve_luminance=preserve_luminance,
    )
    output(data, title="Color Page — RGB Mixer Set")
    success("Color Page RGB Mixer Monochrome applied.")


@page_app.command("layer-mixer-set")
@handle_errors
def page_layer_mixer_set(
    clip_name: Optional[str] = typer.Argument(None, help="Clip name"),
    node_index: int = typer.Option(2, "--node-index", "--node", help="1-based layer node index feeding the Layer Mixer"),
    mode: str = typer.Option("Overlay", "--mode", help="Layer Mixer composite mode"),
    opacity: Optional[float] = typer.Option(None, "--opacity", help="Layer Mixer branch opacity, 0..100"),
):
    """Set verified Color Page Layer Mixer composite mode and branch opacity on Disk projects."""
    from ..core import color_page_db

    clip_name = _option_value(clip_name)
    node_index = int(_option_value(node_index) or 2)
    mode = str(_option_value(mode) or "Overlay")
    opacity = _option_value(opacity)

    capability_id = "color.page_layer_mixer_opacity" if opacity is not None else "color.page_layer_mixer_composite"
    set_capability_context(capability_id, "supported")
    set_execution_engine("db_workaround", 0.86)
    if node_index < 1:
        raise ValidationError(
            "Layer node index must be a positive integer.",
            details={"node_index": node_index, "minimum": 1},
            recoverability="not_applicable",
        )
    mode_label, _mode_value = color_page_db.validate_layer_mixer_composite_mode(mode)
    if opacity is not None and (not math.isfinite(float(opacity)) or float(opacity) < 0.0 or float(opacity) > 100.0):
        raise ValidationError(
            "Layer Mixer branch opacity must be between 0 and 100.",
            details={"opacity": float(opacity), "minimum": 0.0, "maximum": 100.0},
            recoverability="not_applicable",
        )

    enforce_mutation_policy(
        capability_id,
        intended_engine="db_workaround",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        suffix = "" if opacity is None else f" and branch opacity to {float(opacity):.3f}"
        dry_run_message(f"Would set Color Page Layer Mixer composite mode to {mode_label}{suffix}")
        return

    conn = get_connection(require_timeline=True)
    data = color_page_db.write_layer_mixer_composite_mode(
        conn,
        clip_name=clip_name,
        layer_node_index=node_index,
        mode=mode,
        opacity=float(opacity) if opacity is not None else None,
    )
    output(data, title="Color Page — Layer Mixer Set")
    success("Color Page Layer Mixer settings applied.")


@page_app.command("bleach-bypass-set")
@handle_errors
def page_bleach_bypass_set(
    clip_name: Optional[str] = typer.Argument(None, help="Clip name"),
    gain: Optional[float] = typer.Option(None, "--gain", "--intensity", help="Optional bleach bypass branch Key Output Gain, 0..1"),
    contrast: Optional[float] = typer.Option(None, "--contrast", help="Requested extra bleach-bypass contrast; currently returns an explicit unsupported diagnostic"),
    desaturation: Optional[float] = typer.Option(None, "--desaturation", "--desat", help="Requested extra desaturation; currently returns an explicit unsupported diagnostic"),
    topology_policy: Optional[str] = typer.Option(None, "--topology-policy", help="Requested topology policy; currently returns an explicit unsupported diagnostic"),
):
    """Apply a verified Color Page bleach-bypass Layer Mixer look, optionally with intensity."""
    from ..core import color_page_db

    clip_name = _option_value(clip_name)
    gain = _option_value(gain)
    contrast = _option_value(contrast)
    desaturation = _option_value(desaturation)
    topology_policy = _option_value(topology_policy)

    set_capability_context("color.page_bleach_bypass", "supported")
    set_execution_engine("db_workaround", 0.86)
    if contrast is not None or desaturation is not None or topology_policy is not None:
        _unsupported_color_page_preview(
            "color.page_bleach_bypass_parametric",
            "not_available_color_page_bleach_bypass_parametric",
            {
                "clip": clip_name,
                "requested_gain": gain,
                "requested_contrast": contrast,
                "requested_desaturation": desaturation,
                "requested_topology_policy": topology_policy,
                "verified_slices": ["color.page_bleach_bypass", "color.page_bleach_bypass_intensity"],
                "rejected_workarounds": ["hidden-primary-contrast", "hidden-desaturation", "recipe-topology-alias"],
            },
            "Color Page — Bleach Bypass Parametric",
        )
        return
    if gain is not None:
        color_page_db.validate_key_output_gain(float(gain))
    enforce_mutation_policy(
        "color.page_bleach_bypass",
        intended_engine="db_workaround",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        if gain is None:
            dry_run_message("Would apply Color Page bleach bypass via Layer Mixer Overlay")
        else:
            dry_run_message("Would apply Color Page bleach bypass topology and Key Output intensity")
        return

    conn = get_connection(require_timeline=True)
    if gain is None:
        data = color_page_db.write_bleach_bypass(conn, clip_name=clip_name)
    else:
        data = color_page_db.write_bleach_bypass_intensity(
            conn,
            clip_name=clip_name,
            gain=float(gain),
            connection_factory=lambda: get_connection(require_timeline=True),
        )
        if isinstance(data.get("verification"), dict) and data["verification"].get("status") == "verified":
            set_verification_status("verified")
            set_recoverability("not_applicable")
    output(data, title="Color Page — Bleach Bypass")
    success("Color Page bleach bypass applied.")


@page_app.command("bleach-bypass-intensity-set")
@handle_errors
def page_bleach_bypass_intensity_set(
    clip_name: Optional[str] = typer.Argument(None, help="Clip name"),
    gain: float = typer.Option(..., "--gain", "--intensity", help="Bleach bypass branch Key Output Gain, 0..1"),
):
    """Set verified Color Page bleach-bypass intensity via Key Output Gain."""
    from ..core import color_page_db

    clip_name = _option_value(clip_name)
    gain = _option_value(gain)

    set_capability_context("color.page_bleach_bypass_intensity", "supported")
    set_execution_engine("db_workaround", 0.86)
    color_page_db.validate_key_output_gain(float(gain))
    enforce_mutation_policy(
        "color.page_bleach_bypass_intensity",
        intended_engine="db_workaround",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        dry_run_message("Would set Color Page bleach bypass intensity via Key Output Gain")
        return

    conn = get_connection(require_timeline=True)
    data = color_page_db.write_bleach_bypass_intensity(
        conn,
        clip_name=clip_name,
        gain=float(gain),
        connection_factory=lambda: get_connection(require_timeline=True),
    )
    if isinstance(data.get("verification"), dict) and data["verification"].get("status") == "verified":
        set_verification_status("verified")
        set_recoverability("not_applicable")
    output(data, title="Color Page — Bleach Bypass Intensity")
    success("Color Page bleach bypass intensity applied.")
