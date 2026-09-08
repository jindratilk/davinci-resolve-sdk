def _insert_setting_precise(
    conn,
    *,
    path: str,
    clip_name: str,
    at: str,
    record_frame: int | None,
    duration: str,
    track: int,
    holder: str,
    holder_kind: str,
    position_x: float | None,
    position_y: float | None,
    prefer_native_direct: bool = False,
) -> dict[str, Any]:
    if track < 1:
        raise ValidationError("Track must be 1 or greater.", details={"track": track})
    normalized_holder_kind = str(holder_kind or "fusion").strip().lower().replace("_", "-")
    if normalized_holder_kind not in {"fusion", "textplus"}:
        raise ValidationError(
            "Unsupported holder kind.",
            details={"holder_kind": holder_kind, "allowed": ["fusion", "textplus"]},
    )
    duration_frames = _parse_positive_duration_frames(duration, conn.fps)
    resolved_record_frame = int(record_frame) if record_frame is not None else parse_record_frame(str(at), conn.fps, _connection_start_frame(conn))

    holder_lookup: dict[str, Any] = {"holder_kind": normalized_holder_kind}
    candidates = _holder_name_candidates(holder, normalized_holder_kind)
    holder_item, holder_lookup = _find_media_pool_item_by_names(conn, candidates)
    holder_lookup["holder_kind"] = normalized_holder_kind

    fresh_empty_timeline_settle = None
    track_summary = _ensure_video_track(conn, track)
    append_summary = None
    native_insert = None
    db_move = None
    db_materialization = None
    native_direct = False
    native_track_lock_direct = False
    track_locks = None
    duration_native_trim = None
    duration_db_update = None
    if holder_item is not None:
        route = ROUTE_MEDIA_POOL_HOLDER_IMPORT_FUSION_COMP
        item, append_summary = _append_holder_to_timeline(
            conn,
            holder_item,
            record_frame=resolved_record_frame,
            duration_frames=duration_frames,
            track_index=track,
            name=clip_name,
        )
    else:
        holder_lookup["fallback_used"] = True
        holder_lookup["fallback_reason"] = "media_pool_holder_not_found"
        native_direct = bool(prefer_native_direct and normalized_holder_kind == "textplus" and track == 1)
        if native_direct:
            route = ROUTE_NATIVE_TEXTPLUS_IMPORT_FUSION_COMP
            item, native_insert = _insert_native_holder_at_frame(
                conn,
                holder=holder,
                holder_kind=normalized_holder_kind,
                record_frame=resolved_record_frame,
            )
        else:
            return _insert_setting_precise_via_scratch_db(
                conn,
                path=path,
                clip_name=clip_name,
                duration=duration,
                duration_frames=duration_frames,
                track=track,
                record_frame=resolved_record_frame,
                holder=holder,
                holder_kind=normalized_holder_kind,
                position_x=position_x,
                position_y=position_y,
                holder_lookup=holder_lookup,
                track_summary=track_summary,
                fresh_empty_timeline_settle=fresh_empty_timeline_settle,
            )
    if item is None:
        raise APICallFailed(
            "Failed to append Fusion/Text+ holder to timeline.",
            details={"path": path, "name": clip_name, "track": track, "record_frame": resolved_record_frame, **(append_summary or {})},
        )

    imported = True
    cleanup = None
    layout_prepared = None
    layout = None
    importer = getattr(item, "ImportFusionComp", None)
    if not callable(importer):
        cleanup = _safe_delete_timeline_item(conn, item)
        raise APICallFailed(
            "Inserted holder clip does not support ImportFusionComp.",
            details={"holder": holder, "holder_kind": normalized_holder_kind, "cleanup": cleanup},
            recoverability="manual" if _timeline_delete_failed(cleanup) else "retryable",
        )
    try:
        layout_prepared = _prepare_setting_import(path)
        import_path = str(layout_prepared.get("import_path") or path)
        imported = importer(import_path)
    except Exception as exc:
        layout = _cleanup_prepared_setting(layout_prepared)
        cleanup = _safe_delete_timeline_item(conn, item)
        raise APICallFailed(
            "ImportFusionComp failed. Check the .setting file format.",
            details={
                "path": path,
                "import_path": import_path if "import_path" in locals() else path,
                "holder": holder,
                "holder_kind": normalized_holder_kind,
                "cleanup": cleanup,
                "layout": layout,
                "error": str(exc),
            },
            recoverability="manual" if _timeline_delete_failed(cleanup) else "retryable",
        ) from exc
    if not imported:
        layout = _cleanup_prepared_setting(layout_prepared)
        cleanup = _safe_delete_timeline_item(conn, item)
        raise APICallFailed(
            "ImportFusionComp failed. Check the .setting file format.",
            details={"path": path, "import_path": import_path, "holder": holder, "holder_kind": normalized_holder_kind, "cleanup": cleanup, "layout": layout},
            recoverability="manual" if _timeline_delete_failed(cleanup) else "retryable",
        )
    layout = _cleanup_prepared_setting(layout_prepared)

    item_props = _apply_timeline_item_name_and_duration(item, name=clip_name, duration_frames=duration_frames)
    position_result = _apply_timeline_item_position(item, position_x, position_y) if position_x is not None or position_y is not None else {
        "requested": {"x": position_x, "y": position_y},
        "applied": False,
    }
    try:
        enumerated = _unique_enumerated_video_item(
            conn,
            track_index=track,
            start=resolved_record_frame,
            duration=duration_frames,
        )
    except Exception as exc:
        cleanup = _safe_delete_timeline_item(conn, item)
        raise APICallFailed(
            "Inserted Fusion/Text+ holder did not verify exact enumerated placement.",
            details={
                "track": track,
                "record_frame": resolved_record_frame,
                "duration_frames": duration_frames,
                "cleanup": cleanup,
                "verification_error": {
                    "type": exc.__class__.__name__,
                    "message": str(exc),
                    "details": getattr(exc, "details", None),
                },
            },
            recoverability="manual",
        ) from exc
    item = enumerated["item"]
    readback = dict(enumerated["readback"])
    tool_summary = _summarize_imported_fusion_tools(item)
    if readback.get("duration") == duration_frames:
        item_props["duration_readback_frames"] = duration_frames
        if isinstance(duration_native_trim, dict) and duration_native_trim.get("ok"):
            item_props["duration_applied"] = True
            item_props["duration_property"] = "native_textplus_cut_trim"
    verification = {
        "imported": bool(imported),
        "track_requested": track,
        "track_readback": readback.get("track_index"),
        "record_frame_requested": resolved_record_frame,
        "start_readback": readback.get("start"),
        "duration_requested_frames": duration_frames,
        "duration_readback_frames": readback.get("duration"),
        "fusion_comp_accessible": bool(tool_summary.get("accessible")),
        "tool_count": tool_summary.get("tool_count"),
        "node_status_verified": False,
        "node_probe_verified": False,
        "visual_output_verified": False,
    }
    verification["track_ok"] = readback.get("track_index") == track
    verification["start_ok"] = readback.get("start") == resolved_record_frame
    verification["duration_ok"] = readback.get("duration") == duration_frames

    if tool_summary.get("accessible") is False:
        set_verification_status("partial")
    elif tool_summary.get("tool_count") == 0:
        cleanup = _safe_delete_timeline_item(conn, item)
        set_verification_status("failed")
        raise APICallFailed(
            "Inserted .setting, but the Fusion composition has no readable tools.",
            details={"path": path, "verification": verification, "item": readback, "cleanup": cleanup},
            recoverability="manual" if _timeline_delete_failed(cleanup) else "retryable",
        )
    elif not (verification["track_ok"] and verification["start_ok"] and verification["duration_ok"]):
        set_verification_status("pending_manual")
    else:
        set_verification_status("partial")

    return {
        "path": path,
        "import_path": import_path,
        "name": clip_name,
        "holder": holder,
        "holder_kind": normalized_holder_kind,
        "holder_lookup": holder_lookup,
        "track": track,
        "record_frame": resolved_record_frame,
        "duration": duration,
        "duration_frames": duration_frames,
        "position_requested": {"x": position_x, "y": position_y},
        "position_applied": position_result,
        "route": route,
        "fresh_empty_timeline_settle": fresh_empty_timeline_settle,
        "track_summary": track_summary,
        "append": append_summary,
        "native_insert": native_insert,
        "native_direct": native_direct,
        "native_track_lock_direct": native_track_lock_direct,
        "track_locks": track_locks,
        "duration_native_trim": duration_native_trim,
        "db_materialization": db_materialization,
        "db_move": db_move,
        "duration_db_update": duration_db_update,
        "connection_reloaded": bool(db_move.get("connection_reloaded")) if isinstance(db_move, dict) else bool(duration_db_update),
        "item": {**item_props, **readback},
        "fusion": tool_summary,
        "layout": layout,
        "verification": verification,
        "cleanup": cleanup,
    }


