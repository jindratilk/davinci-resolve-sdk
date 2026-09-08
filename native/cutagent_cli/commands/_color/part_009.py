@app.command("grade-copy")
@handle_errors
def grade_copy(
    source: str = typer.Option(..., "--from", help="Source clip name"),
    targets: str = typer.Option(..., "--to", help="Target clip names (comma-separated)"),
):
    """Copy grade from one clip to others."""
    set_execution_engine("db_workaround", 0.9)
    set_capability_context("color.grade_copy_apply", "supported")
    source_name = source.strip()
    if not source_name:
        raise ValidationError("Specify a source clip.")
    target_list = [t.strip() for t in targets.split(",") if t.strip()]
    if not target_list:
        raise ValidationError("Specify at least one target clip.")
    enforce_mutation_policy("color.grade_copy_apply", intended_engine="db_workaround", mutating=not is_dry_run())
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            {
                "source": source_name,
                "targets": target_list,
                "copied_count": 0,
                "copied": False,
                "would_copy": True,
                "resolved": False,
            },
            title="Grade Copy",
        )
        return
    from ..core import color_page_db

    conn = get_connection(require_timeline=True)
    data = color_page_db.copy_color_grade_db(conn, source_name=source_name, target_names=target_list)
    set_verification_status("verified")
    set_recoverability("not_applicable")
    output(data, title="Grade Copy")


@app.command("grade-apply")
@handle_errors
def grade_apply(
    path: str = typer.Argument(..., help="DRX file path"),
    clip_name: Optional[str] = typer.Option(None, "--clip"),
    mode: int = typer.Option(0, help="Grade mode: 0=No keyframes, 1=Source TC aligned, 2=Start Frames aligned"),
    require_render_proof: bool = typer.Option(True, "--require-render-proof/--setup-only", help="Export before/after Color Page frames or use exact grade readback only"),
):
    """Apply a grade from a DRX file."""
    set_execution_engine("api_native")
    set_capability_context("color.grade_apply_drx", "supported")
    if mode not in {0, 1, 2}:
        raise ValidationError(
            "Grade apply mode must be 0, 1, or 2.",
            details={
                "mode": mode,
                "supported_modes": {
                    "0": "No keyframes",
                    "1": "Source TC aligned",
                    "2": "Start Frames aligned",
                },
            },
        )
    enforce_mutation_policy(
        "color.grade_apply_drx",
        intended_engine="api_native",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        dry_run_message(f"Would apply grade from '{path}' (mode={mode})")
        return
    resolved_path = str(Path(path).expanduser().resolve())
    if not Path(resolved_path).is_file():
        raise ValidationError("DRX grade file not found.", details={"path": path, "resolved_path": resolved_path})
    from ..core import color_page_db, project_ops

    conn = get_connection(require_timeline=True)
    timeline_ops.require_sdk_color_mutation_guard(conn)
    require_render_proof = bool(_option_value(require_render_proof, True))
    render_proof = (
        _begin_color_render_proof(
            conn,
            clip_name=clip_name,
            route="api_native_grade_apply_drx",
            deliver_proof=True,
        )
        if require_render_proof
        else None
    )
    before_readback = color_page_db.read_color_grade_for_clip(conn, clip_name=clip_name)
    before_signature = color_page_db._grade_state_signature(before_readback)
    color_ops.apply_grade_from_file(conn, clip_name, resolved_path, mode)
    project_ops.save_current_project_if_available(conn)
    after_readback = color_page_db.read_color_grade_for_clip(conn, clip_name=clip_name)
    after_signature = color_page_db._grade_state_signature(after_readback)
    if not after_signature["has_grade"] or after_signature["raw_param_count"] <= 0:
        raise APICallFailed(
            "ApplyGradeFromDRX returned success but Color Page grade readback did not verify.",
            details={
                "clip": clip_name,
                "path": resolved_path,
                "requested_path": path,
                "mode": mode,
                "before_signature": before_signature,
                "after_signature": after_signature,
                "after_readback": after_readback,
            },
        )
    data = {
        "path": resolved_path,
        "requested_path": path,
        "clip": after_readback.get("clip") or clip_name,
        "mode": mode,
        "applied": True,
        "verified": True,
        "route": "api_native_grade_apply_drx",
        "verification": {
            "status": "verified",
            "route": "db_readback_after_api_apply",
            "clip": after_readback.get("clip"),
            "clip_id": after_readback.get("clip_id"),
            "changed": after_signature["sha256"] != before_signature["sha256"],
            "before_signature_sha256": before_signature["sha256"],
            "after_signature_sha256": after_signature["sha256"],
            "has_grade": after_signature["has_grade"],
            "raw_param_count": after_signature["raw_param_count"],
        },
    }
    if render_proof is not None:
        data["render_proof"] = _complete_color_render_proof(conn, render_proof, partial_result=data)
        data["verification"]["render_proof_status"] = data["render_proof"]["status"]
        data["verification"]["render_proof_route"] = data["render_proof"]["route"]
        data["verification"]["render_proof_required"] = True
    else:
        data["verification"]["render_proof_status"] = "not_requested"
        data["verification"]["render_proof_required"] = False
    set_verification_status("verified")
    set_recoverability("not_applicable")
    output(data, title="Grade Apply")


@app.command("lut-refresh")
@handle_errors
def lut_refresh():
    """Refresh the project LUT list."""
    enforce_mutation_policy("system.lut_refresh", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        dry_run_message("Would refresh project LUT list")
        return
    conn = get_connection(require_project=True)
    color_ops.refresh_lut_list(conn)
    success("LUT list refreshed.")
