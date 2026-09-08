from __future__ import annotations

def _capture_pipe_state(comp) -> Dict[str, Any]:
    media_in, media_out = _find_media_io(comp)
    primary = _get_primary_tool(comp)
    return {
        "media_in": media_in,
        "media_out": media_out,
        "main_source": _connected_source(media_out, "Input") if media_out else None,
        "primary": primary,
        "effect_mask_source": _connected_source(primary, "EffectMask") if primary else None,
    }


def _restore_pipe_state(state: Dict[str, Any]) -> None:
    media_out = state.get("media_out")
    main_source = state.get("main_source")
    primary = state.get("primary")
    effect_mask_source = state.get("effect_mask_source")

    if media_out and main_source:
        _connect_tools(main_source, media_out, "Input")
    if primary:
        _disconnect_input(primary, "EffectMask")
        if effect_mask_source:
            _connect_tools(effect_mask_source, primary, "EffectMask")


def _create_comp_tool(comp, tool_type: str, prefix: Optional[str] = None):
    if not hasattr(comp, "AddTool"):
        raise APICallFailed("Fusion composition cannot create tools (missing AddTool).")
    try:
        tool = comp.AddTool(tool_type, -32768, -32768)
    except TypeError:
        tool = comp.AddTool(tool_type)
    if not tool:
        raise APICallFailed(f"Failed to create Fusion tool '{tool_type}'.")
    if prefix:
        _set_tool_name(tool, _next_tool_name(comp, prefix))
    return tool


def _tool_input(tool, name: str, default: Any = None) -> Any:
    if not hasattr(tool, "GetInput"):
        return default
    try:
        value = tool.GetInput(name)
    except Exception:
        return default
    return default if value is None else value


def _tool_input_aliases(tool, names: List[str], default: Any = None) -> Any:
    """Read the first non-null Fusion input from a list of candidate names."""
    for name in names:
        value = _tool_input(tool, name, default=None)
        if value is not None:
            return value
    return default


def _point2_input(tool, name: str) -> Optional[List[float]]:
    """Normalize a Fusion point input without substituting the requested value."""
    value = _tool_input(tool, name, default=None)
    if isinstance(value, dict):
        components = (value.get(1, value.get("1")), value.get(2, value.get("2")))
    elif isinstance(value, (list, tuple)) and len(value) >= 2:
        components = (value[0], value[1])
    else:
        return None
    if any(
        isinstance(component, bool)
        or not isinstance(component, (int, float))
        or not math.isfinite(float(component))
        for component in components
    ):
        return None
    return [float(components[0]), float(components[1])]


def _set_tool_input_aliases(tool, names: List[str], value: Any) -> Optional[str]:
    """Write a Fusion input using the first candidate name that sticks."""
    if not hasattr(tool, "SetInput"):
        return None
    for name in names:
        try:
            tool.SetInput(name, value)
        except Exception:
            continue
        readback = _tool_input(tool, name, default=None)
        if readback is not None:
            return name
    return None


def list_clip_fusion_tools(conn, clip_name: Optional[str], comp_index: int = 1) -> List[Dict[str, Any]]:
    """List Fusion tools on the clip-attached comp."""
    _, comp = _get_clip_comp(conn, clip_name, comp_index, ensure=False)
    return _list_comp_tools(comp)


def get_primary_grade(conn, clip_name: Optional[str], comp_index: int = 1) -> Dict[str, Any]:
    """Read primary Fusion color-correction state from the first ColorCorrector tool."""
    _, comp = _get_clip_comp(conn, clip_name, comp_index, ensure=False)
    tools = _find_tools_by_type(comp, "ColorCorrector")
    if not tools:
        return {"clip": clip_name, "has_primary": False}

    tool = tools[0]
    return {
        "clip": clip_name,
        "has_primary": True,
        "tool_name": getattr(tool, "Name", "ColorCorrector"),
        "gain_r": _tool_input_aliases(tool, ["MasterRedGain", "GainRed"], 1.0),
        "gain_g": _tool_input_aliases(tool, ["MasterGreenGain", "GainGreen"], 1.0),
        "gain_b": _tool_input_aliases(tool, ["MasterBlueGain", "GainBlue"], 1.0),
        "gamma": _tool_input_aliases(tool, ["MasterRGBGamma", "MasterGamma"], 1.0),
        "saturation": _tool_input_aliases(tool, ["Saturation1", "Saturation"], 1.0),
        "master_gain": _tool_input_aliases(tool, ["MasterRGBGain", "MasterGain"], 1.0),
    }


