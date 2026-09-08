from __future__ import annotations

@comp_app.command("delete")
@handle_errors
def comp_delete(
    index: int = typer.Argument(1, help="Composition index"),
    clip_name: Optional[str] = typer.Option(None, "--clip", help="Clip name (current clip when omitted)"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
):
    """Delete a Fusion composition from the current or named timeline clip."""
    if index < 1:
        raise ValidationError(
            "Composition index must be 1 or greater.",
            details={"argument": "index", "value": index, "min": 1},
        )
    enforce_mutation_policy(
        "clip.fusion_comp",
        intended_engine="api_native",
        mutating=not is_dry_run(),
    )
    if index < 1:
        raise ValidationError("Fusion composition index must be 1 or greater.", details={"index": index})
    if is_dry_run():
        preflight_command = (
            f'cutagent clip fusion list "{clip_name}" --json'
            if clip_name
            else "cutagent clip fusion list --json"
        )
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            {
                "message": f"DRY-RUN: Would delete Fusion composition {index} from '{clip_name or 'current clip'}'.",
                "action": "fusion.comp.delete",
                "would_delete": True,
                "dry_run": True,
                "clip": clip_name,
                "target": "named_clip" if clip_name else "current_clip",
                "index": index,
                "route": "timeline_item.DeleteFusionCompByName",
                "preflight_command": preflight_command,
                "readback_command": preflight_command,
                "preflight_readback": "clip fusion tools --clip <name>",
                "requires_resolvable_clip": True,
            },
            title="Fusion Composition Delete Plan",
        )
        return
    require_force_for_machine_mode(
        force=force,
        action="fusion.comp.delete",
        target_kind="fusion_composition",
        target_name=clip_name or "current_clip",
        prompt=f"Delete Fusion composition {index} from '{clip_name or 'current clip'}'?",
        details={"index": index},
    )
    conn = get_connection(require_timeline=True)
    clip_ops.delete_fusion_comp(conn, clip_name, index)
    output(
        {
            "action": "fusion.comp.delete",
            "clip": clip_name,
            "index": index,
            "deleted": True,
            "route": "timeline_item.DeleteFusionCompByName",
        },
        title="Fusion Composition Delete",
    )


@comp_app.command("rename")
@handle_errors
def comp_rename(
    new_name: str = typer.Argument(..., help="New composition name"),
    index: int = typer.Option(1, "--index", "-i", help="Composition index"),
    clip_name: Optional[str] = typer.Option(None, "--clip", help="Clip name (current clip when omitted)"),
):
    """Rename a Fusion composition on the current or named timeline clip."""
    if index < 1:
        raise ValidationError(
            "Composition index must be 1 or greater.",
            details={"argument": "index", "value": index, "min": 1},
        )
    enforce_mutation_policy(
        "clip.fusion_comp",
        intended_engine="api_native",
        mutating=not is_dry_run(),
    )
    if not str(new_name or "").strip():
        raise ValidationError(
            "Fusion comp rename requires NEW_NAME.",
            details={
                "new_name": new_name,
                "example": 'cutagent fusion comp rename "Clean Plate" --index 1 --clip "Interview A" --json',
            },
        )
    if index < 1:
        raise ValidationError("Fusion composition index must be 1 or greater.", details={"index": index})
    if is_dry_run():
        preflight_command = (
            f'cutagent clip fusion list "{clip_name}" --json'
            if clip_name
            else "cutagent clip fusion list --json"
        )
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            {
                "message": f"DRY-RUN: Would rename Fusion composition {index} on '{clip_name or 'current clip'}' to '{new_name}'.",
                "action": "fusion.comp.rename",
                "would_rename": True,
                "dry_run": True,
                "clip": clip_name,
                "target": "named_clip" if clip_name else "current_clip",
                "index": index,
                "new_name": str(new_name),
                "route": "timeline_item.RenameFusionCompByName",
                "preflight_command": preflight_command,
                "readback_command": preflight_command,
                "preflight_readback": "clip fusion tools --clip <name>",
                "requires_resolvable_clip": True,
            },
            title="Fusion Composition Rename Plan",
        )
        return
    conn = get_connection(require_timeline=True)
    data = clip_ops.rename_fusion_comp(conn, clip_name, index, str(new_name))
    output({"action": "fusion.comp.rename", "clip": clip_name, **data}, title="Fusion Composition Rename")


