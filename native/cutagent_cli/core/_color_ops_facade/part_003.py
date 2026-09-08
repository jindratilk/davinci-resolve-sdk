from __future__ import annotations

def reorder_windows(conn, clip_name: Optional[str], window_names: List[str], *, comp_index: int = 1) -> Dict[str, Any]:
    requested_names = [str(name).strip() for name in window_names if str(name).strip()]
    if not requested_names:
        raise ValidationError(
            "Window reorder order must include at least one window name.",
            details={"order": window_names},
            recoverability="not_applicable",
        )
    duplicate_names = sorted({name for name in requested_names if requested_names.count(name) > 1})
    if duplicate_names:
        raise ValidationError(
            "Window reorder order contains duplicate window names.",
            details={"duplicates": duplicate_names, "order": requested_names},
            recoverability="not_applicable",
        )

    def _apply(comp):
        active_chain = _chain_order_from_primary(_get_primary_tool(comp))
        active_window_names = [
            _tool_name(tool)
            for tool in active_chain
            if _tool_type(tool) in WINDOW_TOOL_TYPES
        ]
        unknown_windows = [name for name in requested_names if name not in active_window_names]
        missing_windows = [name for name in active_window_names if name not in requested_names]
        if unknown_windows or missing_windows:
            raise ValidationError(
                "Window reorder order must exactly match the active window chain.",
                details={
                    "requested_order": requested_names,
                    "active_window_order": active_window_names,
                    "unknown_windows": unknown_windows,
                    "missing_windows": missing_windows,
                },
                recoverability="not_applicable",
            )
        ordered_windows = _tools_from_names_exact(comp, requested_names, WINDOW_TOOL_TYPES)
        summary = _canonicalize_graph(comp, include_windows=ordered_windows, create_primary=True)
        return {"clip": clip_name, "window_order": [_tool_name(tool) for tool in ordered_windows], **summary}

    return _mutate_with_graph_rollback(conn, clip_name, comp_index, _apply)


def attach_qualifier(conn, clip_name: Optional[str], qualifier_name: str, *, comp_index: int = 1, position: Optional[int] = None) -> Dict[str, Any]:
    def _apply(comp):
        qualifiers = _ordered_tools_from_names(comp, [], QUALIFIER_TOOL_TYPES)
        names = [_tool_name(tool) for tool in qualifiers if _tool_name(tool) != qualifier_name]
        insert_at = len(names) if position is None else max(0, min(position, len(names)))
        names.insert(insert_at, qualifier_name)
        ordered_qualifiers = _ordered_tools_from_names(comp, names, QUALIFIER_TOOL_TYPES)
        summary = _canonicalize_graph(comp, include_qualifiers=ordered_qualifiers, create_primary=True)
        return {"clip": clip_name, "attached_qualifier": qualifier_name, **summary}

    return _mutate_with_graph_rollback(conn, clip_name, comp_index, _apply)


def detach_qualifier(conn, clip_name: Optional[str], qualifier_name: str, *, comp_index: int = 1) -> Dict[str, Any]:
    def _apply(comp):
        target = _find_tool_by_name(comp, qualifier_name)
        if not target or _tool_type(target) not in QUALIFIER_TOOL_TYPES:
            raise ValidationError(
                "Qualifier tool not found.",
                details={"qualifier": qualifier_name},
                recoverability="not_applicable",
            )
        primary = _get_primary_tool(comp)
        active_chain = _chain_order_from_primary(primary) if primary else []
        active_names = {_tool_name(tool) for tool in active_chain}
        if qualifier_name not in active_names:
            raise ValidationError(
                "Qualifier is not attached to the active mask chain.",
                details={"qualifier": qualifier_name},
                recoverability="not_applicable",
            )

        active_windows = [tool for tool in active_chain if _tool_type(tool) in WINDOW_TOOL_TYPES]
        active_qualifiers = [
            tool
            for tool in active_chain
            if _tool_type(tool) in QUALIFIER_TOOL_TYPES and _tool_name(tool) != qualifier_name
        ]
        active_trackers = [tool for tool in active_chain if _tool_type(tool) in TRACKER_TOOL_TYPES]
        summary = _canonicalize_graph(
            comp,
            include_windows=active_windows,
            include_qualifiers=active_qualifiers,
            include_trackers=active_trackers,
            create_primary=True,
        )
        for input_id in ("Input", "Solid.Matte", "Garbage.Matte", "EffectMask"):
            _disconnect_input(target, input_id)
        return {"clip": clip_name, "detached_qualifier": qualifier_name, **summary}

    return _mutate_with_graph_rollback(conn, clip_name, comp_index, _apply)


