from __future__ import annotations

import math
import time


def _option_value(value, default=None):
    if value.__class__.__name__ in {"OptionInfo", "ArgumentInfo"}:
        return default
    return value


def _tag_db_workaround_route(data, route: str):
    if isinstance(data, dict):
        data["db_session_route"] = data.get("route")
        data["route"] = route
    return data


def _unsupported_color_page_preview(capability_id: str, route: str, payload: dict, title: str) -> None:
    feature = get_capabilities().get("feature_graph", {}).get(capability_id, {})
    caveats = feature.get("caveats") if isinstance(feature.get("caveats"), dict) else {}
    status = str(feature.get("status") or "unsupported")
    diagnostic = {
        "route": route,
        "available": False,
        "would_mutate": False,
        "capability_id": capability_id,
        "capability_status": status,
        **payload,
        "verification": {
            "status": "not_available",
            "source": "capability_graph",
        },
        "caveats": caveats,
    }

    set_capability_context(capability_id, status)
    if status == "supported":
        resolved_engine = feature.get("engine")
        if resolved_engine:
            set_execution_engine(str(resolved_engine))
    else:
        set_execution_engine("not_available", 0.0)
    set_verification_status("not_available")
    set_recoverability("manual")
    if is_dry_run():
        output(diagnostic, title=title)
        return

    raise CapabilityNegotiationFailed(
        "Color Page command is not production-verified.",
        details=diagnostic,
    )


def _validate_finishing_float(value, *, option_name: str, minimum: float, maximum: float) -> float:
    value = _option_value(value)
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(
            f"Color Page finishing {option_name} must be a number.",
            details={option_name.lstrip("-").replace("-", "_"): value},
            recoverability="not_applicable",
        ) from exc
    if numeric < minimum or numeric > maximum:
        raise ValidationError(
            f"Color Page finishing {option_name} must be between {minimum:g} and {maximum:g}.",
            details={option_name.lstrip("-").replace("-", "_"): numeric, "minimum": minimum, "maximum": maximum},
            recoverability="not_applicable",
        )
    return numeric


def _apply_color_page_finishing_fx(
    *,
    capability_id: str,
    route: str,
    effect_name: str,
    clip_name,
    params: dict,
    title: str,
):
    normalized_clip = _option_value(clip_name)
    if normalized_clip is not None:
        normalized_clip = str(normalized_clip).strip()
        if not normalized_clip:
            raise ValidationError(
                "Color Page finishing clip name must not be empty.",
                details={"clip": clip_name},
                recoverability="not_applicable",
            )

    set_execution_engine("workaround_setting", 0.75)
    set_capability_context(capability_id, "supported")
    enforce_mutation_policy(capability_id, intended_engine="workaround_setting", mutating=not is_dry_run())
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            {
                "route": route,
                "clip": normalized_clip,
                "effect": effect_name,
                "params": params,
                "would_apply_fusion_builtin": True,
                "applied": False,
                "verified": False,
                "required_page": "color",
            },
            title=f"{title} Preview",
        )
        return

    conn = get_connection(require_timeline=True)
    data = fx_template_ops.add_fx_via_template(
        conn,
        effect_name,
        clip_name=normalized_clip,
        params=params,
        verify=True,
    )
    if isinstance(data, dict):
        data["route"] = route
        data["clip"] = normalized_clip
        data["required_page"] = "color"
        data["verified_route"] = "fusion_builtin_inline"
    output(data, title=title)


@page_app.command("magic-mask")
@handle_errors
def page_magic_mask(
    clip_name: Optional[str] = typer.Argument(None, help="Clip name; defaults to current Color page clip"),
    direction: str = typer.Option(
        "bi",
        "--direction",
        "--mode",
        help="Native API direction probe: f, b, or bi. The draw-stroke workflow uses --mask-type person or object.",
    ),
    regenerate: bool = typer.Option(False, "--regenerate", help="Regenerate an existing Magic Mask"),
):
    """Report Color Page Magic Mask GUI-assisted workflow availability."""
    set_execution_engine("resolve_gui")
    set_capability_context("color.page_magic_mask", "supported")
    normalized_clip = _option_value(clip_name)
    if normalized_clip is not None:
        normalized_clip = str(normalized_clip).strip()
        if not normalized_clip:
            raise ValidationError(
                "Color Page magic-mask clip name must not be empty.",
                details={"clip": clip_name},
                recoverability="not_applicable",
            )
    normalized_direction = str(_option_value(direction, "bi") or "bi").strip().upper()
    if normalized_direction not in {"F", "B", "BI"}:
        raise ValidationError(
            "Color Page magic-mask direction must be one of f, b, or bi.",
            details={"direction": direction, "allowed": ["f", "b", "bi"]},
            recoverability="not_applicable",
        )

    policy = enforce_mutation_policy("color.page_magic_mask", intended_engine="resolve_gui", mutating=False)
    set_verification_status("not_requested")
    set_recoverability("manual")
    output(
        {
            "route": "color.page_magic_mask_gui",
            "available": True,
            "would_mutate": False,
            "clip": normalized_clip,
            "direction": normalized_direction,
            "regenerate": bool(regenerate),
            "workflow_command": "color page magic-mask-draw-stroke",
            "workflow_mode_options": ["person", "object"],
            "requires_stroke": True,
            "requires_proof": True,
            "track_supported": True,
            "native_methods_rejected": ["CreateMagicMask", "RegenerateMagicMask"],
            "policy": policy,
        },
        title="Color Page Magic Mask Availability",
    )


@page_app.command("magic-mask-draw-stroke")
@handle_errors
def page_magic_mask_draw_stroke(
    clip_name: str = typer.Argument(..., help="Clip name to target on the Color page"),
    mask_type: str = typer.Option(
        "person",
        "--mask-type",
        "--mode",
        help="Magic Mask target type: person or object.",
    ),
    stroke: str = typer.Option(..., "--stroke", help="Normalized frame stroke: x,y;x,y;..."),
    track: bool = typer.Option(False, "--track", help="Run Magic Mask tracking after drawing the stroke"),
):
    """Draw a DaVinci Resolve Color Page Magic Mask stroke through the internal GUI-assisted workflow."""
    from ..core import magic_mask_gui_route

    normalized_clip = magic_mask_gui_route.validate_clip_target(clip_name)
    normalized_mask_type = magic_mask_gui_route.normalize_magic_mask_mode(mask_type)
    stroke_points = magic_mask_gui_route.parse_normalized_stroke(stroke)
    policy = enforce_mutation_policy("color.page_magic_mask", intended_engine="resolve_gui", mutating=not is_dry_run())
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            {
                "message": f"DRY-RUN: Would draw a {normalized_mask_type} Magic Mask stroke on '{normalized_clip}'.",
                "route": magic_mask_gui_route.ROUTE,
                "clip": normalized_clip,
                "mode": normalized_mask_type,
                "stroke": {"points_normalized": [[x, y] for x, y in stroke_points]},
                "track_requested": bool(track),
                "proof_required": True,
                "policy": policy,
            },
            title="Color Page Magic Mask Draw Stroke",
        )
        return

    conn = get_connection(require_timeline=True)

    def _export_proof(path: Path) -> dict:
        metadata = _export_color_page_frame_as_still(conn, resolved_path=path, requested_output_path=str(path))
        return {"export_path": str(path), **metadata}

    data = magic_mask_gui_route.run_magic_mask_draw_stroke(
        conn,
        clip_name=normalized_clip,
        mode=normalized_mask_type,
        stroke_points=stroke_points,
        track_requested=bool(track),
        proof_exporter=_export_proof,
    )
    output(data, title="Color Page Magic Mask Draw Stroke")


@page_app.command("cat-set")
@handle_errors
def page_cat_set(
    clip_name: Optional[str] = typer.Argument(None, help="Clip name; defaults to current Color page clip"),
    method: str = typer.Option("CAT02", "--method", help="Requested CAT method, for example CAT02"),
    source_illuminant: str = typer.Option("D65", "--source-illuminant", help="Requested source illuminant"),
    target_illuminant: str = typer.Option("D55", "--target-illuminant", help="Requested target illuminant"),
):
    """Apply native Chromatic Adaptation Transform controls through a Fusion CAT tool."""
    normalized_clip = _option_value(clip_name)
    if normalized_clip is not None:
        normalized_clip = str(normalized_clip).strip()
        if not normalized_clip:
            raise ValidationError(
                "Color Page CAT clip name must not be empty.",
                details={"clip": clip_name},
                recoverability="not_applicable",
            )
    normalized_method = str(_option_value(method, "CAT02") or "CAT02").strip()
    normalized_source = str(_option_value(source_illuminant, "D65") or "D65").strip()
    normalized_target = str(_option_value(target_illuminant, "D55") or "D55").strip()

    set_execution_engine("fusion_native", 0.85)
    set_capability_context("color.page_cat_set", "supported")
    enforce_mutation_policy("color.page_cat_set", intended_engine="fusion_native", mutating=not is_dry_run())
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            {
                "action": "color.page.cat_set",
                "route": "fusion_native_chromatic_adaptation",
                "clip": normalized_clip,
                "method": normalized_method,
                "source_illuminant": normalized_source,
                "target_illuminant": normalized_target,
                "would_apply_fusion_cat": True,
                "applied": False,
                "verified": False,
                "required_page": "color",
            },
            title="Color Page CAT Set Preview",
        )
        return

    conn = get_connection(require_timeline=True)
    data = color_ops.set_chromatic_adaptation(
        conn,
        normalized_clip,
        method=normalized_method,
        source_illuminant=normalized_source,
        target_illuminant=normalized_target,
    )
    data["required_page"] = "color"
    data["verified_route"] = "fusion_chromatic_adaptation_tool_readback"
    set_verification_status("verified")
    set_recoverability("retryable")
    output(data, title="Color Page CAT Set")


@page_app.command("scope-set")
@handle_errors
def page_scope_set(
    mode: str = typer.Option("parade", "--mode", help="Requested GUI scope mode"),
    y_rgb: str = typer.Option("rgb", "--y-rgb", help="Requested Y/RGB scope channel mode"),
    colorize: bool = typer.Option(False, "--colorize", help="Requested GUI scope colorize toggle"),
    skin_tone_indicator: bool = typer.Option(False, "--skin-tone-indicator", help="Requested vectorscope skin-tone indicator"),
    zoom: str = typer.Option("1x", "--zoom", help="Requested GUI scope zoom"),
):
    """Set native Color Page Scopes panel controls through the GUI route."""
    from ..core import color_scope_gui_route

    normalized_mode = color_scope_gui_route.normalize_scope_mode(str(_option_value(mode, "parade") or "parade"))
    normalized_y_rgb = color_scope_gui_route.normalize_y_rgb(str(_option_value(y_rgb, "rgb") or "rgb"))
    normalized_zoom = color_scope_gui_route.normalize_zoom(str(_option_value(zoom, "1x") or "1x"))
    normalized_colorize = bool(_option_value(colorize, False))
    normalized_skin = bool(_option_value(skin_tone_indicator, False))

    set_execution_engine("resolve_gui", 0.78)
    set_capability_context("color.page_scope_set_gui", "supported")
    enforce_mutation_policy("color.page_scope_set_gui", intended_engine="resolve_gui", mutating=not is_dry_run())
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            {
                "action": "color.page.scope_set",
                "route": color_scope_gui_route.ROUTE,
                "mode": normalized_mode,
                "y_rgb": normalized_y_rgb,
                "colorize": normalized_colorize,
                "skin_tone_indicator": normalized_skin,
                "zoom": normalized_zoom,
                "would_apply_gui": True,
                "applied": False,
                "verified": False,
                "required_page": "color",
            },
            title="Color Page Scope Set Preview",
        )
        return

    conn = get_connection(require_timeline=True)
    data = color_scope_gui_route.run_scope_set(
        conn,
        mode=normalized_mode,
        y_rgb=normalized_y_rgb,
        colorize=normalized_colorize,
        skin_tone_indicator=normalized_skin,
        zoom=normalized_zoom,
    )
    data["required_page"] = "color"
    data["verified_route"] = "native_color_page_scopes_gui_readback"
    output(data, title="Color Page Scope Set")


