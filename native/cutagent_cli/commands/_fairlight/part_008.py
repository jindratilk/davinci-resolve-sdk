"""Fairlight Sound Library selection, delete, and insert commands."""

from __future__ import annotations

def _sound_library_result_path(item: dict[str, Any]) -> str | None:
    file_info = item.get("file") if isinstance(item.get("file"), dict) else {}
    container_info = item.get("container") if isinstance(item.get("container"), dict) else {}
    raw_path = str(file_info.get("path") or "").strip()
    if raw_path:
        return raw_path
    filename = str(file_info.get("filename") or item.get("filename") or "").strip()
    container_path = str(container_info.get("path") or "").strip()
    if filename and container_path:
        candidate = Path(filename).expanduser()
        if candidate.is_absolute():
            return str(candidate)
        return str(Path(container_path).expanduser() / filename)
    return None


def _sound_library_match_summary(item: dict[str, Any], *, index: int) -> dict[str, Any]:
    file_info = item.get("file") if isinstance(item.get("file"), dict) else {}
    return {
        "result_index": int(index),
        "clip_id": item.get("clip_id"),
        "file_id": file_info.get("file_id"),
        "name": item.get("name"),
        "filename": item.get("filename") or file_info.get("filename"),
        "path": _sound_library_result_path(item),
    }


def _sound_library_number(value: Any, *, default: float | None = None) -> float | None:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _sound_library_int(value: Any, *, default: int | None = None) -> int | None:
    number = _sound_library_number(value, default=None)
    if number is None:
        return default
    return int(round(number))


def _sound_library_sync_samples(item: dict[str, Any], *, override: int | None = None) -> int:
    if override is not None:
        if override < 0:
            raise ValidationError(
                "Sound Library sync samples must be non-negative.",
                details={"sync_samples": override, "min": 0},
                recoverability="not_applicable",
            )
        return int(override)
    edit = item.get("edit") if isinstance(item.get("edit"), dict) else {}
    edit_range = edit.get("range") if isinstance(edit.get("range"), dict) else {}
    return max(0, _sound_library_int(edit_range.get("sync"), default=0) or 0)


def _sound_library_sample_rate(item: dict[str, Any]) -> int:
    file_info = item.get("file") if isinstance(item.get("file"), dict) else {}
    sample_rate = _sound_library_int(file_info.get("sample_rate"), default=0) or 0
    if sample_rate <= 0:
        raise ReadinessFailed(
            "Sound Library sync-to-playhead requires a positive sample rate in the indexed DB row.",
            details={
                "clip_id": item.get("clip_id"),
                "file_id": file_info.get("file_id"),
                "sample_rate": file_info.get("sample_rate"),
                "required_field": "FLAssetBaseFile.sample_rate",
            },
        )
    return sample_rate


def _sound_library_current_playhead(conn) -> dict[str, Any]:
    playhead = timeline_ops.get_playhead(conn)
    if not isinstance(playhead, dict) or playhead.get("frame") is None or not playhead.get("timecode"):
        raise ReadinessFailed(
            "Could not read the current playhead before Sound Library sync-to-playhead insert.",
            details={"playhead": playhead},
        )
    return playhead


