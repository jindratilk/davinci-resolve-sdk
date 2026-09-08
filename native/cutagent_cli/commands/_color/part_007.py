@page_app.command("node-add")
@handle_errors
def page_node_add(
    clip_name: Optional[str] = typer.Argument(None, help="Clip name"),
    kind: str = typer.Option("serial", "--kind", "--type", help="Node kind to add. Currently verified: serial, parallel, layer"),
    position: str = typer.Option("after", "--position", help="Where to add the serial node. Verified: after, before"),
    node_index: int = typer.Option(1, "--node-index", "--node", help="Target node index for --position before"),
):
    """Add a native Color Page node via DB."""
    from ..core import color_page_db

    clip_name = _option_value(clip_name)
    kind = color_page_db.validate_page_node_add_kind(_option_value(kind))
    position = str(_option_value(position) or "after").strip().lower()
    node_index = int(_option_value(node_index) or 1)
    if position not in {"after", "before"}:
        raise ValidationError(
            "Invalid Color Page node-add position.",
            details={"position": position, "allowed": ["after", "before"]},
            recoverability="not_applicable",
        )
    if node_index < 1:
        raise ValidationError(
            "Node index must be a positive integer.",
            details={"node_index": node_index, "minimum": 1},
            recoverability="not_applicable",
        )
    if kind in {"parallel", "layer"} and (position != "after" or node_index != 1):
        _unsupported_color_page_preview(
            "color.page_node_add_arbitrary_topology",
            "not_available_color_page_node_add_arbitrary_topology",
            {
                "clip": clip_name,
                "kind": kind,
                "position": position,
                "node_index": node_index,
                "verified_default_only": True,
            },
            "Color Page Node Add Topology Availability",
        )
        return

    capability_id = {
        "layer": "color.page_node_add_layer",
        "parallel": "color.page_node_add_parallel",
        "serial": "color.page_node_add_serial",
    }[kind]
    set_execution_engine("db_workaround", 0.75)
    set_capability_context(capability_id, "supported")

    enforce_mutation_policy(
        capability_id,
        intended_engine="db_workaround",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        dry_run_message(f"Would add a {kind} Color Page node via DB")
        return

    conn = get_connection(require_timeline=True)
    timeline_ops.require_sdk_color_mutation_guard(conn)
    if kind == "parallel":
        data = color_page_db.write_page_node_add_parallel(conn, clip_name=clip_name)
    elif kind == "layer":
        data = color_page_db.write_page_node_add_layer(conn, clip_name=clip_name)
    else:
        data = color_page_db.write_page_node_add_serial(
            conn,
            clip_name=clip_name,
            position=position,
            target_node_index=node_index,
        )
    data["requested_kind"] = kind
    output(data, title="Color Page — Node Add")
    success(f"Color Page {kind} node added via DB.")


@page_app.command("node-add-topology")
@handle_errors
def page_node_add_topology(
    clip_name: Optional[str] = typer.Argument(None, help="Clip name"),
    topology: str = typer.Option("serial", "--topology", help="Node topology to add: serial, parallel, layer, or mixer"),
    position: str = typer.Option("after", "--position", help="Insertion position: after, before, selected, or node-N"),
):
    """Add a verified native Color Page topology via DB."""
    from ..core import color_page_db

    clip_name = _option_value(clip_name)
    raw_topology = str(_option_value(topology, "serial") or "serial").strip().lower().replace("_", "-")
    topology_aliases = {
        "serial": "serial",
        "serial-node": "serial",
        "parallel": "parallel",
        "parallel-mixer": "parallel",
        "layer": "layer",
        "layer-mixer": "layer",
        "mixer": "layer",
    }
    if raw_topology not in topology_aliases:
        raise ValidationError(
            "Color Page node-add-topology supports serial, parallel, layer, and mixer.",
            details={"topology": topology, "allowed": sorted(topology_aliases)},
            recoverability="not_applicable",
        )
    kind = color_page_db.validate_page_node_add_kind(topology_aliases[raw_topology])
    raw_position = str(_option_value(position, "after") or "after").strip().lower().replace("_", "-")
    node_index = 1
    normalized_position = raw_position
    if raw_position in {"selected", "after"}:
        normalized_position = "after"
    elif raw_position == "before":
        normalized_position = "before"
    elif raw_position.startswith("node-"):
        normalized_position = "before"
        try:
            node_index = int(raw_position.split("-", 1)[1])
        except ValueError as exc:
            raise ValidationError(
                "Color Page node-add-topology --position node-N requires a numeric N.",
                details={"position": position},
                recoverability="not_applicable",
            ) from exc
    else:
        raise ValidationError(
            "Color Page node-add-topology --position must be after, before, selected, or node-N.",
            details={"position": position, "allowed": ["after", "before", "selected", "node-N"]},
            recoverability="not_applicable",
        )
    if node_index < 1:
        raise ValidationError(
            "Node index must be a positive integer.",
            details={"node_index": node_index, "minimum": 1},
            recoverability="not_applicable",
        )
    if kind in {"parallel", "layer"} and (normalized_position != "after" or node_index != 1):
        raise ValidationError(
            "Parallel and layer topology insertion is verified only at the graph tail.",
            details={
                "topology": topology,
                "effective_kind": kind,
                "position": position,
                "verified_position": "after",
                "verified_node_index": 1,
            },
            recoverability="not_applicable",
        )

    set_execution_engine("db_workaround", 0.75)
    set_capability_context("color.page_node_add_arbitrary_topology", "supported")
    enforce_mutation_policy(
        "color.page_node_add_arbitrary_topology",
        intended_engine="db_workaround",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        dry_run_message(f"Would add Color Page {kind} topology via DB")
        return

    conn = get_connection(require_timeline=True)
    timeline_ops.require_sdk_color_mutation_guard(conn)
    if kind == "parallel":
        data = color_page_db.write_page_node_add_parallel(conn, clip_name=clip_name)
    elif kind == "layer":
        data = color_page_db.write_page_node_add_layer(conn, clip_name=clip_name)
    else:
        data = color_page_db.write_page_node_add_serial(
            conn,
            clip_name=clip_name,
            position=normalized_position,
            target_node_index=node_index,
        )
    data["route"] = "db_workaround_color_page_node_add_topology"
    data["requested_topology"] = topology
    data["effective_kind"] = kind
    data["requested_position"] = position
    data["effective_position"] = normalized_position
    data["target_node_index"] = node_index
    output(data, title="Color Page — Node Add Topology")
    success(f"Color Page {kind} topology added via DB.")


@page_app.command("alpha-output-connect")
@handle_errors
def page_alpha_output_connect(
    clip_name: str = typer.Argument(..., help="Exact clip name on the active timeline"),
    track: Optional[int] = typer.Option(None, "--track", help="Exact 1-based video track selector"),
    at: Optional[str] = typer.Option(None, "--at", help="Exact timeline position selector"),
    node_index: int = typer.Option(1, "--node-index", "--node", help="Color node whose key output feeds Alpha Output"),
):
    """Connect a verified single Color node to the native Alpha Output via Project.db."""
    from ..core import color_page_db

    normalized_clip = str(_option_value(clip_name) or "").strip()
    normalized_track = _option_value(track)
    normalized_at = str(_option_value(at) or "").strip()
    normalized_node_index = int(_option_value(node_index, 1) or 1)
    if not normalized_clip:
        raise ValidationError(
            "Color Page Alpha Output clip name must not be empty.",
            recoverability="not_applicable",
        )
    if normalized_track is None or int(normalized_track) <= 0 or not normalized_at:
        raise ValidationError(
            "Color Page Alpha Output requires exact --track and --at selectors.",
            details={"track": normalized_track, "at": normalized_at or None},
            recoverability="not_applicable",
        )
    normalized_track = int(normalized_track)
    if normalized_node_index != 1:
        raise ValidationError(
            "Color Page Alpha Output is currently verified only for node 1 in a single-node graph.",
            details={"node_index": normalized_node_index, "verified_node_index": 1},
            recoverability="not_applicable",
        )

    capability_id = "color.page_alpha_output_connect"
    set_execution_engine("db_workaround", 0.8)
    set_capability_context(capability_id, "supported")
    policy = enforce_mutation_policy(
        capability_id,
        intended_engine="db_workaround",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            {
                "message": "DRY-RUN: Would connect the selected Color node key output to native Alpha Output.",
                "route": "db_workaround_color_page_alpha_output_connect",
                "clip": normalized_clip,
                "track": normalized_track,
                "at": normalized_at,
                "node_index": normalized_node_index,
                "verified_topology": "single_node_rgb_alpha",
                "final_foreground_proof_required": True,
                "policy": policy,
            },
            title="Color Page Alpha Output Connect Preview",
        )
        return

    conn = get_connection(require_timeline=True)
    data = color_page_db.write_page_alpha_output_connect(
        conn,
        clip_name=normalized_clip,
        track=normalized_track,
        at=normalized_at,
        node_index=normalized_node_index,
    )
    data["final_foreground_proof_required"] = True
    data["required_next_proof"] = (
        "Export target-only early, middle, and late frames and verify the complete intended foreground subject."
    )
    set_verification_status("verified")
    set_recoverability("not_applicable")
    output(data, title="Color Page Alpha Output Connect")
    success("Color Page Alpha Output connected and verified after reopening DaVinci Resolve.")


def _sky_primary_gui_expected_db_values(primary_values: dict[str, object]) -> dict[str, float]:
    expected: dict[str, float] = {}
    for name, raw_value in primary_values.items():
        if raw_value is None:
            continue
        value = float(raw_value)
        if name == "saturation":
            expected[name] = value / 50.0
        elif name == "hue":
            expected[name] = (value - 50.0) / 50.0
        elif name == "lum_mix":
            expected[name] = value / 100.0
        else:
            expected[name] = value
    return expected


_SKY_PRIMARY_DB_DEFAULTS = {
    "temperature": 0.0,
    "tint": 0.0,
    "hue": 0.0,
    "highlights": 0.0,
    "shadows": 0.0,
    "color_boost": 0.0,
    "mid_detail": 0.0,
    "saturation": 1.0,
    "contrast": 1.0,
    "lum_mix": 1.0,
}


def _verify_sky_primary_gui_db_readback(
    conn,
    *,
    clip_name: str | None,
    node_index: int,
    primary_values: dict[str, object],
    tolerance: float = 0.02,
) -> dict[str, object]:
    expected = _sky_primary_gui_expected_db_values(primary_values)
    save_project: dict[str, object] = {"attempted": False, "ok": None, "target": None}
    save_project_fn = None
    save_target = None
    for target_name, target in (
        ("project_manager", getattr(conn, "project_manager", None)),
        ("project", getattr(conn, "project", None)),
    ):
        candidate = getattr(target, "SaveProject", None) if target is not None else None
        if callable(candidate):
            save_project_fn = candidate
            save_target = target_name
            break
    if callable(save_project_fn):
        save_project["attempted"] = True
        save_project["target"] = save_target
        try:
            save_project["ok"] = bool(save_project_fn())
        except Exception as exc:
            save_project["ok"] = False
            save_project["error"] = str(exc)
    readback = color_page_db.read_color_grade_for_clip(conn, clip_name=clip_name)
    state = readback.get("readback") if isinstance(readback.get("readback"), dict) else {}
    actual: dict[str, float] = {}
    sources = []
    for param in state.get("raw_params") or []:
        if int(param.get("node") or 0) != int(node_index):
            continue
        name = str(param.get("name") or "")
        if name not in expected or "value" not in param:
            continue
        actual[name] = float(param["value"])
    if actual:
        sources.append("read_color_grade_for_clip.raw_params")

    snapshot_values: dict[str, float] = {}
    snapshot_error = None
    if expected and any(name not in actual for name in expected):
        db_path = readback.get("project_db_path")
        clip_readback = readback.get("clip") or clip_name
        if db_path:
            try:
                snapshot = color_page_db.snapshot_color_data(str(db_path), clip_name=clip_readback)
                for clip in snapshot.get("clips") or []:
                    for version in clip.get("versions") or []:
                        for param in version.get("params") or []:
                            if int(param.get("node") or 0) != int(node_index):
                                continue
                            name = str(param.get("name") or "")
                            if name not in expected or "value" not in param:
                                continue
                            snapshot_values[name] = float(param["value"])
                if snapshot_values:
                    actual.update(snapshot_values)
                    sources.append("snapshot_color_data.params")
            except Exception as exc:
                snapshot_error = str(exc)

    implicit_defaults: dict[str, float] = {}
    for name, expected_value in expected.items():
        if name in actual:
            continue
        default_value = _SKY_PRIMARY_DB_DEFAULTS.get(name)
        if default_value is None:
            continue
        if abs(float(expected_value) - float(default_value)) <= tolerance:
            actual[name] = float(default_value)
            implicit_defaults[name] = float(default_value)
    if implicit_defaults:
        sources.append("implicit_db_default")

    mismatches = []
    for name, expected_value in expected.items():
        actual_value = actual.get(name)
        if actual_value is None or abs(float(actual_value) - float(expected_value)) > tolerance:
            mismatches.append(
                {
                    "name": name,
                    "expected": round(float(expected_value), 6),
                    "actual": None if actual_value is None else round(float(actual_value), 6),
                }
            )
    return {
        "status": "verified" if not mismatches else "failed",
        "node_index": int(node_index),
        "expected": {name: round(value, 6) for name, value in expected.items()},
        "actual": {name: round(value, 6) for name, value in actual.items()},
        "snapshot_actual": {name: round(value, 6) for name, value in snapshot_values.items()},
        "implicit_defaults": {name: round(value, 6) for name, value in implicit_defaults.items()},
        "mismatches": mismatches,
        "source": "project_db_color_page_params",
        "sources": sources,
        "save_project": save_project,
        "snapshot_error": snapshot_error,
        "readback": readback,
    }


def _sky_linear_window_db_geometry(
    *,
    window_size: float,
    window_aspect: float,
    window_pan: float,
    window_tilt: float,
    softness: float,
    window_opacity: float,
) -> dict[str, float]:
    """Map sky-isolation GUI-style controls to the verified DB linear-window domain."""
    del window_aspect  # Linear sky recovery intentionally spans the frame horizontally.
    x = max(-2.0, min(2.0, (float(window_pan) - 50.0) / 25.0))
    y = max(-2.0, min(2.0, (float(window_tilt) - 50.0) / 27.0))
    height = max(0.05, min(4.0, float(window_size) / 100.0 * 1.05))
    soft = max(0.0, min(62.5, float(softness)))
    opacity = max(0.0, min(100.0, float(window_opacity)))
    return {
        "x": x,
        "y": y,
        "width": 4.0,
        "height": height,
        "soft_1": soft,
        "soft_2": soft,
        "soft_3": soft,
        "soft_4": soft,
        "opacity": opacity,
    }


@page_app.command("sky-isolation")
@handle_errors
def page_sky_isolation(
    clip_name: Optional[str] = typer.Argument(None, help="Clip name; defaults to current Color page clip"),
    hue: str = typer.Option("0,359", "--hue", help="Sky qualifier hue range in degrees or turns"),
    saturation: str = typer.Option("0,55", "--saturation", "--sat-range", help="Sky qualifier saturation range"),
    luma: str = typer.Option("45,100", "--luma", help="Sky qualifier luma range"),
    window_size: float = typer.Option(100.0, "--window-size", "--size", help="Linear Power Window Size GUI value"),
    window_aspect: float = typer.Option(100.0, "--window-aspect", "--aspect", help="Linear Power Window Aspect GUI value"),
    window_pan: float = typer.Option(50.0, "--window-pan", "--pan", help="Linear Power Window Pan GUI value"),
    window_tilt: float = typer.Option(80.0, "--window-tilt", "--tilt", help="Linear Power Window Tilt GUI value; higher values target the top of frame"),
    window_opacity: float = typer.Option(100.0, "--window-opacity", "--opacity", help="Linear Power Window Opacity GUI value"),
    softness: float = typer.Option(20.0, "--softness", help="Power Window Soft 1-4 GUI value"),
    blur: float = typer.Option(5.0, "--blur", help="Qualifier matte blur"),
    clean_black: float = typer.Option(5.0, "--clean-black", help="Qualifier clean black"),
    clean_white: float = typer.Option(5.0, "--clean-white", help="Qualifier clean white"),
    track: bool = typer.Option(False, "--track/--no-track", help="Track the created native Power Window before applying the sky correction"),
    track_direction: str = typer.Option("forward", "--track-direction", help="Power Window tracking direction when --track is enabled"),
    highlights: float = typer.Option(-35.0, "--highlights", help="Sky recovery Highlights GUI value on the isolated node"),
    sky_saturation: float = typer.Option(60.0, "--sky-saturation", "--sat", help="Sky recovery Saturation GUI value on the isolated node"),
    sky_temperature: Optional[float] = typer.Option(None, "--sky-temperature", "--sky-temp", help="Sky recovery Temp GUI value on the isolated node"),
    sky_tint: Optional[float] = typer.Option(None, "--sky-tint", help="Sky recovery Tint GUI value on the isolated node"),
    sky_contrast: Optional[float] = typer.Option(None, "--sky-contrast", help="Sky recovery Contrast GUI value on the isolated node"),
    sky_pivot: Optional[float] = typer.Option(None, "--sky-pivot", help="Sky recovery Pivot GUI value on the isolated node"),
    sky_shadows: Optional[float] = typer.Option(None, "--sky-shadows", help="Sky recovery Shadows GUI value on the isolated node"),
    sky_color_boost: Optional[float] = typer.Option(None, "--sky-color-boost", help="Sky recovery Color Boost GUI value on the isolated node"),
    sky_mid_detail: Optional[float] = typer.Option(None, "--sky-mid-detail", help="Sky recovery Mid/Detail GUI value on the isolated node"),
    sky_hue: Optional[float] = typer.Option(None, "--sky-hue", help="Sky recovery Hue GUI value on the isolated node"),
    sky_lum_mix: Optional[float] = typer.Option(None, "--sky-lum-mix", help="Sky recovery Lum Mix GUI value on the isolated node"),
    slope: Optional[str] = typer.Option(None, "--slope", help="Legacy DB CDL option; unsupported in the GUI workflow"),
    offset: Optional[str] = typer.Option(None, "--offset", help="Legacy DB CDL option; unsupported in the GUI workflow"),
    power: Optional[str] = typer.Option(None, "--power", help="Legacy DB CDL option; unsupported in the GUI workflow"),
    max_changed_percent: float = typer.Option(
        45.0,
        "--max-changed-percent",
        help="Fail if proof changes more than this percentage of frame pixels",
    ),
    max_bottom_fraction: float = typer.Option(
        0.45,
        "--max-bottom-fraction",
        help="Fail if changed pixels extend below this normalized frame height",
    ),
    min_changed_percent: float = typer.Option(
        0.01,
        "--min-changed-percent",
        help="Fail if proof changes fewer than this percentage of frame pixels",
    ),
    min_max_channel_diff: int = typer.Option(
        3,
        "--min-max-channel-diff",
        help="Fail if the strongest proof pixel changes by fewer than this many 8-bit channel levels",
    ),
    min_mean_abs_diff: float = typer.Option(
        0.2,
        "--min-mean-abs-diff",
        help="Fail if the proof mean absolute channel difference is weaker than this 8-bit value",
    ),
):
    """Recover an overexposed sky through a proof-gated native Color Page GUI local workflow."""
    from ..core import color_page_db, color_page_gui_route

    clip_name = color_page_gui_route.normalize_optional_clip(_option_value(clip_name))
    hue = str(_option_value(hue, "0,359") or "").strip()
    saturation = str(_option_value(saturation, "0,55") or "").strip()
    luma = str(_option_value(luma, "45,100") or "").strip()
    window_size = float(_option_value(window_size, 100.0))
    window_aspect = float(_option_value(window_aspect, 100.0))
    window_pan = float(_option_value(window_pan, 50.0))
    window_tilt = float(_option_value(window_tilt, 80.0))
    window_opacity = float(_option_value(window_opacity, 100.0))
    softness = float(_option_value(softness, 20.0))
    blur = float(_option_value(blur, 5.0))
    clean_black = float(_option_value(clean_black, 5.0))
    clean_white = float(_option_value(clean_white, 5.0))
    track = bool(_option_value(track, False))
    track_direction = color_page_gui_route.normalize_track_direction(_option_value(track_direction, "forward") or "forward")
    highlights = float(_option_value(highlights, -35.0))
    sky_saturation = float(_option_value(sky_saturation, 60.0))
    sky_temperature = _option_value(sky_temperature)
    sky_tint = _option_value(sky_tint)
    sky_contrast = _option_value(sky_contrast)
    sky_pivot = _option_value(sky_pivot)
    sky_shadows = _option_value(sky_shadows)
    sky_color_boost = _option_value(sky_color_boost)
    sky_mid_detail = _option_value(sky_mid_detail)
    sky_hue = _option_value(sky_hue)
    sky_lum_mix = _option_value(sky_lum_mix)
    slope = _option_value(slope)
    offset = _option_value(offset)
    power = _option_value(power)
    max_changed_percent = float(_option_value(max_changed_percent, 45.0))
    max_bottom_fraction = float(_option_value(max_bottom_fraction, 0.45))
    min_changed_percent = float(_option_value(min_changed_percent, 0.01))
    min_max_channel_diff = int(_option_value(min_max_channel_diff, 3))
    min_mean_abs_diff = float(_option_value(min_mean_abs_diff, 0.2))
    if max_changed_percent <= 0.0 or max_changed_percent > 100.0:
        raise ValidationError(
            "--max-changed-percent must be greater than 0 and at most 100.",
            details={"max_changed_percent": max_changed_percent},
            recoverability="not_applicable",
        )
    if min_changed_percent < 0.0 or min_changed_percent >= max_changed_percent:
        raise ValidationError(
            "--min-changed-percent must be non-negative and lower than --max-changed-percent.",
            details={"min_changed_percent": min_changed_percent, "max_changed_percent": max_changed_percent},
            recoverability="not_applicable",
        )
    if max_bottom_fraction <= 0.0 or max_bottom_fraction > 1.0:
        raise ValidationError(
            "--max-bottom-fraction must be greater than 0 and at most 1.",
            details={"max_bottom_fraction": max_bottom_fraction},
            recoverability="not_applicable",
        )
    if min_max_channel_diff < 1 or min_max_channel_diff > 255:
        raise ValidationError(
            "--min-max-channel-diff must be between 1 and 255.",
            details={"min_max_channel_diff": min_max_channel_diff},
            recoverability="not_applicable",
        )
    if min_mean_abs_diff < 0.0 or min_mean_abs_diff > 255.0:
        raise ValidationError(
            "--min-mean-abs-diff must be between 0 and 255.",
            details={"min_mean_abs_diff": min_mean_abs_diff},
            recoverability="not_applicable",
        )
    if any(value is not None for value in (slope, offset, power)):
        set_execution_engine("resolve_gui")
        set_capability_context("color.page_sky_isolation_gui", "supported")
        set_verification_status("failed")
        set_recoverability("manual")
        raise CapabilityNegotiationFailed(
            "Legacy DB CDL options are not supported by the production-safe GUI sky isolation workflow.",
            details={
                "route": color_page_gui_route.ROUTE_SKY_ISOLATION_GUI,
                "unsupported_options": {
                    "slope": slope,
                    "offset": offset,
                    "power": power,
                },
                "supported_correction_controls": [
                    "--highlights",
                    "--sky-saturation",
                    "--sky-temperature",
                    "--sky-tint",
                    "--sky-contrast",
                    "--sky-pivot",
                    "--sky-shadows",
                    "--sky-color-boost",
                    "--sky-mid-detail",
                    "--sky-hue",
                    "--sky-lum-mix",
                ],
            },
            recoverability="manual",
        )

    hsl_request = color_page_gui_route.normalize_qualifier_gui_hsl_controls(
        hue=hue,
        saturation=saturation,
        luma=luma,
        softness=softness,
    )
    matte_request = color_page_gui_route.normalize_qualifier_gui_matte_controls(
        blur=blur,
        clean_black=clean_black,
        clean_white=clean_white,
    )
    window_request = color_page_gui_route.normalize_power_window_gui_controls(
        shape="linear",
        size=window_size,
        aspect=window_aspect,
        pan=window_pan,
        tilt=window_tilt,
        opacity=window_opacity,
        soft_1=softness,
        soft_2=softness,
        soft_3=softness,
        soft_4=softness,
    )
    primary_request = color_page_gui_route.normalize_primary_gui_controls(
        temperature=sky_temperature,
        tint=sky_tint,
        contrast=sky_contrast if sky_contrast is not None else 1.0,
        pivot=sky_pivot,
        shadows=sky_shadows,
        highlights=highlights,
        color_boost=sky_color_boost,
        mid_detail=sky_mid_detail,
        saturation=sky_saturation,
        hue=sky_hue,
        lum_mix=sky_lum_mix,
    )
    window_db_geometry = _sky_linear_window_db_geometry(
        window_size=window_size,
        window_aspect=window_aspect,
        window_pan=window_pan,
        window_tilt=window_tilt,
        softness=softness,
        window_opacity=window_opacity,
    )
    primary_db_values = _sky_primary_gui_expected_db_values(primary_request["values"])

    capability_id = "color.page_sky_isolation_gui"
    policy = enforce_mutation_policy(
        capability_id,
        intended_engine="resolve_gui",
        mutating=not is_dry_run(),
    )
    set_execution_engine("resolve_gui")
    set_capability_context(capability_id, "supported")
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            {
                "message": "DRY-RUN: Would isolate and recover sky through GUI Power Window + HSL qualifier + Primaries with render/locality proof.",
                "route": color_page_gui_route.ROUTE_SKY_ISOLATION_GUI,
                "clip": clip_name,
                "would_mutate": True,
                "steps": [
                    "add_db_serial_node",
                    "initialize_db_node_grade_body",
                    "set_gui_hsl_qualifier",
                    "set_gui_matte_refinement",
                    "set_db_linear_power_window",
                    *(["track_gui_power_window"] if track else []),
                    "set_db_primary_correction",
                    "verify_render_proof_and_locality",
                ],
                "requested": {
                    "window": window_request,
                    "window_db_geometry": window_db_geometry,
                    "tracking": {
                        "enabled": track,
                        "direction": track_direction if track else None,
                        "route": color_page_gui_route.ROUTE_POWER_WINDOW_TRACK if track else None,
                    },
                    "qualifier": hsl_request,
                    "matte": matte_request,
                    "correction": primary_request,
                    "expected_primary_db_values": primary_db_values,
                    "locality_guard": {
                        "min_changed_percent": min_changed_percent,
                        "max_changed_percent": max_changed_percent,
                        "min_max_channel_diff": min_max_channel_diff,
                        "min_mean_abs_diff": min_mean_abs_diff,
                        "max_bottom_fraction": max_bottom_fraction,
                    },
                },
                "policy": policy,
            },
            title="Color Page Sky Isolation GUI Preview",
        )
        return

    conn = get_connection(require_timeline=True)
    try:
        steps = []
        node_add = color_page_db.write_page_node_add_serial(conn, clip_name=clip_name)
        steps.append({"step": "add_db_serial_node", "result": node_add})
        node_index = int(node_add["node_index"])

        init_set = color_page_db.write_color_grade(
            conn,
            clip_name=clip_name,
            node_index=node_index,
            contrast=1.01,
        )
        conn = get_connection(require_timeline=True)
        init_readback = _verify_sky_primary_gui_db_readback(
            conn,
            clip_name=clip_name,
            node_index=node_index,
            primary_values={"contrast": 1.01},
        )
        steps.append(
            {
                "step": "initialize_db_node_grade_body",
                "result": {
                    "primary_db_set": init_set,
                    "save_and_readback": init_readback,
                    "render_proof_required": False,
                },
            }
        )

        hsl_set = color_page_gui_route.run_qualifier_gui_hsl_set(
            conn,
            clip_name=clip_name,
            controls=hsl_request["controls"],
        )
        steps.append({"step": "set_gui_hsl_qualifier", "result": hsl_set})

        matte_set = color_page_gui_route.run_qualifier_gui_matte_set(
            conn,
            clip_name=clip_name,
            controls=matte_request["controls"],
        )
        steps.append({"step": "set_gui_matte_refinement", "result": matte_set})

        conn = get_connection(require_timeline=True)
        window_set = color_page_db.write_linear_power_window(
            conn,
            clip_name=clip_name,
            node_index=node_index,
            **window_db_geometry,
        )
        steps.append({"step": "set_db_linear_power_window", "result": window_set})

        # DB-backed Color Page writes close and reopen the project, which resets the
        # ResolveConnection singleton. Never keep using the pre-mutation API object
        # for GUI tracking or proof export after this point.
        conn = get_connection(require_timeline=True)

        if track:
            def _export_track_proof(path: Path) -> dict:
                proof_conn = get_connection(require_timeline=True)
                metadata = _export_color_page_frame_as_still(proof_conn, resolved_path=path, requested_output_path=str(path))
                return {"export_path": str(path), **metadata}

            track_set = color_page_gui_route.run_power_window_track(
                conn,
                clip_name=clip_name,
                shape=window_request["shape"],
                direction=track_direction,
                proof_exporter=_export_track_proof,
                expected_node_index=node_index,
            )
            steps.append({"step": "track_gui_power_window", "result": track_set})

        conn = get_connection(require_timeline=True)
        proof = _begin_color_render_proof(
            conn,
            clip_name=clip_name,
            route=color_page_gui_route.ROUTE_SKY_ISOLATION_GUI,
        )
        primary_set = color_page_db.write_color_grade(
            conn,
            clip_name=clip_name,
            node_index=node_index,
            **primary_db_values,
        )
        final_primary_step = {"step": "set_db_primary_correction", "result": primary_set}
        partial = {
            "route": color_page_gui_route.ROUTE_SKY_ISOLATION_GUI,
            "clip": clip_name,
            "node_index": node_index,
            "steps": steps + [final_primary_step],
        }
        conn_after = get_connection(require_timeline=True)
        render_proof = _complete_color_render_proof(conn_after, proof, partial_result=partial)
        final_graph = color_page_gui_route._color_node_graph_snapshot(conn_after, clip_name)
        primary_readback = _verify_sky_primary_gui_db_readback(
            conn_after,
            clip_name=clip_name,
            node_index=node_index,
            primary_values=primary_request["values"],
        )
        if primary_readback["status"] != "verified":
            set_verification_status("failed")
            set_recoverability("manual")
            raise APICallFailed(
                "Color Page sky isolation GUI Primaries did not verify on the newly created local node.",
                details={
                    "reason": "sky_isolation_primary_db_readback_failed",
                    "primary_readback": primary_readback,
                    "render_proof": render_proof,
                    "partial_result": partial,
                },
                recoverability="manual",
            )
        final_node = None
        for node in final_graph.get("nodes") or []:
            if int(node.get("index") or 0) == node_index:
                final_node = node
                break
        final_tools = [str(value) for value in (final_node or {}).get("tools") or []]
        missing_tools = []
        if not any("Power Windows" in value for value in final_tools):
            missing_tools.append("Power Windows")
        if not any("HSL Qualifier" in value for value in final_tools):
            missing_tools.append("HSL Qualifier")
        if not any("Primary" in value or "Saturation, Hue" in value for value in final_tools):
            missing_tools.append("Primary Balance")
        if track and not any("Tracking" in value for value in final_tools):
            missing_tools.append("Tracking")
        if missing_tools:
            set_verification_status("failed")
            set_recoverability("manual")
            raise APICallFailed(
                "Color Page sky isolation final node graph did not contain the required local grading tools.",
                details={
                    "reason": "sky_isolation_final_node_graph_missing_tools",
                    "node_index": node_index,
                    "missing_tools": missing_tools,
                    "final_node": final_node,
                    "final_graph": final_graph,
                    "render_proof": render_proof,
                    "partial_result": partial,
                },
                recoverability="manual",
            )
        comparison = render_proof.get("comparison") if isinstance(render_proof.get("comparison"), dict) else {}
        frame = comparison.get("frame") if isinstance(comparison.get("frame"), dict) else {}
        bounds = comparison.get("changed_bounds") if isinstance(comparison.get("changed_bounds"), dict) else None
        changed_percent = float(comparison.get("changed_pixel_percent") or 0.0)
        max_channel_abs_diff = int(comparison.get("max_channel_abs_diff") or 0)
        mean_abs_diff = float(comparison.get("mean_abs_diff") or 0.0)
        frame_height = int(frame.get("height") or 0)
        max_bottom = int(frame_height * max_bottom_fraction) if frame_height else None
        locality_failures = []
        if changed_percent < min_changed_percent:
            locality_failures.append("changed_percent_below_minimum")
        if changed_percent > max_changed_percent:
            locality_failures.append("changed_percent_above_maximum")
        if max_channel_abs_diff < min_max_channel_diff:
            locality_failures.append("max_channel_diff_below_minimum")
        if mean_abs_diff < min_mean_abs_diff:
            locality_failures.append("mean_abs_diff_below_minimum")
        if not bounds:
            locality_failures.append("missing_changed_bounds")
        elif max_bottom is not None and int(bounds.get("bottom") or 0) > max_bottom:
            locality_failures.append("changed_bounds_extend_below_sky_guard")
        locality = {
            "status": "verified" if not locality_failures else "failed",
            "failures": locality_failures,
            "changed_pixel_percent": changed_percent,
            "changed_bounds": bounds,
            "frame_height": frame_height,
            "max_bottom_fraction": max_bottom_fraction,
            "max_bottom_pixel": max_bottom,
            "min_changed_percent": min_changed_percent,
            "max_changed_percent": max_changed_percent,
            "max_channel_abs_diff": max_channel_abs_diff,
            "min_max_channel_diff": min_max_channel_diff,
            "mean_abs_diff": mean_abs_diff,
            "min_mean_abs_diff": min_mean_abs_diff,
        }
        if locality_failures:
            set_verification_status("failed")
            set_recoverability("manual")
            raise ColorRenderProofFailed(
                "Color Page sky isolation changed pixels outside the allowed sky locality guard.",
                details={
                    "reason": "sky_isolation_locality_guard_failed",
                    "locality": locality,
                    "render_proof": render_proof,
                    "partial_result": partial,
                },
                recoverability="manual",
            )
        steps.append(final_primary_step)
        data = {
            "route": color_page_gui_route.ROUTE_SKY_ISOLATION_GUI,
            "clip": clip_name,
            "node_index": node_index,
            "requested": {
                "window": window_request,
                "window_db_geometry": window_db_geometry,
                "tracking": {
                    "enabled": track,
                    "direction": track_direction if track else None,
                    "route": color_page_gui_route.ROUTE_POWER_WINDOW_TRACK if track else None,
                },
                "qualifier": hsl_request,
                "matte": matte_request,
                "correction": primary_request,
                "expected_primary_db_values": primary_db_values,
            },
            "steps": steps,
            "final_node_graph": final_graph,
            "final_node": final_node,
            "render_proof": render_proof,
            "primary_readback": primary_readback,
            "locality": locality,
            "verification": {
                "status": "verified",
                "render_proof_status": render_proof["status"],
                "render_proof_route": render_proof["route"],
                "locality_status": locality["status"],
                "node_targeting": "new_gui_serial_node",
                "power_window_tracking": "verified" if track else "not_requested",
            },
        }
        set_execution_engine("resolve_gui")
        set_verification_status("verified")
        set_recoverability("not_applicable")
    except CLIError:
        set_execution_engine("resolve_gui", 0.65)
        set_capability_context(capability_id, "supported")
        set_verification_status("failed")
        raise
    output(data, title="Color Page — Sky Isolation GUI")
    success("Color Page sky isolation verified through GUI route and render/locality proof.")


@page_app.command("node-cleanup")
@handle_errors
def page_node_cleanup(
    clip_name: Optional[str] = typer.Argument(None, help="Clip name"),
    mode: str = typer.Option("empty-serial", "--mode", help="Cleanup mode. Currently verified: empty-serial"),
):
    """Clean up verified native Color Page node graph cases via DB."""
    from ..core import color_page_db

    clip_name = _option_value(clip_name)
    normalized_mode = str(_option_value(mode) or "").strip().lower().replace("_", "-")
    if normalized_mode != "empty-serial":
        _unsupported_color_page_preview(
            "color.page_node_cleanup_general",
            "not_available_color_page_node_cleanup_general",
            {
                "clip": clip_name,
                "mode": normalized_mode,
                "verified_modes": ["empty-serial"],
            },
            "Color Page Node Cleanup General Availability",
        )
        return

    set_execution_engine("db_workaround", 0.75)
    set_capability_context("color.page_node_cleanup_empty_serial", "supported")

    enforce_mutation_policy(
        "color.page_node_cleanup_empty_serial",
        intended_engine="db_workaround",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        dry_run_message("Would remove empty serial Color Page nodes via DB")
        return

    conn = get_connection(require_timeline=True)
    data = color_page_db.write_page_node_cleanup_empty_serial(conn, clip_name=clip_name)
    data["mode"] = normalized_mode
    output(data, title="Color Page — Node Cleanup")
    success("Color Page empty serial nodes cleaned up via DB.")


@page_app.command("node-cleanup-general")
@handle_errors
def page_node_cleanup_general(
    clip_name: Optional[str] = typer.Argument(None, help="Clip name"),
    mode: str = typer.Option("all", "--mode", help="Requested general graph cleanup mode"),
):
    """Clean up verified native Color Page node graph cases via DB."""
    from ..core import color_page_db

    clip_name = _option_value(clip_name)
    requested_mode = str(_option_value(mode, "all") or "all").strip().lower().replace("_", "-")
    if requested_mode not in {"all", "empty-serial", "empty-serials"}:
        raise ValidationError(
            "Color Page node-cleanup-general currently supports empty serial cleanup.",
            details={"mode": mode, "allowed": ["all", "empty-serial", "empty-serials"]},
            recoverability="not_applicable",
        )
    set_execution_engine("db_workaround", 0.75)
    set_capability_context("color.page_node_cleanup_general", "supported")
    enforce_mutation_policy(
        "color.page_node_cleanup_general",
        intended_engine="db_workaround",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        dry_run_message("Would remove empty serial Color Page nodes via DB")
        return

    conn = get_connection(require_timeline=True)
    data = color_page_db.write_page_node_cleanup_empty_serial(conn, clip_name=clip_name)
    data["route"] = "db_workaround_color_page_node_cleanup_general"
    data["requested_mode"] = requested_mode
    data["effective_mode"] = "empty-serial"
    output(data, title="Color Page — Node Cleanup General")
    success("Color Page empty serial nodes cleaned up via DB.")


@page_app.command("cst-set")
@handle_errors
def page_cst_set(
    clip_name: Optional[str] = typer.Argument(None, help="Clip name"),
    node_index: int = typer.Option(1, "--node-index", "--node", help="1-based Color Page node index to receive/update the CST OFX tool"),
    input_color_space: Optional[str] = typer.Option(None, "--input-color-space", help="Input color space label or DaVinci Resolve token"),
    input_gamma: Optional[str] = typer.Option(None, "--input-gamma", help="Input gamma label or DaVinci Resolve token"),
    output_color_space: Optional[str] = typer.Option(None, "--output-color-space", help="Output color space label or DaVinci Resolve token"),
    output_gamma: Optional[str] = typer.Option(None, "--output-gamma", help="Output gamma label or DaVinci Resolve token"),
    require_render_proof: bool = typer.Option(
        True,
        "--require-render-proof/--setup-only",
        help="Export before/after Color Page frames and fail unless the rendered image changes.",
    ),
):
    """Create/update native ResolveFX Color Space Transform via DB and rendered-frame proof."""
    from ..core import color_page_db

    clip_name = _option_value(clip_name)
    input_color_space = _option_value(input_color_space)
    input_gamma = _option_value(input_gamma)
    output_color_space = _option_value(output_color_space)
    output_gamma = _option_value(output_gamma)
    require_render_proof = bool(_option_value(require_render_proof, True))
    node_index = int(_option_value(node_index, 1) or 1)
    if node_index < 1:
        raise ValidationError(
            "Color Page node index must be a positive integer.",
            details={"node_index": node_index, "minimum": 1},
            recoverability="not_applicable",
        )

    set_execution_engine("db_workaround", 0.75)
    set_capability_context("color.page_cst_set", "supported")

    if not any([input_color_space, input_gamma, output_color_space, output_gamma]):
        raise ValidationError(
            "Color Page cst-set requires at least one CST option.",
            recoverability="not_applicable",
        )

    enforce_mutation_policy(
        "color.page_cst_set",
        intended_engine="db_workaround",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        output(
            {
                "message": "DRY-RUN: Would set Color Page Color Space Transform options via DB.",
                "route": "db_workaround_color_page_cst_existing_ofx",
                "clip": clip_name,
                "requested": {
                    "node_index": node_index,
                    "input_color_space": input_color_space,
                    "input_gamma": input_gamma,
                    "output_color_space": output_color_space,
                    "output_gamma": output_gamma,
                },
                "render_proof_required": require_render_proof,
                "render_proof": {
                    "status": "would_run" if require_render_proof else "not_requested",
                    "required": require_render_proof,
                },
            },
            title="Color Page — CST Set Preview",
        )
        return

    conn = get_connection(require_timeline=True)
    render_proof = None
    if require_render_proof:
        render_proof = _begin_color_render_proof(
            conn,
            clip_name=clip_name,
            route="db_workaround_color_page_cst_set",
        )
    data = color_page_db.write_color_space_transform(
        conn,
        clip_name=clip_name,
        node_index=node_index,
        input_color_space=input_color_space,
        input_gamma=input_gamma,
        output_color_space=output_color_space,
        output_gamma=output_gamma,
    )
    data["route"] = data.get("route") or (data.get("mutation_result") or {}).get("route", "db_workaround_color_page_cst_existing_ofx")
    data.setdefault("verification", {})
    if render_proof is not None:
        conn_after = get_connection(require_timeline=True)
        try:
            data["render_proof"] = _complete_color_render_proof(
                conn_after,
                render_proof,
                partial_result=data,
                min_changed_pixel_percent=0.5,
                min_mean_abs_diff=0.1,
                min_max_channel_abs_diff=2,
            )
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
    output(data, title="Color Page — CST Set")
    success("Color Page Color Space Transform options written and verified.")


@page_app.command("power-window-circle")
@handle_errors
def page_power_window_circle(
    clip_name: Optional[str] = typer.Argument(None, help="Clip name"),
    node_index: int = typer.Option(1, "--node-index", "--node", help="1-based Color Page node index; create/use an empty local node for secondaries"),
    size: float = typer.Option(288.0, "--size", help="Circle Power Window size in DaVinci Resolve DB units"),
    soft_1: Optional[float] = typer.Option(None, "--soft-1", help="Circle Power Window GUI Soft 1 value, 0..100"),
    pan: Optional[float] = typer.Option(None, "--pan", help="Circle Power Window GUI Pan value, 0..100 with 50 centered"),
    tilt: Optional[float] = typer.Option(None, "--tilt", help="Circle Power Window GUI Tilt value, 0..100 with 50 centered"),
    opacity: Optional[float] = typer.Option(None, "--opacity", help="Circle Power Window GUI Opacity value, 0..100"),
    invert: Optional[bool] = typer.Option(None, "--invert/--no-invert", help="Set the outside/inverted Circle Power Window selection"),
):
    """Create/update a native Color Page Circle Power Window via DB readback."""
    from ..core import color_page_db

    clip_name = _option_value(clip_name)
    node_index = int(_option_value(node_index) or 1)
    size = _option_value(size, 288.0)
    soft_1 = _option_value(soft_1)
    pan = _option_value(pan)
    tilt = _option_value(tilt)
    opacity = _option_value(opacity)

    set_execution_engine("db_workaround", 0.75)
    set_capability_context("color.page_power_window_circle", "supported")

    if node_index < 1:
        raise ValidationError(
            "Color Page power-window-circle --node must be a positive integer.",
            details={"node_index": node_index, "minimum": 1},
            recoverability="not_applicable",
        )
    if size <= 0 or size > 4096:
        raise ValidationError(
            "Color Page power-window-circle --size must be between 0 and 4096.",
            details={"size": size},
            recoverability="not_applicable",
        )
    if pan is not None and (pan < 0 or pan > 100):
        raise ValidationError(
            "Color Page power-window-circle --pan must be between 0 and 100.",
            details={"pan": pan},
            recoverability="not_applicable",
        )
    if soft_1 is not None and (soft_1 < 0 or soft_1 > 100):
        raise ValidationError(
            "Color Page power-window-circle --soft-1 must be between 0 and 100.",
            details={"soft_1": soft_1},
            recoverability="not_applicable",
        )
    if tilt is not None and (tilt < 0 or tilt > 100):
        raise ValidationError(
            "Color Page power-window-circle --tilt must be between 0 and 100.",
            details={"tilt": tilt},
            recoverability="not_applicable",
        )
    if opacity is not None and (opacity < 0 or opacity > 100):
        raise ValidationError(
            "Color Page power-window-circle --opacity must be between 0 and 100.",
            details={"opacity": opacity},
            recoverability="not_applicable",
        )

    enforce_mutation_policy(
        "color.page_power_window_circle",
        intended_engine="db_workaround",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        dry_run_message("Would create/update a native Color Page Circle Power Window via DB")
        return

    conn = get_connection(require_timeline=True)
    data = color_page_db.write_circle_power_window(
        conn,
        clip_name=clip_name,
        node_index=node_index,
        size=float(size),
        soft_1=float(soft_1) if soft_1 is not None else None,
        pan=float(pan) if pan is not None else None,
        tilt=float(tilt) if tilt is not None else None,
        opacity=float(opacity) if opacity is not None else None,
        invert=invert,
    )
    output(data, title="Color Page — Power Window Circle")
    success("Color Page Circle Power Window written to DB.")


@page_app.command("power-window-gradient")
@handle_errors
def page_power_window_gradient(
    clip_name: Optional[str] = typer.Argument(None, help="Clip name"),
    node_index: int = typer.Option(1, "--node-index", "--node", help="1-based Color Page node index; create/use an empty local node for secondaries"),
    size: float = typer.Option(
        200.0,
        "--size",
        help="Legacy internal Gradient Soft 1 payload; GUI Soft 1 2.00 is internal 200.0",
    ),
):
    """Create/update a native Color Page Gradient Power Window via DB readback."""
    from ..core import color_page_db

    clip_name = _option_value(clip_name)
    node_index = int(_option_value(node_index) or 1)
    size = _option_value(size, 200.0)

    set_execution_engine("db_workaround", 0.75)
    set_capability_context("color.page_power_window_gradient", "supported")

    if node_index < 1:
        raise ValidationError(
            "Color Page power-window-gradient --node must be a positive integer.",
            details={"node_index": node_index, "minimum": 1},
            recoverability="not_applicable",
        )
    enforce_mutation_policy(
        "color.page_power_window_gradient",
        intended_engine="db_workaround",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        dry_run_message("Would create/update a native Color Page Gradient Power Window via DB")
        return

    color_page_db.validate_gradient_power_window_size(float(size))
    conn = get_connection(require_timeline=True)
    data = color_page_db.write_gradient_power_window(
        conn,
        clip_name=clip_name,
        node_index=node_index,
        size=float(size),
    )
    output(data, title="Color Page — Power Window Gradient")
    success("Color Page Gradient Power Window written to DB.")


@page_app.command("power-window-linear")
@handle_errors
def page_power_window_linear(
    clip_name: Optional[str] = typer.Argument(None, help="Clip name"),
    node_index: int = typer.Option(1, "--node-index", "--node", help="1-based Color Page node index; create/use an empty local node for secondaries"),
    x: Optional[float] = typer.Option(None, "--x", help="Linear Power Window internal horizontal offset (-2..2, 0 default)"),
    y: Optional[float] = typer.Option(None, "--y", help="Linear Power Window internal vertical offset (-2..2, 0 default)"),
    width: Optional[float] = typer.Option(None, "--width", help="Linear Power Window internal width scale (0.05..4, 1 default)"),
    height: Optional[float] = typer.Option(None, "--height", help="Linear Power Window internal height scale (0.05..4, 1 default)"),
    soft_1: Optional[float] = typer.Option(None, "--soft-1", help="Linear Power Window GUI Soft 1 value (0..62.5)"),
    soft_2: Optional[float] = typer.Option(None, "--soft-2", help="Linear Power Window GUI Soft 2 value (0..62.5)"),
    soft_3: Optional[float] = typer.Option(None, "--soft-3", help="Linear Power Window GUI Soft 3 value (0..62.5)"),
    soft_4: Optional[float] = typer.Option(None, "--soft-4", help="Linear Power Window GUI Soft 4 value (0..62.5)"),
    opacity: Optional[float] = typer.Option(None, "--opacity", help="Linear Power Window GUI Opacity value (0..100)"),
):
    """Create/update a native Color Page Linear Power Window via DB readback."""
    from ..core import color_page_db

    clip_name = _option_value(clip_name)
    node_index = int(_option_value(node_index) or 1)
    x = _option_value(x)
    y = _option_value(y)
    width = _option_value(width)
    height = _option_value(height)
    soft_1 = _option_value(soft_1)
    soft_2 = _option_value(soft_2)
    soft_3 = _option_value(soft_3)
    soft_4 = _option_value(soft_4)
    opacity = _option_value(opacity)

    set_execution_engine("db_workaround", 0.75)
    set_capability_context("color.page_power_window_linear", "supported")

    if node_index < 1:
        raise ValidationError(
            "Color Page power-window-linear --node must be a positive integer.",
            details={"node_index": node_index, "minimum": 1},
            recoverability="not_applicable",
        )
    enforce_mutation_policy(
        "color.page_power_window_linear",
        intended_engine="db_workaround",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        dry_run_message("Would create/update a native Color Page Linear Power Window via DB")
        return

    color_page_db.validate_linear_power_window_geometry(
        x=float(x) if x is not None else None,
        y=float(y) if y is not None else None,
        width=float(width) if width is not None else None,
        height=float(height) if height is not None else None,
        soft_1=float(soft_1) if soft_1 is not None else None,
        soft_2=float(soft_2) if soft_2 is not None else None,
        soft_3=float(soft_3) if soft_3 is not None else None,
        soft_4=float(soft_4) if soft_4 is not None else None,
        opacity=float(opacity) if opacity is not None else None,
    )
    conn = get_connection(require_timeline=True)
    data = color_page_db.write_linear_power_window(
        conn,
        clip_name=clip_name,
        node_index=node_index,
        x=float(x) if x is not None else None,
        y=float(y) if y is not None else None,
        width=float(width) if width is not None else None,
        height=float(height) if height is not None else None,
        soft_1=float(soft_1) if soft_1 is not None else None,
        soft_2=float(soft_2) if soft_2 is not None else None,
        soft_3=float(soft_3) if soft_3 is not None else None,
        soft_4=float(soft_4) if soft_4 is not None else None,
        opacity=float(opacity) if opacity is not None else None,
    )
    output(data, title="Color Page — Power Window Linear")
    success("Color Page Linear Power Window written to DB.")


@page_app.command("power-window-rectangle")
@handle_errors
def page_power_window_rectangle(
    clip_name: Optional[str] = typer.Argument(None, help="Clip name"),
    node_index: int = typer.Option(1, "--node-index", "--node", help="1-based Color Page node index; create/use an empty local node for secondaries"),
    x: Optional[float] = typer.Option(None, "--x", help="Rectangle/Linear Power Window internal horizontal offset (-2..2, 0 default)"),
    y: Optional[float] = typer.Option(None, "--y", help="Rectangle/Linear Power Window internal vertical offset (-2..2, 0 default)"),
    width: Optional[float] = typer.Option(None, "--width", help="Rectangle/Linear Power Window internal width scale (0.05..4, 1 default)"),
    height: Optional[float] = typer.Option(None, "--height", help="Rectangle/Linear Power Window internal height scale (0.05..4, 1 default)"),
    soft_1: Optional[float] = typer.Option(None, "--soft-1", help="Rectangle/Linear Power Window GUI Soft 1 value (0..62.5)"),
    soft_2: Optional[float] = typer.Option(None, "--soft-2", help="Rectangle/Linear Power Window GUI Soft 2 value (0..62.5)"),
    soft_3: Optional[float] = typer.Option(None, "--soft-3", help="Rectangle/Linear Power Window GUI Soft 3 value (0..62.5)"),
    soft_4: Optional[float] = typer.Option(None, "--soft-4", help="Rectangle/Linear Power Window GUI Soft 4 value (0..62.5)"),
    opacity: Optional[float] = typer.Option(None, "--opacity", help="Rectangle/Linear Power Window GUI Opacity value (0..100)"),
    require_render_proof: bool = typer.Option(False, "--require-render-proof", help="Export before/after Color Page frames and fail unless the rendered image changes"),
):
    """Create/update DaVinci Resolve's rectangular Linear Power Window via DB readback."""
    from ..core import color_page_db

    clip_name = _option_value(clip_name)
    node_index = int(_option_value(node_index) or 1)
    x = _option_value(x)
    y = _option_value(y)
    width = _option_value(width)
    height = _option_value(height)
    soft_1 = _option_value(soft_1)
    soft_2 = _option_value(soft_2)
    soft_3 = _option_value(soft_3)
    soft_4 = _option_value(soft_4)
    opacity = _option_value(opacity)
    require_render_proof = bool(_option_value(require_render_proof, False))

    set_execution_engine("db_workaround", 0.75)
    set_capability_context("color.page_power_window_rectangle", "supported")

    if node_index < 1:
        raise ValidationError(
            "Color Page power-window-rectangle --node must be a positive integer.",
            details={"node_index": node_index, "minimum": 1},
            recoverability="not_applicable",
        )
    enforce_mutation_policy(
        "color.page_power_window_rectangle",
        intended_engine="db_workaround",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        dry_run_message("Would create/update DaVinci Resolve's rectangular Linear Power Window via DB")
        return

    color_page_db.validate_linear_power_window_geometry(
        x=float(x) if x is not None else None,
        y=float(y) if y is not None else None,
        width=float(width) if width is not None else None,
        height=float(height) if height is not None else None,
        soft_1=float(soft_1) if soft_1 is not None else None,
        soft_2=float(soft_2) if soft_2 is not None else None,
        soft_3=float(soft_3) if soft_3 is not None else None,
        soft_4=float(soft_4) if soft_4 is not None else None,
        opacity=float(opacity) if opacity is not None else None,
    )
    conn = get_connection(require_timeline=True)
    render_proof = None
    if require_render_proof:
        render_proof = _begin_color_render_proof(
            conn,
            clip_name=clip_name,
            route="db_workaround_color_page_power_window_rectangle",
        )
    data = color_page_db.write_linear_power_window(
        conn,
        clip_name=clip_name,
        node_index=node_index,
        x=float(x) if x is not None else None,
        y=float(y) if y is not None else None,
        width=float(width) if width is not None else None,
        height=float(height) if height is not None else None,
        soft_1=float(soft_1) if soft_1 is not None else None,
        soft_2=float(soft_2) if soft_2 is not None else None,
        soft_3=float(soft_3) if soft_3 is not None else None,
        soft_4=float(soft_4) if soft_4 is not None else None,
        opacity=float(opacity) if opacity is not None else None,
    )
    data["db_route"] = data.get("route")
    data["route"] = "db_workaround_color_page_power_window_rectangle"
    data["native_shape"] = "linear"
    data["alias_of"] = "color page power-window-linear"
    if render_proof is not None:
        conn_after = get_connection(require_timeline=True)
        data["render_proof"] = _complete_color_render_proof(conn_after, render_proof, partial_result=data)
        data.setdefault("verification", {})
        data["verification"]["status"] = "verified"
        data["verification"]["render_proof_status"] = data["render_proof"]["status"]
        data["verification"]["render_proof_route"] = data["render_proof"]["route"]
        data["verification"]["render_proof_required"] = True
        set_verification_status("verified")
        set_recoverability("not_applicable")
    output(data, title="Color Page — Power Window Rectangle")
    success("DaVinci Resolve rectangular Linear Power Window written to DB.")


@page_app.command("power-window-polygon")
@handle_errors
def page_power_window_polygon(
    clip_name: Optional[str] = typer.Argument(None, help="Clip name"),
    node_index: int = typer.Option(1, "--node-index", "--node", help="1-based Color Page node index; create/use an empty local node for secondaries"),
    points: Optional[str] = typer.Option(
        None,
        "--points",
        help="Polygon Power Window points as normalized 'x,y;x,y;x,y' pairs",
    ),
):
    """Create/update a native Color Page Polygon Power Window via DB readback."""
    from ..core import color_page_db

    clip_name = _option_value(clip_name)
    node_index = int(_option_value(node_index) or 1)
    points = _option_value(points)
    parsed_points = color_page_db.parse_power_window_points_spec(points) if points is not None else None

    set_execution_engine("db_workaround", 0.75)
    set_capability_context("color.page_power_window_polygon", "supported")

    if node_index < 1:
        raise ValidationError(
            "Color Page power-window-polygon --node must be a positive integer.",
            details={"node_index": node_index, "minimum": 1},
            recoverability="not_applicable",
        )
    enforce_mutation_policy(
        "color.page_power_window_polygon",
        intended_engine="db_workaround",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        dry_run_message("Would create/update a native Color Page Polygon Power Window via DB")
        return

    conn = get_connection(require_timeline=True)
    data = color_page_db.write_polygon_power_window(
        conn,
        clip_name=clip_name,
        node_index=node_index,
        points=parsed_points,
    )
    output(data, title="Color Page — Power Window Polygon")
    success("Color Page Polygon Power Window written to DB.")


@page_app.command("power-window-curve")
@handle_errors
def page_power_window_curve(
    clip_name: Optional[str] = typer.Argument(None, help="Clip name"),
    node_index: int = typer.Option(1, "--node-index", "--node", help="1-based Color Page node index; create/use an empty local node for secondaries"),
    points: Optional[str] = typer.Option(
        None,
        "--points",
        help="Closed Curve Power Window points as normalized 'x,y;x,y;x,y' pairs",
    ),
):
    """Create/update a native Color Page Curve Power Window via DB readback."""
    from ..core import color_page_db

    clip_name = _option_value(clip_name)
    node_index = int(_option_value(node_index) or 1)
    points = _option_value(points)
    parsed_points = color_page_db.parse_power_window_points_spec(points) if points is not None else None

    set_execution_engine("db_workaround", 0.75)
    set_capability_context("color.page_power_window_curve", "supported")

    if node_index < 1:
        raise ValidationError(
            "Color Page power-window-curve --node must be a positive integer.",
            details={"node_index": node_index, "minimum": 1},
            recoverability="not_applicable",
        )
    enforce_mutation_policy(
        "color.page_power_window_curve",
        intended_engine="db_workaround",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        dry_run_message("Would create/update a native Color Page Curve Power Window via DB")
        return

    conn = get_connection(require_timeline=True)
    data = color_page_db.write_curve_power_window(
        conn,
        clip_name=clip_name,
        node_index=node_index,
        points=parsed_points,
    )
    output(data, title="Color Page — Power Window Curve")
    success("Color Page Curve Power Window written to DB.")


@page_app.command("param-delete")
@handle_errors
def page_param_delete(
    clip_name: Optional[str] = typer.Argument(None, help="Clip name"),
    param: list[str] = typer.Option(..., "--param", help="Color Page param name to delete; repeatable"),
):
    """Delete explicit Color Page DB params so DaVinci Resolve falls back to defaults."""
    from ..core import color_page_db

    enforce_mutation_policy(
        "color.page_param_delete",
        intended_engine="db_workaround",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        dry_run_message("Would delete explicit Color Page params from DB")
        return

    conn = get_connection(require_timeline=True)
    data = color_page_db.delete_color_params(conn, clip_name=clip_name, param_names=param)
    _tag_db_workaround_route(data, "db_workaround_color_page_param_delete")
    output(data, title="Color Page — Param Delete")
    success("Color Page params deleted from DB.")


@page_app.command("snapshot")
@handle_errors
def page_snapshot(
    db_path: Optional[str] = typer.Argument(None, help="Path to Project.db (auto-detected if omitted)"),
    clip_name: Optional[str] = typer.Option(None, "--clip", help="Filter by clip name"),
):
    """Snapshot all color grade data from a Project.db for analysis."""
    from ..core import color_page_db

    set_execution_engine("db_workaround", 0.75)
    set_capability_context("color.page_wheel_set", "supported")
    normalized_clip = None
    if clip_name is not None:
        normalized_clip = clip_name.strip()
        if not normalized_clip:
            raise ValidationError(
                "--clip must not be empty.",
                details={"clip": clip_name},
                recoverability="not_applicable",
            )

    if db_path is None:
        conn = get_connection(require_timeline=True)
        db_path = _resolve_project_db_path(conn)
    else:
        db_path = db_path.strip()
        if not db_path:
            raise ValidationError(
                "Project.db path must not be empty.",
                details={"db_path": db_path},
                recoverability="not_applicable",
            )

    db_path = _validate_project_db_path(db_path)

    data = color_page_db.snapshot_color_data(db_path, clip_name=normalized_clip)
    if normalized_clip is not None and not data.get("clips"):
        raise ClipNotFound(f"Clip '{normalized_clip}' not found in Project.db snapshot.")
    output(data, title="Color Page — DB Snapshot")


def _validate_project_db_path(db_path: str) -> str:
    path = Path(db_path).expanduser()
    if not path.exists():
        raise ValidationError(
            "Project.db path does not exist.",
            details={"db_path": str(path)},
            recoverability="not_applicable",
        )
    if not path.is_file():
        raise ValidationError(
            "Project.db path must be a file.",
            details={"db_path": str(path)},
            recoverability="not_applicable",
        )

    required_tables = {"Sm2TiItem", "ListMgt::LmVersion"}
    try:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            rows = connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name IN (?, ?)",
                tuple(required_tables),
            ).fetchall()
        finally:
            connection.close()
    except sqlite3.Error as exc:
        raise ValidationError(
            "Project.db path is not a readable SQLite database.",
            details={"db_path": str(path), "sqlite_error": str(exc)},
            recoverability="not_applicable",
        ) from exc

    found_tables = {row[0] for row in rows}
    missing_tables = sorted(required_tables - found_tables)
    if missing_tables:
        raise ValidationError(
            "Project.db is missing required DaVinci Resolve color tables.",
            details={"db_path": str(path), "missing_tables": missing_tables},
            recoverability="not_applicable",
        )
    return str(path)


def _resolve_project_db_path(conn) -> str:
    """Resolve the Disk project DB path from a live connection."""
    from ..runtime_health import resolve_current_disk_project_db

    details = resolve_current_disk_project_db(conn)
    path = details.get("project_db_path")
    if path:
        return str(path)
    raise APICallFailed("Could not determine project DB path.")

@page_app.command("resolvefx-list")
@handle_errors
def page_resolvefx_list(
    category: Optional[str] = typer.Option(None, "--category", help="Filter by ResolveFX category substring"),
):
    """List installed native ResolveFX plugins from the live Fusion registry."""
    from ..core import resolvefx_db

    set_execution_engine("api_native")
    set_capability_context("color.page_resolvefx_list", "supported")
    conn = get_connection(require_project=False)
    rows = resolvefx_db.list_resolvefx_registry(conn)
    if category:
        needle = str(category).strip().casefold()
        rows = [row for row in rows if needle in row["category"].casefold()]
    output(
        rows,
        columns=[("name", "Name"), ("category", "Category"), ("plugin_id", "Plugin Id")],
        title="ResolveFX Plugins",
    )


@page_app.command("resolvefx-param-discover")
@handle_errors
def page_resolvefx_param_discover(
    fx: str = typer.Option(..., "--fx", help="ResolveFX name or plugin id to inspect through a temporary Fusion comp"),
):
    """Discover live ResolveFX OFX input descriptors for one installed effect."""
    from ..core import resolvefx_db

    fx = str(_option_value(fx) or "").strip()
    if not fx:
        raise ValidationError(
            "ResolveFX effect name must not be empty.",
            recoverability="not_applicable",
        )
    set_execution_engine("api_native", 0.85)
    set_capability_context("color.page_resolvefx_param_discover", "supported")
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        dry_run_message(f"Would discover ResolveFX input descriptors for '{fx}' through Fusion.GetInputList()")
        return
    conn = get_connection(require_project=False)
    data = resolvefx_db.discover_resolvefx_params(conn, fx)
    set_verification_status("partial")
    set_recoverability("manual")
    output(data, title="Color Page — ResolveFX Param Discover")
    success("ResolveFX input descriptors discovered; parameter writes still require render proof.")


@page_app.command("resolvefx-add")
@handle_errors
def page_resolvefx_add(
    clip_name: Optional[str] = typer.Argument(None, help="Clip name"),
    node_index: int = typer.Option(1, "--node-index", "--node", help="1-based Color Page node index to receive the ResolveFX OFX tool"),
    fx: str = typer.Option(..., "--fx", help="ResolveFX name or plugin id (e.g. vignette, box-blur, com.blackmagicdesign.resolvefx.glow)"),
):
    """Add a native ResolveFX to a clip Color Page node via verified Project.db route."""
    from ..core import resolvefx_db

    clip_name = _option_value(clip_name)
    node_index = int(_option_value(node_index, 1) or 1)
    if node_index < 1:
        raise ValidationError(
            "Color Page node index must be a positive integer.",
            details={"node_index": node_index, "minimum": 1},
            recoverability="not_applicable",
        )
    set_execution_engine("db_workaround", 0.85)
    set_capability_context("color.page_resolvefx_add", "supported")
    enforce_mutation_policy(
        "color.page_resolvefx_add",
        intended_engine="db_workaround",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        plugin_id = resolvefx_db.normalize_resolvefx_plugin_id(fx)
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        dry_run_message(f"Would insert native ResolveFX '{plugin_id}' on Color Page node {node_index} via DB")
        return
    conn = get_connection(require_timeline=True)
    timeline_ops.require_sdk_color_mutation_guard(conn)
    plugin_resolution = resolvefx_db.resolve_resolvefx_plugin_id(conn, fx)
    plugin_id = plugin_resolution["plugin_id"]
    render_proof = _begin_color_render_proof(
        conn,
        clip_name=clip_name,
        route="db_workaround_color_page_resolvefx_add",
    )
    data = resolvefx_db.write_resolvefx_tool(conn, clip_name=clip_name, node_index=node_index, plugin=plugin_id)
    data["plugin_resolution"] = plugin_resolution
    conn_after = get_connection(require_timeline=True)
    try:
        data["render_proof"] = _complete_color_render_proof(
            conn_after,
            render_proof,
            partial_result=data,
        )
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
    data.setdefault("verification", {})
    data["verification"]["status"] = "verified"
    data["verification"]["render_proof_status"] = data["render_proof"]["status"]
    data["verification"]["render_proof_route"] = data["render_proof"]["route"]
    data["verification"]["render_proof_required"] = True
    set_verification_status("verified")
    set_recoverability("not_applicable")
    output(data, title="Color Page — ResolveFX Add")
    success("Native ResolveFX inserted on the requested grade node via DB.")


@page_app.command("resolvefx-param-set")
@handle_errors
def page_resolvefx_param_set(
    clip_name: Optional[str] = typer.Argument(None, help="Clip name"),
    node_index: int = typer.Option(1, "--node-index", "--node", help="1-based Color Page node index containing the ResolveFX OFX tool"),
    param: str = typer.Option(..., "--param", help="ResolveFX OFX option name; Box Blur accepts 'strength' alias for HStrength"),
    value: str = typer.Option(..., "--value", help="Parameter value"),
    value_type: str = typer.Option("double", "--type", help="Value type: auto, double, int, bool, or string"),
    fx: Optional[str] = typer.Option(None, "--fx", help="Optional current ResolveFX name/plugin id guard"),
    require_render_proof: bool = typer.Option(True, "--require-render-proof/--setup-only", help="Export before/after Color Page frames and fail unless rendered pixels change"),
):
    """Set a native ResolveFX OFX option on a clip Color Page node."""
    from ..core import resolvefx_db

    clip_name = _option_value(clip_name)
    node_index = int(_option_value(node_index, 1) or 1)
    if node_index < 1:
        raise ValidationError(
            "Color Page node index must be a positive integer.",
            details={"node_index": node_index, "minimum": 1},
            recoverability="not_applicable",
        )
    param = str(_option_value(param) or "").strip()
    value = str(_option_value(value) or "")
    value_type = str(_option_value(value_type) or "double").strip().lower()
    fx = _option_value(fx)
    set_execution_engine("db_workaround", 0.85)
    set_capability_context("color.page_resolvefx_param_set", "supported")
    enforce_mutation_policy(
        "color.page_resolvefx_param_set",
        intended_engine="db_workaround",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        proof_note = "with render proof" if bool(_option_value(require_render_proof, True)) else "as setup-only DB readback"
        dry_run_message(f"Would set native ResolveFX option '{param}' to '{value}' via DB {proof_note}")
        return
    conn = get_connection(require_timeline=True)
    plugin_resolution = resolvefx_db.resolve_resolvefx_plugin_id(conn, fx) if fx else None
    plugin_id = plugin_resolution["plugin_id"] if plugin_resolution else None
    render_proof = None
    if bool(_option_value(require_render_proof, True)):
        render_proof = _begin_color_render_proof(
            conn,
            clip_name=clip_name,
            route="db_workaround_color_page_resolvefx_param_set",
        )
    data = resolvefx_db.write_resolvefx_param(
        conn,
        clip_name=clip_name,
        node_index=node_index,
        param_name=param,
        value=value,
        value_type=value_type,
        plugin=plugin_id,
    )
    if plugin_resolution is not None:
        data["plugin_resolution"] = plugin_resolution
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
        data["verification"]["status"] = "readback_only"
        data["verification"]["render_proof_status"] = "not_requested"
        data["verification"]["render_proof_required"] = True
        data["verification"]["required_next_proof"] = (
            "Rerun without --setup-only before claiming this ResolveFX parameter is visually applied."
        )
        data["render_proof"] = {
            "status": "not_requested",
            "required": True,
            "required_next_proof": data["verification"]["required_next_proof"],
        }
        set_verification_status("partial")
        set_recoverability("manual")
    output(data, title="Color Page — ResolveFX Param Set")
    success("Native ResolveFX option written to the requested grade node via DB.")


@page_app.command("resolvefx-param-list")
@handle_errors
def page_resolvefx_param_list(
    clip_name: Optional[str] = typer.Argument(None, help="Clip name"),
    node_index: int = typer.Option(1, "--node-index", "--node", help="1-based Color Page node index containing the ResolveFX OFX tool"),
    fx: Optional[str] = typer.Option(None, "--fx", help="Optional current ResolveFX name/plugin id guard"),
):
    """List decoded native ResolveFX OFX options on a clip Color Page node."""
    from ..core import resolvefx_db

    clip_name = _option_value(clip_name)
    node_index = int(_option_value(node_index, 1) or 1)
    if node_index < 1:
        raise ValidationError(
            "Color Page node index must be a positive integer.",
            details={"node_index": node_index, "minimum": 1},
            recoverability="not_applicable",
        )
    fx = _option_value(fx)
    set_execution_engine("db_direct", 0.8)
    set_capability_context("color.page_resolvefx_param_list", "supported")
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        dry_run_message("Would read decoded native ResolveFX option payloads from the active grade version")
        return
    conn = get_connection(require_timeline=True)
    plugin_resolution = resolvefx_db.resolve_resolvefx_plugin_id(conn, fx) if fx else None
    plugin_id = plugin_resolution["plugin_id"] if plugin_resolution else None
    data = resolvefx_db.read_resolvefx_params(conn, clip_name=clip_name, node_index=node_index, plugin=plugin_id)
    if plugin_resolution is not None:
        data["plugin_resolution"] = plugin_resolution
    set_verification_status("partial")
    set_recoverability("manual")
    output(data, title="Color Page — ResolveFX Param List")
    success("Native ResolveFX option payloads listed from the active Color Page grade version.")


@page_app.command("resolvefx-remove")
@handle_errors
def page_resolvefx_remove(
    clip_name: Optional[str] = typer.Argument(None, help="Clip name"),
    node_index: int = typer.Option(1, "--node-index", "--node", help="1-based Color Page node index containing the ResolveFX OFX tool"),
):
    """Remove the native ResolveFX from a clip Color Page node via verified Project.db route."""
    from ..core import resolvefx_db

    clip_name = _option_value(clip_name)
    node_index = int(_option_value(node_index, 1) or 1)
    if node_index < 1:
        raise ValidationError(
            "Color Page node index must be a positive integer.",
            details={"node_index": node_index, "minimum": 1},
            recoverability="not_applicable",
        )
    set_execution_engine("db_workaround", 0.85)
    set_capability_context("color.page_resolvefx_remove", "supported")
    enforce_mutation_policy(
        "color.page_resolvefx_remove",
        intended_engine="db_workaround",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        dry_run_message(f"Would remove the native ResolveFX from Color Page node {node_index} via DB")
        return
    conn = get_connection(require_timeline=True)
    data = resolvefx_db.write_resolvefx_tool(conn, clip_name=clip_name, node_index=node_index, plugin=None, remove=True)
    if isinstance(data.get("verification"), dict) and data["verification"].get("status") == "verified":
        set_verification_status("verified")
        set_recoverability("not_applicable")
    output(data, title="Color Page — ResolveFX Remove")
    success("Native ResolveFX removed from the requested grade node via DB.")
