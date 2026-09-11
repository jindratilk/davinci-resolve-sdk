from __future__ import annotations

@app.command("insert-setting")
@handle_errors
def insert_setting(
    path: Optional[str] = typer.Argument(None, help=".setting file to insert as a Fusion Composition clip"),
    name: Optional[str] = typer.Option(None, "--name", help="Timeline clip name after insertion"),
    timeline_name: Optional[str] = typer.Option(None, "--timeline", help="Target timeline name; defaults to active timeline"),
    at: str = typer.Option("0s", "--at", help="Timeline position: timecode, seconds, or frames"),
    duration: str = typer.Option("5s", "--duration", help="Clip duration: timecode, seconds, or frames"),
    holder: str = typer.Option("Fusion Composition", "--holder", help="Generator name used as the holder clip"),
    track: int | None = typer.Option(None, "--track", help="Precise video track index; uses Media Pool holder if available, otherwise native holder + DB placement"),
    record_frame: int | None = typer.Option(None, "--record-frame", help="Exact DaVinci Resolve recordFrame; takes precedence over --at"),
    position_x: float | None = typer.Option(None, "--position-x", help="Optional inspector X position"),
    position_y: float | None = typer.Option(None, "--position-y", help="Optional inspector Y position"),
    holder_kind: str = typer.Option("fusion", "--holder-kind", help="fusion or textplus"),
    render_template: Optional[str] = typer.Option(None, "--render-template", help="Render this .setting template before insertion"),
    text: Optional[str] = typer.Option(None, "--text", help="Text replacement for template text placeholders"),
    image: Optional[str] = typer.Option(None, "--image", help="Image path replacement for template image placeholders"),
    style_markdown: bool = typer.Option(True, "--style-markdown/--plain-text", help="Parse **bold** markdown into CharacterLevelStyling"),
    bold_style: str = typer.Option("ExtraBold", "--bold-style", help="Fusion font style used for markdown bold ranges"),
    params: List[str] = typer.Option([], "--param", help="Raw template replacement as KEY=VALUE; repeatable"),
    require_text: bool = typer.Option(False, "--require-text", help="Require a recognized text placeholder to be replaced"),
    require_image: bool = typer.Option(False, "--require-image", help="Require a recognized image placeholder to be replaced"),
    require_styling: bool = typer.Option(False, "--require-styling", help="Require a recognized styling placeholder to be replaced"),
    keep_rendered: bool = typer.Option(False, "--keep-rendered", help="Keep the rendered temporary .setting file"),
    rendered_output: Optional[str] = typer.Option(None, "--rendered-output", help="Write rendered .setting to this path instead of a temporary file"),
):
    """Insert a holder Fusion Composition clip and apply a .setting file."""
    set_execution_engine("workaround_setting")
    if track is not None and track < 1:
        raise ValidationError("Track must be 1 or greater.", details={"track": track})
    normalized_holder_kind = str(holder_kind or "fusion").strip().lower().replace("_", "-")
    if normalized_holder_kind not in {"fusion", "textplus"}:
        raise ValidationError(
            "Unsupported holder kind.",
            details={"holder_kind": holder_kind, "allowed": ["fusion", "textplus"]},
        )
    enforce_mutation_policy("fusion.setting_insert", intended_engine="workaround_setting", mutating=not is_dry_run())

    source = _resolve_insert_setting_source(
        path=path,
        render_template=render_template,
        text=text,
        image=image,
        style_markdown=style_markdown,
        bold_style=bold_style,
        params=params,
        require_text=require_text,
        require_image=require_image,
        require_styling=require_styling,
        keep_rendered=keep_rendered,
        rendered_output=rendered_output,
    )
    effective_path = str(source["path"])

    clip_name = str(name or os.path.splitext(os.path.basename(effective_path))[0] or "Fusion Composition").strip()
    holder_name = str(holder or "Fusion Composition").strip() or "Fusion Composition"
    if normalized_holder_kind == "textplus" and holder_name == "Fusion Composition":
        holder_name = "Text+"
    preview_at_seconds = parse_time_input(str(at), 24.0)
    preview_duration_frames = _parse_positive_duration_frames(duration, 24.0)
    precise_route_requested = track is not None

    if is_dry_run():
        cleanup = dict(source.get("cleanup") or {})
        cleanup["temporary_setting_deleted"] = _delete_rendered_setting(source.get("cleanup_path"))
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            {
                "message": (
                    f"DRY-RUN: Would precisely insert '{holder_name}' and apply .setting file: {effective_path}"
                    if precise_route_requested
                    else f"DRY-RUN: Would insert '{holder_name}' and apply .setting file: {effective_path}"
                ),
                "action": "fusion.insert_setting",
                "would_insert": True,
                "would_apply": True,
                "dry_run": True,
                "path": effective_path,
                "name": clip_name,
                "timeline": timeline_name,
                "holder": holder_name,
                "holder_kind": normalized_holder_kind,
                "at": at,
                "record_frame": record_frame,
                "duration": duration,
                "track": track,
                "position_requested": {"x": position_x, "y": position_y},
                "at_seconds_at_24fps": preview_at_seconds,
                "duration_frames_at_24fps": preview_duration_frames,
                "route": (
                    ROUTE_MEDIA_POOL_HOLDER_IMPORT_FUSION_COMP
                    + " | "
                    + (
                        ROUTE_NATIVE_TEXTPLUS_SCRATCH_DB_IMPORT_FUSION_COMP
                        if normalized_holder_kind == "textplus"
                        else ROUTE_NATIVE_FUSION_SCRATCH_DB_IMPORT_FUSION_COMP
                    )
                )
                if precise_route_requested
                else (
                    ROUTE_NATIVE_TEXTPLUS_IMPORT_FUSION_COMP
                    if normalized_holder_kind == "textplus"
                    else ROUTE_NATIVE_HOLDER_IMPORT_FUSION_COMP
                ),
                "render": source["render"],
                "cleanup": cleanup,
            },
            title="Fusion Insert Setting Plan",
        )
        return

    conn = get_connection(require_timeline=True)
    original_timeline = None
    original_timeline_name = None
    timeline_switch = None
    restored_original_timeline = False
    if timeline_name:
        try:
            original_timeline = conn.project.GetCurrentTimeline() if getattr(conn, "project", None) and hasattr(conn.project, "GetCurrentTimeline") else getattr(conn, "timeline", None)
            original_timeline_name = _timeline_name(original_timeline)
            timeline_switch = timeline_ops.switch_timeline(conn, name=timeline_name, return_details=True)
        except Exception:
            _delete_rendered_setting(source.get("cleanup_path"))
            raise
    if precise_route_requested:
        try:
            data = _insert_setting_precise(
                conn,
                path=effective_path,
                clip_name=clip_name,
                at=at,
                record_frame=record_frame,
                duration=duration,
                track=track,
                holder=holder_name,
                holder_kind=normalized_holder_kind,
                position_x=position_x,
                position_y=position_y,
            )
        except Exception:
            _delete_rendered_setting(source.get("cleanup_path"))
            raise
        timeline_item_cleanup = data.pop("cleanup", None)
        cleanup = {"temporary_setting_deleted": _delete_rendered_setting(source.get("cleanup_path"))}
        if data.get("connection_reloaded"):
            try:
                from ..connection import ResolveConnection

                fresh_conn = ResolveConnection.get()
                fresh_conn.connect()
                if original_timeline_name:
                    restored_original_timeline = bool(timeline_ops.switch_timeline(fresh_conn, name=original_timeline_name))
                conn = fresh_conn
            except Exception:
                restored_original_timeline = False
        elif original_timeline is not None:
            restored_original_timeline = _restore_original_timeline(conn.project, original_timeline)
            try:
                conn.refresh()
            except Exception:
                pass
        output(
            mutation_payload(
                action="fusion.insert_setting",
                target={"kind": "timeline_item", "name": clip_name},
                timeline=timeline_name or _timeline_name(getattr(conn, "timeline", None)),
                timeline_switch={key: value for key, value in (timeline_switch or {}).items() if key != "timeline"} if timeline_switch else None,
                restored_original_timeline=restored_original_timeline,
                **data,
                timeline_item_cleanup=timeline_item_cleanup,
                render=source["render"],
                cleanup=cleanup,
                message=f"Inserted Fusion/Text+ setting precisely: {effective_path}",
            ),
            title="Fusion Insert Setting",
        )
        return

    duration_frames = _parse_positive_duration_frames(duration, conn.fps)
    try:
        playhead_reference = at
        if record_frame is not None:
            timeline_start = int(conn.timeline.GetStartFrame() or getattr(conn, "start_frame", 0) or 0)
            relative_frame = int(record_frame) - timeline_start if int(record_frame) >= timeline_start else int(record_frame)
            playhead_reference = f"{relative_frame}f"
        playhead_timecode = timeline_ops.set_playhead(conn, playhead_reference)
        if normalized_holder_kind == "textplus":
            inserter = require_api_method(
                conn.timeline,
                "InsertFusionTitleIntoTimeline",
                capability_id="timeline.insert_title",
                runtime_object="timeline",
            )
            item = inserter(holder_name or "Text+")
            native_insert_route = ROUTE_NATIVE_TEXTPLUS_IMPORT_FUSION_COMP
        else:
            inserter = require_api_method(
                conn.timeline,
                "InsertGeneratorIntoTimeline",
                capability_id="timeline.insert_generator",
                runtime_object="timeline",
            )
            item = inserter(holder_name)
            native_insert_route = ROUTE_NATIVE_HOLDER_IMPORT_FUSION_COMP
        if not item:
            raise APICallFailed(
                "Failed to insert Fusion Composition holder.",
                details={"holder": holder_name, "holder_kind": normalized_holder_kind, "route": native_insert_route},
            )

        applied_item_props = _apply_timeline_item_name_and_duration(item, name=clip_name, duration_frames=duration_frames)
        importer = getattr(item, "ImportFusionComp", None)
        if not callable(importer):
            timeline_item_cleanup = _safe_delete_timeline_item(conn, item)
            raise APICallFailed(
                "Inserted holder clip does not support ImportFusionComp.",
                details={"holder": holder_name, "name": clip_name, "cleanup": timeline_item_cleanup},
            )
        layout_prepared = None
        layout = None
        try:
            layout_prepared = _prepare_setting_import(effective_path)
            import_path = str(layout_prepared.get("import_path") or effective_path)
            imported = importer(import_path)
        except Exception as exc:
            layout = _cleanup_prepared_setting(layout_prepared)
            timeline_item_cleanup = _safe_delete_timeline_item(conn, item)
            raise APICallFailed(
                "ImportFusionComp failed. Check the .setting file format.",
                details={
                    "path": effective_path,
                    "import_path": import_path if "import_path" in locals() else effective_path,
                    "holder": holder_name,
                    "name": clip_name,
                    "cleanup": timeline_item_cleanup,
                    "layout": layout,
                    "error": str(exc),
                },
            ) from exc
        if not imported:
            layout = _cleanup_prepared_setting(layout_prepared)
            timeline_item_cleanup = _safe_delete_timeline_item(conn, item)
            raise APICallFailed(
                "ImportFusionComp failed. Check the .setting file format.",
                details={
                    "path": effective_path,
                    "import_path": import_path,
                    "holder": holder_name,
                    "name": clip_name,
                    "cleanup": timeline_item_cleanup,
                    "layout": layout,
                },
            )
        layout = _cleanup_prepared_setting(layout_prepared)
    except Exception:
        _delete_rendered_setting(source.get("cleanup_path"))
        raise

    tool_summary = _summarize_imported_fusion_tools(item)
    verification = {
        "imported": bool(imported),
        "fusion_comp_accessible": bool(tool_summary.get("accessible")),
        "tool_count": tool_summary.get("tool_count"),
        "duration_requested_frames": duration_frames,
        "duration_readback_frames": applied_item_props.get("duration_readback_frames"),
        "node_status_verified": False,
        "node_probe_verified": False,
        "visual_output_verified": False,
    }
    verification["duration_ok"] = applied_item_props.get("duration_readback_frames") in (duration_frames, None)
    if tool_summary.get("accessible") is False:
        set_verification_status("partial")
    elif tool_summary.get("tool_count") == 0:
        set_verification_status("failed")
        _delete_rendered_setting(source.get("cleanup_path"))
        raise APICallFailed(
            "Imported .setting, but the Fusion composition has no readable tools.",
            details={"path": effective_path, "verification": verification},
        )
    elif not verification["duration_ok"]:
        set_verification_status("pending_manual")
    else:
        set_verification_status("partial")

    cleanup = {"temporary_setting_deleted": _delete_rendered_setting(source.get("cleanup_path"))}
    if original_timeline is not None:
        restored_original_timeline = _restore_original_timeline(conn.project, original_timeline)
        try:
            conn.refresh()
        except Exception:
            pass

    output(
        mutation_payload(
            action="fusion.insert_setting",
            target={"kind": "timeline_item", "name": clip_name},
            timeline=timeline_name or _timeline_name(getattr(conn, "timeline", None)),
            timeline_switch={key: value for key, value in (timeline_switch or {}).items() if key != "timeline"} if timeline_switch else None,
            restored_original_timeline=restored_original_timeline,
            path=effective_path,
            import_path=import_path,
            name=clip_name,
            holder=holder_name,
            at=at,
            playhead_timecode=playhead_timecode,
            duration=duration,
            duration_frames=duration_frames,
            route=native_insert_route,
            item=applied_item_props,
            fusion=tool_summary,
            layout=layout,
            verification=verification,
            render=source["render"],
            cleanup=cleanup,
            message=f"Inserted Fusion Composition and applied .setting file: {effective_path}",
        ),
        title="Fusion Insert Setting",
    )