def _sound_library_sync_insert_plan(
    conn,
    item: dict[str, Any],
    *,
    sync_samples_override: int | None = None,
) -> dict[str, Any]:
    sync_samples = _sound_library_sync_samples(item, override=sync_samples_override)
    file_info = item.get("file") if isinstance(item.get("file"), dict) else {}
    sample_rate = (
        _sound_library_sample_rate(item)
        if sync_samples > 0
        else max(0, _sound_library_int(file_info.get("sample_rate"), default=0) or 0)
    )
    playhead = _sound_library_current_playhead(conn)
    fps = float(getattr(conn, "fps", 0.0) or 0.0)
    if fps <= 0:
        raise ReadinessFailed(
            "Sound Library sync-to-playhead requires a positive timeline frame rate.",
            details={"fps": getattr(conn, "fps", None)},
        )
    start_frame = int(getattr(conn, "start_frame", 0) or 0)
    current_frame = int(playhead["frame"])
    if current_frame < start_frame:
        start_frame = current_frame
    sync_offset_frames = int(round((sync_samples / sample_rate) * fps)) if sync_samples > 0 else 0
    requested_insert_frame = current_frame - sync_offset_frames
    insert_frame = max(start_frame, requested_insert_frame)
    frames_clipped_at_timeline_start = max(0, start_frame - requested_insert_frame)
    computed_start_offset = 0
    if frames_clipped_at_timeline_start > 0:
        computed_start_offset = int(round((frames_clipped_at_timeline_start / fps) * sample_rate))
    file_duration = _sound_library_int(file_info.get("duration"), default=0) or 0
    if file_duration > 0 and computed_start_offset >= file_duration:
        raise ValidationError(
            "Sound Library sync point cannot be aligned because the required source offset is beyond the indexed file duration.",
            details={
                "sync_samples": sync_samples,
                "computed_start_offset_in_samples": computed_start_offset,
                "duration_samples": file_duration,
                "current_playhead": playhead,
                "timeline_start_frame": start_frame,
            },
            recoverability="manual",
        )
    insert_timecode = seconds_to_timecode(frames_to_seconds(insert_frame, fps), fps)
    return {
        "enabled": True,
        "source": "override" if sync_samples_override is not None else "FLAssetBaseClip.ed_sync",
        "sync_samples": sync_samples,
        "sample_rate": sample_rate,
        "sync_offset_frames": sync_offset_frames,
        "requested_insert_frame": requested_insert_frame,
        "insert_frame": insert_frame,
        "insert_timecode": insert_timecode,
        "computed_start_offset_in_samples": computed_start_offset,
        "frames_clipped_at_timeline_start": frames_clipped_at_timeline_start,
        "original_playhead": playhead,
    }


def _select_sound_library_insert_result(
    cursor: sqlite3.Cursor,
    *,
    query: str | None,
    clip_id: str | None,
    file_id: str | None,
    result_index: int | None,
    limit: int,
) -> tuple[dict[str, Any], list[dict[str, Any]], bool]:
    if not query and not clip_id and not file_id:
        set_verification_status("not_requested")
        raise ValidationError(
            "Sound Library insert requires a query, --clip-id, or --file-id.",
            details={
                "example": "cutagent fairlight sound-library insert footsteps --result-index 1 --json",
                "required_one_of": ["query", "--clip-id", "--file-id"],
                "api_note": "Sound Library insert is available only for DB-indexed results with a resolved file path.",
            },
            recoverability="not_applicable",
        )
    results, truncated = _query_sound_library_rows(
        cursor,
        query=query,
        clip_id=clip_id,
        file_id=file_id,
        limit=limit,
    )
    return _select_sound_library_insert_result_from_rows(
        results,
        truncated=truncated,
        query=query,
        clip_id=clip_id,
        file_id=file_id,
        result_index=result_index,
    )


