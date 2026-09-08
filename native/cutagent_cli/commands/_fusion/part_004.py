from __future__ import annotations

@mask_app.command("rectangle")
@handle_errors
def mask_rectangle(
    center: str = typer.Option("0.5,0.5", "--center", "-c", help="Center X,Y"),
    width: float = typer.Option(0.5, "--width", "-w", help="Width"),
    height: float = typer.Option(0.5, "--height", help="Height"),
    softness: float = typer.Option(0.0, "--softness", "-s", help="Soft edge"),
):
    """Add a rectangle mask."""
    enforce_mutation_policy("fusion.mutation", intended_engine="fusion_native")
    cx, cy = _parse_xy_option(center, option_name="center")
    if is_dry_run():
        output(
            {
                "message": f"DRY-RUN: Would add rectangle mask at center=({cx}, {cy}), width={width}, height={height}, softness={softness}.",
                "action": "fusion.mask.rectangle",
                "center": [cx, cy],
                "width": width,
                "height": height,
                "softness": softness,
                "would_add": True,
                "route": "fusion_api.add_mask_rectangle",
            },
            title="Fusion Mask Rectangle",
        )
        return
    conn = get_connection(require_timeline=True)
    api = fusion_api.get_fusion_api(conn)
    tool = api.add_mask_rectangle(center=(cx, cy), width=width, height=height, softness=softness)
    tool_name = tool.Name if hasattr(tool, "Name") else "RectangleMask"
    success(f"Added rectangle mask ({tool_name})")


@mask_app.command("ellipse")
@handle_errors
def mask_ellipse(
    center: str = typer.Option("0.5,0.5", "--center", "-c", help="Center X,Y"),
    width: float = typer.Option(0.5, "--width", "-w", help="Width"),
    height: float = typer.Option(0.5, "--height", help="Height"),
    softness: float = typer.Option(0.0, "--softness", "-s", help="Soft edge"),
):
    """Add an ellipse mask."""
    enforce_mutation_policy("fusion.mutation", intended_engine="fusion_native")
    cx, cy = _parse_xy_option(center, option_name="center")
    if is_dry_run():
        output(
            {
                "message": f"DRY-RUN: Would add ellipse mask at center=({cx}, {cy}), width={width}, height={height}, softness={softness}.",
                "action": "fusion.mask.ellipse",
                "center": [cx, cy],
                "width": width,
                "height": height,
                "softness": softness,
                "would_add": True,
                "route": "fusion_api.add_mask_ellipse",
            },
            title="Fusion Mask Ellipse",
        )
        return
    conn = get_connection(require_timeline=True)
    api = fusion_api.get_fusion_api(conn)
    tool = api.add_mask_ellipse(center=(cx, cy), width=width, height=height, softness=softness)
    tool_name = tool.Name if hasattr(tool, "Name") else "EllipseMask"
    success(f"Added ellipse mask ({tool_name})")


@mask_app.command("polygon")
@handle_errors
def mask_polygon(
    points: str = typer.Argument(..., help="Points as 'x,y;x,y;...'"),
):
    """Add a polygon mask."""
    enforce_mutation_policy("fusion.mutation", intended_engine="fusion_native")
    parsed = _parse_xy_points(points)
    if is_dry_run():
        output(
            {
                "message": f"DRY-RUN: Would add polygon mask with {len(parsed)} points.",
                "action": "fusion.mask.polygon",
                "points": [[x, y] for x, y in parsed],
                "point_count": len(parsed),
                "would_add": True,
                "route": "fusion_api.add_mask_polygon",
            },
            title="Fusion Mask Polygon",
        )
        return
    conn = get_connection(require_timeline=True)
    api = fusion_api.get_fusion_api(conn)
    tool = api.add_mask_polygon(parsed)
    tool_name = tool.Name if hasattr(tool, "Name") else "PolylineMask"
    success(f"Added polygon mask ({tool_name}) with {len(parsed)} points")