# === Tool Commands ===

tool_app = typer.Typer(help="Tool operations (add, delete, connect, configure).")
app.add_typer(tool_app, name="tool")

node_app = typer.Typer(help="Node aliases for Fusion tool operations.")
app.add_typer(node_app, name="node")

image_app = typer.Typer(help="Fusion image source injection for existing templates/tools.")
app.add_typer(image_app, name="image")

text_app = typer.Typer(help="Fusion/Text+ text update helpers.")
app.add_typer(text_app, name="text")

nested_text_app = typer.Typer(help="Nested compound/text timeline updates.")
app.add_typer(nested_text_app, name="nested-text")


def _list_option(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def _image_transform_payload(
    *,
    zoom_x: float | None = None,
    zoom_y: float | None = None,
    pan: float | None = None,
    tilt: float | None = None,
    position_x: float | None = None,
    position_y: float | None = None,
) -> dict[str, Any]:
    return {
        "zoom_x": zoom_x,
        "zoom_y": zoom_y,
        "pan": pan,
        "tilt": tilt,
        "position_x": position_x,
        "position_y": position_y,
    }


def _run_image_set_entry(conn: Any, entry: dict[str, Any]) -> dict[str, Any]:
    item, selector = _resolve_timeline_item(
        conn,
        clip_name=_normalize_optional_string(entry.get("clip")),
        track=entry.get("track"),
        record_frame=entry.get("record_frame"),
    )
    data = fusion_image_ops.set_image_on_item(
        conn,
        item,
        str(entry.get("image_path") or entry.get("image") or ""),
        group_tool_name=_normalize_optional_string(entry.get("group_tool")),
        group_input_name=_normalize_optional_string(entry.get("group_input")),
        group_inputs=entry.get("group_inputs") if isinstance(entry.get("group_inputs"), dict) else None,
        import_media=bool(entry.get("import_media", True)),
        transform=_image_transform_payload(
            zoom_x=entry.get("zoom_x"),
            zoom_y=entry.get("zoom_y"),
            pan=entry.get("pan"),
            tilt=entry.get("tilt"),
            position_x=entry.get("position_x"),
            position_y=entry.get("position_y"),
        ),
    )
    return {
        "clip": _media_pool_item_name(item) or _normalize_optional_string(entry.get("clip")) or None,
        "selector": selector,
        **data,
    }


@image_app.command("set")
@handle_errors
def image_set(
    image_path: str = typer.Option(..., "--image", "--image-path", help="Local image file to inject"),
    clip_name: str | None = typer.Option(None, "--clip", help="Clip name selector"),
    track: int | None = typer.Option(None, "--track", min=1, help="Video track index selector"),
    record_frame: str | None = typer.Option(None, "--record-frame", help="Record-domain point selector"),
    group_tool: str | None = typer.Option(None, "--group-tool", help="Preferred group tool name"),
    group_input: str | None = typer.Option(None, "--group-input", help="Preferred group input name"),
    import_media: bool = typer.Option(True, "--import-media/--no-import-media", help="Import image into Media Pool before MediaID assignment"),
    zoom_x: float | None = typer.Option(None, "--zoom-x", help="Transform ZoomX value"),
    zoom_y: float | None = typer.Option(None, "--zoom-y", help="Transform ZoomY value"),
    pan: float | None = typer.Option(None, "--pan", help="Transform Pan value"),
    tilt: float | None = typer.Option(None, "--tilt", help="Transform Tilt value"),
    position_x: float | None = typer.Option(None, "--position-x", help="Alias for Pan"),
    position_y: float | None = typer.Option(None, "--position-y", help="Alias for Tilt"),
):
    """Set an image path/media source on Fusion tools inside a timeline item."""
    set_execution_engine("api_native")
    enforce_mutation_policy("fusion.mutation", intended_engine="api_native", mutating=not is_dry_run())
    normalized_path = fusion_image_ops.validate_image_path(image_path)
    selector = _selector_payload(clip_name=_normalize_optional_string(clip_name), track=track, record_frame=record_frame)
    transform = _image_transform_payload(
        zoom_x=zoom_x,
        zoom_y=zoom_y,
        pan=pan,
        tilt=tilt,
        position_x=position_x,
        position_y=position_y,
    )
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            mutation_payload(
                action="fusion.image.set",
                target={"kind": "timeline_item", "name": selector.get("clip") or "current"},
                changed=False,
                clip=_normalize_optional_string(clip_name),
                **fusion_image_ops.build_image_set_plan(
                    selector=selector,
                    image_path=normalized_path,
                    group_tool_name=group_tool,
                    group_input_name=group_input,
                    import_media=import_media,
                    transform=transform,
                ),
                dry_run=True,
            ),
            title="Fusion Image Set Plan",
        )
        return

    conn = get_connection(require_timeline=True)
    data = _run_image_set_entry(
        conn,
        {
            "clip": clip_name,
            "track": track,
            "record_frame": record_frame,
            "image_path": normalized_path,
            "group_tool": group_tool,
            "group_input": group_input,
            "import_media": import_media,
            **transform,
        },
    )
    set_verification_status("verified" if data.get("updated") else "failed")
    output(
        mutation_payload(
            action="fusion.image.set",
            target={"kind": "timeline_item", "name": data.get("clip") or "current"},
            changed=bool(data.get("updated")),
            **data,
        ),
        title="Fusion Image Set",
    )