def _select_sound_library_insert_result_from_rows(
    results: list[dict[str, Any]],
    *,
    truncated: bool,
    query: str | None,
    clip_id: str | None,
    file_id: str | None,
    result_index: int | None,
) -> tuple[dict[str, Any], list[dict[str, Any]], bool]:
    matches = results
    if clip_id:
        matches = [item for item in matches if str(item.get("clip_id") or "") == str(clip_id)]
    if file_id:
        matches = [
            item
            for item in matches
            if str((item.get("file") if isinstance(item.get("file"), dict) else {}).get("file_id") or "") == str(file_id)
        ]
    summaries = [_sound_library_match_summary(item, index=index) for index, item in enumerate(matches, start=1)]
    if result_index is not None:
        if result_index < 1 or result_index > len(matches):
            set_verification_status("not_requested")
            raise ValidationError(
                "Sound Library result index is out of range.",
                details={
                    "result_index": int(result_index),
                    "match_count": len(matches),
                    "matches": summaries,
                },
                recoverability="not_applicable",
            )
        return matches[result_index - 1], summaries, truncated
    if not matches:
        set_verification_status("not_requested")
        raise ValidationError(
            "Sound Library insert query did not match any indexed results.",
            details={
                "query": query,
                "clip_id": clip_id,
                "file_id": file_id,
                "truncated": truncated,
                "hint": "Use `fairlight sound-library search` first to inspect available indexed results.",
            },
            recoverability="not_applicable",
        )
    exact_selector = bool(clip_id or file_id or result_index is not None)
    if truncated and not exact_selector:
        set_verification_status("not_requested")
        raise ValidationError(
            "Sound Library insert refuses to insert from a truncated match set.",
            details={
                "query": query,
                "clip_id": clip_id,
                "file_id": file_id,
                "match_count": len(matches),
                "truncated": truncated,
                "matches": summaries,
                "hint": "Increase --limit or pass --result-index, --clip-id, or --file-id to choose one result.",
            },
            recoverability="not_applicable",
        )
    if len(matches) > 1:
        set_verification_status("not_requested")
        raise ValidationError(
            "Sound Library insert matched multiple indexed results.",
            details={
                "query": query,
                "clip_id": clip_id,
                "file_id": file_id,
                "match_count": len(matches),
                "truncated": truncated,
                "matches": summaries,
                "hint": "Pass --result-index, --clip-id, or --file-id to choose one result.",
            },
            recoverability="not_applicable",
        )
    return matches[0], summaries, truncated


