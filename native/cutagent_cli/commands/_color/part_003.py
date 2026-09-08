from __future__ import annotations

@app.command("auto-color")
@handle_errors
def auto_color(
    input_file: str = typer.Option(..., "--input", "-i", help="Input video file to analyze"),
    clip_name: Optional[str] = typer.Argument(None, help="Clip name to apply CDL to"),
    node: int = typer.Option(1, help="Node index to apply CDL"),
    frame: int = typer.Option(100, "--frame", help="Frame number to sample for analysis"),
    apply: bool = typer.Option(True, "--apply/--no-apply", help="Apply CDL to clip (or just analyze)"),
):
    """Analyze a video file and generate auto-color CDL correction.

    Uses ffmpeg signalstats to measure luma (Y) and chroma (Cb/Cr) levels,
    then calculates CDL slope/offset to normalize to target levels.
    With --no-apply, only prints the analysis without modifying any clip.
    """
    input_path = _validate_auto_color_request(input_file, node, frame, apply, clip_name)
    if apply:
        enforce_mutation_policy(
            "color.cdl_set",
            intended_engine="workaround_setting",
            mutating=not is_dry_run(),
        )
    else:
        set_execution_engine("workaround_setting")
        set_verification_status("not_requested")
        set_recoverability("not_applicable")

    if is_dry_run():
        if apply:
            conn = get_connection(require_timeline=True)
            item = color_ops.resolve_item(conn, clip_name)
            target = item.GetName() if hasattr(item, "GetName") else clip_name
            set_verification_status("not_requested")
            set_recoverability("not_applicable")
            output(
                {
                    "message": f"DRY-RUN: Would analyze '{input_path}' and apply auto-color CDL to '{target}'",
                    "input": str(input_path),
                    "clip": target,
                    "node": node,
                    "frame": frame,
                    "apply": True,
                }
            )
            return

    conn = None
    if apply:
        conn = get_connection(require_timeline=True)
        color_ops.resolve_item(conn, clip_name)

    # Extract a single frame and analyze with signalstats
    stats = {}
    result = None
    temp_dir = tempfile.mkdtemp(prefix="resolve_autocolor_")
    try:
        stats_file = os.path.join(temp_dir, "stats.txt")
        cmd = [
            resolve_tool("ffmpeg"), "-y",
            "-i", str(input_path),
            "-vf", f"select=eq(n\\,{frame}),signalstats,metadata=print:file={stats_file}",
            "-frames:v", "1",
            "-f", "null", "-",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

        # Parse signalstats output
        try:
            with open(stats_file, "r") as f:
                for line in f:
                    # Format: lavfi.signalstats.YAVG=128.5
                    m = re.search(r"lavfi\.signalstats\.(\w+)=([\d.]+)", line)
                    if m:
                        stats[m.group(1)] = float(m.group(2))
        except FileNotFoundError:
            # Fallback: parse from stderr
            for line in result.stderr.splitlines():
                m = re.search(r"lavfi\.signalstats\.(\w+)=([\d.]+)", line)
                if m:
                    stats[m.group(1)] = float(m.group(2))
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    if not stats:
        raise APICallFailed(
            f"Failed to analyze video with signalstats. "
            f"ffmpeg stderr: {(result.stderr if result is not None else '')[-300:]}"
        )

    # Key stats: YAVG (luma avg), YMIN, YMAX, UAVG (Cb), VAVG (Cr)
    y_avg = stats.get("YAVG", 128)
    y_min = stats.get("YMIN", 16)
    y_max = stats.get("YMAX", 235)
    u_avg = stats.get("UAVG", 128)  # Cb (should be ~128 for neutral)
    v_avg = stats.get("VAVG", 128)  # Cr (should be ~128 for neutral)

    # Target values (broadcast standard: 16-235 range)
    target_y = 128.0   # middle gray
    target_uv = 128.0  # neutral chroma

    # Calculate CDL slope (gain) to normalize luma
    # slope = target / current (in 0-1 normalized space)
    y_norm = y_avg / 255.0
    target_y_norm = target_y / 255.0
    base_slope = target_y_norm / max(y_norm, 0.01)
    base_slope = max(0.5, min(2.0, base_slope))

    # White balance correction from chroma deviation
    # Cb > 128 = blue cast → reduce blue, boost red
    # Cr > 128 = red cast → reduce red, boost blue
    u_deviation = (u_avg - target_uv) / 255.0  # blue-yellow axis
    v_deviation = (v_avg - target_uv) / 255.0  # red-cyan axis

    slope_r = max(0.5, min(2.0, base_slope + v_deviation * 0.5))
    slope_g = max(0.5, min(2.0, base_slope))
    slope_b = max(0.5, min(2.0, base_slope + u_deviation * 0.5))

    # Calculate offset to lift blacks if crushed
    offset_val = 0.0
    if y_min < 10:
        offset_val = (16 - y_min) / 255.0  # lift to broadcast black
        offset_val = max(0.0, min(0.1, offset_val))

    slope_str = f"{slope_r:.3f} {slope_g:.3f} {slope_b:.3f}"
    offset_str = f"{offset_val:.3f} {offset_val:.3f} {offset_val:.3f}" if offset_val > 0.001 else None

    analysis = {
        "input": str(input_path),
        "frame": frame,
        "luma_avg": round(y_avg, 1),
        "luma_min": round(y_min, 1),
        "luma_max": round(y_max, 1),
        "chroma_cb": round(u_avg, 1),
        "chroma_cr": round(v_avg, 1),
        "slope": slope_str,
        "offset": offset_str,
        "node": node,
    }

    if apply:
        if conn is None:
            conn = get_connection(require_timeline=True)
        color_ops.set_cdl(
            conn, clip_name, node,
            slope=slope_str,
            offset=offset_str,
            power=None,
            saturation=None,
        )
        analysis["applied"] = True
        output(analysis, title="Auto-Color CDL Applied")
        success(f"Applied auto-color CDL on node {node}: slope={slope_str}")
    else:
        analysis["applied"] = False
        output(analysis, title="Auto-Color Analysis")


@primary_app.command("get")
@handle_errors
def primary_get(
    clip_name: Optional[str] = typer.Option(None, "--clip", help="Clip name (current clip when omitted)"),
    comp_index: int = typer.Option(1, "--comp", help="Fusion composition index"),
):
    """Read primary Fusion color-corrector state from the clip."""
    conn = get_connection(require_timeline=True)
    data = color_ops.get_primary_grade(conn, clip_name, comp_index=comp_index)
    output(data, title="Primary Grade")


@graph_app.command("inspect")
@handle_errors
def graph_inspect(
    clip_name: Optional[str] = typer.Option(None, "--clip", help="Clip name (current clip when omitted)"),
    comp_index: int = typer.Option(1, "--comp", help="Fusion composition index"),
):
    """Inspect clip-attached Fusion grading graph state."""
    set_execution_engine("api_native")
    set_capability_context("color.node_graph_ops", "supported")
    if comp_index < 1:
        raise ValidationError(
            "Fusion composition index must be a positive integer.",
            details={"clip": clip_name, "comp_index": comp_index},
        )
    normalized_clip = None
    if clip_name is not None:
        normalized_clip = clip_name.strip()
        if not normalized_clip:
            raise ValidationError("Clip name must not be empty.", details={"clip": clip_name})
    conn = get_connection(require_timeline=True)
    data = color_ops.inspect_fusion_graph(conn, normalized_clip, comp_index=comp_index)
    output(data, title="Fusion Graph")


@graph_app.command("validate")
@handle_errors
def graph_validate(
    clip_name: Optional[str] = typer.Option(None, "--clip", help="Clip name (current clip when omitted)"),
    comp_index: int = typer.Option(1, "--comp", help="Fusion composition index"),
    strict: bool = typer.Option(False, "--strict", help="Treat orphaned grading tools as errors"),
):
    """Validate the Fusion grading graph invariants."""
    set_execution_engine("api_native")
    set_capability_context("color.node_graph_ops", "supported")
    if comp_index < 1:
        raise ValidationError(
            "Fusion composition index must be a positive integer.",
            details={"clip": clip_name, "comp_index": comp_index},
        )
    normalized_clip = None
    if clip_name is not None:
        normalized_clip = clip_name.strip()
        if not normalized_clip:
            raise ValidationError("Clip name must not be empty.", details={"clip": clip_name})
    conn = get_connection(require_timeline=True)
    data = color_ops.validate_fusion_graph(conn, normalized_clip, comp_index=comp_index, strict=strict)
    output(data, title="Fusion Graph Validate")


@graph_app.command("normalize")
@handle_errors
def graph_normalize(
    clip_name: Optional[str] = typer.Option(None, "--clip", help="Clip name (current clip when omitted)"),
    comp_index: int = typer.Option(1, "--comp", help="Fusion composition index"),
):
    """Normalize the grading graph into the canonical no-GUI layout."""
    enforce_mutation_policy("fusion.mutation", intended_engine="fusion_native")
    conn = get_connection(require_timeline=True)
    data = color_ops.normalize_fusion_graph(conn, clip_name, comp_index=comp_index)
    output(data, title="Fusion Graph Normalize")


@primary_app.command("set")
@handle_errors
def primary_set(
    clip_name: Optional[str] = typer.Option(None, "--clip", help="Clip name (current clip when omitted)"),
    comp_index: int = typer.Option(1, "--comp", help="Fusion composition index"),
    gain_r: Optional[float] = typer.Option(None, "--gain-r", help="Red gain"),
    gain_g: Optional[float] = typer.Option(None, "--gain-g", help="Green gain"),
    gain_b: Optional[float] = typer.Option(None, "--gain-b", help="Blue gain"),
    gamma: Optional[float] = typer.Option(None, "--gamma", help="Master gamma"),
    saturation: Optional[float] = typer.Option(None, "--saturation", "--sat", help="Saturation"),
    master_gain: Optional[float] = typer.Option(None, "--master-gain", help="Master gain"),
):
    """Create/update a clip-attached Fusion ColorCorrector primary grade."""
    if not any(v is not None for v in (gain_r, gain_g, gain_b, gamma, saturation, master_gain)):
        raise ValidationError(
            "Specify at least one primary parameter to set.",
            details={
                "gain_r": gain_r,
                "gain_g": gain_g,
                "gain_b": gain_b,
                "gamma": gamma,
                "saturation": saturation,
                "master_gain": master_gain,
            },
        )
    enforce_mutation_policy(
        "fusion.mutation",
        intended_engine="fusion_native",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        dry_run_message("Would set the clip-attached primary grade parameters.")
        return

    conn = get_connection(require_timeline=True)
    data = color_ops.set_primary_grade(
        conn,
        clip_name,
        comp_index=comp_index,
        gain_r=gain_r,
        gain_g=gain_g,
        gain_b=gain_b,
        gamma=gamma,
        saturation=saturation,
        master_gain=master_gain,
    )
    _mark_color_render_unverified(data, readback_source="clip_attached_fusion_comp")
    output(data, title="Primary Grade")


@comp_app.command("doctor")
@handle_errors
def comp_doctor(
    clip_name: Optional[str] = typer.Option(None, "--clip", help="Clip name (current clip when omitted)"),
    comp_index: int = typer.Option(1, "--comp", help="Fusion composition index"),
    strict: bool = typer.Option(False, "--strict", help="Treat orphaned grading tools as errors"),
):
    """Inspect and validate a clip-attached Fusion grading comp."""
    conn = get_connection(require_timeline=True)
    data = color_ops.doctor_fusion_comp(conn, clip_name, comp_index=comp_index, strict=strict)
    output(data, title="Fusion Comp Doctor")


@comp_app.command("repair")
@handle_errors
def comp_repair(
    clip_name: Optional[str] = typer.Option(None, "--clip", help="Clip name (current clip when omitted)"),
    comp_index: int = typer.Option(1, "--comp", help="Fusion composition index"),
    prune_orphans: bool = typer.Option(True, "--prune-orphans/--keep-orphans", help="Delete orphaned grading tools"),
):
    """Repair a broken grading comp and optionally prune orphaned tools."""
    enforce_mutation_policy("fusion.mutation", intended_engine="fusion_native")
    conn = get_connection(require_timeline=True)
    data = color_ops.repair_fusion_comp(conn, clip_name, comp_index=comp_index, prune_orphans=prune_orphans)
    output(data, title="Fusion Comp Repair")


@comp_app.command("flatten")
@handle_errors
def comp_flatten(
    clip_name: Optional[str] = typer.Option(None, "--clip", help="Clip name (current clip when omitted)"),
    comp_index: int = typer.Option(1, "--comp", help="Fusion composition index"),
):
    """Flatten grading comp back to primary-only image processing."""
    enforce_mutation_policy("fusion.mutation", intended_engine="fusion_native")
    conn = get_connection(require_timeline=True)
    data = color_ops.flatten_fusion_comp(conn, clip_name, comp_index=comp_index)
    output(data, title="Fusion Comp Flatten")


@comp_app.command("export")
@handle_errors
def comp_export(
    output_path: str = typer.Argument(..., help="Output .setting path"),
    clip_name: Optional[str] = typer.Option(None, "--clip", help="Clip name (current clip when omitted)"),
    comp_index: int = typer.Option(1, "--comp", help="Fusion composition index"),
):
    """Export the clip-attached Fusion grading comp."""
    enforce_mutation_policy("clip.fusion_comp", intended_engine="api_native", mutating=False)
    resolved_output_path = clip_ops.validate_fusion_export_request(comp_index, output_path)
    enforce_mutation_policy("clip.fusion_comp", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        dry_run_message(
            f"Would export Fusion grading composition {comp_index} from '{clip_name or 'current'}' to: {resolved_output_path}"
        )
        return

    conn = get_connection(require_timeline=True)
    data = color_ops.export_fusion_comp(conn, clip_name, resolved_output_path, comp_index=comp_index)
    output(data, title="Fusion Comp Export")


@window_app.command("list")
@handle_errors
def window_list(
    clip_name: Optional[str] = typer.Option(None, "--clip", help="Clip name (current clip when omitted)"),
    comp_index: int = typer.Option(1, "--comp", help="Fusion composition index"),
):
    """List clip-attached Fusion windows/masks."""
    conn = get_connection(require_timeline=True)
    rows = color_ops.list_windows(conn, clip_name, comp_index=comp_index)
    output(rows, columns=[("name", "Name"), ("type", "Type"), ("shape", "Shape")], title="Color Windows")


@window_app.command("rectangle")
@handle_errors
def window_rectangle(
    clip_name: Optional[str] = typer.Option(None, "--clip", help="Clip name (current clip when omitted)"),
    center: str = typer.Option("0.5,0.5", "--center", help="Center X,Y"),
    width: float = typer.Option(0.5, "--width", help="Width"),
    height: float = typer.Option(0.5, "--height", help="Height"),
    softness: float = typer.Option(0.0, "--softness", help="Soft edge"),
    comp_index: int = typer.Option(1, "--comp", help="Fusion composition index"),
):
    """Add a rectangular grading window via Fusion mask."""
    set_execution_engine("fusion_native")
    set_capability_context("fusion.mutation", "supported")
    shape, center_xy, width, height, softness, comp_index = color_ops.validate_window_geometry_request(
        shape="rectangle",
        center=center,
        width=width,
        height=height,
        softness=softness,
        comp_index=comp_index,
    )
    normalized_clip = None
    if clip_name is not None:
        normalized_clip = clip_name.strip()
        if not normalized_clip:
            raise ValidationError(
                "Clip name must not be empty.",
                details={"clip": clip_name},
                recoverability="not_applicable",
            )
    enforce_mutation_policy("fusion.mutation", intended_engine="fusion_native", mutating=not is_dry_run())
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            {
                "clip": normalized_clip,
                "shape": shape,
                "center": [center_xy[0], center_xy[1]],
                "width": width,
                "height": height,
                "softness": softness,
                "comp_index": comp_index,
                "would_create": True,
                "created": False,
                "resolved": False,
            },
            title="Window Rectangle Preview",
        )
        return
    conn = get_connection(require_timeline=True)
    data = color_ops.add_window(
        conn,
        normalized_clip,
        shape=shape,
        center=center_xy,
        width=width,
        height=height,
        softness=softness,
        comp_index=comp_index,
    )
    output(data, title="Window Rectangle")


@window_app.command("ellipse")
@handle_errors
def window_ellipse(
    clip_name: Optional[str] = typer.Option(None, "--clip", help="Clip name (current clip when omitted)"),
    center: str = typer.Option("0.5,0.5", "--center", help="Center X,Y"),
    width: float = typer.Option(0.5, "--width", help="Width"),
    height: float = typer.Option(0.5, "--height", help="Height"),
    softness: float = typer.Option(0.0, "--softness", help="Soft edge"),
    comp_index: int = typer.Option(1, "--comp", help="Fusion composition index"),
):
    """Add an elliptical grading window via Fusion mask."""
    set_execution_engine("fusion_native")
    set_capability_context("fusion.mutation", "supported")
    shape, center_xy, width, height, softness, comp_index = color_ops.validate_window_geometry_request(
        shape="ellipse",
        center=center,
        width=width,
        height=height,
        softness=softness,
        comp_index=comp_index,
    )
    normalized_clip = None
    if clip_name is not None:
        normalized_clip = clip_name.strip()
        if not normalized_clip:
            raise ValidationError(
                "Clip name must not be empty.",
                details={"clip": clip_name},
                recoverability="not_applicable",
            )
    enforce_mutation_policy("fusion.mutation", intended_engine="fusion_native", mutating=not is_dry_run())
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            {
                "clip": normalized_clip,
                "shape": shape,
                "center": [center_xy[0], center_xy[1]],
                "width": width,
                "height": height,
                "softness": softness,
                "comp_index": comp_index,
                "would_create": True,
                "created": False,
                "resolved": False,
            },
            title="Window Ellipse Preview",
        )
        return
    conn = get_connection(require_timeline=True)
    data = color_ops.add_window(
        conn,
        normalized_clip,
        shape=shape,
        center=center_xy,
        width=width,
        height=height,
        softness=softness,
        comp_index=comp_index,
    )
    output(data, title="Window Ellipse")


@window_app.command("polygon")
@handle_errors
def window_polygon(
    points: str = typer.Argument(..., help="Points as 'x,y;x,y;...'"),
    clip_name: Optional[str] = typer.Option(None, "--clip", help="Clip name (current clip when omitted)"),
    comp_index: int = typer.Option(1, "--comp", help="Fusion composition index"),
):
    """Add a polygon grading window via Fusion mask."""
    set_execution_engine("fusion_native")
    set_capability_context("fusion.mutation", "supported")
    _, _, _, _, _, comp_index = color_ops.validate_window_geometry_request(
        shape="polygon",
        comp_index=comp_index,
    )
    parsed = color_ops.validate_polygon_points(points)
    normalized_clip = None
    if clip_name is not None:
        normalized_clip = clip_name.strip()
        if not normalized_clip:
            raise ValidationError(
                "Clip name must not be empty.",
                details={"clip": clip_name},
                recoverability="not_applicable",
            )
    enforce_mutation_policy("fusion.mutation", intended_engine="fusion_native", mutating=not is_dry_run())
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            {
                "clip": normalized_clip,
                "shape": "polygon",
                "points": [[x, y] for x, y in parsed],
                "point_count": len(parsed),
                "comp_index": comp_index,
                "would_create": True,
                "created": False,
                "resolved": False,
            },
            title="Window Polygon Preview",
        )
        return
    conn = get_connection(require_timeline=True)
    data = color_ops.add_window(conn, normalized_clip, shape="polygon", points=parsed, comp_index=comp_index)
    output(data, title="Window Polygon")