# === Keyer Commands ===

keyer_app = typer.Typer(help="Fusion keying (chroma key).")
app.add_typer(keyer_app, name="keyer")

_CHROMA_KEYER_COLORS = {"green", "blue", "red"}


@keyer_app.command("chroma")
@handle_errors
def keyer_chroma(
    color: str = typer.Option("green", "--color", "-c", help="Key color (green/blue/red)"),
    threshold: float = typer.Option(0.3, "--threshold", "-t", help="Threshold"),
):
    """Add a chroma keyer inline."""
    enforce_mutation_policy("fusion.mutation", intended_engine="fusion_native")
    color_key = str(color or "").strip().lower()
    if color_key not in _CHROMA_KEYER_COLORS:
        raise ValidationError(
            "Unsupported chroma key color.",
            details={"color": color, "allowed": sorted(_CHROMA_KEYER_COLORS)},
        )
    conn = get_connection(require_timeline=True)
    api = fusion_api.get_fusion_api(conn)
    tool = api.add_keyer_chroma(color=color_key, threshold=threshold)
    tool_name = tool.Name if hasattr(tool, "Name") else "ChromaKeyer"
    success(f"Added chroma keyer ({tool_name}), color={color_key}, threshold={threshold}")


# === Tracker Commands ===

tracker_app = typer.Typer(help="Fusion tracking.")
app.add_typer(tracker_app, name="tracker")


@tracker_app.command("add")
@handle_errors
def tracker_add(
    pattern_center: str = typer.Option("0.5,0.5", "--pattern-center", "-p", help="Initial pattern center X,Y"),
):
    """Add a tracker tool inline."""
    enforce_mutation_policy("fusion.mutation", intended_engine="fusion_native")
    cx, cy = _parse_xy_option(pattern_center, option_name="pattern_center")
    if is_dry_run():
        output(
            {
                "message": f"DRY-RUN: Would add Fusion tracker at pattern_center=({cx}, {cy}).",
                "action": "fusion.tracker.add",
                "pattern_center": [cx, cy],
                "would_add": True,
                "route": "fusion_api.add_tracker",
            },
            title="Fusion Tracker Add",
        )
        return
    conn = get_connection(require_timeline=True)
    api = fusion_api.get_fusion_api(conn)
    tool = api.add_tracker(pattern_center=(cx, cy))
    tool_name = tool.Name if hasattr(tool, "Name") else "Tracker"
    success(f"Added tracker ({tool_name}) at ({cx}, {cy})")


# === Legacy .setting file commands (keep for compatibility) ===


def _load_setting_template(template_path: str) -> str:
    if not os.path.isfile(template_path):
        raise APICallFailed(f"Template file not found: {template_path}")
    with open(template_path, "r", encoding="utf-8") as handle:
        return handle.read()


def _validate_image_substitution(template_code: str, image_path: Optional[str], *, template_path: str) -> None:
    if image_path is None:
        return

    image_text = str(image_path).strip()
    if not image_text:
        raise ValidationError(
            "--image requires a non-empty image path.",
            details={"template": template_path, "image": image_path},
        )

    has_image_placeholder = any(placeholder in template_code for placeholder in DEFAULT_IMAGE_PLACEHOLDERS)
    if not has_image_placeholder:
        raise ValidationError(
            "Template does not contain a recognized image placeholder for --image.",
            details={
                "template": template_path,
                "image": image_text,
                "recognized_placeholders": DEFAULT_IMAGE_PLACEHOLDERS,
            },
        )

    if not os.path.isfile(image_text):
        raise APICallFailed(
            f"Image file not found: {image_text}",
            details={"template": template_path, "image": image_text},
        )