setting_app = typer.Typer(help="Fusion .setting file inspection and authoring helpers.")
app.add_typer(setting_app, name="setting")


@setting_app.command("inspect")
@handle_errors
def setting_inspect(
    path: str = typer.Argument(..., help=".setting file to inspect"),
):
    """Inspect a Fusion .setting graph without contacting DaVinci Resolve."""
    set_execution_engine("api_native")
    set_capability_context("fusion.setting_inspect", "supported")
    set_verification_status("verified")
    set_recoverability("not_applicable")
    output(inspect_setting(path), title="Fusion Setting Inspect")


def _setting_validate_static_result(payload: dict[str, Any], *, fail_on_warning: bool) -> dict[str, Any]:
    errors = list(payload.get("errors") or [])
    warnings = list(payload.get("warnings") or [])
    failure = bool(errors) or (fail_on_warning and bool(warnings))
    return {
        "ok": not failure,
        "path": payload["path"],
        "valid": bool(payload["valid"]),
        "validation_scope": "static_graph_structure_only",
        "render_verified": False,
        "timeline_import_verified": False,
        "visual_output_verified": False,
        "tool_count": payload.get("tool_count"),
        "error_count": len(errors),
        "warning_count": len(warnings),
        "errors": errors,
        "warnings": warnings,
        "layout": payload.get("layout"),
        "fail_on_warning": fail_on_warning,
        "message": (
            "Static Fusion graph validation passed. This does not verify DaVinci Resolve import, runtime node status, or visible rendered pixels."
            if not failure
            else "Static Fusion graph validation failed before any DaVinci Resolve runtime import."
        ),
    }