@window_app.command("attach")
@handle_errors
def window_attach(
    window_name: str = typer.Argument(..., help="Window tool name"),
    clip_name: Optional[str] = typer.Option(None, "--clip", help="Clip name (current clip when omitted)"),
    position: Optional[int] = typer.Option(None, "--position", help="0-based stack position"),
    comp_index: int = typer.Option(1, "--comp", help="Fusion composition index"),
):
    """Attach a window into the active mask chain."""
    set_execution_engine("fusion_native")
    set_capability_context("fusion.mutation", "supported")
    normalized_window, comp_index, position = color_ops.validate_window_attach_request(
        window_name,
        comp_index=comp_index,
        position=position,
    )
    normalized_clip = None
    if clip_name is not None:
        normalized_clip = clip_name.strip()
        if not normalized_clip:
            raise ValidationError(
                "Clip name must not be empty.",
                details={"clip": clip_name},
                recoverability="not_applicable",
            )
    enforce_mutation_policy("fusion.mutation", intended_engine="fusion_native", mutating=not is_dry_run())
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            {
                "clip": normalized_clip,
                "window": normalized_window,
                "position": position,
                "comp_index": comp_index,
                "would_attach": True,
                "attached": False,
                "resolved": False,
            },
            title="Window Attach Preview",
        )
        return
    conn = get_connection(require_timeline=True)
    data = color_ops.attach_window(conn, normalized_clip, normalized_window, comp_index=comp_index, position=position)
    output(data, title="Window Attach")