def set_primary_grade(
    conn,
    clip_name: Optional[str],
    *,
    comp_index: int = 1,
    gain_r: Optional[float] = None,
    gain_g: Optional[float] = None,
    gain_b: Optional[float] = None,
    gamma: Optional[float] = None,
    saturation: Optional[float] = None,
    master_gain: Optional[float] = None,
) -> Dict[str, Any]:
    """Create/update a clip-attached Fusion ColorCorrector primary grade."""
    def _apply(comp):
        tools = _find_tools_by_type(comp, "ColorCorrector")
        tool = tools[0] if tools else _create_comp_tool(comp, "ColorCorrector", prefix="ColorCorrector")
        if not tools:
            _canonicalize_graph(comp, create_primary=True)
        else:
            _canonicalize_graph(comp, create_primary=False)

        updates = {
            ("MasterRedGain", "GainRed"): gain_r,
            ("MasterGreenGain", "GainGreen"): gain_g,
            ("MasterBlueGain", "GainBlue"): gain_b,
            ("MasterRGBGamma", "MasterGamma"): gamma,
            ("Saturation1", "Saturation"): saturation,
            ("MasterRGBGain", "MasterGain"): master_gain,
        }
        used_inputs: Dict[str, str] = {}
        for keys, value in updates.items():
            if value is None:
                continue
            used = _set_tool_input_aliases(tool, list(keys), value)
            if used:
                used_inputs[keys[0]] = used

        data = get_primary_grade(conn, clip_name, comp_index=comp_index)
        if used_inputs:
            data["input_map"] = used_inputs
        return data

    return _mutate_with_graph_rollback(conn, clip_name, comp_index, _apply)


CAT_METHOD_TOKENS: Dict[str, str] = {
    "bradford": "CAT_BRADFORD",
    "cat_bradford": "CAT_BRADFORD",
    "bradford_linear": "CAT_BRADFORD_LINEAR",
    "cat_bradford_linear": "CAT_BRADFORD_LINEAR",
    "cat02": "CAT_CAT02",
    "cat_02": "CAT_CAT02",
    "cat_cat02": "CAT_CAT02",
    "cmccat2000": "CAT_CMCCAT2000",
    "cmc_cat_2000": "CAT_CMCCAT2000",
    "cat_cmccat2000": "CAT_CMCCAT2000",
    "cmccat97": "CAT_CMCCAT97",
    "cmc_cat_97": "CAT_CMCCAT97",
    "cat_cmccat97": "CAT_CMCCAT97",
    "sharp": "CAT_SHARP",
    "cat_sharp": "CAT_SHARP",
    "von_kries": "CAT_VON_KRIES",
    "vonkries": "CAT_VON_KRIES",
    "cat_von_kries": "CAT_VON_KRIES",
    "xyz_scale": "CAT_XYZ_SCALE",
    "xyzscale": "CAT_XYZ_SCALE",
    "cat_xyz_scale": "CAT_XYZ_SCALE",
}

CAT_ILLUMINANT_TOKENS: Dict[str, str] = {
    value.lower().replace("illuminant::", ""): value
    for value in (
        "Illuminant::A",
        "Illuminant::ACES",
        "Illuminant::B",
        "Illuminant::C",
        "Illuminant::D50",
        "Illuminant::D55",
        "Illuminant::D60",
        "Illuminant::D65",
        "Illuminant::D75",
        "Illuminant::DCI",
        "Illuminant::E",
        "Illuminant::F1",
        "Illuminant::F2",
        "Illuminant::F3",
        "Illuminant::F4",
        "Illuminant::F5",
        "Illuminant::F6",
        "Illuminant::F7",
        "Illuminant::F8",
        "Illuminant::F9",
        "Illuminant::F10",
        "Illuminant::F11",
        "Illuminant::F12",
    )
}
CAT_ILLUMINANT_TOKENS.update({value.lower(): value for value in CAT_ILLUMINANT_TOKENS.values()})


def _normalize_cat_token(value: str | None, mapping: Dict[str, str], *, label: str) -> str:
    raw = str(value or "").strip()
    normalized = raw.lower().replace("-", "_").replace(" ", "_")
    normalized = "_".join(part for part in normalized.split("_") if part)
    token = mapping.get(raw.lower()) or mapping.get(normalized)
    if token:
        return token
    raise ValidationError(
        f"Unsupported Chromatic Adaptation {label}.",
        details={"value": value, "known": sorted(set(mapping.values()))},
        recoverability="not_applicable",
    )


def _cat_readback(tool) -> Dict[str, Any]:
    return {
        "method": _tool_input(tool, "CATMethod"),
        "source_illuminant_type": _tool_input(tool, "SourceIlluminantType"),
        "source_illuminant": _tool_input(tool, "SourceStdIlluminant"),
        "target_illuminant_type": _tool_input(tool, "TargetIlluminantType"),
        "target_illuminant": _tool_input(tool, "TargetStdIlluminant"),
        "color_space": _tool_input(tool, "ColorSpace"),
        "gamma": _tool_input(tool, "Gamma"),
        "blend": _tool_input(tool, "Blend"),
    }