def attach_window_to_tracker(conn, clip_name: Optional[str], tracker_name: str, window_name: str, *, comp_index: int = 1) -> Dict[str, Any]:
    _, comp = _get_clip_comp(conn, clip_name, comp_index, ensure=False)
    _resolve_tracker_tool(comp, tracker_name)
    window = _find_tool_by_name(comp, window_name)
    available_windows = [_tool_name(tool) for tool in _all_tools(comp) if _tool_type(tool) in WINDOW_TOOL_TYPES]
    if not window or _tool_type(window) not in WINDOW_TOOL_TYPES:
        raise APICallFailed(
            "Window not found.",
            details={"window": window_name, "available_windows": available_windows},
        )

    def _apply(comp):
        tracker, resolved_tracker_name, tracker_resolution = _resolve_tracker_tool(comp, tracker_name)
        window = _find_tool_by_name(comp, window_name)
        primary = _get_primary_tool(comp)
        media_in, media_out = _find_media_io(comp)
        if not window or _tool_type(window) not in WINDOW_TOOL_TYPES:
            raise APICallFailed("Window not found.", details={"window": window_name})
        if not primary:
            primary = _create_comp_tool(comp, "ColorCorrector", prefix="ColorCorrector")
        if media_in:
            _connect_tools(media_in, primary, "Input")
            _connect_tools(media_in, tracker, "Input")
        if media_out:
            _connect_tools(primary, media_out, "Input")
        _connect_tools(tracker, primary, "EffectMask")

        upstream = _connected_source(tracker, "Foreground")
        if upstream and not _same_tool(upstream, window):
            _disconnect_input(window, "EffectMask")
            _connect_tools(upstream, window, "EffectMask")
        _connect_tools(window, tracker, "Foreground")

        graph = inspect_fusion_graph(conn, clip_name, comp_index=comp_index)
        data = {
            "clip": clip_name,
            **_tracker_response_fields(tracker_name, resolved_tracker_name, tracker_resolution),
            "window": window_name,
            "primary": graph.get("primary"),
            "windows": [row["name"] for row in graph.get("windows") or [] if row.get("active_mask_chain")],
            "qualifiers": [row["name"] for row in graph.get("qualifiers") or [] if row.get("active_mask_chain")],
            "trackers": [row["name"] for row in graph.get("trackers") or [] if row.get("active_mask_chain")],
        }
        return data

    return _mutate_with_graph_rollback(conn, clip_name, comp_index, _apply)


def attach_qualifier_to_tracker(conn, clip_name: Optional[str], tracker_name: str, qualifier_name: str, *, comp_index: int = 1) -> Dict[str, Any]:
    _, comp = _get_clip_comp(conn, clip_name, comp_index, ensure=False)
    _resolve_tracker_tool(comp, tracker_name)
    qualifier = _find_tool_by_name(comp, qualifier_name)
    available_qualifiers = [_tool_name(tool) for tool in _all_tools(comp) if _tool_type(tool) in QUALIFIER_TOOL_TYPES]
    if not qualifier or _tool_type(qualifier) not in QUALIFIER_TOOL_TYPES:
        raise APICallFailed(
            "Qualifier not found.",
            details={"qualifier": qualifier_name, "available_qualifiers": available_qualifiers},
        )

    def _apply(comp):
        _, resolved_tracker_name, tracker_resolution = _resolve_tracker_tool(comp, tracker_name)
        ordered_qualifiers = _ordered_tools_from_names(comp, [qualifier_name], QUALIFIER_TOOL_TYPES)
        for tool in _all_tools(comp):
            if _tool_type(tool) in QUALIFIER_TOOL_TYPES and _tool_name(tool) not in {_tool_name(q) for q in ordered_qualifiers}:
                ordered_qualifiers.append(tool)
        ordered_trackers = _ordered_tools_from_names(comp, [resolved_tracker_name], TRACKER_TOOL_TYPES)
        for tool in _all_tools(comp):
            if _tool_type(tool) in TRACKER_TOOL_TYPES and _tool_name(tool) not in {_tool_name(t) for t in ordered_trackers}:
                ordered_trackers.append(tool)
        summary = _canonicalize_graph(comp, include_qualifiers=ordered_qualifiers, include_trackers=ordered_trackers, create_primary=True)
        return {
            "clip": clip_name,
            **_tracker_response_fields(tracker_name, resolved_tracker_name, tracker_resolution),
            "qualifier": qualifier_name,
            **summary,
        }

    return _mutate_with_graph_rollback(conn, clip_name, comp_index, _apply)