def _render_setting_from_spec(spec: dict[str, Any]) -> str:
    template_path = str(spec.get("template") or "").strip()
    if not template_path:
        raise ValidationError("Each batch item requires a template path.", details={"item": spec})

    template_code = _load_setting_template(template_path)
    text = spec.get("text")
    image = spec.get("image")
    bold_style = str(spec.get("bold_style") or "ExtraBold")

    clean_text = None
    styling = None
    if text is not None:
        clean_text, styling = parse_styled_text(str(text), bold_style)

    replacements = spec.get("placeholders")
    if replacements is not None and (not isinstance(replacements, dict) or isinstance(replacements, list)):
        raise ValidationError(
            "placeholders must be a JSON object.",
            details={"template": template_path},
        )

    _validate_image_substitution(template_code, None if image is None else str(image), template_path=template_path)

    return render_setting_template(
        template_code,
        text=clean_text,
        styling=styling,
        image=None if image is None else str(image),
        replacements={str(key): value for key, value in (replacements or {}).items()},
    )


def _insert_rendered_setting(
    conn,
    *,
    rendered: str,
    name: str,
    at: str,
    duration: float,
    track: int,
    holder: str = "Fusion Composition",
    holder_kind: str = "fusion",
) -> dict[str, Any]:
    duration_frames = _parse_positive_duration_frames(f"{duration}s", conn.fps)

    with tempfile.NamedTemporaryFile(suffix=".setting", delete=False, mode="w", encoding="utf-8") as handle:
        handle.write(rendered)
        setting_path = handle.name

    try:
        data = _insert_setting_precise(
            conn,
            path=setting_path,
            clip_name=name,
            at=at,
            record_frame=None,
            duration=f"{duration_frames}f",
            track=track,
            holder=holder,
            holder_kind=holder_kind,
            position_x=None,
            position_y=None,
        )
        return data
    finally:
        try:
            os.unlink(setting_path)
        except Exception:
            pass


_INSERT_STYLED_ROUTES = ("auto", "setting", "native-title")


def _validate_insert_styled_request(
    *,
    text: str,
    template_path: Optional[str],
    at: str,
    duration: str,
    track: int,
    bold_style: str,
    route: str,
) -> dict[str, Any]:
    from ..utils.timecode import parse_time_input, seconds_to_frames

    text_value = str(text or "").strip()
    if not text_value:
        raise ValidationError("Provide overlay text as an argument or with --text.")

    route_key = str(route or "auto").strip().lower().replace("_", "-")
    if route_key not in set(_INSERT_STYLED_ROUTES):
        raise ValidationError(
            "Unsupported text overlay route.",
            details={"route": route, "allowed": list(_INSERT_STYLED_ROUTES)},
        )

    try:
        start_seconds = parse_time_input(str(at or "0s"), 24.0)
    except Exception as error:
        raise ValidationError(
            "Invalid --at value for styled text insertion.",
            details={"at": at, "value": at, "reason": str(error)},
        ) from error
    if start_seconds < 0:
        raise ValidationError("Styled text start time must be non-negative.", details={"at": at})

    try:
        duration_seconds = parse_time_input(str(duration or "5s"), 24.0)
    except Exception as error:
        raise ValidationError(
            "Invalid --duration value for styled text insertion.",
            details={"duration": duration, "value": duration, "reason": str(error)},
        ) from error
    duration_frames = seconds_to_frames(duration_seconds, 24.0)
    if duration_frames <= 0:
        raise ValidationError("Text overlay duration must be greater than 0.", details={"duration": duration})

    if route_key in {"auto", "setting"} and track < 1:
        raise ValidationError("Text overlay track must be 1 or greater for the setting route.", details={"track": track})

    resolved_template = None
    template_source = None
    if route_key in {"auto", "setting"}:
        resolved_template = template_path or text_ops.default_text_overlay_template_path()
        template_source = "custom" if template_path else "bundled"
        if not os.path.isfile(resolved_template):
            raise APICallFailed("Text overlay template file not found.", details={"template": resolved_template})

    clean_text, styling = parse_styled_text(text_value, bold_style)
    return {
        "text": text_value,
        "clean_text": clean_text,
        "styled_range_count": styling.count("{ 109") if styling else 0,
        "bold_style": bold_style,
        "route": route_key,
        "template": resolved_template,
        "template_source": template_source,
        "at": at,
        "duration": duration,
        "duration_frames_at_24fps": duration_frames,
        "track": track,
    }


