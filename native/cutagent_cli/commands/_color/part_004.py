from __future__ import annotations

@tracker_app.command("list")
@handle_errors
def tracker_list(
    clip_name: Optional[str] = typer.Option(None, "--clip", help="Clip name (current clip when omitted)"),
    comp_index: int = typer.Option(1, "--comp", help="Fusion composition index"),
):
    """List clip-attached Fusion trackers."""
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
    rows = color_ops.list_trackers(conn, normalized_clip, comp_index=comp_index)
    output(
        rows,
        columns=[
            ("name", "Name"),
            ("type", "Type"),
            ("active_mask_chain", "Active"),
            ("orphaned", "Orphaned"),
            ("order", "Order"),
        ],
        title="Trackers",
    )


@tracker_app.command("add")
@handle_errors
def tracker_add(
    clip_name: Optional[str] = typer.Option(None, "--clip", help="Clip name (current clip when omitted)"),
    pattern_center: str = typer.Option("0.5,0.5", "--pattern-center", help="Initial pattern center X,Y"),
    comp_index: int = typer.Option(1, "--comp", help="Fusion composition index"),
):
    """Add a Fusion tracker to the clip grading comp."""
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
    pattern_center = color_ops.validate_pattern_center(pattern_center)
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
    enforce_mutation_policy("fusion.mutation", intended_engine="fusion_native", mutating=not is_dry_run())
    if is_dry_run():
        output(
            {
                "clip": normalized_clip,
                "would_add": True,
                "added": False,
                "pattern_center": pattern_center,
                "comp_index": comp_index,
                "resolved": False,
            },
            title="Tracker Add Preview",
        )
        return
    conn = get_connection(require_timeline=True)
    data = color_ops.add_tracker(conn, normalized_clip, pattern_center=pattern_center, comp_index=comp_index)
    output(data, title="Tracker Add")