@window_app.command("detach")
@handle_errors
def window_detach(
    window_name: str = typer.Argument(..., help="Window tool name"),
    clip_name: Optional[str] = typer.Option(None, "--clip", help="Clip name (current clip when omitted)"),
    comp_index: int = typer.Option(1, "--comp", help="Fusion composition index"),
):
    """Detach a window from the active mask chain."""
    set_execution_engine("fusion_native")
    set_capability_context("fusion.mutation", "supported")
    normalized_window, comp_index, _ = color_ops.validate_window_attach_request(
        window_name,
        comp_index=comp_index,
    )
    normalized_clip = None
    if clip_name is not None:
        normalized_clip = clip_name.strip()
        if not normalized_clip:
            raise ValidationError(
                "Clip name must not be empty.",
                details={"clip": clip_name},
                recoverability="not_applicable",
            )
    enforce_mutation_policy("fusion.mutation", intended_engine="fusion_native", mutating=not is_dry_run())
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            {
                "clip": normalized_clip,
                "window": normalized_window,
                "comp_index": comp_index,
                "would_detach": True,
                "detached": False,
                "resolved": False,
            },
            title="Window Detach Preview",
        )
        return
    conn = get_connection(require_timeline=True)
    data = color_ops.detach_window(conn, normalized_clip, normalized_window, comp_index=comp_index)
    output(data, title="Window Detach")