@page_app.command("color-slice-set")
@handle_errors
def page_color_slice_set(
    clip_name: Optional[str] = typer.Argument(None, help="Clip name; defaults to current Color page clip"),
    vector: str = typer.Option("red", "--vector", help="ColorSlice vector: red, skin, yellow, green, cyan, blue, or magenta"),
    hue: Optional[float] = typer.Option(None, "--hue", help="Requested Color Slice hue"),
    saturation: Optional[float] = typer.Option(None, "--saturation", help="Requested Color Slice saturation adjustment"),
    luma: Optional[float] = typer.Option(None, "--luma", help="Requested Color Slice luma adjustment"),
):
    """Set native Color Page ColorSlice vector controls through the GUI route."""
    from ..core import color_slice_gui_route

    set_execution_engine("resolve_gui", 0.68)
    set_capability_context("color.page_color_slice", "supported")
    normalized_clip = _option_value(clip_name)
    normalized_vector = color_slice_gui_route.normalize_vector(str(_option_value(vector, "red") or "red"))
    normalized_hue = color_slice_gui_route.validate_hue(_option_value(hue))
    normalized_saturation = color_slice_gui_route.validate_saturation(_option_value(saturation))
    normalized_density = color_slice_gui_route.validate_density(_option_value(luma))
    if normalized_hue is None and normalized_saturation is None and normalized_density is None:
        raise ValidationError(
            "ColorSlice set requires at least one of --hue, --saturation, or --luma.",
            details={"hue": hue, "saturation": saturation, "luma": luma},
            recoverability="not_applicable",
        )

    enforce_mutation_policy("color.page_color_slice", intended_engine="resolve_gui", mutating=not is_dry_run())
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            {
                "action": "color.page.color_slice_set",
                "route": color_slice_gui_route.ROUTE,
                "clip": normalized_clip,
                "vector": normalized_vector,
                "requested": {
                    "hue": normalized_hue,
                    "saturation": normalized_saturation,
                    "luma": normalized_density,
                },
                "would_apply_gui": True,
                "applied": False,
                "verified": False,
                "required_page": "color",
            },
            title="Color Page ColorSlice Set Preview",
        )
        return

    conn = get_connection(require_timeline=True)
    data = color_slice_gui_route.run_color_slice_set(
        conn,
        clip_name=normalized_clip,
        vector=normalized_vector,
        hue=normalized_hue,
        saturation=normalized_saturation,
        density=normalized_density,
    )
    data["required_page"] = "color"
    data["verified_route"] = "native_color_page_colorslice_gui_readback"
    output(data, title="Color Page ColorSlice Set")


@page_app.command("auto-color-ai")
@handle_errors
def page_auto_color_ai(
    clip_name: Optional[str] = typer.Argument(None, help="Clip name; defaults to current Color page clip"),
    undo_after_proof: bool = typer.Option(False, "--undo-after-proof/--keep-applied", help="Undo native Auto Color after frame proof verification"),
    proof_dir: Optional[str] = typer.Option(None, "--proof-dir", help="Directory for before/after proof frame exports"),
):
    """Apply DaVinci Resolve's native Color Page Auto Color command."""
    from ..core import color_auto_color_ai_gui_route

    normalized_clip = _option_value(clip_name)
    normalized_undo = bool(_option_value(undo_after_proof, False))
    normalized_proof_dir = _option_value(proof_dir)
    proof_path = Path(str(normalized_proof_dir)).expanduser() if normalized_proof_dir else None

    set_execution_engine("resolve_gui", 0.78)
    set_capability_context("ai_neural.auto_color_ai", "supported")
    enforce_mutation_policy("ai_neural.auto_color_ai", intended_engine="resolve_gui", mutating=not is_dry_run())
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            {
                "action": "color.page.auto_color_ai",
                "route": color_auto_color_ai_gui_route.ROUTE,
                "clip": normalized_clip,
                "would_apply_gui": True,
                "undo_after_proof": normalized_undo,
                "applied": False,
                "verified": False,
                "required_page": "color",
            },
            title="Color Page Auto Color AI Preview",
        )
        return

    conn = get_connection(require_timeline=True)
    driver = color_auto_color_ai_gui_route.MacOSAutoColorAiGuiDriver()
    permissions = driver.preflight_permissions()
    color_auto_color_ai_gui_route.process_ready()
    page_state = color_auto_color_ai_gui_route.ensure_color_page(conn)
    target = color_auto_color_ai_gui_route.verify_current_clip_target(conn, normalized_clip)
    root = color_auto_color_ai_gui_route.proof_root(proof_path)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    before_path = root / f"auto-color-ai-before-{stamp}.png"
    after_path = root / f"auto-color-ai-after-{stamp}.png"
    undo_path = root / f"auto-color-ai-undo-{stamp}.png"

    before_meta = _export_color_page_frame_as_still(conn, resolved_path=before_path, requested_output_path=str(before_path))
    before_rgb = _load_frame_rgb_array(before_path)
    apply_action = driver.click_auto_color()
    color_auto_color_ai_gui_route.wait_for_auto_color()
    conn.refresh()
    after_meta = _export_color_page_frame_as_still(conn, resolved_path=after_path, requested_output_path=str(after_path))
    after_rgb = _load_frame_rgb_array(after_path)
    comparison = _compare_before_after_pixels(before_rgb, after_rgb)
    render_proof = {
        "status": "verified" if int(comparison.get("changed_pixel_count") or 0) > 0 else "failed",
        "route": color_auto_color_ai_gui_route.ROUTE,
        "before": {"path": str(before_path), "visual_check_path": _workspace_relative_path(before_path), "metadata": before_meta},
        "after": {"path": str(after_path), "visual_check_path": _workspace_relative_path(after_path), "metadata": after_meta},
        "comparison": comparison,
    }
    if render_proof["status"] != "verified":
        set_verification_status("failed")
        set_recoverability("manual")
        raise ColorRenderProofFailed(
            "Native DaVinci Resolve Auto Color completed, but exported before/after frames were pixel-identical.",
            details={"reason": "auto_color_ai_no_pixel_change", "render_proof": render_proof},
        )

    undo_action = None
    undo_proof = None
    if normalized_undo:
        undo_action = driver.click_undo()
        color_auto_color_ai_gui_route.wait_for_auto_color(1.5)
        conn.refresh()
        undo_meta = _export_color_page_frame_as_still(conn, resolved_path=undo_path, requested_output_path=str(undo_path))
        undo_rgb = _load_frame_rgb_array(undo_path)
        undo_comparison = _compare_before_after_pixels(before_rgb, undo_rgb)
        undo_proof = {
            "status": "verified" if int(undo_comparison.get("changed_pixel_count") or 0) == 0 else "failed",
            "undo": {"path": str(undo_path), "visual_check_path": _workspace_relative_path(undo_path), "metadata": undo_meta},
            "comparison": undo_comparison,
        }
        if undo_proof["status"] != "verified":
            set_verification_status("failed")
            set_recoverability("manual")
            raise APICallFailed(
                "Native Auto Color undo did not restore the exported frame to the pre-apply state.",
                details={"render_proof": render_proof, "undo_proof": undo_proof},
            )

    color_auto_color_ai_gui_route.mark_verified()
    output(
        {
            "action": "color.page.auto_color_ai",
            "route": color_auto_color_ai_gui_route.ROUTE,
            "target": target,
            "changed": True,
            "undo_after_proof": normalized_undo,
            "apply_action": apply_action,
            "undo_action": undo_action,
            "render_proof": render_proof,
            "undo_proof": undo_proof,
            "preflight": {"permissions": permissions, "page": page_state},
            "required_page": "color",
            "verified_route": "native_color_page_auto_color_menu_frame_diff",
        },
        title="Color Page Auto Color AI",
    )


@page_app.command("warper-set")
@handle_errors
def page_warper_set(
    clip_name: Optional[str] = typer.Argument(None, help="Clip name; defaults to current Color page clip"),
    point: Optional[str] = typer.Option(None, "--point", help="Source Color Warper map coordinate as normalized x,y"),
    to: Optional[str] = typer.Option(None, "--to", help="Target Color Warper map coordinate as normalized x,y"),
):
    """Set a verified single-pin Color Warper Chroma Warp payload via Project.db."""
    from ..core import color_page_db

    def _parse_pair(raw: Optional[str], *, option_name: str) -> tuple[float, float]:
        normalized = _option_value(raw)
        if normalized is None or str(normalized).strip() == "":
            raise ValidationError(
                f"{option_name} is required for Color Warper single-pin DB route.",
                details={option_name.lstrip("-").replace("-", "_"): normalized},
                recoverability="not_applicable",
            )
        parts = [part.strip() for part in str(normalized).split(",")]
        if len(parts) != 2:
            raise ValidationError(
                f"{option_name} must be two comma-separated normalized numbers.",
                details={option_name.lstrip("-").replace("-", "_"): normalized},
                recoverability="not_applicable",
            )
        try:
            x, y = float(parts[0]), float(parts[1])
        except ValueError as exc:
            raise ValidationError(
                f"{option_name} must contain numeric x,y values.",
                details={option_name.lstrip("-").replace("-", "_"): normalized},
                recoverability="not_applicable",
            ) from exc
        color_page_db._validate_warper_coord_pair((x, y), label=option_name.lstrip("-").replace("-", "_"))
        return x, y

    source = _parse_pair(point, option_name="--point")
    target = _parse_pair(to, option_name="--to")
    enforce_mutation_policy("color.page_color_warper", intended_engine="db_workaround")
    set_capability_context("color.page_color_warper", "supported")
    set_execution_engine("db_workaround", 0.82)
    set_verification_status("render_unverified")
    set_recoverability("manual")
    if is_dry_run():
        output(
            {
                "route": "db_workaround_color_page_warper_single_pin",
                "clip": _option_value(clip_name),
                "point": {"x": source[0], "y": source[1]},
                "target": {"x": target[0], "y": target[1]},
                "would_mutate": True,
            },
            title="Color Page Warper Preview",
        )
        return
    conn = get_connection()
    data = color_page_db.write_color_warper_pin(conn, clip_name=clip_name, point=source, target=target)
    set_verification_status("render_unverified")
    output(data, title="Color Page Warper")
    success("Color Page Warper single-pin payload written to DB.")