@image_app.command("batch")
@handle_errors
def image_batch(
    batch: str = typer.Option(..., "--batch", "--input", help="Batch JSON path"),
):
    """Apply multiple Fusion image injections from a JSON batch."""
    set_execution_engine("api_native")
    enforce_mutation_policy("fusion.mutation", intended_engine="api_native", mutating=not is_dry_run())
    entries = _load_batch_entries(batch)
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        results = []
        for index, entry in enumerate(entries):
            normalized_path = fusion_image_ops.validate_image_path(str(entry.get("image_path") or entry.get("image") or ""))
            selector = _selector_payload(
                clip_name=_normalize_optional_string(entry.get("clip")),
                track=entry.get("track"),
                record_frame=entry.get("record_frame"),
            )
            results.append(
                {
                    "index": index,
                    "ok": True,
                    **fusion_image_ops.build_image_set_plan(
                        selector=selector,
                        image_path=normalized_path,
                        group_tool_name=_normalize_optional_string(entry.get("group_tool")),
                        group_input_name=_normalize_optional_string(entry.get("group_input")),
                        group_inputs=entry.get("group_inputs") if isinstance(entry.get("group_inputs"), dict) else None,
                        import_media=bool(entry.get("import_media", True)),
                        transform=_image_transform_payload(
                            zoom_x=entry.get("zoom_x"),
                            zoom_y=entry.get("zoom_y"),
                            pan=entry.get("pan"),
                            tilt=entry.get("tilt"),
                            position_x=entry.get("position_x"),
                            position_y=entry.get("position_y"),
                        ),
                    ),
                }
            )
        output(
            mutation_payload(
                action="fusion.image.batch",
                target={"kind": "timeline", "name": "current"},
                changed=False,
                batch_path=batch,
                result_count=len(results),
                success_count=len(results),
                failure_count=0,
                results=results,
                dry_run=True,
            ),
            title="Fusion Image Batch Plan",
        )
        return

    conn = get_connection(require_timeline=True)
    results = []
    success_count = 0
    for index, entry in enumerate(entries):
        try:
            result = _run_image_set_entry(conn, entry)
            results.append({"index": index, "ok": True, **result})
            success_count += 1
        except Exception as exc:
            results.append({"index": index, "ok": False, "selector": _selector_payload(clip_name=_normalize_optional_string(entry.get("clip")), track=entry.get("track"), record_frame=entry.get("record_frame")), "error": _exception_payload(exc)})
    output(
        mutation_payload(
            action="fusion.image.batch",
            target={"kind": "timeline", "name": _timeline_name(getattr(conn, "timeline", None)) or "current"},
            changed=any(result.get("updated") for result in results if result.get("ok")),
            batch_path=batch,
            result_count=len(results),
            success_count=success_count,
            failure_count=len(results) - success_count,
            results=results,
        ),
        title="Fusion Image Batch",
    )