@window_app.command("reorder")
@handle_errors
def window_reorder(
    order: str = typer.Argument(..., help="Comma-separated window tool names in desired order"),
    clip_name: Optional[str] = typer.Option(None, "--clip", help="Clip name (current clip when omitted)"),
    comp_index: int = typer.Option(1, "--comp", help="Fusion composition index"),
):
    """Reorder active windows inside the mask stack."""
    set_execution_engine("fusion_native")
    set_capability_context("fusion.mutation", "supported")
    names = [part.strip() for part in order.split(",") if part.strip()]
    if not names:
        raise ValidationError(
            "Window reorder order must include at least one window name.",
            details={"order": order},
            recoverability="not_applicable",
        )
    duplicate_names = sorted({name for name in names if names.count(name) > 1})
    if duplicate_names:
        raise ValidationError(
            "Window reorder order contains duplicate window names.",
            details={"duplicates": duplicate_names, "order": names},
            recoverability="not_applicable",
        )
    _, _, _, _, _, comp_index = color_ops.validate_window_geometry_request(
        shape="rectangle",
        center=(0.5, 0.5),
        width=0.5,
        height=0.5,
        softness=0.0,
        comp_index=comp_index,
    )
    normalized_clip = None
    if clip_name is not None:
        normalized_clip = clip_name.strip()
        if not normalized_clip:
            raise ValidationError(
                "Clip name must not be empty.",
                details={"clip": clip_name},
                recoverability="not_applicable",
            )
    enforce_mutation_policy("fusion.mutation", intended_engine="fusion_native", mutating=not is_dry_run())
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            {
                "clip": normalized_clip,
                "requested_order": names,
                "comp_index": comp_index,
                "would_reorder": True,
                "reordered": False,
                "resolved": False,
            },
            title="Window Reorder Preview",
        )
        return
    conn = get_connection(require_timeline=True)
    data = color_ops.reorder_windows(conn, normalized_clip, names, comp_index=comp_index)
    output(data, title="Window Reorder")