def tracker_set_target(conn, clip_name: Optional[str], tracker_name: str, center: Tuple[float, float], *, comp_index: int = 1) -> Dict[str, Any]:
    center = validate_pattern_center(center)
    item, comp = _get_clip_comp(conn, clip_name, comp_index, ensure=False)
    tracker, resolved_tracker_name, tracker_resolution = _resolve_tracker_tool(comp, tracker_name)
    tracker.SetInput("PatternCenter1", {1: center[0], 2: center[1]})
    comp_count = None
    if hasattr(item, "GetFusionCompCount"):
        try:
            comp_count = int(item.GetFusionCompCount() or 0)
        except Exception:
            comp_count = None
    return {
        "clip": clip_name,
        **_tracker_response_fields(tracker_name, resolved_tracker_name, tracker_resolution),
        "pattern_center": center,
        "comp_index": comp_index,
        "comp_count": comp_count,
        "updated": True,
    }


def _tracker_track_timeout_s() -> float:
    raw = os.environ.get("CUTAGENT_TRACKER_TRACK_TIMEOUT_S", "30")
    try:
        timeout = float(raw)
    except (TypeError, ValueError):
        timeout = 30.0
    return max(2.0, timeout)


def tracker_track(conn, clip_name: Optional[str], tracker_name: str, *, direction: str, comp_index: int = 1) -> Dict[str, Any]:
    project = getattr(conn, "project", None)
    is_rendering = getattr(project, "IsRenderingInProgress", None)
    if callable(is_rendering):
        try:
            if is_rendering():
                raise APICallFailed(
                    "Cannot start Fusion tracker while DaVinci Resolve render is in progress.",
                    details={"tracker": tracker_name, "direction": direction, "render_in_progress": True},
                )
        except APICallFailed:
            raise
        except Exception:
            pass

    item, comp = _get_clip_comp(conn, clip_name, comp_index, ensure=False)
    if _comp_is_rendering(comp):
        raise APICallFailed(
            "Cannot start Fusion tracker while the clip composition is already rendering.",
            details={"tracker": tracker_name, "direction": direction, "comp_rendering": True},
        )

    tracker, resolved_tracker_name, tracker_resolution = _resolve_tracker_tool(comp, tracker_name)
    command_input = "TrackForward" if direction == "forward" else "TrackReverse"
    tracker.SetInput(command_input, 1)
    timeout_s = _tracker_track_timeout_s()
    if not _wait_for_comp_render_idle(comp, timeout_s=timeout_s):
        stop_tracking = getattr(tracker, "SetInput", None)
        stop_attempted = False
        if callable(stop_tracking):
            try:
                stop_tracking("StopTracking", 1)
                stop_attempted = True
            except Exception:
                stop_attempted = False
        if stop_attempted and _wait_for_comp_render_idle(comp, timeout_s=3.0):
            raise APICallFailed(
                "Fusion tracker did not complete within timeout and tracking was stopped before DaVinci Resolve reported a warning modal.",
                details={
                    "tracker": resolved_tracker_name,
                    "requested_tracker": tracker_name,
                    "direction": direction,
                    "timeout_s": timeout_s,
                    "comp_rendering_stopped": True,
                    "modal_warning_possible": False,
                },
            )
        abort_render = getattr(comp, "AbortRender", None)
        if callable(abort_render):
            try:
                abort_render()
            except Exception:
                pass
        abort_render_ui = getattr(comp, "AbortRenderUI", None)
        if callable(abort_render_ui):
            try:
                abort_render_ui()
            except Exception:
                pass
        raise APICallFailed(
            "Fusion tracker did not complete within timeout; DaVinci Resolve may show a render warning modal.",
            details={
                "tracker": resolved_tracker_name,
                "requested_tracker": tracker_name,
                "direction": direction,
                "timeout_s": timeout_s,
                "stop_tracking_attempted": stop_attempted,
                "comp_rendering_aborted": True,
                "modal_warning_possible": True,
            },
            recoverability="manual",
        )
    comp_count = None
    if hasattr(item, "GetFusionCompCount"):
        try:
            comp_count = int(item.GetFusionCompCount() or 0)
        except Exception:
            comp_count = None
    return {
        "clip": clip_name,
        **_tracker_response_fields(tracker_name, resolved_tracker_name, tracker_resolution),
        "direction": direction,
        "triggered": True,
        "completed": True,
        "comp_index": comp_index,
        "comp_count": comp_count,
        "timeout_s": timeout_s,
        "modal_warning_possible": False,
    }