@page_app.command("ofx-glow-set")
@handle_errors
def page_ofx_glow_set(
    clip_name: Optional[str] = typer.Argument(None, help="Clip name; defaults to current Color page clip"),
    gain: float = typer.Option(0.35, "--gain", help="SoftGlow Gain value, 0..5"),
):
    """Apply a supported Color Page finishing glow through the Fusion SoftGlow workaround route."""
    glow_gain = _validate_finishing_float(gain, option_name="--gain", minimum=0.0, maximum=5.0)
    _apply_color_page_finishing_fx(
        capability_id="color.page_ofx_glow_set",
        route="workaround_color_page_ofx_glow_set",
        effect_name="Glow",
        clip_name=clip_name,
        params={"Gain": glow_gain},
        title="Color Page — OFX Glow Set",
    )


@page_app.command("sharpen-set")
@handle_errors
def page_sharpen_set(
    clip_name: Optional[str] = typer.Argument(None, help="Clip name; defaults to current Color page clip"),
    amount: float = typer.Option(0.35, "--amount", help="UnsharpMask Amount value, 0..5"),
):
    """Apply a supported Color Page finishing sharpen through the Fusion UnsharpMask workaround route."""
    sharpen_amount = _validate_finishing_float(amount, option_name="--amount", minimum=0.0, maximum=5.0)
    _apply_color_page_finishing_fx(
        capability_id="color.page_sharpen_set",
        route="workaround_color_page_sharpen_set",
        effect_name="Sharpen",
        clip_name=clip_name,
        params={"Amount": sharpen_amount},
        title="Color Page — Sharpen Set",
    )


@page_app.command("softening-set")
@handle_errors
def page_softening_set(
    clip_name: Optional[str] = typer.Argument(None, help="Clip name; defaults to current Color page clip"),
    radius: float = typer.Option(2.0, "--radius", help="Blur radius applied to XBlurSize/YBlurSize, 0..100"),
):
    """Apply a supported Color Page finishing softening pass through the Fusion Blur workaround route."""
    blur_radius = _validate_finishing_float(radius, option_name="--radius", minimum=0.0, maximum=100.0)
    _apply_color_page_finishing_fx(
        capability_id="color.page_softening_set",
        route="workaround_color_page_softening_set",
        effect_name="Blur",
        clip_name=clip_name,
        params={"XBlurSize": blur_radius, "YBlurSize": blur_radius},
        title="Color Page — Softening Set",
    )