@tracker_app.command("set-target")
@handle_errors
def tracker_set_target(
    tracker_name: str = typer.Argument(..., help="Tracker tool name"),
    center: str = typer.Option("0.5,0.5", "--center", help="Pattern center X,Y"),
    clip_name: Optional[str] = typer.Option(None, "--clip", help="Clip name (current clip when omitted)"),
    comp_index: int = typer.Option(1, "--comp", help="Fusion composition index"),
):
    """Update a tracker target center."""
    set_execution_engine("fusion_native")
    set_capability_context("fusion.mutation", "supported")
    normalized_tracker = tracker_name.strip()
    if not normalized_tracker:
        raise ValidationError(
            "Tracker name must not be empty.",
            details={"tracker": tracker_name},
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
    center_xy = color_ops.validate_pattern_center(center)
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
    enforce_mutation_policy("fusion.mutation", intended_engine="fusion_native", mutating=not is_dry_run())
    if is_dry_run():
        output(
            {
                "clip": normalized_clip,
                "tracker": normalized_tracker,
                "pattern_center": center_xy,
                "comp_index": comp_index,
                "would_set_target": True,
                "updated": False,
                "resolved": False,
            },
            title="Tracker Set Target Preview",
        )
        return
    conn = get_connection(require_timeline=True)
    data = color_ops.tracker_set_target(conn, normalized_clip, normalized_tracker, center_xy, comp_index=comp_index)
    output(data, title="Tracker Set Target")


@tracker_app.command("track-forward")
@handle_errors
def tracker_track_forward(
    tracker_name: str = typer.Argument(..., help="Tracker tool name"),
    clip_name: Optional[str] = typer.Option(None, "--clip", help="Clip name (current clip when omitted)"),
    comp_index: int = typer.Option(1, "--comp", help="Fusion composition index"),
):
    """Trigger tracker forward analysis."""
    set_execution_engine("fusion_native")
    set_capability_context("fusion.mutation", "supported")
    normalized_tracker = tracker_name.strip()
    if not normalized_tracker:
        raise ValidationError(
            "Tracker name must not be empty.",
            details={"tracker": tracker_name},
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
    enforce_mutation_policy("fusion.mutation", intended_engine="fusion_native", mutating=not is_dry_run())
    if is_dry_run():
        output(
            {
                "clip": normalized_clip,
                "tracker": normalized_tracker,
                "direction": "forward",
                "comp_index": comp_index,
                "would_track": True,
                "triggered": False,
                "resolved": False,
            },
            title="Tracker Track Forward Preview",
        )
        return
    conn = get_connection(require_timeline=True)
    data = color_ops.tracker_track(conn, normalized_clip, normalized_tracker, direction="forward", comp_index=comp_index)
    output(data, title="Tracker Track Forward")


@tracker_app.command("track-reverse")
@handle_errors
def tracker_track_reverse(
    tracker_name: str = typer.Argument(..., help="Tracker tool name"),
    clip_name: Optional[str] = typer.Option(None, "--clip", help="Clip name (current clip when omitted)"),
    comp_index: int = typer.Option(1, "--comp", help="Fusion composition index"),
):
    """Trigger tracker reverse analysis."""
    set_execution_engine("fusion_native")
    set_capability_context("fusion.mutation", "supported")
    normalized_tracker = tracker_name.strip()
    if not normalized_tracker:
        raise ValidationError(
            "Tracker name must not be empty.",
            details={"tracker": tracker_name},
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
    enforce_mutation_policy("fusion.mutation", intended_engine="fusion_native", mutating=not is_dry_run())
    if is_dry_run():
        output(
            {
                "clip": normalized_clip,
                "tracker": normalized_tracker,
                "direction": "reverse",
                "comp_index": comp_index,
                "would_track": True,
                "triggered": False,
                "resolved": False,
            },
            title="Tracker Track Reverse Preview",
        )
        return
    conn = get_connection(require_timeline=True)
    data = color_ops.tracker_track(conn, normalized_clip, normalized_tracker, direction="reverse", comp_index=comp_index)
    output(data, title="Tracker Track Reverse")


@tracker_app.command("attach-window")
@handle_errors
def tracker_attach_window(
    tracker_name: str = typer.Argument(..., help="Tracker tool name"),
    window_name: str = typer.Argument(..., help="Window tool name"),
    clip_name: Optional[str] = typer.Option(None, "--clip", help="Clip name (current clip when omitted)"),
    comp_index: int = typer.Option(1, "--comp", help="Fusion composition index"),
):
    """Ensure a window feeds the tracked mask chain."""
    set_execution_engine("fusion_native")
    set_capability_context("fusion.mutation", "supported")
    normalized_tracker = tracker_name.strip()
    normalized_window = window_name.strip()
    if not normalized_tracker:
        raise ValidationError(
            "Tracker name must not be empty.",
            details={"tracker": tracker_name},
            recoverability="not_applicable",
        )
    if not normalized_window:
        raise ValidationError(
            "Window name must not be empty.",
            details={"window": window_name},
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
    enforce_mutation_policy("fusion.mutation", intended_engine="fusion_native", mutating=not is_dry_run())
    if is_dry_run():
        output(
            {
                "clip": normalized_clip,
                "tracker": normalized_tracker,
                "window": normalized_window,
                "comp_index": comp_index,
                "would_attach": True,
                "attached": False,
                "resolved": False,
            },
            title="Tracker Attach Window Preview",
        )
        return
    conn = get_connection(require_timeline=True)
    data = color_ops.attach_window_to_tracker(
        conn,
        normalized_clip,
        normalized_tracker,
        normalized_window,
        comp_index=comp_index,
    )
    output(data, title="Tracker Attach Window")


@tracker_app.command("attach-qualifier")
@handle_errors
def tracker_attach_qualifier(
    tracker_name: str = typer.Argument(..., help="Tracker tool name"),
    qualifier_name: str = typer.Argument(..., help="Qualifier tool name"),
    clip_name: Optional[str] = typer.Option(None, "--clip", help="Clip name (current clip when omitted)"),
    comp_index: int = typer.Option(1, "--comp", help="Fusion composition index"),
):
    """Ensure a qualifier feeds the tracked mask chain."""
    set_execution_engine("fusion_native")
    set_capability_context("fusion.mutation", "supported")
    normalized_tracker = tracker_name.strip()
    normalized_qualifier = qualifier_name.strip()
    if not normalized_tracker:
        raise ValidationError(
            "Tracker name must not be empty.",
            details={"tracker": tracker_name},
            recoverability="not_applicable",
        )
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
    enforce_mutation_policy("fusion.mutation", intended_engine="fusion_native", mutating=not is_dry_run())
    if is_dry_run():
        output(
            {
                "clip": normalized_clip,
                "tracker": normalized_tracker,
                "qualifier": normalized_qualifier,
                "comp_index": comp_index,
                "would_attach": True,
                "attached": False,
                "resolved": False,
            },
            title="Tracker Attach Qualifier Preview",
        )
        return
    conn = get_connection(require_timeline=True)
    data = color_ops.attach_qualifier_to_tracker(
        conn,
        normalized_clip,
        normalized_tracker,
        normalized_qualifier,
        comp_index=comp_index,
    )
    output(data, title="Tracker Attach Qualifier")


@mask_app.command("inspect")
@handle_errors
def mask_inspect(
    clip_name: Optional[str] = typer.Option(None, "--clip", help="Clip name (current clip when omitted)"),
    comp_index: int = typer.Option(1, "--comp", help="Fusion composition index"),
):
    """Inspect the active mask chain and orphaned mask helpers."""
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
    data = color_ops.inspect_mask_stack(conn, normalized_clip, comp_index=comp_index)
    output(data, title="Mask Stack")


@secondary_app.command("create")
@handle_errors
def secondary_create(
    clip_name: Optional[str] = typer.Option(None, "--clip", help="Clip name (current clip when omitted)"),
    window_shape: Optional[str] = typer.Option(None, "--window", help="rectangle|ellipse"),
    qualifier_color: Optional[str] = typer.Option(None, "--qualifier-color", help="green|blue|red"),
    qualifier_threshold: float = typer.Option(0.3, "--threshold", help="Qualifier threshold"),
    track: bool = typer.Option(False, "--track", help="Wrap the secondary with a tracker"),
    pattern_center: str = typer.Option("0.5,0.5", "--pattern-center", help="Tracker pattern center X,Y"),
    comp_index: int = typer.Option(1, "--comp", help="Fusion composition index"),
):
    """Compose a secondary grade from window, qualifier, and optional tracker."""
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
    window_shape, qualifier_color, qualifier_threshold, track, center, comp_index = color_ops.validate_secondary_create_request(
        window_shape=window_shape,
        qualifier_color=qualifier_color,
        qualifier_threshold=qualifier_threshold,
        track=track,
        pattern_center=pattern_center,
        comp_index=comp_index,
    )
    enforce_mutation_policy("fusion.mutation", intended_engine="fusion_native", mutating=not is_dry_run())
    if is_dry_run():
        output(
            {
                "clip": normalized_clip,
                "would_create": True,
                "created": False,
                "window": window_shape,
                "qualifier_color": qualifier_color,
                "threshold": qualifier_threshold,
                "track": track,
                "pattern_center": center,
                "comp_index": comp_index,
            },
            title="Secondary Create Preview",
        )
        return
    conn = get_connection(require_timeline=True)
    data = color_ops.secondary_create(
        conn,
        normalized_clip,
        window_shape=window_shape,
        qualifier_color=qualifier_color,
        qualifier_threshold=qualifier_threshold,
        track=track,
        pattern_center=center,
        comp_index=comp_index,
    )
    output(data, title="Secondary Create")


@secondary_app.command("isolate-green-screen")
@handle_errors
def secondary_isolate_green_screen(
    clip_name: Optional[str] = typer.Option(None, "--clip", help="Clip name (current clip when omitted)"),
    threshold: float = typer.Option(0.3, "--threshold", help="Qualifier threshold"),
    track: bool = typer.Option(False, "--track", help="Wrap the isolation with a tracker"),
    comp_index: int = typer.Option(1, "--comp", help="Fusion composition index"),
):
    """Create a green-screen isolation secondary."""
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
    _, qualifier_color, threshold, track, pattern_center, comp_index = color_ops.validate_secondary_create_request(
        window_shape=None,
        qualifier_color="green",
        qualifier_threshold=threshold,
        track=track,
        pattern_center=(0.5, 0.5),
        comp_index=comp_index,
    )
    enforce_mutation_policy("fusion.mutation", intended_engine="fusion_native", mutating=not is_dry_run())
    if is_dry_run():
        output(
            {
                "clip": normalized_clip,
                "would_create": True,
                "created": False,
                "qualifier_color": qualifier_color,
                "threshold": threshold,
                "track": track,
                "pattern_center": pattern_center,
                "comp_index": comp_index,
            },
            title="Isolate Green Screen Preview",
        )
        return
    conn = get_connection(require_timeline=True)
    data = color_ops.secondary_create(
        conn,
        normalized_clip,
        qualifier_color=qualifier_color,
        qualifier_threshold=threshold,
        track=track,
        pattern_center=pattern_center,
        comp_index=comp_index,
    )
    output(data, title="Isolate Green Screen")


@secondary_app.command("tracked-window")
@handle_errors
def secondary_tracked_window(
    clip_name: Optional[str] = typer.Option(None, "--clip", help="Clip name (current clip when omitted)"),
    shape: str = typer.Option("rectangle", "--shape", help="rectangle|ellipse"),
    pattern_center: str = typer.Option("0.5,0.5", "--pattern-center", help="Tracker pattern center X,Y"),
    comp_index: int = typer.Option(1, "--comp", help="Fusion composition index"),
):
    """Create a tracked window secondary."""
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
    window_shape, _, _, track, pattern_center, comp_index = color_ops.validate_secondary_create_request(
        window_shape=shape,
        qualifier_color=None,
        qualifier_threshold=0.3,
        track=True,
        pattern_center=pattern_center,
        comp_index=comp_index,
    )
    enforce_mutation_policy("fusion.mutation", intended_engine="fusion_native", mutating=not is_dry_run())
    if is_dry_run():
        output(
            {
                "clip": normalized_clip,
                "would_create": True,
                "created": False,
                "window": window_shape,
                "track": track,
                "pattern_center": pattern_center,
                "comp_index": comp_index,
            },
            title="Tracked Window Preview",
        )
        return
    conn = get_connection(require_timeline=True)
    data = color_ops.secondary_create(
        conn,
        normalized_clip,
        window_shape=window_shape,
        track=track,
        pattern_center=pattern_center,
        comp_index=comp_index,
    )
    output(data, title="Tracked Window")


@secondary_app.command("subject-isolation")
@handle_errors
def secondary_subject_isolation(
    clip_name: Optional[str] = typer.Option(None, "--clip", help="Clip name (current clip when omitted)"),
    pattern_center: str = typer.Option("0.5,0.5", "--pattern-center", help="Tracker pattern center X,Y"),
    comp_index: int = typer.Option(1, "--comp", help="Fusion composition index"),
):
    """Create a subject-isolation stack using ellipse window plus tracker."""
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
    window_shape, _, _, track, pattern_center, comp_index = color_ops.validate_secondary_create_request(
        window_shape="ellipse",
        qualifier_color=None,
        qualifier_threshold=0.3,
        track=True,
        pattern_center=pattern_center,
        comp_index=comp_index,
    )
    enforce_mutation_policy("fusion.mutation", intended_engine="fusion_native", mutating=not is_dry_run())
    if is_dry_run():
        output(
            {
                "clip": normalized_clip,
                "would_create": True,
                "created": False,
                "window": window_shape,
                "track": track,
                "pattern_center": pattern_center,
                "comp_index": comp_index,
            },
            title="Subject Isolation Preview",
        )
        return
    conn = get_connection(require_timeline=True)
    data = color_ops.secondary_create(
        conn,
        normalized_clip,
        window_shape=window_shape,
        track=track,
        pattern_center=pattern_center,
        comp_index=comp_index,
    )
    output(data, title="Subject Isolation")


@fx_app.command("list")
@handle_errors
def fx_list():
    """List available Fusion-template grading effects from the FX registry."""
    tpl_dir = os.environ.get("RESOLVE_FX_TEMPLATE_DIR", os.path.expanduser("~/.cutagent-cli/fx-templates"))
    data = fx_template_ops.list_fx_registry(tpl_dir)
    output(data, title="Color FX Templates")


@fx_app.command("apply")
@handle_errors
def fx_apply(
    name: str = typer.Argument(..., help="Reviewed effect ID or alias"),
    clip_name: Optional[str] = typer.Option(None, "--clip", help="Target timeline clip"),
    item_id: Optional[str] = typer.Option(None, "--item-id", help="Exact native timeline item ID"),
    track: Optional[int] = typer.Option(None, "--track", min=1, help="Exact video track index; requires --record-frame"),
    record_frame: Optional[str] = typer.Option(None, "--record-frame", "--at", help="Record-domain position inside the target"),
    template: Optional[str] = typer.Option(None, "--template", help="Reviewed custom .setting path with sibling manifest"),
    params: Optional[str] = typer.Option(None, "--params", help="JSON object of reviewed parameter IDs and typed values"),
    verify: bool = typer.Option(True, "--verify/--no-verify", help="Require structural and rendered verification"),
    proof_dir: Optional[str] = typer.Option(None, "--proof-dir", help="Directory for retained rendered evidence"),
):
    """Apply one reviewed Fusion finishing effect to one exact timeline item."""
    import json as json_mod

    parsed_params = {}
    if params:
        try:
            parsed_params = json_mod.loads(params)
        except json_mod.JSONDecodeError as exc:
            raise ValidationError("Invalid JSON in --params.", details={"params": params, "error": str(exc)})
        if not isinstance(parsed_params, dict):
            raise ValidationError("--params must be a JSON object.")

    request = fx_template_ops.validate_effect_request(name, template_path=template, params=parsed_params)
    mutation_target.validate_timeline_item_selector(clip_name, item_id=item_id, track=track, record_frame=record_frame)
    if not verify:
        raise ValidationError("Consequential effect mutations require --verify.")
    effect_engine = "fusion_native" if request["path"] is None else "workaround_setting"
    enforce_mutation_policy(
        "edit.ofx_resolvefx_native",
        intended_engine=effect_engine,
        mutating=not is_dry_run(),
    )
    set_execution_engine(effect_engine)
    if is_dry_run():
        output(
            {
                "dry_run": True,
                "effect": {"id": request["spec"]["id"], "display_name": request["spec"]["name"]},
                "parameters": request["params"],
                "target_selector": {"name": clip_name, "timeline_item_id": item_id, "track": track, "record_frame": record_frame},
                "verification": {"required": True, "mode": "structural_and_rendered"},
            },
            title="Color FX Apply Plan",
        )
        return
    conn = get_connection(require_timeline=True)
    data = fx_template_ops.add_fx_via_template(
        conn,
        name,
        clip_name=clip_name,
        template_path=template,
        params=parsed_params,
        verify=verify,
        item_id=item_id,
        track=track,
        record_frame=record_frame,
        proof_dir=proof_dir,
    )
    output(data, title="Color FX Apply")


@wheels_app.command("set")
@handle_errors
def wheels_set(
    clip_name: Optional[str] = typer.Argument(None, help="Clip name (current clip when omitted)"),
    node: int = typer.Option(1, "--node", help="Node index"),
    lift: Optional[str] = typer.Option(None, "--lift", help="Lift triplet 'R G B'"),
    gamma: Optional[str] = typer.Option(None, "--gamma", help="Gamma triplet 'R G B'"),
    gain: Optional[str] = typer.Option(None, "--gain", help="Gain triplet 'R G B'"),
    sat: Optional[float] = typer.Option(None, "--sat", help="Saturation multiplier"),
    mode: str = typer.Option("cdl", "--mode", help="Compatibility mode: cdl|lut|both"),
    lut_output: Optional[str] = typer.Option(None, "--lut-output", help="Output path for generated LUT"),
):
    """Set primary color wheel values through verified Color Page Project.db params."""
    try:
        preflight_node = int(node)
    except Exception:
        preflight_node = 1
    preflight_mode = str(mode).strip().lower()
    preflight_db_route = preflight_mode in {"cdl", "both"} and preflight_node == 1
    set_execution_engine("db_workaround" if preflight_db_route else "workaround_setting")
    set_capability_context("color.wheels_emulation", "supported")
    normalized_clip = None
    if clip_name is not None:
        normalized_clip = clip_name.strip()
        if not normalized_clip:
            raise ValidationError("Clip name must not be empty.", details={"clip": clip_name})
    request = color_ops.validate_wheels_request(
        node=node,
        lift=lift,
        gamma=gamma,
        gain=gain,
        sat=sat,
        mode=mode,
        lut_output=lut_output,
    )
    db_route_requested = request["mode"] in {"cdl", "both"} and request["node"] == 1
    set_execution_engine("db_workaround" if db_route_requested else "workaround_setting")
    set_capability_context("color.wheels_emulation", "supported")
    enforce_mutation_policy(
        "color.wheels_emulation",
        intended_engine="db_workaround" if db_route_requested else "workaround_setting",
        mutating=not is_dry_run(),
    )
    if not db_route_requested:
        set_execution_engine("workaround_setting")
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            {
                "clip": normalized_clip,
                "node": request["node"],
                "mode": request["mode"],
                "lift": request["lift"],
                "gamma": request["gamma"],
                "gain": request["gain"],
                "sat": request["sat"],
                "lut_output": request["lut_output"],
                "would_apply_cdl": request["mode"] in {"cdl", "both"},
                "would_write_color_page_db": db_route_requested,
                "would_generate_lut": request["mode"] in {"lut", "both"},
                "applied": False,
            },
            title="Color Wheels Set",
        )
        return

    conn = get_connection(require_timeline=True)
    data = color_ops.emulate_wheels(
        conn,
        normalized_clip,
        node=request["node"],
        lift=lift,
        gamma=gamma,
        gain=gain,
        sat=sat,
        mode=request["mode"],
        lut_output=request["lut_output"],
        verify_project_db=True,
    )
    data["route"] = data.get("cdl_apply_route") or "wheels_emulation"
    if data.get("cdl_readback_available") or (request["mode"] == "lut" and data.get("lut_applied")):
        _mark_color_render_unverified(data, readback_source="color_wheels_readback")
    else:
        set_verification_status("pending_manual")
        set_recoverability("manual")
    output(data, title="Color Wheels Set")


# ---------------------------------------------------------------------------
# color page — DB-backed native Color page operations
# ---------------------------------------------------------------------------


@page_app.command("read")
@handle_errors
def page_read(
    clip_name: Optional[str] = typer.Argument(None, help="Clip name (None = current)"),
):
    """Read color grade params from the DB (Lift/Gamma/Gain/Saturation)."""
    from ..core import color_page_db

    set_execution_engine("db_workaround", 0.75)
    set_capability_context("color.page_wheel_set", "supported")
    normalized_clip = None
    if clip_name is not None:
        normalized_clip = clip_name.strip()
        if not normalized_clip:
            raise ValidationError(
                "Clip name must not be empty.",
                details={"clip": clip_name},
                recoverability="not_applicable",
            )
    conn = get_connection(require_timeline=True)
    item = clip_ops.cutagent_clip(conn, normalized_clip)
    resolved_clip = normalized_clip
    if hasattr(item, "GetName"):
        try:
            resolved_clip = item.GetName()
        except Exception:
            pass
    data = color_page_db.snapshot_color_data(
        _resolve_project_db_path(conn),
        clip_name=resolved_clip,
    )
    data["clip"] = resolved_clip
    output(data, title="Color Page — Grade Parameters")


@page_app.command("scope-read")
@handle_errors
def page_scope_read(
    at: Optional[str] = typer.Option(None, "--at", help="Optional timeline position to sample before restoring the playhead"),
    output_path: str = typer.Option("color_scope_read.png", "--output", "-o", help="Exported frame path used for scope analysis"),
    mode: str = typer.Option("all", "--mode", help="Scope payload: all, waveform, rgb-parade, or vectorscope"),
):
    """Read waveform/vectorscope-style metrics from the current Color Page frame."""
    set_execution_engine("api_native")
    set_capability_context("color.page_scope_read", "supported")
    normalized_mode = str(mode or "").strip().lower().replace("_", "-")
    if normalized_mode not in {"all", "waveform", "rgb-parade", "vectorscope"}:
        raise ValidationError(
            "Color Page scope-read --mode must be one of: all, waveform, rgb-parade, vectorscope.",
            details={"mode": mode, "supported_modes": ["all", "waveform", "rgb-parade", "vectorscope"]},
            recoverability="not_applicable",
        )

    resolved_path = _resolve_output_file_path(output_path)
    enforce_mutation_policy("color.page_scope_read", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            {
                "route": "api_native_color_page_scope_read",
                "mode": normalized_mode,
                "requested_at": at,
                "output_path": str(resolved_path),
                "visual_check_path": _workspace_relative_path(resolved_path),
                "requested_output_path": output_path,
                "would_set_playhead": at is not None,
                "would_export": True,
                "would_analyze": True,
                "exported": False,
                "verified": False,
                "required_page": "color",
            },
            title="Color Page — Scope Read Preview",
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
    analysis = _analyze_scope_pixels(rgb)
    scopes = (
        analysis
        if normalized_mode == "all"
        else {
            "frame": analysis["frame"],
            normalized_mode.replace("-", "_"): analysis[normalized_mode.replace("-", "_")],
        }
    )

    set_verification_status("verified")
    set_recoverability("manual" if restore_error else "not_applicable")
    output(
        {
            "route": "api_native_color_page_scope_read",
            "mode": normalized_mode,
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
                "analysis_verified": True,
                "pixel_count": analysis["frame"]["pixel_count"],
                "decode_route": "ffmpeg_rawvideo_rgb24",
            },
            "frame_export": metadata,
            "scopes": scopes,
        },
        title="Color Page — Scope Read",
    )


@page_app.command("false-color-read")
@handle_errors
def page_false_color_read(
    at: Optional[str] = typer.Option(None, "--at", help="Optional timeline position to sample before restoring the playhead"),
    output_path: str = typer.Option("color_false_color_read.png", "--output", "-o", help="Exported frame path used for false-color exposure analysis"),
):
    """Analyze Color Page exposure as false-color-style IRE/luma bands."""
    set_execution_engine("api_native")
    set_capability_context("color.page_false_color_read", "supported")
    resolved_path = _resolve_output_file_path(output_path)

    enforce_mutation_policy("color.page_false_color_read", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            {
                "route": "api_native_color_page_false_color_read",
                "requested_at": at,
                "output_path": str(resolved_path),
                "visual_check_path": _workspace_relative_path(resolved_path),
                "requested_output_path": output_path,
                "profile": "ire_luma_tutorial",
                "would_set_playhead": at is not None,
                "would_export": True,
                "would_analyze": True,
                "exported": False,
                "verified": False,
                "required_page": "color",
            },
            title="Color Page — False Color Read Preview",
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
    analysis = _analyze_false_color_pixels(rgb)

    set_verification_status("verified")
    set_recoverability("manual" if restore_error else "not_applicable")
    output(
        {
            "route": "api_native_color_page_false_color_read",
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
                "analysis_verified": True,
                "pixel_count": analysis["frame"]["pixel_count"],
                "decode_route": "ffmpeg_rawvideo_rgb24",
            },
            "frame_export": metadata,
            "false_color": analysis,
        },
        title="Color Page — False Color Read",
    )


def _validate_match_anchor(anchor_x: Optional[float], anchor_y: Optional[float], radius: int) -> tuple[float | None, float | None, int]:
    if (anchor_x is None) != (anchor_y is None):
        raise ValidationError(
            "Color Page shot-match requires both --anchor-x and --anchor-y, or neither.",
            details={"anchor_x": anchor_x, "anchor_y": anchor_y},
            recoverability="not_applicable",
        )
    if anchor_x is None or anchor_y is None:
        return None, None, _validate_sample_radius(radius)
    return (
        _validate_normalized_coordinate(anchor_x, option_name="--anchor-x"),
        _validate_normalized_coordinate(anchor_y, option_name="--anchor-y"),
        _validate_sample_radius(radius),
    )


def _export_match_frame(conn, *, at: Optional[str], resolved_path: Path, requested_output_path: str) -> dict[str, object]:
    target = None
    if at is not None:
        target = timeline_ops.set_playhead(conn, at, return_details=True)
    metadata = _export_color_page_frame_as_still(
        conn,
        resolved_path=resolved_path,
        requested_output_path=requested_output_path,
    )
    rgb = _load_frame_rgb_array(resolved_path)
    return {
        "requested_at": at,
        "target": target,
        "output_path": str(resolved_path),
        "visual_check_path": _workspace_relative_path(resolved_path),
        "requested_output_path": requested_output_path,
        "frame_export": metadata,
        "rgb": rgb,
    }


def _validate_distinct_color_frame_outputs(paths: dict[str, Path]) -> None:
    seen: dict[Path, str] = {}
    for label, path in paths.items():
        existing = seen.get(path)
        if existing is not None:
            raise ValidationError(
                "Color Page frame proof outputs must use distinct file paths.",
                details={"duplicate_path": str(path), "first_output": existing, "second_output": label},
                recoverability="not_applicable",
            )
        seen[path] = label