@sound_library_app.command("delete")
@handle_errors
def sound_library_delete(
    query: str | None = typer.Argument(None, help="Search query or known library result name"),
    clip_id: str | None = typer.Option(None, "--clip-id", help="Exact FLAssetBaseClip_id to remove from the index"),
    file_id: str | None = typer.Option(None, "--file-id", help="Exact FLAssetBaseFile_id whose indexed clip should be removed"),
    file_path: Path | None = typer.Option(None, "--file-path", "--path", help="Exact local file path to remove from the Sound Library index"),
    result_index: int | None = typer.Option(None, "--result-index", min=1, help="1-based result index when the selector matches multiple rows"),
    limit: int = typer.Option(50, "--limit", help="Maximum DB search results to consider, 1-500"),
    all_matches: bool = typer.Option(False, "--all", help="Delete every matched index row; refuses truncated match sets"),
    delete_orphan_file_row: bool = typer.Option(
        True,
        "--delete-orphan-file-row/--keep-file-row",
        help="Delete the FLAssetBaseFile row when no remaining clip references it",
    ),
    delete_orphan_container_row: bool = typer.Option(
        True,
        "--delete-orphan-container-row/--keep-container-row",
        help="Delete the FLAssetBaseContainer row when no remaining file references it",
    ),
    database: str = typer.Option(
        "project",
        "--database",
        "--db",
        help="Sound Library DB scope: project/current-project or user/local-database",
    ),
):
    """Remove Fairlight Sound Library index rows from Project.db or DaVinci Resolve Local Database User.db."""
    limit = _validate_sound_library_limit(limit)
    database_scope = _normalize_sound_library_database(database)
    normalized_file_path = str(Path(file_path).expanduser().resolve(strict=False)) if file_path else None
    if not query and not clip_id and not file_id and not normalized_file_path:
        raise ValidationError(
            "Sound Library delete requires a query, --clip-id, --file-id, or --file-path.",
            details={
                "example": "cutagent fairlight sound-library delete footsteps --result-index 1 --json",
                "required_one_of": ["query", "--clip-id", "--file-id", "--file-path"],
                "api_note": "Sound Library delete removes selected DB index rows only; it does not delete media files from disk.",
            },
            recoverability="not_applicable",
        )
    if all_matches and result_index is not None:
        raise ValidationError(
            "Sound Library delete cannot combine --all with --result-index.",
            details={"all": bool(all_matches), "result_index": int(result_index)},
            recoverability="not_applicable",
        )
    enforce_mutation_policy("fairlight.sound_library_delete", intended_engine="db_workaround", mutating=not is_dry_run())
    if is_dry_run():
        set_execution_engine("db_workaround")
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            {
                "action": "fairlight.sound_library.delete",
                "route": "db_workaround",
                "database": database_scope,
                "dry_run": True,
                "would_search": True,
                "would_delete": True,
                "query": query,
                "clip_id": clip_id,
                "file_id": file_id,
                "file_path": normalized_file_path,
                "result_index": result_index,
                "limit": limit,
                "all_matches": bool(all_matches),
                "delete_orphan_file_row": bool(delete_orphan_file_row),
                "delete_orphan_container_row": bool(delete_orphan_container_row),
                "target": _sound_library_database_target(database_scope),
                "db_target": {"database": database_scope, "target": _sound_library_database_target(database_scope)},
                "db_write": {"tables": list(_SOUND_LIBRARY_REQUIRED_TABLES)},
                "verification": {"method": "sound_library_db_readback"},
                "limitations": {
                    "audition": "not exposed by the DaVinci Resolve scripting API",
                    "sync_to_playhead": "available for insert placement through FLAssetBaseClip.ed_sync alignment; Sound Library audition sync preview is not exposed by the DaVinci Resolve scripting API",
                    "media_file_delete": "not performed; only Sound Library DB index rows are removed",
                },
            },
            title="Fairlight Sound Library Delete Plan",
        )
        return

    conn = get_connection(require_project=True)

    def _writer(_connection, cursor, _session):
        selected, match_summaries, truncated = _select_sound_library_delete_results(
            cursor,
            query=query,
            clip_id=clip_id,
            file_id=file_id,
            file_path=normalized_file_path,
            result_index=result_index,
            all_matches=all_matches,
            limit=limit,
        )
        deleted_targets: list[dict[str, Any]] = []
        for item in selected:
            target = _sound_library_delete_target_summary(item)
            selected_clip_id = target.get("clip_id")
            selected_file_id = target.get("file_id")
            selected_container_id = target.get("container_id")
            selected_file_refs = _sound_library_reference_values(
                selected_file_id,
                target.get("file_cookie"),
                target.get("clip_file_cookie"),
            )
            selected_container_refs = _sound_library_reference_values(
                selected_container_id,
                target.get("container_cookie"),
                target.get("file_container_cookie"),
            )
            if not selected_clip_id:
                raise ReadinessFailed(
                    "Sound Library delete matched a row without a clip id.",
                    details={"target": target, "required_field": "FLAssetBaseClip_id"},
                )
            cursor.execute(
                "DELETE FROM FLAssetBaseClip WHERE CAST(FLAssetBaseClip_id AS TEXT) = ?",
                (str(selected_clip_id),),
            )
            clip_rows_deleted = max(int(cursor.rowcount or 0), 0)
            if clip_rows_deleted < 1:
                raise ReadinessFailed(
                    "Sound Library clip row was not deleted.",
                    details={"clip_id": selected_clip_id, "target": target},
                )

            file_refs_after = _sound_library_reference_count(
                cursor,
                table_name="FLAssetBaseClip",
                column_name="file_cookie",
                values=selected_file_refs,
            )
            file_rows_deleted = 0
            if delete_orphan_file_row and selected_file_id and file_refs_after == 0:
                cursor.execute(
                    "DELETE FROM FLAssetBaseFile WHERE CAST(FLAssetBaseFile_id AS TEXT) = ?",
                    (str(selected_file_id),),
                )
                file_rows_deleted = max(int(cursor.rowcount or 0), 0)

            container_refs_after = _sound_library_reference_count(
                cursor,
                table_name="FLAssetBaseFile",
                column_name="container_cookie",
                values=selected_container_refs,
            )
            container_rows_deleted = 0
            if delete_orphan_container_row and selected_container_id and container_refs_after == 0:
                cursor.execute(
                    "DELETE FROM FLAssetBaseContainer WHERE CAST(FLAssetBaseContainer_id AS TEXT) = ?",
                    (str(selected_container_id),),
                )
                container_rows_deleted = max(int(cursor.rowcount or 0), 0)

            deleted_targets.append(
                {
                    **target,
                    "clip_row_deleted": bool(clip_rows_deleted),
                    "file_row_deleted": bool(file_rows_deleted),
                    "container_row_deleted": bool(container_rows_deleted),
                    "remaining_clip_refs_for_file": int(file_refs_after),
                    "remaining_file_refs_for_container": int(container_refs_after),
                }
            )
        return {
            "action": "fairlight.sound_library.delete",
            "database": database_scope,
            "changed": True,
            "runtime_write_called": False,
            "target": _sound_library_database_target(database_scope),
            "query": query,
            "clip_id": clip_id,
            "file_id": file_id,
            "file_path": normalized_file_path,
            "result_index": result_index,
            "all_matches": bool(all_matches),
            "match_count": len(match_summaries),
            "deleted_count": len(deleted_targets),
            "matches": match_summaries,
            "deleted": deleted_targets,
            "db_write": {"tables": list(_SOUND_LIBRARY_REQUIRED_TABLES)},
            "truncated": truncated,
            "delete_orphan_file_row": bool(delete_orphan_file_row),
            "delete_orphan_container_row": bool(delete_orphan_container_row),
            "limitations": {
                "audition": "not exposed by the DaVinci Resolve scripting API",
                "sync_to_playhead": "available for insert placement through FLAssetBaseClip.ed_sync alignment; Sound Library audition sync preview is not exposed by the DaVinci Resolve scripting API",
                "media_file_delete": "not performed; only Sound Library DB index rows are removed",
            },
            "message": f"Removed Sound Library index rows from the {_sound_library_database_label(database_scope)} database.",
        }

    def _verifier(_fresh_conn, mutation_result, session):
        return _verify_sound_library_delete(
            project_db_path=session.project_db_path if hasattr(session, "project_db_path") else session["db_path"],
            deleted_targets=mutation_result["deleted"],
        )

    if database_scope == "user":
        data = _execute_sound_library_user_db_mutation(
            conn,
            context="Fairlight Sound Library delete User.db write",
            writer=_writer,
            verifier=_verifier,
        )
    else:
        data = db_session.execute_sqlite_disk_db_mutation(
            conn,
            context="Fairlight Sound Library delete DB write",
            writer=_writer,
            verifier=_verifier,
            allow_project_name_inference=True,
        )
    set_recoverability("manual")
    output(data, title="Fairlight Sound Library Delete")