def secondary_create(
    conn,
    clip_name: Optional[str],
    *,
    window_shape: Optional[str] = None,
    qualifier_color: Optional[str] = None,
    qualifier_threshold: float = 0.3,
    track: bool = False,
    pattern_center: Tuple[float, float] = (0.5, 0.5),
    comp_index: int = 1,
) -> Dict[str, Any]:
    window_shape, qualifier_color, qualifier_threshold, track, pattern_center, comp_index = validate_secondary_create_request(
        window_shape=window_shape,
        qualifier_color=qualifier_color,
        qualifier_threshold=qualifier_threshold,
        track=track,
        pattern_center=pattern_center,
        comp_index=comp_index,
    )
    created: Dict[str, Any] = {
        "clip": clip_name,
        "requested": {
            "window": window_shape,
            "qualifier_color": qualifier_color,
            "track": track,
            "pattern_center": pattern_center,
            "comp_index": comp_index,
        },
    }
    expected_names: Dict[str, str] = {}
    if window_shape:
        window_result = add_window(conn, clip_name, shape=window_shape, comp_index=comp_index)
        expected_names["window"] = window_result["name"]
    if qualifier_color:
        qualifier_result = add_qualifier_chroma(
            conn,
            clip_name,
            color=qualifier_color,
            threshold=qualifier_threshold,
            comp_index=comp_index,
        )
        expected_names["qualifier"] = qualifier_result["name"]
    if track:
        tracker_result = add_tracker(conn, clip_name, pattern_center=pattern_center, comp_index=comp_index)
        expected_names["tracker"] = tracker_result["name"]
    graph = validate_fusion_graph(conn, clip_name, comp_index=comp_index)
    row_sets = {
        "window": [row for row in graph.get("windows") or [] if row.get("active_mask_chain")],
        "qualifier": [row for row in graph.get("qualifiers") or [] if row.get("active_mask_chain")],
        "tracker": [row for row in graph.get("trackers") or [] if row.get("active_mask_chain")],
    }
    for key, expected_name in expected_names.items():
        row = next((candidate for candidate in row_sets[key] if candidate.get("name") == expected_name), None)
        if row is None:
            raise APICallFailed(
                f"Secondary {key} was not attached after creation.",
                details={"expected": expected_name, "active": [candidate.get("name") for candidate in row_sets[key]]},
            )
        created[key] = row
    created["created"] = expected_names
    created["graph"] = graph
    return created


def inspect_color(conn, clip_name: Optional[str], *, node_stack_layer_index: int = 1) -> Dict[str, Any]:
    """Aggregate native Color page and clip-attached Fusion grading state."""
    item = resolve_item(conn, clip_name)
    resolved_clip = clip_name
    if resolved_clip is None and hasattr(item, "GetName"):
        try:
            resolved_clip = item.GetName()
        except Exception:
            resolved_clip = None
    data: Dict[str, Any] = {"clip": resolved_clip, "node_stack_layer_index": node_stack_layer_index}
    data["node_count"] = get_num_nodes(conn, clip_name, node_stack_layer_index=node_stack_layer_index)
    nodes: List[Dict[str, Any]] = []
    for i in range(1, data["node_count"] + 1):
        row: Dict[str, Any] = {"index": i}
        try:
            row["label"] = get_node_label(conn, clip_name, i, node_stack_layer_index=node_stack_layer_index)
        except Exception:
            row["label"] = ""
        try:
            row["lut"] = get_node_lut(conn, clip_name, i, node_stack_layer_index=node_stack_layer_index)
        except Exception:
            row["lut"] = ""
        try:
            row["tools"] = get_tools_in_node(conn, clip_name, i, node_stack_layer_index=node_stack_layer_index)
        except Exception:
            row["tools"] = []
        nodes.append(row)
    data["nodes"] = nodes
    data["cdl"] = get_cdl(conn, clip_name)
    try:
        data["versions"] = list_color_versions(conn, clip_name)
    except Exception:
        data["versions"] = []
    try:
        data["color_group"] = get_color_group(conn, clip_name)
    except Exception:
        data["color_group"] = {"group_name": None}
    try:
        fusion_tools = list_clip_fusion_tools(conn, clip_name)
        data["fusion"] = {
            "comp_count": 1 if fusion_tools else 0,
            "tools": fusion_tools,
            "primary": get_primary_grade(conn, clip_name),
            "windows": list_windows(conn, clip_name),
            "qualifiers": list_qualifiers(conn, clip_name),
            "trackers": list_trackers(conn, clip_name),
        }
    except Exception as exc:
        data["fusion"] = {"comp_count": 0, "error": str(exc), "tools": []}
    return data