def _run_text_set_entry(item: Any, entry: dict[str, Any]) -> dict[str, Any]:
    has_text_update = "text" in entry
    if has_text_update:
        data = fusion_text_ops.set_text_on_item(
            item,
            text=str(entry.get("text") or ""),
            role=_normalize_optional_string(entry.get("role")),
            explicit_tool=_normalize_optional_string(entry.get("tool")),
            tool_candidates=_list_option(entry.get("tool_candidates")),
            input_names=_list_option(entry.get("inputs") or entry.get("input")),
            uppercase=bool(entry.get("uppercase", False)),
            double_spaces=bool(entry.get("double_spaces", False)),
            bold_style=str(entry.get("bold_style") or "ExtraBold"),
            styled=entry.get("styled"),
            cls_tool_candidates=_list_option(entry.get("cls_tool_candidates")),
        )
    else:
        data = {
            "role": _normalize_optional_string(entry.get("role")),
            "text_skipped": True,
            "verified": None,
            "updated": False,
        }
    position_x = entry.get("position_x", entry.get("pan"))
    position_y = entry.get("position_y", entry.get("tilt"))
    if entry.get("reset_timeline_position"):
        data["timeline_position_reset"] = _apply_timeline_item_position(item, 0.0, 0.0)
        data["updated"] = bool(data.get("updated")) or bool(data["timeline_position_reset"].get("applied"))
    if position_x is not None or position_y is not None:
        data["position"] = _apply_timeline_item_position(
            item,
            float(position_x) if position_x is not None else None,
            float(position_y) if position_y is not None else None,
        )
        data["updated"] = bool(data.get("updated")) or bool(data["position"].get("applied"))
    center_x = entry.get("center_x")
    center_y = entry.get("center_y")
    center = entry.get("center")
    if (center_x is None or center_y is None) and isinstance(center, (list, tuple)) and len(center) >= 2:
        center_x = center[0]
        center_y = center[1]
    if center_x is not None and center_y is not None:
        data["center"] = fusion_text_ops.set_center_on_item(
            item,
            center_x=float(center_x),
            center_y=float(center_y),
            role=_normalize_optional_string(entry.get("role")),
            explicit_tool=_normalize_optional_string(entry.get("tool")),
            tool_candidates=_list_option(entry.get("tool_candidates")),
        )
        data["updated"] = bool(data.get("updated")) or bool(data["center"].get("applied"))
    return data


@text_app.command("set")
@handle_errors
def text_set(
    text: str = typer.Option(..., "--text", help="Text to set"),
    clip_name: str | None = typer.Option(None, "--clip", help="Clip name selector"),
    track: int | None = typer.Option(None, "--track", min=1, help="Video track index selector"),
    record_frame: str | None = typer.Option(None, "--record-frame", help="Record-domain point selector"),
    role: str | None = typer.Option(None, "--role", help="Optional role hint: body/header"),
    tool: str | None = typer.Option(None, "--tool", help="Explicit tool name"),
    tool_candidate: list[str] | None = typer.Option(None, "--tool-candidate", help="Additional preferred tool names"),
    input_name: list[str] | None = typer.Option(None, "--input", help="Preferred input name fallback order"),
    uppercase: bool = typer.Option(False, "--uppercase", help="Uppercase the final text"),
    double_spaces: bool = typer.Option(False, "--double-spaces", help="Replace spaces with double spaces"),
    styled: bool = typer.Option(False, "--styled/--plain", help="Force CharacterLevelStyling parsing"),
    bold_style: str = typer.Option("ExtraBold", "--bold-style", help="Bold style name for CharacterLevelStyling"),
    cls_tool: list[str] | None = typer.Option(None, "--cls-tool", help="Preferred CLS tool candidates"),
):
    """Set text on an existing Fusion/Text+ tool with fallback tool/input discovery."""
    set_execution_engine("api_native")
    enforce_mutation_policy("fusion.mutation", intended_engine="api_native", mutating=not is_dry_run())
    selector = _selector_payload(clip_name=_normalize_optional_string(clip_name), track=track, record_frame=record_frame)
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            mutation_payload(
                action="fusion.text.set",
                target={"kind": "timeline_item", "name": selector.get("clip") or "current"},
                changed=False,
                clip=_normalize_optional_string(clip_name),
                **fusion_text_ops.build_text_set_plan(
                    selector=selector,
                    text=text,
                    role=_normalize_optional_string(role),
                    explicit_tool=_normalize_optional_string(tool),
                    tool_candidates=_list_option(tool_candidate),
                    input_names=_list_option(input_name),
                    uppercase=uppercase,
                    double_spaces=double_spaces,
                    bold_style=bold_style,
                ),
                dry_run=True,
            ),
            title="Fusion Text Set Plan",
        )
        return

    conn = get_connection(require_timeline=True)
    item, resolved_selector = _resolve_timeline_item(conn, clip_name=clip_name, track=track, record_frame=record_frame)
    data = _run_text_set_entry(
        item,
        {
            "text": text,
            "role": role,
            "tool": tool,
            "tool_candidates": tool_candidate,
            "inputs": input_name,
            "uppercase": uppercase,
            "double_spaces": double_spaces,
            "styled": styled,
            "bold_style": bold_style,
            "cls_tool_candidates": cls_tool,
        },
    )
    set_verification_status("verified" if data.get("verified") else "failed")
    output(
        mutation_payload(
            action="fusion.text.set",
            target={"kind": "timeline_item", "name": _media_pool_item_name(item) or "current"},
            changed=bool(data.get("updated")),
            clip=_media_pool_item_name(item) or _normalize_optional_string(clip_name),
            selector=resolved_selector,
            **data,
        ),
        title="Fusion Text Set",
    )