@sound_library_app.command("insert")
@handle_errors
def sound_library_insert(
    query: str | None = typer.Argument(None, help="Search query or known library result name"),
    clip_id: str | None = typer.Option(None, "--clip-id", help="Exact FLAssetBaseClip_id to insert"),
    file_id: str | None = typer.Option(None, "--file-id", help="Exact FLAssetBaseFile_id to insert"),
    result_index: int | None = typer.Option(None, "--result-index", min=1, help="1-based result index when the query matches multiple rows"),
    limit: int = typer.Option(50, "--limit", help="Maximum DB search results to consider, 1-500"),
    start_offset_in_samples: int = typer.Option(0, "--start-offset-samples", help="Sample offset within source media"),
    duration_in_samples: int = typer.Option(0, "--duration-samples", help="Duration to insert in samples (0 = full available duration)"),
    sync_to_playhead: bool = typer.Option(
        False,
        "--sync-to-playhead/--no-sync-to-playhead",
        help="Align the indexed Sound Library sync point (FLAssetBaseClip.ed_sync) to the current playhead before inserting",
    ),
    sync_samples: int | None = typer.Option(
        None,
        "--sync-samples",
        min=0,
        help="Override the indexed ed_sync value, in source audio samples, when using --sync-to-playhead",
    ),
    restore_playhead: bool = typer.Option(
        True,
        "--restore-playhead/--leave-playhead",
        help="Restore the original playhead after a sync-to-playhead insert",
    ),
    check_path: bool = typer.Option(True, "--check-path/--no-check-path", help="Require the resolved Sound Library file path to exist before calling DaVinci Resolve"),
    database: str = typer.Option(
        "project",
        "--database",
        "--db",
        help="Sound Library DB scope: project/current-project or user/local-database",
    ),
):
    """Insert one DB-indexed Sound Library file on the current Fairlight track."""
    limit = _validate_sound_library_limit(limit)
    database_scope = _normalize_sound_library_database(database)
    enforce_mutation_policy("fairlight.sound_library", intended_engine="api_native", mutating=False)
    if sync_samples is not None and not sync_to_playhead:
        set_verification_status("not_requested")
        raise ValidationError(
            "--sync-samples requires --sync-to-playhead.",
            details={"sync_samples": sync_samples, "required_option": "--sync-to-playhead"},
            recoverability="not_applicable",
        )
    if sync_to_playhead and start_offset_in_samples:
        set_verification_status("not_requested")
        raise ValidationError(
            "--sync-to-playhead cannot be combined with --start-offset-samples.",
            details={
                "sync_to_playhead": True,
                "start_offset_in_samples": int(start_offset_in_samples),
                "reason": "the start offset is computed from the indexed Sound Library sync point",
            },
            recoverability="not_applicable",
        )
    if not query and not clip_id and not file_id:
        set_verification_status("not_requested")
        raise ValidationError(
            "Sound Library insert requires a query, --clip-id, or --file-id.",
            details={
                "example": "cutagent fairlight sound-library insert footsteps --result-index 1 --json",
                "required_one_of": ["query", "--clip-id", "--file-id"],
                "api_note": "Sound Library insert is available only for DB-indexed results with a resolved file path.",
            },
            recoverability="not_applicable",
        )
    if not is_dry_run():
        enforce_mutation_policy("fairlight.sound_library", intended_engine="api_native")
    if is_dry_run():
        set_verification_status("not_requested")
        set_recoverability("not_applicable")
        output(
            {
                "action": "fairlight.sound_library.insert",
                "route": "db_workaround+api_native",
                "database": database_scope,
                "dry_run": True,
                "would_search": True,
                "would_insert": True,
                "query": query,
                "clip_id": clip_id,
                "file_id": file_id,
                "result_index": result_index,
                "limit": limit,
                "start_offset_in_samples": int(start_offset_in_samples),
                "duration_in_samples": int(duration_in_samples),
                "sync_to_playhead": bool(sync_to_playhead),
                "sync_samples": sync_samples,
                "restore_playhead": bool(restore_playhead),
                "target": "current_fairlight_track_at_playhead",
                "db_target": {"database": database_scope, "target": _sound_library_database_target(database_scope)},
                "native_api": "Project.InsertAudioToCurrentTrackAtPlayhead(path, startOffsetInSamples, durationInSamples)",
                "limitations": {
                    "audition": "not exposed by the DaVinci Resolve scripting API",
                    "index_file": "use fairlight sound-library index-file PATH or index-folder FOLDER with the same --database scope to add local audio",
                    "sync_to_playhead": "available for insert by aligning FLAssetBaseClip.ed_sync with Timeline.SetCurrentTimecode plus native Project.InsertAudioToCurrentTrackAtPlayhead",
                },
            },
            title="Fairlight Sound Library Insert Plan",
        )
        return

    conn = get_connection(require_timeline=True)
    results, truncated, db_target = _query_sound_library_database(
        conn,
        database_scope=database_scope,
        query=query,
        clip_id=clip_id,
        file_id=file_id,
        limit=limit,
    )
    selected, matches, truncated = _select_sound_library_insert_result_from_rows(
        results,
        truncated=truncated,
        query=query,
        clip_id=clip_id,
        file_id=file_id,
        result_index=result_index,
    )
    resolved_path = _sound_library_result_path(selected)
    if not resolved_path:
        set_verification_status("not_requested")
        raise ReadinessFailed(
            "Sound Library result does not expose a file path that can be inserted natively.",
            details={
                "query": query,
                "selected_result": _sound_library_match_summary(selected, index=result_index or 1),
                "required_field": "FLAssetBaseFile.path or FLAssetBaseContainer.path + filename",
                "api_note": "The DaVinci Resolve insert API requires a concrete audio file path.",
            },
        )
    expanded_path = str(Path(resolved_path).expanduser())
    if check_path and not Path(expanded_path).exists():
        set_verification_status("not_requested")
        raise ReadinessFailed(
            "Sound Library result file path is not available on this machine.",
            details={
                "path": expanded_path,
                "query": query,
                "selected_result": _sound_library_match_summary(selected, index=result_index or 1),
                "recovery_hint": "Mount the Sound Library volume or rerun with --no-check-path to let DaVinci Resolve attempt the insert.",
            },
        )
    sync_plan = None
    playhead_move = None
    playhead_restore = None
    effective_start_offset_in_samples = int(start_offset_in_samples)
    if sync_to_playhead:
        sync_plan = _sound_library_sync_insert_plan(
            conn,
            selected,
            sync_samples_override=sync_samples,
        )
        effective_start_offset_in_samples = int(sync_plan["computed_start_offset_in_samples"])
        original_tc = str(sync_plan["original_playhead"]["timecode"])
        insert_tc = str(sync_plan["insert_timecode"])
        if insert_tc != original_tc:
            playhead_move = timeline_ops.set_playhead(conn, insert_tc, return_details=True)
    try:
        insert_result = fairlight_ops.insert_audio_to_current_track(
            conn,
            expanded_path,
            start_offset_in_samples=effective_start_offset_in_samples,
            duration_in_samples=duration_in_samples,
        )
    finally:
        if sync_plan is not None and restore_playhead:
            original_tc = str(sync_plan["original_playhead"]["timecode"])
            try:
                playhead_restore = timeline_ops.set_playhead(conn, original_tc, return_details=True)
            except Exception as exc:
                playhead_restore = {
                    "ok": False,
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                    "target_timecode": original_tc,
                }
    insert_verification = insert_result.get("verification") if isinstance(insert_result, dict) else None
    insert_verification_status = (
        str(insert_verification.get("status"))
        if isinstance(insert_verification, dict) and insert_verification.get("status")
        else "pending_manual"
    )
    set_verification_status(insert_verification_status)
    set_recoverability("manual")
    output(
        mutation_payload(
            action="fairlight.sound_library.insert",
            target={
                "kind": "sound_library_result",
                "name": selected.get("name"),
                "path": expanded_path,
            },
            changed=True,
            runtime_write_called=True,
            route="db_workaround+api_native",
            database=database_scope,
            db_target=db_target,
            db_readback={
                "database": _sound_library_database_label(database_scope),
                "tables": list(_SOUND_LIBRARY_REQUIRED_TABLES),
                "truncated": truncated,
            },
            native_api="Project.InsertAudioToCurrentTrackAtPlayhead(path, startOffsetInSamples, durationInSamples)",
            query=query,
            clip_id=clip_id,
            file_id=file_id,
            result_index=result_index,
            match_count=len(matches),
            matches=matches,
            selected_result=selected,
            media_path=expanded_path,
            start_offset_in_samples=effective_start_offset_in_samples,
            requested_start_offset_in_samples=int(start_offset_in_samples),
            duration_in_samples=int(duration_in_samples),
            sync_to_playhead=sync_plan,
            playhead_move=playhead_move,
            playhead_restore=playhead_restore,
            insert=insert_result,
            limitations={
                "audition": "not exposed by the DaVinci Resolve scripting API",
                "sync_to_playhead": (
                    "Sound Library insert can align the indexed FLAssetBaseClip.ed_sync point to the current playhead through "
                    "Timeline.SetCurrentTimecode plus native Project.InsertAudioToCurrentTrackAtPlayhead; Sound Library audition preview remains not exposed."
                ),
                "verification": (
                    "Clip placement is verified when DaVinci Resolve timeline item readback exposes a new or changed audio item with the expected media name; "
                    "otherwise the command reports pending_manual without using GUI automation."
                ),
            },
            message="Inserted Sound Library result on the current Fairlight track.",
        ),
        title="Fairlight Sound Library Insert",
    )