def export_clip_lut(conn, clip_name: Optional[str], export_type: int, output_path: str) -> Dict[str, Any]:
    """Export the current clip grade as LUT from the Color page context."""
    with _with_required_page(conn, "color"):
        item = resolve_item(conn, clip_name)
        resolved_clip = clip_name
        if resolved_clip is None and hasattr(item, "GetName"):
            try:
                resolved_clip = item.GetName()
            except Exception:
                resolved_clip = None
        exporter = getattr(item, "ExportLUT", None)
        if not callable(exporter):
            raise APICallFailed("ExportLUT not available.", details={"clip": resolved_clip})
        result = exporter(export_type, output_path)
        if result is False:
            raise APICallFailed(
                "ExportLUT failed.",
                details={"clip": resolved_clip, "export_type": export_type, "output_path": output_path},
            )
        return {"clip": resolved_clip, "export_type": export_type, "output_path": output_path, "exported": True}


# --- Delegated color group / LUT / node / version / gallery operations ---

def _ops_module():
    return sys.modules[__name__]


def _get_color_group_obj(conn, group_name: str):
    return _groups._get_color_group_obj(conn, group_name)


def list_color_groups(conn) -> List[Dict[str, Any]]:
    return _groups.list_color_groups(conn)


def add_color_group(conn, group_name: str) -> bool:
    return _groups.add_color_group(conn, group_name)


def delete_color_group(conn, group_name: str) -> bool:
    return _groups.delete_color_group(conn, group_name, ops_module=_ops_module())


def get_color_group(conn, clip_name: Optional[str]) -> Dict[str, Any]:
    return _groups.get_color_group(conn, clip_name, ops_module=_ops_module())


def assign_to_color_group(conn, clip_name: Optional[str], group_name: str) -> bool:
    return _groups.assign_to_color_group(conn, clip_name, group_name, ops_module=_ops_module())


def remove_from_color_group(conn, clip_name: Optional[str]) -> bool:
    return _groups.remove_from_color_group(conn, clip_name, ops_module=_ops_module())


def get_name(conn, group_name: str) -> str:
    return _groups.get_name(conn, group_name, ops_module=_ops_module())


def set_name(conn, group_name: str, new_name: str) -> bool:
    return _groups.set_name(conn, group_name, new_name, ops_module=_ops_module())


def rename_color_group(conn, group_name: str, new_name: str) -> Dict[str, Any]:
    """Rename a color group."""
    result = set_name(conn, group_name, new_name)
    if result is False:
        raise APICallFailed("Failed to rename color group.", details={"group": group_name, "new_name": new_name})
    return {"old_name": group_name, "name": new_name, "renamed": bool(result)}


def get_clips_in_timeline(conn, group_name: str) -> List[Dict[str, Any]]:
    return _groups.get_clips_in_timeline(conn, group_name, ops_module=_ops_module())


def get_color_group_clips(conn, group_name: str) -> Dict[str, Any]:
    """Return timeline clips assigned to a color group."""
    return {"group": group_name, "clips": get_clips_in_timeline(conn, group_name)}


def _color_group_graph_summary(group_name: str, graph_type: str, graph: Any) -> Dict[str, Any]:
    return _groups._color_group_graph_summary(group_name, graph_type, graph)


def get_pre_clip_node_graph(conn, group_name: str) -> Dict[str, Any]:
    return _groups.get_pre_clip_node_graph(conn, group_name, ops_module=_ops_module())


def get_post_clip_node_graph(conn, group_name: str) -> Dict[str, Any]:
    return _groups.get_post_clip_node_graph(conn, group_name, ops_module=_ops_module())


def _normalize_lut_key(value: str) -> str:
    return _luts._normalize_lut_key(value)


def _dedupe_strings(values: List[str]) -> List[str]:
    return _luts._dedupe_strings(values)


def _resolve_lut_roots() -> List[str]:
    return _luts._resolve_lut_roots(ops_module=_ops_module())


def _relative_lut_key_for_known_root(path: str) -> Optional[str]:
    return _luts._relative_lut_key_for_known_root(path, ops_module=_ops_module())


def _refresh_lut_list_best_effort(conn) -> Optional[str]:
    return _luts._refresh_lut_list_best_effort(conn, ops_module=_ops_module())


def _install_lut_for_resolve(conn, source_path: str) -> Tuple[str, str, Optional[str]]:
    return _luts._install_lut_for_resolve(conn, source_path, ops_module=_ops_module())


def _lut_path_candidates(conn, lut_path: str) -> Dict[str, Any]:
    return _luts._lut_path_candidates(conn, lut_path, ops_module=_ops_module())


