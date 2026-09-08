from __future__ import annotations

@app.command("export-lut")
@handle_errors
def export_lut(
    output_path: str = typer.Argument(..., help="Output LUT path"),
    clip_name: Optional[str] = typer.Option(None, "--clip", help="Clip name (current clip when omitted)"),
    export_type: int = typer.Option(2, "--type", help="DaVinci Resolve ExportLUT type integer (default: 2)"),
):
    """Export current clip grade as LUT from Color page context."""
    output_path = lut_generator.validate_cube_output_path(output_path)
    enforce_mutation_policy("clip.export_lut", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        output(
            {
                "clip": clip_name,
                "target": {
                    "kind": "named_clip" if clip_name else "current_clip",
                    "name": clip_name,
                    "resolved": False,
                },
                "export_type": export_type,
                "output_path": output_path,
                "page_switch_required": True,
                "exported": False,
                "would_export": True,
            },
            title="LUT Export",
        )
        return
    conn = get_connection(require_timeline=True)
    data = color_ops.export_clip_lut(conn, clip_name, export_type=export_type, output_path=output_path)
    output(data, title="LUT Export")


# --- Versions ---

version_app = typer.Typer(help="Color version management.")
app.add_typer(version_app, name="version")


@version_app.command("list")
@handle_errors
def version_list(
    clip_name: Optional[str] = typer.Argument(None),
):
    """List color versions."""
    conn = get_connection(require_timeline=True)
    rows = color_ops.list_color_versions(conn, clip_name)
    output(rows, columns=[("name", "Name"), ("type", "Type")], title="Color Versions")


@version_app.command("add")
@handle_errors
def version_add(
    name_or_clip: str = typer.Argument(..., help="Version name (or clip name in legacy syntax)"),
    maybe_name: Optional[str] = typer.Argument(None, help="Version name in legacy syntax: color version add <clip> <name>"),
    remote: bool = typer.Option(False, "--remote"),
    clip_name: Optional[str] = typer.Option(None, "--clip"),
):
    """Add a new color version."""
    if maybe_name is not None:
        if clip_name is not None:
            raise ValidationError("Use either '--clip <name> <version>' or legacy '<clip> <version>', not both.")
        clip_name = name_or_clip
        name = maybe_name
    else:
        name = name_or_clip

    enforce_mutation_policy("color.grade_copy_apply", intended_engine="workaround_setting")
    conn = get_connection(require_timeline=True)
    vtype = "remote" if remote else "local"
    color_ops.add_color_version(conn, clip_name, name, remote)
    success(f"Added {vtype} version: {name}")


@version_app.command("load")
@handle_errors
def version_load(
    name: str = typer.Argument(..., help="Version name"),
    remote: bool = typer.Option(False, "--remote"),
    clip_name: Optional[str] = typer.Option(None, "--clip"),
):
    """Load a color version."""
    _run_version_load(name=name, remote=remote, clip_name=clip_name)


def _run_version_load(*, name: str, remote: bool, clip_name: Optional[str]) -> None:
    set_capability_context("color.grade_copy_apply", "supported")
    set_execution_engine("workaround_setting")
    normalized_name = name.strip()
    if not normalized_name:
        raise ValidationError(
            "Version name must not be empty.",
            details={"name": name},
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
    enforce_mutation_policy("color.grade_copy_apply", intended_engine="workaround_setting", mutating=not is_dry_run())
    set_execution_engine("workaround_setting")
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            {
                "clip": normalized_clip,
                "name": normalized_name,
                "remote": remote,
                "version_type": "remote" if remote else "local",
                "would_load": True,
                "loaded": False,
                "active_after_load": None,
                "resolved": False,
            },
            title="Color Version Load Preview",
        )
        return
    conn = get_connection(require_timeline=True)
    data = color_ops.load_color_version(conn, normalized_clip, normalized_name, remote)
    if data.get("active_after_load") is True:
        set_verification_status("verified")
        set_recoverability("not_applicable")
    else:
        set_verification_status("pending_manual")
        set_recoverability("manual")
    output(data, title="Color Version Load")


@version_app.command("activate")
@handle_errors
def version_activate(
    name: str = typer.Argument(..., help="Version name"),
    remote: bool = typer.Option(False, "--remote"),
    clip_name: Optional[str] = typer.Option(None, "--clip"),
):
    """Activate/load a color version and verify it became current."""
    _run_version_load(name=name, remote=remote, clip_name=clip_name)


@version_app.command("rollback")
@handle_errors
def version_rollback(
    name: str = typer.Argument(..., help="Version name to roll back to"),
    remote: bool = typer.Option(False, "--remote"),
    clip_name: Optional[str] = typer.Option(None, "--clip"),
):
    """Roll back by loading a named color version and verifying it became current."""
    _run_version_load(name=name, remote=remote, clip_name=clip_name)


@version_app.command("duplicate")
@handle_errors
def version_duplicate(
    name: str = typer.Argument(..., help="New duplicate version name"),
    remote: bool = typer.Option(False, "--remote"),
    clip_name: Optional[str] = typer.Option(None, "--clip"),
):
    """Duplicate the current color grade into a new named version."""
    normalized_name = name.strip()
    if not normalized_name:
        raise ValidationError(
            "Version name must not be empty.",
            details={"name": name},
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
    enforce_mutation_policy("color.grade_copy_apply", intended_engine="api_native", mutating=not is_dry_run())
    set_execution_engine("api_native")
    set_capability_context("color.grade_copy_apply", "supported")
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            {
                "clip": normalized_clip,
                "name": normalized_name,
                "remote": remote,
                "version_type": "remote" if remote else "local",
                "would_duplicate": True,
                "duplicated": False,
                "resolved": False,
            },
            title="Color Version Duplicate Preview",
        )
        return
    conn = get_connection(require_timeline=True)
    color_ops.add_color_version(conn, normalized_clip, normalized_name, remote)
    set_verification_status("verified")
    set_recoverability("not_applicable")
    output(
        {
            "clip": normalized_clip,
            "name": normalized_name,
            "remote": remote,
            "version_type": "remote" if remote else "local",
            "duplicated": True,
            "method": "TimelineItem.AddVersion",
            "verification": {
                "status": "verified",
                "note": "DaVinci Resolve API accepted AddVersion; use color version activate/load to verify a specific active version.",
            },
        },
        title="Color Version Duplicate",
    )


@version_app.command("delete")
@handle_errors
def version_delete(
    name: str = typer.Argument(..., help="Version name"),
    remote: bool = typer.Option(False, "--remote"),
    clip_name: Optional[str] = typer.Option(None, "--clip"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
):
    """Delete a color version."""
    enforce_mutation_policy("color.grade_copy_apply", intended_engine="workaround_setting")
    require_force_for_machine_mode(
        force=force,
        action="color.version.delete",
        target_kind="color_version",
        target_name=name,
        prompt=f"Delete color version '{name}'?",
        details={"clip": clip_name, "remote": remote},
    )
    conn = get_connection(require_timeline=True)
    data = color_ops.delete_color_version(conn, clip_name, name, remote)
    output(data, title="Deleted Color Version")


# --- Source / Remote Grades ---

source_grade_app = typer.Typer(help="Source/remote grade scoping for repeated timeline cuts.")
app.add_typer(source_grade_app, name="source-grade")


def _normalize_source_grade_scope(scope: str) -> str:
    normalized = str(scope or "").strip().lower()
    if normalized not in {"current-source", "timeline-sources"}:
        raise ValidationError(
            "Unsupported source grade scope.",
            details={"scope": scope, "supported_scopes": ["current-source", "timeline-sources"]},
            recoverability="not_applicable",
        )
    return normalized


@source_grade_app.command("plan")
@handle_errors
def source_grade_plan(
    clip_name: Optional[str] = typer.Option(None, "--clip", help="Clip name (current clip when omitted)"),
    scope: str = typer.Option("current-source", "--scope", help="current-source or timeline-sources"),
    include_singletons: bool = typer.Option(False, "--include-singletons", help="Include one-off sources in the plan"),
):
    """Plan whether color grading should use remote/source scope or local timeline scope."""
    normalized_scope = _normalize_source_grade_scope(scope)
    set_capability_context("color.source_remote_grade", "supported")
    set_execution_engine("api_native")
    set_verification_status("verified")
    set_recoverability("not_applicable")
    conn = get_connection(require_timeline=True)
    data = color_source_grade.plan_source_grade(
        conn,
        clip_name=clip_name,
        scope=normalized_scope,
        include_singletons=include_singletons,
    )
    output(data, title="Source Grade Plan")


@source_grade_app.command("prepare-remote")
@handle_errors
def source_grade_prepare_remote(
    name: str = typer.Argument(..., help="Remote version name to create/load"),
    clip_name: Optional[str] = typer.Option(None, "--clip", help="Clip name (current clip when omitted)"),
    create: bool = typer.Option(True, "--create/--no-create", help="Create the remote version if missing on the selected source"),
    load: bool = typer.Option(True, "--load/--no-load", help="Load the remote version on every same-source timeline instance"),
    include_singletons: bool = typer.Option(False, "--include-singletons", help="Allow a one-off source to use remote scope"),
):
    """Create/load one shared remote grade version for all timeline cuts from the same source media."""
    set_capability_context("color.source_remote_grade", "supported")
    set_execution_engine("api_native")
    enforce_mutation_policy("color.source_remote_grade", intended_engine="api_native", mutating=not is_dry_run())
    normalized_name = str(name or "").strip()
    if not normalized_name:
        raise ValidationError(
            "Remote version name must not be empty.",
            details={"name": name},
            recoverability="not_applicable",
        )
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            {
                "name": normalized_name,
                "clip": clip_name,
                "scope": "current-source",
                "remote": True,
                "version_type": "remote",
                "would_create": create,
                "would_load": load,
                "resolved": False,
            },
            title="Source Remote Grade Preview",
        )
        return
    conn = get_connection(require_timeline=True)
    with color_ops._with_required_page(conn, "color"):
        data = color_source_grade.prepare_remote_source_grade(
            conn,
            name=normalized_name,
            clip_name=clip_name,
            create=create,
            load=load,
            include_singletons=include_singletons,
        )
    verification = data.get("verification") or {}
    if verification.get("status") == "verified":
        set_verification_status("verified")
        set_recoverability("not_applicable")
    else:
        set_verification_status("failed")
        set_recoverability("manual")
    output(data, title="Prepared Source Remote Grade")


def _source_grade_instance_proof_target(conn, instance: dict, *, frame_offset: int = 0) -> dict[str, object]:
    from ..utils.timecode import seconds_to_timecode

    timeline_start = _color_timeline_start_frame(conn)
    start = _absolute_timeline_frame(conn, int(instance["start"]), timeline_start=timeline_start)
    duration = max(1, int(instance.get("duration") or 1))
    midpoint_offset = max(0, min(duration // 2, duration - 1))
    target_frame = start + midpoint_offset + int(frame_offset)
    end = start + duration
    target_frame = max(start, min(target_frame, end - 1))
    target_tc = seconds_to_timecode(target_frame / conn.fps, conn.fps)
    return {
        "clip": instance.get("name"),
        "position": target_tc,
        "target_frame": target_frame,
        "target_timecode": target_tc,
        "target_source": "source_grade_instance_midpoint",
        "frame_offset": int(frame_offset),
        "target_clip": {
            "name": instance.get("name"),
            "track_type": instance.get("track_type"),
            "track_index": instance.get("track_index"),
            "index_in_track": instance.get("index_in_track"),
            "start": instance.get("start"),
            "duration": instance.get("duration"),
            "end": instance.get("end"),
            "source_identity": instance.get("source_identity"),
        },
    }


def _source_grade_capture_summary(capture: dict[str, object]) -> dict[str, object]:
    return {
        "path": capture.get("path"),
        "visual_check_path": capture.get("visual_check_path"),
        "metadata": capture.get("metadata"),
        "playhead": capture.get("playhead"),
    }


def _capture_source_grade_instance_proofs(
    conn,
    *,
    proof_dir: Path,
    targets: list[dict[str, object]],
    stem: str,
) -> list[dict[str, object]]:
    captures: list[dict[str, object]] = []
    for index, target in enumerate(targets, 1):
        capture = _capture_color_render_proof_frame(
            conn,
            target=target,
            path=proof_dir / f"{stem}_{index:02d}.png",
        )
        captures.append(capture)
    return captures


@source_grade_app.command("apply-cdl")
@handle_errors
def source_grade_apply_cdl(
    version_name: str = typer.Option("CutAgent Source Grade", "--version-name", help="Remote source color version to create/load"),
    clip_name: Optional[str] = typer.Option(None, "--clip", help="Clip name (current clip when omitted)"),
    node: int = typer.Option(1, "--node", help="Node index"),
    slope: Optional[str] = typer.Option(None, help="Slope as 'R G B'"),
    offset: Optional[str] = typer.Option(None, help="Offset as 'R G B'"),
    power: Optional[str] = typer.Option(None, help="Power as 'R G B'"),
    saturation: Optional[float] = typer.Option(None, "--sat", help="Saturation"),
    include_singletons: bool = typer.Option(False, "--include-singletons", help="Allow a one-off source to use remote scope"),
    proof_instances: int = typer.Option(2, "--proof-instances", help="Number of same-source instances to render-proof; 0 means all"),
):
    """Apply a CDL to one shared remote/source grade and proof multiple same-source timeline instances."""
    normalized_name = str(version_name or "").strip()
    if not normalized_name:
        raise ValidationError(
            "Remote version name must not be empty.",
            details={"version_name": version_name},
            recoverability="not_applicable",
        )
    if proof_instances < 0:
        raise ValidationError(
            "--proof-instances must be 0 or a positive integer.",
            details={"proof_instances": proof_instances},
            recoverability="not_applicable",
        )
    node_index, cdl_requested = color_ops.validate_cdl_payload(node, slope, offset, power, saturation)
    if len(cdl_requested) == 1:
        raise ValidationError("source-grade apply-cdl requires at least one option: --slope/--offset/--power/--sat")

    set_capability_context("color.source_remote_grade", "supported")
    set_execution_engine("api_native")
    enforce_mutation_policy("color.source_remote_grade", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            {
                "clip": clip_name,
                "version_name": normalized_name,
                "remote": True,
                "version_type": "remote",
                "node": node_index,
                "cdl_requested": cdl_requested,
                "proof_instances": proof_instances,
                "would_prepare_remote": True,
                "would_apply": True,
                "resolved": False,
            },
            title="Source Remote CDL Preview",
        )
        return

    from ..core import project_ops

    conn = get_connection(require_timeline=True)
    original_playhead = timeline_ops.get_playhead(conn)
    proof_dir = Path(tempfile.mkdtemp(prefix="cutagent_source_grade_cdl_proof_"))
    with color_ops._with_required_page(conn, "color"):
        plan = color_source_grade.plan_source_grade(
            conn,
            clip_name=clip_name,
            scope="current-source",
            include_singletons=include_singletons,
        )
        groups = plan.get("groups") or []
        if not groups:
            raise ValidationError(
                "No same-source timeline instances were found for source remote CDL grading.",
                details={"clip": clip_name, "include_singletons": include_singletons, "recommendation": plan.get("recommendation")},
                recoverability="manual",
            )
        instances = list(groups[0].get("instances") or [])
        if len(instances) > 1 and proof_instances == 1:
            raise ValidationError(
                "Remote/source grading must proof at least two same-source instances when multiple instances exist.",
                details={"proof_instances": proof_instances, "same_source_instance_count": len(instances)},
                recoverability="not_applicable",
            )
        if proof_instances == 0:
            proof_count = len(instances)
        else:
            proof_count = min(len(instances), max(1, int(proof_instances)))
        proof_targets = [
            _source_grade_instance_proof_target(conn, instance)
            for instance in instances[:proof_count]
        ]

        prepare = color_source_grade.prepare_remote_source_grade(
            conn,
            name=normalized_name,
            clip_name=clip_name,
            create=True,
            load=True,
            include_singletons=include_singletons,
        )
        before_captures = _capture_source_grade_instance_proofs(
            conn,
            proof_dir=proof_dir,
            targets=proof_targets,
            stem="before",
        )
        if proof_targets:
            timeline_ops.set_playhead(conn, str(proof_targets[0]["target_timecode"]), return_details=True)
        applied = color_ops.set_cdl(
            conn,
            None,
            node_index,
            slope=slope,
            offset=offset,
            power=power,
            saturation=saturation,
        )
        project_ops.save_current_project_if_available(conn)
        readback = color_ops.get_cdl(conn, None, node_index=node_index)
        after_captures = _capture_source_grade_instance_proofs(
            conn,
            proof_dir=proof_dir,
            targets=proof_targets,
            stem="after",
        )

    instance_proofs: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []
    for index, (instance, target, before, after) in enumerate(
        zip(instances[:proof_count], proof_targets, before_captures, after_captures),
        1,
    ):
        comparison = _compare_before_after_pixels(before["rgb"], after["rgb"])
        changed_pixel_count = int(comparison.get("changed_pixel_count") or 0)
        proof_status = "verified" if changed_pixel_count > 0 else "failed"
        row = {
            "index": index,
            "status": proof_status,
            "instance": instance,
            "target": target,
            "before": _source_grade_capture_summary(before),
            "after": _source_grade_capture_summary(after),
            "comparison": comparison,
        }
        instance_proofs.append(row)
        if proof_status != "verified":
            failures.append(row)

    data = {
        "clip": clip_name,
        "version_name": normalized_name,
        "remote": True,
        "version_type": "remote",
        "node": node_index,
        "cdl_requested": cdl_requested,
        "applied": bool(applied),
        "route": "api_native_source_remote_cdl_set",
        "prepare_remote": prepare,
        "readback": readback,
        "render_proof": {
            "status": "verified" if not failures else "failed",
            "proof_kind": "source_remote_multi_instance_color_page_stills",
            "proof_dir": str(proof_dir),
            "proofed_instance_count": len(instance_proofs),
            "same_source_instance_count": len(instances),
            "instances": instance_proofs,
        },
        "verification": {
            "status": "verified" if not failures else "failed",
            "route": "api_native_source_remote_cdl_set",
            "remote_scope_status": (prepare.get("verification") or {}).get("status"),
            "render_proof_status": "verified" if not failures else "failed",
            "proofed_instance_count": len(instance_proofs),
            "same_source_instance_count": len(instances),
        },
    }

    if isinstance(original_playhead, dict) and original_playhead.get("timecode"):
        try:
            data["render_proof"]["restored_playhead"] = timeline_ops.set_playhead(
                conn,
                str(original_playhead["timecode"]),
                return_details=True,
            )
        except Exception as exc:
            data["render_proof"]["restore_warning"] = str(exc)

    if failures:
        set_verification_status("failed")
        set_recoverability("manual")
        raise ColorRenderProofFailed(
            "Source remote CDL command completed, but at least one same-source timeline instance did not change in rendered pixels.",
            details={"reason": "source_remote_instance_render_proof_failed", "partial_result": data},
        )

    set_verification_status("verified")
    set_recoverability("not_applicable")
    output(data, title="Source Remote CDL")


# --- Color Groups ---

group_app = typer.Typer(help="Color group management.")
app.add_typer(group_app, name="group")


@group_app.command("list")
@handle_errors
def group_list():
    """List project color groups."""
    set_execution_engine("api_native")
    set_capability_context("color.color_group_management", "supported")
    conn = get_connection(require_project=True)
    rows = color_ops.list_color_groups(conn)
    output(rows, columns=[("index", "#"), ("name", "Name")], title="Color Groups")


@group_app.command("add")
@handle_errors
def group_add(
    group_name: str = typer.Argument(..., help="Color group name"),
):
    """Add a color group."""
    enforce_mutation_policy("color.color_group_management", intended_engine="api_native")
    conn = get_connection(require_project=True)
    color_ops.add_color_group(conn, group_name)
    success(f"Added color group: {group_name}")


@group_app.command("delete")
@handle_errors
def group_delete(
    group_name: str = typer.Argument(..., help="Color group name"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
):
    """Delete a color group."""
    enforce_mutation_policy("color.color_group_management", intended_engine="api_native")
    require_force_for_machine_mode(
        force=force,
        action="color.group.delete",
        target_kind="color_group",
        target_name=group_name,
        prompt=f"Delete color group '{group_name}'?",
    )
    conn = get_connection(require_project=True)
    color_ops.delete_color_group(conn, group_name)
    success(f"Deleted color group: {group_name}")


@group_app.command("assign")
@handle_errors
def group_assign(
    group_name: str = typer.Argument(..., help="Color group name"),
    clip_name: Optional[str] = typer.Option(None, "--clip", help="Clip name (current clip when omitted)"),
):
    """Assign a clip to a color group."""
    enforce_mutation_policy("color.color_group_management", intended_engine="api_native")
    conn = get_connection(require_timeline=True)
    color_ops.assign_to_color_group(conn, clip_name, group_name)
    success(f"Assigned clip to color group: {group_name}")


@group_app.command("remove")
@handle_errors
def group_remove(
    clip_name: Optional[str] = typer.Option(None, "--clip", help="Clip name (current clip when omitted)"),
):
    """Remove a clip from its color group."""
    enforce_mutation_policy("color.color_group_management", intended_engine="api_native")
    conn = get_connection(require_timeline=True)
    color_ops.remove_from_color_group(conn, clip_name)
    success("Removed clip from color group.")


@group_app.command("rename")
@handle_errors
def group_rename(
    group: str = typer.Argument(..., help="Color group name"),
    new_name: str = typer.Argument(..., help="New color group name"),
):
    """Rename a color group."""
    enforce_mutation_policy("color.color_group_management", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        dry_run_message(f"Would rename color group '{group}' to '{new_name}'.")
        return
    conn = get_connection(require_project=True)
    output(color_ops.rename_color_group(conn, group, new_name), title="Color Group")


@group_app.command("clips")
@handle_errors
def group_clips(
    group: str = typer.Argument(..., help="Color group name"),
):
    """List timeline clips assigned to a color group."""
    conn = get_connection(require_project=True)
    output(color_ops.get_color_group_clips(conn, group), title="Color Group Clips")


@group_app.command("graph")
@handle_errors
def group_graph(
    group: str = typer.Argument(..., help="Color group name"),
    stage: str = typer.Option("pre", "--stage", help="pre|post"),
):
    """Inspect a color group's pre/post clip node graph."""
    if stage not in {"pre", "post"}:
        raise ValidationError("Invalid color group graph stage. Use pre or post.", details={"stage": stage})
    conn = get_connection(require_project=True)
    data = color_ops.get_pre_clip_node_graph(conn, group) if stage == "pre" else color_ops.get_post_clip_node_graph(conn, group)
    output(data, title="Color Group Graph")


# --- Thumbnail ---

@app.command("thumbnail")
@handle_errors
def thumbnail(
    output_path: str = typer.Option("color_thumbnail.png", "--output", "-o", help="Output file path"),
):
    """Export thumbnail of current clip under playhead."""
    set_execution_engine("workaround_setting")
    set_capability_context("color.thumbnail", "supported")
    resolved_path = _resolve_output_file_path(output_path)
    enforce_mutation_policy("color.thumbnail", intended_engine="workaround_setting", mutating=not is_dry_run())
    if is_dry_run():
        output(
            {
                "output_path": str(resolved_path),
                "requested_output_path": output_path,
                "would_export": True,
                "exported": False,
                "verified": False,
                "page_switch_required": True,
            },
            title="Color Thumbnail Preview",
        )
        return
    conn = get_connection(require_timeline=True)
    with color_ops._with_required_page(conn, "color"):
        ok = conn.project.ExportCurrentFrameAsStill(str(resolved_path))
    if not ok:
        raise APICallFailed(
            "Failed to export current frame thumbnail.",
            details={"output_path": str(resolved_path), "requested_output_path": output_path},
        )
    if not resolved_path.is_file():
        raise APICallFailed(
            "Thumbnail export reported success but output file was not created.",
            details={"output_path": str(resolved_path), "requested_output_path": output_path},
        )
    metadata = _image_file_metadata(resolved_path)
    set_verification_status("verified")
    set_recoverability("not_applicable")
    output(
        {
            "output_path": str(resolved_path),
            "requested_output_path": output_path,
            "exported": True,
            "verified": True,
            **metadata,
        },
        title="Color Thumbnail",
    )


# --- Gallery ---

gallery_app = typer.Typer(help="Gallery and stills management.")
app.add_typer(gallery_app, name="gallery")

# Gallery > Album (singular API path)
album_app = typer.Typer(help="Gallery still album operations.")
gallery_app.add_typer(album_app, name="album")


@album_app.command("list")
@handle_errors
def gallery_album_list():
    """List gallery still albums."""
    conn = get_connection(require_project=True)
    rows = gallery_ops.list_albums(conn)
    output(rows, columns=[("index", "#"), ("name", "Name")], title="Gallery Albums")


@album_app.command("create")
@handle_errors
def gallery_album_create(
    name: Optional[str] = typer.Argument(None, help="Optional album name"),
):
    """Create a gallery still album."""
    if name is not None:
        name = str(name).strip()
        if not name:
            raise ValidationError("Album name must not be empty.", details={"name": name})
    enforce_mutation_policy("color.gallery_stills", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        planned_name = name or "Untitled"
        output(
            {
                "name": planned_name,
                "requested_name": name,
                "created": False,
                "would_create": True,
            },
            title="Gallery Album Create",
        )
        return
    conn = get_connection(require_project=True)
    data = gallery_ops.create_album(conn, name)
    output(data, title="Gallery Album Create")


@album_app.command("rename")
@handle_errors
def gallery_album_rename(
    album: str = typer.Argument(..., help="Album name or 1-based index"),
    new_name: str = typer.Argument(..., help="New album name"),
):
    """Rename a gallery still album."""
    enforce_mutation_policy("color.gallery_stills", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        dry_run_message(f"Would rename gallery album '{album}' to '{new_name}'.")
        return
    conn = get_connection(require_project=True)
    output(gallery_ops.rename_album(conn, album, new_name), title="Gallery Album Rename")


@album_app.command("switch")
@handle_errors
def gallery_album_switch(
    album: str = typer.Argument(..., help="Album name or 1-based index"),
):
    """Switch current gallery album."""
    album = str(album).strip()
    if not album:
        raise ValidationError("Album selector must not be empty.", details={"album": album})
    enforce_mutation_policy("color.gallery_stills", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        output(
            {
                "album": album,
                "requested_album": album,
                "switched": False,
                "would_switch": True,
                "verified": False,
                "resolved": False,
            },
            title="Switched Gallery Album",
        )
        return
    conn = get_connection(require_project=True)
    data = gallery_ops.switch_album(conn, album)
    output(data, title="Switched Gallery Album")


@album_app.command("current")
@handle_errors
def gallery_album_current():
    """Show current gallery album."""
    conn = get_connection(require_project=True)
    data = color_ops.get_current_album_info(conn)
    output(data, title="Current Album")


# Gallery > Still (singular API path)
still_app = typer.Typer(help="Gallery still operations.")
gallery_app.add_typer(still_app, name="still")


@still_app.command("list")
@handle_errors
def gallery_still_list(
    album: Optional[str] = typer.Option(None, "--album", help="Album name or 1-based index"),
):
    """List stills in selected/current album."""
    conn = get_connection(require_project=True)
    rows = gallery_ops.list_stills(conn, album=album)
    output(rows, columns=[("index", "#"), ("label", "Label")], title="Gallery Stills")


@still_app.command("import")
@handle_errors
def gallery_still_import(
    path: str = typer.Argument(..., help="Still image or DRX path"),
    album: Optional[str] = typer.Option(None, "--album", help="Album name or 1-based index"),
):
    """Import still(s) into selected/current album."""
    raw_path = str(path).strip()
    if not raw_path:
        raise ValidationError("Import path must not be empty.", details={"path": raw_path})
    import_path = Path(raw_path).expanduser()
    if not import_path.is_file():
        raise ValidationError(
            "Import file not found.",
            details={"path": str(import_path)},
            recoverability="not_applicable",
        )
    if album is not None:
        album = str(album).strip()
        if not album:
            raise ValidationError("Album selector must not be empty.", details={"album": album})
    enforce_mutation_policy("color.gallery_stills", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        output(
            {
                "path": str(import_path),
                "album": album or "current",
                "imported": False,
                "would_import": True,
                "resolved": False,
            },
            title="Still Import",
        )
        return
    conn = get_connection(require_project=True)
    data = gallery_ops.import_stills(conn, path=str(import_path), album=album)
    output(data, title="Still Import")


@still_app.command("export")
@handle_errors
def gallery_still_export(
    selector: str = typer.Argument(..., help="Still selector (index or label)"),
    output_path_or_dir: str = typer.Argument(..., help="Output path or directory"),
    format: str = typer.Option("drx", "--format", help="drx|png|jpg"),
    album: Optional[str] = typer.Option(None, "--album", help="Album name or 1-based index"),
):
    """Export one still from selected/current album."""
    selector = str(selector).strip()
    if not selector:
        raise ValidationError("Still selector must not be empty.", details={"selector": selector})
    output_path_or_dir = str(output_path_or_dir).strip()
    if not output_path_or_dir:
        raise ValidationError("Output path must not be empty.", details={"output_path_or_dir": output_path_or_dir})
    format = str(format).strip().lower()
    allowed_formats = ["drx", "png", "jpg"]
    if format not in allowed_formats:
        raise ValidationError(
            "--format must be one of drx, png, or jpg.",
            details={"format": format, "allowed": allowed_formats},
            recoverability="not_applicable",
        )
    if album is not None:
        album = str(album).strip()
        if not album:
            raise ValidationError("Album selector must not be empty.", details={"album": album})
    enforce_mutation_policy("color.gallery_stills", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        output(
            {
                "selector": selector,
                "output": os.path.abspath(output_path_or_dir),
                "requested_output": output_path_or_dir,
                "format": format,
                "album": album or "current",
                "exported": False,
                "would_export": True,
                "resolved": False,
            },
            title="Still Export",
        )
        return
    conn = get_connection(require_project=True)
    data = gallery_ops.export_still(
        conn,
        selector=selector,
        output_path_or_dir=output_path_or_dir,
        fmt=format,
        album=album,
    )
    output(data, title="Still Export")


@still_app.command("delete")
@handle_errors
def gallery_still_delete(
    selector: str = typer.Argument(..., help="Still selector (index or label)"),
    album: Optional[str] = typer.Option(None, "--album", help="Album name or 1-based index"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
):
    """Delete one still from selected/current album."""
    selector = str(selector).strip()
    if not selector:
        raise ValidationError("Still selector must not be empty.", details={"selector": selector})
    if album is not None:
        album = str(album).strip()
        if not album:
            raise ValidationError("Album selector must not be empty.", details={"album": album})
    enforce_mutation_policy("color.gallery_stills", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        output(
            {
                "selector": selector,
                "album": album or "current",
                "deleted": False,
                "would_delete": True,
                "resolved": False,
                "verified": False,
            },
            title="Still Delete",
        )
        return
    require_force_for_machine_mode(
        force=force,
        action="color.gallery.still.delete",
        target_kind="gallery_still",
        target_name=selector,
        prompt=f"Delete gallery still '{selector}'?",
        details={"album": album or "current"},
    )
    conn = get_connection(require_project=True)
    gallery_ops.delete_still(conn, selector=selector, album=album)
    output(
        {
            "selector": selector,
            "album": album or "current",
            "deleted": True,
            "verified": True,
        },
        title="Still Delete",
    )


@still_app.command("label")
@handle_errors
def gallery_still_label(
    selector: str = typer.Argument(..., help="Still selector (index or label)"),
    set_label: Optional[str] = typer.Option(None, "--set", help="Set still label"),
    album: Optional[str] = typer.Option(None, "--album", help="Album name or 1-based index"),
):
    """Get or set a still label."""
    selector = str(selector).strip()
    if not selector:
        raise ValidationError("Still selector must not be empty.", details={"selector": selector})
    if album is not None:
        album = str(album).strip()
        if not album:
            raise ValidationError("Album selector must not be empty.", details={"album": album})
    if set_label is None:
        conn = get_connection(require_project=True)
        data = gallery_ops.get_still_label(conn, selector=selector, album=album)
        output(data)
        return
    set_label = str(set_label).strip()
    if not set_label:
        raise ValidationError("Still label must not be empty.", details={"label": set_label})
    enforce_mutation_policy("color.gallery_stills", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        output(
            {
                "selector": selector,
                "label": set_label,
                "album": album or "current",
                "updated": False,
                "would_update": True,
                "resolved": False,
            },
            title="Still Label",
        )
        return
    conn = get_connection(require_project=True)
    gallery_ops.set_still_label(conn, selector=selector, label=set_label, album=album)
    readback = gallery_ops.get_still_label(conn, selector=selector, album=album)
    readback_label = str(readback.get("label") or "")
    if readback_label != set_label:
        raise APICallFailed(
            "SetLabel returned success but label readback did not match.",
            details={
                "selector": selector,
                "requested_label": set_label,
                "readback_label": readback_label,
                "album": album or "current",
            },
        )
    set_verification_status("verified")
    set_recoverability("not_applicable")
    output(
        {
            "selector": selector,
            "label": set_label,
            "readback_label": readback_label,
            "album": album or "current",
            "updated": True,
            "verified": True,
            "route": "api_native_gallery_still_label",
        },
        title="Still Label",
    )

@still_app.command("grab")
@handle_errors
def gallery_still_grab():
    """Grab a still from current timeline frame."""
    enforce_mutation_policy("color.gallery_stills", intended_engine="api_native")
    conn = get_connection(require_timeline=True)
    before_stills = gallery_ops.list_stills(conn)
    before_count = len(before_stills)
    color_ops.grab_still(conn)
    after_stills = gallery_ops.list_stills(conn)
    after_count = len(after_stills)
    if after_count <= before_count:
        raise APICallFailed(
            "GrabStill returned success but current gallery album did not gain a still.",
            details={
                "before_count": before_count,
                "after_count": after_count,
                "before_stills": before_stills,
                "after_stills": after_stills,
            },
        )
    before_keys = {_gallery_still_row_key(row) for row in before_stills}
    created_stills = [row for row in after_stills if _gallery_still_row_key(row) not in before_keys]
    if len(created_stills) != after_count - before_count:
        created_stills = []
    set_verification_status("verified")
    set_recoverability("not_applicable")
    output(
        {
            "grabbed": True,
            "verified": True,
            "route": "api_native_gallery_grab_still",
            "album": "current",
            "before_count": before_count,
            "after_count": after_count,
            "created_count": after_count - before_count,
            "created_stills": created_stills,
        },
        title="Still Grab",
    )


def _gallery_still_row_key(row: dict[str, object]) -> tuple[object, object]:
    return (row.get("index"), row.get("label"))


@still_app.command("apply")
@handle_errors
def gallery_still_apply(
    selector: str = typer.Argument(..., help="Still selector (index or label)"),
    clip_name: Optional[str] = typer.Option(None, "--clip", help="Target clip name"),
    mode: int = typer.Option(0, "--mode", help="Grade mode: 0, 1, 2"),
    album: Optional[str] = typer.Option(None, "--album", help="Album name or 1-based index"),
):
    """Apply still grade to a clip."""
    selector = str(selector).strip()
    if not selector:
        raise ValidationError("Still selector must not be empty.", details={"selector": selector})
    if mode not in (0, 1, 2):
        raise ValidationError(
            "--mode must be one of 0, 1, or 2.",
            details={"mode": mode, "allowed": [0, 1, 2]},
            recoverability="not_applicable",
        )
    if clip_name is not None:
        clip_name = str(clip_name).strip()
        if not clip_name:
            raise ValidationError("Clip name must not be empty.", details={"clip": clip_name})
    if album is not None:
        album = str(album).strip()
        if not album:
            raise ValidationError("Album selector must not be empty.", details={"album": album})
    enforce_mutation_policy("color.gallery_stills", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        output(
            {
                "selector": selector,
                "clip": clip_name,
                "mode": mode,
                "album": album or "current",
                "applied": False,
                "would_apply": True,
                "resolved": False,
                "verified": False,
            },
            title="Still Apply",
        )
        return
    conn = get_connection(require_timeline=True)
    data = gallery_ops.apply_still(conn, selector=selector, clip_name=clip_name, mode=mode, album=album)
    set_verification_status("verified")
    set_recoverability("not_applicable")
    output(data, title="Still Apply")


root_still_app = typer.Typer(help="Timeline still operations from the color page.")
app.add_typer(root_still_app, name="still")


@root_still_app.command("grab-all")
@handle_errors
def color_still_grab_all(
    source: str = typer.Option("first", "--source", help="Still source: first or middle"),
):
    """Grab stills for all clips on the current timeline."""
    enforce_mutation_policy("color.gallery_stills", intended_engine="api_native", mutating=not is_dry_run())
    if is_dry_run():
        dry_run_message(f"Would grab all stills from {source} frame.")
        return
    conn = get_connection(require_timeline=True)
    from ..core import timeline_ops

    output(timeline_ops.grab_all_stills(conn, source), title="Grab All Stills")


# Power Grade namespace
power_grade_app = typer.Typer(help="Power grade operations.")
app.add_typer(power_grade_app, name="power-grade")


def _power_grade_list_impl():
    set_execution_engine("api_native")
    set_capability_context("color.gallery_power_grade_list_album", "supported")
    conn = get_connection(require_project=True)
    rows = color_ops.list_power_grades(conn)
    output(rows, columns=[("index", "#"), ("album", "Album"), ("label", "Label")], title="Power Grades")


def _unsupported_power_grade_preview(capability_id: str, route: str, payload: dict, title: str) -> None:
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

    set_execution_engine("not_available", 0.0)
    set_capability_context(capability_id, status)
    enforce_mutation_policy(capability_id, intended_engine="not_available", mutating=False)
    set_verification_status("not_available")
    set_recoverability("manual")
    if is_dry_run():
        output(diagnostic, title=title)
        return

    raise CapabilityNegotiationFailed(
        "PowerGrade command is not production-verified.",
        details=diagnostic,
    )


def _power_grade_apply_impl(selector: str, clip_name: Optional[str], *, capability_id: str = "color.power_grade_apply"):
    from ..core import power_grade_db

    selector = str(selector).strip()
    if not selector:
        raise ValidationError("Power grade selector must not be empty.", details={"selector": selector})
    if clip_name is not None:
        clip_name = str(clip_name).strip()
        if not clip_name:
            raise ValidationError("Clip name must not be empty.", details={"clip": clip_name})
    set_execution_engine("db_workaround", 0.85)
    set_capability_context(capability_id, "supported")
    enforce_mutation_policy(
        capability_id,
        intended_engine="db_workaround",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        dry_run_message("Would apply the selected PowerGrade grade body via the user gallery DB route")
        return
    conn = get_connection(require_timeline=True)
    render_proof = _begin_color_render_proof(
        conn,
        clip_name=clip_name,
        route="db_workaround_power_grade_apply",
        deliver_proof=True,
    )
    data = power_grade_db.apply_power_grade_db(conn, selector=selector, clip_name=clip_name)
    conn_after = get_connection(require_timeline=True)
    data["render_proof"] = _complete_color_render_proof(conn_after, render_proof, partial_result=data)
    if isinstance(data.get("verification"), dict):
        data["verification"]["render_proof_status"] = data["render_proof"]["status"]
        data["verification"]["render_proof_route"] = data["render_proof"]["route"]
    if isinstance(data.get("verification"), dict) and data["verification"].get("status") == "verified":
        set_verification_status("verified")
        set_recoverability("not_applicable")
    output(data, title="Power Grade Apply")
    success("PowerGrade grade body applied via user gallery DB route.")


# --- Power Grades ---

@power_grade_app.command("list")
@handle_errors
def power_grade_list(
    from_db: bool = typer.Option(False, "--db", help="List PowerGrade stills from the user gallery database"),
):
    """List power grades."""
    if not bool(_option_value(from_db, False)):
        return _power_grade_list_impl()
    from ..core import power_grade_db
    from ..runtime_health import resolve_current_disk_project_db

    set_execution_engine("db_workaround", 0.85)
    set_capability_context("color.power_grade_apply", "supported")
    conn = get_connection(require_project=True)
    current_database = resolve_current_disk_project_db(conn, allow_project_name_inference=True)
    user_db_path = power_grade_db.user_gallery_db_path_from_project_db(
        str(current_database.get("project_db_path") or "")
    )
    rows = power_grade_db.list_power_grade_stills(user_db_path)
    output(
        rows,
        columns=[("index", "#"), ("label", "Label"), ("version_id", "Grade Version")],
        title="Power Grades (User Gallery DB)",
    )


@power_grade_app.command("apply")
@handle_errors
def power_grade_apply(
    selector: str = typer.Argument(..., help="Power grade selector (index or label)"),
    clip_name: Optional[str] = typer.Option(None, "--clip", help="Target clip"),
):
    """Apply a PowerGrade still's grade body to a clip via the user gallery DB route."""
    _power_grade_apply_impl(selector=selector, clip_name=clip_name)


@power_grade_app.command("template-apply")
@handle_errors
def power_grade_template_apply(
    template: str = typer.Argument(..., help="PowerGrade template selector, label, or path-like name"),
    clip_name: Optional[str] = typer.Option(None, "--clip", help="Target clip"),
    mode: int = typer.Option(0, "--mode", help="Full-grade mode: 0 only"),
):
    """Apply a PowerGrade template selector through the verified user gallery DB route."""
    template = str(template).strip()
    if not template:
        raise ValidationError("PowerGrade template selector must not be empty.", details={"template": template})
    if clip_name is not None:
        clip_name = str(clip_name).strip()
        if not clip_name:
            raise ValidationError("Clip name must not be empty.", details={"clip": clip_name})
    if mode != 0:
        raise ValidationError(
            "PowerGrade template apply currently supports full-grade mode 0 through the verified user gallery DB route.",
            details={"mode": mode, "supported_modes": [0]},
            recoverability="not_applicable",
        )
    _power_grade_apply_impl(selector=template, clip_name=clip_name, capability_id="color.power_grade_template_apply")


power_grade_album_app = typer.Typer(help="PowerGrade album operations.")
power_grade_app.add_typer(power_grade_album_app, name="album")


@power_grade_album_app.command("create")
@handle_errors
def power_grade_album_create(
    name: str = typer.Argument(..., help="PowerGrade album name"),
):
    """Create a PowerGrade album."""
    enforce_mutation_policy(
        "color.gallery_power_grade_list_album",
        intended_engine="api_native",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        dry_run_message(f"Would create PowerGrade album: {name}")
        return
    conn = get_connection(require_project=True)
    output(gallery_ops.create_power_grade_album(conn, name), title="PowerGrade Album")


# --- LUT Generation ---

@app.command("curves")
@handle_errors
def curves(
    red: Optional[str] = typer.Option(None, "--red", help="Red curve points '0,0;0.5,0.6;1,1'"),
    green: Optional[str] = typer.Option(None, "--green", help="Green curve points"),
    blue: Optional[str] = typer.Option(None, "--blue", help="Blue curve points"),
    master: Optional[str] = typer.Option(None, "--master", help="Master curve points"),
    output_path: str = typer.Option("/tmp/curve.cube", "--output", "-o", help="Output .cube file"),
):
    """Generate a .cube LUT from RGB curve points."""
    set_execution_engine("workaround_setting")
    set_capability_context("color.curves_lut", "supported")
    if not any([red, green, blue, master]):
        raise ValidationError(
            "Specify at least one curve (--red, --green, --blue, or --master).",
            details={"red": red, "green": green, "blue": blue, "master": master},
        )
    output_path = lut_generator.validate_curves_lut_request(
        output_path=output_path,
        red=red,
        green=green,
        blue=blue,
        master=master,
    )
    if is_dry_run():
        dry_run_message(f"Would generate curves LUT at '{output_path}'")
        return

    lut_generator.generate_curves_lut(
        output_path=output_path, red=red, green=green, blue=blue, master=master,
    )
    set_verification_status("file_verified")
    set_recoverability("not_applicable")
    success(f"Generated curves LUT: {output_path}")


@app.command("huesat")
@handle_errors
def huesat(
    hue_shift: float = typer.Option(0.0, "--hue-shift", help="Hue rotation in degrees"),
    sat_boost: float = typer.Option(1.0, "--sat-boost", help="Saturation multiplier"),
    val_boost: float = typer.Option(1.0, "--val-boost", help="Value/brightness multiplier"),
    output_path: str = typer.Option("/tmp/huesat.cube", "--output", "-o", help="Output .cube file"),
):
    """Generate a .cube LUT from hue/saturation modifications."""
    output_path = lut_generator.validate_huesat_lut_request(
        output_path=output_path,
        hue_shift=hue_shift,
        sat_boost=sat_boost,
        val_boost=val_boost,
    )
    if is_dry_run():
        dry_run_message(f"Would generate hue/sat LUT at '{output_path}'")
        return

    lut_generator.generate_hue_sat_lut(
        output_path=output_path,
        hue_shift=hue_shift, sat_boost=sat_boost, val_boost=val_boost,
    )
    success(f"Generated hue/sat LUT: {output_path}")