loudness_app = typer.Typer(help="Fairlight loudness operations.")
app.add_typer(loudness_app, name="loudness")

_FAIRLIGHT_LOUDNESS_DB_BLOCKER_EVIDENCE = {
    "available_db_route": "cutagent fairlight loudness info --json",
    "db_readback_command": "fairlight.loudness.info",
    "db_schema_evidence": {
        "source": "local DaVinci Resolve 20 Free Project.db schema probes",
        "sampled_project_db_count": 5,
        "read_scope": "negative_loudness_analysis_schema_probe",
        "searched_table_or_column_fragments": [
            "loud",
            "lufs",
            "true_peak",
            "bs1770",
            "ebu",
            "atsc",
            "itu",
            "integrated",
            "short_term",
            "audio_meter",
        ],
        "sampled_tables_matching_loudness_analysis": [],
        "meter_setup_columns_seen": [
            "AudioMeterDBUEnable",
            "AudioMeterAlignmentLevel",
        ],
        "analysis_result_columns_seen": [],
        "loudness_analysis_schema_found_in_samples": False,
        "offline_analysis_result_route_found_in_samples": False,
        "normalization_write_route_found_in_samples": False,
    },
    "api_setting_snapshot_evidence": {
        "source": "Project.GetSetting()/Timeline.GetSetting() snapshot via embedded DaVinci Resolve 20.3.2 Free",
        "project": "CUTAGENT_FAIRLIGHT_PARITY_20260605_175239",
        "timeline": "FL_PARITY_24FPS",
        "queryable_audio_meter_keys": [
            "limitAudioMeterAlignLevel",
            "limitAudioMeterDisplayMode",
            "limitAudioMeterHighLevel",
            "limitAudioMeterLUFS",
            "limitAudioMeterLoudnessScale",
            "limitAudioMeterLowLevel",
        ],
        "read_scope": "project/timeline loudness meter preferences only",
        "offline_analysis_supported": False,
        "normalization_supported": False,
        "live_meter_values_supported": False,
    },
    "loudness_model_evidence": {
        "read_scope": "loudness_schema_probe_and_meter_setup_signals",
        "read_consistency": "disk_project_db",
        "storage_probe": "tables/views matching loudness, LUFS, true-peak, BS.1770, EBU, ATSC, ITU, or audio-meter columns",
        "loudness_schema_probe_supported": True,
        "loudness_rows_may_be_reported": True,
        "meter_setup_signal_supported": True,
        "live_meter_values_supported": False,
        "offline_analysis_supported": False,
        "normalization_supported": False,
        "export_supported": False,
    },
    "render_loudness_normalization_boundary": {
        "blackmagic_feature_scope": "Deliver page render-time audio normalization/loudness target settings",
        "documented_as_native_feature": True,
        "equivalent_to_fairlight_loudness_analyze_or_timeline_normalize": False,
        "timeline_mutation_supported": False,
        "analysis_result_readback_supported": False,
        "command_boundary_note": (
            "DaVinci Resolve can normalize loudness during Deliver renders, but that is an export-time render setting. "
            "`fairlight loudness analyze/normalize` requires Fairlight loudness analysis or timeline normalization "
            "readback, which remains unavailable through the verified scripting/DB routes."
        ),
    },
    "native_probe_evidence": _FAIRLIGHT_LOUDNESS_NATIVE_PROBE_EVIDENCE,
    "db_blocker_note": (
        "`fairlight loudness info` can report stored loudness/LUFS/true-peak schema candidates and meter setup "
        "signals, but it is read-only evidence. It is not a verified live-meter, offline analysis, graph export, "
        "reset, timeline normalization, or render-time normalization route."
    ),
}