def _parse_batch_spec(spec_path: Optional[str], spec_json: Optional[str]) -> list[dict[str, Any]]:
    if bool(spec_path) == bool(spec_json):
        raise ValidationError(
            "Provide exactly one of --spec or --spec-json.",
            details={"spec": spec_path, "spec_json": bool(spec_json)},
        )

    if spec_path:
        if not os.path.isfile(spec_path):
            raise APICallFailed(f"Spec file not found: {spec_path}")
        with open(spec_path, "r", encoding="utf-8") as handle:
            raw = handle.read()
    else:
        raw = spec_json or ""

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValidationError("Spec must be valid JSON.", details={"error": str(exc)}) from exc

    items = payload.get("items") if isinstance(payload, dict) else payload
    if not isinstance(items, list) or len(items) == 0:
        raise ValidationError("Spec must decode to a non-empty item list.")

    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValidationError("Each batch item must be a JSON object.", details={"index": index})
        normalized.append(item)
    return normalized


def _bundled_template_dir() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "assets", "fusion-templates"))

@app.command("preview")
@handle_errors
def preview(
    text: str = typer.Argument(..., help='Text with **bold** markers (e.g., "This is **important**")'),
    bold_style: str = typer.Option("ExtraBold", help="Font style for bold text"),
):
    """Preview CharacterLevelStyling for styled text (dry-run)."""
    clean, cls_array = parse_styled_text(text, bold_style)
    output({
        "original": text,
        "clean_text": clean,
        "character_level_styling": cls_array or "(none — no bold markers found)",
        "bold_style": bold_style,
    }, title="Styled Text Preview")


@app.command("generate")
@handle_errors
def generate(
    template_path: str = typer.Option(..., "--template", "-t", help="Path to .setting template file"),
    text: Optional[str] = typer.Option(None, "--text", help="Text to insert (supports **bold**)"),
    image: Optional[str] = typer.Option(None, "--image", help="Image path to insert"),
    bold_style: str = typer.Option("ExtraBold", "--bold-style"),
    output_path: str = typer.Option(None, "--output", "-o", help="Output .setting file path"),
):
    """Generate a .setting file from a template with styled text."""
    if not os.path.isfile(template_path):
        raise APICallFailed(f"Template file not found: {template_path}")

    with open(template_path, "r", encoding="utf-8") as f:
        template_code = f.read()

    _validate_image_substitution(template_code, image, template_path=template_path)

    clean_text = None
    styling = None

    if text:
        clean_text, styling = parse_styled_text(text, bold_style)

    rendered = render_setting_template(template_code, text=clean_text, styling=styling, image=image)

    if output_path:
        with open(output_path, "w") as f:
            f.write(rendered)
        success(f"Generated .setting file: {output_path}")
    else:
        if get_output_mode() == "json":
            output({"rendered": rendered}, title="Generated Setting")
        else:
            # Print to stdout
            console.print(rendered)


