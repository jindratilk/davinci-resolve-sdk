@app.command("create")
@handle_errors
def create(
    job: str | None = typer.Option(None, "--job", help="Path to a structured multicam job JSON file"),
    job_json: str | None = typer.Option(None, "--job-json", help="Inline structured multicam job JSON"),
    angle: list[str] | None = typer.Option(
        None,
        "--angle",
        help="Repeatable source spec; repeat a label for separate sequential clips on one angle: A=camA.mov",
    ),
    timeline_name: str | None = typer.Option(None, "--timeline-name", help="Target timeline name for the multicam job"),
    multicam_name: str | None = typer.Option(None, "--multicam-name", help="Optional native multicam clip name"),
    sync_mode: str | None = typer.Option(None, "--sync-mode", "--sync", help="Native multicam Angle Sync: in, out, timecode, sound, marker"),
    cleanup_stale: bool = typer.Option(False, "--cleanup-stale", help="Remove DB-only stale target rows for this multicam/timeline name before creating"),
    replace_existing: bool = typer.Option(False, "--replace-existing", help="Alias for --cleanup-stale; live visible targets still fail"),
):
    """Create a native multicam clip in the Media Pool from a structured job."""
    payload = _load_multicam_job_input(
        operation="create",
        job=job,
        job_json=job_json,
        angle_specs=angle,
        timeline_name=timeline_name,
        multicam_name=multicam_name,
        sync_mode=sync_mode,
    )
    effective_settings = multicam_engine.resolve_effective_settings(payload)
    cleanup_stale_requested = _bool_option(cleanup_stale) or _bool_option(replace_existing)
    enforce_mutation_policy(
        "multicam.create",
        intended_engine="db_workaround",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        output(
            mutation_payload(
                action="multicam.create",
                changed=False,
                target={
                    "kind": "multicam_clip",
                    "name": effective_settings["multicam_name"],
                },
                timeline_name=effective_settings["timeline_name"],
                multicam_name=effective_settings["multicam_name"],
                sync_mode=effective_settings["sync_mode"],
                reference_source=effective_settings["reference_source"],
                angle_order=effective_settings["angle_order"],
                cleanup_stale=cleanup_stale_requested,
                source_count=len(payload.get("sources") or []),
                runtime_validation="not_performed",
                message=(
                    "Would create native multicam clip "
                    f"'{effective_settings['multicam_name']}' for timeline "
                    f"'{effective_settings['timeline_name']}'."
                ),
            )
        )
        return

    conn = get_connection(require_project=True)
    _require_sdk_multicam_create_guard(conn)
    create_kwargs = {"cleanup_stale_targets": True} if cleanup_stale_requested else {}
    data = multicam_engine.multicam_create(conn, job=payload, **create_kwargs)
    output(data, title="Multicam Create")


@app.command("inspect")
@handle_errors
def inspect(
    multicam_name: str | None = typer.Option(None, "--multicam-name", help="Native multicam clip name"),
    timeline_name: str | None = typer.Option(None, "--timeline", help="Optional timeline name to inspect multicam segment state"),
):
    """Inspect a native multicam clip and its current timeline state."""
    set_execution_engine("db_direct")
    conn = get_connection(require_project=True)
    resolved_multicam_name = str(multicam_name or "").strip()
    if not resolved_multicam_name:
        data = multicam_engine.list_multicam_inspection_context(conn, timeline_name=timeline_name)
        output(data, title="Multicam Inspect")
        return

    data = multicam_engine.inspect_multicam(conn, multicam_name=resolved_multicam_name, timeline_name=timeline_name)
    output(data, title="Multicam Inspect")


@app.command("match-frame")
@handle_errors
def match_frame(
    multicam_name: str | None = typer.Option(None, "--multicam-name", help="Native multicam clip name for direct internal matching"),
    media_id: str | None = typer.Option(None, "--media-id"),
    sequence_id: str | None = typer.Option(None, "--sequence-id"),
    angle_number: int | None = typer.Option(None, "--angle", min=1, help="One-based angle; optional when timeline selector is decodable"),
    record_frame: int | None = typer.Option(None, "--record-frame", min=0, help="Frame relative to the multicam start"),
    timeline_name: str | None = typer.Option(None, "--timeline", help="Timeline name for timeline-to-source match frame"),
    timeline_frame: int | None = typer.Option(None, "--timeline-frame", min=0, help="Absolute timeline frame"),
    media_type: str = typer.Option("video", "--media-type", help="video or audio"),
):
    """Resolve a multicam or timeline frame to the exact underlying source item/frame."""
    enforce_mutation_policy(
        "multicam.match_frame",
        intended_engine="db_direct",
        mutating=False,
    )
    direct_mode = record_frame is not None
    timeline_mode = timeline_frame is not None or bool(str(timeline_name or "").strip())
    if direct_mode == timeline_mode:
        raise ValidationError(
            "Use either --record-frame with --angle, or --timeline with --timeline-frame.",
            details={"record_frame": record_frame, "timeline": timeline_name, "timeline_frame": timeline_frame},
        )
    conn = get_connection(require_project=True)
    current_db = resolve_current_disk_project_db(conn)
    if direct_mode:
        if angle_number is None:
            raise ValidationError("Direct multicam match frame requires --angle.")
        data = native_multicam_db.match_multicam_frame(
            str(current_db["project_db_path"]),
            multicam_name=multicam_name,
            media_id=media_id,
            sequence_id=sequence_id,
            angle_number=angle_number,
            record_frame=int(record_frame),
            media_type=media_type,
        )
    else:
        resolved_timeline_name = str(timeline_name or "").strip()
        if not resolved_timeline_name or timeline_frame is None:
            raise ValidationError("Timeline multicam match frame requires --timeline and --timeline-frame.")
        data = native_multicam_db.match_timeline_multicam_frame(
            str(current_db["project_db_path"]),
            timeline_name=resolved_timeline_name,
            timeline_frame=int(timeline_frame),
            media_type=media_type,
            angle_number=angle_number,
        )
    output(data, title="Multicam Match Frame")


@app.command("flatten")
@handle_errors
def flatten(
    timeline_name: str = typer.Option(..., "--timeline", help="Timeline whose native multicam items should be flattened"),
    grade_policy: str = typer.Option(
        "copy_multicam",
        "--grade-policy",
        help="Flatten grade policy: copy_multicam or retain_angle",
    ),
    angle_number: int | None = typer.Option(
        None,
        "--angle",
        min=1,
        help="Override the selected angle for every matching wrapper; otherwise decode each persistent selector",
    ),
    scope: str = typer.Option("both", "--scope", help="Flatten video, audio, or both"),
    force: bool = typer.Option(False, "--force", "-f", help="Confirm destructive Disk-DB mutation"),
):
    """Replace timeline multicam wrappers with distinct underlying source items."""
    enforce_mutation_policy(
        "multicam.flatten",
        intended_engine="db_workaround",
        mutating=not is_dry_run(),
    )
    conn = get_connection(require_project=True, require_timeline=False)
    expected_multicam_native_id = os.environ.get("CUTAGENT_SDK_EXPECTED_MULTICAM_NATIVE_ID", "").strip() or None
    expected_timeline_native_id = _require_sdk_timeline_native_identity(conn, timeline_name)
    current_db = resolve_current_disk_project_db(conn)
    kwargs = {
        "timeline_name": timeline_name,
        "grade_policy": grade_policy,
        "angle_number": angle_number,
        "scope": scope,
        "multicam_media_id": expected_multicam_native_id,
        "timeline_native_id": expected_timeline_native_id,
    }
    if is_dry_run():
        plan = native_multicam_db.plan_multicam_flatten(str(current_db["project_db_path"]), **kwargs)
        output(
            mutation_payload(
                action=plan["action"],
                changed=False,
                target={"kind": "timeline", "name": timeline_name},
                runtime_validation="performed",
                **{key: value for key, value in plan.items() if key != "action"},
                message=f"Would flatten native multicam items on timeline '{timeline_name}'.",
            )
        )
        return

    if not force:
        if is_machine_mode():
            raise ConfirmationRequired(
                "Machine-mode native multicam flatten requires --force.",
                details={
                    "action": "multicam.flatten",
                    "target_kind": "timeline",
                    "timeline_name": timeline_name,
                    "required_option": "--force",
                },
            )
        typer.confirm(f"Flatten native multicam items on timeline '{timeline_name}'?", abort=True)

    data = native_multicam_db.flatten_multicam_timeline(conn, **kwargs)
    output(data, title="Multicam Flatten")


@app.command("convert")
@handle_errors
def convert(
    timeline_name: str | None = typer.Option(None, "--timeline", help="Timeline to convert into a native multicam clip"),
    compound_name: str | None = typer.Option(None, "--compound", help="Compound clip to convert into a native multicam clip"),
    media_id: str | None = typer.Option(None, "--media-id", help="Exact timeline/compound Sm2MpMedia_id"),
    multicam_name: str | None = typer.Option(None, "--multicam-name", help="Optional new multicam clip name"),
    force: bool = typer.Option(False, "--force", "-f", help="Confirm destructive Disk-DB mutation"),
):
    """Convert a two-to-six-track timeline or compound clip to native multicam."""
    enforce_mutation_policy(
        "multicam.convert",
        intended_engine="db_workaround",
        mutating=not is_dry_run(),
    )
    conn = get_connection(require_project=True, require_timeline=False)
    current_db = resolve_current_disk_project_db(conn)
    kwargs = {
        "timeline_name": timeline_name,
        "compound_name": compound_name,
        "media_id": media_id,
        "multicam_name": multicam_name,
    }
    if is_dry_run():
        plan = native_multicam_db.plan_multicam_convert(str(current_db["project_db_path"]), **kwargs)
        output(
            mutation_payload(
                action=plan["action"],
                changed=False,
                target={"kind": "multicam_clip", "name": plan["multicam_name"]},
                runtime_validation="performed",
                **{key: value for key, value in plan.items() if key != "action"},
                message=f"Would convert '{plan['source_name']}' to native multicam '{plan['multicam_name']}'.",
            )
        )
        return

    if not force:
        if is_machine_mode():
            raise ConfirmationRequired(
                "Machine-mode timeline/compound multicam conversion requires --force.",
                details={
                    "action": "multicam.convert",
                    "target_kind": "timeline_or_compound",
                    "timeline_name": timeline_name,
                    "compound_name": compound_name,
                    "media_id": media_id,
                    "required_option": "--force",
                },
            )
        typer.confirm("Convert this timeline or compound clip into a native multicam clip?", abort=True)

    data = native_multicam_db.convert_to_multicam(conn, **kwargs)
    output(data, title="Multicam Convert")


@app.command("set-start-timecode")
@handle_errors
def set_start_timecode(
    start_timecode: str = typer.Option(..., "--start-timecode", help="New native multicam start timecode"),
    multicam_name: str | None = typer.Option(None, "--multicam-name", help="Native multicam clip name"),
    media_id: str | None = typer.Option(None, "--media-id"),
    sequence_id: str | None = typer.Option(None, "--sequence-id"),
):
    """Change multicam start timecode while preserving every internal item offset."""
    enforce_mutation_policy(
        "multicam.set_start_timecode",
        intended_engine="db_workaround",
        mutating=not is_dry_run(),
    )
    conn = get_connection(require_project=True)
    kwargs = {
        "start_timecode": start_timecode,
        "multicam_name": multicam_name,
        "media_id": media_id,
        "sequence_id": sequence_id,
    }
    if is_dry_run():
        current_db = resolve_current_disk_project_db(conn)
        data = native_multicam_db.plan_multicam_start_timecode(str(current_db["project_db_path"]), **kwargs)
    else:
        data = native_multicam_db.set_multicam_start_timecode(conn, **kwargs)
    output(data, title="Multicam Set Start Timecode")


@app.command("recover-timing")
@handle_errors
def recover_timing(
    multicam_name: str | None = typer.Option(None, "--multicam-name", help="Native multicam clip name"),
    media_id: str | None = typer.Option(None, "--media-id", help="Exact Sm2MpMedia_id for the native multicam clip"),
    sequence_id: str | None = typer.Option(None, "--sequence-id", help="Exact Sm2Sequence_id for the native multicam sequence"),
    source_specs: str | None = typer.Option(None, "--source-specs", help="Path to source spec JSON"),
    source_specs_json: str | None = typer.Option(None, "--source-specs-json", help="Inline source spec JSON"),
    apply_timemap: bool = typer.Option(False, "--apply-timemap", help="Rewrite MediaTimemapBA for internal video/audio items"),
    apply_source_start_tc: bool = typer.Option(False, "--apply-source-start-tc", help="Rewrite Start/Duration/MediaStartTime from source start timing"),
    apply_media_extents: bool = typer.Option(False, "--apply-media-extents", help="Rewrite Sm2Sequence.MediaExtents from recovered source timing"),
    verify_reopen: bool = typer.Option(False, "--verify-reopen", help="After project reopen, confirm the multicam still exists in the Media Pool"),
):
    """Recover native multicam timing fields through the Disk Project.db route."""
    enforce_mutation_policy(
        "multicam.recover_timing",
        intended_engine="db_workaround",
        mutating=not is_dry_run(),
    )
    resolved_source_specs = _load_multicam_source_specs(
        source_specs_path=source_specs,
        source_specs_json=source_specs_json,
    )
    conn = get_connection(require_project=True)
    current_db = resolve_current_disk_project_db(conn)
    if is_dry_run():
        plan = native_multicam_db.plan_multicam_timing_recovery(
            str(current_db["project_db_path"]),
            source_specs=resolved_source_specs,
            multicam_name=multicam_name,
            media_id=media_id,
            sequence_id=sequence_id,
            apply_timemap=apply_timemap,
            apply_source_start_tc=apply_source_start_tc,
            apply_media_extents=apply_media_extents,
            verify_reopen=verify_reopen,
            conn=conn,
        )
        plan["changed"] = False
        plan["would_change"] = bool(plan.get("updated_items")) or (
            plan.get("sequence_extents", {}).get("before") != plan.get("sequence_extents", {}).get("after")
        )
        plan["runtime_validation"] = "performed"
        output(plan, title="Multicam Recover Timing")
        return

    data = native_multicam_db.recover_multicam_timing(
        conn,
        source_specs=resolved_source_specs,
        multicam_name=multicam_name,
        media_id=media_id,
        sequence_id=sequence_id,
        apply_timemap=apply_timemap,
        apply_source_start_tc=apply_source_start_tc,
        apply_media_extents=apply_media_extents,
        verify_reopen=verify_reopen,
    )
    output(data, title="Multicam Recover Timing")


@app.command("strip-embedded-audio")
@handle_errors
def strip_embedded_audio(
    multicam_name: str | None = typer.Option(None, "--multicam-name", help="Native multicam clip name"),
    media_id: str | None = typer.Option(None, "--media-id", help="Exact Sm2MpMedia_id for the native multicam clip"),
    sequence_id: str | None = typer.Option(None, "--sequence-id", help="Exact Sm2Sequence_id for the native multicam sequence"),
    allow_missing_audio: bool = typer.Option(False, "--allow-missing-audio", help="Allow no-op when embedded audio tracks were already removed"),
    force: bool = typer.Option(False, "--force", "-f", help="Confirm destructive Disk-DB mutation"),
):
    """Remove embedded audio tracks/items from a native multicam sequence."""
    enforce_mutation_policy(
        "multicam.strip_embedded_audio",
        intended_engine="db_workaround",
        mutating=not is_dry_run(),
    )
    conn = get_connection(require_project=True)
    if is_dry_run():
        current_db = resolve_current_disk_project_db(conn)
        plan = native_multicam_db.plan_multicam_embedded_audio_strip(
            str(current_db["project_db_path"]),
            multicam_name=multicam_name,
            media_id=media_id,
            sequence_id=sequence_id,
            allow_missing_audio=allow_missing_audio,
        )
        output(
            mutation_payload(
                action="multicam.strip_embedded_audio",
                changed=False,
                target={"kind": "multicam_clip", "name": plan["multicam_name"]},
                multicam_name=plan["multicam_name"],
                multicam_media_id=plan["multicam_media_id"],
                multicam_sequence_id=plan["multicam_sequence_id"],
                removed_audio_tracks=0,
                removed_audio_items=0,
                would_remove_audio_tracks=plan["would_remove_audio_tracks"],
                would_remove_audio_items=plan["would_remove_audio_items"],
                video_tracks_preserved=plan["video_tracks_preserved"],
                video_items_preserved=plan["video_items_preserved"],
                runtime_validation="performed",
                message=f"Would strip embedded audio from native multicam '{plan['multicam_name']}'.",
            )
        )
        return

    if not force:
        if is_machine_mode():
            raise ConfirmationRequired(
                "Machine-mode native multicam embedded audio strip requires --force.",
                details={
                    "action": "multicam.strip_embedded_audio",
                    "target_kind": "multicam_clip",
                    "multicam_name": multicam_name,
                    "multicam_media_id": media_id,
                    "multicam_sequence_id": sequence_id,
                    "required_option": "--force",
                },
            )
        typer.confirm("Strip embedded audio tracks/items from this native multicam clip?", abort=True)

    data = native_multicam_db.strip_multicam_embedded_audio(
        conn,
        multicam_name=multicam_name,
        media_id=media_id,
        sequence_id=sequence_id,
        allow_missing_audio=allow_missing_audio,
    )
    output(data, title="Multicam Strip Embedded Audio")


@app.command("replace-audio")
@handle_errors
def replace_audio(
    multicam_name: str | None = typer.Option(None, "--multicam-name", help="Native multicam clip name"),
    media_id: str | None = typer.Option(None, "--media-id", help="Exact Sm2MpMedia_id for the native multicam clip"),
    sequence_id: str | None = typer.Option(None, "--sequence-id", help="Exact Sm2Sequence_id for the native multicam sequence"),
    audio_source: list[str] | None = typer.Option(None, "--audio-source", help="Repeatable isolated audio source spec: id=/path/audio.wav"),
    audio_angle_map: str | None = typer.Option(None, "--audio-angle-map", help="Map audio source ids to angle labels or zero-based indices: source_id=A,source_id=B"),
    angle_order: list[str] | None = typer.Option(None, "--angle-order", help="Repeatable angle labels used to resolve --audio-angle-map labels"),
    angle_order_json: str | None = typer.Option(None, "--angle-order-json", help="Path to JSON array or object with angle_order[]"),
    audio_offsets_json: str | None = typer.Option(None, "--audio-offsets-json", help="Path to JSON offsets object in frames; negative means audio starts before multicam"),
    unmapped_audio: str = typer.Option("keep", "--unmapped-audio", help="Policy for existing internal audio angles not mapped by a replacement source: keep or remove"),
    force: bool = typer.Option(False, "--force", "-f", help="Confirm Disk-DB mutation"),
):
    """Replace audio items inside a native multicam sequence with isolated sources."""
    enforce_mutation_policy(
        "multicam.replace_audio",
        intended_engine="db_workaround",
        mutating=not is_dry_run(),
    )
    resolved_sources = podcast_audio_activity.parse_audio_sources(audio_source)
    resolved_audio_angle_map = podcast_audio_activity.parse_audio_angle_map(audio_angle_map)
    resolved_angle_order = _load_optional_angle_order_input(
        angle_order=angle_order,
        angle_order_json=angle_order_json,
    )
    offsets = podcast_audio_activity.load_audio_offsets_json(audio_offsets_json)
    conn = get_connection(require_project=True)
    if is_dry_run():
        current_db = resolve_current_disk_project_db(conn)
        plan = native_multicam_db.plan_multicam_audio_replacement(
            str(current_db["project_db_path"]),
            multicam_name=multicam_name,
            media_id=media_id,
            sequence_id=sequence_id,
            audio_sources=resolved_sources,
            audio_angle_map=resolved_audio_angle_map,
            angle_order=resolved_angle_order,
            offsets=offsets,
            unmapped_audio=unmapped_audio,
        )
        output(
            mutation_payload(
                action=plan["action"],
                changed=False,
                target={"kind": "multicam_clip", "name": plan["multicam_name"]},
                would_change=bool(plan.get("replacements") or plan.get("removed_unmapped_audio_items")),
                runtime_validation="performed",
                **{key: value for key, value in plan.items() if key != "action"},
                message=f"Would replace internal audio for native multicam '{plan['multicam_name']}'.",
            )
        )
        return

    if not force:
        if is_machine_mode():
            raise ConfirmationRequired(
                "Machine-mode native multicam audio replacement requires --force.",
                details={
                    "action": "multicam.replace_audio",
                    "target_kind": "multicam_clip",
                    "multicam_name": multicam_name,
                    "multicam_media_id": media_id,
                    "multicam_sequence_id": sequence_id,
                    "required_option": "--force",
                },
            )
        typer.confirm("Replace internal audio items inside this native multicam clip?", abort=True)

    data = native_multicam_db.replace_multicam_audio(
        conn,
        multicam_name=multicam_name,
        media_id=media_id,
        sequence_id=sequence_id,
        audio_sources=resolved_sources,
        audio_angle_map=resolved_audio_angle_map,
        angle_order=resolved_angle_order,
        offsets=offsets,
        unmapped_audio=unmapped_audio,
    )
    output(data, title="Multicam Replace Audio")


@replace_app.command("audio")
@handle_errors
def replace_audio_by_angle(
    multicam_name: str | None = typer.Option(None, "--multicam-name", help="Native multicam clip name"),
    media_id: str | None = typer.Option(None, "--media-id", help="Exact Sm2MpMedia_id for the native multicam clip"),
    sequence_id: str | None = typer.Option(None, "--sequence-id", help="Exact Sm2Sequence_id for the native multicam sequence"),
    angle: list[str] | None = typer.Option(None, "--angle", help="DaVinci Resolve one-based angle audio replacement: 1=/path/mic.wav"),
    empty: list[str] | None = typer.Option(None, "--empty", help="DaVinci Resolve one-based angle number whose internal audio item should be removed"),
    offset: list[str] | None = typer.Option(None, "--offset", help="Per-angle sync offset in frames: 1=-12, 2=5"),
    audio_offsets_json: str | None = typer.Option(None, "--audio-offsets-json", help="Path to JSON offsets object; keys may be angle_1 ids or legacy source ids"),
    unmapped: str = typer.Option("keep", "--unmapped", help="Policy for existing audio angles not mentioned by --angle/--empty: keep, remove, or error"),
    force: bool = typer.Option(False, "--force", "-f", help="Confirm Disk-DB mutation"),
):
    """Replace or clear audio items inside native multicam angles."""
    enforce_mutation_policy(
        "multicam.replace_audio",
        intended_engine="db_workaround",
        mutating=not is_dry_run(),
    )
    targets = _parse_resolve_angle_media_targets(angle, media_kind="audio")
    empty_numbers = _parse_resolve_angle_numbers(empty, option_name="--empty")
    if not targets and not empty_numbers:
        raise ValidationError(
            "multicam replace audio requires at least one --angle or --empty target.",
            details={
                "examples": [
                    "multicam replace audio --angle 1=/abs/mic_1.wav",
                    "multicam replace audio --empty 3",
                ]
            },
        )
    target_numbers = {int(target["angle_number"]) for target in targets}
    conflicting_empty = sorted(target_numbers.intersection(empty_numbers))
    if conflicting_empty:
        raise ValidationError(
            "A multicam angle cannot be both replaced and emptied.",
            details={"angle_numbers": conflicting_empty},
        )
    audio_sources = [
        {"id": str(target["source_id"]), "path": str(target["path"]), "clip_name": str(target["clip_name"])}
        for target in targets
    ]
    audio_angle_map = {str(target["source_id"]): str(int(target["angle_index"])) for target in targets}
    offsets = podcast_audio_activity.load_audio_offsets_json(audio_offsets_json)
    for angle_number, frames in _parse_angle_offset_specs(offset).items():
        offsets[f"angle_{angle_number}"] = frames
    empty_angle_indices = [number - 1 for number in empty_numbers]

    conn = get_connection(require_project=True)
    if is_dry_run():
        current_db = resolve_current_disk_project_db(conn)
        plan = native_multicam_db.plan_multicam_audio_replacement(
            str(current_db["project_db_path"]),
            multicam_name=multicam_name,
            media_id=media_id,
            sequence_id=sequence_id,
            audio_sources=audio_sources,
            audio_angle_map=audio_angle_map,
            angle_order=[],
            offsets=offsets,
            unmapped_audio=unmapped,
            empty_angle_indices=empty_angle_indices,
        )
        output(
            mutation_payload(
                action=plan["action"],
                changed=False,
                target={"kind": "multicam_clip", "name": plan["multicam_name"]},
                would_change=bool(plan.get("replacements") or plan.get("removed_unmapped_audio_items")),
                runtime_validation="performed",
                angle_targets=[
                    {
                        "angle_number": int(target["angle_number"]),
                        "angle_index": int(target["angle_index"]),
                        "path": str(target["path"]),
                    }
                    for target in targets
                ],
                **{key: value for key, value in plan.items() if key != "action"},
                message=f"Would replace internal audio by DaVinci Resolve angle number for native multicam '{plan['multicam_name']}'.",
            )
        )
        return

    if not force:
        if is_machine_mode():
            raise ConfirmationRequired(
                "Machine-mode native multicam angle audio replacement requires --force.",
                details={
                    "action": "multicam.replace.audio",
                    "target_kind": "multicam_clip",
                    "multicam_name": multicam_name,
                    "multicam_media_id": media_id,
                    "multicam_sequence_id": sequence_id,
                    "required_option": "--force",
                },
            )
        typer.confirm("Replace internal audio items inside this native multicam clip?", abort=True)

    data = native_multicam_db.replace_multicam_audio(
        conn,
        multicam_name=multicam_name,
        media_id=media_id,
        sequence_id=sequence_id,
        audio_sources=audio_sources,
        audio_angle_map=audio_angle_map,
        angle_order=[],
        offsets=offsets,
        unmapped_audio=unmapped,
        empty_angle_indices=empty_angle_indices,
    )
    output(data, title="Multicam Replace Audio")


@replace_app.command("video")
@handle_errors
def replace_video_by_angle(
    multicam_name: str | None = typer.Option(None, "--multicam-name", help="Native multicam clip name"),
    media_id: str | None = typer.Option(None, "--media-id", help="Exact Sm2MpMedia_id for the native multicam clip"),
    sequence_id: str | None = typer.Option(None, "--sequence-id", help="Exact Sm2Sequence_id for the native multicam sequence"),
    angle: list[str] | None = typer.Option(None, "--angle", help="DaVinci Resolve one-based angle video replacement: 3=/path/camera.braw"),
    source_in: list[str] | None = typer.Option(None, "--source-in", help="Per-angle source in frame override: 3=120"),
    start: list[str] | None = typer.Option(None, "--start", help="Per-angle internal multicam start frame override: 3=0"),
    duration: list[str] | None = typer.Option(None, "--duration", help="Per-angle internal multicam duration frame override: 3=2400"),
    allow_short_source: bool = typer.Option(False, "--allow-short-source", help="Allow replacement media shorter than the requested internal range"),
    force: bool = typer.Option(False, "--force", "-f", help="Confirm Disk-DB mutation"),
):
    """Replace video items inside native multicam angles."""
    enforce_mutation_policy(
        "multicam.replace_video",
        intended_engine="db_workaround",
        mutating=not is_dry_run(),
    )
    targets = _parse_resolve_angle_media_targets(angle, media_kind="video")
    if not targets:
        raise ValidationError(
            "multicam replace video requires at least one --angle target.",
            details={"example": "multicam replace video --angle 3=/abs/camera_3.braw"},
        )
    source_in_frames = _angle_number_frame_map_to_indices(_parse_angle_offset_specs(source_in))
    start_frames = _angle_number_frame_map_to_indices(_parse_angle_offset_specs(start))
    duration_frames = _angle_number_frame_map_to_indices(_parse_angle_offset_specs(duration))
    target_indices = {int(target["angle_index"]) for target in targets}
    for option_name, frame_map in (
        ("--source-in", source_in_frames),
        ("--start", start_frames),
        ("--duration", duration_frames),
    ):
        unknown = sorted(set(frame_map) - target_indices)
        if unknown:
            raise ValidationError(
                f"{option_name} references an angle that is not present in --angle targets.",
                details={
                    "option": option_name,
                    "angle_indices": unknown,
                    "angle_numbers": [index + 1 for index in unknown],
                    "target_angle_numbers": sorted(index + 1 for index in target_indices),
                },
            )
    video_targets = [
        {
            "angle_index": int(target["angle_index"]),
            "angle_number": int(target["angle_number"]),
            "path": str(target["path"]),
            "clip_name": str(target["clip_name"]),
        }
        for target in targets
    ]

    conn = get_connection(require_project=True)
    if is_dry_run():
        current_db = resolve_current_disk_project_db(conn)
        plan = native_multicam_db.plan_multicam_video_replacement(
            str(current_db["project_db_path"]),
            multicam_name=multicam_name,
            media_id=media_id,
            sequence_id=sequence_id,
            video_targets=video_targets,
            source_in_frames=source_in_frames,
            start_frames=start_frames,
            duration_frames=duration_frames,
            allow_short_source=allow_short_source,
        )
        output(
            mutation_payload(
                action=plan["action"],
                changed=False,
                target={"kind": "multicam_clip", "name": plan["multicam_name"]},
                would_change=bool(plan.get("replacements")),
                runtime_validation="performed",
                angle_targets=[
                    {
                        "angle_number": int(target["angle_number"]),
                        "angle_index": int(target["angle_index"]),
                        "path": str(target["path"]),
                    }
                    for target in targets
                ],
                **{key: value for key, value in plan.items() if key != "action"},
                message=f"Would replace internal video by DaVinci Resolve angle number for native multicam '{plan['multicam_name']}'.",
            )
        )
        return

    if not force:
        if is_machine_mode():
            raise ConfirmationRequired(
                "Machine-mode native multicam angle video replacement requires --force.",
                details={
                    "action": "multicam.replace.video",
                    "target_kind": "multicam_clip",
                    "multicam_name": multicam_name,
                    "multicam_media_id": media_id,
                    "multicam_sequence_id": sequence_id,
                    "required_option": "--force",
                },
            )
        typer.confirm("Replace internal video items inside this native multicam clip?", abort=True)

    data = native_multicam_db.replace_multicam_video(
        conn,
        multicam_name=multicam_name,
        media_id=media_id,
        sequence_id=sequence_id,
        video_targets=video_targets,
        source_in_frames=source_in_frames,
        start_frames=start_frames,
        duration_frames=duration_frames,
        allow_short_source=allow_short_source,
    )
    output(data, title="Multicam Replace Video")


@app.command("reorder-angles")
@handle_errors
def reorder_angles(
    multicam_name: str | None = typer.Option(None, "--multicam-name", help="Native multicam clip name"),
    media_id: str | None = typer.Option(None, "--media-id", help="Exact Sm2MpMedia_id for the native multicam clip"),
    sequence_id: str | None = typer.Option(None, "--sequence-id", help="Exact Sm2Sequence_id for the native multicam sequence"),
    angle_order: list[str] | None = typer.Option(
        None,
        "--angle-order",
        help="Repeatable desired angle order value; matches media path, basename, or clip name",
    ),
    angle_order_json: str | None = typer.Option(
        None,
        "--angle-order-json",
        help="Path to a JSON array or object with angle_order[] values",
    ),
    rename_tracks: bool = typer.Option(
        True,
        "--rename-tracks/--no-rename-tracks",
        help="Rename internal multicam angle tracks to Angle 1..N after reordering",
    ),
    include_audio: bool = typer.Option(
        True,
        "--include-audio/--video-only",
        help="Reorder audio angle tracks alongside video tracks when available",
    ),
    strict: bool = typer.Option(
        True,
        "--strict/--partial",
        help="Require the requested order to cover every matching track exactly once",
    ),
):
    """Reorder native multicam angle tracks/items via the Disk Project.db route."""
    requested_order = _load_angle_order_input(
        angle_order=angle_order,
        angle_order_json=angle_order_json,
    )
    enforce_mutation_policy(
        "multicam.reorder_angles",
        intended_engine="db_workaround",
        mutating=not is_dry_run(),
    )
    conn = get_connection(require_project=True)
    if is_dry_run():
        current_db = resolve_current_disk_project_db(conn)
        plan = native_multicam_db.plan_multicam_angle_reorder(
            str(current_db["project_db_path"]),
            multicam_name=multicam_name,
            media_id=media_id,
            sequence_id=sequence_id,
            angle_order=requested_order,
            rename_tracks=rename_tracks,
            include_audio=include_audio,
            strict=strict,
        )
        action = str(plan.pop("action", "multicam.reorder_angles"))
        would_change = bool(plan.pop("would_change", False))
        output(
            mutation_payload(
                action=action,
                changed=False,
                target={"kind": "multicam_clip", "name": plan["multicam_name"]},
                would_change=would_change,
                **plan,
                message=f"Would reorder native multicam angles for '{plan['multicam_name']}'.",
            )
        )
        return

    data = native_multicam_db.reorder_multicam_angles(
        conn,
        multicam_name=multicam_name,
        media_id=media_id,
        sequence_id=sequence_id,
        angle_order=requested_order,
        rename_tracks=rename_tracks,
        include_audio=include_audio,
        strict=strict,
    )
    output(data, title="Multicam Reorder Angles")


@angle_app.command("rename")
@handle_errors
def angle_rename(
    angle_number: int = typer.Option(..., "--angle", min=1, help="One-based internal multicam angle number"),
    name: str = typer.Option(..., "--name", help="New persistent angle track name"),
    multicam_name: str | None = typer.Option(None, "--multicam-name"),
    media_id: str | None = typer.Option(None, "--media-id"),
    sequence_id: str | None = typer.Option(None, "--sequence-id"),
    media_type: str = typer.Option("both", "--media-type", help="both, video, or audio"),
):
    """Rename the internal video/audio track for a native multicam angle."""
    enforce_mutation_policy("multicam.angle.rename", intended_engine="db_workaround", mutating=not is_dry_run())
    data = _run_persistent_angle_edit(
        operation="rename",
        multicam_name=multicam_name,
        media_id=media_id,
        sequence_id=sequence_id,
        angle_number=angle_number,
        media_type=media_type,
        name=name,
    )
    output(data, title="Multicam Angle Rename")


@angle_app.command("set-enabled")
@handle_errors
def angle_set_enabled(
    angle_number: int = typer.Option(..., "--angle", min=1, help="One-based internal multicam angle number"),
    enabled: bool = typer.Option(..., "--enabled/--disabled", help="Enable or disable the persistent angle track"),
    multicam_name: str | None = typer.Option(None, "--multicam-name"),
    media_id: str | None = typer.Option(None, "--media-id"),
    sequence_id: str | None = typer.Option(None, "--sequence-id"),
    media_type: str = typer.Option("both", "--media-type", help="both, video, or audio"),
):
    """Enable or disable native multicam angle tracks using the verified track-state DB bit."""
    enforce_mutation_policy("multicam.angle.set_enabled", intended_engine="db_workaround", mutating=not is_dry_run())
    data = _run_persistent_angle_edit(
        operation="set_enabled",
        multicam_name=multicam_name,
        media_id=media_id,
        sequence_id=sequence_id,
        angle_number=angle_number,
        media_type=media_type,
        enabled=enabled,
    )
    output(data, title="Multicam Angle Set Enabled")


@angle_app.command("remove")
@handle_errors
def angle_remove(
    angle_number: int = typer.Option(..., "--angle", min=1, help="One-based internal multicam angle number"),
    multicam_name: str | None = typer.Option(None, "--multicam-name"),
    media_id: str | None = typer.Option(None, "--media-id"),
    sequence_id: str | None = typer.Option(None, "--sequence-id"),
    force: bool = typer.Option(False, "--force", "-f", help="Confirm removal of the internal video/audio angle"),
):
    """Remove one complete native multicam angle while retaining at least two angles."""
    enforce_mutation_policy("multicam.angle.remove", intended_engine="db_workaround", mutating=not is_dry_run())
    if not is_dry_run() and not force:
        if is_machine_mode():
            raise ConfirmationRequired(
                "Machine-mode multicam angle removal requires --force.",
                details={"action": "multicam.angle.remove", "required_option": "--force"},
            )
        typer.confirm("Remove this internal multicam video/audio angle?", abort=True)
    data = _run_persistent_angle_edit(
        operation="remove_angle",
        multicam_name=multicam_name,
        media_id=media_id,
        sequence_id=sequence_id,
        angle_number=angle_number,
    )
    output(data, title="Multicam Angle Remove")


@source_app.command("move")
@handle_errors
def source_move(
    angle_number: int = typer.Option(..., "--angle", min=1, help="One-based internal multicam angle number"),
    item_index: int = typer.Option(..., "--item-index", min=0, help="Zero-based source item index within the angle"),
    record_start_frame: int = typer.Option(..., "--record-start-frame", min=0, help="New start relative to multicam start"),
    multicam_name: str | None = typer.Option(None, "--multicam-name"),
    media_id: str | None = typer.Option(None, "--media-id"),
    sequence_id: str | None = typer.Option(None, "--sequence-id"),
    media_type: str = typer.Option("both", "--media-type", help="both, video, or audio"),
):
    """Move one distinct source item, linked in video and audio by default."""
    enforce_mutation_policy("multicam.source.move", intended_engine="db_workaround", mutating=not is_dry_run())
    data = _run_persistent_angle_edit(
        operation="move_item",
        multicam_name=multicam_name,
        media_id=media_id,
        sequence_id=sequence_id,
        angle_number=angle_number,
        media_type=media_type,
        item_index=item_index,
        record_start_frame=record_start_frame,
    )
    output(data, title="Multicam Source Move")


@source_app.command("remove")
@handle_errors
def source_remove(
    angle_number: int = typer.Option(..., "--angle", min=1, help="One-based internal multicam angle number"),
    item_index: int = typer.Option(..., "--item-index", min=0, help="Zero-based source item index within the angle"),
    multicam_name: str | None = typer.Option(None, "--multicam-name"),
    media_id: str | None = typer.Option(None, "--media-id"),
    sequence_id: str | None = typer.Option(None, "--sequence-id"),
    media_type: str = typer.Option("both", "--media-type", help="both, video, or audio"),
    force: bool = typer.Option(False, "--force", "-f", help="Confirm source item removal"),
):
    """Remove one distinct source item from video and audio tracks by default."""
    enforce_mutation_policy("multicam.source.remove", intended_engine="db_workaround", mutating=not is_dry_run())
    if not is_dry_run() and not force:
        if is_machine_mode():
            raise ConfirmationRequired(
                "Machine-mode multicam source removal requires --force.",
                details={"action": "multicam.source.remove", "required_option": "--force"},
            )
        typer.confirm("Remove this distinct multicam video/audio source item?", abort=True)
    data = _run_persistent_angle_edit(
        operation="remove_item",
        multicam_name=multicam_name,
        media_id=media_id,
        sequence_id=sequence_id,
        angle_number=angle_number,
        media_type=media_type,
        item_index=item_index,
    )
    output(data, title="Multicam Source Remove")


@source_app.command("property-set")
@handle_errors
def source_property_set(
    key: str = typer.Argument(..., help="Media Pool clip property key, including camera RAW properties exposed by DaVinci Resolve"),
    value: str = typer.Argument(..., help="Requested property value"),
    angle_number: int = typer.Option(..., "--angle", min=1, help="One-based internal multicam angle number"),
    record_frame: int = typer.Option(..., "--record-frame", min=0, help="Frame relative to the multicam start inside the desired source item"),
    multicam_name: str | None = typer.Option(None, "--multicam-name"),
    media_id: str | None = typer.Option(None, "--media-id"),
    sequence_id: str | None = typer.Option(None, "--sequence-id"),
    media_type: str = typer.Option("video", "--media-type", help="video or audio"),
):
    """Set and read back a property on an exact Media Pool source nested in a multicam angle."""
    enforce_mutation_policy("multicam.source.property_set", intended_engine="api_native", mutating=not is_dry_run())
    conn = get_connection(require_project=True)
    current_db = resolve_current_disk_project_db(conn)
    target = {
        "multicam_name": multicam_name,
        "media_id": media_id,
        "sequence_id": sequence_id,
        "angle_number": angle_number,
        "record_frame": record_frame,
        "media_type": media_type,
    }
    if is_dry_run():
        resolved = multicam_source.resolve_angle_source(
            conn,
            project_db_path=str(current_db["project_db_path"]),
            **target,
        )
        resolved.pop("clip", None)
        output(
            mutation_payload(
                action="multicam.source.property_set",
                changed=False,
                target={"kind": "multicam_source", "name": resolved["media_pool"].get("name")},
                key=key,
                value=value,
                resolved=resolved,
                runtime_validation="performed",
                message=f"Would set multicam source property {key} = {value}.",
            )
        )
        return
    data = multicam_source.set_angle_source_property(
        conn,
        project_db_path=str(current_db["project_db_path"]),
        key=key,
        value=value,
        **target,
    )
    output(data, title="Multicam Source Property Set")


@source_app.command("grade-cdl")
@handle_errors
def source_grade_cdl(
    angle_number: int = typer.Option(..., "--angle", min=1, help="One-based internal multicam angle number"),
    record_frame: int = typer.Option(..., "--record-frame", min=0, help="Frame relative to the multicam start inside the desired source item"),
    multicam_name: str | None = typer.Option(None, "--multicam-name"),
    media_id: str | None = typer.Option(None, "--media-id"),
    sequence_id: str | None = typer.Option(None, "--sequence-id"),
    version_name: str = typer.Option("CutAgent Multicam Source Grade", "--version-name", help="Remote/source grade version name"),
    node: int = typer.Option(
        1,
        "--node",
        min=1,
        max=1,
        help="Color node index; currently node 1 only because higher nodes lack reliable CDL readback",
    ),
    slope: str | None = typer.Option(None, "--slope", help="CDL slope as R G B"),
    offset: str | None = typer.Option(None, "--offset", help="CDL offset as R G B"),
    power: str | None = typer.Option(None, "--power", help="CDL power as R G B"),
    saturation: float | None = typer.Option(None, "--sat", help="CDL saturation"),
):
    """Validate a nested multicam source CDL target; mutation is currently unavailable."""
    enforce_mutation_policy("multicam.source.grade_cdl", intended_engine="not_available", mutating=not is_dry_run())
    conn = get_connection(require_project=True)
    current_db = resolve_current_disk_project_db(conn)
    target = {
        "multicam_name": multicam_name,
        "media_id": media_id,
        "sequence_id": sequence_id,
        "angle_number": angle_number,
        "record_frame": record_frame,
        "media_type": "video",
    }
    data = multicam_source.apply_angle_source_cdl(
        conn,
        project_db_path=str(current_db["project_db_path"]),
        version_name=version_name,
        node=node,
        slope=slope,
        offset=offset,
        power=power,
        saturation=saturation,
        **target,
    )
    output(data, title="Multicam Source Grade CDL")


@source_app.command("raw-braw-set")
@handle_errors
def source_raw_braw_set(
    angle_number: int = typer.Option(..., "--angle", min=1, help="One-based internal multicam angle number"),
    record_frame: int = typer.Option(..., "--record-frame", min=0, help="Frame relative to the multicam start inside the desired source item"),
    multicam_name: str | None = typer.Option(None, "--multicam-name"),
    media_id: str | None = typer.Option(None, "--media-id"),
    sequence_id: str | None = typer.Option(None, "--sequence-id"),
    settings_json: str | None = typer.Option(None, "--settings-json", help="BRAW SDK sidecar JSON patch for any persistent RAW processing key"),
    iso: int | None = typer.Option(None, "--iso", min=1, help="Per-frame Blackmagic RAW ISO"),
    exposure: float | None = typer.Option(None, "--exposure", help="Per-frame Blackmagic RAW exposure in stops"),
    white_balance_kelvin: int | None = typer.Option(None, "--white-balance-kelvin", min=1),
    white_balance_tint: float | None = typer.Option(None, "--white-balance-tint"),
):
    """Set exact Blackmagic RAW angle-source settings through a verified BRAW sidecar."""
    enforce_mutation_policy("multicam.source.raw_braw_set", intended_engine="api_native", mutating=not is_dry_run())
    raw_settings: dict[str, Any] = {}
    if str(settings_json or "").strip():
        try:
            parsed = json.loads(str(settings_json))
        except json.JSONDecodeError as exc:
            raise ValidationError("--settings-json must be valid JSON.", details={"error": str(exc)}) from exc
        if not isinstance(parsed, dict):
            raise ValidationError("--settings-json must contain a JSON object.")
        raw_settings.update(parsed)
    for key, value in {
        "iso": iso,
        "exposure": exposure,
        "white_balance_kelvin": white_balance_kelvin,
        "white_balance_tint": white_balance_tint,
    }.items():
        if value is not None:
            raw_settings[key] = value
    if not raw_settings:
        raise ValidationError(
            "Provide --settings-json or at least one typed BRAW setting.",
            details={"typed_options": ["--iso", "--exposure", "--white-balance-kelvin", "--white-balance-tint"]},
        )

    conn = get_connection(require_project=True)
    current_db = resolve_current_disk_project_db(conn)
    target = {
        "multicam_name": multicam_name,
        "media_id": media_id,
        "sequence_id": sequence_id,
        "angle_number": angle_number,
        "record_frame": record_frame,
        "media_type": "video",
    }
    if is_dry_run():
        resolved = multicam_source.resolve_angle_source(
            conn,
            project_db_path=str(current_db["project_db_path"]),
            **target,
        )
        resolved.pop("clip", None)
        output(
            mutation_payload(
                action="multicam.source.raw_braw_set",
                changed=False,
                target={"kind": "multicam_source", "name": resolved["media_pool"].get("name")},
                raw_settings=raw_settings,
                resolved=resolved,
                runtime_validation="performed",
                message="Would patch and DaVinci Resolve-verify the exact angle source BRAW sidecar.",
            )
        )
        return
    data = multicam_source.apply_angle_source_braw_sidecar(
        conn,
        project_db_path=str(current_db["project_db_path"]),
        raw_settings=raw_settings,
        **target,
    )
    output(data, title="Multicam Source Blackmagic RAW Set")


@app.command("seed-timeline")
@handle_errors
def seed_timeline(
    multicam_name: str | None = typer.Option(None, "--multicam-name", help="Native multicam clip name"),
    media_id: str | None = typer.Option(None, "--media-id", help="Exact Sm2MpMedia_id for the native multicam clip"),
    folder: str | None = typer.Option(None, "--folder", help="Optional Media Pool folder path to disambiguate duplicate multicam names"),
    timeline_name: str | None = typer.Option(None, "--timeline", help="Target timeline name; defaults to the active timeline"),
    record_frame: str | None = typer.Option(None, "--record-frame", help="Record-domain frame, timecode, seconds, or frames offset for the V1 append"),
    absolute_record_frame: int | None = typer.Option(None, "--absolute-record-frame", min=0, help="Exact DaVinci Resolve API recordFrame; no timeline-start offset is applied"),
    require_empty: bool = typer.Option(False, "--require-empty", help="Fail unless the target timeline has no video/audio items"),
    reset_first: bool = typer.Option(False, "--reset-first", help="Clear video/audio timeline items before appending, preserving tracks"),
    force: bool = typer.Option(False, "--force", "-f", help="Confirm reset-first timeline item deletion"),
):
    """Append a native multicam clip to V1 of a target timeline."""
    enforce_mutation_policy(
        "multicam.seed_timeline",
        intended_engine="db_workaround",
        mutating=not is_dry_run(),
    )
    conn = get_connection(require_project=True)
    current_db = resolve_current_disk_project_db(conn)
    if is_dry_run():
        plan = native_multicam_db.plan_multicam_timeline_seed(
            conn,
            project_db_path=str(current_db["project_db_path"]),
            multicam_name=multicam_name,
            media_id=media_id,
            folder=folder,
            timeline_name=timeline_name,
            record_frame=record_frame,
            absolute_record_frame=absolute_record_frame,
            require_empty=require_empty,
            reset_first=reset_first,
        )
        output(
            mutation_payload(
                action=plan["action"],
                changed=False,
                target=plan["target"],
                would_change=bool(plan.get("ready")),
                runtime_validation="performed",
                **{key: value for key, value in plan.items() if key not in {"action", "target"}},
                message=f"Would seed native multicam '{plan['multicam_name']}' onto V1.",
            )
        )
        return

    if reset_first and not force:
        if is_machine_mode():
            raise ConfirmationRequired(
                "Machine-mode native multicam timeline seed reset requires --force.",
                details={
                    "action": "multicam.seed_timeline",
                    "target_kind": "timeline",
                    "timeline_name": timeline_name,
                    "required_option": "--force",
                },
            )
        typer.confirm("Clear video/audio timeline items before seeding this multicam?", abort=True)

    data = native_multicam_db.seed_multicam_timeline(
        conn,
        project_db_path=str(current_db["project_db_path"]),
        multicam_name=multicam_name,
        media_id=media_id,
        folder=folder,
        timeline_name=timeline_name,
        record_frame=record_frame,
        absolute_record_frame=absolute_record_frame,
        require_empty=require_empty,
        reset_first=reset_first,
    )
    output(data, title="Multicam Seed Timeline")


@app.command("verdict-list")
@handle_errors
def verdict_list(
    registry_path: str | None = typer.Option(None, "--registry-path", help="Optional manual UI verdict registry path"),
):
    """List repo-recorded manual DaVinci Resolve UI verdicts for multicam families."""
    data = multicam_ui_verdicts.list_manual_multicam_ui_verdicts(path_override=registry_path)
    output(data, title="Multicam Verdict List")


@app.command("verdict-set")
@handle_errors
def verdict_set(
    status: str = typer.Option(..., "--status", help="Manual UI verdict status: ui_confirmed or ui_rejected"),
    multicam_name: str | None = typer.Option(None, "--multicam-name", help="Exact multicam clip name to match"),
    clip_name_pattern: str | None = typer.Option(None, "--clip-name-pattern", help="Regex pattern used to match multicam clip names"),
    angle_count: int | None = typer.Option(None, "--angle-count", help="Optional angle count filter for the verdict rule"),
    label: str | None = typer.Option(None, "--label", help="Human-readable verdict label"),
    verified_on: str | None = typer.Option(None, "--verified-on", help="Absolute verification date in YYYY-MM-DD format"),
    note: list[str] | None = typer.Option(None, "--note", help="Repeatable note entry stored with the verdict"),
    rule_id: str | None = typer.Option(None, "--rule-id", help="Optional stable rule id to update"),
    registry_path: str | None = typer.Option(None, "--registry-path", help="Optional manual UI verdict registry path"),
):
    """Create or update a repo-recorded manual DaVinci Resolve UI verdict."""
    enforce_mutation_policy(
        "multicam.verdict_set",
        intended_engine="api_native",
        mutating=not is_dry_run(),
    )
    if bool(multicam_name) == bool(clip_name_pattern):
        raise ValidationError(
            "Provide exactly one of --multicam-name or --clip-name-pattern.",
            details={
                "multicam_name": multicam_name,
                "clip_name_pattern": clip_name_pattern,
            },
        )
    patterns = [clip_name_pattern] if clip_name_pattern else [rf"^{re.escape(str(multicam_name or '').strip())}$"]
    normalized_options = multicam_ui_verdicts.validate_manual_multicam_ui_verdict_options(
        status=status,
        verified_on=verified_on,
    )
    if is_dry_run():
        dry_run_message(
            f"Would record manual multicam UI verdict '{normalized_options['status']}' for pattern '{patterns[0]}'."
        )
        return

    data = multicam_ui_verdicts.upsert_manual_multicam_ui_verdict(
        status=str(normalized_options["status"]),
        label=label,
        angle_count=angle_count,
        clip_name_patterns=patterns,
        notes=list(note or []),
        verified_on=normalized_options["verified_on"],
        rule_id=rule_id,
        path_override=registry_path,
    )
    output(data, title="Multicam Verdict Set")


@app.command("verdict-clear")
@handle_errors
def verdict_clear(
    rule_id: str = typer.Option(..., "--rule-id", help="Rule id returned by multicam verdict-list or multicam inspect"),
    registry_path: str | None = typer.Option(None, "--registry-path", help="Optional manual UI verdict registry path"),
):
    """Remove a repo-recorded manual DaVinci Resolve UI verdict."""
    enforce_mutation_policy(
        "multicam.verdict_clear",
        intended_engine="api_native",
        mutating=not is_dry_run(),
    )
    normalized_rule_id = str(rule_id or "").strip()
    if not normalized_rule_id:
        raise ValidationError(
            "Manual multicam UI verdict removal requires a rule id.",
            details={"rule_id": rule_id},
        )
    if is_dry_run():
        dry_run_message(f"Would remove manual multicam UI verdict '{normalized_rule_id}'.")
        return

    data = multicam_ui_verdicts.remove_manual_multicam_ui_verdict(
        rule_id=normalized_rule_id,
        path_override=registry_path,
    )
    output(data, title="Multicam Verdict Clear")


@app.command("timeline-create")
@handle_errors
def timeline_create(
    job: str | None = typer.Option(None, "--job", help="Path to a structured multicam job JSON file"),
    job_json: str | None = typer.Option(None, "--job-json", help="Inline structured multicam job JSON"),
    cleanup_stale: bool = typer.Option(False, "--cleanup-stale", help="Remove DB-only stale target rows for this multicam/timeline name before creating"),
    replace_existing: bool = typer.Option(False, "--replace-existing", help="Alias for --cleanup-stale; live visible targets still fail"),
):
    """Create a target timeline containing a real native multicam item from a structured job."""
    payload = multicam_engine.load_multicam_job(job_path=job, job_json=job_json)
    effective_settings = multicam_engine.resolve_effective_settings(payload)
    cleanup_stale_requested = _bool_option(cleanup_stale) or _bool_option(replace_existing)
    enforce_mutation_policy(
        "multicam.timeline_create",
        intended_engine="db_workaround",
        mutating=not is_dry_run(),
    )
    if is_dry_run():
        output(
            mutation_payload(
                action="multicam.timeline_create",
                changed=False,
                target={
                    "kind": "timeline",
                    "name": effective_settings["timeline_name"],
                },
                timeline_name=effective_settings["timeline_name"],
                multicam_name=effective_settings["multicam_name"],
                sync_mode=effective_settings["sync_mode"],
                reference_source=effective_settings["reference_source"],
                angle_order=effective_settings["angle_order"],
                cleanup_stale=cleanup_stale_requested,
                source_count=len(payload.get("sources") or []),
                runtime_validation="not_performed",
                message=(
                    "Would create timeline "
                    f"'{effective_settings['timeline_name']}' containing native multicam "
                    f"'{effective_settings['multicam_name']}'."
                ),
            )
        )
        return

    conn = get_connection(require_project=True)
    _require_sdk_multicam_create_guard(conn)
    timeline_kwargs = {"cleanup_stale_targets": True} if cleanup_stale_requested else {}
    data = multicam_engine.timeline_create(conn, job=payload, **timeline_kwargs)
    output(data, title="Multicam Timeline Create")


@app.command("switch")
@handle_errors
def switch(
    multicam_name: str = typer.Option(..., "--multicam-name", help="Native multicam clip name"),
    job: str | None = typer.Option(None, "--job", help="Path to a structured multicam job JSON file"),
    job_json: str | None = typer.Option(None, "--job-json", help="Inline structured multicam job JSON"),
    angle: list[str] | None = typer.Option(
        None,
        "--angle",
        help="Repeatable source spec; repeat a label for separate sequential clips on one angle: A=camA.mov",
    ),
    timeline_name: str | None = typer.Option(None, "--timeline-name", "--timeline", help="Optional target timeline name"),
    switch_by: str | None = typer.Option(None, "--switch-by", help="Convenience switch planner: transcript or audio-activity"),
    transcript: str | None = typer.Option(None, "--transcript", help="Path to ElevenLabs Scribe v2 JSON transcript for convenience switch planning"),
    speaker_map: str | None = typer.Option(None, "--speaker-map", help="Optional explicit speaker mapping: speaker_0=A,speaker_1=B"),
    audio_source: list[str] | None = typer.Option(None, "--audio-source", help="Repeatable audio activity source spec: id=/path/audio.wav"),
    audio_angle_map: str | None = typer.Option(None, "--audio-angle-map", help="Audio activity mapping: source_id=ANGLE,source_id=ANGLE"),
    audio_target: list[str] | None = typer.Option(None, "--audio-target", help="Repeatable flexible target spec: source_id=ANGLE or source_id=ANGLE_A,ANGLE_B"),
    audio_sync: str | None = typer.Option(None, "--audio-sync", help="Audio sync mode for audio-activity: prealigned, waveform, offsets-json"),
    sync_reference_audio: str | None = typer.Option(None, "--sync-reference-audio", help="Reference camera/audio file for waveform audio sync"),
    sync_reference_angle: str | None = typer.Option(None, "--sync-reference-angle", help="Reference angle for waveform audio sync when the angle has a source path"),
    audio_offsets_json: str | None = typer.Option(None, "--audio-offsets-json", help="Path to JSON offsets object for audio-activity sync"),
    overlap_policy: str | None = typer.Option(None, "--overlap-policy", help="Overlap handling: angle/wide, dominant, hold, mark"),
    overlap_angle: str | None = typer.Option(None, "--overlap-angle", "--wide-angle", help="Multicam angle to use for overlap/wide moments"),
    analysis_window_ms: int | None = typer.Option(None, "--analysis-window-ms", min=1, help="Audio activity analysis window in milliseconds"),
    activity_floor_db: float | None = typer.Option(None, "--activity-floor-db", help="Absolute dBFS floor required for activity"),
    activity_margin_db: float | None = typer.Option(None, "--activity-margin-db", help="dB above per-source noise floor required for activity"),
    dominance_margin_db: float | None = typer.Option(None, "--dominance-margin-db", help="Leader margin in dB required before avoiding overlap handling"),
    min_switch_ms: int | None = typer.Option(None, "--min-switch-ms", min=0, help="Minimum planned video switch duration in milliseconds"),
    switch_delay_ms: int | None = typer.Option(None, "--switch-delay-ms", min=0, help="New audio target must persist this long before switching"),
    max_silence_hold_ms: int | None = typer.Option(None, "--max-silence-hold-ms", min=0, help="Hold previous angle through silence up to this duration"),
    video_source_offset: list[str] | None = typer.Option(None, "--video-source-offset", help="Per-angle source-frame offset for rendered video: A=104"),
    video_only: bool = typer.Option(False, "--video-only", help="Apply multicam angle switches to timeline video only and preserve timeline audio"),
    audio_only: bool = typer.Option(False, "--audio-only", help="Apply multicam angle switches to timeline audio only and leave timeline video untouched"),
    plan_only: bool = typer.Option(False, "--plan-only", help="Build and return the multicam switch plan without connecting to DaVinci Resolve or applying it"),
    write_plan: str | None = typer.Option(None, "--write-plan", help="Optional JSON path to write the generated switch plan"),
    replace_active_timeline: bool = typer.Option(True, "--replace-active-timeline/--new-timeline", help="Rewrite the current active timeline or create/target another one from the job plan"),
):
    """Apply a structured native multicam switch plan."""
    video_only = bool(_typer_default(video_only, False))
    audio_only = bool(_typer_default(audio_only, False))
    if video_only and audio_only:
        raise ValidationError(
            "Multicam switch cannot be both --video-only and --audio-only.",
            details={"video_only": video_only, "audio_only": audio_only},
        )
    switch_scope = "video" if video_only else "audio" if audio_only else "linked"
    plan_only = bool(_typer_default(plan_only, False))
    write_plan = _typer_default(write_plan)
    replace_active_timeline = bool(_typer_default(replace_active_timeline, True))
    payload = _load_multicam_job_input(
        operation="switch",
        job=job,
        job_json=job_json,
        angle_specs=angle,
        timeline_name=timeline_name,
        multicam_name=multicam_name,
        switch_by=switch_by,
        transcript_path=transcript,
        speaker_map=speaker_map,
        audio_source_specs=audio_source,
        audio_angle_map=audio_angle_map,
        audio_target_specs=audio_target,
        audio_sync=audio_sync,
        sync_reference_audio=sync_reference_audio,
        sync_reference_angle=sync_reference_angle,
        audio_offsets_json=audio_offsets_json,
        overlap_policy=overlap_policy,
        overlap_angle=overlap_angle,
        analysis_window_ms=analysis_window_ms,
        activity_floor_db=activity_floor_db,
        activity_margin_db=activity_margin_db,
        dominance_margin_db=dominance_margin_db,
        min_switch_ms=min_switch_ms,
        switch_delay_ms=switch_delay_ms,
        max_silence_hold_ms=max_silence_hold_ms,
        video_source_offset_specs=video_source_offset,
        allow_unresolved_targets=plan_only,
        replace_active_timeline=replace_active_timeline,
        allow_multicam_name_with_structured_job=True,
    )
    if plan_only:
        rule_program = payload.get("rule_program")
        if isinstance(rule_program, dict):
            rule_program["allow_unresolved_targets"] = True
    enforce_mutation_policy(
        "multicam.switch",
        intended_engine="db_workaround",
        mutating=not is_dry_run() and not plan_only,
    )
    if plan_only:
        plan_conn = _DryRunMulticamContext()
        runtime_validation = "not_performed"
        runtime_validation_error = None
        rule_kind = str((payload.get("rule_program") or {}).get("kind") or "").strip() if isinstance(payload.get("rule_program"), dict) else ""
        if rule_kind == "audio_activity_v1" and not is_dry_run():
            try:
                plan_conn = get_connection(require_project=True)
                runtime_validation = "live_project_context"
            except Exception as exc:
                runtime_validation = "dry_context_fallback"
                runtime_validation_error = str(exc)
        plan = multicam_engine.build_multicam_job_plan(plan_conn, payload)
        if str(write_plan or "").strip():
            out_path = Path(str(write_plan)).expanduser()
            if out_path.parent and not out_path.parent.exists():
                raise ValidationError(
                    "Switch plan output directory does not exist.",
                    details={"write_plan": str(out_path), "parent": str(out_path.parent)},
                )
            out_path.write_text(json.dumps(plan, indent=2), encoding="utf-8")
        output(
            mutation_payload(
                action="multicam.switch.plan",
                changed=False,
                target={"kind": "multicam_clip", "name": multicam_name},
                multicam_name=multicam_name,
                timeline_name=timeline_name or plan["timeline_settings"]["timeline_name"],
                replace_active_timeline=replace_active_timeline,
                switch_scope=switch_scope,
                segment_count=plan.get("segment_count", len(plan.get("segments") or [])),
                unresolved_segment_count=len((plan.get("audio_activity") or {}).get("unresolved_segments") or []),
                source_count=len(plan.get("sources") or []),
                plan=plan,
                write_plan=str(Path(str(write_plan)).expanduser()) if str(write_plan or "").strip() else None,
                runtime_validation=runtime_validation,
                runtime_validation_error=runtime_validation_error,
                message=f"Built native multicam switch plan for '{multicam_name}'.",
            )
        )
        return
    if is_dry_run():
        plan = multicam_engine.build_multicam_job_plan(_DryRunMulticamContext(), payload)
        output(
            mutation_payload(
                action="multicam.switch",
                changed=False,
                target={"kind": "multicam_clip", "name": multicam_name},
                multicam_name=multicam_name,
                timeline_name=timeline_name or plan["timeline_settings"]["timeline_name"],
                replace_active_timeline=replace_active_timeline,
                switch_scope=switch_scope,
                segment_count=plan.get("segment_count", len(plan.get("segments") or [])),
                source_count=len(plan.get("sources") or []),
                runtime_validation="not_performed",
                message=f"Would apply native multicam switch plan to '{multicam_name}'.",
            )
        )
        return

    conn = get_connection(require_project=True, require_timeline=replace_active_timeline)
    multicam_media_id = _require_sdk_multicam_native_identity(conn, multicam_name)
    timeline_native_id = _require_sdk_timeline_native_identity(
        conn,
        timeline_name or payload["timeline_settings"]["timeline_name"],
    )
    if replace_active_timeline:
        _require_sdk_isolated_multicam_program(
            conn,
            multicam_media_id=multicam_media_id,
            switch_scope=switch_scope,
        )
    plan = multicam_engine.build_multicam_job_plan(conn, payload)
    data = multicam_engine.multicam_switch(
        conn,
        multicam_name=multicam_name,
        plan=plan,
        timeline_name=timeline_name or plan["timeline_settings"]["timeline_name"],
        replace_active_timeline=replace_active_timeline,
        switch_scope=switch_scope,
        multicam_media_id=multicam_media_id,
        timeline_native_id=timeline_native_id,
    )
    output(data, title="Multicam Switch")


@app.command("smart-switch")
@handle_errors
def smart_switch(
    multicam_name: str = typer.Option(..., "--multicam-name", help="Native multicam clip name"),
    timeline_name: str = typer.Option(..., "--timeline", "--timeline-name", help="Target timeline name"),
    angle: list[str] | None = typer.Option(None, "--angle", help="Repeatable multicam source spec: A=/path/cam_a.mov"),
    audio_source: list[str] | None = typer.Option(None, "--audio-source", help="Repeatable isolated speaker audio: speaker_a=/path/mic_a.wav"),
    audio_angle_map: str | None = typer.Option(None, "--audio-angle-map", help="Direct isolated-audio mapping: speaker_a=A,speaker_b=B"),
    audio_sync: str = typer.Option("waveform", "--audio-sync", help="CutAgent sync engine: waveform, offsets-json, or prealigned"),
    sync_reference_audio: str | None = typer.Option(None, "--sync-reference-audio", help="Optional waveform reference file"),
    sync_reference_angle: str | None = typer.Option(None, "--sync-reference-angle", help="Optional waveform reference angle; defaults to the first angle"),
    audio_offsets_json: str | None = typer.Option(None, "--audio-offsets-json", help="Verified CutAgent offsets JSON"),
    minimum_edit_duration_ms: int = typer.Option(1200, "--minimum-edit-duration-ms", min=1),
    edit_change_delay_ms: int = typer.Option(500, "--edit-change-delay-ms", min=0),
    wide_angle_mode: str = typer.Option("automatic", "--wide-angle-mode", help="automatic or manual"),
    wide_angle: str | None = typer.Option(None, "--wide-angle", help="Required when --wide-angle-mode manual"),
    wide_angle_frequency: str = typer.Option("medium", "--wide-angle-frequency", help="off, low, medium, or high"),
    use_wide_angle_for_intro_outro: bool = typer.Option(
        True,
        "--wide-intro-outro/--no-wide-intro-outro",
        help="Open and close the cut on the wide angle",
    ),
    use_wide_angle_for_silence: bool = typer.Option(
        True,
        "--wide-silence/--no-wide-silence",
        help="Use the wide angle when no speaker is active",
    ),
    switch_mode: str = typer.Option("video-only", "--switch", help="video-only or video-and-audio"),
    use_audio_only_fast_analysis: bool = typer.Option(
        False,
        "--audio-only-fast-analysis/--audio-plus-angle-metadata",
        help="Use audio alone, or combine it with deterministic angle/shot metadata",
    ),
    analysis_window_ms: int = typer.Option(250, "--analysis-window-ms", min=1),
    activity_floor_db: float = typer.Option(-50.0, "--activity-floor-db"),
    activity_margin_db: float = typer.Option(6.0, "--activity-margin-db"),
    dominance_margin_db: float = typer.Option(4.0, "--dominance-margin-db"),
    max_silence_hold_ms: int = typer.Option(8000, "--max-silence-hold-ms", min=0),
    video_source_offset: list[str] | None = typer.Option(None, "--video-source-offset", help="Per-angle source-frame offset: A=104"),
    replace_active_timeline: bool = typer.Option(True, "--replace-active-timeline/--new-timeline"),
    plan_only: bool = typer.Option(False, "--plan-only", help="Build the persistent switch plan without applying it"),
    write_plan: str | None = typer.Option(None, "--write-plan", help="Optional JSON output path for the plan"),
):
    """Create a persistent SmartSwitch-equivalent multicam cut without GUI automation."""
    normalized_switch_mode = str(switch_mode or "").strip().lower().replace("_", "-")
    if normalized_switch_mode not in {"video-only", "video-and-audio"}:
        raise ValidationError(
            "SmartSwitch --switch must be video-only or video-and-audio.",
            details={"switch": switch_mode},
        )
    normalized_wide_mode = str(wide_angle_mode or "").strip().lower().replace("-", "_")
    if normalized_wide_mode == "manual" and not str(wide_angle or "").strip():
        raise ValidationError("SmartSwitch manual wide-angle mode requires --wide-angle.")
    job = _build_multicam_convenience_job(
        operation="switch",
        angle_specs=angle,
        timeline_name=timeline_name,
        multicam_name=multicam_name,
        switch_by="audio-activity",
        audio_source_specs=audio_source,
        audio_angle_map=audio_angle_map,
        audio_sync=audio_sync,
        sync_reference_audio=sync_reference_audio,
        sync_reference_angle=sync_reference_angle,
        audio_offsets_json=audio_offsets_json,
        overlap_policy="wide",
        overlap_angle=wide_angle if normalized_wide_mode == "manual" else None,
        analysis_window_ms=analysis_window_ms,
        activity_floor_db=activity_floor_db,
        activity_margin_db=activity_margin_db,
        dominance_margin_db=dominance_margin_db,
        min_switch_ms=minimum_edit_duration_ms,
        switch_delay_ms=edit_change_delay_ms,
        max_silence_hold_ms=max_silence_hold_ms,
        video_source_offset_specs=video_source_offset,
        allow_unresolved_targets=False,
        replace_active_timeline=replace_active_timeline,
    )
    rule_program = dict(job.get("rule_program") or {})
    rule_program["kind"] = "smart_switch_v1"
    rule_program["smart_switch"] = {
        "minimum_edit_duration_ms": minimum_edit_duration_ms,
        "edit_change_delay_ms": edit_change_delay_ms,
        "wide_angle_mode": normalized_wide_mode,
        "wide_angle": str(wide_angle or "").strip() or None,
        "wide_angle_frequency": str(wide_angle_frequency or "").strip().lower(),
        "use_wide_angle_for_intro_outro": bool(use_wide_angle_for_intro_outro),
        "use_wide_angle_for_silence": bool(use_wide_angle_for_silence),
        "switch": normalized_switch_mode.replace("-", "_"),
        "use_audio_only_fast_analysis": bool(use_audio_only_fast_analysis),
    }
    job["rule_program"] = rule_program
    switch_scope = "video" if normalized_switch_mode == "video-only" else "linked"
    enforce_mutation_policy(
        "multicam.smart_switch",
        intended_engine="db_workaround",
        mutating=not is_dry_run() and not plan_only,
    )
    if plan_only:
        try:
            plan_conn = get_connection(require_project=True)
            runtime_validation = "live_project_context"
        except Exception:
            plan_conn = _DryRunMulticamContext()
            runtime_validation = "dry_context_fallback"
        plan = multicam_engine.build_multicam_job_plan(plan_conn, job)
        if str(write_plan or "").strip():
            out_path = Path(str(write_plan)).expanduser()
            if not out_path.parent.exists():
                raise ValidationError("SmartSwitch plan output directory does not exist.", details={"parent": str(out_path.parent)})
            out_path.write_text(json.dumps(plan, indent=2), encoding="utf-8")
        output(
            mutation_payload(
                action="multicam.smart_switch.plan",
                changed=False,
                target={"kind": "timeline", "name": timeline_name},
                switch_scope=switch_scope,
                plan=plan,
                runtime_validation=runtime_validation,
                message=f"Built persistent SmartSwitch-equivalent plan for '{multicam_name}'.",
            )
        )
        return
    if is_dry_run():
        plan = multicam_engine.build_multicam_job_plan(_DryRunMulticamContext(), job)
        output(
            mutation_payload(
                action="multicam.smart_switch",
                changed=False,
                target={"kind": "timeline", "name": timeline_name},
                switch_scope=switch_scope,
                plan=plan,
                runtime_validation="not_performed",
                message=f"Would apply persistent SmartSwitch-equivalent edits to '{timeline_name}'.",
            )
        )
        return
    conn = get_connection(require_project=True, require_timeline=replace_active_timeline)
    multicam_media_id = _require_sdk_multicam_native_identity(conn, multicam_name)
    timeline_native_id = _require_sdk_timeline_native_identity(conn, timeline_name)
    if replace_active_timeline:
        _require_sdk_isolated_multicam_program(conn, multicam_media_id=multicam_media_id, switch_scope=switch_scope)
    plan = multicam_engine.build_multicam_job_plan(conn, job)
    data = multicam_engine.multicam_switch(
        conn,
        multicam_name=multicam_name,
        plan=plan,
        timeline_name=timeline_name,
        replace_active_timeline=replace_active_timeline,
        switch_scope=switch_scope,
        multicam_media_id=multicam_media_id,
        timeline_native_id=timeline_native_id,
    )
    data["smart_switch"] = dict((plan.get("audio_activity") or {}).get("smart_switch") or {})
    output(data, title="Multicam SmartSwitch")


@app.command("settings")
@handle_errors
def settings(
    job: str | None = typer.Option(None, "--job", help="Path to a structured multicam job JSON file"),
    job_json: str | None = typer.Option(None, "--job-json", help="Inline structured multicam job JSON"),
):
    """Resolve effective multicam settings from a structured job."""
    if not str(job or "").strip() and not str(job_json or "").strip():
        output(_multicam_settings_job_context(), title="Multicam Settings")
        return

    payload = multicam_engine.load_multicam_job(job_path=job, job_json=job_json)
    data = {
        "effective_settings": multicam_engine.resolve_effective_settings(payload),
        "sources": payload.get("sources") or [],
        "selection_policy_result": payload.get("selection_policy_result") or {},
    }
    output(data, title="Multicam Settings")