@qualifier_app.command("list")
@handle_errors
def qualifier_list(
    clip_name: Optional[str] = typer.Option(None, "--clip", help="Clip name (current clip when omitted)"),
    comp_index: int = typer.Option(1, "--comp", help="Fusion composition index"),
):
    """List clip-attached qualifier/keyer tools."""
    set_execution_engine("fusion_native")
    set_capability_context("fusion.mutation", "supported")
    normalized_clip = None
    if clip_name is not None:
        normalized_clip = clip_name.strip()
        if not normalized_clip:
            raise ValidationError(
                "Clip name must not be empty.",
                details={"clip": clip_name},
                recoverability="not_applicable",
            )
    try:
        comp_index = int(comp_index)
    except (TypeError, ValueError) as exc:
        raise ValidationError(
            "Fusion composition index must be a positive integer.",
            details={"comp_index": comp_index},
            recoverability="not_applicable",
        ) from exc
    if comp_index < 1:
        raise ValidationError(
            "Fusion composition index must be a positive integer.",
            details={"comp_index": comp_index},
            recoverability="not_applicable",
        )
    conn = get_connection(require_timeline=True)
    rows = color_ops.list_qualifiers(conn, normalized_clip, comp_index=comp_index)
    output(
        rows,
        columns=[
            ("order", "Order"),
            ("name", "Name"),
            ("type", "Type"),
            ("mode", "Mode"),
            ("active_mask_chain", "Active"),
            ("orphaned", "Orphaned"),
        ],
        title="Qualifiers",
    )