@text_app.command("batch")
@handle_errors
def text_batch(
    batch: str = typer.Option(..., "--batch", "--input", help="Batch JSON path"),
):
    """Apply multiple Fusion/Text+ updates from a JSON batch."""
    set_execution_engine("api_native")
    enforce_mutation_policy("fusion.mutation", intended_engine="api_native", mutating=not is_dry_run())
    entries = _load_batch_entries(batch)
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        results = []
        for index, entry in enumerate(entries):
            selector = _selector_payload(
                clip_name=_normalize_optional_string(entry.get("clip")),
                track=entry.get("track"),
                record_frame=entry.get("record_frame"),
            )
            if "text" in entry:
                plan_entry = fusion_text_ops.build_text_set_plan(
                    selector=selector,
                    text=str(entry.get("text") or ""),
                    role=_normalize_optional_string(entry.get("role")),
                    explicit_tool=_normalize_optional_string(entry.get("tool")),
                    tool_candidates=_list_option(entry.get("tool_candidates")),
                    input_names=_list_option(entry.get("inputs") or entry.get("input")),
                    uppercase=bool(entry.get("uppercase", False)),
                    double_spaces=bool(entry.get("double_spaces", False)),
                    bold_style=str(entry.get("bold_style") or "ExtraBold"),
                )
            else:
                plan_entry = {
                    "selector": selector,
                    "role": _normalize_optional_string(entry.get("role")),
                    "text_skipped": True,
                    "center": [entry.get("center_x"), entry.get("center_y")]
                    if entry.get("center_x") is not None and entry.get("center_y") is not None
                    else entry.get("center"),
                    "reset_timeline_position": bool(entry.get("reset_timeline_position")),
                }
            results.append({"index": index, "ok": True, **plan_entry})
        output(
            mutation_payload(
                action="fusion.text.batch",
                target={"kind": "timeline", "name": "current"},
                changed=False,
                batch_path=batch,
                result_count=len(results),
                success_count=len(results),
                failure_count=0,
                results=results,
                dry_run=True,
            ),
            title="Fusion Text Batch Plan",
        )
        return

    conn = get_connection(require_timeline=True)
    results = []
    success_count = 0
    for index, entry in enumerate(entries):
        try:
            item, selector = _resolve_timeline_item(
                conn,
                clip_name=_normalize_optional_string(entry.get("clip")),
                track=entry.get("track"),
                record_frame=entry.get("record_frame"),
            )
            result = _run_text_set_entry(item, entry)
            results.append({"index": index, "ok": True, "clip": _media_pool_item_name(item) or _normalize_optional_string(entry.get("clip")), "selector": selector, **result})
            success_count += 1
        except Exception as exc:
            results.append({"index": index, "ok": False, "selector": _selector_payload(clip_name=_normalize_optional_string(entry.get("clip")), track=entry.get("track"), record_frame=entry.get("record_frame")), "error": _exception_payload(exc)})
    output(
        mutation_payload(
            action="fusion.text.batch",
            target={"kind": "timeline", "name": _timeline_name(getattr(conn, "timeline", None)) or "current"},
            changed=any(result.get("updated") for result in results if result.get("ok")),
            batch_path=batch,
            result_count=len(results),
            success_count=success_count,
            failure_count=len(results) - success_count,
            results=results,
        ),
        title="Fusion Text Batch",
    )