@page_app.command("curve-spline-set")
@handle_errors
def page_curve_spline_set(
    clip_name: Optional[str] = typer.Argument(None, help="Clip name; defaults to current Color page clip"),
    channel: str = typer.Option("Y", "--channel", help="Requested curve channel: Y, R, G, or B"),
    points: Optional[str] = typer.Option(None, "--points", help="Requested freeform curve points"),
):
    """Set native Color Page Custom Curves control points via the verified DB route."""
    from ..core import color_page_db

    clip_name = _option_value(clip_name)
    normalized_channel = str(_option_value(channel, "Y") or "Y").strip().lower()
    channel_map = {
        "y": "y",
        "master": "y",
        "luma": "y",
        "r": "red",
        "red": "red",
        "g": "green",
        "green": "green",
        "b": "blue",
        "blue": "blue",
    }
    if normalized_channel not in channel_map:
        raise ValidationError(
            "Color Page curve-spline-set --channel must be one of Y, R, G, or B.",
            details={"channel": channel, "allowed": ["Y", "R", "G", "B"]},
            recoverability="not_applicable",
        )
    points = _option_value(points)
    if points is None:
        raise ValidationError(
            "Color Page curve-spline-set requires --points as normalized x,y pairs.",
            details={"format": "0,0;0.5,0.6;1,1"},
            recoverability="not_applicable",
        )

    parsed = color_page_db.parse_curve_points_spec(points)
    set_execution_engine("db_workaround", 0.75)
    set_capability_context("color.page_curve_spline_freeform", "supported")
    enforce_mutation_policy(
        "color.page_curve_spline_freeform",
        intended_engine="db_workaround",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        dry_run_message("Would set Color Page Custom Curves spline points via DB")
        return

    kwargs = {"y": None, "red": None, "green": None, "blue": None}
    kwargs[channel_map[normalized_channel]] = parsed
    conn = get_connection(require_timeline=True)
    data = color_page_db.write_custom_curve_points(conn, clip_name=clip_name, **kwargs)
    data["route"] = "db_workaround_color_page_curve_spline_set"
    data["requested_channel"] = channel
    data["effective_channel"] = channel_map[normalized_channel]
    _mark_color_render_unverified(data, readback_source="project_db_custom_curve_points")
    output(data, title="Color Page — Curve Spline Set")
    success("Color Page Custom Curves spline points written to DB.")


@page_app.command("hue-curve-spline-set")
@handle_errors
def page_hue_curve_spline_set(
    clip_name: Optional[str] = typer.Argument(None, help="Clip name; defaults to current Color page clip"),
    mode: str = typer.Option("hue-vs-hue", "--mode", help="Requested Hue curve mode"),
    points: Optional[str] = typer.Option(None, "--points", help="Requested exact GUI spline points/handles"),
):
    """Set native Color Page Hue curve spline points via the verified DB route."""
    from ..core import color_page_db

    clip_name = _option_value(clip_name)
    normalized_mode = str(_option_value(mode, "hue-vs-hue") or "hue-vs-hue").strip().lower().replace("_", "-")
    points = _option_value(points)
    if points is None:
        raise ValidationError(
            "Color Page hue-curve-spline-set requires --points.",
            details={"format": "input_hue,value;input_hue,value"},
            recoverability="not_applicable",
        )
    parsed_points = color_page_db.parse_hue_curve_points_spec(points, mode=normalized_mode)
    set_execution_engine("db_workaround", 0.75)
    set_capability_context("color.page_hue_curve_gui_spline", "supported")
    enforce_mutation_policy(
        "color.page_hue_curve_gui_spline",
        intended_engine="db_workaround",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        dry_run_message(f"Would set Color Page {normalized_mode} GUI spline points via DB")
        return

    conn = get_connection(require_timeline=True)
    data = color_page_db.write_hue_curve_points(
        conn,
        clip_name=clip_name,
        mode=normalized_mode,
        points=parsed_points,
    )
    data["route"] = "db_workaround_color_page_hue_curve_spline_set"
    data["requested_mode"] = mode
    data["effective_mode"] = normalized_mode
    output(data, title="Color Page — Hue Curve Spline Set")
    success(f"Color Page {normalized_mode} spline points written to DB.")


@page_app.command("sat-curve-spline-set")
@handle_errors
def page_sat_curve_spline_set(
    clip_name: Optional[str] = typer.Argument(None, help="Clip name; defaults to current Color page clip"),
    mode: str = typer.Option("sat-vs-sat", "--mode", help="Requested Sat/Lum curve mode"),
    points: Optional[str] = typer.Option(None, "--points", help="Requested exact GUI spline points/handles"),
):
    """Set native Color Page Sat/Lum curve spline points via the verified DB route."""
    from ..core import color_page_db

    clip_name = _option_value(clip_name)
    normalized_mode = str(_option_value(mode, "sat-vs-sat") or "sat-vs-sat").strip().lower().replace("_", "-")
    points = _option_value(points)
    if points is None:
        raise ValidationError(
            "Color Page sat-curve-spline-set requires --points.",
            details={"format": "input,value;input,value"},
            recoverability="not_applicable",
        )
    parsed_points = color_page_db.parse_sat_curve_points_spec(points, mode=normalized_mode)
    set_execution_engine("db_workaround", 0.75)
    set_capability_context("color.page_sat_curve_gui_spline", "supported")
    enforce_mutation_policy(
        "color.page_sat_curve_gui_spline",
        intended_engine="db_workaround",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        dry_run_message(f"Would set Color Page {normalized_mode} GUI spline points via DB")
        return

    conn = get_connection(require_timeline=True)
    data = color_page_db.write_sat_curve_points(
        conn,
        clip_name=clip_name,
        mode=normalized_mode,
        points=parsed_points,
    )
    data["route"] = "db_workaround_color_page_sat_curve_spline_set"
    data["requested_mode"] = mode
    data["effective_mode"] = normalized_mode
    output(data, title="Color Page — Sat/Lum Curve Spline Set")
    success(f"Color Page {normalized_mode} spline points written to DB.")


@page_app.command("power-window-gradient-transform")
@handle_errors
def page_power_window_gradient_transform(
    clip_name: Optional[str] = typer.Argument(None, help="Clip name; defaults to current Color page clip"),
    angle: Optional[float] = typer.Option(None, "--angle", help="Not yet supported; Gradient angle needs overlay payload fixtures"),
    softness: Optional[float] = typer.Option(None, "--softness", help="Gradient Soft 1 GUI value"),
    x: Optional[float] = typer.Option(None, "--x", help="Gradient Pan GUI value; 50.0 is centered"),
    y: Optional[float] = typer.Option(None, "--y", help="Gradient Tilt GUI value; 50.0 is centered"),
):
    """Set verified Gradient Power Window pan/tilt/Soft 1 controls via DB."""
    from ..core import color_page_db

    clip_name = _option_value(clip_name)
    angle = _option_value(angle)
    softness = _option_value(softness)
    x = _option_value(x)
    y = _option_value(y)
    set_execution_engine("db_workaround", 0.75)
    set_capability_context("color.page_power_window_gradient_transform", "supported")

    if angle is not None:
        raise ValidationError(
            "Gradient Power Window --angle is not verified yet; use --x, --y, and --softness only.",
            details={"angle": angle, "supported": ["--x", "--y", "--softness"]},
            recoverability="manual",
        )

    enforce_mutation_policy(
        "color.page_power_window_gradient_transform",
        intended_engine="db_workaround",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        dry_run_message("Would update verified Gradient Power Window pan/tilt/Soft 1 controls via DB")
        return

    size = None
    if softness is not None:
        size = float(softness) * color_page_db.POWER_WINDOW_GRADIENT_SOFT_1_SCALE
        color_page_db.validate_gradient_power_window_size(size)

    conn = get_connection(require_timeline=True)
    data = color_page_db.write_gradient_power_window(
        conn,
        clip_name=clip_name,
        size=size,
        pan=float(x) if x is not None else None,
        tilt=float(y) if y is not None else None,
    )
    output(data, title="Color Page — Power Window Gradient Transform")
    success("Color Page Gradient Power Window transform written to DB.")


@page_app.command("power-window-circle-detail")
@handle_errors
def page_power_window_circle_detail(
    clip_name: Optional[str] = typer.Argument(None, help="Clip name; defaults to current Color page clip"),
    opacity: Optional[float] = typer.Option(None, "--opacity", help="Circle Power Window GUI Opacity value, 0..100"),
    soft_2: Optional[float] = typer.Option(None, "--soft-2", help="Rejected for Circle: disabled by the DaVinci Resolve GUI fixture"),
    soft_3: Optional[float] = typer.Option(None, "--soft-3", help="Rejected for Circle: disabled by the DaVinci Resolve GUI fixture"),
    soft_4: Optional[float] = typer.Option(None, "--soft-4", help="Rejected for Circle: disabled by the DaVinci Resolve GUI fixture"),
    invert: Optional[bool] = typer.Option(None, "--invert/--no-invert", help="Set the outside/inverted Circle Power Window selection"),
):
    """Set verified Circle Power Window detail controls; reject GUI-disabled fields."""
    from ..core import color_page_db

    clip_name = _option_value(clip_name)
    opacity = _option_value(opacity)
    soft_2 = _option_value(soft_2)
    soft_3 = _option_value(soft_3)
    soft_4 = _option_value(soft_4)
    invert = _option_value(invert)

    set_execution_engine("db_workaround", 0.75)
    set_capability_context("color.page_power_window_circle_detail", "supported")

    requested_disabled = {
        name: value
        for name, value in {"soft_2": soft_2, "soft_3": soft_3, "soft_4": soft_4}.items()
        if value is not None
    }
    if requested_disabled:
        raise ValidationError(
            "DaVinci Resolve disables Circle Power Window Soft 2/3/4 in the verified GUI fixture; use Soft 1 on power-window-circle.",
            details={
                "unsupported": requested_disabled,
                "supported": ["--opacity", "--invert", "--no-invert"],
                "fixture": "manual-fixtures-20260609-circle-detail",
            },
            recoverability="not_applicable",
        )
    if opacity is None and invert is None:
        raise ValidationError(
            "Color Page power-window-circle-detail requires at least one verified option.",
            details={"supported": ["--opacity", "--invert", "--no-invert"]},
            recoverability="not_applicable",
        )
    if opacity is not None and (opacity < 0 or opacity > 100):
        raise ValidationError(
            "Color Page power-window-circle-detail --opacity must be between 0 and 100.",
            details={"opacity": opacity},
            recoverability="not_applicable",
        )

    enforce_mutation_policy(
        "color.page_power_window_circle_detail",
        intended_engine="db_workaround",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        dry_run_message("Would set verified Circle Power Window opacity/invert details via DB")
        return

    conn = get_connection(require_timeline=True)
    data = color_page_db.write_circle_power_window(
        conn,
        clip_name=clip_name,
        opacity=float(opacity) if opacity is not None else None,
        invert=invert,
    )
    data["db_route"] = data.get("route")
    data["route"] = "db_workaround_color_page_power_window_circle_detail"
    data["verified_slices"] = ["opacity"] if opacity is not None else []
    if invert is not None:
        data["verified_slices"].append("invert")
    output(data, title="Color Page — Power Window Circle Detail")
    success("Color Page Circle Power Window detail controls written to DB.")


@page_app.command("power-window-overlay-transform")
@handle_errors
def page_power_window_overlay_transform(
    clip_name: Optional[str] = typer.Argument(None, help="Clip name; defaults to current Color page clip"),
    shape: str = typer.Option("linear", "--shape", help="Verified shape route: linear or rectangle"),
    x: Optional[float] = typer.Option(None, "--x", help="Linear/rectangle internal horizontal offset (-2..2)"),
    y: Optional[float] = typer.Option(None, "--y", help="Linear/rectangle internal vertical offset (-2..2)"),
    width: Optional[float] = typer.Option(None, "--width", help="Linear/rectangle internal width scale (0.05..4)"),
    height: Optional[float] = typer.Option(None, "--height", help="Linear/rectangle internal height scale (0.05..4)"),
    soft_1: Optional[float] = typer.Option(None, "--soft-1", help="Linear/rectangle GUI Soft 1 value (0..62.5)"),
    soft_2: Optional[float] = typer.Option(None, "--soft-2", help="Linear/rectangle GUI Soft 2 value (0..62.5)"),
    soft_3: Optional[float] = typer.Option(None, "--soft-3", help="Linear/rectangle GUI Soft 3 value (0..62.5)"),
    soft_4: Optional[float] = typer.Option(None, "--soft-4", help="Linear/rectangle GUI Soft 4 value (0..62.5)"),
    opacity: Optional[float] = typer.Option(None, "--opacity", help="Linear/rectangle GUI Opacity value (0..100)"),
    rotate: Optional[float] = typer.Option(None, "--rotate", help="Rejected: viewer overlay rotation is not verified"),
    feather: Optional[float] = typer.Option(None, "--feather", help="Rejected: viewer overlay feather drag is not verified"),
):
    """Set fixture-backed Power Window overlay geometry by explicit values."""
    from ..core import color_page_db

    clip_name = _option_value(clip_name)
    shape = str(_option_value(shape, "linear") or "linear").strip().lower()
    x = _option_value(x)
    y = _option_value(y)
    width = _option_value(width)
    height = _option_value(height)
    soft_1 = _option_value(soft_1)
    soft_2 = _option_value(soft_2)
    soft_3 = _option_value(soft_3)
    soft_4 = _option_value(soft_4)
    opacity = _option_value(opacity)
    rotate = _option_value(rotate)
    feather = _option_value(feather)

    set_execution_engine("db_workaround", 0.75)
    set_capability_context("color.page_power_window_overlay_transform", "supported")

    unsupported = {}
    if rotate is not None:
        unsupported["rotate"] = rotate
    if feather is not None:
        unsupported["feather"] = feather
    if unsupported:
        raise ValidationError(
            "Viewer overlay rotate/feather drags are not production-verified; use explicit x/y/width/height/softness/opacity values.",
            details={
                "unsupported": unsupported,
                "supported": ["--shape linear", "--shape rectangle", "--x", "--y", "--width", "--height", "--soft-1", "--soft-2", "--soft-3", "--soft-4", "--opacity"],
                "fixture": "manual-fixtures-20260610-power-window-overlay",
            },
            recoverability="not_applicable",
        )
    if shape not in {"linear", "rectangle"}:
        raise ValidationError(
            "Color Page power-window-overlay-transform --shape must be linear or rectangle for the verified DB route.",
            details={"shape": shape, "allowed": ["linear", "rectangle"]},
            recoverability="not_applicable",
        )
    updates = {
        "x": x,
        "y": y,
        "width": width,
        "height": height,
        "soft_1": soft_1,
        "soft_2": soft_2,
        "soft_3": soft_3,
        "soft_4": soft_4,
        "opacity": opacity,
    }
    if all(value is None for value in updates.values()):
        raise ValidationError(
            "Color Page power-window-overlay-transform requires at least one explicit verified value.",
            details={"supported": list(updates.keys())},
            recoverability="not_applicable",
        )
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

    enforce_mutation_policy(
        "color.page_power_window_overlay_transform",
        intended_engine="db_workaround",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        dry_run_message("Would set verified Power Window overlay geometry values via DB")
        return

    conn = get_connection(require_timeline=True)
    data = color_page_db.write_linear_power_window(
        conn,
        clip_name=clip_name,
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
    data["route"] = "db_workaround_color_page_power_window_overlay_transform"
    data["native_shape"] = "linear"
    data["requested_shape"] = shape
    data["verified_slices"] = [name for name, value in updates.items() if value is not None]
    output(data, title="Color Page — Power Window Overlay Transform")
    success("Color Page Power Window overlay transform values written to DB.")


@page_app.command("power-window-track")
@handle_errors
def page_power_window_track(
    clip_name: Optional[str] = typer.Argument(None, help="Clip name; defaults to current Color page clip"),
    shape: str = typer.Option("circle", "--shape", help="Requested native Power Window shape to track"),
    direction: str = typer.Option("forward", "--direction", help="Requested tracker direction"),
    wait_seconds: float = typer.Option(2.0, "--wait-seconds", help="Seconds to wait before saving and verifying tracker readback"),
):
    """Run native Color Page Power Window tracking through the workflow-owned GUI route."""
    from ..core import power_window_track_gui_route

    set_execution_engine("resolve_gui", 0.65)
    set_capability_context("color.page_power_window_track", "supported")
    normalized_clip = _option_value(clip_name)
    if normalized_clip is not None:
        normalized_clip = str(normalized_clip).strip()
        if not normalized_clip:
            raise ValidationError(
                "Color Page Power Window tracker clip name must not be empty.",
                details={"clip": clip_name},
                recoverability="not_applicable",
            )
    normalized_shape = power_window_track_gui_route.normalize_shape(str(_option_value(shape, "circle") or "circle"))
    normalized_direction = power_window_track_gui_route.normalize_direction(str(_option_value(direction, "forward") or "forward"))
    normalized_wait = power_window_track_gui_route.validate_wait_seconds(_option_value(wait_seconds, 2.0))

    enforce_mutation_policy("color.page_power_window_track", intended_engine="resolve_gui", mutating=not is_dry_run())
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            {
                "action": "color.page.power_window_track",
                "route": power_window_track_gui_route.ROUTE,
                "clip": normalized_clip,
                "shape": normalized_shape,
                "direction": normalized_direction,
                "wait_seconds": normalized_wait,
                "would_apply_gui": True,
                "applied": False,
                "verified": False,
                "required_page": "color",
                "requires_tracker_panel": "Tracker - Window",
                "requires_proof": True,
            },
            title="Color Page Power Window Track Preview",
        )
        return

    conn = get_connection(require_timeline=True)
    data = power_window_track_gui_route.run_power_window_track(
        conn,
        clip_name=normalized_clip,
        shape=normalized_shape,
        direction=normalized_direction,
        wait_seconds=normalized_wait,
    )
    data["required_page"] = "color"
    data["verified_route"] = "native_color_page_tracker_gui_readback"
    output(data, title="Color Page Power Window Track")


@page_app.command("power-window-gui-set")
@handle_errors
def page_power_window_gui_set(
    clip_name: Optional[str] = typer.Argument(None, help="Clip name; defaults to current Color page clip"),
    shape: str = typer.Option("linear", "--shape", help="Power Window shape button to create/select"),
    size: Optional[float] = typer.Option(None, "--size", help="Window Size GUI value, 0..100"),
    aspect: Optional[float] = typer.Option(None, "--aspect", help="Window Aspect GUI value, 0..100"),
    pan: Optional[float] = typer.Option(None, "--pan", help="Window Pan GUI value, 0..100"),
    tilt: Optional[float] = typer.Option(None, "--tilt", help="Window Tilt GUI value, 0..100"),
    rotate: Optional[float] = typer.Option(None, "--rotate", help="Window Rotate GUI value, -180..180"),
    opacity: Optional[float] = typer.Option(None, "--opacity", help="Window Opacity GUI value, 0..100"),
    soft_1: Optional[float] = typer.Option(None, "--soft-1", help="Window Soft 1 GUI value, 0..100"),
    soft_2: Optional[float] = typer.Option(None, "--soft-2", help="Window Soft 2 GUI value, 0..100"),
    soft_3: Optional[float] = typer.Option(None, "--soft-3", help="Window Soft 3 GUI value, 0..100"),
    soft_4: Optional[float] = typer.Option(None, "--soft-4", help="Window Soft 4 GUI value, 0..100"),
    inside: Optional[float] = typer.Option(None, "--inside", help="Window Inside GUI value, 0..100"),
    outside: Optional[float] = typer.Option(None, "--outside", help="Window Outside GUI value, 0..100"),
    invert: Optional[bool] = typer.Option(None, "--invert/--no-invert", help="Requested invert toggle; currently fails unless a verified GUI control is found"),
    expected_node_index: Optional[int] = typer.Option(None, "--expected-node-index", "--expect-node", help="Fail unless this node reads back with Power Windows"),
):
    """Create/select and transform a native Color Page Power Window through the workflow-owned GUI route."""
    from ..core import color_page_gui_route

    clip_name = color_page_gui_route.normalize_optional_clip(_option_value(clip_name))
    request = color_page_gui_route.normalize_power_window_gui_controls(
        shape=str(_option_value(shape, "linear") or "linear"),
        size=_option_value(size),
        aspect=_option_value(aspect),
        pan=_option_value(pan),
        tilt=_option_value(tilt),
        rotate=_option_value(rotate),
        opacity=_option_value(opacity),
        soft_1=_option_value(soft_1),
        soft_2=_option_value(soft_2),
        soft_3=_option_value(soft_3),
        soft_4=_option_value(soft_4),
        inside=_option_value(inside),
        outside=_option_value(outside),
    )
    expected_node_index = _option_value(expected_node_index)
    if expected_node_index is not None and int(expected_node_index) < 1:
        raise ValidationError(
            "Color Page Power Window GUI expected node index must be a positive integer.",
            details={"expected_node_index": expected_node_index, "minimum": 1},
            recoverability="not_applicable",
        )
    invert = _option_value(invert)
    if invert is not None:
        set_execution_engine("resolve_gui")
        set_capability_context("color.page_power_window_gui_set", "supported")
        set_verification_status("failed")
        set_recoverability("manual")
        raise CapabilityNegotiationFailed(
            "Color Page Power Window invert is not exposed through the verified GUI route yet.",
            details={
                "route": color_page_gui_route.ROUTE_POWER_WINDOW_GUI_SET,
                "requested_invert": bool(invert),
                "supported_window_controls": sorted(color_page_gui_route.POWER_WINDOW_GUI_CONTROL_RANGES),
                "required_fix": "Add a narrow verified invert control locator with screenshot and render/locality proof before enabling this option.",
            },
            recoverability="manual",
        )

    capability_id = "color.page_power_window_gui_set"
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
                "message": "DRY-RUN: Would create/select and transform a native Color Page Power Window through the GUI-assisted route.",
                "route": color_page_gui_route.ROUTE_POWER_WINDOW_GUI_SET,
                "clip": clip_name,
                "shape": request["shape"],
                "requested_controls": request["controls"],
                "expected_node_index": expected_node_index,
                "would_mutate": True,
                "render_proof": {
                    "status": "not_requested",
                    "reason": "setup_only_power_window_may_not_change_pixels",
                    "required_next_proof": "Apply a visible correction on the same selected node and verify rendered-frame pixel diff plus locality.",
                },
                "policy": policy,
            },
            title="Color Page Power Window GUI Set Preview",
        )
        return

    conn = get_connection(require_timeline=True)
    try:
        data = color_page_gui_route.run_power_window_gui_set(
            conn,
            clip_name=clip_name,
            shape=request["shape"],
            controls=request["controls"],
            expected_node_index=int(expected_node_index) if expected_node_index is not None else None,
        )
        data["render_proof"] = {
            "status": "not_requested",
            "reason": "setup_only_power_window_may_not_change_pixels",
            "required_next_proof": data["verification"]["required_next_proof"],
        }
        set_verification_status("pending_manual")
        set_recoverability("manual")
    except CLIError:
        set_verification_status("failed")
        raise
    output(data, title="Color Page Power Window GUI Set")

@page_app.command("qualifier-panel-probe")
@handle_errors
def page_qualifier_panel_probe(
    clip_name: Optional[str] = typer.Argument(None, help="Clip name; defaults to current Color page clip"),
):
    """Inspect native Color Page Qualifier panel controls through the workflow-owned GUI route."""
    from ..core import color_page_gui_route

    normalized_clip = color_page_gui_route.normalize_optional_clip(_option_value(clip_name))
    policy = enforce_mutation_policy(
        "color.page_qualifier_panel_probe",
        intended_engine="resolve_gui",
        mutating=False,
    )
    set_execution_engine("resolve_gui")
    set_capability_context("color.page_qualifier_panel_probe", "supported")
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            {
                "message": "DRY-RUN: Would inspect the native Color Page Qualifier panel through the GUI-assisted route.",
                "route": color_page_gui_route.ROUTE_QUALIFIER_PANEL_PROBE,
                "clip": normalized_clip,
                "would_mutate": False,
                "proof_required": True,
                "required_panel": "Color page Qualifier palette",
                "policy": policy,
            },
            title="Color Page Qualifier Panel Probe",
        )
        return

    conn = get_connection(require_timeline=True)
    data = color_page_gui_route.run_qualifier_panel_probe(conn, clip_name=normalized_clip)
    output(data, title="Color Page Qualifier Panel Probe")

@page_app.command("qualifier-gui-hsl-set")
@handle_errors
def page_qualifier_gui_hsl_set(
    clip_name: Optional[str] = typer.Argument(None, help="Clip name; defaults to current Color page clip"),
    hue: Optional[str] = typer.Option(None, "--hue", help="Requested native GUI HSL qualifier hue range"),
    saturation: Optional[str] = typer.Option(None, "--saturation", help="Requested native GUI HSL qualifier saturation range"),
    luma: Optional[str] = typer.Option(None, "--luma", help="Requested native GUI HSL qualifier luma range"),
    softness: Optional[float] = typer.Option(None, "--softness", help="Set Hue/Saturation/Luminance GUI soft controls, 0-1 or 0-100"),
    hue_softness: Optional[float] = typer.Option(None, "--hue-softness", help="Set Hue Soft only, 0-1 or 0-100"),
    saturation_softness: Optional[float] = typer.Option(None, "--saturation-softness", "--sat-softness", help="Set Saturation Low/High Soft, 0-1 or 0-100"),
    luma_softness: Optional[float] = typer.Option(None, "--luma-softness", help="Set Luminance Low/High Soft, 0-1 or 0-100"),
    require_render_proof: bool = typer.Option(
        True,
        "--require-render-proof/--setup-only",
        help=(
            "Require before/after rendered-frame pixel proof. Use --setup-only only inside a larger workflow "
            "that will apply a visible correction and perform final render proof."
        ),
    ),
):
    """Set native Color Page Qualifier HSL controls through a proof-gated GUI route."""
    from ..core import color_page_gui_route

    normalized_clip = color_page_gui_route.normalize_optional_clip(_option_value(clip_name))
    request = color_page_gui_route.normalize_qualifier_gui_hsl_controls(
        hue=_option_value(hue),
        saturation=_option_value(saturation),
        luma=_option_value(luma),
        softness=_option_value(softness),
        hue_softness=_option_value(hue_softness),
        saturation_softness=_option_value(saturation_softness),
        luma_softness=_option_value(luma_softness),
    )
    require_render_proof = bool(_option_value(require_render_proof, True))
    policy = enforce_mutation_policy(
        "color.page_qualifier_gui_hsl_set",
        intended_engine="resolve_gui",
        mutating=not is_dry_run(),
    )
    set_execution_engine("resolve_gui")
    set_capability_context("color.page_qualifier_gui_hsl_set", "supported")
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            {
                "message": "DRY-RUN: Would set native Color Page Qualifier HSL controls through the GUI-assisted route.",
                "route": color_page_gui_route.ROUTE_QUALIFIER_GUI_HSL_SET,
                "clip": normalized_clip,
                "ranges": request["ranges"],
                "requested_controls": request["controls"],
                "required_probe_decision": "ready_for_proof_gated_write",
                "proof_required": True,
                "render_proof_required": bool(require_render_proof),
                "setup_only": not bool(require_render_proof),
                "required_panel": "Color page Qualifier palette with HSL-specific settable controls",
                "policy": policy,
            },
            title="Color Page Qualifier GUI HSL Set Preview",
        )
        return

    conn = get_connection(require_timeline=True)
    driver = color_page_gui_route.MacOSColorPageGuiDriver()
    probe = color_page_gui_route.run_qualifier_panel_probe(conn, clip_name=normalized_clip, driver=driver)
    summary = probe.get("summary") if isinstance(probe.get("summary"), dict) else {}
    decision = summary.get("hsl_write_decision") if isinstance(summary.get("hsl_write_decision"), dict) else {}
    if decision.get("status") != "ready_for_proof_gated_write":
        set_verification_status("failed")
        set_recoverability("manual")
        raise CapabilityNegotiationFailed(
            "Native Color Page Qualifier GUI HSL controls are not exposed safely enough to mutate.",
            details={
                "route": color_page_gui_route.ROUTE_QUALIFIER_GUI_HSL_SET,
                "clip": normalized_clip,
                "probe_summary": summary,
                "required_decision": "ready_for_proof_gated_write",
                "actual_decision": decision.get("status"),
            },
            recoverability="manual",
        )
    render_proof = None
    if require_render_proof:
        render_proof = _begin_color_render_proof(
            conn,
            clip_name=normalized_clip,
            route=color_page_gui_route.ROUTE_QUALIFIER_GUI_HSL_SET,
        )
    try:
        data = color_page_gui_route.run_qualifier_gui_hsl_set(
            conn,
            clip_name=normalized_clip,
            controls=request["controls"],
            driver=driver,
            probe=probe,
        )
        data["initial_probe"] = probe
        if render_proof is not None:
            conn_after = get_connection(require_timeline=True)
            data["render_proof"] = _complete_color_render_proof(conn_after, render_proof, partial_result=data)
            data["verification"]["status"] = "verified"
            data["verification"]["render_proof_status"] = data["render_proof"]["status"]
            data["verification"]["render_proof_route"] = data["render_proof"]["route"]
            set_verification_status("verified")
            set_recoverability("not_applicable")
        else:
            data["render_proof"] = {
                "status": "not_requested",
                "reason": "setup_only_qualifier_mask_may_not_change_pixels",
                "required_next_proof": "Apply a visible correction on the same node and verify rendered-frame pixel diff plus locality.",
            }
            data["verification"].update(
                {
                    "status": "setup_only",
                    "render_proof_required": False,
                    "final_grade_success": False,
                    "required_next_proof": data["render_proof"]["required_next_proof"],
                }
            )
            set_verification_status("pending_manual")
            set_recoverability("manual")
    except CLIError:
        set_verification_status("failed")
        raise
    output(data, title="Color Page Qualifier GUI HSL Set")

@page_app.command("qualifier-gui-matte-set")
@handle_errors
def page_qualifier_gui_matte_set(
    clip_name: Optional[str] = typer.Argument(None, help="Clip name; defaults to current Color page clip"),
    softness: Optional[float] = typer.Option(None, "--softness", help="Requested native GUI Qualifier softness"),
    blur: Optional[float] = typer.Option(None, "--blur", help="Requested native GUI matte blur"),
    clean_black: Optional[float] = typer.Option(None, "--clean-black", help="Requested native GUI matte clean black"),
    clean_white: Optional[float] = typer.Option(None, "--clean-white", help="Requested native GUI matte clean white"),
    denoise: Optional[float] = typer.Option(None, "--denoise", help="Requested native GUI matte denoise when probe exposes a settable control"),
    grow_shrink: Optional[float] = typer.Option(None, "--grow-shrink", help="Requested native GUI matte grow/shrink when probe exposes a settable control"),
    require_render_proof: bool = typer.Option(
        True,
        "--require-render-proof/--setup-only",
        help=(
            "Require before/after rendered-frame pixel proof. Use --setup-only only inside a larger workflow "
            "that will apply a visible correction and perform final render proof."
        ),
    ),
):
    """Set native Color Page Qualifier matte/refinement controls through a proof-gated GUI route."""
    from ..core import color_page_gui_route

    normalized_clip = color_page_gui_route.normalize_optional_clip(_option_value(clip_name))
    request = color_page_gui_route.normalize_qualifier_gui_matte_controls(
        softness=_option_value(softness),
        blur=_option_value(blur),
        clean_black=_option_value(clean_black),
        clean_white=_option_value(clean_white),
        denoise=_option_value(denoise),
        grow_shrink=_option_value(grow_shrink),
    )
    require_render_proof = bool(_option_value(require_render_proof, True))
    policy = enforce_mutation_policy(
        "color.page_qualifier_gui_matte_set",
        intended_engine="resolve_gui",
        mutating=not is_dry_run(),
    )
    set_execution_engine("resolve_gui")
    set_capability_context("color.page_qualifier_gui_matte_set", "partial")
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            {
                "message": "DRY-RUN: Would set native Color Page Qualifier matte controls through the GUI-assisted route.",
                "route": color_page_gui_route.ROUTE_QUALIFIER_GUI_MATTE_SET,
                "clip": normalized_clip,
                "values": request["values"],
                "requested_controls": request["controls"],
                "required_probe_flag": "matte_refinement_gui_write_supported",
                "proof_required": True,
                "render_proof_required": bool(require_render_proof),
                "setup_only": not bool(require_render_proof),
                "required_panel": "Color page Qualifier palette with matte/refinement settable controls",
                "policy": policy,
            },
            title="Color Page Qualifier GUI Matte Set Preview",
        )
        return

    conn = get_connection(require_timeline=True)
    driver = color_page_gui_route.MacOSColorPageGuiDriver()
    probe = color_page_gui_route.run_qualifier_panel_probe(conn, clip_name=normalized_clip, driver=driver)
    summary = probe.get("summary") if isinstance(probe.get("summary"), dict) else {}
    if not summary.get("matte_refinement_gui_write_supported"):
        set_verification_status("failed")
        set_recoverability("manual")
        raise CapabilityNegotiationFailed(
            "Native Color Page Qualifier GUI matte controls are not exposed safely enough to mutate.",
            details={
                "route": color_page_gui_route.ROUTE_QUALIFIER_GUI_MATTE_SET,
                "clip": normalized_clip,
                "probe_summary": summary,
                "required_summary_flag": "matte_refinement_gui_write_supported",
                "actual_summary_flag": summary.get("matte_refinement_gui_write_supported"),
            },
            recoverability="manual",
        )
    render_proof = None
    if require_render_proof:
        render_proof = _begin_color_render_proof(
            conn,
            clip_name=normalized_clip,
            route=color_page_gui_route.ROUTE_QUALIFIER_GUI_MATTE_SET,
        )
    try:
        data = color_page_gui_route.run_qualifier_gui_matte_set(
            conn,
            clip_name=normalized_clip,
            controls=request["controls"],
            driver=driver,
            probe=probe,
        )
        data["initial_probe"] = probe
        if render_proof is not None:
            conn_after = get_connection(require_timeline=True)
            data["render_proof"] = _complete_color_render_proof(conn_after, render_proof, partial_result=data)
            data["verification"]["status"] = "verified"
            data["verification"]["render_proof_status"] = data["render_proof"]["status"]
            data["verification"]["render_proof_route"] = data["render_proof"]["route"]
            set_verification_status("verified")
            set_recoverability("not_applicable")
        else:
            data["render_proof"] = {
                "status": "not_requested",
                "reason": "setup_only_qualifier_matte_may_not_change_pixels",
                "required_next_proof": "Apply a visible correction on the same node and verify rendered-frame pixel diff plus locality.",
            }
            data["verification"].update(
                {
                    "status": "setup_only",
                    "render_proof_required": False,
                    "final_grade_success": False,
                    "required_next_proof": data["render_proof"]["required_next_proof"],
                }
            )
            set_verification_status("pending_manual")
            set_recoverability("manual")
    except CLIError:
        set_verification_status("failed")
        raise
    output(data, title="Color Page Qualifier GUI Matte Set")

@page_app.command("primary-gui-set")
@handle_errors
def page_primary_gui_set(
    clip_name: Optional[str] = typer.Argument(None, help="Clip name; defaults to current Color page clip"),
    track: Optional[int] = typer.Option(None, "--track", help="Exact 1-based video track selector"),
    at: Optional[str] = typer.Option(None, "--at", help="Exact timeline position selector"),
    temperature: Optional[float] = typer.Option(None, "--temperature", "--temp", help="Selected-node Primaries Temp GUI value"),
    tint: Optional[float] = typer.Option(None, "--tint", help="Selected-node Primaries Tint GUI value"),
    contrast: Optional[float] = typer.Option(None, "--contrast", help="Selected-node Primaries Contrast GUI value"),
    pivot: Optional[float] = typer.Option(None, "--pivot", help="Selected-node Primaries Pivot GUI value"),
    mid_detail: Optional[float] = typer.Option(None, "--mid-detail", help="Selected-node Primaries Mid/Detail GUI value"),
    color_boost: Optional[float] = typer.Option(None, "--color-boost", help="Selected-node Primaries Color Boost GUI value"),
    shadows: Optional[float] = typer.Option(None, "--shadows", help="Selected-node Primaries Shadows GUI value"),
    highlights: Optional[float] = typer.Option(None, "--highlights", help="Selected-node Primaries Highlights GUI value"),
    saturation: Optional[float] = typer.Option(None, "--saturation", "--sat", help="Selected-node Primaries Saturation GUI value"),
    hue: Optional[float] = typer.Option(None, "--hue", help="Selected-node Primaries Hue GUI value"),
    lum_mix: Optional[float] = typer.Option(None, "--lum-mix", help="Selected-node Primaries Lum Mix GUI value"),
    require_render_proof: bool = typer.Option(
        True,
        "--require-render-proof/--setup-only",
        help=(
            "Require before/after rendered-frame pixel proof. Use --setup-only only inside a larger workflow "
            "that will perform final render proof."
        ),
    ),
):
    """Set selected-node Primaries controls through the workflow-owned GUI route."""
    from ..core import color_page_gui_route

    normalized_clip = color_page_gui_route.normalize_optional_clip(_option_value(clip_name))
    normalized_track = _option_value(track)
    normalized_at = _option_value(at)
    request = color_page_gui_route.normalize_primary_gui_controls(
        temperature=_option_value(temperature),
        tint=_option_value(tint),
        contrast=_option_value(contrast),
        pivot=_option_value(pivot),
        mid_detail=_option_value(mid_detail),
        color_boost=_option_value(color_boost),
        shadows=_option_value(shadows),
        highlights=_option_value(highlights),
        saturation=_option_value(saturation),
        hue=_option_value(hue),
        lum_mix=_option_value(lum_mix),
    )
    require_render_proof = bool(_option_value(require_render_proof, True))
    capability_id = "color.page_primary_gui_set"
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
                "message": "DRY-RUN: Would set selected-node Color Page Primaries controls through the GUI-assisted route.",
                "route": color_page_gui_route.ROUTE_PRIMARY_GUI_SET,
                "clip": normalized_clip,
                "track": normalized_track,
                "at": normalized_at,
                "values": request["values"],
                "requested_controls": request["controls"],
                "required_panel": "Color page Primaries - Color Wheels palette",
                "render_proof_required": require_render_proof,
                "node_targeting": "current_selected_color_page_node",
                "policy": policy,
            },
            title="Color Page Primary GUI Set Preview",
        )
        return

    conn = get_connection(require_timeline=True)
    render_proof = None
    if require_render_proof:
        render_proof = _begin_color_render_proof(
            conn,
            clip_name=normalized_clip,
            track=normalized_track,
            at=normalized_at,
            route=color_page_gui_route.ROUTE_PRIMARY_GUI_SET,
        )
    try:
        data = color_page_gui_route.run_primary_gui_set(
            conn,
            clip_name=normalized_clip,
            track=normalized_track,
            at=normalized_at,
            controls=request["controls"],
        )
        if render_proof is not None:
            conn_after = get_connection(require_timeline=True)
            data["render_proof"] = _complete_color_render_proof(conn_after, render_proof, partial_result=data)
            data["verification"]["status"] = "verified"
            data["verification"]["render_proof_status"] = data["render_proof"]["status"]
            data["verification"]["render_proof_route"] = data["render_proof"]["route"]
            set_verification_status("verified")
            set_recoverability("not_applicable")
        else:
            data["render_proof"] = {
                "status": "not_requested",
                "reason": "setup_only_primary_gui_set",
                "required_next_proof": "Verify the final workflow with rendered-frame pixel diff and locality checks.",
            }
            data["verification"].update(
                {
                    "status": "setup_only",
                    "render_proof_required": False,
                    "final_grade_success": False,
                    "required_next_proof": data["render_proof"]["required_next_proof"],
                }
            )
            set_verification_status("pending_manual")
            set_recoverability("manual")
    except CLIError:
        set_verification_status("failed")
        raise
    output(data, title="Color Page Primary GUI Set")