@qualifier_app.command("chroma")
@handle_errors
def qualifier_chroma(
    clip_name: Optional[str] = typer.Option(None, "--clip", help="Clip name (current clip when omitted)"),
    color: str = typer.Option("green", "--color", help="Key color (green/blue/red)"),
    threshold: float = typer.Option(0.3, "--threshold", help="Threshold"),
    comp_index: int = typer.Option(1, "--comp", help="Fusion composition index"),
):
    """Add a chroma qualifier via Fusion ChromaKeyer."""
    set_execution_engine("fusion_native")
    set_capability_context("fusion.mutation", "supported")
    normalized_clip = None
    if clip_name is not None:
        normalized_clip = clip_name.strip()
        if not normalized_clip:
            raise ValidationError(
                "Clip name must not be empty.",
                details={"clip": clip_name},
                recoverability="not_applicable",
            )
    color, threshold, comp_index = color_ops.validate_qualifier_chroma_request(color, threshold, comp_index)
    enforce_mutation_policy("fusion.mutation", intended_engine="fusion_native")
    conn = get_connection(require_timeline=True)
    data = color_ops.add_qualifier_chroma(conn, normalized_clip, color=color, threshold=threshold, comp_index=comp_index)
    output(data, title="Qualifier Chroma")


@qualifier_app.command("attach")
@handle_errors
def qualifier_attach(
    qualifier_name: str = typer.Argument(..., help="Qualifier tool name"),
    clip_name: Optional[str] = typer.Option(None, "--clip", help="Clip name (current clip when omitted)"),
    position: Optional[int] = typer.Option(None, "--position", help="0-based stack position"),
    comp_index: int = typer.Option(1, "--comp", help="Fusion composition index"),
):
    """Attach a qualifier into the active mask chain."""
    enforce_mutation_policy("fusion.mutation", intended_engine="fusion_native")
    conn = get_connection(require_timeline=True)
    data = color_ops.attach_qualifier(conn, clip_name, qualifier_name, comp_index=comp_index, position=position)
    output(data, title="Qualifier Attach")