def _nested_update_entry(
    conn: Any,
    entry: dict[str, Any],
    *,
    dry_run: bool,
) -> dict[str, Any]:
    item, selector = _resolve_timeline_item(
        conn,
        clip_name=_normalize_optional_string(entry.get("clip")),
        track=entry.get("track"),
        record_frame=entry.get("record_frame"),
    )
    open_state = _open_nested_timeline(conn, item)
    result: dict[str, Any] = {}
    try:
        text_items = _collect_nested_text_items(open_state["nested_timeline"])
        header_row, body_row = _select_nested_text_targets(
            text_items,
            header_clip_name=_normalize_optional_string(entry.get("header_clip")),
            body_clip_name=_normalize_optional_string(entry.get("body_clip")),
        )
        result = {
            "compound_clip": _media_pool_item_name(item) or _normalize_optional_string(entry.get("clip")) or None,
            "selector": selector,
            "original_timeline": _timeline_name(open_state["original_timeline"]),
            "nested_timeline": _timeline_name(open_state["nested_timeline"]),
            "opened_via": open_state["opened_via"],
            "header_item": header_row["name"] if header_row is not None else None,
            "body_item": body_row["name"] if body_row is not None else None,
            "text_item_count": len(text_items),
            "available_text_items": [row["name"] for row in text_items],
        }
        if dry_run:
            result["header_updated"] = False
            result["body_updated"] = False
            return result
        header_result = None
        body_result = None
        if header_row is not None and entry.get("header") is not None:
            header_result = fusion_text_ops.set_text_on_item(
                header_row["item"],
                text=str(entry.get("header") or ""),
                role="header",
                uppercase=bool(entry.get("header_uppercase", False)),
                double_spaces=bool(entry.get("header_double_spaces", False)),
                bold_style=str(entry.get("bold_style") or "ExtraBold"),
                styled=None,
            )
        if body_row is not None and entry.get("body") is not None:
            body_result = fusion_text_ops.set_text_on_item(
                body_row["item"],
                text=str(entry.get("body") or ""),
                role="body",
                uppercase=False,
                double_spaces=False,
                bold_style=str(entry.get("bold_style") or "ExtraBold"),
                styled=None,
            )
        result.update(
            {
                "header_updated": bool(header_result and header_result.get("updated")),
                "body_updated": bool(body_result and body_result.get("updated")),
                "attempts": {"header": header_result, "body": body_result},
                "verification": {"header": header_result.get("readback") if header_result else None, "body": body_result.get("readback") if body_result else None},
            }
        )
        return result
    finally:
        restored = _restore_original_timeline(open_state["project"], open_state["original_timeline"])
        try:
            setattr(conn, "timeline", open_state["original_timeline"])
        except Exception:
            pass
        result["restored_original_timeline"] = restored