@app.command("apply")
@handle_errors
def apply_setting(
    path: str = typer.Argument(..., help=".setting file to apply"),
    clip_name: Optional[str] = typer.Option(None, "--clip", help="Clip name (or current)"),
    track: Optional[int] = typer.Option(None, "--track", help="Video track index used with --record-frame"),
    record_frame: Optional[str] = typer.Option(None, "--record-frame", help="Timeline record frame used with --track"),
    verify_frame: Optional[str] = typer.Option(None, "--verify-frame", help="After apply, export this timeline frame for visual verification"),
    export_check: Optional[str] = typer.Option(None, "--export-check", help="PNG output path for --verify-frame visual verification"),
    sdk_graph_runtime: bool = typer.Option(False, "--sdk-graph-runtime", hidden=True),
):
    """Apply a .setting file to a clip via ImportFusionComp."""
    if isinstance(track, typer.models.OptionInfo):
        track = None
    if isinstance(record_frame, typer.models.OptionInfo):
        record_frame = None
    if isinstance(sdk_graph_runtime, typer.models.OptionInfo):
        sdk_graph_runtime = False
    _validate_target_selector(_normalize_optional_string(clip_name), track, record_frame)
    enforce_mutation_policy("fusion.mutation", intended_engine="fusion_native", mutating=not is_dry_run())
    resolved_path = os.path.abspath(os.path.expanduser(str(path)))
    if not os.path.isfile(resolved_path):
        raise APICallFailed(f"File not found: {resolved_path}")
    if sdk_graph_runtime:
        if any(value is not None for value in (clip_name, track, record_frame, verify_frame, export_check)):
            raise ValidationError("The private SDK Fusion graph runtime cannot be combined with public apply selectors.")
        if is_dry_run():
            raise ValidationError("The private SDK Fusion graph runtime does not accept dry-run dispatch.")
        try:
            with open(resolved_path, "rb") as request_file:
                request_bytes = request_file.read()
            expected_payload_digest = os.environ.get("CUTAGENT_MUTATION_POLICY_PAYLOAD_SHA256")
            if os.environ.get("CUTAGENT_MUTATION_POLICY_SCOPE_VALID") == "1":
                actual_payload_digest = f"sha256:{hashlib.sha256(request_bytes).hexdigest()}"
                if expected_payload_digest != actual_payload_digest:
                    raise ValidationError("The private SDK Fusion graph request changed after policy authorization.")
            request_payload = json.loads(request_bytes.decode("utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValidationError("The private SDK Fusion graph request file is invalid.") from exc
        conn = get_connection(require_timeline=True)
        result = sdk_fusion_graph.apply_sdk_fusion_graph(conn, request_payload)
        set_verification_status("verified")
        set_recoverability("not_applicable")
        output({"action": "fusion.apply", "sdkGraphRuntime": True, **result}, title="Fusion Graph Apply")
        return
    if export_check and not verify_frame:
        raise ValidationError("--export-check requires --verify-frame.", details={"export_check": export_check})
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            {
                "message": f"DRY-RUN: Would apply .setting file: {resolved_path}",
                "action": "fusion.apply",
                "would_apply": True,
                "dry_run": True,
                "path": resolved_path,
                "clip": clip_name,
                "track": track,
                "record_frame": record_frame,
                "target": "track_record" if track is not None and record_frame is not None else ("named_clip" if clip_name else "current_clip"),
                "route": ROUTE_IMPORT_FUSION_COMP,
                "requires_resolvable_clip": True,
                "verify_frame": verify_frame,
                "export_check": export_check,
                "would_export_check": bool(verify_frame),
            },
            title="Fusion Apply Plan",
        )
        return

    conn = get_connection(require_timeline=True)
    item, selector = _resolve_timeline_item(conn, clip_name=clip_name, track=track, record_frame=record_frame)

    if not hasattr(item, "ImportFusionComp"):
        raise APICallFailed("This clip doesn't support ImportFusionComp.")

    layout_prepared = None
    layout = None
    try:
        layout_prepared = _prepare_setting_import(resolved_path)
        import_path = str(layout_prepared.get("import_path") or resolved_path)
        result = item.ImportFusionComp(import_path)
    except Exception as exc:
        layout = _cleanup_prepared_setting(layout_prepared)
        raise APICallFailed(
            "ImportFusionComp failed. Check the file format.",
            details={"path": resolved_path, "import_path": import_path if "import_path" in locals() else resolved_path, "layout": layout, "error": str(exc)},
        ) from exc
    layout = _cleanup_prepared_setting(layout_prepared)
    if result:
        payload = {
            "message": f"Applied .setting file: {resolved_path}",
            "action": "fusion.apply",
            "path": resolved_path,
            "import_path": import_path,
            "clip": clip_name,
            "target_selector": selector,
            "clip_readback": _media_pool_item_name(item) or None,
            "route": ROUTE_IMPORT_FUSION_COMP,
            "applied": True,
            "imported": True,
            "layout": layout,
        }
        if verify_frame:
            verification = _export_apply_verification_frame(
                conn,
                frame_ref=verify_frame,
                output_path=export_check,
                setting_path=resolved_path,
            )
            set_verification_status("partial")
            set_recoverability("not_applicable" if verification.get("restored_playhead") else "manual")
            payload["verify_frame"] = verify_frame
            payload["verification"] = verification
        else:
            set_verification_status("partial")
            set_recoverability("not_applicable")
        output(payload, title="Fusion Apply")
    else:
        raise APICallFailed(
            "ImportFusionComp failed. Check the file format.",
            details={"path": resolved_path, "import_path": import_path, "layout": layout},
        )


def _export_apply_verification_frame(
    conn: Any,
    *,
    frame_ref: str,
    output_path: str | None,
    setting_path: str,
) -> dict[str, Any]:
    from . import timeline as timeline_commands

    if output_path:
        resolved_path = timeline_commands._resolve_thumbnail_output_file_path(output_path)
        requested_output_path = output_path
    else:
        safe_frame = str(frame_ref).replace(":", "-").replace("/", "_").replace(" ", "_")
        resolved_path = Path(setting_path).expanduser().resolve(strict=False).with_name(f"{Path(setting_path).stem}_verify_{safe_frame}.png")
        requested_output_path = str(resolved_path)

    original_playhead = timeline_ops.get_playhead(conn)
    target = timeline_ops.set_playhead(conn, frame_ref, return_details=True)
    restored = False
    restore_error: str | None = None
    metadata: dict[str, Any] = {}
    try:
        metadata = timeline_commands._export_current_frame_as_still(
            conn,
            resolved_path=resolved_path,
            requested_output_path=requested_output_path,
            error_message="Applied .setting, but visual verification frame export failed.",
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
        "output_path": str(resolved_path),
        "visual_check_path": timeline_commands._workspace_relative_path(resolved_path),
        "requested_output_path": requested_output_path,
        "original_playhead": original_playhead,
        "target": target,
        "restored_playhead": restored,
        "restore_warning": restore_error,
        "exported": True,
        "verified": True,
        "page_switch_required": True,
        **metadata,
    }


def _parse_template_params(values: list[str] | tuple[str, ...] | None) -> dict[str, str]:
    replacements: dict[str, str] = {}
    invalid: list[str] = []
    for raw in values or []:
        token = str(raw)
        if "=" not in token:
            invalid.append(token)
            continue
        key, value = token.split("=", 1)
        key = key.strip()
        if not key:
            invalid.append(token)
            continue
        replacements[key] = value
    if invalid:
        raise ValidationError(
            "--param values must use KEY=VALUE.",
            details={"invalid_params": invalid, "expected": "KEY=VALUE"},
        )
    return replacements


def _placeholder_report(template_code: str, rendered_code: str) -> dict[str, dict[str, Any]]:
    def _category(placeholders: list[str]) -> dict[str, Any]:
        before = [placeholder for placeholder in placeholders if placeholder in template_code]
        after = [placeholder for placeholder in placeholders if placeholder in rendered_code]
        return {
            "present": bool(before),
            "matched": before,
            "remaining": after,
            "applied": bool(before) and len(after) < len(before),
        }

    return {
        "text": _category(DEFAULT_TEXT_PLACEHOLDERS),
        "image": _category(DEFAULT_IMAGE_PLACEHOLDERS),
        "styling": _category(DEFAULT_STYLE_PLACEHOLDERS),
    }


def _delete_rendered_setting(path: str | None) -> bool:
    if not path:
        return False
    try:
        if os.path.exists(path):
            os.unlink(path)
            return True
    except Exception:
        return False
    return False


def _resolve_insert_setting_source(
    *,
    path: str | None,
    render_template: str | None,
    text: str | None,
    image: str | None,
    style_markdown: bool,
    bold_style: str,
    params: list[str] | tuple[str, ...] | None,
    require_text: bool,
    require_image: bool,
    require_styling: bool,
    keep_rendered: bool,
    rendered_output: str | None,
) -> dict[str, Any]:
    has_path = bool(str(path or "").strip())
    has_template = bool(str(render_template or "").strip())
    if has_path == has_template:
        raise ValidationError(
            "Specify exactly one setting source: positional path or --render-template.",
            details={"path": path, "render_template": render_template},
        )

    if has_path:
        effective_path = os.path.abspath(os.path.expanduser(str(path)))
        if not os.path.isfile(effective_path):
            raise APICallFailed(f"File not found: {effective_path}")
        return {
            "path": effective_path,
            "rendered": False,
            "template": None,
            "cleanup_path": None,
            "cleanup": {"temporary_setting_deleted": False},
            "render": {
                "enabled": False,
                "template": None,
                "text_applied": False,
                "image_applied": False,
                "styling_applied": False,
                "params": [],
                "rendered_path_kept": False,
            },
        }

    template_path = str(render_template)
    if not os.path.isfile(template_path):
        raise APICallFailed(f"Template file not found: {template_path}")
    if image is not None and not os.path.isfile(str(image)):
        raise APICallFailed(f"Image file not found: {image}")

    replacements = _parse_template_params(params)
    with open(template_path, "r", encoding="utf-8") as handle:
        template_code = handle.read()

    clean_text = text
    styling = None
    if style_markdown:
        clean_text, styling = parse_styled_text(text or "", bold_style)

    rendered_code = render_setting_template(
        template_code,
        text=clean_text if clean_text is not None else text,
        styling=styling,
        image=image,
        replacements=replacements,
    )
    placeholders = _placeholder_report(template_code, rendered_code)
    missing: list[str] = []
    if require_text and not placeholders["text"]["applied"]:
        missing.append("text")
    if require_image and not placeholders["image"]["applied"]:
        missing.append("image")
    if require_styling and not placeholders["styling"]["applied"]:
        missing.append("styling")
    if missing:
        raise ValidationError(
            "Required template placeholders were not replaced.",
            details={"missing": missing, "template": template_path, "placeholders": placeholders},
        )

    cleanup_path = None
    if rendered_output:
        rendered_path = os.path.abspath(os.path.expanduser(str(rendered_output)))
        output_parent = os.path.dirname(rendered_path)
        if output_parent:
            os.makedirs(output_parent, exist_ok=True)
        with open(rendered_path, "w", encoding="utf-8") as handle:
            handle.write(rendered_code)
        rendered_path_kept = True
    else:
        tmp = tempfile.NamedTemporaryFile("w", delete=False, suffix=".setting", encoding="utf-8")
        try:
            tmp.write(rendered_code)
            rendered_path = tmp.name
        finally:
            tmp.close()
        rendered_path_kept = bool(keep_rendered)
        if not keep_rendered:
            cleanup_path = rendered_path

    return {
        "path": rendered_path,
        "rendered": True,
        "template": template_path,
        "cleanup_path": cleanup_path,
        "cleanup": {"temporary_setting_deleted": False},
        "render": {
            "enabled": True,
            "template": template_path,
            "text_applied": bool(placeholders["text"]["applied"]),
            "image_applied": bool(placeholders["image"]["applied"]),
            "styling_applied": bool(placeholders["styling"]["applied"]),
            "params": sorted(replacements.keys()),
            "rendered_path_kept": rendered_path_kept,
            "placeholders": placeholders,
        },
    }