def _set_lut_with_candidates(conn, setter, node_index: int, lut_path: str, getter=None) -> Tuple[str, Dict[str, Any]]:
    return _luts._set_lut_with_candidates(conn, setter, node_index, lut_path, ops_module=_ops_module(), getter=getter)


def get_lut_info(conn, clip_name: Optional[str], node: int, *, node_stack_layer_index: int = 1) -> Dict[str, Any]:
    return _luts.get_lut_info(conn, clip_name, node, node_stack_layer_index=node_stack_layer_index, ops_module=_ops_module())


def set_lut(conn, clip_name: Optional[str], node: int, path: str, *, node_stack_layer_index: int = 1) -> bool:
    return _luts.set_lut(conn, clip_name, node, path, node_stack_layer_index=node_stack_layer_index, ops_module=_ops_module())


def clear_lut(conn, clip_name: Optional[str], node: int, *, node_stack_layer_index: int = 1) -> bool:
    return _luts.clear_lut(conn, clip_name, node, node_stack_layer_index=node_stack_layer_index, ops_module=_ops_module())


def import_lut_library(
    conn,
    source_path: str,
    *,
    folder: str = "CutAgent/Imported",
    overwrite: bool = False,
    apply: bool = False,
    apply_clip_name: Optional[str] = None,
    apply_node: int = 1,
    apply_lut_key: Optional[str] = None,
) -> Dict[str, Any]:
    return _luts.import_lut_library(
        conn,
        source_path,
        folder=folder,
        overwrite=overwrite,
        apply=apply,
        apply_clip_name=apply_clip_name,
        apply_node=apply_node,
        apply_lut_key=apply_lut_key,
        ops_module=_ops_module(),
    )


def get_cdl(conn, clip_name: Optional[str], *, node_index: int = 1) -> Dict[str, Any]:
    return _cdl.get_cdl(conn, clip_name, ops_module=_ops_module(), node_index=node_index)


def _parse_cdl_triplet(name: str, value: str) -> str:
    return _cdl._parse_cdl_triplet(name, value)


def _cdl_payload_variants(cdl_dict: Dict[str, Any], node_index: int) -> List[Dict[str, Any]]:
    return _cdl._cdl_payload_variants(cdl_dict, node_index)


def validate_cdl_payload(
    node: int,
    slope: Optional[str] = None,
    offset: Optional[str] = None,
    power: Optional[str] = None,
    saturation: Optional[float] = None,
) -> tuple[int, Dict[str, Any]]:
    return _cdl.validate_cdl_payload(node, slope, offset, power, saturation)


def set_cdl(
    conn,
    clip_name: Optional[str],
    node: int,
    slope: Optional[str] = None,
    offset: Optional[str] = None,
    power: Optional[str] = None,
    saturation: Optional[float] = None,
) -> bool:
    return _cdl.set_cdl(
        conn,
        clip_name,
        node,
        slope=slope,
        offset=offset,
        power=power,
        saturation=saturation,
        ops_module=_ops_module(),
    )


def set_cdl_db(
    conn,
    clip_name: Optional[str],
    node: int,
    slope: Optional[str] = None,
    offset: Optional[str] = None,
    power: Optional[str] = None,
    saturation: Optional[float] = None,
) -> Dict[str, Any]:
    return _cdl.set_cdl_db(
        conn,
        clip_name,
        node,
        slope=slope,
        offset=offset,
        power=power,
        saturation=saturation,
    )


def _parse_wheels_triplet(name: str, value: Optional[str]) -> Optional[tuple[float, float, float]]:
    return _cdl._parse_wheels_triplet(name, value)


def _clamp01(value: float) -> float:
    return _cdl._clamp01(value)


def _curves_from_wheels(
    lift: tuple[float, float, float],
    gamma: tuple[float, float, float],
    gain: tuple[float, float, float],
) -> dict[str, str]:
    return _cdl._curves_from_wheels(lift, gamma, gain)


def validate_wheels_request(
    *,
    node: int = 1,
    lift: Optional[str] = None,
    gamma: Optional[str] = None,
    gain: Optional[str] = None,
    sat: Optional[float] = None,
    mode: str = "cdl",
    lut_output: Optional[str] = None,
) -> Dict[str, Any]:
    return _cdl.validate_wheels_request(
        node=node,
        lift=lift,
        gamma=gamma,
        gain=gain,
        sat=sat,
        mode=mode,
        lut_output=lut_output,
        ops_module=_ops_module(),
    )