def set_chromatic_adaptation(
    conn,
    clip_name: Optional[str],
    *,
    comp_index: int = 1,
    method: str = "CAT02",
    source_illuminant: str = "D65",
    target_illuminant: str = "D55",
) -> Dict[str, Any]:
    """Create/update a native Fusion ChromaticAdaptation CAT tool on a clip."""

    method_token = _normalize_cat_token(method, CAT_METHOD_TOKENS, label="method")
    source_token = _normalize_cat_token(source_illuminant, CAT_ILLUMINANT_TOKENS, label="source illuminant")
    target_token = _normalize_cat_token(target_illuminant, CAT_ILLUMINANT_TOKENS, label="target illuminant")
    requested = {
        "method": method_token,
        "source_illuminant": source_token,
        "target_illuminant": target_token,
    }

    def _apply(comp):
        tools = _find_tools_by_type(comp, "ChromaticAdaptation")
        created = False
        tool = tools[0] if tools else None
        if tool is None:
            tool = _create_comp_tool(comp, "ChromaticAdaptation", prefix="ChromaticAdaptation")
            _connect_tool_inline(comp, tool)
            created = True

        updates = {
            "CATMethod": method_token,
            "SourceIlluminantType": "Standard",
            "SourceStdIlluminant": source_token,
            "TargetIlluminantType": "Standard",
            "TargetStdIlluminant": target_token,
            "ColorSpace": "REC709_COLORSPACE",
            "Gamma": "LINEAR_GAMMA",
            "Blend": 1.0,
        }
        for input_name, value in updates.items():
            tool.SetInput(input_name, value)

        readback = _cat_readback(tool)
        expected = {
            "method": method_token,
            "source_illuminant_type": "Standard",
            "source_illuminant": source_token,
            "target_illuminant_type": "Standard",
            "target_illuminant": target_token,
            "color_space": "REC709_COLORSPACE",
            "gamma": "LINEAR_GAMMA",
        }
        mismatches = [
            {"input": name, "expected": expected_value, "actual": readback.get(name)}
            for name, expected_value in expected.items()
            if readback.get(name) != expected_value
        ]
        if mismatches:
            raise APICallFailed(
                "Chromatic Adaptation Fusion tool did not verify requested inputs.",
                details={"mismatches": mismatches, "readback": readback},
                recoverability="manual",
            )

        return {
            "action": "color.page.cat_set",
            "route": "fusion_native_chromatic_adaptation",
            "clip": clip_name,
            "tool_name": _tool_name(tool),
            "tool_type": _tool_type(tool),
            "created_tool": created,
            "requested": requested,
            "readback": readback,
            "native_tool": "Fusion ChromaticAdaptation",
        }

    return _mutate_with_graph_rollback(conn, clip_name, comp_index, _apply)