# === Composition Commands ===

comp_app = typer.Typer(help="Composition operations (play, render, info).")
app.add_typer(comp_app, name="comp")


@comp_app.command("current")
@handle_errors
def comp_current():
    """Show current composition info."""
    conn = get_connection(require_timeline=True)
    api = fusion_api.get_fusion_api(conn)

    info = api.get_comp_info()
    output(info, title="Current Fusion Composition")


@comp_app.command("play")
@handle_errors
def comp_play():
    """Play the composition."""
    enforce_mutation_policy("fusion.mutation", intended_engine="fusion_native")
    conn = get_connection(require_timeline=True)
    api = fusion_api.get_fusion_api(conn)

    api.play()
    success("Started playback.")


@comp_app.command("stop")
@handle_errors
def comp_stop():
    """Stop playback."""
    enforce_mutation_policy("fusion.mutation", intended_engine="fusion_native")
    conn = get_connection(require_timeline=True)
    api = fusion_api.get_fusion_api(conn)

    api.stop()
    success("Stopped playback.")


@comp_app.command("render")
@handle_errors
def comp_render(
    wait: bool = typer.Option(False, "--wait", help="Wait for render to complete"),
):
    """Render the composition."""
    enforce_mutation_policy("fusion.mutation", intended_engine="fusion_native")
    conn = get_connection(require_timeline=True)
    api = fusion_api.get_fusion_api(conn)

    api.render(wait=wait)
    if wait:
        success("Render completed.")
    else:
        success("Render started.")


@comp_app.command("range")
@handle_errors
def comp_range(
    start: int = typer.Argument(..., help="Start frame"),
    end: int = typer.Argument(..., help="End frame"),
):
    """Set composition render range."""
    enforce_mutation_policy("fusion.mutation", intended_engine="fusion_native")
    conn = get_connection(require_timeline=True)
    api = fusion_api.get_fusion_api(conn)

    api.set_render_range(start, end)
    success(f"Set render range: {start} - {end}")