def emulate_wheels(
    conn,
    clip_name: Optional[str],
    *,
    node: int = 1,
    lift: Optional[str] = None,
    gamma: Optional[str] = None,
    gain: Optional[str] = None,
    sat: Optional[float] = None,
    mode: str = "cdl",
    lut_output: Optional[str] = None,
    verify_project_db: bool = True,
) -> Dict[str, Any]:
    return _cdl.emulate_wheels(
        conn,
        clip_name,
        node=node,
        lift=lift,
        gamma=gamma,
        gain=gain,
        sat=sat,
        mode=mode,
        lut_output=lut_output,
        verify_project_db=verify_project_db,
        ops_module=_ops_module(),
    )


def _get_node_graph(conn, clip_name: Optional[str], *, node_stack_layer_index: int = 1):
    return _nodes._get_node_graph(conn, clip_name, node_stack_layer_index=node_stack_layer_index, ops_module=_ops_module())


def get_num_nodes(conn, clip_name: Optional[str], *, node_stack_layer_index: int = 1) -> int:
    return _nodes.get_num_nodes(conn, clip_name, node_stack_layer_index=node_stack_layer_index, ops_module=_ops_module())


def _validate_node_index_for_graph(graph, clip_name: Optional[str], node_index: int) -> int:
    return _nodes._validate_node_index_for_graph(graph, clip_name, node_index)


def validate_node_index(conn, clip_name: Optional[str], node_index: int, *, node_stack_layer_index: int = 1) -> int:
    return _nodes.validate_node_index(conn, clip_name, node_index, node_stack_layer_index=node_stack_layer_index, ops_module=_ops_module())


def set_node_lut(conn, clip_name: Optional[str], node_index: int, lut_path: str, *, node_stack_layer_index: int = 1) -> bool:
    return _nodes.set_node_lut(conn, clip_name, node_index, lut_path, node_stack_layer_index=node_stack_layer_index, ops_module=_ops_module())


def get_node_lut(conn, clip_name: Optional[str], node_index: int, *, node_stack_layer_index: int = 1) -> str:
    return _nodes.get_node_lut(conn, clip_name, node_index, node_stack_layer_index=node_stack_layer_index, ops_module=_ops_module())


def set_node_cache_mode(conn, clip_name: Optional[str], node_index: int, cache_value: int, *, node_stack_layer_index: int = 1) -> bool:
    return _nodes.set_node_cache_mode(conn, clip_name, node_index, cache_value, node_stack_layer_index=node_stack_layer_index, ops_module=_ops_module())


def get_node_cache_mode(conn, clip_name: Optional[str], node_index: int, *, node_stack_layer_index: int = 1) -> Dict[str, Any]:
    return _nodes.get_node_cache_mode(conn, clip_name, node_index, node_stack_layer_index=node_stack_layer_index, ops_module=_ops_module())


def get_node_label(conn, clip_name: Optional[str], node_index: int, *, node_stack_layer_index: int = 1) -> str:
    return _nodes.get_node_label(conn, clip_name, node_index, node_stack_layer_index=node_stack_layer_index, ops_module=_ops_module())


def set_node_label(conn, clip_name: Optional[str], node_index: int, label: str, *, node_stack_layer_index: int = 1) -> bool:
    return _nodes.set_node_label(conn, clip_name, node_index, label, node_stack_layer_index=node_stack_layer_index, ops_module=_ops_module())


def get_tools_in_node(conn, clip_name: Optional[str], node_index: int, *, node_stack_layer_index: int = 1) -> List[str]:
    return _nodes.get_tools_in_node(conn, clip_name, node_index, node_stack_layer_index=node_stack_layer_index, ops_module=_ops_module())


def set_node_enabled(conn, clip_name: Optional[str], node_index: int, is_enabled: bool, *, node_stack_layer_index: int = 1) -> bool:
    return _nodes.set_node_enabled(conn, clip_name, node_index, is_enabled, node_stack_layer_index=node_stack_layer_index, ops_module=_ops_module())


def apply_grade_from_drx(conn, clip_name: Optional[str], drx_path: str, grade_mode: int = 0, *, node_stack_layer_index: int = 1) -> bool:
    return _nodes.apply_grade_from_drx(conn, clip_name, drx_path, grade_mode, node_stack_layer_index=node_stack_layer_index, ops_module=_ops_module())


def apply_arri_cdl_lut(conn, clip_name: Optional[str], *, node_stack_layer_index: int = 1) -> Dict[str, Any]:
    return _nodes.apply_arri_cdl_lut(conn, clip_name, node_stack_layer_index=node_stack_layer_index, ops_module=_ops_module())