def _format_tool_row(tool, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    attrs = tool.GetAttrs() if hasattr(tool, "GetAttrs") else {}
    row = {
        "name": getattr(tool, "Name", ""),
        "type": attrs.get("TOOLS_RegID", getattr(tool, "ID", "?")),
    }
    if extra:
        row.update(extra)
    return row


def list_windows(conn, clip_name: Optional[str], comp_index: int = 1) -> List[Dict[str, Any]]:
    """List Fusion masks/windows attached to a clip comp."""
    _, comp = _get_clip_comp(conn, clip_name, comp_index, ensure=False)
    rows: List[Dict[str, Any]] = []
    for tool in _find_tools_by_type(comp, "RectangleMask"):
        rows.append(_format_tool_row(tool, {"shape": "rectangle"}))
    for tool in _find_tools_by_type(comp, "EllipseMask"):
        rows.append(_format_tool_row(tool, {"shape": "ellipse"}))
    for tool in _find_tools_by_type(comp, "PolylineMask"):
        rows.append(_format_tool_row(tool, {"shape": "polygon"}))
    return rows


def validate_window_geometry_request(
    *,
    shape: str,
    center: Any = (0.5, 0.5),
    width: Optional[float] = None,
    height: Optional[float] = None,
    softness: float = 0.0,
    comp_index: int = 1,
) -> tuple[str, tuple[float, float], float, float, float, int]:
    shape_norm = str(shape or "").strip().lower()
    if shape_norm not in {"rectangle", "ellipse", "polygon"}:
        raise ValidationError(
            "Unsupported window shape.",
            details={"shape": shape},
            recoverability="not_applicable",
        )

    requested_comp = _validate_comp_index(comp_index)
    try:
        if isinstance(center, str):
            parts = [part.strip() for part in center.split(",")]
        else:
            parts = list(center)
    except TypeError as exc:
        raise ValidationError(
            "Window center must be two comma-separated numbers.",
            details={"center": center},
            recoverability="not_applicable",
        ) from exc
    if len(parts) != 2:
        raise ValidationError(
            "Window center must be two comma-separated numbers.",
            details={"center": center},
            recoverability="not_applicable",
        )
    try:
        cx, cy = float(parts[0]), float(parts[1])
    except (TypeError, ValueError) as exc:
        raise ValidationError(
            "Window center must contain numeric values.",
            details={"center": center},
            recoverability="not_applicable",
        ) from exc
    if not math.isfinite(cx) or not math.isfinite(cy):
        raise ValidationError(
            "Window center must contain finite values.",
            details={"center": center},
            recoverability="not_applicable",
        )

    try:
        width_value = 0.5 if width is None else float(width)
    except (TypeError, ValueError) as exc:
        raise ValidationError(
            "Window width must be greater than 0.",
            details={"width": width},
            recoverability="not_applicable",
        ) from exc
    try:
        height_value = 0.5 if height is None else float(height)
    except (TypeError, ValueError) as exc:
        raise ValidationError(
            "Window height must be greater than 0.",
            details={"height": height},
            recoverability="not_applicable",
        ) from exc
    try:
        softness_value = float(softness)
    except (TypeError, ValueError) as exc:
        raise ValidationError(
            "Window softness must be non-negative.",
            details={"softness": softness},
            recoverability="not_applicable",
        ) from exc
    if not math.isfinite(width_value) or width_value <= 0:
        raise ValidationError(
            "Window width must be greater than 0.",
            details={"width": width},
            recoverability="not_applicable",
        )
    if not math.isfinite(height_value) or height_value <= 0:
        raise ValidationError(
            "Window height must be greater than 0.",
            details={"height": height},
            recoverability="not_applicable",
        )
    if not math.isfinite(softness_value) or softness_value < 0:
        raise ValidationError(
            "Window softness must be non-negative.",
            details={"softness": softness},
            recoverability="not_applicable",
        )
    return shape_norm, (cx, cy), width_value, height_value, softness_value, requested_comp


def validate_polygon_points(value: Any) -> List[Tuple[float, float]]:
    if isinstance(value, str):
        raw_points = [part.strip() for part in value.split(";") if part.strip()]
    else:
        try:
            raw_points = list(value or [])
        except TypeError as exc:
            raise ValidationError(
                "Polygon points must be formatted as 'x,y;x,y;x,y'.",
                details={"points": value},
                recoverability="not_applicable",
            ) from exc
    points: List[Tuple[float, float]] = []
    for index, raw in enumerate(raw_points, 1):
        if isinstance(raw, str):
            parts = [part.strip() for part in raw.split(",")]
        else:
            try:
                parts = list(raw)
            except TypeError as exc:
                raise ValidationError(
                    "Polygon point must contain two numeric values.",
                    details={"point": raw, "index": index},
                    recoverability="not_applicable",
                ) from exc
        if len(parts) != 2:
            raise ValidationError(
                "Polygon point must contain two numeric values.",
                details={"point": raw, "index": index},
                recoverability="not_applicable",
            )
        try:
            px, py = float(parts[0]), float(parts[1])
        except (TypeError, ValueError) as exc:
            raise ValidationError(
                "Polygon point values must be numeric.",
                details={"point": raw, "index": index},
                recoverability="not_applicable",
            ) from exc
        if not math.isfinite(px) or not math.isfinite(py):
            raise ValidationError(
                "Polygon point values must be finite.",
                details={"point": raw, "index": index},
                recoverability="not_applicable",
            )
        points.append((px, py))
    if len(points) < 3:
        raise ValidationError(
            "Polygon window requires at least three points.",
            details={"points": value, "point_count": len(points)},
            recoverability="not_applicable",
        )
    return points


def add_window(
    conn,
    clip_name: Optional[str],
    *,
    shape: str,
    center: Tuple[float, float] = (0.5, 0.5),
    width: Optional[float] = None,
    height: Optional[float] = None,
    softness: float = 0.0,
    points: Optional[List[Tuple[float, float]]] = None,
    comp_index: int = 1,
) -> Dict[str, Any]:
    """Add a Fusion mask tool to a clip comp."""
    shape_norm, center, width_value, height_value, softness_value, comp_index = validate_window_geometry_request(
        shape=shape,
        center=center,
        width=width,
        height=height,
        softness=softness,
        comp_index=comp_index,
    )
    geometry = {
        "center": [center[0], center[1]],
        "width": width_value,
        "height": height_value,
        "softness": softness_value,
    }
    polygon_points: Optional[List[Tuple[float, float]]] = None
    if shape_norm == "polygon":
        polygon_points = validate_polygon_points(points)
        geometry["points"] = [[px, py] for px, py in polygon_points]

    def _apply(comp):
        readback_geometry = geometry
        if shape_norm == "rectangle":
            tool = _create_comp_tool(comp, "RectangleMask", prefix="RectangleMask")
            if hasattr(tool, "SetInput"):
                tool.SetInput("Center", {1: center[0], 2: center[1]})
                tool.SetInput("Width", width_value)
                tool.SetInput("Height", height_value)
                tool.SetInput("SoftEdge", softness_value)
        elif shape_norm == "ellipse":
            tool = _create_comp_tool(comp, "EllipseMask", prefix="EllipseMask")
            if hasattr(tool, "SetInput"):
                tool.SetInput("Center", {1: center[0], 2: center[1]})
                tool.SetInput("Width", width_value)
                tool.SetInput("Height", height_value)
                tool.SetInput("SoftEdge", softness_value)
        elif shape_norm == "polygon":
            tool = _create_comp_tool(comp, "PolylineMask", prefix="PolygonMask")
            polyline: Dict[int, Dict[int, float]] = {}
            for i, (px, py) in enumerate(polygon_points or [], 1):
                polyline[i] = {1: px, 2: py, 3: 0.0}
            if hasattr(tool, "SetInput"):
                tool.SetInput("Polyline", polyline)
        else:
            raise ValidationError("Unsupported window shape.", details={"shape": shape})

        if shape_norm in {"rectangle", "ellipse"}:
            readback_geometry = {
                "center": _point2_input(tool, "Center"),
                "width": _tool_input(tool, "Width", default=None),
                "height": _tool_input(tool, "Height", default=None),
                "softness": _tool_input(tool, "SoftEdge", default=None),
            }

        ordered_windows = [t for t in _all_tools(comp) if _tool_type(t) in WINDOW_TOOL_TYPES]
        ordered_qualifiers = [t for t in _all_tools(comp) if _tool_type(t) in QUALIFIER_TOOL_TYPES]
        ordered_trackers = [t for t in _all_tools(comp) if _tool_type(t) in TRACKER_TOOL_TYPES]
        _canonicalize_graph(
            comp,
            include_windows=ordered_windows,
            include_qualifiers=ordered_qualifiers,
            include_trackers=ordered_trackers,
            create_primary=True,
        )
        attached_to = _get_primary_tool(comp)
        return _format_tool_row(
            tool,
            {
                "shape": shape_norm,
                "clip": clip_name,
                "geometry": readback_geometry,
                "center": readback_geometry["center"],
                "width": readback_geometry["width"],
                "height": readback_geometry["height"],
                "softness": readback_geometry["softness"],
                "points": readback_geometry.get("points"),
                "attached_to": _tool_name(attached_to) if attached_to else None,
            },
        )

    return _mutate_with_graph_rollback(conn, clip_name, comp_index, _apply)


def list_qualifiers(conn, clip_name: Optional[str], comp_index: int = 1) -> List[Dict[str, Any]]:
    """List Fusion qualifier/keyer tools with active-chain state."""
    graph = inspect_fusion_graph(conn, clip_name, comp_index=comp_index)
    active_order = {name: index + 1 for index, name in enumerate(graph.get("mask_chain") or [])}
    rows: List[Dict[str, Any]] = []
    for row in graph.get("qualifiers") or []:
        qualifier = dict(row)
        name = qualifier.get("name")
        order = active_order.get(name)
        qualifier["mode"] = "chroma"
        qualifier["order"] = order
        qualifier["active_mask_chain"] = order is not None
        qualifier["orphaned"] = order is None
        qualifier["comp_index"] = graph.get("comp_index")
        qualifier["comp_count"] = graph.get("comp_count")
        rows.append(qualifier)
    return sorted(rows, key=lambda row: (row["order"] is None, row["order"] or row.get("name") or ""))


def add_qualifier_chroma(
    conn,
    clip_name: Optional[str],
    *,
    color: str = "green",
    threshold: float = 0.3,
    comp_index: int = 1,
) -> Dict[str, Any]:
    """Add a Fusion chroma-keyer as a qualifier primitive."""
    color, threshold, comp_index = validate_qualifier_chroma_request(color, threshold, comp_index)

    def _apply(comp):
        tool = _create_comp_tool(comp, "ChromaKeyer", prefix="ChromaKeyer")
        if hasattr(tool, "SetInput"):
            tool.SetInput("KeyColor", CHROMA_KEY_COLORS[color])
            tool.SetInput("Threshold", threshold)
        ordered_windows = [t for t in _all_tools(comp) if _tool_type(t) in WINDOW_TOOL_TYPES]
        ordered_qualifiers = [t for t in _all_tools(comp) if _tool_type(t) in QUALIFIER_TOOL_TYPES]
        ordered_trackers = [t for t in _all_tools(comp) if _tool_type(t) in TRACKER_TOOL_TYPES]
        _canonicalize_graph(
            comp,
            include_windows=ordered_windows,
            include_qualifiers=ordered_qualifiers,
            include_trackers=ordered_trackers,
            create_primary=True,
        )
        attached_to = _get_primary_tool(comp)
        return _format_tool_row(
            tool,
            {
                "mode": "chroma",
                "color": color,
                "threshold": threshold,
                "clip": clip_name,
                "attached_to": _tool_name(attached_to) if attached_to else None,
            },
        )

    return _mutate_with_graph_rollback(conn, clip_name, comp_index, _apply)


def list_trackers(conn, clip_name: Optional[str], comp_index: int = 1) -> List[Dict[str, Any]]:
    """List Fusion tracker tools with active-chain state."""
    graph = inspect_fusion_graph(conn, clip_name, comp_index=comp_index)
    active_order = {name: index + 1 for index, name in enumerate(graph.get("mask_chain") or [])}
    rows: List[Dict[str, Any]] = []
    for row in graph.get("trackers") or []:
        tracker = dict(row)
        name = tracker.get("name")
        order = active_order.get(name)
        tracker["order"] = order
        tracker["active_mask_chain"] = order is not None
        tracker["orphaned"] = order is None
        tracker["comp_index"] = graph.get("comp_index")
        tracker["comp_count"] = graph.get("comp_count")
        rows.append(tracker)
    return sorted(rows, key=lambda row: (row["order"] is None, row["order"] or row.get("name") or ""))


def add_tracker(
    conn,
    clip_name: Optional[str],
    *,
    pattern_center: Tuple[float, float] = (0.5, 0.5),
    comp_index: int = 1,
) -> Dict[str, Any]:
    """Add a tracker as a wrapper over the current effect-mask chain."""
    pattern_center = validate_pattern_center(pattern_center)

    def _apply(comp):
        tool = _create_comp_tool(comp, "Tracker", prefix="Tracker")
        if hasattr(tool, "SetInput"):
            tool.SetInput("PatternCenter1", {1: pattern_center[0], 2: pattern_center[1]})
            tool.SetInput("PathCenter", 0)
            tool.SetInput("AddIntelliTrack", 1)
        ordered_windows = [t for t in _all_tools(comp) if _tool_type(t) in WINDOW_TOOL_TYPES]
        ordered_qualifiers = [t for t in _all_tools(comp) if _tool_type(t) in QUALIFIER_TOOL_TYPES]
        ordered_trackers = [t for t in _all_tools(comp) if _tool_type(t) in TRACKER_TOOL_TYPES]
        _canonicalize_graph(
            comp,
            include_windows=ordered_windows,
            include_qualifiers=ordered_qualifiers,
            include_trackers=ordered_trackers,
            create_primary=True,
        )
        attached_to = _get_primary_tool(comp)
        return _format_tool_row(
            tool,
            {
                "pattern_center": _point2_input(tool, "PatternCenter1"),
                "clip": clip_name,
                "attached_to": _tool_name(attached_to) if attached_to else None,
            },
        )

    return _mutate_with_graph_rollback(conn, clip_name, comp_index, _apply)


def reset_fusion_grading(conn, clip_name: Optional[str], *, comp_index: int = 1) -> Dict[str, Any]:
    """Remove clip-attached grading helpers and restore MediaIn -> MediaOut."""
    def _apply(comp):
        pre_graph = inspect_fusion_graph(conn, clip_name, comp_index=comp_index)
        media_in, media_out = _find_media_io(comp)
        deleted: List[str] = []
        for tool in list(_all_tools(comp)):
            if _tool_type(tool) not in COLOR_RELATED_TOOL_TYPES:
                continue
            if _delete_tool(comp, _tool_name(tool)):
                deleted.append(_tool_name(tool))
        if media_in and media_out:
            _connect_tools(media_in, media_out, "Input")
        return {
            "clip": clip_name,
            "comp_index": pre_graph.get("comp_index"),
            "comp_count": pre_graph.get("comp_count"),
            "deleted_tools": deleted,
        }

    return _mutate_with_graph_rollback(conn, clip_name, comp_index, _apply)


def preview_reset_fusion_grading(conn, clip_name: Optional[str], *, comp_index: int = 1) -> Dict[str, Any]:
    """Preview the grading helpers reset_fusion_grading would remove."""
    graph = inspect_fusion_graph(conn, clip_name, comp_index=comp_index)
    delete_rows = [row for row in graph.get("tools") or [] if row.get("type") in COLOR_RELATED_TOOL_TYPES]
    return {
        "clip": clip_name,
        "comp_index": graph.get("comp_index"),
        "comp_count": graph.get("comp_count"),
        "would_reset": True,
        "reset": False,
        "would_delete_tools": [row.get("name") for row in delete_rows],
        "tool_count": len(delete_rows),
        "preserves_comp": True,
    }


def normalize_fusion_graph(conn, clip_name: Optional[str], *, comp_index: int = 1) -> Dict[str, Any]:
    """Normalize the grading graph into the canonical no-GUI layout."""
    def _apply(comp):
        summary = _canonicalize_graph(comp, create_primary=bool([tool for tool in _all_tools(comp) if _tool_type(tool) in COLOR_RELATED_TOOL_TYPES]))
        return {"clip": clip_name, "normalized": True, **summary}

    return _mutate_with_graph_rollback(conn, clip_name, comp_index, _apply)


def repair_fusion_comp(conn, clip_name: Optional[str], *, comp_index: int = 1, prune_orphans: bool = True) -> Dict[str, Any]:
    """Repair and optionally prune orphaned grading tools."""
    def _apply(comp):
        pre_graph = inspect_fusion_graph(conn, clip_name, comp_index=comp_index)
        active_window_names = [row["name"] for row in pre_graph.get("windows") or [] if row.get("active_mask_chain")]
        active_qualifier_names = [row["name"] for row in pre_graph.get("qualifiers") or [] if row.get("active_mask_chain")]
        active_tracker_names = [row["name"] for row in pre_graph.get("trackers") or [] if row.get("active_mask_chain")]
        _canonicalize_graph(
            comp,
            include_windows=_ordered_tools_from_names(comp, active_window_names, set(WINDOW_TOOL_TYPES)),
            include_qualifiers=_ordered_tools_from_names(comp, active_qualifier_names, QUALIFIER_TOOL_TYPES),
            include_trackers=_ordered_tools_from_names(comp, active_tracker_names, TRACKER_TOOL_TYPES),
            create_primary=True,
        )
        pruned_orphans: List[str] = []
        if prune_orphans:
            for orphan in pre_graph.get("orphaned_tools") or []:
                _delete_tool(comp, orphan["name"])
            pruned_orphans = [orphan["name"] for orphan in pre_graph.get("orphaned_tools") or []]
            _canonicalize_graph(
                comp,
                include_windows=_ordered_tools_from_names(comp, active_window_names, set(WINDOW_TOOL_TYPES)),
                include_qualifiers=_ordered_tools_from_names(comp, active_qualifier_names, QUALIFIER_TOOL_TYPES),
                include_trackers=_ordered_tools_from_names(comp, active_tracker_names, TRACKER_TOOL_TYPES),
                create_primary=True,
            )
        graph = inspect_fusion_graph(conn, clip_name, comp_index=comp_index)
        return {
            "clip": clip_name,
            "repaired": True,
            "primary": graph.get("primary"),
            "windows": [row["name"] for row in graph.get("windows") or [] if row.get("active_mask_chain")],
            "qualifiers": [row["name"] for row in graph.get("qualifiers") or [] if row.get("active_mask_chain")],
            "trackers": [row["name"] for row in graph.get("trackers") or [] if row.get("active_mask_chain")],
            "pruned_orphans": pruned_orphans,
        }

    return _mutate_with_graph_rollback(conn, clip_name, comp_index, _apply)


def flatten_fusion_comp(conn, clip_name: Optional[str], *, comp_index: int = 1) -> Dict[str, Any]:
    """Keep only the primary ColorCorrector in the main image pipe and remove mask helpers."""
    def _apply(comp):
        deleted: List[str] = []
        primary_tools = [tool for tool in _all_tools(comp) if _tool_type(tool) in PRIMARY_TOOL_TYPES]
        keep_primary = primary_tools[0] if primary_tools else None
        for tool in list(_all_tools(comp)):
            tool_type = _tool_type(tool)
            name = _tool_name(tool)
            if tool_type in MASK_CHAIN_TYPES:
                if _delete_tool(comp, name):
                    deleted.append(name)
            elif tool_type in PRIMARY_TOOL_TYPES and keep_primary and tool != keep_primary:
                if _delete_tool(comp, name):
                    deleted.append(name)
        summary = _canonicalize_graph(comp, include_windows=[], include_qualifiers=[], include_trackers=[], create_primary=bool(keep_primary))
        return {"clip": clip_name, "flattened": True, "deleted_tools": deleted, **summary}

    return _mutate_with_graph_rollback(conn, clip_name, comp_index, _apply)


def export_fusion_comp(conn, clip_name: Optional[str], output_path: str, *, comp_index: int = 1) -> Dict[str, Any]:
    """Export clip-attached Fusion comp as a .setting file."""
    from . import clip_ops

    clip_ops.export_fusion_comp(conn, clip_name, comp_index, output_path)
    return {"clip": clip_name, "comp_index": comp_index, "output_path": output_path, "exported": True}


def doctor_fusion_comp(conn, clip_name: Optional[str], *, comp_index: int = 1, strict: bool = False) -> Dict[str, Any]:
    """Return graph inspection plus validation details."""
    graph = validate_fusion_graph(conn, clip_name, comp_index=comp_index, strict=strict)
    graph["doctor"] = True
    return graph


def _ordered_tools_from_names(comp, names: List[str], allowed_types: set[str]) -> List[Any]:
    tool_index = _tool_map(comp)
    ordered = []
    seen: set[str] = set()
    for name in names:
        tool = tool_index.get(name)
        if not tool or _tool_type(tool) not in allowed_types or name in seen:
            continue
        ordered.append(tool)
        seen.add(name)
    for tool in _all_tools(comp):
        name = _tool_name(tool)
        if name in seen or _tool_type(tool) not in allowed_types:
            continue
        ordered.append(tool)
    return ordered


def _tools_from_names_exact(comp, names: List[str], allowed_types: set[str]) -> List[Any]:
    tool_index = _tool_map(comp)
    ordered = []
    seen: set[str] = set()
    for name in names:
        tool = tool_index.get(name)
        if not tool or _tool_type(tool) not in allowed_types or name in seen:
            continue
        ordered.append(tool)
        seen.add(name)
    return ordered


def inspect_mask_stack(conn, clip_name: Optional[str], *, comp_index: int = 1) -> Dict[str, Any]:
    graph = inspect_fusion_graph(conn, clip_name, comp_index=comp_index)
    return {
        "clip": clip_name,
        "primary": graph.get("primary"),
        "mask_chain": graph.get("mask_chain"),
        "windows": graph.get("windows"),
        "qualifiers": graph.get("qualifiers"),
        "trackers": graph.get("trackers"),
        "orphaned_tools": graph.get("orphaned_tools"),
    }


def validate_window_attach_request(
    window_name: str,
    *,
    comp_index: int = 1,
    position: Optional[int] = None,
) -> tuple[str, int, Optional[int]]:
    normalized_window = str(window_name or "").strip()
    if not normalized_window:
        raise ValidationError(
            "Window name must not be empty.",
            details={"window": window_name},
            recoverability="not_applicable",
        )
    requested_comp = _validate_comp_index(comp_index)
    normalized_position = None
    if position is not None:
        try:
            normalized_position = int(position)
        except (TypeError, ValueError) as exc:
            raise ValidationError(
                "Window stack position must be a non-negative integer.",
                details={"position": position},
                recoverability="not_applicable",
            ) from exc
        if normalized_position < 0:
            raise ValidationError(
                "Window stack position must be a non-negative integer.",
                details={"position": position},
                recoverability="not_applicable",
            )
    return normalized_window, requested_comp, normalized_position


def attach_window(conn, clip_name: Optional[str], window_name: str, *, comp_index: int = 1, position: Optional[int] = None) -> Dict[str, Any]:
    window_name, comp_index, position = validate_window_attach_request(
        window_name,
        comp_index=comp_index,
        position=position,
    )

    def _apply(comp):
        target = _find_tool_by_name(comp, window_name)
        if not target or _tool_type(target) not in WINDOW_TOOL_TYPES:
            available_windows = [
                _tool_name(tool)
                for tool in _all_tools(comp)
                if _tool_type(tool) in WINDOW_TOOL_TYPES
            ]
            raise APICallFailed(
                "Window not found.",
                details={"window": window_name, "available_windows": available_windows},
            )
        pre_mask_chain = [_tool_name(tool) for tool in _chain_order_from_primary(_get_primary_tool(comp))]
        windows = _ordered_tools_from_names(comp, [], set(WINDOW_TOOL_TYPES))
        names = [_tool_name(tool) for tool in windows if _tool_name(tool) != window_name]
        insert_at = len(names) if position is None else min(position, len(names))
        names.insert(insert_at, window_name)
        ordered_windows = _ordered_tools_from_names(comp, names, set(WINDOW_TOOL_TYPES))
        summary = _canonicalize_graph(comp, include_windows=ordered_windows, create_primary=True)
        post_mask_chain = [_tool_name(tool) for tool in _chain_order_from_primary(_get_primary_tool(comp))]
        return {
            "clip": clip_name,
            "attached_window": window_name,
            "position": insert_at,
            "pre_mask_chain": pre_mask_chain,
            "post_mask_chain": post_mask_chain,
            **summary,
        }

    return _mutate_with_graph_rollback(conn, clip_name, comp_index, _apply)


def detach_window(conn, clip_name: Optional[str], window_name: str, *, comp_index: int = 1) -> Dict[str, Any]:
    window_name, comp_index, _ = validate_window_attach_request(window_name, comp_index=comp_index)

    def _apply(comp):
        target = _find_tool_by_name(comp, window_name)
        available_windows = [
            _tool_name(tool)
            for tool in _all_tools(comp)
            if _tool_type(tool) in WINDOW_TOOL_TYPES
        ]
        if not target or _tool_type(target) not in WINDOW_TOOL_TYPES:
            raise APICallFailed(
                "Window not found.",
                details={"window": window_name, "available_windows": available_windows},
            )

        pre_mask_chain = [_tool_name(tool) for tool in _chain_order_from_primary(_get_primary_tool(comp))]
        if window_name not in pre_mask_chain:
            raise APICallFailed(
                "Window is not attached to the active mask chain.",
                details={
                    "window": window_name,
                    "available_windows": available_windows,
                    "mask_chain": pre_mask_chain,
                },
            )

        active_window_names = [
            name
            for name in pre_mask_chain
            if name != window_name and _tool_type(_find_tool_by_name(comp, name)) in WINDOW_TOOL_TYPES
        ]
        active_qualifier_names = [
            name
            for name in pre_mask_chain
            if _tool_type(_find_tool_by_name(comp, name)) in QUALIFIER_TOOL_TYPES
        ]
        active_tracker_names = [
            name
            for name in pre_mask_chain
            if _tool_type(_find_tool_by_name(comp, name)) in TRACKER_TOOL_TYPES
        ]
        summary = _canonicalize_graph(
            comp,
            include_windows=_tools_from_names_exact(comp, active_window_names, WINDOW_TOOL_TYPES),
            include_qualifiers=_tools_from_names_exact(comp, active_qualifier_names, QUALIFIER_TOOL_TYPES),
            include_trackers=_tools_from_names_exact(comp, active_tracker_names, TRACKER_TOOL_TYPES),
            create_primary=True,
        )
        _disconnect_input(target, "EffectMask")
        post_mask_chain = [_tool_name(tool) for tool in _chain_order_from_primary(_get_primary_tool(comp))]
        return {
            "clip": clip_name,
            "detached_window": window_name,
            "pre_mask_chain": pre_mask_chain,
            "post_mask_chain": post_mask_chain,
            **summary,
        }

    return _mutate_with_graph_rollback(conn, clip_name, comp_index, _apply)