@page_app.command("still-match")
@handle_errors
def page_still_match(
    target_clip: Optional[str] = typer.Argument(None, help="Target clip name; defaults to current Color page clip"),
    still: Optional[str] = typer.Option(None, "--still", help="Requested Gallery still selector"),
    mode: str = typer.Option("side-by-side", "--mode", help="Requested viewer match mode"),
):
    """Run native Gallery still comparison through the workflow-owned GUI route."""
    from ..core import still_match_gui_route

    set_execution_engine("resolve_gui", 0.65)
    set_capability_context("color.page_still_match", "supported")
    normalized_target = _option_value(target_clip)
    if normalized_target is not None:
        normalized_target = str(normalized_target).strip()
        if not normalized_target:
            raise ValidationError(
                "Color Page still-match target clip must not be empty.",
                details={"target_clip": target_clip},
                recoverability="not_applicable",
            )
    normalized_still = _option_value(still)
    if normalized_still is not None:
        normalized_still = str(normalized_still).strip()
        if not normalized_still:
            raise ValidationError(
                "Color Page still-match --still must not be empty.",
                details={"still": still},
                recoverability="not_applicable",
            )
    normalized_mode = still_match_gui_route.normalize_mode(str(_option_value(mode, "side-by-side") or "side-by-side"))

    enforce_mutation_policy("color.page_still_match", intended_engine="resolve_gui", mutating=not is_dry_run())
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            {
                "action": "color.page.still_match",
                "route": still_match_gui_route.ROUTE,
                "target_clip": normalized_target,
                "still": normalized_still or "1",
                "mode": normalized_mode,
                "would_apply_gui": True,
                "applied": False,
                "verified": False,
                "required_page": "color",
                "requires_gallery_panel": True,
                "requires_proof": True,
            },
            title="Color Page Still Match Preview",
        )
        return

    conn = get_connection(require_timeline=True)
    data = still_match_gui_route.run_still_match(
        conn,
        target_clip=normalized_target,
        still=normalized_still,
        mode=normalized_mode,
    )
    data["required_page"] = "color"
    data["verified_route"] = "native_gallery_still_match_gui_proof"
    output(data, title="Color Page Still Match")