@nested_text_app.command("update")
@handle_errors
def nested_text_update(
    header: str | None = typer.Option(None, "--header", help="Header text"),
    body: str | None = typer.Option(None, "--body", help="Body text"),
    clip_name: str | None = typer.Option(None, "--clip", help="Compound clip name selector"),
    track: int | None = typer.Option(None, "--track", min=1, help="Video track index selector"),
    record_frame: str | None = typer.Option(None, "--record-frame", help="Record-domain point selector"),
    header_clip: str | None = typer.Option(None, "--header-clip", help="Nested header clip name"),
    body_clip: str | None = typer.Option(None, "--body-clip", help="Nested body clip name"),
    header_uppercase: bool = typer.Option(False, "--header-uppercase", help="Uppercase header text"),
    header_double_spaces: bool = typer.Option(False, "--header-double-spaces", help="Double-space header text"),
    preset: str | None = typer.Option(None, "--preset", help="Optional compatibility preset; legacy-explanation selects legacy explanation header/body clips and typography"),
    bold_style: str = typer.Option("ExtraBold", "--bold-style", help="Bold style name for CharacterLevelStyling"),
):
    """Open a nested compound timeline and update its inner header/body text clips."""
    set_execution_engine("api_native")
    enforce_mutation_policy("fusion.mutation", intended_engine="api_native", mutating=not is_dry_run())
    if preset == "legacy-explanation":
        header_uppercase = True
        header_double_spaces = True
        header_clip = header_clip or fusion_text_ops.HEADER_DEFAULT_NAME
        body_clip = body_clip or fusion_text_ops.BODY_DEFAULT_NAME
    conn = get_connection(require_timeline=True)
    data = _nested_update_entry(
        conn,
        {
            "clip": clip_name,
            "track": track,
            "record_frame": record_frame,
            "header": header,
            "body": body,
            "header_clip": header_clip,
            "body_clip": body_clip,
            "header_uppercase": header_uppercase,
            "header_double_spaces": header_double_spaces,
            "bold_style": bold_style,
        },
        dry_run=is_dry_run(),
    )
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            mutation_payload(
                action="fusion.nested_text.update",
            target={"kind": "timeline_item", "name": data.get("compound_clip") or "current"},
            changed=False,
            **data,
            dry_run=True,
            ),
            title="Fusion Nested Text Plan",
        )
        return
    set_verification_status("verified" if data.get("header_updated") or data.get("body_updated") else "failed")
    output(
        mutation_payload(
            action="fusion.nested_text.update",
            target={"kind": "timeline_item", "name": data.get("compound_clip") or "current"},
            changed=bool(data.get("header_updated") or data.get("body_updated")),
            **data,
        ),
        title="Fusion Nested Text Update",
    )


@nested_text_app.command("batch")
@handle_errors
def nested_text_batch(
    batch: str = typer.Option(..., "--batch", "--input", help="Batch JSON path"),
):
    """Apply multiple nested header/body updates from JSON."""
    set_execution_engine("api_native")
    enforce_mutation_policy("fusion.mutation", intended_engine="api_native", mutating=not is_dry_run())
    entries = _load_batch_entries(batch)
    conn = get_connection(require_timeline=True)
    results = []
    success_count = 0
    for index, entry in enumerate(entries):
        if entry.get("preset") == "legacy-explanation":
            entry = {
                **entry,
                "header_uppercase": True,
                "header_double_spaces": True,
                "header_clip": entry.get("header_clip") or fusion_text_ops.HEADER_DEFAULT_NAME,
                "body_clip": entry.get("body_clip") or fusion_text_ops.BODY_DEFAULT_NAME,
            }
        try:
            result = _nested_update_entry(conn, entry, dry_run=is_dry_run())
            results.append({"index": index, "ok": True, **result})
            success_count += 1
        except Exception as exc:
            results.append({"index": index, "ok": False, "selector": _selector_payload(clip_name=_normalize_optional_string(entry.get("clip")), track=entry.get("track"), record_frame=entry.get("record_frame")), "error": _exception_payload(exc)})
    payload = mutation_payload(
        action="fusion.nested_text.batch",
        target={"kind": "timeline", "name": _timeline_name(getattr(conn, "timeline", None)) or "current"},
        changed=any((row.get("header_updated") or row.get("body_updated")) for row in results if row.get("ok")),
        batch_path=batch,
        result_count=len(results),
        success_count=success_count,
        failure_count=len(results) - success_count,
        results=results,
    )
    if is_dry_run():
        payload["dry_run"] = True
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(payload, title="Fusion Nested Text Batch Plan")
        return
    output(payload, title="Fusion Nested Text Batch")