def _runtime_validation_error_payload(exc: Exception) -> dict[str, Any]:
    if isinstance(exc, CLIError):
        return {
            "code": exc.code,
            "message": str(exc),
            "details": exc.details,
            "recoverability": exc.recoverability,
        }
    return {
        "code": exc.__class__.__name__,
        "message": str(exc),
        "details": {},
        "recoverability": "manual",
    }


def _runtime_validation_failure_payload(code: str, message: str, details: dict[str, Any]) -> dict[str, Any]:
    return {
        "code": code,
        "message": message,
        "details": details,
        "recoverability": "manual",
    }


def _runtime_safe_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _runtime_safe_payload(inner) for key, inner in value.items() if key != "timeline"}
    if isinstance(value, (list, tuple)):
        return [_runtime_safe_payload(inner) for inner in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _project_timeline_names(conn: Any) -> set[str]:
    names: set[str] = set()
    project = getattr(conn, "project", None)
    if project is None:
        return names
    try:
        count = int(project.GetTimelineCount() or 0)
    except Exception:
        count = 0
    for index in range(1, count + 1):
        try:
            timeline = project.GetTimelineByIndex(index)
        except Exception:
            timeline = None
        name = _timeline_name(timeline)
        if name:
            names.add(name)
    return names


def _unique_validate_scratch_timeline_name(conn: Any) -> str:
    existing = _project_timeline_names(conn)
    for _attempt in range(20):
        candidate = f"CutAgent Validate Scratch {os.urandom(4).hex()}"
        if candidate not in existing:
            return candidate
    raise ValidationError(
        "Unable to allocate a unique scratch timeline name for runtime validation.",
        details={"existing_timeline_count": len(existing)},
    )


def _optional_int(value: Any) -> int | None:
    try:
        parsed = int(str(value).strip())
    except Exception:
        return None
    return parsed if parsed > 0 else None


def _optional_float(value: Any) -> float | None:
    try:
        parsed = float(str(value).strip())
    except Exception:
        return None
    return parsed if parsed > 0 else None


def _current_timeline_format(conn: Any) -> dict[str, Any]:
    timeline = getattr(conn, "timeline", None)
    settings = {}
    if timeline is not None:
        try:
            raw_settings = timeline.GetSetting()
            if isinstance(raw_settings, dict):
                settings = raw_settings
        except Exception:
            settings = {}
    width = _optional_int(settings.get("timelineResolutionWidth"))
    height = _optional_int(settings.get("timelineResolutionHeight"))
    fps = _optional_float(settings.get("timelineFrameRate")) or _optional_float(getattr(conn, "fps", None))
    return {"width": width, "height": height, "fps": fps}


def _restore_runtime_validation_timeline(
    conn: Any,
    *,
    original_timeline: Any,
    original_timeline_name: str | None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "attempted": False,
        "ok": original_timeline is None and not original_timeline_name,
        "name": original_timeline_name,
    }
    if original_timeline_name:
        payload["attempted"] = True
        try:
            details = timeline_ops.switch_timeline(conn, name=original_timeline_name, return_details=True)
            payload.update({"ok": True, "method": "timeline_ops.switch_timeline", "details": _runtime_safe_payload(details)})
        except Exception as exc:
            payload.update({"ok": False, "method": "timeline_ops.switch_timeline", "error": _runtime_validation_error_payload(exc)})
        return payload
    if original_timeline is not None and getattr(conn, "project", None) is not None:
        payload["attempted"] = True
        payload["method"] = "Project.SetCurrentTimeline"
        try:
            payload["api_result"] = _restore_original_timeline(conn.project, original_timeline)
            payload["ok"] = bool(payload["api_result"])
            try:
                conn.refresh()
            except Exception:
                pass
        except Exception as exc:
            payload.update({"ok": False, "error": _runtime_validation_error_payload(exc)})
    return payload


def _delete_runtime_validation_scratch_timeline(conn: Any, *, name: str | None, cleanup: bool) -> dict[str, Any]:
    payload: dict[str, Any] = {"attempted": False, "ok": True, "name": name, "cleanup_requested": cleanup}
    if not name:
        payload["reason"] = "scratch timeline was not allocated"
        return payload
    if not cleanup:
        payload["retained"] = True
        return payload
    timeline_names = _project_timeline_names(conn)
    if timeline_names and name not in timeline_names:
        payload["reason"] = "scratch timeline is not present"
        return payload
    payload["attempted"] = True
    try:
        payload["api_result"] = bool(timeline_ops.delete_timeline(conn, name))
        payload["ok"] = bool(payload["api_result"])
    except Exception as exc:
        payload.update({"ok": False, "error": _runtime_validation_error_payload(exc)})
    return payload


def _setting_validate_runtime_result(
    *,
    path: str,
    holder_kind: str,
    holder: str | None,
    at: str,
    duration: str,
    text: str | None,
    image: str | None,
    style_markdown: bool,
    bold_style: str,
    params: list[str] | tuple[str, ...],
    require_text: bool,
    require_image: bool,
    require_styling: bool,
    cleanup: bool,
) -> dict[str, Any]:
    normalized_holder_kind = str(holder_kind or "fusion").strip().lower().replace("_", "-")
    if normalized_holder_kind not in {"fusion", "textplus"}:
        raise ValidationError(
            "Unsupported holder kind.",
            details={"holder_kind": holder_kind, "allowed": ["fusion", "textplus"]},
        )
    render_template = bool(text is not None or image is not None or params or require_text or require_image or require_styling)
    source = _resolve_insert_setting_source(
        path=None if render_template else path,
        render_template=path if render_template else None,
        text=text,
        image=image,
        style_markdown=style_markdown,
        bold_style=bold_style,
        params=params,
        require_text=require_text,
        require_image=require_image,
        require_styling=require_styling,
        keep_rendered=False,
        rendered_output=None,
    )
    effective_path = str(source["path"])
    holder_name = str(holder or ("Text+" if normalized_holder_kind == "textplus" else "Fusion Composition")).strip()
    clip_name = f"CutAgent setting validate - {os.path.basename(effective_path)}"
    if is_dry_run():
        cleanup_payload = dict(source.get("cleanup") or {})
        cleanup_payload["temporary_setting_deleted"] = _delete_rendered_setting(source.get("cleanup_path"))
        return {
            "requested": True,
            "ok": None,
            "dry_run": True,
            "validation_scope": "resolve_runtime_import_and_tool_probe",
            "isolation": "scratch_timeline",
            "touched_user_timeline": False,
            "would_create_scratch_timeline": True,
            "would_delete_scratch_timeline": cleanup,
            "would_insert_temporary_clip": True,
            "would_cleanup_temporary_clip": cleanup,
            "holder": holder_name,
            "holder_kind": normalized_holder_kind,
            "at": at,
            "duration": duration,
            "render": source.get("render"),
            "cleanup": cleanup_payload,
            "layout": (inspect_setting(effective_path).get("layout") if os.path.isfile(effective_path) else None),
            "message": "Dry run only: static validation and template rendering were checked, but DaVinci Resolve runtime import and node diagnostics were not executed.",
        }

    conn = get_connection(require_timeline=True)
    original_timeline = None
    original_timeline_name = None
    original_playhead = None
    try:
        original_timeline = conn.project.GetCurrentTimeline() if getattr(conn, "project", None) and hasattr(conn.project, "GetCurrentTimeline") else getattr(conn, "timeline", None)
        original_timeline_name = _timeline_name(original_timeline)
    except Exception:
        original_timeline = getattr(conn, "timeline", None)
        original_timeline_name = _timeline_name(original_timeline)
    try:
        original_playhead = timeline_ops.get_playhead(conn)
    except Exception:
        original_playhead = None

    item = None
    imported = False
    applied_item_props: dict[str, Any] = {}
    playhead_result: Any = None
    tool_summary: dict[str, Any] = {}
    layout_prepared = None
    layout = None
    cleanup_payload: dict[str, Any] = {
        "temporary_clip": {"attempted": False, "reason": "scratch_timeline_deleted_instead"},
        "scratch_timeline": {"attempted": False, "ok": False},
        "temporary_setting_deleted": False,
    }
    scratch_timeline_name = None
    scratch_timeline_created = False
    scratch_timeline_format: dict[str, Any] = {}
    restored_playhead = False
    restore_payload: dict[str, Any] = {"attempted": False, "ok": False}
    restore_error = None
    runtime_error = None
    cleanup_errors: list[dict[str, Any]] = []
    runtime_ok = False
    try:
        duration_frames = _parse_positive_duration_frames(duration, float(getattr(conn, "fps", 24.0) or 24.0))
        scratch_timeline_name = _unique_validate_scratch_timeline_name(conn)
        scratch_timeline_format = _current_timeline_format(conn)
        timeline_ops.create_timeline(
            conn,
            scratch_timeline_name,
            width=scratch_timeline_format.get("width"),
            height=scratch_timeline_format.get("height"),
            fps=scratch_timeline_format.get("fps"),
        )
        scratch_timeline_created = True
        playhead_result = timeline_ops.set_playhead(conn, at)
        if normalized_holder_kind == "textplus":
            inserter = require_api_method(
                conn.timeline,
                "InsertFusionTitleIntoTimeline",
                capability_id="timeline.insert_title",
                runtime_object="timeline",
            )
            item = inserter(holder_name or "Text+")
            route = ROUTE_NATIVE_TEXTPLUS_IMPORT_FUSION_COMP
        else:
            inserter = require_api_method(
                conn.timeline,
                "InsertGeneratorIntoTimeline",
                capability_id="timeline.insert_generator",
                runtime_object="timeline",
            )
            item = inserter(holder_name or "Fusion Composition")
            route = ROUTE_NATIVE_HOLDER_IMPORT_FUSION_COMP
        if not item:
            raise APICallFailed(
                "Failed to insert temporary Fusion validation holder.",
                details={"holder": holder_name, "holder_kind": normalized_holder_kind},
            )
        applied_item_props = _apply_timeline_item_name_and_duration(item, name=clip_name, duration_frames=duration_frames)
        importer = getattr(item, "ImportFusionComp", None)
        if not callable(importer):
            raise APICallFailed(
                "Temporary holder clip does not support ImportFusionComp.",
                details={"holder": holder_name, "holder_kind": normalized_holder_kind},
            )
        layout_prepared = _prepare_setting_import(effective_path)
        import_path = str(layout_prepared.get("import_path") or effective_path)
        imported = bool(importer(import_path))
        if not imported:
            raise APICallFailed(
                "ImportFusionComp failed during runtime validation.",
                details={"path": effective_path, "import_path": import_path, "holder": holder_name, "holder_kind": normalized_holder_kind},
            )
        tool_summary = _summarize_imported_fusion_tools(item, include_diagnostics=True)
        if tool_summary.get("accessible") is False:
            raise APICallFailed(
                "Imported .setting, but the Fusion composition is not accessible.",
                details={"path": effective_path, "import_path": import_path, "holder": holder_name, "holder_kind": normalized_holder_kind},
            )
        if not tool_summary.get("tool_count"):
            raise APICallFailed(
                "Imported .setting, but no Fusion tools are readable.",
                details={"path": effective_path, "import_path": import_path, "holder": holder_name, "holder_kind": normalized_holder_kind},
            )
        if int(tool_summary.get("node_error_count") or 0) > 0:
            raise ValidationError(
                "DaVinci Resolve runtime reported Fusion node diagnostics with errors.",
                details={"path": effective_path, "import_path": import_path, "node_errors": tool_summary.get("node_errors") or []},
            )
    except Exception as exc:
        runtime_error = _runtime_validation_error_payload(exc)
    finally:
        restore_payload = _restore_runtime_validation_timeline(
            conn,
            original_timeline=original_timeline,
            original_timeline_name=original_timeline_name,
        )
        if not restore_payload.get("ok"):
            cleanup_errors.append({"source": "restore_original_timeline", **restore_payload})
        if restore_payload.get("ok") and original_playhead and isinstance(original_playhead, dict) and original_playhead.get("timecode"):
            try:
                timeline_ops.set_playhead(conn, str(original_playhead["timecode"]))
                restored_playhead = True
            except Exception as exc:
                restore_error = str(exc)
                cleanup_errors.append(
                    {
                        "source": "restore_original_playhead",
                        "timecode": original_playhead.get("timecode"),
                        "error": _runtime_validation_error_payload(exc),
                    }
                )
        cleanup_payload["scratch_timeline"] = _delete_runtime_validation_scratch_timeline(
            conn,
            name=scratch_timeline_name,
            cleanup=cleanup,
        )
        if cleanup and not cleanup_payload["scratch_timeline"].get("ok"):
            cleanup_errors.append({"source": "delete_scratch_timeline", **cleanup_payload["scratch_timeline"]})
        layout = _cleanup_prepared_setting(layout_prepared)
        if source.get("cleanup_path"):
            cleanup_payload["temporary_setting_deleted"] = _delete_rendered_setting(source.get("cleanup_path"))
            if not cleanup_payload["temporary_setting_deleted"]:
                cleanup_errors.append({"source": "delete_temporary_setting", "path": source.get("cleanup_path")})
    runtime_ok = runtime_error is None and not cleanup_errors
    if cleanup_errors and runtime_error is None:
        runtime_error = _runtime_validation_failure_payload(
            "RUNTIME_CLEANUP_FAILED",
            "DaVinci Resolve runtime validation completed, but cleanup or state restore failed.",
            {"cleanup_errors": cleanup_errors},
        )
    health_status = "failed"
    if runtime_ok:
        if bool(tool_summary.get("node_status_verified")) and bool(tool_summary.get("node_probe_verified")):
            health_status = "verified"
        else:
            health_status = "partial"

    return {
        "requested": True,
        "ok": runtime_ok,
        "dry_run": False,
        "validation_scope": "resolve_runtime_import_and_tool_probe",
        "isolation": "scratch_timeline",
        "touched_user_timeline": False,
        "original_timeline": original_timeline_name,
        "scratch_timeline_name": scratch_timeline_name,
        "scratch_timeline_created": scratch_timeline_created,
        "scratch_timeline_format": scratch_timeline_format,
        "holder": holder_name,
        "holder_kind": normalized_holder_kind,
        "route": route if "route" in locals() else None,
        "at": at,
        "duration": duration,
        "playhead": playhead_result,
        "render": source.get("render"),
        "layout": layout,
        "imported": imported,
        "timeline_import_verified": imported,
        "fusion_comp_accessible": bool(tool_summary.get("accessible")),
        "tool_count": tool_summary.get("tool_count"),
        "node_status_verified": bool(tool_summary.get("node_status_verified")),
        "node_probe_verified": bool(tool_summary.get("node_probe_verified")),
        "node_error_count": int(tool_summary.get("node_error_count") or 0),
        "node_errors": tool_summary.get("node_errors") or [],
        "node_unknown_count": int(tool_summary.get("node_unknown_count") or 0),
        "node_unknowns": tool_summary.get("node_unknowns") or [],
        "runtime_health_status": health_status,
        "tools": tool_summary.get("tools") or [],
        "item": applied_item_props,
        "cleanup": cleanup_payload,
        "cleanup_ok": not cleanup_errors,
        "cleanup_errors": cleanup_errors,
        "restore": restore_payload,
        "restored_original_timeline": bool(restore_payload.get("ok")),
        "restored_playhead": restored_playhead,
        "restore_error": restore_error,
        "error": runtime_error,
        "message": (
            "DaVinci Resolve runtime import and tool diagnostics are verified inside an isolated scratch timeline. Visual pixels are still not verified without a frame export."
            if runtime_ok and health_status == "verified"
            else "DaVinci Resolve runtime import passed, but DaVinci Resolve did not expose enough node-status/probe evidence to prove GUI node health."
            if runtime_ok
            else "DaVinci Resolve runtime validation failed; inspect error, node_errors, and per-tool runtime_status/output_probe."
        ),
    }


@setting_app.command("validate")
@handle_errors
def setting_validate(
    path: str = typer.Argument(..., help=".setting file to validate"),
    fail_on_warning: bool = typer.Option(False, "--fail-on-warning", help="Return VALIDATION_ERROR when warnings are present"),
    runtime: bool = typer.Option(False, "--runtime", help="Import into an isolated scratch timeline holder and inspect runtime tool diagnostics"),
    holder_kind: str = typer.Option("fusion", "--holder-kind", help="Runtime validation holder kind: fusion or textplus"),
    holder: Optional[str] = typer.Option(None, "--holder", help="Runtime validation holder name"),
    at: str = typer.Option("0s", "--at", help="Runtime validation timeline position"),
    duration: str = typer.Option("2s", "--duration", help="Runtime validation temporary clip duration"),
    text: Optional[str] = typer.Option(None, "--text", help="Render template text before runtime validation"),
    image: Optional[str] = typer.Option(None, "--image", help="Render template image path before runtime validation"),
    style_markdown: bool = typer.Option(True, "--style-markdown/--plain-text", help="Parse **bold** markdown before runtime validation"),
    bold_style: str = typer.Option("ExtraBold", "--bold-style", help="Fusion font style used for markdown bold ranges"),
    params: List[str] = typer.Option([], "--param", help="Raw template replacement as KEY=VALUE; repeatable"),
    require_text: bool = typer.Option(False, "--require-text", help="Require a recognized text placeholder before runtime validation"),
    require_image: bool = typer.Option(False, "--require-image", help="Require a recognized image placeholder before runtime validation"),
    require_styling: bool = typer.Option(False, "--require-styling", help="Require a recognized styling placeholder before runtime validation"),
    cleanup: bool = typer.Option(True, "--cleanup/--keep-temporary-clip", help="Delete the temporary runtime validation scratch timeline"),
):
    """Validate static .setting structure; optionally import into an isolated scratch timeline for runtime node diagnostics."""
    set_execution_engine("fusion_native" if runtime else "api_native")
    set_capability_context("fusion.setting_validate", "supported")
    enforce_mutation_policy("fusion.setting_validate", intended_engine="fusion_native" if runtime else "api_native", mutating=runtime and not is_dry_run())
    payload = inspect_setting(path)
    static_result = _setting_validate_static_result(payload, fail_on_warning=fail_on_warning)
    runtime_result = {"requested": False, "ok": None}
    if static_result["ok"] and runtime:
        runtime_result = _setting_validate_runtime_result(
            path=payload["path"],
            holder_kind=holder_kind,
            holder=holder,
            at=at,
            duration=duration,
            text=text,
            image=image,
            style_markdown=style_markdown,
            bold_style=bold_style,
            params=params,
            require_text=require_text,
            require_image=require_image,
            require_styling=require_styling,
            cleanup=cleanup,
        )
    failure = not static_result["ok"] or (runtime and runtime_result.get("ok") is False)
    verification_status = "failed" if failure else "verified"
    if not failure and runtime and runtime_result.get("runtime_health_status") != "verified":
        verification_status = "partial"
    set_verification_status(verification_status)
    set_recoverability("manual" if failure else "not_applicable")
    if failure:
        raise ValidationError(
            "Fusion .setting validation failed.",
            details={
                "path": static_result["path"],
                "validation_scope": "static_graph_structure_plus_runtime" if runtime else "static_graph_structure_only",
                "static_validation": static_result,
                "runtime_validation": runtime_result,
                "fail_on_warning": fail_on_warning,
            },
        )
    output(
        {
            "path": static_result["path"],
            "valid": True,
            "validation_scope": "static_graph_structure_plus_runtime" if runtime else "static_graph_structure_only",
            "template_render_verified": bool((runtime_result.get("render") or {}).get("enabled")) if runtime else False,
            "render_verified": False,
            "timeline_import_verified": bool(runtime_result.get("timeline_import_verified")) if runtime else False,
            "runtime_node_status_verified": bool(runtime_result.get("node_status_verified")) if runtime else False,
            "runtime_node_probe_verified": bool(runtime_result.get("node_probe_verified")) if runtime else False,
            "runtime_health_status": runtime_result.get("runtime_health_status") if runtime else "not_requested",
            "visual_output_verified": False,
            "error_count": static_result["error_count"],
            "warning_count": static_result["warning_count"],
            "warnings": static_result["warnings"],
            "static_validation": static_result,
            "runtime_validation": runtime_result,
            "layout": payload.get("layout"),
            "message": (
                runtime_result.get("message")
                if runtime
                else "Static Fusion graph validation passed. This does not verify DaVinci Resolve import, runtime node status, or visible rendered pixels. Use --runtime for temporary DaVinci Resolve import diagnostics and timeline frame-export for visual proof."
            ),
        },
        title="Fusion Setting Validate",
    )


@setting_app.command("summary")
@handle_errors
def setting_summary_command(
    path: str = typer.Argument(..., help=".setting file to summarize"),
    connections: bool = typer.Option(False, "--connections", help="Include SourceOp connection edges"),
    animated: bool = typer.Option(False, "--animated", help="Include animated input references"),
):
    """Summarize a Fusion .setting graph for quick agent inspection."""
    set_execution_engine("api_native")
    set_capability_context("fusion.setting_summary", "supported")
    set_verification_status("verified")
    set_recoverability("not_applicable")
    output(setting_summary(path, include_connections=connections, include_animated=animated), title="Fusion Setting Summary")


@setting_app.command("center-to-polypath")
@handle_errors
def setting_center_to_polypath(
    x: float = typer.Argument(..., help="Normalized Fusion Center X, usually 0..1"),
    y: float = typer.Argument(..., help="Normalized Fusion Center Y, usually 0..1"),
):
    """Convert normalized Center coordinates to PolyPath point coordinates."""
    set_execution_engine("api_native")
    set_capability_context("fusion.setting_coords", "supported")
    set_verification_status("verified")
    set_recoverability("not_applicable")
    output({"center": {"X": x, "Y": y}, "polypath": normalized_center_to_polypath(x, y)}, title="Center To PolyPath")


@setting_app.command("polypath-to-center")
@handle_errors
def setting_polypath_to_center(
    x: float = typer.Argument(..., help="Fusion PolyPath X coordinate"),
    y: float = typer.Argument(..., help="Fusion PolyPath Y coordinate"),
):
    """Convert PolyPath point coordinates to normalized Center coordinates."""
    set_execution_engine("api_native")
    set_capability_context("fusion.setting_coords", "supported")
    set_verification_status("verified")
    set_recoverability("not_applicable")
    output({"polypath": {"X": x, "Y": y}, "center": polypath_to_normalized_center(x, y)}, title="PolyPath To Center")


macro_app = typer.Typer(help="Fusion macro/.setting operations.")
app.add_typer(macro_app, name="macro")


def _resolve_macro_setting_path(name_or_path: str) -> str:
    return _resolve_named_setting_path(
        name_or_path,
        kind="macro",
        command_path="fusion macro apply",
        example_name="cutagent_textplus_default",
    )


def _resolve_template_setting_path(name_or_path: str) -> str:
    return _resolve_named_setting_path(
        name_or_path,
        kind="template",
        command_path="fusion template apply",
        example_name="cutagent_textplus_default",
    )


def _resolve_named_setting_path(name_or_path: str, *, kind: str, command_path: str, example_name: str) -> str:
    requested = str(name_or_path or "").strip()
    if not requested:
        upper = "MACRO_OR_SETTING" if kind == "macro" else "TEMPLATE_OR_SETTING"
        raise ValidationError(
            f"Fusion {kind} apply requires {upper}.",
            details={
                "example": f"cutagent {command_path} {example_name} --json",
                "discovery_hint": "Use `cutagent fusion template list --json` to inspect available .setting macros/templates.",
            },
        )

    def _name_variants(token: str) -> list[str]:
        variants = [token]
        if not token.lower().endswith(".setting"):
            variants.append(f"{token}.setting")
        return variants

    path_like = os.path.isabs(requested) or os.sep in requested or (os.altsep and os.altsep in requested)
    if path_like:
        candidates = [os.path.abspath(os.path.expanduser(path)) for path in _name_variants(requested)]
        for candidate in candidates:
            if os.path.isfile(candidate):
                return candidate
        raise ValidationError(
            f"Fusion {kind} file not found.",
            details={kind: requested, "candidates": candidates},
        )

    directories = _macro_directories()
    direct_candidates: list[str] = []
    for directory in directories:
        for file_name in _name_variants(requested):
            direct_candidates.append(os.path.join(directory, file_name))
    for candidate in direct_candidates:
        if os.path.isfile(candidate):
            return os.path.abspath(candidate)

    matches: list[str] = []
    requested_names = {variant.lower() for variant in _name_variants(requested)}
    for directory in directories:
        if not os.path.isdir(directory):
            continue
        for root, _, files in os.walk(directory):
            for file_name in files:
                if file_name.lower() in requested_names:
                    matches.append(os.path.abspath(os.path.join(root, file_name)))
    unique_matches = sorted(dict.fromkeys(matches))
    if len(unique_matches) == 1:
        return unique_matches[0]
    if len(unique_matches) > 1:
        raise ValidationError(
            f"Fusion {kind} name is ambiguous.",
            details={kind: requested, "matches": unique_matches},
        )

    available = _available_macro_settings(directories)
    raise ValidationError(
        f"Fusion {kind} not found.",
        details={
            kind: requested,
            "searched_directories": directories,
            "candidates": direct_candidates,
            f"available_{kind}s": available[:50],
            "discovery_hint": "Use `cutagent fusion template list --json` or pass an absolute .setting path.",
        },
    )


def _macro_directories() -> list[str]:
    home = os.path.expanduser("~")
    directories = [
        *_template_directories(),
        os.path.join(home, "Library", "Application Support", "Blackmagic Design", "DaVinci Resolve", "Fusion", "Macros"),
        os.path.join(home, "Library", "Application Support", "Blackmagic Design", "DaVinci Resolve", "Fusion", "Templates"),
        os.path.join(os.sep, "Library", "Application Support", "Blackmagic Design", "DaVinci Resolve", "Fusion", "Macros"),
        os.path.join(os.sep, "Library", "Application Support", "Blackmagic Design", "DaVinci Resolve", "Fusion", "Templates"),
    ]
    seen: set[str] = set()
    normalized: list[str] = []
    for directory in directories:
        resolved = os.path.abspath(os.path.expanduser(directory))
        if resolved in seen:
            continue
        seen.add(resolved)
        normalized.append(resolved)
    return normalized


def _available_macro_settings(directories: list[str]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for directory in directories:
        if not os.path.isdir(directory):
            continue
        for root, _, files in os.walk(directory):
            for file_name in sorted(files):
                if not file_name.lower().endswith(".setting"):
                    continue
                rows.append({"name": file_name, "path": os.path.abspath(os.path.join(root, file_name))})
    return rows


@macro_app.command("apply")
@handle_errors
def macro_apply(
    macro: str = typer.Argument(..., help="Macro/template name or .setting path"),
    clip_name: Optional[str] = typer.Option(None, "--clip", help="Clip name (or current)"),
):
    """Apply a Fusion macro/template .setting to a clip."""
    enforce_mutation_policy("fusion.mutation", intended_engine="fusion_native")
    path = _resolve_macro_setting_path(macro)
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            {
                "message": f"DRY-RUN: Would apply Fusion macro '{macro}' from '{path}' to '{clip_name or 'current clip'}'.",
                "action": "fusion.macro.apply",
                "macro": str(macro),
                "path": path,
                "clip": clip_name,
                "target": "named_clip" if clip_name else "current_clip",
                "route": ROUTE_IMPORT_FUSION_COMP,
                "would_apply": True,
                "dry_run": True,
            },
            title="Fusion Macro Apply Plan",
        )
        return

    conn = get_connection(require_timeline=True)
    item = clip_ops.cutagent_clip(conn, clip_name)
    if not hasattr(item, "ImportFusionComp"):
        raise APICallFailed("This clip doesn't support ImportFusionComp.")

    layout_prepared = None
    layout = None
    try:
        layout_prepared = _prepare_setting_import(path)
        import_path = str(layout_prepared.get("import_path") or path)
        result = item.ImportFusionComp(import_path)
    except Exception as exc:
        layout = _cleanup_prepared_setting(layout_prepared)
        raise APICallFailed(
            "ImportFusionComp failed. Check the .setting file format.",
            details={"macro": macro, "path": path, "import_path": import_path if "import_path" in locals() else path, "clip": clip_name, "layout": layout, "error": str(exc)},
        ) from exc
    layout = _cleanup_prepared_setting(layout_prepared)
    if not result:
        raise APICallFailed(
            "ImportFusionComp failed. Check the .setting file format.",
            details={"macro": macro, "path": path, "import_path": import_path, "clip": clip_name, "layout": layout},
        )
    set_verification_status("partial")
    set_recoverability("not_applicable")
    output(
        {
            "action": "fusion.macro.apply",
            "macro": str(macro),
            "path": path,
            "import_path": import_path,
            "clip": clip_name,
            "clip_readback": _media_pool_item_name(item) or None,
            "route": ROUTE_IMPORT_FUSION_COMP,
            "applied": True,
            "imported": True,
            "layout": layout,
        },
        title="Fusion Macro Apply",
    )


@app.command("insert-settings-batch", hidden=True)
@handle_errors
def insert_settings_batch(
    spec_path: Optional[str] = typer.Option(None, "--spec", help="Path to JSON spec file"),
    spec_json: Optional[str] = typer.Option(None, "--spec-json", help="Inline JSON spec"),
):
    """Insert multiple Fusion/Text+ clips from .setting template specs."""
    enforce_mutation_policy("fusion.mutation", intended_engine="fusion_native")
    conn = get_connection(require_timeline=True)
    items = _parse_batch_spec(spec_path, spec_json)

    created: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []

    for index, item in enumerate(items):
        try:
            rendered = _render_setting_from_spec(item)
            created.append(
                _insert_rendered_setting(
                    conn,
                    rendered=rendered,
                    name=str(item.get("name") or f"Styled Item {index + 1}"),
                    at=str(item.get("at") or "0s"),
                    duration=float(item.get("duration") or 5.0),
                    track=int(item.get("track") or 2),
                    holder=str(item.get("holder") or "Fusion Composition"),
                    holder_kind=str(item.get("holder_kind") or "fusion"),
                ),
            )
        except Exception as error:
            failures.append({
                "index": index,
                "name": item.get("name"),
                "template": item.get("template"),
                "error": str(error),
            })

    output(
        {
            "created": created,
            "failures": failures,
            "requested": len(items),
            "created_count": len(created),
            "failure_count": len(failures),
        },
        title="Inserted Settings Batch",
    )


# === Template management ===

template_app = typer.Typer(help="Manage .setting templates.")
app.add_typer(template_app, name="template")

_DEFAULT_TEMPLATE_DIR = os.path.expanduser("~/resolve-templates")


def _get_template_dir() -> str:
    """Get template directory (configurable via env)."""
    return os.environ.get("RESOLVE_TEMPLATE_DIR", _DEFAULT_TEMPLATE_DIR)


def _template_directories() -> list[str]:
    directories = [_get_template_dir(), _bundled_template_dir()]
    seen: set[str] = set()
    normalized: list[str] = []
    for directory in directories:
        resolved = os.path.abspath(directory)
        if resolved in seen:
            continue
        seen.add(resolved)
        normalized.append(resolved)
    return normalized


@template_app.command("apply")
@handle_errors
def template_apply(
    template: str = typer.Argument(..., help="Template name or .setting path"),
    clip_name: Optional[str] = typer.Option(None, "--clip", help="Clip name (or current)"),
    track: Optional[int] = typer.Option(None, "--track", min=1, help="Video track index for deterministic clip selection"),
    record_frame: Optional[str] = typer.Option(None, "--record-frame", "--at", help="Record-domain frame/time inside the target clip"),
):
    """Apply a Fusion template .setting to a clip."""
    enforce_mutation_policy("fusion.mutation", intended_engine="fusion_native")
    template = template.strip()
    path = _resolve_template_setting_path(template)
    clip_name_value = _normalize_optional_string(clip_name)
    track_value = _option_value(track)
    record_frame_value = _option_value(record_frame)
    if is_dry_run():
        if clip_name_value or track_value is not None or record_frame_value is not None:
            conn = get_connection(require_timeline=True)
            if track_value is not None or record_frame_value is not None:
                clip_ops.cutagent_clip_by_selector(conn, clip_name_value, track=track_value, record_frame=record_frame_value)
            else:
                clip_ops.cutagent_clip(conn, clip_name_value)
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        target = "track_record" if track_value is not None else "named_clip" if clip_name_value else "current_clip"
        output(
            {
                "message": f"DRY-RUN: Would apply Fusion template '{template}' from '{path}' to '{clip_name_value or 'current clip'}'.",
                "action": "fusion.template.apply",
                "template": template,
                "path": path,
                "clip": clip_name_value,
                "selector": {"track": track_value, "record_frame": record_frame_value} if track_value is not None else None,
                "target": target,
                "route": ROUTE_IMPORT_FUSION_COMP,
                "would_apply": True,
                "dry_run": True,
            },
            title="Fusion Template Apply Plan",
        )
        return

    conn = get_connection(require_timeline=True)
    if track_value is not None or record_frame_value is not None:
        item = clip_ops.cutagent_clip_by_selector(conn, clip_name_value, track=track_value, record_frame=record_frame_value)
    else:
        item = clip_ops.cutagent_clip(conn, clip_name_value)
    if not hasattr(item, "ImportFusionComp"):
        raise APICallFailed("This clip doesn't support ImportFusionComp.")

    layout_prepared = None
    layout = None
    try:
        layout_prepared = _prepare_setting_import(path)
        import_path = str(layout_prepared.get("import_path") or path)
        result = item.ImportFusionComp(import_path)
    except Exception as exc:
        layout = _cleanup_prepared_setting(layout_prepared)
        raise APICallFailed(
            "ImportFusionComp failed. Check the .setting file format.",
            details={"template": template, "path": path, "import_path": import_path if "import_path" in locals() else path, "clip": clip_name, "layout": layout, "error": str(exc)},
        ) from exc
    layout = _cleanup_prepared_setting(layout_prepared)
    if not result:
        raise APICallFailed(
            "ImportFusionComp failed. Check the .setting file format.",
            details={"template": template, "path": path, "import_path": import_path, "clip": clip_name, "layout": layout},
        )
    set_verification_status("partial")
    set_recoverability("not_applicable")
    output(
        {
            "action": "fusion.template.apply",
            "template": template,
            "path": path,
            "import_path": import_path,
            "clip": clip_name_value,
            "selector": {"track": track_value, "record_frame": record_frame_value} if track_value is not None else None,
            "clip_readback": _media_pool_item_name(item) or None,
            "route": ROUTE_IMPORT_FUSION_COMP,
            "applied": True,
            "imported": True,
            "layout": layout,
        },
        title="Fusion Template Apply",
    )


@template_app.command("list")
@handle_errors
def template_list():
    """List .setting templates."""
    rows = []
    for directory in _template_directories():
        if not os.path.isdir(directory):
            continue
        for file_name in sorted(f for f in os.listdir(directory) if f.endswith(".setting")):
            rows.append({
                "name": file_name,
                "path": os.path.join(directory, file_name),
                "source": "bundled" if directory == _bundled_template_dir() else "user",
            })
    if not rows:
        output({"directories": _template_directories(), "templates": [], "note": "No template directories exist."})
        return
    output(rows, columns=[("name", "Template"), ("path", "Path")], quiet_key="name")


@template_app.command("show")
@handle_errors
def template_show(
    name: str = typer.Argument(..., help="Template filename"),
):
    """Show template contents."""
    path = None
    for directory in _template_directories():
        candidate = os.path.join(directory, name)
        if os.path.isfile(candidate):
            path = candidate
            break
    if not path:
        raise APICallFailed(f"Template not found: {name}")
    with open(path) as f:
        rendered = f.read()
    if get_output_mode() == "json":
        output({"template": name, "rendered": rendered}, title="Template")
    else:
        console.print(rendered)


@template_app.command("dir")
@handle_errors
def template_dir(
    set_path: Optional[str] = typer.Option(None, "--set", help="Set template directory"),
):
    """Show or set the template directory."""
    if set_path:
        if is_dry_run():
            output(
                {
                    "message": f"DRY-RUN: Would set template directory to: {set_path}",
                    "action": "fusion.template.dir",
                    "directory": set_path,
                    "would_set": True,
                    "would_create_directory": not os.path.isdir(set_path),
                    "persistent": False,
                },
                title="Fusion Template Directory",
            )
            return
        existed = os.path.isdir(set_path)
        os.environ["RESOLVE_TEMPLATE_DIR"] = set_path
        os.makedirs(set_path, exist_ok=True)
        output(
            {
                "message": f"Template directory set to: {set_path}",
                "action": "fusion.template.dir",
                "directory": set_path,
                "created_directory": not existed,
                "persistent": False,
            },
            title="Fusion Template Directory",
        )
    else:
        output({"directory": _get_template_dir()})


@template_app.command("scaffold")
@handle_errors
def template_scaffold(
    kind: str = typer.Argument(..., help="title|generator|effect|transition"),
    name: str = typer.Argument(..., help="Template name"),
    output_path: Optional[str] = typer.Option(None, "--output", help="Output .setting path"),
    overwrite: bool = typer.Option(False, "--overwrite", help="Replace an existing template file"),
):
    """Scaffold a minimal Fusion template."""
    output(sdk_tools.fusion_template_scaffold(kind, name, output_path, dry_run=is_dry_run(), overwrite=overwrite), title="Fusion Template Scaffold")


@template_app.command("validate")
@handle_errors
def template_validate(
    path: str = typer.Argument(..., help=".setting path"),
):
    """Validate a Fusion template file."""
    output(sdk_tools.validate_fusion_template(path), title="Fusion Template Validate")


@template_app.command("install")
@handle_errors
def template_install(
    path: str = typer.Argument(..., help=".setting path"),
    kind: str = typer.Option(..., "--kind", help="title|generator|effect|transition"),
    overwrite: bool = typer.Option(False, "--overwrite", help="Replace an existing installed template"),
):
    """Install a Fusion template into the user DaVinci Resolve templates folder."""
    output(sdk_tools.install_fusion_template(path, kind, dry_run=is_dry_run(), overwrite=overwrite), title="Fusion Template Install")


@template_app.command("uninstall")
@handle_errors
def template_uninstall(
    name: str = typer.Argument(..., help="Template name"),
    kind: str = typer.Option(..., "--kind", help="title|generator|effect|transition"),
):
    """Remove an installed Fusion template."""
    output(sdk_tools.uninstall_fusion_template(name, kind, dry_run=is_dry_run()), title="Fusion Template Uninstall")


@template_app.command("package-drfx")
@handle_errors
def template_package_drfx(
    path: str = typer.Argument(..., help="Template folder path"),
    output_file: str = typer.Option(..., "--output", help="Output .drfx path"),
    overwrite: bool = typer.Option(False, "--overwrite", help="Replace an existing archive"),
):
    """Package a Fusion template folder as a .drfx bundle."""
    output(sdk_tools.package_drfx(path, output_file, dry_run=is_dry_run(), overwrite=overwrite), title="Fusion Template Package")


@template_app.command("unpack-drfx")
@handle_errors
def template_unpack_drfx(
    file: str = typer.Argument(..., help=".drfx bundle path"),
    output_dir: str = typer.Option(..., "--output", help="Output directory"),
    overwrite: bool = typer.Option(False, "--overwrite", help="Replace existing files"),
):
    """Unpack a .drfx bundle."""
    output(sdk_tools.unpack_drfx(file, output_dir, dry_run=is_dry_run(), overwrite=overwrite), title="Fusion Template Unpack")


template_icon_app = typer.Typer(help="Fusion template icon operations.")
template_app.add_typer(template_icon_app, name="icon")