@page_app.command("hdr-detail-set")
@handle_errors
def page_hdr_detail_set(
    clip_name: Optional[str] = typer.Argument(None, help="Clip name"),
    zone: str = typer.Option(..., "--zone", help="HDR detail zone: highlight, specular"),
    x: Optional[float] = typer.Option(None, "--x", help="HDR detail X vector value"),
    y: Optional[float] = typer.Option(None, "--y", help="HDR detail Y vector value"),
    sat: Optional[float] = typer.Option(None, "--sat", help="HDR detail saturation control"),
    range_value: Optional[float] = typer.Option(None, "--range", help="HDR detail range boundary"),
    falloff: Optional[float] = typer.Option(None, "--falloff", help="HDR detail falloff control"),
):
    """Set verified native Color Page HDR Highlight/Specular detail controls via Project.db."""
    from ..core import color_page_db

    clip_name = _option_value(clip_name)
    x = _option_value(x)
    y = _option_value(y)
    sat = _option_value(sat)
    range_value = _option_value(range_value)
    falloff = _option_value(falloff)
    normalized_zone = str(_option_value(zone, zone) or "").strip().lower()
    set_execution_engine("db_workaround", 0.85)
    set_capability_context("color.page_hdr_detail_set", "supported")
    if normalized_zone not in color_page_db.HDR_DETAIL_ZONE_NAMES:
        raise ValidationError(
            "Color Page HDR detail zone must be one of: highlight, specular.",
            details={"zone": zone, "supported_zones": sorted(color_page_db.HDR_DETAIL_ZONE_NAMES)},
            recoverability="not_applicable",
        )
    specified = {
        axis: value
        for axis, value in {"x": x, "y": y, "sat": sat, "range": range_value, "falloff": falloff}.items()
        if value is not None
    }
    if not specified:
        raise ValidationError(
            "Color Page hdr-detail-set requires at least one HDR detail value.",
            details={"supported_values": ["x", "y", "sat", "range", "falloff"]},
            recoverability="not_applicable",
        )
    for axis, value in specified.items():
        color_page_db._validate_hdr_zone_value(axis, float(value))

    enforce_mutation_policy(
        "color.page_hdr_detail_set",
        intended_engine="db_workaround",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        dry_run_message("Would set Color Page HDR detail controls via DB")
        return

    conn = get_connection(require_timeline=True)
    data = color_page_db.write_hdr_detail(
        conn,
        clip_name=clip_name,
        zone=normalized_zone,
        x=None if x is None else float(x),
        y=None if y is None else float(y),
        sat=None if sat is None else float(sat),
        range_value=None if range_value is None else float(range_value),
        falloff=None if falloff is None else float(falloff),
    )
    if isinstance(data.get("verification"), dict) and data["verification"].get("status") == "verified":
        set_verification_status("verified")
        set_recoverability("not_applicable")
    output(data, title="Color Page — HDR Detail Set")
    success("Color Page HDR detail controls written to DB.")


@page_app.command("hdr-zone-set")
@handle_errors
def page_hdr_zone_set(
    clip_name: Optional[str] = typer.Argument(None, help="Clip name"),
    zone: str = typer.Option(..., "--zone", help="HDR wheel zone: dark, shadow, light, highlight, specular"),
    x: Optional[float] = typer.Option(None, "--x", help="HDR zone X vector value"),
    y: Optional[float] = typer.Option(None, "--y", help="HDR zone Y vector value"),
    z: Optional[float] = typer.Option(None, "--z", help="HDR zone Z vector value for dark/shadow/light"),
    sat: Optional[float] = typer.Option(None, "--sat", help="HDR zone saturation control for highlight/specular"),
    range_value: Optional[float] = typer.Option(None, "--range", help="HDR zone range boundary for highlight/specular"),
    falloff: Optional[float] = typer.Option(None, "--falloff", help="HDR zone falloff control for highlight/specular"),
):
    """Set verified native Color Page HDR zone controls via Project.db."""
    from ..core import color_page_db

    clip_name = _option_value(clip_name)
    x = _option_value(x)
    y = _option_value(y)
    z = _option_value(z)
    sat = _option_value(sat)
    range_value = _option_value(range_value)
    falloff = _option_value(falloff)
    normalized_zone = str(_option_value(zone, zone) or "").strip().lower()
    set_execution_engine("db_workaround", 0.85)
    set_capability_context("color.page_hdr_zone_set", "supported")
    if x is None and y is None and z is None and sat is None and range_value is None and falloff is None:
        raise ValidationError(
            "Color Page hdr-zone-set requires at least one HDR zone value.",
            details={"supported_values": ["x", "y", "z", "sat", "range", "falloff"]},
            recoverability="not_applicable",
        )
    if normalized_zone in color_page_db.HDR_DETAIL_ZONE_NAMES and z is not None:
        raise ValidationError(
            "Highlight/Specular HDR detail controls do not expose --z.",
            details={"zone": normalized_zone, "unsupported_axis": "z"},
            recoverability="not_applicable",
        )
    if normalized_zone in color_page_db.HDR_ZONE_PARAM_KEYS and any(
        value is not None for value in (sat, range_value, falloff)
    ):
        raise ValidationError(
            "Dark/Shadow/Light HDR zone controls accept --x/--y/--z only.",
            details={"zone": normalized_zone, "unsupported": ["sat", "range", "falloff"]},
            recoverability="not_applicable",
        )
    if normalized_zone not in set(color_page_db.HDR_ZONE_PARAM_KEYS) | set(color_page_db.HDR_DETAIL_ZONE_NAMES):
        raise ValidationError(
            "Color Page hdr-zone-set --zone must be one of: dark, shadow, light, highlight, specular.",
            details={
                "zone": zone,
                "supported_zones": sorted([*color_page_db.HDR_ZONE_PARAM_KEYS, *color_page_db.HDR_DETAIL_ZONE_NAMES]),
            },
            recoverability="not_applicable",
        )
    for axis, value in (("x", x), ("y", y), ("z", z), ("sat", sat), ("range", range_value), ("falloff", falloff)):
        if value is not None:
            color_page_db._validate_hdr_zone_value(axis, float(value))

    enforce_mutation_policy(
        "color.page_hdr_zone_set",
        intended_engine="db_workaround",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        dry_run_message("Would set Color Page HDR zone controls via DB")
        return

    conn = get_connection(require_timeline=True)
    data = color_page_db.write_hdr_zone(
        conn,
        clip_name=clip_name,
        zone=normalized_zone,
        x=None if x is None else float(x),
        y=None if y is None else float(y),
        z=None if z is None else float(z),
        sat=None if sat is None else float(sat),
        range_value=None if range_value is None else float(range_value),
        falloff=None if falloff is None else float(falloff),
    )
    if isinstance(data.get("verification"), dict) and data["verification"].get("status") == "verified":
        set_verification_status("verified")
        set_recoverability("not_applicable")
    output(data, title="Color Page — HDR Zone Set")
    success("Color Page HDR zone values written to DB.")


@page_app.command("qualifier-matte-refine")
@handle_errors
def page_qualifier_matte_refine(
    clip_name: Optional[str] = typer.Argument(None, help="Clip name; defaults to current Color page clip"),
    hue: Optional[str] = typer.Option(None, "--hue", help="Hue center,width,soft,symmetry in native Qualifier UI units 0..100"),
    saturation: Optional[str] = typer.Option(None, "--saturation", help="Saturation low,high,low_soft,high_soft in UI units 0..100"),
    luma: Optional[str] = typer.Option(None, "--luma", help="Luminance low,high,low_soft,high_soft in UI units 0..100"),
    blur_radius: Optional[float] = typer.Option(None, "--blur-radius", help="Matte Finesse Blur Radius in UI units 0..100"),
):
    """Set verified native Color Page HSL Qualifier matte refinement values via Project.db."""
    from ..core import color_page_db

    def _parse_quad(raw: Optional[str], *, option_name: str) -> tuple[float, float, float, float] | None:
        normalized = _option_value(raw)
        if normalized is None or str(normalized).strip() == "":
            return None
        parts = [part.strip() for part in str(normalized).split(",")]
        if len(parts) != 4:
            raise ValidationError(
                f"Color Page qualifier-matte-refine {option_name} must contain four comma-separated numbers.",
                details={option_name.lstrip("-").replace("-", "_"): normalized},
                recoverability="not_applicable",
            )
        try:
            values = tuple(float(part) for part in parts)
        except ValueError as exc:
            raise ValidationError(
                f"Color Page qualifier-matte-refine {option_name} must contain numeric values.",
                details={option_name.lstrip("-").replace("-", "_"): normalized},
                recoverability="not_applicable",
            ) from exc
        for index, value in enumerate(values):
            color_page_db._validate_qualifier_ui_value(value, label=f"{option_name}_{index + 1}")
        return values  # type: ignore[return-value]

    hue_values = _parse_quad(hue, option_name="--hue")
    saturation_values = _parse_quad(saturation, option_name="--saturation")
    luma_values = _parse_quad(luma, option_name="--luma")
    blur_value = _option_value(blur_radius)
    if blur_value is not None:
        blur_value = float(blur_value)
        color_page_db._validate_qualifier_ui_value(blur_value, label="blur_radius")
    if hue_values is None and saturation_values is None and luma_values is None and blur_value is None:
        raise ValidationError(
            "Color Page qualifier-matte-refine requires --hue, --saturation, --luma, or --blur-radius.",
            details={"required_any": ["--hue", "--saturation", "--luma", "--blur-radius"]},
            recoverability="not_applicable",
        )

    enforce_mutation_policy("color.page_qualifier_matte_refinement", intended_engine="db_workaround")
    set_capability_context("color.page_qualifier_matte_refinement", "supported")
    set_execution_engine("db_workaround", 0.82)
    set_verification_status("render_unverified")
    set_recoverability("manual")
    payload = {
        "route": "db_workaround_color_page_qualifier_matte_refine",
        "clip": _option_value(clip_name),
        "hue": hue_values,
        "saturation": saturation_values,
        "luma": luma_values,
        "blur_radius": blur_value,
        "would_mutate": True,
    }
    if is_dry_run():
        output(payload, title="Color Page Qualifier Matte Refine Preview")
        return

    conn = get_connection()
    data = color_page_db.write_qualifier_matte_refinement(
        conn,
        clip_name=clip_name,
        hue=hue_values,
        saturation=saturation_values,
        luma=luma_values,
        blur_radius=blur_value,
    )
    set_verification_status("render_unverified")
    output(data, title="Color Page Qualifier Matte Refine")
    success("Color Page HSL Qualifier matte refinement values written to DB.")


@page_app.command("magic-mask-refine")
@handle_errors
def page_magic_mask_refine(
    clip_name: Optional[str] = typer.Argument(None, help="Clip name; defaults to current Color page clip"),
    object_mode: str = typer.Option("person", "--object-mode", help="Requested Magic Mask object/refinement mode"),
    track: bool = typer.Option(False, "--track", help="Request native Magic Mask tracking"),
    stroke: Optional[str] = typer.Option(None, "--stroke", help="Normalized refinement stroke: x,y;x,y;..."),
):
    """Draw a native Magic Mask refinement stroke through the Color Page GUI route."""
    from ..core import magic_mask_gui_route

    set_execution_engine("resolve_gui")
    set_capability_context("color.page_magic_mask_refinement", "partial")
    if clip_name is None:
        raise ValidationError(
            "Color Page magic-mask-refine requires an explicit clip target.",
            details={
                "required": ["clip_name", "--stroke"],
                "example": 'cutagent color page magic-mask-refine "Interview A" --stroke "0.48,0.35;0.52,0.56" --track --json',
                "route": magic_mask_gui_route.ROUTE,
            },
            recoverability="not_applicable",
        )
    normalized_clip = magic_mask_gui_route.validate_clip_target(str(clip_name))
    normalized_mode = magic_mask_gui_route.normalize_magic_mask_mode(object_mode)
    if stroke is None:
        raise ValidationError(
            "Color Page magic-mask-refine requires --stroke so the native Magic Mask refinement is explicit and proofable.",
            details={
                "required": ["--stroke"],
                "stroke_format": "x,y;x,y;...",
                "coordinates": "normalized viewer coordinates from 0.0 to 1.0",
                "example": '--stroke "0.48,0.35;0.52,0.56"',
                "route": magic_mask_gui_route.ROUTE,
            },
            recoverability="not_applicable",
        )
    stroke_points = magic_mask_gui_route.parse_normalized_stroke(stroke)
    policy = enforce_mutation_policy("color.page_magic_mask_refinement", intended_engine="resolve_gui", mutating=not is_dry_run())
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            {
                "message": f"DRY-RUN: Would draw a {normalized_mode} Magic Mask refinement stroke on '{normalized_clip}'.",
                "route": magic_mask_gui_route.ROUTE,
                "clip": normalized_clip,
                "mode": normalized_mode,
                "stroke": {"points_normalized": [[x, y] for x, y in stroke_points]},
                "track_requested": bool(track),
                "proof_required": True,
                "supported_scope": "refinement_stroke_and_optional_tracking",
                "unsupported_scope": ["matte_finesse_controls", "automatic_object_selection_without_stroke", "tracked_mask_keyframe_readback"],
                "policy": policy,
            },
            title="Color Page Magic Mask Refinement",
        )
        return

    conn = get_connection(require_timeline=True)

    def _export_proof(path: Path) -> dict:
        metadata = _export_color_page_frame_as_still(conn, resolved_path=path, requested_output_path=str(path))
        return {"export_path": str(path), **metadata}

    render_proof = _begin_color_render_proof(
        conn,
        clip_name=normalized_clip,
        route=magic_mask_gui_route.ROUTE,
    )
    data = magic_mask_gui_route.run_magic_mask_draw_stroke(
        conn,
        clip_name=normalized_clip,
        mode=normalized_mode,
        stroke_points=stroke_points,
        track_requested=bool(track),
        proof_exporter=_export_proof,
    )
    conn_after = get_connection(require_timeline=True)
    data["render_proof"] = _complete_color_render_proof(
        conn_after,
        render_proof,
        partial_result=data,
    )
    set_verification_status("verified")
    data["action"] = "color.page.magic_mask_refine"
    data["supported_scope"] = "refinement_stroke_and_optional_tracking"
    data["unsupported_scope"] = ["matte_finesse_controls", "automatic_object_selection_without_stroke", "tracked_mask_keyframe_readback"]
    output(data, title="Color Page Magic Mask Refinement")


@page_app.command("lut-library-import")
@handle_errors
def page_lut_library_import(
    source: str = typer.Argument(..., help="Local .cube file or directory of .cube LUTs to import"),
    folder: str = typer.Option("CutAgent/Imported", "--folder", help="Relative DaVinci Resolve LUT library folder"),
    overwrite: bool = typer.Option(False, "--overwrite", help="Overwrite existing imported LUT files"),
    apply: bool = typer.Option(False, "--apply", help="Apply the first imported LUT to a Color page node after refresh"),
    clip_name: Optional[str] = typer.Option(None, "--clip", help="Clip name to apply the imported LUT to; defaults to current clip when --apply is used"),
    node: int = typer.Option(1, "--node", help="Color node index for --apply"),
    apply_lut: Optional[str] = typer.Option(None, "--apply-lut", help="Specific imported LUT key to apply"),
):
    """Import LUTs into DaVinci Resolve's LUT library and refresh the native LUT list."""
    source = str(_option_value(source) or "").strip()
    folder = str(_option_value(folder, "CutAgent/Imported") or "CutAgent/Imported").strip()
    overwrite = bool(_option_value(overwrite, False))
    apply = bool(_option_value(apply, False))
    clip_name = _option_value(clip_name)
    apply_lut = _option_value(apply_lut)
    node = int(_option_value(node, 1))

    set_execution_engine("workaround_setting", 0.8)
    set_capability_context("color.page_lut_library_import", "supported")

    if not source:
        raise ValidationError("LUT library source path must not be empty.", details={"source": source})
    source_path = Path(source).expanduser()
    if not source_path.is_absolute():
        source_path = Path.cwd() / source_path
    source_path = source_path.resolve(strict=False)
    if not source_path.exists():
        raise ValidationError(
            "LUT library source path was not found.",
            details={"source": source, "resolved_path": str(source_path)},
        )
    if source_path.is_file() and source_path.suffix.lower() != ".cube":
        raise ValidationError(
            "LUT library import currently supports .cube files.",
            details={"source": source, "resolved_path": str(source_path)},
        )
    if node < 1:
        raise ValidationError(
            "Node index must be a positive integer.",
            details={"node": node, "minimum": 1},
            recoverability="not_applicable",
        )
    if apply_lut is not None and not str(apply_lut).strip():
        raise ValidationError("Color Page lut-library-import --apply-lut must not be empty.", details={"apply_lut": apply_lut})
    if clip_name is not None and not str(clip_name).strip():
        raise ValidationError("Color Page lut-library-import --clip must not be empty.", details={"clip": clip_name})

    should_apply = apply or apply_lut is not None or clip_name is not None
    enforce_mutation_policy(
        "color.page_lut_library_import",
        intended_engine="workaround_setting",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        dry_run_message(
            f"Would import LUT library '{source_path}' into DaVinci Resolve folder '{folder}'"
            + (f" and apply to node {node}" if should_apply else "")
        )
        return

    conn = get_connection(require_timeline=should_apply, require_project=True)
    if should_apply:
        timeline_ops.require_sdk_color_mutation_guard(conn)
    data = color_ops.import_lut_library(
        conn,
        str(source_path),
        folder=folder,
        overwrite=overwrite,
        apply=should_apply,
        apply_clip_name=str(clip_name).strip() if clip_name is not None else None,
        apply_node=node,
        apply_lut_key=str(apply_lut).strip() if apply_lut is not None else None,
    )
    set_verification_status("verified")
    set_recoverability("not_applicable")
    output(data, title="Color Page — LUT Library Import")
    success("LUT library imported and refreshed.")


@page_app.command("dctl-apply")
@handle_errors
def page_dctl_apply(
    name: str = typer.Argument(..., help="DCTL/LUT name or path"),
    clip_name: Optional[str] = typer.Option(None, "--clip", help="Clip name; defaults to current Color page clip"),
    node: int = typer.Option(1, "--node", help="Color node index"),
):
    """Apply a DCTL as a Color Page node LUT through the verified LUT route."""
    name = str(_option_value(name) or "").strip()
    clip_name = _option_value(clip_name)
    node = int(_option_value(node, 1))

    set_execution_engine("workaround_setting", 0.8)
    set_capability_context("color.page_dctl_apply", "supported")

    if not name:
        raise ValidationError("Color Page dctl-apply name/path must not be empty.", details={"name": name})
    if node < 1:
        raise ValidationError(
            "Node index must be a positive integer.",
            details={"node": node, "minimum": 1},
            recoverability="not_applicable",
        )
    if clip_name is not None and not str(clip_name).strip():
        raise ValidationError("Color Page dctl-apply --clip must not be empty.", details={"clip": clip_name})

    enforce_mutation_policy(
        "color.page_dctl_apply",
        intended_engine="workaround_setting",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        dry_run_message(f"Would apply DCTL/LUT '{name}' to node {node}")
        return

    conn = get_connection(require_timeline=True)
    normalized_clip = str(clip_name).strip() if clip_name is not None else None
    proof = _begin_color_render_proof(
        conn,
        clip_name=normalized_clip,
        route="api_native_color_page_dctl_apply",
        deliver_proof=True,
    )
    color_ops.set_lut(conn, normalized_clip, node, name)
    readback = color_ops.get_lut_info(conn, normalized_clip, node)
    data = {
        "clip": normalized_clip,
        "node": node,
        "applied": True,
        "cleared": False,
        "requested_dctl": name,
        "readback": readback,
        "readback_lut_path": readback.get("lut_path"),
        "route": "api_native_color_page_dctl_apply",
        "alias_of": "color lut --set",
    }
    data["render_proof"] = _complete_color_render_proof(conn, proof, partial_result=data)
    set_verification_status("verified")
    set_recoverability("not_applicable")
    output(data, title="Color Page — DCTL Apply")
    success("DCTL/LUT applied to Color Page node.")


@page_app.command("dctl-remove")
@handle_errors
def page_dctl_remove(
    clip_name: Optional[str] = typer.Option(None, "--clip", help="Clip name; defaults to current Color page clip"),
    node: int = typer.Option(1, "--node", help="Color node index"),
):
    """Remove a DCTL/LUT from a Color Page node through the verified LUT route."""
    clip_name = _option_value(clip_name)
    node = int(_option_value(node, 1))

    set_execution_engine("workaround_setting", 0.8)
    set_capability_context("color.page_dctl_remove", "supported")

    if node < 1:
        raise ValidationError(
            "Node index must be a positive integer.",
            details={"node": node, "minimum": 1},
            recoverability="not_applicable",
        )
    if clip_name is not None and not str(clip_name).strip():
        raise ValidationError("Color Page dctl-remove --clip must not be empty.", details={"clip": clip_name})

    enforce_mutation_policy(
        "color.page_dctl_remove",
        intended_engine="workaround_setting",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        dry_run_message(f"Would remove DCTL/LUT from node {node}")
        return

    conn = get_connection(require_timeline=True)
    normalized_clip = str(clip_name).strip() if clip_name is not None else None
    color_ops.clear_lut(conn, normalized_clip, node)
    readback = color_ops.get_lut_info(conn, normalized_clip, node)
    set_verification_status("verified")
    set_recoverability("not_applicable")
    output(
        {
            "clip": normalized_clip,
            "node": node,
            "applied": False,
            "cleared": True,
            "readback": readback,
            "readback_lut_path": readback.get("lut_path"),
            "route": "api_native_color_page_dctl_remove",
            "alias_of": "color lut --clear",
        },
        title="Color Page — DCTL Remove",
    )
    success("DCTL/LUT removed from Color Page node.")