@qualifier_app.command("detach")
@handle_errors
def qualifier_detach(
    qualifier_name: str = typer.Argument(..., help="Qualifier tool name"),
    clip_name: Optional[str] = typer.Option(None, "--clip", help="Clip name (current clip when omitted)"),
    comp_index: int = typer.Option(1, "--comp", help="Fusion composition index"),
):
    """Detach a qualifier from the active mask chain."""
    set_execution_engine("fusion_native")
    set_capability_context("fusion.mutation", "supported")
    normalized_qualifier = qualifier_name.strip()
    if not normalized_qualifier:
        raise ValidationError(
            "Qualifier name must not be empty.",
            details={"qualifier": qualifier_name},
            recoverability="not_applicable",
        )
    normalized_clip = None
    if clip_name is not None:
        normalized_clip = clip_name.strip()
        if not normalized_clip:
            raise ValidationError(
                "Clip name must not be empty.",
                details={"clip": clip_name},
                recoverability="not_applicable",
            )
    try:
        comp_index = int(comp_index)
    except (TypeError, ValueError) as exc:
        raise ValidationError(
            "Fusion composition index must be a positive integer.",
            details={"comp_index": comp_index},
            recoverability="not_applicable",
        ) from exc
    if comp_index < 1:
        raise ValidationError(
            "Fusion composition index must be a positive integer.",
            details={"comp_index": comp_index},
            recoverability="not_applicable",
        )
    enforce_mutation_policy("fusion.mutation", intended_engine="fusion_native")
    conn = get_connection(require_timeline=True)
    data = color_ops.detach_qualifier(conn, normalized_clip, normalized_qualifier, comp_index=comp_index)
    output(data, title="Qualifier Detach")