@tool_app.command("list")
@handle_errors
def tool_list(
    selected: bool = typer.Option(False, "--selected", help="Show only selected tools"),
):
    """List tools in the composition."""
    conn = get_connection(require_timeline=True)
    api = fusion_api.get_fusion_api(conn)
    
    tools = api.list_tools(selected_only=selected)
    output(
        tools,
        columns=[("id", "ID"), ("name", "Name"), ("type", "Type")],
        title="Fusion Tools",
        quiet_key="name"
    )


@tool_app.command("add")
@handle_errors
def tool_add(
    tool_type: str = typer.Argument(..., help="Tool type (TextPlus, Merge, Background, etc.)"),
    name: Optional[str] = typer.Option(None, "--name", help="Custom tool name"),
    x: int = typer.Option(-32768, "--x", help="X position (-32768 = auto)"),
    y: int = typer.Option(-32768, "--y", help="Y position (-32768 = auto)"),
):
    """Add a tool to the composition.
    
    Common tool types:
    - TextPlus: Text/titles
    - Merge: Compositing
    - Background: Solid color
    - Loader: Image/sequence
    - Transform: Position/scale/rotation
    - Blur: Blur effect
    - RectangleMask: Rectangle mask
    - EllipseMask: Ellipse mask
    - ColorCorrector: Color correction
    - Tracker: Motion tracking
    - MediaIn, MediaOut: Timeline clip I/O
    """
    enforce_mutation_policy("fusion.mutation", intended_engine="fusion_native")
    tool_type = tool_type.strip()
    if not tool_type:
        raise ValidationError(
            "Fusion tool add requires TOOL_TYPE.",
            details={
                "tool_type": tool_type,
                "common_tool_types": ["TextPlus", "Merge", "Background", "Transform", "ColorCorrector", "Blur"],
                "example": 'cutagent fusion tool add TextPlus --name "Title" --json',
            },
        )
    if is_dry_run():
        output(
            {
                "message": f"DRY-RUN: Would add Fusion tool '{tool_type}' named '{name or 'auto'}' at ({x}, {y}).",
                "action": "fusion.tool.add",
                "tool_type": tool_type,
                "requested_name": name,
                "x": x,
                "y": y,
                "route": "fusion_comp.AddTool",
            },
            title="Fusion Tool Add",
        )
        return
    conn = get_connection(require_timeline=True)
    api = fusion_api.get_fusion_api(conn)
    
    tool = api.add_tool(tool_type, x=x, y=y, name=name)
    tool_name = tool.Name if hasattr(tool, "Name") else str(tool)
    success(f"Added tool: {tool_name} ({tool_type})")


@node_app.command("add")
@handle_errors
def node_add(
    tool_type: str = typer.Argument(..., help="Tool type (TextPlus, Merge, Background, etc.)"),
    name: Optional[str] = typer.Option(None, "--name", help="Custom tool name"),
    x: int = typer.Option(-32768, "--x", help="X position (-32768 = auto)"),
    y: int = typer.Option(-32768, "--y", help="Y position (-32768 = auto)"),
):
    """Add a Fusion node; alias for `fusion tool add`."""
    enforce_mutation_policy("fusion.mutation", intended_engine="fusion_native")
    tool_type = tool_type.strip()
    if not tool_type:
        raise ValidationError(
            "Fusion node add requires TOOL_TYPE.",
            details={
                "tool_type": tool_type,
                "common_tool_types": ["TextPlus", "Merge", "Background", "Transform", "ColorCorrector", "Blur"],
                "example": 'cutagent fusion node add TextPlus --name "Title" --json',
            },
        )
    if is_dry_run():
        dry_run_message(f"Would add Fusion node '{tool_type}' named '{name or 'auto'}' at ({x}, {y}).")
        return
    conn = get_connection(require_timeline=True)
    api = fusion_api.get_fusion_api(conn)

    tool = api.add_tool(tool_type, x=x, y=y, name=name)
    tool_name = tool.Name if hasattr(tool, "Name") else str(tool)
    output(
        {
            "action": "fusion.node.add",
            "tool_type": tool_type,
            "name": tool_name,
            "requested_name": name,
            "x": x,
            "y": y,
            "route": "fusion_comp.AddTool",
        },
        title="Fusion Node Add",
    )