def reset_all_grades(conn, clip_name: Optional[str], *, node_stack_layer_index: int = 1) -> bool:
    return _nodes.reset_all_grades(conn, clip_name, node_stack_layer_index=node_stack_layer_index, ops_module=_ops_module())


def copy_grade(conn, source_name: str, target_names: List[str]) -> List[str]:
    return _nodes.copy_grade(conn, source_name, target_names, ops_module=_ops_module())


def apply_grade_from_file(
    conn,
    clip_name: Optional[str],
    path: str,
    mode: int = 0,
    *,
    node_stack_layer_index: int = 1,
) -> bool:
    return _nodes.apply_grade_from_file(conn, clip_name, path, mode, node_stack_layer_index=node_stack_layer_index, ops_module=_ops_module())


def list_color_versions(conn, clip_name: Optional[str]) -> List[Dict[str, str]]:
    return _versions.list_color_versions(conn, clip_name, ops_module=_ops_module())


def add_color_version(
    conn,
    clip_name: Optional[str],
    name: str,
    remote: bool = False,
) -> bool:
    return _versions.add_color_version(conn, clip_name, name, remote, ops_module=_ops_module())


def load_color_version(
    conn,
    clip_name: Optional[str],
    name: str,
    remote: bool = False,
) -> Dict[str, Any]:
    return _versions.load_color_version(conn, clip_name, name, remote, ops_module=_ops_module())


def _get_color_version_names(item, version_type: int) -> List[str]:
    return _versions._get_color_version_names(item, version_type)


def _current_color_version(item) -> Tuple[Optional[str], Optional[int]]:
    return _versions._current_color_version(item)


def _load_color_version_for_delete(item, name: str, version_type: int, *, reason: str) -> str:
    return _versions._load_color_version_for_delete(item, name, version_type, reason=reason)


def delete_color_version(
    conn,
    clip_name: Optional[str],
    name: str,
    remote: bool = False,
) -> Dict[str, Any]:
    return _versions.delete_color_version(conn, clip_name, name, remote, ops_module=_ops_module())


def refresh_lut_list(conn) -> bool:
    return _luts.refresh_lut_list(conn)


def _get_gallery(conn):
    return _gallery._get_gallery(conn)


def _get_current_album(conn):
    return _gallery._get_current_album(conn)


def list_gallery_albums(conn) -> List[Dict[str, str]]:
    return _gallery.list_gallery_albums(conn)


def get_current_album_info(conn) -> Dict[str, Any]:
    return _gallery.get_current_album_info(conn)


def switch_gallery_album(conn, name: str) -> bool:
    return _gallery.switch_gallery_album(conn, name)


def list_gallery_stills(conn) -> List[Dict[str, Any]]:
    return _gallery.list_gallery_stills(conn)


def grab_still(conn) -> bool:
    return _gallery.grab_still(conn, ops_module=_ops_module())


def _resolve_still_selector(stills: List[Any], selector: str) -> Any:
    target_album = _gallery._get_current_album(_ops_module().resolve if hasattr(_ops_module(), "resolve") else None)
    return _gallery._resolve_still_selector(stills, selector, target_album=target_album)


def export_still(conn, selector: str, output_path_or_dir: str, fmt: str = "drx") -> Dict[str, Any]:
    return _gallery.export_still(conn, selector, output_path_or_dir, fmt=fmt)


def import_stills(conn, path: str) -> Dict[str, Any]:
    return _gallery.import_stills(conn, path)


def _export_still_to_drx(conn, still: Any) -> str:
    return _gallery._export_still_to_drx(conn, still)


def apply_still(
    conn,
    selector: str,
    clip_name: Optional[str] = None,
    mode: int = 0,
    album: Optional[str] = None,
) -> Dict[str, Any]:
    return _gallery.apply_still(conn, selector, clip_name=clip_name, mode=mode, album=album, ops_module=_ops_module())


def list_power_grades(conn) -> List[Dict[str, Any]]:
    return _gallery.list_power_grades(conn)


def _power_grade_rows(conn) -> List[Dict[str, Any]]:
    return _gallery._power_grade_rows(conn)


def _public_power_grade_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return _gallery._public_power_grade_rows(rows)


def _resolve_power_grade_row(rows: List[Dict[str, Any]], selector: str) -> Dict[str, Any]:
    return _gallery._resolve_power_grade_row(rows, selector)


def apply_power_grade(conn, selector: str, clip_name: Optional[str] = None, mode: int = 0) -> Dict[str, Any]:
    return _gallery.apply_power_grade(conn, selector, clip_name=clip_name, mode=mode, ops_module=_ops_module())
